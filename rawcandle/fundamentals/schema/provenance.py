from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

from rawcandle.fundamentals.schema.contract import V4_CANONICAL_FINANCIAL_FIELDS


COMMON_EARNINGS_FIELD = "net_income_common"
COMMON_EARNINGS_NATIVE_FIELD = "netinccmn"
COMMON_EARNINGS_PROVENANCE_TABLE = "v4_common_earnings_provenance"
OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE = "v4_operating_working_capital_provenance"
OPERATING_WORKING_CAPITAL_NATIVE_FIELDS = {
    "accounts_receivable": "receivables",
    "inventory": "inventory",
    "accounts_payable": "payables",
    "deferred_revenue": "deferredrev",
    "total_assets": "assets",
}
LEGACY_PROVENANCE_TABLE = "v4_field_provenance"
PROVENANCE_COLUMNS = (
    "provenance_id",
    "quarter_id",
    "canonical_field",
    "provider",
    "provider_observation_id",
    "source_native_field",
    "transformation",
    "accepted_at_utc",
    "rule_version",
    "confidence",
)
KNOWN_PROVENANCE_FIELDS = frozenset(V4_CANONICAL_FINANCIAL_FIELDS)
LEGACY_PROVENANCE_FIELDS = KNOWN_PROVENANCE_FIELDS - {COMMON_EARNINGS_FIELD, *OPERATING_WORKING_CAPITAL_NATIVE_FIELDS}

COMMON_EARNINGS_PROVENANCE_SCHEMA_SQL = f"""
CREATE TABLE {COMMON_EARNINGS_PROVENANCE_TABLE} (
    provenance_id INTEGER PRIMARY KEY,
    quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    canonical_field TEXT NOT NULL CHECK (canonical_field = '{COMMON_EARNINGS_FIELD}'),
    provider TEXT NOT NULL,
    provider_observation_id TEXT NOT NULL,
    source_native_field TEXT NOT NULL CHECK (source_native_field = '{COMMON_EARNINGS_NATIVE_FIELD}'),
    transformation TEXT NOT NULL,
    accepted_at_utc TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    confidence TEXT NOT NULL,
    UNIQUE(quarter_id, canonical_field, provider_observation_id, source_native_field)
);

CREATE INDEX idx_v4_common_earnings_provenance_field
ON {COMMON_EARNINGS_PROVENANCE_TABLE}(canonical_field, provider);
"""

OPERATING_WORKING_CAPITAL_PROVENANCE_SCHEMA_SQL = f"""
CREATE TABLE {OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE} (
    provenance_id INTEGER PRIMARY KEY,
    quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    canonical_field TEXT NOT NULL CHECK (canonical_field IN ({','.join(repr(field) for field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS)})),
    provider TEXT NOT NULL,
    provider_observation_id TEXT NOT NULL,
    source_native_field TEXT NOT NULL,
    transformation TEXT NOT NULL,
    accepted_at_utc TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    confidence TEXT NOT NULL,
    UNIQUE(quarter_id, canonical_field, provider_observation_id, source_native_field),
    CHECK ((canonical_field = 'accounts_receivable' AND source_native_field = 'receivables')
        OR (canonical_field = 'inventory' AND source_native_field = 'inventory')
        OR (canonical_field = 'accounts_payable' AND source_native_field = 'payables')
        OR (canonical_field = 'deferred_revenue' AND source_native_field = 'deferredrev')
        OR (canonical_field = 'total_assets' AND source_native_field = 'assets'))
);

CREATE INDEX idx_v4_operating_working_capital_provenance_field
ON {OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE}(canonical_field, provider);
"""


def ensure_provenance_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {COMMON_EARNINGS_PROVENANCE_TABLE} (
            provenance_id INTEGER PRIMARY KEY,
            quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
            canonical_field TEXT NOT NULL CHECK (canonical_field = '{COMMON_EARNINGS_FIELD}'),
            provider TEXT NOT NULL,
            provider_observation_id TEXT NOT NULL,
            source_native_field TEXT NOT NULL CHECK (source_native_field = '{COMMON_EARNINGS_NATIVE_FIELD}'),
            transformation TEXT NOT NULL,
            accepted_at_utc TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            confidence TEXT NOT NULL,
            UNIQUE(quarter_id, canonical_field, provider_observation_id, source_native_field)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE} (
            provenance_id INTEGER PRIMARY KEY,
            quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
            canonical_field TEXT NOT NULL CHECK (canonical_field IN ({','.join(repr(field) for field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS)})),
            provider TEXT NOT NULL,
            provider_observation_id TEXT NOT NULL,
            source_native_field TEXT NOT NULL,
            transformation TEXT NOT NULL,
            accepted_at_utc TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            confidence TEXT NOT NULL,
            UNIQUE(quarter_id, canonical_field, provider_observation_id, source_native_field),
            CHECK ((canonical_field = 'accounts_receivable' AND source_native_field = 'receivables')
                OR (canonical_field = 'inventory' AND source_native_field = 'inventory')
                OR (canonical_field = 'accounts_payable' AND source_native_field = 'payables')
                OR (canonical_field = 'deferred_revenue' AND source_native_field = 'deferredrev')
                OR (canonical_field = 'total_assets' AND source_native_field = 'assets'))
        )
        """
    )
    conn.execute(
        f"""CREATE INDEX IF NOT EXISTS idx_v4_operating_working_capital_provenance_field
        ON {OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE}(canonical_field, provider)"""
    )
    conn.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_v4_common_earnings_provenance_field
        ON {COMMON_EARNINGS_PROVENANCE_TABLE}(canonical_field, provider)
        """
    )
    conflict = conn.execute(
        f"SELECT 1 FROM {LEGACY_PROVENANCE_TABLE} WHERE canonical_field=? LIMIT 1",
        (COMMON_EARNINGS_FIELD,),
    ).fetchone()
    if conflict is not None:
        raise sqlite3.IntegrityError("COMMON_EARNINGS_PROVENANCE_IN_LEGACY_STORE")
    placeholders = ",".join("?" for _ in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS)
    conflict = conn.execute(
        f"SELECT 1 FROM {LEGACY_PROVENANCE_TABLE} WHERE canonical_field IN ({placeholders}) LIMIT 1",
        tuple(OPERATING_WORKING_CAPITAL_NATIVE_FIELDS),
    ).fetchone()
    if conflict is not None:
        raise sqlite3.IntegrityError("OPERATING_WORKING_CAPITAL_PROVENANCE_IN_LEGACY_STORE")


