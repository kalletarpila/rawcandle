from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.publication_journal import (
    PUBLICATION_ROLES,
    PublicationRecoveryError,
    prepare_journal,
    guard_production_writes,
    recover_if_required,
    restore_old_generation,
    safety_status,
    sha256_file,
    sqlite_verification,
    update_journal,
)
from rawcandle.fundamentals.admin.refresh_fundamentals import CONTRACT_VERSION
from rawcandle.fundamentals.admin.refresh_production import (
    SimulatedPublicationCrash,
    _publish_refresh_state,
    _replace_role,
    load_production_authorization,
    render_report,
    run_production_apply,
)
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import AdminOperationType
from rawcandle.fundamentals.admin.production_transaction import ProductionOperation, run_transaction
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def _database(path: Path, generation: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE generation(value TEXT NOT NULL)")
        connection.execute("INSERT INTO generation VALUES(?)", (generation,))


def _generation(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("SELECT value FROM generation").fetchone()[0])


def _publication_fixture(tmp_path: Path) -> tuple[Path, dict[str, dict[str, object]]]:
    roles: dict[str, dict[str, object]] = {}
    backup_dir = tmp_path / "backups"
    candidate_dir = tmp_path / "candidates"
    production_dir = tmp_path / "production"
    for directory in (backup_dir, candidate_dir, production_dir):
        directory.mkdir()
    for role in PUBLICATION_ROLES:
        production = production_dir / f"{role}.db"
        backup = backup_dir / f"{role}.db"
        candidate = candidate_dir / f"{role}.db"
        _database(production, "old")
        shutil.copy2(production, backup)
        _database(candidate, "new")
        roles[role] = {
            "production_path": str(production),
            "old_production_fingerprint": sha256_file(production),
            "backup_path": str(backup),
            "verified_backup_fingerprint": sha256_file(backup),
            "candidate_path": str(candidate),
            "candidate_fingerprint": sha256_file(candidate),
            "replacement_state": "NOT_STARTED",
        }
    journal_path = tmp_path / "journal.json"
    prepare_journal(
        path=journal_path, operation_type="REFRESH_FUNDAMENTALS", run_id="production-run",
        preview_run_id="preview-run", test_run_id="test-run",
        refresh_set_fingerprint="f" * 64, old_source_watermark=None,
        new_source_watermark="2026-09-20", source_schema_fingerprint="schema", roles=roles,
    )
    return journal_path, roles


@pytest.mark.parametrize("published_count", [0, 1, 2, 3])
def test_crash_recovery_restores_complete_old_generation(tmp_path: Path, published_count: int) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    for role in PUBLICATION_ROLES[:published_count]:
        journal = _replace_role(role, journal, journal_path=journal_path)
    if published_count == 3:
        journal = update_journal(journal_path, journal, state="POSTFLIGHT", postflight_state="RUNNING")
    result = recover_if_required(journal_path)
    assert result["status"] == "RECOVERED"
    assert result["recovered"] is True
    assert [_generation(Path(str(roles[role]["production_path"]))) for role in PUBLICATION_ROLES] == ["old"] * 3
    terminal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert terminal["state"] == "RECOVERED"
    assert terminal["candidate_cleanup"]["status"] == "COMPLETED"
    assert all(not Path(str(roles[role]["candidate_path"])).exists() for role in PUBLICATION_ROLES)


def test_terminal_recovery_removes_run_owned_read_only_source_copies(tmp_path: Path) -> None:
    run_id = "production-run"
    lane = tmp_path / "temp" / run_id
    lane.mkdir(parents=True)
    roles: dict[str, dict[str, object]] = {}
    backup_dir = tmp_path / "backups"
    production_dir = tmp_path / "production"
    backup_dir.mkdir()
    production_dir.mkdir()
    for role in PUBLICATION_ROLES:
        production = production_dir / f"{role}.db"
        backup = backup_dir / f"{role}.db"
        candidate = lane / f"{role}.db"
        _database(production, "old")
        shutil.copy2(production, backup)
        _database(candidate, "new")
        roles[role] = {
            "production_path": str(production),
            "old_production_fingerprint": sha256_file(production),
            "backup_path": str(backup),
            "verified_backup_fingerprint": sha256_file(backup),
            "candidate_path": str(candidate),
            "candidate_fingerprint": sha256_file(candidate),
            "replacement_state": "NOT_STARTED",
        }
    _database(lane / "market.db", "authority")
    _database(lane / "taxonomy.db", "authority")
    journal_path = tmp_path / "journal.json"
    journal = prepare_journal(
        path=journal_path, operation_type="REFRESH_FUNDAMENTALS", run_id=run_id,
        preview_run_id="preview", test_run_id="test", refresh_set_fingerprint="f" * 64,
        old_source_watermark=None, new_source_watermark="2026-09-20",
        source_schema_fingerprint="schema", roles=roles,
    )
    recovered = restore_old_generation(journal, journal_path=journal_path)
    assert recovered["status"] == "RECOVERED"
    assert not lane.exists()


def test_publication_journal_intent_is_durable_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    target = Path(str(roles["provider"]["production_path"])).resolve()
    real_replace = os.replace
    observed: list[tuple[str, str]] = []

    def observing_replace(source, destination):
        if Path(destination).resolve() == target:
            durable = json.loads(journal_path.read_text(encoding="utf-8"))
            observed.append((durable["state"], durable["current_publication_step"]))
        return real_replace(source, destination)

    monkeypatch.setattr("rawcandle.fundamentals.admin.refresh_production.os.replace", observing_replace)
    completed = _replace_role("provider", journal, journal_path=journal_path)
    assert observed == [("PUBLISHING", "REPLACING_PROVIDER")]
    assert completed["roles"]["provider"]["replacement_state"] == "REPLACED_AND_VERIFIED"


def test_recovery_journal_intent_is_durable_before_each_restore_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    targets = {
        Path(str(record["production_path"])).resolve(): role
        for role, record in roles.items()
    }
    real_replace = os.replace
    observed: list[tuple[str, str, str, str]] = []

    def observing_replace(source, destination):
        destination_path = Path(destination).resolve()
        if destination_path in targets:
            durable = json.loads(journal_path.read_text(encoding="utf-8"))
            observed.append((
                targets[destination_path], durable["state"], durable["current_publication_step"],
                durable["rollback_recovery_state"],
            ))
        return real_replace(source, destination)

    monkeypatch.setattr("rawcandle.fundamentals.admin.publication_journal.os.replace", observing_replace)
    restore_old_generation(journal, journal_path=journal_path)
    assert observed == [
        ("provider", "RECOVERING", "RESTORING_PROVIDER", "RESTORING_PROVIDER"),
        ("canonical", "RECOVERING", "RESTORING_CANONICAL", "RESTORING_CANONICAL"),
        ("analysis", "RECOVERING", "RESTORING_ANALYSIS", "RESTORING_ANALYSIS"),
    ]


@pytest.mark.parametrize("crash_role", PUBLICATION_ROLES)
def test_crash_during_recovery_restarts_complete_old_generation_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_role: str,
) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    for role in PUBLICATION_ROLES:
        journal = _replace_role(role, journal, journal_path=journal_path)
    assert [_generation(Path(str(roles[role]["production_path"]))) for role in PUBLICATION_ROLES] == ["new"] * 3

    class RecoveryCrash(BaseException):
        pass

    real_replace = os.replace
    crash_target = Path(str(roles[crash_role]["production_path"])).resolve()
    crashed = False

    def crash_during_role_restore(source, destination):
        nonlocal crashed
        result = real_replace(source, destination)
        if Path(destination).resolve() == crash_target and not crashed:
            crashed = True
            raise RecoveryCrash("simulated process loss during recovery")
        return result

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.publication_journal.os.replace",
        crash_during_role_restore,
    )
    with pytest.raises(RecoveryCrash):
        recover_if_required(journal_path)
    interrupted = json.loads(journal_path.read_text(encoding="utf-8"))
    assert interrupted["state"] == "RECOVERING"
    assert interrupted["rollback_recovery_state"] == f"RESTORING_{crash_role.upper()}"
    restored_count = PUBLICATION_ROLES.index(crash_role) + 1
    assert [_generation(Path(str(roles[role]["production_path"]))) for role in PUBLICATION_ROLES] == (
        ["old"] * restored_count + ["new"] * (len(PUBLICATION_ROLES) - restored_count)
    )

    recovered = recover_if_required(journal_path)
    assert recovered["status"] == "RECOVERED"
    assert [_generation(Path(str(roles[role]["production_path"]))) for role in PUBLICATION_ROLES] == ["old"] * 3
    terminal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert terminal["state"] == "RECOVERED"
    assert set(terminal["old_generation_verification"]) == set(PUBLICATION_ROLES)


