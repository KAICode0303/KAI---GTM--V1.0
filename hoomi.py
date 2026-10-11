"""Hoomi - the Sales Intelligence Companion for Kai's Company.

How it works (Version 1): Hoomi runs LOCAL Python calculations on the fictional data and answers with
transparent, rule-based logic (keyword matching + templates). It is not an LLM or an autonomous agent.
See the About page for details.

Modular design for the future: the whole "brain" is `answer_with_mood(question, ws)`.
To connect Claude, LangChain or n8n later, replace that one function (send it the numbers produced
by the helpers below as context) - the mascot, panel and pages do not need to change.

Two parts live here:
  1. The mascot: original SVG + CSS with four states  (greet, think, success, alert)
  2. The brain: briefings, priorities, alerts and question answering
"""
import re
from datetime import datetime

import analytics as a
import metrics as m
from metrics import money

# ======================================================================================
# 1. THE MASCOT
# ======================================================================================
HOOMI_CSS = """
.hm-wrap{display:inline-block;animation:hm-float 4.2s ease-in-out infinite}
.hm{overflow:visible;--eye:#39FF88}
.hm .st{display:none}
.hm[data-state=greet] .g,.hm[data-state=think] .t,.hm[data-state=success] .s,.hm[data-state=alert] .al{display:inline}
.hm[data-state=think]{--eye:#6BF3FF} .hm[data-state=alert]{--eye:#FFC857}
.hm .glow{filter:drop-shadow(0 0 5px var(--eye))}
.hm .eye{transform-box:fill-box;transform-origin:center;animation:hm-blink 5.5s infinite}
.hm .bulb{transform-box:fill-box;transform-origin:center;animation:hm-pulse 2.2s ease-in-out infinite;fill:var(--eye)}
.hm[data-state=alert] .bulb{animation-duration:.7s}
.hm .arm-l,.hm .arm-r{transform-box:fill-box;transition:transform .4s ease}
.hm[data-state=greet] .arm-l{animation:hm-wave 2.6s ease-in-out infinite;transform-origin:90% 10%}
.hm[data-state=success] .arm-l{transform:rotate(130deg);transform-origin:90% 10%}
.hm[data-state=success] .arm-r{transform:rotate(-130deg);transform-origin:10% 10%}
.hm .dots circle{animation:hm-dots 1.2s infinite;opacity:.2} .hm .dots circle:nth-child(2){animation-delay:.2s} .hm .dots circle:nth-child(3){animation-delay:.4s}
.hm[data-state=success] .burst{animation:hm-twinkle 1.1s ease-in-out infinite}
.hm[data-state=alert]{animation:hm-shake 3s ease-in-out infinite}
.hm .shadow{transform-box:fill-box;transform-origin:center;animation:hm-shadow 4.2s ease-in-out infinite}
@keyframes hm-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}
@keyframes hm-shadow{0%,100%{opacity:.30;transform:scaleX(1)}50%{opacity:.14;transform:scaleX(.78)}}
@keyframes hm-blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.08)}}
@keyframes hm-pulse{0%,100%{opacity:.65;transform:scale(.9)}50%{opacity:1;transform:scale(1.15)}}
@keyframes hm-wave{0%,100%{transform:rotate(0)}50%{transform:rotate(-22deg)}}
@keyframes hm-dots{0%,100%{opacity:.2}50%{opacity:1}}
@keyframes hm-twinkle{0%,100%{opacity:.2;transform:scale(.6)}50%{opacity:1;transform:scale(1.2)}}
@keyframes hm-shake{0%,86%,100%{transform:rotate(0)}90%{transform:rotate(-2.5deg)}94%{transform:rotate(2.5deg)}}
@media (prefers-reduced-motion: reduce){.hm-wrap,.hm,.hm *{animation:none !important}}
"""

STAR = "M0,-9 C1,-3 3,-1 9,0 C3,1 1,3 0,9 C-1,3 -3,1 -9,0 C-3,-1 -1,-3 0,-9Z"


