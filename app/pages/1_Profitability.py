import streamlit as st
import plotly.graph_objects as go
from ui import section_header, styled_pct_table, trend_phrase, band_counts_phrase, best_worst_phrase, verdict_metric, alerts_list, data_quality_note
from db import compute_cumulative_ratios, compute_live_bands, classify
from config_static import METRIC_LABELS, CHART_COLORS

st.set_page_config(page_title="Profitability", page_icon=":material/trending_up:", layout="wide")
view_mode, company_id, segment = section_header("Profitability — IFRS 17 margin", ["GB", "LT", "Micro"])
label = METRIC_LABELS["ifrs17_margin"]

with st.spinner("Loading profitability data..."):
    df = compute_cumulative_ratios()
seg_df = df[df["segment"] == segment]

if view_mode == "Market Overview":
    band = compute_live_bands(segment, "ifrs17_margin")
    trend = seg_df.groupby("quarter_label")["ifrs17_margin"].median().reset_index().sort_values("quarter_label")
    higher_better = band["polarity"] == "higher_better"

    vals = trend["ifrs17_margin"].dropna()
    latest_v = float(vals.iloc[-1]) if len(vals) else None
    delta_v = float(vals.iloc[-1] - vals.iloc[-2]) if len(vals) > 1 else None
    verdict_metric(f"{segment} median {label.lower()}", latest_v, delta_v, higher_better, "pct")

    basis = "Percentile bands, recomputed from the current dataset" if band.get("type") == "percentile" else "Fixed bands, justified from established filers only"
    st.caption(f"{basis} (n={band['n']} company-quarters)." if "n" in band else basis + ".")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=trend["quarter_label"], y=trend["ifrs17_margin"], mode="lines+markers",
                              name=f"{segment} median", line=dict(color=CHART_COLORS["primary"], width=3)))
    fig.add_hline(y=band["healthy_above"], line_dash="dot", line_color=CHART_COLORS["healthy"], annotation_text="healthy above")
    fig.add_hline(y=band["distressed_below"], line_dash="dot", line_color=CHART_COLORS["distressed"], annotation_text="distressed below")
    fig.update_layout(title=f"{segment} median {label} vs. current bands", height=420,
                       yaxis_tickformat=".0%", yaxis_title=label, xaxis_title="Quarter", plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Alerts")
    latest_q = seg_df["quarter_label"].max()
    latest = seg_df[seg_df["quarter_label"] == latest_q]
    alerts_list(latest, "company_name", "ifrs17_margin", segment, "ifrs17_margin")

    with st.expander("View data table"):
        table = seg_df[["quarter_label", "company_name", "ifrs17_margin"]].dropna().sort_values("quarter_label")
        st.dataframe(styled_pct_table(table, ["ifrs17_margin"]), width="stretch")

    with st.expander("Analyst notes"):
        st.markdown(
            f"- Segment median has {trend_phrase(trend.set_index('quarter_label')['ifrs17_margin'], higher_better)}.\n"
            f"- Latest quarter ({latest_q}): {band_counts_phrase(latest['ifrs17_margin'].tolist(), segment, 'ifrs17_margin')}.\n"
            f"- {best_worst_phrase(latest, 'company_name', 'ifrs17_margin', higher_better)}"
        )
else:
    companies_in_seg = seg_df[["company_id", "company_name"]].drop_duplicates()
    name_row = companies_in_seg[companies_in_seg["company_id"] == company_id]
    if not name_row.empty:
        data_quality_note(name_row.iloc[0]["company_name"])

    comp_df = seg_df[seg_df["company_id"] == company_id][["quarter_label", "ifrs17_margin"]].dropna().sort_values("quarter_label")
    band = compute_live_bands(segment, "ifrs17_margin")
    higher_better = band["polarity"] == "higher_better"
    latest_v = float(comp_df["ifrs17_margin"].iloc[-1]) if not comp_df.empty else None
    delta_v = float(comp_df["ifrs17_margin"].iloc[-1] - comp_df["ifrs17_margin"].iloc[-2]) if len(comp_df) > 1 else None
    verdict_metric(f"Latest {label.lower()}", latest_v, delta_v, higher_better, "pct")
    if latest_v is not None:
        st.caption(f"Classified **{classify(segment, 'ifrs17_margin', latest_v)}** against {segment}'s current bands.")

    if comp_df.empty:
        st.caption("No IFRS17 data on record for this company in this segment.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=comp_df["quarter_label"], y=comp_df["ifrs17_margin"], mode="lines+markers",
                                  line=dict(color=CHART_COLORS["primary"], width=3)))
        fig.update_layout(title=f"{label} over time", height=420, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch")
        with st.expander("View data table"):
            st.dataframe(styled_pct_table(comp_df, ["ifrs17_margin"]), width="stretch")
        with st.expander("Analyst notes"):
            st.markdown(f"- {label} has {trend_phrase(comp_df.set_index('quarter_label')['ifrs17_margin'], higher_better)}.")

st.caption("The IFRS17-vs-combined-ratio divergence view is still on the build list.")
