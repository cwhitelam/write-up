#!/bin/sh
# Stop-hook gate for the write-up skill.
#
# POSIX sh on purpose. Claude Code runs hook commands through `sh -c` on macOS and
# Linux and through Git Bash on Windows, so a shell script is the one form that
# needs nothing installed. This tool only makes sense inside a git repo, and Git for
# Windows ships Git Bash, so `sh` is available anywhere the tool is useful. Python is
# not: macOS ships no bundled Python 3, and Windows ships none at all.
#
# It asks for a write-up exactly once, when a branch actually looks finished, and
# then once more if real work lands after the article was written. Everything else
# is silence. A hook that cries wolf gets disabled, and a disabled hook documents
# nothing.
#
# Contract: print a JSON block decision on stdout and exit 0. Every other path exits
# 0 silently. A hook must never be the reason a session breaks, so unexpected states
# fail open rather than blocking the user.

set -u

quiet() { exit 0; }

# Reason strings are emitted inside JSON with no escaping pass, so they must contain
# no double quotes, backslashes, or newlines. Keep it that way when editing them.
block() {
  printf '{"decision":"block","reason":"%s"}\n' "$1"
  exit 0
}

payload=$(cat 2>/dev/null) || quiet

# Re-entry guard: this hook already spoke once this turn.
case "$payload" in
  *'"stop_hook_active":true'* | *'"stop_hook_active": true'*) quiet ;;
esac

command -v git >/dev/null 2>&1 || quiet

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || quiet
wt_root=$(git rev-parse --show-toplevel 2>/dev/null) || quiet
[ -n "$wt_root" ] || quiet
cd "$wt_root" 2>/dev/null || quiet

# One wiki per repository, not one per worktree: the article, the skip files and the
# config all live in the MAIN checkout, or a branch worked in .worktrees/foo would
# write its article into that worktree and lose it when the worktree is dropped. But
# every git QUESTION below (which branch, is it clean, is it pushed) must be asked
# from the worktree itself: cd-ing into the main checkout first would gate on
# whatever branch main happens to have checked out, a different branch entirely.
main_root="$wt_root"
common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
case "$common" in
  */.git) d=${common%/.git}; [ -d "$d" ] && main_root="$d" ;;
esac

# ---------------------------------------------------------------- config ----
# Scalars out of .write-up.json, read from the main checkout. Reading them with
# grep beats depending on jq, which is no more installed than python is.
CFG="$main_root/.write-up.json"
flat=""
[ -f "$CFG" ] && flat=$(tr -d '\n\r' < "$CFG" 2>/dev/null)

# The hook's own flags live inside the "hook" object. Grepping the whole file for a
# key like "enabled" reads screenshots.enabled instead whenever that block happens
# to come first, so booleans are scoped to the hook object's slice.
hook_seg=$(printf '%s' "$flat" | sed -n 's/.*"hook"[[:space:]]*:[[:space:]]*{\([^}]*\)}.*/\1/p')
[ -n "$hook_seg" ] || hook_seg="$flat"

cfg_str() { # cfg_str <key> <default>   (whole-file scope: string keys are unique)
  v=$(printf '%s' "$flat" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" 2>/dev/null |
      head -1 | sed 's/.*"\([^"]*\)"$/\1/')
  if [ -n "$v" ]; then printf '%s' "$v"; else printf '%s' "$2"; fi
}
cfg_bool() { # cfg_bool <key> <default>   (hook-object scope)
  v=$(printf '%s' "$hook_seg" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*[a-z][a-z]*" 2>/dev/null |
      head -1 | sed 's/.*[:[:space:]]//')
  case "$v" in true | false) printf '%s' "$v" ;; *) printf '%s' "$2" ;; esac
}

[ "$(cfg_bool enabled true)" = "true" ] || quiet

OUT=$(cfg_str outputDir "docs/write-ups")
DEFAULT_BRANCH=$(cfg_str defaultBranch main)
WRAPUP=$(cfg_bool wrapUp true)
DAYS=$(cfg_bool dayEntries true)

# ---------------------------------------------------------------- branch ----
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || quiet
[ -n "$branch" ] && [ "$branch" != "HEAD" ] || quiet

skip_seg=$(printf '%s' "$hook_seg" | grep -o '"skipBranches"[^]]*]' 2>/dev/null)
if [ -n "$skip_seg" ]; then
  case "$skip_seg" in *"\"$branch\""*) quiet ;; esac
