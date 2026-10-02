from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.refresh_review_queue import (
    ACCEPT_FISCAL_IDENTITY_REVISION,
    ACCEPT_RETAINED_HISTORY,
    GLOBAL_BLOCKING_REVIEW,
    TICKER_LOCAL_REVIEW,
    RefreshReviewQueue,
    classify_review_scope,
    fiscal_revision_approval_eligibility,
    match_fiscal_revision_approval,
    match_retained_history_approval,
    partition_changes,
    present_review_item,
    queue_path_for_run_root,
    retained_history_approval_eligibility,
    review_reason_explanation,
)
from rawcandle.fundamentals.admin.refresh_copy_runtime import _load_bound_preview
from rawcandle.fundamentals.admin.refresh_fundamentals import CONTRACT_VERSION
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def _yyai_review(*, evidence_suffix: str = "") -> dict[str, object]:
    events = []
    for index in range(23):
        dimension = "ARQ" if index < 13 else "MRQ"
        events.append({
            "ticker": "YYAI",
            "dimension": dimension,
            "event": "AGED_OUT_OF_SOURCE_WINDOW" if index == 0 else "AMBIGUOUS_SOURCE_REMOVAL",
            "classification_reason": (
                "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW"
                if index == 0
                else "BOUNDARY_FISCAL_WINDOW_TOO_SHORT"
            ),
            "source_identity": {
                "ticker": "YYAI", "dimension": dimension,
                "date": f"2017-01-{index + 1:02d}{evidence_suffix}",
                "reportperiod": "2016-12-31",
            },
            "fiscal_identity": {
                "fiscal_year": 2017 + index // 4,
                "fiscal_quarter": f"Q{index % 4 + 1}",
            },
            "was_oldest_prefix": True,
            "chronology_coherent": True,
            "same_fiscal_current_keys": [],
            "expected_quarterly_window_covered": index == 0,
        })
    return {
        "ticker": "YYAI",
        "classification": "REVIEW_REQUIRED",
        "review_reason": "AMBIGUOUS_SOURCE_REMOVAL",
        "identity": {
            "status": "KNOWN", "ticker": "YYAI",
            "company_id": 77, "security_id": 770,
        },
        "source_completeness": {
            "ARQ": {"status": "COMPLETE", "ticker": "YYAI", "dimension": "ARQ"},
            "MRQ": {"status": "COMPLETE", "ticker": "YYAI", "dimension": "MRQ"},
        },
        "source_history_action": {
            "newly_aged_out_source_rows": 1,
            "ambiguous_removals": 22,
        },
        "source_history_events": events,
    }


def _ticker_local_review(ticker: str, company_id: int) -> dict[str, object]:
    review = _yyai_review()
    review["ticker"] = ticker
    review["identity"] = {
        "status": "KNOWN", "ticker": ticker,
        "company_id": company_id, "security_id": company_id * 10,
    }
    for event in review["source_history_events"]:
        event["ticker"] = ticker
        event["source_identity"]["ticker"] = ticker
    for dimension in ("ARQ", "MRQ"):
        review["source_completeness"][dimension]["ticker"] = ticker
    return review


