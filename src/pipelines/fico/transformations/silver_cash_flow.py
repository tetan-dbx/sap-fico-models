"""Silver: cash liquidity flows — actual and forecast unioned with a scenario flag."""

from pyspark import pipelines as dp

from common import get_source

# Columns common to both the actual and forecast cash-flow sources.
_COMMON = [
    "CAST(CashFlowID AS STRING) AS cash_flow_id",
    "CAST(CompanyCode AS STRING) AS company_code",
    "CAST(TransactionDate AS DATE) AS transaction_date",
    "CAST(PostingDate AS DATE) AS posting_date",
    "CAST(TransactionCurrency AS STRING) AS transaction_currency",
    "CAST(AmountInTransactionCurrency AS DECIMAL(34,4)) AS amount_in_transaction_currency",
    "CAST(CompanyCodeCurrency AS STRING) AS company_code_currency",
    "CAST(AmountInCompanyCodeCurrency AS DECIMAL(34,4)) AS amount_in_cc_currency",
    "CAST(GlobalCurrency AS STRING) AS global_currency",
    "CAST(AmountInGlobalCurrency AS DECIMAL(34,4)) AS amount_in_global_currency",
    "CAST(BankAccountInternalID AS STRING) AS bank_account_internal_id",
]


@dp.materialized_view(
    name="silver_cash_flow",
    comment="Cash liquidity flows for working-capital insight; actual + forecast with scenario flag.",
    cluster_by=["company_code", "posting_date"],
)
@dp.expect_or_drop("valid_company", "company_code IS NOT NULL")
@dp.expect_or_drop("amount_present", "amount_in_cc_currency IS NOT NULL")
@dp.expect("scenario_domain", "scenario IN ('actual','forecast')")
def silver_cash_flow():
    actual = spark.read.table(get_source("cashflow")).selectExpr(
        *_COMMON,
        "NULLIF(TRIM(Bank), '') AS bank",
        "CAST(BankName AS STRING) AS bank_name",
        "CAST(BankCountry AS STRING) AS bank_country",
        "'actual' AS scenario",
    )
    forecast = spark.read.table(get_source("cashflowforecast")).selectExpr(
        *_COMMON,
        "CAST(NULL AS STRING) AS bank",
        "CAST(NULL AS STRING) AS bank_name",
        "CAST(NULL AS STRING) AS bank_country",
        "'forecast' AS scenario",
    )
    return actual.unionByName(forecast)
