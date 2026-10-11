"""The floating Hoomi assistant (bottom-right of every page).

Streamlit pages can't float things on their own, so we use a small trick:
  1. Python calculates everything Hoomi will say (briefing, priorities, alerts, quick answers).
  2. `components.html` runs a tiny JavaScript that builds the floating widget inside the page.
The widget is click-to-expand, draggable (position remembered), and shows a welcome animation on the
first visit. Quick-question chips are answered from the pre-computed Python results, so the numbers
always match the dashboard.
"""
import hashlib
import json

import streamlit.components.v1 as components

import analytics as a
import hoomi
import metrics as m
import theme

WIDGET_CSS = """
#hoomi-root{--hs:%(surface)s;--hs2:%(surface2)s;--ht:%(text)s;--hm:%(muted)s;--hb:%(border)s;--hteal:%(teal)s;--hgreen:%(green)s;--htd:%(teal_d)s;
 position:fixed;right:22px;bottom:22px;z-index:2147483000;font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif;color:var(--ht)}
#hm-launch{background:none;border:0;padding:0;cursor:grab;position:relative;touch-action:none;filter:drop-shadow(0 10px 18px rgba(0,190,200,.38));display:block}
#hm-launch:active{cursor:grabbing}
.hm-badge{position:absolute;top:4px;right:2px;min-width:22px;height:22px;padding:0 5px;box-sizing:border-box;border-radius:99px;background:#FFC857;color:#5A3B00;font:800 12px/22px sans-serif;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.hm-tease{position:absolute;right:94px;bottom:46px;background:var(--hs);color:var(--ht);border:1px solid var(--hb);border-radius:16px 16px 4px 16px;padding:.5rem .8rem;font-size:13px;font-weight:600;white-space:nowrap;box-shadow:0 6px 20px rgba(0,150,160,.18);animation:hm-pop .4s ease}
#hm-panel{position:absolute;right:0;bottom:108px;width:396px;max-width:calc(100vw - 28px);max-height:70vh;display:none;flex-direction:column;border-radius:24px;background:var(--hs);border:1px solid var(--hb);box-shadow:0 18px 50px rgba(0,60,70,.28);overflow:hidden}
#hm-panel.open{display:flex;animation:hm-pop .28s ease}
@keyframes hm-pop{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:none}}
.hm-head{display:flex;align-items:center;gap:.6rem;padding:.7rem 1rem;cursor:grab;touch-action:none;background:linear-gradient(110deg,color-mix(in srgb,var(--hteal) 26%%,var(--hs)),var(--hs) 70%%,color-mix(in srgb,var(--hgreen) 20%%,var(--hs)));border-bottom:1px solid var(--hb);position:relative;overflow:hidden}
.hm-head b{font:800 16px 'Sora',sans-serif} .hm-head small{display:block;color:var(--hm);font-size:11px}
.hm-x{margin-left:auto;background:var(--hs2);border:1px solid var(--hb);color:var(--ht);width:28px;height:28px;border-radius:50%%;cursor:pointer;font-size:14px}
.hm-body{overflow:auto;padding:.8rem 1rem 1rem;font-size:13.5px;line-height:1.45}
.hm-body details{border:1px solid var(--hb);border-radius:14px;margin:.45rem 0;background:var(--hs2);overflow:hidden}
.hm-body summary{cursor:pointer;padding:.55rem .8rem;font-weight:700;list-style:none}
.hm-body summary::-webkit-details-marker{display:none}
.hm-body summary:after{content:'+';float:right;color:var(--htd)} .hm-body details[open] summary:after{content:'–'}
.hm-body .in{padding:0 .8rem .7rem} .hm-body ul{margin:.2rem 0 .2rem 1.1rem;padding:0} .hm-body li{margin:.25rem 0}
.hm-bubble{background:var(--hs2);border:1px solid var(--hb);border-radius:16px 16px 16px 4px;padding:.6rem .8rem;margin-bottom:.4rem}
.hm-chips{display:flex;flex-wrap:wrap;gap:.35rem;margin:.4rem 0}
.hm-chip{border:1px solid var(--hb);background:var(--hs);color:var(--ht);border-radius:99px;padding:.3rem .7rem;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s}
.hm-chip:hover{background:linear-gradient(90deg,var(--hteal),var(--hgreen));color:#053640;border-color:transparent}
#hm-answer{margin-top:.4rem;min-height:20px}
.hm-foot{font-size:10.5px;color:var(--hm);padding:.4rem 1rem;border-top:1px solid var(--hb)}
.hm-welcome{text-align:center;position:relative;padding:.3rem 0 .6rem}
.hm-welcome button{margin-top:.5rem;border:0;border-radius:99px;padding:.5rem 1.1rem;font-weight:800;color:#053640;cursor:pointer;background:linear-gradient(90deg,var(--hteal),var(--hgreen))}
.hm-star{position:absolute;background:var(--hteal);clip-path:polygon(50%% 0,61%% 39%%,100%% 50%%,61%% 61%%,50%% 100%%,39%% 61%%,0 50%%,39%% 39%%);animation:hm-tw 2.6s ease-in-out infinite;pointer-events:none}
@keyframes hm-tw{0%%,100%%{opacity:.2;transform:scale(.6)}50%%{opacity:1;transform:scale(1.1) rotate(25deg)}}
@media (prefers-reduced-motion: reduce){.hm-star,.hm-tease,#hm-panel.open{animation:none !important}}
"""