def _trug_fiscal_review() -> dict[str, object]:
    source_identity = {
        "ticker": "TRUG", "dimension": "MRQ",
        "date": "2022-03-31", "reportperiod": "2022-03-31",
    }
    proposed = {"fiscal_year": 2022, "fiscal_quarter": "Q4"}
    arq_key = {
        "ticker": "TRUG", "dimension": "ARQ",
        "date": "2022-06-24", "reportperiod": "2022-03-31",
    }
    event = {
        "ticker": "TRUG",
        "dimension": "MRQ",
        "event": "FISCAL_IDENTITY_REVISION",
        "review_status": "REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION",
        "source_identity": dict(source_identity),
        "old_source_identity": dict(source_identity),
        "current_source_identity": dict(source_identity),
        "stable_source_key": True,
        "old_fiscal_identity": {"fiscal_year": 2022, "fiscal_quarter": "Q1"},
        "current_fiscal_identity": proposed,
        "old_source_fingerprint": "old-source-fingerprint",
        "current_source_fingerprint": "new-source-fingerprint",
        "financial_payload_changed": False,
        "target_fiscal_identity_already_exists": True,
        "arq_companion_identity_proof": {
            "status": "AGREES",
            "dimension": "ARQ",
            "reportperiod": "2022-03-31",
            "proposed_mrq_fiscal_identity": proposed,
            "published_fiscal_identities": [proposed],
            "source_fiscal_identities": [proposed],
            "published_source_keys": [arq_key],
            "source_source_keys": [arq_key],
            "published_source_fingerprints": ["published-arq-fingerprint"],
            "source_source_fingerprints": ["source-arq-fingerprint"],
        },
    }
    return {
        "ticker": "TRUG",
        "classification": "REVIEW_REQUIRED",
        "review_reason": "REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION",
        "identity": {
            "status": "KNOWN", "ticker": "TRUG", "company_id": 2212,
            "security_id": 2222, "company_key": "SEC_CIK:0001857086",
            "current_ticker": "TRUG", "provider_security_id": "636515",
            "provider_ticker": "TRUG",
        },
        "source_completeness": {
            "ARQ": {"status": "COMPLETE", "ticker": "TRUG", "dimension": "ARQ"},
            "MRQ": {"status": "COMPLETE", "ticker": "TRUG", "dimension": "MRQ"},
        },
        "source_history_action": {"ambiguous_removals": 0},
        "fiscal_identity_revisions": [event],
        "source_history_events": [event],
    }


def test_trug_shaped_fiscal_revision_is_local_and_persists_complete_queue_evidence(tmp_path: Path) -> None:
    scope = classify_review_scope(_trug_fiscal_review())
    partition = partition_changes([
        {"ticker": "SAFE", "classification": "HISTORICAL_REVISION"},
        _trug_fiscal_review(),
    ])

    assert scope["scope"] == TICKER_LOCAL_REVIEW
    assert scope["review_type"] == "REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION"
    assert scope["locality_proof"]["proven_local_shape"] == "MRQ_FISCAL_REVISION_WITH_ARQ_COMPANION"
    assert partition["binding"]["safe_tickers"] == ["SAFE"]
    assert [item["ticker"] for item in partition["held"]] == ["TRUG"]
    assert partition["global_blockers"] == []

    stored = RefreshReviewQueue(tmp_path / "review.db").upsert_local(
        scope, run_id="preview-1", published_binding="published-1",
    )
    assert stored["queue_item_id"]
    assert stored["first_seen_run_id"] == stored["last_seen_run_id"] == "preview-1"
    assert stored["last_published_binding"] == "published-1"
    assert stored["review_context"]["identity_binding"]["provider_security_id"] == "636515"
    fiscal = stored["fiscal_identities"][0]
    assert fiscal["old_fiscal_identity"] == {"fiscal_year": 2022, "fiscal_quarter": "Q1"}
    assert fiscal["current_fiscal_identity"] == {"fiscal_year": 2022, "fiscal_quarter": "Q4"}
    assert fiscal["old_source_identity"] == fiscal["current_source_identity"]
    assert fiscal["arq_companion_identity_proof"]["status"] == "AGREES"
    assert present_review_item(stored)["accept_retained_history_eligible"] is False
    presented = present_review_item(stored)
    assert presented["accept_fiscal_revision_eligible"] is True
    assert presented["fiscal_revision_event_count"] == 1


