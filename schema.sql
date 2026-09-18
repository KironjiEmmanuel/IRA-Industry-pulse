-- ============================================================
-- IRA Dashboard — Core Schema (Phase 6b)
--
-- Design grounded in the hybrid star schema decided earlier:
--   - dim_period / dim_company / dim_class as shared dimensions
--   - fact_pl: WIDE table for fixed-column P&L data
--     (fingerprints: PL_GB_SUMMARY, PL_LT_SUMMARY, PL_MICRO_SUMMARY,
--      GB_COMBINED_PREMIUM_SUMMARY, MICRO_COMBINED_PREMIUM_SUMMARY)
--   - fact_class_metric: LONG/EAV table for variable-metric,
--     class-level data (the 12-instance LT revenue-account group,
--     the 9 GB class metrics, the 11 Micro class metrics)
--   - fact_balance_sheet: LONG/EAV table for the transposed,
--     chunked capital-structure sheets
--   - fact_load_audit: traceability — which sheet/fingerprint fed
--     which rows, so a bad load can be traced back to its source
--     sheet without re-deriving that from scratch
-- ============================================================

-- ------------------------------------------------------------
-- DIMENSION TABLES
-- ------------------------------------------------------------

CREATE TABLE dim_period (
    period_id       SERIAL PRIMARY KEY,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    period_end_date DATE,
    quarter_label   VARCHAR(10) NOT NULL,  -- e.g. '2025Q1' — human-readable, used in the ETL's own logging
    UNIQUE (year, quarter)
);
COMMENT ON TABLE dim_period IS
    'One row per reporting quarter. Populated from the PERIOD_METADATA '
    'fingerprint (the "Details" cover sheet) rather than parsed from the '
    'filename, since filenames have already shown formatting drift.';

CREATE TABLE dim_company (
    company_id      SERIAL PRIMARY KEY,
    company_name    VARCHAR(200) NOT NULL UNIQUE,
    -- normalized_name exists because IRA's own source data has trailing
    -- whitespace / spacing inconsistencies on company names (confirmed
    -- during fingerprint building — e.g. "AFRICAN MERCHANT ASSURANCE ").
    -- ETL should always upsert against normalized_name, never raw text.
    normalized_name VARCHAR(200) NOT NULL UNIQUE
);
COMMENT ON TABLE dim_company IS
    'One row per insurer. normalized_name (trimmed, single-spaced, '
    'uppercased) is the real join key the ETL should match against — '
    'company_name preserves IRA''s original formatting for display.';

CREATE TABLE dim_class (
    class_id        SERIAL PRIMARY KEY,
    class_name      VARCHAR(100) NOT NULL,
    segment         VARCHAR(10) NOT NULL CHECK (segment IN ('LT', 'GB', 'Micro')),
    UNIQUE (class_name, segment)
);
COMMENT ON TABLE dim_class IS
    'Business class per segment. LT classes come from titles (Life '
    'Assurance, Annuities, ...); GB classes are column headers (Aviation, '
    'Engineering, ...); Micro "classes" are product types (Life, General, '
    'Bundled). segment is part of the natural key since IRA reuses some '
    'generic labels across segments.';

-- ------------------------------------------------------------
-- FACT TABLE 1: WIDE — company-level P&L / combined summaries
-- ------------------------------------------------------------

CREATE TABLE fact_pl (
    period_id                          INT NOT NULL REFERENCES dim_period(period_id),
    company_id                         INT NOT NULL REFERENCES dim_company(company_id),
    segment                            VARCHAR(10) NOT NULL CHECK (segment IN ('LT', 'GB', 'Micro')),
    source_fingerprint_id              VARCHAR(60) NOT NULL,  -- e.g. 'PL_GB_SUMMARY' — traceability, not a join key

    -- IFRS17 income statement line items (from PL_GB/LT/MICRO_SUMMARY)
    insurance_revenue                  NUMERIC(18,2),
    insurance_service_expense          NUMERIC(18,2),
    reinsurance_expenses                NUMERIC(18,2),  -- new in 2026: split out from net figure below
    reinsurance_income                  NUMERIC(18,2),  -- new in 2026: split out from net figure below
    net_reinsurance_expense            NUMERIC(18,2),
    insurance_service_result           NUMERIC(18,2),
    net_investment_income              NUMERIC(18,2),
    finance_expense_insurance_contracts NUMERIC(18,2),
    finance_income_reinsurance_contracts NUMERIC(18,2),
    net_financial_result                NUMERIC(18,2),
    asset_mgmt_services_revenue        NUMERIC(18,2),
    other_income                       NUMERIC(18,2),
    other_finance_costs                NUMERIC(18,2),
    other_operating_expenses           NUMERIC(18,2),
    share_of_profit_associates         NUMERIC(18,2),
    profit_before_income_tax           NUMERIC(18,2),
    income_tax_expense                 NUMERIC(18,2),
    profit_for_the_year                NUMERIC(18,2),

    -- combined premium/UW summary line items (from GB/MICRO_COMBINED_PREMIUM_SUMMARY)
    -- nullable: only populated when source_fingerprint_id is one of the COMBINED variants
    gross_direct_premium               NUMERIC(18,2),
    inward_reinsurance                 NUMERIC(18,2),
    outward_reinsurance                NUMERIC(18,2),
    net_premium_written                NUMERIC(18,2),
    net_earned_premium_income          NUMERIC(18,2),
    incurred_claims                    NUMERIC(18,2),
    net_commissions                    NUMERIC(18,2),
    expense_of_management              NUMERIC(18,2),
    underwriting_profit_loss           NUMERIC(18,2),
    investment_income                  NUMERIC(18,2),
    operating_profit                   NUMERIC(18,2),

    loaded_at                          TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (period_id, company_id, source_fingerprint_id)
);
COMMENT ON TABLE fact_pl IS
    'Wide fact table for fixed-column sheets: the three P&L summaries '
    '(GB/LT/Micro) and the two combined premium summaries. Two logically '
    'different report types share this table because both are '
    'company-grain, wide-shape data — kept in separate column groups '
    'rather than separate tables to avoid a third near-identical wide '
    'table for what is structurally the same shape. reinsurance_expenses '
    'and reinsurance_income are NULL for any quarter before 2026, since '
    'IRA only started splitting that column out then — a known, '
    'documented gap, not a load error.';

