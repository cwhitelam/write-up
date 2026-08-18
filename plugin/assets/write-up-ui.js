// write-up-ui.js --- shared runtime for every write-up article (like glossary.js).
// The presentation layer on top of an article's own styles: scroll reveals, link
// underline-draw, infobox image reveal, and styling for the Decisions (ADR log) and
// Day-by-day (journal) sections. Self-injecting: one <script> include per article is all
// it takes, nothing per-article to maintain. No network, no dependencies.
(function () {
  if (window.__bpUI) return; window.__bpUI = true;

  // Detect an embedded render up front so the CSS below can opt out of motion.
  // Same-origin check is guarded: a cross-origin embed throws on window.top access.
  try { if (window.self !== window.top) document.documentElement.classList.add('bp-framed'); }
  catch (e) { document.documentElement.classList.add('bp-framed'); }

  var CSS = `
:root{--bp-accent:#ff6e14;--bp-ease:cubic-bezier(.22,1,.36,1);}

/* ===== motion + interactions ===== */
.bp-rv{opacity:0;transform:translateY(16px);
  transition:opacity .85s var(--bp-ease),transform .85s var(--bp-ease);}
.bp-rv.bp-in{opacity:1;transform:none;}
article a{text-decoration:none;background-image:linear-gradient(currentColor,currentColor);
  background-size:0 1px;background-repeat:no-repeat;background-position:0 92%;transition:background-size .4s var(--bp-ease);}
article a:hover{background-size:100% 1px;}
.infobox img{clip-path:inset(0 0 100% 0);transform:scale(1.06);
  transition:clip-path 1.1s var(--bp-ease),transform 1.4s var(--bp-ease);}
.infobox.bp-in img{clip-path:inset(0 0 0 0);transform:none;}
@media(prefers-reduced-motion:reduce){
  .bp-rv,.infobox img{opacity:1!important;transform:none!important;clip-path:none!important;transition:none!important;}
}
/* Embedded in an iframe nobody scrolls (a preview, a print pipeline), the reveal never
   fires and the article sits at low opacity forever. Show everything immediately. */
html.bp-framed .bp-rv,html.bp-framed .infobox img,
html.bp-static .bp-rv,html.bp-static .infobox img{
  opacity:1!important;transform:none!important;clip-path:none!important;transition:none!important;}

/* ===== Decisions (ADR log) ===== */
.dec{border-left:2px solid var(--rule);padding-left:16px;margin:0 0 15px;transition:border-color .3s var(--bp-ease);}
.dec:hover{border-left-color:var(--bp-accent);}
.dec .d{font:600 16px/1.45 var(--sans);}
.dec .d small{font:600 11px/1 var(--sans);letter-spacing:.03em;color:var(--muted);background:var(--pre-bg);
  border:1px solid var(--rule);border-radius:5px;padding:2px 7px;margin-left:8px;vertical-align:middle;}
.dec .w{color:var(--sup);font-size:15px;margin-top:2px;}

/* ===== Day by day (journal timeline) ===== */
.journal{position:relative;margin-left:6px;padding-left:26px;}
.journal::before{content:"";position:absolute;left:5px;top:8px;bottom:8px;width:2px;background:var(--rule);}
.day{position:relative;margin:0 0 22px;}
.day::before{content:"";position:absolute;left:-27px;top:5px;width:11px;height:11px;border-radius:50%;
  background:var(--bg);border:2px solid var(--bp-accent);transition:transform .4s var(--bp-ease);}
.day:hover::before{transform:scale(1.3);}
.day .date{font:600 12px/1 var(--sans);letter-spacing:.05em;text-transform:uppercase;color:var(--bp-accent);}
.day h3{font:600 17px/1.3 var(--sans);margin:3px 0 6px;}
.day ul{margin:0;padding-left:20px;} .day li{margin:5px 0;font-size:15px;color:var(--sup);}
`;

  function run() {
    var s = document.createElement('style'); s.textContent = CSS; document.head.appendChild(s);

    // reveal targets (no per-article markup needed)
    var sel = 'article > p, article > h1, .infobox, article section > h2, article section > p,' +
              ' article section > ul, article section > ol, article section > figure, .dec, .day';
    var items = [].slice.call(document.querySelectorAll(sel));
    items.forEach(function (el) { el.classList.add('bp-rv'); });

    function revealAll() {
      // bp-static, not just bp-in: bp-in animates up from opacity 0, and an environment
      // that starved the observer of frames will starve the transition too. This sets the
      // finished state outright, so the article is readable either way.
      document.documentElement.classList.add('bp-static');
      items.forEach(function (el) { el.classList.add('bp-in'); });
    }

    if (!('IntersectionObserver' in window)) { revealAll(); return; }

    var io = new IntersectionObserver(function (es, o) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('bp-in'); o.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });
    items.forEach(function (el) { io.observe(el); });

    // Fail open. The reveal starts every element at opacity 0, so if the observer never
    // delivers (a throttled or occluded tab, a prerender, a browser that suspends
    // callbacks) the whole article stays invisible. An unanimated page is a far better
    // failure than an unreadable one, and this is a document format first.
    setTimeout(function () {
      if (!document.querySelector('.bp-rv.bp-in')) { io.disconnect(); revealAll(); }
    }, 1200);
  }

  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', run); else run();
})();
