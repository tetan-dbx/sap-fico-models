"""Carry source column comments to the silver/gold tables (idempotent).

Runs as a bundle job task after the pipeline so the comments survive full
refreshes (SDP re-materialization can reset column-level metadata). For every
silver/gold column it:
  * carries the VERBATIM comment from the originating sap_shared source column
    (resolved through the rename lineage parsed from the transform files), or
  * applies an accurate authored description for columns we derive, or
  * leaves it empty when neither is known (never invents a comment).

Metric-view column comments come from the YAML dimension/measure definitions and
are handled by deploy_metric_views.py, so they are not touched here.
"""

import argparse
import pathlib
import re

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

# Source tables are NOT hard-coded here: they are read from the deployed pipeline's
# `configuration` block (keys `source.<key>` -> `catalog.schema.table`), which is the
# single source of truth (see resources/fico_pipeline.pipeline.yml).
SOURCE_PREFIX = "source."

# Columns we compute (no single source column) -> accurate authored comments.
DERIVED = {
    "posting_month": "Calendar month of the posting date (month start).",
    "posting_year": "Calendar year of the posting date.",
    "fiscal_quarter": "Fiscal quarter derived from the fiscal period; special periods flagged as 'Special'.",
    "account_type_desc": "Financial account type description (General Ledger, Customer (AR), Vendor (AP), Asset, Material).",
    "debit_amount": "Debit (Soll) amount in company-code currency; 0 for credit lines.",
    "credit_amount": "Credit (Haben) amount in company-code currency shown positive; 0 for debit lines.",
    "net_amount": "Signed net posting amount in company-code currency (debit minus credit).",
    "entry_lag_days": "Days between posting date and document entry (creation) date.",
    "document_key": "Composite accounting document key: company_code|fiscal_year|accounting_document.",
    "flow_month": "Calendar month of the cash-flow posting date (month start).",
    "cash_in_cc": "Cash inflow in company-code currency (positive amounts; 0 otherwise).",
    "cash_out_cc": "Cash outflow in company-code currency shown positive (negative amounts; 0 otherwise).",
    "net_amount_cc": "Signed net cash flow in company-code currency.",
    "scenario": "Cash-flow scenario: 'actual' or 'forecast'.",
    "ar_ap": "Receivable (AR) for customer items or Payable (AP) for vendor items.",
    "is_open": "Whether the item is currently open (no clearing date).",
    "days_to_clear": "Days from posting to clearing on cleared items (null while open).",
    "days_open": "Days the item has been open as of the as-of snapshot date (null once cleared).",
    "open_amount": "Open (uncleared) amount in company-code currency; 0 once cleared.",
    "aging_bucket": "Aging band for open items, aged to the as-of snapshot date "
                    "('1: 0-30', '2: 31-60', '3: 61-90', '4: 91-180', '5: 181-365', '6: 365+') or 'Cleared'.",
    "is_withholding_tax_subject": "Whether the supplier is subject to withholding tax in any company code.",
    "cost_center_hierarchy_id": "Standard cost-center hierarchy the rollup path is taken from.",
    "hier_level_0": "Ancestor hierarchy node at level 0 (top / group level).",
    "hier_level_1": "Ancestor hierarchy node at level 1.",
    "hier_level_2": "Ancestor hierarchy node at level 2.",
    "hier_level_3": "Ancestor hierarchy node at level 3.",
    "hier_level_4": "Ancestor hierarchy node at level 4.",
    "hier_level_5": "Ancestor hierarchy node at level 5 (most specific).",
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--transformations_dir", required=True)
    p.add_argument("--pipeline_id", required=True,
                   help="SDP pipeline whose `configuration` lists the source.<key> tables.")
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--warehouse_id", required=True)
    return p.parse_args()


def run_sql(w, wid, q):
    r = w.statement_execution.execute_statement(warehouse_id=wid, statement=q, wait_timeout="50s")
    state = r.status.state if r.status else None
    while state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
        state = r.status.state if r.status else None
    if state != StatementState.SUCCEEDED:
        msg = r.status.error.message if (r.status and r.status.error) else state
        raise RuntimeError(f"SQL failed ({state}): {msg}\n{q[:200]}")
    return list(r.result.data_array) if (r.result and r.result.data_array) else []


def load_sources(w, pipeline_id):
    """source key -> (catalog, schema, table), from the pipeline's configuration."""
    spec = w.pipelines.get(pipeline_id).spec
    conf = (spec.configuration if spec else None) or {}
    sources = {}
    for k, v in conf.items():
        if not k.startswith(SOURCE_PREFIX):
            continue
        parts = [p.strip("`") for p in v.split(".")]
        if len(parts) != 3:
            raise ValueError(f"pipeline configuration {k}={v!r} is not a catalog.schema.table name")
        sources[k[len(SOURCE_PREFIX):]] = tuple(parts)
    if not sources:
        raise RuntimeError(f"pipeline {pipeline_id} has no '{SOURCE_PREFIX}*' configuration entries")
    return sources


def fetch_source_comments(w, wid, sources):
    by_cat = {}
    for key, (cat, sch, tbl) in sources.items():
        by_cat.setdefault(cat, set()).add((sch, tbl))
    out = {}
    for cat, pairs in by_cat.items():
        cond = " OR ".join(f"(table_schema = '{s}' AND table_name = '{t}')" for s, t in sorted(pairs))
        rows = run_sql(w, wid, f"SELECT table_schema, table_name, column_name, comment "
                              f"FROM `{cat}`.information_schema.columns WHERE {cond}")
        for sname, tname, cname, comment in rows:
            for key, (c, s, t) in sources.items():
                if c == cat and s == sname and t == tname:
                    out.setdefault(key, {})[str(cname).upper()] = (comment or "").strip()
    return out


def parse_lineage(tx_dir, src_comments):
    """business_col -> verbatim source comment, via selectExpr rename lineage."""
    mapping = {}
    for f in sorted(pathlib.Path(tx_dir).glob("silver_*.py")):
        text = f.read_text()
        pool = {}
        for k in re.findall(r'get_source\("(\w+)"\)', text):
            pool.update(src_comments.get(k, {}))
        for lit in re.findall(r'"([^"]*\bAS\b[^"]*)"', text):
            if " AS " not in lit:
                continue
            expr, target = lit.rsplit(" AS ", 1)
            target = target.strip()
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", target):
                continue
            toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr)
            matched = {t.upper() for t in toks if t.upper() in pool}
            if len(matched) == 1:
                cmt = pool[next(iter(matched))]
                if cmt and target not in mapping:
                    mapping[target] = cmt
    return mapping


