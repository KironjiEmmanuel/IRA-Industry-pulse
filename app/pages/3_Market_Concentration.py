import streamlit as st
import plotly.graph_objects as go
from ui import section_header, styled_pct_table, trend_phrase, format_kes, verdict_metric, data_quality_note
from db import compute_market_concentration
from config_static import METRIC_LABELS, CHART_COLORS

st.set_page_config(page_title="Market Concentration", page_icon=":material/pie_chart:", layout="wide")
view_mode, company_id, segment = section_header("Market share & concentration", ["GB", "Micro"])

with st.spinner("Loading market concentration data..."):
    data = compute_market_concentration(segment)
hhi, top3, share = data["hhi"], data["top3"], data["company_share"]

HHI_UNCONCENTRATED = 1500
HHI_CONCENTRATED = 2500

if view_mode == "Market Overview":
    hhi_sorted = hhi.sort_values("quarter_label")
    hhi_vals = hhi_sorted["hhi"].dropna()
    latest_hhi = float(hhi_vals.iloc[-1]) if len(hhi_vals) else None
    delta_hhi = float(hhi_vals.iloc[-1] - hhi_vals.iloc[-2]) if len(hhi_vals) > 1 else None
    verdict_metric(f"{segment} market HHI", latest_hhi, delta_hhi, None, "count")

    st.subheader("Alerts")
    if latest_hhi is None:
        st.caption("No HHI data available for this segment yet.")
    elif latest_hhi > HHI_CONCENTRATED:
        st.warning(f"{segment} is **highly concentrated** — HHI of {latest_hhi:,.0f} is above the 2,500 threshold.")
    elif latest_hhi < HHI_UNCONCENTRATED:
        st.success(f"{segment} is unconcentrated — HHI of {latest_hhi:,.0f} is below the 1,500 threshold.")
    else:
        st.info(f"{segment} is moderately concentrated — HHI of {latest_hhi:,.0f}.")

    # top-3 companies per quarter, for the HHI hover -- who's actually driving concentration
    top3_detail = (
        share.sort_values(["yq", "market_share"], ascending=[True, False])
        .groupby(["yq", "quarter_label"])
        .apply(lambda g: "<br>".join(f"{r.company_name}: {r.market_share:.0%}" for r in g.head(3).itertuples()), include_groups=False)
        .reset_index(name="top3_detail")
    )
    hhi_plot = hhi_sorted.merge(top3_detail, on=["yq", "quarter_label"], how="left")

    fig_hhi = go.Figure()
    fig_hhi.add_trace(go.Scatter(
        x=hhi_plot["quarter_label"], y=hhi_plot["hhi"], mode="lines+markers",
        line=dict(color=CHART_COLORS["primary"], width=3),
        customdata=hhi_plot["top3_detail"],
        hovertemplate="<b>%{x}</b><br>HHI: %{y:.0f}<br><br>Top 3 by share:<br>%{customdata}<extra></extra>",
    ))
    fig_hhi.add_hline(y=HHI_UNCONCENTRATED, line_dash="dot", line_color=CHART_COLORS["healthy"], annotation_text="unconcentrated below 1,500")
    fig_hhi.add_hline(y=HHI_CONCENTRATED, line_dash="dot", line_color=CHART_COLORS["distressed"], annotation_text="highly concentrated above 2,500")
    fig_hhi.update_layout(title=f"{segment} — market concentration (HHI), hover a point for the top 3 that quarter",
                           height=400, yaxis_title="HHI", plot_bgcolor="white")
    st.plotly_chart(fig_hhi, width="stretch")
    with st.expander("View data table"):
        st.dataframe(hhi[["quarter_label", "hhi"]], width="stretch")

    fig_top3 = go.Figure()
    fig_top3.add_trace(go.Bar(x=top3["quarter_label"], y=top3["top3_share"], marker_color=CHART_COLORS["primary"]))
    fig_top3.update_layout(title=f"{segment} — combined share held by the top 3 companies", height=320,
                            yaxis_tickformat=".0%", plot_bgcolor="white")
    st.plotly_chart(fig_top3, width="stretch")
    with st.expander("View data table"):
        st.dataframe(styled_pct_table(top3[["quarter_label", "top3_share"]], ["top3_share"]), width="stretch")

    latest_q = share["yq"].max()
    latest = share[share["yq"] == latest_q].sort_values("market_share", ascending=False)
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(x=latest["company_name"], y=latest["market_share"], marker_color=CHART_COLORS["primary"]))
    fig_bar.update_layout(title=f"{segment} — market share by company, {latest['quarter_label'].iloc[0] if len(latest) else ''}",
                           height=420, yaxis_tickformat=".0%", plot_bgcolor="white")
    st.plotly_chart(fig_bar, width="stretch")
    with st.expander("View data table"):
        table = share[["quarter_label", "company_name", "disc_gross_direct_premium", "market_share"]].sort_values(["quarter_label", "market_share"], ascending=[True, False]).copy()
        table["disc_gross_direct_premium"] = table["disc_gross_direct_premium"].apply(format_kes)
        st.dataframe(styled_pct_table(table, ["market_share"]), width="stretch")

    with st.expander("Analyst notes"):
        top_names = ", ".join(f"{r.company_name} ({r.market_share:.0%})" for r in latest.head(3).itertuples()) if len(latest) else "no data"
        st.markdown(
            f"- HHI has {trend_phrase(hhi_sorted.set_index('quarter_label')['hhi'], higher_is_better=False, unit='count')}.\n"
            f"- Top 3 this quarter: {top_names}."
        )
else:
    companies_in_seg = share[["company_id", "company_name"]].drop_duplicates()
    name_row = companies_in_seg[companies_in_seg["company_id"] == company_id]
    if not name_row.empty:
        data_quality_note(name_row.iloc[0]["company_name"])

    comp = share[share["company_id"] == company_id][["quarter_label", "disc_gross_direct_premium", "market_share"]].sort_values("quarter_label")
    ms_vals = comp["market_share"].dropna()
    latest_v = float(ms_vals.iloc[-1]) if len(ms_vals) else None
    delta_v = float(ms_vals.iloc[-1] - ms_vals.iloc[-2]) if len(ms_vals) > 1 else None
    verdict_metric("Latest market share", latest_v, delta_v, True, "pct")

    if comp.empty:
        st.caption("No gross direct premium on record for this company in this segment — it may report under a different segment, or not file this figure.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=comp["quarter_label"], y=comp["market_share"], mode="lines+markers",
                                  line=dict(color=CHART_COLORS["primary"], width=3)))
        fig.update_layout(title="Market share over time", height=380, yaxis_tickformat=".0%", plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch")
        with st.expander("View data table"):
            display_comp = comp.copy()
            display_comp["disc_gross_direct_premium"] = display_comp["disc_gross_direct_premium"].apply(format_kes)
            st.dataframe(styled_pct_table(display_comp, ["market_share"]), width="stretch")
        with st.expander("Analyst notes"):
            st.markdown(f"- Market share has {trend_phrase(comp.set_index('quarter_label')['market_share'], higher_is_better=True)}.")
