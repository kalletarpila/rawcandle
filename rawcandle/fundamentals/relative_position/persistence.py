from __future__ import annotations

import hashlib
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.relative_position.engine import (
    MINIMUM_PEERS,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    CoverageRecord,
    PeerScope,
    RelativeMeasure,
    RelativePositionResult,
    RelativeSnapshot,
    RelativeStatus,
    canonical_json,
    recalculate_result_fingerprint,
)


PERSISTENCE_SCHEMA_VERSION = "V4_RELATIVE_POSITION_CURRENT_SNAPSHOT_V1"
SEMANTIC_MODE = "CURRENT_REVISED_SNAPSHOT"
MAX_BULK_SNAPSHOTS_PER_MODEL = 2
MAX_AUDIT_ROWS_PER_MODEL = 64
PRODUCTION_ANALYSIS_DB = Path(
    "/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS relative_position_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    schema_version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relative_position_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK (semantic_mode='CURRENT_REVISED_SNAPSHOT'),
    snapshot_date TEXT NOT NULL,
    calculation_source_fingerprint TEXT NOT NULL,
    source_content_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('WRITING','COMPLETE')),
    result_row_count INTEGER NOT NULL CHECK (result_row_count>=0),
    coverage_row_count INTEGER NOT NULL CHECK (coverage_row_count>=0),
    ready_row_count INTEGER NOT NULL CHECK (ready_row_count>=0),
    created_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    UNIQUE(model_fingerprint,source_content_fingerprint)
);

