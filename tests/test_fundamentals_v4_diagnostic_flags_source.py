from __future__ import annotations

import argparse
import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_diagnostic_flags_rehearsal import run
from rawcandle.fundamentals.diagnostic_flags.engine import FLAG_NAMES
from rawcandle.fundamentals.diagnostic_flags.rehearsal import _run_once
from rawcandle.fundamentals.diagnostic_flags.source import (
    ReadOnlyDiagnosticPaths,
    latest_fresh_source_rows,
    load_diagnostic_source,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def databases(tmp_path: Path) -> ReadOnlyDiagnosticPaths:
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    with sqlite3.connect(canonical) as conn:
        conn.executescript(
            """
            CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT);
            CREATE TABLE v4_quarter(quarter_id INTEGER,company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,period_end TEXT,source_availability_date TEXT);
            CREATE TABLE v4_quarter_financials(quarter_id INTEGER,accounts_receivable REAL,inventory REAL,accounts_payable REAL,deferred_revenue REAL,total_assets REAL);
            CREATE TABLE v4_ttm_values(
              ttm_id INTEGER,company_id INTEGER,security_id INTEGER,endpoint_quarter_id INTEGER,
              endpoint_fiscal_year INTEGER,endpoint_fiscal_quarter TEXT,period_end TEXT,
              readiness_status TEXT,ttm_source_available_date TEXT,ttm_revenue REAL,ttm_ebit REAL,
              ttm_net_income_common REAL,ttm_operating_cashflow REAL,ttm_capex REAL,cash REAL,
              total_debt REAL,model_version TEXT
            );
            INSERT INTO security VALUES(1,1,'TEST');
            INSERT INTO v4_quarter VALUES
              (1,1,2025,'Q3','2025-09-30','2025-11-01'),
              (2,1,2025,'Q4','2025-12-31','2026-02-01');
            INSERT INTO v4_quarter_financials VALUES
              (1,10,5,4,1,100),(2,12,5,4,1,100);
            INSERT INTO v4_ttm_values VALUES
              (1,1,1,1,2025,'Q3','2025-09-30','TTM_READY','2025-11-02',100,10,8,9,-2,5,10,'TTM_V1'),
              (2,1,1,2,2025,'Q4','2025-12-31','TTM_READY','2026-02-02',100,10,8,9,-2,5,10,'TTM_V1');
            """
        )
    with sqlite3.connect(analysis) as conn:
        conn.executescript(
            """
            CREATE TABLE score_result(score_result_id INTEGER,quarter_id INTEGER,model_fingerprint TEXT);
            CREATE TABLE score_component(score_result_id INTEGER,component_name TEXT,component_score REAL);
            CREATE TABLE lifecycle_revised_result(quarter_id INTEGER,final_state TEXT,lifecycle_status TEXT,model_fingerprint TEXT);
            CREATE TABLE valuation_revised_result(
              quarter_id INTEGER,fundamental_available_date TEXT,valuation_status TEXT,reason_code TEXT,
              applicability_classification TEXT,ebit_yield REAL,fcf_yield REAL,earnings_yield REAL,
              sector TEXT,industry TEXT,market_cap REAL,model_fingerprint TEXT
            );
            INSERT INTO score_result VALUES(1,1,'score-fp'),(2,2,'score-fp');
            INSERT INTO score_component VALUES(1,'FUNDAMENTAL_TRAJECTORY',6),(2,'FUNDAMENTAL_TRAJECTORY',8);
            INSERT INTO lifecycle_revised_result VALUES(1,'MATURE','READY','life-fp'),(2,'MATURE','READY','life-fp');
            INSERT INTO valuation_revised_result VALUES
              (1,'2025-11-03','VALUATION_FULL','READY','SUPPORTED',.1,.1,.1,'Technology','Software',1000,'val-fp'),
              (2,'2026-02-03','VALUATION_FULL','READY','SUPPORTED',.1,.1,.1,'Technology','Software',1000,'val-fp');
            """
        )
    return ReadOnlyDiagnosticPaths(canonical, analysis)


def test_source_resolves_exact_prior_and_preserves_databases(tmp_path: Path):
    paths = databases(tmp_path)
    before = (sha256(paths.canonical_db), sha256(paths.analysis_db))
    source = load_diagnostic_source(paths)
    after = (sha256(paths.canonical_db), sha256(paths.analysis_db))
    assert before == after
    assert len(source.rows) == 2
    assert source.rows[0].diagnostic_input.prior is None
    assert source.rows[1].diagnostic_input.prior.quarter_id == 1
    assert source.rows[1].diagnostic_input.fiscal_chain_consecutive is True
    assert source.source_model_fingerprints == (
        ("score", "score-fp"),
        ("lifecycle", "life-fp"),
        ("valuation", "val-fp"),
    )


def test_current_fresh_resolution_is_explicit_and_deterministic(tmp_path: Path):
    source = load_diagnostic_source(databases(tmp_path))
    fresh = latest_fresh_source_rows(source.rows, as_of=date(2026, 3, 1), freshness_days=60)
    stale = latest_fresh_source_rows(source.rows, as_of=date(2027, 3, 1), freshness_days=60)
    assert [row.diagnostic_input.current.quarter_id for row in fresh] == [2]
    assert stale == ()


def test_normalized_full_replay_is_byte_identical(tmp_path: Path):
    source = load_diagnostic_source(databases(tmp_path))
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first_sha, records = _run_once(source, first, collect=True, current_ids={2})
    second_sha, _ = _run_once(source, second, collect=False)
    assert first_sha == second_sha
    assert first.read_bytes() == second.read_bytes()
    assert len(records) == len(source.rows) * len(FLAG_NAMES)


def test_cli_refuses_output_outside_rehearsal_root(tmp_path: Path):
    paths = databases(tmp_path)
    args = argparse.Namespace(
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        output_dir=tmp_path / "unsafe-output",
        as_of=date(2026, 3, 1),
        freshness_days=180,
    )
    with pytest.raises(PermissionError, match="PHASE6B_OUTPUT_MUST_BE_UNDER_REHEARSAL_ROOT"):
        run(args)
