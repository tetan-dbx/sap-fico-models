"""Silver: supplier withholding-tax settings (AP / tax compliance)."""

from pyspark import pipelines as dp

from common import get_source


@dp.materialized_view(
    name="silver_supplier_wht",
    comment="Supplier withholding-tax configuration (grain: supplier + company code + WHT type).",
    cluster_by=["supplier"],
)
@dp.expect_or_drop(
    "valid_keys",
    "supplier IS NOT NULL AND company_code IS NOT NULL AND withholding_tax_type IS NOT NULL",
)
def silver_supplier_wht():
    return spark.read.table(get_source("supplierwithholdingtax")).selectExpr(
        "CAST(Supplier AS STRING) AS supplier",
        "CAST(CompanyCode AS STRING) AS company_code",
        "CAST(WithholdingTaxType AS STRING) AS withholding_tax_type",
        "CAST(WithholdingTaxCode AS STRING) AS withholding_tax_code",
        "CAST(IsWithholdingTaxSubject AS BOOLEAN) AS is_withholding_tax_subject",
        "CAST(RecipientType AS STRING) AS recipient_type",
        "CAST(WithholdingTaxExmptPercent AS DECIMAL(5,2)) AS wht_exempt_percent",
        "CAST(ExemptionReason AS STRING) AS exemption_reason",
    )
