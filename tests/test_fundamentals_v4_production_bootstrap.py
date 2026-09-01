from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request

from rawcandle.fundamentals.schema.contract import V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.migrations import bootstrap_all, canonical_field_contract_present, connect
from rawcandle.fundamentals.schema.production_bootstrap import (
    ALLOWED_DIMENSIONS,
    ProductionPaths,
    baseline_fingerprints,
    canonicalize_arq_production,
    classify_anchor,
    create_production_databases,
    csv_profile,
    debt_reconciliation,
    download_sharadar_5y_bulk,
    fcf_reconciliation,
    field_coverage,
    hard_case_validation,
    ingest_bulk_provider_rows,
    preflight,
    production_integrity,
    production_paths,
    q4_global_coverage,
    quarter_continuity,
    replay,
    run_production_bootstrap,
    sharesbas_audit,
    target_tickers,
)
from rawcandle.fundamentals.schema.provenance import read_provenance


class FakeResponse:
    def __init__(self, payload: bytes, *, status: int = 200, url: str = "https://download.test/fundamentals.zip") -> None:
        self._payload = io.BytesIO(payload)
        self.status = status
        self.url = url
        self.headers = {"Content-Type": "application/zip"}

    def read(self, size: int = -1) -> bytes:
        return self._payload.read(size)

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url


class FakeOpener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requests: list[Request] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        del timeout
        self.requests.append(request)
        return FakeResponse(self.payload)


def _paths(tmp_path: Path) -> ProductionPaths:
    artifact = tmp_path / "artifact"
    return ProductionPaths(
        repo_root=tmp_path,
        artifact_root=artifact,
        provider_db=tmp_path / "data" / "fundamentals_provider.db",
        canonical_db=tmp_path / "data" / "fundamentals_v4.db",
        analysis_db=tmp_path / "data" / "fundamentals_analysis.db",
        bootstrap_csv=tmp_path / "temp" / "v3_active_tickers_99_27.csv",
        bulk_zip_path=artifact / "sharadar_fundamentals_5y.zip",
        extracted_csv_path=artifact / "sharadar_fundamentals_5y.csv",
    )


