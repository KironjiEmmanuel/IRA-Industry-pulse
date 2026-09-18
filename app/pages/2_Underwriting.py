import streamlit as st
import plotly.graph_objects as go
from ui import section_header, styled_pct_table, trend_phrase, band_counts_phrase, best_worst_phrase, verdict_metric, alerts_list, data_quality_note
from db import compute_cumulative_ratios, compute_live_bands, classify
from config_static import METRIC_LABELS, CHART_COLORS

st.set_page_config(page_title="Underwriting", page_icon=":material/receipt_long:", layout="wide")
view_mode, company_id, segment = section_header("Underwriting — loss, commission, expense & combined ratio", ["GB", "Micro"])

with st.spinner("Loading underwriting data..."):
    df = compute_cumulative_ratios()
seg_df = df[df["segment"] == segment]
metrics = ["loss_ratio", "commission_ratio", "expense_ratio", "combined_ratio"]

if view_mode == "Market Overview":
    metric = st.selectbox("Metric", metrics, format_func=lambda m: METRIC_LABELS[m])
    label = METRIC_LABELS[metric]
    band = compute_live_bands(segment, metric)
    higher_better = band["polarity"] == "higher_better"

    trend = seg_df.groupby("quarter_label")[metric].median().reset_index().sort_values("quarter_label")
    vals = trend[metric].dropna()
    latest_v = float(vals.iloc[-1]) if len(vals) else None
    delta_v = float(vals.iloc[-1] - vals.iloc[-2]) if len(vals) > 1 else None
    verdict_metric(f"{segment} median {label.lower()}", latest_v, delta_v, higher_better, "pct")

    basis = "Percentile bands, recomputed from the current dataset" if band.get("type") == "percentile" else "Fixed bands, justified from established filers only"
    st.caption(f"{basis} (n={band['n']} company-quarters)." if "n" in band else basis + ".")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=trend["quarter_label"], y=trend[metric], mode="lines+markers",
                              name=f"{segment} median", line=dict(color=CHART_COLORS["primary"], width=3)))
    fig.add_hline(y=band["healthy_below"], line_dash="dot", line_color=CHART_COLORS["healthy"], annotation_text="healthy below")
    fig.add_hline(y=band["distressed_above"], line_dash="dot", line_color=CHART_COLORS["distressed"], annotation_text="distressed above")
    fig.update_layout(title=f"{segment} median {label} vs. current bands", height=420,
                       yaxis_tickformat=".0%", yaxis_title=label, xaxis_title="Quarter", plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Alerts")
    latest_q = seg_df["quarter_label"].max()
    latest = seg_df[seg_df["quarter_label"] == latest_q]
    alerts_list(latest, "company_name", metric, segment, metric)

    with st.expander("View data table"):
        table = seg_df[["quarter_label", "company_name"] + metrics].dropna(how="all", subset=metrics).sort_values("quarter_label")
        st.dataframe(styled_pct_table(table, metrics), width="stretch")

    with st.expander("Analyst notes"):
        st.markdown(
            f"- Segment median has {trend_phrase(trend.set_index('quarter_label')[metric], higher_better)}.\n"
            f"- Latest quarter ({latest_q}): {band_counts_phrase(latest[metric].tolist(), segment, metric)}.\n"
            f"- {best_worst_phrase(latest, 'company_name', metric, higher_better)}"
        )
else:
    companies_in_seg = seg_df[["company_id", "company_name"]].drop_duplicates()
    name_row = companies_in_seg[companies_in_seg["company_id"] == company_id]
    if not name_row.empty:
        data_quality_note(name_row.iloc[0]["company_name"])

    comp_df = seg_df[seg_df["company_id"] == company_id][["quarter_label"] + metrics].dropna(how="all", subset=metrics).sort_values("quarter_label")
    if comp_df.empty:
        st.caption("No underwriting data on record for this company in this segment.")
    else:
        fig = go.Figure()
        for m, color in zip(metrics, CHART_COLORS["sequence"]):
            fig.add_trace(go.Scatter(x=comp_df["quarter_label"], y=comp_df[m], mode="lines+markers", name=METRIC_LABELS[m], line=dict(color=color)))
        fig.update_layout(title="Underwriting ratios over time", height=420, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch")

        latest = comp_df.iloc[-1]
        prev = comp_df.iloc[-2] if len(comp_df) > 1 else None
        cols = st.columns(4)
        for c, m in zip(cols, metrics):
            band = compute_live_bands(segment, m)
            val = latest.get(m)
            val = float(val) if val is not None and val == val else None
            delta = None
            if val is not None and prev is not None and prev.get(m) == prev.get(m):
                delta = val - float(prev[m])
            with c:
                verdict_metric(METRIC_LABELS[m], val, delta, band["polarity"] == "higher_better", "pct")

        with st.expander("View data table"):
            st.dataframe(styled_pct_table(comp_df, metrics), width="stretch")
        with st.expander("Analyst notes"):
            notes = []
            for m in metrics:
                b = compute_live_bands(segment, m)
                notes.append(f"- {METRIC_LABELS[m]} has {trend_phrase(comp_df.set_index('quarter_label')[m], b['polarity']=='higher_better')}.")
            st.markdown("\n".join(notes))

st.caption("Segment-vs-company benchmarking view is still on the build list.")
