"""About / Technical notes."""
import streamlit as st

import db
import hoomi
import theme
from views import mascot
from theme import page_header, section


def v2_notes():
    section("Kai's GTM V2.0 and Hoomi", "what is new, and what is honestly limited")
    with st.container(border=True):
        st.markdown("""
**What V2 adds.** A Welcome screen with two navigation views (Leadership Hub, GTM Team: *not* a login), the **Executive Pulse**, the **GTM Workspace**
(linked accounts, prospects, outreach activities and opportunities) and a grounded **Ask Hoomi** chat. The V1 views are kept under *Classic views*.

**How Ask Hoomi answers (all local, zero hosted calls).**
- *Numbers* (pipeline, revenue, win rate, follow-ups, top SDR…) are **calculated** from the workspace, never retrieved or generated.
- *Documents* (the seven approved Kai's Company documents: capabilities, three ICPs, three case studies; plus KYC profiles) go through local retrieval (FastEmbed vectors in a Chroma index) and an
  **answerability gate**. The offline engine then **quotes the closest sentences** with citations. It is extractive: it cannot reason or paraphrase.
- If the evidence is not close enough, Hoomi says **insufficient evidence** instead of guessing.
- Fireworks AI (generate-then-verify) is an opt-in answer style in Ask Hoomi. It needs your own `.env` and a per-session approval; until then
  nothing leaves this computer.

**Data.** Two separate local SQLite stores: the V2 workspace (`data/gtm_v2.db`) and the V1 store (`data/kai_gtm.db`). They start from the same
records and are edited independently. There is no CRM integration; the CSV import is a local file feature.

**Known limits.** On the 20-question pack evaluation (`eval/pack_report.md`) the offline engine answered 16 and refused all 7 unanswerable ones; its misses are
incomplete or off-target quotes on compound and cross-document questions, never invented text. The Fireworks path has only been tested with mocks, and there is no authentication.
""")
    st.divider()


def render():
    page_header("About & Technical Notes", "How this product is built, how the numbers are defined, and where it could go next.")
    v2_notes()
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        mascot.render(150, caption=False)
    with c2:
        st.markdown("""**Kai's Company Sales & GTM Command Center** is an internal GTM management product built for a Maven Week 1
        "Data Analysis with Vibe Coding" project and extended in Week 2 with Hoomi. No paid APIs or external services are connected.""")

    section("Classic Hoomi (Version 1)")
    with st.container(border=True):
        st.markdown("""
- Hoomi is a **rule-based assistant**. It is *not* an LLM and *not* an autonomous agent.
- Every number Hoomi says is computed **locally in Python** from the same filtered data you see on screen (`metrics.py`, `analytics.py`).
- Questions are matched by **keywords** to a fixed set of answer templates (`hoomi.py → answer_with_mood`). Unknown questions get a polite "I only know these topics" reply.
- Priorities are scored by a transparent formula: *weighted deal value × urgency* (overdue follow-up +50%, stalled +50%, closing within 30 days +50%).
- The old floating panel (`hoomi_widget.py`) is retired in V2: the floating mascot now opens the Ask Hoomi chat.
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
            "generate_gtm_data.py / generate_data.py   data generators", language="text")

    section("Roadmap: from Hoomi v1 to a real AI agent")
    st.markdown("""
1. **Claude-powered answers** - send Hoomi's computed numbers to Claude to write natural-language explanations (the numbers stay deterministic).
2. **Tools for the agent** - expose functions such as *get pipeline*, *list stalled deals*, *draft follow-up email* so the model decides what to calculate.
3. **n8n / LangChain workflows** - scheduled Monday briefings, Slack alerts for stalled deals, automatic follow-up reminders.
4. **Real data connectors** - CRM and prospecting tools once approved and secured.
5. **Guardrails & evaluation** - test answers against known numbers; human approval before any outbound action.
""")

    section("Data")
    with st.container(border=True):
        st.markdown("Edits you make in **Leads & Opportunities** are saved to `data/kai_gtm.db`. Reset restores the original CSV data.")
        if st.button("↩️ Reset data", key="reset_demo"):
            db.seed()
            st.toast("Data restored.", icon="✅")
            st.rerun()
