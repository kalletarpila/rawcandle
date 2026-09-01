from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from rawcandle.fundamentals.relative_position.engine import RelativeMeasure
from rawcandle.fundamentals.relative_position.source import (
    IdentityIndex,
    ReadOnlySourcePaths,
    load_current_relative_source,
    resolve_observation_security,
    resolve_taxonomy_ticker,
)
from rawcandle.fundamentals.relative_position.rehearsal import run_full_universe_rehearsal
from rawcandle.cli.run_fundamentals_v4_relative_position_rehearsal import build_parser
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as FUND_MODEL
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VAL_MODEL


def identity_index() -> IdentityIndex:
    security1 = {"security_id": 1, "company_id": 1, "current_ticker": "NEW", "active": 1}
    security2 = {"security_id": 2, "company_id": 2, "current_ticker": "TWO", "active": 1}
    return IdentityIndex(
        security_by_id={1: security1, 2: security2},
        active_by_company={1: (security1,), 2: (security2,)},
        current_ticker_to_companies={"NEW": frozenset({1}), "TWO": frozenset({2})},
        alias_to_companies={"OLD": frozenset({1}), "NEW": frozenset({1})},
    )


def test_identity_mapping_prefers_observation_security_and_supports_alias_history() -> None:
    index = identity_index()
    assert resolve_observation_security(index, 1, 1) == ("OBSERVATION_SECURITY_ID", 1, "NEW")
    assert resolve_observation_security(index, 1, None) == ("UNIQUE_ACTIVE_SECURITY_FALLBACK", 1, "NEW")
    assert resolve_observation_security(index, 1, 2) == ("SECURITY_ID_UNRESOLVED", None, None)
    assert resolve_taxonomy_ticker("NEW", index) == ("DIRECT_CURRENT_TICKER", 1)
    assert resolve_taxonomy_ticker("OLD", index) == ("ALIAS_ONLY", 1)
    assert resolve_taxonomy_ticker("MISSING", index) == ("UNMAPPED", None)