CREATE TABLE IF NOT EXISTS relative_position_active_snapshot (
    model_fingerprint TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL UNIQUE
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE RESTRICT,
    activated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relative_position_result (
    relative_position_result_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    measure TEXT NOT NULL CHECK (measure IN ('FUNDAMENTAL_SCORE','ABSOLUTE_VALUATION_SCORE')),
    peer_scope TEXT NOT NULL CHECK (peer_scope IN ('UNIVERSE','SECTOR','INDUSTRY','ECOSYSTEM')),
    peer_group_id TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    source_observation_date TEXT NOT NULL,
    source_score REAL NOT NULL CHECK (source_score>=0 AND source_score<=100),
    percentile REAL CHECK (percentile IS NULL OR (percentile>=0 AND percentile<=100)),
    rank_low INTEGER NOT NULL CHECK (rank_low>=1),
    rank_high INTEGER NOT NULL CHECK (rank_high>=rank_low),
    average_rank REAL NOT NULL,
    peer_count INTEGER NOT NULL CHECK (peer_count>=1),
    tie_count INTEGER NOT NULL CHECK (tie_count>=1),
    result_status TEXT NOT NULL CHECK (result_status IN ('RELATIVE_POSITION_READY','PEER_GROUP_TOO_SMALL')),
    reason_code TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    UNIQUE(snapshot_id,company_id,measure,peer_scope,peer_group_id)
);

CREATE TABLE IF NOT EXISTS relative_position_coverage (
    relative_position_coverage_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE CASCADE,
    source_observation_id TEXT NOT NULL,
    company_id INTEGER,
    measure TEXT NOT NULL CHECK (measure IN ('FUNDAMENTAL_SCORE','ABSOLUTE_VALUATION_SCORE')),
    peer_scope TEXT NOT NULL CHECK (peer_scope IN ('UNIVERSE','SECTOR','INDUSTRY','ECOSYSTEM')),
    peer_group_id TEXT NOT NULL DEFAULT '',
    coverage_status TEXT NOT NULL CHECK (coverage_status IN (
        'RELATIVE_POSITION_READY','SOURCE_MEASURE_NOT_ELIGIBLE',
        'PEER_CLASSIFICATION_MISSING','NOT_ECOSYSTEM_MEMBER',
        'PEER_GROUP_TOO_SMALL','INVALID_SOURCE_VALUE','IDENTITY_MAPPING_UNRESOLVED'
    )),
    reason_code TEXT NOT NULL,
    peer_count INTEGER CHECK (peer_count IS NULL OR peer_count>=0),
    UNIQUE(snapshot_id,source_observation_id,measure,peer_scope,peer_group_id)
);

CREATE TABLE IF NOT EXISTS relative_position_refresh_audit (
    refresh_audit_id INTEGER PRIMARY KEY,
    model_fingerprint TEXT NOT NULL,
    checked_at_utc TEXT NOT NULL,
    requested_snapshot_date TEXT NOT NULL,
    calculation_source_fingerprint TEXT NOT NULL,
    source_content_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('ACTIVATED','NO_CHANGE')),
    active_snapshot_id TEXT NOT NULL
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_relative_position_snapshot_model
    ON relative_position_snapshot(model_fingerprint,status,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_relative_position_result_company
    ON relative_position_result(snapshot_id,company_id,measure,peer_scope);
CREATE INDEX IF NOT EXISTS idx_relative_position_result_group
    ON relative_position_result(snapshot_id,measure,peer_scope,peer_group_id,company_id);
CREATE INDEX IF NOT EXISTS idx_relative_position_coverage_company
    ON relative_position_coverage(snapshot_id,company_id,measure,peer_scope);
CREATE INDEX IF NOT EXISTS idx_relative_position_audit_model
    ON relative_position_refresh_audit(model_fingerprint,refresh_audit_id DESC);
"""


@dataclass(frozen=True)
class ApplyReport:
    snapshot_id: str
    source_content_fingerprint: str
    result_fingerprint: str
    result_rows_inserted: int
    result_rows_deleted: int
    result_rows_unchanged: int
    coverage_rows_inserted: int
    coverage_rows_deleted: int
    coverage_rows_unchanged: int
    activation_changes: int
    snapshots_inserted: int
    snapshots_deleted: int
    audit_rows_inserted: int
    active_snapshot_count: int
    retained_snapshot_count: int
    outcome: str


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def schema_signature(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    names = (
        "relative_position_schema_meta",
        "relative_position_snapshot",
        "relative_position_active_snapshot",
        "relative_position_result",
        "relative_position_coverage",
        "relative_position_refresh_audit",
        "idx_relative_position_snapshot_model",
        "idx_relative_position_result_company",
        "idx_relative_position_result_group",
        "idx_relative_position_coverage_company",
        "idx_relative_position_audit_model",
    )
    placeholders = ",".join("?" for _ in names)
    return [tuple(row) for row in conn.execute(
        f"SELECT type,name,sql FROM sqlite_schema WHERE name IN ({placeholders}) ORDER BY type,name",
        names,
    )]


def ensure_schema(conn: sqlite3.Connection, *, applied_at_utc: str) -> None:
    for statement in (part.strip() for part in SCHEMA_SQL.split(";")):
        if statement:
            conn.execute(statement)
    row = conn.execute(
        "SELECT schema_version FROM relative_position_schema_meta WHERE singleton=1"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO relative_position_schema_meta(singleton,schema_version,applied_at_utc) VALUES (1,?,?)",
            (PERSISTENCE_SCHEMA_VERSION, applied_at_utc),
        )
    elif str(row[0]) != PERSISTENCE_SCHEMA_VERSION:
        conn.execute(
            "UPDATE relative_position_schema_meta SET schema_version=?,applied_at_utc=? WHERE singleton=1",
            (PERSISTENCE_SCHEMA_VERSION, applied_at_utc),
        )


def migrate_analysis_copy(
    analysis_db: Path,
    *,
    applied_at_utc: str,
) -> dict[str, Any]:
    resolved = analysis_db.resolve()
    if resolved == PRODUCTION_ANALYSIS_DB.resolve():
        raise PermissionError("PHASE4C_PRODUCTION_SCHEMA_MIGRATION_BLOCKED")
    if analysis_db.is_symlink():
        raise PermissionError("PHASE4C_SYMLINK_DESTINATION_BLOCKED")
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    before = schema_signature(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at_utc)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    after = schema_signature(conn)
    quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    foreign_keys = len(list(conn.execute("PRAGMA foreign_key_check")))
    conn.close()
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "objects_before": len(before),
        "objects_after": len(after),
        "objects_added": len(after) - len(before),
        "quick_check": quick,
        "foreign_key_violations": foreign_keys,
    }


def source_content_fingerprint(snapshot: RelativeSnapshot) -> str:
    results: list[dict[str, Any]] = []
    for result in snapshot.results:
        row = result.to_dict()
        for field in (
            "snapshot_date", "source_fingerprint", "model_version", "model_fingerprint"
        ):
            row.pop(field, None)
        results.append(row)
    coverage: list[dict[str, Any]] = []
    for record in snapshot.coverage:
        row = record.to_dict()
        row.pop("snapshot_date", None)
        coverage.append(row)
    return _hash({
        "model_fingerprint": snapshot.model_fingerprint,
        "semantic_mode": snapshot.semantic_mode,
        "results": results,
        "coverage": coverage,
    })


def _result_key(result: RelativePositionResult) -> tuple[str, str, str, int]:
    return (
        _enum_value(result.measure),
        _enum_value(result.peer_scope),
        result.peer_group_id,
        result.company_id,
    )


def _coverage_key(record: CoverageRecord) -> tuple[str, int, str, str, str]:
    return (
        _enum_value(record.measure),
        record.company_id if record.company_id is not None else -1,
        _enum_value(record.peer_scope),
        record.peer_group_id or "",
        record.source_observation_id,
    )


def validate_snapshot(snapshot: RelativeSnapshot) -> None:
    if snapshot.model_version != MODEL_VERSION or snapshot.model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("RELATIVE_POSITION_MODEL_IDENTITY_MISMATCH")
    if snapshot.semantic_mode != SEMANTIC_MODE:
        raise ValueError("RELATIVE_POSITION_SEMANTIC_MODE_MISMATCH")
    if snapshot.result_fingerprint != recalculate_result_fingerprint(snapshot):
        raise ValueError("RELATIVE_POSITION_RESULT_FINGERPRINT_MISMATCH")
    if tuple(sorted(snapshot.results, key=_result_key)) != snapshot.results:
        raise ValueError("RELATIVE_POSITION_RESULTS_NOT_DETERMINISTICALLY_ORDERED")
    if tuple(sorted(snapshot.coverage, key=_coverage_key)) != snapshot.coverage:
        raise ValueError("RELATIVE_POSITION_COVERAGE_NOT_DETERMINISTICALLY_ORDERED")

    result_keys: set[tuple[int, str, str, str]] = set()
    coverage_keys: set[tuple[str, str, str, str]] = set()
    results_by_group: dict[tuple[str, str, str], list[RelativePositionResult]] = defaultdict(list)
    results_by_coverage_key: dict[tuple[str, str, str, str], RelativePositionResult] = {}
    coverage_scopes: dict[tuple[str, str], set[str]] = defaultdict(set)
    measures_seen: set[str] = set()

    for result in snapshot.results:
        measure = _enum_value(result.measure)
        scope = _enum_value(result.peer_scope)
        status = _enum_value(result.status)
        if measure not in {item.value for item in RelativeMeasure}:
            raise ValueError("RELATIVE_POSITION_MEASURE_INVALID")
        if scope not in {item.value for item in PeerScope}:
            raise ValueError("RELATIVE_POSITION_SCOPE_INVALID")
        if status not in {RelativeStatus.READY.value, RelativeStatus.PEER_GROUP_TOO_SMALL.value}:
            raise ValueError("RELATIVE_POSITION_RESULT_STATUS_INVALID")
        if (
            result.model_version != MODEL_VERSION
            or result.model_fingerprint != MODEL_FINGERPRINT
            or result.snapshot_date != snapshot.snapshot_date
            or result.source_fingerprint != snapshot.source_fingerprint
        ):
            raise ValueError("RELATIVE_POSITION_RESULT_SNAPSHOT_MISMATCH")
        numbers = (result.score, result.average_rank)
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in numbers):
            raise ValueError("RELATIVE_POSITION_RESULT_NONFINITE")
        if not 0 <= result.score <= 100:
            raise ValueError("RELATIVE_POSITION_SOURCE_SCORE_INVALID")
        if result.percentile is not None and (
            isinstance(result.percentile, bool)
            or not math.isfinite(float(result.percentile))
            or not 0 <= result.percentile <= 100
        ):
            raise ValueError("RELATIVE_POSITION_PERCENTILE_INVALID")
        if not (
            1 <= result.rank_low <= result.rank_high <= result.peer_count
            and result.tie_count == result.rank_high - result.rank_low + 1
            and math.isclose(
                result.average_rank,
                (result.rank_low + result.rank_high) / 2.0,
                abs_tol=0.0,
            )
        ):
            raise ValueError("RELATIVE_POSITION_TIE_METADATA_INVALID")
        minimum = MINIMUM_PEERS[PeerScope(scope)]
        if status == RelativeStatus.READY.value:
            if result.peer_count < minimum or result.percentile is None:
                raise ValueError("RELATIVE_POSITION_READY_MINIMUM_INVALID")
        elif result.peer_count >= minimum or result.percentile is not None:
            raise ValueError("RELATIVE_POSITION_TOO_SMALL_CONTRACT_INVALID")
        identity = (result.company_id, measure, scope, result.peer_group_id)
        if identity in result_keys:
            raise ValueError(f"DUPLICATE_RELATIVE_POSITION_RESULT:{identity}")
        result_keys.add(identity)
        coverage_identity = (
            result.source_observation_id, measure, scope, result.peer_group_id
        )
        results_by_coverage_key[coverage_identity] = result
        results_by_group[(measure, scope, result.peer_group_id)].append(result)
        measures_seen.add(measure)

    for group, rows in results_by_group.items():
        peer_counts = {row.peer_count for row in rows}
        if peer_counts != {len(rows)}:
            raise ValueError(f"RELATIVE_POSITION_GROUP_INCOMPLETE:{group}")
        ordered_scores = sorted(row.score for row in rows)
        for row in rows:
            low = 1 + sum(value < row.score for value in ordered_scores)
            high = sum(value <= row.score for value in ordered_scores)
            expected_percentile = (
                100.0 * (((low + high) / 2.0) - 1.0) / (len(rows) - 1.0)
                if len(rows) >= MINIMUM_PEERS[PeerScope(group[1])]
                else None
            )
            if (row.rank_low, row.rank_high) != (low, high):
                raise ValueError("RELATIVE_POSITION_RANK_BOUNDARY_INVALID")
            if expected_percentile is None:
                if row.percentile is not None:
                    raise ValueError("RELATIVE_POSITION_UNEXPECTED_PERCENTILE")
            elif not math.isclose(float(row.percentile), expected_percentile, abs_tol=1e-12):
                raise ValueError("RELATIVE_POSITION_PERCENTILE_FORMULA_MISMATCH")

    for record in snapshot.coverage:
        measure = _enum_value(record.measure)
        scope = _enum_value(record.peer_scope)
        status = _enum_value(record.status)
        if measure not in {item.value for item in RelativeMeasure}:
            raise ValueError("RELATIVE_POSITION_COVERAGE_MEASURE_INVALID")
        if scope not in {item.value for item in PeerScope}:
            raise ValueError("RELATIVE_POSITION_COVERAGE_SCOPE_INVALID")
        if status not in {item.value for item in RelativeStatus}:
            raise ValueError("RELATIVE_POSITION_COVERAGE_STATUS_INVALID")
        if record.snapshot_date != snapshot.snapshot_date:
            raise ValueError("RELATIVE_POSITION_COVERAGE_SNAPSHOT_MISMATCH")
        group_id = record.peer_group_id or ""
        identity = (record.source_observation_id, measure, scope, group_id)
        if identity in coverage_keys:
            raise ValueError(f"DUPLICATE_RELATIVE_POSITION_COVERAGE:{identity}")
        coverage_keys.add(identity)
        coverage_scopes[(record.source_observation_id, measure)].add(scope)
        result = results_by_coverage_key.get(identity)
        result_status = _enum_value(result.status) if result is not None else None
        if status in {RelativeStatus.READY.value, RelativeStatus.PEER_GROUP_TOO_SMALL.value}:
            if result is None or result_status != status or result.peer_count != record.peer_count:
                raise ValueError("RELATIVE_POSITION_RESULT_COVERAGE_MISMATCH")
        elif result is not None:
            raise ValueError("RELATIVE_POSITION_UNAVAILABLE_HAS_RESULT")
        measures_seen.add(measure)

    required_scopes = {item.value for item in PeerScope}
    for identity, scopes in coverage_scopes.items():
        if scopes != required_scopes:
            raise ValueError(f"RELATIVE_POSITION_PARTIAL_SOURCE_COVERAGE:{identity}:{sorted(scopes)}")
    if measures_seen != {item.value for item in RelativeMeasure}:
        raise ValueError("RELATIVE_POSITION_COMPLETE_SNAPSHOT_REQUIRES_BOTH_MEASURES")


def _snapshot_id(model_fingerprint: str, content_fingerprint: str) -> str:
    return _hash({"model_fingerprint": model_fingerprint, "content": content_fingerprint})


def _insert_audit(
    conn: sqlite3.Connection,
    snapshot: RelativeSnapshot,
    content_fingerprint: str,
    active_snapshot_id: str,
    *,
    checked_at_utc: str,
    outcome: str,
) -> None:
    conn.execute(
        """INSERT INTO relative_position_refresh_audit(
               model_fingerprint,checked_at_utc,requested_snapshot_date,
               calculation_source_fingerprint,source_content_fingerprint,
               result_fingerprint,outcome,active_snapshot_id
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            snapshot.model_fingerprint,
            checked_at_utc,
            snapshot.snapshot_date,
            snapshot.source_fingerprint,
            content_fingerprint,
            snapshot.result_fingerprint,
            outcome,
            active_snapshot_id,
        ),
    )
    conn.execute(
        """DELETE FROM relative_position_refresh_audit
            WHERE model_fingerprint=? AND refresh_audit_id NOT IN (
                SELECT refresh_audit_id FROM relative_position_refresh_audit
                WHERE model_fingerprint=? ORDER BY refresh_audit_id DESC LIMIT ?
            )""",
        (snapshot.model_fingerprint, snapshot.model_fingerprint, MAX_AUDIT_ROWS_PER_MODEL),
    )


def _result_values(snapshot_id: str, result: RelativePositionResult) -> tuple[Any, ...]:
    return (
        snapshot_id,
        result.company_id,
        result.security_id,
        result.ticker,
        _enum_value(result.measure),
        _enum_value(result.peer_scope),
        result.peer_group_id,
        result.source_observation_id,
        result.source_observation_date,
        result.score,
        result.percentile,
        result.rank_low,
        result.rank_high,
        result.average_rank,
        result.peer_count,
        result.tie_count,
        _enum_value(result.status),
        result.reason_code,
        result.model_version,
        result.model_fingerprint,
    )


def _coverage_values(snapshot_id: str, record: CoverageRecord) -> tuple[Any, ...]:
    return (
        snapshot_id,
        record.source_observation_id,
        record.company_id,
        _enum_value(record.measure),
        _enum_value(record.peer_scope),
        record.peer_group_id or "",
        _enum_value(record.status),
        record.reason_code,
        record.peer_count,
    )


def apply_snapshot(
    conn: sqlite3.Connection,
    snapshot: RelativeSnapshot,
    *,
    applied_at_utc: str,
    inject_failure_at: str | None = None,
) -> ApplyReport:
    validate_snapshot(snapshot)
    if conn.in_transaction:
        raise RuntimeError("RELATIVE_POSITION_APPLY_REQUIRES_CLEAN_TRANSACTION")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if conn.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='relative_position_snapshot'"
    ).fetchone() is None:
        raise RuntimeError("RELATIVE_POSITION_SCHEMA_NOT_MIGRATED")
    content_fp = source_content_fingerprint(snapshot)
    new_snapshot_id = _snapshot_id(snapshot.model_fingerprint, content_fp)
    active = conn.execute(
        """SELECT a.snapshot_id,s.source_content_fingerprint
             FROM relative_position_active_snapshot a
             JOIN relative_position_snapshot s ON s.snapshot_id=a.snapshot_id
            WHERE a.model_fingerprint=? AND s.status='COMPLETE'""",
        (snapshot.model_fingerprint,),
    ).fetchone()
    if active is not None and str(active["source_content_fingerprint"]) == content_fp:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _insert_audit(
                conn,
                snapshot,
                content_fp,
                str(active["snapshot_id"]),
                checked_at_utc=applied_at_utc,
                outcome="NO_CHANGE",
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        retained = int(conn.execute(
            "SELECT COUNT(*) FROM relative_position_snapshot WHERE model_fingerprint=?",
            (snapshot.model_fingerprint,),
        ).fetchone()[0])
        return ApplyReport(
            snapshot_id=str(active["snapshot_id"]),
            source_content_fingerprint=content_fp,
            result_fingerprint=str(conn.execute(
                "SELECT result_fingerprint FROM relative_position_snapshot WHERE snapshot_id=?",
                (active["snapshot_id"],),
            ).fetchone()[0]),
            result_rows_inserted=0,
            result_rows_deleted=0,
            result_rows_unchanged=len(snapshot.results),
            coverage_rows_inserted=0,
            coverage_rows_deleted=0,
            coverage_rows_unchanged=len(snapshot.coverage),
            activation_changes=0,
            snapshots_inserted=0,
            snapshots_deleted=0,
            audit_rows_inserted=1,
            active_snapshot_count=1,
            retained_snapshot_count=retained,
            outcome="NO_CHANGE",
        )

    previous_active_id = str(active["snapshot_id"]) if active is not None else None
    result_deleted = coverage_deleted = snapshots_deleted = 0
    result_inserted = coverage_inserted = snapshots_inserted = 0
    existing_snapshot_reused = False
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT snapshot_id,status FROM relative_position_snapshot WHERE model_fingerprint=? AND source_content_fingerprint=?",
            (snapshot.model_fingerprint, content_fp),
        ).fetchone()
        if existing is None:
            conn.execute(
                """INSERT INTO relative_position_snapshot(
                       snapshot_id,model_version,model_fingerprint,semantic_mode,snapshot_date,
                       calculation_source_fingerprint,source_content_fingerprint,result_fingerprint,
                       status,result_row_count,coverage_row_count,ready_row_count,
                       created_at_utc,completed_at_utc
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (
                    new_snapshot_id,
                    snapshot.model_version,
                    snapshot.model_fingerprint,
                    snapshot.semantic_mode,
                    snapshot.snapshot_date,
                    snapshot.source_fingerprint,
                    content_fp,
                    snapshot.result_fingerprint,
                    "WRITING",
                    len(snapshot.results),
                    len(snapshot.coverage),
                    sum(result.status == RelativeStatus.READY for result in snapshot.results),
                    applied_at_utc,
                ),
            )
            snapshots_inserted = 1
            if inject_failure_at == "metadata":
                raise RuntimeError("INJECTED_RELATIVE_POSITION_METADATA_FAILURE")
            conn.executemany(
                """INSERT INTO relative_position_result(
                       snapshot_id,company_id,security_id,ticker,measure,peer_scope,
                       peer_group_id,source_observation_id,source_observation_date,
                       source_score,percentile,rank_low,rank_high,average_rank,
                       peer_count,tie_count,result_status,reason_code,model_version,model_fingerprint
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [_result_values(new_snapshot_id, result) for result in snapshot.results],
            )
            result_inserted = len(snapshot.results)
            if inject_failure_at == "results":
                raise RuntimeError("INJECTED_RELATIVE_POSITION_RESULT_FAILURE")
            conn.executemany(
                """INSERT INTO relative_position_coverage(
                       snapshot_id,source_observation_id,company_id,measure,peer_scope,
                       peer_group_id,coverage_status,reason_code,peer_count
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                [_coverage_values(new_snapshot_id, record) for record in snapshot.coverage],
            )
            coverage_inserted = len(snapshot.coverage)
            conn.execute(
                "UPDATE relative_position_snapshot SET status='COMPLETE',completed_at_utc=? WHERE snapshot_id=? AND status='WRITING'",
                (applied_at_utc, new_snapshot_id),
            )
        elif str(existing["status"]) != "COMPLETE":
            raise RuntimeError("RELATIVE_POSITION_EXISTING_SNAPSHOT_INCOMPLETE")
        else:
            new_snapshot_id = str(existing["snapshot_id"])
            existing_snapshot_reused = True

        stored = _load_snapshot(conn, new_snapshot_id)
        if stored is None:
            raise RuntimeError("RELATIVE_POSITION_STORED_SNAPSHOT_MISSING")
        validate_snapshot(stored)
        if source_content_fingerprint(stored) != content_fp:
            raise RuntimeError("RELATIVE_POSITION_STORED_CONTENT_FINGERPRINT_MISMATCH")
        if inject_failure_at == "before_activation":
            raise RuntimeError("INJECTED_RELATIVE_POSITION_PRE_ACTIVATION_FAILURE")

        if active is None:
            conn.execute(
                "INSERT INTO relative_position_active_snapshot(model_fingerprint,snapshot_id,activated_at_utc) VALUES (?,?,?)",
                (snapshot.model_fingerprint, new_snapshot_id, applied_at_utc),
            )
        else:
            conn.execute(
                "UPDATE relative_position_active_snapshot SET snapshot_id=?,activated_at_utc=? WHERE model_fingerprint=?",
                (new_snapshot_id, applied_at_utc, snapshot.model_fingerprint),
            )

        keep = [new_snapshot_id]
        if previous_active_id is not None and previous_active_id != new_snapshot_id:
            keep.append(previous_active_id)
        placeholders = ",".join("?" for _ in keep)
        obsolete = [dict(row) for row in conn.execute(
            f"""SELECT snapshot_id,
                       (SELECT COUNT(*) FROM relative_position_result r WHERE r.snapshot_id=s.snapshot_id) result_rows,
                       (SELECT COUNT(*) FROM relative_position_coverage c WHERE c.snapshot_id=s.snapshot_id) coverage_rows
                  FROM relative_position_snapshot s
                 WHERE model_fingerprint=? AND snapshot_id NOT IN ({placeholders})""",
            (snapshot.model_fingerprint, *keep),
        )]
        result_deleted = sum(int(row["result_rows"]) for row in obsolete)
        coverage_deleted = sum(int(row["coverage_rows"]) for row in obsolete)
        for row in obsolete:
            conn.execute(
                "DELETE FROM relative_position_snapshot WHERE snapshot_id=?",
                (row["snapshot_id"],),
            )
        snapshots_deleted = len(obsolete)
        if inject_failure_at == "cleanup":
            raise RuntimeError("INJECTED_RELATIVE_POSITION_CLEANUP_FAILURE")
        _insert_audit(
            conn,
            snapshot,
            content_fp,
            new_snapshot_id,
            checked_at_utc=applied_at_utc,
            outcome="ACTIVATED",
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    retained = int(conn.execute(
        "SELECT COUNT(*) FROM relative_position_snapshot WHERE model_fingerprint=?",
        (snapshot.model_fingerprint,),
    ).fetchone()[0])
    stored_result_fingerprint = str(conn.execute(
        "SELECT result_fingerprint FROM relative_position_snapshot WHERE snapshot_id=?",
        (new_snapshot_id,),
    ).fetchone()[0])
    return ApplyReport(
        snapshot_id=new_snapshot_id,
        source_content_fingerprint=content_fp,
        result_fingerprint=stored_result_fingerprint,
        result_rows_inserted=result_inserted,
        result_rows_deleted=result_deleted,
        result_rows_unchanged=len(snapshot.results) if existing_snapshot_reused else 0,
        coverage_rows_inserted=coverage_inserted,
        coverage_rows_deleted=coverage_deleted,
        coverage_rows_unchanged=len(snapshot.coverage) if existing_snapshot_reused else 0,
        activation_changes=1,
        snapshots_inserted=snapshots_inserted,
        snapshots_deleted=snapshots_deleted,
        audit_rows_inserted=1,
        active_snapshot_count=1,
        retained_snapshot_count=retained,
        outcome="ACTIVATED",
    )


def _load_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> RelativeSnapshot | None:
    metadata = conn.execute(
        "SELECT * FROM relative_position_snapshot WHERE snapshot_id=? AND status='COMPLETE'",
        (snapshot_id,),
    ).fetchone()
    if metadata is None:
        return None
    results = tuple(RelativePositionResult(
        model_version=str(row["model_version"]),
        model_fingerprint=str(row["model_fingerprint"]),
        snapshot_date=str(metadata["snapshot_date"]),
        source_fingerprint=str(metadata["calculation_source_fingerprint"]),
        company_id=int(row["company_id"]),
        security_id=int(row["security_id"]) if row["security_id"] is not None else None,
        ticker=row["ticker"],
        measure=RelativeMeasure(str(row["measure"])),
        peer_scope=PeerScope(str(row["peer_scope"])),
        peer_group_id=str(row["peer_group_id"]),
        source_observation_id=str(row["source_observation_id"]),
        source_observation_date=str(row["source_observation_date"]),
        score=float(row["source_score"]),
        percentile=float(row["percentile"]) if row["percentile"] is not None else None,
        rank_low=int(row["rank_low"]),
        rank_high=int(row["rank_high"]),
        average_rank=float(row["average_rank"]),
        peer_count=int(row["peer_count"]),
        tie_count=int(row["tie_count"]),
        status=RelativeStatus(str(row["result_status"])),
        reason_code=str(row["reason_code"]),
    ) for row in conn.execute(
        """SELECT * FROM relative_position_result WHERE snapshot_id=?
            ORDER BY measure,peer_scope,peer_group_id,company_id""",
        (snapshot_id,),
    ))
    coverage = tuple(CoverageRecord(
        snapshot_date=str(metadata["snapshot_date"]),
        source_observation_id=str(row["source_observation_id"]),
        company_id=int(row["company_id"]) if row["company_id"] is not None else None,
        measure=RelativeMeasure(str(row["measure"])),
        peer_scope=PeerScope(str(row["peer_scope"])),
        peer_group_id=str(row["peer_group_id"]) or None,
        status=RelativeStatus(str(row["coverage_status"])),
        reason_code=str(row["reason_code"]),
        peer_count=int(row["peer_count"]) if row["peer_count"] is not None else None,
    ) for row in conn.execute(
        """SELECT * FROM relative_position_coverage WHERE snapshot_id=?
            ORDER BY measure,COALESCE(company_id,-1),peer_scope,peer_group_id,source_observation_id""",
        (snapshot_id,),
    ))
    return RelativeSnapshot(
        model_version=str(metadata["model_version"]),
        model_fingerprint=str(metadata["model_fingerprint"]),
        semantic_mode=str(metadata["semantic_mode"]),
        snapshot_date=str(metadata["snapshot_date"]),
        source_fingerprint=str(metadata["calculation_source_fingerprint"]),
        result_fingerprint=str(metadata["result_fingerprint"]),
        results=results,
        coverage=coverage,
    )


class RelativePositionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def active_metadata(self, *, model_fingerprint: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT s.*,
                      (SELECT MAX(requested_snapshot_date)
                         FROM relative_position_refresh_audit a
                        WHERE a.model_fingerprint=s.model_fingerprint) AS validated_through_date
                 FROM relative_position_active_snapshot p
                 JOIN relative_position_snapshot s ON s.snapshot_id=p.snapshot_id
                WHERE p.model_fingerprint=? AND s.model_fingerprint=? AND s.status='COMPLETE'""",
            (model_fingerprint, model_fingerprint),
        ).fetchone()
        return dict(row) if row else None

    def current_company(
        self, company_id: int, *, model_fingerprint: str
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            """SELECT r.*,s.snapshot_date,s.calculation_source_fingerprint,
                      s.result_fingerprint
                 FROM relative_position_result r
                 JOIN relative_position_active_snapshot p ON p.snapshot_id=r.snapshot_id
                 JOIN relative_position_snapshot s ON s.snapshot_id=r.snapshot_id
                WHERE p.model_fingerprint=? AND r.model_fingerprint=? AND r.company_id=?
                  AND s.status='COMPLETE'
                ORDER BY r.measure,r.peer_scope,r.peer_group_id""",
            (model_fingerprint, model_fingerprint, company_id),
        )]

    def company_scope(
        self,
        company_id: int,
        *,
        model_fingerprint: str,
        measure: str,
        peer_scope: str,
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            """SELECT r.*,s.snapshot_date,s.calculation_source_fingerprint,
                      s.result_fingerprint
                 FROM relative_position_result r
                 JOIN relative_position_active_snapshot p ON p.snapshot_id=r.snapshot_id
                 JOIN relative_position_snapshot s ON s.snapshot_id=r.snapshot_id
                WHERE p.model_fingerprint=? AND r.model_fingerprint=? AND r.company_id=?
                  AND r.measure=? AND r.peer_scope=? AND s.status='COMPLETE'
                ORDER BY r.peer_group_id""",
            (model_fingerprint, model_fingerprint, company_id, measure, peer_scope),
        )]

    def current_universe(
        self, *, model_fingerprint: str, measure: str, peer_scope: str
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            """SELECT r.*,s.snapshot_date,s.calculation_source_fingerprint,
                      s.result_fingerprint
                 FROM relative_position_result r
                 JOIN relative_position_active_snapshot p ON p.snapshot_id=r.snapshot_id
                 JOIN relative_position_snapshot s ON s.snapshot_id=r.snapshot_id
                WHERE p.model_fingerprint=? AND r.model_fingerprint=?
                  AND r.measure=? AND r.peer_scope=? AND s.status='COMPLETE'
                ORDER BY r.peer_group_id,r.company_id""",
            (model_fingerprint, model_fingerprint, measure, peer_scope),
        )]

    def peer_group(
        self,
        *,
        model_fingerprint: str,
        measure: str,
        peer_scope: str,
        peer_group_id: str,
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            """SELECT r.*,s.snapshot_date,s.calculation_source_fingerprint,
                      s.result_fingerprint
                 FROM relative_position_result r
                 JOIN relative_position_active_snapshot p ON p.snapshot_id=r.snapshot_id
                 JOIN relative_position_snapshot s ON s.snapshot_id=r.snapshot_id
                WHERE p.model_fingerprint=? AND r.model_fingerprint=?
                  AND r.measure=? AND r.peer_scope=? AND r.peer_group_id=?
                  AND s.status='COMPLETE'
                ORDER BY r.company_id""",
            (model_fingerprint, model_fingerprint, measure, peer_scope, peer_group_id),
        )]

    def explain_unavailable(
        self,
        company_id: int,
        *,
        model_fingerprint: str,
        measure: str,
        peer_scope: str,
    ) -> list[dict[str, Any]]:
        results = self.company_scope(
            company_id,
            model_fingerprint=model_fingerprint,
            measure=measure,
            peer_scope=peer_scope,
        )
        if results:
            return results
        return [dict(row) for row in self.conn.execute(
            """SELECT c.*,s.snapshot_date,s.calculation_source_fingerprint,
                      s.result_fingerprint
                 FROM relative_position_coverage c
                 JOIN relative_position_active_snapshot p ON p.snapshot_id=c.snapshot_id
                 JOIN relative_position_snapshot s ON s.snapshot_id=c.snapshot_id
                WHERE p.model_fingerprint=? AND c.company_id=?
                  AND c.measure=? AND c.peer_scope=?
                  AND s.status='COMPLETE'
                ORDER BY c.peer_group_id,c.source_observation_id""",
            (model_fingerprint, company_id, measure, peer_scope),
        )]


