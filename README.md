# SAP FICO Semantic Layer on Databricks

Build a governed **finance (FICO) semantic layer** on top of **SAP data products shared from
SAP Business Data Cloud (BDC)**, then give business users **self-service analytics with Genie**.
The whole stack is one Databricks Asset Bundle.

1. **Model.** A Spark Declarative Pipeline turns the shared SAP tables into a clean
   silver → gold star schema.
2. **Define metrics.** Unity Catalog **metric views** turn that schema into reusable KPIs: GL movement, YTD and
   closing balances, cash-flow forecast variance, cost-center spend roll-ups, AR/AP aging, DSO/DPO.
3. **Consume.** **Genie spaces** (natural-language Q&A) and an **AI/BI dashboard** are built on the
   metric views. Every consumer uses the same metric definitions.

The SAP data is accessed **zero-copy** through Delta Sharing. Nothing is extracted from SAP.

## Architecture

```
SAP Business Data Cloud ──(Delta Sharing, zero-copy)──▶ mounted share catalogs (sap_shared_*)
                                                               │
                         Spark Declarative Pipeline (serverless, batch MVs + expectations)
                                                               ▼
                                silver_*   typed, cleaned, renamed, quality-checked
                                                               ▼
                         gold_dim_* / gold_fact_*   Kimball star schema
                                                               ▼
                         semantic_*   Unity Catalog metric views (governed KPIs)
                                                               ▼
                 Genie spaces (self-service Q&A)  ·  AI/BI dashboard  ·  SQL / BI tools
```

## Prerequisites

