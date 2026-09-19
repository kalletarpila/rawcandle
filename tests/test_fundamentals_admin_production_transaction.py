import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import production_transaction as tx
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import AdminOperationType


IDENTITY = {"domain": "dc_ecosystem", "version": "v2", "semantic_fingerprint": "semantic"}


def _value(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT value FROM state").fetchone()[0]


def _set(path: Path, value: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE state SET value=?", (value,))
        conn.commit()


def _fixture(tmp_path: Path, monkeypatch, *, operation=AdminOperationType.CHECK_UPDATE_TAXONOMY, roles=("analysis",), source_mutation=False):
    source = tmp_path / "sources"
    source.mkdir()
    paths = BatchAddTickerPaths(*(source / f"{role}.db" for role in ("provider", "canonical", "analysis", "market", "taxonomy")))
    for path in paths.as_dict().values():
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE state(value TEXT NOT NULL)")
            conn.execute("INSERT INTO state VALUES('old')")
            conn.commit()
    run_root = tmp_path / "runs"
    test_id = "test_copy_run"
    (run_root / test_id).mkdir(parents=True)
    (run_root / test_id / "result.json").write_text(json.dumps({
        "operation_type": operation.value, "mode": "COPY_ONLY_APPLY", "outcome": "COMPLETED",
        "preview_fingerprint": "preview-fp", "downstream": {"invocation_counts": {"full_v2_rebuild": 1}, "active_taxonomy": IDENTITY},
    }))
    payload = tmp_path / "preview.json"
    payload.write_text("{}")

    def validate(paths_arg, saved, expected):
        assert expected == "preview-fp"
        assert _value(paths_arg.taxonomy_db) == "old"
        return {"as_of_date": "2026-09-18", "taxonomy_dependency": IDENTITY, "no_change": False}

    def mutate(paths_arg, preview):
        if source_mutation:
            _set(paths_arg.provider_db, "new")
            _set(paths_arg.canonical_db, "new")
        return {"outcome": "APPLIED" if source_mutation else "NOT_REQUIRED"}

    op = tx.ProductionOperation(operation, roles, validate, mutate)

    def rebuild(target, sources, *, as_of_date, output, inject_failure_at=None):
        assert not target.exists()
        with sqlite3.connect(target) as conn:
            conn.execute("CREATE TABLE state(value TEXT NOT NULL)")
            conn.execute("INSERT INTO state VALUES('new')")
            conn.commit()
        return {"status": "READY", "target": str(target), "package": {"rows": 1}, "rv": {"rows": 1}, "validation": {"ok": True}, "taxonomy_dependency": IDENTITY}

    monkeypatch.setattr(tx, "rebuild_v2_analysis", rebuild)
    monkeypatch.setattr(tx, "validate_rebuild", lambda target, **kwargs: {"state": _value(target)})
    monkeypatch.setattr(tx, "database_inventory", lambda path: {"quick_check": "ok"})
    monkeypatch.setattr(tx, "_source_fingerprints", lambda current: {role: tx._sha256(current.as_dict()[role]) for role in ("provider", "canonical", "market", "taxonomy")})
    kwargs = dict(preview_payload_path=payload, preview_fingerprint="preview-fp", test_run_id=test_id,
                  source_paths=paths, run_root=run_root, backup_root=tmp_path / "backups",
                  scheduler_log_dir=str(tmp_path / "scheduler"), lock_path=tmp_path / "admin.lock",
                  rehearsal=True)
    return op, paths, kwargs


def test_atomic_rehearsal_reopens_replaced_analysis_and_only_backs_up_write_set(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "COMPLETED"
    assert _value(paths.analysis_db) == "new"
    assert result["postflight"]["state"] == "new"
    assert set(result["backups"]) == {"analysis"}
    assert result["atomic_replacement"]["same_filesystem"] is True
    report = Path(result["artifact_dir"], "operation_report.md").read_text()
    assert "Verified backups" in report and "Atomic replacement" in report


def test_exact_production_mode_selects_explicit_production_validator(tmp_path, monkeypatch):
    paths = _fixture(tmp_path, monkeypatch)[1]
    run_root = tmp_path / "production-runs"
    lock_path = tmp_path / "production.lock"
    payload = tmp_path / "production-preview.json"
    payload.write_text("{}", encoding="utf-8")
    for role, path in paths.as_dict().items():
        monkeypatch.setitem(tx.PRODUCTION, role, path)
    monkeypatch.setattr(tx, "ADMIN_RUN_ROOT", run_root)
    monkeypatch.setattr(tx, "ADMIN_LOCK", lock_path)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.batch_add_tickers._assert_clean_worktree",
        lambda: {"status": "CLEAN"},
    )
    calls = []

    def copy_validator(*args):
        raise AssertionError("copy validator must not validate an actual production transaction")

    def production_validator(*args):
        calls.append("production")
        return {"as_of_date": "2026-09-19", "taxonomy_dependency": IDENTITY, "no_change": True}

    operation = tx.ProductionOperation(
        AdminOperationType.ADD_TICKERS,
        ("provider", "canonical", "analysis"),
        copy_validator,
        lambda *args: {"outcome": "NOT_REQUIRED"},
        production_validate_preview=production_validator,
    )

    result = tx.run_transaction(
        operation,
        preview_payload_path=payload,
        preview_fingerprint="preview-fp",
        test_run_id="fresh-test",
        source_paths=paths,
        run_root=run_root,
        lock_path=lock_path,
        production_intent=True,
    )

    assert result["outcome"] == "NO_CHANGE"
    assert calls == ["production"]


def test_production_mode_rejects_arbitrary_path_before_validator(tmp_path, monkeypatch):
    paths = _fixture(tmp_path, monkeypatch)[1]
    for role, path in paths.as_dict().items():
        monkeypatch.setitem(tx.PRODUCTION, role, path)
    arbitrary = tmp_path / "arbitrary-provider.db"
    sqlite3.connect(arbitrary).close()
    unsafe = BatchAddTickerPaths(
        arbitrary, paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db,
    )
    operation = tx.ProductionOperation(
        AdminOperationType.ADD_TICKERS,
        ("provider", "canonical", "analysis"),
        lambda *args: {},
        lambda *args: {},
        production_validate_preview=lambda *args: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    with pytest.raises(PermissionError, match="EXACT_PRODUCTION_PATHS_REQUIRED"):
        tx.run_transaction(
            operation,
            preview_payload_path=tmp_path / "missing.json",
            preview_fingerprint="preview-fp",
            test_run_id="fresh-test",
            source_paths=unsafe,
            production_intent=True,
        )


def test_post_replacement_failure_restores_analysis_and_add_sources(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch, operation=AdminOperationType.ADD_TICKERS,
                                 roles=("provider", "canonical", "analysis"), source_mutation=True)
    result = tx.run_transaction(op, inject_failure_at="post_replacement", **kwargs)
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert result["rollback"]["status"] == "ROLLED_BACK"
    assert all(_value(paths.as_dict()[role]) == "old" for role in ("provider", "canonical", "analysis"))
    assert all(
        tx._sha256(paths.as_dict()[role]) == result["backups"][role]["verification"]["sha256"]
        for role in ("provider", "canonical", "analysis")
    )
    assert set(result["backups"]) == {"provider", "canonical", "analysis"}


def test_rebuild_failure_restores_add_sources_and_old_analysis(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch, operation=AdminOperationType.ADD_TICKERS,
                                 roles=("provider", "canonical", "analysis"), source_mutation=True)
    monkeypatch.setattr(tx, "rebuild_v2_analysis", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rebuild failed")))
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert all(_value(paths.as_dict()[role]) == "old" for role in ("provider", "canonical", "analysis"))
    with tx.production_lock(lock_path=kwargs["lock_path"], scheduler_log_dir=kwargs["scheduler_log_dir"]):
        pass


def test_invalid_backup_blocks_source_mutation(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch, operation=AdminOperationType.ADD_TICKERS,
                                 roles=("provider", "canonical", "analysis"), source_mutation=True)
    monkeypatch.setattr(tx, "_check_sqlite", lambda path: (_ for _ in ()).throw(RuntimeError("INVALID_BACKUP")))
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "BACKUP"
    assert all(_value(paths.as_dict()[role]) == "old" for role in ("provider", "canonical", "analysis"))


def test_candidate_validation_failure_restores_add_sources(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch, operation=AdminOperationType.ADD_TICKERS,
                                 roles=("provider", "canonical", "analysis"), source_mutation=True)
    rebuild = tx.rebuild_v2_analysis

    def not_ready(*args, **options):
        result = rebuild(*args, **options)
        result["status"] = "FAILED_VALIDATION"
        return result

    monkeypatch.setattr(tx, "rebuild_v2_analysis", not_ready)
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert all(_value(paths.as_dict()[role]) == "old" for role in ("provider", "canonical", "analysis"))


def test_source_change_during_rebuild_rejects_candidate_and_restores_add_sources(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch, operation=AdminOperationType.ADD_TICKERS,
                                 roles=("provider", "canonical", "analysis"), source_mutation=True)
    rebuild = tx.rebuild_v2_analysis

    def change_read_only_market(*args, **options):
        result = rebuild(*args, **options)
        _set(paths.market_db, "external_change")
        return result

    monkeypatch.setattr(tx, "rebuild_v2_analysis", change_read_only_market)
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert result["failed_stage"] == "SOURCE_RECHECK"
    assert all(_value(paths.as_dict()[role]) == "old" for role in ("provider", "canonical", "analysis"))


def test_analysis_change_during_rebuild_rejects_candidate_without_overwriting_it(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tx, "_source_fingerprints", lambda current: {
        role: tx._sha256(current.as_dict()[role]) for role in ("provider", "canonical", "market", "taxonomy", "analysis")
    })
    rebuild = tx.rebuild_v2_analysis

    def change_analysis(*args, **options):
        result = rebuild(*args, **options)
        _set(paths.analysis_db, "external_change")
        return result

    monkeypatch.setattr(tx, "rebuild_v2_analysis", change_analysis)
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "SOURCE_RECHECK"
    assert _value(paths.analysis_db) == "external_change"


@pytest.mark.parametrize("reason", ["V2_REBUILD_RV_SOURCE_OR_RESULT_MISMATCH", "V2_REBUILD_TAXONOMY_MISMATCH", "V2_REBUILD_QUICK_CHECK_FAILED"])
def test_postflight_validation_failure_restores_old_analysis(tmp_path, monkeypatch, reason):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tx, "validate_rebuild", lambda *args, **options: (_ for _ in ()).throw(RuntimeError(reason)))
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED_ROLLED_BACK"
    assert reason in result["error"]
    assert _value(paths.analysis_db) == "old"


def test_taxonomy_changes_during_rebuild_reject_candidate_before_replacement(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    rebuild = tx.rebuild_v2_analysis

    def mutate_taxonomy(target, sources, **options):
        result = rebuild(target, sources, **options)
        _set(paths.taxonomy_db, "external_change")
        return result

    monkeypatch.setattr(tx, "rebuild_v2_analysis", mutate_taxonomy)
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "SOURCE_RECHECK"
    assert _value(paths.analysis_db) == "old"


def test_missing_matching_copy_test_rejects_before_backup(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    kwargs["test_run_id"] = "missing"
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED"
    assert not (tmp_path / "backups").exists()
    assert _value(paths.analysis_db) == "old"


def test_no_change_skips_test_backup_lock_and_rebuild(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    op = tx.ProductionOperation(op.operation_type, op.written_roles,
                                lambda *args: {"as_of_date": "2026-09-18", "no_change": True}, op.mutate_sources)
    kwargs["test_run_id"] = "missing"
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "NO_CHANGE"
    assert result["backups"] == {}
    assert _value(paths.analysis_db) == "old"
    assert not (tmp_path / "backups").exists()


def test_same_preview_invocations_have_distinct_artifact_and_candidate_paths(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    op = tx.ProductionOperation(op.operation_type, op.written_roles,
                                lambda *args: {"as_of_date": "2026-09-18", "no_change": True}, op.mutate_sources)
    first = tx.run_transaction(op, **kwargs)
    second = tx.run_transaction(op, **kwargs)
    assert first["outcome"] == second["outcome"] == "NO_CHANGE"
    assert first["run_id"] != second["run_id"]
    assert Path(first["artifact_dir"], "result.json").exists()
    assert Path(second["artifact_dir"], "result.json").exists()


def test_stale_preview_fails_before_backup(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)
    op = tx.ProductionOperation(op.operation_type, op.written_roles,
                                lambda *args: (_ for _ in ()).throw(ValueError("STALE_PREVIEW")), op.mutate_sources)
    result = tx.run_transaction(op, **kwargs)
    assert result["outcome"] == "FAILED"
    assert "STALE_PREVIEW" in result["error"]
    assert not (tmp_path / "backups").exists()
    assert result["retry_authorization"]["direct_production_retry_available"] is False
    assert result["retry_authorization"]["preview_test_rerun_required"] is True


def test_retryable_prewrite_lock_failure_preserves_test_and_allows_direct_retry(tmp_path, monkeypatch):
    op, paths, kwargs = _fixture(tmp_path, monkeypatch)

    with tx.production_lock(lock_path=kwargs["lock_path"], scheduler_log_dir=kwargs["scheduler_log_dir"]):
        failed = tx.run_transaction(op, **kwargs)

    assert failed["outcome"] == "FAILED"
    assert failed["write_boundary_crossed"] is False
    assert failed["retry_authorization"] == {
        "direct_production_retry_available": True,
        "preview_test_preserved": True,
        "preview_test_rerun_required": False,
        "reason": "RETRYABLE_PREWRITE_FAILURE",
    }
    assert "Another Administration operation" in failed["user_failure_reason"]
    assert _value(paths.analysis_db) == "old"

    retried = tx.run_transaction(op, **kwargs)

    assert retried["outcome"] == "COMPLETED"
    assert _value(paths.analysis_db) == "new"


def test_dirty_git_is_recorded_as_warning_and_does_not_block_production(tmp_path, monkeypatch):
    paths = _fixture(tmp_path, monkeypatch)[1]
    run_root = tmp_path / "production-runs"
    lock_path = tmp_path / "production.lock"
    payload = tmp_path / "production-preview.json"
    payload.write_text("{}", encoding="utf-8")
    for role, path in paths.as_dict().items():
        monkeypatch.setitem(tx.PRODUCTION, role, path)
    monkeypatch.setattr(tx, "ADMIN_RUN_ROOT", run_root)
    monkeypatch.setattr(tx, "ADMIN_LOCK", lock_path)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.batch_add_tickers._assert_clean_worktree",
        lambda: {"head": "abc123", "dirty": True, "status_clean": False, "changed_tracked_paths": ["module.py"]},
    )
    operation = tx.ProductionOperation(
        AdminOperationType.ADD_TICKERS,
        ("provider", "canonical", "analysis"),
        lambda *args: {},
        lambda *args: {"outcome": "NOT_REQUIRED"},
        production_validate_preview=lambda *args: {
            "as_of_date": "2026-09-19", "taxonomy_dependency": IDENTITY, "no_change": True,
        },
    )

    result = tx.run_transaction(
        operation,
        preview_payload_path=payload,
        preview_fingerprint="preview-fp",
        test_run_id="unused-for-no-change",
        source_paths=paths,
        run_root=run_root,
        lock_path=lock_path,
        production_intent=True,
    )

    assert result["outcome"] == "NO_CHANGE"
    assert result["git_state"]["dirty"] is True
    assert result["warnings"] == [{
        "code": "DIRTY_GIT_WORKTREE",
        "message": "Git worktree contains uncommitted changes.",
    }]
    assert "CLEAN_GIT_WORKTREE_REQUIRED" not in json.dumps(result)


def test_lock_excludes_second_admin_and_scheduler_then_releases(tmp_path):
    lock_path = tmp_path / "admin.lock"
    log_dir = str(tmp_path / "scheduler")
    with tx.production_lock(lock_path=lock_path, scheduler_log_dir=log_dir):
        with pytest.raises(RuntimeError, match="ALREADY_RUNNING"):
            with tx.production_lock(lock_path=lock_path, scheduler_log_dir=log_dir):
                pass
        from rawcandle.scheduler.runner import SchedulerAlreadyRunningError, acquire_scheduler_lock
        with pytest.raises(SchedulerAlreadyRunningError):
            acquire_scheduler_lock(log_dir)
    with tx.production_lock(lock_path=lock_path, scheduler_log_dir=log_dir):
        assert json.loads(lock_path.read_text())["pid"] > 0


def test_running_scheduler_blocks_admin_and_releases_admin_lock(tmp_path):
    from rawcandle.scheduler.runner import SchedulerAlreadyRunningError, acquire_scheduler_lock, release_scheduler_lock

    lock_path = tmp_path / "admin.lock"
    log_dir = str(tmp_path / "scheduler")
    scheduler_handle = acquire_scheduler_lock(log_dir)
    try:
        with pytest.raises(SchedulerAlreadyRunningError):
            with tx.production_lock(lock_path=lock_path, scheduler_log_dir=log_dir):
                pass
    finally:
        release_scheduler_lock(scheduler_handle)
    with tx.production_lock(lock_path=lock_path, scheduler_log_dir=log_dir):
        pass


def test_abandoned_lock_text_does_not_block_kernel_lock(tmp_path):
    lock_path = tmp_path / "admin.lock"
    lock_path.write_text('{"pid": 999999, "started_at_utc": "old"}\n')
    with tx.production_lock(lock_path=lock_path, scheduler_log_dir=str(tmp_path / "scheduler")) as owner:
        assert owner["pid"] != 999999
        assert json.loads(lock_path.read_text())["pid"] == owner["pid"]


def test_publication_rejects_unvalidated_candidate(tmp_path):
    target = tmp_path / "target.db"
    candidate = tmp_path / "candidate.db"
    for path in (target, candidate):
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE state(value TEXT)")
    with pytest.raises(RuntimeError, match="READY_MARKER"):
        tx._publish_candidate(candidate=candidate, target=target, rebuild={}, backup={},
                              lock_owner={"pid": 1}, bound_test={"outcome": "COMPLETED"}, source_stable=True,
                              production_intent=False, rehearsal=True)


def test_publication_rejects_candidate_target_identity(tmp_path):
    target = tmp_path / "analysis.db"
    with sqlite3.connect(target) as conn:
        conn.execute("CREATE TABLE state(value TEXT)")
    with pytest.raises(ValueError, match="PATH_UNSAFE"):
        tx._publish_candidate(candidate=target, target=target,
                              rebuild={"status": "READY", "target": str(target)}, backup={"backup": str(target)},
                              lock_owner={"pid": 1}, bound_test={"outcome": "COMPLETED"}, source_stable=True,
                              production_intent=False, rehearsal=True)


def test_publication_rejects_production_target_without_intent(tmp_path):
    with pytest.raises(PermissionError, match="EXPLICIT_PRODUCTION_INTENT"):
        tx._publish_candidate(candidate=tmp_path / "candidate.db", target=tx.PRODUCTION["analysis"],
                              rebuild={}, backup={}, lock_owner={}, bound_test={}, source_stable=False,
                              production_intent=False, rehearsal=True)