def test_recovery_is_idempotent_after_recovered_state(tmp_path: Path) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    first = recover_if_required(journal_path)
    mtimes = {role: Path(str(record["production_path"])).stat().st_mtime_ns for role, record in roles.items()}
    second = recover_if_required(journal_path)
    assert first["recovered"] is True
    assert second == {"status": "RECOVERED", "recovered": False}
    assert guard_production_writes(journal_path) == {"status": "RECOVERED", "recovered": False}
    assert {role: Path(str(record["production_path"])).stat().st_mtime_ns for role, record in roles.items()} == mtimes


def test_completed_journal_never_restores_old_generation(tmp_path: Path) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    for role in PUBLICATION_ROLES:
        journal = _replace_role(role, journal, journal_path=journal_path)
    update_journal(journal_path, journal, state="COMPLETED", postflight_state="PASSED")
    assert recover_if_required(journal_path) == {"status": "COMPLETED", "recovered": False}
    assert [_generation(Path(str(roles[role]["production_path"]))) for role in PUBLICATION_ROLES] == ["new"] * 3


def test_completed_journal_is_not_a_global_write_blocker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal_path, _roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    update_journal(journal_path, journal, state="COMPLETED", postflight_state="PASSED")
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.publication_journal.restore_old_generation",
        lambda *_args, **_kwargs: pytest.fail("completed journal must not trigger recovery"),
    )
    assert guard_production_writes(journal_path) == {"status": "COMPLETED", "recovered": False}


