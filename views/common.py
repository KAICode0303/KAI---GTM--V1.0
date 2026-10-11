"""Small helpers shared by all pages."""
import pandas as pd
import streamlit as st

DOLLAR = st.column_config.NumberColumn(format="dollar")


def money_col(label):
    return st.column_config.NumberColumn(label, format="dollar")


def date_col(label):
    return st.column_config.DateColumn(label, format="MMM D, YYYY")


def show_table(df, config=None, height=None, key=None):
    """A standard read-only table (sortable by clicking headers)."""
    df = df.copy()
    for col in df.select_dtypes("float").columns:          # whole dollars look cleaner than $586,850.00
        if df[col].abs().max() > 1000:
            df[col] = df[col].round(0)
    extra = {"height": height} if height else {}
    st.dataframe(df, hide_index=True, width="stretch", column_config=config or {}, key=key, **extra)


def search(df, text, columns):
    """Case-insensitive 'contains' search across several text columns."""
    if not text or not text.strip():
        return df
    hay = df[columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
    return df[hay.str.contains(text.strip().lower(), regex=False)]


def pick_clicked(event, axis="x"):
    """Return the category the user clicked in a Plotly chart (or None)."""
    try:
        pts = event.selection.points
        return pts[0][axis] if pts else None
    except Exception:
        return None


def note(text, kind="note"):
    st.markdown(f'<div class="{kind}">{text}</div>', unsafe_allow_html=True)
