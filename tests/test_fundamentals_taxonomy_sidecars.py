"""Checkpointed Snapshot taxonomy reads use SQLite's own writer exclusion."""

from contextlib import closing
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from rawcandle import datacenter_taxonomy_operation_log as locks
from rawcandle.fundamentals.admin import source_bundle as sources
from rawcandle.fundamentals.admin import universe_reconciliation as reconciliation
from rawcandle.fundamentals.generations import resolve_active_generation
from tests import test_fundamentals_admin_source_bundle as source_fixtures
from tests import test_fundamentals_universe_reconciliation as fix8


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def empty_wal(path):
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    # A real read-only SQLite open creates the exact incident state, even when
    # every connection is explicitly closed. No fabricated live-file cleanup.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("SELECT name FROM sqlite_schema LIMIT 1").fetchall()
    assert Path(str(path) + "-wal").stat().st_size == 0
    assert Path(str(path) + "-shm").stat().st_size == 32768


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.setattr(locks, "DEFAULT_TAXONOMY_OPERATION_ROOT", tmp_path / "temp/taxonomy")
    return (
        source_fixtures._canonical(tmp_path / "canonical.db"),
        source_fixtures._taxonomy(tmp_path / "taxonomy.db", journal_mode="DELETE"),
    )


def protected(native, **kwargs):
    canonical, taxonomy = native
    return sources.protected_direct_taxonomy_source(
        taxonomy, canonical, operation_id="fix8a", require_checkpointed=True, **kwargs
    )


@pytest.mark.parametrize("mode", ["DELETE", "WAL", "EMPTY_WAL", "CHECKPOINT"])
def test_safe_native_sqlite_lifecycle_preserves_main_and_binding(native, mode):
    canonical, taxonomy = native
    keeper = None
    if mode != "DELETE":
        empty_wal(taxonomy)
        if mode == "WAL":
            # Normal last rw close leaves WAL-mode main and no sidecars.
            with closing(sqlite3.connect(taxonomy)) as db:
                db.execute("SELECT name FROM sqlite_schema LIMIT 1").fetchall()
        elif mode == "CHECKPOINT":
            keeper = sqlite3.connect(taxonomy)
            keeper.execute("UPDATE ec_taxonomy_version SET source_hash='checkpointed'")
            keeper.commit()
            assert keeper.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
            assert Path(str(taxonomy) + "-wal").stat().st_size == 0
    before = digest(taxonomy), sources._file_identity(taxonomy)
    try:
        with protected(native) as binding:
            _, dependency = sources.load_active_dc_memberships(taxonomy, canonical)
            assert binding.semantic_fingerprint == dependency["semantic_fingerprint"]
            assert binding.version == "DC_V1"
            assert locks.current_taxonomy_operation_lock().operation_id == "fix8a"
        assert (digest(taxonomy), sources._file_identity(taxonomy)) == before
        assert not locks.authoritative_taxonomy_lock_path().exists()
    finally:
        if keeper:
            keeper.close()


def test_valid_committed_wal_is_not_ignored_or_called_corrupt(native):
    _, taxonomy = native
    empty_wal(taxonomy)
    before = digest(taxonomy)
    with closing(sqlite3.connect(taxonomy)) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_IN_WAL'")
        writer.commit()
        assert Path(str(taxonomy) + "-wal").stat().st_size > 0
        assert digest(taxonomy) == before
        with closing(sqlite3.connect(taxonomy.as_uri() + "?mode=ro", uri=True)) as reader:
            assert reader.execute("SELECT taxonomy_version_code FROM ec_taxonomy_version").fetchone()[0] == "DC_IN_WAL"
        wal_before = digest(Path(str(taxonomy) + "-wal"))
        with pytest.raises(sources.SourceBundleError, match="NONEMPTY_WAL"):
            with protected(native):
                pytest.fail("main-file-only binding admitted uncheckpointed state")
        assert digest(Path(str(taxonomy) + "-wal")) == wal_before