def test_missing_backup_fails_closed_and_blocks_writes(tmp_path: Path) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    Path(str(roles["canonical"]["backup_path"])).unlink()
    with pytest.raises(PublicationRecoveryError, match="CRITICAL_RECOVERY_FAILED"):
        recover_if_required(journal_path)
    status = safety_status(journal_path)
    assert status["status"] == "RECOVERY_FAILED"
    assert status["production_writes_blocked"] is True
    with pytest.raises(PublicationRecoveryError, match="PRODUCTION_WRITES_BLOCKED"):
        recover_if_required(journal_path)
    terminal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert terminal["candidate_cleanup"]["status"] == "COMPLETED"
    assert all(not Path(str(roles[role]["candidate_path"])).exists() for role in PUBLICATION_ROLES)


def test_incomplete_refresh_journal_recovers_then_requires_fresh_add_tickers_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    _database(market, "authority")
    _database(taxonomy, "authority")
    paths = BatchAddTickerPaths(
        Path(str(roles["provider"]["production_path"])),
        Path(str(roles["canonical"]["production_path"])),
        Path(str(roles["analysis"]["production_path"])),
        market,
        taxonomy,
    )
    run_root = tmp_path / "runs"
    run_root.mkdir()
    preview_path = tmp_path / "preview.json"
    preview_path.write_text("{}", encoding="utf-8")
    taxonomy_identity = {"domain": "dc_ecosystem", "version": "v", "semantic_fingerprint": "t"}
    mutation_calls: list[bool] = []
    validation_calls: list[bool] = []
    test_validation_calls: list[bool] = []

    def validate_preview(_paths, _payload, _fingerprint):
        validation_calls.append(True)
        return {"as_of_date": "2026-09-20", "taxonomy_dependency": taxonomy_identity}

    operation = ProductionOperation(
        operation_type=AdminOperationType.ADD_TICKERS,
        written_roles=("analysis",),
        validate_preview=validate_preview,
        mutate_sources=lambda *_args: mutation_calls.append(True) or {"outcome": "NO_CHANGE"},
    )
    def verify_test(*_args, **_kwargs):
        test_validation_calls.append(True)
        return {"outcome": "COMPLETED", "downstream": {"active_taxonomy": taxonomy_identity}}

    monkeypatch.setattr("rawcandle.fundamentals.admin.production_transaction._verify_test", verify_test)
    monkeypatch.setattr("rawcandle.fundamentals.admin.production_transaction._source_fingerprints", lambda *_args: {"stable": True})
    monkeypatch.setattr("rawcandle.fundamentals.admin.production_transaction._storage_preflight", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.production_transaction._backup_write_set",
        lambda *_args, **_kwargs: {"analysis": {
            "backup": str(tmp_path / "analysis-backup.db"),
            "verification": {"size": 0, "quick_check": "ok", "foreign_key_check": "ok", "sha256": "fixture"},
        }},
    )
    first = run_transaction(
        operation, preview_payload_path=preview_path, preview_fingerprint="f" * 64,
        test_run_id="test", source_paths=paths, run_root=run_root,
        lock_path=tmp_path / "admin.lock", scheduler_log_dir=str(tmp_path / "scheduler"),
        rehearsal=True, publication_journal_path=journal_path,
    )
    assert mutation_calls == []
    assert first["outcome"] == "RETRY_REQUIRED"
    assert "RECOVERED_RETRY_REQUIRED" in first["error"]
    assert first["retry_authorization"] == {
        "direct_production_retry_available": False,
        "preview_test_preserved": False,
        "preview_test_rerun_required": True,
        "reason": "RECOVERY_COMPLETED_FRESH_INVOCATION_REQUIRED",
    }
    assert first["publication_recovery"]["status"] == "RECOVERED"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == "RECOVERED"
    assert [_generation(paths.as_dict()[role]) for role in PUBLICATION_ROLES] == ["old"] * 3

    second = run_transaction(
        operation, preview_payload_path=preview_path, preview_fingerprint="f" * 64,
        test_run_id="test", source_paths=paths, run_root=run_root,
        lock_path=tmp_path / "admin.lock", scheduler_log_dir=str(tmp_path / "scheduler"),
        rehearsal=True, publication_journal_path=journal_path,
    )
    assert second["outcome"] == "NO_CHANGE"
    assert mutation_calls == [True]
    assert len(validation_calls) == 3
    assert len(test_validation_calls) == 2


