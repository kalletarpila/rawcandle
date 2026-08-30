from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.fundamentals.schema.contract import SCHEMA_VERSION, V4_CANONICAL_FINANCIAL_FIELDS


PROVIDER_SCHEMA_SQL = """
CREATE TABLE schema_version (
    db_name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE provider_run (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('SHARADAR','YAHOO','SEC','MIGRATED_FROM_V3')),
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    status TEXT NOT NULL,
    request_scope TEXT NOT NULL,
    entitlement_scope TEXT,
    source_version TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE provider_observation (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES provider_run(run_id),
    provider TEXT NOT NULL CHECK (provider IN ('SHARADAR','YAHOO','SEC','MIGRATED_FROM_V3')),
    provider_record_key TEXT NOT NULL,
    company_id INTEGER,
    security_id INTEGER,
    provider_ticker TEXT,
    provider_security_id TEXT,
    native_table TEXT NOT NULL,
    dimension TEXT,
    calendardate TEXT,
    reportperiod TEXT,
    fiscalperiod TEXT,
    source_availability_date TEXT,
    observed_at_utc TEXT,
    fetched_at_utc TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    provider_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(provider, native_table, provider_record_key, content_hash)
);

CREATE TABLE sharadar_fundamental_observation (
    observation_id TEXT PRIMARY KEY REFERENCES provider_observation(observation_id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    permaticker TEXT,
    dimension TEXT NOT NULL CHECK (dimension IN ('ARQ','MRQ','ART','MRT','ARY','MRY')),
    calendardate TEXT,
    reportperiod TEXT NOT NULL,
    fiscalperiod TEXT,
    date TEXT,
    lastupdated TEXT,
    revenue INTEGER,
    gp INTEGER,
    opinc INTEGER,
    ebit INTEGER,
    ebitda INTEGER,
    netinc INTEGER,
    ncfo INTEGER,
    capex INTEGER,
    fcf INTEGER,
    cashneq INTEGER,
    debt INTEGER,
    debtc INTEGER,
    debtnc INTEGER,
    sharesbas INTEGER,
    shareswa INTEGER,
    shareswadil INTEGER
);

CREATE INDEX idx_provider_observation_provider_ticker ON provider_observation(provider, provider_ticker);
CREATE INDEX idx_provider_observation_period ON provider_observation(provider_ticker, dimension, reportperiod, fiscalperiod);
CREATE INDEX idx_sharadar_fundamental_period ON sharadar_fundamental_observation(ticker, dimension, reportperiod, fiscalperiod);
"""


CANONICAL_SCHEMA_SQL = """
CREATE TABLE schema_version (
    db_name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE company (
    company_id INTEGER PRIMARY KEY,
    company_key TEXT NOT NULL UNIQUE,
    company_name TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE security (
    security_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    current_ticker TEXT NOT NULL,
    exchange TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    valid_from TEXT,
    valid_to TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(current_ticker)
);

CREATE TABLE ticker_alias (
    alias_id INTEGER PRIMARY KEY,
    security_id INTEGER NOT NULL REFERENCES security(security_id),
    ticker TEXT NOT NULL,
    provider TEXT,
    valid_from TEXT,
    valid_to TEXT,
    source TEXT NOT NULL,
    UNIQUE(security_id, ticker, provider, valid_from)
);

CREATE TABLE provider_security_identity (
    provider TEXT NOT NULL,
    provider_security_id TEXT NOT NULL,
    security_id INTEGER NOT NULL REFERENCES security(security_id),
    provider_ticker TEXT,
    source TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(provider, provider_security_id)
);

CREATE TABLE company_cik (
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    cik_normalized TEXT NOT NULL,
    cik_display TEXT NOT NULL,
    source TEXT NOT NULL,
    source_table TEXT,
    source_row_id TEXT,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(company_id, cik_normalized)
);

CREATE TABLE v4_quarter (
    quarter_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    period_end TEXT NOT NULL,
    source_fiscalperiod TEXT NOT NULL,
    source_reportperiod TEXT NOT NULL,
    identity_provider TEXT NOT NULL,
    identity_status TEXT NOT NULL,
    source_availability_date TEXT,
    first_public_result_date TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(company_id, fiscal_year, fiscal_quarter)
);

CREATE TABLE v4_quarter_financials (
    quarter_id INTEGER PRIMARY KEY REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    revenue INTEGER,
    gross_profit INTEGER,
    operating_income INTEGER,
    ebit INTEGER,
    ebitda INTEGER,
    net_income INTEGER,
    operating_cashflow INTEGER,
    capex INTEGER,
    free_cashflow INTEGER,
    cash INTEGER,
    total_debt INTEGER,
    shares_outstanding INTEGER,
    canonical_source_policy TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE v4_field_provenance (
    provenance_id INTEGER PRIMARY KEY,
    quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    canonical_field TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_observation_id TEXT NOT NULL,
    source_native_field TEXT NOT NULL,
    transformation TEXT NOT NULL,
    accepted_at_utc TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    confidence TEXT NOT NULL,
    UNIQUE(quarter_id, canonical_field, provider_observation_id, source_native_field),
    CHECK (canonical_field IN ('revenue','gross_profit','operating_income','ebit','ebitda','net_income','operating_cashflow','capex','free_cashflow','cash','total_debt','shares_outstanding'))
);

CREATE TABLE v4_ttm_contract (
    quarter_id INTEGER PRIMARY KEY REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    required_fields_json TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_at_utc TEXT
);

CREATE INDEX idx_v4_quarter_company_period ON v4_quarter(company_id, fiscal_year, fiscal_quarter);
CREATE INDEX idx_v4_provenance_field ON v4_field_provenance(canonical_field, provider);
"""


