"""Hoomi's mascot: an interactive 3D robotic cat (Three.js), isolated in its own iframe component.

The component lives in static/hoomi3d/ and is served by Streamlit's static file serving (.streamlit/config.toml: enableStaticServing).
It is a self-contained page: it loads only its own files (vendored Three.js, MIT), makes no network calls and sends nothing anywhere.
Two instances: HERO on the Welcome page and in the Ask Hoomi header, and a small FLOATING one at the bottom-right of every page.
Clicking either asks the page to open Ask Hoomi: the component presses a hidden Streamlit button (navigation only).
The earlier 2D mascot is retired; its file is kept in assets/hoomi_pixel_backup/ and is not referenced by the app.
"""
import streamlit as st

NAME = "Hoomi"
CAPTION = "Hoomi, your robotic GTM cat"
URL = "/app/static/hoomi3d/hoomi3d.html"
HERO_ASPECT = 1.12                 # height / width of the hero stage
FAB_SIZE = 116


def hero_height(width):
    return int(width * HERO_ASPECT)


def render(width=300, caption=False):
    """The full 3D cat. The stage fills its column; `width` only sets how tall it is."""
    st.iframe(f"{URL}?mode=hero", height=hero_height(width))
    if caption:
        st.caption(CAPTION)


FAB_CSS = f"""<style>
.st-key-hoomi_fab3d {{position:fixed; right:10px; bottom:6px; z-index:1000; width:{FAB_SIZE}px !important; height:{FAB_SIZE}px;}}
.st-key-hoomi_fab3d iframe {{border:0; background:transparent; color-scheme:light; width:{FAB_SIZE}px; height:{FAB_SIZE}px;}}
.st-key-hoomi_fab3d::after {{content:"Ask Hoomi"; position:absolute; right:{FAB_SIZE - 14}px; top:30px; padding:3px 10px; border-radius:99px; font:700 .72rem 'Plus Jakarta Sans',sans-serif;
    background:var(--surface); color:var(--text); border:1px solid var(--border); box-shadow:var(--shadow); opacity:0; transform:translateX(6px); transition:all .2s ease; pointer-events:none; white-space:nowrap;}}
.st-key-hoomi_fab3d:hover::after {{opacity:1; transform:none;}}
.st-key-hoomi_open_chat {{position:fixed; left:-9999px; top:0; width:1px; height:1px; overflow:hidden;}}   /* the 3D cat presses this: it must exist in the page, but never be seen */
@media (max-width: 640px) {{.st-key-hoomi_fab3d, .st-key-hoomi_fab3d iframe {{width:96px !important; height:96px !important;}} .st-key-hoomi_fab3d {{right:6px; bottom:6px;}}}}
@media (min-width: 641px) {{.block-container {{padding-bottom: 8rem;}}}}   /* content can scroll clear of the floating cat */
</style>"""


def fab(on_click):
    """The floating 3D Hoomi (bottom-right) plus the hidden button that opens Ask Hoomi. `on_click` runs when the cat is clicked."""
    st.markdown(FAB_CSS, unsafe_allow_html=True)
    with st.container(key="hoomi_open_chat"):
        st.button("Open Ask Hoomi", key="hoomi_open_chat_btn", on_click=on_click)
    with st.container(key="hoomi_fab3d"):
        st.iframe(f"{URL}?mode=fab", height=FAB_SIZE, width=FAB_SIZE)
