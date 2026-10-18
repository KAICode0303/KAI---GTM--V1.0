"""Kai's GTM V2.0 (Hoomi) - Streamlit app.

Run with:  streamlit run app.py

Flow of this file:
  1. page setup + theme (light by default, dark toggle)
  2. Welcome screen: pick Leadership Hub or GTM Team (navigation only, not a login)
  3. sidebar: V2 pages (Executive Pulse, Ask Hoomi, GTM Workspace) and the classic V1 views with their original filters
  4. route to the chosen page

Two separate synthetic data stores, both local and git-ignored: the V2 workspace (data/gtm_v2.db: Pulse, Workspace, Ask Hoomi) and the V1
store (data/kai_gtm.db: the classic views). They start from the same demo records but are edited independently.
"""
from datetime import date

import streamlit as st

import hoomi_widget
import metrics as m
import theme
import workspace
from gtm.store import GTMStore, default_path
from views import about, accounts, content, executive, hoomi_page, leads_opps, pulse, research, revenue, sdr, welcome, workspace_gtm

st.set_page_config(page_title="Kai's GTM V2.0 | Hoomi", page_icon="✨", layout="wide", initial_sidebar_state="expanded")
st.session_state.setdefault("dark", False)
st.session_state.setdefault("role", None)
theme.apply_theme()

PULSE, HOOMI, WORKSPACE = "📊  Executive Pulse", "🤖  Ask Hoomi", "🗂️  GTM Workspace"
CLASSIC = ["🏠  Command Center", "🔭  Market Intelligence", "🏢  Accounts & Prospecting", "📞  SDR Activity",
           "📄  Content & Collaterals", "💼  Leads & Opportunities", "💰  Revenue & GP", "ℹ️  About"]


@st.cache_resource
def get_store(path):
    return GTMStore(path)                    # created and seeded on first use; the path is part of the cache key


def sidebar_brand():
    st.markdown('<div style="display:flex;align-items:center;gap:.6rem"><div style="width:44px;height:44px;border-radius:50%;display:flex;align-items:center;'
                'justify-content:center;font:800 1.2rem Sora,sans-serif;color:var(--on_accent);background:linear-gradient(135deg,var(--teal),var(--green))">H</div>'
                '<div><div class="sb-brand">Kai\'s GTM V2.0</div><div class="sb-sub">with Hoomi</div></div></div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ welcome gate
if st.session_state.role is None:
    with st.sidebar:
        sidebar_brand()
        st.toggle("🌙 Dark mode", key="dark")
        st.caption("Synthetic demo data · no login · no hosted AI")
    welcome.render()
    st.stop()

role = st.session_state.role
primary = welcome.ROLES[role]["order"]
if st.session_state.get("nav") not in primary + CLASSIC:
    st.session_state.nav = primary[0]
    st.session_state.nav_primary = primary[0]


def go_primary():
    st.session_state.nav = st.session_state.nav_primary
    st.session_state.nav_classic = None


def go_classic():
    st.session_state.nav = st.session_state.nav_classic
    st.session_state.nav_primary = None


def switch_role():
    st.session_state.role = None


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    sidebar_brand()
    st.markdown(f'<div class="sb-role">{welcome.ROLES[role]["icon"]} <b>{role}</b> · navigation only</div>', unsafe_allow_html=True)
    st.button("↩ Switch view", key="switch_role", on_click=switch_role, width="stretch")
    st.toggle("🌙 Dark mode", key="dark")
    st.radio("Navigate", primary, index=None, key="nav_primary", label_visibility="collapsed", on_change=go_primary)
    with st.expander("Classic views (V1)", expanded=st.session_state.nav in CLASSIC):
        st.radio("Classic views", CLASSIC, index=None, key="nav_classic", label_visibility="collapsed", on_change=go_classic)
    page = st.session_state.nav

    name = welcome.clean_name(st.text_input("Hoomi calls you…", key="user_name", placeholder="Your first name"))
    owners = regions = segments = services = stages = None
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    needs_v1 = page in CLASSIC or page == HOOMI
    raw = workspace.load_raw() if needs_v1 else None
    if page in CLASSIC and page != CLASSIC[-1]:
        st.markdown('<div class="sb-label">Filters (classic views)</div>', unsafe_allow_html=True)
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
            return chosen or list(options)                  # nothing chosen = everything

        owners = pick("Sales owner", sorted(raw["opps"]["sales_owner"].unique()), "f_owner")
        regions = pick("Region", ["US", "Europe", "LATAM", "APAC"], "f_region")
        with st.expander("More filters"):
            segments = pick("Customer segment", sorted(raw["opps"]["customer_segment"].unique()), "f_segment")
            services = pick("Service", sorted(raw["opps"]["service_offering"].unique()), "f_service")
            stages = pick("Stage", m.STAGES, "f_stage")
    elif needs_v1:                                          # Ask Hoomi: the classic briefing tab uses the unfiltered V1 data
        owners, regions = sorted(raw["opps"]["sales_owner"].unique()), ["US", "Europe", "LATAM", "APAC"]
    st.caption("Synthetic demo data · classic views as of " + f"{m.AS_OF:%b %d, %Y}")

# ------------------------------------------------------------------ route
gtm_store = get_store(str(default_path()))
ws = workspace.build(raw, owners, regions, start, end, segments, services, stages) if needs_v1 and owners is not None else None

if page == PULSE:
    pulse.render(gtm_store, name)
elif page == WORKSPACE:
    workspace_gtm.render(gtm_store)
elif page == HOOMI:
    hoomi_page.render(ws, name, gtm_store)
elif page == CLASSIC[0]:
    executive.render(ws, name)
elif page == CLASSIC[1]:
    research.render(ws)
elif page == CLASSIC[2]:
    accounts.render(ws)
elif page == CLASSIC[3]:
    sdr.render(ws)
elif page == CLASSIC[4]:
    content.render(ws)
elif page == CLASSIC[5]:
    leads_opps.render(ws)
elif page == CLASSIC[6]:
    revenue.render(ws)
else:
    about.render()

if page in CLASSIC and ws is not None:                      # the classic floating Hoomi quick panel stays on the classic views only
    hoomi_widget.render(ws, name)