def _write_bootstrap_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ticker", "FY2027 alkoi", "FY2026 alkoi", "FY2025 alkoi", "FY2024 alkoi", "FY2023 alkoi", "Tyypillinen tilikauden alku", "Lähde", "chain_status", "break_reason"]
    rows = [
        ["AAPL", "", "2025-09-28", "2024-09-29", "2023-10-01", "2022-09-25", "Sunnuntai lahella syyskuun loppua", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", "BROKEN_AT_FY2006", "SOURCE_HISTORY_EXHAUSTED"],
        ["WDAY", "2026-02-01", "2025-02-01", "2024-02-01", "2023-02-01", "2022-02-01", "1. helmikuuta", "https://data.sec.gov/api/xbrl/companyfacts/CIK0001327811.json", "BROKEN_AT_FY2011", "UNRESOLVED_BOUNDARY"],
        ["ASTH", "", "2026-01-01", "2025-01-01", "2024-01-01", "2023-01-01", "1. tammikuuta", "https://data.sec.gov/api/xbrl/companyfacts/CIK0001083446.json", "BROKEN_AT_FY2015", "UNRESOLVED_BOUNDARY"],
        ["CECO", "", "2026-01-01", "2025-01-01", "2024-01-01", "2023-01-01", "1. tammikuuta", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000003197.json", "BROKEN_AT_FY2009", "UNRESOLVED_BOUNDARY"],
        ["MISS", "", "2026-01-01", "2025-01-01", "2024-01-01", "2023-01-01", "1. tammikuuta", "https://example.test/no-cik", "BROKEN_AT_FY2020", "NO_FISCAL_YEAR"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _fundamental_rows() -> list[dict[str, str]]:
    rows = [
        _row("AAPL", "199059", "ARQ", "2025-12-27", "2026-Q1", revenue="0", sharesbas="100"),
        _row("AAPL", "199059", "MRQ", "2025-12-27", "2026-Q1", revenue="1", sharesbas="100"),
        _row("AAPL", "199059", "ARQ", "2025-09-27", "2025-Q4", sharesbas="100"),
        _row("WDAY", "194807", "ARQ", "2026-04-30", "2027-Q1", sharesbas="200"),
        _row("WDAY", "194807", "MRQ", "2026-04-30", "2027-Q1", sharesbas="200"),
        _row("ASTH", "124446", "ARQ", "2026-03-31", "2026-Q1", sharesbas="300"),
        _row("CECO", "199985", "ARQ", "2026-03-31", "2026-Q1", sharesbas="400"),
        _row("OUT", "999999", "ARQ", "2026-03-31", "2026-Q1"),
        _row("AAPL", "199059", "ART", "2025-12-27", "2026-Q1"),
    ]
    return rows


def _row(ticker: str, permaticker: str, dimension: str, reportperiod: str, fiscalperiod: str, *, revenue: str = "10", sharesbas: str = "100") -> dict[str, str]:
    return {
        "ticker": ticker,
        "permaticker": permaticker,
        "dimension": dimension,
        "calendardate": reportperiod,
        "reportperiod": reportperiod,
        "fiscalperiod": fiscalperiod,
        "date": "2026-08-30",
        "lastupdated": "2026-08-30",
        "revenue": revenue,
        "gp": "9",
        "opinc": "8",
        "ebit": "7",
        "ebitda": "6",
        "netinc": "5",
        "netinccmn": "4",
        "ncfo": "4",
        "capex": "-1",
        "fcf": "3",
        "cashneq": "2",
        "debt": "3",
        "debtc": "1",
        "debtnc": "2",
        "sharesbas": sharesbas,
        "shareswa": "101",
        "shareswadil": "102",
    }


def _write_bulk_csv(path: Path, rows: list[dict[str, str]] | None = None) -> None:
    rows = rows or _fundamental_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _zip_bytes(rows: list[dict[str, str]] | None = None) -> bytes:
    handle = io.StringIO()
    rows = rows or _fundamental_rows()
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fundamentals.csv", handle.getvalue())
    return output.getvalue()


def _bootstrap(paths: ProductionPaths) -> None:
    _write_bootstrap_csv(paths.bootstrap_csv)
    _write_bulk_csv(paths.extracted_csv_path)
    create_production_databases(paths, "now")
    from rawcandle.fundamentals.schema.identity_calendar_bootstrap import bootstrap_identity_calendar

    bootstrap_identity_calendar(paths.canonical_db, paths.bootstrap_csv, "now")
    ingest_bulk_provider_rows(paths, "run", "now")
    canonicalize_arq_production(paths, "now")


def test_production_db_path_preflight(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_bootstrap_csv(paths.bootstrap_csv)
    result = preflight(paths, api_key_configured=True, git_status="")
    assert result["ok_to_create"]


def test_existing_unknown_db_blocks_creation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_bootstrap_csv(paths.bootstrap_csv)
    paths.provider_db.parent.mkdir()
    paths.provider_db.write_text("unknown", encoding="utf-8")
    assert not preflight(paths, api_key_configured=True, git_status="")["ok_to_create"]


def test_5y_bulk_only_and_no_10y_or_full_request(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    opener = FakeOpener(_zip_bytes())
    manifest = download_sharadar_5y_bulk(paths, api_key="secret", opener=opener)
    url = opener.requests[0].full_url
    assert "years=5" in url
    assert "years=10" not in url
    assert "years=full" not in url
    assert manifest["status"] == "SUCCESS"


def test_default_urlopen_uses_timeout_keyword(tmp_path: Path, monkeypatch: Any) -> None:
    import rawcandle.fundamentals.schema.production_bootstrap as module

    paths = _paths(tmp_path)
    calls = []

    def fake_urlopen(request: Request, *args: Any, **kwargs: Any) -> FakeResponse:
        calls.append((request, args, kwargs))
        return FakeResponse(_zip_bytes())

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    manifest = module.download_sharadar_5y_bulk(paths, api_key="secret")
    assert manifest["status"] == "SUCCESS"
    assert calls
    assert calls[0][1] == ()
    assert calls[0][2]["timeout"] == 120.0


def test_zip_manifest_hash(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manifest = download_sharadar_5y_bulk(paths, api_key="secret", opener=FakeOpener(_zip_bytes()))
    assert manifest["zip_size"] > 0
    assert len(manifest["zip_sha256"]) == 64
    assert manifest["extracted_rows"] == 9


def test_provider_universe_matching_and_unmatched_reporting(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    summary = json.loads((paths.artifact_root / "provider_ingest_summary.json").read_text())
    assert summary["rows_matched_to_target_universe"] == 7
    assert summary["rows_excluded_outside_target"] == 1
    assert summary["rows_excluded_dimension"] == 1
    assert summary["identity_match"]["bulk_permaticker_field_present"] is True
    assert summary["identity_match"]["bulk_rows_with_permaticker"] == 9
    assert summary["identity_match"]["matched_rows_with_permaticker"] == 7
    assert summary["identity_match"]["permaticker_links_inserted"] == 4
    assert summary["identity_match"]["permaticker_conflicts"] == 0
    assert summary["identity_match"]["ticker_security_collisions"] == 0
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_security_identity WHERE provider='SHARADAR'").fetchone()[0] == 4
        aapl = conn.execute(
            """
            SELECT s.current_ticker
            FROM provider_security_identity psi
            JOIN security s ON s.security_id=psi.security_id
            WHERE psi.provider='SHARADAR' AND psi.provider_security_id='199059'
            """
        ).fetchone()
        assert aapl["current_ticker"] == "AAPL"


def test_company_security_bootstrap_and_cik_null_allowed(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM security").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0] == 4


def test_fiscal_anchor_bootstrap(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company_fiscal_year_anchor").fetchone()[0] > 0


def test_arq_and_mrq_ingest(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    counts = json.loads((paths.artifact_root / "provider_ingest_summary.json").read_text())["provider_counts"]
    assert counts["arq_observations"] == 5
    assert counts["mrq_observations"] == 2


def test_non_quarterly_dimensions_excluded(tmp_path: Path) -> None:
    assert ALLOWED_DIMENSIONS == {"ARQ", "MRQ"}


def test_arq_canonicalization(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0] == 5


def test_fiscalperiod_parser_explicit_q4_reportperiod_and_all_12_fields(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM v4_quarter WHERE fiscal_quarter='Q4'").fetchone()[0] == 1
        assert conn.execute("SELECT period_end FROM v4_quarter WHERE source_fiscalperiod='2026-Q1' AND company_id=(SELECT company_id FROM security WHERE current_ticker='AAPL')").fetchone()[0] == "2025-12-27"
        assert canonical_field_contract_present(conn)


def test_sharesbas_source_availability_and_first_public_date(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        row = conn.execute("SELECT f.shares_outstanding, q.source_availability_date, q.first_public_result_date FROM v4_quarter q JOIN v4_quarter_financials f ON f.quarter_id=q.quarter_id LIMIT 1").fetchone()
        assert row["shares_outstanding"] is not None
        assert row["source_availability_date"] == "2026-08-30"
        assert row["first_public_result_date"] is None


def test_provenance_every_non_null_field_provider_null_and_zero_preserved(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT revenue FROM v4_quarter_financials f JOIN v4_quarter q ON q.quarter_id=f.quarter_id JOIN security s ON s.company_id=q.company_id WHERE s.current_ticker='AAPL' AND q.source_fiscalperiod='2026-Q1'").fetchone()[0] == 0
        for field in V4_CANONICAL_FINANCIAL_FIELDS:
            assert read_provenance(conn, canonical_field=field)


def test_fcf_and_debt_consistency(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    assert fcf_reconciliation(paths)["EXACT"] == 7
    assert debt_reconciliation(paths)["EXACT"] == 7


def test_duplicate_quarter_and_provider_observation_prevention(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    first = baseline_fingerprints(paths)
    ingest_bulk_provider_rows(paths, "run", "now")
    canonicalize_arq_production(paths, "now")
    assert first == baseline_fingerprints(paths)


def test_replay_idempotency_and_fingerprints_deterministic(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    before = baseline_fingerprints(paths)
    summary = replay(paths, before, "now")
    assert summary["changed_canonical_values"] == 0
    assert summary["duplicate_rows_created"] == 0
    assert summary["fingerprints_identical"]


def test_hard_cases(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    results = {row["ticker"]: row for row in hard_case_validation(paths)}
    assert results["AAPL"]["result"] == "PASS"
    assert results["WDAY"]["result"] == "PASS"
    assert results["ASTH"]["result"] == "PASS"
    assert results["CECO"]["result"] == "PASS"


def test_no_mrq_canonical_overwrite(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT revenue FROM v4_quarter_financials f JOIN v4_quarter q ON q.quarter_id=f.quarter_id JOIN security s ON s.company_id=q.company_id WHERE s.current_ticker='AAPL' AND q.source_fiscalperiod='2026-Q1'").fetchone()[0] == 0


def test_no_yahoo_or_sec_ingest(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    with connect(paths.provider_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_observation WHERE provider IN ('YAHOO','SEC')").fetchone()[0] == 0


def test_no_v3_writes_and_api_key_redaction() -> None:
    import rawcandle.fundamentals.schema.production_bootstrap as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "rc_fundamentals_v3.db" not in source
    assert "from swingmaster" not in source
    assert "import swingmaster" not in source
    assert "/home/kalle/projects/swingmaster" not in source
    assert "YOUR_KEY_HERE" not in source
    assert "SHARADAR_API_KEY=" not in source


def test_analysis_db_empty_and_no_ttm_execution(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    _, canonical, analysis, _ = production_integrity(paths)
    assert canonical["ttm_rows"] == 0
    assert analysis["score_rows"] == 0
    assert analysis["lifecycle_rows"] == 0
    assert analysis["valuation_rows"] == 0


def test_cross_db_integrity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    _, _, _, cross = production_integrity(paths)
    assert sum(cross.values()) == 0


def test_csv_profile_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "bulk.csv"
    _write_bulk_csv(path)
    rows, columns, dimensions = csv_profile(path)
    assert rows == 9
    assert columns > 20
    assert {"ARQ", "MRQ", "ART"} <= dimensions


def test_target_tickers(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_bootstrap_csv(paths.bootstrap_csv)
    assert "AAPL" in target_tickers(paths.bootstrap_csv)


def test_field_coverage_latest_windows_contract(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    overall, latest8, latest4, latest1, summary = field_coverage(paths)
    assert len(overall) == 13
    assert len(latest8) == 13
    assert len(latest4) == 13
    assert len(latest1) == 13
    assert "companies_with_8_quarters" in summary
    assert "companies_with_4_quarters" in summary
    assert "companies_with_latest_quarter" in summary


def test_q4_global_coverage_and_continuity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    q4 = q4_global_coverage(paths)
    _, continuity = quarter_continuity(paths)
    assert q4["explicit_q4_present"] >= 0
    assert sum(continuity.values()) > 0


def test_anchor_classification() -> None:
    class Row(dict):
        def __getitem__(self, item: str) -> Any:
            return dict.__getitem__(self, item)

    assert classify_anchor("2026-04-30", Row(fiscal_year_start="2026-02-01"), None) == "ANCHOR_VALIDATED"


def test_sharesbas_audit(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _bootstrap(paths)
    summary = sharesbas_audit(paths)
    assert summary["populated"] == 5
    assert summary.get("zero", 0) == 0
    assert summary.get("negative", 0) == 0


def test_run_production_bootstrap_with_fake_bulk(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_bootstrap_csv(paths.bootstrap_csv)
    summary = run_production_bootstrap(paths, api_key="secret", git_status="", opener=FakeOpener(_zip_bytes()))
    assert summary["classification"] in {"V4_PRODUCTION_BOOTSTRAP_COMPLETE", "V4_PRODUCTION_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS"}
    assert paths.provider_db.exists()
    assert paths.canonical_db.exists()
    assert paths.analysis_db.exists()


def test_missing_key_blocks_before_download(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_bootstrap_csv(paths.bootstrap_csv)
    summary = run_production_bootstrap(paths, api_key=None, git_status="", opener=FakeOpener(_zip_bytes()))
    assert summary["classification"] == "V4_PRODUCTION_BOOTSTRAP_BLOCKED"
    assert "sharadar_key_missing" in summary["blocking_reasons"]