def test_completed_refresh_journal_allows_add_tickers_to_reach_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    update_journal(journal_path, journal, state="COMPLETED", postflight_state="PASSED")
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    _database(market, "authority")
    _database(taxonomy, "authority")
    paths = BatchAddTickerPaths(
        Path(str(roles["provider"]["production_path"])),
        Path(str(roles["canonical"]["production_path"])),
        Path(str(roles["analysis"]["production_path"])), market, taxonomy,
    )
    run_root = tmp_path / "runs"
    run_root.mkdir()
    preview_path = tmp_path / "preview.json"
    preview_path.write_text("{}", encoding="utf-8")
    taxonomy_identity = {"domain": "dc_ecosystem", "version": "v", "semantic_fingerprint": "t"}
    mutation_calls: list[bool] = []
    operation = ProductionOperation(
        operation_type=AdminOperationType.ADD_TICKERS, written_roles=("analysis",),
        validate_preview=lambda *_args: {"as_of_date": "2026-09-20", "taxonomy_dependency": taxonomy_identity},
        mutate_sources=lambda *_args: mutation_calls.append(True) or {"outcome": "NO_CHANGE"},
    )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.production_transaction._verify_test",
        lambda *_args, **_kwargs: {"outcome": "COMPLETED", "downstream": {"active_taxonomy": taxonomy_identity}},
    )
    monkeypatch.setattr("rawcandle.fundamentals.admin.production_transaction._source_fingerprints", lambda *_args: {"stable": True})
    monkeypatch.setattr("rawcandle.fundamentals.admin.production_transaction._storage_preflight", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.production_transaction._backup_write_set",
        lambda *_args, **_kwargs: {"analysis": {
            "backup": str(tmp_path / "analysis-backup.db"),
            "verification": {"size": 0, "quick_check": "ok", "foreign_key_check": "ok", "sha256": "fixture"},
        }},
    )
    result = run_transaction(
        operation, preview_payload_path=preview_path, preview_fingerprint="f" * 64,
        test_run_id="test", source_paths=paths, run_root=run_root,
        lock_path=tmp_path / "admin.lock", scheduler_log_dir=str(tmp_path / "scheduler"),
        rehearsal=True, publication_journal_path=journal_path,
    )
    assert mutation_calls == [True]
    assert result["outcome"] == "NO_CHANGE"


