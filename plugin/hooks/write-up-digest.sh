#!/bin/sh
# Replay the human half of past Claude Code sessions, in POSIX sh.
#
# The Python CLI has a richer `digest`, but the daily capture is the one job that runs on
# a clock without anyone present, so it must not depend on a runtime that macOS and
# Windows do not ship. This is the dependency-free path: git, sed, grep, sort.
#
#   write-up-digest.sh                      today, this repo
#   write-up-digest.sh --since 2026-08-01   from a date
#   write-up-digest.sh --all                every project, not just this repo
#   write-up-digest.sh --session a42107df   one session (an id prefix is enough)
#   write-up-digest.sh --projects DIR       explicit transcript root (for cron/tasks)
#
# Fidelity note: transcripts are JSONL, and this reads them with sed rather than a JSON
# parser. Every field it extracts is a flat scalar with a distinctive delimiter, which is
# why that is safe here. \uXXXX escapes are left as written; nothing else is lost.

set -u

SINCE=""
SESSION=""
ALL=0
MAXCHARS=700
PROJECTS_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --since) SINCE="${2:-}"; shift 2 ;;
    --session) SESSION="${2:-}"; shift 2 ;;
    --all) ALL=1; shift ;;
    --max-chars) MAXCHARS="${2:-700}"; shift 2 ;;
    --projects) PROJECTS_ARG="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[ -n "$SINCE" ] || [ -n "$SESSION" ] || SINCE=$(date +%Y-%m-%d)

# --projects wins over $HOME. A scheduled task does not inherit an interactive
# shell's environment, and guessing at HOME there is how this silently found nothing.
PROJECTS="${PROJECTS_ARG:-$HOME/.claude/projects}"
[ -d "$PROJECTS" ] || { echo "no Claude transcript root at $PROJECTS" >&2; exit 1; }

# Claude Code names each project dir after the cwd with [:\/.] replaced by '-'.
if [ "$ALL" = "1" ]; then
  DIRS=$(find "$PROJECTS" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
else
  here=$(pwd)
  root=$(git rev-parse --show-toplevel 2>/dev/null) && here="$root"
  enc=$(printf '%s' "$here" | sed 's/[:\/.]/-/g')
  DIRS=$(find "$PROJECTS" -mindepth 1 -maxdepth 1 -type d -name "$enc" 2>/dev/null)
  [ -n "$DIRS" ] || DIRS=$(find "$PROJECTS" -mindepth 1 -maxdepth 1 -type d -name "$enc*" 2>/dev/null)
fi
[ -n "$DIRS" ] || { echo "no transcripts for this repo; try --all" >&2; exit 1; }

TMP=$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/wu-digest.$$")
trap 'rm -f "$TMP" "$TMP.s"' EXIT INT TERM
: > "$TMP"

for d in $DIRS; do
  for f in "$d"/*.jsonl; do
    [ -f "$f" ] || continue
    sid=$(basename "$f" .jsonl)
    case "$SESSION" in "") ;; *) case "$sid" in "$SESSION"*) ;; *) continue ;; esac ;; esac

    # origin.kind=human is the only marker that separates what the person typed from tool
    # results and replayed context, both of which also carry "type":"user".
    grep '"origin":{"kind":"human"}' "$f" 2>/dev/null | while IFS= read -r line; do
      ts=$(printf '%s' "$line" | sed -n 's/.*"timestamp":"\([^"]*\)".*/\1/p')
      [ -n "$ts" ] || continue
      case "$SINCE" in "") ;; *) [ "${ts%%T*}" \< "$SINCE" ] && continue ;; esac

      br=$(printf '%s' "$line" | sed -n 's/.*"gitBranch":"\([^"]*\)".*/\1/p')
      [ -n "$br" ] || br="-"

      # Two content shapes: a bare string for a typed message, an array of blocks when
      # the message carried an image or a pasted file. Take the text either way.
      txt=$(printf '%s' "$line" | sed -n 's/.*"content":"\(.*\)"},"uuid".*/\1/p')
      [ -n "$txt" ] || txt=$(printf '%s' "$line" |
        sed -n 's/.*"type":"text","text":"\(.*\)"}[],].*/\1/p' | head -1)
      # A message typed while the model was still working arrives as a queued_command,
      # where the text lives in attachment.prompt instead of message.content.
      [ -n "$txt" ] || txt=$(printf '%s' "$line" |
        sed -n 's/.*"prompt":"\(.*\)","commandMode".*/\1/p')
      [ -n "$txt" ] || continue

      # Unescape just enough to read: newlines become separators, quotes and slashes real.
      txt=$(printf '%s' "$txt" | sed 's/\\n/ \/ /g; s/\\t/ /g; s/\\"/"/g; s/\\\\/\\/g' |
        cut -c1-"$MAXCHARS")
      printf '%s\t%s\t%s\t%s\n' "$ts" "$sid" "$br" "$txt" >> "$TMP"
    done
  done
done

[ -s "$TMP" ] || { echo "no messages found"; exit 0; }

# A resumed session replays its history into a new file, so the same message lands twice.
# Second-precision plus a prefix of the text is enough to collapse those.
sort -u -t'	' -k1,1 -k4,4 "$TMP" | sort -t'	' -k1,1 > "$TMP.s"

label="${SESSION:-$SINCE}"
count=$(wc -l < "$TMP.s" | tr -d ' ')
sessions=$(cut -f2 "$TMP.s" | sort -u | wc -l | tr -d ' ')
printf '# Write-up digest: %s\n%s user messages across %s session(s)\n' "$label" "$count" "$sessions"

last=""
while IFS='	' read -r ts sid br txt; do
  if [ "$sid" != "$last" ]; then
    printf '\n## Session %s  %s  [%s]\n' "$(printf '%s' "$sid" | cut -c1-8)" \
      "$(printf '%s' "$ts" | sed 's/T/ /; s/:[0-9][0-9]\..*//')" "$br"
    last="$sid"
  fi
  printf -- '- [%s] %s\n' "$(printf '%s' "$ts" | sed 's/.*T//; s/:[0-9][0-9]\..*//')" "$txt"
done < "$TMP.s"
