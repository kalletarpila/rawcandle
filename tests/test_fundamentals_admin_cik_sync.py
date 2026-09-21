from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.cik_sync import (
    audit,
    run_apply,
    run_preview,
    run_production_apply,
)
from rawcandle.fundamentals.admin.provider_cik import (
    extract_sharadar_cik,
    normalize_cik,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def _provider(path: Path, rows: list[tuple[str, str, str | None]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE sharadar_ticker_metadata("
            "table_name TEXT,ticker TEXT,permaticker TEXT,name TEXT,exchange TEXT,"
            "isdelisted TEXT,category TEXT,secfilings TEXT,lastupdated TEXT,"
            "PRIMARY KEY(table_name,ticker,permaticker))"
        )
        for ticker, permaticker, cik in rows:
            secfilings = (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
                if cik is not None else None
            )
            connection.execute(
                "INSERT INTO sharadar_ticker_metadata VALUES(?,?,?,?,?,?,?,?,?)",
                ("fundamentals", ticker, permaticker, f"{ticker} Co", "NASDAQ", "N", "Domestic Common Stock", secfilings, "2026-09-20"),
            )


def _canonical(
    path: Path,
    securities: list[tuple[int, int, str, str]],
    ciks: list[tuple[int, str]] | None = None,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE company(company_id INTEGER PRIMARY KEY,company_key TEXT NOT NULL,company_name TEXT,status TEXT,created_at_utc TEXT,updated_at_utc TEXT);"
            "CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL,current_ticker TEXT,exchange TEXT,active INTEGER,valid_from TEXT,valid_to TEXT,created_at_utc TEXT,updated_at_utc TEXT);"
            "CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,ticker TEXT,provider TEXT,valid_from TEXT,valid_to TEXT,source TEXT);"
            "CREATE TABLE provider_security_identity(provider TEXT,provider_security_id TEXT,security_id INTEGER,provider_ticker TEXT,source TEXT,created_at_utc TEXT,PRIMARY KEY(provider,provider_security_id));"
            "CREATE TABLE provider_company_identity(provider TEXT,provider_identifier_type TEXT,provider_identifier_value TEXT,company_id INTEGER,provider_ticker TEXT,source TEXT,source_type TEXT,source_value TEXT,created_at_utc TEXT,PRIMARY KEY(provider,provider_identifier_type,provider_identifier_value));"
            "CREATE TABLE company_cik(company_id INTEGER,cik_normalized TEXT,cik_display TEXT,source TEXT,source_table TEXT,source_row_id TEXT,status TEXT,created_at_utc TEXT,source_type TEXT,source_name TEXT,source_field TEXT,source_value TEXT,derivation TEXT,confidence TEXT,PRIMARY KEY(company_id,cik_normalized));"
            "CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,source_availability_date TEXT,first_public_result_date TEXT);"
            "CREATE TABLE v4_quarter_financials(quarter_id INTEGER PRIMARY KEY,revenue INTEGER);"
        )
        companies = sorted({company_id for _, company_id, _, _ in securities})
        for company_id in companies:
            connection.execute(
                "INSERT INTO company VALUES(?,?,?,?,?,?)",
                (company_id, f"COMPANY:{company_id}", f"Company {company_id}", "ACTIVE", "2026-01-01", "2026-01-01"),
            )
            connection.execute(
                "INSERT INTO v4_quarter VALUES(?,?,?,?,?,?)",
                (company_id, company_id, 2026, "Q1", "2026-05-01", "2026-05-01"),
            )
            connection.execute("INSERT INTO v4_quarter_financials VALUES(?,?)", (company_id, company_id * 100))
        for security_id, company_id, ticker, permaticker in securities:
            connection.execute(
                "INSERT INTO security VALUES(?,?,?,?,?,?,?,?,?)",
                (security_id, company_id, ticker, "NASDAQ", 1, "2020-01-01", None, "2026-01-01", "2026-01-01"),
            )
            connection.execute(
                "INSERT INTO ticker_alias(security_id,ticker,provider,valid_from,source) VALUES(?,?,?,?,?)",
                (security_id, ticker, "SHARADAR", "2020-01-01", "fixture"),
            )
            connection.execute(
                "INSERT INTO provider_security_identity VALUES('SHARADAR',?,?,?,?,?)",
                (permaticker, security_id, ticker, "fixture", "2026-01-01"),
            )
        for company_id, cik in ciks or ():
            connection.execute(
                "INSERT INTO company_cik VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (company_id, cik, cik, "fixture", "fixture", str(company_id), "ACTIVE", "2026-01-01", "fixture", "fixture", "cik", cik, "fixture", "HIGH"),
            )


def _paths(tmp_path: Path, rows, securities, ciks=()) -> BatchAddTickerPaths:
    tmp_path.mkdir(parents=True, exist_ok=True)
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    _provider(provider, list(rows))
    _canonical(canonical, list(securities), list(ciks))
    for path in (analysis, market, taxonomy):
        with sqlite3.connect(path):
            pass
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def test_sharadar_cik_parser_is_narrow_and_canonical() -> None:
    valid = extract_sharadar_cik(
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=12345"
    )
    assert valid.status == "AVAILABLE"
    assert valid.cik_normalized == "0000012345"
    assert normalize_cik("0000012345") == "0000012345"
    assert extract_sharadar_cik(None).status == "UNAVAILABLE"
    assert extract_sharadar_cik("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=bad").status == "INVALID"
    assert extract_sharadar_cik("https://example.com/?CIK=12345").status == "UNSUPPORTED"
    assert extract_sharadar_cik("http://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=12345").status == "UNSUPPORTED"


def test_audit_classifies_eligible_matching_conflicts_dedupe_and_unavailable(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path,
        rows=[
            ("ELIG", "101", "123"), ("MATCH", "102", "456"),
            ("CONFLICT", "103", "790"), ("SAMEA", "104", "321"),
            ("SAMEB", "105", "321"), ("DISA", "106", "111"),
            ("DISB", "107", "112"), ("MULTIA", "108", "999"),
            ("MULTIB", "109", "999"), ("NONE", "110", None),
        ],
        securities=[
            (1, 1, "ELIG", "101"), (2, 2, "MATCH", "102"),
            (3, 3, "CONFLICT", "103"), (4, 4, "SAMEA", "104"),
            (5, 4, "SAMEB", "105"), (6, 5, "DISA", "106"),
            (7, 5, "DISB", "107"), (8, 6, "MULTIA", "108"),
            (9, 7, "MULTIB", "109"), (10, 8, "NONE", "110"),
        ],
        ciks=[(2, "0000000456"), (3, "0000000789")],
    )
    result = audit(paths)
    by_company = {item["company_id"]: item for item in result["items"]}
    assert by_company[1]["classification"] == "SYNC_ELIGIBLE"
    assert by_company[2]["classification"] == "ALREADY_IN_SYNC"
    assert by_company[3]["classification"] == "REVIEW_REQUIRED_CIK_CONFLICT"
    assert by_company[3]["representation_changes"] == []
    assert by_company[4]["classification"] == "SYNC_ELIGIBLE"
    assert by_company[4]["proposed_cik"] == "0000000321"
    assert by_company[5]["classification"] == "REVIEW_REQUIRED_CIK_CONFLICT"
    assert by_company[6]["classification"] == "REVIEW_REQUIRED_CIK_MULTI_COMPANY"
    assert by_company[7]["classification"] == "REVIEW_REQUIRED_CIK_MULTI_COMPANY"
    assert by_company[8]["classification"] == "PROVIDER_CIK_UNAVAILABLE"
    assert result["counts"]["sync_eligible"] == 2
    assert result["counts"]["provider_cik_unavailable"] == 1
    assert result["counts"]["review_required"] == 4


def test_format_normalization_updates_all_proven_equivalent_identity_representations(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path,
        rows=[("LEGACY", "101", "1308648")],
        securities=[(1, 1, "LEGACY", "101")],
        ciks=[(1, "1308648")],
    )
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE company SET company_key='SEC_CIK:1308648' WHERE company_id=1")
        connection.execute(
            "INSERT INTO provider_company_identity VALUES(?,?,?,?,?,?,?,?,?)",
            ("SEC", "CIK", "1308648", 1, "LEGACY", "fixture", "fixture", "1308648", "2026-01-01"),
        )
    production_before = paths.canonical_db.read_bytes()
    preview = run_preview(paths=paths, run_root=tmp_path / "runs")
    assert preview["summary_counts"]["sync_eligible"] == 0
    assert preview["summary_counts"]["format_normalization_eligible"] == 1
    assert paths.canonical_db.read_bytes() == production_before
    item = preview["audit"]["items"][0]
    assert item["classification"] == "FORMAT_NORMALIZATION_ELIGIBLE"
    assert item["semantic_cik"] == "0001308648"
    assert item["semantic_identity_change"] is False
    assert [
        (change["field_identifier"], change["before"], change["after"])
        for change in item["representation_changes"]
    ] == [
        ("company_cik.cik_normalized", "1308648", "0001308648"),
        ("company_cik.cik_display", "1308648", "0001308648"),
        ("company_cik.source_value", "1308648", "0001308648"),
        ("provider_company_identity.provider_identifier_value", "1308648", "0001308648"),
        ("provider_company_identity.source_value", "1308648", "0001308648"),
        ("company.company_key", "SEC_CIK:1308648", "SEC_CIK:0001308648"),
    ]
    proposed = preview["proposed_changes"][0]
    assert proposed["representation_changes"] == item["representation_changes"]
    report = (Path(preview["artifact_dir"]) / "operation_report.md").read_text(encoding="utf-8")
    assert "semantic CIK: `0001308648`; semantic identity change: No" in report
    assert "`company_cik.cik_normalized`: `1308648` -> `0001308648`" in report
    assert "Provider CIK unavailable among canonical missing-CIK cases: 0" in report

    test = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        confirm_apply=True,
        paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
    )

    assert test["updated_count"] == 1
    assert test["validation"]["company_mapping_semantically_unchanged"] is True
    assert test["validation"]["provider_company_identity_semantically_unchanged"] is True
    after = test["after_audit"]
    assert after["counts"]["format_normalization_eligible"] == 0
    assert after["counts"]["noncanonical_existing_cik_rows"] == 0
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT cik_normalized FROM company_cik").fetchone()[0] == "1308648"


def test_format_preview_reports_only_fields_that_actually_change(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path,
        rows=[("MIXED", "101", "1308648")],
        securities=[(1, 1, "MIXED", "101")],
        ciks=[(1, "0001308648")],
    )
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute(
            "UPDATE company_cik SET cik_display='1308648' WHERE company_id=1"
        )

    result = audit(paths)
    item = result["items"][0]

    assert item["classification"] == "FORMAT_NORMALIZATION_ELIGIBLE"
    assert item["representation_changes"] == [{
        "table": "company_cik",
        "field": "cik_display",
        "field_identifier": "company_cik.cik_display",
        "before": "1308648",
        "after": "0001308648",
    }]


def test_real_preview_test_production_path_publishes_only_company_cik(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path / "dbs",
        rows=[("ELIG", "101", "123")],
        securities=[(1, 1, "ELIG", "101")],
    )
    run_root = tmp_path / "runs"
    temp_root = tmp_path / "temp"
    backup_root = tmp_path / "backups"
    preview = run_preview(paths=paths, run_root=run_root)
    assert preview["outcome"] == "COMPLETED"
    assert preview["summary_counts"]["sync_eligible"] == 1
    preview_report = (Path(preview["artifact_dir"]) / "operation_report.md").read_text(encoding="utf-8")
    assert "ELIG / company_id=1: SYNC_ELIGIBLE" in preview_report
    assert "provider CIK: 0000000123; canonical CIK: missing" in preview_report
    test = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        confirm_apply=True,
        paths=paths,
        run_root=run_root,
        temp_root=temp_root,
    )
    assert test["outcome"] == "COMPLETED"
    assert test["updated_count"] == 1
    assert test["validation"]["non_target_canonical_unchanged"] is True
    assert test["validation"]["provider_unchanged"] is True
    assert test["validation"]["analysis_unchanged"] is True
    assert not temp_root.exists() or not any(temp_root.rglob("*.db"))
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0] == 0
    production = run_production_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        test_run_id=test["run_id"],
        confirm_production=True,
        paths=paths,
        run_root=run_root,
        temp_root=temp_root,
        backup_root=backup_root,
        journal_path=tmp_path / "journal.json",
    )
    assert production["outcome"] == "COMPLETED"
    assert production["cleanup_status"] == "COMPLETED"
    assert production["validation"]["provider_unchanged"] is True
    assert production["validation"]["analysis_unchanged"] is True
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute(
            "SELECT cik_normalized FROM company_cik WHERE company_id=1"
        ).fetchone()[0] == "0000000123"
    assert (backup_root / production["run_id"] / "canonical.db").is_file()


