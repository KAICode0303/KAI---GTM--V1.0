"""Look & feel for Kai's Company Sales & GTM Command Center.

- Light mode is the default; dark mode uses deep teal/navy (no black).
- `apply_theme(dark)` injects all CSS (colours are CSS variables, so switching themes only swaps the variables).
- Small reusable UI helpers: kpi_card, page_header, section, empty_state, sparkles.
- Sparkles / falling particles are pure CSS, sit behind content (pointer-events: none),
  and are switched off automatically for people who prefer reduced motion.
"""
import random

import streamlit as st

LIGHT = dict(bg1="#F2FCFA", bg2="#E4F7F4", surface="#FFFFFF", surface2="#F1FBF9", text="#0A2E36", muted="#547A83",
             border="rgba(0,160,170,.18)", teal="#00C7D1", teal_d="#007F8A", green="#2BE57E", green_d="#0E9F52",
             shadow="0 6px 24px rgba(0,150,160,.10)", star="#00D6D6", chip="rgba(0,214,214,.12)", amber="#F59E0B",
             sb1="#E9FAF7", sb2="#DDF5F2")
DARK = dict(bg1="#06222B", bg2="#082D38", surface="#0E3340", surface2="#123C4A", text="#E6FBFA", muted="#8CBAC1",
            border="rgba(0,214,214,.20)", teal="#00D6D6", teal_d="#3EE6E6", green="#39FF88", green_d="#39FF88",
            shadow="0 8px 28px rgba(0,0,0,.28)", star="#7DFFE0", chip="rgba(0,214,214,.14)", amber="#FFC857",
            sb1="#072833", sb2="#0A3340")

CHART_COLORS = ["#00C7D1", "#2BE57E", "#5B8DEF", "#F5A524", "#FF7AA8", "#9B7BFF", "#FF8A5B", "#7FD6A8"]
FONT_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&display=swap');"

