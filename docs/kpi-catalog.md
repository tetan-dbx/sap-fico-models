# CFO KPI Catalog — FICO Metric Views

How the CFO-level KPIs map to the metric views, their measures, and the underlying
gold columns. Query measures with `MEASURE(\`Measure Name\`)` grouped by dimensions.

## Profitability / P&L — `semantic_gl_journal_metrics`
| KPI | Measure(s) | Notes |
|-----|-----------|-------|
| Debit / Credit / Net (local) | `Debit (Local)`, `Credit (Local)`, `Net Movement (Local)` | Signed `amount_in_cc_currency` split by `debit_credit_code` |
| Debit / Credit / Net (functional) | `Debit (Functional)`, `Credit (Functional)`, `Net Movement (Functional)` | Functional currency; **equals local in this dataset** — no true group currency in the shares |
| Period amount | `Net Movement (Local)` grouped by `Fiscal Period` / `Posting Month` | Period activity |
| YTD | `YTD Net Movement (Local)` | Window: cumulative within year |
| Running / closing balance | `Closing Balance (Local)` | Window: cumulative all-time (anchored at 2012 data start). **Balance-sheet accounts only** — P&L accounts close each year, so filter to an account/BS account type |
| Rolling 12M / MoM | `Rolling 12M Net Movement (Local)`, `MoM Net Movement Growth %` | Trailing-window + derived growth |
| Prior-year comparison | any measure grouped by `Fiscal Year` / `Posting Year` | Pivot the year dimension (measures are reusable across it) |
| Reversals | `Reversal Net Movement (Local)`, `Reversal Line Count` | Posting-quality / audit |

## Liquidity / Cash — `semantic_cash_flow_metrics`
| KPI | Measure(s) | Notes |
|-----|-----------|-------|
| Net cash flow (multi-currency) | `Net Cash Flow (Local)` / `(Group)` / `(Transaction)` | Three currency views |
| Cash in / out | `Cash Inflow (Local)`, `Cash Outflow (Local)` | |
| YTD / rolling | `YTD Net Cash Flow (Local)`, `Rolling 12M Net Cash Flow (Local)` | Window measures |
| Forecast variance (primary) | `Forecast Variance` (EUR), `Forecast Variance %` | Signed `actual − forecast` (and as % of forecast); this is the FP&A/treasury headline. Uses the `Scenario` dimension — don't group by Scenario |
| Forecast accuracy | `Forecast Accuracy %` | `100 * (1 − |actual − forecast| / |actual|)`, **floored at 0%** so a >100% miss reads 0% (never negative); shown as a bounded companion to variance. Non-additive — computed at display grain |

## Working capital — `semantic_open_items_ar_ap_metrics`
| KPI | Measure(s) | Notes |
|-----|-----------|-------|
| Open receivables / payables | `Open Amount`, `Open Item Count` | Filter `AR / AP` |
| Overdue | `Overdue Amount`, `Overdue Item Count` | Open past net payment terms (`days_open > net_payment_days`), aged to the as-of snapshot date |
| AR / AP aging | `Open Amount` by `Aging Bucket` | Buckets `1: 0-30` / `2: 31-60` / `3: 61-90` / `4: 91-180` / `5: 181-365` / `6: 365+` (numbered to sort); aged to the as-of snapshot date, not today |
| DSO / DPO | `DSO / DPO (Amount-Weighted)` | **Amount-weighted** posting→clearing days (business-standard DSO/DPO); AR=DSO, AP=DPO. `Average Days To Clear (Simple)` is the unweighted reference |

## Cost control (Controlling) — `semantic_cost_center_metrics`
| KPI | Measure(s) | Notes |
|-----|-----------|-------|
| Spend (local / functional) | `Actual Spend (Local)`, `Actual Spend (Functional)` | Functional equals local in this dataset |
| Spend by hierarchy | `Actual Spend (Local)` by `Hierarchy Level 0..3` | Roll-up across the standard cost-center hierarchy |
| YTD spend | `YTD Spend (Local)` | Window measure |
| By department | `Actual Spend (Local)` by `Department` / `Cost Center Name` | |

## Example queries
Replace `<catalog>.<schema>` with your `catalog` / `schema` bundle variables.
```sql
-- YTD net movement by month (group by GL account for meaningful figures)
SELECT `Posting Month`, `G/L Account`,
       MEASURE(`Net Movement (Local)`) AS period, MEASURE(`YTD Net Movement (Local)`) AS ytd
FROM <catalog>.<schema>.semantic_gl_journal_metrics
WHERE `Posting Year` = 2024
GROUP BY ALL ORDER BY ALL;

-- Cost-center spend rolled up to a hierarchy level
SELECT `Hierarchy Level 1`, MEASURE(`Actual Spend (Local)`) AS spend
FROM <catalog>.<schema>.semantic_cost_center_metrics
GROUP BY ALL ORDER BY spend DESC;

-- Cash-flow forecast accuracy by month (do NOT group by Scenario)
SELECT `Flow Month`, MEASURE(`Forecast Accuracy %`) AS accuracy_pct
FROM <catalog>.<schema>.semantic_cash_flow_metrics
GROUP BY ALL ORDER BY ALL;
```

## Not modeled (source data not shared)
GL budget/plan (actual/plan variance), arbitrary target-currency FX conversion,
Balance-Sheet vs P&L statement classification (needs a GL-account/FSV hierarchy),
and profit-center/FSV hierarchies.
