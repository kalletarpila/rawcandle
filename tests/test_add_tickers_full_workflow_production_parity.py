from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Callable

import pytest

from rawcandle.fundamentals.admin import batch_add_tickers, production_operations, production_transaction
from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
from rawcandle.fundamentals.admin.publication_journal import (
    PUBLICATION_ROLES,
)
from rawcandle.fundamentals.admin.source_bundle import semantic_source_binding
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
    copied_sources: list[Path] = []
    downstream_sources: list[dict[str, Path]] = []
    contention_checks: list[str] = []
    original_backup = batch_add_tickers.online_backup
    original_test_downstream = batch_add_tickers.run_full_v2_downstream
    original_production_downstream = production_transaction.rebuild_v2_analysis

    def observed_backup(source: Path, destination: Path) -> None:
        copied_sources.append(Path(source).resolve())
        original_backup(source, destination)

    def observed_test_downstream(sources: dict[str, Path], **kwargs: object) -> dict[str, object]:
        downstream_sources.append({key: Path(value).resolve() for key, value in sources.items()})
        with pytest.raises(RuntimeError, match="taxonomy operation lock is active"):
            with taxonomy_operation_lock_context(
                deployment_id="fixture_writer",
                operation_type="ACTIVATE",
                operation_id="during-add-tickers-test",
            ):
                raise AssertionError("taxonomy writer entered during Add Tickers Test")
        contention_checks.append("TEST")
        return original_test_downstream(sources, **kwargs)

    def observed_production_downstream(
        target: Path, sources: dict[str, Path], **kwargs: object,
    ) -> dict[str, object]:
        downstream_sources.append({key: Path(value).resolve() for key, value in sources.items()})
        with pytest.raises(RuntimeError, match="taxonomy operation lock is active"):
            with taxonomy_operation_lock_context(
                deployment_id="fixture_writer",
                operation_type="ACTIVATE",
                operation_id="during-add-tickers-production",
            ):
                raise AssertionError("taxonomy writer entered during Add Tickers Production")
        contention_checks.append("PRODUCTION")
        return original_production_downstream(target, sources, **kwargs)

    monkeypatch.setattr(batch_add_tickers, "online_backup", observed_backup)
    monkeypatch.setattr(production_transaction, "online_backup", observed_backup)
    monkeypatch.setattr(batch_add_tickers, "run_full_v2_downstream", observed_test_downstream)
    monkeypatch.setattr(production_transaction, "rebuild_v2_analysis", observed_production_downstream)

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
    started = time.monotonic()
    workflow = service.full_workflow(
        operation_type="ADD_TICKERS",
        raw_inputs="KRSA PSQL QVCG",
    )
    runtime = time.monotonic() - started

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
    assert production_result["journal"]["state"] == "COMPLETED"
    assert set(production_result["journal"]["roles"]) == set(PUBLICATION_ROLES)
    assert "market" not in production_result["journal"]["roles"]
    assert "taxonomy" not in production_result["journal"]["roles"]

    bindings = (
        preview_result["read_only_source_binding"],
        test_result["downstream"]["read_only_source_binding"],
        production_result["production_source_binding"],
    )
    for binding in bindings:
        assert binding["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
        assert binding["taxonomy"]["mode"] == "DIRECT_LOCKED_READ"
    tested_contract = semantic_source_binding(bindings[1])
    production_contract = semantic_source_binding(bindings[2])
    assert tested_contract == production_contract
    assert tested_contract["market"]["source_contract_version"] == "FUNDAMENTALS_READ_ONLY_SOURCE_V1"
    assert tested_contract["market"]["valuation_coverage"]["status_identity_fingerprints"]
    assert tested_contract["taxonomy"]["version"] == "DC_PARITY_V1"
    assert production_result["test_source_binding_comparison"]["status"] == "MATCH"
    assert len(downstream_sources) == 2
    for sources in downstream_sources:
        assert sources["market"] != fixture.paths.market_db.resolve()
        assert sources["taxonomy"] == fixture.paths.taxonomy_db.resolve()
    assert contention_checks == ["TEST", "PRODUCTION"]
    assert fixture.paths.market_db.resolve() not in copied_sources
    assert fixture.paths.taxonomy_db.resolve() not in copied_sources

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
    assert not [
        path
        for bundle in temp_root.rglob("market_source_bundle")
        for path in bundle.rglob("*")
        if path.is_file() and path.suffix in {".db", ".sqlite", ".sqlite3"}
    ]
    assert not list(temp_root.rglob("market.db"))
    assert not list(temp_root.rglob("taxonomy.db"))
    with taxonomy_operation_lock_context(
        deployment_id="fixture_writer",
        operation_type="ACTIVATE",
        operation_id="after-add-tickers-workflow",
    ):
        pass
    assert runtime < 90


def _semantic_database(path: Path) -> tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]:
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return tuple(
            (table, tuple(sorted(connection.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr)))
            for table in tables
        )


