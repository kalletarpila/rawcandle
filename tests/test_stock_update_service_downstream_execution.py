from __future__ import annotations

import pytest

from services.stock_update_service import (
    StockTickerDownstreamResult,
    StockUpdateDateRange,
    run_stock_data_update,
    execute_ticker_downstream_updates,
)


def test_execute_ticker_downstream_updates_normal_path_call_order() -> None:
    calls = []

    def sync_splits(ticker: str, stock: object) -> int:
        calls.append(("split_sync", ticker, stock))
        return 1

    def maybe_backfill_splits(ticker: str) -> bool:
        calls.append(("backfill", ticker))
        return False

    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        calls.append(("divergence", ticker, only_missing))
        return (True, 3, "")

    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        calls.append(("candlestick", ticker, analysis_start, analysis_end))
        return (5, None)

    stock = object()
    date_ranges = [
        StockUpdateDateRange("2026-01-10", "2026-01-20"),
        StockUpdateDateRange("2026-01-01", "2026-01-25"),
    ]

    result = execute_ticker_downstream_updates(
        ticker="AAA",
        stock=stock,
        ohlcv_rows_inserted=2,
        date_ranges=date_ranges,
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert calls == [
        ("split_sync", "AAA", stock),
        ("backfill", "AAA"),
        ("divergence", "AAA", True),
        ("candlestick", "AAA", "2026-01-01", "2026-01-25"),
    ]
    assert result.split_sync_inserted == 1
    assert result.split_backfill_recomputed is False
    assert result.divergence_attempted is True
    assert result.divergence_success is True
    assert result.divergence_days == 3
    assert result.candlestick_attempted is True
    assert result.candlestick_total == 5
    assert result.candlestick_error is None


def test_execute_ticker_downstream_updates_split_sync_exception_is_caught() -> None:
    calls = []

    def sync_splits(ticker: str, stock: object) -> int:
        calls.append(("split_sync", ticker))
        raise RuntimeError("boom")

    def maybe_backfill_splits(ticker: str) -> bool:
        calls.append(("backfill", ticker))
        return False

    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        calls.append(("divergence", ticker, only_missing))
        return (True, 1, "")

    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        raise AssertionError("candlestick should not be called")

    result = execute_ticker_downstream_updates(
        ticker="AAA",
        stock=object(),
        ohlcv_rows_inserted=0,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert calls == [
        ("split_sync", "AAA"),
        ("backfill", "AAA"),
        ("divergence", "AAA", True),
    ]
    assert result.split_sync_attempted is True
    assert "AAA" in result.split_sync_warning
    assert "boom" in result.split_sync_warning
    assert result.warnings == [result.split_sync_warning]


def test_execute_ticker_downstream_updates_backfill_true_skips_divergence() -> None:
    def sync_splits(ticker: str, stock: object) -> int:
        return 0

    def maybe_backfill_splits(ticker: str) -> bool:
        return True

    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        raise AssertionError("divergence should not be called")

    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        raise AssertionError("candlestick should not be called")

    result = execute_ticker_downstream_updates(
        ticker="AAA",
        stock=object(),
        ohlcv_rows_inserted=0,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert result.divergence_attempted is False
    assert result.divergence_skipped_reason == "split_backfill_recomputed"
    assert result.divergence_success is True
    assert result.divergence_days == 0
    assert result.divergence_error == ""


def test_execute_ticker_downstream_updates_backfill_exception_propagates() -> None:
    def maybe_backfill_splits(ticker: str) -> bool:
        raise RuntimeError("backfill failed")

    with pytest.raises(RuntimeError, match="backfill failed"):
        execute_ticker_downstream_updates(
            ticker="AAA",
            stock=object(),
            ohlcv_rows_inserted=0,
            date_ranges=[],
            sync_splits=lambda ticker, stock: 0,
            maybe_backfill_splits=maybe_backfill_splits,
            calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
                0,
                None,
            ),
        )


def test_execute_ticker_downstream_updates_divergence_exception_propagates() -> None:
    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        raise RuntimeError("div failed")

    with pytest.raises(RuntimeError, match="div failed"):
        execute_ticker_downstream_updates(
            ticker="AAA",
            stock=object(),
            ohlcv_rows_inserted=0,
            date_ranges=[],
            sync_splits=lambda ticker, stock: 0,
            maybe_backfill_splits=lambda ticker: False,
            calculate_divergences=calculate_divergences,
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
                0,
                None,
            ),
        )


def test_execute_ticker_downstream_updates_skips_candlestick_when_no_rows_inserted() -> None:
    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        raise AssertionError("candlestick should not be called")

    result = execute_ticker_downstream_updates(
        ticker="AAA",
        stock=object(),
        ohlcv_rows_inserted=0,
        date_ranges=[],
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert result.candlestick_attempted is False
    assert result.candlestick_total is None
    assert result.candlestick_error is None


def test_execute_ticker_downstream_updates_candlestick_exception_is_caught() -> None:
    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        raise RuntimeError("candle failed")

    result = execute_ticker_downstream_updates(
        ticker="AAA",
        stock=object(),
        ohlcv_rows_inserted=1,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert result.candlestick_attempted is True
    assert result.candlestick_total == 0
    assert "candle failed" in result.candlestick_error
    assert any("candle failed" in warning for warning in result.warnings)


def test_execute_ticker_downstream_updates_empty_date_ranges_propagates() -> None:
    with pytest.raises(ValueError):
        execute_ticker_downstream_updates(
            ticker="AAA",
            stock=object(),
            ohlcv_rows_inserted=1,
            date_ranges=[],
            sync_splits=lambda ticker, stock: 0,
            maybe_backfill_splits=lambda ticker: False,
            calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
                0,
                None,
            ),
        )


def test_stock_ticker_downstream_result_has_no_dow_fields() -> None:
    result = StockTickerDownstreamResult(ticker="AAA")

    assert not hasattr(result, "dow_summary")
    assert not hasattr(result, "dow_structures_updated")


def test_divergence_incompatible_return_shape_propagates() -> None:
    with pytest.raises(ValueError):
        execute_ticker_downstream_updates(
            ticker="AAA",
            stock=object(),
            ohlcv_rows_inserted=0,
            date_ranges=[],
            sync_splits=lambda ticker, stock: 0,
            maybe_backfill_splits=lambda ticker: False,
            calculate_divergences=lambda ticker, only_missing: (True, 1),
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
                0,
                None,
            ),
        )


def test_candlestick_incompatible_return_shape_is_caught() -> None:
    result = execute_ticker_downstream_updates(
        ticker="AAA",
        stock=object(),
        ohlcv_rows_inserted=1,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (5,),
    )

    assert result.candlestick_attempted is True
    assert result.candlestick_total == 0
    assert result.candlestick_error
    assert result.warnings

