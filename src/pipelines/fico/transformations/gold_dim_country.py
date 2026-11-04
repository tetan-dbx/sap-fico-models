"""Gold: country dimension (pass-through of the cleaned reference data)."""

from pyspark import pipelines as dp


@dp.materialized_view(
    name="gold_dim_country",
    comment="Country/region dimension for geographic reporting.",
    cluster_by=["country"],
)
def dim_country():
    return spark.read.table("silver_country")
