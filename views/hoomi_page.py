"""Module 8 - Hoomi, the personal sales intelligence companion (full-page view)."""
import streamlit as st

import hoomi
import theme
from theme import page_header, section


def render(ws, name=""):
    st.session_state.setdefault("hoomi_hist", [])
    mood = st.session_state.get("hoomi_mood", "greet")
    b = hoomi.briefing(ws, name)

    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        st.markdown(hoomi.hoomi_svg(230, mood), unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="hero" style="margin:0">{theme.sparkles()}<div class="eyebrow">Meet Hoomi</div><h1>Your sales intelligence buddy</h1>'
                    f'<p>{b["greeting"]}</p></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(theme.safe('<div class="bubble">' + hoomi.md_to_html("\n".join(f"- {x}" for x in b["bullets"])) + "</div>"), unsafe_allow_html=True)

    section("Top 5 priorities", "ranked by value and urgency")
    for i, p in enumerate(hoomi.top_priorities(ws), 1):
        st.markdown(theme.safe(f'<div class="ok"><b>{i}. {p["icon"]} {p["title"]}</b><br><span style="opacity:.85">{p["detail"]}</span></div>'), unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        section("Ask Hoomi", "type a question or tap a suggestion")
        with st.form("ask_hoomi", clear_on_submit=True):
            typed = st.text_input("Your question", placeholder="e.g. Which opportunities are at risk?", label_visibility="collapsed")
            go = st.form_submit_button("Ask Hoomi", type="primary")
        cols = st.columns(3)
        clicked = None
        for i, q in enumerate(hoomi.SUGGESTED_QUESTIONS):
            if cols[i % 3].button(q, key=f"hq_{i}", width="stretch"):
                clicked = q
        question = clicked or (typed if go else None)
        if question:
            text, mood_new = hoomi.answer_with_mood(question, ws)
            st.session_state.hoomi_hist.insert(0, (question, text))
            st.session_state.hoomi_mood = mood_new if mood_new in ("success", "alert") else "greet"
            st.rerun()
        if not st.session_state.hoomi_hist:
            theme.empty_state("Ask me anything about the pipeline", "I answer from the numbers on screen, so my answers follow your filters.", "💬")
        for qn, ans in st.session_state.hoomi_hist[:5]:
            st.markdown(f"**You:** {qn}")
            st.markdown(theme.safe(f'<div class="bubble">{hoomi.md_to_html(ans)}</div>'), unsafe_allow_html=True)
            st.write("")
    with right:
        section("Alerts")
        with st.container(border=True):
            st.markdown("**⏸️ Stalled deals**")
            al = hoomi.stalled_alerts(ws.opps)
            for x in al[:4]:
                st.markdown(theme.safe(f'<div class="warn">{hoomi.md_to_html(x)}</div>'), unsafe_allow_html=True)
            if not al:
                st.caption("None 🎉")
            st.markdown("**⏰ Overdue follow-ups**")
            ov = hoomi.overdue_alerts(ws.opps)
            for x in ov[:4]:
                st.markdown(theme.safe(f'<div class="warn">{hoomi.md_to_html(x)}</div>'), unsafe_allow_html=True)
            if not ov:
                st.caption("None 🎉")
        with st.container(border=True):
            st.markdown("**📄 Collateral deadlines**")
            for x in hoomi.collateral_flags(ws):
                st.markdown(theme.safe(f"- {x}"))
            st.markdown("**📞 SDR snapshot**")
            for x in hoomi.sdr_summary(ws):
                st.markdown(theme.safe(f"- {x}"))
        with st.container(border=True):
            st.markdown("**💰 Revenue, GP & reps**")
            for x in hoomi.financial_insights(ws) + hoomi.rep_insights(ws):
                st.markdown(theme.safe(f"- {x}"))

    section("Hoomi's moods", "click to preview")
    mc = st.columns(4)
    for col, (s, label) in zip(mc, [("greet", "Greeting"), ("think", "Thinking"), ("success", "Success"), ("alert", "Alert")]):
        with col, st.container(border=True):
            st.markdown(f'<div style="text-align:center">{hoomi.hoomi_svg(110, s)}</div>', unsafe_allow_html=True)
            st.markdown(f"<div style='text-align:center'><b>{label}</b></div>", unsafe_allow_html=True)
