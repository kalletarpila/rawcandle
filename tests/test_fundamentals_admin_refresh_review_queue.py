from __future__ import annotations

import json
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.refresh_review_queue import (
    GLOBAL_BLOCKING_REVIEW,
    TICKER_LOCAL_REVIEW,
    RefreshReviewQueue,
    classify_review_scope,
    partition_changes,
    queue_path_for_run_root,
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
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED"):
        queue.apply_action("YYAI", "ACCEPT_RETAINED_HISTORY")
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED"):
        queue.apply_action("YYAI", "CONFIRM_TRUE_SOURCE_REMOVAL")

    queue.resolve_absent(["YYAI"], [], run_id="preview-2")
    resolved = queue.get("YYAI")
    assert resolved is not None
    assert resolved["status"] == "RESOLVED"
    assert queue.pending_tickers() == []


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