def create_sources(root: Path) -> ReadOnlySourcePaths:
    analysis = root / "analysis.db"
    canonical = root / "canonical.db"
    market = root / "market.db"
    taxonomy = root / "taxonomy.db"
    as_of = date(2026, 9, 1)
    exact = (as_of - timedelta(days=180)).isoformat()
    stale = (as_of - timedelta(days=181)).isoformat()
    with sqlite3.connect(canonical) as conn:
        conn.executescript("""
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,active INTEGER);
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,ticker TEXT);
            CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,period_end TEXT,source_availability_date TEXT);
            CREATE TABLE v4_ttm_values(ttm_id INTEGER PRIMARY KEY,company_id INTEGER,security_id INTEGER,endpoint_quarter_id INTEGER,model_version TEXT,output_fingerprint TEXT);
        """)
        conn.executemany("INSERT INTO security VALUES (?,?,?,1)", [(1, 1, "ONE"), (2, 2, "TWO"), (3, 3, "THREE")])
        conn.execute("INSERT INTO ticker_alias VALUES (1,1,'OLDONE')")
        conn.executemany("INSERT INTO v4_quarter VALUES (?,?,?,?,?,?)", [
            (1, 1, 2025, "Q4", "2025-12-31", "2026-02-01"),
            (2, 1, 2026, "Q1", "2026-03-31", exact),
            (3, 1, 2026, "Q2", "2026-06-30", "2026-10-01"),
            (4, 2, 2026, "Q1", "2026-03-31", stale),
            (5, 3, 2026, "Q1", "2026-03-31", "2026-08-01"),
        ])
        conn.executemany("INSERT INTO v4_ttm_values VALUES (?,?,?,?,?,?)", [
            (1, 1, 1, 1, "V4_TTM_EBIT_FIRST_V1", "t1"),
            (2, 1, 1, 2, "V4_TTM_EBIT_FIRST_V1", "t2"),
            (3, 1, 1, 3, "V4_TTM_EBIT_FIRST_V1", "t3"),
            (4, 2, 2, 4, "V4_TTM_EBIT_FIRST_V1", "t4"),
            (5, 3, 3, 5, "V4_TTM_EBIT_FIRST_V1", "t5"),
        ])
    with sqlite3.connect(analysis) as conn:
        conn.executescript("""
            CREATE TABLE score_result(score_result_id INTEGER PRIMARY KEY,company_id INTEGER,quarter_id INTEGER,model_version TEXT,model_fingerprint TEXT,total_score REAL,readiness_status TEXT,missing_input_reason TEXT,generated_at_utc TEXT,run_id TEXT);
            CREATE TABLE valuation_revised_result(valuation_revised_result_id INTEGER PRIMARY KEY,company_id INTEGER,security_id INTEGER,ticker TEXT,fiscal_sequence INTEGER,quarter_id INTEGER,fundamental_available_date TEXT,total_valuation_score REAL,valuation_status TEXT,reason_code TEXT,sector TEXT,industry TEXT,model_version TEXT,model_fingerprint TEXT,source_fingerprint TEXT,engine_result_fingerprint TEXT,result_fingerprint TEXT,history_mode TEXT);
        """)
        conn.executemany("INSERT INTO score_result VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (1, 1, 1, "SIMPLE_FUNDAMENTAL_SCORE_V1", FUND_MODEL, 10.0, "SCORE_FULL", None, "now", "r"),
            (2, 1, 2, "SIMPLE_FUNDAMENTAL_SCORE_V1", FUND_MODEL, 20.0, "SCORE_FULL", None, "now", "r"),
            (3, 1, 3, "SIMPLE_FUNDAMENTAL_SCORE_V1", FUND_MODEL, 99.0, "SCORE_FULL", None, "now", "r"),
            (4, 2, 4, "SIMPLE_FUNDAMENTAL_SCORE_V1", FUND_MODEL, 30.0, "SCORE_FULL", None, "now", "r"),
            (5, 3, 5, "SIMPLE_FUNDAMENTAL_SCORE_V1", FUND_MODEL, None, "SCORE_LIMITED", "limited", "now", "r"),
        ])
        conn.executemany("INSERT INTO valuation_revised_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            (1, 1, 1, "OLDONE", 8105, 2, exact, 40.0, "VALUATION_FULL", "VALUATION_FULL", "Old", "Old", "ABSOLUTE_VALUATION_SCORE_V1", VAL_MODEL, "s", "e", "v1", "REVISED_HISTORY"),
            (2, 2, 2, "TWO", 8105, 4, stale, None, "VALUATION_NOT_APPLICABLE", "UNSUPPORTED_REIT_MODEL", "Old", "Old", "ABSOLUTE_VALUATION_SCORE_V1", VAL_MODEL, "s", "e", "v2", "REVISED_HISTORY"),
        ])
    with sqlite3.connect(market) as conn:
        conn.execute("CREATE TABLE ticker_meta(ticker TEXT,sector TEXT,industry TEXT)")
        conn.executemany("INSERT INTO ticker_meta VALUES (?,?,?)", [
            ("ONE", "Technology", "Software - Application"),
            ("TWO", "Real Estate", "REIT - Retail"),
            ("THREE", "Healthcare", "Biotechnology"),
        ])
    with sqlite3.connect(taxonomy) as conn:
        conn.executescript("""
            CREATE TABLE ec_ecosystem(ecosystem_id INTEGER PRIMARY KEY,ecosystem_code TEXT,status TEXT);
            CREATE TABLE ec_taxonomy_version(taxonomy_version_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,taxonomy_version_code TEXT,source_reference TEXT,source_hash TEXT,status TEXT,is_active INTEGER);
            CREATE TABLE ec_entity(entity_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,entity_type TEXT,ticker TEXT,status TEXT);
            CREATE TABLE ec_membership(membership_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,taxonomy_version_id INTEGER,parent_entity_id INTEGER,child_entity_id INTEGER,membership_role TEXT,is_primary INTEGER,role_weight REAL,status TEXT);
            INSERT INTO ec_ecosystem VALUES (1,'DATACENTER','ACTIVE');
            INSERT INTO ec_taxonomy_version VALUES (1,1,'TEST_V1','test.csv','hash','ACTIVE',1);
            INSERT INTO ec_entity VALUES (1,1,'TICKER','OLDONE','ACTIVE');
            INSERT INTO ec_membership VALUES (1,1,1,99,1,'CORE',1,1.0,'ACTIVE');
        """)
    return ReadOnlySourcePaths(analysis, canonical, market, taxonomy)


