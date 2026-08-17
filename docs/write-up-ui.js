// write-up-ui.js --- shared runtime for every write-up article (like glossary.js).
// Adds a persistent Old/New reading toggle plus the "New" presentation layer on top of the
// article's own (Old) Grokipedia styles: buttery scroll reveals, link underline-draw, infobox
// image reveal, and styling for the Decisions (ADR log) + Day-by-day (journal) sections.
//   OLD = the article exactly as authored (static, hides Decisions/Day-by-day).
//   NEW = motion + those two sections shown.
// The reader's choice persists in localStorage across articles. Self-injecting: one <script>
// include per article is all it takes; nothing per-article to maintain. No network, no deps.
(function () {
  if (window.__bpUI) return; window.__bpUI = true;

  var CSS = `
:root{--bp-accent:#ff6e14;--bp-ease:cubic-bezier(.22,1,.36,1);}

/* ===== NEW mode: motion + interactions ===== */
body.new .bp-rv{opacity:0;transform:translateY(16px);
  transition:opacity .85s var(--bp-ease),transform .85s var(--bp-ease);}
body.new .bp-rv.bp-in{opacity:1;transform:none;}
body.new article a{text-decoration:none;background-image:linear-gradient(currentColor,currentColor);
  background-size:0 1px;background-repeat:no-repeat;background-position:0 92%;transition:background-size .4s var(--bp-ease);}
body.new article a:hover{background-size:100% 1px;}
body.new .infobox img{clip-path:inset(0 0 100% 0);transform:scale(1.06);
  transition:clip-path 1.1s var(--bp-ease),transform 1.4s var(--bp-ease);}
body.new .infobox.bp-in img{clip-path:inset(0 0 0 0);transform:none;}
@media(prefers-reduced-motion:reduce){
  body.new .bp-rv,body.new .infobox img{opacity:1!important;transform:none!important;clip-path:none!important;transition:none!important;}
}

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

/* ===== OLD mode: hide the New-only sections ===== */
body.old #decisions,body.old #journal,body.old .toc-new{display:none;}

/* ===== toggle bar ===== */
#bp-ab{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:60;display:flex;align-items:center;gap:2px;
  background:#000;border:1px solid rgba(255,255,255,.2);border-radius:999px;padding:5px;box-shadow:0 10px 34px rgba(0,0,0,.45);}
#bp-ab button{background:none;border:0;color:#b5b5b5;font:600 13px system-ui,sans-serif;padding:7px 20px;border-radius:999px;cursor:pointer;transition:.18s;}
#bp-ab button.on{background:#fff;color:#000;}
`;

  function run() {
    var s = document.createElement('style'); s.textContent = CSS; document.head.appendChild(s);

    // reveal targets (no per-article markup needed)
    var sel = 'article > p, article > h1, .infobox, article section > h2, article section > p,' +
              ' article section > ul, article section > ol, article section > figure, .dec, .day';
    var items = [].slice.call(document.querySelectorAll(sel));
    items.forEach(function (el) { el.classList.add('bp-rv'); });

    var io = null;
    if ('IntersectionObserver' in window) {
      io = new IntersectionObserver(function (es, o) {
        es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('bp-in'); o.unobserve(e.target); } });
      }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });
    }
    function observe() { if (io) items.forEach(function (el) { io.observe(el); }); else items.forEach(function (el) { el.classList.add('bp-in'); }); }

    // toggle bar
    var bar = document.createElement('div'); bar.id = 'bp-ab';
    bar.innerHTML = '<button data-m="old">Old</button><button data-m="new">New</button>';
    document.body.appendChild(bar);
    var btns = [].slice.call(bar.querySelectorAll('button'));

    function setMode(m) {
      document.body.classList.remove('old', 'new'); document.body.classList.add(m);
      btns.forEach(function (b) { b.classList.toggle('on', b.dataset.m === m); });
      try { localStorage.setItem('bp-mode', m); } catch (e) {}
      if (m === 'new') { items.forEach(function (el) { el.classList.remove('bp-in'); }); if (io) io.disconnect(); observe(); }
    }
    btns.forEach(function (b) { b.addEventListener('click', function () { setMode(b.dataset.m); }); });
    addEventListener('keydown', function (e) {
      if (['INPUT', 'TEXTAREA'].indexOf((document.activeElement || {}).tagName) > -1) return;
      if (e.key === 'o') setMode('old'); if (e.key === 'n') setMode('new');
    });

    var saved = null; try { saved = localStorage.getItem('bp-mode'); } catch (e) {}
    setMode(saved || 'new');
  }

  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', run); else run();
})();
