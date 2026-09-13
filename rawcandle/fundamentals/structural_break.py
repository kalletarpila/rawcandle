from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1"
EVENT_TABLE = "fundamentals_economic_structural_event"
QUARTER_TABLE = "fundamentals_quarter_economic_regime"
TTM_TABLE = "fundamentals_ttm_economic_regime"
STRUCTURAL_BREAKING_STATUSES = {
    "MAJOR_BUSINESS_COMBINATION",
    "REVERSE_MERGER_MAJOR_BUSINESS_CHANGE",
    "BUSINESS_COMPARABILITY_REVIEW_REQUIRED",
    "UNRESOLVED_EVENT_DATE",
    "UNRESOLVED_FISCAL_BOUNDARY",
}
CONTINUOUS_STATUSES = {
    "NO_ECONOMIC_BREAK",
    "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE",
    "TICKER_REUSE_SEPARATION",
}


@dataclass(frozen=True)
class StructuralEligibility:
    company_id: int
    quarter_id: int | None
    ttm_id: int | None
    eligible: bool
    reason_code: str
    event_id: str | None
    event_type: str | None
    event_date: str | None
    comparability_status: str | None
    ttm_regime_status: str


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}


def has_structural_contract(conn: sqlite3.Connection) -> bool:
    return EVENT_TABLE in _tables(conn) and TTM_TABLE in _tables(conn)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {EVENT_TABLE}(
            event_id TEXT PRIMARY KEY,
            contract_version TEXT NOT NULL,
            company_id INTEGER NOT NULL,
            security_id INTEGER,
            provider TEXT,
            provider_security_id TEXT,
            predecessor_ticker TEXT,
            successor_ticker TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT,
            comparability_status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            effective_date TEXT,
            evidence_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            economic_event_fingerprint TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS {QUARTER_TABLE}(
            quarter_id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES {EVENT_TABLE}(event_id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL,
            period_end TEXT NOT NULL,
            source_availability_date TEXT,
            economic_regime TEXT NOT NULL,
            regime_reason TEXT NOT NULL,
            regime_fingerprint TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS {TTM_TABLE}(
            ttm_id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES {EVENT_TABLE}(event_id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL,
            endpoint_quarter_id INTEGER NOT NULL,
            endpoint_period_end TEXT NOT NULL,
            endpoint_available_date TEXT,
            ttm_regime_status TEXT NOT NULL,
            regime_reason TEXT NOT NULL,
            input_regimes_json TEXT NOT NULL,
            same_regime_observation_count INTEGER NOT NULL,
            regime_fingerprint TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_structural_event_company
            ON {EVENT_TABLE}(company_id, successor_ticker);
        CREATE INDEX IF NOT EXISTS idx_structural_quarter_company
            ON {QUARTER_TABLE}(company_id, economic_regime);
        CREATE INDEX IF NOT EXISTS idx_structural_ttm_company
            ON {TTM_TABLE}(company_id, endpoint_quarter_id, ttm_regime_status);
        """
    )


def normalize_status(value: str) -> str:
    return "NO_ECONOMIC_BREAK" if value == "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE" else value


def default_events(transitions: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    events = []
    for row in transitions:
        status = str(row["structural_break"])
        review = "ACCEPTED" if status != "BUSINESS_COMPARABILITY_REVIEW_REQUIRED" else "REVIEW_REQUIRED"
        events.append(
            {
                "predecessor_ticker": str(row["historical_ticker"]),
                "successor_ticker": str(row["current_ticker"]),
                "event_type": status,
                "event_date": str(row.get("event_date") or row.get("effective_date")),
                "effective_date": str(row.get("effective_date") or row.get("event_date")),
                "comparability_status": normalize_status(status),
                "review_status": review,
                "reason": str(row.get("semantics") or status),
                "provider": "SHARADAR",
                "provider_security_id": str(row.get("permaticker") or ""),
                "evidence": {
                    "phase": "PHASE13F3_3",
                    "transition": dict(row),
                    "identity_rule": "stable_provider_identity_required_when_available",
                    "period_start_policy": "explicit_or_authoritative_only",
                },
            }
        )
    return tuple(events)


def _resolve_event_identity(conn: sqlite3.Connection, event: Mapping[str, Any]) -> tuple[int, int | None, str]:
    provider = str(event.get("provider") or "")
    provider_security_id = str(event.get("provider_security_id") or "")
    if provider and provider_security_id and "provider_security_identity" in _tables(conn):
        row = conn.execute(
            "SELECT s.company_id,s.security_id "
            "FROM provider_security_identity p JOIN security s USING(security_id) "
            "WHERE p.provider=? AND p.provider_security_id=?",
            (provider, provider_security_id),
        ).fetchone()
        if row is not None:
            return int(row[0]), int(row[1]), "PROVIDER_SECURITY_IDENTITY"
    rows = conn.execute(
        "SELECT company_id,security_id FROM security WHERE active=1 AND UPPER(current_ticker)=?",
        (str(event["successor_ticker"]).upper(),),
    ).fetchall()
    if len(rows) == 1:
        return int(rows[0][0]), int(rows[0][1]), "UNIQUE_ACTIVE_TICKER_FALLBACK"
    raise LookupError(f"STRUCTURAL_EVENT_IDENTITY_UNRESOLVED:{event['successor_ticker']}")


def _quarter_regime(period_end: str, event_date: str | None, status: str) -> tuple[str, str]:
    normalized = normalize_status(status)
    if normalized in CONTINUOUS_STATUSES:
        return "SINGLE_CONTINUOUS_REGIME", "NO_ECONOMIC_BREAK"
    if not event_date:
        return "UNRESOLVED", "UNRESOLVED_EVENT_DATE"
    if period_end < event_date:
        return "PRE_EVENT", "PERIOD_END_BEFORE_EVENT"
    return "UNRESOLVED", "UNRESOLVED_FISCAL_BOUNDARY"


def _ttm_regime(input_regimes: Sequence[str], status: str) -> tuple[str, str, int]:
    normalized = normalize_status(status)
    if normalized in CONTINUOUS_STATUSES:
        return "SINGLE_CONTINUOUS_REGIME", "NO_ECONOMIC_BREAK", len(input_regimes)
    counts = Counter(input_regimes)
    if counts == Counter({"PRE_EVENT": 4}):
        return "PRE_EVENT_COHERENT", "FOUR_PRE_EVENT_INPUT_QUARTERS", 4
    if counts == Counter({"POST_EVENT_CLEAN": 4}):
        return "POST_EVENT_COHERENT", "FOUR_POST_EVENT_CLEAN_INPUT_QUARTERS", 4
    if "UNRESOLVED" in counts:
        return "STRUCTURAL_NOT_READY", "UNRESOLVED_FISCAL_BOUNDARY", counts["UNRESOLVED"]
    return "STRUCTURAL_NOT_READY", "TTM_INPUTS_CROSS_ECONOMIC_REGIME", max(counts.values() or [0])


def apply_contract(
    canonical_db: Path,
    *,
    events: Sequence[Mapping[str, Any]],
    applied_at_utc: str,
) -> dict[str, Any]:
    with sqlite3.connect(canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            ensure_schema(conn)
            conn.execute(f"DELETE FROM {TTM_TABLE}")
            conn.execute(f"DELETE FROM {QUARTER_TABLE}")
            conn.execute(f"DELETE FROM {EVENT_TABLE}")
            event_rows = []
            quarter_rows = []
            ttm_rows = []
            for event in events:
                company_id, security_id, identity_status = _resolve_event_identity(conn, event)
                payload = {
                    "contract_version": CONTRACT_VERSION,
                    "company_id": company_id,
                    "security_id": security_id,
                    "successor_ticker": str(event["successor_ticker"]).upper(),
                    "predecessor_ticker": str(event.get("predecessor_ticker") or "").upper() or None,
                    "event_type": str(event["event_type"]),
                    "event_date": event.get("event_date"),
                    "comparability_status": normalize_status(str(event["comparability_status"])),
                    "review_status": str(event["review_status"]),
                    "effective_date": event.get("effective_date"),
                    "provider": event.get("provider"),
                    "provider_security_id": event.get("provider_security_id"),
                    "identity_status": identity_status,
                    "evidence": event.get("evidence") or {},
                    "reason": str(event.get("reason") or event["event_type"]),
                }
                economic_payload = {k: v for k, v in payload.items() if k not in {"identity_status"}}
                event_id = stable_hash(economic_payload)
                economic_fp = stable_hash(economic_payload)
                conn.execute(
                    f"INSERT INTO {EVENT_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event_id,
                        CONTRACT_VERSION,
                        company_id,
                        security_id,
                        payload["provider"],
                        payload["provider_security_id"],
                        payload["predecessor_ticker"],
                        payload["successor_ticker"],
                        payload["event_type"],
                        payload["event_date"],
                        payload["comparability_status"],
                        payload["review_status"],
                        payload["effective_date"],
                        canonical_json({**payload["evidence"], "identity_status": identity_status}),
                        payload["reason"],
                        economic_fp,
                        applied_at_utc,
                        applied_at_utc,
                    ),
                )
                event_rows.append({**economic_payload, "event_id": event_id, "economic_event_fingerprint": economic_fp})
                quarters = conn.execute(
                    "SELECT quarter_id,period_end,source_availability_date FROM v4_quarter "
                    "WHERE company_id=? ORDER BY fiscal_year,CASE fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END",
                    (company_id,),
                ).fetchall()
                quarter_regime_by_id: dict[int, str] = {}
                for quarter in quarters:
                    regime, reason = _quarter_regime(
                        str(quarter["period_end"]),
                        payload["event_date"],
                        payload["comparability_status"],
                    )
                    q_payload = {
                        "quarter_id": int(quarter["quarter_id"]),
                        "event_id": event_id,
                        "company_id": company_id,
                        "period_end": str(quarter["period_end"]),
                        "source_availability_date": quarter["source_availability_date"],
                        "economic_regime": regime,
                        "regime_reason": reason,
                    }
                    fp = stable_hash(q_payload)
                    conn.execute(
                        f"INSERT INTO {QUARTER_TABLE} VALUES(?,?,?,?,?,?,?,?)",
                        (
                            q_payload["quarter_id"],
                            event_id,
                            company_id,
                            q_payload["period_end"],
                            q_payload["source_availability_date"],
                            regime,
                            reason,
                            fp,
                        ),
                    )
                    quarter_regime_by_id[int(quarter["quarter_id"])] = regime
                    quarter_rows.append({**q_payload, "regime_fingerprint": fp})
                ttms = conn.execute(
                    "SELECT ttm_id,endpoint_quarter_id,period_end,ttm_source_available_date,input_quarter_ids_json "
                    "FROM v4_ttm_values WHERE company_id=? ORDER BY endpoint_fiscal_year,CASE endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END",
                    (company_id,),
                ).fetchall()
                for ttm in ttms:
                    input_ids = [int(value) for value in json.loads(str(ttm["input_quarter_ids_json"] or "[]"))]
                    input_regimes = [quarter_regime_by_id.get(qid, "UNRESOLVED") for qid in input_ids]
                    status, reason, same_count = _ttm_regime(input_regimes, payload["comparability_status"])
                    t_payload = {
                        "ttm_id": int(ttm["ttm_id"]),
                        "event_id": event_id,
                        "company_id": company_id,
                        "endpoint_quarter_id": int(ttm["endpoint_quarter_id"]),
                        "endpoint_period_end": str(ttm["period_end"]),
                        "endpoint_available_date": ttm["ttm_source_available_date"],
                        "ttm_regime_status": status,
                        "regime_reason": reason,
                        "input_regimes": input_regimes,
                        "same_regime_observation_count": same_count,
                    }
                    fp = stable_hash(t_payload)
                    conn.execute(
                        f"INSERT INTO {TTM_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            t_payload["ttm_id"],
                            event_id,
                            company_id,
                            t_payload["endpoint_quarter_id"],
                            t_payload["endpoint_period_end"],
                            t_payload["endpoint_available_date"],
                            status,
                            reason,
                            canonical_json(input_regimes),
                            same_count,
                            fp,
                        ),
                    )
                    ttm_rows.append({**t_payload, "regime_fingerprint": fp})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "contract_version": CONTRACT_VERSION,
        "event_count": len(event_rows),
        "quarter_regime_count": len(quarter_rows),
        "ttm_regime_count": len(ttm_rows),
        "events": event_rows,
        "quarter_regime_counts": dict(sorted(Counter(row["economic_regime"] for row in quarter_rows).items())),
        "ttm_regime_counts": dict(sorted(Counter(row["ttm_regime_status"] for row in ttm_rows).items())),
        "economic_event_fingerprint": stable_hash(event_rows),
        "regime_fingerprint": stable_hash({"events": event_rows, "quarters": quarter_rows, "ttm": ttm_rows}),
    }


def contract_fingerprint(conn: sqlite3.Connection) -> str | None:
    if not has_structural_contract(conn):
        return None
    rows = [dict(row) for row in conn.execute(
        f"SELECT event_id,contract_version,company_id,security_id,predecessor_ticker,successor_ticker,"
        f"event_type,event_date,comparability_status,review_status,effective_date,economic_event_fingerprint "
        f"FROM {EVENT_TABLE} ORDER BY successor_ticker,event_id"
    )]
    regimes = [dict(row) for row in conn.execute(
        f"SELECT ttm_id,event_id,company_id,endpoint_quarter_id,ttm_regime_status,regime_reason,"
        f"input_regimes_json,same_regime_observation_count,regime_fingerprint "
        f"FROM {TTM_TABLE} ORDER BY company_id,endpoint_quarter_id,ttm_id"
    )]
    return stable_hash({"contract_version": CONTRACT_VERSION, "events": rows, "ttm_regimes": regimes})


def latest_ttm_eligibility(conn: sqlite3.Connection, *, as_of_date: str) -> tuple[dict[int, StructuralEligibility], dict[str, Any]]:
    if not has_structural_contract(conn):
        return {}, {"status": "STRUCTURAL_CONTRACT_ABSENT_LEGACY_ALLOWED", "fingerprint": None}
    rows = [dict(row) for row in conn.execute(
        f"""WITH latest AS (
                SELECT t.company_id,t.ttm_id,t.endpoint_quarter_id,t.ttm_source_available_date,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.company_id
                         ORDER BY t.endpoint_fiscal_year DESC,
                                  CASE t.endpoint_fiscal_quarter WHEN 'Q4' THEN 4 WHEN 'Q3' THEN 3 WHEN 'Q2' THEN 2 ELSE 1 END DESC,
                                  t.ttm_id DESC
                       ) rank_number
                  FROM v4_ttm_values t
                 WHERE t.ttm_source_available_date IS NULL OR t.ttm_source_available_date<=?
             )
             SELECT l.company_id,l.ttm_id,l.endpoint_quarter_id,e.event_id,e.event_type,e.event_date,
                    e.comparability_status,r.ttm_regime_status,r.regime_reason
               FROM latest l
               JOIN {EVENT_TABLE} e ON e.company_id=l.company_id
               LEFT JOIN {TTM_TABLE} r ON r.ttm_id=l.ttm_id
              WHERE l.rank_number=1
              ORDER BY l.company_id""",
        (as_of_date,),
    )]
    out: dict[int, StructuralEligibility] = {}
    counts: Counter[str] = Counter()
    for row in rows:
        status = normalize_status(str(row["comparability_status"]))
        regime = str(row["ttm_regime_status"] or "UNRESOLVED")
        eligible = True
        reason = "ELIGIBLE"
        if status in STRUCTURAL_BREAKING_STATUSES:
            if row["event_date"] is None:
                eligible, reason = False, "UNRESOLVED_EVENT_DATE"
            elif as_of_date > str(row["event_date"]) and regime != "POST_EVENT_COHERENT":
                eligible, reason = False, "CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM"
            elif regime == "STRUCTURAL_NOT_READY":
                eligible, reason = False, str(row["regime_reason"] or "STRUCTURAL_NOT_READY")
        counts[reason] += 1
        out[int(row["company_id"])] = StructuralEligibility(
            company_id=int(row["company_id"]),
            quarter_id=int(row["endpoint_quarter_id"]) if row["endpoint_quarter_id"] is not None else None,
            ttm_id=int(row["ttm_id"]) if row["ttm_id"] is not None else None,
            eligible=eligible,
            reason_code=reason,
            event_id=row["event_id"],
            event_type=row["event_type"],
            event_date=row["event_date"],
            comparability_status=status,
            ttm_regime_status=regime,
        )
    return out, {
        "status": "STRUCTURAL_CONTRACT_APPLIED",
        "as_of_date": as_of_date,
        "event_company_count": len(out),
        "eligibility_reason_counts": dict(sorted(counts.items())),
        "fingerprint": contract_fingerprint(conn),
    }


def allowed_history_quarter_ids(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    current_quarter_id: int,
) -> set[int] | None:
    if not has_structural_contract(conn):
        return None
    current = conn.execute(
        f"SELECT ttm_regime_status FROM {TTM_TABLE} WHERE company_id=? AND endpoint_quarter_id=?",
        (company_id, current_quarter_id),
    ).fetchone()
    if current is None:
        return None
    regime = str(current[0])
    if regime == "SINGLE_CONTINUOUS_REGIME":
        return None
    return {
        int(row[0])
        for row in conn.execute(
            f"SELECT endpoint_quarter_id FROM {TTM_TABLE} WHERE company_id=? AND ttm_regime_status=?",
            (company_id, regime),
        )
    }