def quick_check(
    conn: sqlite3.Connection,
    *,
    model_fingerprint: str,
    expected_snapshot: RelativeSnapshot | None = None,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    details: list[str] = []
    active_rows = [dict(row) for row in conn.execute(
        "SELECT * FROM relative_position_active_snapshot WHERE model_fingerprint=?",
        (model_fingerprint,),
    )]
    if len(active_rows) != 1:
        details.append(f"ACTIVE_SNAPSHOT_COUNT:{len(active_rows)}")
        stored = None
    else:
        stored = _load_snapshot(conn, str(active_rows[0]["snapshot_id"]))
        if stored is None:
            details.append("ACTIVE_SNAPSHOT_NOT_COMPLETE")
    if stored is not None:
        try:
            validate_snapshot(stored)
        except Exception as exc:
            details.append(f"SNAPSHOT_VALIDATION:{exc}")
        metadata = conn.execute(
            "SELECT * FROM relative_position_snapshot WHERE snapshot_id=?",
            (active_rows[0]["snapshot_id"],),
        ).fetchone()
        if metadata is not None:
            if int(metadata["result_row_count"]) != len(stored.results):
                details.append("RESULT_ROW_COUNT_MISMATCH")
            if int(metadata["coverage_row_count"]) != len(stored.coverage):
                details.append("COVERAGE_ROW_COUNT_MISMATCH")
            ready_rows = sum(
                result.status == RelativeStatus.READY for result in stored.results
            )
            if int(metadata["ready_row_count"]) != ready_rows:
                details.append("READY_ROW_COUNT_MISMATCH")
            if str(metadata["source_content_fingerprint"]) != source_content_fingerprint(stored):
                details.append("SOURCE_CONTENT_FINGERPRINT_MISMATCH")
        if expected_snapshot is not None:
            if source_content_fingerprint(stored) != source_content_fingerprint(expected_snapshot):
                details.append("EXPECTED_SNAPSHOT_CONTENT_MISMATCH")
    duplicate_results = int(conn.execute(
        """SELECT COUNT(*) FROM (
               SELECT snapshot_id,company_id,measure,peer_scope,peer_group_id,COUNT(*) n
                 FROM relative_position_result GROUP BY 1,2,3,4,5 HAVING n>1
           )"""
    ).fetchone()[0])
    if duplicate_results:
        details.append("DUPLICATE_LOGICAL_RESULTS")
    taxonomy_layer = int(conn.execute(
        "SELECT COUNT(*) FROM relative_position_result WHERE peer_scope NOT IN ('UNIVERSE','SECTOR','INDUSTRY','ECOSYSTEM')"
    ).fetchone()[0])
    if taxonomy_layer:
        details.append("INVALID_PEER_SCOPE")
    sqlite_result = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    foreign_keys = len(list(conn.execute("PRAGMA foreign_key_check")))
    if sqlite_result.lower() != "ok":
        details.append(f"SQLITE_QUICK_CHECK:{sqlite_result}")
    if foreign_keys:
        details.append("FOREIGN_KEY_VIOLATIONS")
    if RelativePositionRepository(conn).active_metadata(
        model_fingerprint="WRONG_FINGERPRINT"
    ) is not None:
        details.append("WRONG_FINGERPRINT_RESOLVED")
    retained = int(conn.execute(
        "SELECT COUNT(*) FROM relative_position_snapshot WHERE model_fingerprint=?",
        (model_fingerprint,),
    ).fetchone()[0])
    if retained > MAX_BULK_SNAPSHOTS_PER_MODEL:
        details.append(f"RETENTION_LIMIT_EXCEEDED:{retained}")
    return {
        "ok": not details,
        "details": details,
        "active_snapshot_count": len(active_rows),
        "retained_snapshot_count": retained,
        "result_rows": len(stored.results) if stored else 0,
        "coverage_rows": len(stored.coverage) if stored else 0,
        "sqlite_quick_check": sqlite_result,
        "foreign_key_violations": foreign_keys,
        "active_result_fingerprint": stored.result_fingerprint if stored else None,
        "active_source_content_fingerprint": (
            source_content_fingerprint(stored) if stored else None
        ),
    }
