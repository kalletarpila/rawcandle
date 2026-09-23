from __future__ import annotations

import json
import os
import shutil
import sqlite3
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import full_v2_downstream, refresh_copy_runtime, refresh_production
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
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    CONTRACT_VERSION,
    FINANCIAL_FIELDS,
    validate_complete_history,
)
from rawcandle.fundamentals.admin.refresh_production import (
    RefreshPostflightValidationError,
    SimulatedPublicationCrash,
    _required_taxonomy_dependency,
    _validate_analysis_generation,
    _publish_refresh_state,
    _postflight,
    _replace_role,
    compare_test_and_production_source_bindings,
    load_production_authorization,
    render_report,
    run_production_apply as _run_production_apply,
)
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import AdminOperationType
from rawcandle.fundamentals.admin.production_transaction import ProductionOperation, run_transaction
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.admin.source_bundle import TaxonomySourceBinding
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_database,
)


FIXTURE_AS_OF_DATE = "2026-09-22"


def run_production_apply(*args, **kwargs):
    kwargs.setdefault("as_of_date", FIXTURE_AS_OF_DATE)
    return _run_production_apply(*args, **kwargs)


def _database(path: Path, generation: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE generation(value TEXT NOT NULL)")
        connection.execute("INSERT INTO generation VALUES(?)", (generation,))


def _generation(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("SELECT value FROM generation").fetchone()[0])


def _source_binding(as_of_date: str = "2026-09-22") -> dict[str, object]:
    return {
        "market": {
            "mode": "STABLE_SOURCE_BUNDLE",
            "bundle_path": "/ephemeral/market.db",
            "manifest_path": "/ephemeral/manifest.json",
            "old_full_copy_bytes_avoided": 1_000,
            "compact_bundle_bytes": 100,
            "bundle_build_seconds": 0.1,
            "bundle_manifest": {
                "source_contract_version": "FUNDAMENTALS_READ_ONLY_SOURCE_V1",
                "mode": "STABLE_SOURCE_BUNDLE",
                "as_of_date": as_of_date,
                "canonical_binding": {
                    "semantic_fingerprint": "canonical-fp",
                    "valuation_requirement_count": 2,
                    "recent_ticker_count": 1,
                    "validation_sample_ticker": "TEST",
                },
                "market": {
                    "semantic_fingerprint": "market-fp",
                    "physical_sha256": "physical-layout-may-differ",
                    "schema_fingerprint": "market-schema",
                    "row_counts": {"ticker_meta": 1, "osakedata": 2, "splits_data": 0},
                    "valuation_coverage": {
                        "requirements": 2,
                        "status_counts": {
                            "PRICE_FOUND": 1, "NO_MATCHING_VALID_PRICE": 0,
                            "NO_CUTOFF": 1, "NO_TICKER": 0,
                        },
                        "status_identity_fingerprints": {
                            "PRICE_FOUND": "price-found-fp",
                            "NO_MATCHING_VALID_PRICE": "no-match-fp",
                            "NO_CUTOFF": "no-cutoff-fp",
                            "NO_TICKER": "no-ticker-fp",
                        },
                    },
                },
            },
        },
        "taxonomy": {
            "mode": "DIRECT_LOCKED_READ",
            "binding": {
                "domain": "dc_ecosystem", "version": "v",
                "semantic_fingerprint": "t", "membership_rows": 1,
            },
        },
    }


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
    source_binding = _source_binding()
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
            "read_only_source_binding": source_binding,
        },
    }), encoding="utf-8")
    (test_dir / "read_only_source_binding.json").write_text(
        json.dumps(source_binding), encoding="utf-8",
    )
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
    assert test["_authorized_source_binding"]["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert Path(test["_authorized_source_binding_path"]).name == "read_only_source_binding.json"


def test_production_authorization_rejects_mismatched_binding_artifact(tmp_path: Path) -> None:
    run_root, preview_path, fingerprint, test_id = _authorization_fixture(tmp_path)
    binding_path = run_root / test_id / "read_only_source_binding.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    binding["market"]["bundle_manifest"]["market"]["semantic_fingerprint"] = "tampered"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")

    with pytest.raises(ValueError, match="TEST_SOURCE_BINDING_EVIDENCE_MISMATCH"):
        load_production_authorization(
            preview_payload_path=preview_path, preview_fingerprint=fingerprint,
            test_run_id=test_id, run_root=run_root,
        )


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


