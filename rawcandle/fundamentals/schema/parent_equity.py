"""Additive parent-equity acceptance on inactive canonical copies only.

Parent equity is not common equity; preferred-capital exclusion is not proven.
The accepted shares observation is the sole binding, never a richer fallback row.
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.generations import PROJECT_ROOT, resolve_active_generation

RULE_VERSION = "PARENT_EQUITY_ACCEPTED_ARQ_V1"
FIELD_MAPPING = {"parent_equity": "equity", "parent_equity_usd": "equityusd"}
SOURCE_TABLE = "v4_parent_equity_source"
PROVENANCE_TABLE = "v4_parent_equity_provenance"
NUMERIC_SOURCE_FIELDS = ("pb", "marketcap", "price", "sharesbas", "shareswa", "shareswadil", "sharefactor")


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def assert_inactive_copy(path: Path) -> None:
    resolved = path.resolve()
    active = resolve_active_generation().role_paths()
    protected = {*[p.resolve() for p in active.values()], *[(PROJECT_ROOT / "data" / name).resolve() for name in ("fundamentals_v4.db", "fundamentals_provider.db", "fundamentals_analysis.db")]}
    if path.is_symlink() or resolved in protected or (resolved.parent / "generation_manifest.json").exists():
        raise PermissionError("PARENT_EQUITY_INACTIVE_COPY_REQUIRED")
    if not path.is_file():
        raise FileNotFoundError(path)


def ensure_schema(conn: sqlite3.Connection) -> None:
    columns = {r[1] for r in conn.execute("PRAGMA table_info(v4_quarter_financials)")}
    for field in FIELD_MAPPING:
        if field not in columns:
            conn.execute(f"ALTER TABLE v4_quarter_financials ADD COLUMN {field} REAL")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {SOURCE_TABLE} (
        quarter_id INTEGER PRIMARY KEY REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
        provider TEXT NOT NULL CHECK(provider='SHARADAR'),
        observation_id TEXT NOT NULL, content_hash TEXT NOT NULL,
        dimension TEXT NOT NULL CHECK(dimension='ARQ'), fiscalperiod TEXT NOT NULL,
        reportperiod TEXT NOT NULL, provider_date TEXT,
        source_availability_date TEXT, fetched_at_utc TEXT, lastupdated TEXT,
        acceptance_rule TEXT NOT NULL, accepted_at_utc TEXT NOT NULL,
        category TEXT, pb REAL, marketcap REAL, price REAL, sharesbas REAL,
        shareswa REAL, shareswadil REAL, sharefactor REAL
    )""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {PROVENANCE_TABLE} (
        provenance_id INTEGER PRIMARY KEY,
        quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
        canonical_field TEXT NOT NULL CHECK(canonical_field IN ('parent_equity','parent_equity_usd')),
        provider TEXT NOT NULL CHECK(provider='SHARADAR'), provider_observation_id TEXT NOT NULL,
        source_native_field TEXT NOT NULL, transformation TEXT NOT NULL CHECK(transformation='DIRECT'),
        accepted_at_utc TEXT NOT NULL, rule_version TEXT NOT NULL, confidence TEXT NOT NULL,
        UNIQUE(quarter_id,canonical_field),
        CHECK((canonical_field='parent_equity' AND source_native_field='equity') OR
              (canonical_field='parent_equity_usd' AND source_native_field='equityusd'))
    )""")


