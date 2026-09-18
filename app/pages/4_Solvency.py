import streamlit as st
import plotly.graph_objects as go
from ui import section_header, styled_pct_table, trend_phrase, verdict_metric, data_quality_note
from db import load_balance_sheet_ratios, compute_negative_equity_duration
from config_static import METRIC_LABELS, CHART_COLORS

st.set_page_config(page_title="Solvency", page_icon=":material/account_balance:", layout="wide")
view_mode, company_id, segment = section_header("Balance sheet & solvency", ["GB", "LT", "Micro"])

st.caption(
    "Capital-to-assets, liquidity ratio, and equity-to-insurance-liabilities are composition-based "
    "solvency proxies, not IRA's official risk-weighted RBC solvency margin (that needs risk-weighted "
    "asset data this appendix doesn't have)."
)
if segment == "LT":
    st.caption("LT has no underwriting/combined-ratio equivalent — fund accounting, not underwriting "
               "accounting — so IFRS17 margin plus these balance-sheet ratios are LT's full scorecard.")

with st.spinner("Loading balance sheet data..."):
    bs = load_balance_sheet_ratios()
seg_df = bs[bs["segment"] == segment] if not bs.empty else bs
metrics = ["capital_to_assets", "liquidity_ratio", "equity_to_insurance_liabilities"]

if view_mode == "Market Overview":
    metric = st.selectbox("Metric", metrics, format_func=lambda m: METRIC_LABELS[m])
    label = METRIC_LABELS[metric]
    trend = seg_df.groupby("quarter_label")[metric].median().reset_index().sort_values("quarter_label") if not seg_df.empty else seg_df
    vals = trend[metric].dropna() if not trend.empty else trend
    latest_v = float(vals.iloc[-1]) if len(vals) else None
    delta_v = float(vals.iloc[-1] - vals.iloc[-2]) if len(vals) > 1 else None
    verdict_metric(f"{segment} median {label.lower()}", latest_v, delta_v, True, "pct")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=trend["quarter_label"], y=trend[metric], mode="lines+markers",
                              name=f"{segment} median", line=dict(color=CHART_COLORS["primary"], width=3)))
    fig.update_layout(title=f"{segment} median {label}", height=380, yaxis_tickformat=".0%",
                       xaxis_title="Quarter", plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    with st.expander("View data table"):
        table = seg_df[["quarter_label", "company_name"] + metrics].dropna(how="all", subset=metrics).sort_values("quarter_label")
        st.dataframe(styled_pct_table(table, metrics), width="stretch")
    with st.expander("Analyst notes"):
        st.markdown(f"- Segment median {label.lower()} has {trend_phrase(trend.set_index('quarter_label')[metric], higher_is_better=True)}.")

    st.subheader("Alerts — negative equity")
    st.caption("Duration matters as much as the fact of it: chronic vs. recent vs. one-off get different weight.")
    neg = compute_negative_equity_duration()
    neg_seg = neg[neg["segment"] == segment]
    if neg_seg.empty:
        st.success("No companies with negative equity on record in this segment.")
    else:
        def bucket(row):
            if row["quarters_negative"] >= row["quarters_reported"] - 1 and row["quarters_reported"] >= 5:
                return "Chronic"
            if row["latest_negative"] and row["quarters_negative"] <= 3:
                return "Recent deterioration"
            return "One-off / intermittent"
        neg_seg = neg_seg.copy()
        neg_seg["pattern"] = neg_seg.apply(bucket, axis=1)
        color_map = {"Chronic": CHART_COLORS["distressed"], "Recent deterioration": CHART_COLORS["watch"], "One-off / intermittent": CHART_COLORS["muted"]}
        fig_neg = go.Figure()
        fig_neg.add_trace(go.Bar(x=neg_seg["company_name"], y=neg_seg["pct_negative"],
                                  marker_color=[color_map[p] for p in neg_seg["pattern"]]))
        fig_neg.update_layout(title=f"{segment} — share of reported quarters with negative equity (color = pattern)",
                               height=380, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig_neg, width="stretch")
        st.dataframe(
            styled_pct_table(
                neg_seg[["company_name", "quarters_negative", "quarters_reported", "pct_negative", "pattern"]]
                .sort_values("pct_negative", ascending=False),
                ["pct_negative"],
            ),
            width="stretch",
        )
        chronic = neg_seg[neg_seg["pattern"] == "Chronic"]["company_name"].tolist()
        recent = neg_seg[neg_seg["pattern"] == "Recent deterioration"]["company_name"].tolist()
        if chronic:
            st.warning(f"Chronic negative equity: {', '.join(chronic)}.")
        if recent:
            st.warning(f"Recent deterioration into negative equity: {', '.join(recent)}.")
else:
    companies_in_seg = seg_df[["company_id", "company_name"]].drop_duplicates() if not seg_df.empty else seg_df
    if not seg_df.empty:
        name_row = companies_in_seg[companies_in_seg["company_id"] == company_id]
        if not name_row.empty:
            data_quality_note(name_row.iloc[0]["company_name"])

    comp = seg_df[seg_df["company_id"] == company_id][["quarter_label"] + metrics].sort_values("quarter_label") if not seg_df.empty else seg_df
    cta_vals = comp["capital_to_assets"].dropna() if not comp.empty else comp
    latest_v = float(cta_vals.iloc[-1]) if len(cta_vals) else None
    delta_v = float(cta_vals.iloc[-1] - cta_vals.iloc[-2]) if len(cta_vals) > 1 else None
    verdict_metric("Latest capital-to-assets", latest_v, delta_v, True, "pct")

    if comp.empty:
        st.caption("No balance sheet data on record for this company.")
    else:
        fig = go.Figure()
        for m, color in zip(metrics, CHART_COLORS["sequence"]):
            fig.add_trace(go.Scatter(x=comp["quarter_label"], y=comp[m], mode="lines+markers", name=METRIC_LABELS[m], line=dict(color=color)))
        fig.update_layout(title="Solvency ratios over time", height=420, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch")
        with st.expander("View data table"):
            st.dataframe(styled_pct_table(comp, metrics), width="stretch")
        with st.expander("Analyst notes"):
            notes = [f"- {METRIC_LABELS[m]} has {trend_phrase(comp.set_index('quarter_label')[m], higher_is_better=True)}." for m in metrics]
            st.markdown("\n".join(notes))

    st.subheader("Alerts — negative equity")
    neg = compute_negative_equity_duration()
    row = neg[neg["company_id"] == company_id]
    if not row.empty:
        r = row.iloc[0]
        st.error(f"Negative equity in {r['quarters_negative']} of {r['quarters_reported']} reported quarters "
                 f"({r['pct_negative']:.0%}) — {'currently negative' if r['latest_negative'] else 'not currently negative'}.")
    else:
        st.success("No negative-equity quarters on record for this company.")
