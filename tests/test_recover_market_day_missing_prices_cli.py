from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rawcandle.cli import recover_market_day_missing_prices as cli
from services.stock_update_service import StockOhlcvRow, StockTickerDownstreamResult


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


def _runtime(call_log: dict) -> cli.RecoveryRuntimeAdapters:
    def stock_factory(ticker: str) -> str:
        call_log.setdefault("stock_factory", []).append(ticker)
        return f"stock:{ticker}"

    def maybe_update_quarter_state(ticker: str, market: str, stock: str) -> dict:
        call_log.setdefault("quarter_state", []).append((ticker, market, stock))
        return {"checked": True}

    return cli.RecoveryRuntimeAdapters(
        stock_factory=stock_factory,
        maybe_update_quarter_state=maybe_update_quarter_state,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, start, end: (1, None),
    )


def test_dry_run_does_not_write_or_run_downstream(tmp_path, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])

    def fake_provider(market, target_date):
        return {"MSFT": _row("MSFT")}

    def fail_runtime(path: str):
        raise AssertionError("runtime should not be built in dry-run")

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=False,
        confirm_write=False,
        limit=0,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=fake_provider,
        runtime_builder=fail_runtime,
    )

    count = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM osakedata").fetchone()[0]
    assert report.status == "DRY_RUN_COMPLETED"
    assert report.inserted == 0
    assert report.downstream_attempted == 0
    assert count == 3


def test_apply_requires_confirm_write(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=False,
        limit=0,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
    )

    assert report.status == "APPLY_CONFIRMATION_REQUIRED"
    assert report.inserted == 0


def test_latest_right_edge_apply_inserts_and_runs_hooks(tmp_path, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])
    calls = {}

    monkeypatch.setattr(
        cli,
        "execute_ticker_downstream_updates",
        lambda **kwargs: calls.setdefault("downstream", []).append(kwargs["ticker"]) or StockTickerDownstreamResult(ticker=kwargs["ticker"]),
    )

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=1,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {"MSFT": _row("MSFT")},
        runtime_builder=lambda path: _runtime(calls),
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT osake, pvm FROM osakedata WHERE osake='MSFT' AND pvm='2026-06-13'"
    ).fetchone()
    conn.close()
    assert report.inserted == 1
    assert report.quarter_state_attempted == 1
    assert report.downstream_attempted == 1
    assert calls["downstream"] == ["MSFT"]
    assert row == ("MSFT", "2026-06-13")


def test_apply_skips_already_present_row(tmp_path, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])
    calls = {}

    monkeypatch.setattr(
        cli,
        "execute_ticker_downstream_updates",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    monkeypatch.setattr(
        cli,
        "_insert_recovered_ohlcv_row_if_missing",
        lambda conn, row: "already_present_skipped",
    )

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=1,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {"MSFT": _row("MSFT")},
        runtime_builder=lambda path: _runtime(calls),
    )

    assert report.already_present_skipped == 1
    assert report.inserted == 0


def test_apply_blocks_interior_gap(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])
    _insert_day(db_path, date="2026-06-16", tickers=["AAPL", "MSFT"])

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=0,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {"MSFT": _row("MSFT")},
    )

    assert report.status == "APPLY_BLOCKED_REQUIRES_FROM_DATE_RECOMPUTE"


def test_limit_one_processes_only_one(tmp_path, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT", "NVDA"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])
    calls = {}

    monkeypatch.setattr(
        cli,
        "execute_ticker_downstream_updates",
        lambda **kwargs: StockTickerDownstreamResult(ticker=kwargs["ticker"]),
    )

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=1,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {
            "MSFT": _row("MSFT"),
            "NVDA": _row("NVDA"),
        },
        runtime_builder=lambda path: _runtime(calls),
    )

    assert report.apply_limit == 1
    assert report.processed == 1


def test_provider_empty_result(tmp_path) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=0,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {},
    )

    assert report.status == "PROVIDER_EMPTY_OR_FAILED"
    assert report.inserted == 0


def test_downstream_failure_increments_counter(tmp_path, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])
    calls = {}

    def broken_downstream(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "execute_ticker_downstream_updates", broken_downstream)

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=1,
        commit_every=100,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {"MSFT": _row("MSFT")},
        runtime_builder=lambda path: _runtime(calls),
    )

    assert report.inserted == 1
    assert report.downstream_failed == 1
    assert report.status == "APPLY_COMPLETED_WITH_WARNINGS"


def test_commit_every_n(tmp_path, monkeypatch) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT", "NVDA"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])
    calls = {}

    monkeypatch.setattr(
        cli,
        "execute_ticker_downstream_updates",
        lambda **kwargs: StockTickerDownstreamResult(ticker=kwargs["ticker"]),
    )

    report = cli.build_recovery_apply_report(
        db_path=str(db_path),
        market="usa",
        target_date="2026-06-13",
        provider="polygon_grouped_daily",
        apply=True,
        confirm_write=True,
        limit=0,
        commit_every=2,
        reference_window_days=10,
        min_reference_count=1,
        provider_fetcher=lambda market, target_date: {
            "MSFT": _row("MSFT"),
            "NVDA": _row("NVDA"),
        },
        runtime_builder=lambda path: _runtime(calls),
    )

    assert report.commits_done >= 1


def test_json_output_contains_counters(tmp_path, monkeypatch, capsys) -> None:
    db_path = _build_test_db(tmp_path)
    _insert_day(db_path, date="2026-06-12", tickers=["AAPL", "MSFT"])
    _insert_day(db_path, date="2026-06-13", tickers=["AAPL"])

    monkeypatch.setattr(
        cli,
        "build_recovery_apply_report",
        lambda **kwargs: cli.RecoveryApplyReport(
            db_path=str(db_path),
            market="usa",
            target_date="2026-06-13",
            provider="polygon_grouped_daily",
            classification="DAY_LEVEL_GAP",
            gap_position="LATEST_OR_RIGHT_EDGE_GAP",
            downstream_recompute_mode="LATEST_DAY_RECOMPUTE_OK",
            dry_run=True,
            apply=False,
            apply_limit=1,
            missing_before=1,
            provider_snapshot_count=1,
            recoverable_planned=1,
            not_found_in_provider=0,
            processed=0,
            inserted=0,
            already_present_skipped=0,
            invalid_ohlc_skipped=0,
            insert_failed=0,
            quarter_state_attempted=0,
            quarter_state_ok=0,
            quarter_state_failed=0,
            downstream_attempted=0,
            downstream_ok=0,
            downstream_failed=0,
            still_missing_after=1,
            commits_done=0,
            would_process=1,
            would_insert=1,
            would_run_downstream=1,
            provider_status="OK",
            status="DRY_RUN_COMPLETED",
            apply_safety_note="note",
            recoverable_tickers=["MSFT"],
            not_found_in_provider_tickers=[],
        ),
    )

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
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "DRY_RUN_COMPLETED"
    assert payload["recoverable_planned"] == 1
    assert payload["commits_done"] == 0