def hoomi_svg(size=170, state="greet"):
    """Hoomi as inline SVG. state: greet | think | success | alert."""
    return f"""<div class="hm-wrap" style="width:{size}px"><svg class="hm" data-state="{state}" viewBox="0 0 220 245" width="{size}"
 xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Hoomi, the friendly AI companion">
<defs>
 <radialGradient id="hmB" cx="35%" cy="22%" r="90%"><stop offset="0" stop-color="#B9FFF8"/><stop offset=".45" stop-color="#4DE8E6"/><stop offset="1" stop-color="#0CA9BE"/></radialGradient>
 <linearGradient id="hmF" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0E3A4B"/><stop offset="1" stop-color="#072332"/></linearGradient>
</defs>
<ellipse class="shadow" cx="110" cy="234" rx="52" ry="6" fill="#00B5C0"/>
<!-- antenna with a glowing star -->
<path d="M110 40 L110 24" stroke="#19C9D4" stroke-width="4" stroke-linecap="round"/>
<g transform="translate(110 15) scale(1.25)"><path class="bulb glow" d="{STAR}"/></g>
<!-- ears -->
<ellipse cx="26" cy="110" rx="15" ry="19" fill="#12B5C6"/><ellipse cx="194" cy="110" rx="15" ry="19" fill="#12B5C6"/>
<circle cx="26" cy="110" r="5" fill="var(--eye)" class="glow"/><circle cx="194" cy="110" r="5" fill="var(--eye)" class="glow"/>
<!-- body, feet, arms -->
<ellipse cx="92" cy="226" rx="16" ry="8" fill="#12B5C6"/><ellipse cx="128" cy="226" rx="16" ry="8" fill="#12B5C6"/>
<g transform="rotate(28 64 186)"><ellipse class="arm-l" cx="64" cy="186" rx="12" ry="19" fill="#27D3D6"/></g>
<g transform="rotate(-28 156 186)"><ellipse class="arm-r" cx="156" cy="186" rx="12" ry="19" fill="#27D3D6"/></g>
<path d="M74 170 Q110 156 146 170 Q158 214 110 224 Q62 214 74 170Z" fill="url(#hmB)"/>
<circle cx="110" cy="192" r="10" fill="#072332"/><path class="glow" d="{STAR}" transform="translate(110 192) scale(.75)" fill="var(--eye)"/>
<!-- head -->
<ellipse cx="110" cy="100" rx="88" ry="68" fill="url(#hmB)"/>
<ellipse cx="66" cy="58" rx="28" ry="10" fill="#fff" opacity=".35" transform="rotate(-24 66 58)"/>
<rect x="40" y="60" width="140" height="82" rx="41" fill="url(#hmF)" stroke="#39FF88" stroke-opacity=".35" stroke-width="1.5"/>
<circle cx="62" cy="122" r="6" fill="#FF8FB8" opacity=".38"/><circle cx="158" cy="122" r="6" fill="#FF8FB8" opacity=".38"/>
<!-- eyes + mouth per state -->
<g class="st g"><ellipse class="eye glow" cx="84" cy="98" rx="11.5" ry="16" fill="var(--eye)"/><ellipse class="eye glow" cx="136" cy="98" rx="11.5" ry="16" fill="var(--eye)"/>
 <circle cx="88" cy="91" r="4" fill="#fff"/><circle cx="140" cy="91" r="4" fill="#fff"/>
 <path class="glow" d="M95 120 Q110 134 125 120" fill="none" stroke="var(--eye)" stroke-width="4" stroke-linecap="round"/></g>
<g class="st t"><ellipse class="eye glow" cx="84" cy="98" rx="11.5" ry="16" fill="var(--eye)"/><ellipse class="eye glow" cx="136" cy="98" rx="11.5" ry="16" fill="var(--eye)"/>
 <circle cx="80" cy="90" r="5" fill="#fff"/><circle cx="132" cy="90" r="5" fill="#fff"/>
 <ellipse class="glow" cx="110" cy="124" rx="5" ry="4" fill="var(--eye)"/>
 <g class="dots" fill="var(--eye)"><circle cx="150" cy="36" r="4"/><circle cx="164" cy="30" r="4"/><circle cx="178" cy="24" r="4"/></g></g>
<g class="st s"><path class="glow" d="M70 104 Q84 84 98 104 M122 104 Q136 84 150 104" fill="none" stroke="var(--eye)" stroke-width="5.5" stroke-linecap="round"/>
 <path class="glow" d="M93 117 Q110 144 127 117Z" fill="var(--eye)"/>
 <g class="burst" fill="#39FF88"><path d="{STAR}" transform="translate(22 52) scale(.9)"/><path d="{STAR}" transform="translate(200 56) scale(1.1)"/><path d="{STAR}" transform="translate(206 168) scale(.7)"/></g></g>
<g class="st al"><ellipse class="eye glow" cx="84" cy="100" rx="12.5" ry="17" fill="var(--eye)"/><ellipse class="eye glow" cx="136" cy="100" rx="12.5" ry="17" fill="var(--eye)"/>
 <circle cx="86" cy="93" r="4" fill="#fff"/><circle cx="138" cy="93" r="4" fill="#fff"/>
 <path d="M70 74 L96 80 M150 74 L124 80" stroke="var(--eye)" stroke-width="4" stroke-linecap="round"/>
 <path class="glow" d="M98 128 Q110 119 122 128" fill="none" stroke="var(--eye)" stroke-width="4" stroke-linecap="round"/>
 <circle cx="184" cy="34" r="13" fill="#FFC857"/><text x="184" y="40" text-anchor="middle" font-size="18" font-weight="800" fill="#5A3B00" font-family="sans-serif">!</text></g>
</svg></div>"""