def test_source_binding_ignores_physical_layout_and_out_of_contract_fields() -> None:
    tested = _source_binding()
    production = deepcopy(tested)
    production["market"]["bundle_manifest"]["market"]["physical_sha256"] = "different-layout"
    production["market"]["bundle_manifest"]["market"]["source_identity_after"] = "later-irrelevant-row"
    production["market"]["bundle_path"] = "/different/ephemeral/path.db"
    production["taxonomy"]["copy_sha256"] = "different-copy-layout"

    comparison = compare_test_and_production_source_bindings(tested, production)

    assert comparison["status"] == "MATCH"
    assert comparison["differing_contract_sections"] == []


@pytest.mark.parametrize(
    ("mutation", "expected_section"),
    [
        (lambda value: value["market"]["bundle_manifest"]["market"].update(semantic_fingerprint="changed-price-value"), "market"),
        (lambda value: value["market"]["bundle_manifest"]["market"]["valuation_coverage"]["status_identity_fingerprints"].update(NO_CUTOFF="changed-identity"), "market"),
        (lambda value: value["market"]["bundle_manifest"]["canonical_binding"].update(semantic_fingerprint="changed-canonical"), "market"),
        (lambda value: value["market"]["bundle_manifest"].update(source_contract_version="V2"), "market"),
        (lambda value: value["market"]["bundle_manifest"].update(as_of_date="2026-09-23"), "market"),
        (lambda value: value["taxonomy"]["binding"].update(version="v2"), "taxonomy"),
        (lambda value: value["taxonomy"]["binding"].update(semantic_fingerprint="changed-taxonomy"), "taxonomy"),
    ],
)
def test_material_source_binding_changes_are_stale(mutation, expected_section: str) -> None:
    tested = _source_binding()
    production = deepcopy(tested)
    mutation(production)

    comparison = compare_test_and_production_source_bindings(tested, production)

    assert comparison["status"] == "STALE"
    assert comparison["differing_contract_sections"] == [expected_section]


