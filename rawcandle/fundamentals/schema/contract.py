from __future__ import annotations


V4_CANONICAL_FINANCIAL_FIELDS: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "operating_income",
    "ebit",
    "ebitda",
    "net_income",
    "net_income_common",
    "operating_cashflow",
    "capex",
    "free_cashflow",
    "cash",
    "total_debt",
    "shares_outstanding",
    "accounts_receivable",
    "inventory",
    "accounts_payable",
    "deferred_revenue",
    "total_assets",
)

SHARADAR_ARQ_FIELD_MAPPING: dict[str, str] = {
    "revenue": "revenue",
    "gross_profit": "gp",
    "operating_income": "opinc",
    "ebit": "ebit",
    "ebitda": "ebitda",
    "net_income": "netinc",
    "net_income_common": "netinccmn",
    "operating_cashflow": "ncfo",
    "capex": "capex",
    "free_cashflow": "fcf",
    "cash": "cashneq",
    "total_debt": "debt",
    "shares_outstanding": "sharesbas",
    "accounts_receivable": "receivables",
    "inventory": "inventory",
    "accounts_payable": "payables",
    "deferred_revenue": "deferredrev",
    "total_assets": "assets",
}

SHARADAR_SUPPORT_FIELDS: tuple[str, ...] = (
    "debtc",
    "debtnc",
    "shareswa",
    "shareswadil",
    "calendardate",
    "reportperiod",
    "fiscalperiod",
    "date",
    "lastupdated",
)

PROVIDER_NAMES: tuple[str, ...] = ("SHARADAR", "YAHOO", "SEC", "MIGRATED_FROM_V3")

SCHEMA_VERSION = "v4_6a2_operating_working_capital"
