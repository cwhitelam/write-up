/* glossary.js --- Write-up glossary hovercards.
   Copied into your wiki folder by `writeup.py init` / `writeup.py build`. Edit it freely:
   it is YOUR project's glossary and nothing overwrites it once it exists.

   Self-contained and self-injecting: one <script src="glossary.js"></script> per article
   is all it needs (it adds its own styles, wraps terms, and owns the card).

   The runtime is a DUMB deterministic dictionary matcher. A word gets a hovercard ONLY
   because it is curated into GLOSSARY below. There is no auto-detection at read time, so
   "MAUI" can never resolve to the Hawaiian island. Candidates are proposed at authoring
   time (`writeup.py suggest`, plus Claude reading its own prose) and curated in by hand.

   TWO ENTRY SHAPES:
     external : a real canonical doc (framework, vendor, RFC). Set `url`, and the card
                shows a source line and an outbound link with a north-east arrow.
     internal : a concept of your own with no vendor doc. Either omit `url` for a
                definition-only card, or point it at the write-up that introduced the
                idea ('some-branch.html') and the card links in-wiki with an arrow.

   POLICY BAKED INTO THE RUNTIME:
     OVERLINK  : a term is eligible only if it is in GLOSSARY. Universal words (API, JSON,
                 HTTP, URL, ID) are never added. When under 70% sure, leave it out.
     DISTANCE  : the first occurrence is decorated, plus at most one more that recurs a
                 screenful or more farther down (the "you scrolled past and forgot" case).
                 Cap two per term, ever. Not once per section.
     EXCLUSION : never inside code (<pre>/<code>), links, headings, the infobox, or refs.
                 So the glossary is for prose-level CONCEPTS, never code identifiers. */
