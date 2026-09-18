# IRA Kenya Insurance Analytics — Phase A Glossary
### Reference document for threshold determination & dashboard design
Compiled from the full Phase A exploration (`02_comprehensive_phase_a_exploration.ipynb`) —
P&L/IFRS 17, loss ratio/underwriting, market share, and balance sheet/solvency.

---

## 1. Data foundation

### Source structure
- IRA quarterly workbooks: 54–55 sheets, ~5 recurring *shapes* across GB/LT/Micro segments:
  P&L (IFRS 17), class-level revenue components, pre-computed ratios, company-level revenue
  accounts, and transposed balance sheets.
- **Appendix numbers are unstable** — IRA renumbers every quarter (e.g. balance sheets sat at
  Appendix 21/22 in 2024, 24/25/26 in 2025, 4/5/6 in 2026). All extraction in this project
  uses **content-based detection** (title text, header signature), never appendix number.
- IRA's own report titles ("January–March" = Q1, "January–June" = Q2, etc.) confirm figures
  are **cumulative year-to-date**, not discrete standalone quarters — verified against a
  published IRA total (Q1 2024 GB premium: IRA reports KES 69.82bn, our GB total came to
  KES 69.69bn).

### Fact tables (Postgres / Supabase)
| Table | Shape | Covers |
|---|---|---|
| `fact_pl` | wide, multiple row-shapes via `source_fingerprint_id` | IFRS17 P&L + GB/Micro combined-premium (underwriting) rows |
| `fact_balance_sheet` | long/EAV (`period_id, company_id, segment, line_item, line_value`) | Balance sheet line items, all 9 quarters |
| `dim_company` | dimension | `company_id`, `company_name`, `normalized_name` — **contains 6 placeholder rows, see §3** |

### `fact_pl` fingerprints
| `source_fingerprint_id` | Segment | Contains |
|---|---|---|
| `PL_GB_SUMMARY` | GB | IFRS17: insurance_revenue, insurance_service_result, etc. |
| `PL_LT_SUMMARY` | LT | same IFRS17 shape |
| `PL_MICRO_SUMMARY` | Micro | same IFRS17 shape |
| `GB_COMBINED_PREMIUM_SUMMARY` | GB | Statutory underwriting: gross_direct_premium, net_earned_premium_income, incurred_claims, net_commissions, expense_of_management, underwriting_profit_loss |
| `MICRO_COMBINED_PREMIUM_SUMMARY` | Micro | same underwriting shape |
| *(none)* | LT | **No underwriting-account equivalent exists for LT** — see §2 |

### Period mapping (hand-typed stand-in — replace with real `dim_period` join when available)
```python
PERIOD_META = {
    7:(2024,1,'2024Q1'), 10:(2024,2,'2024Q2'), 13:(2024,3,'2024Q3'), 16:(2024,4,'2024Q4'),
    1:(2025,1,'2025Q1'), 5:(2025,2,'2025Q2'), 23:(2025,3,'2025Q3'), 26:(2025,4,'2025Q4'),
    29:(2026,1,'2026Q1'),
}
```

---

## 2. Locked-in scope decisions

1. **Profitability layer = IFRS 17 only** (`insurance_service_result ÷ insurance_revenue`),
   consistent across GB/LT/Micro. This is the one framework genuinely comparable across
   segments — IFRS 17 was built specifically to replace fund accounting (LT) and
   underwriting accounting (GB) with a single recognition standard.
2. **Statutory combined ratio is shown alongside IFRS 17, not instead of it.** The two
   disagree on profit/loss direction for ~1/3 of GB companies in a given quarter — both are
   legitimate, differently-defined metrics; the divergence itself is worth surfacing, not
   resolving by picking one.
3. **LT has no underwriting-account equivalent by design.** Appendix 14 (LT's fund-accounting
   revenue account: Life Fund B/F, Total Benefits, Bonuses Paid, Annuities Paid, Life Fund
   C/F) is not in any fact table. It answers a *different* question (fund solvency/reserve
   adequacy) than underwriting profitability, and needs its own `fact_lt_fund` table, not a
   retrofit into GB-shaped columns.
4. **Both YTD (as-reported) and discrete (de-cumulated) views are built** for anything
   premium-based. Margin ratios are less distorted by the YTD convention (numerator and
   denominator both cumulative), but raw totals and concentration metrics are **not** —
   de-cumulation is mandatory there.
