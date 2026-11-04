"""Silver: operational accounting document line items (the FICO transaction grain)."""

from pyspark import pipelines as dp

from common import get_source


@dp.materialized_view(
    name="silver_acctg_doc_item",
    comment="Cleaned, typed accounting document line items from the SAP entry-view journal.",
    cluster_by=["company_code", "posting_date"],
)
@dp.expect_or_drop(
    "valid_keys",
    "company_code IS NOT NULL AND accounting_document IS NOT NULL "
    "AND fiscal_year IS NOT NULL AND accounting_document_item IS NOT NULL",
)
@dp.expect_or_drop("valid_posting_date", "posting_date IS NOT NULL")
@dp.expect_or_drop("amount_present", "amount_in_cc_currency IS NOT NULL")
@dp.expect("debit_credit_domain", "debit_credit_code IN ('S','H')")
@dp.expect("account_type_domain", "account_type IN ('S','D','K','A','M')")
def silver_acctg_doc_item():
    return spark.read.table(get_source("operationalacctgdocitem")).selectExpr(
        "CAST(CompanyCode AS STRING) AS company_code",
        "CAST(AccountingDocument AS STRING) AS accounting_document",
        "CAST(FiscalYear AS STRING) AS fiscal_year",
        "CAST(AccountingDocumentItem AS STRING) AS accounting_document_item",
        "CAST(FiscalPeriod AS STRING) AS fiscal_period",
        "CAST(PostingDate AS DATE) AS posting_date",
        "CAST(DocumentDate AS DATE) AS document_date",
        "CAST(ValueDate AS DATE) AS value_date",
        "CAST(ClearingDate AS DATE) AS clearing_date",
        "CAST(ChartOfAccounts AS STRING) AS chart_of_accounts",
        "CAST(GLAccount AS STRING) AS gl_account",
        "CAST(FinancialAccountType AS STRING) AS account_type",
        "CAST(DebitCreditCode AS STRING) AS debit_credit_code",
        "CAST(PostingKey AS STRING) AS posting_key",
        "NULLIF(TRIM(CostCenter), '') AS cost_center",
        "NULLIF(TRIM(ProfitCenter), '') AS profit_center",
        "NULLIF(TRIM(ControllingArea), '') AS controlling_area",
        "NULLIF(TRIM(BusinessArea), '') AS business_area",
        "NULLIF(TRIM(Segment), '') AS segment",
        "NULLIF(TRIM(PartnerCompany), '') AS partner_company",
        "NULLIF(TRIM(PartnerSegment), '') AS partner_segment",
        "NULLIF(TRIM(PartnerBusinessArea), '') AS partner_business_area",
        "CAST(CompanyCodeCurrency AS STRING) AS company_code_currency",
        "CAST(AmountInCompanyCodeCurrency AS DECIMAL(34,4)) AS amount_in_cc_currency",
        "CAST(FunctionalCurrency AS STRING) AS functional_currency",
        "CAST(AmountInFunctionalCurrency AS DECIMAL(34,4)) AS amount_in_functional_currency",
        "CAST(TaxAmountInCoCodeCrcy AS DECIMAL(34,4)) AS tax_amount_cc",
        "CAST(IsOpenItemManaged AS BOOLEAN) AS is_open_item_managed",
        "NULLIF(TRIM(Customer), '') AS customer",
        "NULLIF(TRIM(Supplier), '') AS supplier",
        "NULLIF(TRIM(Material), '') AS material",
        "NULLIF(TRIM(CostElement), '') AS cost_element",
        "NULLIF(TRIM(TaxCode), '') AS tax_code",
        "CAST(PaymentTerms AS STRING) AS payment_terms",
        "CAST(NetPaymentDays AS INT) AS net_payment_days",
        "CAST(PaymentMethod AS STRING) AS payment_method",
        "CAST(WithholdingTaxCode AS STRING) AS withholding_tax_code",
        "CAST(AssignmentReference AS STRING) AS assignment_reference",
        "CAST(DocumentItemText AS STRING) AS document_item_text",
    )