ANALYSIS_SCHEMA_SQL = """
CREATE TABLE schema_version (
    db_name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE analysis_model_run (
    run_id TEXT PRIMARY KEY,
    model_type TEXT NOT NULL CHECK (model_type IN ('SCORE','LIFECYCLE','VALUATION')),
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE score_result (
    score_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    quarter_id INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    total_score REAL,
    readiness_status TEXT NOT NULL,
    missing_input_reason TEXT,
    generated_at_utc TEXT NOT NULL,
    run_id TEXT REFERENCES analysis_model_run(run_id)
);

CREATE TABLE score_component (
    score_component_id INTEGER PRIMARY KEY,
    score_result_id INTEGER NOT NULL REFERENCES score_result(score_result_id) ON DELETE CASCADE,
    component_name TEXT NOT NULL,
    component_score REAL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(score_result_id, component_name)
);

CREATE TABLE lifecycle_result (
    lifecycle_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    quarter_id INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    lifecycle_class TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    run_id TEXT REFERENCES analysis_model_run(run_id)
);

CREATE TABLE valuation_result (
    valuation_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    quarter_id INTEGER NOT NULL,
    valuation_date TEXT,
    price REAL,
    valuation_metrics_json TEXT NOT NULL DEFAULT '{}',
    ohlcv_source_db TEXT NOT NULL DEFAULT 'data/osakedata.db',
    status TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    run_id TEXT REFERENCES analysis_model_run(run_id)
);

CREATE INDEX idx_score_result_company_quarter ON score_result(company_id, quarter_id);
CREATE INDEX idx_lifecycle_result_company_quarter ON lifecycle_result(company_id, quarter_id);
CREATE INDEX idx_valuation_result_company_quarter ON valuation_result(company_id, quarter_id);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def bootstrap_database(path: Path, db_name: str, schema_sql: str, applied_at_utc: str) -> None:
    with connect(path) as conn:
        conn.executescript(schema_sql)
        conn.execute(
            "INSERT OR REPLACE INTO schema_version(db_name, version, applied_at_utc) VALUES (?, ?, ?)",
            (db_name, SCHEMA_VERSION, applied_at_utc),
        )


def bootstrap_all(provider_db: Path, canonical_db: Path, analysis_db: Path, applied_at_utc: str) -> None:
    bootstrap_database(provider_db, "fundamentals_provider", PROVIDER_SCHEMA_SQL, applied_at_utc)
    bootstrap_database(canonical_db, "fundamentals_v4", CANONICAL_SCHEMA_SQL, applied_at_utc)
    bootstrap_database(analysis_db, "fundamentals_analysis", ANALYSIS_SCHEMA_SQL, applied_at_utc)


def canonical_financial_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(v4_quarter_financials)")}


def canonical_field_contract_present(conn: sqlite3.Connection) -> bool:
    return set(V4_CANONICAL_FINANCIAL_FIELDS) <= canonical_financial_columns(conn)
