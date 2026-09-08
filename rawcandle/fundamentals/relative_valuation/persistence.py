from __future__ import annotations

import hashlib
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .engine import (
    COMPONENTS,
    HISTORY_ENDPOINT_CAP,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    WEIGHTS,
    RelativeValuationInput,
    RelativeValuationSnapshot,
    canonical_json,
    select_history,
)


PERSISTENCE_VERSION = "RELATIVE_VALUATION_CURRENT_SNAPSHOT_V1"
MAX_BULK_SNAPSHOTS = 2
MAX_AUDIT_ROWS = 64
PRODUCTION_ANALYSIS_DB = Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db")
PEER_SCOPES = ("ECOSYSTEM", "INDUSTRY", "SECTOR", "UNIVERSE")

LAYOUT_CONTRACT = {
    "version": PERSISTENCE_VERSION,
    "semantic_mode": "CURRENTLY_REVISED_NOT_PIT",
    "retention": {"bulk_snapshots": 2, "audit_rows": 64},
    "tables": {
        "snapshot": "one immutable complete package",
        "pointer": "one active package per model",
        "company": "one row per selected company",
        "peer": "four explicit scope rows per company",
        "own_history": "one aggregate row per company",
        "component": "three normalized evidence rows per company",
        "audit": "bounded checks including date-only no-change",
    },
}
LAYOUT_FINGERPRINT = hashlib.sha256(canonical_json(LAYOUT_CONTRACT).encode("ascii")).hexdigest()

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS relative_valuation_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    persistence_version TEXT NOT NULL,
    layout_fingerprint TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relative_valuation_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    persistence_version TEXT NOT NULL,
    layout_fingerprint TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK(semantic_mode='CURRENTLY_REVISED_NOT_PIT'),
    as_of_date TEXT NOT NULL,
    calculated_at_utc TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    physical_content_fingerprint TEXT NOT NULL,
    market_price_start_date TEXT,
    market_price_end_date TEXT,
    status TEXT NOT NULL CHECK(status IN ('WRITING','COMPLETE')),
    company_count INTEGER NOT NULL CHECK(company_count>=0),
    current_fresh_count INTEGER NOT NULL CHECK(current_fresh_count>=0),
    current_peer_eligible_count INTEGER NOT NULL CHECK(current_peer_eligible_count>=0),
    own_history_ready_count INTEGER NOT NULL CHECK(own_history_ready_count>=0),
    own_history_limited_count INTEGER NOT NULL CHECK(own_history_limited_count>=0),
    created_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    UNIQUE(model_fingerprint,source_fingerprint,result_fingerprint)
);
CREATE TABLE IF NOT EXISTS relative_valuation_active_snapshot (
    model_fingerprint TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL UNIQUE REFERENCES relative_valuation_snapshot(snapshot_id) ON DELETE RESTRICT,
    activated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relative_valuation_company_result (
    snapshot_id TEXT NOT NULL REFERENCES relative_valuation_snapshot(snapshot_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    quarter_id INTEGER,
    fiscal_year INTEGER,
    fiscal_quarter TEXT,
    period_end TEXT,
    endpoint_available_date TEXT NOT NULL,
    current_fresh INTEGER NOT NULL CHECK(current_fresh IN (0,1)),
    as_of_date TEXT NOT NULL,
    current_price_date TEXT,
    current_price_age_days INTEGER,
    current_price REAL,
    valuation_status TEXT NOT NULL,
    valuation_reason TEXT NOT NULL,
    current_valuation_score REAL,
    filing_valuation_score REAL,
    score_change REAL,
    market_cap REAL,
    enterprise_value REAL,
    operating_yield REAL,
    fcf_yield REAL,
    reported_earnings_yield REAL,
    PRIMARY KEY(snapshot_id,company_id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS relative_valuation_peer_position (
    snapshot_id TEXT NOT NULL,
    company_id INTEGER NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('UNIVERSE','SECTOR','INDUSTRY','ECOSYSTEM')),
    group_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    percentile REAL,
    peer_count INTEGER,
    rank_low INTEGER,
    rank_high INTEGER,
    average_rank REAL,
    source_score REAL,
    PRIMARY KEY(snapshot_id,company_id,scope),
    FOREIGN KEY(snapshot_id,company_id) REFERENCES relative_valuation_company_result(snapshot_id,company_id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS relative_valuation_own_history (
    snapshot_id TEXT NOT NULL,
    company_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    percentile REAL,
    minimum_positive_count INTEGER NOT NULL,
    window_start_date TEXT NOT NULL,
    window_end_date TEXT NOT NULL,
    endpoint_cap INTEGER NOT NULL,
    selected_endpoint_count INTEGER NOT NULL,
    fiscal_gap_count INTEGER NOT NULL,
    PRIMARY KEY(snapshot_id,company_id),
    FOREIGN KEY(snapshot_id,company_id) REFERENCES relative_valuation_company_result(snapshot_id,company_id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS relative_valuation_component_history (
    snapshot_id TEXT NOT NULL,
    company_id INTEGER NOT NULL,
    component_type TEXT NOT NULL CHECK(component_type IN ('OPERATING_YIELD','FCF_YIELD','REPORTED_EARNINGS_YIELD')),
    weight REAL NOT NULL,
    status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    current_yield REAL,
    historical_positive_median REAL,
    historical_percentile REAL,
    eligible_observation_count INTEGER NOT NULL,
    positive_count INTEGER NOT NULL,
    nonpositive_count INTEGER NOT NULL,
    missing_invalid_count INTEGER NOT NULL,
    observation_start_date TEXT,
    observation_end_date TEXT,
    positive_start_date TEXT,
    positive_end_date TEXT,
    less_count INTEGER NOT NULL,
    equal_count INTEGER NOT NULL,
    greater_count INTEGER NOT NULL,
    PRIMARY KEY(snapshot_id,company_id,component_type),
    FOREIGN KEY(snapshot_id,company_id) REFERENCES relative_valuation_company_result(snapshot_id,company_id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS relative_valuation_refresh_audit (
    audit_id INTEGER PRIMARY KEY,
    model_fingerprint TEXT NOT NULL,
    checked_at_utc TEXT NOT NULL,
    requested_as_of_date TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('ACTIVATED','NO_CHANGE','DATE_ONLY_NO_CHANGE')),
    active_snapshot_id TEXT NOT NULL REFERENCES relative_valuation_snapshot(snapshot_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_relative_valuation_snapshot_model
    ON relative_valuation_snapshot(model_fingerprint,status,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_relative_valuation_peer_group
    ON relative_valuation_peer_position(snapshot_id,scope,group_id,company_id);
CREATE INDEX IF NOT EXISTS idx_relative_valuation_audit_model
    ON relative_valuation_refresh_audit(model_fingerprint,audit_id DESC);
"""

SCHEMA_OBJECTS = (
    "relative_valuation_schema_meta", "relative_valuation_snapshot",
    "relative_valuation_active_snapshot", "relative_valuation_company_result",
    "relative_valuation_peer_position", "relative_valuation_own_history",
    "relative_valuation_component_history", "relative_valuation_refresh_audit",
    "idx_relative_valuation_snapshot_model", "idx_relative_valuation_peer_group",
    "idx_relative_valuation_audit_model",
)


@dataclass(frozen=True)
class ApplyReport:
    outcome: str
    snapshot_id: str
    physical_content_fingerprint: str
    company_rows_inserted: int
    peer_rows_inserted: int
    own_history_rows_inserted: int
    component_rows_inserted: int
    bulk_rows_deleted: int
    snapshots_inserted: int
    snapshots_deleted: int
    pointer_changes: int
    audit_rows_inserted: int
    retained_snapshot_count: int

    @property
    def logical_bulk_writes(self) -> int:
        return (self.company_rows_inserted + self.peer_rows_inserted
                + self.own_history_rows_inserted + self.component_rows_inserted
                + self.bulk_rows_deleted)


def schema_signature(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    marks = ",".join("?" for _ in SCHEMA_OBJECTS)
    return [tuple(row) for row in conn.execute(
        f"SELECT type,name,sql FROM sqlite_schema WHERE name IN ({marks}) ORDER BY type,name",
        SCHEMA_OBJECTS,
    )]


def ensure_schema(conn: sqlite3.Connection, *, applied_at_utc: str) -> None:
    for statement in (part.strip() for part in SCHEMA_SQL.split(";")):
        if statement:
            conn.execute(statement)
    row = conn.execute("SELECT persistence_version,layout_fingerprint FROM relative_valuation_schema_meta WHERE singleton=1").fetchone()
    identity = (PERSISTENCE_VERSION, LAYOUT_FINGERPRINT)
    if row is None:
        conn.execute("INSERT INTO relative_valuation_schema_meta VALUES (1,?,?,?)", (*identity, applied_at_utc))
    elif tuple(row) != identity:
        raise ValueError("RELATIVE_VALUATION_PERSISTENCE_IDENTITY_MISMATCH")


def migrate_analysis_copy(path: Path, *, applied_at_utc: str) -> dict[str, Any]:
    resolved = path.resolve()
    if path.is_symlink() or resolved == PRODUCTION_ANALYSIS_DB.resolve():
        raise PermissionError("RELATIVE_VALUATION_PRODUCTION_MIGRATION_BLOCKED")
    conn = sqlite3.connect(resolved)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        before = schema_signature(conn)
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at_utc)
        conn.commit()
        return {
            "objects_before": len(before), "objects_after": len(schema_signature(conn)),
            "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_violations": len(list(conn.execute("PRAGMA foreign_key_check"))),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _history_counts(source: RelativeValuationInput, component: str, current: float | None, as_of: str) -> tuple[int, int, int]:
    selected, _, _ = select_history(source.history, as_of_date=as_of)
    values: list[float] = []
    for row in selected:
        if component == "OPERATING_YIELD":
            numerator, denominator = row.ttm_operating_income, row.enterprise_value
        elif component == "FCF_YIELD":
            numerator, denominator = row.ttm_free_cashflow, row.market_cap
        else:
            numerator, denominator = row.ttm_reported_common_earnings, row.market_cap
        n, d = _finite(numerator), _finite(denominator)
        if n is not None and d is not None and n > 0 and d > 0:
            values.append(n / d)
    if current is None:
        return 0, 0, len(values)
    return (sum(value < current for value in values), sum(value == current for value in values), sum(value > current for value in values))


def _normalized(snapshot: RelativeValuationSnapshot, inputs: Sequence[RelativeValuationInput]) -> dict[str, list[dict[str, Any]]]:
    sources = {row.company_id: row for row in inputs}
    if set(sources) != {row.company_id for row in snapshot.companies}:
        raise ValueError("RELATIVE_VALUATION_SOURCE_COMPANY_SET_MISMATCH")
    companies: list[dict[str, Any]] = []
    peers: list[dict[str, Any]] = []
    own: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    for row in snapshot.companies:
        if row.company_id is None:
            raise ValueError("RELATIVE_VALUATION_COMPANY_ID_REQUIRED")
        current = row.current_valuation
        companies.append({
            "company_id": row.company_id, "security_id": row.security_id, "ticker": row.ticker,
            "quarter_id": current.get("quarter_id"), "fiscal_year": current.get("fiscal_year"),
            "fiscal_quarter": current.get("fiscal_quarter"), "period_end": current.get("period_end"),
            "endpoint_available_date": row.endpoint_available_date, "current_fresh": int(row.current_fresh),
            "as_of_date": snapshot.as_of_date, "current_price_date": current.get("price_date"),
            "current_price_age_days": current.get("price_age_calendar_days"), "current_price": current.get("selected_price"),
            "valuation_status": str(current.get("valuation_status") or "VALUATION_NOT_READY"),
            "valuation_reason": str(current.get("reason_code") or "UNKNOWN"),
            "current_valuation_score": current.get("total_valuation_score"),
            "filing_valuation_score": (row.filing_valuation or {}).get("total_valuation_score"),
            "score_change": row.score_change_due_to_current_price, "market_cap": current.get("market_cap"),
            "enterprise_value": current.get("enterprise_value"), "operating_yield": current.get("operating_income_yield"),
            "fcf_yield": current.get("fcf_yield"), "reported_earnings_yield": current.get("earnings_yield"),
        })
        results = {(str(item["peer_scope"]), str(item.get("peer_group_id") or "")): item for item in row.current_peer_results}
        for coverage in row.current_peer_coverage:
            scope = str(coverage["peer_scope"])
            group_id = str(coverage.get("peer_group_id") or "")
            result = results.get((scope, group_id))
            peers.append({
                "company_id": row.company_id, "scope": scope, "group_id": group_id,
                "status": str(coverage["status"]), "reason_code": str(coverage["reason_code"]),
                "percentile": result.get("percentile") if result else None,
                "peer_count": coverage.get("peer_count"), "rank_low": result.get("rank_low") if result else None,
                "rank_high": result.get("rank_high") if result else None,
                "average_rank": result.get("average_rank") if result else None,
                "source_score": current.get("total_valuation_score"),
            })
        history = row.own_history
        own.append({
            "company_id": row.company_id, "status": history.status, "reason_code": history.reason_code,
            "percentile": history.percentile,
            "minimum_positive_count": history.minimum_component_positive_history_count,
            "window_start_date": history.window_start_date, "window_end_date": history.window_end_date,
            "endpoint_cap": HISTORY_ENDPOINT_CAP, "selected_endpoint_count": history.selected_endpoint_count,
            "fiscal_gap_count": history.fiscal_gap_count,
        })
        for component in history.components:
            less, equal, greater = _history_counts(sources[row.company_id], component.component, component.current_yield, snapshot.as_of_date)
            components.append({
                "company_id": row.company_id, "component_type": component.component,
                "weight": WEIGHTS[component.component], "status": component.component_history_status,
                "reason_code": component.reason_code, "current_yield": component.current_yield,
                "historical_positive_median": component.historical_median_positive_yield,
                "historical_percentile": component.historical_percentile,
                "eligible_observation_count": component.component_observation_count,
                "positive_count": component.positive_history_count,
                "nonpositive_count": component.nonpositive_history_count,
                "missing_invalid_count": component.missing_or_invalid_history_count,
                "observation_start_date": component.component_first_observation_date,
                "observation_end_date": component.component_last_observation_date,
                "positive_start_date": component.positive_history_start_date,
                "positive_end_date": component.positive_history_end_date,
                "less_count": less, "equal_count": equal, "greater_count": greater,
            })
    for values, key in ((companies, lambda x: x["company_id"]),
                        (peers, lambda x: (x["company_id"], x["scope"])),
                        (own, lambda x: x["company_id"]),
                        (components, lambda x: (x["company_id"], x["component_type"]))):
        values.sort(key=key)
    return {"companies": companies, "peers": peers, "own_history": own, "components": components}


def physical_content_fingerprint(content: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(content).encode("ascii")).hexdigest()


def _economic_bulk_fingerprint(content: Mapping[str, Any]) -> str:
    comparable = {key: [dict(row) for row in rows] for key, rows in content.items()}
    for row in comparable["companies"]:
        row.pop("as_of_date", None)
    for row in comparable["own_history"]:
        row.pop("window_end_date", None)
    return physical_content_fingerprint(comparable)


def validate_snapshot(snapshot: RelativeValuationSnapshot, inputs: Sequence[RelativeValuationInput]) -> tuple[dict[str, list[dict[str, Any]]], str]:
    if snapshot.model_version != MODEL_VERSION or snapshot.model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("RELATIVE_VALUATION_MODEL_IDENTITY_MISMATCH")
    if snapshot.semantic_mode != "CURRENTLY_REVISED_NOT_PIT":
        raise ValueError("RELATIVE_VALUATION_SEMANTIC_MODE_MISMATCH")
    expected_result = hashlib.sha256(canonical_json({
        "model_version": snapshot.model_version,
        "model_fingerprint": snapshot.model_fingerprint,
        "semantic_mode": snapshot.semantic_mode,
        "as_of_date": snapshot.as_of_date,
        "source_fingerprint": snapshot.source_fingerprint,
        "companies": [asdict(row) for row in snapshot.companies],
    }).encode("ascii")).hexdigest()
    if snapshot.result_fingerprint != expected_result:
        raise ValueError("RELATIVE_VALUATION_RESULT_FINGERPRINT_MISMATCH")
    content = _normalized(snapshot, inputs)
    company_ids = [row["company_id"] for row in content["companies"]]
    if len(company_ids) != len(set(company_ids)):
        raise ValueError("RELATIVE_VALUATION_DUPLICATE_COMPANY")
    peer_counts: dict[int, int] = {}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in content["peers"]:
        peer_counts[row["company_id"]] = peer_counts.get(row["company_id"], 0) + 1
        if row["scope"] not in PEER_SCOPES:
            raise ValueError("RELATIVE_VALUATION_PEER_SCOPE_INVALID")
        if row["percentile"] is not None:
            expected = 100.0 * (float(row["average_rank"]) - 1.0) / (int(row["peer_count"]) - 1.0)
            if not math.isclose(float(row["percentile"]), expected, abs_tol=1e-12):
                raise ValueError("RELATIVE_VALUATION_PEER_PERCENTILE_MISMATCH")
        if row["rank_low"] is not None:
            groups.setdefault((row["scope"], row["group_id"]), []).append(row)
    if any(peer_counts.get(company_id) != 4 for company_id in company_ids):
        raise ValueError("RELATIVE_VALUATION_REQUIRES_FOUR_PEER_SCOPES")
    for identity, rows in groups.items():
        scores = sorted(float(row["source_score"]) for row in rows)
        for row in rows:
            score = float(row["source_score"])
            low = 1 + sum(value < score for value in scores)
            high = sum(value <= score for value in scores)
            if (row["rank_low"], row["rank_high"], row["peer_count"]) != (low, high, len(rows)):
                raise ValueError(f"RELATIVE_VALUATION_PEER_RANK_MISMATCH:{identity}")
    component_counts: dict[int, int] = {}
    by_company: dict[int, list[dict[str, Any]]] = {}
    for row in content["components"]:
        component_counts[row["company_id"]] = component_counts.get(row["company_id"], 0) + 1
        by_company.setdefault(row["company_id"], []).append(row)
        if row["less_count"] + row["equal_count"] + row["greater_count"] != row["positive_count"]:
            raise ValueError("RELATIVE_VALUATION_COMPONENT_COUNTS_MISMATCH")
        if row["historical_percentile"] is not None:
            expected = 100.0 * (row["less_count"] + 0.5 * row["equal_count"]) / row["positive_count"]
            if not math.isclose(float(row["historical_percentile"]), expected, abs_tol=1e-12):
                raise ValueError("RELATIVE_VALUATION_HISTORY_PERCENTILE_MISMATCH")
    if any(component_counts.get(company_id) != 3 for company_id in company_ids):
        raise ValueError("RELATIVE_VALUATION_REQUIRES_THREE_COMPONENTS")
    for row in content["own_history"]:
        if row["percentile"] is not None:
            expected = sum(item["weight"] * float(item["historical_percentile"]) for item in by_company[row["company_id"]])
            if not math.isclose(float(row["percentile"]), expected, abs_tol=1e-12):
                raise ValueError("RELATIVE_VALUATION_AGGREGATE_MISMATCH")
    return content, physical_content_fingerprint(content)


def _snapshot_id(snapshot: RelativeValuationSnapshot, physical: str) -> str:
    return hashlib.sha256(canonical_json({
        "model": snapshot.model_fingerprint, "layout": LAYOUT_FINGERPRINT,
        "as_of": snapshot.as_of_date, "source": snapshot.source_fingerprint,
        "result": snapshot.result_fingerprint, "physical": physical,
    }).encode("ascii")).hexdigest()


def _insert_many(conn: sqlite3.Connection, table: str, snapshot_id: str, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    sql = f"INSERT INTO {table}(snapshot_id,{','.join(fields)}) VALUES ({','.join('?' for _ in range(len(fields)+1))})"
    conn.executemany(sql, [(snapshot_id, *(row[field] for field in fields)) for row in rows])


def _audit(conn: sqlite3.Connection, snapshot: RelativeValuationSnapshot, active_id: str, checked_at: str, outcome: str) -> None:
    conn.execute("INSERT INTO relative_valuation_refresh_audit(model_fingerprint,checked_at_utc,requested_as_of_date,source_fingerprint,result_fingerprint,outcome,active_snapshot_id) VALUES (?,?,?,?,?,?,?)",
                 (MODEL_FINGERPRINT, checked_at, snapshot.as_of_date, snapshot.source_fingerprint, snapshot.result_fingerprint, outcome, active_id))
    conn.execute("DELETE FROM relative_valuation_refresh_audit WHERE model_fingerprint=? AND audit_id NOT IN (SELECT audit_id FROM relative_valuation_refresh_audit WHERE model_fingerprint=? ORDER BY audit_id DESC LIMIT ?)",
                 (MODEL_FINGERPRINT, MODEL_FINGERPRINT, MAX_AUDIT_ROWS))


def apply_snapshot(conn: sqlite3.Connection, snapshot: RelativeValuationSnapshot,
                   inputs: Sequence[RelativeValuationInput], *, applied_at_utc: str,
                   inject_failure_at: str | None = None) -> ApplyReport:
    conn.row_factory = sqlite3.Row
    content, physical = validate_snapshot(snapshot, inputs)
    snapshot_id = _snapshot_id(snapshot, physical)
    existing_table = conn.execute("SELECT 1 FROM sqlite_schema WHERE name='relative_valuation_snapshot'").fetchone()
    active = None
    if existing_table:
        active = conn.execute("SELECT s.* FROM relative_valuation_active_snapshot a JOIN relative_valuation_snapshot s USING(snapshot_id) WHERE a.model_fingerprint=?", (MODEL_FINGERPRINT,)).fetchone()
    if active is not None and str(active["source_fingerprint"]) == snapshot.source_fingerprint and str(active["result_fingerprint"]) == snapshot.result_fingerprint:
        return ApplyReport("NO_CHANGE", str(active["snapshot_id"]), str(active["physical_content_fingerprint"]), 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           conn.execute("SELECT COUNT(*) FROM relative_valuation_snapshot WHERE model_fingerprint=?", (MODEL_FINGERPRINT,)).fetchone()[0])
    date_only = active is not None and _economic_bulk_fingerprint(_persisted_content(conn, str(active["snapshot_id"]))) == _economic_bulk_fingerprint(content)
    ensure_schema(conn, applied_at_utc=applied_at_utc)
    conn.commit()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if date_only:
            active_id = str(active["snapshot_id"])
            _audit(conn, snapshot, active_id, applied_at_utc, "DATE_ONLY_NO_CHANGE")
            conn.commit()
            retained = conn.execute("SELECT COUNT(*) FROM relative_valuation_snapshot WHERE model_fingerprint=?", (MODEL_FINGERPRINT,)).fetchone()[0]
            return ApplyReport("DATE_ONLY_NO_CHANGE", active_id, str(active["physical_content_fingerprint"]), 0, 0, 0, 0, 0, 0, 0, 0, 1, retained)
        prices = [row["current_price_date"] for row in content["companies"] if row["current_price_date"]]
        peer_eligible = sum(row["scope"] == "UNIVERSE" and row["status"] in {"RELATIVE_POSITION_READY", "PEER_GROUP_TOO_SMALL"} for row in content["peers"])
        values = (snapshot_id, MODEL_VERSION, MODEL_FINGERPRINT, PERSISTENCE_VERSION, LAYOUT_FINGERPRINT,
                  snapshot.semantic_mode, snapshot.as_of_date, applied_at_utc, snapshot.source_fingerprint,
                  snapshot.result_fingerprint, physical, min(prices) if prices else None, max(prices) if prices else None,
                  "WRITING", len(content["companies"]), sum(row["current_fresh"] for row in content["companies"]), peer_eligible,
                  sum(row["current_fresh"] and item["status"] == "READY" for row, item in zip(content["companies"], content["own_history"])),
                  sum(row["current_fresh"] and item["status"] == "LIMITED_HISTORY" for row, item in zip(content["companies"], content["own_history"])),
                  applied_at_utc, None)
        conn.execute("INSERT INTO relative_valuation_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        if inject_failure_at == "metadata": raise RuntimeError("INJECTED_METADATA")
        _insert_many(conn, "relative_valuation_company_result", snapshot_id, content["companies"])
        if inject_failure_at == "company": raise RuntimeError("INJECTED_COMPANY")
        _insert_many(conn, "relative_valuation_peer_position", snapshot_id, content["peers"])
        if inject_failure_at == "peer": raise RuntimeError("INJECTED_PEER")
        _insert_many(conn, "relative_valuation_own_history", snapshot_id, content["own_history"])
        if inject_failure_at == "own_history": raise RuntimeError("INJECTED_OWN_HISTORY")
        _insert_many(conn, "relative_valuation_component_history", snapshot_id, content["components"])
        if inject_failure_at == "component": raise RuntimeError("INJECTED_COMPONENT")
        if inject_failure_at == "before_reconciliation": raise RuntimeError("INJECTED_BEFORE_RECONCILIATION")
        persisted = _persisted_content(conn, snapshot_id)
        if physical_content_fingerprint(persisted) != physical:
            raise RuntimeError("RELATIVE_VALUATION_PERSISTED_CONTENT_MISMATCH")
        if inject_failure_at in {"before_activation", "after_reconciliation"}: raise RuntimeError("INJECTED_BEFORE_ACTIVATION")
        conn.execute("UPDATE relative_valuation_snapshot SET status='COMPLETE',completed_at_utc=? WHERE snapshot_id=?", (applied_at_utc, snapshot_id))
        old = conn.execute("SELECT snapshot_id FROM relative_valuation_active_snapshot WHERE model_fingerprint=?", (MODEL_FINGERPRINT,)).fetchone()
        conn.execute("INSERT INTO relative_valuation_active_snapshot VALUES (?,?,?) ON CONFLICT(model_fingerprint) DO UPDATE SET snapshot_id=excluded.snapshot_id,activated_at_utc=excluded.activated_at_utc", (MODEL_FINGERPRINT, snapshot_id, applied_at_utc))
        if inject_failure_at == "after_activation": raise RuntimeError("INJECTED_AFTER_ACTIVATION")
        stale = [row[0] for row in conn.execute("SELECT snapshot_id FROM relative_valuation_snapshot WHERE model_fingerprint=? AND status='COMPLETE' ORDER BY created_at_utc DESC,snapshot_id DESC LIMIT -1 OFFSET ?", (MODEL_FINGERPRINT, MAX_BULK_SNAPSHOTS))]
        deleted = 0
        for stale_id in stale:
            deleted += sum(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE snapshot_id=?", (stale_id,)).fetchone()[0] for table in ("relative_valuation_company_result","relative_valuation_peer_position","relative_valuation_own_history","relative_valuation_component_history"))
            conn.execute("DELETE FROM relative_valuation_snapshot WHERE snapshot_id=?", (stale_id,))
        if inject_failure_at == "cleanup": raise RuntimeError("INJECTED_CLEANUP")
        _audit(conn, snapshot, snapshot_id, applied_at_utc, "ACTIVATED")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    retained = conn.execute("SELECT COUNT(*) FROM relative_valuation_snapshot WHERE model_fingerprint=?", (MODEL_FINGERPRINT,)).fetchone()[0]
    return ApplyReport("ACTIVATED", snapshot_id, physical, len(content["companies"]), len(content["peers"]), len(content["own_history"]), len(content["components"]), deleted, 1, len(stale), 1 if old is None or old[0] != snapshot_id else 0, 1, retained)


def _persisted_content(conn: sqlite3.Connection, snapshot_id: str) -> dict[str, list[dict[str, Any]]]:
    tables = {
        "companies": ("relative_valuation_company_result", "company_id"),
        "peers": ("relative_valuation_peer_position", "company_id,scope"),
        "own_history": ("relative_valuation_own_history", "company_id"),
        "components": ("relative_valuation_component_history", "company_id,component_type"),
    }
    output: dict[str, list[dict[str, Any]]] = {}
    for key, (table, order) in tables.items():
        rows = []
        for row in conn.execute(f"SELECT * FROM {table} WHERE snapshot_id=? ORDER BY {order}", (snapshot_id,)):
            item = dict(row)
            item.pop("snapshot_id")
            rows.append(item)
        output[key] = rows
    return output


class RelativeValuationRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def active_snapshot_id(self, *, model_fingerprint: str) -> str | None:
        row = self.connection.execute("SELECT snapshot_id FROM relative_valuation_active_snapshot WHERE model_fingerprint=?", (model_fingerprint,)).fetchone()
        return str(row[0]) if row else None

    def previous_snapshot_id(self, *, model_fingerprint: str) -> str | None:
        active = self.active_snapshot_id(model_fingerprint=model_fingerprint)
        row = self.connection.execute("SELECT snapshot_id FROM relative_valuation_snapshot WHERE model_fingerprint=? AND status='COMPLETE' AND snapshot_id<>? ORDER BY created_at_utc DESC,snapshot_id DESC LIMIT 1", (model_fingerprint, active or "")).fetchone()
        return str(row[0]) if row else None

    def snapshot_metadata(self, snapshot_id: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM relative_valuation_snapshot WHERE snapshot_id=? AND model_fingerprint=? AND status='COMPLETE'", (snapshot_id, model_fingerprint)).fetchone()
        return dict(row) if row else None

    def active_metadata(self, *, model_fingerprint: str) -> dict[str, Any] | None:
        snapshot_id = self.active_snapshot_id(model_fingerprint=model_fingerprint)
        return self.snapshot_metadata(snapshot_id, model_fingerprint=model_fingerprint) if snapshot_id else None

    def company(self, company_id: int, *, model_fingerprint: str, snapshot_id: str | None = None) -> dict[str, Any] | None:
        target = snapshot_id or self.active_snapshot_id(model_fingerprint=model_fingerprint)
        if target is None or self.snapshot_metadata(target, model_fingerprint=model_fingerprint) is None:
            return None
        row = self.connection.execute("SELECT * FROM relative_valuation_company_result WHERE snapshot_id=? AND company_id=?", (target, company_id)).fetchone()
        if row is None: return None
        output = dict(row)
        output["peer_positions"] = [dict(item) for item in self.connection.execute("SELECT * FROM relative_valuation_peer_position WHERE snapshot_id=? AND company_id=? ORDER BY scope", (target, company_id))]
        output["own_history"] = dict(self.connection.execute("SELECT * FROM relative_valuation_own_history WHERE snapshot_id=? AND company_id=?", (target, company_id)).fetchone())
        output["components"] = [dict(item) for item in self.connection.execute(
            "SELECT * FROM relative_valuation_component_history WHERE snapshot_id=? AND company_id=? "
            "ORDER BY CASE component_type WHEN 'OPERATING_YIELD' THEN 1 WHEN 'FCF_YIELD' THEN 2 ELSE 3 END",
            (target, company_id),
        )]
        return output

    def company_by_ticker(self, ticker: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        target = self.active_snapshot_id(model_fingerprint=model_fingerprint)
        if target is None:
            return None
        rows = self.connection.execute(
            "SELECT company_id FROM relative_valuation_company_result WHERE snapshot_id=? AND UPPER(ticker)=UPPER(?)",
            (target, ticker),
        ).fetchall()
        if len(rows) != 1:
            return None
        return self.company(int(rows[0][0]), model_fingerprint=model_fingerprint)

    def companies(self, company_ids: Sequence[int], *, model_fingerprint: str) -> list[dict[str, Any]]:
        return [row for company_id in company_ids if (row := self.company(company_id, model_fingerprint=model_fingerprint)) is not None]

    def current_universe(self, *, model_fingerprint: str) -> list[dict[str, Any]]:
        target = self.active_snapshot_id(model_fingerprint=model_fingerprint)
        if target is None: return []
        return [dict(row) for row in self.connection.execute("SELECT * FROM relative_valuation_company_result WHERE snapshot_id=? ORDER BY company_id", (target,))]

    def peer_group(self, *, model_fingerprint: str, scope: str, group_id: str) -> list[dict[str, Any]]:
        target = self.active_snapshot_id(model_fingerprint=model_fingerprint)
        if target is None or scope not in PEER_SCOPES: return []
        return [dict(row) for row in self.connection.execute("SELECT * FROM relative_valuation_peer_position WHERE snapshot_id=? AND scope=? AND group_id=? ORDER BY company_id", (target, scope, group_id))]


def quick_check(conn: sqlite3.Connection, *, model_fingerprint: str = MODEL_FINGERPRINT) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    active = conn.execute("SELECT snapshot_id FROM relative_valuation_active_snapshot WHERE model_fingerprint=?", (model_fingerprint,)).fetchall()
    snapshots = conn.execute("SELECT snapshot_id FROM relative_valuation_snapshot WHERE model_fingerprint=?", (model_fingerprint,)).fetchall()
    errors: list[str] = []
    if len(active) > 1 or len(snapshots) > MAX_BULK_SNAPSHOTS: errors.append("RETENTION_OR_POINTER_COUNT")
    for row in snapshots:
        sid = row[0]
        metadata = conn.execute("SELECT * FROM relative_valuation_snapshot WHERE snapshot_id=?", (sid,)).fetchone()
        counts = {
            "company": conn.execute("SELECT COUNT(*) FROM relative_valuation_company_result WHERE snapshot_id=?", (sid,)).fetchone()[0],
            "peer": conn.execute("SELECT COUNT(*) FROM relative_valuation_peer_position WHERE snapshot_id=?", (sid,)).fetchone()[0],
            "own": conn.execute("SELECT COUNT(*) FROM relative_valuation_own_history WHERE snapshot_id=?", (sid,)).fetchone()[0],
            "component": conn.execute("SELECT COUNT(*) FROM relative_valuation_component_history WHERE snapshot_id=?", (sid,)).fetchone()[0],
        }
        if counts != {"company": metadata["company_count"], "peer": 4*metadata["company_count"], "own": metadata["company_count"], "component": 3*metadata["company_count"]}: errors.append(f"ROW_COUNTS:{sid}")
        if physical_content_fingerprint(_persisted_content(conn, sid)) != metadata["physical_content_fingerprint"]: errors.append(f"PHYSICAL:{sid}")
        for item in conn.execute("SELECT * FROM relative_valuation_peer_position WHERE snapshot_id=? AND percentile IS NOT NULL", (sid,)):
            if item["peer_count"] is None or item["peer_count"] <= 1 or not math.isclose(
                item["percentile"], 100.0 * (item["average_rank"] - 1.0) / (item["peer_count"] - 1.0), abs_tol=1e-12,
            ):
                errors.append(f"PEER_PERCENTILE:{sid}:{item['company_id']}:{item['scope']}")
        for item in conn.execute("SELECT * FROM relative_valuation_component_history WHERE snapshot_id=?", (sid,)):
            if item["less_count"] + item["equal_count"] + item["greater_count"] != item["positive_count"]:
                errors.append(f"COMPONENT_COUNTS:{sid}:{item['company_id']}:{item['component_type']}")
            if item["historical_percentile"] is not None:
                expected = 100.0 * (item["less_count"] + 0.5 * item["equal_count"]) / item["positive_count"]
                if not math.isclose(item["historical_percentile"], expected, abs_tol=1e-12):
                    errors.append(f"COMPONENT_PERCENTILE:{sid}:{item['company_id']}:{item['component_type']}")
        aggregates = conn.execute(
            "SELECT o.company_id,o.percentile,SUM(c.weight*c.historical_percentile) expected "
            "FROM relative_valuation_own_history o JOIN relative_valuation_component_history c "
            "USING(snapshot_id,company_id) WHERE o.snapshot_id=? AND o.percentile IS NOT NULL GROUP BY o.company_id,o.percentile",
            (sid,),
        )
        for item in aggregates:
            if not math.isclose(item["percentile"], item["expected"], abs_tol=1e-12):
                errors.append(f"AGGREGATE:{sid}:{item['company_id']}")
    sqlite_ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    foreign_keys = list(conn.execute("PRAGMA foreign_key_check"))
    return {
        "ok": not errors and sqlite_ok and not foreign_keys,
        "errors": errors, "active_count": len(active), "snapshot_count": len(snapshots),
        "sqlite_quick_check": "ok" if sqlite_ok else "failed",
        "foreign_key_violations": len(foreign_keys),
    }
