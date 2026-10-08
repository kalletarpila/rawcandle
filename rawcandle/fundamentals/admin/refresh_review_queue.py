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
ACCEPT_RETAINED_HISTORY = "ACCEPT_RETAINED_HISTORY"
RETAINED_HISTORY_APPROVAL_VERSION = "REFRESH_RETAINED_HISTORY_APPROVAL_V1"
ACCEPT_FISCAL_IDENTITY_REVISION = "ACCEPT_FISCAL_IDENTITY_REVISION"
FISCAL_REVISION_APPROVAL_VERSION = "REFRESH_FISCAL_REVISION_APPROVAL_V1"
FISCAL_IDENTITY_REVISION = "FISCAL_IDENTITY_REVISION"
REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION = "REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION"
CONFIRM_TRUE_SOURCE_REMOVAL = "CONFIRM_TRUE_SOURCE_REMOVAL"
TRUE_REMOVAL_APPROVAL_VERSION = "REFRESH_TRUE_SOURCE_REMOVAL_APPROVAL_V1"
TRUE_SOURCE_REMOVAL = "TRUE_SOURCE_REMOVAL"
SUPPORTED_ACTIONS = (
    "WAIT_FOR_PROVIDER", "RETRY_REEVALUATION", ACCEPT_RETAINED_HISTORY,
    ACCEPT_FISCAL_IDENTITY_REVISION, CONFIRM_TRUE_SOURCE_REMOVAL,
)
BLOCKED_ACTIONS: tuple[str, ...] = ()
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
    REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION: (
        "Provider fiscal identity changed on an existing source observation and requires operator review."
    ),
    TRUE_SOURCE_REMOVAL: (
        "Complete provider history proves that exact published source observations are no longer returned."
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
    resolution_evidence_json TEXT,
    queue_item_id TEXT,
    review_context_json TEXT
);
CREATE TABLE IF NOT EXISTS refresh_review_queue_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    run_id TEXT,
    evidence_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_review_queue_audit_ticker
