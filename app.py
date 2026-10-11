"""Kai's Company - Sales & GTM Command Center (Streamlit).

Run with:  streamlit run app.py

Flow of this file:
  1. page setup + theme (light by default, dark toggle)
  2. load all data from SQLite
  3. sidebar: navigation + global filters (period, owner, region, segment, service, stage)
  4. build one filtered `Workspace`, show the chosen page
  5. add the floating Hoomi assistant
"""
from datetime import date

import pandas as pd
import streamlit as st

import hoomi
import hoomi_widget
import metrics as m
import theme
import workspace
from views import about, accounts, content, executive, hoomi_page, leads_opps, research, revenue, sdr

st.set_page_config(page_title="Kai's Company | Sales & GTM Command Center", page_icon="✨", layout="wide", initial_sidebar_state="expanded")
st.session_state.setdefault("dark", False)
theme.apply_theme()

raw = workspace.load_raw()

PAGES = ["🏠  Command Center", "🔭  Market Intelligence", "🏢  Accounts & Prospecting", "📞  SDR Activity",
         "📄  Content & Collaterals", "💼  Leads & Opportunities", "💰  Revenue & GP", "🤖  Hoomi", "ℹ️  About"]

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown(f'<div style="display:flex;align-items:center;gap:.5rem"><div style="width:64px">{hoomi.hoomi_svg(64, "greet")}</div>'
                f'<div><div class="sb-brand">Kai\'s Company</div><div class="sb-sub">GTM Command Center</div></div></div>', unsafe_allow_html=True)
    st.toggle("🌙 Dark mode", key="dark")
    page = st.radio("Navigate", PAGES, label_visibility="collapsed", key="page")

    st.markdown('<div class="sb-label">Filters</div>', unsafe_allow_html=True)
    preset = st.selectbox("Period", ["Full year 2026", "Year to date", "Last 90 days", "Last 30 days", "Custom"], key="period",
                          help="Open deals are always a live snapshot. Won/Lost deals, leads and SDR activity follow the period.")
    today = m.AS_OF.date()
    ranges = {"Full year 2026": (date(2026, 1, 1), date(2026, 12, 31)), "Year to date": (date(2026, 1, 1), today),
              "Last 90 days": (date.fromordinal(today.toordinal() - 90), today), "Last 30 days": (date.fromordinal(today.toordinal() - 30), today)}
    if preset == "Custom":
        rng = st.date_input("Dates", (date(2026, 1, 1), today), min_value=date(2026, 1, 1), max_value=date(2026, 12, 31), key="custom_dates")
        start, end = rng if isinstance(rng, (tuple, list)) and len(rng) == 2 else ranges["Full year 2026"]
    else:
        start, end = ranges[preset]

    def pick(label, options, key):
        chosen = st.multiselect(label, options, key=key, placeholder="All")
        return chosen or list(options)      # nothing chosen = everything

    owners = pick("Sales owner", sorted(raw["opps"]["sales_owner"].unique()), "f_owner")
    regions = pick("Region", ["US", "Europe", "LATAM", "APAC"], "f_region")
    with st.expander("More filters"):
        segments = pick("Customer segment", sorted(raw["opps"]["customer_segment"].unique()), "f_segment")
        services = pick("Service", sorted(raw["opps"]["service_offering"].unique()), "f_service")
        stages = pick("Stage", m.STAGES, "f_stage")
    name = st.text_input("Hoomi calls you…", key="user_name", placeholder="Your first name")
    st.caption(f"Fictional demo data · as of {m.AS_OF:%b %d, %Y}")

# ------------------------------------------------------------------ build workspace and route
ws = workspace.build(raw, owners, regions, start, end, segments, services, stages)

if page == PAGES[0]:
    executive.render(ws, name)
elif page == PAGES[1]:
    research.render(ws)
elif page == PAGES[2]:
    accounts.render(ws)
elif page == PAGES[3]:
    sdr.render(ws)
elif page == PAGES[4]:
    content.render(ws)
elif page == PAGES[5]:
    leads_opps.render(ws)
elif page == PAGES[6]:
    revenue.render(ws)
elif page == PAGES[7]:
    hoomi_page.render(ws, name)
else:
    about.render()

hoomi_widget.render(ws, name)
