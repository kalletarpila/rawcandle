from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import batch_add_tickers, production_operations, production_transaction
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.add_tickers_production_parity_fixtures import (
    FixtureSharadarClient,
    build_parity_fixture,
)


@pytest.mark.integration
def test_real_full_workflow_publishes_three_reviewed_identity_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_parity_fixture(tmp_path / "databases")
    run_root = tmp_path / "runs"
    temp_root = tmp_path / "temp"
    FixtureSharadarClient.calls = []
    FixtureSharadarClient.rows_by_ticker = fixture.rows
    monkeypatch.setattr(batch_add_tickers, "SharadarClient", FixtureSharadarClient)

    def preview(raw_inputs: str, **kwargs: object) -> dict[str, object]:
        return batch_add_tickers.run_preview(
            raw_inputs,
            source_paths=fixture.paths,
            run_root=Path(str(kwargs["run_root"])),
            temp_root=temp_root,
            network_allowed=bool(kwargs.get("network_allowed")),
            market=str(kwargs.get("market") or "usa"),
            progress_callback=kwargs.get("progress_callback"),  # type: ignore[arg-type]
        )

    def test_apply(**kwargs: object) -> dict[str, object]:
        return batch_add_tickers.run_apply(
            preview_payload_path=Path(str(kwargs["preview_payload_path"])),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            source_paths=fixture.paths,
            run_root=Path(str(kwargs["run_root"])),
            temp_root=temp_root,
            confirm_apply=bool(kwargs.get("confirm_apply")),
            progress_callback=kwargs.get("progress_callback"),  # type: ignore[arg-type]
        )

    def production_apply(**kwargs: object) -> dict[str, object]:
        return production_transaction.run_transaction(
            production_operations.ADD_TICKERS,
            preview_payload_path=Path(str(kwargs["preview_payload_path"])),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            test_run_id=str(kwargs["test_run_id"]),
            source_paths=fixture.paths,
            run_root=Path(str(kwargs["run_root"])),
            backup_root=tmp_path / "backups",
            scheduler_log_dir=str(tmp_path / "scheduler"),
            lock_path=tmp_path / "production.lock",
            publication_journal_path=tmp_path / "publication-journal.json",
            rehearsal=True,
            progress_callback=kwargs.get("progress_callback"),  # type: ignore[arg-type]
        )

    service = FundamentalsAdminUIService(
        run_root=run_root,
        add_preview=preview,
        add_apply=test_apply,
        add_production_apply=production_apply,
        identity_paths=fixture.paths,
        operation_lock_path=tmp_path / "ui.lock",
        recover_publication_on_startup=False,
    )
    workflow = service.full_workflow(
        operation_type="ADD_TICKERS",
        raw_inputs="KRSA PSQL QVCG",
    )

    assert workflow.outcome == "COMPLETED", workflow.message
    result = json.loads(Path(workflow.artifact_dir, "workflow_result.json").read_text(encoding="utf-8"))
    assert [stage["stage"] for stage in result["stages"]] == [
        "Preview", "Test on copies", "Production update",
    ]
    assert result["terminal_summary"]["production_completed"] is True
    assert result["terminal_summary"]["batch_outcome"]["requested"] == 3
    assert result["terminal_summary"]["batch_outcome"]["published_added"] == 3

    child_results = {
        stage["stage"]: json.loads(
            Path(run_root, stage["run_id"], "result.json").read_text(encoding="utf-8")
        )
        for stage in result["stages"]
    }
    preview_result = child_results["Preview"]
    test_result = child_results["Test on copies"]
    production_result = child_results["Production update"]
    assert preview_result["applyability"] == {
        "copy_apply_authorized": True,
        "eligible_count": 3,
        "review_required_count": 0,
        "rejected_count": 0,
        "blocking_items": [],
    }
    assert test_result["downstream"]["invocation_counts"]["full_v2_rebuild"] == 1
    test_tickers = {row["ticker"]: row for row in test_result["ticker_reporting"]}
    for ticker, expected in fixture.expected_arq.items():
        lineage = test_tickers[ticker]["lineage"]
        assert lineage["source_arq_acceptance_invariant"] == f"{expected}/{expected}"
        assert lineage["canonical_quarter_invariant"] == f"{expected}/{expected}"
        assert lineage["analysis_input_ttm_rows"] == expected
    assert test_tickers["KRSA"]["after"]["analysis"]["score"]["status"] == "SCORE_FULL"
    assert test_tickers["PSQL"]["after"]["analysis"]["score"]["status"] == "SCORE_NOT_READY"
    assert test_tickers["PSQL"]["after"]["analysis"]["integrity_status"] == "READY"
    assert test_tickers["QVCG"]["after"]["analysis"]["score"]["status"] == "SCORE_FULL"
    assert test_tickers["QVCG"]["after"]["analysis"]["rv"]["status"] == "VALUATION_FULL"
    assert production_result["outcome"] == "COMPLETED"
    assert production_result["lock_owner"]
    assert set(production_result["backups"]) == {"provider", "canonical", "analysis"}
    assert all(
        backup["verification"]["quick_check"] == "ok"
        for backup in production_result["backups"].values()
    )
    assert production_result["publication_recovery_preflight"] == {
        "status": "NO_JOURNAL", "recovered": False,
    }
    assert production_result["full_v2_rebuild"]["status"] == "READY"
    assert production_result["atomic_replacement"]["status"] == "REPLACED"
    assert production_result["postflight"]
    assert production_result["rollback"]["status"] == "NOT_REQUIRED"

    with sqlite3.connect(fixture.paths.canonical_db) as connection:
        identities = {
            ticker: connection.execute(
                "SELECT company_id,security_id FROM security WHERE current_ticker=?", (ticker,)
            ).fetchone()
            for ticker in fixture.expected_arq
        }
        assert identities["KRSA"][0] == 627
        assert identities["KRSA"][1] != 628
        assert identities["PSQL"][0] not in {627, 700, 701}
        assert identities["QVCG"][0] not in {627, 700, 701, identities["PSQL"][0]}
        assert connection.execute(
            "SELECT active FROM security WHERE security_id=628 AND current_ticker='CYCN'"
        ).fetchone() == (1,)
        for ticker, expected in fixture.expected_arq.items():
            company_id = identities[ticker][0]
            assert connection.execute(
                "SELECT COUNT(*) FROM v4_quarter WHERE company_id=?", (company_id,)
            ).fetchone()[0] == expected

    assert FixtureSharadarClient.calls
    assert all("fields" not in call for call in FixtureSharadarClient.calls)
    assert all(stage["report"] for stage in result["stages"])
    assert not list((tmp_path / "databases").glob(".*.candidate.db*"))
