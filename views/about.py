"""About / Technical notes."""
import streamlit as st

import db
import hoomi
import theme
from theme import page_header, section


def render():
    page_header("About & Technical Notes", "How this product is built, how the numbers are defined, and where it could go next.")
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        st.markdown(hoomi.hoomi_svg(150, "greet"), unsafe_allow_html=True)
    with c2:
        st.markdown("""**Kai's Company Sales & GTM Command Center** is a *fictional* internal GTM management product built for a Maven Week 1
        "Data Analysis with Vibe Coding" project. All companies, people, emails and figures are invented. No real or confidential data is used,
        and no paid APIs or external services are connected.""")

    section("How Hoomi works (Version 1)")
    with st.container(border=True):
        st.markdown("""
- Hoomi is a **rule-based assistant**. It is *not* an LLM and *not* an autonomous agent.
- Every number Hoomi says is computed **locally in Python** from the same filtered data you see on screen (`metrics.py`, `analytics.py`).
- Questions are matched by **keywords** to a fixed set of answer templates (`hoomi.py → answer_with_mood`). Unknown questions get a polite "I only know these topics" reply.
- Priorities are scored by a transparent formula: *weighted deal value × urgency* (overdue follow-up +50%, stalled +50%, closing within 30 days +50%).
- The floating panel (`hoomi_widget.py`) shows pre-computed answers, so it works offline.
- **Upgrade path:** replace `answer_with_mood()` with a call to Claude, LangChain or an n8n webhook, passing the numbers from the helper functions as context. The mascot, panel and pages stay unchanged.
""")

    section("Financial definitions")
    st.markdown("""
| Metric | Definition |
|---|---|
| Open pipeline | Deal value of opportunities not yet Won or Lost (**forecast**) |
| Weighted pipeline | Deal value × closing probability, open deals only (**forecast**) |
| Realized revenue / GP | Won deals only (**actual**). Open pipeline is never counted as realized |
| Gross profit | Revenue − delivery cost; **GP margin** = GP ÷ revenue |
| Win rate | Won ÷ (Won + Lost) |
| Lead → Opportunity | Opportunities ÷ leads created in the period |
| Opportunity → Win | Won ÷ all opportunities |
| Response rate | Positive responses ÷ (calls + emails + LinkedIn touches) |
| Stalled deal | Open deal with no activity for more than 30 days |
| Overdue follow-up | Open deal whose next follow-up date is before "today" (8 Oct 2026) |
| Risk-adjusted gap | FY target − realized − (weighted forecast − stalled weighted value) |
| Period filter | Open deals are a live snapshot; Won/Lost deals, leads and activity are filtered by date |
""")

    section("Data model", "linked by stable IDs")
    st.code("Opportunity (OPP-) → Lead (LEAD-) → Contact (CON-) → Account (ACC-)\n"
            "Collateral (COL-) → Account / Opportunity     Account research (ACR-) → Account\n"
            "SDR activity: qualified leads & meetings come from Leads     Targets: monthly revenue + GP per rep", language="text")

    section("Project structure")
    st.code("app.py              navigation, global filters, theme toggle\n"
            "theme.py            colours, light/dark, sparkles, KPI cards, chart style\n"
            "workspace.py        loads data + applies global filters\n"
            "metrics.py          pipeline maths (v1, preserved)\n"
            "analytics.py        leads, SDR, collateral, revenue/GP, forecast gap\n"
            "hoomi.py            mascot SVG + rule-based brain\n"
            "hoomi_widget.py     floating draggable assistant\n"
            "db.py               SQLite persistence (CSV = seed data)\n"
            "views/              one file per module\n"
            "generate_gtm_data.py / generate_data.py   fictional data generators", language="text")

    section("Roadmap: from Hoomi v1 to a real AI agent")
    st.markdown("""
1. **Claude-powered answers** - send Hoomi's computed numbers to Claude to write natural-language explanations (the numbers stay deterministic).
2. **Tools for the agent** - expose functions such as *get pipeline*, *list stalled deals*, *draft follow-up email* so the model decides what to calculate.
3. **n8n / LangChain workflows** - scheduled Monday briefings, Slack alerts for stalled deals, automatic follow-up reminders.
4. **Real data connectors** - CRM and prospecting tools once approved and secured.
5. **Guardrails & evaluation** - test answers against known numbers; human approval before any outbound action.
""")

    section("Demo data")
    with st.container(border=True):
        st.markdown("Edits you make in **Leads & Opportunities** are saved to `data/kai_gtm.db`. Reset restores the original fictional CSV data.")
        if st.button("↩️ Reset demo data", key="reset_demo"):
            db.seed()
            st.toast("Demo data restored.", icon="✅")
            st.rerun()