def test_ordinary_rollback_can_record_rolled_back_terminal_state(tmp_path: Path) -> None:
    journal_path, roles = _publication_fixture(tmp_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal = _replace_role("provider", journal, journal_path=journal_path)
    journal = update_journal(journal_path, journal, state="ROLLING_BACK")
    recovered = restore_old_generation(journal, journal_path=journal_path)
    terminal = update_journal(journal_path, recovered["journal"], state="ROLLED_BACK")
    assert terminal["state"] == "ROLLED_BACK"
    assert guard_production_writes(journal_path) == {"status": "ROLLED_BACK", "recovered": False}
    assert [_generation(Path(str(roles[role]["production_path"]))) for role in PUBLICATION_ROLES] == ["old"] * 3


def _authorization_fixture(tmp_path: Path) -> tuple[Path, Path, str, str]:
    run_root = tmp_path / "runs"
    preview_dir = run_root / "20260920T100000Z_refresh_fundamentals_preview"
    test_id = "20260920T110000Z_refresh_fundamentals_test"
    test_dir = run_root / test_id
    preview_dir.mkdir(parents=True)
    test_dir.mkdir()
    fingerprint = "f" * 64
    preview_path = preview_dir / "refresh_preview.json"
    preview_path.write_text(json.dumps({
        "contract_version": CONTRACT_VERSION, "refresh_set_fingerprint": fingerprint,
        "future_test_authorized": True, "discovery": {"status": "COMPLETE"},
        "schema": {"schema_fingerprint": "schema"},
        "ticker_changes": [{"ticker": "TEST", "classification": "HISTORICAL_REVISION"}],
    }), encoding="utf-8")
    (test_dir / "result.json").write_text(json.dumps({
        "operation_type": "REFRESH_FUNDAMENTALS", "mode": "COPY_ONLY_APPLY",
        "outcome": "COMPLETED", "preview_fingerprint": fingerprint,
        "bound_preview_run_id": preview_dir.name, "production_file_state_unchanged": True,
        "downstream": {
            "analysis": {"status": "READY", "invocation_counts": {"full_v2_rebuild": 1}},
            "canonical": {
                "identity_contract": {"company_security_identity_mapping_unchanged": True},
                "publication_date_bootstrap": {"repair_required": 0},
            },
        },
    }), encoding="utf-8")
    (test_dir / "source_revalidation.json").write_text(json.dumps({
        "refresh_set_fingerprint": fingerprint, "schema": {"schema_fingerprint": "schema"},
    }), encoding="utf-8")
    return run_root, preview_path, fingerprint, test_id


def test_production_authorization_requires_exact_bound_successful_test(tmp_path: Path) -> None:
    run_root, preview_path, fingerprint, test_id = _authorization_fixture(tmp_path)
    preview, test = load_production_authorization(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint,
        test_run_id=test_id, run_root=run_root,
    )
    assert preview["refresh_set_fingerprint"] == fingerprint
    assert test["bound_preview_run_id"] == preview_path.parent.name


def test_production_authorization_rejects_test_refresh_set_mismatch(tmp_path: Path) -> None:
    run_root, preview_path, fingerprint, test_id = _authorization_fixture(tmp_path)
    source = run_root / test_id / "source_revalidation.json"
    source.write_text(json.dumps({
        "refresh_set_fingerprint": "a" * 64, "schema": {"schema_fingerprint": "schema"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="TEST_REFRESH_SET_MISMATCH"):
        load_production_authorization(
            preview_payload_path=preview_path, preview_fingerprint=fingerprint,
            test_run_id=test_id, run_root=run_root,
        )


def test_refresh_state_is_written_to_candidate_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    production = tmp_path / "production.db"
    candidate = tmp_path / "candidate.db"
    for path in (production, candidate):
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE provider_observation(observation_id TEXT,provider TEXT,native_table TEXT,provider_record_key TEXT,company_id INTEGER,security_id INTEGER,content_hash TEXT)")
            connection.execute("CREATE TABLE sharadar_fundamental_observation(observation_id TEXT,ticker TEXT,dimension TEXT,date TEXT,reportperiod TEXT,lastupdated TEXT)")
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production._provider_semantic_fingerprint",
        lambda _path: "provider-semantic",
    )
    state = _publish_refresh_state(
        candidate, source_watermark="2026-09-20", schema_fingerprint="schema",
        run_id="run", completed_at="2026-09-20T12:00:00Z",
    )
    with sqlite3.connect(production) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='sharadar_refresh_state'").fetchone()[0] == 0
    with sqlite3.connect(candidate) as connection:
        row = connection.execute("SELECT published_source_watermark,successful_run_id FROM sharadar_refresh_state").fetchone()
    assert row == ("2026-09-20", "run")
    assert state["next_query_overlap_days"] == 3


def test_backup_sqlite_verification_records_physical_evidence(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    _database(path, "old")
    evidence = sqlite_verification(path)
    assert evidence["quick_check"] == "ok"
    assert evidence["foreign_key_errors"] == 0
    assert evidence["sha256"] == sha256_file(path)


def test_ui_service_routes_refresh_production_to_shared_backend(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def production(**kwargs):
        calls.append(kwargs)
        return {
            "operation_type": "REFRESH_FUNDAMENTALS", "mode": "PRODUCTION_APPLY",
            "outcome": "COMPLETED", "preview_fingerprint": "f" * 64,
            "test_run_id": "test-run",
        }

    service = FundamentalsAdminUIService(
        run_root=tmp_path, refresh_production_apply=production,
    )
    response = service.production_apply(
        "REFRESH_FUNDAMENTALS", preview_payload_path=str(tmp_path / "preview.json"),
        preview_fingerprint="f" * 64,
        confirmation="CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS", test_run_id="test-run",
    )
    assert response.outcome == "COMPLETED"
    assert calls[0]["confirm_production"] is True
    assert calls[0]["production_intent"] is True
    assert calls[0]["test_run_id"] == "test-run"


def _install_rehearsal_doubles(monkeypatch: pytest.MonkeyPatch, source_paths: BatchAddTickerPaths) -> None:
    revalidated = {
        "state": {"mode": "BOOTSTRAP_BASELINE", "published_watermark": None},
        "schema": {"schema_fingerprint": "schema"},
        "discovery": {"observed_source_max_lastupdated": "2026-09-20"},
        "ticker_changes": [{
            "ticker": "TEST", "classification": "HISTORICAL_REVISION",
            "identity": {"company_id": 1, "security_id": 1, "provider_security_id": "100"},
        }],
        "histories": {"TEST": {"ARQ": object(), "MRQ": object()}},
        "merge_plans": {"TEST": {}},
        "refresh_set_fingerprint": "f" * 64,
    }
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.revalidate_bound_source",
        lambda *_args, **_kwargs: revalidated,
    )

    def replace_provider(path, *_args, **_kwargs):
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE generation SET value='new'")
        return {"ticker_count": 1, "tickers": [], "unrelated_state_unchanged": True}

    monkeypatch.setattr("rawcandle.fundamentals.admin.refresh_production.replace_provider_histories", replace_provider)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production._publish_refresh_state",
        lambda *_args, **_kwargs: {
            "published_source_watermark": "2026-09-20", "provider_semantic_fingerprint": "provider",
            "source_schema_fingerprint": "schema", "successful_run_id": _kwargs["run_id"],
            "completed_at_utc": _kwargs["completed_at"],
        },
    )

    canonical_result = {
        "publication_date_bootstrap": {
            "repair_required": 0, "bootstrap_eligible": 1,
            "preservation_map_applied": 1, "preservation_map_applicable_existing_quarters": 1,
        },
        "removed_quarter_publication_evidence": [],
        "identity_contract": {
            "after": {"fingerprint": "identity"},
            "company_security_identity_mapping_unchanged": True,
        },
        "impact": {
            "added_quarters": 0, "changed_quarters": 1, "removed_quarters": 0,
            "source_availability_date_changes": 1, "bootstrap_only_date_changes": 1,
            "first_public_result_date_preserved": 1, "new_first_public_result_date_established": 0,
        },
    }

    def rebuild_canonical(_provider, canonical, **_kwargs):
        with sqlite3.connect(canonical) as connection:
            connection.execute("UPDATE generation SET value='new'")
        return canonical_result

    monkeypatch.setattr("rawcandle.fundamentals.admin.refresh_production.fresh_rebuild_canonical", rebuild_canonical)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production._identity_mapping",
        lambda *_args: {"fingerprint": "identity"},
    )
    monkeypatch.setattr("rawcandle.fundamentals.admin.refresh_production._analysis_state", lambda *_args: {})
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.validate_provider_candidate",
        lambda *_args, **_kwargs: {"quick_check": "ok"},
    )

    def rebuild_analysis(_sources, *, output, **_kwargs):
        output.mkdir(parents=True)
        candidate = output / "analysis_candidate.db"
        _database(candidate, "new")
        return {
            "candidate_analysis_db": str(candidate), "status": "READY",
            "invocation_counts": {"full_v2_rebuild": 1},
            "taxonomy_dependency": {"domain": "dc_ecosystem", "version": "v", "semantic_fingerprint": "t"},
        }

    monkeypatch.setattr("rawcandle.fundamentals.admin.refresh_production.run_full_v2_downstream", rebuild_analysis)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production._postflight",
        lambda **_kwargs: {"status": "PASSED", "roles": list(PUBLICATION_ROLES)},
    )


