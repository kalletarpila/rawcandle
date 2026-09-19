from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rawcandle.fundamentals.admin.operation_report import render_operation_report
from rawcandle.fundamentals.admin.ticker_reporting import (
    build_preview_reporting,
    enrich_after_state,
    render_ticker_sections,
)


def _databases(tmp_path: Path) -> SimpleNamespace:
    paths = SimpleNamespace(
        canonical_db=tmp_path / "canonical.db",
        analysis_db=tmp_path / "analysis.db",
        taxonomy_db=tmp_path / "taxonomy.db",
    )
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.executescript(
            "CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT,exchange TEXT,active INTEGER);"
            "INSERT INTO security VALUES(10,1,'FULL','NASDAQ',1);"
        )
    with sqlite3.connect(paths.analysis_db) as connection:
        connection.executescript(
            "CREATE TABLE score_result(company_id INTEGER,quarter_id INTEGER,readiness_status TEXT,missing_input_reason TEXT);"
            "CREATE TABLE lifecycle_revised_result(company_id INTEGER,fiscal_sequence INTEGER,lifecycle_status TEXT,reason_code TEXT);"
            "CREATE TABLE valuation_revised_result(company_id INTEGER,fiscal_sequence INTEGER,valuation_status TEXT,reason_code TEXT);"
            "CREATE TABLE relative_position_active_snapshot(snapshot_id TEXT);"
            "CREATE TABLE relative_position_result(snapshot_id TEXT,company_id INTEGER,peer_scope TEXT,result_status TEXT);"
            "CREATE TABLE relative_position_coverage(snapshot_id TEXT,company_id INTEGER,coverage_status TEXT);"
            "CREATE TABLE relative_valuation_active_snapshot(snapshot_id TEXT);"
            "CREATE TABLE relative_valuation_company_result(snapshot_id TEXT,company_id INTEGER,valuation_status TEXT,valuation_reason TEXT);"
            "INSERT INTO score_result VALUES(1,2,'FULL',NULL);"
            "INSERT INTO lifecycle_revised_result VALUES(1,2,'READY','CURRENT_STATE_READY');"
            "INSERT INTO valuation_revised_result VALUES(1,2,'VALUATION_FULL','READY');"
            "INSERT INTO relative_position_active_snapshot VALUES('rp');"
            "INSERT INTO relative_position_result VALUES('rp',1,'UNIVERSE','RELATIVE_POSITION_READY');"
            "INSERT INTO relative_position_result VALUES('rp',1,'ECOSYSTEM','RELATIVE_POSITION_READY');"
            "INSERT INTO relative_valuation_active_snapshot VALUES('rv');"
            "INSERT INTO relative_valuation_company_result VALUES('rv',1,'VALUATION_FULL','READY');"
        )
    with sqlite3.connect(paths.taxonomy_db) as connection:
        connection.executescript(
            "CREATE TABLE ec_ecosystem(ecosystem_id INTEGER,ecosystem_code TEXT,status TEXT);"
            "CREATE TABLE ec_taxonomy_version(taxonomy_version_id INTEGER,ecosystem_id INTEGER,is_active INTEGER,status TEXT);"
            "CREATE TABLE ec_entity(entity_id INTEGER,entity_type TEXT,entity_code TEXT,entity_name TEXT,ticker TEXT,status TEXT);"
            "CREATE TABLE ec_membership(child_entity_id INTEGER,parent_entity_id INTEGER,taxonomy_version_id INTEGER,membership_role TEXT,status TEXT);"
            "INSERT INTO ec_ecosystem VALUES(1,'DATACENTER','ACTIVE');"
            "INSERT INTO ec_taxonomy_version VALUES(1,1,1,'ACTIVE');"
            "INSERT INTO ec_entity VALUES(1,'TICKER','FULL','Full Co','FULL','ACTIVE');"
            "INSERT INTO ec_entity VALUES(2,'GROUP_L1','COMPUTE','Compute','', 'ACTIVE');"
            "INSERT INTO ec_entity VALUES(3,'GROUP_L2','ACCELERATOR','Accelerators','', 'ACTIVE');"
            "INSERT INTO ec_entity VALUES(4,'GROUP_L2','WATCH','Watch list','', 'ACTIVE');"
            "INSERT INTO ec_membership VALUES(1,2,1,'CORE','ACTIVE');"
            "INSERT INTO ec_membership VALUES(1,3,1,'EXTENDED','ACTIVE');"
            "INSERT INTO ec_membership VALUES(1,4,1,'WATCH_ONLY','ACTIVE');"
        )
    return paths