def test_fiscal_revision_approval_is_exact_idempotent_and_writes_no_financial_db(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_trug_fiscal_review())
    stored = queue.upsert_local(scope, run_id="preview-1", published_binding="published-1")
    assert fiscal_revision_approval_eligibility(stored)["eligible"] is True
    financial_paths = [tmp_path / name for name in ("provider.db", "canonical.db", "analysis.db")]
    for index, path in enumerate(financial_paths):
        path.write_bytes(f"unchanged-{index}".encode())
    before = {path: path.read_bytes() for path in financial_paths}

    first = queue.apply_action(
        "TRUG", ACCEPT_FISCAL_IDENTITY_REVISION,
        evidence={"source": "fixture", "comment": "reviewed"},
    )
    second = queue.apply_action("TRUG", ACCEPT_FISCAL_IDENTITY_REVISION)

    assert second == first
    assert first["status"] == "RETRY_REEVALUATION"
    assert first["resolution_evidence"]["binding"]["queue_evidence_fingerprint"]
    assert first["resolution_evidence"]["binding"]["fiscal_identities"][0]["old_source_fingerprint"]
    pending = present_review_item(first)
    assert pending["operator_status_label"] == "Approved - pending publication"
    assert pending["approval_pending_publication"] is True
    assert pending["accept_fiscal_revision_eligible"] is False
    assert pending["accept_retained_history_eligible"] is False
    assert {path: path.read_bytes() for path in financial_paths} == before
    matched = match_fiscal_revision_approval(first, scope, published_binding="published-1")
    assert matched["applied"] is True
    consumed = queue.finalize_published_approval(
        "TRUG",
        production_run_id="production-2",
        approval_evidence_fingerprint=first["resolution_evidence"][
            "approval_evidence_fingerprint"
        ],
        published_state_binding_before="published-1",
        published_state_binding_after="production-2",
        published_at_utc="2026-10-02T12:00:00Z",
    )
    assert consumed["status"] == "RESOLVED"
    duplicate = queue.finalize_published_approval(
        "TRUG",
        production_run_id="production-2",
        approval_evidence_fingerprint=first["resolution_evidence"][
            "approval_evidence_fingerprint"
        ],
        published_state_binding_before="published-1",
        published_state_binding_after="production-2",
        published_at_utc="2026-10-02T12:00:00Z",
    )
    assert duplicate == consumed
    assert [item["event_type"] for item in queue.audit_history("TRUG")] == [
        "FISCAL_REVISION_APPROVED", "FISCAL_REVISION_APPROVAL_CONSUMED",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda scope: scope["affected_source_keys"][0].update(date="2022-04-01"),
        lambda scope: scope["fiscal_identities"][0]["current_fiscal_identity"].update(fiscal_quarter="Q3"),
        lambda scope: scope["fiscal_identities"][0].update(current_source_fingerprint="drifted"),
        lambda scope: scope["fiscal_identities"][0]["arq_companion_identity_proof"].update(status="MISSING_OR_CONFLICTING"),
        lambda scope: scope["identity_binding"].update(company_id=999),
        lambda scope: scope.update(scope=GLOBAL_BLOCKING_REVIEW),
    ],
)
def test_fiscal_revision_approval_fails_closed_on_exact_evidence_drift(
    tmp_path: Path, mutation,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_trug_fiscal_review())
    queue.upsert_local(scope, run_id="preview-1", published_binding="published-1")
    approved = queue.apply_action("TRUG", ACCEPT_FISCAL_IDENTITY_REVISION)
    changed = json.loads(json.dumps(scope))
    mutation(changed)

    result = match_fiscal_revision_approval(
        approved, changed, published_binding="published-1",
    )
    assert result["applied"] is False
    assert result["reason"] == "FISCAL_REVISION_APPROVAL_EVIDENCE_DRIFT"


def test_fiscal_revision_drift_reopens_queue_and_preserves_audit(tmp_path: Path) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_trug_fiscal_review())
    queue.upsert_local(scope, run_id="preview-1", published_binding="published-1")
    queue.apply_action("TRUG", ACCEPT_FISCAL_IDENTITY_REVISION)
    changed = json.loads(json.dumps(scope))
    changed["fiscal_identities"][0]["current_source_fingerprint"] = "drifted"

    reopened = queue.upsert_local(
        changed, run_id="preview-2", published_binding="published-1",
    )

    assert reopened["status"] == "OPEN"
    assert reopened["operator_action"] is None
    assert reopened["resolution_evidence"] is None
    assert [item["event_type"] for item in queue.audit_history("TRUG")] == [
        "FISCAL_REVISION_APPROVED", "FISCAL_REVISION_APPROVAL_INVALIDATED",
    ]


