from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.delta.context import (
    LIFECYCLE_CONTEXT_FINGERPRINT,
    VALUATION_DIAGNOSTIC_FINGERPRINT,
)
from rawcandle.fundamentals.delta.engine import (
    COMPONENT_MAXIMA,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    RECONCILIATION_TOLERANCE,
    SEMANTIC_MODE,
    DeltaStatus,
    Horizon,
    canonical_json,
    calculate_fundamental_delta,
    fingerprint,
)
from rawcandle.fundamentals.delta.context import (
    calculate_lifecycle_context,
    calculate_valuation_diagnostic,
)
from rawcandle.fundamentals.delta.source import DeltaSource
from rawcandle.fundamentals.lifecycle.engine import LifecycleState, LifecycleStatus


PERSISTENCE_VERSION = "V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2"
RETIRED_PERSISTENCE_VERSION = "V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V1"
LAYOUT_FINGERPRINT = fingerprint({
    "persistence_version": PERSISTENCE_VERSION,
    "tables": {
        "package": "normalized metadata and aggregate provenance",
        "status": tuple(status.value for status in DeltaStatus),
        "reason": "normalized reason codebook",
        "component_type": tuple(COMPONENT_MAXIMA.items()),
        "result": "compact three-horizon endpoint",
        "component": "WITHOUT ROWID endpoint/component audit",
    },
    "indexes": (
        "package_id,company_id,fiscal_sequence DESC",
        "package_id,fiscal_year,fiscal_quarter,company_id",
    ),
})
HISTORY_MODE = "REVISED_HISTORY"
PACKAGE_TABLE = "fundamental_delta_package"
STATUS_TABLE = "fundamental_delta_status"
REASON_TABLE = "fundamental_delta_reason"
COMPONENT_TYPE_TABLE = "fundamental_delta_component_type"
TOTAL_TABLE = "fundamental_delta_result"
COMPONENT_TABLE = "fundamental_delta_component"
META_TABLE = PACKAGE_TABLE
LIFECYCLE_TABLE = "lifecycle_change_revised_context"  # retired V1 object, never created
VALUATION_TABLE = "valuation_change_revised_diagnostic"  # retired V1 object, never created
PRODUCTION_ANALYSIS_DB = Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db")
DELTA_STATUS_SQL = ",".join(repr(status.value) for status in DeltaStatus)
LIFECYCLE_STATE_SQL = ",".join(repr(state.value) for state in LifecycleState)
LIFECYCLE_STATUS_SQL = ",".join(repr(status.value) for status in LifecycleStatus)


SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {PACKAGE_TABLE} (
    package_id INTEGER PRIMARY KEY,
    persistence_version TEXT NOT NULL CHECK (persistence_version='{PERSISTENCE_VERSION}'),
    layout_fingerprint TEXT NOT NULL CHECK (layout_fingerprint='{LAYOUT_FINGERPRINT}'),
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK (semantic_mode='{SEMANTIC_MODE}'),
    history_mode TEXT NOT NULL CHECK (history_mode='{HISTORY_MODE}'),
    score_model_fingerprint TEXT NOT NULL,
    fundamental_source_fingerprint TEXT NOT NULL,
    fundamental_result_fingerprint TEXT NOT NULL,
    lifecycle_model_fingerprint TEXT NOT NULL,
    lifecycle_source_fingerprint TEXT NOT NULL,
    lifecycle_result_fingerprint TEXT NOT NULL,
    valuation_model_fingerprint TEXT NOT NULL,
    valuation_source_fingerprint TEXT NOT NULL,
    valuation_result_fingerprint TEXT NOT NULL,
    economic_package_fingerprint TEXT NOT NULL,
    physical_content_fingerprint TEXT NOT NULL,
    total_row_count INTEGER NOT NULL CHECK (total_row_count>=0),
    component_row_count INTEGER NOT NULL CHECK (component_row_count>=0),
    applied_at_utc TEXT NOT NULL,
    UNIQUE(model_fingerprint,history_mode)
);

