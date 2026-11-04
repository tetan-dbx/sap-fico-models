"""Silver: cost center descriptions, currently-valid and in the chosen language."""

from pyspark import pipelines as dp

from common import get_source, VALIDITY_CURRENT, TEXT_LANGUAGE


@dp.materialized_view(
    name="silver_cost_center_text",
    comment="Currently-valid cost center names/descriptions in the configured language.",
    cluster_by=["controlling_area", "cost_center"],
)
@dp.expect_or_drop(
    "valid_keys", "controlling_area IS NOT NULL AND cost_center IS NOT NULL"
)
def silver_cost_center_text():
    return (
        spark.read.table(get_source("costcentertext"))
        .where(f"ValidityEndDate = {VALIDITY_CURRENT} AND Language = '{TEXT_LANGUAGE}'")
        .selectExpr(
            "CAST(ControllingArea AS STRING) AS controlling_area",
            "CAST(CostCenter AS STRING) AS cost_center",
            "CAST(CostCenterName AS STRING) AS cost_center_name",
            "CAST(CostCenterDescription AS STRING) AS cost_center_description",
        )
    )