def _rehearsal_fixture(tmp_path: Path) -> tuple[BatchAddTickerPaths, Path, Path, str, str]:
    database_dir = tmp_path / "databases"
    database_dir.mkdir()
    paths = []
    for role in ("provider", "canonical", "analysis", "market", "taxonomy"):
        path = database_dir / f"{role}.db"
        _database(path, "old" if role in PUBLICATION_ROLES else "authority")
        paths.append(path)
    source_paths = BatchAddTickerPaths(*paths)
    run_root, preview_path, fingerprint, test_id = _authorization_fixture(tmp_path)
    return source_paths, run_root, preview_path, fingerprint, test_id


def test_production_shaped_rehearsal_commits_only_after_postflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    journal_path = tmp_path / "active-journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert result["outcome"] == "COMPLETED"
    assert result["journal"]["state"] == "COMPLETED"
    assert result["postflight"]["status"] == "PASSED"
    assert [_generation(paths.as_dict()[role]) for role in PUBLICATION_ROLES] == ["new"] * 3
    assert all(_generation(Path(record["backup"])) == "old" for record in result["backups"].values())
    assert not (tmp_path / "temp" / result["run_id"]).exists()
    assert not any((tmp_path / "temp").rglob("*.db"))


def test_production_analysis_candidate_uses_isolated_market_and_taxonomy_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    observed: dict[str, Path] = {}

    def rebuild_analysis(sources, *, output, **_kwargs):
        observed.update({role: Path(path) for role, path in sources.items()})
        output.mkdir(parents=True)
        candidate = output / "analysis_candidate.db"
        _database(candidate, "new")
        return {
            "candidate_analysis_db": str(candidate), "status": "READY",
            "invocation_counts": {"full_v2_rebuild": 1},
            "taxonomy_dependency": {"domain": "dc_ecosystem", "version": "v", "semantic_fingerprint": "t"},
        }

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.run_full_v2_downstream",
        rebuild_analysis,
    )
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=tmp_path / "journal.json",
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert result["outcome"] == "COMPLETED"
    assert observed["market"] != paths.market_db
    assert observed["taxonomy"] != paths.taxonomy_db
    assert observed["market"].name == "market.db"
    assert observed["taxonomy"].name == "taxonomy.db"
    assert result["read_only_source_copies"]["market"]["purpose"] == "FULL_V2_READ_ONLY_SOURCE"
    assert result["cleanup"]["status"] == "COMPLETED"
    assert result["cleanup"]["remaining_phase_owned_files"] == 0


