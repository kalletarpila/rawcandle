from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli.result_publication_research_export import main
from rawcandle.fundamentals.result_publication_daily_research import RULE_VERSION, YahooEvent
from rawcandle.fundamentals.result_publication_daily_research_service import QuarterKey
from rawcandle.fundamentals.result_publication_research_export import (
    EXPORT_COLUMNS,
    V2_ARTIFACT_VERSION,
    YAHOO_ARTIFACT_VERSION,
    ExportRequest,
    RecordingYahooObservationProvider,
    load_v2_candidate_artifact,
    load_yahoo_observation_artifact,
    run_research_export,
    validate_v2_candidate_artifact,
    write_yahoo_observation_artifact,
)


NOW = "2026-09-29T12:00:00Z"
DATES = ("2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23", "2026-01-26")


class FailingYahooProvider:
    def get_events(self, key: QuarterKey, ticker: str, period_end: str):
        del key, ticker, period_end
        raise RuntimeError("offline")


class StaticYahooProvider:
    def __init__(self) -> None:
        self.calls: list[QuarterKey] = []

    def get_events(self, key: QuarterKey, ticker: str, period_end: str):
        del ticker, period_end
        self.calls.append(key)
        return (YahooEvent("2026-01-20T16:00:00-05:00"),)


def _databases(tmp_path: Path) -> tuple[Path, Path]:
    canonical = tmp_path / "canonical.db"
    ohlc = tmp_path / "osakedata.db"
    with sqlite3.connect(canonical) as connection:
        connection.executescript(
            """
            CREATE TABLE v4_quarter(
                quarter_id INTEGER PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,
                fiscal_quarter TEXT,period_end TEXT
            );
            CREATE TABLE v4_result_publication_authority(
                company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,quarter_id INTEGER,
                status TEXT,result_publication_timestamp_utc TEXT,
                result_publication_evidence_reference TEXT,selected_evidence_id TEXT,
                PRIMARY KEY(company_id,fiscal_year,fiscal_quarter)
            );
            CREATE TABLE v4_result_publication_evidence(
                evidence_id TEXT PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,
                fiscal_quarter TEXT,source_type TEXT,source_timestamp_utc TEXT,
                source_reference TEXT,accession_number TEXT,disposition TEXT
            );
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,active INTEGER
            );
            """
        )
        authority = (
            (1, "VERIFIED", "2026-01-20T13:00:00Z", "AAA"),
            (2, "AMBIGUOUS", None, "BBB"),
            (3, "UNRESOLVED", None, "CCC"),
            (4, "NOT_FOUND", None, "DDD"),
        )
        for company_id, status, timestamp, ticker in authority:
            connection.execute(
                "INSERT INTO v4_quarter VALUES(?,?,?,?,?)",
                (company_id, company_id, 2025, "Q4", "2025-12-31"),
            )
            connection.execute(
                "INSERT INTO v4_result_publication_authority VALUES(?,?,?,?,?,?,?,?)",
                (
                    company_id,
                    2025,
                    "Q4",
                    company_id,
                    status,
                    timestamp,
                    "https://example.test/a1" if company_id == 1 else None,
                    "e1" if company_id == 1 else None,
                ),
            )
            connection.execute("INSERT INTO security VALUES(?,?,?,1)", (company_id, company_id, ticker))
        evidence = (
            ("e1", 1, "2026-01-20T13:00:00Z", "acc-1", "ACCEPTED"),
            ("e2a", 2, "2026-01-20T22:00:00Z", "acc-2-a", "CONFLICT"),
            ("e2b", 2, "2026-01-23T22:00:00Z", "acc-2-b", "CONFLICT"),
        )
        for evidence_id, company_id, timestamp, accession, disposition in evidence:
            connection.execute(
                "INSERT INTO v4_result_publication_evidence VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    evidence_id,
                    company_id,
                    2025,
                    "Q4",
                    "SEC_8K_ITEM_2_02",
                    timestamp,
                    f"https://example.test/{evidence_id}",
                    accession,
                    disposition,
                ),
            )
    with sqlite3.connect(ohlc) as connection:
        connection.execute("CREATE TABLE osakedata(osake TEXT,pvm TEXT)")
        for ticker in ("AAA", "BBB", "CCC", "DDD"):
            connection.executemany("INSERT INTO osakedata VALUES(?,?)", [(ticker, day) for day in DATES])
        connection.execute("CREATE UNIQUE INDEX idx_osake_pvm ON osakedata(osake,pvm)")
    return canonical, ohlc