# ======================================================================================
# 2. THE BRAIN  (everything below takes a Workspace `ws` from workspace.py)
# ======================================================================================
SUGGESTED_QUESTIONS = [
    "What is our total pipeline?",
    "Which opportunities are at risk?",
    "Who is the top-performing sales rep?",
    "Which region has the largest pipeline?",
    "What is our gross profit?",
    "What should I focus on today?",
    "How is SDR activity doing?",
    "Which collateral is overdue?",
    "Are we on track for our targets?",
]


def md_to_html(text):
    """Minimal markdown -> HTML (bold, bullets, line breaks) for cards and the floating panel."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    lines = text.split("\n")
    out, in_list = [], False
    for ln in lines:
        if ln.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{ln[2:]}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(ln + "<br>" if ln else "")
    if in_list:
        out.append("</ul>")
    return "".join(out)


def greeting(name=""):
    hour = datetime.now().hour
    part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    who = name.strip() or "there"
    return f"Good {part}, {who}! I'm Hoomi, your sales buddy. Here's what I noticed today."


# ---------- alerts ----------
def stalled_alerts(opps):
    s = m.stalled_deals(opps)
    return [f"**{r['client_name']}** ({r['sales_owner']}, {r['stage']}, {money(r['deal_value'])}) - "
            f"{int(r['days_since_activity'])} days quiet" for _, r in s.iterrows()]


def overdue_alerts(opps):
    o = m.overdue_followups(opps)
    return [f"**{r['client_name']}** ({r['sales_owner']}) - follow-up {int(r['days_overdue'])} days overdue, "
            f"{money(r['deal_value'])} in {r['stage']}" for _, r in o.iterrows()]


def high_value_alerts(opps):
    h = m.high_value_deals(opps)
    return [f"**{r['client_name']}** - {money(r['deal_value'])} in {r['stage']} "
            f"({int(r['close_probability'] * 100)}% likely, {r['sales_owner']})" for _, r in h.iterrows()]


def collateral_flags(ws):
    c = ws.collateral
    if c.empty:
        return ["No collateral items in this selection."]
    out = []
    over = c[c["overdue"]].sort_values("days_overdue", ascending=False)
    if len(over):
        out.append(f"**{len(over)} items overdue.** Most late: {over.iloc[0]['title']} "
                   f"({over.iloc[0]['owner']}, {int(over.iloc[0]['days_overdue'])} days).")
        urgent = over[(over["priority"] == "High")]
        if len(urgent):
            out.append(f"{len(urgent)} of them are **High priority**, e.g. {urgent.iloc[0]['title']}.")
    soon = c[c["due_soon"]]
    if len(soon):
        out.append(f"{len(soon)} items due in the next 7 days: " + ", ".join(soon["title"].head(3)) + ".")
    return out or ["All collateral is on schedule."]


def sdr_summary(ws):
    s = ws.sdr
    if s.empty:
        return ["No SDR activity in this period."]
    t = a.sdr_totals(s)
    out = [f"The team made **{t['touches']:,} outreach touches** with a **{t['response_rate']:.1%} response rate**, "
           f"yielding **{t['qualified_leads']} qualified leads** and **{t['meetings_booked']} meetings booked** "
           f"({t['show_rate']:.0%} held)."]
    lb = a.sdr_by_rep(s)
    out.append(f"**{lb.iloc[0]['owner']}** leads the SDR leaderboard with {int(lb.iloc[0]['meetings_booked'])} meetings booked.")
    att = a.activity_attainment(s, ws.act_targets, len(ws.owners), ws.start, ws.end).sort_values("attainment")
    if len(att) and att.iloc[0]["target"] > 0:
        w = att.iloc[0]
        out.append(f"Biggest gap to target: **{w['label']}** at {w['attainment']:.0%} of target.")
    return out


def financial_insights(ws):
    opps = ws.opps
    k = m.kpis(opps)
    if k["won_revenue"] == 0:
        return ["No Won revenue in the current selection yet."]
    out = [f"Won revenue is {money(k['won_revenue'])} with {money(k['won_gp'])} gross profit ({k['gp_margin']:.1%} margin)."]
    reg = m.summarize_by(opps, "region")
    if not reg.empty:
        out.append(f"{reg.iloc[0]['region']} is the top region for Won revenue ({money(reg.iloc[0]['won_revenue'])}).")
    svc = m.summarize_by(opps[opps["stage"] == "Won"], "service_offering")
    if not svc.empty:
        best = svc.sort_values("gp_margin", ascending=False).iloc[0]
        out.append(f"{best['service_offering']} has the best Won margin ({best['gp_margin']:.1%}).")
    return out


def rep_insights(ws):
    out = []
    by_rep = m.summarize_by(ws.opps, "sales_owner")
    if by_rep.empty:
        return out
    out.append(f"{by_rep.iloc[0]['sales_owner']} leads on Won revenue with {money(by_rep.iloc[0]['won_revenue'])}.")
    bp = by_rep.sort_values("weighted_pipeline", ascending=False).iloc[0]
    out.append(f"{bp['sales_owner']} has the largest weighted pipeline ({money(bp['weighted_pipeline'])}).")
    _, att = m.targets_vs_actuals(ws.opps, ws.targets, owners=ws.owners)
    if not att.empty:
        s = att.sort_values("attainment", ascending=False)
        out.append(f"{s.iloc[0]['sales_owner']} has the best target attainment ({s.iloc[0]['attainment']:.0%}); "
                   f"{s.iloc[-1]['sales_owner']} has the most room to grow ({s.iloc[-1]['attainment']:.0%}).")
    return out


# ---------- priorities ----------
def top_priorities(ws, n=5):
    """Top sales priorities: highest-value urgent deals, plus overdue collateral and the weakest SDR metric."""
    items = []
    o = ws.opps[ws.opps["is_open"]].copy()
    if not o.empty:
        soon = (o["expected_close_date"] - m.AS_OF).dt.days <= 30
        o["urgency"] = 1 + .5 * o["overdue_followup"] + .5 * (o["days_since_activity"] > m.STALL_DAYS) + .5 * soon
        o["score"] = o["weighted_value"] * o["urgency"]
        for _, r in o.sort_values("score", ascending=False).head(3).iterrows():
            if r["stage"] == "Negotiation" and (r["expected_close_date"] - m.AS_OF).days <= 30:
                t = f"Close {r['client_name']}"
                d = f"{money(r['deal_value'])} in Negotiation, expected {r['expected_close_date']:%b %d}. Next: {r['next_action']}."
            elif r["overdue_followup"]:
                t = f"Follow up with {r['client_name']}"
                d = f"Follow-up is {int(r['days_overdue'])} days overdue on a {money(r['deal_value'])} {r['stage']} deal ({r['sales_owner']})."
            elif r["days_since_activity"] > m.STALL_DAYS:
                t = f"Re-engage {r['client_name']}"
                d = f"No activity for {int(r['days_since_activity'])} days on {money(r['deal_value'])}. Next: {r['next_action']}."
            else:
                t = f"Advance {r['client_name']}"
                d = f"{money(r['deal_value'])} in {r['stage']} ({int(r['close_probability'] * 100)}% likely). Next: {r['next_action']}."
            items.append({"icon": "💰", "title": t, "detail": d})
    c = ws.collateral
    over = c[c["overdue"]].sort_values(["priority", "days_overdue"], ascending=[True, False]) if not c.empty else c
    if len(over):
        r = over.iloc[0]
        items.append({"icon": "📄", "title": f"Finish: {r['title']}",
                      "detail": f"{int(r['days_overdue'])} days overdue ({r['owner']}, {r['priority']} priority). Next: {r['next_action']}."})
    if not ws.sdr.empty:
        att = a.activity_attainment(ws.sdr, ws.act_targets, len(ws.owners), ws.start, ws.end).sort_values("attainment")
        if len(att) and att.iloc[0]["target"] > 0:
            w = att.iloc[0]
            items.append({"icon": "📞", "title": f"Lift {w['label'].lower()}",
                          "detail": f"Only {w['attainment']:.0%} of target ({w['actual']} vs {w['target']}). Protect time for prospecting."})
    more = o.sort_values("score", ascending=False).iloc[3:] if not o.empty else o
    for _, r in more.iterrows():
        if len(items) >= n:
            break
        items.append({"icon": "💰", "title": f"Advance {r['client_name']}", "detail": f"{money(r['deal_value'])} in {r['stage']}. Next: {r['next_action']}."})
    return items[:n]


def briefing(ws, name=""):
    """A friendly executive briefing: greeting + 4-5 headline bullets + mood."""
    k = m.kpis(ws.opps)
    if ws.opps.empty:
        return {"greeting": greeting(name), "bullets": ["There is no data for the current filters."], "mood": "greet"}
    st_n, ov_n = len(m.stalled_deals(ws.opps)), len(m.overdue_followups(ws.opps))
    bullets = [f"**{money(k['open_pipeline'])}** open pipeline, **{money(k['weighted_pipeline'])}** weighted. "
               f"Won revenue **{money(k['won_revenue'])}** at **{k['gp_margin']:.1%}** GP margin."]
    g = a.forecast_gap(ws.opps, ws.targets, ws.owners)
    bullets.append(f"Full-year plan: **{g['rev_attainment']:.0%}** achieved so far; risk-adjusted forecast "
                   f"{'covers' if g['risk_gap'] <= 0 else 'is short of'} the target by **{money(abs(g['risk_gap']))}**.")
    if st_n or ov_n:
        bullets.append(f"**{st_n} stalled deals** and **{ov_n} overdue follow-ups** need attention.")
    bullets += sdr_summary(ws)[:1]
    cs = a.collateral_summary(ws.collateral)
    if cs["overdue"]:
        bullets.append(f"**{cs['overdue']} collateral items** are overdue.")
    return {"greeting": greeting(name), "bullets": bullets, "mood": "alert" if (st_n + ov_n + cs["overdue"]) else "greet"}


# ---------- question answering ----------
def _has(q, *words):
    return any(re.search(r"\b" + re.escape(w), q) for w in words)


def _list(lines, n=5):
    return "\n".join(f"- {x}" for x in lines[:n])


def answer_with_mood(question, ws):
    """THE BRAIN. Returns (markdown_answer, mood). Rule-based: keywords -> real calculations.

    >>> FUTURE UPGRADE POINT: replace this function's body with a Claude / LangChain / n8n call.
    """
    q = question.lower().strip()
    if not q:
        return "Ask me something about the pipeline! Try one of the suggested questions.", "greet"
    opps = ws.opps
    if opps.empty and not _has(q, "sdr", "outreach", "collateral", "deck"):
        return "There are no opportunities in the current filters, so I have nothing to calculate. Try widening the filters.", "greet"
    k = m.kpis(opps)

    if _has(q, "region"):
        reg = m.summarize_by(opps, "region")
        if _has(q, "revenue", "won", "profit"):
            t = reg.iloc[0]
            return f"**{t['region']}** leads Won revenue with **{money(t['won_revenue'])}** and {money(t['won_gp'])} gross profit.", "success"
        reg = reg.sort_values("open_pipeline", ascending=False)
        t = reg.iloc[0]
        extra = f" Runner-up: {reg.iloc[1]['region']} ({money(reg.iloc[1]['open_pipeline'])})." if len(reg) > 1 else ""
        return (f"**{t['region']}** has the largest open pipeline at **{money(t['open_pipeline'])}** "
                f"({money(t['weighted_pipeline'])} weighted).{extra}"), "success"

    if _has(q, "priorit", "focus", "should i", "to do", "todo", "today"):
        p = top_priorities(ws)
        return "Here are your top priorities:\n" + "\n".join(f"- {x['icon']} **{x['title']}** - {x['detail']}" for x in p), "success"

    if _has(q, "overdue", "follow-up", "follow up", "followup") and not _has(q, "collateral", "deck", "proposal", "content", "document"):
        o = overdue_alerts(opps)
        if not o:
            return "No overdue follow-ups. Nice discipline!", "success"
        return f"**{len(o)} follow-ups are overdue.** Most overdue:\n" + _list(o), "alert"

    if _has(q, "risk", "stall", "stuck", "cold"):
        r = m.at_risk_deals(opps)
        if r.empty:
            return "Good news - no open deals look at risk right now.", "success"
        lines = [f"**{x['client_name']}** ({x['sales_owner']}, {x['stage']}, {money(x['deal_value'])}) - "
                 f"{int(x['days_since_activity'])} days since last activity" for _, x in r.iterrows()]
        return (f"**{len(r)} open deals** look at risk ({money(r['deal_value'].sum())} total). Top 5 by weighted value:\n" + _list(lines)), "alert"

    if _has(q, "collateral", "deck", "case study", "case studies", "content", "proposal", "one-pager", "rfp", "document"):
        return "**Collateral status**\n" + _list(collateral_flags(ws), 6), "alert" if ws.collateral["overdue"].any() else "success"

    if _has(q, "sdr", "outreach", "cold call", "calls", "email", "linkedin", "meeting", "response", "activity", "productiv", "prospecting"):
        return "**SDR activity**\n" + _list(sdr_summary(ws)), "success"

    if _has(q, "lead", "conversion", "convert", "funnel"):
        lm = a.lead_metrics(ws.leads, opps)
        return (f"**{lm['leads']} leads** -> **{lm['qualified']} qualified** -> **{lm['meetings_held']} meetings held** -> "
                f"**{lm['opportunities']} opportunities** -> **{lm['won']} won**.\n"
                f"Lead-to-opportunity: **{lm['lead_to_opp']:.0%}**. Opportunity-to-win: **{lm['opp_to_win']:.0%}**."), "success"

    if _has(q, "target", "gap", "forecast", "quota", "attain", "on track", "plan"):
        g = a.forecast_gap(opps, ws.targets, ws.owners)
        verdict = "short of" if g["risk_gap"] > 0 else "ahead of"
        return (f"Full-year revenue target is **{money(g['fy_rev_target'])}**; **{money(g['rev_won'])}** is won ({g['rev_attainment']:.0%}). "
                f"Weighted forecast adds {money(g['rev_forecast'])}, but {money(g['stalled_weighted'])} of that sits in stalled deals. "
                f"Risk-adjusted we are **{verdict} target by {money(abs(g['risk_gap']))}**."), "success" if g["risk_gap"] <= 0 else "alert"

    if _has(q, "segment", "industry", "customer type"):
        s = m.summarize_by(opps, "customer_segment")
        t = s.iloc[0]
        return f"**{t['customer_segment']}** is the top segment by Won revenue (**{money(t['won_revenue'])}**, {t['gp_margin']:.1%} margin).", "success"

    if _has(q, "service", "offering"):
        s = m.summarize_by(opps, "service_offering")
        t = s.iloc[0]
        best = s[s["won_revenue"] > 0].sort_values("gp_margin", ascending=False)
        extra = f" Best margin: {best.iloc[0]['service_offering']} ({best.iloc[0]['gp_margin']:.1%})." if len(best) else ""
        return f"**{t['service_offering']}** leads on Won revenue (**{money(t['won_revenue'])}**).{extra}", "success"

    if _has(q, "gross profit", "margin", "gp", "profit"):
        return (f"Won gross profit is **{money(k['won_gp'])}** on {money(k['won_revenue'])} revenue - a **{k['gp_margin']:.1%}** margin. "
                f"(Gross profit = revenue - delivery cost, Won deals only.)"), "success"

    if _has(q, "win rate", "win", "lost", "loss"):
        return (f"Win rate is **{k['win_rate']:.0%}** ({k['won_deals']} won vs {k['lost_deals']} lost; open deals aren't counted)."), "success"

    if _has(q, "pipeline"):
        return (f"Open pipeline is **{money(k['open_pipeline'])}** across {k['open_deals']} deals. Weighted by closing probability it's "
                f"**{money(k['weighted_pipeline'])}**. (Won revenue of {money(k['won_revenue'])} is reported separately.)"), "success"

    if _has(q, "revenue", "won", "closed", "sales"):
        if _has(q, "rep", "who", "top", "best"):
            pass                                           # falls through to the top-rep rule below
        else:
            return f"Won revenue is **{money(k['won_revenue'])}** from {k['won_deals']} deals.", "success"

    if _has(q, "rep", "who", "top", "best", "leader"):
        t = m.summarize_by(opps, "sales_owner").iloc[0]
        return (f"**{t['sales_owner']}** is the top performer with **{money(t['won_revenue'])}** Won revenue and "
                f"{money(t['won_gp'])} gross profit, plus {money(t['weighted_pipeline'])} weighted pipeline still open."), "success"

    if _has(q, "high", "big", "largest", "value"):
        h = m.high_value_deals(opps)
        if h.empty:
            return f"No open deals are at or above {money(m.HIGH_VALUE)}.", "greet"
        return f"{len(h)} open deals are worth {money(m.HIGH_VALUE)}+:\n" + _list(high_value_alerts(opps)), "success"

    return ("I only know some topics: pipeline, risk, overdue follow-ups, top rep, region, segments, services, gross profit, "
            "win rate, targets, SDR activity, leads, collateral and priorities. Try one of the suggestions!"), "greet"


def answer_question(question, ws):
    return answer_with_mood(question, ws)[0]


def faq_answers(ws):
    """Pre-computed answers for the floating panel's quick-question chips: {question: (html, mood)}."""
    out = {}
    for q in SUGGESTED_QUESTIONS:
        text, mood = answer_with_mood(q, ws)
        out[q] = [md_to_html(text), mood]
    return out