def test_ui_service_routes_cik_preview_and_preserves_self_contained_report(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path / "dbs",
        rows=[("LEGACY", "101", "1308648")],
        securities=[(1, 1, "LEGACY", "101")],
        ciks=[(1, "1308648")],
    )
    run_root = tmp_path / "runs"
    service = FundamentalsAdminUIService(
        run_root=run_root,
        cik_preview=lambda **kwargs: run_preview(paths=paths, **kwargs),
    )

    result = service.preview("SYNCHRONIZE_PROVIDER_CIK")

    assert result.status == "COMPLETED"
    assert result.preview_payload_path is not None
    assert any("Formatting-only normalization candidates: 1" in row for row in result.summary_rows)
    assert any(
        "LEGACY / company_id=1: FORMAT_NORMALIZATION_ELIGIBLE" in row
        and "company_cik.cik_normalized: 1308648 -> 0001308648" in row
        for row in result.summary_rows
    )
    report = (run_root / str(result.run_id) / "operation_report.md").read_text(encoding="utf-8")
    assert "LEGACY / company_id=1: FORMAT_NORMALIZATION_ELIGIBLE" in report
    assert "Zero-write Preview: Yes" in report
    capability = next(
        item for item in service.capabilities()
        if item.operation_type == "SYNCHRONIZE_PROVIDER_CIK"
    )
    assert capability.production_confirmation_hint == "CONFIRM_PRODUCTION_PROVIDER_CIK_SYNC"


