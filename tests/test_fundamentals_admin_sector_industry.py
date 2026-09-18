from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.history import AdminRunHistory
from rawcandle.fundamentals.admin.sector_industry import (
    _production_logical_state,
    build_sector_industry_plan,
    parse_sector_industry_request,
    run_apply,
    run_production_apply,
    run_preview,
)


def _db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _paths(tmp_path: Path) -> BatchAddTickerPaths:
    tmp_path.mkdir(parents=True, exist_ok=True)
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    with _db(provider):
        pass
    with _db(taxonomy):
        pass
    with _db(canonical) as conn:
        conn.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY, company_name TEXT);
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,exchange TEXT,active INTEGER,valid_from TEXT,valid_to TEXT);
            CREATE TABLE ticker_alias(security_id INTEGER,ticker TEXT,provider TEXT,valid_from TEXT,valid_to TEXT,source TEXT);
            CREATE TABLE fundamentals_operational_universe_active_version(singleton INTEGER PRIMARY KEY,universe_version_id TEXT,activated_at_utc TEXT);
            CREATE TABLE fundamentals_operational_universe_version(universe_version_id TEXT PRIMARY KEY,contract_version TEXT,scope TEXT,as_of_date TEXT,source_fingerprint TEXT,economic_result_fingerprint TEXT,physical_content_fingerprint TEXT,status TEXT,member_count INTEGER,company_count INTEGER,active_security_count INTEGER,zero_active_company_count INTEGER,multi_active_company_count INTEGER,created_at_utc TEXT,activated_at_utc TEXT);
            CREATE TABLE fundamentals_operational_universe_member(universe_version_id TEXT,company_id INTEGER,security_id INTEGER,current_ticker TEXT,market TEXT,membership_status TEXT,identity_resolution_status TEXT,active_security_count INTEGER,all_security_count INTEGER,effective_start_date TEXT,effective_end_date TEXT,source TEXT,reason TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE fundamentals_economic_structural_event(event_id INTEGER,contract_version TEXT,company_id INTEGER,security_id INTEGER,provider TEXT,provider_security_id TEXT,predecessor_ticker TEXT,successor_ticker TEXT,event_type TEXT,event_date TEXT,comparability_status TEXT,review_status TEXT,effective_date TEXT,evidence_json TEXT,reason TEXT,economic_event_fingerprint TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            """
        )
        conn.execute("INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'u1','2026-09-15T00:00:00Z')")
        conn.execute("INSERT INTO fundamentals_operational_universe_version VALUES('u1','c','scope','2026-09-15','s','econ','phys','COMPLETE',9,9,8,1,1,'x','x')")
        members = [
            (1, 11, "EXACT", "NYSE", 1, 1),
            (2, 12, "NORM", "NYSE", 1, 1),
            (3, 13, "CHG", "NYSE", 1, 1),
            (4, 14, "NULLC", "NYSE", 1, 1),
            (5, 15, "MISSRC", "NYSE", 1, 1),
            (6, 16, "AMBIG", "NYSE", 1, 1),
            (7, 17, "MULTI", "NYSE", 2, 2),
            (8, 18, "STRUCT", "NYSE", 1, 1),
        ]
        for company_id, security_id, ticker, exchange, active_count, all_count in members:
            conn.execute("INSERT INTO company VALUES(?,?)", (company_id, f"{ticker} Co"))
            conn.execute("INSERT INTO security VALUES(?,?,?,?,?,?,?)", (security_id, company_id, ticker, exchange, 1, "2020-01-01", None))
            membership_status = "ACTIVE_MULTI_SECURITY" if ticker == "MULTI" else "ACTIVE"
            membership_security_id = None if ticker == "MULTI" else security_id
            conn.execute(
                "INSERT INTO fundamentals_operational_universe_member VALUES('u1',?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (company_id, membership_security_id, ticker, "usa", membership_status, "RESOLVED", active_count, all_count, "2020-01-01", None, "test", "test", "x", "x"),
            )
        conn.execute("INSERT INTO security VALUES(170,7,'MULTIB','NYSE',1,'2020-01-01',NULL)")
        conn.execute("INSERT INTO company VALUES(9,'HIST Co')")
        conn.execute("INSERT INTO security VALUES(19,9,'HIST','NYSE',0,'2020-01-01',NULL)")
        conn.execute(
            "INSERT INTO fundamentals_operational_universe_member VALUES('u1',?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (9, 19, "HIST", "usa", "HISTORICAL_RETAINED_NO_ACTIVE_SECURITY", "NO_ACTIVE_SECURITY", 0, 1, "2020-01-01", None, "test", "historical", "x", "x"),
        )
        conn.execute("INSERT INTO ticker_alias VALUES(13,'OLDCHG','TEST','2020-01-01',NULL,'test')")
        conn.execute("INSERT INTO fundamentals_economic_structural_event VALUES(1,'c',8,18,'TEST','18','OLD','STRUCT','SPIN','2025-01-01','BREAK','REVIEWED','2025-01-01','{}','test','fp','x','x')")
    with _db(market) as conn:
        conn.execute("CREATE TABLE ticker_meta(ticker TEXT, market TEXT, sector TEXT, industry TEXT)")
        rows = [
            ("EXACT", "usa", "Technology", "Software"),
            ("NORM", "usa", "Health Care", "Medical Devices"),
            ("CHG", "usa", "Industrials", "Machinery"),
            ("NULLC", "usa", "Consumer Defensive", "Retail"),
            ("AMBIG", "usa", "Technology", "Hardware"),
            ("AMBIG", "usa", "Industrials", "Tools"),
            ("MULTI", "usa", "Technology", "Software"),
            ("STRUCT", "usa", "Energy", "Oil & Gas"),
        ]
        conn.executemany("INSERT INTO ticker_meta VALUES(?,?,?,?)", rows)
    with _db(analysis) as conn:
        conn.execute(
            "CREATE TABLE valuation_revised_result(company_id INTEGER,security_id INTEGER,ticker TEXT,sector TEXT,industry TEXT,applicability_classification TEXT,calculated_at_utc TEXT)"
        )
        rows = [
            (1, 11, "EXACT", "Technology", "Software"),
            (2, 12, "NORM", "Health-Care", "medical devices"),
            (3, 13, "CHG", "Technology", "Software"),
            (4, 14, "NULLC", None, "Retail"),
            (5, 15, "MISSRC", "Technology", "Software"),
            (6, 16, "AMBIG", "Technology", "Hardware"),
            (7, 17, "MULTI", "Technology", "Software"),
            (8, 18, "STRUCT", "Technology", "Software"),
        ]
        for company_id, security_id, ticker, sector, industry in rows:
            conn.execute("INSERT INTO valuation_revised_result VALUES(?,?,?,?,?,?,?)", (company_id, security_id, ticker, sector, industry, "SUPPORTED", "x"))
            conn.execute("INSERT INTO valuation_revised_result VALUES(?,?,?,?,?,?,?)", (company_id, security_id, ticker, sector, industry, "SUPPORTED", "x"))
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def test_full_scan_classifies_core_decisions(tmp_path: Path) -> None:
    plan = build_sector_industry_plan(_paths(tmp_path), parse_sector_industry_request(""))
    decisions = {item["ticker"]: item["decision"] for item in plan.items}

    assert plan.denominator_count == 8
    assert decisions["EXACT"] == "EXACT_MATCH"
    assert decisions["NORM"] == "NORMALIZED_EQUIVALENT"
    assert decisions["CHG"] == "CHANGE_REQUIRED"
    assert decisions["NULLC"] == "MISSING_PERSISTED_CLASSIFICATION"
    assert decisions["MISSRC"] == "MISSING_SOURCE_CLASSIFICATION"
    assert decisions["AMBIG"] == "AMBIGUOUS_SOURCE_CLASSIFICATION"
    assert decisions["MULTI"] == "IDENTITY_REVIEW_REQUIRED"
    assert decisions["STRUCT"] == "STRUCTURAL_BOUNDARY_REVIEW_REQUIRED"


def test_denominator_uses_active_memberships_not_total_or_expanded_security_rows(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    with sqlite3.connect(paths.canonical_db) as conn:
        total_members = conn.execute("SELECT COUNT(*) FROM fundamentals_operational_universe_member").fetchone()[0]
        active_members = conn.execute(
            "SELECT COUNT(*) FROM fundamentals_operational_universe_member WHERE membership_status LIKE 'ACTIVE%'"
        ).fetchone()[0]
        expanded_active_securities = conn.execute("SELECT COUNT(*) FROM security WHERE active=1").fetchone()[0]

    plan = build_sector_industry_plan(paths, parse_sector_industry_request(""))

    assert total_members == 9
    assert active_members == 8
    assert expanded_active_securities == 9
    assert plan.denominator_count == active_members
    assert plan.denominator_count != total_members
    assert plan.denominator_count != expanded_active_securities
    assert {item["ticker"] for item in plan.items}.isdisjoint({"HIST"})
    assert {item["decision"] for item in plan.items if item["ticker"] == "MULTI"} == {"IDENTITY_REVIEW_REQUIRED"}


def test_filtered_scan_resolves_current_ticker_and_alias(tmp_path: Path) -> None:
    plan = build_sector_industry_plan(_paths(tmp_path), parse_sector_industry_request("EXACT OLDCHG MISSING"))

    assert [item["ticker"] for item in plan.items] == ["EXACT", "CHG", "MISSING"]
    assert plan.items[-1]["decision"] == "NOT_APPLICABLE"


def test_preview_writes_durable_progress_without_tickers(tmp_path: Path) -> None:
    result = run_preview("", source_paths=_paths(tmp_path / "source"), run_root=tmp_path / "runs")

    assert result["outcome"] == "COMPLETED"
    run_dir = Path(result["artifact_dir"])
    assert (run_dir / "sector_industry_preview_payload.json").is_file()
    assert (run_dir / "progress_stages.json").is_file()
    assert AdminRunHistory(tmp_path / "runs").progress(result["run_id"]).terminal_outcome == "COMPLETED"


def test_apply_rejects_stale_preview_after_ticker_meta_change(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "source")
    preview = run_preview("CHG", source_paths=paths, run_root=tmp_path / "runs")
    with sqlite3.connect(paths.market_db) as conn:
        conn.execute("UPDATE ticker_meta SET sector='Utilities' WHERE ticker='CHG'")

    result = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
    )

    assert result["outcome"] == "FAILED"
    assert result["error"] == "ValueError"


def test_apply_corrects_copy_lane_once_and_repeat_no_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path / "source")
    preview = run_preview("CHG NULLC", source_paths=paths, run_root=tmp_path / "runs")
    calls = []

    def fake_downstream(paths_arg, output, *, changed_tickers, applied_at, progress, as_of_date):
        calls.append(tuple(changed_tickers))
        assert as_of_date == preview["started_at_utc"][:10]
        return {
            "invocation_counts": {"package": 1, "relative_position": 1, "relative_valuation": 1},
            "package": {"first_apply": {"economic_result_fingerprint": "pkg"}},
            "relative_position": {"result_fingerprint": "rp"},
            "relative_valuation": {"snapshot": {"result_fingerprint": "rv"}},
            "active_taxonomy": {"domain": "dc_ecosystem", "version": "active", "semantic_fingerprint": "taxonomy-hash"},
        }

    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry._run_downstream", fake_downstream)
    result = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
        keep_copies=True,
    )

    assert result["outcome"] == "COMPLETED"
    assert calls == [("CHG", "NULLC")]
    assert result["downstream"]["repeat"]["outcome"] == "NO_CHANGE"
    assert result["downstream"]["invocation_counts"] == {"package": 1, "relative_position": 1, "relative_valuation": 1}
    assert result["downstream"]["active_taxonomy"]["semantic_fingerprint"] == "taxonomy-hash"
    with sqlite3.connect(Path(result["cleanup"]["retained"]) / "analysis.db") as conn:
        assert conn.execute("SELECT DISTINCT sector,industry FROM valuation_revised_result WHERE ticker='CHG'").fetchall() == [("Industrials", "Machinery")]


def test_apply_rejects_same_row_count_ticker_meta_content_drift(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "source")
    preview = run_preview("CHG", source_paths=paths, run_root=tmp_path / "runs")
    with sqlite3.connect(paths.market_db) as conn:
        conn.execute("UPDATE ticker_meta SET sector='Technology' WHERE ticker='CHG'")

    result = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths, run_root=tmp_path / "runs", temp_root=tmp_path / "temp",
        confirm_apply=True,
    )
    assert result["outcome"] == "FAILED"
    assert result["error"] == "ValueError"
    with sqlite3.connect(paths.analysis_db) as conn:
        assert conn.execute("SELECT sector FROM valuation_revised_result WHERE ticker='CHG' LIMIT 1").fetchone()[0] == "Technology"


def test_no_change_apply_skips_downstream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path / "source")
    preview = run_preview("EXACT NORM", source_paths=paths, run_root=tmp_path / "runs")
    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry._run_downstream", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("downstream should not run")))

    result = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
    )

    assert result["outcome"] == "COMPLETED"
    assert result["downstream"]["invocation_counts"] == {"package": 0, "relative_position": 0, "relative_valuation": 0}


def test_apply_rolls_back_copy_lane_after_classification_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path / "source")
    preview = run_preview("CHG", source_paths=paths, run_root=tmp_path / "runs")

    result = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
        keep_copies=True,
        failure_boundary="classification_apply",
    )

    assert result["outcome"] == "ROLLED_BACK"
    with sqlite3.connect(Path(result["cleanup"]["retained"]) / "analysis.db") as conn:
        assert conn.execute("SELECT DISTINCT sector,industry FROM valuation_revised_result WHERE ticker='CHG'").fetchall() == [("Technology", "Software")]


def _remove_safe_sector_industry_changes(paths: BatchAddTickerPaths) -> None:
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.execute("UPDATE valuation_revised_result SET sector='Industrials',industry='Machinery' WHERE ticker='CHG'")
        conn.execute("UPDATE valuation_revised_result SET sector='Consumer Defensive',industry='Retail' WHERE ticker='NULLC'")


def _accept_test_population(plan: dict[str, object]) -> dict[str, object]:
    items = list(plan.get("items", []))
    safe_changes = [item for item in items if isinstance(item, dict) and item.get("safe_to_apply")]
    return {
        "status": "ACCEPTED" if not safe_changes else "REJECTED",
        "failures": [] if not safe_changes else ["SAFE_CHANGES_PRESENT_REQUIRES_SEPARATE_REVIEW"],
        "safe_changes": safe_changes,
        "denominator": plan.get("denominator_count"),
    }


def test_production_apply_requires_confirmation(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "source")
    _remove_safe_sector_industry_changes(paths)
    preview = run_preview("", source_paths=paths, run_root=tmp_path / "runs")

    with pytest.raises(PermissionError, match="CONFIRM_PRODUCTION"):
        run_production_apply(
            preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"],
            source_paths=paths,
            run_root=tmp_path / "runs",
            backup_root=tmp_path / "backups",
            temp_root=tmp_path / "temp",
            confirm_production=False,
        )


def test_production_apply_requires_full_universe_preview(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "source")
    preview = run_preview("EXACT", source_paths=paths, run_root=tmp_path / "runs")

    with pytest.raises(PermissionError, match="FULL_UNIVERSE"):
        run_production_apply(
            preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"],
            source_paths=paths,
            run_root=tmp_path / "runs",
            backup_root=tmp_path / "backups",
            temp_root=tmp_path / "temp",
            confirm_production=True,
        )


def test_production_no_change_apply_crosses_no_write_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path / "source")
    _remove_safe_sector_industry_changes(paths)
    preview = run_preview("", source_paths=paths, run_root=tmp_path / "runs")

    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry._production_preflight", lambda *args, **kwargs: {"status": "OK"})
    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry._accepted_population_gate", _accept_test_population)

    result = run_production_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        backup_root=tmp_path / "backups",
        temp_root=tmp_path / "temp",
        confirm_production=True,
    )

    assert result["outcome"] == "NO_CHANGE"
    assert result["mode"] == "PRODUCTION_NO_CHANGE_APPLY"
    assert result["downstream"]["classification_writes"] == 0
    assert result["downstream"]["invocation_counts"] == {"package": 0, "relative_position": 0, "relative_valuation": 0}
    assert result["downstream"]["repeat"]["outcome"] == "NO_CHANGE"
    assert result["rollback"]["status"] == "NOT_REQUIRED"
    assert result["production_apply"]["backup"]["status"] == "NOT_REQUIRED_NO_WRITE_BOUNDARY"
    assert result["production_apply"]["logical_state_compare"]["identical"] is True


def test_production_apply_rejects_stale_preview_before_write_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path / "source")
    _remove_safe_sector_industry_changes(paths)
    preview = run_preview("", source_paths=paths, run_root=tmp_path / "runs")
    with sqlite3.connect(paths.market_db) as conn:
        conn.execute("UPDATE ticker_meta SET sector='Utilities' WHERE ticker='EXACT'")

    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry._production_preflight", lambda *args, **kwargs: {"status": "OK"})

    result = run_production_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        backup_root=tmp_path / "backups",
        temp_root=tmp_path / "temp",
        confirm_production=True,
    )

    assert result["outcome"] == "FAILED"
    assert result["rollback"]["status"] == "NOT_REQUIRED"
    assert result["downstream"]["production_outcome"].startswith("OUTCOME B")


def test_production_logical_state_ignores_physical_inventory_noise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path)
    calls = []

    def fake_inventory(path: Path) -> dict[str, object]:
        calls.append(path)
        return {
            "schema_fingerprint": "schema",
            "row_counts": {"t": 1},
            "logical_fingerprints": {"t": "logical"},
            "quick_check": "ok",
            "foreign_key_errors": 0,
            "mtime_ns": len(calls),
            "sha256": f"physical-{len(calls)}",
        }

    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry.database_inventory", fake_inventory)
    monkeypatch.setattr("rawcandle.fundamentals.admin.sector_industry._active_identities", lambda _: {"active": "same"})

    first = _production_logical_state(paths)
    second = _production_logical_state(paths)

    assert first == second
    assert all("mtime_ns" not in item and "sha256" not in item for item in first["databases"].values())