def test_postflight_failure_rolls_back_complete_three_database_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    journal_path = tmp_path / "active-journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
        inject_failure_at="POSTFLIGHT",
    )
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert result["rollback"]["status"] == "ROLLED_BACK"
    assert result["journal"]["state"] == "ROLLED_BACK"
    assert [_generation(paths.as_dict()[role]) for role in PUBLICATION_ROLES] == ["old"] * 3
    assert not any((tmp_path / "temp").rglob("*.db"))


@pytest.mark.parametrize(
    ("failure_stage", "target"),
    [
        ("PROVIDER_CANDIDATE", "replace_provider_histories"),
        ("CANONICAL_CANDIDATE", "fresh_rebuild_canonical"),
        ("ANALYSIS_CANDIDATE", "run_full_v2_downstream"),
        ("CANDIDATE_VALIDATION", "validate_provider_candidate"),
    ],
)
def test_candidate_failure_never_crosses_publication_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str, target: str,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    original = {role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES}

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"fixture failure in {failure_stage}")

    monkeypatch.setattr(f"rawcandle.fundamentals.admin.refresh_production.{target}", fail)
    journal_path = tmp_path / "active-journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == failure_stage
    assert result["write_boundary_crossed"] is False
    assert {role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES} == original
    assert not journal_path.exists()
    assert not (tmp_path / "temp" / result["run_id"]).exists()
    assert not (tmp_path / "backups" / result["run_id"]).exists()
    assert result["cleanup"]["status"] == "COMPLETED"
    assert result["cleanup"]["remaining_phase_owned_files"] == 0
    if failure_stage == "ANALYSIS_CANDIDATE":
        report = (Path(result["artifact_dir"]) / "operation_report.md").read_text(encoding="utf-8")
        assert "Publication boundary entered: NO" in report
        assert "Provider candidate replacements: 1" in report
        assert "Provider published replacements: 0" in report
        assert "## Canonical Candidate Impact" in report
        assert "Candidate prepared; not published" in report
        assert "| Refreshed |" not in report


def test_final_source_recheck_rejects_stale_candidate_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    original = {role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES}
    calls = 0

    def changing_source(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        value = {
            "state": {"mode": "BOOTSTRAP_BASELINE", "published_watermark": None},
            "schema": {"schema_fingerprint": "schema"},
            "discovery": {"observed_source_max_lastupdated": "2026-09-20"},
            "ticker_changes": [{
                "ticker": "TEST", "classification": "HISTORICAL_REVISION",
                "identity": {"company_id": 1, "security_id": 1, "provider_security_id": "100"},
            }],
            "histories": {"TEST": {"ARQ": object(), "MRQ": object()}},
            "merge_plans": {"TEST": {}},
            "refresh_set_fingerprint": fingerprint if calls == 1 else "a" * 64,
        }
        return value

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.revalidate_bound_source", changing_source,
    )
    journal_path = tmp_path / "active-journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert calls == 2
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "FINAL_SOURCE_RECHECK"
    assert result["retry_authorization"]["preview_test_rerun_required"] is True
    assert {role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES} == original
    assert not journal_path.exists()
    assert not (tmp_path / "backups" / result["run_id"]).exists()


def test_start_source_recheck_rejects_stale_test_before_candidate_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    original = {role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES}
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.revalidate_bound_source",
        lambda *_args, **_kwargs: {
            "refresh_set_fingerprint": "a" * 64,
            "schema": {"schema_fingerprint": "schema"},
        },
    )
    journal_path = tmp_path / "active-journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "SOURCE_REVALIDATION"
    assert result["retry_authorization"]["preview_test_rerun_required"] is True
    assert {role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES} == original
    assert not journal_path.exists()
    assert not (tmp_path / "temp" / result["run_id"]).exists()


@pytest.mark.parametrize(
    "crash_point",
    [
        "AFTER_PREPARED",
        "AFTER_PROVIDER_REPLACEMENT",
        "AFTER_CANONICAL_REPLACEMENT",
        "AFTER_ANALYSIS_REPLACEMENT",
        "AFTER_ALL_REPLACEMENTS_BEFORE_POSTFLIGHT",
        "AFTER_POSTFLIGHT_BEFORE_COMPLETED",
    ],
)
def test_process_crash_boundaries_recover_complete_old_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_point: str,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    journal_path = tmp_path / "active-journal.json"
    with pytest.raises(SimulatedPublicationCrash, match=crash_point):
        run_production_apply(
            preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
            source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
            backup_root=tmp_path / "backups", journal_path=journal_path,
            confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
            scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
            inject_crash_at=crash_point,
        )
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] != "COMPLETED"
    recovered = recover_if_required(journal_path)
    assert recovered["status"] == "RECOVERED"
    assert [_generation(paths.as_dict()[role]) for role in PUBLICATION_ROLES] == ["old"] * 3
    assert set(json.loads(journal_path.read_text(encoding="utf-8"))["old_generation_verification"]) == set(PUBLICATION_ROLES)
    assert not any((tmp_path / "temp").rglob("*.db"))