def test_fiscal_revision_action_is_ineligible_for_wrong_or_incomplete_scope(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    source_window = queue.upsert_local(
        classify_review_scope(_yyai_review()),
        run_id="preview-1",
        published_binding="published-1",
    )
    assert fiscal_revision_approval_eligibility(source_window)["eligible"] is False

    fiscal = RefreshReviewQueue(tmp_path / "fiscal.db").upsert_local(
        classify_review_scope(_trug_fiscal_review()),
        run_id="preview-1",
        published_binding="published-1",
    )
    incomplete = json.loads(json.dumps(fiscal))
    incomplete["fiscal_identities"][0]["arq_companion_identity_proof"] = None
    assert fiscal_revision_approval_eligibility(incomplete)["eligible"] is False
    global_item = json.loads(json.dumps(fiscal))
    global_item["review_context"]["scope"] = GLOBAL_BLOCKING_REVIEW
    assert fiscal_revision_approval_eligibility(global_item)["eligible"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["source_history_events"][0].update(dimension="ARQ"),
        lambda value: value["source_history_events"][0]["arq_companion_identity_proof"].update(status="MISSING_OR_CONFLICTING"),
        lambda value: value["source_completeness"]["ARQ"].update(status="INCOMPLETE"),
        lambda value: value["source_completeness"]["MRQ"].update(status="INCOMPLETE"),
        lambda value: value["identity"].update(status="REVIEW_REQUIRED"),
        lambda value: value["identity"].pop("provider_security_id"),
        lambda value: value["source_history_events"][0].update(ticker="OTHER"),
        lambda value: value["source_history_events"][0].pop("old_fiscal_identity"),
        lambda value: value["source_history_events"][0].update(stable_source_key=False),
        lambda value: value["source_history_events"].append({"event": "UNRELATED", "ticker": "TRUG"}),
    ],
)
def test_unproven_fiscal_revision_shapes_remain_global(mutation) -> None:
    review = _trug_fiscal_review()
    mutation(review)
    assert classify_review_scope(review)["scope"] == GLOBAL_BLOCKING_REVIEW


def test_fiscal_partition_fingerprint_rejects_evidence_drift() -> None:
    first = partition_changes([_trug_fiscal_review()])
    changed = _trug_fiscal_review()
    changed["source_history_events"][0]["current_source_fingerprint"] = "drifted"
    second = partition_changes([changed])

    assert first["partition_fingerprint"] != second["partition_fingerprint"]
    assert first["held"][0]["source_evidence_fingerprint"] != second["held"][0]["source_evidence_fingerprint"]


def test_fiscal_queue_evidence_tamper_is_rejected(tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    path = queue_path_for_run_root(run_root)
    queue = RefreshReviewQueue(path)
    queue.upsert_local(
        classify_review_scope(_trug_fiscal_review()),
        run_id="preview-1",
        published_binding="published-1",
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE refresh_review_queue SET fiscal_identities_json='[]' WHERE ticker='TRUG'"
        )

    with pytest.raises(ValueError, match="REFRESH_REVIEW_QUEUE_EVIDENCE_TAMPERED"):
        queue.get("TRUG")
    service = FundamentalsAdminUIService(
        run_root=run_root,
        recover_publication_on_startup=False,
        operation_lock_path=tmp_path / "ui.lock",
    )
    assert service.list_refresh_review_queue()["status"] == "ERROR"


def test_yyai_short_window_is_proven_ticker_local_but_aytu_safe_is_not_queued() -> None:
    yyai = classify_review_scope(_yyai_review())
    partition = partition_changes([
        {"ticker": "AAA", "classification": "HISTORICAL_REVISION"},
        {"ticker": "AYTU", "classification": "SOURCE_HISTORY_CHANGE"},
        _yyai_review(),
    ])

    assert yyai["scope"] == TICKER_LOCAL_REVIEW
    assert yyai["review_type"] == "PROVIDER_ANOMALY_SUSPECTED"
    assert len(yyai["affected_source_keys"]) == 23
    assert partition["binding"]["safe_tickers"] == ["AAA", "AYTU"]
    assert [item["ticker"] for item in partition["held"]] == ["YYAI"]
    assert partition["global_blockers"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["identity"].update(status="REVIEW_REQUIRED"),
        lambda value: value["source_completeness"]["MRQ"].update(status="INCOMPLETE"),
        lambda value: value["source_history_events"][0].update(ticker="OTHER"),
        lambda value: value["source_history_events"][0].update(companion_dimension_conflict=True),
    ],
)
def test_nonisolatable_review_remains_global_blocking(mutation) -> None:
    review = _yyai_review()
    mutation(review)
    assert classify_review_scope(review)["scope"] == GLOBAL_BLOCKING_REVIEW


