from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    current_universe_rows,
    ensure_candidate_schema,
    reject_production_path,
    run_candidate_apply,
    stable_hash,
    taxonomy_identity,
    universe_identity,
)
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.persistence import LAYOUT_FINGERPRINT, PERSISTENCE_VERSION


def _canonical(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY, company_key TEXT UNIQUE, company_name TEXT, status TEXT, created_at_utc TEXT, updated_at_utc TEXT);
            CREATE TABLE security(security_id INTEGER PRIMARY KEY, company_id INTEGER, current_ticker TEXT, exchange TEXT, active INTEGER, valid_from TEXT, valid_to TEXT, created_at_utc TEXT, updated_at_utc TEXT);
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY, security_id INTEGER, ticker TEXT, provider TEXT, valid_from TEXT, valid_to TEXT, source TEXT);
            INSERT INTO company VALUES (1,'SEC_CIK:1','AAA','ACTIVE','now','now'),(2,'SEC_CIK:2','BBB','ACTIVE','now','now'),(3,'SEC_CIK:3','CCC','ACTIVE','now','now');
            INSERT INTO security VALUES (10,1,'AAA','NYSE',1,NULL,NULL,'now','now');
            INSERT INTO security VALUES (20,2,'BBB','NYSE',0,NULL,NULL,'now','now');
            INSERT INTO security VALUES (30,3,'CCC.A','NYSE',1,NULL,NULL,'now','now');
            INSERT INTO security VALUES (31,3,'CCC.B','NYSE',1,NULL,NULL,'now','now');
            INSERT INTO ticker_alias VALUES (1,10,'OLD.AAA','LOCAL','2020','2021','fixture');
            """
        )


def _analysis(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE relative_valuation_snapshot(
                snapshot_id TEXT PRIMARY KEY, model_version TEXT, model_fingerprint TEXT,
                persistence_version TEXT, layout_fingerprint TEXT, semantic_mode TEXT,
                as_of_date TEXT, calculated_at_utc TEXT, source_fingerprint TEXT,
                result_fingerprint TEXT, physical_content_fingerprint TEXT,
                market_price_start_date TEXT, market_price_end_date TEXT, status TEXT,
                company_count INTEGER, current_fresh_count INTEGER,
                current_peer_eligible_count INTEGER, own_history_ready_count INTEGER,
                own_history_limited_count INTEGER, created_at_utc TEXT, completed_at_utc TEXT
            );
            CREATE TABLE relative_valuation_active_snapshot(model_fingerprint TEXT PRIMARY KEY, snapshot_id TEXT, activated_at_utc TEXT);
            CREATE TABLE relative_position_snapshot(snapshot_id TEXT PRIMARY KEY, model_fingerprint TEXT, snapshot_date TEXT, source_content_fingerprint TEXT, result_fingerprint TEXT, status TEXT);
            CREATE TABLE operating_income_v2_package_manifest(family_fingerprint TEXT, persistence_version TEXT, persistence_fingerprint TEXT PRIMARY KEY, economic_result_fingerprint TEXT, physical_content_fingerprint TEXT, status TEXT, applied_at_utc TEXT, family_version TEXT, model_manifest_json TEXT);
            INSERT INTO relative_valuation_snapshot VALUES ('rv1','RV','{RV_MODEL_FINGERPRINT}','{PERSISTENCE_VERSION}','{LAYOUT_FINGERPRINT}','CURRENTLY_REVISED_NOT_PIT','2026-09-10','now','src','res','phys',NULL,NULL,'COMPLETE',1,1,1,1,0,'now','now');
            INSERT INTO relative_valuation_active_snapshot VALUES ('{RV_MODEL_FINGERPRINT}','rv1','now');
            INSERT INTO relative_position_snapshot VALUES ('rp1','rp_model','2026-09-10','src','res','COMPLETE');
            INSERT INTO operating_income_v2_package_manifest VALUES ('fam','persist','pkg','econ','phys','COMPLETE','now','family','{{}}');
            """
        )


def _taxonomy(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE ec_taxonomy_version(taxonomy_version_id INTEGER PRIMARY KEY, taxonomy_version_code TEXT, source_reference TEXT, source_hash TEXT, status TEXT, is_active INTEGER, active_from TEXT, active_to TEXT);
            CREATE TABLE ec_entity(entity_id INTEGER PRIMARY KEY, entity_type TEXT, entity_code TEXT, entity_name TEXT, ticker TEXT, status TEXT);
            CREATE TABLE ec_membership(membership_id INTEGER PRIMARY KEY, taxonomy_version_id INTEGER, child_entity_id INTEGER, membership_type TEXT, membership_role TEXT, is_primary INTEGER, role_weight REAL, status TEXT);
            INSERT INTO ec_taxonomy_version VALUES (1,'TAX_V1','fixture.csv','hash','ACTIVE',1,'2026-01-01',NULL);
            INSERT INTO ec_entity VALUES (1,'TICKER','AAA','AAA','AAA','ACTIVE');
            INSERT INTO ec_membership VALUES (1,1,1,'CONTAINS','PRIMARY',1,1.0,'ACTIVE');
            """
        )


def _paths(tmp_path: Path) -> CandidatePaths:
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    taxonomy = tmp_path / "taxonomy.db"
    _canonical(canonical)
    _analysis(analysis)
    _taxonomy(taxonomy)
    return CandidatePaths(canonical, analysis, taxonomy)


def test_universe_backfill_classifies_security_cardinality(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    members, aliases = current_universe_rows(paths.canonical_db, now="now")
    identity = universe_identity(members, aliases, as_of_date="2026-09-11")
    assert identity["member_count"] == 3
    assert identity["zero_active_company_count"] == 1
    assert identity["multi_active_company_count"] == 1
    assert len(identity["economic_result_fingerprint"]) == 64


def test_candidate_apply_is_idempotent_and_dependency_states_detect_mismatch(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    first = run_candidate_apply(paths, apply=True, applied_at_utc="now")
    second = run_candidate_apply(paths, apply=True, applied_at_utc="now")
    universe = first["universe"]["identity"]
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    assert second["universe"]["outcome"] == "NO_CHANGE"
    assert second["dependencies"]["outcome"] == "NO_CHANGE"
    assert candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-11",
        expected_universe_fingerprint=universe["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )["state"] == "COMPATIBLE"
    assert candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-11",
        expected_universe_fingerprint="wrong",
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )["state"] == "OPERATIONAL_UNIVERSE_MISMATCH"
    assert candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-11",
        expected_universe_fingerprint=universe["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint="wrong",
    )["state"] == "ECONOMIC_TAXONOMY_MISMATCH"


def test_dry_run_does_not_create_schema(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    ensure_candidate_schema(paths, applied_at_utc="now", apply=False)
    with sqlite3.connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='fundamentals_operational_universe_version'").fetchone() is None


def test_production_path_refusal() -> None:
    from rawcandle.fundamentals.phase12d import PRODUCTION

    with pytest.raises(PermissionError):
        reject_production_path(PRODUCTION["canonical"], "canonical")


def test_stable_hash_is_deterministic() -> None:
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})
