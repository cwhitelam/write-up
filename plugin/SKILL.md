---
name: write-up
description: >-
  Write the STORY of a piece of work as a self-contained HTML article: Why (the
  problem), What was built, How (the path, roads-not-taken inline), Decisions (an
  ADR log), Day by day (a dated journal), Highlights (the load-bearing code,
  verbatim). Use when finishing anything worth remembering, when the user says
  "document how we got here / write this up / write the story of this / write-up
  this", when wrapping up a branch or a long session, when they want their Claude
  Code history turned into something durable, or via /write-up. A gated Stop hook
  also invokes it at wrap-up.
---

# write-up

Turn a finished piece of work into its build story: a low-token, self-contained HTML page
written from what you already hold in session context. The value is the reasoning that
normally evaporates when the session ends, plus the few snippets of code that actually made
the thing possible. A diff says what changed. A write-up says what we were thinking and
which code carried it.

The unit is **a piece of work**, whatever that means here: a branch, a feature, a debugging
session that finally landed, a refactor, a spike that answered a question, a tool built over
a weekend. It does not need a ticket, an issue number, or even a branch of its own.

Articles accumulate into a small local wiki with a generated front page, full-text search,
cross-article hover previews, automatic backlinks, and glossary hovercards. Over time that
wiki becomes the readable version of a Claude Code history that would otherwise be a pile of
transcripts nobody reopens.

## The toolchain

Two pieces, and only the first is required.

**The Stop hook**, `hooks/write-up-hook.sh`, is POSIX sh. Claude Code invokes it; you
never do. It needs nothing installed, because Claude Code runs hook commands through
`sh -c` on macOS and Linux and Git Bash on Windows.

**The CLI**, `scripts/writeup.py`, is optional and needs Python 3.8 or newer:

```
python <skill-dir>/scripts/writeup.py <command>
```

`<skill-dir>` is the directory this SKILL.md was loaded from. In practice that is
`~/.claude/skills/write-up` (user install) or `<repo>/.claude/skills/write-up`
(project install). Resolve it once, then reuse it.

**Check for Python once per session, before you rely on it** (`python --version` or
`python3 --version`). If it is missing, use the right-hand column. Never tell the user
to install Python; every job here has a path that does not need it.

| Command | What it does | If Python is absent |
|---|---|---|
| `init` | Write `.write-up.json`, create the wiki folder, install the runtime JS. Once per repo, or `--home` for the repo-less wiki at `~/.claude/write-ups`. | Read `git remote -v`, write the config yourself (shape below), and copy `write-up-ui.js` and `glossary.seed.js` from `<skill-dir>/assets/` into the wiki folder, naming the second one `glossary.js`. |
| `build` | Rebuild `index.html` + `manifest.js` from every article on disk. | Not needed. Step 8 has you update both directly, one entry each. Use `build` only to repair a wiki that has drifted. |
| `digest` | Replay past Claude sessions for this repo as one chronological digest. `--list` indexes every session (id, date, message count, opening line); `--session <id>`, `--branch <b>`, `--since <date>`, `--grep <text>`, `--all` scope it. | Read the `.jsonl` transcripts under `~/.claude/projects/<encoded-cwd>/` with Grep and Read. Slower and costlier, so scope it tightly. |
| `suggest [article]` | Propose glossary candidates from an article's prose. | Skip it. You already know which terms in your own prose are non-obvious. |
| `shot --window <re> --slug <s>` | Capture a screenshot into the branch's assets folder. | Use the browser tools for web pages. Desktop windows need the CLI. |
| `sweep` | List Mid-flight articles whose branch already has a merged pull request. The only command that makes a network call. | Ask the user which branches have merged. |
| `doctor` | Check the install and report what is missing. | Check the files exist yourself. |

## Configuration

