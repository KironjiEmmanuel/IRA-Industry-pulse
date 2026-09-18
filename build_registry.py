"""
Fingerprint Registry — built from Q1 2025 IRA workbook (reference quarter)

Purpose: decouple sheet IDENTITY (what data it holds) from sheet LABEL
(what IRA happens to call it / number it this quarter). ETL matches an
incoming sheet against this registry using header_signature + title_pattern,
NOT the appendix number.

Each entry:
  fingerprint_id      - stable internal identifier, never changes across quarters
  description         - human-readable, what this data actually is
  segment             - LT (Long-Term/Life) | GB (General Business) | Micro | Combined
  shape               - 'wide_company_rows' (companies=rows, metrics/classes=cols)
                         | 'transposed_company_cols' (companies=cols, chunked across
                            multiple sheets due to Excel column limits)
  value_type          - 'absolute' | 'percentage' | 'ratio' | 'mixed_needs_review'
  maps_to_fact_table  - target Postgres fact table
  header_signature    - the exact header row tuple used for matching (order-sensitive)
  title_must_contain  - substring(s) in the title row that disambiguate sheets
                         which share an identical header_signature (e.g. GDP vs
                         claims-paid vs claims-incurred all reuse the same GB
                         class-column header)
  class_dimension     - 'from_title' if the dim_class value is embedded in the
                         title text (not a column) | 'from_columns' if classes
                         are literally the column headers | null if not class-level
  known_instances_2025Q1 - sheet_name -> dim_class value, for reference/audit only.
                         NEVER used as a matching key by the ETL.
  needs_review         - flags entries where something looked off and shouldn't
                         be silently trusted
"""
import json

registry = []

# ---------------------------------------------------------------
# 1. Company-level P&L (IFRS17 income statement), one row per company
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "PL_GB_SUMMARY",
    "description": "General Business (GB) company-level P&L / IFRS17 income statement",
    "segment": "GB",
    "shape": "wide_company_rows",
    "value_type": "absolute",
    "maps_to_fact_table": "fact_pl",
    "header_signature": ["Company","Insurance Revenue","Insurance Service Expense",
        "Net expenses from reinsurance contracts held","Insurance Service Result",
        "Net Investment Income","Finance expenses from insurance contracts",
        "Finance income from reinsurance contracts","Net Financial Result",
        "Asset management services revenue","Other Income","Other finance costs",
        "Other operating expenses",
        "Share of profit of associates and joint ventures accounted for using the equity method",
        "Profit before income tax","Income tax expense","Profit for the year"],
    "title_must_contain": ["SUMMARY OF GENERAL"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 1": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "PL_LT_SUMMARY",
    "description": "Long-Term (LT/Life) company-level P&L / IFRS17 income statement",
    "segment": "LT",
    "shape": "wide_company_rows",
    "value_type": "absolute",
    "maps_to_fact_table": "fact_pl",
    "header_signature": ["Company","Insurance Revenue","Insurance Service Expense",
        "Net expenses from reinsurance contracts held","Insurance Service Result",
        "Net Investment Income","Finance expenses from insurance contracts",
        "Finance income from reinsurance contracts","Net Financial Result",
        "Asset management services revenue","Other Income","Other finance costs",
        "Other operating expenses",
        "Share of profit of associates and joint ventures accounted for using the equity method",
        "Profit before income tax","Income tax expense","Profit for the year"],
    "title_must_contain": ["SUMMARY OF LONG TE"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 2": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "PL_MICRO_SUMMARY",
    "description": "Micro-insurer company-level P&L / IFRS17 income statement",
    "segment": "Micro",
    "shape": "wide_company_rows",
    "value_type": "absolute",
    "maps_to_fact_table": "fact_pl",
    "header_signature": ["Company","Insurance Revenue","Insurance Service Expense",
        "Net expenses from reinsurance contracts held","Insurance Service Result",
        "Net Investment Income","Finance expenses from insurance contracts",
        "Finance income from reinsurance contracts","Net Financial Result",
        "Asset management services revenue","Other Income","Other finance costs",
        "Other operating expenses",
        "Share of profit of associates and joint ventures accounted for using the equity method",
        "Profit before income tax","Income tax expense","Profit for the year"],
    "title_must_contain": ["SUMMARY OF MICRO"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 3": None},
    "needs_review": False,
    "note": "Shares IDENTICAL header_signature with PL_LT_SUMMARY (Appendix 2). "
            "title_must_contain is the ONLY thing that disambiguates these three. "
            "This is a real collision risk if a future quarter's title text drifts.",
})

# ---------------------------------------------------------------
# 2. LT premium by class — absolute AND percentage versions
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "LT_PREMIUM_BY_CLASS_ABS",
    "description": "LT gross premium by business class, absolute KES, per company",
    "segment": "LT",
    "shape": "wide_company_rows",
    "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": ["Company","Life Assurances","Annuities","Personal Pensions",
        "Deposit Administration","Group Life","Group Credit","Permanent Health",
        "Investments","Total","Market Share (%)"],
    "title_must_contain": ["SUMMARY OF LONG TE"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 4": "premium_absolute"},
    "needs_review": False,
    "note": "CRITICAL VALUE-SEMANTIC WATCH: In Q1 2024, an appendix with this exact "
            "'Life Assurances | Annuities | Pensions...' header carried PERCENTAGE "
            "values (e.g. 10.54) not absolute shillings. Value-sanity check must "
            "confirm magnitude (KES premiums are 5-7 figures) before trusting "
            "header match alone.",
})