def esc(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


def main():
    args = parse_args()
    w = WorkspaceClient()
    sources = load_sources(w, args.pipeline_id)
    print(f"Source tables from pipeline {args.pipeline_id}: "
          + ", ".join(".".join(v) for v in sources.values()))
    src = fetch_source_comments(w, args.warehouse_id, sources)
    canon = parse_lineage(args.transformations_dir, src)
    for k, v in DERIVED.items():
        canon.setdefault(k, v)

    rows = run_sql(w, args.warehouse_id,
                   f"SELECT table_name, column_name FROM {args.catalog}.information_schema.columns "
                   f"WHERE table_schema='{args.schema}' AND (table_name LIKE 'silver_%' OR table_name LIKE 'gold_%') "
                   f"ORDER BY table_name, ordinal_position")
    applied, skipped = 0, 0
    for tname, cname in rows:
        cmt = canon.get(cname)
        if not cmt:
            skipped += 1
            continue
        run_sql(w, args.warehouse_id,
                f"COMMENT ON COLUMN `{args.catalog}`.`{args.schema}`.`{tname}`.`{cname}` IS '{esc(cmt)}'")
        applied += 1
    print(f"Applied {applied} column comments ({skipped} left empty: no source comment, not derived).")


if __name__ == "__main__":
    main()