def _yahoo_artifact(path: Path, *, valid: bool = True) -> Path:
    payload = {
        "artifact_version": YAHOO_ARTIFACT_VERSION if valid else "wrong",
        "created_at_utc": NOW,
        "projection_rule_version": RULE_VERSION,
        "source_scope": "fixture",
        "observations": [
            {
                "company_id": 2,
                "fiscal_year": 2025,
                "fiscal_quarter": "Q4",
                "ticker_used": "HISTORICAL-BBB",
                "yahoo_event_timestamp": "2026-01-20T16:00:00-05:00",
                "yahoo_event_timezone": "America/New_York",
                "observed_at_utc": NOW,
                "provider": "YAHOO_FINANCE",
                "transport": "yfinance",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _v2_artifact(path: Path, *, reference: str = "https://example.test/e2b", valid: bool = True) -> Path:
    payload = {
        "artifact_version": V2_ARTIFACT_VERSION if valid else "wrong",
        "created_at_utc": NOW,
        "projection_rule_version": RULE_VERSION,
        "candidates": [
            {
                "company_id": 2,
                "fiscal_year": 2025,
                "fiscal_quarter": "Q4",
                "selected_candidate_id": "acc-2-b",
                "selected_evidence_reference": reference,
                "selected_candidate_timestamp_utc": "2026-01-23T22:00:00Z",
                "classifier_version": "initial_result_sec_semantic_v2_research",
                "review_status": "ACCEPTED",
                "reviewed_at_utc": NOW,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _request(tmp_path: Path, **changes) -> ExportRequest:
    canonical, ohlc = _databases(tmp_path)
    values = {
        "canonical_db": canonical,
        "ohlc_db": ohlc,
        "output": tmp_path / "result.csv",
    }
    values.update(changes)
    return ExportRequest(**values)


def test_artifact_parsing_and_stable_quarter_identity(tmp_path: Path) -> None:
    yahoo = load_yahoo_observation_artifact(_yahoo_artifact(tmp_path / "yahoo.json"))
    v2 = load_v2_candidate_artifact(_v2_artifact(tmp_path / "v2.json"))
    key = QuarterKey(2, 2025, "Q4")
    assert [event.timestamp for event in yahoo.provider.get_events(key, "BBB", "2025-12-31")] == [
        "2026-01-20T16:00:00-05:00"
    ]
    assert v2.provider.get_candidate_id(key) == "acc-2-b"


def test_invalid_yahoo_and_v2_artifacts_fail_clearly(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="YAHOO_ARTIFACT_VERSION_INVALID"):
        load_yahoo_observation_artifact(_yahoo_artifact(tmp_path / "bad-yahoo.json", valid=False))
    with pytest.raises(ValueError, match="V2_ARTIFACT_VERSION_INVALID"):
        load_v2_candidate_artifact(_v2_artifact(tmp_path / "bad-v2.json", valid=False))


def test_v2_artifact_must_match_current_sec_evidence(tmp_path: Path) -> None:
    canonical, _ = _databases(tmp_path)
    valid = validate_v2_candidate_artifact(canonical, _v2_artifact(tmp_path / "v2.json"))
    assert valid.row_count == 1
    with pytest.raises(ValueError, match="V2_CANDIDATE_NOT_CURRENT"):
        validate_v2_candidate_artifact(
            canonical,
            _v2_artifact(tmp_path / "stale-v2.json", reference="https://example.test/stale"),
        )


def test_csv_columns_default_filter_and_metadata_sidecar(tmp_path: Path) -> None:
    metadata = run_research_export(_request(tmp_path), generated_at_utc=NOW)
    with (tmp_path / "result.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == EXPORT_COLUMNS
    assert [row["ticker"] for row in rows] == ["AAA"]
    assert metadata["evaluated_rows"] == 4
    assert metadata["exported_rows"] == 1
    sidecar = json.loads((tmp_path / "result.csv.metadata.json").read_text())
    assert sidecar["canonical_db_sha256"]
    assert sidecar["ohlc_db_sha256"]
    assert sidecar["projection_rule_version"] == RULE_VERSION


def test_include_unusable_and_jsonl_full_scope(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        output=tmp_path / "result.jsonl",
        output_format="jsonl",
        include_unusable=True,
    )
    metadata = run_research_export(request, generated_at_utc=NOW)
    rows = [json.loads(line) for line in request.output.read_text().splitlines()]
    assert len(rows) == 4
    assert metadata["status_counts"] == {"EXACT": 1, "UNUSABLE": 3}


def test_frozen_yahoo_is_reproducible_and_yahoo_only_adds_high_row(tmp_path: Path) -> None:
    yahoo = _yahoo_artifact(tmp_path / "yahoo.json")
    first = _request(
        tmp_path,
        output=tmp_path / "first.csv",
        yahoo_mode="frozen",
        yahoo_observations=yahoo,
    )
    second = ExportRequest(**{**first.__dict__, "output": tmp_path / "second.csv"})
    first_meta = run_research_export(first, generated_at_utc=NOW)
    second_meta = run_research_export(second, generated_at_utc=NOW)
    assert first.output.read_bytes() == second.output.read_bytes()
    assert first_meta["status_counts"] == second_meta["status_counts"] == {
        "EXACT": 1,
        "HEURISTIC_HIGH": 1,
        "UNUSABLE": 2,
    }


def test_v2_only_and_combined_modes_use_validated_candidate(tmp_path: Path) -> None:
    v2 = _v2_artifact(tmp_path / "v2.json")
    v2_only = _request(tmp_path, output=tmp_path / "v2.csv", v2_candidates=v2)
    combined = ExportRequest(
        **{
            **v2_only.__dict__,
            "output": tmp_path / "combined.csv",
            "yahoo_mode": "frozen",
            "yahoo_observations": _yahoo_artifact(tmp_path / "yahoo.json"),
        }
    )
    v2_meta = run_research_export(v2_only, generated_at_utc=NOW)
    combined_meta = run_research_export(combined, generated_at_utc=NOW)
    assert v2_meta["status_counts"] == combined_meta["status_counts"] == {
        "EXACT": 1,
        "HEURISTIC_HIGH": 1,
        "UNUSABLE": 2,
    }
    with v2_only.output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[1]["research_method"] == "SEC_V2_STRONG_INITIAL"


def test_live_yahoo_failure_degrades_and_is_recorded(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        include_unusable=True,
        yahoo_mode="live",
        write_yahoo_observations=tmp_path / "live-yahoo.json",
    )
    metadata = run_research_export(
        request,
        generated_at_utc=NOW,
        live_yahoo_provider=FailingYahooProvider(),
    )
    assert metadata["status_counts"] == {"EXACT": 1, "UNUSABLE": 3}
    assert len(metadata["yahoo_live_errors"]) == 1
    frozen = json.loads((tmp_path / "live-yahoo.json").read_text())
    assert frozen["observations"] == []
    assert len(frozen["provider_errors"]) == 1


def test_live_yahoo_writes_only_observations_actually_requested(tmp_path: Path) -> None:
    provider = StaticYahooProvider()
    request = _request(
        tmp_path,
        yahoo_mode="live",
        write_yahoo_observations=tmp_path / "live-yahoo.json",
    )
    metadata = run_research_export(request, generated_at_utc=NOW, live_yahoo_provider=provider)
    assert provider.calls == [QuarterKey(2, 2025, "Q4")]
    assert metadata["yahoo_live_observations"] == 1
    loaded = load_yahoo_observation_artifact(tmp_path / "live-yahoo.json")
    assert loaded.row_count == 1


def test_single_ticker_cli_and_canonical_database_remain_read_only(tmp_path: Path, capsys) -> None:
    canonical, ohlc = _databases(tmp_path)
    before = canonical.read_bytes()
    output = tmp_path / "aaa.csv"
    result = main(
        [
            "--canonical-db",
            str(canonical),
            "--ohlc-db",
            str(ohlc),
            "--output",
            str(output),
            "--tickers",
            "AAA",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["evaluated_rows"] == 1
    assert canonical.read_bytes() == before


def test_cli_rejects_frozen_mode_without_artifact(tmp_path: Path, capsys) -> None:
    canonical, ohlc = _databases(tmp_path)
    result = main(
        [
            "--canonical-db",
            str(canonical),
            "--ohlc-db",
            str(ohlc),
            "--output",
            str(tmp_path / "bad.csv"),
            "--yahoo-mode",
            "frozen",
        ]
    )
    assert result == 2
    assert "YAHOO_FROZEN_ARTIFACT_REQUIRED" in capsys.readouterr().out
