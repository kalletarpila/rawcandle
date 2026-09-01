from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.lifecycle.engine import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    TTM_MODEL_VERSION,
    LifecycleMachineState,
    LifecycleObservation,
    LifecycleState,
    LifecycleStatus,
    advance_state_machine,
    classify_raw_state,
)


HISTORY_MODE = "REVISED_HISTORY"
TABLE_NAME = "lifecycle_revised_result"

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    lifecycle_revised_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    quarter_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_sequence INTEGER NOT NULL,
    period_end TEXT NOT NULL,
    source_available_date TEXT,
    history_mode TEXT NOT NULL CHECK (history_mode = 'REVISED_HISTORY'),
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    source_input_fingerprint TEXT NOT NULL,
    raw_state TEXT NOT NULL,
    final_state TEXT,
    lifecycle_status TEXT NOT NULL,
    startup_profile TEXT,
    final_startup_profile TEXT,
    reason_code TEXT NOT NULL,
    transition_reason TEXT NOT NULL,
    missing_inputs_json TEXT NOT NULL,
    last_confirmed_state TEXT,
    candidate_state TEXT,
    candidate_count INTEGER NOT NULL CHECK (candidate_count IN (0,1)),
    revenue_growth_yoy_ttm REAL,
    ebit_margin_ttm REAL,
    ebit_margin_direction REAL,
    fcf_margin_ttm REAL,
    evidence_json TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    UNIQUE(company_id, fiscal_year, fiscal_quarter, model_fingerprint, history_mode)
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_revised_current
    ON {TABLE_NAME}(model_fingerprint, history_mode, company_id, fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_revised_class
    ON {TABLE_NAME}(model_fingerprint, history_mode, lifecycle_status, final_state, final_startup_profile);
"""

LOGICAL_FIELDS = (
    "company_id", "security_id", "ticker", "quarter_id", "fiscal_year", "fiscal_quarter",
    "fiscal_sequence", "period_end", "source_available_date", "history_mode", "model_version",
    "model_fingerprint", "source_input_fingerprint", "raw_state", "final_state",
    "lifecycle_status", "startup_profile", "final_startup_profile", "reason_code",
    "transition_reason", "missing_inputs_json", "last_confirmed_state", "candidate_state",
    "candidate_count", "revenue_growth_yoy_ttm", "ebit_margin_ttm",
    "ebit_margin_direction", "fcf_margin_ttm", "evidence_json",
)


@dataclass(frozen=True)
class RevisedSource:
    observations: tuple[LifecycleObservation, ...]
    tickers: Mapping[int, str | None]
    fiscal_sequences: Mapping[int, int]
    source_input_fingerprint: str


@dataclass(frozen=True)
class ReplaceReport:
    rows_before: int
    rows_after: int
    rows_deleted: int
    rows_inserted: int
    rows_unchanged: int
    result_fingerprint: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fiscal_sequence(year: int, quarter: str) -> int:
    positions = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
    if quarter not in positions:
        raise ValueError(f"INVALID_FISCAL_QUARTER:{quarter}")
    return int(year) * 4 + positions[quarter]


def _hash(value: Any) -> str:
    def normalized(item: Any) -> Any:
        if isinstance(item, float) and not math.isfinite(item):
            return {"non_finite": str(item)}
        if isinstance(item, Mapping):
            return {str(key): normalized(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalized(child) for child in item]
        return item

    payload = json.dumps(normalized(value), sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number


def _read_connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def load_revised_source(
    canonical_db: Path,
    *,
    company_ids: Sequence[int] = (),
    tickers: Sequence[str] = (),
) -> RevisedSource:
    filters: list[str] = ["t.model_version = ?"]
    params: list[Any] = [TTM_MODEL_VERSION]
    if company_ids:
        filters.append(f"t.company_id IN ({','.join('?' for _ in company_ids)})")
        params.extend(int(value) for value in company_ids)
    if tickers:
        filters.append(f"UPPER(s.current_ticker) IN ({','.join('?' for _ in tickers)})")
        params.extend(value.upper() for value in tickers)
    where = " AND ".join(filters)
    with _read_connection(canonical_db) as conn:
        rows = [dict(row) for row in conn.execute(
            f"""
            SELECT t.*, s.current_ticker AS ticker
            FROM v4_ttm_values t
            LEFT JOIN security s ON s.security_id=t.security_id AND s.company_id=t.company_id
            WHERE {where}
            ORDER BY t.company_id, t.endpoint_fiscal_year,
                     CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                     t.ttm_id
            """,
            params,
        )]
        if tickers:
            found = {str(row["ticker"]).upper() for row in rows if row.get("ticker")}
            missing = sorted(set(value.upper() for value in tickers) - found)
            if missing:
                raise ValueError(f"TICKER_NOT_FOUND:{','.join(missing)}")
        if not rows:
            return RevisedSource((), {}, {}, _hash([]))
        ttm_ids = [int(row["ttm_id"]) for row in rows]
        inputs: dict[int, list[dict[str, Any]]] = defaultdict(list)
        batch_size = 900
        for start in range(0, len(ttm_ids), batch_size):
            batch = ttm_ids[start:start + batch_size]
            sql = f"""
                SELECT i.*, q.company_id, f.revenue
                FROM v4_ttm_input_quarter i
                JOIN v4_quarter q ON q.quarter_id=i.input_quarter_id
                JOIN v4_quarter_financials f ON f.quarter_id=i.input_quarter_id
                WHERE i.ttm_id IN ({','.join('?' for _ in batch)})
                ORDER BY i.ttm_id, i.input_position
            """
            for input_row in conn.execute(sql, batch):
                inputs[int(input_row["ttm_id"])].append(dict(input_row))

    identities: set[tuple[int, int]] = set()
    by_company: dict[int, dict[int, Mapping[str, Any]]] = defaultdict(dict)
    tickers_by_quarter: dict[int, str | None] = {}
    sequences: dict[int, int] = {}
    for row in rows:
        company_id = int(row["company_id"])
        sequence = fiscal_sequence(int(row["endpoint_fiscal_year"]), str(row["endpoint_fiscal_quarter"]))
        identity = (company_id, sequence)
        if identity in identities:
            raise ValueError(f"DUPLICATE_CANONICAL_LIFECYCLE_INPUT:{company_id}:{sequence}")
        identities.add(identity)
        if row.get("security_id") is not None and row.get("ticker") is None:
            raise ValueError(f"AMBIGUOUS_SECURITY_IDENTITY:{company_id}:{row['endpoint_quarter_id']}")
        by_company[company_id][sequence] = row
        quarter_id = int(row["endpoint_quarter_id"])
        tickers_by_quarter[quarter_id] = row.get("ticker")
        sequences[quarter_id] = sequence

    observations: list[LifecycleObservation] = []
    source_payload: list[dict[str, Any]] = []
    for company_id in sorted(by_company):
        company_rows = by_company[company_id]
        for sequence in sorted(company_rows):
            row = company_rows[sequence]
            lag = company_rows.get(sequence - 4)
            chain_valid = lag is not None and all(value in company_rows for value in range(sequence - 4, sequence + 1))
            input_rows = inputs.get(int(row["ttm_id"]), [])
            positions = [int(item["input_position"]) for item in input_rows]
            input_company_ok = all(int(item["company_id"]) == company_id for item in input_rows)
            input_chain_ok = len(input_rows) == 4 and positions == [1, 2, 3, 4]
            if int(row.get("core_ttm_ready") or 0) == 1 and (not input_company_ok or not input_chain_ok):
                raise ValueError(f"BROKEN_READY_TTM_INPUT_CHAIN:{company_id}:{row['endpoint_quarter_id']}")
            quarterly_revenues = tuple(_number(item.get("revenue")) for item in input_rows)
            source_version = _hash({
                "ttm_output": row.get("output_fingerprint"),
                "ttm_input": row.get("input_values_hash"),
                "lag4_ttm_output": lag.get("output_fingerprint") if lag and chain_valid else None,
                "quarter_inputs": [
                    [item.get("input_quarter_id"), item.get("input_values_hash"), item.get("revenue")]
                    for item in input_rows
                ],
            })
            observation = LifecycleObservation(
                company_id=company_id,
                security_id=int(row["security_id"]) if row.get("security_id") is not None else None,
                endpoint_quarter_id=int(row["endpoint_quarter_id"]),
                endpoint_fiscal_year=int(row["endpoint_fiscal_year"]),
                endpoint_fiscal_quarter=str(row["endpoint_fiscal_quarter"]),
                period_end=str(row["period_end"]),
                source_available_date=row.get("ttm_source_available_date"),
                source_data_version=source_version,
                core_ttm_ready=bool(row.get("core_ttm_ready")),
                ttm_revenue=_number(row.get("ttm_revenue")),
                ttm_ebit=_number(row.get("ttm_ebit")),
                ttm_free_cashflow=_number(row.get("ttm_free_cashflow")),
                lag4_ttm_revenue=_number(lag.get("ttm_revenue")) if lag and chain_valid else None,
                lag4_ttm_ebit=_number(lag.get("ttm_ebit")) if lag and chain_valid else None,
                lag4_chain_valid=chain_valid,
                input_quarter_revenues=quarterly_revenues,
                ttm_model_version=str(row["model_version"]),
            )
            observations.append(observation)
            source_payload.append({
                "observation": asdict(observation),
                "ticker": row.get("ticker"),
                "fiscal_sequence": sequence,
            })
    return RevisedSource(tuple(observations), tickers_by_quarter, sequences, _hash(source_payload))


def build_revised_results(source: RevisedSource, *, generated_at: str | None = None) -> list[dict[str, Any]]:
    generated = generated_at or utc_now()
    grouped: dict[int, list[LifecycleObservation]] = defaultdict(list)
    for observation in source.observations:
        grouped[observation.company_id].append(observation)
    output: list[dict[str, Any]] = []
    for company_id in sorted(grouped):
        state = LifecycleMachineState()
        observations = sorted(grouped[company_id], key=lambda item: source.fiscal_sequences[item.endpoint_quarter_id])
        for observation in observations:
            raw = classify_raw_state(observation)
            state, result = advance_state_machine(state, raw)
            metrics = raw.metrics
            evidence = {
                "input_quarter_revenues": list(observation.input_quarter_revenues),
                "lag4_chain_valid": observation.lag4_chain_valid,
                "source_data_version": observation.source_data_version,
                "ttm_model_version": observation.ttm_model_version,
            }
            output.append({
                "company_id": company_id,
                "security_id": observation.security_id,
                "ticker": source.tickers.get(observation.endpoint_quarter_id),
                "quarter_id": observation.endpoint_quarter_id,
                "fiscal_year": observation.endpoint_fiscal_year,
                "fiscal_quarter": observation.endpoint_fiscal_quarter,
                "fiscal_sequence": source.fiscal_sequences[observation.endpoint_quarter_id],
                "period_end": observation.period_end,
                "source_available_date": observation.source_available_date,
                "history_mode": HISTORY_MODE,
                "model_version": MODEL_VERSION,
                "model_fingerprint": MODEL_FINGERPRINT,
                "source_input_fingerprint": observation.source_data_version,
                "raw_state": raw.raw_state.value,
                "final_state": result.final_state.value if result.final_state else None,
                "lifecycle_status": result.lifecycle_status.value,
                "startup_profile": raw.startup_profile.value if raw.startup_profile else None,
                "final_startup_profile": result.final_startup_profile.value if result.final_startup_profile else None,
                "reason_code": raw.reason_code.value,
                "transition_reason": result.transition_reason.value,
                "missing_inputs_json": json.dumps(raw.missing_inputs, separators=(",", ":")),
                "last_confirmed_state": result.last_confirmed_state.value if result.last_confirmed_state else None,
                "candidate_state": result.candidate_state.value if result.candidate_state else None,
                "candidate_count": result.candidate_count,
                "revenue_growth_yoy_ttm": metrics.revenue_growth_yoy_ttm,
                "ebit_margin_ttm": metrics.ebit_margin_ttm,
                "ebit_margin_direction": metrics.ebit_margin_direction,
                "fcf_margin_ttm": metrics.fcf_margin_ttm,
                "evidence_json": json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False),
                "generated_at_utc": generated,
            })
    validate_results(output)
    return output


def validate_results(rows: Sequence[Mapping[str, Any]]) -> None:
    seen: set[tuple[Any, ...]] = set()
    previous: dict[int, int] = {}
    for row in rows:
        if row.get("history_mode") != HISTORY_MODE:
            raise ValueError("INVALID_HISTORY_MODE")
        if row.get("model_version") != MODEL_VERSION or row.get("model_fingerprint") != MODEL_FINGERPRINT:
            raise ValueError("LIFECYCLE_MODEL_IDENTITY_MISMATCH")
        identity = (row.get("company_id"), row.get("fiscal_year"), row.get("fiscal_quarter"))
        if identity in seen:
            raise ValueError(f"DUPLICATE_REVISED_RESULT:{identity}")
        seen.add(identity)
        sequence = int(row["fiscal_sequence"])
        company_id = int(row["company_id"])
        if company_id in previous and sequence <= previous[company_id]:
            raise ValueError(f"NON_INCREASING_FISCAL_SEQUENCE:{company_id}")
        previous[company_id] = sequence
        not_ready = row.get("lifecycle_status") == LifecycleStatus.NOT_READY.value
        if not_ready != (row.get("raw_state") == LifecycleState.UNCLASSIFIED.value):
            raise ValueError("UNCLASSIFIED_STATUS_MISMATCH")
        if not_ready and row.get("final_state") is not None:
            raise ValueError("UNCLASSIFIED_PUBLISHED_FINAL_STATE")
        if int(row.get("candidate_count", -1)) not in (0, 1):
            raise ValueError("INVALID_CANDIDATE_COUNT")
        for field in ("revenue_growth_yoy_ttm", "ebit_margin_ttm", "ebit_margin_direction", "fcf_margin_ttm"):
            value = row.get(field)
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"NON_FINITE_RESULT:{field}")


def logical_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    values = [[row.get(field) for field in LOGICAL_FIELDS] for row in rows]
    values.sort(key=lambda item: (item[0], item[6]))
    return _hash(values)


def ensure_revised_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def persisted_rows(conn: sqlite3.Connection, model_fingerprint: str = MODEL_FINGERPRINT) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        f"SELECT * FROM {TABLE_NAME} WHERE history_mode=? AND model_fingerprint=? ORDER BY company_id,fiscal_sequence",
        (HISTORY_MODE, model_fingerprint),
    )]


def replace_revised_results(
    conn: sqlite3.Connection,
    rows: Sequence[Mapping[str, Any]],
    *,
    company_scope: Sequence[int] | None = None,
) -> ReplaceReport:
    validate_results(rows)
    target_companies = {int(row["company_id"]) for row in rows}
    if company_scope is not None:
        scope = {int(company_id) for company_id in company_scope}
        if not target_companies.issubset(scope):
            raise ValueError("RESULT_COMPANY_OUTSIDE_REPLACEMENT_SCOPE")
    else:
        scope = None
    target_fp = logical_fingerprint(rows)
    ensure_revised_schema(conn)
    all_existing = persisted_rows(conn)
    existing = all_existing if scope is None else [row for row in all_existing if int(row["company_id"]) in scope]
    before = len(existing)
    if logical_fingerprint(existing) == target_fp:
        return ReplaceReport(before, before, 0, 0, before, target_fp)
    columns = (*LOGICAL_FIELDS, "generated_at_utc")
    placeholders = ",".join("?" for _ in columns)
    conn.execute("SAVEPOINT lifecycle_revised_replace")
    try:
        if scope is None:
            conn.execute(
                f"DELETE FROM {TABLE_NAME} WHERE history_mode=? AND model_fingerprint=?",
                (HISTORY_MODE, MODEL_FINGERPRINT),
            )
        elif scope:
            conn.execute(
                f"DELETE FROM {TABLE_NAME} WHERE history_mode=? AND model_fingerprint=? "
                f"AND company_id IN ({','.join('?' for _ in scope)})",
                (HISTORY_MODE, MODEL_FINGERPRINT, *sorted(scope)),
            )
        conn.executemany(
            f"INSERT INTO {TABLE_NAME} ({','.join(columns)}) VALUES ({placeholders})",
            [[row.get(column) for column in columns] for row in rows],
        )
        all_stored = persisted_rows(conn)
        stored = all_stored if scope is None else [row for row in all_stored if int(row["company_id"]) in scope]
        if logical_fingerprint(stored) != target_fp:
            raise RuntimeError("PERSISTED_LIFECYCLE_FINGERPRINT_MISMATCH")
        conn.execute("RELEASE lifecycle_revised_replace")
    except Exception:
        conn.execute("ROLLBACK TO lifecycle_revised_replace")
        conn.execute("RELEASE lifecycle_revised_replace")
        raise
    return ReplaceReport(before, len(rows), before, len(rows), 0, target_fp)


class RevisedLifecycleRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"""SELECT * FROM {TABLE_NAME}
                WHERE company_id=? AND history_mode=? AND model_fingerprint=?
                ORDER BY fiscal_sequence DESC LIMIT 1""",
            (company_id, HISTORY_MODE, model_fingerprint),
        ).fetchone()
        return dict(row) if row else None

    def current_universe(
        self,
        *,
        model_fingerprint: str,
        lifecycle_status: str | None = None,
        lifecycle_class: str | None = None,
        startup_profile: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = ["r.history_mode=?", "r.model_fingerprint=?"]
        params: list[Any] = [HISTORY_MODE, model_fingerprint]
        for column, value in (("lifecycle_status", lifecycle_status), ("final_state", lifecycle_class), ("final_startup_profile", startup_profile)):
            if value is not None:
                filters.append(f"r.{column}=?")
                params.append(value)
        rows = self.conn.execute(
            f"""SELECT r.* FROM {TABLE_NAME} r
                WHERE {' AND '.join(filters)}
                  AND r.fiscal_sequence=(SELECT MAX(x.fiscal_sequence) FROM {TABLE_NAME} x
                    WHERE x.company_id=r.company_id AND x.history_mode=r.history_mode
                      AND x.model_fingerprint=r.model_fingerprint)
                ORDER BY r.company_id""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            f"""SELECT * FROM {TABLE_NAME} WHERE company_id=? AND history_mode=? AND model_fingerprint=?
                ORDER BY fiscal_sequence""",
            (company_id, HISTORY_MODE, model_fingerprint),
        )]

    def fiscal_quarter(
        self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"""SELECT * FROM {TABLE_NAME} WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?
                AND history_mode=? AND model_fingerprint=?""",
            (company_id, fiscal_year, fiscal_quarter, HISTORY_MODE, model_fingerprint),
        ).fetchone()
        return dict(row) if row else None