def test_queue_is_idempotent_updates_same_item_and_survives_watermark_change(tmp_path: Path) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    first_scope = classify_review_scope(_yyai_review())
    first = queue.upsert_local(first_scope, run_id="preview-1", published_binding="published-1")
    second = queue.upsert_local(first_scope, run_id="preview-2", published_binding="published-2")

    assert first["first_seen_run_id"] == second["first_seen_run_id"] == "preview-1"
    assert second["last_seen_run_id"] == "preview-2"
    assert second["last_published_binding"] == "published-2"
    assert queue.pending_tickers() == ["YYAI"]

    changed_scope = classify_review_scope(_yyai_review(evidence_suffix="-changed"))
    changed = queue.upsert_local(changed_scope, run_id="preview-3", published_binding="published-3")
    assert changed["source_evidence_fingerprint"] != first["source_evidence_fingerprint"]
    assert changed["first_seen_run_id"] == "preview-1"
    assert queue.pending_tickers() == ["YYAI"]


def test_queue_operator_actions_never_edit_financial_state_and_resolution_is_reevaluation_only(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    queue.upsert_local(
        classify_review_scope(_yyai_review()),
        run_id="preview-1",
        published_binding="published-1",
    )

    waiting = queue.apply_action("YYAI", "WAIT_FOR_PROVIDER", evidence={"ticket": "provider-1"})
    assert waiting["status"] == "WAITING_PROVIDER"
    retry = queue.apply_action("YYAI", "RETRY_REEVALUATION")
    assert retry["status"] == "RETRY_REEVALUATION"
    financial_paths = [
        tmp_path / name
        for name in ("provider.db", "canonical.db", "analysis.db")
    ]
    for index, path in enumerate(financial_paths):
        path.write_bytes(f"unchanged-{index}".encode())
    before = {path: path.read_bytes() for path in financial_paths}
    accepted = queue.apply_action(
        "YYAI",
        ACCEPT_RETAINED_HISTORY,
        evidence={"source": "fixture", "comment": "reviewed"},
    )
    assert accepted["status"] == "RETRY_REEVALUATION"
    assert accepted["operator_action"] == ACCEPT_RETAINED_HISTORY
    assert accepted["resolution_evidence"]["binding"]["ticker"] == "YYAI"
    assert accepted["resolution_evidence"]["operator_evidence"]["comment"] == "reviewed"
    assert {path: path.read_bytes() for path in financial_paths} == before
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED"):
        queue.apply_action("YYAI", "CONFIRM_TRUE_SOURCE_REMOVAL")

    queue.resolve_absent(["YYAI"], [], run_id="preview-2")
    resolved = queue.get("YYAI")
    assert resolved is not None
    assert resolved["status"] == "RESOLVED"
    assert queue.pending_tickers() == []


def test_retained_history_approval_is_exact_idempotent_and_consumed_only_by_matching_evidence(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_yyai_review())
    stored = queue.upsert_local(
        scope, run_id="preview-1", published_binding="published-1",
    )
    eligibility = retained_history_approval_eligibility(stored)
    assert eligibility == {
        "eligible": True,
        "reason": "Exact ticker-local retained-history evidence is eligible.",
        "affected_source_count": 23,
    }

    first = queue.apply_action(
        "YYAI",
        ACCEPT_RETAINED_HISTORY,
        evidence={"source": "fixture", "comment": "accept exact history"},
    )
    second = queue.apply_action(
        "YYAI",
        ACCEPT_RETAINED_HISTORY,
        evidence={"source": "fixture", "comment": "duplicate"},
    )
    assert second == first
    assert len(queue.audit_history("YYAI")) == 1
    pending = present_review_item(first)
    assert pending["operator_status_label"] == "Approved - pending publication"
    assert pending["accept_retained_history_eligible"] is False
    assert pending["accept_fiscal_revision_eligible"] is False

    matched = match_retained_history_approval(
        second, scope, published_binding="published-1",
    )
    assert matched["applied"] is True
    assert len(matched["approved_source_keys"]) == 23
    consumed = queue.finalize_published_approval(
        "YYAI",
        production_run_id="production-2",
        approval_evidence_fingerprint=first["resolution_evidence"][
            "approval_evidence_fingerprint"
        ],
        published_state_binding_before="published-1",
        published_state_binding_after="production-2",
        published_at_utc="2026-10-02T12:00:00Z",
    )
    assert consumed["status"] == "RESOLVED"
    assert consumed["resolution_evidence"]["production_run_id"] == "production-2"
    assert consumed["resolution_evidence"]["published_state_binding_before"] == (
        "published-1"
    )
    assert consumed["resolution_evidence"]["published_state_binding_after"] == (
        "production-2"
    )
    assert [item["event_type"] for item in queue.audit_history("YYAI")] == [
        "RETAINED_HISTORY_APPROVED",
        "RETAINED_HISTORY_APPROVAL_CONSUMED",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda scope: scope["affected_source_keys"][0].update(date="2017-01-99"),
        lambda scope: scope["fiscal_identities"][0].update(fiscal_quarter="Q4"),
        lambda scope: scope["identity_binding"].update(company_id=999),
        lambda scope: scope.update(scope=GLOBAL_BLOCKING_REVIEW),
    ],
)
def test_retained_history_approval_fails_closed_on_material_evidence_drift(
    tmp_path: Path, mutation,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_yyai_review())
    queue.upsert_local(scope, run_id="preview-1", published_binding="published-1")
    approved = queue.apply_action("YYAI", ACCEPT_RETAINED_HISTORY)
    changed = json.loads(json.dumps(scope))
    mutation(changed)

    result = match_retained_history_approval(
        approved, changed, published_binding="published-1",
    )

    assert result["applied"] is False
    assert result["reason"] == "RETAINED_HISTORY_APPROVAL_EVIDENCE_DRIFT"


