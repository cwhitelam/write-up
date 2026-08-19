#!/usr/bin/env python3
"""writeup.py --- the Write-up skill's toolchain.

One CLI, Python 3.8+, standard library only (Pillow is optional and only for `shot`).

  writeup.py init      set up .write-up.json and the wiki folder for this repo
  writeup.py build     regenerate index.html + manifest.js from the articles
  writeup.py digest    combine every Claude session about a branch into one story digest
  writeup.py suggest   propose glossary candidates from an article's prose
  writeup.py shot      capture a screenshot into the branch's assets folder
  writeup.py sweep     find Mid-flight articles whose pull request has merged
  writeup.py doctor    check the install and report what is missing

Every command works from anywhere inside the repo (or a git worktree of it).
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time

# Windows consoles default to the legacy code page (cp1252 on US installs) and Linux
# under LANG=C defaults to ascii, so printing anything the user wrote raises
# UnicodeEncodeError. Nothing in this file is non-ASCII; the text comes from the
# repository and from Claude transcripts, where an arrow or a smart quote is routine.
# reconfigure() has existed since 3.7 and the floor here is 3.8, but stdout is not
# always a TextIOWrapper (harnesses replace it), so the capability is checked.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
ASSET_DIR = os.path.join(SKILL_DIR, "assets")
HOOK_SCRIPT = os.path.join(SKILL_DIR, "hooks", "write-up-hook.sh")
CONFIG_NAME = ".write-up.json"

# Runtime files copied into the wiki folder. The articles load these by relative
# path, so a missing one is a silent 404 and a broken page; `build` restores them.
RUNTIME_ASSETS = {
    "write-up-ui.js": "write-up-ui.js",
    "glossary.js": "glossary.seed.js",
}

DEFAULTS = {
    "project": None,
    "outputDir": "docs/write-ups",
    "forge": {
        "type": "none",
        "repoUrl": "",
        "branchUrl": "",
        "fileUrl": "",
        "ticketUrl": "",
        "prUrl": "",
        "defaultBranch": "main",
    },
    "hook": {
        "enabled": True,
        "wrapUp": True,
        "dayEntries": True,
        "skipBranches": ["main", "master", "develop"],
    },
    "screenshots": {"enabled": True, "quality": 85},
}


# --------------------------------------------------------------------------- git


def git(*args, **kw):
    """Run a git command, return stripped stdout, or None if it failed."""
    cwd = kw.get("cwd")
    try:
        out = subprocess.check_output(
            ["git"] + list(args), stderr=subprocess.DEVNULL, cwd=cwd
        )
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return None


def repo_root(cwd=None):
    r = git("rev-parse", "--show-toplevel", cwd=cwd)
    return r.replace("/", os.sep) if r else None


def main_checkout(cwd=None):
    """The main checkout's root, even when called from inside a worktree."""
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    if not common:
        return repo_root(cwd)
    return os.path.dirname(common.replace("/", os.sep))


def current_branch(cwd=None):
    b = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    return None if not b or b == "HEAD" else b