def test_stale_preview_rejects_before_test_copy_creation(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path / "dbs", rows=[("ELIG", "101", "123")],
        securities=[(1, 1, "ELIG", "101")],
    )
    run_root = tmp_path / "runs"
    temp_root = tmp_path / "temp"
    preview = run_preview(paths=paths, run_root=run_root)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE company SET company_name='Changed' WHERE company_id=1")
    import pytest

    with pytest.raises(RuntimeError, match="CIK_SYNC_STALE_PREVIEW"):
        run_apply(
            preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"],
            confirm_apply=True,
            paths=paths,
            run_root=run_root,
            temp_root=temp_root,
        )
    assert not temp_root.exists()


def test_production_postflight_failure_restores_old_canonical_and_records_terminal_rollback(
    tmp_path: Path, monkeypatch,
) -> None:
    paths = _paths(
        tmp_path / "dbs", rows=[("ELIG", "101", "123")],
        securities=[(1, 1, "ELIG", "101")],
    )
    run_root = tmp_path / "runs"
    preview = run_preview(paths=paths, run_root=run_root)
    test = run_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        confirm_apply=True,
        paths=paths,
        run_root=run_root,
        temp_root=tmp_path / "temp",
    )
    from rawcandle.fundamentals.admin import cik_sync

    original_audit = cik_sync.audit

    def fail_published_postflight(candidate_paths):
        result = original_audit(candidate_paths)
        if candidate_paths.canonical_db == paths.canonical_db:
            with sqlite3.connect(paths.canonical_db) as connection:
                if connection.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0]:
                    raise RuntimeError("injected postflight failure")
        return result

    monkeypatch.setattr(cik_sync, "audit", fail_published_postflight)
    from rawcandle.fundamentals.admin.cik_sync import _canonical_fingerprints

    before = _canonical_fingerprints(paths.canonical_db)
    production = run_production_apply(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        test_run_id=test["run_id"],
        confirm_production=True,
        paths=paths,
        run_root=run_root,
        temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups",
        journal_path=tmp_path / "journal.json",
    )

    assert production["outcome"] == "ROLLED_BACK"
    assert production["rollback"]["status"] == "ROLLED_BACK"
    assert _canonical_fingerprints(paths.canonical_db) == before
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0] == 0
    status = json.loads((run_root / production["run_id"] / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "FAILED_AFTER_WRITE"
