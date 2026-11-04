"""Gold: journal line fact — accounting document items enriched with header metadata.

This is the core FICO fact. Amounts follow the verified SAP convention that
``amount_in_cc_currency`` is signed (debit positive, credit negative):
    net_amount   = signed amount
    debit_amount = amount where DebitCreditCode = 'S' (>= 0)
    credit_amount = -amount where DebitCreditCode = 'H' (>= 0)
so that net_amount = debit_amount - credit_amount.
"""

from pyspark import pipelines as dp

from common import ACCOUNT_TYPE_DESC


@dp.materialized_view(
    name="gold_fact_journal_line",
    comment="Journal line fact (G/L, cost center, profit center) with debit/credit/net amounts and header context.",
    cluster_by=["company_code", "posting_date"],
)
def fact_journal_line():
    # Drop header columns that duplicate item-level ones; the line item wins.
    header = spark.read.table("silver_journal_header").drop(
        "posting_date", "document_date", "fiscal_period"
    )
    items = spark.read.table("silver_acctg_doc_item")

    return items.join(
        header, ["company_code", "accounting_document", "fiscal_year"], "left"
    ).selectExpr(
        "*",
        "date_trunc('MONTH', posting_date) AS posting_month",
        "year(posting_date) AS posting_year",
        "CASE WHEN CAST(fiscal_period AS INT) BETWEEN 1 AND 12 "
        "     THEN concat('Q', CAST(CEIL(CAST(fiscal_period AS INT) / 3.0) AS INT)) "
        "     ELSE 'Special' END AS fiscal_quarter",
        f"{ACCOUNT_TYPE_DESC} AS account_type_desc",
        "CASE WHEN debit_credit_code = 'S' THEN amount_in_cc_currency ELSE 0 END AS debit_amount",
        "CASE WHEN debit_credit_code = 'H' THEN -amount_in_cc_currency ELSE 0 END AS credit_amount",
        "amount_in_cc_currency AS net_amount",
        "datediff(creation_date, posting_date) AS entry_lag_days",
        "concat_ws('|', company_code, fiscal_year, accounting_document) AS document_key",
    )