def slug_for(name):
    """Filesystem-safe article slug for a branch or topic name.

    Branch names routinely contain '/' (feature/search, fix/login). Left alone
    that would nest the article into a subfolder the build never scans, so every
    path-forming caller goes through here.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name or "").strip("-.") or "work"


# ------------------------------------------------------------------------ config


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


HOME_OUTPUT_DIR = ".claude/write-ups"


def home_root():
    return os.path.expanduser("~")


def resolve_scope():
    """Where this invocation's wiki lives: ("<root>", "repo") or ("<home>", "home").

    Not every piece of work worth writing up is a branch. Research that answered a
    question, a data investigation, a decision reached in one long conversation: none of
    those have a repo, and before this they had nowhere to go. An initialised repo always
    wins so a project's wiki is never bypassed by accident; otherwise a home config, then
    any repo at all, then home as the last resort.
    """
    root = repo_root()
    if root and os.path.exists(config_path(root)):
        return root, "repo"
    if os.path.exists(config_path(home_root())):
        return home_root(), "home"
    if root:
        return root, "repo"
    return home_root(), "home"


def config_path(root):
    return os.path.join(root, CONFIG_NAME)


def load_config(root):
    """Config from the repo root, falling back to the main checkout's copy.

    A worktree that predates the config still resolves it, so the wiki behaves
    identically from every checkout of the same repository.
    """
    cfg = {}
    for candidate in (root, main_checkout(root)):
        if not candidate:
            continue
        p = config_path(candidate)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    cfg = json.load(fh)
                break
            except Exception as e:
                warn("could not read %s (%s); using defaults" % (p, e))
    merged = deep_merge(DEFAULTS, cfg)
    if root and os.path.normpath(root) == os.path.normpath(home_root()):
        # A home wiki has no project and no forge. "Notebook" beats the username, and
        # the output dir has to move out of the way of anything else in $HOME.
        merged.setdefault("outputDir", HOME_OUTPUT_DIR)
        if not cfg.get("outputDir"):
            merged["outputDir"] = HOME_OUTPUT_DIR
        if not merged.get("project"):
            merged["project"] = "Notebook"
    if not merged.get("project"):
        merged["project"] = os.path.basename(root.rstrip(os.sep)) if root else "Write-ups"
    return merged


def wiki_dir(root, cfg):
    """Where this repository's wiki lives: always the main checkout, never a worktree.

    A worktree's own root would give it a private wiki that disappears when the worktree
    is dropped, and leave the real front page missing that article. One repository, one
    wiki. Home scope has no worktrees, so it is unaffected.
    """
    if root and os.path.normpath(root) != os.path.normpath(home_root()):
        main = main_checkout(root)
        if main and os.path.isdir(main):
            root = main
    return os.path.join(root, *cfg["outputDir"].replace("\\", "/").split("/"))


def nl_join(entries):
    """Join manifest entries one per line, so git can merge concurrent additions."""
    if not entries:
        return ""
    return "\n  " + ",\n  ".join(entries) + "\n"

def warn(msg):
    print("write-up: " + msg, file=sys.stderr)


def die(msg, code=1):
    warn(msg)
    sys.exit(code)


# ------------------------------------------------------------------ forge detect

FORGE_TEMPLATES = {
    "github": {
        "branchUrl": "{repo}/tree/{branch}",
        "fileUrl": "{repo}/blob/{branch}/{path}",
        "ticketUrl": "{repo}/issues/{id}",
        "prUrl": "{repo}/pull/{id}",
    },
    "gitlab": {
        "branchUrl": "{repo}/-/tree/{branch}",
        "fileUrl": "{repo}/-/blob/{branch}/{path}",
        "ticketUrl": "{repo}/-/issues/{id}",
        "prUrl": "{repo}/-/merge_requests/{id}",
    },
    "bitbucket": {
        "branchUrl": "{repo}/src/{branch}/",
        "fileUrl": "{repo}/src/{branch}/{path}",
        "ticketUrl": "{repo}/issues/{id}",
        "prUrl": "{repo}/pull-requests/{id}",
    },
    "azure": {
        "branchUrl": "{repo}?version=GB{branch}",
        "fileUrl": "{repo}?path=/{path}&version=GB{branch}",
        "ticketUrl": "{org}/_workitems/edit/{id}",
        "prUrl": "{repo}/pullrequest/{id}",
    },
}


def detect_forge(remote):
    """Map a git remote URL onto a forge type and its URL patterns.

    Returns a forge dict. Unrecognised hosts get type 'none' and empty patterns,
    which the skill reads as "write plain text, do not link".
    """
    forge = dict(DEFAULTS["forge"])
    if not remote:
        return forge
    url = remote.strip()
    if url.endswith(".git"):
        url = url[:-4]
    # scp-style ssh (git@host:path) -> https
    m = re.match(r"^[\w.+-]+@([^:]+):(.+)$", url)
    if m:
        url = "https://%s/%s" % (m.group(1), m.group(2))
    url = re.sub(r"^ssh://(?:[\w.+-]+@)?", "https://", url)
    url = re.sub(r"^https://[\w.+-]+@", "https://", url)
    m = re.match(r"^https?://([^/]+)/(.+)$", url)
    if not m:
        return forge
    host, path = m.group(1), m.group(2).strip("/")

    if "dev.azure.com" in host or "visualstudio.com" in host:
        # https://dev.azure.com/org/project/_git/repo  or  ssh v3/org/project/repo
        parts = [p for p in path.split("/") if p and p != "v3"]
        if "_git" in parts:
            i = parts.index("_git")
            org_project, repo = parts[:i], parts[i + 1 :]
        elif len(parts) >= 3:
            org_project, repo = parts[:2], parts[2:]
        else:
            return forge
        if not repo:
            return forge
        base = "https://dev.azure.com/" + "/".join(org_project)
        repo_url = base + "/_git/" + repo[0]
        t = FORGE_TEMPLATES["azure"]
        forge.update(
            type="azure",
            repoUrl=repo_url,
            branchUrl=t["branchUrl"].format(repo=repo_url, branch="{branch}"),
            fileUrl=t["fileUrl"].format(repo=repo_url, path="{path}", branch="{branch}"),
            ticketUrl=t["ticketUrl"].format(org=base, id="{id}"),
            prUrl=t["prUrl"].format(repo=repo_url, id="{id}"),
        )
        return forge

    kind = (
        "github" if "github" in host
        else "gitlab" if "gitlab" in host
        else "bitbucket" if "bitbucket" in host
        else None
    )
    if not kind:
        return forge
    repo_url = "https://%s/%s" % (host, path)
    t = FORGE_TEMPLATES[kind]
    forge.update(
        type=kind,
        repoUrl=repo_url,
        branchUrl=t["branchUrl"].format(repo=repo_url, branch="{branch}"),
        fileUrl=t["fileUrl"].format(repo=repo_url, branch="{branch}", path="{path}"),
        ticketUrl=t["ticketUrl"].format(repo=repo_url, id="{id}"),
        prUrl=t["prUrl"].format(repo=repo_url, id="{id}"),
    )
    return forge


def default_branch_of(root):
    head = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", cwd=root)
    if head:
        return head.rsplit("/", 1)[-1]
    for name in ("main", "master"):
        if git("rev-parse", "--verify", "--quiet", "refs/heads/" + name, cwd=root):
            return name
    return "main"


# -------------------------------------------------------------------- init


def ensure_runtime(wdir):
    """Copy any missing runtime asset into the wiki folder. Returns what it wrote."""
    written = []
    if not os.path.isdir(wdir):
        os.makedirs(wdir)
    for dest, src in RUNTIME_ASSETS.items():
        dpath = os.path.join(wdir, dest)
        spath = os.path.join(ASSET_DIR, src)
        if os.path.exists(dpath) or not os.path.exists(spath):
            continue
        shutil.copyfile(spath, dpath)
        written.append(dest)
    return written


def cmd_init(args):
    if args.home:
        root, scope = home_root(), "home"
    else:
        root = repo_root()
        scope = "repo"
        if not root:
            root, scope = home_root(), "home"
            warn("no git repository here, setting up the home wiki instead "
                 "(%s). Use --home to ask for this explicitly." % HOME_OUTPUT_DIR)
        else:
            # A worktree's root is not the repository's root. Config written there
            # vanishes with the worktree and is invisible to every other checkout.
            main = main_checkout(root)
            if main and os.path.normpath(main) != os.path.normpath(root):
                warn("this is a worktree; the config and wiki belong to the main "
                     "checkout at %s" % main)
                root = main
    cfg_file = config_path(root)
    if os.path.exists(cfg_file) and not args.force:
        print("%s already exists (use --force to overwrite)" % CONFIG_NAME)
        cfg = load_config(root)
    else:
        if scope == "home":
            remote, forge = None, dict(DEFAULTS["forge"])
        else:
            remote = git("remote", "get-url", "origin", cwd=root)
            forge = detect_forge(remote)
            forge["defaultBranch"] = default_branch_of(root)
        cfg = deep_merge(DEFAULTS, {})
        if scope == "home":
            cfg["outputDir"] = HOME_OUTPUT_DIR
            cfg["project"] = args.project or "Notebook"
        else:
            cfg["project"] = args.project or os.path.basename(root.rstrip(os.sep))
        cfg["forge"] = forge
        with open(cfg_file, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
        print("wrote %s (forge: %s)" % (cfg_file, forge["type"]))
        if scope == "home":
            print("  home wiki: no repository, no forge, so References stay plain text.")
            print("  The Stop hook only fires inside a repository; use /write-up here.")
        elif forge["type"] == "none":
            print("  no known forge on remote %r; articles will not link to code."
                  % (remote or "<none>"))
            print("  Fill forge.fileUrl / branchUrl / ticketUrl / prUrl by hand to enable links.")

    wdir = wiki_dir(root, cfg)
    written = ensure_runtime(wdir)
    print("wiki folder: %s%s" % (wdir, ("  (+%s)" % ", ".join(written)) if written else ""))

    if args.private and scope == "home":
        warn("--private is a no-op for the home wiki: it is outside any repository "
             "already, so nothing can stage it.")
    elif args.private:
        exclude = os.path.join(
            git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root)
            or os.path.join(root, ".git"),
            "info",
            "exclude",
        )
        rel = cfg["outputDir"].rstrip("/") + "/"
        try:
            existing = ""
            if os.path.exists(exclude):
                with open(exclude, encoding="utf-8") as fh:
                    existing = fh.read()
            if rel not in existing:
                if not os.path.isdir(os.path.dirname(exclude)):
                    os.makedirs(os.path.dirname(exclude))
                with open(exclude, "a", encoding="utf-8") as fh:
                    fh.write(("" if existing.endswith("\n") or not existing else "\n") + rel + "\n")
                print("added %s to .git/info/exclude (machine-local wiki)" % rel)
            else:
                print("%s already excluded" % rel)
        except Exception as e:
            warn("could not update .git/info/exclude: %s" % e)
    elif scope == "repo":
        print("wiki is committed with the repo. Use --private to keep it machine-local instead.")

    if scope == "home":
        print("\nNext: finish something worth keeping, then ask Claude to write it up "
              "(or run /write-up). It does not have to be code.")
    else:
        print("\nNext: finish a branch, then ask Claude to write its write-up (or run /write-up).")
    return 0


# ------------------------------------------------------------------------- build


def strip_tags(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def scan_articles(wdir):
    items = []
    for f in sorted(glob.glob(os.path.join(wdir, "*.html"))):
        slug = os.path.splitext(os.path.basename(f))[0]
        if slug == "index":
            continue
        with open(f, encoding="utf-8") as fh:
            txt = fh.read()
        art = re.search(r"<article>(.*?)</article>", txt, re.S)
        art = art.group(1) if art else txt
        title_m = re.search(r"<h1>(.*?)</h1>", art, re.S)
        title = strip_tags(title_m.group(1)) if title_m else slug
        body_wo = re.sub(
            r'<div class="infobox">.*?</div>\s*(?=<p|<section)', "", art, count=1, flags=re.S
        )
        body_wo = re.sub(r'<p class="fact">.*?</p>', "", body_wo, count=1, flags=re.S)
        lead_m = re.search(r"<p>(.*?)</p>", body_wo, re.S)
        lead = strip_tags(lead_m.group(1)) if lead_m else ""
        ib = re.search(r'<div class="infobox">(.*?)</div>', art, re.S)
        ibx = ib.group(1) if ib else ""
        st_m = re.search(r"<dt>Status</dt><dd>(.*?)</dd>", ibx, re.S)
        status = strip_tags(st_m.group(1)) if st_m else ""
        tk_m = re.search(r"#(\d{1,7})", ibx)
        ticket = tk_m.group(1) if tk_m else ""
        dt_m = re.search(r"<dt>(?:Documented|Merged)</dt><dd>(.*?)</dd>", ibx, re.S)
        date = strip_tags(dt_m.group(1)) if dt_m else ""
        refs = []
        for h in re.findall(r'href="([^"/#]+)\.html"', art):
            if h not in ("index", slug) and h not in refs:
                refs.append(h)
        items.append(
            {
                "slug": slug,
                "title": title,
                "lead": lead,
                "status": status,
                "ticket": ticket,
                "date": date,
                "refs": refs,
                "body": strip_tags(art)[:8000],
            }
        )
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def cmd_build(args):
    root = None if args.dir else resolve_scope()[0]
    cfg = load_config(root) if root else deep_merge(DEFAULTS, {"project": None})
    if root:
        wdir = args.dir or wiki_dir(root, cfg)
    else:
        wdir = args.dir
        cfg["project"] = args.project or os.path.basename(os.path.dirname(os.path.abspath(wdir)))
    if args.project:
        cfg["project"] = args.project
    if not cfg.get("project"):
        cfg["project"] = "Write-ups"
    if not os.path.isdir(wdir):
        die("no wiki folder at %s (run: writeup.py init)" % wdir)

    restored = ensure_runtime(wdir)
    items = scan_articles(wdir)

    with open(os.path.join(wdir, "manifest.js"), "w", encoding="utf-8", newline="\n") as fh:
        # One article per line, not one long line. Two people adding articles on two
        # branches both touch this file, and a single multi-kilobyte line makes that an
        # unmergeable conflict every time. Per-line entries let git merge the common case
        # by itself, and leave a readable conflict when it cannot.
        fh.write("window.WRITEUPS = [" + nl_join([
            json.dumps(it, ensure_ascii=False, sort_keys=True) for it in items
        ]) + "];\n")

    tpl_path = os.path.join(ASSET_DIR, "index-template.html")
    if not os.path.exists(tpl_path):
        # Fail loudly and non-zero. A quiet aside here lets the front page rot
        # unnoticed while new articles pile up behind it.
        print("wrote manifest.js (%d articles)" % len(items))
        die("index-template.html missing at %s; index.html NOT regenerated "
            "and the front page is now stale" % tpl_path, 2)

    with open(tpl_path, encoding="utf-8") as fh:
        tpl = fh.read()
    project = cfg["project"]
    idx_path = os.path.join(wdir, "index.html")
    esc = lambda s: html.escape(s, quote=True)

    rows = []
    for b in items:
        full = b["lead"]
        cut = full.find(". ")
        if 40 <= cut <= 200:
            lead = full[: cut + 1]
        elif len(full) > 180:
            lead = full[:180].rsplit(" ", 1)[0] + "..."
        else:
            lead = full
        meta = (b["date"] or "") + " &middot; <code>" + esc(b["slug"]) + "</code>"
        if b["status"]:
            meta += " &middot; " + esc(b["status"])
        rows.append(
            '    <li class="entry">\n'
            '      <a class="t" href="' + esc(b["slug"]) + '.html">' + esc(b["title"]) + "</a>\n"
            "      <p>" + esc(lead) + "</p>\n"
            '      <span class="m">' + meta + "</span>\n"
            "    </li>"
        )
    # A project named after the artifact itself ("Write-up", "writeups") would
    # otherwise render as "Write-up Write-ups". Drop the redundant half.
    flat = re.sub(r"[^a-z]", "", project.lower())
    stutters = flat.endswith("writeup") or flat.endswith("writeups")
    out = tpl.replace("{{PROJECT}}", esc(project))
    out = out.replace("{{SUFFIX}}", "" if stutters else " Write-ups")
    out = out.replace("{{TAG}}", "wiki" if stutters else "write-ups")
    # A wiki published somewhere public (GitHub Pages, an internal host) is read
    # by people who never saw the repo, so link it back when the forge is known.
    repo_url = (cfg.get("forge") or {}).get("repoUrl") or ""
    out = out.replace(
        "{{REPOLINK}}",
        '<p class="sub"><a href="%s">%s</a></p>'
        % (esc(repo_url), esc(re.sub(r"^https?://", "", repo_url)))
        if repo_url
        else "",
    )
    out = re.sub(
        r'(<ol class="entries">).*?(</ol>)',
        lambda m: m.group(1) + "\n" + "\n".join(rows) + "\n  " + m.group(2),
        out,
        flags=re.S,
        count=1,
    )
    with open(idx_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    print(
        'wrote manifest.js + index.html (%d article%s, project="%s")%s'
        % (
            len(items),
            "" if len(items) == 1 else "s",
            project,
            ("  [restored %s]" % ", ".join(restored)) if restored else "",
        )
    )
    return 0


# ------------------------------------------------------------------------ digest


def encoded_project_dirs(proj_root, root, all_projects):
    """Claude keys transcript folders by the encoded cwd ([:\\/.] -> -).

    Match every checkout of this repo: the main checkout and any worktree whose
    path starts with it, plus sibling worktrees named after the repo folder.
    """
    if not os.path.isdir(proj_root):
        return []
    dirs = [
        os.path.join(proj_root, d)
        for d in os.listdir(proj_root)
        if os.path.isdir(os.path.join(proj_root, d))
    ]
    if all_projects:
        return dirs
    mainroot = main_checkout(root) or root
    enc = re.sub(r"[:\\/.]", "-", mainroot)
    name = os.path.basename(mainroot.rstrip(os.sep))
    keep = []
    for d in dirs:
        b = os.path.basename(d)
        if b.lower().startswith(enc.lower()) or ("-" + name.lower()) in b.lower():
            keep.append(d)
    return keep or dirs


def collect_events(dirs, branch=None, since=None, session=None, grep=None,
                   max_chars=700, max_summary=8000):
    """Genuine typed user messages from Claude's transcripts, in time order.

    Read-only. Assistant turns, tool traffic, sidechains and slash-command
    envelopes are dropped, so what comes back is the human half of the
    conversation: the intent, which is what a story is made of. Compaction
    summaries live inside user records, so history from before a compaction
    survives automatically.
    """
    needle = ('"gitBranch":"%s"' % branch) if branch else '"type":"user"'
    events, seen = [], set()
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if needle not in line or '"type":"user"' not in line:
                            continue
                        try:
                            r = json.loads(line)
                        except Exception:
                            continue
                        if r.get("type") != "user" or r.get("isSidechain") or r.get("isMeta"):
                            continue
                        if branch and r.get("gitBranch") != branch:
                            continue
                        sid = r.get("sessionId") or "?"
                        if session and not sid.startswith(session):
                            continue
                        ts = r.get("timestamp") or ""
                        if since and ts[:10] < since:
                            continue
                        m = r.get("message") or {}
                        if m.get("role") != "user":
                            continue
                        c = m.get("content")
                        if isinstance(c, str):
                            text = c
                        elif isinstance(c, list):
                            text = "\n".join(
                                p.get("text", "")
                                for p in c
                                if isinstance(p, dict) and p.get("type") == "text"
                            )
                        else:
                            continue
                        t = (text or "").strip()
                        if not t:
                            continue
                        if t.startswith(
                            ("<command-name>", "<local-command", "<command-message>", "Caveat:")
                        ):
                            continue
                        if grep and grep.lower() not in t.lower():
                            continue
                        cap = max_summary if t.startswith("This session is being continued") \
                            else max_chars
                        if len(t) > cap:
                            t = t[:cap] + " [...]"
                        # A resumed session replays its history into a new transcript
                        # file, so the same message is on disk more than once.
                        key = (sid, ts[:19], t[:200])   # second precision: ms can differ
                        if key in seen:
                            continue
                        seen.add(key)
                        events.append(
                            {
                                "time": ts,
                                "session": sid,
                                "branch": r.get("gitBranch") or "",
                                "dir": os.path.basename(d),
                                "text": t,
                            }
                        )
            except Exception:
                continue
    events.sort(key=lambda e: e["time"])
    return events


def group_sessions(events):
    order, groups = [], {}
    for e in events:
        if e["session"] not in groups:
            groups[e["session"]] = []
            order.append(e["session"])
        groups[e["session"]].append(e)
    return order, groups


def cmd_digest(args):
    root = repo_root()
    proj_root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(proj_root):
        die("no Claude transcript root at %s" % proj_root)
    dirs = encoded_project_dirs(proj_root, root or os.getcwd(), args.all_projects)

    # Scope. Default is the current branch, which is right when work maps onto
    # branches. --all / --since / --session / --grep cover everything else: work
    # done straight on main, a conversation you remember by date, or by a phrase.
    branch = None
    if not (args.all or args.session or args.since or args.grep or args.list):
        branch = args.branch or current_branch()
    elif args.branch:
        branch = args.branch

    events = collect_events(
        dirs, branch=branch, since=args.since, session=args.session, grep=args.grep,
        max_chars=args.max_chars, max_summary=args.max_summary,
    )

    if args.list:
        order, groups = group_sessions(events)
        if not order:
            print("No sessions found (searched %d project dir(s))." % len(dirs))
            return 0
        print("%d session(s), oldest first. Digest one with: digest --session <id>\n" % len(order))
        print("%-8s  %-16s  %5s  %-22s  %s" % ("ID", "STARTED", "MSGS", "BRANCH", "FIRST MESSAGE"))
        for sid in order:
            g = groups[sid]
            first = re.sub(r"\s+", " ", g[0]["text"])[:58]
            print("%-8s  %-16s  %5d  %-22s  %s"
                  % (sid[:8], g[0]["time"][:16].replace("T", " "), len(g),
                     (g[0]["branch"] or "-")[:22], first))
        return 0

    if not events:
        scope = (
            "branch %r" % branch if branch
            else "session %r" % args.session if args.session
            else "everything matching your filters"
        )
        print("No conversations found for %s (searched %d project dir(s))." % (scope, len(dirs)))
        return 0

    order, groups = group_sessions(events)
    label = branch or args.session or args.grep or args.since or "all work"
    print("# Write-up digest: %s" % label)
    print("%d user messages across %d session(s)" % (len(events), len(order)))
    for n, sid in enumerate(order, 1):
        g = groups[sid]
        stamp = g[0]["time"][:16].replace("T", " ")
        where = g[0]["branch"] or g[0]["dir"]
        print("")
        print("## Session %d  %s  (%s)  [%s]" % (n, stamp, sid[:8], where))
        for e in g:
            hhmm = e["time"][11:16] if len(e["time"]) >= 16 else ""
            print("- [%s] %s" % (hhmm, re.sub(r"\r?\n+", " / ", e["text"])))
    return 0


# ----------------------------------------------------------------------- suggest

DENY = {
    w.lower()
    for w in [
        "API", "JSON", "HTTP", "HTTPS", "HTML", "CSS", "XML", "URL", "URI", "ID", "UI", "UX",
        "SQL", "JS", "TS", "SDK", "JDK", "CLI", "IDE", "OS", "DI", "DTO", "CRUD", "PR", "QA",
        "CI", "CD", "TCP", "UDP", "DNS", "REST", "JWT", "iOS", "Android", "Windows", "Linux",
        "macOS", "Google", "Apple", "Microsoft", "GitHub", "GitLab", "README",
    ]
}

KNOWN = [
    "Blazor", "Razor", "React", "Vue", "Svelte", "Angular", "Next.js", "Nuxt", "Django",
    "Flask", "FastAPI", "Rails", "Laravel", "Spring Boot", "Express", "Prisma", "Drizzle",
    "SQLAlchemy", "EF Core", "Entity Framework Core", "Hibernate", "Redis", "Postgres",
    "PostgreSQL", "SQLite", "Elasticsearch", "Kafka", "RabbitMQ", "Docker", "Kubernetes",
    "Terraform", "Playwright", "Cypress", "Vitest", "Jest", "pytest", "WebAssembly", "gRPC",
    "GraphQL", "OAuth", "OIDC", "SAML", "WebSocket", "Server-Sent Events", "Serilog",
    "OpenTelemetry", "Sentry",
]

HINTS = [
    (["react", "next.js", "vue", "svelte", "angular", "nuxt"], "the framework's own docs"),
    (["blazor", "razor", "ef core", "entity framework", ".net", "maui"], "learn.microsoft.com"),
    (["docker", "kubernetes", "terraform"], "the vendor's docs"),
    (["oauth", "oidc", "jwt", "saml"], "an IETF RFC"),
    (["postgres", "sqlite", "redis", "kafka"], "the project's docs"),
]

PAREN = re.compile(r"\b([A-Z][A-Za-z0-9.\-/]{1,})\s*\(([^)]{3,60})\)")
ACR = re.compile(r"\b([A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*)\b")
DOTACR = re.compile(r"\b([A-Z](?:[-.][A-Z0-9]){1,}[A-Z0-9]?)\b")
CAMEL = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][A-Za-z0-9]+)+)\b")


def hint(term):
    t = term.lower()
    for keys, where in HINTS:
        if any(k in t for k in keys):
            return where
    return ""


def curated_aliases(wdir):
    p = os.path.join(wdir, "glossary.js")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as fh:
        txt = fh.read()
    al = set()
    for block in re.findall(r"match:\s*\[([^\]]*)\]", txt):
        for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", block):
            al.add((a or b).lower())
    for title in re.findall(r"title:\s*'([^']+)'", txt):
        al.add(title.split(" (")[0].lower())
    return al


def article_prose(txt):
    """Article text minus code, infobox, headings and refs (the runtime's exclusions)."""
    body = re.search(r"<article>(.*?)</article>", txt, re.S)
    body = body.group(1) if body else txt
    body = re.sub(r"<pre.*?</pre>", " ", body, flags=re.S)
    body = re.sub(r"<code.*?</code>", " ", body, flags=re.S)
    body = re.sub(r'<div class="infobox">.*?</div>\s*(?=<p|<section)', " ", body, flags=re.S)
    body = re.sub(r'<ol class="refs">.*?</ol>', " ", body, flags=re.S)
    body = re.sub(r"<h[1-3][^>]*>.*?</h[1-3]>", " ", body, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


def cmd_suggest(args):
    root = resolve_scope()[0]
    cfg = load_config(root)
    wdir = wiki_dir(root, cfg)
    files = args.article or [
        os.path.basename(f)
        for f in sorted(glob.glob(os.path.join(wdir, "*.html")))
        if os.path.basename(f) != "index.html"
    ]
    known = curated_aliases(wdir)
    per_article, corpus = {}, {}
    for name in files:
        path = name if os.path.isabs(name) else os.path.join(wdir, name)
        if not os.path.exists(path):
            print("skip (not found): %s" % name)
            continue
        with open(path, encoding="utf-8") as fh:
            text = article_prose(fh.read())
        found = {}
        add = lambda term, sig: found.setdefault(term.strip(), set()).add(sig)
        for m in PAREN.finditer(text):
            if sum(c.isupper() for c in m.group(1)) >= 2:
                add(m.group(1), "expansion")
        for rx, sig in ((ACR, "acronym"), (DOTACR, "acronym"), (CAMEL, "camel")):
            for m in rx.finditer(text):
                add(m.group(1), sig)
        for k in KNOWN:
            if re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", text):
                add(k, "known")
        keep = {}
        for term, sigs in found.items():
            if term.lower() in DENY or term.lower() in known or len(term) < 3:
                continue
            keep[term] = sigs
            corpus.setdefault(term, set()).add(name)
        per_article[os.path.basename(path)] = keep

    def score(term, sigs):
        s = (3 if "expansion" in sigs else 0) + (2 if "known" in sigs else 0)
        s += (1 if "camel" in sigs else 0) + (1 if "acronym" in sigs else 0)
        return s + max(0, len(corpus.get(term, [])) - 1)

    total = 0
    for name, keep in per_article.items():
        if not keep:
            continue
        print("\n=== %s ===" % name)
        for term, sigs in sorted(keep.items(), key=lambda kv: (-score(*kv), kv[0].lower())):
            used = len(corpus.get(term, []))
            h = hint(term)
            print(
                "  [%d] %-26s %-24s %s%s"
                % (
                    score(term, sigs),
                    term,
                    "/".join(sorted(sigs)),
                    ("used in %d articles" % used) if used > 1 else "",
                    ("   ~" + h) if h else "",
                )
            )
            total += 1
    print("\n%d candidate(s). Curate the winners into %s"
          % (total, os.path.join(cfg["outputDir"], "glossary.js")))
    print('(blurb + verified URL); ignore the rest, that is the OVERLINK "no".')
    return 0


# -------------------------------------------------------------------------- shot


def _win_windows():
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    wins = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left < 200 or rect.bottom - rect.top < 150:
            return True
        wins.append((hwnd, buf.value, (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(proc(cb), 0)
    return user32, wt, wins


def _grab_screen(out, quality):
    try:
        from PIL import ImageGrab

        img = ImageGrab.grab()
        img.convert("RGB").save(out, "JPEG", quality=quality)
        return out, "%dx%d" % (img.width, img.height)
    except ImportError:
        pass
    png = os.path.splitext(out)[0] + ".png"
    for cmd in (
        ["screencapture", "-x", png],
        ["import", "-window", "root", png],
        ["gnome-screenshot", "-f", png],
        ["spectacle", "-b", "-n", "-o", png],
    ):
        if shutil.which(cmd[0]):
            if subprocess.call(cmd) == 0 and os.path.exists(png):
                return png, "screen"
    die("no capture backend. Install Pillow (pip install pillow) "
        "or a screenshot tool (screencapture / ImageMagick / gnome-screenshot).")


def cmd_shot(args):
    if args.list:
        if sys.platform != "win32":
            die("--list enumerates windows on Windows only. "
                "Use --screen, or the browser tools for a web page.")
        _, _, wins = _win_windows()
        for _, title, (l, t, r, b) in wins:
            print("%5dx%-5d %s" % (r - l, b - t, title))
        return 0

    if not args.screen and not args.window:
        die("need --window <title regex>, --screen, or --list")

    out = args.out
    if not out:
        if not args.slug:
            die("need --slug (or an explicit --out)")
        root = resolve_scope()[0]
        cfg = load_config(root)
        branch = slug_for(args.branch or current_branch() or "work")
        d = os.path.join(wiki_dir(root, cfg), "assets", branch)
        if not os.path.isdir(d):
            os.makedirs(d)
        n = len([f for f in os.listdir(d) if f.lower().endswith((".jpg", ".png"))]) + 1
        out = os.path.join(d, "%02d-%s.jpg" % (n, args.slug))

    if args.screen:
        path, size = _grab_screen(out, args.quality)
    else:
        if sys.platform != "win32":
            die("--window works on Windows only. Use --screen, or capture a web page "
                "with the browser tools.")
        try:
            from PIL import ImageGrab
        except ImportError:
            die("window capture needs Pillow (pip install pillow)")
        user32, wt, wins = _win_windows()
        pat = re.compile(args.window, re.IGNORECASE)
        matches = [w for w in wins if pat.search(w[1])]
        if not matches:
            die("no visible window matches %r (try --list)" % args.window)
        if len(matches) > 1:
            warn("multiple windows match %r:" % args.window)
            for _, title, _ in matches:
                warn("  " + title)
            return 1
        hwnd, title, _ = matches[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(args.settle_ms / 1000.0)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, __import__("ctypes").byref(rect))
        # Pixels outside the virtual screen come back black, so a window hanging off
        # any edge silently yields a cut-off shot. Say so rather than shipping it.
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        if rect.left < vx or rect.top < vy or rect.right > vx + vw or rect.bottom > vy + vh:
            warn(
                "window extends off-screen (%d,%d-%d,%d vs screen %d,%d-%d,%d); the "
                "off-screen part will be cut. Move or resize it on-screen first."
                % (rect.left, rect.top, rect.right, rect.bottom, vx, vy, vx + vw, vy + vh)
            )
        img = ImageGrab.grab(
            bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True
        )
        img.convert("RGB").save(out, "JPEG", quality=args.quality)
        path, size = out, "%dx%d" % (img.width, img.height)

    kb = os.path.getsize(path) // 1024
    print("saved %s (%s, %dKB)" % (path, size, kb))
    return 0


# ------------------------------------------------------------------------- sweep


def merged_pr(cfg, branch):
    """Return (pr_id, iso_date) for a completed PR on `branch`, or None.

    Only GitHub (via the gh CLI) and Azure DevOps (via a PAT) are supported.
    Any failure returns None: a hook must never break a session.
    """
    kind = cfg["forge"]["type"]
    if kind == "github" and shutil.which("gh"):
        try:
            out = subprocess.check_output(
                ["gh", "pr", "list", "--head", branch, "--state", "merged",
                 "--limit", "1", "--json", "number,mergedAt"],
                stderr=subprocess.DEVNULL, timeout=15,
            )
            rows = json.loads(out.decode("utf-8", "replace") or "[]")
            if rows:
                return str(rows[0].get("number")), (rows[0].get("mergedAt") or "")[:10]
        except Exception:
            return None
        return None
    if kind == "azure":
        import base64
        import urllib.request

        pat = os.environ.get("AZURE_DEVOPS_PAT")
        if not pat:
            p = os.path.join(os.path.expanduser("~"), ".azure_devops_pat")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    pat = fh.read().strip()
        repo = cfg["forge"].get("repoUrl") or ""
        m = re.match(r"^(https://dev\.azure\.com/[^/]+/[^/]+)/_git/(.+)$", repo)
        if not pat or not m:
            return None
        api = (
            "%s/_apis/git/repositories/%s/pullrequests"
            "?searchCriteria.sourceRefName=refs/heads/%s"
            "&searchCriteria.status=completed&api-version=7.0" % (m.group(1), m.group(2), branch)
        )
        try:
            req = urllib.request.Request(api)
            req.add_header(
                "Authorization",
                "Basic " + base64.b64encode((":" + pat).encode()).decode(),
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            if data.get("count"):
                pr = data["value"][0]
                return str(pr.get("pullRequestId")), (pr.get("closedDate") or "")[:10]
        except Exception:
            return None
    return None


def cmd_sweep(args):
    """Report Mid-flight articles whose branch already has a merged pull request.

    This is the one feature that touches the network, so it lives here in the optional
    CLI and not in the Stop hook. A hook that makes an HTTP call is a hook that hangs.
    """
    # Sweep is about pull requests, so unlike every other command it genuinely needs a
    # repository and a forge. Say so plainly rather than failing on a missing remote.
    root = repo_root() or die("sweep needs a git repository: it looks for merged pull requests")
    cfg = load_config(root)
    wdir = wiki_dir(root, cfg)
    if not os.path.isdir(wdir):
        die("no wiki folder at %s" % wdir)

    kind = cfg["forge"]["type"]
    if kind not in ("github", "azure"):
        die("sweep supports github (via the gh CLI) and azure (via a PAT); forge is %r" % kind)

    hits = 0
    for item in scan_articles(wdir):
        if (item.get("status") or "").lower() not in ("mid-flight", "midflight", "in progress"):
            continue
        found = merged_pr(cfg, item["slug"])
        if not found:
            continue
        hits += 1
        pr_id, when = found
        print("%s.html  PR #%s merged %s" % (item["slug"], pr_id, when or "?"))
    if not hits:
        print("nothing to close out")
        return 0
    print("")
    print("Invoke the write-up skill in FINAL SWEEP mode for each: set Status to Merged, "
          "add the PR row, and repoint Reference links to %s."
          % cfg["forge"].get("defaultBranch", "main"))
    return 0


# ------------------------------------------------------------------------ doctor


def cmd_doctor(args):
    ok = True

    def check(label, good, detail=""):
        nonlocal ok
        if not good:
            ok = False
        print("  %s %s%s" % ("OK  " if good else "FAIL", label, ("  " + detail) if detail else ""))

    print("writeup.py doctor")
    print("\nskill")
    check("SKILL.md", os.path.exists(os.path.join(SKILL_DIR, "SKILL.md")), SKILL_DIR)
    for a in ("template.html", "index-template.html", "write-up-ui.js", "glossary.seed.js"):
        check("assets/" + a, os.path.exists(os.path.join(ASSET_DIR, a)))
    check("hooks/write-up-hook.sh", os.path.exists(HOOK_SCRIPT))
    # Python is the optional half. It is reported, not required: the hook and the
    # daily loop run without it.
    print("  ..   python       %s (optional: build, digest, suggest, shot)"
          % sys.version.split()[0])

    root, scope = resolve_scope()
    print("\n%s" % ("repo" if scope == "repo" else "home wiki"))
    if scope == "repo":
        check("inside a git repository", True, root)
    else:
        check("home wiki", True, root)
        print("  ..   note         no repository here, so the Stop hook stays silent;"
              " use /write-up")
    cfg_file = config_path(root)
    check(CONFIG_NAME, os.path.exists(cfg_file), cfg_file if os.path.exists(cfg_file)
          else "run: writeup.py init")
    cfg = load_config(root)
    wdir = wiki_dir(root, cfg)
    check("wiki folder", os.path.isdir(wdir), wdir)
    for a in RUNTIME_ASSETS:
        p = os.path.join(wdir, a)
        check("wiki/" + a, os.path.exists(p), "" if os.path.exists(p) else "run: writeup.py build")
    print("  ..   project      %s" % cfg["project"])
    print("  ..   forge        %s" % cfg["forge"]["type"])
    print("  ..   articles     %d" % (len(scan_articles(wdir)) if os.path.isdir(wdir) else 0))

    print("\nhook")
    if scope == "home":
        check("Stop hook", True, "not applicable outside a repository")
        print("\n%s" % ("all good" if ok else "some checks failed (see above)"))
        return 0 if ok else 1

    # Installed as a plugin, the hook ships in hooks/hooks.json and Claude Code wires
    # it on enable, so there is nothing in settings.json to find. Check that first or
    # every plugin user sees a false failure here.
    as_plugin = (os.path.exists(os.path.join(SKILL_DIR, ".claude-plugin", "plugin.json"))
                 and os.path.exists(os.path.join(SKILL_DIR, "hooks", "hooks.json")))
    if as_plugin:
        check("Stop hook wired", True, "by the plugin (hooks/hooks.json)")
        print("\n%s" % ("all good" if ok else "some checks failed (see above)"))
        return 0 if ok else 1

    found = []
    for p in (
        os.path.join(root, ".claude", "settings.json"),
        os.path.join(root, ".claude", "settings.local.json"),
        os.path.join(os.path.expanduser("~"), ".claude", "settings.json"),
    ):
        try:
            with open(p, encoding="utf-8") as fh:
                if "write-up-hook.sh" in fh.read():
                    found.append(p)
        except Exception:
            continue
    check("Stop hook wired", bool(found), found[0] if found else "see README (Wiring the hook)")

    print("\n%s" % ("all good" if ok else "some checks failed (see above)"))
    return 0 if ok else 1


# --------------------------------------------------------------------------- cli


def build_parser():
    p = argparse.ArgumentParser(prog="writeup.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    i = sub.add_parser("init", help="set up this repo (config + wiki folder)")
    i.add_argument("--project", help="wordmark shown on the wiki (default: repo folder name)")
    i.add_argument("--private", action="store_true",
                   help="keep the wiki machine-local via .git/info/exclude")
    i.add_argument("--home", action="store_true",
                   help="set up the home wiki (~/%s) for work that is not in a repo"
                        % HOME_OUTPUT_DIR)
    i.add_argument("--force", action="store_true", help="overwrite an existing config")
    i.set_defaults(func=cmd_init)

    b = sub.add_parser("build", help="regenerate index.html + manifest.js")
    b.add_argument("dir", nargs="?", help="explicit wiki directory")
    b.add_argument("--project", help="override the wordmark for this build")
    b.set_defaults(func=cmd_build)

    d = sub.add_parser("digest", help="replay your Claude sessions for this repo")
    d.add_argument("--list", action="store_true",
                   help="list sessions (id, date, message count, first message)")
    d.add_argument("--branch", help="only this branch (the default is the current one)")
    d.add_argument("--session", help="only this session id (a prefix is enough)")
    d.add_argument("--since", help="only messages on or after this date (YYYY-MM-DD)")
    d.add_argument("--grep", help="only messages containing this text")
    d.add_argument("--all", action="store_true", help="every session, no branch filter")
    d.add_argument("--max-chars", type=int, default=700)
    d.add_argument("--max-summary", type=int, default=8000)
    d.add_argument("--all-projects", action="store_true",
                   help="scan every project dir, not just this repo's")
    d.set_defaults(func=cmd_digest)

    s = sub.add_parser("suggest", help="propose glossary candidates")
    s.add_argument("article", nargs="*", help="article filename(s); default: all")
    s.set_defaults(func=cmd_suggest)

    sh = sub.add_parser("shot", help="capture a screenshot into the branch's assets folder")
    sh.add_argument("--window", help="window title regex (Windows only)")
    sh.add_argument("--screen", action="store_true", help="capture the primary screen")
    sh.add_argument("--list", action="store_true", help="list visible windows (Windows only)")
    sh.add_argument("--slug", help="filename slug; produces NN-<slug>.jpg")
    sh.add_argument("--branch", help="assets subfolder (default: current branch)")
    sh.add_argument("--out", help="explicit output path, bypassing the convention")
    sh.add_argument("--quality", type=int, default=85)
    sh.add_argument("--settle-ms", type=int, default=450)
    sh.set_defaults(func=cmd_shot)

    sw = sub.add_parser("sweep", help="find Mid-flight articles whose PR has merged")
    sw.set_defaults(func=cmd_sweep)

    dr = sub.add_parser("doctor", help="check the install")
    dr.set_defaults(func=cmd_doctor)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
