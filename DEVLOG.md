# Vibe-Coding Development Log

Use this for the "process" section of your Maven document. Add your own reflections!

| # | Iteration | What happened | Lesson |
|---|---|---|---|
| 1 | Planning | Gave Claude Code one detailed brief: business context, segments, services, reps, KPIs, Hoomi, tech limits. | A specific brief (with "no paid APIs") avoided scope creep. |
| 2 | Data first | `generate_data.py` made 50 fictional deals with a fixed random seed. Rules: GP = revenue − cost; Won = 100%, Lost = 0%; services matched to sensible segments. First run failed: only 45 company names, not 50 (caught by an assert). Added 5. | Asserts catch mistakes early. |
| 3 | One source of truth | Moved all maths into `metrics.py` so dashboard + Hoomi can't disagree. | Define metrics once. |
| 4 | Hoomi | Designed mascot in SVG/CSS; rule-based answers in `hoomi.py` with a single `answer_question()` upgrade point. | Design for the future without building it yet. |
| 5 | Dashboard | `app.py`: filters → one filtered DataFrame → KPIs, charts, tabs, tracker. Empty-filter state shows a friendly warning. | Filter once, reuse everywhere. |
| 6 | Testing | 12 pytest checks (GP formula, weighted pipeline, group totals add up, empty data, Hoomi's answers) + Streamlit AppTest smoke test with filters and empty selection. All pass. | Test the numbers, not just the looks. |
| 7 | Visual check | Screenshotted the live app. Found: bold `**` shown literally inside HTML cards, inconsistent KPI tag wrapping, `$1067000` without commas. Fixed all three. | Always look at the real output. |
| 8 | Cleanup | Replaced deprecated `use_container_width` warnings. | Read the warnings. |

## Prompts worth screenshotting
1. The original full brief (the pasted prompt).
2. "Why are bold markers showing as `**`?" → explanation of markdown inside HTML.
3. Your own follow-up tweaks (e.g. "make Hoomi bigger", "add a Q&A about X").

---

# Version 2: Sales & GTM Command Center

| # | Iteration | What happened | Lesson |
|---|---|---|---|
| 9 | Inspect + back up | Read all v1 files, copied them to `backup_v1/`, kept `metrics.py` and the 50 deals untouched. | Never upgrade without a restore point. |
| 10 | Data design | `generate_gtm_data.py` builds accounts, contacts, 300 leads, SDR activity, research and collateral **around** the existing deals, linked by IDs (OPP → LEAD → CONTACT → ACCOUNT). | Design the links first, then the screens. |
| 11 | Derived, not random | SDR "qualified leads / meetings" are *calculated from* the leads table, so two screens can never disagree. | One source of truth. |
| 12 | Test caught a data bug | `test_sdr_outcomes_come_from_leads` failed: 2 leads fell on a simulated "day off" so the SDR log lost them. Fixed the generator. | Tests find problems eyes miss. |
| 13 | Target realism | Flat targets made the full-year forecast look absurdly ahead of plan. Added a Q4 ramp and a *risk-adjusted* view that removes stalled deals. | Check whether results *feel* believable. |
| 14 | Theme system | CSS variables switch light ↔ dark; Streamlit's own theme is switched at runtime so tables and widgets follow. | Theme with variables, not copy-paste. |
| 15 | Visual bugs found by screenshots | (a) `$` pairs rendered as maths, garbling text; (b) KPI tags squeezed labels; (c) Hoomi's antenna star flew off and an arm detached because CSS animation overrode SVG `transform` attributes. Fixed with `&#36;`, a new card layout, and wrapper groups. | Always look at the real output, in both themes. |
| 16 | Floating Hoomi | A small injected script builds a draggable, click-to-expand panel with a first-visit welcome. Answers are pre-computed in Python so numbers match the dashboard. | Keep logic in Python, use JS only for behaviour. |
| 17 | Testing | 30 pytest checks (links, date logic, funnels, no double counting, filters, empty states, Hoomi answers, edit→save→reset) + app smoke tests across 6 filter scenarios × 9 pages + browser tests of Hoomi (open, ask, drag, theme switch). | Test numbers, states *and* interactions. |

## Prompts worth screenshotting (v2)
1. The full "Upgrade to Command Center" brief (eight modules, design direction, star animations).
2. "Back up first and preserve what works" (shows safe working habits).
3. Your own follow-ups, e.g. "make the stars subtler", "add a Fintech view".
