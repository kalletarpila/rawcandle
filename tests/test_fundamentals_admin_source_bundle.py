from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from rawcandle import datacenter_taxonomy_operation_log as taxonomy_locking
from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.refresh_copy_runtime import prepare_refresh_test_read_only_sources
from rawcandle.fundamentals.admin.source_bundle import (
    MARKET_READ_CLOSURE,
    SOURCE_CONTRACT_VERSION,
    TAXONOMY_READ_CLOSURE,
    SourceBundleError,
    StableReadOnlySourceBundle,
    TaxonomySourceMode,
    bind_taxonomy_source,
    build_stable_read_only_source_bundle,
    protected_direct_taxonomy_source,
    validate_stable_read_only_source_bundle,
)
from rawcandle.fundamentals.operating_income_v2.canonical_valuation_source import (
    load_canonical_source,
)
from rawcandle.fundamentals.operating_income_v2.peer_source_context import (
    _classification_source,
)
from rawcandle.fundamentals.operating_income_v2.rehearsal import _load_split_events
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import (
    load_active_dc_memberships,
)
from rawcandle.fundamentals.relative_valuation import source as rv_source
from rawcandle.fundamentals.relative_valuation.source import ReadOnlySourcePaths, _bars


AS_OF = "2026-09-08"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                current_ticker TEXT NOT NULL,
                exchange TEXT,
                market TEXT,
                active INTEGER NOT NULL
            );
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,ticker TEXT);
            CREATE TABLE v4_ttm_values(
                ttm_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                security_id INTEGER NOT NULL,
                endpoint_fiscal_year INTEGER NOT NULL,
                endpoint_fiscal_quarter TEXT NOT NULL,
                endpoint_quarter_id INTEGER NOT NULL,
                period_end TEXT NOT NULL,
                ttm_source_available_date TEXT,
                readiness_status TEXT NOT NULL,
                blocker_codes_json TEXT NOT NULL,
                ttm_ebit REAL,
                ttm_free_cashflow REAL,
                ttm_net_income_common REAL,
                net_income_common_4q_ready INTEGER,
                shares_outstanding REAL,
                cash REAL,
                total_debt REAL,
                output_fingerprint TEXT,
                model_version TEXT NOT NULL,
                updated_at_utc TEXT,
                run_id TEXT
            );
            INSERT INTO security VALUES(11,1,'AAA','NASDAQ','usa',1);
            INSERT INTO security VALUES(22,2,'BBB','NASDAQ','usa',1);
            INSERT INTO v4_ttm_values VALUES(
                101,1,11,2026,'Q1',1001,'2026-03-31','2026-04-20',
                'TTM_READY','[]',12,9,7,1,10,5,2,'fp-a',
                'V4_TTM_EBIT_FIRST_V1','2026-04-20T00:00:00Z','r1'
            );
            INSERT INTO v4_ttm_values VALUES(
                202,2,22,2026,'Q2',2002,'2026-06-30','2026-08-20',
                'TTM_READY','[]',22,14,11,1,20,8,3,'fp-b',
                'V4_TTM_EBIT_FIRST_V1','2026-08-20T00:00:00Z','r1'
            );
            INSERT INTO v4_ttm_values VALUES(
                303,1,11,2025,'Q4',1000,'2025-12-31',NULL,
                'TTM_NOT_READY','["SOURCE_DATE_MISSING"]',NULL,NULL,NULL,0,10,5,2,'fp-c',
                'V4_TTM_EBIT_FIRST_V1','2026-01-01T00:00:00Z','r1'
            );
            """
        )
    return path.absolute()


def _market(path: Path, *, journal_mode: str = "DELETE", include_splits: bool = True) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA journal_mode={journal_mode}")
        connection.executescript(
            """
            CREATE TABLE ticker_meta(ticker TEXT,market TEXT,sector TEXT,industry TEXT);
            CREATE TABLE osakedata(
                id INTEGER PRIMARY KEY,
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
                open REAL,high REAL,low REAL,close REAL
            );
            CREATE INDEX idx_fixture_prices ON osakedata(osake,pvm DESC);
            INSERT INTO ticker_meta VALUES('AAA','usa','Technology','Hardware');
            INSERT INTO ticker_meta VALUES('BBB','usa','Industrials','Machinery');
            """
        )
        if include_splits:
            connection.execute(
                "CREATE TABLE splits_data(osake TEXT,split_date TEXT,split_ratio REAL,is_price_data_corrected INTEGER)"
            )
            connection.execute("INSERT INTO splits_data VALUES('AAA','2026-02-01',2,1)")
        start = date(2026, 3, 1)
        rows = []
        row_id = 1
        for ticker, offset in (("AAA", 0.0), ("BBB", 100.0)):
            for index in range(200):
                current = start + timedelta(days=index)
                value = 10.0 + offset + index / 10
                rows.append((row_id, ticker, current.isoformat(), value, value + 1, value - 1, value + 0.5))
                row_id += 1
        connection.executemany("INSERT INTO osakedata VALUES(?,?,?,?,?,?,?)", rows)
    return path.absolute()


def _taxonomy(path: Path, *, journal_mode: str = "WAL") -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA journal_mode={journal_mode}")
        connection.executescript(
            """
            CREATE TABLE ec_ecosystem(
                ecosystem_id INTEGER PRIMARY KEY,ecosystem_code TEXT,ecosystem_name TEXT,status TEXT
            );
            CREATE TABLE ec_taxonomy_version(
                taxonomy_version_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,
                taxonomy_version_code TEXT,taxonomy_name TEXT,source_reference TEXT,
                source_hash TEXT,status TEXT,is_active INTEGER,active_from TEXT,active_to TEXT
            );
            CREATE TABLE ec_entity(
                entity_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,entity_type TEXT,
                entity_code TEXT,entity_name TEXT,ticker TEXT,status TEXT,entity_level INTEGER
            );
            CREATE TABLE ec_membership(
                membership_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,taxonomy_version_id INTEGER,
                parent_entity_id INTEGER,child_entity_id INTEGER,membership_type TEXT,
                membership_role TEXT,is_primary INTEGER,role_weight REAL,status TEXT,source_note TEXT
            );
            INSERT INTO ec_ecosystem VALUES(1,'DATACENTER','Data Center','ACTIVE');
            INSERT INTO ec_taxonomy_version VALUES(
                10,1,'DC_V1','Data Center V1','fixture','source-sha','ACTIVE',1,'2026-01-01',NULL
            );
            INSERT INTO ec_entity VALUES(100,1,'GROUP_L1','COMPUTE','Compute',NULL,'ACTIVE',1);
            INSERT INTO ec_entity VALUES(110,1,'GROUP_L2','CHIPS','Chips',NULL,'ACTIVE',2);
            INSERT INTO ec_entity VALUES(120,1,'TICKER','AAA','AAA','AAA','ACTIVE',3);
            INSERT INTO ec_membership VALUES(1000,1,10,100,110,'CONTAINS',NULL,1,1,'ACTIVE',NULL);
            INSERT INTO ec_membership VALUES(1001,1,10,110,120,'CONTAINS','CORE',1,1,'ACTIVE','fixture');
            """
        )
    return path.absolute()


def _copy_sqlite(source: Path, destination: Path) -> Path:
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as target:
        source_connection.backup(target)
    return destination.absolute()


def _analysis(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE valuation_revised_result(
                valuation_revised_result_id INTEGER PRIMARY KEY,
                company_id INTEGER,fiscal_sequence INTEGER,fundamental_available_date TEXT,
                model_fingerprint TEXT,history_mode TEXT,valuation_status TEXT,
                fiscal_year INTEGER,fiscal_quarter TEXT,quarter_id INTEGER
            );
            CREATE TABLE relative_position_active_snapshot(
                snapshot_id TEXT,model_fingerprint TEXT
            );
            CREATE TABLE relative_position_snapshot(snapshot_id TEXT,snapshot_date TEXT);
            """
        )
    return path.absolute()