def test_active_reader_is_compatible_and_sqlite_writer_excluded_for_lifetime(native):
    _, taxonomy = native
    empty_wal(taxonomy)
    with closing(sqlite3.connect(taxonomy.as_uri() + "?mode=ro", uri=True)) as reader:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM ec_taxonomy_version").fetchall()
        with protected(native) as binding:
            assert binding.runtime_authorized
            with closing(sqlite3.connect(taxonomy, timeout=0)) as writer:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    writer.execute("BEGIN IMMEDIATE")
            with pytest.raises(RuntimeError, match="taxonomy operation lock is active"):
                with locks.taxonomy_operation_lock_context(deployment_id="writer", operation_type="WRITE"):
                    pytest.fail("native writer entered")
        # The SQLite reservation has been released; the existing reader remains.
        with closing(sqlite3.connect(taxonomy, timeout=0)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.rollback()


@pytest.mark.parametrize("pending_change", [False, True])
@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
def test_active_sqlite_writer_or_pending_transaction_blocks_without_wait(native, pending_change, mode):
    _, taxonomy = native
    if mode == "WAL":
        empty_wal(taxonomy)
    before = digest(taxonomy)
    with closing(sqlite3.connect(taxonomy)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        if pending_change:
            writer.execute("UPDATE ec_taxonomy_version SET source_hash='not committed'")
        with pytest.raises(sources.SourceBundleError, match="RESERVATION_FAILED.*locked|ROLLBACK_JOURNAL_PRESENT"):
            with protected(native):
                pytest.fail("active writer admitted")
        writer.rollback()
    assert digest(taxonomy) == before
    assert not locks.authoritative_taxonomy_lock_path().exists()


@pytest.mark.parametrize("bad", ["corrupt_wal", "shm_size", "orphan_shm", "orphan_wal", "symlink", "rollback"])
def test_unsafe_or_ambiguous_sidecar_blocks_before_sqlite_cleanup(native, bad):
    _, taxonomy = native
    empty_wal(taxonomy)
    wal = Path(str(taxonomy) + "-wal")
    shm = Path(str(taxonomy) + "-shm")
    if bad == "corrupt_wal":
        wal.write_bytes(b"invalid WAL fixture")
    elif bad == "shm_size":
        shm.write_bytes(b"x")
    elif bad == "orphan_shm":
        wal.unlink()
    elif bad == "orphan_wal":
        shm.unlink()
    elif bad == "symlink":
        wal.unlink()
        wal.symlink_to(taxonomy)
    else:
        Path(str(taxonomy) + "-journal").write_bytes(b"pending rollback fixture")
    before = {str(p): (digest(p), p.lstat().st_ino) for p in (taxonomy, wal, shm, Path(str(taxonomy) + "-journal")) if p.exists()}
    with pytest.raises(sources.SourceBundleError, match="TAXONOMY_SQLITE_"):
        with protected(native):
            pytest.fail("unsafe sidecar admitted")
    assert before == {p: (digest(Path(p)), Path(p).lstat().st_ino) for p in before}


def test_inconsistent_sidecar_owner_blocks(native, monkeypatch):
    _, taxonomy = native
    empty_wal(taxonomy)
    wal = Path(str(taxonomy) + "-wal")
    original = Path.stat

    def wrong_owner(path, *a, **kw):
        result = original(path, *a, **kw)
        if path == wal:
            values = list(result)
            values[4] += 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "stat", wrong_owner)
    with pytest.raises(sources.SourceBundleError, match="SIDECAR_IDENTITY"):
        with protected(native):
            pytest.fail("foreign owner admitted")


def test_replacement_after_binding_is_dependency_drift(native):
    _, taxonomy = native
    replacement = taxonomy.with_name("replacement.db")
    shutil.copyfile(taxonomy, replacement)
    with pytest.raises(sources.SourceBundleError, match="SOURCE_DRIFT"):
        with protected(native):
            replacement.replace(taxonomy)
    assert not locks.authoritative_taxonomy_lock_path().exists()


def test_change_between_inspection_and_sqlite_acquisition_is_rejected(native, monkeypatch):
    _, taxonomy = native
    original = sqlite3.connect
    changed = False

    def connect(*a, **kw):
        nonlocal changed
        if not changed and "mode=ro" in str(a[0]):
            changed = True
            now = taxonomy.stat()
            os.utime(taxonomy, ns=(now.st_atime_ns, now.st_mtime_ns + 1))
        return original(*a, **kw)

    monkeypatch.setattr(sources.sqlite3, "connect", connect)
    with pytest.raises(sources.SourceBundleError, match="SOURCE_DRIFT"):
        with protected(native):
            pytest.fail("changed dependency admitted")


def test_current_binding_allows_completed_changes_between_protected_uses(native):
    _, taxonomy = native
    with protected(native) as first:
        assert first.version == "DC_V1"
    with closing(sqlite3.connect(taxonomy)) as db:
        db.execute("UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_CURRENT'")
        db.commit()
    with protected(native) as current:
        assert current.version == "DC_CURRENT"


def test_guard_executes_no_data_writes_or_checkpoint_and_cleans_up_after_exception(native, monkeypatch):
    _, taxonomy = native
    empty_wal(taxonomy)
    before = digest(taxonomy), sources._file_identity(taxonomy)
    original = sqlite3.connect
    statements = []

    def connect(*a, **kw):
        db = original(*a, **kw)
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr(sources.sqlite3, "connect", connect)
    with pytest.raises(RuntimeError, match="consumer failed"):
        with protected(native):
            raise RuntimeError("consumer failed")
    assert (digest(taxonomy), sources._file_identity(taxonomy)) == before
    assert not locks.authoritative_taxonomy_lock_path().exists()
    sql = [s.strip().upper() for s in statements]
    assert "BEGIN" in sql and "PRAGMA QUERY_ONLY=ON" in sql
    assert "BEGIN IMMEDIATE" in sql
    assert not any(s.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "VACUUM")) or "WAL_CHECKPOINT" in s or s.startswith("PRAGMA JOURNAL_MODE=") for s in sql)


