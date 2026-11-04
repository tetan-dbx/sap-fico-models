"""Silver: journal entry (accounting document) headers — BKPF-style metadata."""

from pyspark import pipelines as dp

from common import get_source


@dp.materialized_view(
    name="silver_journal_header",
    comment="Cleaned accounting document headers: ledger, document type, reversal and posting metadata.",
    cluster_by=["company_code", "posting_date"],
)
@dp.expect_or_drop(
    "valid_keys",
    "company_code IS NOT NULL AND accounting_document IS NOT NULL AND fiscal_year IS NOT NULL",
)
def silver_journal_header():
    return spark.read.table(get_source("journalentry")).selectExpr(
        "CAST(CompanyCode AS STRING) AS company_code",
        "CAST(AccountingDocument AS STRING) AS accounting_document",
        "CAST(FiscalYear AS STRING) AS fiscal_year",
        "NULLIF(TRIM(Ledger), '') AS ledger",
        "NULLIF(TRIM(LedgerGroup), '') AS ledger_group",
        "CAST(AccountingDocumentType AS STRING) AS accounting_document_type",
        "CAST(AccountingDocumentCategory AS STRING) AS accounting_document_category",
        "CAST(TransactionCode AS STRING) AS transaction_code",
        "CAST(AccountingDocCreatedByUser AS STRING) AS created_by_user",
        "CAST(AccountingDocumentHeaderText AS STRING) AS document_header_text",
        "CAST(IsReversal AS BOOLEAN) AS is_reversal",
        "CAST(IsReversed AS BOOLEAN) AS is_reversed",
        "CAST(ReversalReason AS STRING) AS reversal_reason",
        "CAST(TransactionCurrency AS STRING) AS transaction_currency",
        "CAST(IntercompanyTransaction AS STRING) AS intercompany_transaction",
        "CAST(DocumentDate AS DATE) AS document_date",
        "CAST(PostingDate AS DATE) AS posting_date",
        "CAST(AccountingDocumentCreationDate AS DATE) AS creation_date",
        "CAST(FiscalPeriod AS STRING) AS fiscal_period",
    )
