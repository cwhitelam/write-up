#!/usr/bin/env python3
"""Install the Write-up skill for Claude Code.

  python install.py                    # user scope: ~/.claude/skills/write-up
  python install.py --project          # this repo:  .claude/skills/write-up
  python install.py --with-hook        # also wire the Stop hook into settings.json
  python install.py --uninstall        # remove the skill (leaves your wiki alone)

Idempotent: re-running upgrades an existing install in place. Your wiki folder,
your .write-up.json, and your glossary.js are never touched.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "skill")


def user_scope():
    return os.path.join(os.path.expanduser("~"), ".claude", "skills", "write-up")


def project_scope():
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL
        ).decode().strip().replace("/", os.sep)
    except Exception:
        root = os.getcwd()
    return os.path.join(root, ".claude", "skills", "write-up")


def settings_for(dest, project):
    # dest is <scope>/.claude/skills/write-up, so settings.json is two levels up.
    if project:
        return os.path.join(os.path.dirname(os.path.dirname(dest)), "settings.json")
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def hook_command(dest):
    """The Stop-hook command line.

    A shell script, not this file: Claude Code runs hook commands through
    `sh -c` on macOS and Linux and Git Bash on Windows, so sh is the one
    interpreter present on every machine that can run this tool at all.
    Python is optional here and stays optional.
    """
    script = os.path.join(dest, "hooks", "write-up-hook.sh").replace("\\", "/")
    return 'sh "%s"' % script


def wire_hook(settings_path, dest):
    cmd = hook_command(dest)
    data = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            print("  cannot parse %s (%s). Add the hook by hand:" % (settings_path, e))
            print("    " + cmd)
            return False
        shutil.copyfile(settings_path, settings_path + ".bak")
    hooks = data.setdefault("hooks", {})
    stop = hooks.setdefault("Stop", [])
    for group in stop:
        for h in group.get("hooks", []):
            if "write-up-hook.sh" in str(h.get("command", "")):
                h["command"] = cmd  # refresh the path on re-install
                _write_json(settings_path, data)
                print("  hook already present, path refreshed")
                return True
    stop.append({"hooks": [{"type": "command", "command": cmd}]})
    _write_json(settings_path, data)
    print("  wired Stop hook into %s%s" % (
        settings_path, " (backup: settings.json.bak)" if os.path.exists(settings_path + ".bak") else ""))
    return True


def _write_json(path, data):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", action="store_true",
                    help="install into this repo instead of your home directory")
    ap.add_argument("--with-hook", action="store_true",
                    help="add the Stop hook to settings.json (backs it up first)")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()

    dest = project_scope() if args.project else user_scope()

    if args.uninstall:
        if os.path.isdir(dest):
            shutil.rmtree(dest)
            print("removed %s" % dest)
        else:
            print("nothing installed at %s" % dest)
        print("Your wiki folder and .write-up.json were left alone.")
        print("If you wired the Stop hook, remove it from settings.json by hand.")
        return 0

    if not os.path.isdir(SRC):
        print("cannot find the skill payload at %s" % SRC, file=sys.stderr)
        return 1
    if sys.version_info < (3, 8):
        print("write-up needs Python 3.8+ (found %s)" % sys.version.split()[0], file=sys.stderr)
        return 1

    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest)
    print("installed to %s" % dest)

    if args.with_hook:
        wire_hook(settings_for(dest, args.project), dest)
    else:
        print("\nOptional: the Stop hook nudges you to write it up at wrap-up.")
        print("Re-run with --with-hook, or add this to settings.json by hand:")
        print(json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command",
                                            "command": hook_command(dest)}]}]}}, indent=2))

    print("\nNext, in the repo you want documented:")
    print("  %s \"%s\" init" % ("python" if sys.platform == "win32" else "python3",
                                os.path.join(dest, "scripts", "writeup.py")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
