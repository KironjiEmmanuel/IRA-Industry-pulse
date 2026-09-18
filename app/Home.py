import streamlit as st
import plotly.graph_objects as go
from db import load_dim_period, load_dim_company, compute_industry_pulse, compute_headline_metrics
from ui import styled_pct_table, trend_phrase, format_kes, verdict_metric
from config_static import CHART_COLORS, CURRENCY_TICKFORMAT

st.set_page_config(page_title="Kenya IRA Insurance Analytics", page_icon=":material/insights:", layout="wide")

if "selected_company_id" not in st.session_state:
    st.session_state.selected_company_id = None
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "Market Overview"

st.title("Kenya insurance market analytics")
st.caption("Built on IRA quarterly regulatory workbooks — connected live to Supabase")

with st.sidebar:
    st.caption("Kenya IRA Insurance Analytics · live from Supabase")

st.subheader("GB market, at a glance")
st.caption("GB is shown here as the largest, most complete segment. Full detail for GB, LT and Micro lives in each section.")
try:
    with st.spinner("Loading headline metrics..."):
        headline = compute_headline_metrics()
    v1, v2, v3, v4 = st.columns(4)
    cols = [v1, v2, v3, v4]
    for col, key in zip(cols, ["profitability", "underwriting", "market_concentration", "solvency"]):
        h = headline[key]
        with col:
            verdict_metric(h["label"], h["value"], h["delta"], h["higher_better"], h["fmt"])
except Exception as e:
    st.error(f"Could not compute headline metrics: {e}")

with st.expander("Data quality — cleaning applied to this dataset"):
    st.markdown(
        """
- 7 placeholder/junk rows excluded from `dim_company` (IRA subtotal rows, plus a units-header row loaded as a company)
- 3 confirmed company renames merged into one continuous history (APA Insurance, Cannon General Insurance, Intra-Africa Assurance)
- 1 duplicate-load case excluded rather than merged, since it overlaps in time instead of succeeding cleanly (East Africa/n Reinsurance, 2024Q1-Q3) — flagged as unresolved
- Company-specific notes (where they exist) show automatically in that company's Scorecard view
"""
    )

col1, col2, col3 = st.columns(3)
try:
    periods = load_dim_period()
    companies = load_dim_company()
    col1.metric("Quarters loaded", len(periods))
    col2.metric("Companies tracked", len(companies))
    col3.metric("Latest quarter", periods["quarter_label"].iloc[-1] if len(periods) else "—")
except Exception as e:
    st.error(f"Could not reach Supabase: {e}")

st.markdown(
    """
Use the sidebar to move between the four sections — **Profitability**, **Underwriting**,
**Market Concentration**, and **Solvency**. Each section has two views:

- **Market Overview** — how the segment as a whole is trending, and where each company sits against
  the current thresholds
- **Company Scorecard** — a single company's numbers and trend; your pick carries across all four sections
"""
)

st.divider()
st.header("Industry pulse")
st.caption(
    "The whole market — GB, LT and Micro combined — on a discrete-quarter basis. Uses insurance revenue "
    "(IFRS17) as the total rather than gross direct premium, since LT has no gross direct premium figure "
    "at all (no underwriting account, by design) — a premium-based total would silently drop LT out."
)

try:
    pulse = compute_industry_pulse()
    total = pulse["total"]
    share = pulse["segment_share"]

    with st.spinner("Building industry pulse..."):
        fig = go.Figure()
    fig.add_trace(go.Scatter(x=total["quarter_label"], y=total["disc_insurance_revenue"],
                              mode="lines+markers", name="Industry revenue", line=dict(color=CHART_COLORS["primary"], width=3)))
    fig.update_layout(title="Total industry revenue by quarter", height=380,
                       yaxis_title="Insurance revenue (KES)", yaxis_tickformat=CURRENCY_TICKFORMAT,
                       xaxis_title="Quarter", plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")

    with st.expander("View data table"):
        display_total = total.copy()
        display_total["disc_insurance_revenue"] = display_total["disc_insurance_revenue"].apply(format_kes)
        st.dataframe(styled_pct_table(display_total, ["qoq_growth", "yoy_growth"]), width="stretch")

    col_a, col_b = st.columns(2)
    with col_a:
        fig_g = go.Figure()
        fig_g.add_trace(go.Bar(x=total["quarter_label"], y=total["qoq_growth"], name="QoQ growth", marker_color=CHART_COLORS["primary"]))
        fig_g.update_layout(title="Quarter-over-quarter growth", height=320, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig_g, width="stretch")
    with col_b:
        fig_y = go.Figure()
        fig_y.add_trace(go.Bar(x=total["quarter_label"], y=total["yoy_growth"], name="YoY growth", marker_color=CHART_COLORS["muted"]))
        fig_y.update_layout(title="Year-over-year growth", height=320, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig_y, width="stretch")
    with st.expander("View data table"):
        growth_table = total[["quarter_label", "qoq_growth", "yoy_growth"]]
        st.dataframe(styled_pct_table(growth_table, ["qoq_growth", "yoy_growth"]), width="stretch")

    seg_cols = [c for c in ["GB", "LT", "Micro"] if c in share.columns]
    fig_share = go.Figure()
    for seg, color in zip(seg_cols, CHART_COLORS["sequence"]):
        fig_share.add_trace(go.Scatter(x=share["quarter_label"], y=share[seg], mode="lines",
                                        stackgroup="one", name=seg, line=dict(color=color)))
    fig_share.update_layout(title="Segment share of industry revenue over time", height=380,
                             yaxis_title="Insurance revenue (KES)", yaxis_tickformat=CURRENCY_TICKFORMAT,
                             xaxis_title="Quarter", plot_bgcolor="white")
    st.plotly_chart(fig_share, width="stretch")
    with st.expander("View data table"):
        display_share = share.copy()
        for c in seg_cols:
            display_share[c] = display_share[c].apply(format_kes)
        st.dataframe(styled_pct_table(display_share, []), width="stretch")

    with st.expander("Analyst notes"):
        rev_trend = total.set_index("quarter_label")["disc_insurance_revenue"]
        latest_yoy = total["yoy_growth"].dropna().iloc[-1] if total["yoy_growth"].notna().any() else None
        shares_latest = share.iloc[-1] if not share.empty else None
        bits = [f"- Industry revenue has {trend_phrase(rev_trend, higher_is_better=True, unit='currency')}."]
        if latest_yoy is not None:
            bits.append(f"- Most recent year-over-year growth: {latest_yoy:.1%}.")
        if shares_latest is not None and seg_cols:
            total_latest = sum(shares_latest[c] for c in seg_cols)
            shares_pct = ", ".join(f"{c} {shares_latest[c]/total_latest:.0%}" for c in seg_cols) if total_latest else ""
            if shares_pct:
                bits.append(f"- Segment mix, latest quarter: {shares_pct}.")
        st.markdown("\n".join(bits))

except Exception as e:
    st.error(f"Could not compute Industry Pulse: {e}")
