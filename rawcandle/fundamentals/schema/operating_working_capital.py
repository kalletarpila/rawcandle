from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from rawcandle.fundamentals.schema.contract import SCHEMA_VERSION
from rawcandle.fundamentals.schema.migrations import connect
from rawcandle.fundamentals.schema.prototype import parse_fiscalperiod
from rawcandle.fundamentals.schema.provenance import (
    OPERATING_WORKING_CAPITAL_NATIVE_FIELDS,
    OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
    ensure_provenance_schema,
    write_provenance,
)


PRODUCTION_PROVIDER = Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db")
PRODUCTION_CANONICAL = Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db")
RULE_VERSION = "SHARADAR_ARQ_PRIMARY_V1"


def _parse_endpoint(value: Any) -> tuple[int | None, bool]:
    if value is None or isinstance(value, str) and value.strip().lower() in {"", "none", "null", "nan"}:
        return None, False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, True
    if not math.isfinite(number):
        return None, True
    return int(number), False


def _columns(conn: sqlite3.Connection, schema: str, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA {schema}.table_info({table})")}


def _storage(conn: sqlite3.Connection, path: Path, stage: str, elapsed: float, logical_writes: int) -> dict[str, Any]:
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    wal = Path(f"{path}-wal")
    shm = Path(f"{path}-shm")
    return {
        "stage": stage,
        "elapsed_seconds": elapsed,
        "logical_writes": logical_writes,
        "file_size": path.stat().st_size,
        "page_count": int(conn.execute("PRAGMA page_count").fetchone()[0]),
        "freelist_count": int(conn.execute("PRAGMA freelist_count").fetchone()[0]),
        "wal_size": wal.stat().st_size if wal.exists() else 0,
        "shm_size": shm.stat().st_size if shm.exists() else 0,
        "page_size": page_size,
    }


def _validate_destinations(provider_db: Path, canonical_db: Path) -> None:
    resolved = {provider_db.resolve(), canonical_db.resolve()}
    if PRODUCTION_PROVIDER.resolve() in resolved or PRODUCTION_CANONICAL.resolve() in resolved:
        raise PermissionError("PHASE6A2_PRODUCTION_OR_ALIAS_DESTINATION_BLOCKED")
    if provider_db.resolve() == canonical_db.resolve():
        raise ValueError("PROVIDER_AND_CANONICAL_DESTINATIONS_MUST_DIFFER")
    if provider_db.is_symlink() or canonical_db.is_symlink():
        raise ValueError("SYMLINK_DESTINATION_BLOCKED")


def _selected(company_ids: Iterable[int] | None) -> set[int] | None:
    return None if company_ids is None else {int(value) for value in company_ids}


def migrate_and_backfill_operating_working_capital(
    provider_db: Path,
    canonical_db: Path,
    applied_at_utc: str,
    *,
    company_ids: Iterable[int] | None = None,
    inject_failure_at: str | None = None,
) -> dict[str, Any]:
    """Add and backfill the five endpoint fields on explicit non-production copies."""
    _validate_destinations(provider_db, canonical_db)
    selected = _selected(company_ids)
    metrics: dict[str, Any] = {
        "provider_columns_added": 0,
        "canonical_columns_added": 0,
        "provider_rows_changed": 0,
        "canonical_values_changed": 0,
        "provenance_rows_added": 0,
        "provenance_rows_removed": 0,
        "invalid_values": 0,
        "stages": [],
    }
    with connect(canonical_db) as conn:
        conn.execute("ATTACH DATABASE ? AS provider_copy", (str(provider_db.resolve()),))
        try:
            conn.execute("BEGIN IMMEDIATE")
            started = time.perf_counter()
            provider_columns = _columns(conn, "provider_copy", "sharadar_fundamental_observation")
            canonical_columns = _columns(conn, "main", "v4_quarter_financials")
            for canonical_field, native_field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS.items():
                if native_field not in provider_columns:
                    conn.execute(f"ALTER TABLE provider_copy.sharadar_fundamental_observation ADD COLUMN {native_field} INTEGER")
                    metrics["provider_columns_added"] += 1
                if canonical_field not in canonical_columns:
                    conn.execute(f"ALTER TABLE v4_quarter_financials ADD COLUMN {canonical_field} INTEGER")
                    metrics["canonical_columns_added"] += 1
            ensure_provenance_schema(conn)
            metrics["stages"].append(_storage(conn, canonical_db, "schema", time.perf_counter() - started, int(metrics["provider_columns_added"]) + int(metrics["canonical_columns_added"])))
            if inject_failure_at == "schema":
                raise RuntimeError("INJECTED_PHASE6A2_FAILURE")

            started = time.perf_counter()
            provider_rows = conn.execute(
                f"""SELECT s.*,po.company_id,po.payload_json
                   FROM provider_copy.sharadar_fundamental_observation s
                   JOIN provider_copy.provider_observation po USING(observation_id)
                   {'' if selected is None else 'WHERE po.company_id IN (' + ','.join('?' for _ in selected) + ')'}""",
                () if selected is None else tuple(sorted(selected)),
            ).fetchall()
            for row in provider_rows:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, json.JSONDecodeError):
                    metrics["invalid_values"] += 5
                    continue
                values: dict[str, int | None] = {}
                for native_field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS.values():
                    value, invalid = _parse_endpoint(payload.get(native_field))
                    values[native_field] = value
                    metrics["invalid_values"] += int(invalid)
                changed = [field for field, value in values.items() if row[field] != value]
                if changed:
                    conn.execute(
                        f"UPDATE provider_copy.sharadar_fundamental_observation SET {','.join(f'{field}=?' for field in changed)} WHERE observation_id=?",
                        (*[values[field] for field in changed], row["observation_id"]),
                    )
                    metrics["provider_rows_changed"] += 1
            metrics["stages"].append(_storage(conn, canonical_db, "provider_backfill", time.perf_counter() - started, int(metrics["provider_rows_changed"])))
            if inject_failure_at == "provider_backfill":
                raise RuntimeError("INJECTED_PHASE6A2_FAILURE")

            started = time.perf_counter()
            rows = conn.execute(
                f"""SELECT po.observation_id,po.company_id,s.*
                    FROM provider_copy.sharadar_fundamental_observation s
                    JOIN provider_copy.provider_observation po USING(observation_id)
                    WHERE s.dimension='ARQ'
                    ORDER BY s.ticker,s.fiscalperiod,s.reportperiod DESC,
                             COALESCE(s.lastupdated,s.date,'') DESC,po.observation_id"""
            ).fetchall()
            winners: dict[tuple[int, int, str], sqlite3.Row] = {}
            for row in rows:
                if row["company_id"] is None or selected is not None and int(row["company_id"]) not in selected:
                    continue
                try:
                    year, quarter = parse_fiscalperiod(row["fiscalperiod"])
                except ValueError:
                    continue
                winners.setdefault((int(row["company_id"]), year, quarter), row)

            for (company_id, year, quarter), winner in winners.items():
                canonical = conn.execute(
                    """SELECT f.* FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id)
                       WHERE q.company_id=? AND q.fiscal_year=? AND q.fiscal_quarter=?""",
                    (company_id, year, quarter),
                ).fetchone()
                if canonical is None:
                    continue
                quarter_id = int(canonical["quarter_id"])
                for canonical_field, native_field in OPERATING_WORKING_CAPITAL_NATIVE_FIELDS.items():
                    value = winner[native_field]
                    if canonical[canonical_field] != value:
                        conn.execute(f"UPDATE v4_quarter_financials SET {canonical_field}=? WHERE quarter_id=?", (value, quarter_id))
                        metrics["canonical_values_changed"] += 1
                    stale = conn.execute(
                        f"""DELETE FROM {OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE}
                            WHERE quarter_id=? AND canonical_field=?
                              AND (provider_observation_id<>? OR source_native_field<>?)""",
                        (quarter_id, canonical_field, winner["observation_id"], native_field),
                    ).rowcount
                    metrics["provenance_rows_removed"] += stale
                    if value is not None:
                        metrics["provenance_rows_added"] += write_provenance(
                            conn,
                            {
                                "quarter_id": quarter_id,
                                "canonical_field": canonical_field,
                                "provider": "SHARADAR",
                                "provider_observation_id": winner["observation_id"],
                                "source_native_field": native_field,
                                "transformation": "DIRECT",
                                "accepted_at_utc": applied_at_utc,
                                "rule_version": RULE_VERSION,
                                "confidence": "HIGH",
                            },
                            ignore_duplicate=True,
                        )
                    else:
                        removed = conn.execute(
                            f"DELETE FROM {OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE} WHERE quarter_id=? AND canonical_field=?",
                            (quarter_id, canonical_field),
                        ).rowcount
                        metrics["provenance_rows_removed"] += removed
            metrics["stages"].append(_storage(conn, canonical_db, "canonical_backfill", time.perf_counter() - started, int(metrics["canonical_values_changed"]) + int(metrics["provenance_rows_added"]) + int(metrics["provenance_rows_removed"])))
            if inject_failure_at == "canonical_backfill":
                raise RuntimeError("INJECTED_PHASE6A2_FAILURE")

            for schema, name in (("main", "fundamentals_v4"), ("provider_copy", "fundamentals_provider")):
                current = conn.execute(f"SELECT version FROM {schema}.schema_version WHERE db_name=?", (name,)).fetchone()
                if current is None or current[0] != SCHEMA_VERSION:
                    conn.execute(
                        f"INSERT OR REPLACE INTO {schema}.schema_version(db_name,version,applied_at_utc) VALUES (?,?,?)",
                        (name, SCHEMA_VERSION, applied_at_utc),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if conn.in_transaction:
                conn.rollback()
            conn.execute("DETACH DATABASE provider_copy")
    return metrics