def _item(ticker: str, *, source: str, canonical: bool = False, v2: bool = True, rows=()) -> dict:
    return {
        "ticker": ticker,
        "status": "ELIGIBLE",
        "reason": "Eligible",
        "source_category": source,
        "provider_metadata": {"identity": {"name": f"{ticker} Co", "exchange": "NASDAQ"}},
        "market": {"markets": ["usa"]},
        "classification": {"status": "READY", "sector": "Technology", "industry": "Semiconductors"},
        "canonical": {"exists": canonical, "company_id": 1 if canonical and v2 else None},
        "rows": list(rows),
    }


def test_preview_contract_preserves_before_source_coverage_classification_and_taxonomy(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    rows = [
        {"dimension": "ARQ", "fiscalperiod": "2016-Q1", "reportperiod": "2016-03-31"},
        {"dimension": "ARQ", "fiscalperiod": "2026-Q2", "reportperiod": "2026-06-30"},
        {"dimension": "MRY", "fiscalperiod": "2025-FY", "reportperiod": "2025-12-31"},
    ]
    plan = {
        "items": [_item("FULL", source="verified_archive", canonical=True, rows=rows)],
        "network": {"calls": []},
    }

    report = build_preview_reporting(paths, plan)[0]

    assert report["before"] == {
        "category": "Canonical identity already present",
        "provider_data": False,
        "canonical_identity": True,
        "v2_analysis": True,
    }
    assert report["acquisition"] == {
        "source": "Verified local archive",
        "source_category": "verified_archive",
        "network_requested": False,
        "network_used": False,
    }
    assert report["coverage"] == {
        "provider_rows": 3,
        "arq_count": 2,
        "first_fiscal_quarter": "2016 Q1",
        "latest_fiscal_quarter": "2026 Q2",
    }
    assert report["classification"] == {
        "sector": "Technology", "industry": "Semiconductors", "authority": "ticker_meta",
    }
    assert report["taxonomy"]["roles"] == ["CORE", "EXTENDED", "WATCH_ONLY"]
    assert report["after"]["analysis"] == "Not calculated during Preview"


def test_before_state_and_acquisition_categories_cover_new_local_canonical_and_complete(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    plan = {
        "items": [
            _item("NEW", source="verified_archive"),
            _item("LOCAL", source="local_provider"),
            _item("CANON", source="verified_archive", canonical=True, v2=False),
            _item("FULL", source="local_provider", canonical=True),
            _item("MISS", source="network_unavailable"),
            _item("NET", source="network"),
        ],
        "network": {"calls": [{"ticker": "MISS", "status": "NOT_FOUND"}, {"ticker": "NET", "status": "SUCCESS"}]},
    }

    reports = {item["ticker"]: item for item in build_preview_reporting(paths, plan)}

    assert reports["NEW"]["before"]["category"] == "New"
    assert reports["LOCAL"]["before"]["category"] == "Provider data already present"
    assert reports["CANON"]["before"]["category"] == "Canonical identity already present"
    assert reports["FULL"]["before"]["category"] == "Already fully present"
    assert reports["MISS"]["acquisition"]["source"] == "No usable fundamentals found"
    assert reports["MISS"]["acquisition"]["network_requested"] is True
    assert reports["NET"]["acquisition"]["source"] == "Network"
    assert reports["NET"]["acquisition"]["network_used"] is True


def test_copy_and_production_after_state_reports_v2_rp_and_rv(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    preview = build_preview_reporting(paths, {
        "items": [_item("FULL", source="local_provider", canonical=True)],
        "network": {"calls": []},
    })

    copied = enrich_after_state(preview, paths, stage="COPY_ONLY_APPLY", final_actions={"FULL": "Tested successfully"})[0]
    produced = enrich_after_state(preview, paths, stage="PRODUCTION_APPLY", final_actions={"FULL": "Updated"})[0]

    assert copied["after"]["analysis"]["score"]["status"] == "FULL"
    assert copied["after"]["analysis"]["lifecycle"]["status"] == "READY"
    assert copied["after"]["analysis"]["valuation"]["status"] == "VALUATION_FULL"
    assert copied["after"]["analysis"]["rp_v2"] == {
        "total_results": 2, "ecosystem_results": 1,
        "status": "RELATIVE_POSITION_READY", "reason": None,
    }
    assert copied["after"]["analysis"]["rv"]["status"] == "VALUATION_FULL"
    assert copied["final_action"] == "Tested successfully"
    assert produced["final_action"] == "Updated"


def test_non_ready_analysis_and_zero_rp_rv_results_keep_reasons(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("INSERT INTO security VALUES(20,2,'LIMITED','NYSE',1)")
    with sqlite3.connect(paths.analysis_db) as connection:
        connection.execute("INSERT INTO score_result VALUES(2,3,'LIMITED','TTM_SOURCE_MEASURE_UNAVAILABLE')")
        connection.execute("INSERT INTO lifecycle_revised_result VALUES(2,3,'NOT_READY','INSUFFICIENT_HISTORY')")
        connection.execute("INSERT INTO valuation_revised_result VALUES(2,3,'VALUATION_NOT_APPLICABLE','SECTOR_POLICY_EXCLUDED')")
        connection.execute("INSERT INTO relative_position_coverage VALUES('rp',2,'NOT_ECOSYSTEM_MEMBER')")
    preview = build_preview_reporting(paths, {
        "items": [_item("LIMITED", source="local_provider", canonical=True)],
        "network": {"calls": []},
    })

    analysis = enrich_after_state(preview, paths, stage="COPY_ONLY_APPLY")[0]["after"]["analysis"]

    assert analysis["score"] == {"status": "LIMITED", "reason": "TTM_SOURCE_MEASURE_UNAVAILABLE"}
    assert analysis["lifecycle"] == {"status": "NOT_READY", "reason": "INSUFFICIENT_HISTORY"}
    assert analysis["valuation"] == {"status": "VALUATION_NOT_APPLICABLE", "reason": "SECTOR_POLICY_EXCLUDED"}
    assert analysis["rp_v2"]["total_results"] == 0
    assert analysis["rp_v2"]["reason"] == "NOT_ECOSYSTEM_MEMBER"
    assert analysis["rv"] == {"included": False, "status": "Not eligible", "reason": None}


def test_ticker_report_layout_is_stage_aware_and_duration_is_not_duplicated(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    preview = build_preview_reporting(paths, {
        "items": [_item("FULL", source="verified_archive", canonical=True)],
        "network": {"calls": []},
    })
    detail = render_ticker_sections(preview)
    operation = render_operation_report(
        run_id="run",
        result={
            "run_id": "run", "operation_type": "ADD_TICKERS", "mode": "PREVIEW", "outcome": "COMPLETED",
            "started_at_utc": "2026-09-19T00:00:00Z", "completed_at_utc": "2026-09-19T00:01:02Z",
            "ticker_reporting": preview,
        },
    )

    assert "## Ticker Summary" in detail
    assert "### FULL - FULL Co" in detail
    assert "Not calculated during Preview" in detail
    assert "Duration: 1 min 2 sec" in operation
    assert "Completed in 1 min 2 sec" not in operation