CREATE INDEX idx_fact_pl_period ON fact_pl(period_id);
CREATE INDEX idx_fact_pl_company ON fact_pl(company_id);

-- ------------------------------------------------------------
-- FACT TABLE 2: LONG/EAV — class-level metrics
-- ------------------------------------------------------------

CREATE TABLE fact_class_metric (
    period_id               INT NOT NULL REFERENCES dim_period(period_id),
    company_id              INT NOT NULL REFERENCES dim_company(company_id),
    class_id                INT REFERENCES dim_class(class_id),  -- nullable: some LT_CLASS_REVENUE_ACCOUNT
                                                                   -- instances (e.g. 'Combined') may be
                                                                   -- excluded from class-level rollups —
                                                                   -- decide at load time, not schema time
    metric_name              VARCHAR(80) NOT NULL,  -- e.g. 'gross_premium', 'claims_paid', 'market_share_pct'
    metric_value              NUMERIC(18,4),
    value_type                VARCHAR(12) NOT NULL CHECK (value_type IN ('absolute', 'percentage', 'ratio')),
    source_fingerprint_id     VARCHAR(60) NOT NULL,

    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (period_id, company_id, class_id, metric_name, source_fingerprint_id)
);
COMMENT ON TABLE fact_class_metric IS
    'Long/EAV table for variable-metric, class-level data: LT revenue '
    'accounts by class (12 fingerprints instances), GB class metrics (9 '
    'fingerprints), Micro class metrics (11 fingerprints). value_type is '
    'stored per row deliberately — this is the same field the matcher''s '
    'value-sanity tiebreak checks against, so a loader bug that puts a '
    'percentage into an absolute-typed row is checkable with a simple '
    'query, not just trusted blindly.';

CREATE INDEX idx_fact_class_metric_period ON fact_class_metric(period_id);
CREATE INDEX idx_fact_class_metric_company ON fact_class_metric(company_id);
CREATE INDEX idx_fact_class_metric_class ON fact_class_metric(class_id);

-- ------------------------------------------------------------
-- FACT TABLE 3: LONG/EAV — balance sheet (transposed source sheets)
-- ------------------------------------------------------------

CREATE TABLE fact_balance_sheet (
    period_id               INT NOT NULL REFERENCES dim_period(period_id),
    company_id              INT NOT NULL REFERENCES dim_company(company_id),
    segment                  VARCHAR(10) NOT NULL CHECK (segment IN ('LT', 'GB', 'Micro')),
    line_item                 VARCHAR(100) NOT NULL,  -- e.g. 'Share Capital', 'Revaluation Reserves'
    line_value                 NUMERIC(18,2),
    source_fingerprint_id     VARCHAR(60) NOT NULL,

    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (period_id, company_id, line_item)
);
COMMENT ON TABLE fact_balance_sheet IS
    'Long/EAV table for the transposed capital-structure sheets (LT/GB/'
    'Micro). Source sheets are split across multiple chunked worksheets '
    'per quarter (varying counts — 3 chunks one quarter, different the '
    'next) because too many companies exceed one sheet''s column width. '
    'The ETL must stitch chunks back together by row LABEL before '
    'loading here, never by chunk position — chunk count and order are '
    'not stable across quarters.';

CREATE INDEX idx_fact_balance_sheet_period ON fact_balance_sheet(period_id);
CREATE INDEX idx_fact_balance_sheet_company ON fact_balance_sheet(company_id);

-- ------------------------------------------------------------
-- AUDIT TABLE — traceability back to source sheet
-- ------------------------------------------------------------

CREATE TABLE fact_load_audit (
    load_id                 SERIAL PRIMARY KEY,
    period_id                INT NOT NULL REFERENCES dim_period(period_id),
    sheet_name                VARCHAR(60) NOT NULL,   -- the literal sheet name in that quarter's file
    fingerprint_id             VARCHAR(60) NOT NULL,   -- what the matcher resolved it to
    target_fact_table          VARCHAR(30) NOT NULL,
    rows_loaded                 INT NOT NULL,
    loaded_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE fact_load_audit IS
    'One row per sheet successfully loaded. Lets you answer "which sheet '
    'in which quarter''s file produced this fact row" without re-running '
    'the matcher — useful the moment a number on the dashboard looks '
    'wrong and you need to trace it back to source.';