def test_crash_before_prepared_never_requires_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    journal_path = tmp_path / "active-journal.json"
    with pytest.raises(SimulatedPublicationCrash, match="AFTER_BACKUPS_BEFORE_PREPARED"):
        run_production_apply(
            preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
            source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
            backup_root=tmp_path / "backups", journal_path=journal_path,
            confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
            scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
            inject_crash_at="AFTER_BACKUPS_BEFORE_PREPARED",
        )
    assert not journal_path.exists()
    assert [_generation(paths.as_dict()[role]) for role in PUBLICATION_ROLES] == ["old"] * 3


@pytest.mark.parametrize(
    "failure_point",
    ["AFTER_PROVIDER_REPLACEMENT", "AFTER_CANONICAL_REPLACEMENT", "AFTER_ANALYSIS_REPLACEMENT", "POSTFLIGHT"],
)
def test_ordinary_failures_roll_back_complete_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    journal_path = tmp_path / "active-journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
        inject_failure_at=failure_point,
    )
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert result["journal"]["state"] == "ROLLED_BACK"
    assert [_generation(paths.as_dict()[role]) for role in PUBLICATION_ROLES] == ["old"] * 3
    assert not any((tmp_path / "temp").rglob("*.db"))


def test_production_report_separates_financial_and_first_public_changes() -> None:
    report = render_report({
        "outcome": "COMPLETED", "preview_fingerprint": "f" * 64,
        "summary_counts": {"effective_changed_known": 1, "HISTORICAL_REVISION": 1},
        "old_refresh_state": {"published_watermark": None},
        "refresh_state": {
            "published_source_watermark": "2026-09-20", "source_schema_fingerprint": "schema",
        },
        "provider_candidate": {"ticker_count": 1},
        "canonical_candidate": {
            "impact": {
                "added_quarters": 1, "changed_quarters": 2, "removed_quarters": 3,
                "source_availability_date_changes": 4, "bootstrap_only_date_changes": 5,
                "first_public_result_date_preserved": 6,
                "new_first_public_result_date_established": 1,
            },
            "publication_date_bootstrap": {
                "bootstrap_eligible": 5, "preservation_map_applied": 6,
                "preservation_map_applicable_existing_quarters": 6, "repair_required": 0,
            },
            "removed_quarter_publication_evidence": [{}, {}, {}],
            "identity_contract": {"company_security_identity_mapping_unchanged": True},
        },
        "analysis_candidate": {"status": "READY"},
        "backups": {role: {} for role in PUBLICATION_ROLES},
        "journal": {"state": "COMPLETED"}, "postflight": {"status": "PASSED"},
        "rollback": {"status": "NOT_REQUIRED"},
    })
    assert "Canonical published source-driven added/changed/removed: 1 / 2 / 3" in report
    assert "Provider published replacements: 1" in report
    assert "## Canonical Publication" in report
    assert "Published watermark after: 2026-09-20" in report
    assert "First-public bootstrap-only changes: 5" in report
    assert "first_public_result_date preservation map applied: 6/6" in report
    assert "first_public_result_date repair_required: 0" in report
    assert "MRQ overlay intentionally deferred for a later impact study." in report


def test_prepublication_failure_report_uses_candidate_not_published_semantics() -> None:
    report = render_report({
        "outcome": "FAILED", "write_boundary_crossed": False, "production_writes": 0,
        "preview_fingerprint": "f" * 64, "failed_stage": "ANALYSIS_CANDIDATE",
        "summary_counts": {"effective_changed_known": 1},
        "old_refresh_state": {"mode": "BOOTSTRAP_BASELINE", "published_watermark": None},
        "refresh_state": {"mode": "ESTABLISHED_PUBLISHED_STATE", "published_source_watermark": "2026-09-20"},
        "provider_candidate": {"ticker_count": 1},
        "canonical_candidate": {
            "impact": {"added_quarters": 1, "changed_quarters": 2, "removed_quarters": 0},
            "identity_contract": {"company_security_identity_mapping_unchanged": True},
        },
        "ticker_changes": [{"ticker": "TEST", "classification": "HISTORICAL_REVISION", "identity": {"company_id": 1}}],
        "cleanup": {"status": "COMPLETED"},
    })
    assert "Production result: FAILED" in report
    assert "Publication boundary entered: NO" in report
    assert "Production DB writes: 0" in report
    assert "Production generation changed: NO" in report
    assert "Provider candidate replacements: 1" in report
    assert "Provider published replacements: 0" in report
    assert "## Canonical Candidate Impact" in report
    assert "Published watermark after: NONE" in report
    assert "Candidate/proposed next watermark: 2026-09-20" in report
    assert "Full V2/RP/RV: NOT_RUN" in report
    assert "Candidate prepared; not published" in report
    assert "| Refreshed |" not in report