5. **Zero following a positive cumulative figure earlier in the same company-year is treated
   as missing (non-submission), not a real zero**, before de-cumulating.
6. **Balance sheet ratios here are composition-based solvency proxies** (capital-to-assets,
   liquidity ratio) — **not** IRA's official Risk-Based Capital solvency margin, which
   requires risk-weighted asset data not present in this appendix.
7. **Segment-specific thresholds are required.** GB, LT, and Micro have structurally
   different distributions on every metric checked — a single industry-wide band would
   misrepresent at least one segment.

---

## 3. Data-quality issues & fixes (apply these before trusting any number)

| Issue | Fix | Status |
|---|---|---|
| **6 placeholder rows in `dim_company`** (`GRAND TOTAL`=17, `Reinsurers`=46, `TOTAL`=216, `Insurers`=247, `TOTAL INSURERS`=1032, `MICROINSURERS`=1054) loaded as if they were real companies. Confirmed present in `fact_pl` (49 rows) and `fact_balance_sheet`. | `df[~df.company_id.isin([17,46,216,247,1032,1054])]` — filter immediately after loading raw data, upstream of any segment split, so the fix propagates automatically. | **Enforced** (per Kironji, applied across P&L/loss-ratio/market-share/balance-sheet) |
| `Share Capital` / `Share Captial` (typo) | Coalesce: `bfill(axis=1).iloc[:,0]` across variant columns | Applied |
| `Revaluation Reserves` / `Revaluation Reserve` (GB/Micro use singular, LT plural — a real segment convention, not a typo) | Same coalesce pattern | Applied |
| `Investment in Unit Trust` / `Investment In Unit Trusts` (mutually exclusive per company — confirmed never both populated) | Same coalesce pattern | Applied |
| Reliance & Limitations disclaimer text is stale (references wrong quarter's non-submissions; lists a company as excluded that's actually present) | Not machine-readable — don't use as an exclusion list | Documented, not fixable at source |
| Workbook `lockStructure="1"` protection blocks Excel's Unhide dialog | Strip `<workbookProtection>` tag from `xl/workbook.xml`, repackage | Resolved (doesn't affect openpyxl/ETL reads either way) |
| East Africa Reinsurance GB 2024Q1: Total Assets ≠ Total Equity+Liabilities by 1.3 | Rounding, immaterial | Noted |
| Ghana Reinsurance GB 2025Q4: off by 73.8 | Too large for pure rounding — **not yet investigated** | Open |

**Balance sheet extraction integrity check:** 643/645 rows (99.7%) balance exactly
(Total Assets = Total Equity + Liabilities) after placeholder exclusion — strong confirmation
the pivot/extraction logic is correct.

---

## 4. Metric definitions & formulas

| Metric | Formula | Segment(s) |
|---|---|---|
| IFRS 17 margin | `insurance_service_result / insurance_revenue` | GB, LT, Micro |
| Loss ratio | `incurred_claims / net_earned_premium_income` | GB, Micro |
| Commission ratio | `net_commissions / net_earned_premium_income` | GB, Micro |
| Expense ratio | `expense_of_management / net_earned_premium_income` | GB, Micro |
| **Combined ratio** | loss ratio + commission ratio + expense ratio (>100% = underwriting loss) | GB, Micro |
| Market share | `gross_direct_premium / segment_total_gdp` (per quarter, **discrete basis**) | GB, Micro |
| HHI | `Σ(market_share_pct²)` — <1500 unconcentrated, >2500 highly concentrated (standard DOJ-style bands) | GB, Micro |
| Capital-to-assets (proxy) | `Total Equity / Total Assets` | GB, LT, Micro |
| Liquidity ratio (proxy) | `(Cash + Term Deposits + Government Securities) / Total Assets` | GB, LT, Micro |
| Equity-to-insurance-liabilities | `Total Equity / Insurance Contract Liabilities` | GB, LT, Micro |
| De-cumulation | `discrete_Qn = cumulative_Qn − cumulative_Q(n-1)`; Q1 = cumulative_Q1 as-is | premium/claims figures |
| Outlier revenue floor | 10th percentile of segment revenue — excludes tiny-denominator artifacts before ranking best/worst | applied throughout |

---

## 5. Observed distributions — 2026Q1 anchor (use as starting point for threshold bands)

### P&L / IFRS 17 margin
| | GB | LT | Micro |
|---|---|---|---|
| median | 4% | 8% | 3% |
| mean | 3% | 23% | –48% |
| p10–p90 | –15% to 19% | –27% to 40% | –151% to 36% |
| % negative | 23% | 29% | 14% |