JS = r"""
(function () {
  var P = __PAYLOAD__;
  var win = window.parent, doc = win.document;
  var hash = P.sig;
  var H = win.__hoomi = win.__hoomi || {open: false};
  if (doc.getElementById('hoomi-root') && H.hash === hash) return;   // nothing changed: keep the widget as is
  H.hash = hash;
  if (H.timer) win.clearInterval(H.timer);
  ['hoomi-root', 'hoomi-style'].forEach(function (id) { var e = doc.getElementById(id); if (e) e.remove(); });

  var style = doc.createElement('style'); style.id = 'hoomi-style'; style.textContent = P.css; doc.head.appendChild(style);
  var li = function (arr) { return '<ul>' + arr.map(function (x) { return '<li>' + x + '</li>'; }).join('') + '</ul>'; };
  var none = function (t) { return '<i>' + t + '</i>'; };
  var firstVisit = false;
  try { firstVisit = !win.localStorage.getItem('hoomi_seen'); } catch (e) {}

  var alertsHtml = P.alerts.length ? li(P.alerts) : none('Nothing urgent. Nice work!');
  var root = doc.createElement('div'); root.id = 'hoomi-root';
  root.innerHTML =
    '<div id="hm-panel" role="dialog" aria-label="Hoomi assistant">' +
      '<div class="hm-head" id="hm-drag">' + P.svgSmall +
        '<div><b>Hoomi</b><small>Your sales intelligence buddy</small></div>' +
        '<button class="hm-x" data-nodrag="1" aria-label="Close Hoomi">✕</button></div>' +
      '<div class="hm-body">' +
        '<div id="hm-welcome" class="hm-welcome" style="display:none"></div>' +
        '<div class="hm-bubble" id="hm-greet"></div>' +
        '<details open><summary>📋 Executive briefing</summary><div class="in">' + li(P.bullets) + '</div></details>' +
        '<details open><summary>🎯 Top 5 priorities</summary><div class="in">' +
          li(P.priorities.map(function (p) { return p.icon + ' <b>' + p.title + '</b><br><span style="color:var(--hm)">' + p.detail + '</span>'; })) + '</div></details>' +
        '<details><summary>⚠️ Stalled & overdue (' + P.alerts.length + ')</summary><div class="in">' + alertsHtml + '</div></details>' +
        '<details><summary>📞 SDR productivity</summary><div class="in">' + li(P.sdr) + '</div></details>' +
        '<details><summary>📄 Collateral deadlines</summary><div class="in">' + li(P.collateral) + '</div></details>' +
        '<details open><summary>💬 Ask Hoomi</summary><div class="in"><div class="hm-chips" id="hm-chips"></div><div id="hm-answer"></div></div></details>' +
      '</div>' +
      '<div class="hm-foot">Insights are calculated locally from the demo data.</div></div>' +
    '<div class="hm-tease" id="hm-tease" style="display:none">Need a quick briefing? 👋</div>' +
    '<button id="hm-launch" aria-label="Open Hoomi assistant">' + P.svgBig +
      (P.badge ? '<span class="hm-badge">' + P.badge + '</span>' : '') + '</button>';
  doc.body.appendChild(root);

  var panel = root.querySelector('#hm-panel'), launch = root.querySelector('#hm-launch');
  var faces = function () { return root.querySelectorAll('.hm'); };
  var setState = function (s) { faces().forEach(function (f) { f.setAttribute('data-state', s); }); };
  root.querySelector('#hm-greet').innerHTML = P.greeting;

  // quick-question chips (answers were pre-computed in Python)
  var chips = root.querySelector('#hm-chips'), answer = root.querySelector('#hm-answer'), settle;
  Object.keys(P.faq).forEach(function (q) {
    var b = doc.createElement('button'); b.className = 'hm-chip'; b.textContent = q; chips.appendChild(b);
    b.addEventListener('click', function () {
      setState('think'); answer.innerHTML = '<i>Hoomi is thinking…</i>'; win.clearTimeout(settle);
      win.setTimeout(function () {
        answer.innerHTML = '<div class="hm-bubble">' + P.faq[q][0] + '</div>';
        setState(P.faq[q][1] === 'alert' ? 'alert' : 'success');
        settle = win.setTimeout(function () { setState('greet'); }, 4000);
      }, 650);
    });
  });

  // open / close
  function place() {   // keep the panel on screen wherever the user dragged Hoomi
    var r = root.getBoundingClientRect(), room = r.bottom - 120;
    panel.style.maxHeight = Math.max(220, Math.min(win.innerHeight * 0.7, room)) + 'px';
  }
  function setOpen(o) {
    H.open = o; panel.classList.toggle('open', o);
    root.querySelector('#hm-tease').style.display = 'none';
    if (o) { place(); try { win.localStorage.setItem('hoomi_seen', '1'); } catch (e) {} }
  }
  root.querySelector('.hm-x').addEventListener('click', function () { setOpen(false); root.querySelector('#hm-welcome').style.display = 'none'; });

  // draggable (launcher and panel header). A tiny move counts as a click.
  function drag(handle, onClick) {
    var d = null;
    handle.addEventListener('pointerdown', function (e) {
      if (e.target.closest('[data-nodrag]')) return;
      var r = root.getBoundingClientRect();
      d = {x: e.clientX, y: e.clientY, right: win.innerWidth - r.right, bottom: win.innerHeight - r.bottom, moved: false};
      handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener('pointermove', function (e) {
      if (!d) return;
      var dx = e.clientX - d.x, dy = e.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 5) d.moved = true;
      if (d.moved) {
        root.style.right = Math.min(Math.max(d.right - dx, 6), win.innerWidth - 100) + 'px';
        root.style.bottom = Math.min(Math.max(d.bottom - dy, 6), win.innerHeight - 100) + 'px';
      }
    });
    handle.addEventListener('pointerup', function () {
      if (!d) return;
      if (d.moved) { place(); try { win.localStorage.setItem('hoomi_pos', JSON.stringify({r: root.style.right, b: root.style.bottom})); } catch (e) {} }
      else if (onClick) onClick();
      d = null;
    });
  }
  drag(launch, function () { setOpen(!H.open); });
  drag(root.querySelector('#hm-drag'), null);
  try {
    var pos = JSON.parse(win.localStorage.getItem('hoomi_pos') || 'null');
    if (pos) { root.style.right = pos.r; root.style.bottom = pos.b; }
  } catch (e) {}

  // gentle attention-getter: every ~25s, if there is something to look at, Hoomi briefly looks alert
  if (P.badge) H.timer = win.setInterval(function () {
    if (H.open) return; setState('alert'); win.setTimeout(function () { setState('greet'); }, 2600);
  }, 25000);

  // first visit: animated welcome
  var wel = root.querySelector('#hm-welcome');
  if (firstVisit) {
    var stars = [[8, 12, 14], [86, 8, 10], [92, 55, 12], [4, 62, 9], [50, 2, 8]].map(function (s, i) {
      return '<span class="hm-star" style="left:' + s[0] + '%;top:' + s[1] + '%;width:' + s[2] + 'px;height:' + s[2] + 'px;animation-delay:' + (i * .4) + 's"></span>';
    }).join('');
    wel.style.display = 'block';
    wel.innerHTML = stars + '<b style="font:800 18px Sora,sans-serif">Welcome to Kai\'s Company!</b><div id="hm-type" style="min-height:42px;margin-top:.3rem;color:var(--hm)"></div>' +
      '<button id="hm-go">Show me my briefing ✨</button>';
    setState('success'); setOpen(true);
    var msg = "Hi, I'm Hoomi! I read your pipeline, SDR activity and deadlines so you don't have to.", i = 0, t = root.querySelector('#hm-type');
    var typer = win.setInterval(function () { t.textContent = msg.slice(0, ++i); if (i >= msg.length) win.clearInterval(typer); }, 22);
    root.querySelector('#hm-go').addEventListener('click', function () { wel.style.display = 'none'; setState('greet'); });
  } else {
    setState('greet'); if (H.open) { panel.classList.add('open'); place(); }
    else { var te = root.querySelector('#hm-tease'); te.style.display = 'block'; win.setTimeout(function () { te.style.display = 'none'; }, 5000); }
  }
})();
"""


