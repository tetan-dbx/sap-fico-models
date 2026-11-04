"""Silver: supplier (vendor) master — the AP business-partner dimension source."""

from pyspark import pipelines as dp

from common import get_source


@dp.materialized_view(
    name="silver_supplier",
    comment="Cleaned supplier master attributes (grain: supplier).",
    cluster_by=["supplier"],
)
@dp.expect_or_drop("valid_supplier", "supplier IS NOT NULL")
def silver_supplier():
    return spark.read.table(get_source("supplier")).selectExpr(
        "CAST(Supplier AS STRING) AS supplier",
        "CAST(SupplierName AS STRING) AS supplier_name",
        "CAST(SupplierFullName AS STRING) AS supplier_full_name",
        "CAST(SupplierAccountGroup AS STRING) AS account_group",
        "CAST(Country AS STRING) AS country",
        "CAST(Region AS STRING) AS region",
        "CAST(CityName AS STRING) AS city_name",
        "CAST(Industry AS STRING) AS industry",
        "CAST(IsOneTimeAccount AS BOOLEAN) AS is_one_time_account",
        "CAST(VATRegistration AS STRING) AS vat_registration",
        "CAST(PaymentIsBlockedForSupplier AS BOOLEAN) AS payment_is_blocked",
        "CAST(PostingIsBlocked AS BOOLEAN) AS posting_is_blocked",
        "CAST(PurchasingIsBlocked AS BOOLEAN) AS purchasing_is_blocked",
        "CAST(DeletionIndicator AS BOOLEAN) AS deletion_indicator",
        "NULLIF(TRIM(TradingPartner), '') AS trading_partner",
    )