registry.append({
    "fingerprint_id": "LT_PREMIUM_BY_CLASS_PCT",
    "description": "LT gross premium by business class, as % market share, per company",
    "segment": "LT",
    "shape": "wide_company_rows",
    "value_type": "percentage",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": ["Company","Life Assurances","Annuities","Pensions",
        "Deposit Administration","Group Life","Group Credit","Permanent Health",
        "Investments","Total","",""],
    "title_must_contain": ["SUMMARY OF LONG TE"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 5": "premium_pct"},
    "needs_review": False,
})

# ---------------------------------------------------------------
# 3. LT class-level revenue accounts — ONE fingerprint, 12 class instances
#    (this is the long/EAV pattern: same columns, class embedded in title)
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "LT_CLASS_REVENUE_ACCOUNT",
    "description": ("LT business revenue account (Life Fund BF, Gross Premium, Net "
                     "Premium, Claims, Surrenders, Bonuses, Commissions, Investment "
                     "Income/Expense, Life Fund CF) — repeated once per LT class"),
    "segment": "LT",
    "shape": "wide_company_rows",
    "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": ["Company","Life Fund BF","Gross Premium","Net Premium",
        "Other (Fee) Income","Total Benefits","Claims","Surrenders_x000D_",
        "Bonuses Paid","Annuities Paid","Net Commisions","Expense of Management",
        "Investment Income","Investment Expenses","Transfer To (From) P & L",
        "Life Fund CF"],
    "title_must_contain": None,
    "class_dimension": "from_title",
    "known_instances_2025Q1": {
        "APPENDIX 6": "Life Assurance",
        "APPENDIX 7": "Annuities",
        "APPENDIX 8": "Group Life",
        "APPENDIX 9": "Group Credit",
        "APPENDIX 10": "Investments",
        "LINKED": "Linked Investments",
        "NON-LINKED": "Non-Linked Investments",
        "APPENDIX 11": "Permanent Health",
        "PENSIONS": "Pensions",
        "APPENDIX 12": "Personal Pensions",
        "APPENDIX 13": "Deposit Administration",
        "APPENDIX 14": "Combined Long Term (all classes)",
    },
    "needs_review": False,
    "note": "APPENDIX 14 'Combined' is a TOTAL row across all other classes in this "
            "group — decide at load time whether to include it in fact_class_metric "
            "as class='Combined/Total' or treat it as a validation checksum instead "
            "of a loadable row (risk of double-counting if summed naively). "
            "title_must_contain intentionally left empty: header_signature alone is "
            "unique across the whole registry, and two members of this group "
            "(LINKED/NON-LINKED) don't follow the 'BUSINESS REVENUE ACCOUNTS' title "
            "convention the numbered appendices use.",
})

