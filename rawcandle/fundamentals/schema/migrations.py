from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from rawcandle.fundamentals.schema.contract import SCHEMA_VERSION, V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.provenance import (
    COMMON_EARNINGS_FIELD,
    COMMON_EARNINGS_PROVENANCE_SCHEMA_SQL,
    ensure_provenance_schema,
    write_provenance,
    write_provenance_many,
)
from rawcandle.fundamentals.ttm.engine import ensure_ttm_schema


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
    netinccmn INTEGER,
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

CREATE TABLE sharadar_ticker_metadata (
    table_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    permaticker TEXT NOT NULL,
    name TEXT,
    exchange TEXT,
    isdelisted TEXT,
    category TEXT,
    relatedtickers TEXT,
    secfilings TEXT,
    firstpricedate TEXT,
    lastpricedate TEXT,
    firstquarter TEXT,
    lastquarter TEXT,
    lastupdated TEXT,
    payload_json TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    PRIMARY KEY(table_name, ticker, permaticker)
);

CREATE TABLE sharadar_action_metadata (
    date TEXT NOT NULL,
    action TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT,
    contraticker TEXT NOT NULL,
    contraname TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    PRIMARY KEY(date, action, ticker, name, contraticker, contraname)
);

CREATE INDEX idx_provider_observation_provider_ticker ON provider_observation(provider, provider_ticker);
CREATE INDEX idx_provider_observation_period ON provider_observation(provider_ticker, dimension, reportperiod, fiscalperiod);
CREATE INDEX idx_sharadar_fundamental_period ON sharadar_fundamental_observation(ticker, dimension, reportperiod, fiscalperiod);
CREATE INDEX idx_sharadar_ticker_metadata_ticker ON sharadar_ticker_metadata(ticker, table_name);
CREATE INDEX idx_sharadar_ticker_metadata_permaticker ON sharadar_ticker_metadata(permaticker);
CREATE INDEX idx_sharadar_action_metadata_ticker ON sharadar_action_metadata(ticker, date, action);
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

CREATE TABLE provider_company_identity (
    provider TEXT NOT NULL,
    provider_identifier_type TEXT NOT NULL,
    provider_identifier_value TEXT NOT NULL,
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    provider_ticker TEXT,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_value TEXT,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(provider, provider_identifier_type, provider_identifier_value)
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
    source_type TEXT NOT NULL DEFAULT 'LEGACY_BOOTSTRAP',
    source_name TEXT,
    source_field TEXT,
    source_value TEXT,
    derivation TEXT,
    confidence TEXT NOT NULL DEFAULT 'HIGH',
    PRIMARY KEY(company_id, cik_normalized)
);