def test_stale_source_binding_stops_before_downstream_backup_and_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    downstream_called = False
    original_prepare = refresh_production.prepare_compact_read_only_sources

    def stale_prepare(*args, **kwargs):
        read_only, evidence = original_prepare(*args, **kwargs)
        evidence = deepcopy(evidence)
        evidence["market"]["bundle_manifest"]["market"]["semantic_fingerprint"] = "changed-price-value"
        return read_only, evidence

    def forbidden_downstream(*_args, **_kwargs):
        nonlocal downstream_called
        downstream_called = True
        raise AssertionError("downstream must not run for stale Test binding")

    monkeypatch.setattr(refresh_production, "prepare_compact_read_only_sources", stale_prepare)
    monkeypatch.setattr(refresh_production, "run_refresh_production_full_v2_downstream", forbidden_downstream)
    journal_path = tmp_path / "journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )

    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "ANALYSIS_CANDIDATE"
    assert "REFRESH_TEST_SOURCE_BINDING_STALE:market" in result["error"]
    assert result["test_source_binding_comparison"]["status"] == "STALE"
    assert result["retry_authorization"]["preview_test_rerun_required"] is True
    assert downstream_called is False
    assert "backups" not in result
    assert not journal_path.exists()
    assert result["publication_activity"]["live_replacements"] == []
    assert result["cleanup"]["remaining_phase_owned_files"] == 0


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

    @contextmanager
    def protected_taxonomy(_taxonomy, _canonical, *, operation_id):
        yield TaxonomySourceBinding(
            mode="DIRECT_LOCKED_READ", source_path=str(source_paths.taxonomy_db.resolve()),
            domain="dc_ecosystem", version="v", semantic_fingerprint="t",
            membership_rows=1, lock_path=str(source_paths.taxonomy_db.with_suffix(".lock")),
            lock_contract_status="AUTHORITATIVE_TAXONOMY_LOCK_HELD",
            runtime_authorized=True, packaged=False,
        )

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.protected_direct_taxonomy_source",
        protected_taxonomy,
    )

    def prepare_sources(_paths, *, lane_dir, canonical_candidate, as_of_date, taxonomy_binding):
        del canonical_candidate
        assert taxonomy_binding.mode == "DIRECT_LOCKED_READ"
        bundle_dir = lane_dir / "market_source_bundle"
        bundle_dir.mkdir()
        compact_market = bundle_dir / "market.db"
        _database(compact_market, "authority")
        evidence = _source_binding(as_of_date)
        evidence["market"]["bundle_path"] = str(compact_market)
        evidence["market"]["manifest_path"] = str(bundle_dir / "manifest.json")
        evidence["taxonomy"]["binding"]["source_path"] = str(source_paths.taxonomy_db.resolve())
        return {"market": compact_market, "taxonomy": source_paths.taxonomy_db.resolve()}, evidence

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.prepare_compact_read_only_sources",
        prepare_sources,
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
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.validate_rebuild",
        lambda *_args, **_kwargs: {"status": "VALIDATED"},
    )

    def rebuild_analysis(_sources, *, output, **_kwargs):
        output.mkdir(parents=True)
        candidate = output / "analysis_candidate.db"
        _database(candidate, "new")
        return {
            "candidate_analysis_db": str(candidate), "status": "READY",
            "invocation_counts": {"full_v2_rebuild": 1},
            "active_taxonomy": {"domain": "dc_ecosystem", "version": "v", "semantic_fingerprint": "t"},
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
    assert result["publication_activity"]["live_replacements"] == list(PUBLICATION_ROLES)
    assert result["publication_activity"]["rollback_restorations"] == []


def test_production_analysis_candidate_uses_compact_market_and_direct_taxonomy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)
    observed: dict[str, Path] = {}
    copied_sources: list[Path] = []
    actual_online_backup = refresh_production.online_backup

    def recording_backup(source: Path, destination: Path):
        copied_sources.append(source)
        return actual_online_backup(source, destination)

    def rebuild_analysis(sources, *, output, **_kwargs):
        observed.update({role: Path(path) for role, path in sources.items()})
        output.mkdir(parents=True)
        candidate = output / "analysis_candidate.db"
        _database(candidate, "new")
        return {
            "candidate_analysis_db": str(candidate), "status": "READY",
            "invocation_counts": {"full_v2_rebuild": 1},
            "active_taxonomy": {"domain": "dc_ecosystem", "version": "v", "semantic_fingerprint": "t"},
        }

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.run_full_v2_downstream",
        rebuild_analysis,
    )
    monkeypatch.setattr(refresh_production, "online_backup", recording_backup)
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=tmp_path / "journal.json",
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert result["outcome"] == "COMPLETED"
    assert observed["market"] != paths.market_db
    assert observed["taxonomy"] == paths.taxonomy_db.resolve()
    assert observed["market"].parent.name == "market_source_bundle"
    assert observed["market"].name == "market.db"
    assert paths.taxonomy_db not in copied_sources
    assert paths.market_db not in copied_sources
    assert paths.provider_db in copied_sources
    assert paths.canonical_db in copied_sources
    assert result["production_source_binding"]["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert result["production_source_binding"]["taxonomy"]["mode"] == "DIRECT_LOCKED_READ"
    assert result["test_source_binding_comparison"]["status"] == "MATCH"
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
    assert result["publication_activity"]["live_replacements"] == list(PUBLICATION_ROLES)
    assert result["publication_activity"]["rollback_restorations"] == list(PUBLICATION_ROLES)


def test_missing_taxonomy_dependency_is_rejected_before_backup_or_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    _install_rehearsal_doubles(monkeypatch, paths)

    def malformed_rebuild(_sources, *, output, **_kwargs):
        output.mkdir(parents=True)
        candidate = output / "analysis_candidate.db"
        _database(candidate, "new")
        return {
            "candidate_analysis_db": str(candidate), "status": "READY",
            "invocation_counts": {"full_v2_rebuild": 1},
        }

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.run_full_v2_downstream",
        malformed_rebuild,
    )
    journal_path = tmp_path / "journal.json"
    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=journal_path,
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(),
    )
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "CANDIDATE_VALIDATION"
    assert "REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISSING_OR_MALFORMED" in result["error"]
    assert "KeyError" not in result["error"]
    assert result["write_boundary_crossed"] is False
    assert "backups" not in result
    assert not journal_path.exists()
    assert result["publication_activity"]["live_replacements"] == []