def test_adapter_selects_latest_asof_applies_freshness_and_current_classification(tmp_path: Path) -> None:
    paths = create_sources(tmp_path)
    source = load_current_relative_source(paths, as_of_date="2026-09-01", freshness_days=180)
    fundamental = [row for row in source.observations if row.measure == RelativeMeasure.FUNDAMENTAL_SCORE]
    valuation = [row for row in source.observations if row.measure == RelativeMeasure.ABSOLUTE_VALUATION_SCORE]
    assert len(fundamental) == 3
    company1 = next(row for row in fundamental if row.company_id == 1)
    assert company1.score == 20.0
    assert company1.source_observation_id == "score_result:2"
    assert company1.source_eligible is True
    assert company1.sector == "Technology"
    assert company1.ecosystem_memberships[0].ecosystem_id == "DATACENTER"
    assert company1.ecosystem_memberships[0].role == "CORE"
    assert next(row for row in fundamental if row.company_id == 2).eligibility_reason == "SOURCE_OBSERVATION_STALE"
    assert next(row for row in fundamental if row.company_id == 3).eligibility_reason == "SCORE_LIMITED"
    assert valuation[0].ticker == "ONE"
    assert valuation[0].sector == "Technology"
    assert valuation[0].source_eligible is True
    assert valuation[1].source_eligible is False
    assert source.metadata["taxonomy"]["unique_ticker_mapping_counts"] == {"ALIAS_ONLY": 1}


def test_adapter_rejects_duplicate_fundamental_source_result(tmp_path: Path) -> None:
    paths = create_sources(tmp_path)
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.execute(
            "INSERT INTO score_result SELECT 99,company_id,quarter_id,model_version,model_fingerprint,total_score,readiness_status,missing_input_reason,generated_at_utc,run_id FROM score_result WHERE score_result_id=2"
        )
    with pytest.raises(ValueError, match="DUPLICATE_FUNDAMENTAL_SOURCE_RESULT"):
        load_current_relative_source(paths, as_of_date="2026-09-01")


def test_adapter_requires_distinct_explicit_source_paths(tmp_path: Path) -> None:
    paths = create_sources(tmp_path)
    with pytest.raises(ValueError, match="MUST_BE_DISTINCT"):
        load_current_relative_source(
            ReadOnlySourcePaths(paths.analysis_db, paths.analysis_db, paths.market_db, paths.taxonomy_db),
            as_of_date="2026-09-01",
        )


def test_rehearsal_is_byte_deterministic_and_leaves_sources_unchanged(tmp_path: Path) -> None:
    paths = create_sources(tmp_path)
    source_paths = (paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
    }
    output = tmp_path / "output"
    report = run_full_universe_rehearsal(
        paths,
        as_of_date="2026-09-01",
        freshness_days=180,
        output_dir=output,
    )
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
    }
    assert before == after
    assert report["replay_bytes_identical"] is True
    assert (output / "relative_snapshot_run1.json").read_bytes() == (
        output / "relative_snapshot_run2.json"
    ).read_bytes()
    assert report["taxonomy_layer_scope_present"] is False


def test_rehearsal_cli_has_only_explicit_read_only_inputs_and_no_apply_path() -> None:
    parser = build_parser()
    destinations = {action.dest for action in parser._actions}
    assert {"analysis_db", "canonical_db", "market_db", "taxonomy_db", "as_of_date", "output_dir"} <= destinations
    assert "apply" not in destinations
    with pytest.raises(SystemExit):
        parser.parse_args([])
