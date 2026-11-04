"""Silver: cost center master, filtered to the currently-valid record."""

from pyspark import pipelines as dp

from common import get_source, VALIDITY_CURRENT


@dp.materialized_view(
    name="silver_cost_center",
    comment="Currently-valid cost center master (ValidityEndDate = 9999-12-31).",
    cluster_by=["controlling_area", "cost_center"],
)
@dp.expect_or_drop(
    "valid_keys", "controlling_area IS NOT NULL AND cost_center IS NOT NULL"
)
def silver_cost_center():
    return (
        spark.read.table(get_source("costcenter"))
        .where(f"ValidityEndDate = {VALIDITY_CURRENT}")
        .selectExpr(
            "CAST(ControllingArea AS STRING) AS controlling_area",
            "CAST(CostCenter AS STRING) AS cost_center",
            "CAST(CompanyCode AS STRING) AS company_code",
            "NULLIF(TRIM(BusinessArea), '') AS business_area",
            "NULLIF(TRIM(ProfitCenter), '') AS profit_center",
            "CAST(CostCenterCategory AS STRING) AS cost_center_category",
            "CAST(Department AS STRING) AS department",
            "CAST(CostCenterCurrency AS STRING) AS cost_center_currency",
            "CAST(CostCtrResponsiblePersonName AS STRING) AS responsible_person",
            "CAST(CostCtrResponsibleUser AS STRING) AS responsible_user",
            "NULLIF(TRIM(FunctionalArea), '') AS functional_area",
            "CAST(Country AS STRING) AS country",
            "NULLIF(TRIM(Plant), '') AS plant",
            "CAST(IsStatisticalCostCenter AS BOOLEAN) AS is_statistical",
            "CAST(ValidityStartDate AS DATE) AS validity_start_date",
            "CAST(ValidityEndDate AS DATE) AS validity_end_date",
        )
    )
