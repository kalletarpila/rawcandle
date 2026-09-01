from __future__ import annotations

import csv
from pathlib import Path

from rawcandle.fundamentals.schema.contract import SHARADAR_ARQ_FIELD_MAPPING, V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.identity_calendar_bootstrap import (
    BOOTSTRAP_SOURCE_FILENAME,
    bootstrap_identity_calendar,
    detect_column_mapping,
    identity_calendar_counts,
    identity_calendar_paths,
    locate_bootstrap_csv,
    parse_cik_from_source_url,
    run_identity_calendar_prototype,
)
from rawcandle.fundamentals.schema.migrations import bootstrap_all, canonical_field_contract_present, connect
from rawcandle.fundamentals.schema.prototype import canonicalize_arq, load_provider_subset, validate_integrity


def _write_bootstrap_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "ticker",
        "FY2027 alkoi",
        "FY2026 alkoi",
        "FY2025 alkoi",
        "FY2024 alkoi",
        "FY2023 alkoi",
        "Tyypillinen tilikauden alku",
        "Lähde",
        "chain_status",
        "break_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _row(
    ticker: str,
    cik: str | None,
    *,
    fy2027: str = "",
    fy2026: str = "2026-01-01",
    fy2025: str = "2025-01-01",
    fy2024: str = "2024-01-01",
    fy2023: str = "2023-01-01",
    source: str | None = None,
) -> dict[str, str]:
    if source is None:
        source = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json" if cik else ""
    return {
        "ticker": ticker,
        "FY2027 alkoi": fy2027,
        "FY2026 alkoi": fy2026,
        "FY2025 alkoi": fy2025,
        "FY2024 alkoi": fy2024,
        "FY2023 alkoi": fy2023,
        "Tyypillinen tilikauden alku": "1. tammikuuta",
        "Lähde": source,
        "chain_status": "BROKEN_AT_FY2011",
        "break_reason": "UNRESOLVED_BOUNDARY",
    }


