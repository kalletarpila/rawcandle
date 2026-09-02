from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.delta.source import ReadOnlyDeltaPaths, latest_fresh_observations, load_delta_source
from rawcandle.fundamentals.delta.rehearsal import RehearsalPaths, run_full_history_rehearsal
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_FP, MODEL_VERSION as LIFECYCLE_VERSION
from rawcandle.fundamentals.score.engine import COMPONENTS, MODEL_FINGERPRINT as SCORE_FP, MODEL_VERSION as SCORE_VERSION
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_FP, MODEL_VERSION as VALUATION_VERSION


def build_databases(root: Path, *, duplicate_score: bool = False) -> ReadOnlyDeltaPaths:
    root.mkdir(parents=True, exist_ok=True)
    analysis = root / "analysis.db"
    canonical = root / "canonical.db"
    with sqlite3.connect(canonical) as conn:
        conn.executescript("""
        CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,period_end TEXT,source_availability_date TEXT);
        CREATE TABLE v4_ttm_values(ttm_id INTEGER PRIMARY KEY,company_id INTEGER,endpoint_quarter_id INTEGER,model_version TEXT,readiness_status TEXT,output_fingerprint TEXT);
        CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT);
        INSERT INTO security VALUES(1,1,'TEST');
        """)
        for index in range(1, 6):
            year = 2024 + (index // 5)
            conn.execute("INSERT INTO v4_quarter VALUES(?,?,?,?,?,?)", (index, 1, year, f"Q{((index-1)%4)+1}", f"{year}-{((index-1)%4+1)*3:02d}-28", f"{year}-{((index-1)%4+1)*3:02d}-29"))
            conn.execute("INSERT INTO v4_ttm_values VALUES(?,?,?,?,?,?)", (index, 1, index, "V4_TTM_EBIT_FIRST_V1", "TTM_READY", f"ttm:{index}"))
    with sqlite3.connect(analysis) as conn:
        conn.executescript("""
        CREATE TABLE score_result(score_result_id INTEGER PRIMARY KEY,company_id INTEGER,quarter_id INTEGER,model_version TEXT,model_fingerprint TEXT,total_score REAL,readiness_status TEXT,missing_input_reason TEXT,generated_at_utc TEXT,run_id TEXT);
        CREATE TABLE score_component(score_component_id INTEGER PRIMARY KEY,score_result_id INTEGER,component_name TEXT,component_score REAL,evidence_json TEXT);
        CREATE TABLE lifecycle_revised_result(lifecycle_revised_result_id INTEGER PRIMARY KEY,company_id INTEGER,security_id INTEGER,ticker TEXT,quarter_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,fiscal_sequence INTEGER,period_end TEXT,source_available_date TEXT,history_mode TEXT,model_version TEXT,model_fingerprint TEXT,source_input_fingerprint TEXT,raw_state TEXT,final_state TEXT,lifecycle_status TEXT,startup_profile TEXT,final_startup_profile TEXT,reason_code TEXT,transition_reason TEXT,missing_inputs_json TEXT,last_confirmed_state TEXT,candidate_state TEXT,candidate_count INTEGER,revenue_growth_yoy_ttm REAL,ebit_margin_ttm REAL,ebit_margin_direction REAL,fcf_margin_ttm REAL,evidence_json TEXT,generated_at_utc TEXT);
        CREATE TABLE valuation_revised_result(valuation_revised_result_id INTEGER PRIMARY KEY,company_id INTEGER,security_id INTEGER,ticker TEXT,security_active INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,fiscal_sequence INTEGER,quarter_id INTEGER,period_end TEXT,fundamental_available_date TEXT,price_date TEXT,price_age_calendar_days INTEGER,selected_price REAL,shares_outstanding REAL,market_cap REAL,cash REAL,total_debt REAL,net_debt REAL,enterprise_value REAL,ttm_ebit REAL,ttm_free_cashflow REAL,ttm_net_income_common REAL,ebit_yield REAL,ebit_points REAL,fcf_yield REAL,fcf_points REAL,earnings_yield REAL,earnings_points REAL,total_valuation_score REAL,valuation_status TEXT,reason_code TEXT,applicability_classification TEXT,sector TEXT,industry TEXT,model_version TEXT,model_fingerprint TEXT,source_fingerprint TEXT,engine_result_fingerprint TEXT,result_fingerprint TEXT,history_mode TEXT,calculated_at_utc TEXT);
        """)
        component_id = 1
        maxima = {"REVENUE_GROWTH":20,"EBIT_PROFITABILITY":15,"EBIT_MARGIN_DIRECTION":15,"FCF_MARGIN":15,"BALANCE_SHEET_RESILIENCE":15,"DILUTION":10,"FUNDAMENTAL_TRAJECTORY":10}
        for index in range(1, 6):
            year, quarter = (2024, f"Q{index}") if index < 5 else (2025, "Q1")
            seq = year * 4 + int(quarter[1])
            conn.execute("INSERT INTO score_result VALUES(?,?,?,?,?,?,?,?,?,?)", (index,1,index,SCORE_VERSION,SCORE_FP,50,"SCORE_FULL",json.dumps({"imputed_components":[]}),"n","r"))
            for name in COMPONENTS:
                conn.execute("INSERT INTO score_component VALUES(?,?,?,?,?)", (component_id,index,name,maxima[name]/2,json.dumps({"value_status":"OBSERVED"})))
                component_id += 1
            common = (index,1,1,"TEST",index,year,quarter,seq,f"{year}-{int(quarter[1])*3:02d}-28",f"{year}-{int(quarter[1])*3:02d}-29")
            conn.execute("INSERT INTO lifecycle_revised_result VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", common + ("REVISED_HISTORY",LIFECYCLE_VERSION,LIFECYCLE_FP,f"ls:{index}","MATURE","MATURE","LIFECYCLE_READY",None,None,"R","T","[]","MATURE",None,0,0.1,0.2,0.0,0.1,"{}","n"))
            conn.execute("INSERT INTO valuation_revised_result VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (index,1,1,"TEST",1,year,quarter,seq,index,f"{year}-{int(quarter[1])*3:02d}-28",f"{year}-{int(quarter[1])*3:02d}-29",f"{year}-{int(quarter[1])*3:02d}-29",0,10,1,10,1,1,0,10,1,1,1,.1,20,.1,20,.1,10,50,"VALUATION_FULL","READY","SUPPORTED","Technology","Software",VALUATION_VERSION,VALUATION_FP,f"vs:{index}",f"ve:{index}",f"vr:{index}","REVISED_HISTORY","n"))
        if duplicate_score:
            conn.execute("INSERT INTO score_result VALUES(99,1,5,?,?,?,?,?,?,?)", (SCORE_VERSION,SCORE_FP,50,"SCORE_FULL",json.dumps({"imputed_components":[]}),"n","r"))
    return ReadOnlyDeltaPaths(analysis.resolve(), canonical.resolve())


def test_read_only_adapter_loads_deterministically_and_preserves_status(tmp_path):
    paths = build_databases(tmp_path)
    before = (paths.analysis_db.stat().st_size, paths.analysis_db.stat().st_mtime_ns)
    first = load_delta_source(paths, score_model_fingerprint=SCORE_FP, lifecycle_model_fingerprint=LIFECYCLE_FP, valuation_model_fingerprint=VALUATION_FP)
    second = load_delta_source(paths, score_model_fingerprint=SCORE_FP, lifecycle_model_fingerprint=LIFECYCLE_FP, valuation_model_fingerprint=VALUATION_FP)
    assert first.source_fingerprint == second.source_fingerprint
    assert len(first.score_histories[1]) == len(first.lifecycle_histories[1]) == len(first.valuation_histories[1]) == 5
    assert first.score_histories[1][0].readiness_status == "SCORE_FULL"
    assert latest_fresh_observations(first.score_histories, as_of_date="2025-04-01", freshness_days=180)[0].fiscal.fiscal_quarter == "Q1"
    assert before == (paths.analysis_db.stat().st_size, paths.analysis_db.stat().st_mtime_ns)


def test_wrong_fingerprint_and_duplicate_are_rejected(tmp_path):
    paths = build_databases(tmp_path / "one")
    with pytest.raises(ValueError, match="SCORE_MODEL_FINGERPRINT_REJECTED"):
        load_delta_source(paths, score_model_fingerprint="wrong", lifecycle_model_fingerprint=LIFECYCLE_FP, valuation_model_fingerprint=VALUATION_FP)
    duplicate = build_databases(tmp_path / "two", duplicate_score=True)
    with pytest.raises(ValueError, match="DUPLICATE_SCORE_FISCAL_IDENTITY"):
        load_delta_source(duplicate, score_model_fingerprint=SCORE_FP, lifecycle_model_fingerprint=LIFECYCLE_FP, valuation_model_fingerprint=VALUATION_FP)


def test_paths_must_be_explicit_absolute_regular_files(tmp_path):
    with pytest.raises(ValueError, match="PATH_MUST_BE_ABSOLUTE"):
        load_delta_source(ReadOnlyDeltaPaths(Path("a.db"), Path("b.db")), score_model_fingerprint=SCORE_FP, lifecycle_model_fingerprint=LIFECYCLE_FP, valuation_model_fingerprint=VALUATION_FP)


def test_rehearsal_is_byte_deterministic_and_does_not_write_sources(tmp_path):
    source_paths = build_databases(tmp_path / "source")
    sources = (source_paths.analysis_db, source_paths.canonical_db)
    before = [(path.stat().st_size, path.stat().st_mtime_ns) for path in sources]
    output = tmp_path / "artifacts"
    metrics = run_full_history_rehearsal(
        RehearsalPaths(source_paths.analysis_db, source_paths.canonical_db, source_paths.analysis_db, source_paths.canonical_db, source_paths.analysis_db),
        as_of_date="2025-04-01", score_model_fingerprint=SCORE_FP,
        lifecycle_model_fingerprint=LIFECYCLE_FP, valuation_model_fingerprint=VALUATION_FP,
        output_dir=output,
    )
    assert metrics["deterministic_replay"] is True
    assert metrics["production_integrity_equal"] is True
    assert (output / "fundamental_delta_history.jsonl.gz").is_file()
    assert not list(output.glob("*.replay2"))
    assert before == [(path.stat().st_size, path.stat().st_mtime_ns) for path in sources]
