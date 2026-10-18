"""The Executive Pulse: commercial and lead KPIs, a plain-language summary and six charts, all derived from the demo workspace."""
import plotly.graph_objects as go
import streamlit as st

import theme
from gtm import clock, pulse, schema
from metrics import money
from theme import kpi_card, section, style

FOOTER = "Where's your GTM headed? Let's find out."
MONTH_LABELS = {f"2026-{i:02d}": m for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
STAGE_KIND = {**{s: "Open" for s in schema.OPEN_STAGES}, "Won": "Won", "Lost": "Lost"}


def _colors():
    p = theme.palette()
    return {"open": p["teal"], "won": p["green"], "lost": "#C9CEDD" if not theme.is_dark() else "#4A5688", "target": p["lavender"], "pink": p["pink"]}


def _money_axis(fig, axis="y"):
    getattr(fig, f"update_{axis}axes")(tickprefix="$", tickformat="~s")
    return fig


def stage_chart(snap):
    c, st_ = _colors(), snap["stage"]
    fig = go.Figure(go.Bar(y=st_.stage, x=st_.value, orientation="h", marker_color=[c[STAGE_KIND[s].lower()] for s in st_.stage],
                           text=[f"{int(d)} deals" for d in st_.deals], textposition="auto", customdata=st_[["deals", "weighted"]],
                           hovertemplate="<b>%{y}</b><br>Deal value %{x:$,.0f}<br>%{customdata[0]:.0f} deals<br>Weighted %{customdata[1]:$,.0f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    return _money_axis(style(fig.update_layout(title="Deals by stage (deal value)", showlegend=False), 340), "x")


def monthly_chart(snap):
    c, m = _colors(), snap["monthly"]
    x = [MONTH_LABELS.get(mo, mo) for mo in m.month]
    fig = go.Figure()
    fig.add_bar(x=x, y=m.target, name="Target", marker_color=c["target"], hovertemplate="Target %{y:$,.0f}<extra></extra>")
    fig.add_bar(x=x, y=m.actual, name="Actual (won revenue)", marker_color=c["open"], hovertemplate="Actual %{y:$,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=m.forecast, name="Forecast (weighted pipeline)", mode="lines+markers", line=dict(color=c["pink"], width=3, dash="dot"),
                    hovertemplate="Forecast %{y:$,.0f}<extra></extra>")
    fig.update_layout(title="Monthly target vs actual", barmode="group")
    return _money_axis(style(fig, 340))


def split_chart(df, column, title, horizontal=False, height=330):
    c = _colors()
    labels = df[column].tolist()
    fig = go.Figure()
    for name, key in (("Open pipeline", "open_value"), ("Won revenue", "won_value")):
        kw = dict(y=labels, x=df[key], orientation="h") if horizontal else dict(x=labels, y=df[key])
        fig.add_bar(name=name, marker_color=c["open" if key == "open_value" else "won"], hovertemplate=f"{name} %{{{'x' if horizontal else 'y'}:$,.0f}}<extra></extra>", **kw)
    fig.update_layout(title=title, barmode="stack")
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    return _money_axis(style(fig, height), "x" if horizontal else "y")


def modality_chart(snap):
    df = snap["modality"]
    fig = go.Figure(go.Pie(labels=df.modality, values=df.total_value, hole=.55, sort=False,
                           marker=dict(colors=[theme.CHART_COLORS[0], theme.CHART_COLORS[1], theme.CHART_COLORS[2]]),
                           textinfo="label+percent", customdata=df.deals,
                           hovertemplate="<b>%{label}</b><br>Total value %{value:$,.0f}<br>%{customdata} deals<extra></extra>"))
    return style(fig.update_layout(title="Delivery modality (total deal value)", showlegend=False), 330)


def _panel(title, lines):
    items = "".join(f"<li>{theme.safe(x)}</li>" for x in lines)
    st.markdown(f'<div class="panel"><h4>{title}</h4><ul>{items}</ul></div>', unsafe_allow_html=True)


def render(store, name=""):
    snap = pulse.snapshot(store)
    c, k = snap["commercial"], snap["leads"]
    theme.page_header("The Executive Pulse", f"{'Hi ' + name + '. ' if name.strip() else ''}Here is where the GTM stands right now.",
                      eyebrow="Kai's GTM V2.0 · Leadership")
    st.markdown(f'<span style="color:var(--muted);font-size:.82rem">As of {clock.today():%b %d, %Y}</span>', unsafe_allow_html=True)

    section("Commercial", "what the pipeline is worth")
    cards = [("Accounts Closed", f"{c['accounts_closed']}", "accounts with a won deal", "ACTUAL", "🏁", "Distinct accounts with at least one Won opportunity"),
             ("Open Pipeline", money(c["open_pipeline"]), f"{c['open_deals']} open deals", "FORECAST", "🌊", "Sum of deal value for open-stage opportunities"),
             ("Weighted Pipeline", money(c["weighted_pipeline"]), "value × close probability", "FORECAST", "⚖️", "Deal value multiplied by close probability, open deals only"),
             ("Won Revenue", money(c["won_revenue"]), f"{c['won_deals']} won deals", "ACTUAL", "🏆", "Expected revenue of Won opportunities"),
             ("Won Gross Profit", money(c["won_gp"]), "revenue − delivery cost", "ACTUAL", "💎", "Expected gross profit of Won opportunities"),
             ("GP Margin", f"{c['gp_margin']:.1%}", "won GP ÷ won revenue", "ACTUAL", "📈", "Won gross profit divided by won revenue")]
    for col, card in zip(st.columns(6), cards):
        with col:
            kpi_card(*card[:5], tip=card[5])

    section("Leads", "how the top of the funnel is moving")
    cards = [("Total Leads", f"{k['total_leads']}", "prospects in the workspace", "", "🧲", "Every prospect being worked is a lead"),
             ("Warm Leads", f"{k['warm_leads']}", "lead temperature = Warm", "", "🌤️", "Prospects whose lead temperature is Warm"),
             ("Hot Leads", f"{k['hot_leads']}", "lead temperature = Hot", "", "🔥", "Prospects whose lead temperature is Hot"),
             ("Qualified Leads", f"{k['qualified_leads']}", "qualification = Qualified", "", "✅", "Prospects whose qualification status is Qualified"),
             ("Win Rate", f"{c['win_rate']:.0%}", f"{c['won_deals']} won / {c['lost_deals']} lost", "ACTUAL", "🎯", "Won ÷ (Won + Lost); open deals are not counted"),
             ("Pending Follow-ups", f"{k['pending_followups']}", f"{k['overdue_followups']} overdue", "", "⏰", "Pending follow-ups on active sequences; stopped sequences hold none")]
    for col, card in zip(st.columns(6), cards):
        with col:
            kpi_card(*card[:5], tip=card[5])

    section("Executive summary")
    s = snap["summary"]
    cols = st.columns(4)
    for col, (title, key) in zip(cols, [("💼 Revenue by service", "revenue_by_service"), ("🧩 Requested capabilities", "requested_capabilities"),
                                        ("🧑‍💻 SDR performance", "sdr_performance"), ("🩺 Pipeline health", "pipeline_health")]):
        with col:
            _panel(title, s[key])

    section("Charts")
    r1 = st.columns(2)
    r1[0].plotly_chart(stage_chart(snap), width="stretch", key="pulse_stage")
    r1[1].plotly_chart(monthly_chart(snap), width="stretch", key="pulse_monthly")
    if snap["forecast_outside"] > 0:
        st.caption(f"{money(snap['forecast_outside'])} of weighted pipeline is expected to close after December 2026, so it is not on the monthly chart "
                   f"but is in the Weighted Pipeline KPI.")
    r2 = st.columns(2)
    r2[0].plotly_chart(split_chart(snap["region"], "hq_region", "Client HQ region"), width="stretch", key="pulse_region")
    r2[1].plotly_chart(split_chart(snap["segment"], "customer_segment", "Customer segment", horizontal=True), width="stretch", key="pulse_segment")
    r3 = st.columns(2)
    r3[0].plotly_chart(split_chart(snap["capability"], "service_capability", "Service capability", horizontal=True, height=380), width="stretch", key="pulse_capability")
    r3[1].plotly_chart(modality_chart(snap), width="stretch", key="pulse_modality")

    st.markdown(f'<div class="footer-cta"><b>{FOOTER}</b></div>', unsafe_allow_html=True)