def test_retained_history_approval_fails_closed_on_published_binding_drift(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_yyai_review())
    queue.upsert_local(scope, run_id="preview-1", published_binding="published-1")
    approved = queue.apply_action("YYAI", ACCEPT_RETAINED_HISTORY)

    result = match_retained_history_approval(
        approved, scope, published_binding="published-2",
    )

    assert result["applied"] is False


def test_new_review_evidence_invalidates_old_approval_but_preserves_audit(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_yyai_review())
    queue.upsert_local(scope, run_id="preview-1", published_binding="published-1")
    queue.apply_action("YYAI", ACCEPT_RETAINED_HISTORY)
    changed_scope = classify_review_scope(_yyai_review(evidence_suffix="-changed"))

    reopened = queue.upsert_local(
        changed_scope, run_id="preview-2", published_binding="published-1",
    )

    assert reopened["status"] == "OPEN"
    assert reopened["operator_action"] is None
    assert reopened["resolution_evidence"] is None
    assert [item["event_type"] for item in queue.audit_history("YYAI")] == [
        "RETAINED_HISTORY_APPROVED",
        "RETAINED_HISTORY_APPROVAL_INVALIDATED",
    ]


def test_global_or_publication_blocked_item_is_not_eligible(tmp_path: Path) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    scope = classify_review_scope(_yyai_review())
    stored = queue.upsert_local(
        scope, run_id="preview-1", published_binding="published-1",
    )
    assert retained_history_approval_eligibility(
        stored, publication_blocked=True,
    )["eligible"] is False
    global_item = dict(stored)
    global_item["review_context"] = {
        **dict(stored["review_context"]),
        "scope": GLOBAL_BLOCKING_REVIEW,
    }
    assert retained_history_approval_eligibility(global_item)["eligible"] is False


def test_ui_service_exposes_queue_status_and_safe_operator_actions(tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    queue = RefreshReviewQueue(queue_path_for_run_root(run_root))
    queue.upsert_local(
        classify_review_scope(_yyai_review()),
        run_id="preview-1",
        published_binding="published-1",
    )
    service = FundamentalsAdminUIService(
        run_root=run_root,
        recover_publication_on_startup=False,
        operation_lock_path=tmp_path / "ui.lock",
    )

    assert [item["ticker"] for item in service.refresh_review_queue()] == ["YYAI"]
    updated = service.resolve_refresh_review(
        "YYAI", "WAIT_FOR_PROVIDER", evidence={"operator": "fixture"},
    )
    assert updated["status"] == "WAITING_PROVIDER"
    assert service.refresh_review_queue()[0]["operator_action"] == "WAIT_FOR_PROVIDER"


def test_test_binding_rejects_tampered_safe_held_partition(tmp_path: Path) -> None:
    preview_dir = tmp_path / "runs" / "preview"
    preview_dir.mkdir(parents=True)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "refresh_set_fingerprint": "f" * 64,
        "future_test_authorized": True,
        "discovery": {"status": "COMPLETE"},
        "schema": {"schema_fingerprint": "schema"},
        "ticker_changes": [{"ticker": "AAA", "classification": "HISTORICAL_REVISION"}],
        "review_partition": {
            "safe_tickers": [], "held": [], "global_blockers": [],
            "partition_fingerprint": "tampered",
        },
    }
    path = preview_dir / "refresh_preview.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="REFRESH_PREVIEW_PARTITION_MISMATCH"):
        _load_bound_preview(path, "f" * 64, tmp_path / "runs")


