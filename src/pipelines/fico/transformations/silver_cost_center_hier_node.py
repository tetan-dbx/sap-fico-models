"""Silver: cost center standard-hierarchy nodes, currently-valid."""

from pyspark import pipelines as dp

from common import get_source, VALIDITY_CURRENT


@dp.materialized_view(
    name="silver_cost_center_hier_node",
    comment="Currently-valid cost center hierarchy nodes (node, parent, level, assigned cost center).",
    cluster_by=["controlling_area", "cost_center_hierarchy"],
)
@dp.expect_or_drop(
    "valid_keys", "controlling_area IS NOT NULL AND hierarchy_node IS NOT NULL"
)
def silver_cost_center_hier_node():
    return (
        spark.read.table(get_source("costcenterhierarchynode"))
        .where(f"ValidityEndDate = {VALIDITY_CURRENT}")
        .selectExpr(
            "CAST(ControllingArea AS STRING) AS controlling_area",
            "CAST(CostCenterHierarchy AS STRING) AS cost_center_hierarchy",
            "CAST(HierarchyNode AS STRING) AS hierarchy_node",
            "CAST(ParentNode AS STRING) AS parent_node",
            "CAST(HierarchyNodeLevel AS INT) AS hierarchy_node_level",
            "NULLIF(TRIM(CostCenter), '') AS cost_center",
            "CAST(NodeType AS STRING) AS node_type",
        )
    )