def test_production_parity_consumes_real_full_v2_wrapper_output_through_postflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, fingerprint, test_id = _rehearsal_fixture(tmp_path)
    paths.provider_db.unlink()
    paths.canonical_db.unlink()
    bootstrap_database(paths.provider_db, "fundamentals_provider", PROVIDER_SCHEMA_SQL, "2026-09-20T00:00:00Z")
    bootstrap_database(paths.canonical_db, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "2026-09-20T00:00:00Z")
    with sqlite3.connect(paths.provider_db) as connection:
        connection.execute("CREATE TABLE generation(value TEXT NOT NULL)")
        connection.execute("INSERT INTO generation VALUES('old')")
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("CREATE TABLE generation(value TEXT NOT NULL)")
        connection.execute("INSERT INTO generation VALUES('old')")
        connection.execute(
            "INSERT INTO company VALUES(1,'TEST','Test Corp','ACTIVE','2026-09-20T00:00:00Z','2026-09-20T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO security VALUES(1,1,'TEST','NASDAQ',1,NULL,NULL,'2026-09-20T00:00:00Z','2026-09-20T00:00:00Z')"
        )
        connection.execute("INSERT INTO ticker_alias VALUES(1,1,'TEST','SHARADAR',NULL,NULL,'fixture')")
        connection.execute(
            "INSERT INTO provider_security_identity VALUES('SHARADAR','100',1,'TEST','fixture','2026-09-20T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO provider_company_identity VALUES("
            "'SHARADAR','PERMATICKER','100',1,'TEST','fixture','fixture','100','2026-09-20T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO v4_quarter VALUES(1,1,2026,'Q2','2026-06-30','2026-Q2','2026-06-30',"
            "'SHARADAR_ARQ','ACCEPTED','2026-08-15','2026-08-15','2026-09-20T00:00:00Z','2026-09-20T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO v4_quarter_financials(quarter_id,revenue,net_income,shares_outstanding,"
            "canonical_source_policy,created_at_utc,updated_at_utc) "
            "VALUES(1,100,10,5,'SHARADAR_ARQ_PRIMARY','2026-09-20T00:00:00Z','2026-09-20T00:00:00Z')"
        )

    actual_postflight = refresh_production._postflight
    _install_rehearsal_doubles(monkeypatch, paths)
    installed_prepare = refresh_production.prepare_compact_read_only_sources
    prepared_source_pairs: list[dict[str, Path]] = []

    def recording_prepare(*args, **kwargs):
        prepared, evidence = installed_prepare(*args, **kwargs)
        prepared_source_pairs.append(dict(prepared))
        return prepared, evidence

    monkeypatch.setattr(refresh_production, "prepare_compact_read_only_sources", recording_prepare)
    dependency = {
        "domain": "dc_ecosystem", "version": "DC_FIXTURE_V1",
        "semantic_fingerprint": "fixture-semantic",
    }
    source_base = {
        "ticker": "TEST", "date": "2026-08-15", "reportperiod": "2026-06-30",
        "calendardate": "2026-06-30", "fiscalperiod": "2026-Q2",
        "lastupdated": "2026-09-20", **{field: None for field in FINANCIAL_FIELDS},
        "revenue": 120, "netinc": 10, "sharesbas": 5,
    }
    histories = {
        "TEST": {
            dimension: validate_complete_history(
                [dict(source_base, dimension=dimension)], ticker="TEST", dimension=dimension,
            )
            for dimension in ("ARQ", "MRQ")
        }
    }
    merge_plan = {
        "action": {},
        "dimensions": {
            dimension: {"merged_rows": list(histories["TEST"][dimension].rows), "true_removed_keys": []}
            for dimension in ("ARQ", "MRQ")
        },
    }
    revalidated = {
        "state": {"mode": "BOOTSTRAP_BASELINE", "published_watermark": None},
        "schema": {"schema_fingerprint": "schema"},
        "discovery": {"observed_source_max_lastupdated": "2026-09-20"},
        "ticker_changes": [{
            "ticker": "TEST", "classification": "HISTORICAL_REVISION",
            "identity": {"company_id": 1, "security_id": 1, "provider_security_id": "100"},
        }],
        "histories": histories, "merge_plans": {"TEST": merge_plan},
        "refresh_set_fingerprint": fingerprint,
    }
    validation_calls: list[dict[str, object]] = []

    def raw_full_rebuild(target, _sources, **_kwargs):
        _database(target, "new")
        return {
            "status": "READY", "package": {"outcome": "APPLIED"},
            "validation": {"rp_snapshot_id": "rp-fixture"},
            "rv": {"outcome": "APPLIED"}, "fingerprints": {"package": "fixture"},
            "taxonomy_dependency": dependency,
        }

    def validate_analysis(path, **kwargs):
        validation_calls.append({"path": Path(path), **kwargs})
        assert kwargs["taxonomy_dependency"] == dependency
        return {"status": "VALIDATED", "taxonomy_dependency": dict(kwargs["taxonomy_dependency"])}

    monkeypatch.setattr(refresh_production, "revalidate_bound_source", lambda *_args, **_kwargs: revalidated)
    monkeypatch.setattr(refresh_production, "replace_provider_histories", refresh_copy_runtime.replace_provider_histories)
    monkeypatch.setattr(refresh_production, "validate_provider_candidate", refresh_copy_runtime.validate_provider_candidate)
    monkeypatch.setattr(refresh_production, "fresh_rebuild_canonical", refresh_copy_runtime.fresh_rebuild_canonical)
    monkeypatch.setattr(refresh_production, "_identity_mapping", refresh_copy_runtime._identity_mapping)
    monkeypatch.setattr(refresh_production, "_publish_refresh_state", _publish_refresh_state)
    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    monkeypatch.setattr(full_v2_downstream, "rebuild_v2_analysis", raw_full_rebuild)
    monkeypatch.setattr(refresh_production, "run_full_v2_downstream", full_v2_downstream.run_full_v2_downstream)
    monkeypatch.setattr(refresh_production, "_postflight", actual_postflight)
    monkeypatch.setattr(refresh_production, "validate_rebuild", validate_analysis)
    monkeypatch.setattr(refresh_production, "_provider_semantic_fingerprint", lambda *_args: "provider-semantic")

    result = run_production_apply(
        preview_payload_path=preview_path, preview_fingerprint=fingerprint, test_run_id=test_id,
        source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups", journal_path=tmp_path / "journal.json",
        confirm_production=True, rehearsal=True, lock_path=tmp_path / "admin.lock",
        scheduler_log_dir=str(tmp_path / "scheduler"), client=object(), as_of_date="2026-09-22",
    )
    assert result["outcome"] == "COMPLETED"
    assert result["analysis_candidate"]["active_taxonomy"] == dependency
    assert result["candidate_analysis_lineage"]["taxonomy_dependency"] == dependency
    assert result["postflight"]["cross_role_lineage"]["taxonomy_dependency"] == dependency
    assert result["provider_candidate"]["ticker_count"] == 1
    assert result["canonical_candidate"]["identity_contract"]["company_security_identity_mapping_unchanged"] is True
    assert [call["path"] for call in validation_calls] == [
        Path(result["analysis_candidate"]["candidate_analysis_db"]), paths.analysis_db,
    ]
    assert all(
        call["sources"]["market"].parent.name == "market_source_bundle"
        and call["sources"]["taxonomy"] == paths.taxonomy_db.resolve()
        for call in validation_calls
    )
    assert len(prepared_source_pairs) == 1
    assert validation_calls[0]["sources"]["market"] == prepared_source_pairs[0]["market"]
    assert validation_calls[0]["sources"]["taxonomy"] == prepared_source_pairs[0]["taxonomy"]
    assert validation_calls[1]["sources"]["market"] == prepared_source_pairs[0]["market"]
    assert validation_calls[1]["sources"]["taxonomy"] == prepared_source_pairs[0]["taxonomy"]
    assert result["journal"]["state"] == "COMPLETED"
    assert result["refresh_state"]["published_source_watermark"] == "2026-09-20"
    with sqlite3.connect(paths.provider_db) as connection:
        assert connection.execute(
            "SELECT revenue FROM sharadar_fundamental_observation WHERE dimension='ARQ'"
        ).fetchone()[0] == 120
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT revenue FROM v4_quarter_financials").fetchone()[0] == 120
    assert _generation(paths.analysis_db) == "new"


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
    replaced_count = {
        "AFTER_PROVIDER_REPLACEMENT": 1,
        "AFTER_CANONICAL_REPLACEMENT": 2,
        "AFTER_ANALYSIS_REPLACEMENT": 3,
        "POSTFLIGHT": 3,
    }[failure_point]
    assert result["publication_activity"]["live_replacements"] == list(PUBLICATION_ROLES[:replaced_count])
    assert result["publication_activity"]["rollback_restorations"] == list(PUBLICATION_ROLES)


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
        "test_run_id": "test-run",
        "production_source_binding": _source_binding(),
        "test_source_binding_comparison": {"status": "MATCH", "differing_contract_sections": []},
        "publication_activity": {
            "live_replacements": list(PUBLICATION_ROLES), "rollback_restorations": [],
        },
    })
    assert "Canonical published source-driven added/changed/removed: 1 / 2 / 3" in report
    assert "Provider published replacements: 1" in report
    assert "## Canonical Publication" in report
    assert "Published watermark after: 2026-09-20" in report
    assert "Live database replacements before completion/failure: 3 (provider, canonical, analysis)" in report
    assert "Rollback restorations: 0 (none)" in report
    assert "First-public bootstrap-only changes: 5" in report
    assert "first_public_result_date preservation map applied: 6/6" in report
    assert "first_public_result_date repair_required: 0" in report
    assert "MRQ overlay intentionally deferred for a later impact study." in report
    assert "Market mode: `STABLE_SOURCE_BUNDLE`" in report
    assert "Taxonomy mode: `DIRECT_LOCKED_READ`" in report
    assert "Test vs Production: `MATCH`" in report


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
        "publication_activity": {"live_replacements": [], "rollback_restorations": []},
    })
    assert "Production result: FAILED" in report
    assert "Publication boundary entered: NO" in report
    assert "Live database replacements before completion/failure: 0 (none)" in report
    assert "Rollback restorations: 0 (none)" in report
    assert "Net published generation changed: NO" in report
    assert "Provider candidate replacements: 1" in report
    assert "Provider published replacements: 0" in report
    assert "## Canonical Candidate Impact" in report
    assert "Published watermark after: NONE" in report
    assert "Candidate/proposed next watermark: 2026-09-20" in report
    assert "Full V2/RP/RV: NOT_RUN" in report
    assert "Candidate prepared; not published" in report
    assert "| Refreshed |" not in report