def _acceptance_csvs(root: Path) -> None:
    root.mkdir()
    rows = [
        {
            "ticker": "WDAY",
            "permaticker": "19930",
            "dimension": "ARQ",
            "calendardate": "2026-04-30",
            "reportperiod": "2026-04-30",
            "fiscalperiod": "2027-Q1",
            "date": "2026-05-22",
            "lastupdated": "2026-08-30",
            "revenue": "100",
            "gp": "90",
            "opinc": "80",
            "ebit": "70",
            "ebitda": "75",
            "netinc": "60",
            "netinccmn": "55",
            "ncfo": "50",
            "capex": "-10",
            "fcf": "40",
            "cashneq": "30",
            "debt": "20",
            "debtc": "8",
            "debtnc": "12",
            "sharesbas": "10",
            "shareswa": "11",
            "shareswadil": "12",
        }
    ]
    with (root / "acceptance_arq_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    mrq = [dict(rows[0], dimension="MRQ", revenue="101")]
    with (root / "acceptance_mrq_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(mrq)


def test_bootstrap_csv_found() -> None:
    path = locate_bootstrap_csv(Path.cwd())
    assert path.name == BOOTSTRAP_SOURCE_FILENAME
    assert path.exists()


def test_header_mapping_detected(tmp_path: Path) -> None:
    path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(path, [_row("AAPL", "0000320193")])
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    mapping = detect_column_mapping(rows[0].keys())
    assert mapping["valid"]
    assert mapping["source_column"] == "Lähde"
    assert mapping["fy_start_columns"]["2026"] == "FY2026 alkoi"


def test_valid_cik_parsed_from_sec_url() -> None:
    cik, classification = parse_cik_from_source_url("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")
    assert cik == "0000320193"
    assert classification == "CIK_VALID_UNIQUE"


def test_cik_leading_zeros_preserved() -> None:
    assert parse_cik_from_source_url("https://data.sec.gov/api/xbrl/companyfacts/CIK0000003197.json")[0] == "0000003197"


def test_invalid_cik_rejected() -> None:
    cik, classification = parse_cik_from_source_url("https://data.sec.gov/api/xbrl/companyfacts/CIK123.json")
    assert cik is None
    assert classification == "CIK_FORMAT_INVALID"


def test_missing_cik_remains_null(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("MISS", None, source="")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    result = bootstrap_identity_calendar(db, csv_path, "now")
    assert result["counts"]["company_ciks"] == 0
    assert result["cik_audit"][0]["classification"] == "CIK_MISSING_SOURCE"


def test_ticker_multiple_cik_conflict_blocked(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("ABC", "0000000001"), _row("ABC", "0000000002")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    result = bootstrap_identity_calendar(db, csv_path, "now")
    assert {row["classification"] for row in result["cik_audit"]} == {"TICKER_MULTIPLE_CIK_CONFLICT"}
    assert result["counts"]["company_ciks"] == 0


def test_legitimate_multi_ticker_same_cik_supported(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("OLD", "0000000001"), _row("NEW", "0000000001")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    result = bootstrap_identity_calendar(db, csv_path, "now")
    assert result["counts"]["companies"] == 1
    assert result["counts"]["securities"] == 2
    assert result["counts"]["company_ciks"] == 1


def test_fy_start_columns_normalized_to_annual_rows(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    result = bootstrap_identity_calendar(db, csv_path, "now")
    assert result["counts"]["fiscal_anchors"] == 4


def test_blank_fy_start_stays_blank_and_no_inference(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193", fy2027="")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company_fiscal_year_anchor WHERE fiscal_year=2027").fetchone()[0] == 0


def test_fiscal_anchor_conflict_blocked(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("OLD", "0000000001", fy2026="2026-01-01"), _row("NEW", "0000000001", fy2026="2026-02-01")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    result = bootstrap_identity_calendar(db, csv_path, "now")
    assert len(result["anchor_conflicts"]) == 2
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company_fiscal_year_anchor WHERE fiscal_year=2026").fetchone()[0] == 0


def test_chain_status_and_break_reason_preserved(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("WDAY", "0001327811")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    with connect(db) as conn:
        row = conn.execute("SELECT chain_status, break_reason FROM company_fiscal_calendar_profile").fetchone()
        assert row["chain_status"] == "BROKEN_AT_FY2011"
        assert row["break_reason"] == "UNRESOLVED_BOUNDARY"


def test_old_chain_break_does_not_invalidate_later_exact_anchor(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("WDAY", "0001327811", fy2027="2026-02-01")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    with connect(db) as conn:
        assert conn.execute("SELECT confidence FROM company_fiscal_year_anchor WHERE fiscal_year=2027").fetchone()[0] == "VERIFIED"


def test_real_csv_hard_case_ciks_available() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    by_ticker = {row["ticker"]: row for row in rows}
    assert "CIK0000320193.json" in by_ticker["AAPL"]["Lähde"]
    assert "CIK0001327811.json" in by_ticker["WDAY"]["Lähde"]
    assert "CIK0001083446.json" in by_ticker["ASTH"]["Lähde"]
    assert "CIK0000003197.json" in by_ticker["CECO"]["Lähde"]


def test_real_csv_column_mapping_valid() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    assert detect_column_mapping(rows[0].keys())["valid"]


def test_real_csv_expected_scale() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    assert 2400 <= len(rows) <= 2600


def test_real_csv_companyfacts_url_count() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    assert sum(1 for row in rows if "companyfacts/" in row["Lähde"]) == 2448


def test_aapl_cik_imported_if_available() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    aapl = next(row for row in rows if row["ticker"] == "AAPL")
    assert parse_cik_from_source_url(aapl["Lähde"])[0] == "0000320193"


def test_wday_cik_imported_if_available() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    wday = next(row for row in rows if row["ticker"] == "WDAY")
    assert parse_cik_from_source_url(wday["Lähde"])[0] == "0001327811"


def test_asth_cik_imported_if_available() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    asth = next(row for row in rows if row["ticker"] == "ASTH")
    assert parse_cik_from_source_url(asth["Lähde"])[0] == "0001083446"


def test_ceco_cik_imported_if_available() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    ceco = next(row for row in rows if row["ticker"] == "CECO")
    assert parse_cik_from_source_url(ceco["Lähde"])[0] == "0000003197"


def test_wday_asth_ceco_anchors_validate_expected_fiscal_years() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["WDAY"]["FY2027 alkoi"] == "2026-02-01"
    assert by_ticker["ASTH"]["FY2026 alkoi"] == "2026-01-01"
    assert by_ticker["CECO"]["FY2026 alkoi"] == "2026-01-01"


def test_aapl_anchor_preserved() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    aapl = next(row for row in rows if row["ticker"] == "AAPL")
    assert aapl["FY2026 alkoi"] == "2025-09-28"


def test_wday_anchor_validates_fy2027() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    wday = next(row for row in rows if row["ticker"] == "WDAY")
    assert wday["FY2027 alkoi"] <= "2026-04-30"


def test_asth_anchor_validates_fy2026() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    asth = next(row for row in rows if row["ticker"] == "ASTH")
    assert asth["FY2026 alkoi"] <= "2026-03-31"


def test_ceco_anchor_validates_fy2026() -> None:
    rows = list(csv.DictReader(locate_bootstrap_csv(Path.cwd()).open(encoding="utf-8-sig")))
    ceco = next(row for row in rows if row["ticker"] == "CECO")
    assert ceco["FY2026 alkoi"] <= "2026-03-31"


def test_cik_provenance_retained(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    with connect(db) as conn:
        row = conn.execute("SELECT source_type, source_name, source_field, derivation FROM company_cik").fetchone()
        assert row["source_type"] == "LOCAL_VERIFIED_BOOTSTRAP"
        assert row["source_name"] == "v3_active_tickers_99_27"
        assert row["source_field"] == "Lähde"
        assert row["derivation"] == "PARSED_FROM_SEC_COMPANYFACTS_URL"


def test_fiscal_anchor_provenance_retained(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    with connect(db) as conn:
        row = conn.execute("SELECT source_name, source_field, observed_verified FROM company_fiscal_year_anchor WHERE fiscal_year=2026").fetchone()
        assert row["source_name"] == "v3_active_tickers_99_27"
        assert row["source_field"] == "FY2026 alkoi"
        assert row["observed_verified"] == 1


def test_bootstrap_replay_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193"), _row("WDAY", "0001327811", fy2027="2026-02-01")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    first = identity_calendar_counts(db)
    bootstrap_identity_calendar(db, csv_path, "now")
    second = identity_calendar_counts(db)
    assert first == second


def test_no_duplicate_cik_mappings_or_fiscal_anchors(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193")])
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    bootstrap_identity_calendar(db, csv_path, "now")
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM company_fiscal_year_anchor WHERE fiscal_year=2026").fetchone()[0] == 1


def test_v4_1a_canonical_field_contract_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    bootstrap_all(tmp_path / "provider.db", db, tmp_path / "analysis.db", "now")
    with connect(db) as conn:
        assert canonical_field_contract_present(conn)
        assert set(SHARADAR_ARQ_FIELD_MAPPING) == set(V4_CANONICAL_FINANCIAL_FIELDS)


def test_provider_schema_otherwise_unchanged(tmp_path: Path) -> None:
    provider_db = tmp_path / "provider.db"
    bootstrap_all(provider_db, tmp_path / "v4.db", tmp_path / "analysis.db", "now")
    with connect(provider_db) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "provider_run" in tables
    assert "provider_observation" in tables
    assert "sharadar_fundamental_observation" in tables


def test_arq_mrq_behavior_unchanged_and_sharadar_fiscalperiod_not_overwritten(tmp_path: Path) -> None:
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("WDAY", "0001327811", fy2027="2026-02-01")])
    acceptance = tmp_path / "acceptance"
    _acceptance_csvs(acceptance)
    paths = identity_calendar_paths(tmp_path, acceptance_root=acceptance, bootstrap_csv=csv_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    bootstrap_identity_calendar(paths.canonical_db, csv_path, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["WDAY"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        assert provider.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE dimension='MRQ'").fetchone()[0] == 1
        assert canonical.execute("SELECT source_fiscalperiod FROM v4_quarter").fetchone()[0] == "2027-Q1"


def test_no_production_db_creation_after_prototype(tmp_path: Path) -> None:
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("AAPL", "0000320193")])
    acceptance = tmp_path / "acceptance"
    _acceptance_csvs(acceptance)
    paths = identity_calendar_paths(tmp_path, acceptance_root=acceptance, bootstrap_csv=csv_path)
    run_identity_calendar_prototype(paths)
    assert not (tmp_path / "data" / "fundamentals_provider.db").exists()
    assert not (tmp_path / "data" / "fundamentals_v4.db").exists()
    assert not (tmp_path / "data" / "fundamentals_analysis.db").exists()


def test_no_v3_db_dependency_in_new_bootstrap_module() -> None:
    import rawcandle.fundamentals.schema.identity_calendar_bootstrap as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "rc_fundamentals_v3.db" not in source


def test_no_swingmaster_runtime_import_in_new_bootstrap_module() -> None:
    import rawcandle.fundamentals.schema.identity_calendar_bootstrap as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "from swingmaster" not in source
    assert "import swingmaster" not in source
    assert "/home/kalle/projects/swingmaster" not in source


def test_no_sec_network_client_in_new_bootstrap_module() -> None:
    import rawcandle.fundamentals.schema.identity_calendar_bootstrap as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "urllib" not in source


def test_prototype_integrity_clean(tmp_path: Path) -> None:
    csv_path = tmp_path / BOOTSTRAP_SOURCE_FILENAME
    _write_bootstrap_csv(csv_path, [_row("WDAY", "0001327811", fy2027="2026-02-01")])
    acceptance = tmp_path / "acceptance"
    _acceptance_csvs(acceptance)
    paths = identity_calendar_paths(tmp_path, acceptance_root=acceptance, bootstrap_csv=csv_path)
    summary = run_identity_calendar_prototype(paths)
    integrity = validate_integrity(paths)
    assert summary["integrity"]["anchor_conflicts"] == 0
    assert summary["integrity"]["identity_conflicts"] == 0
    assert integrity["provider_quick_check"] == "ok"
    assert integrity["canonical_quick_check"] == "ok"
    assert integrity["analysis_quick_check"] == "ok"
