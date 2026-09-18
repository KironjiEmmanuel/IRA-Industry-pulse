"""
Live Supabase access + live threshold computation.

Percentile bands (GB/LT) and drift median/MAD (all segments) are computed here,
against whatever is in the DB right now -- this is what makes the thresholds
"recompute every cycle" instead of being frozen in a file. Static judgment calls
(exclusions, merges, Micro's fixed bands, drift z-cutoffs) live in config_static.py.
"""

import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client

from config_static import (
    EXCLUDED_COMPANY_IDS, COMPANY_ID_MERGE, PERCENTILE_LOW, PERCENTILE_HIGH,
    METRIC_POLARITY, MICRO_FIXED_BANDS, DRIFT_Z_STABLE, DRIFT_Z_SIGNIFICANT,
)

IFRS17_FINGERPRINTS = ["PL_GB_SUMMARY", "PL_LT_SUMMARY", "PL_MICRO_SUMMARY"]
UW_FINGERPRINTS = ["GB_COMBINED_PREMIUM_SUMMARY", "MICRO_COMBINED_PREMIUM_SUMMARY"]


@st.cache_resource
def get_client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df["company_id"].isin(EXCLUDED_COMPANY_IDS)].copy()
    df["company_id"] = df["company_id"].replace(COMPANY_ID_MERGE)
    return df


@st.cache_data(ttl=3600)
def load_dim_period() -> pd.DataFrame:
    client = get_client()
    res = client.table("dim_period").select("*").order("period_id").execute()
    return pd.DataFrame(res.data)


@st.cache_data(ttl=3600)
def load_dim_company() -> pd.DataFrame:
    client = get_client()
    res = client.table("dim_company").select("*").execute()
    return pd.DataFrame(res.data)


