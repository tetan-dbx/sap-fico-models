"""Gold: cost center dimension — master + name + flattened standard-hierarchy rollup path.

The hierarchy path lets the metric view roll up cost-center spend to any level. For
each cost center we pick its deepest (most specific) leaf assignment, walk up the
parent chain within that hierarchy, and flatten the ancestor node at each level into
`hier_level_0..5` (0 = top / group level). Kept at 1 row per cost center (no fan-out).
"""

from pyspark import pipelines as dp
from pyspark.sql import Window
from pyspark.sql import functions as F

MAX_LEVEL = 6  # observed cost-center hierarchy levels: 0..5


@dp.materialized_view(
    name="gold_dim_cost_center",
    comment="Cost center dimension: master attributes, name, and flattened standard-hierarchy rollup path (grain: controlling_area + cost_center).",
    cluster_by=["controlling_area", "cost_center"],
)
def gold_dim_cost_center():
    nodes = spark.read.table("silver_cost_center_hier_node")

    # Deepest (most specific) leaf assignment per cost center, and the hierarchy it belongs to.
    leaf_win = Window.partitionBy("controlling_area", "cost_center").orderBy(
        F.col("hierarchy_node_level").desc_nulls_last())
    chosen = (
        nodes.where("cost_center IS NOT NULL")
        .withColumn("_rn", F.row_number().over(leaf_win)).where("_rn = 1")
        .select("controlling_area", "cost_center",
                F.col("cost_center_hierarchy").alias("hier"),
                F.col("hierarchy_node").alias("anode"))
    )

    edges = nodes.select(
        F.col("controlling_area").alias("e_ca"),
        F.col("cost_center_hierarchy").alias("e_hier"),
        F.col("hierarchy_node").alias("e_child"),
        F.col("parent_node").alias("e_parent"),
    )

    # Walk up the parent chain within the chosen hierarchy, collecting ancestor nodes.
    acc = chosen
    cur = chosen
    for _ in range(MAX_LEVEL):
        cur = (
            cur.join(
                edges,
                (cur["controlling_area"] == edges["e_ca"])
                & (cur["hier"] == edges["e_hier"])
                & (cur["anode"] == edges["e_child"]),
                "inner",
            )
            .select("controlling_area", "cost_center", "hier", F.col("e_parent").alias("anode"))
            .where("anode IS NOT NULL AND anode <> ''")
        )
        acc = acc.unionByName(cur)
    acc = acc.dropDuplicates(["controlling_area", "cost_center", "hier", "anode"])

    lvl = nodes.select(
        F.col("controlling_area").alias("l_ca"),
        F.col("cost_center_hierarchy").alias("l_hier"),
        F.col("hierarchy_node").alias("l_node"),
        F.col("hierarchy_node_level").alias("l_level"),
    )
    flat = acc.join(
        lvl,
        (acc["controlling_area"] == lvl["l_ca"])
        & (acc["hier"] == lvl["l_hier"])
        & (acc["anode"] == lvl["l_node"]),
        "left",
    )
    levels = flat.groupBy("controlling_area", "cost_center").agg(
        *[F.max(F.when(F.col("l_level") == k, F.col("anode"))).alias(f"hier_level_{k}") for k in range(MAX_LEVEL)],
        F.first("hier", ignorenulls=True).alias("cost_center_hierarchy_id"),
    )

    # Deepest node retained for reference.
    node = (
        nodes.where("cost_center IS NOT NULL")
        .withColumn("_rn", F.row_number().over(leaf_win)).where("_rn = 1")
        .select("controlling_area", "cost_center", "hierarchy_node", "hierarchy_node_level")
    )

    text = spark.read.table("silver_cost_center_text").select(
        "controlling_area", "cost_center", "cost_center_name", "cost_center_description")

    return (
        spark.read.table("silver_cost_center")
        .join(text, ["controlling_area", "cost_center"], "left")
        .join(node, ["controlling_area", "cost_center"], "left")
        .join(levels, ["controlling_area", "cost_center"], "left")
        .selectExpr(
            "controlling_area", "cost_center", "cost_center_name", "cost_center_description",
            "company_code", "profit_center", "business_area", "cost_center_category", "department",
            "functional_area", "country", "plant", "cost_center_currency", "responsible_person", "is_statistical",
            "cost_center_hierarchy_id", "hierarchy_node", "hierarchy_node_level",
            *[f"hier_level_{k}" for k in range(MAX_LEVEL)],
        )
    )
