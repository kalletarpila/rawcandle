from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rawcandle.fundamentals.admin.operation_report import render_operation_report
from rawcandle.fundamentals.admin.ticker_reporting import (
    build_preview_reporting,
    enrich_after_state,
    reporting_counts,
    render_ticker_sections,
    summary_rows,
)


def _databases(tmp_path: Path) -> SimpleNamespace:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
            "CREATE TABLE lifecycle_revised_result(company_id INTEGER,fiscal_sequence INTEGER,lifecycle_status TEXT,final_state TEXT,reason_code TEXT);"
            "CREATE TABLE valuation_revised_result(company_id INTEGER,fiscal_sequence INTEGER,valuation_status TEXT,reason_code TEXT);"
            "CREATE TABLE relative_position_active_snapshot(snapshot_id TEXT);"
            "CREATE TABLE relative_position_result(snapshot_id TEXT,company_id INTEGER,peer_scope TEXT,result_status TEXT);"
            "CREATE TABLE relative_position_coverage(snapshot_id TEXT,company_id INTEGER,coverage_status TEXT,reason_code TEXT);"
            "CREATE TABLE relative_valuation_active_snapshot(snapshot_id TEXT);"
            "CREATE TABLE relative_valuation_company_result(snapshot_id TEXT,company_id INTEGER,valuation_status TEXT,valuation_reason TEXT);"
            "INSERT INTO score_result VALUES(1,2,'FULL',NULL);"
            "INSERT INTO lifecycle_revised_result VALUES(1,2,'READY','SCALING','CURRENT_STATE_READY');"
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
        connection.execute("INSERT INTO lifecycle_revised_result VALUES(2,3,'NOT_READY',NULL,'INSUFFICIENT_HISTORY')")
        connection.execute("INSERT INTO valuation_revised_result VALUES(2,3,'VALUATION_NOT_APPLICABLE','SECTOR_POLICY_EXCLUDED')")
        connection.execute("INSERT INTO relative_position_coverage VALUES('rp',2,'NOT_COVERED','NOT_ECOSYSTEM_MEMBER')")
    preview = build_preview_reporting(paths, {
        "items": [_item("LIMITED", source="local_provider", canonical=True)],
        "network": {"calls": []},
    })

    analysis = enrich_after_state(preview, paths, stage="COPY_ONLY_APPLY")[0]["after"]["analysis"]

    assert analysis["score"] == {
        "status": "LIMITED", "reason": "ttm source measure unavailable",
        "technical_reason": "TTM_SOURCE_MEASURE_UNAVAILABLE",
    }
    assert analysis["lifecycle"] == {"status": "NOT_READY", "state": None, "reason": "INSUFFICIENT_HISTORY"}
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
    assert "Existing V2 analysis" in detail
    assert "Duration: 1 min 2 sec" in operation
    assert "Completed in 1 min 2 sec" not in operation
    assert "Next step: run Test on copies." in operation