ON refresh_review_queue_audit(ticker, audit_id)
"""


def queue_path_for_run_root(run_root: Path) -> Path:
    return run_root.resolve().parent / "fundamentals_refresh_review_queue.db"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(SCHEMA_SQL)
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(refresh_review_queue)").fetchall()
    }
    if "queue_item_id" not in columns:
        connection.execute("ALTER TABLE refresh_review_queue ADD COLUMN queue_item_id TEXT")
    if "review_context_json" not in columns:
        connection.execute("ALTER TABLE refresh_review_queue ADD COLUMN review_context_json TEXT")
    return connection


def _read_connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _queue_evidence_binding(item: Mapping[str, Any]) -> dict[str, Any]:
    context = dict(item.get("review_context") or {})
    return {
        "ticker": str(item.get("ticker") or "").upper(),
        "queue_item_id": item.get("queue_item_id"),
        "review_type": item.get("review_type"),
        "reason_codes": sorted(str(value) for value in item.get("reason_codes") or []),
        "affected_source_keys": _ordered_evidence(item.get("affected_source_keys") or []),
        "fiscal_identities": _ordered_evidence(item.get("fiscal_identities") or []),
        "source_evidence_fingerprint": item.get("source_evidence_fingerprint"),
        "published_binding": item.get("last_published_binding"),
        "identity_binding": dict(context.get("identity_binding") or {}),
        "locality_proof": dict(context.get("locality_proof") or {}),
    }


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    for key in (
        "reason_codes_json",
        "affected_source_keys_json",
        "fiscal_identities_json",
        "resolution_evidence_json",
        "review_context_json",
    ):
        value[key.removesuffix("_json")] = json.loads(value.pop(key)) if value.get(key) else None
    context = value.get("review_context") or {}
    expected = context.get("queue_evidence_fingerprint")
    if expected and expected != fingerprint(_queue_evidence_binding(value)):
        raise ValueError("REFRESH_REVIEW_QUEUE_EVIDENCE_TAMPERED")
    return value


def _ordered_evidence(values: Sequence[Any]) -> list[Any]:
    return sorted((dict(value) if isinstance(value, Mapping) else value for value in values), key=_json)


def _identity_binding(identity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": identity.get("status"),
        "ticker": str(identity.get("ticker") or "").upper(),
        "company_id": identity.get("company_id"),
        "security_id": identity.get("security_id"),
        "company_key": identity.get("company_key"),
        "current_ticker": identity.get("current_ticker"),
        "provider_security_id": identity.get("provider_security_id"),
        "provider_ticker": identity.get("provider_ticker"),
    }


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


def _valid_fiscal_identity(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("fiscal_year"), int)
        and value.get("fiscal_quarter") in {"Q1", "Q2", "Q3", "Q4"}
    )


def _fiscal_event_evidence(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": event.get("ticker"),
        "dimension": event.get("dimension"),
        "source_identity": event.get("source_identity"),
        "old_source_identity": event.get("old_source_identity"),
        "current_source_identity": event.get("current_source_identity"),
        "old_fiscal_identity": event.get("old_fiscal_identity"),
        "current_fiscal_identity": event.get("current_fiscal_identity"),
        "old_source_fingerprint": event.get("old_source_fingerprint"),
        "current_source_fingerprint": event.get("current_source_fingerprint"),
        "financial_payload_changed": event.get("financial_payload_changed"),
        "arq_companion_identity_proof": event.get("arq_companion_identity_proof"),
    }


def _arq_companion_agrees(event: Mapping[str, Any], ticker: str) -> bool:
    proof = event.get("arq_companion_identity_proof")
    source_identity = event.get("source_identity")
    proposed = event.get("current_fiscal_identity")
    if not isinstance(proof, Mapping) or not isinstance(source_identity, Mapping):
        return False
    reportperiod = source_identity.get("reportperiod")
    published_keys = proof.get("published_source_keys")
    source_keys = proof.get("source_source_keys")
    published_fingerprints = proof.get("published_source_fingerprints")
    source_fingerprints = proof.get("source_source_fingerprints")
    expected_identities = [proposed]
    return (
        proof.get("status") == "AGREES"
        and proof.get("dimension") == "ARQ"
        and proof.get("reportperiod") == reportperiod
        and proof.get("proposed_mrq_fiscal_identity") == proposed
        and proof.get("published_fiscal_identities") == expected_identities
        and proof.get("source_fiscal_identities") == expected_identities
        and isinstance(published_keys, list) and bool(published_keys)
        and isinstance(source_keys, list) and bool(source_keys)
        and all(
            isinstance(key, Mapping)
            and str(key.get("ticker") or "").upper() == ticker
            and key.get("dimension") == "ARQ"
            and key.get("reportperiod") == reportperiod
            for key in [*published_keys, *source_keys]
        )
        and isinstance(published_fingerprints, list)
        and len(published_fingerprints) == len(published_keys)
        and all(isinstance(value, str) and bool(value) for value in published_fingerprints)
        and isinstance(source_fingerprints, list)
        and len(source_fingerprints) == len(source_keys)
        and all(isinstance(value, str) and bool(value) for value in source_fingerprints)
    )


def classify_review_scope(change: Mapping[str, Any]) -> dict[str, Any]:
    """Prove supported ticker-local review shapes; fail closed otherwise."""
    ticker = str(change.get("ticker") or "").upper()
    evidence = _review_evidence(change)
    events = evidence["events"]
    completeness = evidence.get("source_completeness") or {}
    identity = evidence.get("identity") or {}
    reasons = sorted({str(item.get("classification_reason")) for item in events if item.get("classification_reason")})
    event_tickers = {str(item.get("ticker") or "").upper() for item in events}
    allowed_reasons = {
        "BOUNDARY_FISCAL_WINDOW_TOO_SHORT",
        "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW",
    }
    complete_arq_mrq = (
        set(completeness) == {"ARQ", "MRQ"}
        and all((completeness.get(dimension) or {}).get("status") == "COMPLETE" for dimension in ("ARQ", "MRQ"))
    )
    source_window_local = (
        change.get("classification") == "REVIEW_REQUIRED"
        and change.get("review_reason") == "AMBIGUOUS_SOURCE_REMOVAL"
        and identity.get("status") == "KNOWN"
        and bool(identity.get("company_id"))
        and bool(identity.get("security_id"))
        and events
        and event_tickers == {ticker}
        and complete_arq_mrq
        and set(reasons).issubset(allowed_reasons)
        and "BOUNDARY_FISCAL_WINDOW_TOO_SHORT" in reasons
        and all(item.get("was_oldest_prefix") is True for item in events)
        and all(item.get("chronology_coherent") is True for item in events)
        and all(not item.get("same_fiscal_current_keys") for item in events)
        and all(not item.get("companion_dimension_conflict") for item in events)
    )
    fiscal_events = [item for item in events if item.get("event") == FISCAL_IDENTITY_REVISION]
    fiscal_identity_binding = (
        identity.get("status") == "KNOWN"
        and str(identity.get("ticker") or "").upper() == ticker
        and bool(identity.get("company_id"))
        and bool(identity.get("security_id"))
        and bool(identity.get("company_key"))
        and bool(identity.get("current_ticker"))
        and bool(identity.get("provider_security_id"))
        and bool(identity.get("provider_ticker"))
    )
    fiscal_event_evidence_complete = bool(fiscal_events) and all(
        item.get("dimension") == "MRQ"
        and item.get("review_status") == REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION
        and item.get("stable_source_key") is True
        and item.get("source_identity") == item.get("old_source_identity")
        and item.get("source_identity") == item.get("current_source_identity")
        and isinstance(item.get("source_identity"), Mapping)
        and str(item["source_identity"].get("ticker") or "").upper() == ticker
        and item["source_identity"].get("dimension") == "MRQ"
        and bool(item["source_identity"].get("date"))
        and bool(item["source_identity"].get("reportperiod"))
        and _valid_fiscal_identity(item.get("old_fiscal_identity"))
        and _valid_fiscal_identity(item.get("current_fiscal_identity"))
        and item.get("old_fiscal_identity") != item.get("current_fiscal_identity")
        and bool(item.get("old_source_fingerprint"))
        and bool(item.get("current_source_fingerprint"))
        and _arq_companion_agrees(item, ticker)
        for item in fiscal_events
    )
    fiscal_revision_local = (
        change.get("classification") == "REVIEW_REQUIRED"
        and change.get("review_reason") == REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION
        and fiscal_identity_binding
        and complete_arq_mrq
        and len(fiscal_events) == len(events)
        and event_tickers == {ticker}
        and fiscal_event_evidence_complete
    )
    true_removal_events = [
        item for item in events if item.get("event") == TRUE_SOURCE_REMOVAL
    ]
    true_removal_reasons = {
        "INTERIOR_SOURCE_KEY_REMOVAL", "SAME_FISCAL_SOURCE_KEY_REPLACEMENT",
    }
    true_removal_local = (
        change.get("classification") == "REVIEW_REQUIRED"
        and change.get("review_reason") == TRUE_SOURCE_REMOVAL
        and fiscal_identity_binding
        and complete_arq_mrq
        and bool(true_removal_events)
        and event_tickers == {ticker}
        and all(
            item.get("classification_reason") in true_removal_reasons
            and isinstance(item.get("source_identity"), Mapping)
            and _valid_fiscal_identity(item.get("fiscal_identity"))
            and (item.get("provider_absence_proof") or {}).get(
                "absent_from_complete_source"
            ) is True
            and (item.get("provider_absence_proof") or {}).get(
                "source_response_status"
            ) == "COMPLETE"
            and bool((item.get("provider_absence_proof") or {}).get(
                "complete_source_raw_fingerprint"
            ))
            and bool((item.get("provider_absence_proof") or {}).get(
                "complete_source_effective_fingerprint"
            ))
            for item in true_removal_events
        )
        and all(
            item.get("event") in {TRUE_SOURCE_REMOVAL, "AGED_OUT_OF_SOURCE_WINDOW"}
            for item in events
        )
        and not any(item.get("companion_dimension_conflict") for item in events)
    )
    local = source_window_local or fiscal_revision_local or true_removal_local
    affected_source_keys = [
        item.get("source_identity") for item in events if item.get("source_identity")
    ]
    fiscal_identities = (
        [_fiscal_event_evidence(item) for item in fiscal_events]
        if fiscal_events
        else [
            item.get("fiscal_identity") for item in (
                true_removal_events if true_removal_events else events
            ) if item.get("fiscal_identity")
        ]
    )
    affected_source_keys = (
        [item.get("source_identity") for item in true_removal_events]
        if true_removal_events else affected_source_keys
    )
    return {
        "ticker": ticker,
        "scope": TICKER_LOCAL_REVIEW if local else GLOBAL_BLOCKING_REVIEW,
        "review_type": (
            "PROVIDER_ANOMALY_SUSPECTED"
            if source_window_local
            else str(change.get("review_reason") or "REVIEW_REQUIRED")
        ),
        "reason_codes": reasons or [str(change.get("review_reason") or "REVIEW_REQUIRED")],
        "affected_source_keys": affected_source_keys,
        "fiscal_identities": fiscal_identities,
        "source_evidence_fingerprint": fingerprint(evidence),
        "identity_binding": _identity_binding(identity),
        "locality_proof": {
            "known_unique_identity": identity.get("status") == "KNOWN",
            "complete_arq_mrq": complete_arq_mrq,
            "single_ticker_events": event_tickers == {ticker},
            "proven_local_shape": (
                "MRQ_FISCAL_REVISION_WITH_ARQ_COMPANION"
                if fiscal_revision_local else "OLDEST_PREFIX_SOURCE_WINDOW"
                if source_window_local else "PROVEN_TRUE_SOURCE_REMOVAL"
                if true_removal_local else None
            ),
            "fiscal_identity_binding_complete": fiscal_identity_binding,
            "mrq_fiscal_revisions_only": bool(fiscal_events) and len(fiscal_events) == len(events)
            and all(item.get("dimension") == "MRQ" for item in fiscal_events),
            "stable_fiscal_source_keys": bool(fiscal_events)
            and all(item.get("stable_source_key") is True for item in fiscal_events),
            "arq_companion_identities_agree": bool(fiscal_events)
            and all(_arq_companion_agrees(item, ticker) for item in fiscal_events),
            "oldest_prefix_only": bool(events) and all(item.get("was_oldest_prefix") is True for item in events),
            "no_cross_ticker_or_companion_conflict": bool(events) and all(not item.get("companion_dimension_conflict") for item in events),
            "no_same_fiscal_replacement_conflict": bool(events) and all(not item.get("same_fiscal_current_keys") for item in events),
            "short_window_is_ticker_local": bool(events) and all(
                item.get("classification_reason") in allowed_reasons for item in events
            ),
            "true_removal_only": bool(true_removal_events)
            and len(true_removal_events) == sum(
                item.get("event") == TRUE_SOURCE_REMOVAL for item in events
            ),
            "provider_absence_proven": bool(true_removal_events) and all(
                (item.get("provider_absence_proof") or {}).get(
                    "absent_from_complete_source"
                ) is True
                and (item.get("provider_absence_proof") or {}).get(
                    "source_response_status"
                ) == "COMPLETE"
                for item in true_removal_events
            ),
            "provider_absence_evidence": [
                {
                    "source_identity": dict(item.get("source_identity") or {}),
                    "fiscal_identity": dict(item.get("fiscal_identity") or {}),
                    "classification_reason": item.get("classification_reason"),
                    "provider_absence_proof": dict(
                        item.get("provider_absence_proof") or {}
                    ),
                }
                for item in true_removal_events
            ],
            "affected_observation_count": len(affected_source_keys),
            "affected_arq_count": sum(
                str(item.get("dimension")) == "ARQ" for item in events
            ),
            "affected_mrq_count": sum(
                str(item.get("dimension")) == "MRQ" for item in events
            ),
        },
    }


def _review_context(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scope": item.get("scope"),
        "review_type": item.get("review_type"),
        "reason_codes": sorted(str(value) for value in item.get("reason_codes") or []),
        "identity_binding": dict(item.get("identity_binding") or {}),
        "locality_proof": dict(item.get("locality_proof") or {}),
    }


def _review_context_with_integrity(
    item: Mapping[str, Any], *, queue_item_id: str, published_binding: str | None,
) -> dict[str, Any]:
    context = _review_context(item)
    context["queue_evidence_fingerprint"] = fingerprint(_queue_evidence_binding({
        "ticker": item.get("ticker"),
        "queue_item_id": queue_item_id,
        "review_type": item.get("review_type"),
        "reason_codes": item.get("reason_codes"),
        "affected_source_keys": item.get("affected_source_keys"),
        "fiscal_identities": item.get("fiscal_identities"),
        "source_evidence_fingerprint": item.get("source_evidence_fingerprint"),
        "last_published_binding": published_binding,
        "review_context": context,
    }))
    return context


def _approval_binding(item: Mapping[str, Any]) -> dict[str, Any]:
    context = dict(item.get("review_context") or {})
    return {
        "ticker": str(item.get("ticker") or "").upper(),
        "queue_item_id": item.get("queue_item_id"),
        "source_evidence_fingerprint": item.get("source_evidence_fingerprint"),
        "affected_source_keys": _ordered_evidence(item.get("affected_source_keys") or []),
        "fiscal_identities": _ordered_evidence(item.get("fiscal_identities") or []),
        "published_binding": item.get("last_published_binding"),
        "queue_evidence_fingerprint": context.get("queue_evidence_fingerprint"),
        "review_scope": context.get("scope"),
        "review_type": context.get("review_type") or item.get("review_type"),
        "reason_codes": sorted(
            str(value)
            for value in (context.get("reason_codes") or item.get("reason_codes") or [])
        ),
        "identity_binding": dict(context.get("identity_binding") or {}),
        "locality_proof": dict(context.get("locality_proof") or {}),
    }


def retained_history_approval_eligibility(
    item: Mapping[str, Any], *, publication_blocked: bool = False,
) -> dict[str, Any]:
    context = dict(item.get("review_context") or {})
    locality = dict(context.get("locality_proof") or {})
    identity = dict(context.get("identity_binding") or {})
    reasons = set(context.get("reason_codes") or item.get("reason_codes") or [])
    checks = (
        (not publication_blocked, "Publication or recovery safety blocks review actions."),
        (str(item.get("status")) in OPEN_STATUSES, "Review item is not unresolved."),
        (context.get("scope") == TICKER_LOCAL_REVIEW, "Review scope is not ticker-local."),
        (identity.get("status") == "KNOWN", "Ticker identity is not uniquely known."),
        (bool(identity.get("company_id")) and bool(identity.get("security_id")), "Stable company/security identity is missing."),
        (bool(item.get("queue_item_id")), "Durable queue item identity is missing."),
        (bool(item.get("affected_source_keys")), "Affected source keys are missing."),
        (bool(item.get("fiscal_identities")), "Affected fiscal identities are missing."),
        (bool(item.get("source_evidence_fingerprint")), "Evidence fingerprint is missing."),
        (bool(item.get("last_published_binding")), "Published-state binding is missing."),
        (
            reasons.issubset({
                "BOUNDARY_FISCAL_WINDOW_TOO_SHORT",
                "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW",
            })
            and "BOUNDARY_FISCAL_WINDOW_TOO_SHORT" in reasons,
            "Review reasons are not retained-history compatible.",
        ),
        (locality.get("complete_arq_mrq") is True, "Complete ARQ/MRQ evidence is missing."),
        (locality.get("single_ticker_events") is True, "Evidence is not limited to one ticker."),
        (locality.get("oldest_prefix_only") is True, "Missing observations are not a clean oldest prefix."),
        (
            locality.get("no_cross_ticker_or_companion_conflict") is True,
            "Companion or cross-ticker evidence is conflicting.",
        ),
        (
            locality.get("no_same_fiscal_replacement_conflict") is True,
            "Same-fiscal replacement evidence is conflicting.",
        ),
        (
            locality.get("short_window_is_ticker_local") is True,
            "Short-window evidence is not proven ticker-local.",
        ),
    )
    for passed, reason in checks:
        if not passed:
            return {"eligible": False, "reason": reason}
    return {
        "eligible": True,
        "reason": "Exact ticker-local retained-history evidence is eligible.",
        "affected_source_count": len(item.get("affected_source_keys") or []),
    }


def match_retained_history_approval(
    queue_item: Mapping[str, Any] | None,
    current_scope: Mapping[str, Any],
    *,
    published_binding: str | None,
) -> dict[str, Any]:
    if not queue_item or queue_item.get("operator_action") != ACCEPT_RETAINED_HISTORY:
        return {"applied": False, "reason": "NO_ACTIVE_RETAINED_HISTORY_APPROVAL"}
    if queue_item.get("status") != "RETRY_REEVALUATION":
        return {"applied": False, "reason": "APPROVAL_NOT_PENDING_REEVALUATION"}
    approval = queue_item.get("resolution_evidence") or {}
    if (
        approval.get("resolution_action") != ACCEPT_RETAINED_HISTORY
        or approval.get("resolution_contract_version")
        != RETAINED_HISTORY_APPROVAL_VERSION
    ):
        return {"applied": False, "reason": "APPROVAL_EVIDENCE_MISSING"}
    approved_binding = approval.get("binding")
    if (
        not isinstance(approved_binding, Mapping)
        or approval.get("approval_evidence_fingerprint")
        != fingerprint(approved_binding)
    ):
        return {"applied": False, "reason": "APPROVAL_FINGERPRINT_INVALID"}
    current_item = {
        **dict(queue_item),
        "source_evidence_fingerprint": current_scope.get("source_evidence_fingerprint"),
        "affected_source_keys": current_scope.get("affected_source_keys"),
        "fiscal_identities": current_scope.get("fiscal_identities"),
        "last_published_binding": published_binding,
        "review_context": _review_context_with_integrity(
            current_scope,
            queue_item_id=str(queue_item.get("queue_item_id") or ""),
            published_binding=published_binding,
        ),
    }
    current_binding = _approval_binding(current_item)
    if dict(approved_binding) != current_binding:
        return {
            "applied": False,
            "reason": "RETAINED_HISTORY_APPROVAL_EVIDENCE_DRIFT",
            "current_binding_fingerprint": fingerprint(current_binding),
        }
    return {
        "applied": True,
        "reason": "EXACT_RETAINED_HISTORY_APPROVAL_MATCH",
        "approval_evidence_fingerprint": approval.get("approval_evidence_fingerprint"),
        "approved_binding": dict(approved_binding),
        "approved_source_keys": current_binding["affected_source_keys"],
        "approved_fiscal_identities": current_binding["fiscal_identities"],
        "operator_reviewed": True,
        "resolution_contract_version": RETAINED_HISTORY_APPROVAL_VERSION,
    }


def fiscal_revision_approval_eligibility(
    item: Mapping[str, Any], *, publication_blocked: bool = False,
) -> dict[str, Any]:
    context = dict(item.get("review_context") or {})
    locality = dict(context.get("locality_proof") or {})
    identity = dict(context.get("identity_binding") or {})
    events = list(item.get("fiscal_identities") or [])
    affected = _ordered_evidence(item.get("affected_source_keys") or [])
    expected_queue_fingerprint = context.get("queue_evidence_fingerprint")
    required_identity = (
        "company_id", "security_id", "company_key", "current_ticker",
        "provider_security_id", "provider_ticker",
    )
    event_evidence_complete = bool(events) and all(
        isinstance(event, Mapping)
        and event.get("dimension") == "MRQ"
        and event.get("source_identity") == event.get("old_source_identity")
        and event.get("source_identity") == event.get("current_source_identity")
        and _valid_fiscal_identity(event.get("old_fiscal_identity"))
        and _valid_fiscal_identity(event.get("current_fiscal_identity"))
        and event.get("old_fiscal_identity") != event.get("current_fiscal_identity")
        and bool(event.get("old_source_fingerprint"))
        and bool(event.get("current_source_fingerprint"))
        and isinstance(event.get("financial_payload_changed"), bool)
        and _arq_companion_agrees(event, str(item.get("ticker") or "").upper())
        for event in events
    )
    event_keys = _ordered_evidence(
        event.get("source_identity") for event in events if isinstance(event, Mapping)
    )
    checks = (
        (not publication_blocked, "Publication or recovery safety blocks review actions."),
        (str(item.get("status")) in OPEN_STATUSES, "Review item is not unresolved."),
        (item.get("review_type") == REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION, "Review item is not a fiscal-identity revision."),
        (context.get("scope") == TICKER_LOCAL_REVIEW, "Review scope is not ticker-local."),
        (context.get("review_type") == REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION, "Review context is not a fiscal-identity revision."),
        (locality.get("proven_local_shape") == "MRQ_FISCAL_REVISION_WITH_ARQ_COMPANION", "Fiscal locality shape is not proven."),
        (locality.get("fiscal_identity_binding_complete") is True, "Fiscal identity binding is incomplete."),
        (locality.get("mrq_fiscal_revisions_only") is True, "Evidence is not limited to MRQ fiscal revisions."),
        (locality.get("stable_fiscal_source_keys") is True, "Fiscal source keys are not stable."),
        (locality.get("arq_companion_identities_agree") is True, "ARQ companion identity does not agree."),
        (identity.get("status") == "KNOWN" and all(identity.get(key) for key in required_identity), "Stable provider/company/security identity is incomplete."),
        (bool(item.get("queue_item_id")), "Durable queue item identity is missing."),
        (bool(affected), "Affected source keys are missing."),
        (event_evidence_complete, "Fiscal revision evidence is incomplete."),
        (affected == event_keys and len(affected) == len(events), "Affected source keys do not exactly match fiscal events."),
        (bool(item.get("source_evidence_fingerprint")), "Evidence fingerprint is missing."),
        (bool(item.get("last_published_binding")), "Published-state binding is missing."),
        (bool(expected_queue_fingerprint), "Queue evidence fingerprint is missing."),
        (expected_queue_fingerprint == fingerprint(_queue_evidence_binding(item)), "Queue evidence fingerprint is invalid."),
    )
    for passed, reason in checks:
        if not passed:
            return {"eligible": False, "reason": reason}
    return {
        "eligible": True,
        "reason": "Exact ticker-local fiscal-revision evidence is eligible.",
        "event_count": len(events),
    }


def match_fiscal_revision_approval(
    queue_item: Mapping[str, Any] | None,
    current_scope: Mapping[str, Any],
    *,
    published_binding: str | None,
) -> dict[str, Any]:
    if not queue_item or queue_item.get("operator_action") != ACCEPT_FISCAL_IDENTITY_REVISION:
        return {"applied": False, "reason": "NO_ACTIVE_FISCAL_REVISION_APPROVAL"}
    if queue_item.get("status") != "RETRY_REEVALUATION":
        return {"applied": False, "reason": "APPROVAL_NOT_PENDING_REEVALUATION"}
    approval = queue_item.get("resolution_evidence") or {}
    if (
        approval.get("resolution_action") != ACCEPT_FISCAL_IDENTITY_REVISION
        or approval.get("resolution_contract_version") != FISCAL_REVISION_APPROVAL_VERSION
    ):
        return {"applied": False, "reason": "APPROVAL_EVIDENCE_MISSING"}
    approved_binding = approval.get("binding")
    if not isinstance(approved_binding, Mapping) or approval.get("approval_evidence_fingerprint") != fingerprint(approved_binding):
        return {"applied": False, "reason": "APPROVAL_FINGERPRINT_INVALID"}
    current_item = {
        **dict(queue_item),
        "source_evidence_fingerprint": current_scope.get("source_evidence_fingerprint"),
        "affected_source_keys": current_scope.get("affected_source_keys"),
        "fiscal_identities": current_scope.get("fiscal_identities"),
        "last_published_binding": published_binding,
        "review_context": _review_context_with_integrity(
            current_scope,
            queue_item_id=str(queue_item.get("queue_item_id") or ""),
            published_binding=published_binding,
        ),
    }
    current_binding = _approval_binding(current_item)
    if dict(approved_binding) != current_binding:
        return {
            "applied": False,
            "reason": "FISCAL_REVISION_APPROVAL_EVIDENCE_DRIFT",
            "current_binding_fingerprint": fingerprint(current_binding),
        }
    return {
        "applied": True,
        "reason": "EXACT_FISCAL_REVISION_APPROVAL_MATCH",
        "approval_evidence_fingerprint": approval.get("approval_evidence_fingerprint"),
        "approved_binding": dict(approved_binding),
        "approved_source_keys": current_binding["affected_source_keys"],
        "approved_fiscal_identities": current_binding["fiscal_identities"],
        "operator_reviewed": True,
        "resolution_contract_version": FISCAL_REVISION_APPROVAL_VERSION,
    }


def true_removal_approval_eligibility(
    item: Mapping[str, Any], *, publication_blocked: bool = False,
) -> dict[str, Any]:
    context = dict(item.get("review_context") or {})
    locality = dict(context.get("locality_proof") or {})
    identity = dict(context.get("identity_binding") or {})
    reasons = set(context.get("reason_codes") or item.get("reason_codes") or [])
    required_identity = (
        "company_id", "security_id", "company_key", "current_ticker",
        "provider_security_id", "provider_ticker",
    )
    allowed_reasons = {
        "INTERIOR_SOURCE_KEY_REMOVAL",
        "SAME_FISCAL_SOURCE_KEY_REPLACEMENT",
        "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW",
    }
    checks = (
        (not publication_blocked, "Publication or recovery safety blocks review actions."),
        (str(item.get("status")) in OPEN_STATUSES, "Review item is not unresolved."),
        (item.get("review_type") == TRUE_SOURCE_REMOVAL, "Review item is not a true source removal."),
        (context.get("scope") == TICKER_LOCAL_REVIEW, "Review scope is not ticker-local."),
        (context.get("review_type") == TRUE_SOURCE_REMOVAL, "Review context is not a true source removal."),
        (locality.get("proven_local_shape") == "PROVEN_TRUE_SOURCE_REMOVAL", "True-removal locality is not proven."),
        (locality.get("complete_arq_mrq") is True, "Complete ARQ/MRQ evidence is missing."),
        (locality.get("single_ticker_events") is True, "Evidence is not limited to one ticker."),
        (locality.get("provider_absence_proven") is True, "Complete provider absence is not proven."),
        (locality.get("no_cross_ticker_or_companion_conflict") is True, "Companion or cross-ticker evidence is conflicting."),
        (identity.get("status") == "KNOWN" and all(identity.get(key) for key in required_identity), "Stable provider/company/security identity is incomplete."),
        (bool(item.get("queue_item_id")), "Durable queue item identity is missing."),
        (bool(item.get("affected_source_keys")), "Exact removed source keys are missing."),
        (bool(item.get("fiscal_identities")), "Affected fiscal identities are missing."),
        (reasons.issubset(allowed_reasons) and bool(reasons & {"INTERIOR_SOURCE_KEY_REMOVAL", "SAME_FISCAL_SOURCE_KEY_REPLACEMENT"}), "Review reasons are not true-removal compatible."),
        (bool(item.get("source_evidence_fingerprint")), "Evidence fingerprint is missing."),
        (bool(item.get("last_published_binding")), "Published-state binding is missing."),
        (bool(context.get("queue_evidence_fingerprint")), "Queue evidence fingerprint is missing."),
        (context.get("queue_evidence_fingerprint") == fingerprint(_queue_evidence_binding(item)), "Queue evidence fingerprint is invalid."),
    )
    for passed, reason in checks:
        if not passed:
            return {"eligible": False, "reason": reason}
    return {
        "eligible": True,
        "reason": "Exact ticker-local true-removal evidence is eligible.",
        "removed_source_count": len(item.get("affected_source_keys") or []),
    }


def match_true_removal_approval(
    queue_item: Mapping[str, Any] | None,
    current_scope: Mapping[str, Any],
    *,
    published_binding: str | None,
) -> dict[str, Any]:
    if not queue_item or queue_item.get("operator_action") != CONFIRM_TRUE_SOURCE_REMOVAL:
        return {"applied": False, "reason": "NO_ACTIVE_TRUE_REMOVAL_APPROVAL"}
    if queue_item.get("status") != "RETRY_REEVALUATION":
        return {"applied": False, "reason": "APPROVAL_NOT_PENDING_REEVALUATION"}
    approval = queue_item.get("resolution_evidence") or {}
    if (
        approval.get("resolution_action") != CONFIRM_TRUE_SOURCE_REMOVAL
        or approval.get("resolution_contract_version")
        != TRUE_REMOVAL_APPROVAL_VERSION
    ):
        return {"applied": False, "reason": "APPROVAL_EVIDENCE_MISSING"}
    approved_binding = approval.get("binding")
    if (
        not isinstance(approved_binding, Mapping)
        or approval.get("approval_evidence_fingerprint")
        != fingerprint(approved_binding)
    ):
        return {"applied": False, "reason": "APPROVAL_FINGERPRINT_INVALID"}
    current_item = {
        **dict(queue_item),
        "source_evidence_fingerprint": current_scope.get("source_evidence_fingerprint"),
        "affected_source_keys": current_scope.get("affected_source_keys"),
        "fiscal_identities": current_scope.get("fiscal_identities"),
        "last_published_binding": published_binding,
        "review_context": _review_context_with_integrity(
            current_scope,
            queue_item_id=str(queue_item.get("queue_item_id") or ""),
            published_binding=published_binding,
        ),
    }
    current_binding = _approval_binding(current_item)
    if dict(approved_binding) != current_binding:
        return {
            "applied": False,
            "reason": "TRUE_REMOVAL_APPROVAL_EVIDENCE_DRIFT",
            "current_binding_fingerprint": fingerprint(current_binding),
        }
    return {
        "applied": True,
        "reason": "EXACT_TRUE_REMOVAL_APPROVAL_MATCH",
        "approval_evidence_fingerprint": approval.get("approval_evidence_fingerprint"),
        "approved_binding": dict(approved_binding),
        "approved_source_keys": current_binding["affected_source_keys"],
        "approved_fiscal_identities": current_binding["fiscal_identities"],
        "operator_reviewed": True,
        "resolution_contract_version": TRUE_REMOVAL_APPROVAL_VERSION,
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


def present_review_item(
    item: Mapping[str, Any], *, publication_blocked: bool = False,
) -> dict[str, Any]:
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
    eligibility = retained_history_approval_eligibility(
        item, publication_blocked=publication_blocked,
    )
    fiscal_eligibility = fiscal_revision_approval_eligibility(
        item, publication_blocked=publication_blocked,
    )
    true_removal_eligibility = true_removal_approval_eligibility(
        item, publication_blocked=publication_blocked,
    )
    approval = item.get("resolution_evidence") or {}
    locality = dict((item.get("review_context") or {}).get("locality_proof") or {})
    approval_pending_publication = (
        status == "RETRY_REEVALUATION"
        and item.get("operator_action")
        in (
            ACCEPT_RETAINED_HISTORY,
            ACCEPT_FISCAL_IDENTITY_REVISION,
            CONFIRM_TRUE_SOURCE_REMOVAL,
        )
        and bool(approval.get("approval_evidence_fingerprint"))
    )
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
        "approval_pending_publication": approval_pending_publication,
        "operator_status_label": (
            "Approved - pending publication"
            if approval_pending_publication else status
        ),
        "currently_held": status in OPEN_STATUSES,
        "accept_retained_history_eligible": (
            eligibility["eligible"] and not approval_pending_publication
        ),
        "accept_retained_history_reason": (
            "Approval already granted and pending successful publication."
            if approval_pending_publication else eligibility["reason"]
        ),
        "accept_fiscal_revision_eligible": (
            fiscal_eligibility["eligible"] and not approval_pending_publication
        ),
        "accept_fiscal_revision_reason": (
            "Approval already granted and pending successful publication."
            if approval_pending_publication else fiscal_eligibility["reason"]
        ),
        "confirm_true_removal_eligible": (
            true_removal_eligibility["eligible"]
            and not approval_pending_publication
        ),
        "confirm_true_removal_reason": (
            "Approval already granted and pending successful publication."
            if approval_pending_publication
            else true_removal_eligibility["reason"]
        ),
        "true_removal_source_keys": source_keys,
        "true_removal_changes_financial_history": any(
            isinstance(value, Mapping) and value.get("dimension") == "ARQ"
            for value in source_keys
        ),
        "true_removal_provider_evidence": locality.get(
            "provider_absence_evidence"
        ) or [],
        "fiscal_revision_event_count": len(fiscal_identities),
        "fiscal_revision_events": fiscal_identities,
        "approval_timestamp_utc": approval.get("operator_timestamp_utc"),
        "approval_operator_evidence": approval.get("operator_evidence"),
        "approved_source_count": len(
            (approval.get("binding") or {}).get("affected_source_keys") or []
        ),
        "approval_evidence_fingerprint": approval.get(
            "approval_evidence_fingerprint"
        ),
        "approval_consumed": bool(approval.get("published_at_utc")),
        "approval_consumed_run_id": approval.get("production_run_id"),
        "approval_published_at_utc": approval.get("published_at_utc"),
        "published_state_binding_before": approval.get(
            "published_state_binding_before"
        ),
        "published_state_binding_after": approval.get(
            "published_state_binding_after"
        ),
    }


@dataclass(frozen=True)
class RefreshReviewQueue:
    path: Path

    def ownership_items(self, *, include_resolved: bool = False) -> list[dict[str, Any]]:
        from .pb_ownership_review import list_cases
        return list_cases(self.path, include_resolved=include_resolved)

    def sync_ownership(self, canonical_db: Path, *, as_of: str, run_id: str) -> dict[str, Any]:
        from .pb_ownership_review import sync
        return sync(self.path, canonical_db, as_of=as_of, run_id=run_id)

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
            prior_item = _decode_row(prior) if prior else None
            queue_item_id = (
                str(prior_item.get("queue_item_id"))
                if prior_item and prior_item.get("queue_item_id")
                else fingerprint({
                    "ticker": ticker,
                    "first_seen_run_id": prior_item.get("first_seen_run_id") if prior_item else run_id,
                    "first_seen_at_utc": prior_item.get("first_seen_at_utc") if prior_item else now,
                })
            )
            context = _review_context_with_integrity(
                item, queue_item_id=queue_item_id, published_binding=published_binding,
            )
            material = {
                "source_evidence_fingerprint": item["source_evidence_fingerprint"],
                "affected_source_keys": _ordered_evidence(item["affected_source_keys"]),
                "fiscal_identities": _ordered_evidence(item["fiscal_identities"]),
                "published_binding": published_binding,
                "review_context": context,
            }
            prior_material = {
                "source_evidence_fingerprint": prior_item.get("source_evidence_fingerprint"),
                "affected_source_keys": _ordered_evidence(prior_item.get("affected_source_keys") or []),
                "fiscal_identities": _ordered_evidence(prior_item.get("fiscal_identities") or []),
                "published_binding": prior_item.get("last_published_binding"),
                "review_context": dict(prior_item.get("review_context") or {}),
            } if prior_item else None
            evidence_drift = bool(prior_material and prior_material != material)
            status = (
                str(prior_item["status"])
                if prior_item and prior_item["status"] in OPEN_STATUSES and not evidence_drift
                else "OPEN"
            )
            first_seen_at = str(prior["first_seen_at_utc"]) if prior else now
            first_seen_run = str(prior["first_seen_run_id"]) if prior else run_id
            operator_action = prior_item.get("operator_action") if prior_item and not evidence_drift else None
            resolution_at = prior_item.get("resolution_at_utc") if prior_item and not evidence_drift else None
            resolution_evidence = prior_item.get("resolution_evidence") if prior_item and not evidence_drift else None
            connection.execute(
                "INSERT OR REPLACE INTO refresh_review_queue "
                "(ticker,review_type,reason_codes_json,affected_source_keys_json,"
                "fiscal_identities_json,source_evidence_fingerprint,first_seen_at_utc,"
                "first_seen_run_id,last_seen_at_utc,last_seen_run_id,status,"
                "last_published_binding,operator_action,resolution_at_utc,"
                "resolution_evidence_json,queue_item_id,review_context_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ticker, item["review_type"], _json(item["reason_codes"]),
                    _json(item["affected_source_keys"]), _json(item["fiscal_identities"]),
                    item["source_evidence_fingerprint"], first_seen_at, first_seen_run,
                    now, run_id, status, published_binding,
                    operator_action, resolution_at,
                    _json(resolution_evidence) if resolution_evidence else None,
                    queue_item_id, _json(context),
                ),
            )
            approval_events = {
                ACCEPT_RETAINED_HISTORY: "RETAINED_HISTORY_APPROVAL_INVALIDATED",
                ACCEPT_FISCAL_IDENTITY_REVISION: "FISCAL_REVISION_APPROVAL_INVALIDATED",
                CONFIRM_TRUE_SOURCE_REMOVAL: "TRUE_REMOVAL_APPROVAL_INVALIDATED",
            }
            if evidence_drift and prior_item.get("operator_action") in approval_events:
                self._append_audit(
                    connection,
                    ticker=ticker,
                    event_type=approval_events[str(prior_item.get("operator_action"))],
                    run_id=run_id,
                    evidence={
                        "reason": "MATERIAL_EVIDENCE_DRIFT",
                        "prior_approval": prior_item.get("resolution_evidence"),
                        "current_material_fingerprint": fingerprint(material),
                    },
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
                row = connection.execute(
                    "SELECT * FROM refresh_review_queue WHERE ticker=? AND status IN (?,?,?)",
                    (ticker, *OPEN_STATUSES),
                ).fetchone()
                if row is not None:
                    item = _decode_row(row)
                    invalidation_events = {
                        ACCEPT_RETAINED_HISTORY: "RETAINED_HISTORY_APPROVAL_INVALIDATED",
                        ACCEPT_FISCAL_IDENTITY_REVISION: "FISCAL_REVISION_APPROVAL_INVALIDATED",
                        CONFIRM_TRUE_SOURCE_REMOVAL: "TRUE_REMOVAL_APPROVAL_INVALIDATED",
                    }
                    invalidation_event = invalidation_events.get(
                        str(item.get("operator_action") or "")
                    )
                    if invalidation_event:
                        self._append_audit(
                            connection,
                            ticker=ticker,
                            event_type=invalidation_event,
                            run_id=run_id,
                            evidence={
                                "reason": "REEVALUATED_WITHOUT_LOCAL_REVIEW",
                                "prior_approval": item.get("resolution_evidence"),
                            },
                        )
                connection.execute(
                    "UPDATE refresh_review_queue SET status='RESOLVED',resolution_at_utc=?,resolution_evidence_json=?,last_seen_run_id=?,last_seen_at_utc=? "
                    "WHERE ticker=? AND status IN (?,?,?)",
                    (now, _json({"reason": "REEVALUATED_WITHOUT_LOCAL_REVIEW", "run_id": run_id}), run_id, now, ticker, *OPEN_STATUSES),
                )
            connection.commit()

    @staticmethod
    def _append_audit(
        connection: sqlite3.Connection,
        *,
        ticker: str,
        event_type: str,
        run_id: str | None,
        evidence: Mapping[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO refresh_review_queue_audit"
            "(ticker,event_type,occurred_at_utc,run_id,evidence_json) VALUES(?,?,?,?,?)",
            (ticker, event_type, utc_now(), run_id, _json(dict(evidence))),
        )

    def apply_action(
        self,
        ticker: str,
        action: str,
        *,
        evidence: Mapping[str, Any] | None = None,
        publication_blocked: bool = False,
    ) -> dict[str, Any]:
        normalized = action.strip().upper()
        if normalized in BLOCKED_ACTIONS:
            raise ValueError(f"REFRESH_REVIEW_ACTION_NOT_IMPLEMENTED:{normalized}")
        if normalized not in SUPPORTED_ACTIONS:
            raise ValueError(f"REFRESH_REVIEW_ACTION_INVALID:{normalized}")
        ticker = ticker.upper()
        with _connect(self.path) as connection:
            row = connection.execute(
                "SELECT * FROM refresh_review_queue WHERE ticker=?", (ticker,)
            ).fetchone()
            if row is None or str(row["status"]) == "RESOLVED":
                raise ValueError("REFRESH_REVIEW_ITEM_NOT_OPEN")
            item = _decode_row(row)
            if normalized in (
                ACCEPT_RETAINED_HISTORY,
                ACCEPT_FISCAL_IDENTITY_REVISION,
                CONFIRM_TRUE_SOURCE_REMOVAL,
            ):
                is_fiscal = normalized == ACCEPT_FISCAL_IDENTITY_REVISION
                is_true_removal = normalized == CONFIRM_TRUE_SOURCE_REMOVAL
                eligibility = (
                    true_removal_approval_eligibility(
                        item, publication_blocked=publication_blocked,
                    ) if is_true_removal else fiscal_revision_approval_eligibility(
                        item, publication_blocked=publication_blocked,
                    ) if is_fiscal else retained_history_approval_eligibility(
                        item, publication_blocked=publication_blocked,
                    )
                )
                if not eligibility["eligible"]:
                    raise ValueError(
                        ("REFRESH_TRUE_REMOVAL_NOT_ELIGIBLE:" if is_true_removal else "REFRESH_FISCAL_REVISION_NOT_ELIGIBLE:" if is_fiscal else "REFRESH_RETAINED_HISTORY_NOT_ELIGIBLE:")
                        + str(eligibility["reason"])
                    )
                binding = _approval_binding(item)
                approval_fingerprint = fingerprint(binding)
                prior_approval = item.get("resolution_evidence") or {}
                if (
                    item.get("operator_action") == normalized
                    and item.get("status") == "RETRY_REEVALUATION"
                    and prior_approval.get("approval_evidence_fingerprint")
                    == approval_fingerprint
                ):
                    return item
                now = utc_now()
                resolution_evidence = {
                    "resolution_action": normalized,
                    "resolution_contract_version": (
                        TRUE_REMOVAL_APPROVAL_VERSION
                        if is_true_removal else FISCAL_REVISION_APPROVAL_VERSION
                        if is_fiscal else RETAINED_HISTORY_APPROVAL_VERSION
                    ),
                    "operator_timestamp_utc": now,
                    "operator_evidence": dict(evidence or {}),
                    "originating_review_run": item.get("last_seen_run_id"),
                    "queue_status_at_approval": item.get("status"),
                    "binding": binding,
                    "approval_evidence_fingerprint": approval_fingerprint,
                }
                status = "RETRY_REEVALUATION"
                resolution_at = now
                self._append_audit(
                    connection,
                    ticker=ticker,
                    event_type=(
                        "TRUE_REMOVAL_APPROVED"
                        if is_true_removal else "FISCAL_REVISION_APPROVED"
                        if is_fiscal else "RETAINED_HISTORY_APPROVED"
                    ),
                    run_id=str(item.get("last_seen_run_id") or "") or None,
                    evidence=resolution_evidence,
                )
            else:
                status = (
                    "WAITING_PROVIDER"
                    if normalized == "WAIT_FOR_PROVIDER"
                    else "RETRY_REEVALUATION"
                )
                resolution_at = None
                resolution_evidence = dict(evidence or {})
            changed = connection.execute(
                "UPDATE refresh_review_queue SET status=?,operator_action=?,resolution_at_utc=NULL,resolution_evidence_json=? WHERE ticker=? AND status!='RESOLVED'",
                (
                    status,
                    normalized,
                    _json(resolution_evidence),
                    ticker,
                ),
            ).rowcount
            if normalized in (
                ACCEPT_RETAINED_HISTORY,
                ACCEPT_FISCAL_IDENTITY_REVISION,
                CONFIRM_TRUE_SOURCE_REMOVAL,
            ):
                connection.execute(
                    "UPDATE refresh_review_queue SET resolution_at_utc=? WHERE ticker=?",
                    (resolution_at, ticker),
                )
            connection.commit()
        if changed != 1:
            raise ValueError("REFRESH_REVIEW_ITEM_NOT_OPEN")
        return self.get(ticker) or {}

    def finalize_published_approval(
        self,
        ticker: str,
        *,
        production_run_id: str,
        approval_evidence_fingerprint: str,
        published_state_binding_before: str,
        published_state_binding_after: str,
        published_at_utc: str,
    ) -> dict[str, Any]:
        ticker = ticker.upper()
        with _connect(self.path) as connection:
            row = connection.execute(
                "SELECT * FROM refresh_review_queue WHERE ticker=?", (ticker,)
            ).fetchone()
            if row is None:
                raise ValueError("REFRESH_REVIEW_ITEM_NOT_OPEN")
            item = _decode_row(row)
            approval = dict(item.get("resolution_evidence") or {})
            action = item.get("operator_action")
            if action not in (
                ACCEPT_RETAINED_HISTORY,
                ACCEPT_FISCAL_IDENTITY_REVISION,
                CONFIRM_TRUE_SOURCE_REMOVAL,
            ):
                raise ValueError("REFRESH_OPERATOR_APPROVAL_MISSING")
            if (
                item.get("status") == "RESOLVED"
                and approval.get("publication_status") == "SUCCESSFULLY_PUBLISHED"
                and approval.get("approval_evidence_fingerprint")
                == approval_evidence_fingerprint
                and approval.get("production_run_id") == production_run_id
                and approval.get("published_state_binding_before")
                == published_state_binding_before
                and approval.get("published_state_binding_after")
                == published_state_binding_after
            ):
                return item
            if item.get("status") != "RETRY_REEVALUATION":
                raise ValueError("REFRESH_OPERATOR_APPROVAL_NOT_PENDING_PUBLICATION")
            binding = approval.get("binding")
            if (
                not isinstance(binding, Mapping)
                or approval.get("approval_evidence_fingerprint")
                != approval_evidence_fingerprint
                or fingerprint(binding) != approval_evidence_fingerprint
                or binding.get("published_binding")
                != published_state_binding_before
                or not published_state_binding_after
            ):
                raise ValueError("REFRESH_OPERATOR_APPROVAL_FINALIZATION_DRIFT")
            approval.update({
                "publication_status": "SUCCESSFULLY_PUBLISHED",
                "published_at_utc": published_at_utc,
                "production_run_id": production_run_id,
                "published_state_binding_before": published_state_binding_before,
                "published_state_binding_after": published_state_binding_after,
                "consumption_status": "SUCCESSFUL_PRODUCTION_PUBLICATION",
            })
            connection.execute(
                "UPDATE refresh_review_queue SET status='RESOLVED',"
                "resolution_at_utc=?,resolution_evidence_json=?,"
                "last_seen_run_id=?,last_seen_at_utc=? WHERE ticker=?",
                (
                    published_at_utc,
                    _json(approval),
                    production_run_id,
                    published_at_utc,
                    ticker,
                ),
            )
            self._append_audit(
                connection,
                ticker=ticker,
                event_type=(
                    "TRUE_REMOVAL_APPROVAL_CONSUMED"
                    if action == CONFIRM_TRUE_SOURCE_REMOVAL
                    else "FISCAL_REVISION_APPROVAL_CONSUMED"
                    if action == ACCEPT_FISCAL_IDENTITY_REVISION
                    else "RETAINED_HISTORY_APPROVAL_CONSUMED"
                ),
                run_id=production_run_id,
                evidence=approval,
            )
            connection.commit()
        return self.get(ticker) or {}

    def audit_history(self, ticker: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with _read_connect(self.path) as connection:
            rows = connection.execute(
                "SELECT * FROM refresh_review_queue_audit "
                "WHERE ticker=? ORDER BY audit_id",
                (ticker.upper(),),
            ).fetchall()
        return [
            {
                **dict(row),
                "evidence": json.loads(str(row["evidence_json"])),
            }
            for row in rows
        ]

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