(function () {
  if (window.__bpGlossary) return;
  window.__bpGlossary = true;

  /* ------------------------------------------------------------------------
     STARTER ENTRIES. Delete what does not apply to your project and add your
     own; this list exists to show both shapes, not to be authoritative.
     ------------------------------------------------------------------------ */
  const GLOSSARY = {
    'worktree': { title: 'Git worktree', source: 'Git documentation',
      url: 'https://git-scm.com/docs/git-worktree', match: ['worktree', 'worktrees'],
      blurb: 'A second working directory checked out from the same repository, on its own branch, so more than one branch is open at a time without stashing or switching.' },
    'mcp': { title: 'MCP (Model Context Protocol)', source: 'modelcontextprotocol.io',
      url: 'https://modelcontextprotocol.io', match: ['MCP', 'Model Context Protocol'],
      blurb: 'An open standard for connecting an AI application to outside systems (databases, APIs, files) through a small server it can call.' },
    'adr': { title: 'ADR (Architecture Decision Record)', source: 'adr.github.io',
      url: 'https://adr.github.io/', match: ['ADR', 'Architecture Decision Record'],
      blurb: 'A short dated note recording one architectural choice, its context, and its consequences, so the reasoning survives after the code changes.' },
    'idempotent': { title: 'Idempotent', source: 'MDN Web Docs',
      url: 'https://developer.mozilla.org/en-US/docs/Glossary/Idempotent',
      match: ['idempotent', 'idempotency'],
      blurb: 'Safe to run more than once: the second and hundredth run leave the system in the same state as the first.' },
    'soft-delete': { title: 'Soft delete', match: ['soft delete', 'soft-deleted', 'soft deleted'],
      source: 'Project convention',
      blurb: 'Marking a row deleted with a flag instead of removing it, so history and foreign keys survive. Every read has to filter the flag out, which is where soft-delete bugs come from.' },
    'feature-flag': { title: 'Feature flag', source: 'martinfowler.com',
      url: 'https://martinfowler.com/articles/feature-toggles.html',
      match: ['feature flag', 'feature flags', 'feature toggle'],
      blurb: 'A runtime switch that turns a code path on or off without a deploy, letting unfinished work ship dark and letting a bad change be turned off instead of rolled back.' }
  };

  function injectStyles() {
    if (document.getElementById('bp-gloss-css')) return;
    const css =
      '.bp-term{border-bottom:1px dotted var(--link);cursor:help;text-decoration:none;color:inherit;transition:border-color .12s ease;}' +
      '.bp-term:hover{border-bottom-color:var(--fg);}' +
      '#bp-gloss{position:fixed;z-index:60;width:302px;max-width:302px;background:var(--bg);border:1px solid var(--rule);' +
      'border-radius:11px;box-shadow:0 8px 28px rgba(0,0,0,.42);padding:13px 16px 14px;font-size:13px;line-height:1.55;' +
      'pointer-events:none;opacity:0;visibility:hidden;transform:translateY(4px);' +
      'transition:opacity .13s ease, transform .13s ease, visibility .13s;}' +
      '@media (prefers-color-scheme:light){#bp-gloss{box-shadow:0 8px 26px rgba(5,5,5,.12);}}' +
      ':root[data-theme="light"] #bp-gloss{box-shadow:0 8px 26px rgba(5,5,5,.12);}' +
      ':root[data-theme="dark"] #bp-gloss{box-shadow:0 8px 28px rgba(0,0,0,.42);}' +
      '#bp-gloss.open{opacity:1;visibility:visible;transform:none;pointer-events:auto;}' +
      '#bp-gloss .gc-s{font-family:var(--sans);font-size:10.5px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-bottom:5px;}' +
      '#bp-gloss .gc-t{font-family:var(--serif);font-size:16px;font-weight:600;line-height:1.35;margin-bottom:5px;}' +
      '#bp-gloss .gc-l{color:var(--fg);}' +
      '#bp-gloss .gc-link{display:none;margin-top:11px;padding-top:10px;border-top:1px solid var(--rule);font-size:12.5px;}' +
      '#bp-gloss .gc-link.on{display:block;}' +
      '#bp-gloss .gc-link a{color:var(--link);text-decoration:none;font-weight:500;}' +
      '#bp-gloss .gc-link a::after{content:"↗";font-size:.8em;vertical-align:super;margin-left:2px;color:var(--muted);}' +
      '#bp-gloss .gc-link.internal a::after{content:"→";}';
    const st = document.createElement('style');
    st.id = 'bp-gloss-css';
    st.textContent = css;
    document.head.appendChild(st);
  }

  function run() {
    const article = document.querySelector('article');
    if (!article) return;                                   // index page, etc.
    injectStyles();

    // alias -> key, longest alias first so a multi-word phrase wins over its own acronym
    const pairs = [];
    Object.entries(GLOSSARY).forEach(([k, d]) => (d.match || [d.title]).forEach(a => pairs.push([a, k])));
    if (!pairs.length) return;
    pairs.sort((a, b) => b[0].length - a[0].length);
    const keyOf = {}; pairs.forEach(([a, k]) => keyOf[a] = k);
    const rxEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const RE = new RegExp('(?<![\\w])(' + pairs.map(p => rxEsc(p[0])).join('|') + ')(?![\\w])', 'g');

    // Pass 1: wrap every eligible occurrence; skip code / links / headings / infobox / refs.
    const SKIP = 'pre, code, a, h1, h2, h3, .infobox, .fact, sup, aside, .refs';
    const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        return n.parentElement && n.parentElement.closest(SKIP)
          ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    const spans = [];
    nodes.forEach(node => {
      const text = node.nodeValue; RE.lastIndex = 0;
      let m, idx = 0, hit = false;
      const frag = document.createDocumentFragment();
      while ((m = RE.exec(text))) {
        hit = true;
        frag.appendChild(document.createTextNode(text.slice(idx, m.index)));
        const s = document.createElement('span');
        s.className = 'bp-term'; s.dataset.term = keyOf[m[1]]; s.textContent = m[1];
        frag.appendChild(s); spans.push(s);
        idx = m.index + m[1].length;
      }
      if (!hit) return;
      frag.appendChild(document.createTextNode(text.slice(idx)));
      node.parentNode.replaceChild(frag, node);
    });
    if (!spans.length) return;

    // Pass 2: distance gate. Measure absolute tops first (no reflow while measuring), then
    // per term keep the first plus at most one more sitting a screenful+ below the last kept.
    const GAP = Math.round(innerHeight * 0.85);             // "a screenful"; tune per corpus
    const tops = spans.map(s => s.getBoundingClientRect().top + scrollY);
    const byKey = {};
    spans.forEach((s, i) => (byKey[s.dataset.term] = byKey[s.dataset.term] || []).push(i));
    const keep = new Set();
    Object.values(byKey).forEach(idxs => {
      let count = 0, last = -Infinity;
      idxs.forEach(i => { if (count === 0 || (count < 2 && tops[i] - last >= GAP)) { keep.add(i); count++; last = tops[i]; } });
    });
    spans.forEach((s, i) => { if (!keep.has(i)) s.replaceWith(document.createTextNode(s.textContent)); });

    // Card + hover bridge (own element/ids, isolated from the cross-article #bp-card).
    const card = document.createElement('div'); card.id = 'bp-gloss';
    card.innerHTML = '<div class="gc-s"></div><div class="gc-t"></div><div class="gc-l"></div>'
      + '<div class="gc-link"><a target="_blank" rel="noopener"></a></div>';
    document.body.appendChild(card);
    let hideT = null;
    const show = (el, d) => {
      clearTimeout(hideT);
      card.querySelector('.gc-s').textContent = d.source || '';
      card.querySelector('.gc-t').textContent = d.title;
      card.querySelector('.gc-l').textContent = d.blurb;
      const link = card.querySelector('.gc-link'), a = link.querySelector('a');
      if (d.url) {
        const internal = !/^https?:/i.test(d.url) && /\.html($|[?#])/i.test(d.url);
        a.href = d.url; a.textContent = d.linkText || d.source || 'Read more';
        a.target = internal ? '_self' : '_blank'; a.rel = internal ? '' : 'noopener';
        link.classList.toggle('internal', internal); link.classList.add('on');
      } else {
        link.classList.remove('on');                         // definition-only card
      }
      const r = el.getBoundingClientRect();
      card.style.left = Math.max(8, Math.min(r.left, innerWidth - card.offsetWidth - 8)) + 'px';
      const below = r.bottom + 9;
      card.style.top = (below + card.offsetHeight > innerHeight ? Math.max(8, r.top - 9 - card.offsetHeight) : below) + 'px';
      card.classList.add('open');
    };
    const hideSoon = () => { hideT = setTimeout(() => card.classList.remove('open'), 220); };
    article.querySelectorAll('.bp-term').forEach(el => {
      const d = GLOSSARY[el.dataset.term]; if (!d) return;
      el.addEventListener('mouseenter', () => show(el, d));
      el.addEventListener('mouseleave', hideSoon);
    });
    card.addEventListener('mouseenter', () => clearTimeout(hideT));
    card.addEventListener('mouseleave', hideSoon);
  }

  // Wait for full load so image heights are settled before the distance gate measures.
  if (document.readyState === 'complete') run();
  else addEventListener('load', run, { once: true });
})();