CSS = """
html, body, [class*="css"], .stApp, button, input, textarea {font-family:'Plus Jakarta Sans',system-ui,-apple-system,'Segoe UI',sans-serif;}
.stApp {background: radial-gradient(900px 500px at 92% -8%, color-mix(in srgb, var(--teal) 22%, transparent), transparent 70%),
                    radial-gradient(800px 500px at -5% 105%, color-mix(in srgb, var(--green) 18%, transparent), transparent 70%),
                    linear-gradient(180deg, var(--bg1), var(--bg2)); color: var(--text);}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stToolbar"], [data-testid="stDecoration"], footer {visibility:hidden; height:0;}
[data-testid="stMain"], [data-testid="stSidebar"] {position:relative; z-index:2;}
.block-container {padding-top:1.6rem; padding-bottom:4rem; max-width:1440px;}
h1,h2,h3,h4 {font-family:'Sora','Plus Jakarta Sans',sans-serif; color:var(--text); letter-spacing:-.01em;}
p, li, label, span {color:inherit;}
a {color:var(--teal_d);}

/* sidebar */
[data-testid="stSidebar"] {background:linear-gradient(180deg,var(--sb1),var(--sb2)); border-right:1px solid var(--border);}
[data-testid="stSidebar"] [role="radiogroup"] {gap:.2rem;}
[data-testid="stSidebar"] [role="radiogroup"] label {padding:.55rem .8rem; border-radius:12px; width:100%; cursor:pointer;
    transition:all .18s ease; border:1px solid transparent;}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {display:none;}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {background:var(--chip); transform:translateX(2px);}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {background:linear-gradient(90deg,var(--teal),var(--green));
    box-shadow:0 4px 14px color-mix(in srgb,var(--teal) 40%,transparent);}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {color:#053640 !important; font-weight:700;}
[data-testid="stSidebar"] [role="radiogroup"] p {font-size:.92rem; font-weight:600;}
.sb-brand {font-family:'Sora',sans-serif; font-weight:800; font-size:1.15rem; color:var(--text); line-height:1.1;}
.sb-sub {font-size:.7rem; letter-spacing:.14em; text-transform:uppercase; color:var(--teal_d); font-weight:700;}
.sb-label {font-size:.68rem; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); font-weight:700; margin:.9rem 0 .2rem;}

/* cards: bordered containers become soft rounded cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {border-radius:20px;}
div[data-testid="stVerticalBlockBorderWrapper"] {background:var(--surface); border:1px solid var(--border) !important; border-radius:20px;
    box-shadow:var(--shadow); transition:box-shadow .2s ease, transform .2s ease;}
.kpi {background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:1rem 1.1rem; box-shadow:var(--shadow);
      transition:transform .2s ease, box-shadow .2s ease; height:100%; position:relative; overflow:hidden;}
.kpi:hover {transform:translateY(-3px); box-shadow:0 12px 30px color-mix(in srgb,var(--teal) 22%,transparent);}
.kpi::after {content:""; position:absolute; right:-30px; top:-30px; width:90px; height:90px; border-radius:50%;
    background:radial-gradient(circle,color-mix(in srgb,var(--green) 28%,transparent),transparent 70%);}
.kpi .top {display:flex; align-items:center; gap:.5rem; margin-bottom:.55rem;}
.kpi .ico {width:30px; height:30px; border-radius:10px; display:flex; align-items:center; justify-content:center; background:var(--chip); font-size:1rem;}
.kpi .label {font-size:.7rem; letter-spacing:.07em; text-transform:uppercase; color:var(--muted); font-weight:700;}
.kpi .value {font-family:'Sora',sans-serif; font-size:1.75rem; font-weight:800; color:var(--text); margin:.3rem 0 .1rem; line-height:1.1;}
.kpi .sub {font-size:.76rem; color:var(--muted);}
.kpi .good {color:var(--green_d); font-weight:700;} .kpi .bad {color:#E5484D; font-weight:700;}
.tag {display:inline-block; font-size:.58rem; font-weight:800; letter-spacing:.06em; padding:2px 8px; border-radius:99px; margin-left:auto;}
.tag.fc {background:rgba(91,141,239,.16); color:#4B78D8;} .tag.act {background:color-mix(in srgb,var(--green) 22%,transparent); color:var(--green_d);}
.tag.sdr {background:rgba(155,123,255,.16); color:#7A5BE0;}

/* header / hero */
.hero {position:relative; overflow:hidden; border-radius:26px; padding:1.4rem 1.8rem; margin-bottom:1.1rem; border:1px solid var(--border);
       background:linear-gradient(120deg, color-mix(in srgb,var(--teal) 16%,var(--surface)), var(--surface) 55%, color-mix(in srgb,var(--green) 14%,var(--surface)));
       box-shadow:var(--shadow);}
.hero .eyebrow {font-size:.72rem; letter-spacing:.16em; text-transform:uppercase; color:var(--teal_d); font-weight:800;}
.hero h1 {margin:.25rem 0 .3rem; font-size:2rem; font-weight:800; background:linear-gradient(90deg,var(--teal_d),var(--green_d));
          -webkit-background-clip:text; -webkit-text-fill-color:transparent;}
.hero p {margin:0; color:var(--muted); max-width:760px; font-size:.95rem;}
.sec {display:flex; align-items:baseline; gap:.6rem; margin:1.3rem 0 .6rem;}
.sec h3 {margin:0; font-size:1.12rem;} .sec span {color:var(--muted); font-size:.84rem;}
.bubble {background:var(--surface); border:1px solid var(--border); border-radius:20px 20px 20px 6px; padding:.9rem 1.1rem; box-shadow:var(--shadow); color:var(--text);}
.pill {display:inline-block; font-size:.68rem; border:1px solid var(--teal); color:var(--teal_d); border-radius:99px; padding:1px 9px; font-weight:700;}
.note {background:var(--chip); border-left:3px solid var(--teal); border-radius:8px; padding:.55rem .8rem; font-size:.86rem; margin:.4rem 0;}
.warn {background:color-mix(in srgb,var(--amber) 14%,transparent); border-left:3px solid var(--amber); border-radius:8px; padding:.55rem .8rem; font-size:.86rem; margin:.35rem 0;}
.ok {background:color-mix(in srgb,var(--green) 14%,transparent); border-left:3px solid var(--green_d); border-radius:8px; padding:.55rem .8rem; font-size:.86rem; margin:.35rem 0;}
.empty {text-align:center; padding:2.2rem 1rem; color:var(--muted);} .empty .big {font-size:2.2rem;}
.empty b {display:block; color:var(--text); font-size:1.05rem; margin:.3rem 0;}

/* tabs, buttons, inputs */
.stTabs [data-baseweb="tab-list"] {gap:.35rem; border-bottom:none;}
.stTabs [data-baseweb="tab"] {border-radius:99px; padding:.35rem 1rem; background:var(--chip); height:auto; transition:all .15s;}
.stTabs [data-baseweb="tab"]:hover {background:color-mix(in srgb,var(--teal) 24%,transparent);}
.stTabs [aria-selected="true"] {background:linear-gradient(90deg,var(--teal),var(--green)) !important;}
.stTabs [aria-selected="true"] p {color:#053640 !important; font-weight:700;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display:none;}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {border-radius:12px; border:1px solid var(--border); transition:all .18s ease; font-weight:600;}
.stButton > button:hover, .stDownloadButton > button:hover {transform:translateY(-1px); border-color:var(--teal); box-shadow:0 4px 14px color-mix(in srgb,var(--teal) 25%,transparent);}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {background:linear-gradient(90deg,var(--teal),var(--green)); color:#053640; border:none;}
[data-testid="stExpander"] {border-radius:16px; border:1px solid var(--border); background:var(--surface);}
[data-testid="stDataFrame"] {border-radius:14px; overflow:hidden;}

/* sparkles, stars and falling particles (decorative only) */
.star {position:absolute; background:var(--star); clip-path:polygon(50% 0,61% 39%,100% 50%,61% 61%,50% 100%,39% 61%,0 50%,39% 39%);
       filter:drop-shadow(0 0 4px var(--star)); animation:twinkle 3.2s ease-in-out infinite; pointer-events:none;}
@keyframes twinkle {0%,100%{opacity:.25; transform:scale(.7) rotate(0)} 50%{opacity:1; transform:scale(1.1) rotate(20deg)}}
.field {position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden;}
.field i {position:absolute; top:-20px; width:6px; height:6px; border-radius:50%; background:var(--star); opacity:0;
          box-shadow:0 0 8px var(--star); animation:fall linear infinite;}
.field i.s {border-radius:0; width:9px; height:9px; clip-path:polygon(50% 0,61% 39%,100% 50%,61% 61%,50% 100%,39% 61%,0 50%,39% 39%); box-shadow:none;}
@keyframes fall {0%{transform:translate3d(0,-20px,0); opacity:0} 10%{opacity:.5} 90%{opacity:.35} 100%{transform:translate3d(30px,105vh,0); opacity:0}}
@media (prefers-reduced-motion: reduce) {.star, .field i {animation:none !important;} .star{opacity:.6} .field{display:none}
  .kpi, .stButton > button, [data-testid="stSidebar"] [role="radiogroup"] label {transition:none !important;}}
"""


