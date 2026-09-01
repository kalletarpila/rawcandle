from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

from rawcandle.fundamentals.schema.contract import V4_CANONICAL_FINANCIAL_FIELDS


COMMON_EARNINGS_FIELD = "net_income_common"
COMMON_EARNINGS_NATIVE_FIELD = "netinccmn"
COMMON_EARNINGS_PROVENANCE_TABLE = "v4_common_earnings_provenance"
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
LEGACY_PROVENANCE_FIELDS = KNOWN_PROVENANCE_FIELDS - {COMMON_EARNINGS_FIELD}

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


def provenance_table(canonical_field: str) -> str:
    if canonical_field not in KNOWN_PROVENANCE_FIELDS:
        raise ValueError(f"UNKNOWN_CANONICAL_PROVENANCE_FIELD:{canonical_field}")
    if canonical_field == COMMON_EARNINGS_FIELD:
        return COMMON_EARNINGS_PROVENANCE_TABLE
    return LEGACY_PROVENANCE_TABLE


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
        tables = (LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE)
    ensure_provenance_schema(conn)
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
    ensure_provenance_schema(conn)
    return sum(
        int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE)
    )


def provenance_counts_by_field(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_provenance_schema(conn)
    counts: dict[str, int] = {}
    for table in (LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE):
        for row in conn.execute(f"SELECT canonical_field,COUNT(*) FROM {table} GROUP BY canonical_field"):
            counts[str(row[0])] = counts.get(str(row[0]), 0) + int(row[1])
    return [{"canonical_field": field, "rows": count} for field, count in sorted(counts.items())]


def provenance_provider_observation_ids(conn: sqlite3.Connection) -> set[str]:
    ensure_provenance_schema(conn)
    return {
        str(row[0])
        for table in (LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE)
        for row in conn.execute(f"SELECT DISTINCT provider_observation_id FROM {table}")
    }