CREATE TABLE IF NOT EXISTS {STATUS_TABLE} (
    status_id INTEGER PRIMARY KEY,
    status_text TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS {REASON_TABLE} (
    reason_id INTEGER PRIMARY KEY,
    reason_text TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS {COMPONENT_TYPE_TABLE} (
    component_id INTEGER PRIMARY KEY,
    component_name TEXT NOT NULL UNIQUE,
    maximum_points REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS {TOTAL_TABLE} (
    endpoint_id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES {PACKAGE_TABLE}(package_id),
    company_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
    fiscal_sequence INTEGER NOT NULL,
    current_available_date TEXT NOT NULL,
    current_score_result_id INTEGER NOT NULL,
    qoq_prior_score_result_id INTEGER,
    qoq_delta REAL,
    qoq_status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
    qoq_reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),
    two_quarter_prior_score_result_id INTEGER,
    two_quarter_delta REAL,
    two_quarter_status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
    two_quarter_reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),
    yoy_prior_score_result_id INTEGER,
    yoy_delta REAL,
    yoy_status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
    yoy_reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),
    reconciliation_status INTEGER NOT NULL CHECK (reconciliation_status IN (0,1)),
    maximum_reconciliation_error REAL,
    engine_result_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    UNIQUE(package_id,company_id,fiscal_sequence)
);

