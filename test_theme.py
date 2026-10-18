"""Guards for the V2 palette: both themes define the same tokens and keep text readable (WCAG contrast ratios)."""
import re

import pytest

import theme


def lum(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_both_themes_define_the_same_tokens():
    assert set(theme.LIGHT) == set(theme.DARK)
    assert {"teal", "green", "pink", "lavender", "on_accent", "text", "muted", "surface", "bg1"} <= set(theme.LIGHT)


@pytest.mark.parametrize("name, p", [("light", theme.LIGHT), ("dark", theme.DARK)])
def test_text_is_readable_on_every_surface(name, p):
    for surface in ("bg1", "bg2", "surface", "surface2", "sb1", "sb2"):
        assert contrast(p["text"], p[surface]) >= 7, (name, "text", surface)             # body text: AAA
        assert contrast(p["muted"], p[surface]) >= 4.5, (name, "muted", surface)         # secondary text: AA
    assert contrast(p["teal_d"], p["surface"]) >= 4.5 and contrast(p["green_d"], p["surface"]) >= 4.5


@pytest.mark.parametrize("name, p", [("light", theme.LIGHT), ("dark", theme.DARK)])
def test_text_on_accent_gradients_is_readable(name, p):
    for accent in ("teal", "green"):
        assert contrast(p["on_accent"], p[accent]) >= 3.5, (name, accent)               # large, bold button and tab labels


def test_palette_is_blue_white_midnight_with_pink_and_lavender():
    assert lum(theme.LIGHT["bg1"]) > .9 and lum(theme.DARK["bg1"]) < .02               # white-ish and midnight
    r, g, b = (int(theme.LIGHT["teal"][i:i + 2], 16) for i in (1, 3, 5))
    assert b > r and b > g                                                              # the primary is blue
    pr, pg, pb = (int(theme.LIGHT["pink"][i:i + 2], 16) for i in (1, 3, 5))
    assert pr > pg and pb > pg                                                          # pink: red and blue above green


def test_sidebar_and_widget_colours_are_set_explicitly_for_both_themes():
    css = theme.V2_CSS
    assert re.search(r'\[data-testid="stSidebar"\] p[^{]*\{color:var\(--text\)', css)
    assert "stWidgetLabel" in css and "background-color:var(--surface2)" in css
    assert "var(--on_accent)" in theme.CSS and "#053640" not in theme.CSS


def test_legend_text_uses_the_theme_text_colour():
    import plotly.graph_objects as go
    fig = theme.style(go.Figure(go.Bar(x=[1], y=[1])))
    assert fig.layout.legend.font.color == theme.palette()["text"]
