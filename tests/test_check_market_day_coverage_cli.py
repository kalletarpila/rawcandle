from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rawcandle.cli import check_market_day_coverage as cli


def _build_test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "osakedata.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT NOT NULL,
            pvm TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            market TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


def _insert_day(
    db_path: Path,
    *,
    date: str,
    tickers: list[str],
    market: str = "usa",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, 1.0, 1.0, 1.0, 1.0, 1000, ?)
        """,
        [(ticker, date, market) for ticker in tickers],
    )
    conn.commit()
    conn.close()


def test_normal_coverage_report(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=tickers)
    _insert_day(db_path, date="2026-06-13", tickers=tickers)
    _insert_day(db_path, date="2026-06-16", tickers=tickers)

    report = cli.build_coverage_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        reference_window_days=10,
        min_reference_count=3,
    )

    assert report.previous_reference_date == "2026-06-12"
    assert report.next_reference_date == "2026-06-16"
    assert report.expected_tickers_count == 5
    assert report.present_tickers_count == 5
    assert report.missing_tickers_count == 0
    assert report.coverage_ratio == 1.0
    assert report.classification == cli.CLASSIFICATION_NORMAL_COVERAGE
    assert report.gap_position == cli.GAP_POSITION_INTERIOR
    assert (
        report.downstream_recompute_mode
        == cli.DOWNSREAM_RECOMPUTE_MODE_FORWARD
    )


def test_interior_day_level_gap_report(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-16", tickers=all_tickers)

    report = cli.build_coverage_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        reference_window_days=10,
        min_reference_count=3,
    )

    assert report.expected_tickers_count == 5
    assert report.present_tickers_count == 2
    assert report.missing_tickers_count == 3
    assert report.missing_tickers == ["NVDA", "QQQ", "SPY"]
    assert report.classification == cli.CLASSIFICATION_DAY_LEVEL_GAP
    assert report.gap_position == cli.GAP_POSITION_INTERIOR
    assert (
        report.downstream_recompute_mode
        == cli.DOWNSREAM_RECOMPUTE_MODE_FORWARD
    )


def test_latest_right_edge_day_level_gap_report(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])

    report = cli.build_coverage_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        reference_window_days=10,
        min_reference_count=3,
    )

    assert report.previous_reference_date == "2026-06-12"
    assert report.next_reference_date is None
    assert report.expected_tickers_count == 5
    assert report.present_tickers_count == 2
    assert report.missing_tickers_count == 3
    assert report.classification == cli.CLASSIFICATION_DAY_LEVEL_GAP
    assert report.gap_position == cli.GAP_POSITION_LATEST_OR_RIGHT_EDGE
    assert (
        report.downstream_recompute_mode
        == cli.DOWNSREAM_RECOMPUTE_MODE_LATEST
    )


def test_text_output_respects_missing_limit(tmp_path, capsys) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAA"])
    _insert_day(db_path, date="2026-06-16", tickers=all_tickers)

    code = cli.main(
        [
            "--db",
            str(db_path),
            "--market",
            "usa",
            "--date",
            "2026-06-13",
            "--missing-limit",
            "2",
            "--min-reference-count",
            "3",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "missing_tickers: 5" in captured.out
    assert "classification: DAY_LEVEL_GAP" in captured.out
    assert "gap_position: INTERIOR_GAP" in captured.out
    assert (
        "downstream_recompute_mode: FROM_RECOVERED_DATE_FORWARD_REQUIRED"
        in captured.out
    )
    assert "BBB" in captured.out
    assert "CCC" in captured.out
    assert "DDD" not in captured.out


def test_json_output_contains_expected_fields(tmp_path, capsys) -> None:
    db_path = _build_test_db(tmp_path)
    tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-16", tickers=tickers)

    code = cli.main(
        [
            "--db",
            str(db_path),
            "--market",
            "usa",
            "--date",
            "2026-06-13",
            "--format",
            "json",
            "--min-reference-count",
            "3",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["market"] == "usa"
    assert payload["target_date"] == "2026-06-13"
    assert payload["previous_reference_date"] == "2026-06-12"
    assert payload["next_reference_date"] == "2026-06-16"
    assert payload["expected_tickers_count"] == 5
    assert payload["present_tickers_count"] == 2
    assert payload["missing_tickers_count"] == 3
    assert payload["classification"] == "DAY_LEVEL_GAP"
    assert payload["gap_position"] == "INTERIOR_GAP"
    assert (
        payload["downstream_recompute_mode"]
        == "FROM_RECOVERED_DATE_FORWARD_REQUIRED"
    )
    assert payload["missing_tickers"] == ["NVDA", "QQQ", "SPY"]


def test_no_reference_dates_is_handled(tmp_path, capsys) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])

    code = cli.main(
        [
            "--db",
            str(db_path),
            "--market",
            "usa",
            "--date",
            "2026-06-13",
            "--reference-window-days",
            "2",
            "--min-reference-count",
            "3",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "previous_reference_date: NONE" in captured.out
    assert "next_reference_date: NONE" in captured.out
    assert "classification: NO_REFERENCE_DATES" in captured.out
    assert "gap_position: NO_REFERENCE" in captured.out
    assert (
        "downstream_recompute_mode: REPORT_ONLY_NO_SAFE_RECOMPUTE_MODE"
        in captured.out
    )