def accept_parent_equity(conn: sqlite3.Connection, provider: sqlite3.Connection, *, accepted_at: str) -> dict[str, int]:
    """Caller owns the inactive-copy transaction; unrelated financial fields untouched."""
    ensure_schema(conn)
    metrics = {"bound_quarters": 0, "values_present": 0}
    metadata = {}
    if provider.execute("SELECT 1 FROM sqlite_master WHERE name='sharadar_ticker_metadata'").fetchone():
        columns = {r[1] for r in provider.execute("PRAGMA table_info(sharadar_ticker_metadata)")}
        restriction = "WHERE table_name IN ('fundamentals','SF1')" if 'table_name' in columns else ''
        metadata = {r['ticker']: r['category'] for r in provider.execute(
            f"SELECT ticker,category FROM sharadar_ticker_metadata {restriction} ORDER BY fetched_at_utc"
        )}
    # Rebuild the accepted projection, also clearing stale/missing bindings.
    conn.execute(f"DELETE FROM {SOURCE_TABLE}")
    conn.execute(f"DELETE FROM {PROVENANCE_TABLE}")
    conn.execute("UPDATE v4_quarter_financials SET parent_equity=NULL,parent_equity_usd=NULL WHERE parent_equity IS NOT NULL OR parent_equity_usd IS NOT NULL")
    for q in conn.execute("""SELECT q.*,f.shares_outstanding,p.provider_observation_id,
        p.accepted_at_utc AS shares_accepted_at FROM v4_quarter q
        JOIN v4_quarter_financials f USING(quarter_id)
        JOIN v4_field_provenance p ON p.quarter_id=q.quarter_id AND p.canonical_field='shares_outstanding'
        WHERE q.identity_status='ACCEPTED' AND p.provider='SHARADAR'""").fetchall():
        observations = provider.execute("SELECT * FROM provider_observation WHERE observation_id=?", (q['provider_observation_id'],)).fetchone()
        if observations is None:
            raise ValueError("PARENT_EQUITY_OBSERVATION_MISSING")
        raw = json.loads(observations['payload_json'])
        if (observations['provider'] != 'SHARADAR' or raw.get('dimension') != 'ARQ'
            or raw.get('fiscalperiod') != f"{q['fiscal_year']}-{q['fiscal_quarter']}"
            or raw.get('reportperiod') != q['source_reportperiod']
            or finite(raw.get('sharesbas')) != finite(q['shares_outstanding'])):
            raise ValueError("PARENT_EQUITY_ACCEPTED_OBSERVATION_MISMATCH")
        qid = q['quarter_id']
        for field, native in FIELD_MAPPING.items():
            value = finite(raw.get(native))
            conn.execute(f"UPDATE v4_quarter_financials SET {field}=? WHERE quarter_id=?", (value, qid))
            if value is not None:
                conn.execute(f"""INSERT INTO {PROVENANCE_TABLE}
                    (quarter_id,canonical_field,provider,provider_observation_id,source_native_field,
                     transformation,accepted_at_utc,rule_version,confidence)
                    VALUES(?,?,'SHARADAR',?,?,'DIRECT',?,?,'HIGH')""",
                    (qid, field, observations['observation_id'], native, accepted_at, RULE_VERSION))
                metrics['values_present'] += 1
        columns = ('quarter_id','provider','observation_id','content_hash','dimension','fiscalperiod','reportperiod','provider_date','source_availability_date','fetched_at_utc','lastupdated','acceptance_rule','accepted_at_utc','category',*NUMERIC_SOURCE_FIELDS)
        values = (qid,'SHARADAR',observations['observation_id'],observations['content_hash'],'ARQ',raw['fiscalperiod'],raw['reportperiod'],raw.get('date'),observations['source_availability_date'],observations['fetched_at_utc'],raw.get('lastupdated'),RULE_VERSION,accepted_at,metadata.get(raw.get('ticker')), *(finite(raw.get(k)) for k in NUMERIC_SOURCE_FIELDS))
        conn.execute(f"INSERT INTO {SOURCE_TABLE} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
        metrics['bound_quarters'] += 1
    return metrics


def migrate_parent_equity(provider_db: Path, canonical_db: Path, *, accepted_at: str) -> dict[str, int]:
    assert_inactive_copy(canonical_db)
    with sqlite3.connect(canonical_db) as conn, sqlite3.connect(f"file:{provider_db.resolve()}?mode=ro", uri=True) as provider:
        conn.row_factory = provider.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('BEGIN IMMEDIATE')
        return accept_parent_equity(conn, provider, accepted_at=accepted_at)
