#!/bin/sh
# Installer for the write-up skill. POSIX sh, no dependencies.
#
#   ./install.sh              user scope: ~/.claude/skills/write-up
#   ./install.sh --project    this repo:  .claude/skills/write-up
#   ./install.sh --uninstall  remove the skill, leave your wiki and config alone
#
# This does not edit settings.json. Wiring a hook means merging into a JSON file,
# and a sed-based merge on a config you care about is a bad trade for the twenty
# seconds it saves. The exact snippet to paste is printed at the end.

set -eu

SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCOPE="user"
MODE="install"

for arg in "$@"; do
  case "$arg" in
    --project) SCOPE="project" ;;
    --uninstall) MODE="uninstall" ;;
    -h | --help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [ "$SCOPE" = "project" ]; then
  root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "--project needs to run inside a git repository" >&2
    exit 1
  }
  BASE="$root/.claude"
else
  BASE="$HOME/.claude"
fi
DEST="$BASE/skills/write-up"

if [ "$MODE" = "uninstall" ]; then
  if [ -d "$DEST" ]; then
    rm -rf "$DEST"
    echo "removed $DEST"
  else
    echo "nothing installed at $DEST"
  fi
  echo "Your wiki, your .write-up.json and your glossary.js were left alone."
  echo "If you wired the Stop hook, remove it from settings.json yourself."
  exit 0
fi

[ -d "$SRC/plugin" ] || { echo "run this from the write-up checkout (no plugin/ next to $0)" >&2; exit 1; }

mkdir -p "$(dirname -- "$DEST")"
rm -rf "$DEST"
cp -R "$SRC/plugin" "$DEST"
chmod +x "$DEST/hooks/write-up-hook.sh" 2>/dev/null || true

echo "installed to $DEST"
echo ""
echo "Next, in each repo you want documented, create .write-up.json:"
echo "  ask Claude to run /write-up setup, or copy the example from the README."
echo ""
echo "Optional Stop hook. It asks for a write-up once, when a branch looks finished."
echo "Paste this into $BASE/settings.json:"
echo ""
# Single-quoted so the inner \" survive as JSON escapes and $HOME/$CLAUDE_PROJECT_DIR
# reach settings.json unexpanded: the hook shell resolves them at run time, which is
# what makes one settings.json portable across machines.
if [ "$SCOPE" = "project" ]; then
  HOOKCMD='sh \"$CLAUDE_PROJECT_DIR/.claude/skills/write-up/hooks/write-up-hook.sh\"'
else
  HOOKCMD='sh \"$HOME/.claude/skills/write-up/hooks/write-up-hook.sh\"'
fi
printf '  {\n    "hooks": {\n      "Stop": [\n'
printf '        { "hooks": [ { "type": "command", "command": "%s" } ] }\n' "$HOOKCMD"
printf '      ]\n    }\n  }\n'
