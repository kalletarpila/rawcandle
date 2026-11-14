"""Owned-copy taxonomy closure and the unchanged native publication boundary."""
from contextlib import closing
import os
import sqlite3

import pytest

from rawcandle import datacenter_taxonomy_operation_log as locks
from rawcandle.fundamentals.admin import source_bundle as sources
from rawcandle.fundamentals.admin import taxonomy as tax
from rawcandle.fundamentals.admin import universe_reconciliation as reconciliation
from rawcandle.fundamentals.operating_income_v2 import peer_source_context as peers
from rawcandle.fundamentals.snapshot.v2_scaffold import _taxonomy_memberships
from rawcandle.fundamentals.generations import resolve_active_generation
from tests import test_fundamentals_admin_source_bundle as fixtures
from tests import test_fundamentals_taxonomy_sidecars as sidecars
from tests import test_fundamentals_universe_reconciliation as native


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(locks, "DEFAULT_TAXONOMY_OPERATION_ROOT", tmp_path / "locks")
    canonical = fixtures._canonical(tmp_path / "canonical.db")
    taxonomy = fixtures._taxonomy(tmp_path / "taxonomy.db", journal_mode="DELETE")
    with closing(sqlite3.connect(taxonomy)) as db, db:
        db.executescript("""
            CREATE TABLE unrelated_research(payload BLOB);
            INSERT INTO unrelated_research VALUES(zeroblob(1048576));
            CREATE TABLE ec_entity_alias(entity_alias_id INTEGER PRIMARY KEY,
                ecosystem_id INTEGER,entity_id INTEGER,alias_type TEXT,
                alias_value TEXT,status TEXT);
            INSERT INTO ec_entity_alias VALUES(1,1,120,'TICKER','OLD_AAA','ACTIVE');
            CREATE INDEX alias_lookup ON ec_entity_alias(alias_value);
            INSERT INTO ec_taxonomy_version VALUES(
                9,1,'DC_OLD','Old','fixture','old','INACTIVE',0,'2025-01-01',NULL);
            INSERT INTO ec_ecosystem VALUES(2,'OTHER','Other','ACTIVE');
            INSERT INTO ec_taxonomy_version VALUES(
                20,2,'OTHER_V1','Other','fixture','other','ACTIVE',1,'2025-01-01',NULL);
            PRAGMA user_version=7;
        """)
    return canonical, taxonomy, tmp_path / "compact.db"


def extract(inputs):
    canonical, taxonomy, destination = inputs
    return sources.prepare_disposable_taxonomy_source(
        taxonomy_db=taxonomy, canonical_db=canonical, destination=destination,
        operation_id="compact-test",
    )


@pytest.mark.parametrize("empty_wal", [False, True])
def test_complete_reader_parity_and_exclusion(inputs, empty_wal):
    canonical, taxonomy, destination = inputs
    if empty_wal:
        sidecars.empty_wal(taxonomy)
    before = sidecars.digest(taxonomy), sources._file_identity(taxonomy)
    evidence = extract(inputs)
    assert evidence["compact_bytes"] < evidence["source_bytes"] / 10
    assert before == (sidecars.digest(taxonomy), sources._file_identity(taxonomy))
    with sources._readonly(taxonomy) as original, sources._readonly(destination) as compact:
        assert {r[0] for r in compact.execute("SELECT name FROM sqlite_schema WHERE type='table'")} == set(sources.TAXONOMY_COPY_TABLES)
        assert compact.execute("PRAGMA user_version").fetchone()[0] == 7
        assert compact.execute("SELECT name FROM sqlite_schema WHERE name='alias_lookup'").fetchone()
        for table in sources.TAXONOMY_COPY_TABLES:
            assert list(map(tuple, original.execute(f'SELECT * FROM "{table}"'))) == list(map(tuple, compact.execute(f'SELECT * FROM "{table}"')))
        assert _taxonomy_memberships(original, "AAA") == _taxonomy_memberships(compact, "AAA")
        with pytest.raises(sqlite3.OperationalError):
            compact.execute("DELETE FROM ec_entity")
    assert sources.load_active_dc_memberships(taxonomy, canonical) == sources.load_active_dc_memberships(destination, canonical)
    assert tax._active_state(tax.TaxonomyPaths(taxonomy_db=taxonomy), "dc_ecosystem") == tax._active_state(tax.TaxonomyPaths(taxonomy_db=destination), "dc_ecosystem")
    index = peers.IdentityIndex({}, {}, {"AAA": frozenset({1})}, {})
    assert peers._taxonomy_source(taxonomy, index) == peers._taxonomy_source(destination, index)
    with pytest.raises(sources.SourceBundleError, match="DESTINATION_EXISTS"):
        extract(inputs)


def test_nonempty_wal_is_preserved_and_gated(inputs):
    _, taxonomy, destination = inputs
    sidecars.empty_wal(taxonomy)
    with closing(sqlite3.connect(taxonomy)) as db:
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("UPDATE ec_entity SET entity_name='changed' WHERE entity_id=120")
        db.commit()
        wal = taxonomy.with_name(taxonomy.name + "-wal")
        before = wal.read_bytes()
        with pytest.raises(sources.SourceBundleError, match="NONEMPTY_WAL"):
            extract(inputs)
        assert wal.read_bytes() == before
    assert not destination.exists()


def test_physical_drift_does_not_publish_partial_copy(inputs, monkeypatch):
    original = sources.load_active_dc_memberships
    calls = []
    def changed(path, canonical):
        value = original(path, canonical)
        calls.append(path)
        if len(calls) == 3:
            stat = inputs[1].stat()
            os.utime(inputs[1], ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        return value
    monkeypatch.setattr(sources, "load_active_dc_memberships", changed)
    with pytest.raises(sources.SourceBundleError, match="SOURCE_DRIFT"):
        extract(inputs)
    assert not inputs[2].exists()
    assert not list(inputs[2].parent.glob(".taxonomy-*.db"))


def test_compact_dependency_native_publication_and_recovery(tmp_path, monkeypatch):
    workflow, decisions, args = native.setup(tmp_path, monkeypatch)
    env = workflow.env
    original = env.paths().taxonomy_db
    compact = original.with_name("compact.db")
    sources.prepare_disposable_taxonomy_source(
        taxonomy_db=original, canonical_db=env.paths().canonical_db,
        destination=compact, operation_id="native-compact",
    )
    compact.replace(original)  # fixture-owned dependency only
    before = native.financial_hashes(env)
    # Source edits are included in the native code binding, as usual.
    args["expected_code"] = reconciliation.code_binding()
    result = reconciliation.run_reconciliation(env, decisions, **args, stop_after="publish")
    assert result["outcome"] == "COMPLETED", result
    assert result["postflight"] == "PASSED"
    assert native.journal.PUBLICATION_ROLES == ("provider", "canonical", "analysis")
    with env.writer_lock():
        recovery = native.journal.restore_old_generation(native.journal.load_journal(env.journal), journal_path=env.journal)
    assert recovery["status"] == "RECOVERED"
    assert resolve_active_generation(env.project).generation_id == args["expected_old"]["generation_id"]
    assert native.financial_hashes(env) == before


def test_owned_environment_rejects_non_native_source(tmp_path, monkeypatch):
    workflow, _, _ = native.setup(tmp_path, monkeypatch)
    with pytest.raises(PermissionError, match="OWNED_TAXONOMY_COPY_REQUIRED"):
        workflow.env.prepare_taxonomy_from(object())
