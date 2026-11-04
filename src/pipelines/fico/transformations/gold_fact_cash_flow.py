"""Gold: cash flow fact — actual and forecast liquidity flows with inflow/outflow split."""

from pyspark import pipelines as dp


@dp.materialized_view(
    name="gold_fact_cash_flow",
    comment="Cash flow fact (actual + forecast) with inflow/outflow/net amounts in company-code currency.",
    cluster_by=["company_code", "posting_date"],
)
def fact_cash_flow():
    return spark.read.table("silver_cash_flow").selectExpr(
        "*",
        "date_trunc('MONTH', posting_date) AS flow_month",
        "CASE WHEN amount_in_cc_currency > 0 THEN amount_in_cc_currency ELSE 0 END AS cash_in_cc",
        "CASE WHEN amount_in_cc_currency < 0 THEN -amount_in_cc_currency ELSE 0 END AS cash_out_cc",
        "amount_in_cc_currency AS net_amount_cc",
    )