def _fault_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    before_production: Callable[[], None] | None = None,
    inject_failure_at: str | None = None,
    inject_crash_at: str | None = None,
) -> tuple[FundamentalsAdminUIService, object, Path]:
    fixture = build_parity_fixture(tmp_path / "databases")
    run_root = tmp_path / "runs"
    temp_root = tmp_path / "temp"
    journal_path = tmp_path / "publication-journal.json"
    FixtureSharadarClient.calls = []
    FixtureSharadarClient.rows_by_ticker = fixture.rows
    monkeypatch.setattr(batch_add_tickers, "SharadarClient", FixtureSharadarClient)
    before_called = False

    def preview(raw_inputs: str, **kwargs: object) -> dict[str, object]:
        return batch_add_tickers.run_preview(
            raw_inputs,
            source_paths=fixture.paths,
            run_root=Path(str(kwargs["run_root"])),
            temp_root=temp_root,
            network_allowed=True,
            market="usa",
            progress_callback=kwargs.get("progress_callback"),  # type: ignore[arg-type]
        )

    def test_apply(**kwargs: object) -> dict[str, object]:
        return batch_add_tickers.run_apply(
            preview_payload_path=Path(str(kwargs["preview_payload_path"])),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            source_paths=fixture.paths,
            run_root=Path(str(kwargs["run_root"])),
            temp_root=temp_root,
            confirm_apply=True,
            progress_callback=kwargs.get("progress_callback"),  # type: ignore[arg-type]
        )

    def production_apply(**kwargs: object) -> dict[str, object]:
        nonlocal before_called
        if before_production is not None and not before_called:
            before_called = True
            before_production()
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
            publication_journal_path=journal_path,
            rehearsal=True,
            inject_failure_at=inject_failure_at,
            inject_crash_at=inject_crash_at,
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
    return service, fixture, journal_path


@pytest.mark.integration
@pytest.mark.parametrize("drift", ("market", "taxonomy"))
def test_full_workflow_rejects_semantic_source_drift_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str,
) -> None:
    holder: dict[str, object] = {}

    def mutate() -> None:
        fixture = holder["fixture"]
        if drift == "market":
            with sqlite3.connect(fixture.paths.market_db) as connection:  # type: ignore[attr-defined]
                connection.execute("UPDATE osakedata SET close=close+1 WHERE osake='KRSA' AND pvm='2026-09-20'")
        else:
            with taxonomy_operation_lock_context(
                deployment_id="fixture_writer",
                operation_type="ACTIVATE",
                operation_id="between-test-and-production",
            ):
                with sqlite3.connect(fixture.paths.taxonomy_db) as connection:  # type: ignore[attr-defined]
                    connection.execute(
                        "UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_PARITY_V2',source_hash='changed' WHERE is_active=1"
                    )

    service, fixture, journal_path = _fault_service(
        tmp_path, monkeypatch, before_production=mutate,
    )
    holder["fixture"] = fixture
    old_generation = {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    }

    workflow = service.full_workflow(operation_type="ADD_TICKERS", raw_inputs="KRSA PSQL QVCG")
    durable = json.loads(Path(workflow.artifact_dir, "workflow_result.json").read_text(encoding="utf-8"))
    production_run = durable["stages"][-1]["run_id"]
    production = json.loads(Path(service.run_root, production_run, "result.json").read_text(encoding="utf-8"))

    assert workflow.outcome == "STOPPED"
    assert "SOURCE_BINDING_STALE" in production["error"]
    assert production["write_boundary_crossed"] is False
    assert "backups" not in production
    assert not journal_path.exists()
    assert {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    } == old_generation