`.write-up.json` at the repo root drives paths and links. Read it before authoring so
every URL you write is correct for this project's forge:

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
  }
}
```

Substitute `{branch}`, `{path}` (repo-relative, no leading slash), and `{id}`. When a
pattern is empty or `forge.type` is `"none"`, write plain text instead of a link. Never
invent a URL shape the config does not describe. `ticketUrl` and `prUrl` matter only when
the project actually uses issues and pull requests; plenty of work has neither, and those
infobox rows are simply omitted. If `.write-up.json` is missing, run `init` first, or fall
back to `docs/write-ups` with no links at all.

## When this runs

- **`/write-up`**: explicit invocation, and the main path. Anything worth remembering
  qualifies. There is no requirement that a branch be finished, or that one exist.
- **Gated Stop hook** (optional, off unless installed): at genuine wrap-up on a feature
  branch (tree clean, ahead of the default branch, pushed) the hook blocks the stop once
  when the article is **missing**, and again when it exists but is **stale** (commits newer
  than the file). Honor it, then let the stop proceed. It stays silent on the default
  branch, so work done straight on `main` is never nagged: use `/write-up` there.
- **Day entry**: at the end of a working day on a branch that already has an article, the
  hook asks for one new `.day` entry. Append it, touch nothing else.
- **Final sweep**: on the default branch, the hook can check whether a Mid-flight article's
  branch has a merged pull request and ask you to close it out.
- Any request like "document how we got here", "write this up", "write the story of this",
  "turn this session into something I can keep", "write this up".

## Work without a branch

Branchless work is normal and fully supported: a spike, a research session, a tool built
outside any repo, several days of small changes straight on `main`. In that case:

- **Name the article yourself.** Use a short descriptive slug for the filename
  (`redis-cache-spike.html`, `why-the-build-is-slow.html`), chosen the way you would title
  an encyclopedia entry, not a commit message.
- **Drop the Ticket and Branch infobox rows** and use **Kind** (Spike / Investigation /
  Tool / Refactor) and **Location** (where the work lives) instead.
- **Status** still applies: Mid-flight, Shipped, Merged, In use, Concluded (investigated,
  decided against), Unresolved (still open), or Abandoned. The front page derives its
  filter chips from whatever statuses exist, so a new value needs no code change. An abandoned
  spike with an honest Why and a clear Decisions log is one of the more useful articles a
  wiki can hold, because it stops the same idea being re-explored next quarter.
- Everything else is unchanged. Highlights still quote real code, References still cite
  real files.

## Structure (fixed)

The page is laid out like an encyclopedia article: fixed header with a serif wordmark,
sticky left table-of-contents rail, serif headings over airy sans prose, superscript
citations. Flow, in order:

| Part | Content |
|---|---|
| **Byline, title, infobox, lead** | "Documented by Claude, date" line, serif title, then the right-floated infobox: the finished-feature image (when one exists) over a facts grid. **Include only the rows that apply.** Candidates: Ticket (`forge.ticketUrl`, only if the project uses issues), **Author** (who WROTE THE CODE, the git commit author, `git log <base>..HEAD --format=%an \| sort -u`, NOT whoever requested it), **Reviewer** (who approved the pull request), Branch (`forge.branchUrl`), Status, Surface (the route, command, or entry point), PR, Documented. Branchless work uses Kind and Location instead of Ticket and Branch. Then a 2 to 4 sentence encyclopedia lead. **When the work did not resolve, or resolved as "do not build this", the lead must say so outright and point at the section that carries the payload** (usually Open). The section order never changes, so the lead is the only thing standing between a reader and the wrong conclusion. |
| **Why** | The problem that started it. 2 to 4 plain sentences: what hurt, what was asked, what made it worth doing. |
| **What** | What exists now that did not before. Tight bullets: commands, surfaces, behavior. |
| **How** | The path in order, one or two lines per step. Real trade-offs written inline as "chose X over Y because Z" so roads-not-taken survive. |
| **Decisions** | The load-bearing choices as an ADR log, one `.dec` each: the decision, a `<small>` date, one line of why and the trade-off. Same reasoning as How, extracted for scanning. Keep it to the choices that mattered; do not restate How verbatim. **A decision that reverses an earlier one must say so in its first clause** ("Supersedes the decision above: ..."), because a plain chronological list gives the reader no way to tell which entry is still in force. |
| **Day by day** | A dated journal, one `.day` per working day, oldest first: date, short title, bullets of what got done. Build it from `git log --date=short` grouped by day plus the session digest. Each entry carries `data-day="YYYY-MM-DD"`, which is how the hook knows today is already logged. |
| **Highlights** | The load-bearing artifact, verbatim. Usually the code that made it work; for an investigation or a spike it is the evidence that carried the finding instead, which is equally quotable: the benchmark, the query plan, the log line, the instrumentation. Each showcase is a one-line plain-english caption on why this snippet is the trick, a superscript cite `[n]`, and the snippet trimmed to the essential lines. Work that shipped no code is not exempt; it just quotes different code. |
| **Open** | Caveats, estimates, deferred work. Omit the section and its TOC entry when there are none. |
| **See also** | Genuinely related articles, one clause each on the relation. Omit when none. Whenever prose anywhere mentions another article that exists, LINK it: cross-article links are what make this a wiki. |
| **References** | Numbered list of the highlight source files (`id="ref-n"`, repo-relative path plus one clause on what it holds). Files tracked in the repo link via `forge.fileUrl`; untracked or gitignored files stay unlinked. Cite from captions and How steps. |

`write-up-ui.js` adds the presentation layer to every article automatically: scroll
reveals, link underlines, and the styling for the Decisions and Day-by-day sections.
Nothing per-article to configure. Author the full article and the runtime handles the
rest.

## Hard rules

- **Low token.** Copy the `<style>` block, the three `<script src>` includes, and the
  trailing `<script>` block from `assets/template.html` **verbatim**. Never restyle per
  article. That script is the scrollspy, the syntax tokenizer, external-link handling,
  hover previews, auto-backlinks, and copy-code buttons. Author only the header wordmark,
  the TOC entries, and the `<article>` slots. For the current conversation use what you
  already hold in context: do not re-read its transcript or the git log. If you genuinely
  do not remember a step, write fewer steps rather than going digging.
- **Links are handled for you.** Write plain `<a href>`. The tail script opens off-site
  links in a new tab with an arrow glyph and keeps internal `.html` links in-tab.
  Cross-article links get hover previews, and **"Referenced by" backlinks are derived from
  the manifest, so never hand-write them** (See also stays curated and outbound; backlinks
  are automatic and inbound). Link authoritative external sources freely in prose.
  Collapsible sections are intentionally not used: the articles are short and the TOC jumps.
- **Multi-session work.** If the work spanned more than this conversation, or your memory
  of the early story is thin, run `writeup.py digest`. It replays the human half of past
  Claude sessions for this repo, compaction summaries included, as one chronological
  session-grouped digest. Scope it to what you need: `--branch <b>` when work maps onto
  branches, `--session <id>` for one conversation (find it with `--list`), `--since <date>`
  for a stretch of days, `--grep <text>` when the user remembers a phrase but not when.
  Use the result as the story spine for sessions you did not live. This is the only
  sanctioned transcript access. Never read raw `.jsonl` files.
- **Documenting the past.** When the user asks you to write up work that happened before
  this conversation, `digest --list` is the starting point: show them the session index,
  let them point at what they mean, then digest that scope and write from it. Do not guess
  which session they meant when the index can just be shown.
- **Highlights are real code.** Quote verbatim from the repo file (Read it if it is not
  already in context; this is the one allowed lookup), trim to the lines that carry the
  idea, HTML-escape `<` `>` `&`. As many showcases as the work earns: a one-line fix has
  one, a subsystem may have several. No API documentation, no exhaustive listings. Only code
  you would point at to explain why the thing works.
- **TOC mirrors the sections.** The sidebar links and the `section id=` anchors match one
  to one. Drop the Open link when there is no Open section.
- **Nothing decorative.** Every element must do something: links navigate, the search pill
  opens the index, Ctrl+K works, citations jump. If an element has no function for this
  article, omit it.
- **Real turns only.** A trade-off line in How means a genuine direction change with a
  reason. Do not invent pivots to fill space. A short honest article beats a padded one.
- **Honest.** Estimates are labeled estimates. Deferred and unfinished work goes in Open.
  Never imply more shipped than did.
- **Spell out acronyms** on first use in an article, in parentheses. After the first
  expansion the bare acronym is fine. Skip only the truly universal ones (URL, HTML, ID).
- **Keep it to one or two screens.** If the work was tiny, the article is tiny.

## Screenshots

- **You are the photographer.** Never hand the user a screenshot task. Browser pages: the
  browser tools save to a path directly. Desktop windows: `writeup.py shot --list` to
  enumerate, `--window '<title regex>' --slug <slug>` to capture one into the assets folder,
  `--screen --slug <slug>` for the whole display. Read every capture back and look at it
  before embedding.
- **Capture during the work, as milestones happen.** First render, a broken state worth
  remembering, the fix working, the finished feature. 2 to 6 per branch, saved to
  `<outputDir>/assets/<branch>/NN-slug.jpg`. At authoring time embed what exists, in order:
  the finished-feature shot as the right-floated `figure.lead-img` beside the lead,
  evolution shots as `figure.step-img` inside the How step they belong to. No assets folder
  means no images, which is fine.
- **Screenshots are the exception, not the default, and are never redacted.** The code
  Highlights are the visual for most work: for a fix, a rule, or a filter change the
  verbatim snippet IS the illustration. Add a screenshot only when the visual is the point
  (a new screen, a component, a dashboard) AND it can be captured with non-sensitive data.
  Preference order: a component fed a crafted sample input; a structural, empty, or
  new-state shot; the user's own non-sensitive view. If the only honest shot is a grid or
  report of real production records, skip the image and ask the user case by case. Do not
  blur, do not crop through data columns, do not fake a state that did not occur. Blur was
  tried and rejected: it looks like a leaked document and advertises that sensitive data is
  there.
- **Capturing on a live desktop.** Off-screen pixels cannot be grabbed: a window hanging
  past a monitor edge yields a silently cut-off shot (the tool warns). Let an app settle
  before placing it, and prefer a browser tab capture for web pages outright, since it
  cannot be occluded or resized by anyone. If the app is being hot-reloaded by another
  session, retake later. A mid-rebuild error page is not the feature.

## Glossary

Non-obvious terms get a hover card from `<outputDir>/glossary.js`. Write plain prose and
the runtime wraps the first occurrence (plus one more only if it recurs a screenful farther
down, cap two), skipping code, links, headings, the infobox, and references.

- **Two entry shapes.** *External*: a real canonical doc (framework, vendor, RFC), which
  links out. *Internal*: a project concept with no vendor doc, carrying a one-line
  definition and optionally an in-wiki link to the article that introduced it.
- **You are the proposer, and this is where you beat the regex.** After drafting, reread
  your own prose and propose candidates a reader might stumble on. Keep a term only if all
  three hold: **non-obvious** to a developer browsing the wiki (skip what a working dev
  knows cold); **load-bearing**, so not knowing it makes a sentence hard to follow; and
  **definable in one sentence with a home**. Bias hard toward NOT proposing: under roughly
  70% sure means skip. The distance gate caps repeats, but eligibility is the only guard
  against clutter.
- **Never invent a URL.** Propose the source and mark the URL as needing verification
  unless you are certain, or confirm it with a quick fetch.
- Because code is never decorated, the internal glossary is for prose-level **concepts**
  (soft delete, feature flag, idempotency), never code identifiers.
- Then run `writeup.py suggest <article>.html` as a cheap offline cross-check: it catches
  the obvious acronym, CamelCase, and known-tech shapes. Curate the winners into
  `glossary.js` and ignore the rest. That is the OVERLINK "no".

## Steps

1. **Resolve the config and output path.** Read `.write-up.json` at the repo root. The
   article is `<outputDir>/<slug>.html`. The slug is the current git branch when the work
   maps onto one, with any `/` replaced by `-` so the file stays flat (`feature/search`
   becomes `feature-search.html`); otherwise pick a short descriptive slug yourself.
2. **Read `assets/template.html`** (sibling of this file).
3. **Replay earlier sessions** if the work spanned more than this one:
   `python <skill-dir>/scripts/writeup.py digest` (scoped per the Multi-session rule
   above). Fold those sessions into the story. The Why usually lives in the first session,
   not the last one.
4. **Fill the slots** from session context plus the digest: `{{TITLE}}` (the
   encyclopedia-entry name of the work, not a sentence), `{{PROJECT}}` (header wordmark,
   from `config.project`), `{{BRANCH}}`, `{{DATE}}`, `{{LEAD}}`, then the sections and
   References per the table above. Build every URL from the `forge` patterns.
5. **Embed images** if `<outputDir>/assets/<branch>/` exists.
6. **Write** the filled HTML. Keep the `<style>`, the three script includes, and the
   trailing `<script>` byte-identical to the template.
7. **Refresh the glossary** when the article introduces new terms (see Glossary above).
8. **Add the article to the wiki index.** Two small edits, both in the wiki folder:

   **`manifest.js`** holds `window.WRITEUPS = [ ... ]`, newest first. Insert one object at
   the front:

   ```js
   {"slug": "<slug>", "title": "<title>", "lead": "<the lead paragraph, plain text>",
    "status": "Shipped", "ticket": "", "date": "YYYY-MM-DD", "refs": ["<other-slug>"],
    "body": "<search text: the lead, every section heading, and the first sentence of
             each section. A few hundred characters, not the whole article.>"}
   ```

   `refs` lists the slugs this article links to; the wiki derives every "Referenced by"
   backlink from it, so an omitted ref is a missing backlink on the other page.

   **`index.html`** holds `<ol class="entries">`. Insert one row at the top:

   ```html
   <li class="entry">
     <a class="t" href="<slug>.html"><title></a>
     <p><one-sentence lead snippet></p>
     <span class="m">YYYY-MM-DD &middot; <code><slug></code> &middot; Shipped</span>
   </li>
   ```

   Match the surrounding rows exactly. If the wiki is empty and has no `index.html` yet,
   copy `<skill-dir>/assets/index-template.html`, substituting `{{PROJECT}}` with the
   project name, `{{SUFFIX}}` and `{{TAG}}` per the config, and `{{REPOLINK}}` with a link
   to `forge.repoUrl` (or nothing when there is no forge).

   With Python available, `writeup.py build` does all of this from the articles on disk.
   Prefer it when it is there, and treat it as the repair tool when a wiki has drifted.
9. **Tell the user the path and open it.**

## Refreshing an existing article

An article is **patched, never regenerated**. Read it first, compare against what has
happened since (session context, or the digest for sessions you did not live), and edit
only where the story actually grew:

- **What**: add bullets for newly shipped outcomes.
- **How**: append new steps in chronological order. Existing steps stay untouched unless a
  decision they describe was later reversed; then update that step in place rather than
  duplicating it.
- **Decisions / Day by day**: append. Never rewrite a past day.
- **Infobox**: update only the rows that changed (Status, PR when one appears).
- **Highlights / References**: add new load-bearing code with its citation, keep numbering.
- **Open**: the one section describing *now*. Rewrite it freely: drop resolved items, add new.
- **Chrome**: if `template.html` changed since the article was written, swap the article's
  `<style>` and trailing `<script>` blocks wholesale for the current template's (they are
  verbatim copies, so this is mechanical) and leave `<article>` content alone.

Never reword prose that still tells the story correctly. Wording churn produces a noisy
diff and destroys the article's stability for zero gain. Update the manifest entry
(step 8) if the lead, status or refs changed; leave it alone if only prose moved.

## Final sweep (after merge)

When the hook reports that a Mid-flight article's branch now has a merged pull request,
patch that article:

- Infobox **Status** becomes Merged; add a **PR** row using `forge.prUrl`; add the merge date.
- **Repoint Reference links** from the branch to the default branch, since the source branch
  is often deleted at merge and every code link would 404. Drop any "resolve once pushed" note.
- Patch only, regenerate nothing. Update the article's `status` in `manifest.js` and
  its status chip in `index.html` to match.

## Where the wiki lives

There are three placements. The first two are inside a repository and the choice is the
user's; the third is what you get when there is no repository at all.

**Resolve it before writing anything.** Read `.write-up.json` at the repo root; if there
is no repo or no config there, read `~/.write-up.json`. An initialised repo always wins,
so a project's wiki is never bypassed by accident.

- **Committed (default)**: `<outputDir>/` is tracked, so articles travel with the repo and
  the wiki is team content. `index.html` and `manifest.js` are generated, so they belong in
  `.gitignore`; the articles and their assets are what get committed.
- **Machine-local** (`init --private`): `<outputDir>/` goes in `.git/info/exclude`, which
  lives in the shared common git dir and so covers the main checkout and every worktree at
  once. Nothing is ever staged or committed, nothing merges, so nothing can conflict. The
  main checkout is the single canonical wiki. Because articles do not travel through git, a
  worktree only ever holds its own branch's article: to gather everything on one front page,
  copy the worktree's `<branch>.html` and its `assets/<branch>/` into the main checkout's
  wiki folder, then add its manifest and index entries there (step 8).
- **Home** (`init --home`, or `init` run anywhere outside a repo): the config is
  `~/.write-up.json` and articles go to `~/.claude/write-ups/`, under the wordmark
  **Notebook**. This is for work that is not a branch and may not be code at all:
  research that reached an answer, a data investigation, a decision argued out over one
  session, a thing you figured out and do not want to figure out twice. The six sections
  are unchanged. `forge.type` is `none`, so References stay plain text and nothing links
  to code. Drop the Ticket, Branch and PR infobox rows and use **Kind** and **Location**
  instead, exactly as for branchless work in a repo.

  **No Stop hook fires here.** Its trigger is branch state, so outside a repository there
  is no automatic prompt and the user must ask. If someone in a repo-less directory
  finishes something worth keeping, it is worth saying so once, then writing it if they
  agree. Do not nag.
