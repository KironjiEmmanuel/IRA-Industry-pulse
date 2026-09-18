import streamlit as st
from db import load_dim_company
from config_static import VIEW_MODES


def format_kes(value) -> str:
    """Scales a raw KES figure to a readable string: 1,234,567 -> 'KES 1.23M'."""
    import math
    if value is None or value != value:  # NaN check without importing pandas here
        return "—"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{sign}KES {v/1e9:.2f}B"
    if v >= 1e6:
        return f"{sign}KES {v/1e6:.2f}M"
    if v >= 1e3:
        return f"{sign}KES {v/1e3:.1f}K"
    return f"{sign}KES {v:,.0f}"


def trend_phrase(series: "pd.Series", higher_is_better: bool, unit: str = "pct") -> str:
    """Short, plain-language read on a quarter-ordered series: direction, size
    of the move, and whether that direction is good or bad for this metric."""
    s = series.dropna()
    if len(s) < 2:
        return "not enough history yet to call a trend"
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    change = last - first
    if unit == "pct":
        fmt = lambda v: f"{v:.1%}"
        flat_threshold = 0.005
    elif unit == "currency":
        fmt = format_kes
        flat_threshold = 0.01 * max(abs(first), 1)
    else:  # plain count, e.g. HHI
        fmt = lambda v: f"{v:,.0f}"
        flat_threshold = 0.01 * max(abs(first), 1)
    if abs(change) < flat_threshold:
        return f"held roughly flat, around {fmt(last)}"
    direction = "risen" if change > 0 else "fallen"
    improving = (change > 0) == higher_is_better
    verdict = "an improving" if improving else "a deteriorating"
    return f"{direction} from {fmt(first)} to {fmt(last)} — {verdict} trend over the period"


def band_counts(values: list[float], segment: str, metric: str) -> dict:
    from db import classify
    counts = {"Healthy": 0, "Watch": 0, "Distressed": 0}
    for v in values:
        label = classify(segment, metric, v)
        if label in counts:
            counts[label] += 1
    return counts


def band_counts_phrase(values: list[float], segment: str, metric: str) -> str:
    c = band_counts(values, segment, metric)
    total = sum(c.values())
    if total == 0:
        return "no companies with data in the latest quarter"
    return f"of {total} companies with data in the latest quarter: {c['Healthy']} healthy, {c['Watch']} watch, {c['Distressed']} distressed"


def best_worst_phrase(latest_df, name_col: str, value_col: str, higher_is_better: bool, unit: str = "pct") -> str:
    d = latest_df.dropna(subset=[value_col])
    if d.empty:
        return ""
    fmt = (lambda v: f"{v:.1%}") if unit == "pct" else (lambda v: f"{v:,.0f}")
    best = d.loc[d[value_col].idxmax() if higher_is_better else d[value_col].idxmin()]
    worst = d.loc[d[value_col].idxmin() if higher_is_better else d[value_col].idxmax()]
    return f"Best: **{best[name_col]}** ({fmt(best[value_col])}). Weakest: **{worst[name_col]}** ({fmt(worst[value_col])})."


def verdict_metric(label: str, value, delta, higher_is_better, fmt: str = "pct"):
    """Renders one verdict number, explicitly stating 'No data' rather than
    rendering nothing when a metric can't be computed -- see
    fintech-dashboard-design's pending/uncertain-state discipline."""
    if value is None:
        st.metric(label, "No data")
        return
    val_str = f"{value:.1%}" if fmt == "pct" else f"{value:,.0f}"
    delta_str = None
    if delta is not None:
        delta_str = f"{delta:+.1%}" if fmt == "pct" else f"{delta:+,.0f}"
    delta_color = "off" if higher_is_better is None else ("normal" if higher_is_better else "inverse")
    st.metric(label, val_str, delta_str, delta_color=delta_color)


def alerts_list(df, name_col: str, value_col: str, segment: str, metric: str, max_items: int = 6):
    """Always-visible (never inside an expander) list of companies currently
    classified Distressed on this metric -- per fintech-dashboard-design's
    'alerts surface directly on the page' rule."""
    from db import classify
    d = df.dropna(subset=[value_col]).copy()
    if d.empty:
        st.caption("No companies with data for this metric in the latest quarter.")
        return
    d["status"] = d[value_col].apply(lambda v: classify(segment, metric, v))
    flagged = d[d["status"] == "Distressed"].sort_values(value_col)
    if flagged.empty:
        st.success("No companies currently classified Distressed on this metric.")
        return
    plural = "company is" if len(flagged) == 1 else "companies are"
    st.warning(f"{len(flagged)} {plural} currently classified **Distressed**:")
    for _, row in flagged.head(max_items).iterrows():
        st.markdown(f"- **{row[name_col]}** — {row[value_col]:.1%}")
    if len(flagged) > max_items:
        st.caption(f"...and {len(flagged) - max_items} more — see the data table below.")


def data_quality_note(company_name: str):
    """Surfaces a known data-quality caveat for this specific company, right
    where its numbers are shown -- not just in code comments or memory."""
    from config_static import DATA_QUALITY_NOTES
    note = DATA_QUALITY_NOTES.get(company_name)
    if note:
        st.info(f"Data note: {note}")


def section_header(section_name: str, segments: list[str]):
    """Renders the Market Overview / Company Scorecard toggle + (in scorecard
    mode) a company selector shared across all four pages via session_state.
    Returns (view_mode, selected_company_id_or_None, selected_segment)."""
    with st.sidebar:
        st.caption("Kenya IRA Insurance Analytics · live from Supabase")

    st.title(section_name)

    view_mode = st.radio(
        "View", VIEW_MODES, horizontal=True,
        index=VIEW_MODES.index(st.session_state.get("view_mode", "Market Overview")),
        key=f"view_mode_radio_{section_name}",
    )
    st.session_state.view_mode = view_mode

    segment = st.selectbox("Segment", segments, key=f"segment_{section_name}")

    company_id = None
    if view_mode == "Company Scorecard":
        companies = load_dim_company()
        options = companies.sort_values("company_name")
        names = options["company_name"].tolist()
        ids = options["company_id"].tolist()

        default_idx = 0
        if st.session_state.get("selected_company_id") in ids:
            default_idx = ids.index(st.session_state["selected_company_id"])

        picked = st.selectbox("Company", names, index=default_idx, key=f"company_pick_{section_name}")
        company_id = ids[names.index(picked)]
        st.session_state.selected_company_id = company_id

    st.divider()
    return view_mode, company_id, segment


def styled_pct_table(df, pct_cols: list[str], other_formats: dict | None = None):
    """Returns a pandas Styler with ratio columns shown as percentages
    (e.g. 0.706 -> 70.6%) instead of raw decimals, for any st.dataframe call."""
    fmt = {c: "{:.1%}" for c in pct_cols if c in df.columns}
    if other_formats:
        fmt.update({c: f for c, f in other_formats.items() if c in df.columns})
    return df.style.format(fmt, na_rep="—")