def test_required_taxonomy_dependency_uses_admin_wrapper_active_taxonomy() -> None:
    dependency = _required_taxonomy_dependency({
        "active_taxonomy": {
            "domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic",
        }
    })
    assert dependency == {
        "domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic",
    }


def test_postflight_accepts_full_v2_admin_active_taxonomy_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    for path in (analysis, market, taxonomy):
        _database(path, "new")
    with sqlite3.connect(provider) as connection:
        connection.execute(
            "CREATE TABLE sharadar_refresh_state("
            "singleton_id INTEGER,published_source_watermark TEXT,provider_semantic_fingerprint TEXT,"
            "source_schema_fingerprint TEXT,successful_run_id TEXT,completed_at_utc TEXT)"
        )
        connection.execute(
            "INSERT INTO sharadar_refresh_state VALUES(1,'2026-09-20','provider','schema','run','completed')"
        )
    with sqlite3.connect(canonical) as connection:
        connection.execute(
            "CREATE TABLE v4_quarter(company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,"
            "first_public_result_date TEXT)"
        )
        connection.execute("INSERT INTO v4_quarter VALUES(1,2026,'Q1','2026-05-01')")
    paths = BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)
    dependency = {"domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic"}
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.validate_provider_candidate",
        lambda *_args, **_kwargs: {"status": "VALID"},
    )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production._identity_mapping",
        lambda *_args: {"fingerprint": "identity"},
    )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.validate_rebuild",
        lambda *_args, **kwargs: {"taxonomy_dependency": kwargs["taxonomy_dependency"]},
    )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production._provider_semantic_fingerprint",
        lambda *_args: "provider",
    )
    expected = {
        role: {"candidate_fingerprint": sha256_file(paths.as_dict()[role])}
        for role in PUBLICATION_ROLES
    }
    result = _postflight(
        paths=paths, histories={}, merge_plans={},
        canonical_result={
            "identity_contract": {"after": {"fingerprint": "identity"}},
            "publication_date_bootstrap": {
                "repair_required": 0, "preservation_map_applied": 1,
                "preservation_map_applicable_existing_quarters": 1,
            },
        },
        analysis_result={"status": "READY", "active_taxonomy": dependency},
        expected_roles=expected,
        refresh_state={
            "published_source_watermark": "2026-09-20",
            "provider_semantic_fingerprint": "provider", "source_schema_fingerprint": "schema",
            "successful_run_id": "run", "completed_at_utc": "completed",
        },
        as_of_date="2026-09-20",
    )
    assert result["cross_role_lineage"]["taxonomy_dependency"] == dependency