def render(ws, name=""):
    """Build the floating Hoomi for the current (filtered) workspace."""
    opps = ws.opps
    b = hoomi.briefing(ws, name)
    alerts = hoomi.overdue_alerts(opps)[:4] + hoomi.stalled_alerts(opps)[:4]
    n_alerts = len(m.stalled_deals(opps)) + len(m.overdue_followups(opps))
    p = theme.palette()
    payload = {
        "css": hoomi.HOOMI_CSS + WIDGET_CSS % {k: p[k] for k in ["surface", "surface2", "text", "muted", "border", "teal", "green", "teal_d"]},
        "svgBig": hoomi.hoomi_svg(92, "greet"), "svgSmall": hoomi.hoomi_svg(54, "greet"),
        "greeting": hoomi.md_to_html(b["greeting"]),
        "bullets": [hoomi.md_to_html(x).replace("<br>", "") for x in b["bullets"]],
        "priorities": [{"icon": x["icon"], "title": x["title"], "detail": x["detail"]} for x in hoomi.top_priorities(ws)],
        "alerts": [hoomi.md_to_html(x).replace("<br>", "") for x in alerts],
        "sdr": [hoomi.md_to_html(x).replace("<br>", "") for x in hoomi.sdr_summary(ws)],
        "collateral": [hoomi.md_to_html(x).replace("<br>", "") for x in hoomi.collateral_flags(ws)],
        "faq": hoomi.faq_answers(ws), "badge": n_alerts,
    }
    payload["sig"] = hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()   # rebuild only when content changes
    data = json.dumps(payload).replace("</", "<\\/")
    components.html(f"<script>{JS.replace('__PAYLOAD__', data)}</script>", height=0)
