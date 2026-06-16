from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rawcandle.cli import plan_market_day_recovery as cli
from services.stock_update_service import StockOhlcvRow


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


def _row(ticker: str, target_date: str = "2026-06-13") -> StockOhlcvRow:
    return StockOhlcvRow(
        ticker=ticker,
        date=target_date,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=1000,
        market="usa",
    )


def test_latest_right_edge_gap_with_recoverable_rows(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])

    report = cli.build_recovery_plan_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        reference_window_days=10,
        min_reference_count=3,
        skip_provider_fetch=False,
        provider_fetcher=lambda market, target_date: {
            "NVDA": _row("NVDA"),
            "QQQ": _row("QQQ"),
        },
    )

    assert report.classification == "DAY_LEVEL_GAP"
    assert report.gap_position == "LATEST_OR_RIGHT_EDGE_GAP"
    assert report.downstream_recompute_mode == "LATEST_DAY_RECOMPUTE_OK"
    assert report.recovery_recommended is True
    assert report.recoverable_tickers_count == 2
    assert report.not_found_in_provider_count == 1
    assert report.recoverable_tickers == ["NVDA", "QQQ"]
    assert report.not_found_in_provider == ["SPY"]


def test_interior_gap_with_recoverable_rows(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-16", tickers=all_tickers)

    report = cli.build_recovery_plan_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        reference_window_days=10,
        min_reference_count=3,
        skip_provider_fetch=False,
        provider_fetcher=lambda market, target_date: {
            "NVDA": _row("NVDA"),
            "QQQ": _row("QQQ"),
            "SPY": _row("SPY"),
        },
    )

    assert report.gap_position == "INTERIOR_GAP"
    assert report.downstream_recompute_mode == "FROM_RECOVERED_DATE_FORWARD_REQUIRED"
    assert "Interior historical gap" in report.apply_safety_note
    assert report.recoverable_tickers_count == 3
    assert report.not_found_in_provider_count == 0


def test_no_day_level_gap_skips_provider_fetch(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=tickers)
    _insert_day(db_path, date="2026-06-13", tickers=tickers)
    _insert_day(db_path, date="2026-06-16", tickers=tickers)

    def fail_fetch(*args, **kwargs):
        raise AssertionError("provider should not be called")

    report = cli.build_recovery_plan_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        reference_window_days=10,
        min_reference_count=3,
        skip_provider_fetch=False,
        provider_fetcher=fail_fetch,
    )

    assert report.recovery_recommended is False
    assert report.provider_status == "SKIPPED"
    assert report.recoverable_tickers_count == 0


def test_skip_provider_fetch(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])

    def fail_fetch(*args, **kwargs):
        raise AssertionError("provider should not be called")

    report = cli.build_recovery_plan_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        reference_window_days=10,
        min_reference_count=3,
        skip_provider_fetch=True,
        provider_fetcher=fail_fetch,
    )

    assert report.provider_status == "SKIPPED"
    assert report.missing_tickers_count == 3


def test_json_output_contains_key_fields(tmp_path, capsys, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL", "MSFT"])

    monkeypatch.setattr(
        cli,
        "fetch_polygon_massive_grouped_daily_ohlcv_by_ticker",
        lambda market, target_date: {
            "NVDA": _row("NVDA"),
            "QQQ": _row("QQQ"),
        },
    )

    code = cli.main(
        [
            "--db",
            str(db_path),
            "--market",
            "usa",
            "--date",
            "2026-06-13",
            "--provider",
            "polygon_grouped_daily",
            "--format",
            "json",
            "--min-reference-count",
            "3",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["classification"] == "DAY_LEVEL_GAP"
    assert payload["gap_position"] == "LATEST_OR_RIGHT_EDGE_GAP"
    assert payload["downstream_recompute_mode"] == "LATEST_DAY_RECOMPUTE_OK"
    assert payload["recovery_recommended"] is True
    assert payload["recoverable_tickers_count"] == 2
    assert payload["not_found_in_provider_count"] == 1


def test_missing_examples_limit_in_text_output(tmp_path, capsys, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    all_tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    _insert_day(db_path, date="2026-06-12", tickers=all_tickers)
    _insert_day(db_path, date="2026-06-13", tickers=["AAA"])

    monkeypatch.setattr(
        cli,
        "fetch_polygon_massive_grouped_daily_ohlcv_by_ticker",
        lambda market, target_date: {
            "BBB": _row("BBB"),
            "CCC": _row("CCC"),
        },
    )

    code = cli.main(
        [
            "--db",
            str(db_path),
            "--market",
            "usa",
            "--date",
            "2026-06-13",
            "--provider",
            "polygon_grouped_daily",
            "--missing-limit",
            "1",
            "--min-reference-count",
            "3",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "recoverable_tickers: 2" in captured.out
    assert "not_found_in_provider: 3" in captured.out
    assert "BBB" in captured.out
    assert "CCC" not in captured.out
    assert "DDD" in captured.out or "EEE" in captured.out or "FFF" in captured.out
