"""
Static threshold config — the pieces that are judgment calls, not data outputs.
These do NOT get recomputed when new quarters load. Anything that IS derivable
from the data (GB/LT percentile bands, drift median/MAD) is computed live in
db.py against whatever's in Supabase right now — see compute_live_bands() and
compute_drift_stats().
"""

# --- data cleaning (confirmed findings, see project memory / analytical-decisions.md) ---
EXCLUDED_COMPANY_IDS = {17, 46, 216, 247, 1032, 1054, 37, 434}
# 17/46/216/247/1032/1054 = IRA total/subtotal rows loaded as companies
# 37 = "Amounts in Thousand Shillings" units-header row loaded as a company
# 434 = duplicate load of East Africa(n) Reinsurance, 2024Q1-Q3 only, overlaps
#       with company_id 14 rather than succeeding it -> excluded, not merged,
#       to avoid double-counting. Open item: needs the same investigation as
#       the Ghana Reinsurance balance-sheet discrepancy.

COMPANY_ID_MERGE = {294: 61, 318: 54, 1036: 44}
# confirmed renames (zero quarter-overlap between old/new id):
#   294 APA INSURANCE LIMITED       -> 61  APA INSURANCE COMPANY
#   318 CANNON GENERAL INSURANCE    -> 54  CANNON GENERAL INSURANCE (K) LIMITED
#  1036 INTRA AFRICA ASSURANCE      -> 44  INTRA-AFRICA ASSURANCE (1-qtr hyphen variant)

# --- percentile levels used for GB / LT bands (computed live from current data) ---
PERCENTILE_LOW = 0.25   # "healthy" / "distressed" cut, lower-tail side
PERCENTILE_HIGH = 0.75  # "healthy" / "distressed" cut, upper-tail side

METRIC_POLARITY = {
    "ifrs17_margin": "higher_better",
    "loss_ratio": "lower_better",
    "commission_ratio": "lower_better",
    "expense_ratio": "lower_better",
    "combined_ratio": "lower_better",
    "capital_to_assets": "higher_better",
    "liquidity_ratio": "higher_better",
    "equity_to_insurance_liabilities": "higher_better",
}

BALANCE_SHEET_METRICS = {"capital_to_assets", "liquidity_ratio", "equity_to_insurance_liabilities"}

# --- Micro: justified fixed bands (n too small for percentiles to mean anything) ---
# Derived from the two established Micro filers only (Britam Micro=69, Turaco=109).
# Other Micro company_ids (76, 91, 96, 131) are thin-premium/noisy entrants and
# should be shown qualitatively, not scored against these bands -- see
# MICRO_ESTABLISHED_IDS below and apply as a revenue-floor-style filter.
MICRO_ESTABLISHED_IDS = {69, 109}

MICRO_FIXED_BANDS = {
    "ifrs17_margin":   {"polarity": "higher_better", "distressed_below": 0.00, "healthy_above": 0.15},
    "loss_ratio":      {"polarity": "lower_better",  "healthy_below": 0.40, "distressed_above": 0.65},
    "commission_ratio":{"polarity": "lower_better",  "healthy_below": 0.05, "distressed_above": 0.15},
    "expense_ratio":   {"polarity": "lower_better",  "healthy_below": 0.32, "distressed_above": 0.42},
    "combined_ratio":  {"polarity": "lower_better",  "healthy_below": 0.90, "distressed_above": 1.15},
    "capital_to_assets": {"polarity": "higher_better", "distressed_below": 0.15, "healthy_above": 0.30},
    "liquidity_ratio":    {"polarity": "higher_better", "distressed_below": 0.35, "healthy_above": 0.55},
    "equity_to_insurance_liabilities": {"polarity": "higher_better", "distressed_below": 0.30, "healthy_above": 1.00},
}