def summarize(rows: Sequence[Mapping[str, Any]], source_fingerprint: str) -> dict[str, Any]:
    dates = [str(row["source_available_date"]) for row in rows if row.get("source_available_date")]
    periods = [str(row["period_end"]) for row in rows]
    return {
        "history_mode": HISTORY_MODE,
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "source_input_fingerprint": source_fingerprint,
        "result_fingerprint": logical_fingerprint(rows),
        "companies": len({row["company_id"] for row in rows}),
        "observations": len(rows),
        "raw_state_counts": dict(sorted(Counter(row["raw_state"] for row in rows).items())),
        "final_state_counts": dict(sorted(Counter(row["final_state"] or "NONE" for row in rows).items())),
        "status_counts": dict(sorted(Counter(row["lifecycle_status"] for row in rows).items())),
        "startup_profile_counts": dict(sorted(Counter(row["startup_profile"] or "NONE" for row in rows).items())),
        "reason_counts": dict(sorted(Counter(row["reason_code"] for row in rows).items())),
        "earliest_period_end": min(periods) if periods else None,
        "latest_period_end": max(periods) if periods else None,
        "earliest_source_available_date": min(dates) if dates else None,
        "latest_source_available_date": max(dates) if dates else None,
    }


def quick_check(
    conn: sqlite3.Connection,
    *,
    expected_rows: Sequence[Mapping[str, Any]] | None = None,
    model_fingerprint: str = MODEL_FINGERPRINT,
) -> dict[str, Any]:
    details: list[str] = []
    try:
        rows = persisted_rows(conn, model_fingerprint)
        validate_results(rows)
        repository = RevisedLifecycleRepository(conn)
        current = repository.current_universe(model_fingerprint=model_fingerprint)
        if len(current) != len({row["company_id"] for row in rows}):
            details.append("CURRENT_UNIVERSE_COUNT_MISMATCH")
        if any(row["raw_state"] == "UNCLASSIFIED" and (row["lifecycle_status"] != "LIFECYCLE_NOT_READY" or row["final_state"] is not None) for row in rows):
            details.append("UNCLASSIFIED_PUBLICATION_MISMATCH")
        ordered_by_company: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            ordered_by_company[int(row["company_id"])].append(row)
            if row["raw_state"] == "DISTRESSED" and row["final_state"] != "DISTRESSED":
                details.append(f"DISTRESSED_IMMEDIATE_ENTRY_MISMATCH:{row['company_id']}:{row['quarter_id']}")
        for company_rows in ordered_by_company.values():
            ordered = sorted(company_rows, key=lambda item: int(item["fiscal_sequence"]))
            for previous, current_row in zip(ordered, ordered[1:]):
                if (
                    previous["final_state"] == "DISTRESSED"
                    and current_row["raw_state"] not in ("DISTRESSED", "UNCLASSIFIED")
                    and current_row["final_state"] != "DISTRESSED"
                    and current_row["transition_reason"] != "CANDIDATE_CONFIRMED"
                ):
                    details.append(
                        f"DISTRESSED_EXIT_CONFIRMATION_MISMATCH:{current_row['company_id']}:{current_row['quarter_id']}"
                    )
        duplicates = conn.execute(
            f"""SELECT COUNT(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,COUNT(*) n FROM {TABLE_NAME}
                WHERE history_mode=? AND model_fingerprint=? GROUP BY 1,2,3 HAVING n>1)""",
            (HISTORY_MODE, model_fingerprint),
        ).fetchone()[0]
        if duplicates:
            details.append("DUPLICATE_LOGICAL_ROWS")
        objects = [str(row[0]).lower() for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index','view')")]
        if any("lifecycle_pit" in name for name in objects):
            details.append("RETIRED_SCHEMA_OBJECT_PRESENT")
        sqlite_result = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        if sqlite_result.lower() != "ok":
            details.append(f"SQLITE_QUICK_CHECK:{sqlite_result}")
        actual_fp = logical_fingerprint(rows)
        if expected_rows is not None:
            expected_companies = {int(row["company_id"]) for row in expected_rows}
            comparable = [row for row in rows if int(row["company_id"]) in expected_companies]
            if logical_fingerprint(comparable) != logical_fingerprint(expected_rows):
                details.append("DIRECT_REPLAY_MISMATCH")
    except Exception as exc:
        details.append(f"VALIDATION_ERROR:{exc}")
        rows = []
        current = []
        actual_fp = ""
        sqlite_result = "not_run"
    return {
        "ok": not details,
        "details": details,
        "rows": len(rows),
        "current_companies": len(current),
        "result_fingerprint": actual_fp,
        "sqlite_quick_check": sqlite_result,
    }
