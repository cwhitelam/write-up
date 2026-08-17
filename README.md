# Write-up

A skill for [Claude Code](https://claude.com/claude-code) that writes the story of a
finished piece of work as a self-contained HTML article, and accumulates those articles
into a small local wiki.

Git records what changed. Write-up records **why**, while the reasoning is still in the
session and still cheap to capture. A week later it is gone, and six months later the only
honest answer to "why is it built this way" is that nobody remembers.

The unit is a piece of work, whatever that means for you: a branch, a feature, a debugging
session that finally landed, a refactor, a spike that answered a question. No ticket system
required. No issue number required. No branch required.

<!-- Replace with a screenshot of your own wiki once you have one. -->
**[See a sample article](example/docs/write-ups/write-up.html)** (clone and open it, or
serve the folder: `python -m http.server` inside `example/docs/write-ups`).

## What an article looks like

Six fixed sections, always in the same order, so a reader who has seen one article can skim
any other:

| Section | What goes in it |
|---|---|
| **Why** | The problem that started it. What hurt, in plain sentences. |
| **What** | What exists now that did not before. |
| **How** | The path in order, with real trade-offs inline: "chose X over Y because Z". Roads not taken survive here. |
| **Decisions** | The load-bearing choices as a dated Architecture Decision Record log. |
| **Day by day** | A dated journal, one entry per working day. |
| **Highlights** | The two or three snippets of code that actually made it work, verbatim, each with one line on why it is the trick. |

Plus an optional **Open** section for caveats and deferred work, a **See also** for related
articles, and a **References** list linking each snippet back to its source file.

Every page is one HTML file. No build step, no framework, no network, no dependencies. It
opens from disk in three years the same way it opens today.

The wiki around them gives you a generated front page with full-text search and status
filters, hover previews on every cross-article link, automatic "Referenced by" backlinks,
glossary hovercards for non-obvious terms, a light/dark toggle, and copy buttons on every
code block.

## Install

Requires Python 3.8 or newer and git. Nothing else.

```bash
git clone https://github.com/YOUR-ORG/write-up.git
cd write-up
python install.py --with-hook          # installs to ~/.claude/skills/write-up
```

Then, in each repo you want documented:

```bash
python ~/.claude/skills/write-up/scripts/writeup.py init
```

`init` reads your git remote, works out whether you are on GitHub, GitLab, Bitbucket, or
Azure DevOps, and writes a `.write-up.json` with the right link patterns. An unrecognised
host is fine: articles just do not link to code.

Check it with `writeup.py doctor`. Drop `--with-hook` if you do not want the Stop hook
(see below), and add `--project` to install into one repo instead of your home directory.

## Use

Ask Claude for one:

```
/write-up
```

or just say "write this up", "document how we got here", or "write the story of this".
Claude writes `docs/write-ups/<slug>.html` from what it already holds in context, then
regenerates the front page. Nothing is mined, nothing is re-read, no transcript is
reprocessed: the model writes from the conversation it is already in, which is both cheaper
and a better story than any reconstruction.

To refresh an article later, ask again. Articles are **patched, never regenerated**: new
outcomes get appended, existing prose is left alone.

## The wiki

```
docs/write-ups/
├── index.html          generated front page (search, filters, newest first)
├── manifest.js         generated search index and backlink graph
├── write-up-ui.js     shared runtime (reading modes, journal styling)
├── glossary.js         your curated term definitions
├── assets/<slug>/      screenshots, if any
└── <slug>.html         one article per piece of work
```

`index.html` and `manifest.js` are **generated**. Never hand-edit them. Run
`writeup.py build` after adding or removing an article and they rebuild from whatever is
on disk, which is why the front page cannot silently go stale.

By default the wiki is committed with your repo, so it is team content. Run
`init --private` instead and it goes into `.git/info/exclude`: never staged, never
committed, never merged, a personal record on your machine.

## Configuration

`.write-up.json` at the repo root:

```json
{
  "project": "Acme Web",
  "outputDir": "docs/write-ups",
  "forge": {
    "type": "github",
    "repoUrl":   "https://github.com/acme/web",
    "branchUrl": "https://github.com/acme/web/tree/{branch}",
    "fileUrl":   "https://github.com/acme/web/blob/{branch}/{path}",
    "ticketUrl": "https://github.com/acme/web/issues/{id}",
    "prUrl":     "https://github.com/acme/web/pull/{id}",
    "defaultBranch": "main"
  },
  "hook": {
    "enabled": true,
    "wrapUp": true,
    "dayEntries": true,
    "mergeSweep": false,
    "skipBranches": ["main", "master", "develop"]
  }
}
```

`init` writes this for you. Edit it freely: the URL patterns are just strings with
`{branch}`, `{path}`, and `{id}` substituted, so a self-hosted forge is a two-minute fix.

## The Stop hook (optional)

The hook is deliberately quiet. It fires only when a branch actually looks finished: the
tree is clean, the branch is ahead of the default branch, and it has been pushed. Then it
asks for a write-up exactly once. If commits land after the article was written it asks
once more for a refresh. That is the whole trigger surface.

It stays silent on `main`, `master`, and `develop`, so working directly on the default
branch is never nagged. Use `/write-up` there instead.

Two extras, both configurable:

- **Day entries** ask for one journal entry per working day on a branch that already has an
  article. Silence per branch with `docs/write-ups/.skip-day-<slug>`.
- **Merge sweep** (off by default) checks whether a Mid-flight article's branch has a
  merged pull request and asks Claude to close the article out. Supports GitHub through the
  `gh` CLI and Azure DevOps through a personal access token. It is the only feature that
  ever touches the network, and it is off unless you turn it on.

Silence any branch entirely with `docs/write-ups/.skip-<slug>`, or set
`hook.enabled: false`.

## Turning old sessions into articles

`digest` replays the human half of your past Claude Code sessions for a repo. It is how you
write up work that happened before this conversation.

```bash
writeup.py digest --list                    # index every session for this repo
writeup.py digest --session a42107df        # replay one conversation
writeup.py digest --branch feature/search   # everything on one branch
writeup.py digest --since 2026-08-01        # a stretch of days
writeup.py digest --grep "rate limit"       # when you remember a phrase, not a date
```

`--list` prints a table of session id, start time, message count, branch, and opening line,
so you can find the conversation you half remember and hand Claude exactly that scope.

Assistant turns, tool calls, and sidechains are dropped. What comes back is what you asked
for, in order, which is what a story is actually made of. Compaction summaries are included
automatically, so history from before a context compaction survives.

## Screenshots

Claude captures its own screenshots rather than asking you to:

```bash
writeup.py shot --list                            # visible windows (Windows)
writeup.py shot --window "Chrome" --slug first-render
writeup.py shot --screen --slug cockpit
```

They land in `docs/write-ups/assets/<slug>/NN-name.jpg` and get embedded automatically.

The skill treats screenshots as the exception, not the default: for most work the code
snippet is the illustration. It will not blur or crop real data to make a shot presentable,
because a blurred screenshot reads as a leaked document. If the only honest shot contains
real records, it skips the image and asks you.

## Privacy

`digest` reads Claude Code's own transcripts under `~/.claude/projects`. It is read only,
it never writes there, and nothing leaves your machine: the output goes to your terminal
and into an article you control. Every other command touches only your repo.

The single exception is the merge sweep, which queries your forge for merged pull requests.
It is off by default.

## Platform support

| | Windows | macOS | Linux |
|---|---|---|---|
| Skill, wiki, build, digest, hook | yes | yes | yes |
| `shot --screen` | yes | yes (needs Pillow or `screencapture`) | yes (needs Pillow or ImageMagick) |
| `shot --window` | yes | no | no |

Window-targeted capture uses the Win32 API and has no portable equivalent. On other
platforms use `--screen`, or capture web pages with Claude's browser tools, which cannot be
occluded by another window anyway. The macOS and Linux screen fallbacks are written against
the standard tools but have not been exercised on those platforms; reports welcome.

## Uninstall

```bash
python install.py --uninstall
```

Your wiki, your config, and your glossary are left alone. If you wired the Stop hook,
remove it from `settings.json` yourself.

## License

MIT. See [LICENSE](LICENSE).