# --- drift feature: robust z-score bands (fixed statistical convention, not data-derived) ---
DRIFT_Z_STABLE = 1.0        # |z| below this -> "Stable"
DRIFT_Z_SIGNIFICANT = 2.5   # |z| at/above this -> "Significant drift"; between the two -> "Moderate drift"

# Segments each metric applies to
SEGMENTS_BY_METRIC = {
    "ifrs17_margin": ["GB", "LT", "Micro"],
    "loss_ratio": ["GB", "Micro"],
    "commission_ratio": ["GB", "Micro"],
    "expense_ratio": ["GB", "Micro"],
    "combined_ratio": ["GB", "Micro"],
}

# Data-quality caveats that need to reach the dashboard wherever the company
# appears (per fintech-dashboard-design: a flag from the pipeline has to reach
# the UI, not stay in code comments) -- keyed by company_name exactly as it
# appears in dim_company.
DATA_QUALITY_NOTES = {
    "EAST AFRICA REINSURANCE": (
        "A second company_id (EAST AFRICAN REINSURANCE, 2024Q1-Q3) overlapped with this "
        "company's own records for the same quarters rather than succeeding them. Treated as "
        "a duplicate load and excluded -- not yet root-caused. Numbers below are this company's "
        "continuous record only."
    ),
    "GHANA REINSURANCE COMPANY": (
        "2025Q4 balance sheet: Total Assets vs. Total Equity + Liabilities is off by 73.8 -- "
        "too large to be simple rounding. Not yet investigated; treat solvency figures for this "
        "quarter with caution."
    ),
    "APA INSURANCE COMPANY": (
        "IRA reported this company under a second name (APA INSURANCE LIMITED) from 2024Q4 "
        "onward. Confirmed as a naming change, not a different company, and merged into one "
        "continuous history below."
    ),
    "CANNON GENERAL INSURANCE (K) LIMITED": (
        "IRA reported this company under a shortened name (CANNON GENERAL INSURANCE) from "
        "2025Q2 onward. Confirmed as a naming change, not a different company, and merged into "
        "one continuous history below."
    ),
    "INTRA-AFRICA ASSURANCE": (
        "One quarter (2024Q4) was reported with a hyphen-dropped name variant. Merged into this "
        "company's continuous history below."
    ),
}

SECTIONS = ["Profitability", "Underwriting", "Market Concentration", "Solvency"]
VIEW_MODES = ["Market Overview", "Company Scorecard"]

# Display labels -- used everywhere instead of raw column-name .replace().title(),
# so wording stays consistent and reads like a finished product, not a debug dump.
METRIC_LABELS = {
    "ifrs17_margin": "IFRS 17 margin",
    "loss_ratio": "Loss ratio",
    "commission_ratio": "Commission ratio",
    "expense_ratio": "Expense ratio",
    "combined_ratio": "Combined ratio",
    "capital_to_assets": "Capital-to-assets ratio",
    "liquidity_ratio": "Liquidity ratio",
    "equity_to_insurance_liabilities": "Equity-to-insurance-liabilities ratio",
    "market_share": "Market share",
    "top3_share": "Top-3 combined share",
    "hhi": "Herfindahl-Hirschman Index (HHI)",
}

# Shared chart palette, matched to .streamlit/config.toml's primaryColor family
# so Plotly figures (which don't inherit Streamlit's theme automatically) look
# like part of the same app rather than a default-blue Plotly drop-in.
CHART_COLORS = {
    "primary": "#1B4965",
    "healthy": "#2E7D5B",
    "watch": "#C98A1B",
    "distressed": "#B3432B",
    "muted": "#7C8A99",
    "sequence": ["#1B4965", "#5FA8D3", "#C98A1B", "#2E7D5B", "#B3432B", "#7C8A99"],
}

# Plotly's SI-prefix tick format -- auto-scales large KES figures to K/M/B on
# chart axes (e.g. 1,234,567 -> "1.23M") instead of a wall of raw digits.
CURRENCY_TICKFORMAT = "~s"