### Loss ratio / underwriting (GB, Micro only)
| | GB | Micro |
|---|---|---|
| loss ratio (median) | 71% | 29% |
| commission ratio (median) | 9% | 9% |
| expense ratio (median) | 29% | 29% |
| **combined ratio (median)** | **105%** | **105%** |

**GB's median combined ratio has run above 100% in every one of the 9 quarters observed
(101–105% range)** — this is the structural baseline, not an anomaly. Threshold bands must
be set relative to this Kenya-specific baseline, not a textbook "under 100% is healthy" rule.

### Market concentration (discrete-quarter basis — cumulative basis is distorted, see §2)
| | GB | Micro |
|---|---|---|
| HHI range (9 quarters) | 476–695 (genuinely unconcentrated) | 5,184–6,544 (severely concentrated) |
| Top-3 share, GB | ~25–30% typically | Micro is essentially 2 players (Britam Micro + Turaco) |

**Seasonal pattern confirmed:** GB's Q1 is consistently the largest discrete quarter every
year (69.7M–80.9M range vs 37–58M for Q2–Q4) — corporate renewal-cycle effect, not an
anomaly to flag against a threshold.

### Balance sheet / solvency proxy
| | GB | LT | Micro |
|---|---|---|---|
| capital-to-assets (median) | 28.7–37.7% across quarters | 10.6–12.3% across quarters | 29.6–61.1% across quarters (thin sample) |

LT's structurally lower ratio is expected (fund accounting — most of the balance sheet is
the Life Fund liability owed to policyholders, not equity).

---

## 6. Key findings for the dashboard

### Negative equity — the strongest convergent finding (3 independent metrics agree)
| Company | Segment | Pattern |
|---|---|---|
| **MADISON** | LT | Negative in **9/9 quarters** — chronic |
| **DIRECTLINE** | GB | Negative in **8/9 quarters** — chronic |
| **KENYA ORIENT** | GB | Negative in 6/9, intermittent |
| **CORPORATE INSURANCE CO** | LT | Negative 2024Q3–2025Q4, **recovered by 2026Q1** |
| **MUA** | GB | Negative only from **2025Q2 onward** — recent deterioration |
| **THE KENYAN ALLIANCE** | LT | Negative in exactly 1 quarter (2025Q4) — one-off, worth a sanity check |

Directline and Kenya Orient are also the worst GB performers on combined ratio (251% and
229% respectively) and among the worst on IFRS 17 margin — three metrics, same companies.
**Duration of negative equity matters as much as the fact of it** — chronic vs. recent vs.
one-off are different dashboard treatments.

### Confirmed vs. retracted anomalies
- **Micro 2025Q4 combined ratio spike (~711%) is real** — confirmed on both cumulative and
  discrete bases, and cross-validated by IFRS 17 margin cratering the same quarter
  (mean –331%, median –199%). Top investigation candidate.
- **GB 2025Q3 mean-margin collapse (–40% on YTD basis) was a cumulative-reporting artifact**
  — retracted once checked on the discrete basis (normal quarter: mean 6%, median 2%).

### Worst/best performers, GB, 2026Q1 (revenue-floor filtered)
- Worst combined ratio: Kenya Orient (251%), Occidental (229%), Directline (167%), Tausi
  (154%), Geminia (153%)
- Best combined ratio: Bupa Global (–7%), Equity Health (45%), Continental Re (75%)

---

## 7. Open items for the thresholds phase

1. How IFRS 17 margin and statutory combined ratio are jointly represented on the dashboard
   — both shown, one primary + one secondary, or divergence itself as a tracked metric.
2. Segment-specific threshold bands (GB/LT/Micro) — no single industry-wide band works.
3. Whether "negative equity duration" becomes its own scored dimension, separate from the
   point-in-time capital-to-assets ratio.
4. Micro 2025Q4 root-cause investigation before deciding how to treat it in any trailing
   average or threshold calibration.
5. Ghana Reinsurance's 73.8 balance-sheet discrepancy — investigate before fully trusting
   that company's solvency figures.
6. Balance sheet only has 9 quarters like everything else now (confirmed via the real DB
   export) — cross-quarter solvency trend work is no longer thinner than the other three
   sections.
7. `fact_lt_fund` table (Appendix 14 data) remains unbuilt — LT solvency work is blocked on
   this until it exists.