def provenance_table(canonical_field: str) -> str:
    if canonical_field not in KNOWN_PROVENANCE_FIELDS:
        raise ValueError(f"UNKNOWN_CANONICAL_PROVENANCE_FIELD:{canonical_field}")
    if canonical_field == COMMON_EARNINGS_FIELD:
        return COMMON_EARNINGS_PROVENANCE_TABLE
    if canonical_field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS:
        return OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE
    return LEGACY_PROVENANCE_TABLE


def _existing_provenance_tables(conn: sqlite3.Connection) -> tuple[str, ...]:
    expected = (
        LEGACY_PROVENANCE_TABLE,
        COMMON_EARNINGS_PROVENANCE_TABLE,
        OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
    )
    existing = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    return tuple(table for table in expected if table in existing)


def write_provenance(
    conn: sqlite3.Connection,
    row: Mapping[str, Any],
    *,
    ignore_duplicate: bool = False,
) -> int:
    canonical_field = str(row.get("canonical_field", ""))
    table = provenance_table(canonical_field)
    if canonical_field == COMMON_EARNINGS_FIELD and row.get("source_native_field") != COMMON_EARNINGS_NATIVE_FIELD:
        raise ValueError("INVALID_COMMON_EARNINGS_NATIVE_FIELD")
    if canonical_field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS and row.get("source_native_field") != OPERATING_WORKING_CAPITAL_NATIVE_FIELDS[canonical_field]:
        raise ValueError("INVALID_OPERATING_WORKING_CAPITAL_NATIVE_FIELD")
    ensure_provenance_schema(conn)
    verb = "INSERT OR IGNORE" if ignore_duplicate else "INSERT"
    columns = PROVENANCE_COLUMNS[1:]
    before = conn.total_changes
    conn.execute(
        f"{verb} INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        tuple(row[column] for column in columns),
    )
    return conn.total_changes - before


def write_provenance_many(
    conn: sqlite3.Connection,
    rows: Iterable[Mapping[str, Any]],
    *,
    ignore_duplicate: bool = False,
) -> int:
    materialized = list(rows)
    ensure_provenance_schema(conn)
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in materialized:
        canonical_field = str(row.get("canonical_field", ""))
        table = provenance_table(canonical_field)
        if canonical_field == COMMON_EARNINGS_FIELD and row.get("source_native_field") != COMMON_EARNINGS_NATIVE_FIELD:
            raise ValueError("INVALID_COMMON_EARNINGS_NATIVE_FIELD")
        if canonical_field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS and row.get("source_native_field") != OPERATING_WORKING_CAPITAL_NATIVE_FIELDS[canonical_field]:
            raise ValueError("INVALID_OPERATING_WORKING_CAPITAL_NATIVE_FIELD")
        grouped.setdefault(table, []).append(row)
    columns = PROVENANCE_COLUMNS[1:]
    verb = "INSERT OR IGNORE" if ignore_duplicate else "INSERT"
    before = conn.total_changes
    for table, table_rows in grouped.items():
        conn.executemany(
            f"{verb} INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            (tuple(row[column] for column in columns) for row in table_rows),
        )
    return conn.total_changes - before


def read_provenance(
    conn: sqlite3.Connection,
    *,
    quarter_id: int | None = None,
    canonical_field: str | None = None,
) -> list[dict[str, Any]]:
    if canonical_field is not None:
        tables = (provenance_table(canonical_field),)
    else:
        tables = _existing_provenance_tables(conn)
    existing = set(_existing_provenance_tables(conn))
    tables = tuple(table for table in tables if table in existing)
    rows: list[dict[str, Any]] = []
    for table in tables:
        clauses: list[str] = []
        parameters: list[Any] = []
        if quarter_id is not None:
            clauses.append("quarter_id=?")
            parameters.append(quarter_id)
        if canonical_field is not None:
            clauses.append("canonical_field=?")
            parameters.append(canonical_field)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows.extend(
            dict(row)
            for row in conn.execute(
                f"SELECT {','.join(PROVENANCE_COLUMNS)} FROM {table}{where}", parameters
            )
        )
    return sorted(
        rows,
        key=lambda row: (
            int(row["quarter_id"]),
            str(row["canonical_field"]),
            int(row["provenance_id"]),
        ),
    )


def count_provenance(conn: sqlite3.Connection) -> int:
    return sum(
        int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in _existing_provenance_tables(conn)
    )


def provenance_counts_by_field(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for table in _existing_provenance_tables(conn):
        for row in conn.execute(f"SELECT canonical_field,COUNT(*) FROM {table} GROUP BY canonical_field"):
            counts[str(row[0])] = counts.get(str(row[0]), 0) + int(row[1])
    return [{"canonical_field": field, "rows": count} for field, count in sorted(counts.items())]


def provenance_provider_observation_ids(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for table in _existing_provenance_tables(conn)
        for row in conn.execute(f"SELECT DISTINCT provider_observation_id FROM {table}")
    }
