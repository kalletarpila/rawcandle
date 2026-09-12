from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13f1_reconciliation import (
    AREB_COMPANY_ID,
    AuditPaths,
    _normalize,
    _rank_after_removal,
    areb_relative_position_audit,
    classification_reconciliation,
    run_audit,
)


def _canonical(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE company(company_id INTEGER PRIMARY KEY,company_key TEXT,company_name TEXT,status TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,exchange TEXT,active INTEGER,valid_from TEXT,valid_to TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,ticker TEXT,provider TEXT,valid_from TEXT,valid_to TEXT,source TEXT);
            CREATE TABLE fundamentals_operational_universe_active_version(universe_version_id TEXT PRIMARY KEY);
            CREATE TABLE fundamentals_operational_universe_version(universe_version_id TEXT PRIMARY KEY,contract_version TEXT,semantic_mode TEXT,as_of_date TEXT,source_fingerprint TEXT,economic_result_fingerprint TEXT,physical_content_fingerprint TEXT,status TEXT,member_count INTEGER,company_count INTEGER,active_security_count INTEGER,zero_active_company_count INTEGER,multi_active_company_count INTEGER,created_at_utc TEXT,completed_at_utc TEXT);
            CREATE TABLE fundamentals_operational_universe_member(universe_version_id TEXT,company_id INTEGER,security_id INTEGER,current_ticker TEXT,market TEXT,membership_status TEXT,identity_resolution_status TEXT,active_security_count INTEGER,all_security_count INTEGER,effective_start_date TEXT,effective_end_date TEXT,source TEXT,reason TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            INSERT INTO fundamentals_operational_universe_active_version VALUES ('u1');
            INSERT INTO fundamentals_operational_universe_version VALUES ('u1','c','CURRENT','2026-09-12','s','e','p','COMPLETE',2,2,2,0,0,'n','n');
            INSERT INTO company VALUES (1,'C1','One','ACTIVE','n','n'),(192,'C192','AREB','ACTIVE','n','n');
            INSERT INTO security VALUES (1,1,'ONE','NASDAQ',1,'2020-01-01',NULL,'n','n'),(192,192,'AREB','NASDAQ',0,'2022-02-07','2026-05-12','n','n');
            INSERT INTO fundamentals_operational_universe_member VALUES
                ('u1',1,1,'ONE','usa','ACTIVE_SINGLE_SECURITY','RESOLVED',1,1,'2020-01-01',NULL,'test','ok','n','n'),
                ('u1',192,192,'AREB','usa','ACTIVE_SINGLE_SECURITY','RESOLVED',1,1,'2022-02-07',NULL,'test','bad','n','n');
        """)


def _market(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE ticker_meta(ticker TEXT,market TEXT,sector TEXT,industry TEXT);
            CREATE TABLE osakedata(osake TEXT,pvm TEXT,market TEXT,open REAL,high REAL,low REAL,close REAL);
            INSERT INTO ticker_meta VALUES
                ('ONE','usa','Technology','Software - Application'),
                ('AREB','usa','Consumer Cyclical','Footwear & Accessories');
            INSERT INTO osakedata VALUES ('ONE','2026-09-12','usa',1,1,1,1),('AREB','2026-09-12','usa',1,1,1,1);
        """)


def _provider(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE sharadar_ticker_metadata(table_name TEXT,ticker TEXT,permaticker TEXT,name TEXT,exchange TEXT,isdelisted TEXT,category TEXT,relatedtickers TEXT,secfilings TEXT,firstpricedate TEXT,lastpricedate TEXT,firstquarter TEXT,lastquarter TEXT,lastupdated TEXT,payload_json TEXT,fetched_at_utc TEXT);
            INSERT INTO sharadar_ticker_metadata VALUES
                ('fundamentals','ONE','1','One','NASDAQ','N','Domestic Common Stock','','','2020-01-01','2026-09-12','','','','{}','n'),
                ('fundamentals','AREB','637535','AREB','NASDAQ','Y','Domestic Common Stock','','','2022-02-07','2026-05-12','','','','{}','n');
        """)


def _analysis(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE valuation_revised_result(valuation_revised_result_id INTEGER PRIMARY KEY,company_id INTEGER,security_id INTEGER,ticker TEXT,fiscal_sequence INTEGER,sector TEXT,industry TEXT,valuation_status TEXT,reason_code TEXT,history_mode TEXT);
            INSERT INTO valuation_revised_result VALUES
                (1,1,1,'ONE',1,'Technology','Software - Application','VALUATION_FULL','VALUATION_FULL','REVISED_HISTORY'),
                (2,192,192,'AREB',1,'Consumer Cyclical','Footwear & Accessories','VALUATION_FULL','VALUATION_FULL','REVISED_HISTORY');
            CREATE TABLE relative_position_active_snapshot(model_fingerprint TEXT PRIMARY KEY,snapshot_id TEXT,activated_at_utc TEXT);
            CREATE TABLE relative_position_snapshot(snapshot_id TEXT PRIMARY KEY,model_version TEXT,model_fingerprint TEXT,semantic_mode TEXT,snapshot_date TEXT,calculation_source_fingerprint TEXT,source_content_fingerprint TEXT,result_fingerprint TEXT,status TEXT,result_row_count INTEGER,coverage_row_count INTEGER,ready_row_count INTEGER,created_at_utc TEXT,completed_at_utc TEXT);
            CREATE TABLE relative_position_result(relative_position_result_id INTEGER PRIMARY KEY,snapshot_id TEXT,company_id INTEGER,security_id INTEGER,ticker TEXT,measure TEXT,peer_scope TEXT,peer_group_id TEXT,source_observation_id TEXT,source_observation_date TEXT,source_score REAL,percentile REAL,rank_low INTEGER,rank_high INTEGER,average_rank REAL,peer_count INTEGER,tie_count INTEGER,result_status TEXT,reason_code TEXT,model_version TEXT,model_fingerprint TEXT);
            INSERT INTO relative_position_active_snapshot VALUES ('m','s','n');
            INSERT INTO relative_position_snapshot VALUES ('s','M','m','CURRENT','2026-09-12','c','s','r','COMPLETE',4,4,4,'n','n');
            INSERT INTO relative_position_result VALUES
                (1,'s',1,1,'ONE','FUNDAMENTAL_SCORE','SECTOR','Technology','score:1','2026-09-12',50,100,2,2,2,2,1,'RELATIVE_POSITION_READY','PERCENTILE_CALCULATED','M','m'),
                (2,'s',1,1,'ONE','FUNDAMENTAL_SCORE','INDUSTRY','Software - Application','score:1','2026-09-12',50,100,1,1,1,1,1,'RELATIVE_POSITION_READY','PERCENTILE_CALCULATED','M','m'),
                (3,'s',192,192,'AREB','FUNDAMENTAL_SCORE','SECTOR','Consumer Cyclical','score:192','2026-09-12',1,0,1,1,1,2,1,'RELATIVE_POSITION_READY','PERCENTILE_CALCULATED','M','m');
            CREATE TABLE relative_valuation_active_snapshot(model_fingerprint TEXT PRIMARY KEY,snapshot_id TEXT,activated_at_utc TEXT);
            CREATE TABLE relative_valuation_snapshot(snapshot_id TEXT PRIMARY KEY,model_version TEXT,model_fingerprint TEXT,persistence_version TEXT,layout_fingerprint TEXT,semantic_mode TEXT,as_of_date TEXT,calculated_at_utc TEXT,source_fingerprint TEXT,result_fingerprint TEXT,physical_content_fingerprint TEXT,market_price_start_date TEXT,market_price_end_date TEXT,status TEXT,company_count INTEGER,current_fresh_count INTEGER,current_peer_eligible_count INTEGER,own_history_ready_count INTEGER,own_history_limited_count INTEGER,created_at_utc TEXT,completed_at_utc TEXT);
            CREATE TABLE relative_valuation_peer_position(snapshot_id TEXT,company_id INTEGER,scope TEXT,group_id TEXT,status TEXT,reason_code TEXT,percentile REAL,peer_count INTEGER,rank_low INTEGER,rank_high INTEGER,average_rank REAL,source_score REAL);
        """)


def _paths(tmp_path: Path) -> AuditPaths:
    canonical, analysis, market, provider, taxonomy = (tmp_path / name for name in ("c.db", "a.db", "m.db", "p.db", "t.db"))
    _canonical(canonical)
    _analysis(analysis)
    _market(market)
    _provider(provider)
    sqlite3.connect(taxonomy).close()
    return AuditPaths(canonical=canonical, analysis=analysis, market=market, provider=provider, taxonomy=taxonomy)


def test_exact_and_normalized_classification_reconciliation(tmp_path: Path) -> None:
    result = classification_reconciliation(_paths(tmp_path))

    assert result["summary"]["primary_active_security_rows"] == 2
    assert result["summary"]["exact_matches"] == 2
    assert result["summary"]["missing_ticker_meta_row"] == 0
    areb = next(row for row in result["rows"] if row["company_id"] == AREB_COMPANY_ID)
    assert areb["exact_match_status"] == "EXACT_MATCH"
    assert _normalize("  Footwear   & Accessories ") == "footwear & accessories"


def test_areb_relative_position_row_existence_is_distinguished_from_participation(tmp_path: Path) -> None:
    result = areb_relative_position_audit(_paths(tmp_path))

    assert result["active_row_count"] == 1
    assert result["ready_row_count"] == 1
    assert result["conclusion"] == "PRODUCTION_DEFECT_AREB_PARTICIPATES_IN_CURRENT_RELATIVE_POSITION"


def test_counterfactual_rank_after_removal_changes_peer_denominator() -> None:
    rows = [
        {"company_id": 1, "source_score": 50.0},
        {"company_id": AREB_COMPANY_ID, "source_score": 1.0},
    ]
    recalculated = _rank_after_removal(rows, AREB_COMPANY_ID)

    assert recalculated[1]["peer_count"] == 1
    assert recalculated[1]["percentile"] is None


def test_protected_production_output_refusal() -> None:
    with pytest.raises(PermissionError):
        run_audit(PRODUCTION["canonical"])