@pytest.mark.parametrize("boundary", [None, "AFTER_PREPARE", "AFTER_ACTIVATION"])
def test_fix8_safe_empty_wal_publication_and_rollback(tmp_path, monkeypatch, boundary):
    workflow, decisions, args = fix8.setup(tmp_path, monkeypatch)
    env = workflow.env
    taxonomy = env.paths().taxonomy_db
    empty_wal(taxonomy)
    before = digest(taxonomy), sources._file_identity(taxonomy)
    financial = fix8.financial_hashes(env)
    result = reconciliation.run_reconciliation(env, decisions, **args, stop_after="publish", inject_failure=boundary)
    assert result["outcome"] == ("ROLLED_BACK" if boundary else "COMPLETED"), result
    assert (digest(taxonomy), sources._file_identity(taxonomy)) == before
    assert (resolve_active_generation(env.project).generation_id == "old") == bool(boundary)
    if boundary:
        assert fix8.financial_hashes(env) == financial
    else:
        assert result["postflight"] == "PASSED"
    assert not locks.authoritative_taxonomy_lock_path().exists()


def test_fix8_unsafe_wal_stops_before_candidate(tmp_path, monkeypatch):
    workflow, decisions, args = fix8.setup(tmp_path, monkeypatch)
    env = workflow.env
    taxonomy = env.paths().taxonomy_db
    empty_wal(taxonomy)
    Path(str(taxonomy) + "-wal").write_bytes(b"unsafe fixture")
    before = fix8.financial_hashes(env)
    result = reconciliation.run_reconciliation(env, decisions, **args, stop_after="publish")
    assert result["outcome"] == "BLOCKED" and result["failed_stage"] == "NATIVE_PREFLIGHT", result
    assert "NONEMPTY_WAL" in result["error"]
    assert "candidate_roles" not in result and fix8.financial_hashes(env) == before
    assert resolve_active_generation(env.project).generation_id == "old"