@pytest.fixture
def sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    return (
        _canonical(tmp_path / "canonical.db"),
        _market(tmp_path / "market.db"),
        _taxonomy(tmp_path / "taxonomy.db"),
    )


def _build(tmp_path: Path, canonical: Path, market: Path, name: str = "bundle", **kwargs: object) -> StableReadOnlySourceBundle:
    return build_stable_read_only_source_bundle(
        market_db=market,
        canonical_db=canonical,
        bundle_dir=tmp_path / name,
        as_of_date=AS_OF,
        **kwargs,
    )


def test_read_closure_is_explicit_and_taxonomy_is_not_packaged() -> None:
    assert SOURCE_CONTRACT_VERSION
    assert {table for item in MARKET_READ_CLOSURE for table in item.tables} == {
        "ticker_meta", "osakedata", "splits_data"
    }
    assert {table for item in TAXONOMY_READ_CLOSURE for table in item.tables} == {
        "ec_taxonomy_version", "ec_ecosystem", "ec_entity", "ec_membership"
    }


def test_compact_market_bundle_matches_existing_reader_semantics(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources
    full_copy = _copy_sqlite(market, tmp_path / "full-market.db")
    bundle = _build(tmp_path, canonical, market)

    full_valuation = load_canonical_source(canonical, full_copy)
    compact_valuation = load_canonical_source(canonical, bundle.market_db)
    assert compact_valuation == full_valuation
    assert _classification_source(bundle.market_db) == _classification_source(full_copy)
    assert _load_split_events(bundle.market_db) == _load_split_events(full_copy)
    with sqlite3.connect(full_copy) as full, sqlite3.connect(bundle.market_db) as compact:
        full.row_factory = compact.row_factory = sqlite3.Row
        assert _bars(compact, "AAA", AS_OF) == _bars(full, "AAA", AS_OF)
        full_state = full.execute(
            "SELECT COUNT(*),MAX(pvm),MAX(id) FROM osakedata WHERE UPPER(osake)='AAA'"
        ).fetchone()
        compact_state = compact.execute(
            "SELECT COUNT(*),MAX(pvm),MAX(id) FROM osakedata WHERE UPPER(osake)='AAA'"
        ).fetchone()
        assert tuple(compact_state) == tuple(full_state)
    assert bundle.manifest["taxonomy"]["packaged"] is False
    assert sorted(path.name for path in bundle.market_db.parent.iterdir()) == [
        "manifest.json", "market.db"
    ]
    assert bundle.manifest["market"]["row_counts"] == {
        "ticker_meta": 2,
        "osakedata": 232,
        "splits_data": 1,
    }
    assert bundle.manifest["market"]["valuation_coverage"]["status_counts"] == {
        "PRICE_FOUND": 2,
        "NO_MATCHING_VALID_PRICE": 0,
        "NO_TICKER": 0,
        "NO_CUTOFF": 1,
    }
    no_cutoff_fingerprint = bundle.manifest["market"]["valuation_coverage"][
        "status_identity_fingerprints"
    ]["NO_CUTOFF"]
    assert len(no_cutoff_fingerprint) == 64
    assert no_cutoff_fingerprint != bundle.manifest["market"]["valuation_coverage"][
        "status_identity_fingerprints"
    ]["NO_TICKER"]


def test_full_relative_valuation_source_loader_has_market_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sources: tuple[Path, Path, Path],
) -> None:
    canonical, market, taxonomy = sources
    analysis = _analysis(tmp_path / "analysis.db")
    full_copy = _copy_sqlite(market, tmp_path / "full-market.db")
    bundle = _build(tmp_path, canonical, market)
    monkeypatch.setattr(rv_source, "assert_v2_active", lambda _: None)
    monkeypatch.setattr(
        rv_source.peer_source,
        "_taxonomy_source",
        lambda *_: ({}, (), "taxonomy-fp", {"status": "FIXTURE"}),
    )
    monkeypatch.setattr(
        rv_source,
        "_listing_eligibility",
        lambda *_: ({11: (True, "ELIGIBLE_ON_DATE"), 22: (True, "ELIGIBLE_ON_DATE")}, {"status": "FIXTURE"}),
    )
    monkeypatch.setattr(
        rv_source.structural_break,
        "latest_ttm_eligibility",
        lambda *_args, **_kwargs: ({}, {"fingerprint": "structural-fp"}),
    )

    full = rv_source.load_relative_valuation_source(
        ReadOnlySourcePaths(analysis, canonical, full_copy, taxonomy),
        as_of_date=AS_OF,
    )
    compact = rv_source.load_relative_valuation_source(
        ReadOnlySourcePaths(analysis, canonical, bundle.market_db, taxonomy),
        as_of_date=AS_OF,
    )

    assert compact == full