else
  case "$branch" in main | master | develop) quiet ;; esac
fi

# Branch names carry slashes; left alone, feature/search would nest the article into
# a subfolder nothing ever scans.
slug=$(printf '%s' "$branch" | tr -c 'A-Za-z0-9._-' '-' | sed 's/^[-.]*//; s/[-.]*$//')
[ -n "$slug" ] || slug="work"

wiki="$main_root/$OUT"
article="$wiki/$slug.html"
[ -f "$wiki/.skip-$slug" ] && quiet

# Paths shown to the model. Relative reads nicer, but from a worktree a relative
# path resolves against the worktree and the article lands in the wrong checkout,
# which is exactly the bug this caused in the field. Absolute whenever the roots
# differ, so the instruction cannot be misresolved.
if [ "$main_root" = "$wt_root" ]; then wdisp="$OUT"; else wdisp="$wiki"; fi

# ------------------------------------------------------------ finished? ----
# Clean tree, pushed, and ahead of the default branch. Anything less is work in
# progress and gets no interruption.
[ -z "$(git status --porcelain 2>/dev/null)" ] || quiet
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1 || quiet
[ -z "$(git log '@{u}..HEAD' --oneline 2>/dev/null)" ] || quiet

base=""
for candidate in "origin/$DEFAULT_BRANCH" "$DEFAULT_BRANCH"; do
  if git rev-parse --verify --quiet "$candidate" >/dev/null 2>&1; then
    base="$candidate"
    break
  fi
done
[ -n "$base" ] || quiet
ahead=$(git rev-list --count "$base..HEAD" 2>/dev/null) || quiet
[ "${ahead:-0}" -gt 0 ] 2>/dev/null || quiet

# --------------------------------------------------------------- no article ----
if [ ! -f "$article" ]; then
  [ "$WRAPUP" = "true" ] || quiet
  block "Branch $branch is finished as far as git can tell: committed, pushed, ahead of $base, and it has no write-up yet. Invoke the write-up skill to write $wdisp/$slug.html from what you already know of this work, describing its actual state: if it is mid-review, unmerged, or has known blockers, say so in the lead and set Status to Mid-flight instead of assuming it shipped. If no write-up is wanted, create $wdisp/.skip-$slug to silence this."
fi

# ------------------------------------------------------------------ stale? ----
# Did real work land after the article was last touched? Asking git this directly
# beats comparing file mtimes, which collide within the same second and reset on
# checkout. Pathspecs are anchored with :(top) so they mean the same thing from a
# worktree as from the main checkout. A machine-local (uncommitted) article has no
# history to compare, so the gate stays quiet there.
last_doc=$(git log -1 --format=%H -- ":(top)$OUT/$slug.html" 2>/dev/null)
if [ -n "$last_doc" ]; then
  since=$(git rev-list --count "$last_doc..HEAD" -- . ":(top,exclude)$OUT/$slug.html" 2>/dev/null)
  if [ "${since:-0}" -gt 0 ] 2>/dev/null; then
    block "$since commit(s) landed on $branch after $wdisp/$slug.html was last updated. Invoke the write-up skill in REFRESH mode: append or update only the sections the new work changed, and leave the rest of the prose alone."
  fi
fi

# -------------------------------------------------------------- day entry ----
[ "$DAYS" = "true" ] || quiet
[ -f "$wiki/.skip-day-$slug" ] && quiet
today=$(date +%Y-%m-%d 2>/dev/null) || quiet
grep -q "data-day=.$today" "$article" 2>/dev/null && quiet

# An article with a journal but no machine-readable dates at all was written to some
# other shape, or predates the convention. Asking for an entry it already contains,
# every day, forever, is the failure that gets a hook switched off. Stay quiet and let
# the wrap-up and refresh gates carry the weight.
if grep -q 'class="day"' "$article" 2>/dev/null; then
  grep -q "data-day=" "$article" 2>/dev/null || quiet
fi

block "End of a working day on $branch and $today is not in the write-up Day by day section yet. Invoke the write-up skill in DAY ENTRY mode: append ONE new day entry dated $today to $wdisp/$slug.html, oldest first, with a short title and 2-5 bullets of what actually got done and decided today, from what you already hold in session context. Leave the .date div empty; the runtime fills the label from data-day. Do not touch any other section. To silence day entries for this branch, create $wdisp/.skip-day-$slug."
