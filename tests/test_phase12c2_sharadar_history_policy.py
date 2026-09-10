from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from urllib.request import Request

import pytest

from rawcandle.fundamentals.schema.migrations import bootstrap_all
from rawcandle.fundamentals.schema.production_bootstrap import (
    ProductionPaths, download_sharadar_bulk, download_sharadar_fundamentals_bulk,
    ingest_bulk_provider_rows, run_production_bootstrap,
)
from rawcandle.fundamentals.schema.sharadar_history_policy import (
    MINIMUM_HISTORY_YEARS, POLICY_FINGERPRINT, POLICY_VERSION,
    enforce_production_history_years, history_policy_metadata,
)
from rawcandle.research.phase12c1_audit import discover_history_policy


FIELDS = [
    "ticker", "permaticker", "dimension", "calendardate", "reportperiod",
    "fiscalperiod", "date", "lastupdated", "revenue", "opinc", "fcf",
    "cashneq", "debt", "sharesbas",
]


class Response:
    status = 200
    url = "https://static.example/fundamentals.zip"
    headers = {"Content-Type": "application/zip"}

    def __init__(self, payload: bytes):
        self.payload = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self.payload.read(size)

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url


def _zip() -> bytes:
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerow(_row("2015-06-30", "2015-Q2", "2026-01-01"))
    writer.writerow({**_row("2016-06-30", "2016-Q2", "2026-01-01"), "dimension": "MRQ"})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("fundamentals.csv", text.getvalue())
    return output.getvalue()


def _row(period: str, fiscalperiod: str, updated: str) -> dict[str, str]:
    return {
        "ticker": "AAA", "permaticker": "1", "dimension": "ARQ",
        "calendardate": period, "reportperiod": period,
        "fiscalperiod": fiscalperiod, "date": updated, "lastupdated": updated,
        "revenue": "100", "opinc": "", "fcf": "10", "cashneq": "20",
        "debt": "0", "sharesbas": "10",
    }


def _paths(tmp_path: Path) -> ProductionPaths:
    artifact = tmp_path / "artifacts"
    return ProductionPaths(
        tmp_path, artifact, tmp_path / "provider.db", tmp_path / "canonical.db",
        tmp_path / "analysis.db", tmp_path / "universe.csv",
        artifact / "fundamentals.zip", artifact / "fundamentals.csv",
    )


def _opener(payload: bytes, seen: list[Request]):
    def open_request(request: Request, timeout: float) -> Response:
        del timeout
        seen.append(request)
        return Response(payload)
    return open_request


def test_contract_has_one_versioned_ten_year_minimum() -> None:
    assert MINIMUM_HISTORY_YEARS == 10
    assert POLICY_VERSION == "SHARADAR_FUNDAMENTALS_HISTORY_POLICY_V1"
    assert POLICY_FINGERPRINT == "1e025bf2a19d494cc1dd6ce3a0b49d94a966db008476f780c7e4dd671cd543b9"
    assert enforce_production_history_years() == MINIMUM_HISTORY_YEARS
    assert enforce_production_history_years(12) == 12