CREATE TABLE IF NOT EXISTS {COMPONENT_TABLE} (
    endpoint_id INTEGER NOT NULL REFERENCES {TOTAL_TABLE}(endpoint_id) ON DELETE CASCADE,
    component_id INTEGER NOT NULL REFERENCES {COMPONENT_TYPE_TABLE}(component_id),
    current_points REAL,
    qoq_prior_points REAL,
    qoq_delta REAL,
    qoq_status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
    qoq_reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),
    two_quarter_prior_points REAL,
    two_quarter_delta REAL,
    two_quarter_status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
    two_quarter_reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),
    yoy_prior_points REAL,
    yoy_delta REAL,
    yoy_status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
    yoy_reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),
    result_fingerprint TEXT NOT NULL,
    PRIMARY KEY(endpoint_id,component_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_fundamental_delta_current
    ON {TOTAL_TABLE}(package_id,company_id,fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_fundamental_delta_cross_section
    ON {TOTAL_TABLE}(package_id,fiscal_year,fiscal_quarter,company_id);
"""

SCHEMA_STATEMENTS = tuple(statement.strip() for statement in SCHEMA_SQL.split(";") if statement.strip())
TABLES = (TOTAL_TABLE, COMPONENT_TABLE)


@dataclass(frozen=True)
class DeltaPersistencePackage:
    total_rows: tuple[dict[str, Any], ...]
    component_rows: tuple[dict[str, Any], ...]
    lifecycle_rows: tuple[dict[str, Any], ...]
    valuation_rows: tuple[dict[str, Any], ...]
    fundamental_source_fingerprint: str
    fundamental_result_fingerprint: str
    lifecycle_source_fingerprint: str
    lifecycle_result_fingerprint: str
    valuation_source_fingerprint: str
    valuation_result_fingerprint: str
    package_fingerprint: str


@dataclass(frozen=True)
class ApplyReport:
    scope: str
    companies: tuple[int, ...]
    total_inserted: int
    total_deleted: int
    total_updated: int
    total_unchanged: int
    component_inserted: int
    component_deleted: int
    component_updated: int
    component_unchanged: int
    lifecycle_inserted: int
    lifecycle_deleted: int
    lifecycle_updated: int
    lifecycle_unchanged: int
    valuation_inserted: int
    valuation_deleted: int
    valuation_updated: int
    valuation_unchanged: int
    retained_other_model_rows: int
    persisted_content_fingerprint: str
    outcome: str


def schema_signature(conn: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(row) for row in conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name,tbl_name"
    ))


def migrate_analysis_copy(path: Path, *, applied_at_utc: str) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink() or path.resolve() == PRODUCTION_ANALYSIS_DB.resolve():
        raise PermissionError("PHASE5C_PRODUCTION_OR_ALIAS_MIGRATION_BLOCKED")
    with sqlite3.connect(path) as conn:
        before = schema_signature(conn)
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at_utc)
        conn.commit()
        after = schema_signature(conn)
        return {
            "persistence_version": PERSISTENCE_VERSION,
            "objects_before": len(before), "objects_after": len(after),
            "objects_added": len(after) - len(before),
            "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
        }


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    physical = {
        "result_fingerprint", "fundamental_delta_component_id", "lifecycle_change_context_id",
        "valuation_change_diagnostic_id",
    }
    return fingerprint({key: value for key, value in row.items() if key not in physical})


def recalculate_row_fingerprint(row: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    output["result_fingerprint"] = _row_fingerprint(output)
    return output


def rebuild_package(
    total_rows: Sequence[Mapping[str, Any]], component_rows: Sequence[Mapping[str, Any]],
    lifecycle_rows: Sequence[Mapping[str, Any]], valuation_rows: Sequence[Mapping[str, Any]],
    *, fundamental_source_fingerprint: str, lifecycle_source_fingerprint: str,
    valuation_source_fingerprint: str,
) -> DeltaPersistencePackage:
    groups = tuple(tuple(dict(row) for row in rows) for rows in (total_rows, component_rows, lifecycle_rows, valuation_rows))
    fundamental_result = fingerprint([row["engine_result_fingerprint"] for row in groups[0]])
    lifecycle_result = fingerprint([row["engine_result_fingerprint"] for row in groups[2]])
    valuation_result = fingerprint([row["engine_result_fingerprint"] for row in groups[3]])
    package_fp = fingerprint({
        "model": MODEL_FINGERPRINT, "fundamental_source": fundamental_source_fingerprint,
        "fundamental_result": fundamental_result, "lifecycle_source": lifecycle_source_fingerprint,
        "lifecycle_result": lifecycle_result, "valuation_source": valuation_source_fingerprint,
        "valuation_result": valuation_result,
        "rows": [[row["result_fingerprint"] for row in rows] for rows in groups],
    })
    package = DeltaPersistencePackage(
        groups[0], groups[1], groups[2], groups[3], fundamental_source_fingerprint,
        fundamental_result, lifecycle_source_fingerprint, lifecycle_result,
        valuation_source_fingerprint, valuation_result, package_fp,
    )
    validate_package(package)
    return package


def _horizon_map(result: Any) -> dict[str, Any]:
    return {item.horizon.value: item for item in result.horizons}


def build_persistence_package(source: DeltaSource) -> DeltaPersistencePackage:
    totals: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    lifecycle: list[dict[str, Any]] = []
    valuation: list[dict[str, Any]] = []
    fundamental_engine_fps: list[str] = []
    lifecycle_engine_fps: list[str] = []
    valuation_engine_fps: list[str] = []
    for company_id, history in source.score_histories.items():
        life_by_seq = {row.fiscal.fiscal_sequence: row for row in source.lifecycle_histories.get(company_id, ())}
        val_by_seq = {row.fiscal.fiscal_sequence: row for row in source.valuation_histories.get(company_id, ())}
        if set(life_by_seq) != {row.fiscal.fiscal_sequence for row in history} or set(val_by_seq) != {row.fiscal.fiscal_sequence for row in history}:
            raise ValueError(f"DELTA_CONTEXT_ENDPOINT_RELATIONSHIP_INCOMPLETE:{company_id}")
        for current in history:
            result_id = int(fingerprint({
                "model_fingerprint": MODEL_FINGERPRINT,
                "company_id": company_id,
                "fiscal_sequence": current.fiscal.fiscal_sequence,
            })[:15], 16)
            delta = calculate_fundamental_delta(current, history, source_fingerprint=source.score_source_fingerprint)
            fundamental_engine_fps.append(delta.result_fingerprint)
            horizons = _horizon_map(delta)
            ready_errors = [abs(float(item.reconciliation_error)) for item in delta.horizons if item.status == DeltaStatus.READY and item.reconciliation_error is not None]
            total = {
                "fundamental_delta_result_id": result_id,
                "company_id": company_id, "fiscal_year": delta.current_fiscal_year,
                "fiscal_quarter": delta.current_fiscal_quarter, "fiscal_sequence": delta.current_fiscal_sequence,
                "period_end": delta.current_period_end, "current_available_date": delta.current_available_date,
                "current_observation_id": delta.current_observation_id,
                "current_score_result_id": delta.current_score_result_id, "current_score": delta.current_score,
                "current_score_status": delta.current_score_status, "score_model_version": delta.score_model_version,
                "score_model_fingerprint": delta.score_model_fingerprint, "model_version": MODEL_VERSION,
                "model_fingerprint": MODEL_FINGERPRINT, "semantic_mode": SEMANTIC_MODE,
                "history_mode": HISTORY_MODE, "source_fingerprint": source.score_source_fingerprint,
                "reconciliation_status": "RECONCILED" if ready_errors else "NOT_APPLICABLE",
                "maximum_reconciliation_error": max(ready_errors) if ready_errors else None,
                "engine_result_fingerprint": delta.result_fingerprint,
            }
            for horizon in Horizon:
                item = horizons[horizon.value]; prefix = horizon.value.lower()
                total.update({
                    f"{prefix}_prior_observation_id": item.prior_observation_id,
                    f"{prefix}_prior_score_result_id": item.prior_score_result_id,
                    f"{prefix}_prior_fiscal_sequence": item.prior_fiscal_sequence,
                    f"{prefix}_prior_available_date": item.prior_available_date,
                    f"{prefix}_prior_score": item.prior_score, f"{prefix}_delta": item.delta_points,
                    f"{prefix}_status": item.status.value, f"{prefix}_reason": item.reason_code,
                })
            total["result_fingerprint"] = _row_fingerprint(total)
            totals.append(total)
            current_components = {row.component_name: row for row in current.components}
            for name in COMPONENT_MAXIMA:
                component = {
                    "fundamental_delta_result_id": result_id, "company_id": company_id,
                    "fiscal_sequence": delta.current_fiscal_sequence, "component_name": name,
                    "maximum_points": COMPONENT_MAXIMA[name],
                    "current_points": current_components.get(name).points if current_components.get(name) else None,
                    "model_fingerprint": MODEL_FINGERPRINT, "history_mode": HISTORY_MODE,
                    "source_fingerprint": source.score_source_fingerprint,
                }
                for horizon in Horizon:
                    total_horizon = horizons[horizon.value]; prefix = horizon.value.lower()
                    item = next(row for row in total_horizon.components if row.component_name == name)
                    component.update({
                        f"{prefix}_prior_score_result_id": total_horizon.prior_score_result_id,
                        f"{prefix}_prior_points": item.prior_points, f"{prefix}_delta": item.delta_points,
                        f"{prefix}_status": item.status.value, f"{prefix}_reason": item.reason_code,
                    })
                component["result_fingerprint"] = _row_fingerprint(component)
                components.append(component)
            life_current = life_by_seq[delta.current_fiscal_sequence]
            life_result = calculate_lifecycle_context(life_current, source.lifecycle_histories[company_id], source_fingerprint=source.lifecycle_source_fingerprint)
            lifecycle_engine_fps.append(life_result.result_fingerprint)
            life = {
                "fundamental_delta_result_id": result_id, "company_id": company_id,
                "fiscal_sequence": delta.current_fiscal_sequence,
                "current_observation_id": life_result.current_observation_id,
                "current_final_state": life_result.current_final_state, "current_raw_state": life_result.current_raw_state,
                "lifecycle_status": life_result.lifecycle_status, "last_confirmed_state": life_result.last_confirmed_state,
                "candidate_state": life_result.candidate_state, "candidate_count": life_result.candidate_count,
                "latest_transition_observation_id": life_result.latest_confirmed_transition_observation_id,
                "latest_transition_fiscal_sequence": life_result.latest_confirmed_transition_fiscal_sequence,
                "consecutive_classified_observations": life_result.consecutive_classified_observations,
                "context_model_fingerprint": LIFECYCLE_CONTEXT_FINGERPRINT,
                "source_fingerprint": source.lifecycle_source_fingerprint,
                "model_fingerprint": MODEL_FINGERPRINT, "history_mode": HISTORY_MODE,
                "engine_result_fingerprint": life_result.result_fingerprint,
            }
            for item in life_result.horizons:
                prefix = item.horizon.value.lower()
                life.update({f"{prefix}_prior_observation_id": item.prior_observation_id,
                             f"{prefix}_prior_final_state": item.prior_final_state,
                             f"{prefix}_state_changed": None if item.state_changed is None else int(item.state_changed),
                             f"{prefix}_status": item.status.value, f"{prefix}_reason": item.reason_code})
            life["result_fingerprint"] = _row_fingerprint(life); lifecycle.append(life)
            val_current = val_by_seq[delta.current_fiscal_sequence]
            val_result = calculate_valuation_diagnostic(val_current, source.valuation_histories[company_id], source_fingerprint=source.valuation_source_fingerprint)
            valuation_engine_fps.append(val_result.result_fingerprint)
            val = {
                "fundamental_delta_result_id": result_id, "company_id": company_id,
                "fiscal_sequence": delta.current_fiscal_sequence,
                "current_observation_id": val_result.current_observation_id,
                "current_valuation_result_id": val_result.current_result_id,
                "valuation_model_fingerprint": val_result.valuation_model_fingerprint,
                "diagnostic_model_fingerprint": VALUATION_DIAGNOSTIC_FINGERPRINT,
                "source_fingerprint": source.valuation_source_fingerprint,
                "model_fingerprint": MODEL_FINGERPRINT, "history_mode": HISTORY_MODE,
                "engine_result_fingerprint": val_result.result_fingerprint,
            }
            for item in val_result.horizons:
                prefix = item.horizon.value.lower()
                val.update({f"{prefix}_status": item.status.value, f"{prefix}_reason": item.reason_code,
                            f"{prefix}_delta": item.score_change,
                            f"{prefix}_payload_json": canonical_json(asdict(item))})
            val["result_fingerprint"] = _row_fingerprint(val); valuation.append(val)
    package = rebuild_package(
        totals, components, lifecycle, valuation,
        fundamental_source_fingerprint=source.score_source_fingerprint,
        lifecycle_source_fingerprint=source.lifecycle_source_fingerprint,
        valuation_source_fingerprint=source.valuation_source_fingerprint,
    )
    if package.fundamental_result_fingerprint != fingerprint(fundamental_engine_fps) or package.lifecycle_result_fingerprint != fingerprint(lifecycle_engine_fps) or package.valuation_result_fingerprint != fingerprint(valuation_engine_fps):
        raise RuntimeError("DELTA_PACKAGE_ENGINE_FINGERPRINT_RECONCILIATION_FAILED")
    return package


def _finite(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))


def validate_package(package: DeltaPersistencePackage) -> None:
    if package.fundamental_result_fingerprint != fingerprint([row["engine_result_fingerprint"] for row in package.total_rows]):
        raise ValueError("FUNDAMENTAL_RESULT_FINGERPRINT_MISMATCH")
    if package.lifecycle_result_fingerprint != fingerprint([row["engine_result_fingerprint"] for row in package.lifecycle_rows]):
        raise ValueError("LIFECYCLE_RESULT_FINGERPRINT_MISMATCH")
    if package.valuation_result_fingerprint != fingerprint([row["engine_result_fingerprint"] for row in package.valuation_rows]):
        raise ValueError("VALUATION_RESULT_FINGERPRINT_MISMATCH")
    expected_package = fingerprint({
        "model": MODEL_FINGERPRINT, "fundamental_source": package.fundamental_source_fingerprint,
        "fundamental_result": package.fundamental_result_fingerprint,
        "lifecycle_source": package.lifecycle_source_fingerprint,
        "lifecycle_result": package.lifecycle_result_fingerprint,
        "valuation_source": package.valuation_source_fingerprint,
        "valuation_result": package.valuation_result_fingerprint,
        "rows": [[row["result_fingerprint"] for row in rows] for rows in (
            package.total_rows, package.component_rows, package.lifecycle_rows, package.valuation_rows
        )],
    })
    if package.package_fingerprint != expected_package:
        raise ValueError("DELTA_PACKAGE_FINGERPRINT_MISMATCH")
    total_ids = {row["fundamental_delta_result_id"] for row in package.total_rows}
    if len(total_ids) != len(package.total_rows): raise ValueError("DUPLICATE_TOTAL_ENDPOINT")
    total_keys = {(row["company_id"], row["fiscal_sequence"]) for row in package.total_rows}
    if len(total_keys) != len(package.total_rows): raise ValueError("DUPLICATE_TOTAL_LOGICAL_ENDPOINT")
    for rows, label in ((package.component_rows,"COMPONENT"),(package.lifecycle_rows,"LIFECYCLE"),(package.valuation_rows,"VALUATION")):
        if any(row["fundamental_delta_result_id"] not in total_ids for row in rows): raise ValueError(f"ORPHAN_{label}_ENDPOINT")
    component_keys = {(row["fundamental_delta_result_id"],row["component_name"]) for row in package.component_rows}
    if len(component_keys) != len(package.component_rows): raise ValueError("DUPLICATE_COMPONENT_ENDPOINT")
    if len(package.component_rows) != 7 * len(package.total_rows): raise ValueError("SEVEN_COMPONENT_RELATIONSHIP_REQUIRED")
    expected_components = set(COMPONENT_MAXIMA)
    component_names_by_result: dict[int, set[str]] = {}
    for row in package.component_rows:
        component_names_by_result.setdefault(int(row["fundamental_delta_result_id"]), set()).add(str(row["component_name"]))
    for result_id in total_ids:
        if component_names_by_result.get(int(result_id)) != expected_components:
            raise ValueError("STABLE_COMPONENT_RELATIONSHIP_REQUIRED")
    if {row["fundamental_delta_result_id"] for row in package.lifecycle_rows} != total_ids or {row["fundamental_delta_result_id"] for row in package.valuation_rows} != total_ids:
        raise ValueError("CONTEXT_ENDPOINT_RELATIONSHIP_REQUIRED")
    for row in (*package.total_rows,*package.component_rows,*package.lifecycle_rows,*package.valuation_rows):
        if row.get("model_fingerprint") != MODEL_FINGERPRINT or row.get("history_mode") != HISTORY_MODE: raise ValueError("DELTA_MODEL_OR_MODE_MISMATCH")
        if row.get("result_fingerprint") != _row_fingerprint(row): raise ValueError("PERSISTED_ROW_FINGERPRINT_MISMATCH")
    if any(row["source_fingerprint"] != package.fundamental_source_fingerprint for row in (*package.total_rows,*package.component_rows)):
        raise ValueError("FUNDAMENTAL_SOURCE_FINGERPRINT_MISMATCH")
    if any(row["source_fingerprint"] != package.lifecycle_source_fingerprint for row in package.lifecycle_rows):
        raise ValueError("LIFECYCLE_SOURCE_FINGERPRINT_MISMATCH")
    if any(row["source_fingerprint"] != package.valuation_source_fingerprint for row in package.valuation_rows):
        raise ValueError("VALUATION_SOURCE_FINGERPRINT_MISMATCH")
    valid_statuses = {status.value for status in DeltaStatus}
    for row in package.total_rows:
        for prefix, lag in (("qoq",1),("two_quarter",2),("yoy",4)):
            if row[f"{prefix}_status"] not in valid_statuses: raise ValueError("TOTAL_STATUS_INVALID")
            ready = row[f"{prefix}_status"] == DeltaStatus.READY.value
            value = row[f"{prefix}_delta"]
            if ready:
                if not _finite(value) or row[f"{prefix}_prior_fiscal_sequence"] != row["fiscal_sequence"]-lag: raise ValueError("READY_TOTAL_LAG_OR_VALUE_INVALID")
                if not math.isclose(float(row["current_score"])-float(row[f"{prefix}_prior_score"]),float(value),abs_tol=RECONCILIATION_TOLERANCE,rel_tol=0): raise ValueError("TOTAL_ARITHMETIC_MISMATCH")
            elif value is not None: raise ValueError("UNAVAILABLE_TOTAL_DELTA_MUST_BE_NULL")
    by_total: dict[int,list[Mapping[str,Any]]] = {}
    for row in package.component_rows:
        by_total.setdefault(int(row["fundamental_delta_result_id"]),[]).append(row)
        if row["component_name"] not in COMPONENT_MAXIMA or float(row["maximum_points"]) != COMPONENT_MAXIMA[row["component_name"]]:
            raise ValueError("COMPONENT_IDENTITY_OR_MAXIMUM_INVALID")
        for prefix in ("qoq", "two_quarter", "yoy"):
            if row[f"{prefix}_status"] not in valid_statuses: raise ValueError("COMPONENT_STATUS_INVALID")
            ready = row[f"{prefix}_status"] == DeltaStatus.READY.value
            if ready:
                if not _finite(row[f"{prefix}_delta"]): raise ValueError("READY_COMPONENT_VALUE_INVALID")
            elif row[f"{prefix}_delta"] is not None:
                raise ValueError("UNAVAILABLE_COMPONENT_DELTA_MUST_BE_NULL")
    for total in package.total_rows:
        for prefix in ("qoq","two_quarter","yoy"):
            if total[f"{prefix}_status"] == DeltaStatus.READY.value:
                values=[row[f"{prefix}_delta"] for row in by_total[int(total["fundamental_delta_result_id"])]]
                if any(not _finite(value) for value in values) or not math.isclose(sum(map(float,values)),float(total[f"{prefix}_delta"]),abs_tol=RECONCILIATION_TOLERANCE,rel_tol=0): raise ValueError("TOTAL_COMPONENT_RECONCILIATION_FAILED")
    valid_states = {state.value for state in LifecycleState}
    valid_lifecycle_statuses = {status.value for status in LifecycleStatus}
    for row in package.lifecycle_rows:
        if row["current_raw_state"] not in valid_states or row["lifecycle_status"] not in valid_lifecycle_statuses:
            raise ValueError("LIFECYCLE_CATEGORICAL_CONTRACT_INVALID")
        for field in ("current_final_state", "last_confirmed_state", "candidate_state", "qoq_prior_final_state", "two_quarter_prior_final_state", "yoy_prior_final_state"):
            if row[field] is not None and row[field] not in valid_states: raise ValueError("LIFECYCLE_STATE_INVALID")
        for prefix in ("qoq", "two_quarter", "yoy"):
            if row[f"{prefix}_status"] not in valid_statuses: raise ValueError("LIFECYCLE_DELTA_STATUS_INVALID")
    for row in package.valuation_rows:
        for prefix in ("qoq", "two_quarter", "yoy"):
            if row[f"{prefix}_status"] not in valid_statuses: raise ValueError("VALUATION_STATUS_INVALID")
            ready = row[f"{prefix}_status"] == DeltaStatus.READY.value
            if ready != _finite(row[f"{prefix}_delta"]): raise ValueError("VALUATION_READINESS_VALUE_INVALID")
            try:
                payload = json.loads(row[f"{prefix}_payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("VALUATION_PAYLOAD_INVALID") from exc
            if ready:
                component_sum = sum(float(payload[field]) for field in ("ebit_points_change", "fcf_points_change", "earnings_points_change"))
                if not math.isclose(component_sum, float(row[f"{prefix}_delta"]), abs_tol=RECONCILIATION_TOLERANCE, rel_tol=0):
                    raise ValueError("VALUATION_COMPONENT_RECONCILIATION_FAILED")



# Phase 5C.2 replaces the never-deployed wide writer with the normalized V2
# implementation. The economic package builder above remains the locked audit
# boundary used to prove that storage normalization does not change results.
from rawcandle.fundamentals.delta.storage_v2 import (  # noqa: E402,F401
    apply_package,
    ensure_schema,
    quick_check,
)