@pytest.mark.integration
def test_full_workflow_publication_failure_rolls_back_three_database_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, journal_path = _fault_service(
        tmp_path, monkeypatch, inject_failure_at="post_replacement",
    )
    old_generation = {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    }

    workflow = service.full_workflow(operation_type="ADD_TICKERS", raw_inputs="KRSA PSQL QVCG")
    durable = json.loads(Path(workflow.artifact_dir, "workflow_result.json").read_text(encoding="utf-8"))
    production = json.loads(
        Path(service.run_root, durable["stages"][-1]["run_id"], "result.json").read_text(encoding="utf-8")
    )

    assert workflow.outcome == "STOPPED"
    assert production["outcome"] == "FAILED_ROLLED_BACK"
    assert production["journal"]["state"] == "ROLLED_BACK"
    assert set(production["journal"]["roles"]) == set(PUBLICATION_ROLES)
    assert {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    } == old_generation
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == "ROLLED_BACK"


@pytest.mark.integration
def test_full_workflow_pre_publication_failure_leaves_no_nonterminal_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, journal_path = _fault_service(
        tmp_path, monkeypatch, inject_failure_at="before_first_replacement",
    )
    old_generation = {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    }

    workflow = service.full_workflow(operation_type="ADD_TICKERS", raw_inputs="KRSA PSQL QVCG")
    durable = json.loads(Path(workflow.artifact_dir, "workflow_result.json").read_text(encoding="utf-8"))
    production = json.loads(
        Path(service.run_root, durable["stages"][-1]["run_id"], "result.json").read_text(encoding="utf-8")
    )

    assert workflow.outcome == "STOPPED"
    assert production["write_boundary_crossed"] is False
    assert production["pre_publication_cleanup"] == {
        "journal_removed": True,
        "backup_directory_removed": True,
    }
    assert "journal" not in production
    assert "backups" not in production
    assert not journal_path.exists()
    assert not list((tmp_path / "backups").rglob("*.db"))
    assert {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    } == old_generation


@pytest.mark.integration
def test_full_workflow_crash_recovers_old_generation_and_requires_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, journal_path = _fault_service(
        tmp_path, monkeypatch, inject_crash_at="AFTER_SOURCE_MUTATION",
    )
    old_generation = {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    }

    with pytest.raises(production_transaction.SimulatedTransactionCrash):
        service.full_workflow(operation_type="ADD_TICKERS", raw_inputs="KRSA PSQL QVCG")

    active = json.loads(journal_path.read_text(encoding="utf-8"))
    assert active["state"] == "PUBLISHING"
    assert set(active["roles"]) == set(PUBLICATION_ROLES)
    retry = production_transaction.run_transaction(
        production_operations.ADD_TICKERS,
        preview_payload_path=service.run_root / active["preview_run_id"] / "phase13d_preview_payload.json",
        preview_fingerprint=active["refresh_set_fingerprint"],
        test_run_id=active["test_run_id"],
        source_paths=fixture.paths,  # type: ignore[attr-defined]
        run_root=service.run_root,
        backup_root=tmp_path / "backups",
        scheduler_log_dir=str(tmp_path / "scheduler"),
        lock_path=tmp_path / "production.lock",
        publication_journal_path=journal_path,
        rehearsal=True,
    )
    assert retry["outcome"] == "RETRY_REQUIRED"
    assert retry["publication_recovery"]["status"] == "RECOVERED"
    assert retry["retry_authorization"]["preview_test_rerun_required"] is True
    terminal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert terminal["state"] == "RECOVERED"
    assert {
        role: _semantic_database(fixture.paths.as_dict()[role])  # type: ignore[attr-defined]
        for role in PUBLICATION_ROLES
    } == old_generation
