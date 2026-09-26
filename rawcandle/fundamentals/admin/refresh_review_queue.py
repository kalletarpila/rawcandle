from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.contracts import fingerprint, utc_now


TICKER_LOCAL_REVIEW = "TICKER_LOCAL_REVIEW"
GLOBAL_BLOCKING_REVIEW = "GLOBAL_BLOCKING_REVIEW"
OPEN_STATUSES = ("OPEN", "WAITING_PROVIDER", "RETRY_REEVALUATION")
SUPPORTED_ACTIONS = ("WAIT_FOR_PROVIDER", "RETRY_REEVALUATION")
BLOCKED_ACTIONS = ("ACCEPT_RETAINED_HISTORY", "CONFIRM_TRUE_SOURCE_REMOVAL")
REASON_EXPLANATIONS = {
    "BOUNDARY_FISCAL_WINDOW_TOO_SHORT": (
        "Provider history is shorter than the required 41-quarter boundary."
    ),
    "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW": (
        "The oldest source observation reached the expected rolling-history boundary."
    ),
    "COMPANION_DIMENSION_CONTRADICTION": (
        "ARQ and MRQ companion evidence imply conflicting source-history actions."
    ),
    "PROVIDER_ANOMALY_SUSPECTED": (
        "Complete provider response is materially shorter than the expected source window."
    ),
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS refresh_review_queue (
    ticker TEXT PRIMARY KEY,
    review_type TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    affected_source_keys_json TEXT NOT NULL,
    fiscal_identities_json TEXT NOT NULL,
    source_evidence_fingerprint TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    first_seen_run_id TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL,
    last_seen_run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    last_published_binding TEXT,
    operator_action TEXT,
    resolution_at_utc TEXT,
    resolution_evidence_json TEXT
)
"""


def queue_path_for_run_root(run_root: Path) -> Path:
    return run_root.resolve().parent / "fundamentals_refresh_review_queue.db"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(SCHEMA_SQL)
    return connection


def _read_connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    for key in (
        "reason_codes_json",
        "affected_source_keys_json",
        "fiscal_identities_json",
        "resolution_evidence_json",
    ):
        value[key.removesuffix("_json")] = json.loads(value.pop(key)) if value.get(key) else None
    return value


def _review_evidence(change: Mapping[str, Any]) -> dict[str, Any]:
    events = [dict(item) for item in change.get("source_history_events") or []]
    return {
        "ticker": str(change.get("ticker") or "").upper(),
        "review_reason": change.get("review_reason"),
        "source_completeness": change.get("source_completeness"),
        "source_history_action": change.get("source_history_action"),
        "events": events,
        "identity": change.get("identity"),
    }


def classify_review_scope(change: Mapping[str, Any]) -> dict[str, Any]:
    """Prove the narrow, single-ticker short-window shape; fail closed otherwise."""
    ticker = str(change.get("ticker") or "").upper()
    evidence = _review_evidence(change)
    events = evidence["events"]
    completeness = evidence.get("source_completeness") or {}
    identity = evidence.get("identity") or {}
    reasons = sorted({str(item.get("classification_reason") or "") for item in events})
    event_tickers = {str(item.get("ticker") or "").upper() for item in events}
    allowed_reasons = {
        "BOUNDARY_FISCAL_WINDOW_TOO_SHORT",
        "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW",
    }
    local = (
        change.get("classification") == "REVIEW_REQUIRED"
        and change.get("review_reason") == "AMBIGUOUS_SOURCE_REMOVAL"
        and identity.get("status") == "KNOWN"
        and bool(identity.get("company_id"))
        and bool(identity.get("security_id"))
        and events
        and event_tickers == {ticker}
        and set(completeness) == {"ARQ", "MRQ"}
        and all((completeness.get(dimension) or {}).get("status") == "COMPLETE" for dimension in ("ARQ", "MRQ"))
        and set(reasons).issubset(allowed_reasons)
        and "BOUNDARY_FISCAL_WINDOW_TOO_SHORT" in reasons
        and all(item.get("was_oldest_prefix") is True for item in events)
        and all(item.get("chronology_coherent") is True for item in events)
        and all(not item.get("same_fiscal_current_keys") for item in events)
        and all(not item.get("companion_dimension_conflict") for item in events)
    )
    return {
        "ticker": ticker,
        "scope": TICKER_LOCAL_REVIEW if local else GLOBAL_BLOCKING_REVIEW,
        "review_type": "PROVIDER_ANOMALY_SUSPECTED" if local else str(change.get("review_reason") or "REVIEW_REQUIRED"),
        "reason_codes": reasons or [str(change.get("review_reason") or "REVIEW_REQUIRED")],
        "affected_source_keys": [item.get("source_identity") for item in events if item.get("source_identity")],
        "fiscal_identities": [item.get("fiscal_identity") for item in events if item.get("fiscal_identity")],
        "source_evidence_fingerprint": fingerprint(evidence),
        "locality_proof": {
            "known_unique_identity": identity.get("status") == "KNOWN",
            "complete_arq_mrq": all((completeness.get(d) or {}).get("status") == "COMPLETE" for d in ("ARQ", "MRQ")),
            "single_ticker_events": event_tickers == {ticker},
            "oldest_prefix_only": bool(events) and all(item.get("was_oldest_prefix") is True for item in events),
            "no_cross_ticker_or_companion_conflict": bool(events) and all(not item.get("companion_dimension_conflict") for item in events),
        },
    }


def partition_changes(changes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    safe = [dict(item) for item in changes if item.get("classification") != "REVIEW_REQUIRED"]
    reviews = [dict(item) for item in changes if item.get("classification") == "REVIEW_REQUIRED"]
    scoped = [(item, classify_review_scope(item)) for item in reviews]
    held = [scope | {"change": item} for item, scope in scoped if scope["scope"] == TICKER_LOCAL_REVIEW]
    global_items = [scope | {"change": item} for item, scope in scoped if scope["scope"] == GLOBAL_BLOCKING_REVIEW]
    binding = {
        "safe_tickers": sorted(str(item.get("ticker")) for item in safe),
        "held": [{key: item[key] for key in ("ticker", "scope", "review_type", "source_evidence_fingerprint")} for item in held],
        "global": [{key: item[key] for key in ("ticker", "scope", "review_type", "source_evidence_fingerprint")} for item in global_items],
    }
    return {
        "safe_changes": safe,
        "held": held,
        "global_blockers": global_items,
        "binding": binding,
        "partition_fingerprint": fingerprint(binding),
    }


def partition_artifact_fingerprint(value: Mapping[str, Any]) -> str:
    binding = {
        "safe_tickers": sorted(str(ticker) for ticker in value.get("safe_tickers") or []),
        "held": [
            {key: item.get(key) for key in ("ticker", "scope", "review_type", "source_evidence_fingerprint")}
            for item in value.get("held") or []
        ],
        "global": [
            {key: item.get(key) for key in ("ticker", "scope", "review_type", "source_evidence_fingerprint")}
            for item in value.get("global_blockers") or []
        ],
    }
    return fingerprint(binding)


def review_reason_explanation(code: str) -> str:
    return REASON_EXPLANATIONS.get(code, code)


def present_review_item(item: Mapping[str, Any]) -> dict[str, Any]:
    reason_codes = [str(value) for value in item.get("reason_codes") or []]
    source_keys = list(item.get("affected_source_keys") or [])
    fiscal_identities = list(item.get("fiscal_identities") or [])
    explanations = [review_reason_explanation(code) for code in reason_codes]
    review_type = str(item.get("review_type") or "TICKER_LOCAL_REVIEW")
    if review_type in REASON_EXPLANATIONS:
        explanations.insert(0, REASON_EXPLANATIONS[review_type])
    explanations = list(dict.fromkeys(explanations))
    count_text = (
        f"{len(source_keys)} affected source observation"
        f"{'s' if len(source_keys) != 1 else ''}."
        if source_keys else ""
    )
    summary = " ".join(value for value in (count_text, *explanations) if value)
    status = str(item.get("status") or "UNKNOWN")
    return {
        **dict(item),
        "review_scope": TICKER_LOCAL_REVIEW,
        "classification": review_type,
        "reason_explanations": explanations,
        "human_summary": summary or "No additional explanation is available.",
        "affected_source_count": len(source_keys),
        "affected_fiscal_identity_count": len(fiscal_identities),
        "evidence_reference": str(item.get("source_evidence_fingerprint") or "")[:12],
        "reevaluation_pending": status == "RETRY_REEVALUATION",
        "currently_held": status in OPEN_STATUSES,
    }


@dataclass(frozen=True)
class RefreshReviewQueue:
    path: Path

    def pending_tickers(self) -> list[str]:
        if not self.path.exists():
            return []
        with _read_connect(self.path) as connection:
            rows = connection.execute(
                "SELECT ticker FROM refresh_review_queue WHERE status IN (?,?,?) ORDER BY ticker",
                OPEN_STATUSES,
            ).fetchall()
        return [str(row[0]) for row in rows]

    def upsert_local(self, item: Mapping[str, Any], *, run_id: str, published_binding: str | None) -> dict[str, Any]:
        now = utc_now()
        ticker = str(item["ticker"])
        with _connect(self.path) as connection:
            prior = connection.execute("SELECT * FROM refresh_review_queue WHERE ticker=?", (ticker,)).fetchone()
            status = str(prior["status"]) if prior and prior["status"] in {"OPEN", "WAITING_PROVIDER"} else "OPEN"
            first_seen_at = str(prior["first_seen_at_utc"]) if prior else now
            first_seen_run = str(prior["first_seen_run_id"]) if prior else run_id
            connection.execute(
                "INSERT OR REPLACE INTO refresh_review_queue VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ticker, item["review_type"], _json(item["reason_codes"]),
                    _json(item["affected_source_keys"]), _json(item["fiscal_identities"]),
                    item["source_evidence_fingerprint"], first_seen_at, first_seen_run,
                    now, run_id, status, published_binding,
                    prior["operator_action"] if prior else None,
                    prior["resolution_at_utc"] if prior else None,
                    prior["resolution_evidence_json"] if prior else None,
                ),
            )
            connection.commit()
        return self.get(ticker) or {}

    def resolve_absent(self, evaluated_tickers: Sequence[str], held_tickers: Sequence[str], *, run_id: str) -> None:
        resolved = sorted(set(evaluated_tickers) - set(held_tickers))
        if not resolved or not self.path.exists():
            return
        now = utc_now()
        with _connect(self.path) as connection:
            for ticker in resolved:
                connection.execute(
                    "UPDATE refresh_review_queue SET status='RESOLVED',resolution_at_utc=?,resolution_evidence_json=?,last_seen_run_id=?,last_seen_at_utc=? "
                    "WHERE ticker=? AND status IN (?,?,?)",
                    (now, _json({"reason": "REEVALUATED_WITHOUT_LOCAL_REVIEW", "run_id": run_id}), run_id, now, ticker, *OPEN_STATUSES),
                )
            connection.commit()

    def apply_action(self, ticker: str, action: str, *, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        normalized = action.strip().upper()
        if normalized in BLOCKED_ACTIONS:
            raise ValueError(f"REFRESH_REVIEW_ACTION_NOT_IMPLEMENTED:{normalized}")
        if normalized not in SUPPORTED_ACTIONS:
            raise ValueError(f"REFRESH_REVIEW_ACTION_INVALID:{normalized}")
        status = "WAITING_PROVIDER" if normalized == "WAIT_FOR_PROVIDER" else "RETRY_REEVALUATION"
        with _connect(self.path) as connection:
            changed = connection.execute(
                "UPDATE refresh_review_queue SET status=?,operator_action=?,resolution_at_utc=NULL,resolution_evidence_json=? WHERE ticker=? AND status!='RESOLVED'",
                (status, normalized, _json(dict(evidence or {})), ticker.upper()),
            ).rowcount
            connection.commit()
        if changed != 1:
            raise ValueError("REFRESH_REVIEW_ITEM_NOT_OPEN")
        return self.get(ticker.upper()) or {}

    def get(self, ticker: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        with _read_connect(self.path) as connection:
            row = connection.execute("SELECT * FROM refresh_review_queue WHERE ticker=?", (ticker.upper(),)).fetchone()
        if row is None:
            return None
        return _decode_row(row)

    def list_items(self, *, include_resolved: bool = False) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        query = "SELECT * FROM refresh_review_queue"
        parameters: tuple[Any, ...] = ()
        if not include_resolved:
            query += " WHERE status IN (?,?,?)"
            parameters = OPEN_STATUSES
        query += " ORDER BY ticker"
        with _read_connect(self.path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_decode_row(row) for row in rows]
