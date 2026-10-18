"""Structured GTM questions answered from the Executive Pulse snapshot: arithmetic and lookups, NOT retrieval or a model.

Keeping this apart from RAG is deliberate: numbers must come from the data and match the dashboard exactly, whereas document
questions are answered from approved text with citations. `route()` decides which path a question takes.
"""
import metrics

money = metrics.money

SUGGESTIONS = ["What is our open pipeline?", "What is the weighted pipeline?", "How much revenue have we won?", "What is our GP margin?",
               "What is our win rate?", "How many hot leads do we have?", "How many follow-ups are pending?", "Who is the top SDR?",
               "Which deals are stalled?", "Are we on track for our monthly target?"]

# (topic, keywords that select it). Order matters: the first topic with a match wins, so specific topics come first.
TOPICS = [
    ("weighted", ("weighted",)),
    ("pipeline", ("pipeline", "open deals", "open opportunities")),
    ("gp_margin", ("gp margin", "gross margin", "margin")),
    ("gross_profit", ("gross profit", " gp")),
    ("win_rate", ("win rate", "win-rate", "winrate")),
    ("accounts_closed", ("accounts closed", "closed accounts", "customers won", "accounts won", "how many customers")),
    ("revenue", ("won revenue", "revenue", "closed-won", "closed won")),
    ("hot", ("hot lead", "hot prospect")),
    ("warm", ("warm lead", "warm prospect")),
    ("qualified", ("qualified lead", "qualified prospect", "how many qualified")),
    ("leads", ("total lead", "how many lead", "how many prospect", "number of leads")),
    ("followups", ("follow-up", "follow up", "followup", "overdue")),
    ("sdr", ("top sdr", "best sdr", "sdr performance", "top-performing", "top performing", "best performing", "which sdr", "who is the top")),
    ("stalled", ("stalled", "at risk", "pipeline health", "no activity")),
    ("demand", ("most requested", "capabilities are requested", "requested capabilit", "service demand")),
    ("target", ("target", "on track", "quota")),
]


def topic(question):
    q = " " + question.lower() + " "
    for name, words in TOPICS:
        if any(w in q for w in words):
            return name
    return None


def route(question):
    """'numbers' when the question is about a GTM metric, otherwise 'documents'."""
    return "numbers" if topic(question) else "documents"


def answer(question, snap):
    """A short sentence with the figures, or None when the question is not a recognised metric question."""
    t = topic(question)
    if not t:
        return None
    c, k, h = snap["commercial"], snap["leads"], snap["health"]
    sdr, m = snap["sdr"], snap["monthly"]
    when = f"{snap['as_of']:%b %d, %Y}"
    text = {
        "weighted": f"Weighted pipeline is **{money(c['weighted_pipeline'])}** (deal value x close probability across {c['open_deals']} open deals).",
        "pipeline": f"Open pipeline is **{money(c['open_pipeline'])}** across {c['open_deals']} open deals; weighted by close probability it is {money(c['weighted_pipeline'])}.",
        "gp_margin": f"GP margin on won deals is **{c['gp_margin']:.1%}** ({money(c['won_gp'])} gross profit on {money(c['won_revenue'])} revenue).",
        "gross_profit": f"Won gross profit is **{money(c['won_gp'])}** (GP margin {c['gp_margin']:.1%}).",
        "win_rate": f"Win rate is **{c['win_rate']:.0%}**: {c['won_deals']} won and {c['lost_deals']} lost (open deals are not counted).",
        "accounts_closed": f"**{c['accounts_closed']}** accounts have closed (at least one won opportunity).",
        "revenue": f"Won revenue is **{money(c['won_revenue'])}** from {c['won_deals']} won deals ({c['accounts_closed']} accounts).",
        "hot": f"There are **{k['hot_leads']}** hot leads out of {k['total_leads']} ({k['warm_leads']} warm).",
        "warm": f"There are **{k['warm_leads']}** warm leads out of {k['total_leads']} ({k['hot_leads']} hot).",
        "qualified": f"**{k['qualified_leads']}** of {k['total_leads']} leads are qualified.",
        "leads": f"There are **{k['total_leads']}** leads: {k['hot_leads']} hot, {k['warm_leads']} warm, {k['qualified_leads']} qualified.",
        "followups": f"**{k['pending_followups']}** follow-ups are pending, **{k['overdue_followups']}** of them overdue. "
                     f"{k['stopped_sequences']} sequences are stopped (opt-out, rejection or closure) and hold no follow-ups.",
        "sdr": (f"Top SDR by won revenue is **{sdr.iloc[0].sdr}** with {money(sdr.iloc[0].won_revenue)} won and {sdr.iloc[0].qualified} qualified leads; "
                f"next are {sdr.iloc[1].sdr} ({money(sdr.iloc[1].won_revenue)}) and {sdr.iloc[2].sdr} ({money(sdr.iloc[2].won_revenue)}).") if len(sdr) >= 3 else "No SDR data.",
        "stalled": f"**{h['stalled_deals']}** open deals ({money(h['stalled_value'])}) have had no activity for {pulse_stall()}+ days"
                   + (f": {', '.join(h['stalled_ids'][:6])}." if h["stalled_ids"] else "."),
        "demand": ("The most requested capability is **" + snap["demand"].iloc[0].capability + f"**, requested by {snap['demand'].iloc[0].accounts} accounts."),
        "target": _target_answer(m, snap),
    }[t]
    return f"{text}\n\n_Source: Executive Pulse, as of {when}._"


def pulse_stall():
    return metrics.STALL_DAYS


def _target_answer(m, snap):
    month = f"{snap['as_of']:%Y-%m}"
    row = m[m.month == month]
    if row.empty:
        return "No monthly target is defined for the current month."
    r = row.iloc[0]
    pct = (r.actual / r.target) if r.target else 0
    return (f"For {month} the target is **{money(r.target)}**, won revenue so far is **{money(r.actual)}** ({pct:.0%} of target), "
            f"and weighted pipeline expected to close this month is {money(r.forecast)}.")
