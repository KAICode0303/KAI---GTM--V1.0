"""Hoomi's mascot: ONE artwork, shown consistently everywhere (Welcome, Ask Hoomi, classic pages, floating button).

The supplied file is a brand sheet (assets/hoomi/hoomi.png, 1536x1024). It is never modified. For display, two crops of that same artwork are
made in memory: the HERO cat (Welcome and page headers; no text, no side panels) and the round APP ICON tile (the small floating button).
If a different, already-single-pose image is dropped into assets/hoomi/ (hoomi.png, .svg, .webp, .jpg) it is shown as is. With no artwork at all,
a clearly labelled placeholder is used.
"""
import base64
import functools
from io import BytesIO
from pathlib import Path

import streamlit as st

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "hoomi"
_TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

CAPTION = "Pixel — Your Creative GTM Strategist"
SHEET_SIZE = (1536, 1024)                    # the supplied brand sheet
CAT_CROP = (352, 8, 674, 540)                # the hero cat only: no title text, no speech bubble, nothing from the right-hand panel
ICON_CROP = (52, 820, 196, 964)              # the sheet's round "App Icon" tile
ICON_CIRCLE = (6, 8, 134, 136)               # the circle inside that tile (made transparent outside it)
WIDTHS = {"hero": 480, "icon": 144}


def asset_path():
    for ext in _TYPES:
        p = ASSET_DIR / f"hoomi{ext}"
        if p.is_file():
            return p
    return None


@functools.lru_cache(maxsize=8)
def _prepared(path, mtime, kind):
    """(base64, mime) of the mascot for `kind` ('hero' or 'icon'), cropped in memory. The file on disk is never written."""
    p = Path(path)
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            from PIL import Image, ImageDraw
            img = Image.open(p).convert("RGBA")
            if img.size == SHEET_SIZE:
                img = img.crop(CAT_CROP if kind == "hero" else ICON_CROP)
                if kind == "icon":
                    mask = Image.new("L", img.size, 0)
                    ImageDraw.Draw(mask).ellipse(ICON_CIRCLE, fill=255)
                    img.putalpha(mask)
            width = WIDTHS[kind]
            if img.width > width:
                img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode(), "image/png"
        except Exception:
            pass
    return base64.b64encode(p.read_bytes()).decode(), _TYPES[p.suffix.lower()]


def data_uri(kind="hero"):
    p = asset_path()
    if not p:
        return None
    data, mime = _prepared(str(p), p.stat().st_mtime, kind)
    return f"data:{mime};base64,{data}"


def html(width=220, caption=True, float_=True):
    """Hero mascot markup: the supplied artwork (cropped to the cat) if present, otherwise the labelled placeholder."""
    uri = data_uri("hero")
    if uri:
        cap = f'<div style="text-align:center;font-weight:700;font-size:.78rem;line-height:1.25;margin-top:.35rem;color:var(--text)">{CAPTION}</div>' if caption else ""
        return (f'<div class="mascot-img{" float" if float_ else ""}" style="width:{width}px"><img alt="Hoomi, {CAPTION}" '
                f'style="width:100%;display:block" src="{uri}">{cap}</div>')
    return ('<div class="mascot-ph" role="img" aria-label="Hoomi mascot placeholder">'
            '<div class="orb" aria-hidden="true">H</div><b>Hoomi</b>'
            '<small>Mascot placeholder. The final Pixel Creative Strategist artwork is not installed yet '
            '(add assets/hoomi/hoomi.png to show it here).</small></div>')


def render(width=220, caption=True):
    st.markdown(html(width, caption), unsafe_allow_html=True)


def fab(on_click):
    """The small floating mascot at the bottom-right. Clicking it calls `on_click` (the app uses it to open Hoomi chat)."""
    uri = data_uri("icon")
    face = (f"background-image:url({uri});background-size:cover;background-position:center;" if uri
            else "background:linear-gradient(135deg,var(--teal),var(--green));")
    st.markdown(f"<style>.st-key-hoomi_fab button{{{face}}}</style>", unsafe_allow_html=True)
    with st.container(key="hoomi_fab"):
        st.button("Ask Hoomi", key="hoomi_fab_btn", help="Ask Hoomi", on_click=on_click)