CREATE TABLE company_fiscal_calendar_profile (
    company_id INTEGER PRIMARY KEY REFERENCES company(company_id) ON DELETE CASCADE,
    typical_fiscal_year_start TEXT,
    chain_status TEXT,
    break_reason TEXT,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_field TEXT,
    source_value TEXT,
    bootstrap_status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE company_fiscal_year_anchor (
    company_id INTEGER NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    fiscal_year_start TEXT NOT NULL,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_field TEXT NOT NULL,
    source_value TEXT,
    confidence TEXT NOT NULL,
    observed_verified INTEGER NOT NULL CHECK (observed_verified IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(company_id, fiscal_year)
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
    updated_at_utc TEXT NOT NULL,
    net_income_common INTEGER
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

""" + COMMON_EARNINGS_PROVENANCE_SCHEMA_SQL + """

CREATE TABLE v4_ttm_contract (
    quarter_id INTEGER PRIMARY KEY REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    required_fields_json TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_at_utc TEXT
);

CREATE INDEX idx_v4_quarter_company_period ON v4_quarter(company_id, fiscal_year, fiscal_quarter);
CREATE INDEX idx_v4_provenance_field ON v4_field_provenance(canonical_field, provider);
CREATE INDEX idx_company_fiscal_year_anchor_year ON company_fiscal_year_anchor(fiscal_year, fiscal_year_start);
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
    with connect(canonical_db) as conn:
        ensure_ttm_schema(conn)
    bootstrap_database(analysis_db, "fundamentals_analysis", ANALYSIS_SCHEMA_SQL, applied_at_utc)


def canonical_financial_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(v4_quarter_financials)")}


def canonical_field_contract_present(conn: sqlite3.Connection) -> bool:
    return set(V4_CANONICAL_FINANCIAL_FIELDS) <= canonical_financial_columns(conn)


def canonical_ttm_contract_present(conn: sqlite3.Connection) -> bool:
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"v4_ttm_contract", "v4_ttm_values", "v4_ttm_input_quarter"} <= tables


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _set_schema_version(conn: sqlite3.Connection, db_name: str, applied_at_utc: str) -> None:
    current = conn.execute("SELECT version FROM schema_version WHERE db_name=?", (db_name,)).fetchone()
    if current is not None and current["version"] == SCHEMA_VERSION:
        return
    conn.execute(
        "INSERT OR REPLACE INTO schema_version(db_name,version,applied_at_utc) VALUES (?,?,?)",
        (db_name, SCHEMA_VERSION, applied_at_utc),
    )


def _storage_evidence(conn: sqlite3.Connection, path: Path, label: str, elapsed: float) -> dict[str, int | float | str]:
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    return {
        "label": label,
        "elapsed_seconds": elapsed,
        "file_size": path.stat().st_size,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "freelist_bytes": page_size * freelist_count,
    }


def migrate_valuation_foundation(
    provider_db: Path,
    canonical_db: Path,
    applied_at_utc: str,
    *,
    allow_production: bool = False,
) -> dict[str, int]:
    """Apply the Phase 3B additive contract to explicitly supplied databases."""
    production_paths = {
        Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
        Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    }
    if not allow_production and {provider_db.resolve(), canonical_db.resolve()} & production_paths:
        raise PermissionError("PHASE3B_PRODUCTION_SCHEMA_MIGRATION_NOT_AUTHORIZED")
    counts = {
        "provider_columns_added": 0,
        "canonical_columns_added": 0,
        "ttm_columns_added": 0,
        "provider_rows_backfilled": 0,
        "canonical_rows_backfilled": 0,
        "provenance_rows_added": 0,
    }
    with connect(provider_db) as provider:
        if "netinccmn" not in _columns(provider, "sharadar_fundamental_observation"):
            provider.execute("ALTER TABLE sharadar_fundamental_observation ADD COLUMN netinccmn INTEGER")
            counts["provider_columns_added"] += 1
        before = provider.total_changes
        provider.execute(
            """
            UPDATE sharadar_fundamental_observation
            SET netinccmn=(
                SELECT CAST(NULLIF(json_extract(po.payload_json, '$.netinccmn'), '') AS INTEGER)
                FROM provider_observation po
                WHERE po.observation_id=sharadar_fundamental_observation.observation_id
            )
            WHERE netinccmn IS NULL
              AND EXISTS (
                  SELECT 1 FROM provider_observation po
                  WHERE po.observation_id=sharadar_fundamental_observation.observation_id
                    AND NULLIF(json_extract(po.payload_json, '$.netinccmn'), '') IS NOT NULL
              )
            """
        )
        counts["provider_rows_backfilled"] = provider.total_changes - before
        _set_schema_version(provider, "fundamentals_provider", applied_at_utc)

    with connect(canonical_db) as canonical:
        if "net_income_common" not in _columns(canonical, "v4_quarter_financials"):
            canonical.execute("ALTER TABLE v4_quarter_financials ADD COLUMN net_income_common INTEGER")
            counts["canonical_columns_added"] += 1
        ensure_provenance_schema(canonical)
        ensure_ttm_schema(canonical)
        ttm_columns = _columns(canonical, "v4_ttm_values")
        if "ttm_net_income_common" not in ttm_columns:
            canonical.execute("ALTER TABLE v4_ttm_values ADD COLUMN ttm_net_income_common REAL")
            counts["ttm_columns_added"] += 1
        if "net_income_common_4q_ready" not in ttm_columns:
            canonical.execute(
                "ALTER TABLE v4_ttm_values ADD COLUMN net_income_common_4q_ready INTEGER NOT NULL DEFAULT 0 CHECK (net_income_common_4q_ready IN (0,1))"
            )
            counts["ttm_columns_added"] += 1

        provider_values: dict[str, int | None] = {}
        with connect(provider_db) as provider:
            provider_values = {
                str(row["observation_id"]): row["netinccmn"]
                for row in provider.execute(
                    "SELECT observation_id,netinccmn FROM sharadar_fundamental_observation"
                )
            }
        selected = canonical.execute(
            """
            SELECT quarter_id,provider,provider_observation_id,accepted_at_utc,confidence
            FROM v4_field_provenance
            WHERE canonical_field='net_income'
            ORDER BY quarter_id,provenance_id
            """
        ).fetchall()
        seen: set[int] = set()
        for row in selected:
            quarter_id = int(row["quarter_id"])
            if quarter_id in seen:
                continue
            seen.add(quarter_id)
            value = provider_values.get(str(row["provider_observation_id"]))
            if value is None:
                continue
            before = canonical.total_changes
            canonical.execute(
                "UPDATE v4_quarter_financials SET net_income_common=? WHERE quarter_id=? AND net_income_common IS NULL",
                (value, quarter_id),
            )
            counts["canonical_rows_backfilled"] += canonical.total_changes - before
            counts["provenance_rows_added"] += write_provenance(
                canonical,
                {
                    "quarter_id": quarter_id,
                    "canonical_field": COMMON_EARNINGS_FIELD,
                    "provider": row["provider"],
                    "provider_observation_id": row["provider_observation_id"],
                    "source_native_field": "netinccmn",
                    "transformation": "DIRECT",
                    "accepted_at_utc": row["accepted_at_utc"],
                    "rule_version": "SHARADAR_ARQ_PRIMARY_V1",
                    "confidence": row["confidence"],
                },
                ignore_duplicate=True,
            )
        _set_schema_version(canonical, "fundamentals_v4", applied_at_utc)
    return counts


def migrate_canonical_valuation_copy(
    canonical_db: Path,
    provider_db: Path,
    applied_at_utc: str,
    *,
    inject_failure_at: str | None = None,
) -> dict[str, object]:
    """Migrate and backfill a non-production canonical copy from a read-only provider."""
    production_canonical = Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db").resolve()
    if canonical_db.resolve() == production_canonical:
        raise PermissionError("PHASE3C_PRODUCTION_CANONICAL_WRITE_BLOCKED")
    if canonical_db.resolve() == provider_db.resolve():
        raise ValueError("CANONICAL_DESTINATION_EQUALS_PROVIDER_SOURCE")
    counts = {
        "canonical_columns_added": 0,
        "ttm_columns_added": 0,
        "canonical_rows_backfilled": 0,
        "provenance_rows_added": 0,
        "ttm_rows_changed": 0,
        "storage_stages": [],
    }
    provider_uri = f"file:{provider_db.resolve()}?mode=ro"
    with connect(canonical_db) as canonical:
        canonical.execute("ATTACH DATABASE ? AS provider_ro", (provider_uri,))
        stages = counts["storage_stages"]
        assert isinstance(stages, list)
        stages.append(_storage_evidence(canonical, canonical_db, "fresh_copy", 0.0))
        try:
            canonical.execute("BEGIN IMMEDIATE")
            started = time.perf_counter()
            if "net_income_common" not in _columns(canonical, "v4_quarter_financials"):
                canonical.execute("ALTER TABLE v4_quarter_financials ADD COLUMN net_income_common INTEGER")
                counts["canonical_columns_added"] += 1
            ensure_provenance_schema(canonical)
            if not canonical_ttm_contract_present(canonical):
                raise RuntimeError("CANONICAL_TTM_CONTRACT_MISSING")
            ttm_columns = _columns(canonical, "v4_ttm_values")
            if "ttm_net_income_common" not in ttm_columns:
                canonical.execute("ALTER TABLE v4_ttm_values ADD COLUMN ttm_net_income_common REAL")
                counts["ttm_columns_added"] += 1
            if "net_income_common_4q_ready" not in ttm_columns:
                canonical.execute(
                    "ALTER TABLE v4_ttm_values ADD COLUMN net_income_common_4q_ready INTEGER NOT NULL DEFAULT 0 CHECK (net_income_common_4q_ready IN (0,1))"
                )
                counts["ttm_columns_added"] += 1
            stages.append(_storage_evidence(canonical, canonical_db, "schema_migration", time.perf_counter() - started))
            if inject_failure_at == "schema":
                raise RuntimeError("INJECTED_CANONICAL_MIGRATION_FAILURE")

            started = time.perf_counter()
            before = canonical.total_changes
            canonical.execute(
                """
                UPDATE v4_quarter_financials
                SET net_income_common=(
                    SELECT CAST(NULLIF(json_extract(po.payload_json,'$.netinccmn'),'') AS INTEGER)
                    FROM v4_field_provenance fp
                    JOIN provider_ro.provider_observation po ON po.observation_id=fp.provider_observation_id
                    WHERE fp.quarter_id=v4_quarter_financials.quarter_id
                      AND fp.canonical_field='net_income'
                    ORDER BY fp.provenance_id LIMIT 1
                )
                WHERE net_income_common IS NULL
                  AND EXISTS (
                    SELECT 1 FROM v4_field_provenance fp
                    JOIN provider_ro.provider_observation po ON po.observation_id=fp.provider_observation_id
                    WHERE fp.quarter_id=v4_quarter_financials.quarter_id
                      AND fp.canonical_field='net_income'
                      AND NULLIF(json_extract(po.payload_json,'$.netinccmn'),'') IS NOT NULL
                  )
                """
            )
            counts["canonical_rows_backfilled"] = canonical.total_changes - before
            provenance_candidates = canonical.execute(
                """
                SELECT fp.quarter_id,fp.provider,fp.provider_observation_id,
                       fp.accepted_at_utc,fp.confidence
                FROM v4_field_provenance fp
                JOIN provider_ro.provider_observation po ON po.observation_id=fp.provider_observation_id
                WHERE fp.canonical_field='net_income'
                  AND NULLIF(json_extract(po.payload_json,'$.netinccmn'),'') IS NOT NULL
                """
            ).fetchall()
            counts["provenance_rows_added"] = write_provenance_many(
                canonical,
                (
                    {
                        "quarter_id": row["quarter_id"], "canonical_field": COMMON_EARNINGS_FIELD,
                        "provider": row["provider"], "provider_observation_id": row["provider_observation_id"],
                        "source_native_field": "netinccmn", "transformation": "DIRECT",
                        "accepted_at_utc": row["accepted_at_utc"], "rule_version": "SHARADAR_ARQ_PRIMARY_V1",
                        "confidence": row["confidence"],
                    }
                    for row in provenance_candidates
                ),
                ignore_duplicate=True,
            )
            stages.append(_storage_evidence(canonical, canonical_db, "canonical_common_earnings_backfill", time.perf_counter() - started))
            if inject_failure_at == "backfill":
                raise RuntimeError("INJECTED_CANONICAL_MIGRATION_FAILURE")

            started = time.perf_counter()
            before = canonical.total_changes
            canonical.execute(
                """
                UPDATE v4_ttm_values
                SET ttm_net_income_common=(
                    SELECT CASE WHEN COUNT(*)=4 AND COUNT(f.net_income_common)=4
                                THEN SUM(f.net_income_common) END
                    FROM v4_ttm_input_quarter i
                    JOIN v4_quarter_financials f ON f.quarter_id=i.input_quarter_id
                    WHERE i.ttm_id=v4_ttm_values.ttm_id
                ),
                net_income_common_4q_ready=CASE WHEN (
                    SELECT COUNT(f.net_income_common)
                    FROM v4_ttm_input_quarter i
                    JOIN v4_quarter_financials f ON f.quarter_id=i.input_quarter_id
                    WHERE i.ttm_id=v4_ttm_values.ttm_id
                )=4 THEN 1 ELSE 0 END
            WHERE COALESCE(ttm_net_income_common,9.87654321e307) != COALESCE((
                    SELECT CASE WHEN COUNT(*)=4 AND COUNT(f.net_income_common)=4
                                THEN SUM(f.net_income_common) END
                    FROM v4_ttm_input_quarter i
                    JOIN v4_quarter_financials f ON f.quarter_id=i.input_quarter_id
                    WHERE i.ttm_id=v4_ttm_values.ttm_id
                ),9.87654321e307)
               OR net_income_common_4q_ready != CASE WHEN (
                    SELECT COUNT(f.net_income_common)
                    FROM v4_ttm_input_quarter i
                    JOIN v4_quarter_financials f ON f.quarter_id=i.input_quarter_id
                    WHERE i.ttm_id=v4_ttm_values.ttm_id
                )=4 THEN 1 ELSE 0 END
                """
            )
            counts["ttm_rows_changed"] = canonical.total_changes - before
            stages.append(_storage_evidence(canonical, canonical_db, "ttm_common_earnings_rebuild", time.perf_counter() - started))
            if inject_failure_at == "ttm":
                raise RuntimeError("INJECTED_CANONICAL_MIGRATION_FAILURE")
            _set_schema_version(canonical, "fundamentals_v4", applied_at_utc)
            canonical.commit()
            stages.append(_storage_evidence(canonical, canonical_db, "final_close_checkpoint", 0.0))
        except Exception:
            canonical.rollback()
            raise
        finally:
            if canonical.in_transaction:
                canonical.rollback()
        canonical.execute("DETACH DATABASE provider_ro")
    return counts