# ---------------------------------------------------------------
# 4. GB class-level metrics — ONE header shape, 9 distinct metrics via title
# ---------------------------------------------------------------
gb_class_header = ["Company","Aviation","Engineering","Fire Domestic","Fire Industrial",
    "Liability","Marine","Motor Private","Motor Commercial","Motor Commercial PSV",
    "Personal Accident","Theft","Workmens' Compensation","Medical","Miscellaneous",
    "Total_x000D_",""]

registry.append({
    "fingerprint_id": "GB_GROSS_PREMIUM_BY_CLASS",
    "description": "GB gross direct premium by class, per company, absolute KES",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["GROSS", "PREMIUM"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 15": None, "GDP": None},
    "needs_review": True,
    "note": "DUPLICATE SHEET PAIR, NOT QUITE IDENTICAL: APPENDIX 15 carries the same "
            "class-level premium data as GDP, but has ONE EXTRA trailing column "
            "('Market Share (%)') that GDP does not. Matcher tolerates this as an "
            "optional trailing column, but ETL must still pick ONE as canonical "
            "source (recommend GDP for the core figures) rather than loading both "
            "as if independent — and decide whether Appendix 15's extra column is "
            "worth capturing separately (it duplicates APPENDIX 16's market-share "
            "data anyway).",
    "optional_trailing_columns": ["Market Share (%)"],
})

registry.append({
    "fingerprint_id": "GB_NET_PREMIUM_INWARD_BY_CLASS",
    "description": "GB net premium income from inward reinsurance, by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["INWARD", "NET PREMIUM"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"INWARD": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_PREMIUM_MARKET_SHARE_BY_CLASS_PCT",
    "description": "GB premium market share (%) by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "percentage",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": ["Company","Aviation","Engineering","Fire Domestic","Fire Industrial",
        "Liability","Marine","Motor Private","Motor Commercial","Motor Commercial PSV",
        "Personal Accident","Theft","Workmens' Compensation","Medical","Miscellaneous",
        "Total_x000D_","",""],
    "title_must_contain": ["MARKET SHARE"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 16": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_CLAIMS_PAID_BY_CLASS",
    "description": "GB claims paid by class, per company, absolute KES",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["CLAIMS PAID"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 17": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_CLAIMS_INCURRED_BY_CLASS",
    "description": "GB claims incurred by class, per company, absolute KES",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["CLAIMS INCURRED"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 18": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_CLAIMS_INCURRED_RATIO_BY_CLASS",
    "description": "GB incurred claims ratio by class, per company — NOMINALLY a ratio",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "mixed_needs_review",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["INCURRED CLAIMS RATIOS"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 19": None},
    "needs_review": True,
    "note": "Title says 'RATIOS' but sample values (e.g. -70.8, 112.2, -232.9) are "
            "NOT in a 0-100% range — magnitude looks like the absolute claims "
            "figures elsewhere, not a ratio. Do NOT trust the title label here. "
            "Hold this sheet out of automatic loading until manually verified "
            "against IRA's PDF narrative report for the same quarter.",
})

registry.append({
    "fingerprint_id": "GB_NET_PREMIUM_INCOME_BY_CLASS",
    "description": "GB net premium income (NPI) by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["NPI", "NET PREMIUM INCOME"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"NPI": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_NET_EARNED_PREMIUM_BY_CLASS",
    "description": "GB net earned premium income (NEPI) by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["NEPI", "NET EARNED PREMIUM"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"NEPI": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_NET_COMMISSIONS_BY_CLASS",
    "description": "GB net commissions by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["NET COMMISSION"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"COM": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_MGMT_EXPENSES_BY_CLASS",
    "description": "GB management expenses by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["MANAGEMENT EXP"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"MGT": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "GB_UW_PROFIT_BY_CLASS",
    "description": "GB underwriting profit/loss by class, per company",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_class_metric",
    "header_signature": gb_class_header,
    "title_must_contain": ["UNDERWRITING PROFIT"],
    "class_dimension": "from_columns",
    "known_instances_2025Q1": {"APPENDIX 20": None},
    "needs_review": False,
})

# ---------------------------------------------------------------
# 5. Combined GB / Micro premium summary (reinsurance-inclusive), company rows
# ---------------------------------------------------------------
combined_header = ["Company","Gross Direct Premium","Inward Reinsurance","Outward Reinsurance",
    "Net Premium Written","UPR B/F","Unexpired Risk Reserve (B/F)","UPR C/F_x000D_",
    "Unexpired Risk Reserve (B/F)","Net Earned Premium Income","Incurred Claims",
    "Net Commisions","Expense of Management","Underwriting Profit /(Loss)",
    "Investment Income","Operating Profit_x000D_"]

registry.append({
    "fingerprint_id": "GB_COMBINED_PREMIUM_SUMMARY",
    "description": "GB combined premium/UW/investment summary per company (all classes combined)",
    "segment": "GB", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_pl",
    "header_signature": combined_header,
    "title_must_contain": ["GENERAL"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 21": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "MICRO_COMBINED_PREMIUM_SUMMARY",
    "description": "Micro combined premium/UW/investment summary per company",
    "segment": "Micro", "shape": "wide_company_rows", "value_type": "absolute",
    "maps_to_fact_table": "fact_pl",
    "header_signature": combined_header,
    "title_must_contain": ["MICRO"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 23": None},
    "needs_review": False,
    "note": "title_must_contain intentionally shortened to a single word. Q1 2026's "
            "equivalent sheet ('APPENDIX 25') uses completely different phrasing "
            "('SUMMARY OF MICROINSURANCE BUSINESS REVENUE ACCOUNTS' vs 2025's "
            "'SUMMARY OF COMBINED...') — even 'MICRO INSURANCE' vs 'MICROINSURANCE' "
            "(one word) varies within IRA's own files. Header shape "
            "(combined_header) is the reliable signal here; title now only needs "
            "to disambiguate GB vs Micro, not carry the full semantic match.",
})

# ---------------------------------------------------------------
# 6. Micro class-level metrics — ONE header shape (Life/General/Bundled/Total),
#    11 distinct metrics via title, mirrors the GB pattern above
# ---------------------------------------------------------------
micro_class_header = ["Company","Life","General","Bundled","Total_x000D_"]

micro_metrics = [
    ("MICRO_GROSS_PREMIUM_BY_TYPE", "GDP (Micro)", "GROSS DIRECT PREMIUM", "absolute"),
    ("MICRO_NET_PREMIUM_INWARD_BY_TYPE", "INWARD (Micro)", "INWARD:", "absolute"),
    ("MICRO_PREMIUM_MARKET_SHARE_PCT", "APPENDIX 23Micro", "MARKET SHARE", "percentage"),
    ("MICRO_CLAIMS_PAID_BY_TYPE", "APPENDIX 24Micro", "CLAIMS PAID", "absolute"),
    ("MICRO_CLAIMS_INCURRED_BY_TYPE", "APPENDIX 25Micro", "CLAIMS INCURRED", "absolute"),
    ("MICRO_CLAIMS_INCURRED_RATIO", "APPENDIX 26Micro", "INCURRED CLAIMS RATIOS", "mixed_needs_review"),
    ("MICRO_NET_PREMIUM_INCOME_BY_TYPE", "NPI (Micro)", "NPI:", "absolute"),
    ("MICRO_NET_EARNED_PREMIUM_BY_TYPE", "NEPI (Micro)", "NET EARNED PREMIUM", "absolute"),
    ("MICRO_NET_COMMISSIONS_BY_TYPE", "COM (Micro)", "NET COMMISSION", "absolute"),
    ("MICRO_MGMT_EXPENSES_BY_TYPE", "MGT (Micro)", "MANAGEMENT EXP", "absolute"),
    ("MICRO_UW_PROFIT_BY_TYPE", "APPENDIX 27Micro", "UNDERWRITING PROFIT", "absolute"),
]
for fid, sheet, title_kw, vtype in micro_metrics:
    entry = {
        "fingerprint_id": fid,
        "description": f"Micro-insurer {title_kw.title()} by product type (Life/General/Bundled)",
        "segment": "Micro", "shape": "wide_company_rows", "value_type": vtype,
        "maps_to_fact_table": "fact_class_metric",
        "header_signature": micro_class_header,
        "title_must_contain": [title_kw],
        "class_dimension": "from_columns",
        "known_instances_2025Q1": {sheet: None},
        "needs_review": vtype == "mixed_needs_review",
    }
    if vtype == "mixed_needs_review":
        entry["note"] = "Same 'RATIOS' labeling concern as GB_CLAIMS_INCURRED_RATIO_BY_CLASS " \
                         "(Appendix 19) — verify magnitude before trusting title label."
    registry.append(entry)

# ---------------------------------------------------------------
# 7. Transposed capital structure sheets (EAV) — companies as COLUMNS,
#    chunked across multiple sheets due to Excel column limits
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "LT_CAPITAL_STRUCTURE",
    "description": ("LT company balance-sheet/capital extract (Share Capital, Share "
                     "Premium, Revaluation Reserves, etc.) — companies as columns, "
                     "chunked across N sheets because too many companies fit one sheet width"),
    "segment": "LT", "shape": "transposed_company_cols", "value_type": "absolute",
    "maps_to_fact_table": "fact_balance_sheet",
    "header_signature": None,
    "header_signature_note": "Column headers here ARE company names, which vary — "
        "match on the FIRST DATA ROW label ('Share Capital') and title_must_contain instead.",
    "row_label_signature": ["Share Capital", "Share Premium", "Revaluation Reserves"],
    "title_must_contain": ["SUMMARY OF LONG TE"],
    "class_dimension": None,
    "known_instances_2025Q1": {
        "APPENDIX 24 i": "chunk_1_of_3", "APPENDIX 24 ii": "chunk_2_of_3", "APPENDIX 24 iii": "chunk_3_of_3"},
    "needs_review": False,
    "note": "This exact content has moved appendix number every year observed: "
            "Appendix 21 (2024) -> Appendix 24 (2025) -> Appendix 4 (2026). "
            "Chunk COUNT also varies (3 sheets in 2024/2025, but split differently "
            "in 2026) — driven by how many companies are on the register that "
            "quarter, not a content change. Stitch chunks back together by row "
            "label before loading, not by sheet position.",
})

registry.append({
    "fingerprint_id": "GB_CAPITAL_STRUCTURE",
    "description": ("GB company balance-sheet/capital extract — companies as columns, "
                     "chunked across N sheets"),
    "segment": "GB", "shape": "transposed_company_cols", "value_type": "absolute",
    "maps_to_fact_table": "fact_balance_sheet",
    "header_signature": None,
    "row_label_signature": ["Share Capital", "Share Captial"],  # NOTE: IRA typo variant seen in 2024
    "title_must_contain": ["SUMMARY OF GENERA"],
    "class_dimension": None,
    "known_instances_2025Q1": {
        "APPENDIX 25 i": "chunk_1_of_4", "APPENDIX 25 ii": "chunk_2_of_4",
        "APPENDIX 25 iii": "chunk_3_of_4", "APPENDIX  25 iv": "chunk_4_of_4"},
    "needs_review": True,
    "note": "IRA's own source data has a spelling inconsistency: 'Share Capital' vs "
            "'Share Captial' (typo) seen across quarters/sheets — row_label_signature "
            "match must tolerate this. Also note the literal sheet name 'APPENDIX  25 iv' "
            "has a double space — exact string matching on sheet NAME would already "
            "fail here even within the same quarter, reinforcing why we don't key off names.",
})

registry.append({
    "fingerprint_id": "MICRO_CAPITAL_STRUCTURE",
    "description": "Micro-insurer company capital extract — companies as columns",
    "segment": "Micro", "shape": "transposed_company_cols", "value_type": "absolute",
    "maps_to_fact_table": "fact_balance_sheet",
    "header_signature": None,
    "row_label_signature": ["Share Capital"],
    "title_must_contain": ["SUMMARY OF MICR"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 26 i": "chunk_1_of_1"},
    "needs_review": False,
})

# ---------------------------------------------------------------
# 8. Non-data / structural sheets — explicitly excluded from ETL
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "NON_DATA_COVER_PAGES",
    "description": "Cover/title/disclaimer/table-of-contents pages — no loadable data",
    "segment": None, "shape": None, "value_type": None,
    "maps_to_fact_table": None,
    "header_signature": None,
    "title_must_contain": None,
    "class_dimension": None,
    "known_instances_2025Q1": {
        "Details": None, "Reliance & Limitations": None, "Table of Contents": None},
    "needs_review": False,
})

registry.append({
    "fingerprint_id": "NON_DATA_TEMPLATE_HELPER",
    "description": ("Appears to be IRA's own internal spreadsheet-range bookkeeping "
                     "sheet (column headers like 'Appendix_1_Range'), not report data"),
    "segment": None, "shape": None, "value_type": None,
    "maps_to_fact_table": None,
    "header_signature": ["Details_Range", ""],
    "title_must_contain": None,
    "class_dimension": None,
    "known_instances_2025Q1": {"Sheet1": None},
    "needs_review": True,
    "note": "Confirm this is genuinely non-loadable before excluding permanently — "
            "worth a quick manual look in Phase 2, not assumed.",
})

# ---------------------------------------------------------------
# 8b. Period metadata sheet — genuinely useful, not just noise.
#     Structured source for dim_period (quarter, year, period-end date)
#     rather than parsing this out of the filename.
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "PERIOD_METADATA",
    "description": "Cover sheet carrying QUARTER / YEAR / PERIOD ENDED as structured labeled cells",
    "segment": None, "shape": "key_value_labels", "value_type": None,
    "maps_to_fact_table": "dim_period",
    "header_signature": None,
    "row_label_signature": ["QUARTER", "YEAR"],
    "title_must_contain": None,
    "class_dimension": None,
    "known_instances_2025Q1": {"Details": None},
    "needs_review": False,
    "note": "Use this sheet to populate dim_period (quarter, year, period-end date) "
            "programmatically instead of parsing the workbook filename — filenames "
            "have already shown formatting drift (underscores, spacing, hyphens) "
            "across the three quarters on hand, so this is the more reliable source.",
})

# ---------------------------------------------------------------
# 9. Sheet with irregular/multi-panel layout — flagged, not auto-handled
# ---------------------------------------------------------------
registry.append({
    "fingerprint_id": "MICRO_TWO_PANEL_UNRESOLVED",
    "description": ("Appendix 22 in 2025Q1: a single sheet containing TWO side-by-side "
                     "mini-tables (GDP panel + Claims Paid panel) rather than one clean "
                     "table. Structurally different from every other sheet in the file."),
    "segment": "Micro", "shape": "irregular_multi_panel", "value_type": "absolute",
    "maps_to_fact_table": None,
    "header_signature": None,
    "title_must_contain": ["MICRO"],
    "class_dimension": None,
    "known_instances_2025Q1": {"APPENDIX 22": "unresolved"},
    "needs_review": True,
    "note": "Do not auto-load. Needs manual split logic before it maps to any fact "
            "table — likely duplicates data already captured in GDP (Micro) and "
            "APPENDIX 24Micro, but not confirmed. Hold for Phase 2 human review. "
            "Also seen at Appendix 24 in Q1 2026 under a differently-phrased title "
            "('SUMMARY OF BUSINESS RESULTS UNDER MICRO...' vs 2025's 'SUMMARY OF "
            "MICRO...') — the structural signal (duplicate 'Company' header) is "
            "what actually identifies this pattern, title is just a Micro-segment check.",
})

with open("/mnt/user-data/outputs/fingerprint_registry_2025Q1.json", "w") as f:
    json.dump({
        "registry_version": "1.0",
        "built_from_quarter": "2025Q1",
        "total_fingerprints": len(registry),
        "entries": registry,
    }, f, indent=2)

print(f"Wrote {len(registry)} fingerprint entries.")
needs_review_count = sum(1 for r in registry if r.get("needs_review"))
print(f"Flagged needs_review: {needs_review_count}")

# ---------------------------------------------------------------
# 10. Phase 5 — expand known_instances to cover 2024 and 2026 too,
#     pulled directly from the matcher's own output (not retyped by
#     hand) so this stays consistent with what the matcher actually
#     decides, not a separate hand-maintained record.
# ---------------------------------------------------------------
import sys
sys.path.insert(0, "/home/claude")
from matcher import load_registry as _load_registry_json, run_matcher as _run_matcher

CLASS_KEYWORDS_IN_ORDER = [
    "Life Assurance", "Annuities", "Group Life", "Group Credit",
    "Non-Linked Investments", "Linked Investments", "Investments",
    "Permanent Health", "Personal Pensions", "Pensions",
    "Deposit Administration", "Combined Long Term",
]

def infer_class_label(title, sheet_name):
    if sheet_name == "LINKED":
        return "Linked Investments"
    if sheet_name == "NON-LINKED":
        return "Non-Linked Investments"
    if sheet_name == "PENSIONS":
        return "Pensions"
    if title:
        for kw in CLASS_KEYWORDS_IN_ORDER:
            if kw.upper() in title.upper():
                return kw
    return None

QUARTER_FILES = {
    "2024Q1": "/mnt/user-data/uploads/Quarter-1_2024_Statistics.xlsx",
    "2026Q1": "/mnt/project/Quarter1_2026__Industry_Statistics.xlsx",
}

by_fid = {e["fingerprint_id"]: e for e in registry}

for quarter_label, path in QUARTER_FILES.items():
    fresh_registry = _load_registry_json()  # re-read what's on disk right now
    results = _run_matcher(path, fresh_registry)

    from collections import defaultdict
    fid_sheets = defaultdict(list)
    for sheet_name, r in results.items():
        if r["verdict"] == "MATCHED":
            fid_sheets[r["fingerprint_ids"][0]].append((sheet_name, r["title"]))

    for fid, sheets in fid_sheets.items():
        entry = by_fid.get(fid)
        if entry is None:
            continue
        key = f"known_instances_{quarter_label}"
        instances = {}
        chunk_total = len(sheets) if entry.get("shape") == "transposed_company_cols" else None
        for idx, (sheet_name, title) in enumerate(sheets, start=1):
            if entry.get("class_dimension") == "from_title":
                instances[sheet_name] = infer_class_label(title, sheet_name)
            elif chunk_total:
                instances[sheet_name] = f"chunk_{idx}_of_{chunk_total}"
            else:
                instances[sheet_name] = None
        entry[key] = instances

# sheets confirmed out of scope for a given quarter (structural, not IRA
# renumbering) — recorded for audit, not matched to any fingerprint
by_fid["NON_DATA_COVER_PAGES"].setdefault("known_instances_2024Q1", {})
by_fid["NON_DATA_COVER_PAGES"]["known_instances_2024Q1"].update({
    "Details": None, "Reliance & Limitations": None, "Table of Contents": None,
})
by_fid["NON_DATA_COVER_PAGES"].setdefault("known_instances_2026Q1", {})
by_fid["NON_DATA_COVER_PAGES"]["known_instances_2026Q1"].update({
    "Reliance & Limitations": None, "Table of Contents": None,
})

with open("/mnt/user-data/outputs/fingerprint_registry_2025Q1.json", "w") as f:
    json.dump({
        "registry_version": "1.1",
        "built_from_quarter": "2025Q1",
        "known_instances_expanded_to": ["2024Q1", "2025Q1", "2026Q1"],
        "total_fingerprints": len(registry),
        "entries": registry,
    }, f, indent=2)

print(f"\nPhase 5: known_instances expanded to 2024Q1 and 2026Q1.")
fids_missing_2024 = [e["fingerprint_id"] for e in registry
                      if e.get("known_instances_2025Q1") and not e.get("known_instances_2024Q1")
                      and e["fingerprint_id"] not in ("PL_MICRO_SUMMARY", "MICRO_CAPITAL_STRUCTURE")
                      and not e["fingerprint_id"].startswith("MICRO_")]
print(f"Fingerprints with 2025 data but no 2024 match (excluding known Micro scope gap): {fids_missing_2024}")