@st.cache_data(ttl=3600)
def load_fact_pl() -> pd.DataFrame:
    """All P&L rows (IFRS17 summaries + combined-premium underwriting rows),
    cleaned and joined to period metadata. Numeric columns coerced."""
    client = get_client()
    periods = load_dim_period()
    companies = load_dim_company()

    fingerprints = IFRS17_FINGERPRINTS + UW_FINGERPRINTS
    res = (
        client.table("fact_pl")
        .select("*")
        .in_("source_fingerprint_id", fingerprints)
        .execute()
    )
    df = pd.DataFrame(res.data)
    if df.empty:
        return df

    df = _clean(df)
    df = df.merge(periods[["period_id", "year", "quarter", "quarter_label"]], on="period_id", how="left")
    df = df.merge(companies[["company_id", "company_name"]], on="company_id", how="left")

    num_cols = [
        "insurance_revenue", "insurance_service_result", "net_earned_premium_income",
        "incurred_claims", "net_commissions", "expense_of_management", "gross_direct_premium",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["yq"] = df["year"] * 10 + df["quarter"]
    return df.sort_values(["company_id", "source_fingerprint_id", "yq"])


def _safe_div(n, d):
    return np.where((pd.notna(d)) & (d != 0), n / d, np.nan)


@st.cache_data(ttl=3600)
def compute_cumulative_ratios() -> pd.DataFrame:
    """Adds ifrs17_margin (all segments) and loss/commission/expense/combined
    ratio (GB/Micro) on the as-reported YTD basis."""
    df = load_fact_pl()
    if df.empty:
        return df
    df = df.copy()
    is_ifrs = df["source_fingerprint_id"].isin(IFRS17_FINGERPRINTS)
    df.loc[is_ifrs, "ifrs17_margin"] = _safe_div(
        df.loc[is_ifrs, "insurance_service_result"], df.loc[is_ifrs, "insurance_revenue"]
    )

    is_uw = df["source_fingerprint_id"].isin(UW_FINGERPRINTS)
    df.loc[is_uw, "loss_ratio"] = _safe_div(df.loc[is_uw, "incurred_claims"], df.loc[is_uw, "net_earned_premium_income"])
    df.loc[is_uw, "commission_ratio"] = _safe_div(df.loc[is_uw, "net_commissions"], df.loc[is_uw, "net_earned_premium_income"])
    df.loc[is_uw, "expense_ratio"] = _safe_div(df.loc[is_uw, "expense_of_management"], df.loc[is_uw, "net_earned_premium_income"])
    df.loc[is_uw, "combined_ratio"] = (
        df.loc[is_uw, "loss_ratio"] + df.loc[is_uw, "commission_ratio"] + df.loc[is_uw, "expense_ratio"]
    )
    return df


def _decumulate(frame: pd.DataFrame, cols: list[str], key_cols: list[str]) -> pd.DataFrame:
    """Applies the 'zero-after-positive = missing' rule, then de-cumulates
    within each calendar year (Q1 = as-reported)."""
    out = []
    for _, g in frame.groupby(key_cols):
        g = g.sort_values("yq").copy()
        for col in cols:
            vals = g[col].values.copy()
            for i in range(1, len(vals)):
                if vals[i] == 0 and pd.notna(vals[i - 1]) and vals[i - 1] > 0:
                    vals[i] = np.nan
            g[col] = vals
        for col in cols:
            disc, prev_val = [], None
            for _, row in g.iterrows():
                if row["quarter"] == 1:
                    disc.append(row[col]); prev_val = row[col]
                else:
                    if pd.notna(row[col]) and pd.notna(prev_val):
                        disc.append(row[col] - prev_val)
                    else:
                        disc.append(np.nan)
                    prev_val = row[col] if pd.notna(row[col]) else prev_val
            g[f"disc_{col}"] = disc
        out.append(g)
    return pd.concat(out) if out else frame


@st.cache_data(ttl=3600)
def compute_discrete_ratios() -> pd.DataFrame:
    """De-cumulated quarter values and discrete-quarter ratios, used for the drift feature."""
    df = compute_cumulative_ratios()
    if df.empty:
        return df
    ifrs = df[df["source_fingerprint_id"].isin(IFRS17_FINGERPRINTS)]
    uw = df[df["source_fingerprint_id"].isin(UW_FINGERPRINTS)]

    ifrs_d = _decumulate(ifrs, ["insurance_revenue", "insurance_service_result"], ["company_id", "segment"])
    ifrs_d["disc_ifrs17_margin"] = _safe_div(ifrs_d["disc_insurance_service_result"], ifrs_d["disc_insurance_revenue"])

    uw_d = _decumulate(
        uw, ["net_earned_premium_income", "incurred_claims", "net_commissions", "expense_of_management", "gross_direct_premium"],
        ["company_id", "segment"],
    )
    uw_d["disc_loss_ratio"] = _safe_div(uw_d["disc_incurred_claims"], uw_d["disc_net_earned_premium_income"])
    uw_d["disc_commission_ratio"] = _safe_div(uw_d["disc_net_commissions"], uw_d["disc_net_earned_premium_income"])
    uw_d["disc_expense_ratio"] = _safe_div(uw_d["disc_expense_of_management"], uw_d["disc_net_earned_premium_income"])
    uw_d["disc_combined_ratio"] = uw_d["disc_loss_ratio"] + uw_d["disc_commission_ratio"] + uw_d["disc_expense_ratio"]

    for frame, key in [(ifrs_d, ["company_id", "segment"]), (uw_d, ["company_id", "segment"])]:
        frame.sort_values(key + ["yq"], inplace=True)

    return pd.concat([ifrs_d, uw_d], axis=0, ignore_index=True, sort=False)


@st.cache_data(ttl=3600)
def compute_industry_pulse() -> dict:
    """Whole-industry rollup (GB+LT+Micro combined), discrete-quarter basis.

    Uses insurance_revenue (IFRS17), not gross_direct_premium -- LT has no
    gross_direct_premium at all (no underwriting-account equivalent, by
    design per the glossary), so a gross_direct_premium total would silently
    understate the industry by omitting LT entirely. insurance_revenue is
    the one figure genuinely comparable/summable across all three segments.
    """
    df = compute_discrete_ratios()
    rev = df[df["disc_insurance_revenue"].notna()][
        ["quarter_label", "yq", "segment", "company_id", "disc_insurance_revenue"]
    ]

    by_segment_quarter = (
        rev.groupby(["yq", "quarter_label", "segment"])["disc_insurance_revenue"]
        .sum()
        .reset_index()
        .sort_values("yq")
    )
    segment_share = by_segment_quarter.pivot(index=["yq", "quarter_label"], columns="segment", values="disc_insurance_revenue").fillna(0.0)
    segment_share = segment_share.reset_index().sort_values("yq")

    total = by_segment_quarter.groupby(["yq", "quarter_label"])["disc_insurance_revenue"].sum().reset_index().sort_values("yq")
    total["qoq_growth"] = total["disc_insurance_revenue"].pct_change()
    total["yoy_growth"] = total["disc_insurance_revenue"].pct_change(periods=4)

    return {"total": total, "segment_share": segment_share}


@st.cache_data(ttl=3600)
def compute_market_concentration(segment: str) -> dict:
    """Market share (%) and HHI on the discrete-quarter basis (glossary decision #4:
    raw totals/concentration are distorted on a YTD basis, margin ratios aren't --
    this one needs de-cumulation, unlike the ratio bands)."""
    df = compute_discrete_ratios()
    seg_df = df[(df["segment"] == segment) & (df["disc_gross_direct_premium"].notna())]
    seg_df = seg_df[seg_df["disc_gross_direct_premium"] > 0]  # a de-cumulated negative is a data artifact, not a real share

    quarter_totals = seg_df.groupby(["yq", "quarter_label"])["disc_gross_direct_premium"].sum().rename("quarter_total")
    merged = seg_df.merge(quarter_totals, on=["yq", "quarter_label"])
    merged["market_share"] = merged["disc_gross_direct_premium"] / merged["quarter_total"]

    hhi = (
        merged.groupby(["yq", "quarter_label"])["market_share"]
        .apply(lambda s: (s ** 2).sum() * 10000)
        .reset_index(name="hhi")
        .sort_values("yq")
    )
    top3 = (
        merged.sort_values(["yq", "market_share"], ascending=[True, False])
        .groupby(["yq", "quarter_label"])
        .head(3)
        .groupby(["yq", "quarter_label"])["market_share"]
        .sum()
        .reset_index(name="top3_share")
        .sort_values("yq")
    )
    return {"company_share": merged, "hhi": hhi, "top3": top3}


BS_LINE_ITEMS = [
    "Total Equity", "Total Assets", "Cash and Cash Balances", "Term Deposits",
    "Government Securites", "Insurance Contract Liabilites",
]


@st.cache_data(ttl=3600)
def load_balance_sheet_ratios() -> pd.DataFrame:
    """Pivots the fact_balance_sheet EAV table to wide, computes the three
    composition-based solvency proxies. These are proxies (capital-to-assets,
    liquidity ratio, equity-to-insurance-liabilities) -- not IRA's official
    risk-weighted RBC solvency margin, which needs data this appendix doesn't have."""
    client = get_client()
    periods = load_dim_period()
    companies = load_dim_company()

    res = (
        client.table("fact_balance_sheet")
        .select("*")
        .in_("line_item", BS_LINE_ITEMS)
        .execute()
    )
    df = pd.DataFrame(res.data)
    if df.empty:
        return df
    df = _clean(df)
    df["line_value"] = pd.to_numeric(df["line_value"], errors="coerce")

    wide = df.pivot_table(
        index=["period_id", "company_id", "segment"], columns="line_item", values="line_value", aggfunc="first"
    ).reset_index()
    wide = wide.merge(periods[["period_id", "year", "quarter", "quarter_label"]], on="period_id", how="left")
    wide = wide.merge(companies[["company_id", "company_name"]], on="company_id", how="left")
    wide["yq"] = wide["year"] * 10 + wide["quarter"]

    wide["capital_to_assets"] = _safe_div(wide.get("Total Equity"), wide.get("Total Assets"))
    liquid_assets = wide.get("Cash and Cash Balances", 0).fillna(0) + wide.get("Term Deposits", 0).fillna(0) + wide.get("Government Securites", 0).fillna(0)
    wide["liquidity_ratio"] = _safe_div(liquid_assets, wide.get("Total Assets"))
    wide["equity_to_insurance_liabilities"] = _safe_div(wide.get("Total Equity"), wide.get("Insurance Contract Liabilites"))

    return wide.sort_values(["company_id", "yq"])


@st.cache_data(ttl=3600)
def compute_negative_equity_duration() -> pd.DataFrame:
    """Per company: how many of its reported quarters had negative Total Equity,
    and out of how many -- the chronic/recent/one-off distinction from Phase A."""
    bs = load_balance_sheet_ratios()
    if bs.empty or "Total Equity" not in bs.columns:
        return pd.DataFrame(columns=["company_id", "company_name", "segment", "quarters_negative", "quarters_reported", "pct_negative", "latest_negative"])
    bs = bs.dropna(subset=["Total Equity"])
    grouped = bs.groupby(["company_id", "company_name", "segment"]).apply(
        lambda g: pd.Series({
            "quarters_negative": int((g["Total Equity"] < 0).sum()),
            "quarters_reported": int(len(g)),
            "latest_negative": bool(g.sort_values("yq").iloc[-1]["Total Equity"] < 0),
        }),
        include_groups=False,
    ).reset_index()
    grouped["pct_negative"] = grouped["quarters_negative"] / grouped["quarters_reported"]
    return grouped[grouped["quarters_negative"] > 0].sort_values("pct_negative", ascending=False)


@st.cache_data(ttl=3600)
def compute_headline_metrics() -> dict:
    """One verdict number per domain (GB segment, the largest/most complete),
    latest quarter vs. previous -- feeds the Home rollup row, per
    fintech-dashboard-design's 'verdict row' requirement for multi-domain apps."""
    cum = compute_cumulative_ratios()
    bs = load_balance_sheet_ratios()
    conc = compute_market_concentration("GB")

    def latest_and_delta(s: pd.Series):
        s = s.dropna().sort_index()
        if len(s) == 0:
            return None, None
        if len(s) == 1:
            return float(s.iloc[-1]), None
        return float(s.iloc[-1]), float(s.iloc[-1] - s.iloc[-2])

    gb_ifrs = cum[cum["segment"] == "GB"].groupby("quarter_label")["ifrs17_margin"].median()
    gb_cr = cum[cum["segment"] == "GB"].groupby("quarter_label")["combined_ratio"].median()
    hhi_s = conc["hhi"].set_index("quarter_label")["hhi"] if not conc["hhi"].empty else pd.Series(dtype=float)

    gb_bs = bs[bs["segment"] == "GB"] if not bs.empty else bs
    if not gb_bs.empty and "capital_to_assets" in gb_bs.columns:
        neg_s = gb_bs.dropna(subset=["capital_to_assets"]).groupby("quarter_label").apply(
            lambda g: float((g["capital_to_assets"] < 0).mean()), include_groups=False
        )
    else:
        neg_s = pd.Series(dtype=float)

    ifrs_val, ifrs_delta = latest_and_delta(gb_ifrs)
    cr_val, cr_delta = latest_and_delta(gb_cr)
    hhi_val, hhi_delta = latest_and_delta(hhi_s)
    neg_val, neg_delta = latest_and_delta(neg_s)

    return {
        "profitability": {"label": "GB median IFRS17 margin", "value": ifrs_val, "delta": ifrs_delta, "fmt": "pct", "higher_better": True},
        "underwriting": {"label": "GB median combined ratio", "value": cr_val, "delta": cr_delta, "fmt": "pct", "higher_better": False},
        "market_concentration": {"label": "GB market HHI", "value": hhi_val, "delta": hhi_delta, "fmt": "count", "higher_better": None},
        "solvency": {"label": "GB companies with negative equity", "value": neg_val, "delta": neg_delta, "fmt": "pct", "higher_better": False},
    }


@st.cache_data(ttl=3600)
def compute_live_bands(segment: str, metric: str) -> dict:
    """Percentile bands for GB/LT, recomputed against the current dataset.
    Falls back to the static justified fixed bands for Micro."""
    if segment == "Micro":
        band = dict(MICRO_FIXED_BANDS[metric])
        band["type"] = "fixed"
        return band

    df = compute_cumulative_ratios()
    vals = df.loc[df["segment"] == segment, metric].dropna()
    polarity = METRIC_POLARITY[metric]
    band = {"type": "percentile", "polarity": polarity, "n": int(len(vals))}
    if len(vals) == 0:
        return band
    lo, hi = vals.quantile(PERCENTILE_LOW), vals.quantile(PERCENTILE_HIGH)
    if polarity == "higher_better":
        band["distressed_below"] = round(float(lo), 4)
        band["healthy_above"] = round(float(hi), 4)
    else:
        band["healthy_below"] = round(float(lo), 4)
        band["distressed_above"] = round(float(hi), 4)
    return band


def classify(segment: str, metric: str, value: float) -> str:
    if value is None or pd.isna(value):
        return "No data"
    band = compute_live_bands(segment, metric)
    if band["polarity"] == "lower_better":
        if value < band["healthy_below"]:
            return "Healthy"
        if value > band["distressed_above"]:
            return "Distressed"
        return "Watch"
    else:
        if value > band["healthy_above"]:
            return "Healthy"
        if value < band["distressed_below"]:
            return "Distressed"
        return "Watch"


@st.cache_data(ttl=3600)
def compute_drift_stats(segment: str, metric: str) -> dict:
    """Median + MAD of the quarter-over-quarter delta of the discrete ratio,
    for the given segment/metric -- the reference distribution the drift
    z-score is measured against."""
    df = compute_discrete_ratios()
    col = f"disc_{metric}"
    seg_df = df[df["segment"] == segment].sort_values(["company_id", "yq"])
    deltas = seg_df.groupby("company_id")[col].diff().dropna()
    if len(deltas) == 0:
        return {"median_delta": 0.0, "mad": 0.0, "n": 0}
    med = float(deltas.median())
    mad = float((deltas - med).abs().median())
    return {"median_delta": round(med, 4), "mad": round(mad, 4), "n": int(len(deltas))}


def drift_label(segment: str, metric: str, delta: float) -> tuple[str, float]:
    """Returns (label, z) for a given company's latest quarter-over-quarter delta."""
    if delta is None or pd.isna(delta):
        return "No data", np.nan
    stats = compute_drift_stats(segment, metric)
    mad = stats["mad"]
    if mad == 0:
        return "Stable", 0.0
    z = (delta - stats["median_delta"]) / (1.4826 * mad)
    az = abs(z)
    if az < DRIFT_Z_STABLE:
        label = "Stable"
    elif az < DRIFT_Z_SIGNIFICANT:
        label = "Moderate drift"
    else:
        label = "Significant drift"
    return label, round(float(z), 2)
