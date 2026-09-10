from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import subprocess
import zipfile
from pathlib import Path

import pytest

from rawcandle.research.historical_universe import runner
from rawcandle.research.historical_universe.contract import CONTRACT_FINGERPRINT, HORIZONS, MODEL_DATA_RISK
from rawcandle.research.historical_universe.engine import (
    choose_latest,
    deterministic_rows,
    identity_status,
    label_feasibility,
    model_applicability,
    parse_cik,
    ranges_overlap,
    resolve_dated_alias,
    security_eligibility,
)


def test_contract_is_versioned_high_risk_and_has_four_locked_horizons() -> None:
    assert len(CONTRACT_FINGERPRINT) == 64
    assert MODEL_DATA_RISK == "HIGH - CURRENTLY_REVISED_NON_PIT_HISTORY"
    assert HORIZONS == (30, 60, 120, 180)


def test_archive_manifest_verifies_size_hash_member_and_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(runner.SOURCE_MEMBER, "ticker,dimension\nAAA,ARQ\n")
    source = tmp_path / "source.zip"
    copied = tmp_path / "archive.zip"
    source.write_bytes(payload.getvalue())
    copied.write_bytes(payload.getvalue())
    monkeypatch.setattr(runner, "SOURCE_SIZE", source.stat().st_size)
    monkeypatch.setattr(runner, "SOURCE_SHA256", hashlib.sha256(source.read_bytes()).hexdigest())
    result = runner.verify_archive(source, copied)
    assert result["verified"] is True
    assert result["member"] == runner.SOURCE_MEMBER


def test_revision_selection_is_deterministic_and_revision_aware() -> None:
    old = {"ticker": "AAA", "date": "2020-01-01", "lastupdated": "2020-02-01", "revenue": "1"}
    revised = {**old, "lastupdated": "2021-02-01", "revenue": "2"}
    assert choose_latest(None, old)
    assert choose_latest(old, revised)
    assert not choose_latest(revised, old)


def test_dated_alias_precedence_rejects_future_and_detects_ambiguity() -> None:
    aliases = [
        {"ticker": "OLD", "valid_from": "2018-01-01", "valid_to": "2020-12-31"},
        {"ticker": "NEW", "valid_from": "2021-01-01", "valid_to": ""},
    ]
    assert resolve_dated_alias("2020-06-01", aliases) == ("OLD", "IDENTITY_ALIAS_RESOLVED")
    assert resolve_dated_alias("2017-06-01", aliases) == (None, "IDENTITY_METADATA_REQUIRED")
    ambiguous = aliases + [{"ticker": "ALT", "valid_from": "2019-01-01", "valid_to": "2020-12-31"}]
    assert resolve_dated_alias("2020-06-01", ambiguous) == (None, "IDENTITY_AMBIGUOUS")


def test_identity_ticker_reuse_ambiguity_and_exact_dated_classification() -> None:
    values = dict(
        permaticker="1", first_fundamental="2019-01-01", last_fundamental="2021-01-01",
        metadata_first_quarter="2018-01-01", metadata_last_quarter="2022-01-01", market_count=1,
    )
    assert identity_status(metadata_count=1, **values) == "IDENTITY_EXACT_DATED"
    assert identity_status(metadata_count=2, **values) == "IDENTITY_REUSED_TICKER_RISK"
    assert identity_status(metadata_count=1, **{**values, "market_count": 2}) == "IDENTITY_AMBIGUOUS"
    assert identity_status(metadata_count=1, **{**values, "metadata_first_quarter": "2022-02-01"}) == "IDENTITY_REUSED_TICKER_RISK"


