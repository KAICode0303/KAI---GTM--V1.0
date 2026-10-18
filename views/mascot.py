"""Hoomi's mascot slot.

The final Hoomi artwork (a gender-neutral robotic cat based on the Pixel Creative Strategist) has NOT been supplied yet, and this
project does not invent it. Until it exists, a clearly labelled placeholder is shown. To install the real asset, put a file named
`hoomi.png`, `hoomi.svg`, `hoomi.webp` or `hoomi.jpg` in assets/hoomi/ - no code change is needed.
"""
import base64
from pathlib import Path

import streamlit as st

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "hoomi"
_TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def asset_path():
    for ext in _TYPES:
        p = ASSET_DIR / f"hoomi{ext}"
        if p.is_file():
            return p
    return None


def html(width=220):
    """Mascot markup: the supplied asset if present, otherwise the labelled placeholder."""
    p = asset_path()
    if p:
        data = base64.b64encode(p.read_bytes()).decode()
        return (f'<div class="mascot-img" style="width:{width}px"><img alt="Hoomi" style="width:100%" '
                f'src="data:{_TYPES[p.suffix.lower()]};base64,{data}"></div>')
    return ('<div class="mascot-ph" role="img" aria-label="Hoomi mascot placeholder">'
            '<div class="orb" aria-hidden="true">H</div><b>Hoomi</b>'
            '<small>Mascot placeholder. The final Pixel Creative Strategist artwork is not installed yet '
            '(add assets/hoomi/hoomi.png to show it here).</small></div>')


def render(width=220):
    st.markdown(html(width), unsafe_allow_html=True)