| Requirement | Details |
|---|---|
| **Databricks workspace** | Unity Catalog enabled, **serverless compute** for jobs and pipelines enabled. |
| **SQL warehouse** | Pro or Serverless (serverless recommended). It runs the metric-view DDL, the dashboard and Genie. |
| **SAP BDC connection** | Your SAP BDC tenant connected to the workspace via Delta Sharing ([Share data between SAP BDC and Databricks](https://docs.databricks.com/aws/en/opensharing/sap-bdc)). |
| **SAP data products shared and mounted** | The six data products below shared from SAP BDC to the workspace, each mounted as a catalog ([Create a catalog from a share](https://docs.databricks.com/aws/en/opensharing/read-data-databricks)). |
| **Privileges** (deploying user / service principal) | `USE CATALOG`, `USE SCHEMA`, `SELECT` on the mounted share catalogs. On the target: `USE CATALOG`, plus `USE SCHEMA`, `CREATE TABLE`, `CREATE MATERIALIZED VIEW` on the target schema (or `CREATE SCHEMA` to create it). `CAN USE` on the SQL warehouse. Permission to create jobs and pipelines. |
| **Databricks CLI** | A recent version with `genie_spaces` bundle support (tested with **v1.19.0**). Authenticate with `databricks auth login --host <workspace-url> --profile <name>`. |
| **Python 3** (optional) | Needed only to regenerate or re-brand the dashboard JSON. |

### SAP data products used

| SAP data product | Table(s) in the share (`schema.table`) | Feeds |
|---|---|---|
| Entry View Journal Entry | `entryviewjournalentry.operationalacctgdocitem` | `gold_fact_journal_line`, `gold_fact_open_item` |
| Journal Entry Header | `journalentryheader.journalentry` | `gold_fact_journal_line` |
| Cash Flow | `cashflow.cashflow`, `cashflow.cashflowforecast` | `gold_fact_cash_flow` |
| Cost Center | `costcenter.costcenter`, `costcenter.costcentertext`, `costcenter.costcenterhierarchynode` | `gold_dim_cost_center` |
| Supplier | `supplier.supplier`, `supplier.supplierwithholdingtax` | `gold_dim_supplier` |
| Country / Region | `country.country` | `gold_dim_country` |

You choose the **catalog name** when you mount each share. Tell the bundle what you chose
with the `source_catalog_*` variables. If a data product's schema or table names differ in
your BDC release, edit the `configuration:` block in `resources/fico_pipeline.pipeline.yml`.
That block is the single source of truth for source tables.

## Quickstart

```bash
git clone <this-repo-url> && cd sap-fico-model

# 1. Create your local bundle config from the template (databricks.yml is gitignored)
cp databricks.yml.template databricks.yml
#    then replace every <PLACEHOLDER>: workspace URL, target catalog/schema,
#    SQL warehouse ID, company name, and the source_catalog_* names of your mounted shares.
```

```sql
-- 2. Create the target schema (once) — on a SQL warehouse or in a notebook
CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>;
```

```bash
# 3. Deploy and run: builds silver + gold, creates the metric views, applies column comments
databricks bundle validate --profile <name>
databricks bundle deploy   --profile <name>
databricks bundle run fico_semantic_layer --profile <name>

# 4. Enable Genie: uncomment "- resources/genie/*.yml" under `include:` in databricks.yml, then
databricks bundle deploy   --profile <name>
```

**Why Genie is a separate step.** The Genie API only lets a space reference tables that already
exist ([databricks/cli#6750](https://github.com/databricks/cli/issues/6750)). The metric views
are created by the job run in step 3, so the Genie spaces can only be deployed after that run.
You only need to do this the first time in a new schema. Afterwards, keep the include on and
`bundle deploy` handles everything.

The job (`fico_semantic_layer`) runs three tasks:
1. `build_gold_pipeline` runs the SDP pipeline to build `silver_*` and `gold_*`.
2. `deploy_metric_views` runs `CREATE OR REPLACE VIEW … WITH METRICS` for every YAML file in `src/metric_views/`.
3. `apply_column_comments` carries the SAP source column comments onto silver and gold. It's
   idempotent, so the comments survive full refreshes.

Every variable can also be overridden on the command line, e.g. `--var="schema=sap_fico_test"`.
Use a different schema per target: the pipeline writes to `${var.catalog}.${var.schema}`
in every target.

## Self-service analytics with Genie

`resources/genie/fico_genie_spaces.yml` deploys **four Genie spaces**, one per finance domain.
Each one is grounded on a single metric view, so Genie answers with the governed measure
definitions instead of re-deriving SQL from raw tables:

| Genie space | Metric view | Example questions |
|---|---|---|
| FICO · General Ledger | `semantic_gl_journal_metrics` | *"Show the top 10 G/L accounts by net movement in 2024"*, *"What is YTD net movement by month for G/L accounts in 2024?"* |
| FICO · Cost Center & Controlling | `semantic_cost_center_metrics` | *"Show actual spend by hierarchy level 1 for 2024"*, *"Which departments have the highest spend?"* |
| FICO · Cash Flow & Liquidity | `semantic_cash_flow_metrics` | *"What was the forecast variance by month in 2024?"*, *"Show cash inflow versus outflow by company for 2024"* |
| FICO · Working Capital (AR & AP) | `semantic_open_items_ar_ap_metrics` | *"What are our current DSO and DPO?"*, *"Show open receivables by aging bucket"* |

Each space's description encodes the domain's semantics: signed amounts, which measures are
non-additive, closing balance only for balance-sheet accounts, aging to the as-of date, and so on.

### Share with business users
Genie users need **`CAN RUN`** on the space, **`SELECT`** on its data and **`CAN USE`** on the
warehouse ([Genie setup](https://docs.databricks.com/aws/en/genie/set-up)):

```sql
GRANT USE CATALOG ON CATALOG <catalog>                       TO `finance-analysts`;
GRANT USE SCHEMA  ON SCHEMA  <catalog>.<schema>              TO `finance-analysts`;
GRANT SELECT      ON SCHEMA  <catalog>.<schema>              TO `finance-analysts`;  -- or per semantic_* view
```

```yaml
# in resources/genie/fico_genie_spaces.yml, under each space:
      permissions:
        - level: CAN_RUN
          group_name: finance-analysts
```

### Improve answer quality
- Add **text instructions**, **example SQL queries** and **SQL functions** (trusted assets) in the Genie UI, then pull them back
  into the bundle with `databricks bundle generate genie-space --resource <key> --force`. Then
  replace the hard-coded `catalog.schema` with `${var.catalog}.${var.schema}`.
- Put **synonyms** and **comments** on metric-view dimensions and measures (`src/metric_views/*.yaml`).
  Genie uses them to map business terms to fields.
- Keep each space **narrow**: one domain and one metric view. Add a new space instead of
  growing an existing one.

## What gets built

### Gold model
| Table | Grain | Source |
|-------|-------|--------|
| `gold_fact_journal_line` | Accounting document line | `operationalacctgdocitem` ⨝ `journalentry` header |
| `gold_fact_cash_flow` | Cash flow record (actual/forecast) | `cashflow` + `cashflowforecast` |
| `gold_fact_open_item` | AR/AP open item | open-item-managed customer/vendor lines |
| `gold_dim_cost_center` | Controlling area + cost center | `costcenter` + text + hierarchy node |
| `gold_dim_supplier` | Supplier | `supplier` + withholding-tax flag |
| `gold_dim_country` | Country | `country` |

### Metric views
| View | Source | Highlights |
|------|--------|------------|
| `semantic_gl_journal_metrics` | `gold_fact_journal_line` | Debit/Credit/Net movement in **local & functional currency**; **YTD / running (closing) balance / rolling 12M / MoM %**; reversals; intercompany/partner dims |
| `semantic_cash_flow_metrics` | `gold_fact_cash_flow` | Net flow in **transaction / local / group** currency; **signed forecast variance (amount & %)** as the headline, with **forecast accuracy % floored at 0–100**; YTD / rolling 12M |
| `semantic_cost_center_metrics` | `gold_fact_journal_line` ⨝ `gold_dim_cost_center` | Actual spend (local & functional); **roll-up across the cost-center hierarchy** (levels 0–3); YTD spend |
| `semantic_open_items_ar_ap_metrics` | `gold_fact_open_item` | Open **& overdue** balances, aging buckets, amount-weighted DSO/DPO |

**Semantic capabilities demonstrated:** several currency views (transaction, local, functional,
and group currency on cash flow); period and YTD; running/closing balance; rolling 12M and
month-over-month; actual vs forecast (cash flow); hierarchy roll-up (cost centers); and
group/intercompany reporting. Time intelligence uses metric-view window measures.
See [`docs/kpi-catalog.md`](docs/kpi-catalog.md) for the CFO-KPI → measure mapping and example queries.

### AI/BI dashboard
`resources/fico_dashboard.yml` deploys a CFO **"Financial Cockpit"** dashboard
(`src/dashboard/fico_cockpit.lvdash.json`) on the four metric views. Pages:
- Executive Overview
- General Ledger / P&L
- Cost Center / Controlling
- Cash & Liquidity
- Working Capital (AR/AP)
- a global Filters page (Company, Fiscal Year, Date Range)

It uses counters, bars, lines, tables, cross-filtering and custom Vega-Lite widgets (a radial
spend share and an AR/AP "items cleared" gauge). Every dataset is `MEASURE()`-based. Additive
measures re-aggregate at widget level, and non-additive ones (DSO/DPO, forecast accuracy, entry
lag) are shown at their display grain.

Dataset queries reference the views **unqualified**. The bundle sets each dataset's default
catalog and schema from `var.catalog` / `var.schema` (`dataset_catalog` / `dataset_schema`),
so the same JSON deploys to any environment.

**Re-brand / re-tune.** Regenerate the JSON with your branding, then redeploy:
```bash
python src/dashboard/build_dashboard.py --custom --customer "Contoso" --wordmark "CONTOSO" --currency EUR
```
- `--custom` adds the Vega-Lite widgets. Leave it out for a native-widgets-only build.
- The theme (colors, font, corner radius) and the default time window (`report_start`,
  `forecast_cap`) are in the `CONFIG` block of `build_dashboard.py`.
- The dashboard *display name* comes from `var.customer_name`.
- Keep logos and other brand assets in `src/dashboard/assets/`, which is gitignored.

## Extend the model
- **Add a metric view.** Drop a `<view_name>.yaml` into `src/metric_views/`, using `${catalog}` and
  `${schema}` in `source:`/`joins:`. The file name becomes the view name, and the next
  `bundle run` deploys it.
- **Add a gold table.** Add a `silver_*.py` / `gold_*.py` transform under
  `src/pipelines/fico/transformations/` (read sources with `get_source("<key>")`), and register
  the source table under `configuration:` in the pipeline YAML.
- **Add a Genie space.** Copy a block in `resources/genie/fico_genie_spaces.yml`, or create the
  space in the UI and import it with `databricks bundle generate genie-space --existing-id <id>`.

## Repository layout
```
databricks.yml.template                # bundle root template: copy to databricks.yml (gitignored)
resources/
  fico_pipeline.pipeline.yml           # SDP pipeline (+ source-table configuration)
  fico_job.yml                         # job: pipeline -> metric views -> column comments
  fico_dashboard.yml                   # AI/BI dashboard
  genie/fico_genie_spaces.yml          # Genie spaces (enabled after the first run)
src/
  pipelines/fico/transformations/      # SDP transforms (silver_*, gold_*, common.py)
  metric_views/                        # metric-view YAML definitions
  deploy/deploy_metric_views.py        # applies the YAML as CREATE VIEW … WITH METRICS
  deploy/apply_column_comments.py      # carries SAP source column comments onto silver/gold
  dashboard/build_dashboard.py         # generates fico_cockpit.lvdash.json
docs/
  kpi-catalog.md                       # KPI → measure mapping, example queries
```

## Metadata / comments
- **Table descriptions** are written in the transform and metric-view YAML `comment` fields.
- **Column comments** come from the SAP data products. `apply_column_comments.py` copies each
  source column's comment verbatim through the rename lineage, using the pipeline's
  `configuration` for the source tables.
- **Derived columns** get written descriptions. Any column with neither a source comment nor
  a written description is left empty; nothing is made up.

## Data conventions (verified by profiling the shared data)
- `DebitCreditCode` is `S` (debit) / `H` (credit); `AmountInCompanyCodeCurrency` is **signed**
  (debits positive, credits negative), so `net = SUM(amount)`.
- `FinancialAccountType`: `S`=G/L, `D`=Customer (AR), `K`=Vendor (AP), `A`=Asset, `M`=Material.
- Time-dependent master data uses `ValidityEndDate = 9999-12-31` for the current record;
  cost-center texts use 2-char language keys (`EN`).
- Open-item aging is measured to the **as-of date** (the latest posting/clearing date in the data),
  not today.

## Scope & limitations
This model uses **only** the six data products listed above. These are not modeled because
those data products don't contain the data:
- opening/closing **GL balances** (only period movements and running totals can be derived)
- **FSV financial statements** and Balance-Sheet/P&L classification
- **credit management**
- **profit-center hierarchy**
- **G/L-account and company-code name masters** (codes only)
- GL budget/plan
- conversion to an arbitrary target currency

In the sample data, the GL/cost-center **functional** currency equals local currency. A true group
currency is only present on cash flow (`global_currency`).

## Troubleshooting
- **`Genie space … table does not exist` on deploy.** The metric views haven't been created yet.
  Run `bundle run fico_semantic_layer` first (see Quickstart step 4).
- **`error downloading Terraform: … openpgp: key expired`.** Point the CLI at a local Terraform:
  `export DATABRICKS_TF_EXEC_PATH=$(which terraform) DATABRICKS_TF_VERSION=$(terraform version -json | jq -r .terraform_version)`.
- **`TABLE_OR_VIEW_NOT_FOUND` in the pipeline.** Check the `source_catalog_*` variables against
  the catalog names of your mounted shares (Catalog Explorer → OpenSharing → Shared with me).
- **Clean up.** `databricks bundle destroy` removes the job, pipeline (and its tables), dashboard
  and Genie spaces. Metric views are created by the job, so drop them with `DROP VIEW`.

## License
© 2026 Databricks, Inc. All rights reserved. The source in this project is provided subject to the
[Databricks License](LICENSE.txt). Referenced third-party libraries are subject to their own licenses:

| Library | Use | License |
|---|---|---|
| [Databricks SDK for Python](https://github.com/databricks/databricks-sdk-py) | deploy scripts (`src/deploy/`) | Apache 2.0 |
| [PySpark](https://github.com/apache/spark) | pipeline transforms | Apache 2.0 |
| [Vega-Lite](https://github.com/vega/vega-lite) | custom dashboard widgets (spec only) | BSD-3-Clause |

SAP, SAP S/4HANA and SAP Business Data Cloud are trademarks or registered trademarks of SAP SE.
This project is not affiliated with or endorsed by SAP SE.