def test_casefold_price_fallback_uses_indexable_source_ticker_forms(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources
    with sqlite3.connect(market) as connection:
        connection.execute("UPDATE osakedata SET osake='aaa' WHERE osake='AAA'")
    bundle = _build(tmp_path, canonical, market)
    with sqlite3.connect(market) as source, sqlite3.connect(bundle.market_db) as compact:
        source.row_factory = compact.row_factory = sqlite3.Row
        assert _bars(compact, "AAA", AS_OF) == _bars(source, "AAA", AS_OF)


def test_conflicting_casefold_price_rows_fail_closed(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources
    with sqlite3.connect(market) as connection:
        connection.execute(
            "INSERT INTO osakedata VALUES(9999,'aaa','2026-09-08',1,2,0.5,99)"
        )
    with pytest.raises(SourceBundleError, match="CASEFOLD_PRICE_CONFLICT:AAA:2026-09-08"):
        _build(tmp_path, canonical, market)


def test_unchanged_delete_journal_source_is_valid_and_not_mutated(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources
    before = (market.stat().st_size, market.stat().st_mtime_ns, _sha256(market))
    bundle = _build(tmp_path, canonical, market)
    repeated = _build(tmp_path, canonical, market, "repeated")
    validate_stable_read_only_source_bundle(bundle)
    after = (market.stat().st_size, market.stat().st_mtime_ns, _sha256(market))
    assert before == after
    assert bundle.manifest == repeated.manifest
    assert bundle.manifest["market"]["source_pragmas"]["journal_mode"] == "delete"
    assert bundle.market_db.stat().st_mode & 0o222 == 0


def test_relevant_value_change_changes_semantic_fingerprint(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources
    first = _build(tmp_path, canonical, market, "first")
    with sqlite3.connect(market) as connection:
        connection.execute("UPDATE osakedata SET close=close+7 WHERE osake='AAA' AND pvm='2026-04-20'")
    second = _build(tmp_path, canonical, market, "second")
    assert first.semantic_fingerprint != second.semantic_fingerprint


def test_post_as_of_irrelevant_price_does_not_change_semantic_fingerprint(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources
    first = _build(tmp_path, canonical, market, "first")
    with sqlite3.connect(market) as connection:
        connection.execute(
            "INSERT INTO osakedata VALUES(9999,'ZZZ','2026-12-01',1,2,0.5,1.5)"
        )
    second = _build(tmp_path, canonical, market, "second")
    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_change_during_extraction_fails_closed_and_cleans_partial_artifacts(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources

    def mutate(stage: str, _: object) -> None:
        if stage == "AFTER_SOURCE_EXTRACTION":
            with sqlite3.connect(market) as connection:
                connection.execute(
                    "UPDATE osakedata SET close=close+1 WHERE osake='AAA' AND pvm='2026-04-20'"
                )

    with pytest.raises(SourceBundleError, match="READ_ONLY_SOURCE_DRIFT"):
        _build(tmp_path, canonical, market, hook=mutate)
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".bundle.partial-*"))


def test_source_file_replacement_is_detected(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources

    def replace(stage: str, _: object) -> None:
        if stage == "AFTER_SOURCE_EXTRACTION":
            replacement = _copy_sqlite(market, tmp_path / "replacement.db")
            os.replace(replacement, market)

    with pytest.raises(SourceBundleError, match="READ_ONLY_SOURCE_DRIFT"):
        _build(tmp_path, canonical, market, hook=replace)


def test_canonical_binding_change_during_extraction_is_detected(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, _ = sources

    def mutate(stage: str, _: object) -> None:
        if stage == "AFTER_SOURCE_EXTRACTION":
            with sqlite3.connect(canonical) as connection:
                connection.execute(
                    "UPDATE v4_ttm_values SET ttm_source_available_date='2026-04-21' WHERE ttm_id=101"
                )

    with pytest.raises(SourceBundleError, match="CANONICAL_BINDING_DRIFT"):
        _build(tmp_path, canonical, market, hook=mutate)


@pytest.mark.parametrize("failure_stage", ["AFTER_BUNDLE_WRITE", "AFTER_BUNDLE_PUBLISH"])
def test_interrupted_write_is_disposable(
    tmp_path: Path,
    sources: tuple[Path, Path, Path],
    failure_stage: str,
) -> None:
    canonical, market, _ = sources

    def interrupt(stage: str, _: object) -> None:
        if stage == failure_stage:
            raise RuntimeError("injected interruption")

    with pytest.raises(RuntimeError, match="injected interruption"):
        _build(tmp_path, canonical, market, hook=interrupt)
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".bundle.partial-*"))


def test_missing_schema_and_missing_bundle_coverage_fail_closed(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path / "canonical.db")
    incomplete = _market(tmp_path / "incomplete.db", include_splits=False)
    with pytest.raises(SourceBundleError, match="READ_ONLY_SOURCE_TABLE_MISSING:splits_data"):
        _build(tmp_path, canonical, incomplete)

    market = _market(tmp_path / "market.db")
    bundle = _build(tmp_path, canonical, market, "valid")
    os.chmod(bundle.market_db, 0o600)
    with sqlite3.connect(bundle.market_db) as connection:
        connection.execute("DELETE FROM osakedata WHERE id=(SELECT MIN(id) FROM osakedata)")
    with pytest.raises(SourceBundleError, match="ROW_COVERAGE_MISMATCH"):
        validate_stable_read_only_source_bundle(bundle)


def test_wal_taxonomy_direct_read_is_bound_and_runtime_authorized(
    tmp_path: Path, sources: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, _, taxonomy = sources
    monkeypatch.setattr(
        taxonomy_locking,
        "DEFAULT_TAXONOMY_OPERATION_ROOT",
        tmp_path / "temp" / "taxonomy",
    )
    fallback_copy = _copy_sqlite(taxonomy, tmp_path / "taxonomy-copy.db")
    fallback = bind_taxonomy_source(fallback_copy, canonical)
    with taxonomy_operation_lock_context(
        deployment_id="fixture",
        operation_type="SOURCE_BUNDLE_PROOF",
        operation_id="fixture-op",
    ) as lock:
        direct = bind_taxonomy_source(
            taxonomy,
            canonical,
            mode=TaxonomySourceMode.DIRECT_LOCKED_READ,
            operation_lock=lock,
        )
    assert direct.semantic_fingerprint == fallback.semantic_fingerprint
    assert direct.version == fallback.version == "DC_V1"
    assert direct.membership_rows == fallback.membership_rows == 1
    assert direct.packaged is False
    assert direct.runtime_authorized is True
    assert direct.lock_contract_status == "AUTHORITATIVE_TAXONOMY_LOCK_HELD"
    with sqlite3.connect(taxonomy) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    direct_memberships, direct_dependency = load_active_dc_memberships(taxonomy, canonical)
    copy_memberships, copy_dependency = load_active_dc_memberships(fallback_copy, canonical)
    assert direct_memberships == copy_memberships
    assert direct_dependency == copy_dependency


def test_protected_direct_taxonomy_read_blocks_writer_and_preserves_file(
    tmp_path: Path, sources: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, _, taxonomy = sources
    lock_root = tmp_path / "temp" / "taxonomy"
    monkeypatch.setattr(taxonomy_locking, "DEFAULT_TAXONOMY_OPERATION_ROOT", lock_root)
    before = hashlib.sha256(taxonomy.read_bytes()).hexdigest()

    with protected_direct_taxonomy_source(taxonomy, canonical, operation_id="read-1") as binding:
        with pytest.raises(RuntimeError, match="taxonomy operation lock is active"):
            with taxonomy_operation_lock_context(
                deployment_id="writer",
                operation_type="ACTIVATE",
                operation_id="writer-1",
            ):
                raise AssertionError("conflicting writer entered protected read")
        _, dependency = load_active_dc_memberships(taxonomy, canonical)
        assert dependency["semantic_fingerprint"] == binding.semantic_fingerprint
        assert dependency["version"] == binding.version

    assert not taxonomy_locking.authoritative_taxonomy_lock_path().exists()
    assert hashlib.sha256(taxonomy.read_bytes()).hexdigest() == before


def test_taxonomy_mutation_after_test_changes_direct_semantic_binding(
    tmp_path: Path, sources: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, _, taxonomy = sources
    monkeypatch.setattr(
        taxonomy_locking,
        "DEFAULT_TAXONOMY_OPERATION_ROOT",
        tmp_path / "temp" / "taxonomy",
    )
    with protected_direct_taxonomy_source(taxonomy, canonical, operation_id="test") as tested:
        tested_contract = (tested.version, tested.semantic_fingerprint, tested.membership_rows)

    with taxonomy_operation_lock_context(
        deployment_id="writer",
        operation_type="ACTIVATE",
        operation_id="writer-2",
    ):
        with sqlite3.connect(taxonomy) as connection:
            connection.execute(
                "UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_V2',source_hash='changed' "
                "WHERE is_active=1"
            )

    with protected_direct_taxonomy_source(taxonomy, canonical, operation_id="production") as current:
        current_contract = (current.version, current.semantic_fingerprint, current.membership_rows)

    assert current_contract != tested_contract


def test_protected_direct_taxonomy_read_releases_lock_after_exception(
    tmp_path: Path, sources: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, _, taxonomy = sources
    monkeypatch.setattr(
        taxonomy_locking,
        "DEFAULT_TAXONOMY_OPERATION_ROOT",
        tmp_path / "temp" / "taxonomy",
    )
    with pytest.raises(RuntimeError, match="injected"):
        with protected_direct_taxonomy_source(taxonomy, canonical, operation_id="failing-read"):
            raise RuntimeError("injected")
    assert not taxonomy_locking.authoritative_taxonomy_lock_path().exists()


def test_taxonomy_direct_read_requires_authoritative_lock(
    sources: tuple[Path, Path, Path]
) -> None:
    canonical, _, taxonomy = sources
    with pytest.raises(SourceBundleError, match="TAXONOMY_AUTHORITATIVE_LOCK_REQUIRED"):
        bind_taxonomy_source(
            taxonomy,
            canonical,
            mode=TaxonomySourceMode.DIRECT_LOCKED_READ,
        )


def test_taxonomy_direct_read_rejects_non_authoritative_lock_root(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, _, taxonomy = sources
    with taxonomy_operation_lock_context(
        deployment_id="fixture",
        operation_type="SOURCE_BUNDLE_PROOF",
        operation_id="wrong-root",
        evidence_root=tmp_path / "temp" / "non-authoritative",
    ) as lock:
        with pytest.raises(SourceBundleError, match="TAXONOMY_AUTHORITATIVE_LOCK_PATH_MISMATCH"):
            bind_taxonomy_source(
                taxonomy,
                canonical,
                mode=TaxonomySourceMode.DIRECT_LOCKED_READ,
                operation_lock=lock,
            )


def test_refresh_test_binding_uses_real_compact_bundle_and_survives_lane_cleanup(
    tmp_path: Path, sources: tuple[Path, Path, Path]
) -> None:
    canonical, market, taxonomy = sources
    provider = tmp_path / "provider.db"
    analysis = tmp_path / "analysis-source.db"
    provider.write_bytes(b"")
    analysis.write_bytes(b"")
    lane = tmp_path / "refresh-test-lane"
    lane.mkdir()

    paths, evidence = prepare_refresh_test_read_only_sources(
        BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy),
        lane_dir=lane,
        canonical_candidate=canonical,
        as_of_date=AS_OF,
    )

    assert paths["market"].resolve() != market.resolve()
    assert evidence["market"]["old_full_copy_bytes_avoided"] == market.stat().st_size
    assert evidence["market"]["compact_bundle_bytes"] == paths["market"].stat().st_size
    assert evidence["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert evidence["market"]["bundle_manifest"]["source_contract_version"] == SOURCE_CONTRACT_VERSION
    assert evidence["market"]["bundle_manifest"]["market"]["valuation_coverage"]["status_counts"] == {
        "PRICE_FOUND": 2,
        "NO_MATCHING_VALID_PRICE": 0,
        "NO_TICKER": 0,
        "NO_CUTOFF": 1,
    }
    assert evidence["taxonomy"]["mode"] == "FULL_SQLITE_BACKUP"
    assert evidence["taxonomy"]["binding"]["version"] == "DC_V1"
    assert evidence["taxonomy"]["copy_sha256"] == _sha256(paths["taxonomy"])

    durable_evidence = evidence
    shutil.rmtree(lane)
    assert not paths["market"].exists()
    assert not paths["taxonomy"].exists()
    assert durable_evidence["market"]["bundle_manifest"]["market"]["semantic_fingerprint"]
    assert durable_evidence["taxonomy"]["binding"]["semantic_fingerprint"]
