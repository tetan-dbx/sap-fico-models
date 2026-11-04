"""Gold: supplier dimension — master attributes + withholding-tax-subject flag."""

from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.materialized_view(
    name="gold_dim_supplier",
    comment="Supplier dimension (grain: supplier) with a withholding-tax-subject flag for AP analytics.",
    cluster_by=["supplier"],
)
def dim_supplier():
    wht = (
        spark.read.table("silver_supplier_wht")
        .where("is_withholding_tax_subject = true")
        .select("supplier")
        .distinct()
        .withColumn("is_withholding_tax_subject", F.lit(True))
    )
    return (
        spark.read.table("silver_supplier")
        .join(wht, ["supplier"], "left")
        .withColumn(
            "is_withholding_tax_subject",
            F.coalesce(F.col("is_withholding_tax_subject"), F.lit(False)),
        )
    )