def test_security_model_and_exact_ticker_overlap_are_separate() -> None:
    assert security_eligibility("Domestic Common Stock") == "RESEARCH_SECURITY_ELIGIBLE"
    assert security_eligibility("ETF") == "RESEARCH_SECURITY_INELIGIBLE"
    assert security_eligibility(None) == "SECURITY_TYPE_METADATA_REQUIRED"
    assert model_applicability("Financial Services") == "FUNDAMENTAL_MODEL_NOT_APPLICABLE_CURRENT_CONTEXT"
    assert model_applicability(None) == "FUNDAMENTAL_MODEL_METADATA_REQUIRED"
    assert ranges_overlap("2020-01-01", "2021-01-01", "2020-06-01", "2022-01-01")
    assert not ranges_overlap("2010-01-01", "2011-01-01", "2020-01-01", "2021-01-01")


def test_label_window_threshold_qqq_alignment_and_censoring() -> None:
    sessions = [f"2020-01-{day:02d}" for day in range(1, 32)] + [f"2020-02-{day:02d}" for day in range(1, 30)]
    company = set(sessions)
    qqq = set(sessions)
    ready = label_feasibility(
        availability_date="2020-01-03", horizon=30, benchmark_sessions=sessions,
        qqq_sessions=qqq, company_sessions=company,
    )
    assert ready.status == "LABEL_FEASIBLE"
    assert ready.qqq_aligned is True
    qqq_without_exit = set(qqq)
    qqq_without_exit.remove(ready.exit_date)
    unaligned = label_feasibility(
        availability_date="2020-01-03", horizon=30, benchmark_sessions=sessions,
        qqq_sessions=qqq_without_exit, company_sessions=company,
    )
    assert unaligned.status == "LABEL_FEASIBLE"
    assert unaligned.qqq_aligned is False
    company = {day for day in company if day < ready.exit_date}
    censored = label_feasibility(
        availability_date="2020-01-03", horizon=30, benchmark_sessions=sessions,
        qqq_sessions=qqq, company_sessions=company,
    )
    assert censored.status == "RIGHT_CENSORED_UNRESOLVED_TERMINAL"
    company.add(sessions[-1])
    gap = label_feasibility(
        availability_date="2020-01-03", horizon=30, benchmark_sessions=sessions,
        qqq_sessions=qqq, company_sessions=company,
    )
    assert gap.status == "MISSING_EXACT_EXIT_TEMPORARY_GAP"


def test_missing_inputs_nonfinite_price_and_deterministic_output() -> None:
    assert label_feasibility(
        availability_date=None, horizon=30, benchmark_sessions=["2020-01-01"],
        qqq_sessions=set(), company_sessions=set(),
    ).status == "MISSING_AVAILABILITY_DATE"
    assert parse_cik("https://x.test/?CIK=0001234") == "0000001234"
    assert deterministic_rows([{"ticker": "B"}, {"ticker": "A"}], ("ticker",)) == [
        {"ticker": "A"}, {"ticker": "B"}
    ]


def test_readonly_connection_prevents_production_shaped_writes(tmp_path: Path) -> None:
    database = tmp_path / "fixture.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE evidence(value TEXT)")
    connection = runner.readonly(database)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        connection.execute("INSERT INTO evidence VALUES('forbidden')")
    connection.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0


def test_sources_and_serialized_contract_do_not_contain_credentials() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [
        root / "rawcandle/research/historical_universe/contract.py",
        root / "rawcandle/research/historical_universe/engine.py",
        root / "rawcandle/research/historical_universe/runner.py",
        root / "rawcandle/cli/run_phase12c3_historical_universe_audit.py",
    ]
    payload = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "sharadar_api_key" not in payload
    assert "x-api-key" not in payload
    assert "authorization:" not in payload


def test_durable_archive_path_is_ignored_without_hiding_research_code() -> None:
    root = Path(__file__).resolve().parents[1]
    archive = "data/source_archives/sharadar/fundamentals/fixture/source.zip"
    ignored = subprocess.run(
        ("git", "check-ignore", "--no-index", "-q", archive), cwd=root,
        check=False,
    )
    assert ignored.returncode == 0
    assert subprocess.run(
        ("git", "check-ignore", "--no-index", "-q", "rawcandle/research/historical_universe/engine.py"),
        cwd=root, check=False,
    ).returncode != 0
