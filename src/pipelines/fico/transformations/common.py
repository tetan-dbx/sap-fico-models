"""Shared configuration and constants for the SAP FICO SDP pipeline.

Source tables are the raw SAP data-product tables shared from SAP Business Data Cloud (BDC)
via Delta Sharing and mounted as catalogs (``sap_shared_*`` by default).
Their fully-qualified names are provided through the pipeline ``configuration`` block
(see resources/fico_pipeline.pipeline.yml) and read here via ``spark.conf.get``.

All conventions below were verified by profiling the actual shared data:
- ``DebitCreditCode`` domain is ``S`` (debit / Soll) and ``H`` (credit / Haben).
- ``AmountInCompanyCodeCurrency`` is already SIGNED (debits positive, credits
  negative), so net movement is a plain SUM and the books net to ~0.
- ``FinancialAccountType`` domain: ``S``=G/L, ``D``=Customer (AR), ``K``=Vendor (AP),
  ``A``=Asset, ``M``=Material.
- Time-dependent master data (cost centers) uses ``ValidityEndDate`` = 9999-12-31 for
  the currently-valid record.
- Cost-center texts use 2-char ISO language keys; ``EN`` is the most complete.
"""

from pyspark.sql import SparkSession


def _spark() -> SparkSession:
    return SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()


def get_source(key: str) -> str:
    """Return the fully-qualified raw source table for ``key`` from pipeline config."""
    return _spark().conf.get(f"source.{key}")


# Currently-valid record sentinel for SAP time-dependent master data.
VALIDITY_CURRENT = "DATE'9999-12-31'"

# Language key used to source cost-center descriptions.
TEXT_LANGUAGE = "EN"

# Map SAP FinancialAccountType -> business description. Applied against a column
# named ``account_type`` (the renamed FinancialAccountType).
ACCOUNT_TYPE_DESC = """
CASE account_type
  WHEN 'S' THEN 'General Ledger'
  WHEN 'D' THEN 'Customer (AR)'
  WHEN 'K' THEN 'Vendor (AP)'
  WHEN 'A' THEN 'Asset'
  WHEN 'M' THEN 'Material'
  ELSE 'Other'
END
"""
