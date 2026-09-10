from __future__ import annotations

import csv
import io
import sqlite3
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest

from rawcandle.fundamentals.schema.migrations import bootstrap_all
from rawcandle.fundamentals.schema.phase12c_backfill import (
    Phase12CPaths, import_staged, provider_counts, staged_provider_reconciliation,
    validate_staged_source,
)
from rawcandle.fundamentals.schema.production_bootstrap import (
    ProductionPaths, download_sharadar_bulk,
)
from rawcandle.cli import run_phase12c_sharadar_backfill as cli


FIELDS = [
    "ticker", "dimension", "calendardate", "reportperiod", "fiscalperiod", "date",
    "lastupdated", "revenue", "opinc", "ebit", "fcf", "cashneq", "debt", "sharesbas",
]


def test_cli_repository_root_is_the_checked_out_repository() -> None:
    assert (cli.ROOT / "rawcandle" / "cli" / "run_phase12c_sharadar_backfill.py").is_file()


class Response:
    status = 200
    headers = {"Content-Type": "application/zip"}
    url = "https://static.example/fundamentals.zip"

    def __init__(self, payload: bytes):
        self.payload = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self.payload.read(size)

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url


def write_source(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for dimension in ("ARQ", "MRQ"):
            writer.writerow({
                "ticker": "AAA", "dimension": dimension, "calendardate": "2016-09-30",
                "reportperiod": "2016-09-30", "fiscalperiod": "2016-Q3", "date": "2016-11-01",
                "lastupdated": "2026-01-01", "revenue": "100", "opinc": "",
                "ebit": "10", "fcf": "5", "cashneq": "20", "debt": "0", "sharesbas": "10",
            })


def fixture_paths(tmp_path: Path) -> Phase12CPaths:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    bootstrap_all(provider, canonical, analysis, "now")
    with sqlite3.connect(canonical) as conn:
        conn.execute("INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) VALUES(1,'AAA','AAA','ACTIVE','n','n')")
        conn.execute("INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) VALUES(1,1,'AAA',1,'n','n')")
    universe = tmp_path / "universe.csv"
    universe.write_text("ticker\nAAA\n", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    source = output / "sharadar_fundamentals_10y.csv"
    write_source(source)
    market = tmp_path / "market.db"; market.touch()
    taxonomy = tmp_path / "taxonomy.db"; taxonomy.touch()
    return Phase12CPaths(tmp_path, output, provider, canonical, analysis, market, taxonomy,
                         tmp_path / "reports", universe, tmp_path / "backups")


def test_download_propagates_ten_year_scope_without_exposing_key(tmp_path: Path) -> None:
    csv_bytes = (",".join(FIELDS) + "\n").encode()
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("fundamentals-10Y.csv", csv_bytes)
    artifact = tmp_path / "artifact"
    paths = ProductionPaths(tmp_path, artifact, tmp_path / "p", tmp_path / "c", tmp_path / "a",
                            tmp_path / "u", artifact / "ten.zip", artifact / "ten.csv")
    seen = {}
    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        return Response(payload.getvalue())
    result = download_sharadar_bulk(paths, years=10, manifest_name="manifest.json",
                                    api_key="top-secret", opener=opener)
    assert "years=10" in seen["url"]
    assert "top-secret" not in str(result)
    assert "top-secret" not in (artifact / "manifest.json").read_text()


def test_validation_rejects_history_that_does_not_extend(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_source(source)
    with pytest.raises(RuntimeError, match="HISTORY_NOT_EXTENDED"):
        validate_staged_source(source, target={"AAA"}, old_oldest_arq="2016-01-01")


def test_import_preserves_nulls_and_identical_replay_is_noop(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    validation = validate_staged_source(paths.staged_csv, target={"AAA"}, old_oldest_arq="2020-09-30")
    first = import_staged(paths, validation)
    second = import_staged(paths, validation)
    assert first["logical_changes"] == 2
    assert second["logical_changes"] == 0
    assert staged_provider_reconciliation(
        paths.staged_csv, paths.provider_db, target={"AAA"}
    ) == {"previously_stored_base_keys_absent_from_snapshot": 0, "unchanged": 2}
    assert provider_counts(paths.provider_db)["totals"]["observations"] == 2
    with sqlite3.connect(paths.provider_db) as conn:
        assert conn.execute("SELECT opinc FROM sharadar_fundamental_observation WHERE dimension='ARQ'").fetchone()[0] is None


def test_revision_is_preserved_as_a_new_provider_observation(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    validation = validate_staged_source(paths.staged_csv, target={"AAA"}, old_oldest_arq="2020-09-30")
    assert import_staged(paths, validation)["logical_changes"] == 2
    rows = list(csv.DictReader(paths.staged_csv.open(newline="", encoding="utf-8")))
    rows[0]["lastupdated"] = "2026-02-01"
    rows[0]["ebit"] = "11"
    with paths.staged_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    revised = validate_staged_source(paths.staged_csv, target={"AAA"}, old_oldest_arq="2020-09-30")
    assert staged_provider_reconciliation(
        paths.staged_csv, paths.provider_db, target={"AAA"}
    ) == {"previously_stored_base_keys_absent_from_snapshot": 0, "revised": 1, "unchanged": 1}
    assert import_staged(paths, revised)["logical_changes"] == 1
    assert provider_counts(paths.provider_db)["totals"]["observations"] == 3


def test_cli_rejects_nonproduction_database_path(tmp_path: Path) -> None:
    args = Namespace(
        provider_db=tmp_path / "wrong.db", canonical_db=cli.PRODUCTION["canonical"],
        analysis_db=cli.PRODUCTION["analysis"], market_db=cli.PRODUCTION["market"],
        taxonomy_db=cli.PRODUCTION["taxonomy"], backup_dir=cli.BACKUP_DIR,
        output=cli.ROOT / "temp/fundamentals_v4_phase12c/test-invalid-path",
        bootstrap_csv=cli.ROOT / "temp/v3_active_tickers_99_27.csv",
        apply=False, confirm=None,
    )
    with pytest.raises(RuntimeError, match="EXACT_PRODUCTION_PATHS_REQUIRED"):
        cli.validate_request(args)


def test_import_failure_rolls_back_all_rows_and_run(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    validation = validate_staged_source(paths.staged_csv, target={"AAA"}, old_oldest_arq="2020-09-30")
    with pytest.raises(RuntimeError, match="INJECTED_IMPORT_FAILURE"):
        import_staged(paths, validation, fail_after=1)
    with sqlite3.connect(paths.provider_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_observation").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM provider_run").fetchone()[0] == 0
