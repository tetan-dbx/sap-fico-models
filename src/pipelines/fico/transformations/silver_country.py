"""Silver: country/region reference data."""

from pyspark import pipelines as dp

from common import get_source


@dp.materialized_view(
    name="silver_country",
    comment="Country/region reference data (ISO codes, EU membership, reporting currency).",
    cluster_by=["country"],
)
@dp.expect_or_drop("valid_country", "country IS NOT NULL")
def silver_country():
    return spark.read.table(get_source("country")).selectExpr(
        "CAST(Country AS STRING) AS country",
        "CAST(CountryISOCode AS STRING) AS country_iso_code",
        "CAST(CountryThreeLetterISOCode AS STRING) AS country_three_letter_iso",
        "CAST(IsEuropeanUnionMember AS BOOLEAN) AS is_eu_member",
        "CAST(CountryCurrency AS STRING) AS country_currency",
        "CAST(TaxCalculationProcedure AS STRING) AS tax_calculation_procedure",
    )