def test_production_downloader_defaults_to_ten_and_records_policy(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    seen: list[Request] = []
    manifest = download_sharadar_fundamentals_bulk(
        paths, api_key="fixture-secret", opener=_opener(_zip(), seen)
    )
    assert len(seen) == 1
    assert "years=10" in seen[0].full_url
    assert manifest["history_policy"] == history_policy_metadata()
    assert manifest["staged_observed_ranges"]["ARQ"]["oldest"] == "2015-06-30"
    serialized = json.dumps(manifest)
    assert "fixture-secret" not in serialized


def test_production_boundary_rejects_less_than_ten_before_network(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    called = []
    with pytest.raises(ValueError, match="at least 10 years"):
        download_sharadar_fundamentals_bulk(
            paths, history_years=9, api_key="fixture-secret",
            opener=_opener(_zip(), called),
        )
    assert called == []
    assert not paths.artifact_root.exists()


def test_complete_production_bootstrap_rejects_less_than_ten_before_preflight(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    called: list[Request] = []
    with pytest.raises(ValueError, match="at least 10 years"):
        run_production_bootstrap(
            paths,
            history_years=9,
            api_key="fixture-secret",
            opener=_opener(_zip(), called),
        )
    assert called == []
    assert not paths.artifact_root.exists()


def test_low_level_generic_downloader_remains_explicitly_separate(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    seen: list[Request] = []
    manifest = download_sharadar_bulk(
        paths, years=5, api_key="fixture-secret", opener=_opener(_zip(), seen)
    )
    assert "years=5" in seen[0].full_url
    assert "history_policy" not in manifest


def test_append_only_retains_absent_old_rows_revisions_nulls_and_other_provider_data(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute(
            "INSERT INTO company VALUES(1,'AAA','AAA','ACTIVE','now','now')"
        )
        connection.execute(
            "INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) "
            "VALUES(1,1,'AAA',1,'now','now')"
        )
    paths.bootstrap_csv.write_text("ticker\nAAA\n", encoding="utf-8")
    paths.artifact_root.mkdir()
    with paths.extracted_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([
            _row("2010-12-31", "2010-Q4", "2011-02-01"),
            _row("2025-12-31", "2025-Q4", "2026-02-01"),
        ])
    with sqlite3.connect(paths.provider_db) as connection:
        connection.execute(
            "INSERT INTO provider_run VALUES('other','YAHOO','now','now','SUCCESS','prices',NULL,NULL,'{}')"
        )
        connection.execute(
            "INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,native_table,"
            "fetched_at_utc,content_hash,provider_status,payload_json) "
            "VALUES('other-observation','other','YAHOO','AAA|2025-01-01','prices','now','hash','SUCCESS','{}')"
        )
    policy = history_policy_metadata()
    first = ingest_bulk_provider_rows(paths, "first", "now", history_policy=policy)
    with paths.extracted_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(_row("2025-12-31", "2025-Q4", "2026-03-01"))
    second = ingest_bulk_provider_rows(paths, "second", "later", history_policy=policy)
    replay = ingest_bulk_provider_rows(paths, "replay", "later", history_policy=policy)
    with sqlite3.connect(paths.provider_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM provider_observation WHERE provider='SHARADAR'").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM provider_observation WHERE provider='YAHOO'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM provider_observation WHERE calendardate='2010-12-31'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM provider_observation WHERE fiscalperiod='2025-Q4'").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE opinc IS NULL").fetchone()[0] == 3
        metadata = json.loads(connection.execute("SELECT metadata_json FROM provider_run WHERE run_id='second'").fetchone()[0])
    assert first["inserted_by_dimension"] == {"ARQ": 2}
    assert second["inserted_by_dimension"] == {"ARQ": 1}
    assert replay["inserted_by_dimension"] == {}
    assert second["retained_observed_ranges"]["ARQ"]["oldest"] == "2010-12-31"
    assert metadata["history_policy"]["retention_mode"] == "APPEND_ONLY_NO_WINDOW_PRUNING"


def test_applicable_production_paths_have_no_five_year_default() -> None:
    root = Path(__file__).resolve().parents[1]
    applicable = [
        root / "rawcandle/fundamentals/schema/production_bootstrap.py",
        root / "rawcandle/cli/run_fundamentals_v4_production_bootstrap.py",
        root / "rawcandle/cli/run_phase12c_sharadar_backfill.py",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in applicable)
    phase12c_cli = applicable[2].read_text(encoding="utf-8")
    assert "download_sharadar_5y_bulk" not in joined
    assert "years=5" not in joined
    assert "years = 5" not in joined
    assert "download_sharadar_fundamentals_bulk(" in phase12c_cli
    assert "download_sharadar_bulk(" not in phase12c_cli


def test_phase12c1_policy_discovery_recognizes_corrected_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    policy, _ = discover_history_policy(root)
    assert policy["verdict"] == "PERMANENT_TEN_YEAR_POLICY_VERIFIED"
    assert policy["can_regress_to_five_years"] is False