def test_preview_semantics_reconcile_mixed_states_and_explain_review(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    arq_rows = [
        {"dimension": "ARQ", "fiscalperiod": "2025-Q1", "reportperiod": "2025-03-31"},
        {"dimension": "ARQ", "fiscalperiod": "2026-Q2", "reportperiod": "2026-06-30"},
    ]
    zero_arq = [{"dimension": "MRY", "fiscalperiod": "2025-FY", "reportperiod": "2025-12-31"}]
    eligible = _item("NEW", source="verified_archive", rows=arq_rows)
    zero = _item("ZERO", source="verified_archive", rows=zero_arq)
    review = _item("PLPC", source="verified_archive", rows=arq_rows)
    review["status"] = "REVIEW_REQUIRED"
    review["reason"] = "MARKET_NOT_UNAMBIGUOUS_USA,MISSING_CLASSIFICATION"
    review["classification"] = {"status": "MISSING", "sector": None, "industry": None}
    complete = _item("FULL", source="local_provider", canonical=True, rows=arq_rows)
    incomplete = _item("INCOMP", source="local_provider", canonical=True, v2=False, rows=zero_arq)
    for existing in (complete, incomplete):
        existing["status"] = "ALREADY_PRESENT"
        existing["reason"] = "Ticker is already present in canonical identities."
    reports = build_preview_reporting(paths, {
        "items": [eligible, zero, review, complete, incomplete],
        "network": {"calls": []},
    })
    result = {
        "run_id": "mixed", "operation_type": "ADD_TICKERS", "mode": "PREVIEW",
        "outcome": "COMPLETED", "ticker_reporting": reports,
    }

    report = render_operation_report(run_id="mixed", result=result)
    counts = reporting_counts(reports)

    assert counts == {
        "requested": 5, "new": 3, "eligible": 2, "already_present": 2,
        "review_required": 1, "rejected": 0, "network": 0, "taxonomy": 1,
    }
    assert "5 tickers requested: 3 new, 2 already present." in report
    assert "Eligible to add: 2. Review required: 1. Rejected: 0." in report
    assert "## Items Requiring Review" in report
    assert "USA market listing could not be confirmed unambiguously" in report
    assert "Sector/Industry classification is missing" in report
    assert "No operation-level blockers were found." in report
    assert "1 ticker requires review." in report
    assert "Next step: resolve review items if needed, then run Test on copies." in report
    assert "No warnings or blockers were found." not in report
    assert "FULL: Already present - complete." in report
    assert "INCOMP: Already present - V2 analysis incomplete." in report
    assert "| ZERO | New | Verified local archive; no network | 0 ARQ |" in report
    assert "Provider data exists, but no usable quarterly ARQ history was identified." in report
    assert "Classification unavailable" in report
    assert "Canonical identity: Not present - will be created if applied" in report
    assert "Canonical identity: Not present - pending review" in report
    assert "Existing V2 analysis" in report
    assert "No existing V2 analysis" in report
    assert "Yes - CORE" not in report


def test_canonical_identity_and_final_action_wording_follow_stage(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    preview = build_preview_reporting(paths, {
        "items": [_item("NEW", source="verified_archive")],
        "network": {"calls": []},
    })
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("INSERT INTO security VALUES(30,3,'NEW','NASDAQ',1)")

    copied = enrich_after_state(
        preview, paths, stage="COPY_ONLY_APPLY",
        final_actions={"NEW": "Tested successfully - new ticker"},
    )
    produced = enrich_after_state(
        preview, paths, stage="PRODUCTION_APPLY",
        final_actions={"NEW": "Added"},
    )

    assert "Canonical identity on copies: Created" in render_ticker_sections(copied)
    assert "Tested successfully - new ticker" in render_ticker_sections(copied)
    assert any(row.startswith("Tested successfully: 1.") for row in summary_rows(copied))
    assert "Canonical identity: Created" in render_ticker_sections(produced)
    assert "- Added" in render_ticker_sections(produced)
    assert "Added: 1. Existing tickers included in rebuild: 0. Source-data updates: 0. No source change: 0." in summary_rows(produced)


def test_new_candidate_identities_resolve_full_limited_not_ready_and_not_applicable(tmp_path: Path) -> None:
    preview_paths = _databases(tmp_path / "preview")
    candidate_paths = _databases(tmp_path / "candidate")
    with sqlite3.connect(preview_paths.taxonomy_db) as connection:
        connection.execute("INSERT INTO ec_entity VALUES(10,'TICKER','NEWFULL','New Full','NEWFULL','ACTIVE')")
        connection.execute("INSERT INTO ec_membership VALUES(10,4,1,'WATCH_ONLY','ACTIVE')")
    tickers = ("NEWFULL", "NEWLIMIT", "NEWNOT", "NEWNA")
    preview = build_preview_reporting(preview_paths, {
        "items": [_item(ticker, source="verified_archive") for ticker in tickers],
        "network": {"calls": []},
    })
    with sqlite3.connect(candidate_paths.canonical_db) as connection:
        connection.executemany(
            "INSERT INTO security VALUES(?,?,?,?,1)",
            [(20 + company_id, company_id, ticker, "NASDAQ") for company_id, ticker in enumerate(tickers, 2)],
        )
    with sqlite3.connect(candidate_paths.analysis_db) as connection:
        connection.executemany(
            "INSERT INTO score_result VALUES(?,?,?,?)",
            [
                (2, 3, "SCORE_FULL", '{"missing_components":[],"ttm_core_ready":true}'),
                (3, 3, "SCORE_LIMITED", '{"missing_components":["REVENUE_GROWTH","OPERATING_MARGIN_DIRECTION"],"ttm_core_ready":true}'),
                (4, 3, "SCORE_NOT_READY", '{"missing_components":["REVENUE_GROWTH"],"ttm_core_ready":false}'),
                (5, 3, "SCORE_FULL", '{"missing_components":[],"ttm_core_ready":true}'),
            ],
        )
        connection.executemany(
            "INSERT INTO lifecycle_revised_result VALUES(?,?,?,?,?)",
            [
                (2, 3, "LIFECYCLE_READY", "TRANSITION", "CLASSIFIED_TRANSITION"),
                (3, 3, "LIFECYCLE_NOT_READY", None, "TTM_INPUTS_NOT_READY"),
                (4, 3, "LIFECYCLE_NOT_READY", None, "SOURCE_AVAILABILITY_DATE_MISSING"),
                (5, 3, "LIFECYCLE_READY", "MATURE", "CLASSIFIED_MATURE"),
            ],
        )
        connection.executemany(
            "INSERT INTO valuation_revised_result VALUES(?,?,?,?)",
            [
                (2, 3, "VALUATION_FULL", "VALUATION_FULL"),
                (3, 3, "VALUATION_FULL", "VALUATION_FULL"),
                (4, 3, "VALUATION_NOT_READY", "TTM_NOT_READY"),
                (5, 3, "VALUATION_NOT_APPLICABLE", "UNSUPPORTED_FINANCIAL_MODEL"),
            ],
        )
        connection.executemany(
            "INSERT INTO relative_position_result VALUES('rp',?,?,?)",
            [
                (2, "UNIVERSE", "RELATIVE_POSITION_READY"),
                (2, "SECTOR", "PEER_GROUP_TOO_SMALL"),
                (3, "UNIVERSE", "RELATIVE_POSITION_READY"),
                (5, "UNIVERSE", "RELATIVE_POSITION_READY"),
            ],
        )
        connection.execute("INSERT INTO relative_position_coverage VALUES('rp',4,'NOT_COVERED','SOURCE_MEASURE_NOT_ELIGIBLE')")
        connection.execute("INSERT INTO relative_valuation_company_result VALUES('rv',2,'VALUATION_FULL','VALUATION_FULL')")

    reports = enrich_after_state(
        preview, candidate_paths, stage="COPY_ONLY_APPLY",
        final_actions={ticker: "Tested successfully - new ticker" for ticker in tickers},
    )
    by_ticker = {report["ticker"]: report for report in reports}
    rendered = render_ticker_sections(reports)

    assert by_ticker["NEWFULL"]["after"]["identity"]["company_id"] == 2
    assert by_ticker["NEWFULL"]["after"]["analysis"]["score"]["status"] == "SCORE_FULL"
    assert by_ticker["NEWLIMIT"]["after"]["analysis"]["score"]["status"] == "SCORE_LIMITED"
    assert by_ticker["NEWNOT"]["after"]["analysis"]["score"]["status"] == "SCORE_NOT_READY"
    assert by_ticker["NEWNA"]["after"]["analysis"]["valuation"]["status"] == "VALUATION_NOT_APPLICABLE"
    assert by_ticker["NEWFULL"]["taxonomy"]["roles"] == ["WATCH_ONLY"]
    assert by_ticker["NEWFULL"]["after"]["analysis"]["rp_v2"]["ecosystem_results"] == 0
    assert "Score V2: FULL" in rendered
    assert "Score V2: LIMITED - missing Revenue Growth, Operating Margin Direction" in rendered
    assert "Score V2: NOT_READY - TTM core inputs unavailable" in rendered
    assert "Lifecycle: READY - Transition" in rendered
    assert "Valuation V2: NOT_APPLICABLE - unsupported financial model" in rendered
    assert "RP V2: 2 results (0 ecosystem) - READY; some peer groups too small" in rendered
    assert "RV: Not eligible" in rendered
    assert "## Analysis Outcome" in rendered
    assert "Score V2 FULL: 2" in rendered
    assert "missing_components" not in rendered


def test_after_state_lookup_failure_is_explicit_reporting_integrity_error(tmp_path: Path) -> None:
    paths = _databases(tmp_path)
    preview = build_preview_reporting(paths, {
        "items": [_item("BROKEN", source="verified_archive")],
        "network": {"calls": []},
    })
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("INSERT INTO security VALUES(30,3,'BROKEN','NASDAQ',1)")

    report = enrich_after_state(preview, paths, stage="COPY_ONLY_APPLY")[0]
    rendered = render_ticker_sections([report])

    assert report["after"]["analysis"]["integrity_status"] == "REPORTING_INTEGRITY_ERROR"
    assert "Reporting integrity error" in rendered
    assert "Score V2: Not available" not in rendered