@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
def test_writer_in_another_process_cannot_enter_protected_source(native, mode):
    _, taxonomy = native
    if mode == "WAL":
        empty_wal(taxonomy)
    script = """
import sqlite3, sys
c=sqlite3.connect(sys.argv[1],timeout=0)
try:
    c.execute('BEGIN IMMEDIATE')
    print('ACQUIRED')
except sqlite3.OperationalError:
    print('BLOCKED')
finally:
    c.rollback(); c.close()
"""
    with protected(native):
        # Closing another reader must retain SQLite's managed reservation.
        with closing(sqlite3.connect(taxonomy.as_uri() + "?mode=ro", uri=True)) as reader:
            reader.execute("SELECT * FROM ec_taxonomy_version").fetchall()
        child = subprocess.run([sys.executable, "-c", script, str(taxonomy)], capture_output=True, text=True, check=True)
        assert child.stdout.strip() == "BLOCKED", child
    child = subprocess.run([sys.executable, "-c", script, str(taxonomy)], capture_output=True, text=True, check=True)
    assert child.stdout.strip() == "ACQUIRED", child


def test_checkpoint_conflicts_and_reader_still_works(native):
    _, taxonomy = native
    empty_wal(taxonomy)
    with protected(native):
        with closing(sqlite3.connect(taxonomy, timeout=0)) as other:
            assert other.execute("SELECT COUNT(*) FROM ec_taxonomy_version").fetchone()[0] == 1
            assert other.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 1



def test_wal_commit_racing_acquisition_is_retained_without_implicit_checkpoint(native, monkeypatch):
    _, taxonomy = native
    empty_wal(taxonomy)
    before = digest(taxonomy), sources._file_identity(taxonomy)
    original = sqlite3.connect
    captured = {}

    def connect(*a, **kw):
        if "mode=rw" in str(a[0]) and not captured:
            with closing(original(taxonomy)) as writer:
                writer.execute("UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_RACED'")
                writer.commit()
            captured["wal"] = digest(Path(str(taxonomy) + "-wal"))
        return original(*a, **kw)

    monkeypatch.setattr(sources.sqlite3, "connect", connect)
    with pytest.raises(sources.SourceBundleError, match="NONEMPTY_WAL"):
        with protected(native):
            pytest.fail("racing WAL accepted")
    assert (digest(taxonomy), sources._file_identity(taxonomy)) == before
    assert digest(Path(str(taxonomy) + "-wal")) == captured["wal"]
    with closing(original(taxonomy.as_uri() + "?mode=ro", uri=True)) as reader:
        assert reader.execute("SELECT taxonomy_version_code FROM ec_taxonomy_version").fetchone()[0] == "DC_RACED"


def test_sqlite_busy_acquisition_does_not_discard_existing_writer_lock(native):
    _, taxonomy = native
    empty_wal(taxonomy)
    with closing(sqlite3.connect(taxonomy)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(sources.SourceBundleError, match="RESERVATION_FAILED"):
            with protected(native):
                pytest.fail("active writer admitted")
        script = """
import sqlite3,sys
c=sqlite3.connect(sys.argv[1],timeout=0)
try:
    c.execute('BEGIN IMMEDIATE')
    print('ACQUIRED')
except sqlite3.OperationalError:
    print('BLOCKED')
finally:
    c.rollback();c.close()
"""
        child = subprocess.run([sys.executable, "-c", script, str(taxonomy)], capture_output=True, text=True, check=True)
        assert child.stdout.strip() == "BLOCKED"
        writer.rollback()