def test_refresh_binding_projects_retained_history_approval() -> None:
    from rawcandle.fundamentals.admin.refresh_fundamentals import (
        refresh_binding_change,
    )

    approval = {
        "applied": True,
        "approval_evidence_fingerprint": "a" * 64,
        "approved_binding": {"ticker": "YYAI", "queue_item_id": "item-1"},
    }
    projected = refresh_binding_change({
        "ticker": "YYAI",
        "classification": "SOURCE_HISTORY_CHANGE",
        "retained_history_approval": approval,
    })

    assert projected["retained_history_approval"] == approval


def test_open_review_items_accumulate_across_multiple_refresh_runs(tmp_path: Path) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    yyai = classify_review_scope(_ticker_local_review("YYAI", 77))
    abc = classify_review_scope(_ticker_local_review("ABC", 88))

    # Run 1: the first hold is persisted.
    queue.upsert_local(yyai, run_id="run-1", published_binding="watermark-1")
    assert queue.pending_tickers() == ["YYAI"]

    # Run 2: YYAI remains open, ABC joins, and safe changes are independent.
    queue.upsert_local(yyai, run_id="run-2", published_binding="watermark-2")
    queue.upsert_local(abc, run_id="run-2", published_binding="watermark-2")
    partition = partition_changes([
        {"ticker": "SAFE2", "classification": "HISTORICAL_REVISION"},
        _ticker_local_review("YYAI", 77),
        _ticker_local_review("ABC", 88),
    ])
    assert partition["binding"]["safe_tickers"] == ["SAFE2"]
    assert queue.pending_tickers() == ["ABC", "YYAI"]

    # Run 3: both unresolved holds survive another watermark advance.
    queue.upsert_local(yyai, run_id="run-3", published_binding="watermark-3")
    queue.upsert_local(abc, run_id="run-3", published_binding="watermark-3")
    assert queue.pending_tickers() == ["ABC", "YYAI"]
    assert queue.get("YYAI")["first_seen_run_id"] == "run-1"
    assert queue.get("YYAI")["last_seen_run_id"] == "run-3"

    # The next reevaluation resolves YYAI but leaves ABC active for Run 4.
    queue.resolve_absent(["YYAI", "ABC"], ["ABC"], run_id="run-4")
    assert queue.pending_tickers() == ["ABC"]
    all_items = {item["ticker"]: item for item in queue.list_items(include_resolved=True)}
    assert all_items["YYAI"]["status"] == "RESOLVED"
    assert all_items["ABC"]["status"] == "OPEN"


def test_review_queue_presentation_uses_only_stored_evidence_and_safe_reason_text(
    tmp_path: Path,
) -> None:
    queue = RefreshReviewQueue(tmp_path / "review.db")
    stored = queue.upsert_local(
        classify_review_scope(_yyai_review()),
        run_id="preview-first",
        published_binding="published-generation-7",
    )

    presented = present_review_item(stored)

    assert presented["ticker"] == "YYAI"
    assert presented["classification"] == "PROVIDER_ANOMALY_SUSPECTED"
    assert presented["affected_source_count"] == 23
    assert presented["affected_fiscal_identity_count"] == 23
    assert "23 affected source observations" in presented["human_summary"]
    assert "required 41-quarter boundary" in presented["human_summary"]
    assert "materially shorter" in presented["human_summary"]
    assert presented["last_published_binding"] == "published-generation-7"
    assert presented["currently_held"] is True