def is_dark():
    return bool(st.session_state.get("dark", False))


def palette():
    return DARK if is_dark() else LIGHT


def apply_theme():
    """Switch Streamlit's own theme (widgets, tables) and inject our CSS."""
    p = palette()
    for key, val in {"base": "dark" if is_dark() else "light", "backgroundColor": p["bg1"],
                     "secondaryBackgroundColor": p["surface2"], "textColor": p["text"], "primaryColor": p["teal"]}.items():
        try:
            st._config.set_option(f"theme.{key}", val)    # lets widgets and tables follow the toggle
        except Exception:
            pass                                          # if Streamlit changes this, our CSS still themes the page
    variables = ";".join(f"--{k}:{v}" for k, v in p.items())
    st.markdown(f"<style>{FONT_IMPORT}:root{{{variables}}}{CSS}</style>", unsafe_allow_html=True)
    st.markdown(particle_field(), unsafe_allow_html=True)


def particle_field(n=16):
    rnd = random.Random(3)
    bits = "".join(
        f'<i class="{"s" if k % 3 == 0 else ""}" style="left:{rnd.randint(1, 98)}%;animation-duration:{rnd.randint(16, 30)}s;'
        f'animation-delay:-{rnd.randint(0, 28)}s"></i>' for k in range(n))
    return f'<div class="field" aria-hidden="true">{bits}</div>'


def sparkles(spots=None):
    """A few twinkling stars for headers; spots = list of (left%, top%, size_px, delay_s)."""
    spots = spots or [(78, 18, 16, 0), (88, 60, 11, 1.1), (64, 70, 9, .6), (94, 22, 8, 2), (52, 14, 7, 1.6), (70, 40, 6, 2.4)]
    return "".join(f'<span class="star" aria-hidden="true" style="left:{x}%;top:{y}%;width:{s}px;height:{s}px;animation-delay:{d}s"></span>'
                   for x, y, s, d in spots)


def page_header(title, subtitle, eyebrow="Kai's Company"):
    st.markdown(f'<div class="hero">{sparkles()}<div class="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)


def section(title, hint=""):
    st.markdown(f'<div class="sec"><h3>{title}</h3><span>{hint}</span></div>', unsafe_allow_html=True)


def safe(text):
    """Stop Streamlit's markdown from treating $...$ as maths (our text is full of dollar amounts)."""
    return str(text).replace("$", "&#36;")


def kpi_card(label, value, sub="", tag="", icon="✨", tip=""):
    cls = {"FORECAST": "fc", "ACTUAL": "act", "SDR": "sdr"}.get(tag, "")
    tg = f'<span class="tag {cls}">{tag}</span>' if tag else ""
    st.markdown(safe(f'<div class="kpi" title="{tip}"><div class="top"><div class="ico">{icon}</div>{tg}</div>'
                     f'<div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'),
                unsafe_allow_html=True)


def empty_state(title, text, icon="🔍"):
    st.markdown(f'<div class="empty"><div class="big">{icon}</div><b>{title}</b>{text}</div>', unsafe_allow_html=True)


def style(fig, height=360, legend_bottom=True):
    """One consistent look for every Plotly chart (light or dark)."""
    p = palette()
    fig.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=CHART_COLORS,
                      template="plotly_dark" if is_dark() else "plotly_white", margin=dict(l=8, r=8, t=44, b=8),
                      font=dict(family="Plus Jakarta Sans, system-ui, sans-serif", color=p["text"], size=12),
                      title=dict(font=dict(family="Sora, sans-serif", size=15, color=p["text"]), x=0.01),
                      hoverlabel=dict(bgcolor=p["surface"], font_color=p["text"], bordercolor=p["teal"]),
                      legend=dict(orientation="h", y=-0.18 if legend_bottom else 1.12, x=0, font=dict(size=11)))
    grid = "rgba(0,214,214,.12)" if is_dark() else "rgba(0,120,130,.10)"
    fig.update_xaxes(gridcolor=grid, zeroline=False, linecolor=grid)
    fig.update_yaxes(gridcolor=grid, zeroline=False, linecolor=grid)
    return fig
