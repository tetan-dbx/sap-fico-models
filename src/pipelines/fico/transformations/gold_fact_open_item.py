"""Gold: AR/AP open-item fact — receivables/payables with aging and clearing signals.

Built from open-item-managed customer (AR, account_type 'D') and vendor
(AP, account_type 'K') line items. An item is open while it has no clearing
date; days-to-clear on cleared items feeds DSO/DPO analysis.

Aging of open items is measured against an **as-of snapshot date** = the latest
date present in the AR/AP data, not the calendar's ``current_date()``. This is a
static / delta-shared dataset, so anchoring to "today" would make every historical
item read as long overdue and collapse the aging into a single bucket. The as-of
date is carried on every row (``as_of_date``) for transparency.
"""

from pyspark import pipelines as dp


@dp.materialized_view(
    name="gold_fact_open_item",
    comment="AR/AP open items and aging derived from open-item-managed customer/vendor line items. Aging is anchored to an as-of snapshot date (latest date in the data), not current_date().",
    cluster_by=["company_code", "ar_ap"],
)
@dp.expect("ar_ap_only", "ar_ap IN ('AR','AP')")
def fact_open_item():
    base = spark.read.table("silver_acctg_doc_item").where(
        "is_open_item_managed = true AND account_type IN ('D','K')"
    )
    # As-of snapshot = latest date present in the AR/AP data. Aging/overdue are
    # measured against this, not today's date (see module docstring).
    as_of = base.selectExpr(
        "max(greatest(posting_date, coalesce(clearing_date, posting_date))) AS as_of_date"
    )
    return base.crossJoin(as_of).selectExpr(
        "company_code",
        "accounting_document",
        "fiscal_year",
        "accounting_document_item",
        "account_type",
        "CASE account_type WHEN 'D' THEN 'AR' WHEN 'K' THEN 'AP' END AS ar_ap",
        "CASE account_type WHEN 'D' THEN 'Customer (AR)' WHEN 'K' THEN 'Vendor (AP)' END AS account_type_desc",
        "gl_account",
        "customer",
        "supplier",
        "posting_date",
        "document_date",
        "clearing_date",
        "net_payment_days",
        "company_code_currency",
        "amount_in_cc_currency",
        "payment_terms",
        "date_trunc('MONTH', posting_date) AS posting_month",
        "as_of_date",
        "(clearing_date IS NULL) AS is_open",
        "CASE WHEN clearing_date IS NOT NULL THEN datediff(clearing_date, posting_date) END AS days_to_clear",
        "CASE WHEN clearing_date IS NULL THEN datediff(as_of_date, posting_date) END AS days_open",
        "CASE WHEN clearing_date IS NULL THEN amount_in_cc_currency ELSE 0 END AS open_amount",
        "CASE "
        "  WHEN clearing_date IS NOT NULL THEN 'Cleared' "
        "  WHEN datediff(as_of_date, posting_date) <= 30 THEN '1: 0-30' "
        "  WHEN datediff(as_of_date, posting_date) <= 60 THEN '2: 31-60' "
        "  WHEN datediff(as_of_date, posting_date) <= 90 THEN '3: 61-90' "
        "  WHEN datediff(as_of_date, posting_date) <= 180 THEN '4: 91-180' "
        "  WHEN datediff(as_of_date, posting_date) <= 365 THEN '5: 181-365' "
        "  ELSE '6: 365+' END AS aging_bucket",
    )