def test_missing_taxonomy_dependency_fails_with_controlled_error() -> None:
    with pytest.raises(
        RefreshPostflightValidationError,
        match="REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISSING_OR_MALFORMED",
    ):
        _required_taxonomy_dependency({"status": "READY"})


def test_mismatched_taxonomy_dependency_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_production.validate_rebuild",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("V2_REBUILD_TAXONOMY_MISMATCH")),
    )
    with pytest.raises(
        RefreshPostflightValidationError,
        match="REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISMATCH",
    ):
        _validate_analysis_generation(
            tmp_path / "analysis.db",
            analysis_result={"active_taxonomy": {
                "domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "wrong",
            }},
            as_of_date="2026-09-20",
            sources={role: tmp_path / f"{role}.db" for role in ("provider", "canonical", "market", "taxonomy")},
        )


def test_rolled_back_report_shows_replacements_restorations_and_no_net_publication() -> None:
    report = render_report({
        "outcome": "FAILED_ROLLED_BACK", "write_boundary_crossed": True,
        "old_refresh_state": {"mode": "BOOTSTRAP_BASELINE", "published_watermark": None},
        "refresh_state": {"mode": "ESTABLISHED_PUBLISHED_STATE", "published_source_watermark": "2026-09-20"},
        "provider_candidate": {"ticker_count": 1}, "canonical_candidate": {},
        "publication_activity": {
            "live_replacements": ["provider", "canonical", "analysis"],
            "rollback_restorations": ["provider", "canonical", "analysis"],
        },
        "rollback": {"status": "ROLLED_BACK"},
    })
    assert "Publication boundary entered: YES" in report
    assert "Live database replacements before completion/failure: 3 (provider, canonical, analysis)" in report
    assert "Rollback restorations: 3 (provider, canonical, analysis)" in report
    assert "Net published generation changed: NO" in report
    assert "Published watermark after: NONE" in report
    assert "Production DB writes: 0" not in report
