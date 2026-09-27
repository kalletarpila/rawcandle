from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "forecasts_v1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS forecast_schema_version (
    db_name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_run (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    adapter TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')),
    scope_json TEXT NOT NULL DEFAULT '{}',
    counters_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS forecast_raw_evidence (
    raw_hash TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    forecast_family TEXT NOT NULL CHECK (
        forecast_family IN ('FISCAL_ESTIMATE','PRICE_TARGET','EARNINGS_HISTORY_REFERENCE')
    ),
    body_text TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    retain_until_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    forecast_family TEXT NOT NULL CHECK (
        forecast_family IN ('FISCAL_ESTIMATE','PRICE_TARGET','EARNINGS_HISTORY_REFERENCE')
    ),
    identity_key TEXT NOT NULL,
    company_id INTEGER,
    security_id INTEGER,
    provider_symbol TEXT NOT NULL,
    first_fetch_id TEXT NOT NULL REFERENCES forecast_fetch(fetch_id)
        DEFERRABLE INITIALLY DEFERRED,
    first_seen_at_utc TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    canonical_payload_json TEXT NOT NULL,
    raw_evidence_hash TEXT REFERENCES forecast_raw_evidence(raw_hash),
    schema_drift_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(provider, forecast_family, identity_key, content_hash)
);

CREATE TABLE IF NOT EXISTS forecast_fetch (
    fetch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES forecast_run(run_id),
    provider TEXT NOT NULL,
    adapter TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    company_id INTEGER,
    security_id INTEGER,
    identity_key TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    forecast_family TEXT NOT NULL CHECK (
        forecast_family IN ('FISCAL_ESTIMATE','PRICE_TARGET','EARNINGS_HISTORY_REFERENCE')
    ),
    requested_at_utc TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'SUCCESS_CHANGED','SUCCESS_UNCHANGED','VALID_NO_DATA',
        'PROVIDER_SYMBOL_UNAVAILABLE','RATE_LIMITED','TRANSIENT_FAILURE',
        'MALFORMED_OR_SCHEMA_MISMATCH'
    )),
    http_status INTEGER,
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
    error_class TEXT,
    error_code TEXT,
    content_hash TEXT,
    snapshot_id TEXT REFERENCES forecast_snapshot(snapshot_id),
    raw_evidence_hash TEXT REFERENCES forecast_raw_evidence(raw_hash),
    diagnostic_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS forecast_estimate (
    estimate_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES forecast_snapshot(snapshot_id) ON DELETE CASCADE,
    occurrence_index INTEGER NOT NULL CHECK (occurrence_index >= 0),
    provider_horizon TEXT NOT NULL,
    provider_end_date TEXT NOT NULL,
    provider_methodology TEXT,
    provider_methodology_state TEXT NOT NULL,
    metric TEXT NOT NULL,
    statistic TEXT NOT NULL,
    value_numeric TEXT,
    value_text TEXT,
    value_state TEXT NOT NULL,
    currency TEXT,
    unit TEXT NOT NULL,
    source_path TEXT NOT NULL,
    analyst_count TEXT,
    expected_fiscal_year INTEGER,
    expected_fiscal_quarter TEXT,
    canonical_quarter_id INTEGER,
    link_status TEXT NOT NULL DEFAULT 'UNLINKED' CHECK (link_status = 'UNLINKED'),
    UNIQUE(snapshot_id, occurrence_index, metric, statistic, source_path)
);

CREATE TABLE IF NOT EXISTS forecast_price_target (
    price_target_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES forecast_snapshot(snapshot_id) ON DELETE CASCADE,
    statistic TEXT NOT NULL CHECK (statistic IN ('current','low','high','mean','median')),
    value_numeric TEXT,
    value_state TEXT NOT NULL,
    currency TEXT,
    unit TEXT NOT NULL DEFAULT 'CURRENCY',
    source_path TEXT NOT NULL,
    UNIQUE(snapshot_id, statistic)
);

CREATE TABLE IF NOT EXISTS forecast_earnings_history_reference (
    reference_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES forecast_snapshot(snapshot_id) ON DELETE CASCADE,
    occurrence_index INTEGER NOT NULL CHECK (occurrence_index >= 0),
    provider_period TEXT NOT NULL,
    provider_quarter_date TEXT NOT NULL,
    provider_methodology TEXT,
    provider_methodology_state TEXT NOT NULL,
    currency TEXT,
    eps_estimate TEXT,
    eps_estimate_state TEXT NOT NULL,
    eps_actual TEXT,
    eps_actual_state TEXT NOT NULL,
    eps_difference TEXT,
    eps_difference_state TEXT NOT NULL,
    surprise_percent TEXT,
    surprise_percent_state TEXT NOT NULL,
    authority TEXT NOT NULL DEFAULT 'YAHOO_PROVIDER_REFERENCE' CHECK (
        authority = 'YAHOO_PROVIDER_REFERENCE'
    ),
    UNIQUE(snapshot_id, occurrence_index)
);

CREATE INDEX IF NOT EXISTS idx_forecast_fetch_asof
    ON forecast_fetch(provider, forecast_family, identity_key, fetched_at_utc, fetch_id);
CREATE INDEX IF NOT EXISTS idx_forecast_fetch_run ON forecast_fetch(run_id, status);
CREATE INDEX IF NOT EXISTS idx_forecast_snapshot_identity
    ON forecast_snapshot(provider, forecast_family, identity_key, first_seen_at_utc);
CREATE INDEX IF NOT EXISTS idx_forecast_estimate_snapshot
    ON forecast_estimate(snapshot_id, occurrence_index, metric, statistic);
CREATE INDEX IF NOT EXISTS idx_forecast_price_target_snapshot
    ON forecast_price_target(snapshot_id, statistic);
CREATE INDEX IF NOT EXISTS idx_forecast_history_snapshot
    ON forecast_earnings_history_reference(snapshot_id, occurrence_index);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect_forecasts_db(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate_forecasts_db(
    path: str | Path,
    *,
    applied_at_utc: str | None = None,
) -> None:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_forecasts_db(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            """
            INSERT INTO forecast_schema_version(db_name, version, applied_at_utc)
            VALUES('forecasts', ?, ?)
            ON CONFLICT(db_name) DO UPDATE SET
                version=excluded.version,
                applied_at_utc=excluded.applied_at_utc
            """,
            (SCHEMA_VERSION, applied_at_utc or utc_now()),
        )