def test_unknown_review_reason_is_shown_raw_without_invented_explanation() -> None:
    assert review_reason_explanation("UNRECOGNIZED_PROVIDER_SHAPE") == "UNRECOGNIZED_PROVIDER_SHAPE"


def test_service_filters_resolved_history_and_reports_empty_missing_and_corrupt_states(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing" / "runs"
    missing_service = FundamentalsAdminUIService(
        run_root=missing_root,
        recover_publication_on_startup=False,
    )
    assert missing_service.list_refresh_review_queue() == {
        "status": "NOT_INITIALIZED",
        "items": [],
    }
    assert not queue_path_for_run_root(missing_root).exists()

    run_root = tmp_path / "active" / "runs"
    queue = RefreshReviewQueue(queue_path_for_run_root(run_root))
    queue.upsert_local(
        classify_review_scope(_ticker_local_review("OPEN1", 101)),
        run_id="run-1",
        published_binding="published-1",
    )
    queue.upsert_local(
        classify_review_scope(_ticker_local_review("WAIT1", 102)),
        run_id="run-1",
        published_binding="published-1",
    )
    queue.apply_action("WAIT1", "WAIT_FOR_PROVIDER")
    queue.upsert_local(
        classify_review_scope(_ticker_local_review("RETRY1", 103)),
        run_id="run-1",
        published_binding="published-1",
    )
    queue.apply_action("RETRY1", "RETRY_REEVALUATION")
    queue.upsert_local(
        classify_review_scope(_ticker_local_review("DONE1", 104)),
        run_id="run-1",
        published_binding="published-1",
    )
    queue.resolve_absent(["DONE1"], [], run_id="run-2")
    service = FundamentalsAdminUIService(
        run_root=run_root,
        recover_publication_on_startup=False,
    )

    active = service.list_refresh_review_queue()
    assert active["status"] == "READY"
    assert {item["status"] for item in active["items"]} == {
        "OPEN", "WAITING_PROVIDER", "RETRY_REEVALUATION",
    }
    assert "DONE1" not in {item["ticker"] for item in active["items"]}
    with_history = service.list_refresh_review_queue(active_only=False)
    assert "DONE1" in {item["ticker"] for item in with_history["items"]}

    empty_root = tmp_path / "empty" / "runs"
    empty_path = queue_path_for_run_root(empty_root)
    RefreshReviewQueue(empty_path).upsert_local(
        classify_review_scope(_ticker_local_review("DONE2", 105)),
        run_id="run-1",
        published_binding="published-1",
    )
    RefreshReviewQueue(empty_path).resolve_absent(["DONE2"], [], run_id="run-2")
    empty_service = FundamentalsAdminUIService(
        run_root=empty_root,
        recover_publication_on_startup=False,
    )
    assert empty_service.list_refresh_review_queue()["status"] == "EMPTY"

    corrupt_root = tmp_path / "corrupt" / "runs"
    corrupt_path = queue_path_for_run_root(corrupt_root)
    corrupt_path.parent.mkdir(parents=True)
    corrupt_path.write_bytes(b"not a sqlite database")
    corrupt_service = FundamentalsAdminUIService(
        run_root=corrupt_root,
        recover_publication_on_startup=False,
    )
    corrupt = corrupt_service.list_refresh_review_queue()
    assert corrupt["status"] == "ERROR"
    assert corrupt["error"] == "Refresh review queue is unreadable."
    assert corrupt_path.read_bytes() == b"not a sqlite database"


def test_review_queue_list_opens_only_the_operational_queue_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rawcandle.fundamentals.admin.refresh_review_queue as queue_module

    run_root = tmp_path / "runs"
    queue_path = queue_path_for_run_root(run_root)
    queue = RefreshReviewQueue(queue_path)
    queue.upsert_local(
        classify_review_scope(_yyai_review()),
        run_id="run-1",
        published_binding="published-1",
    )
    opened: list[Path] = []
    original = queue_module._read_connect

    def recording_connect(path: Path):
        opened.append(path.resolve())
        return original(path)

    monkeypatch.setattr(queue_module, "_read_connect", recording_connect)
    service = FundamentalsAdminUIService(
        run_root=run_root,
        recover_publication_on_startup=False,
    )

    assert service.list_refresh_review_queue()["status"] == "READY"
    assert opened
    assert set(opened) == {queue_path.resolve()}
