import pytest

from services.stock_update_service import (
    EVENT_STARTED,
    STATUS_OK,
    StockUpdateProgressEvent,
    StockUpdateResult,
    format_stock_update_summary_lines,
    run_stock_data_update,
)


def test_stock_update_result_accepts_status_ok():
    result = StockUpdateResult(market="omxh", status=STATUS_OK)
    assert result.status == STATUS_OK


def test_stock_update_result_rejects_invalid_status():
    with pytest.raises(ValueError, match="Invalid stock update status"):
        StockUpdateResult(market="omxh", status="BROKEN")


def test_stock_update_progress_event_accepts_started():
    event = StockUpdateProgressEvent(event_type=EVENT_STARTED)
    assert event.event_type == EVENT_STARTED


def test_stock_update_progress_event_rejects_invalid_event_type():
    with pytest.raises(ValueError, match="Invalid stock update event_type"):
        StockUpdateProgressEvent(event_type="bad_event")


def test_format_stock_update_summary_lines_is_deterministic():
    result = StockUpdateResult(
        market="omxh",
        tickers_checked=10,
        tickers_updated=6,
        tickers_skipped=2,
        tickers_failed=2,
        ohlcv_rows_inserted=123,
        splits_synced=4,
        divergences_updated=5,
        candlesticks_updated=7,
        dow_structures_updated=8,
        warnings=["w1", "w2"],
        errors=["e1"],
        status=STATUS_OK,
    )

    assert format_stock_update_summary_lines(result) == [
        "SUMMARY market=omxh",
        "SUMMARY tickers_checked=10",
        "SUMMARY tickers_updated=6",
        "SUMMARY tickers_skipped=2",
        "SUMMARY tickers_failed=2",
        "SUMMARY ohlcv_rows_inserted=123",
        "SUMMARY splits_synced=4",
        "SUMMARY divergences_updated=5",
        "SUMMARY candlesticks_updated=7",
        "SUMMARY dow_structures_updated=8",
        "SUMMARY warnings=2",
        "SUMMARY errors=1",
        "SUMMARY status=OK",
    ]


def test_format_stock_update_summary_lines_formats_none_dow_as_empty():
    result = StockUpdateResult(market="usa")
    lines = format_stock_update_summary_lines(result)
    assert "SUMMARY dow_structures_updated=" in lines


def test_run_stock_data_update_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="run_stock_data_update is not implemented yet"):
        run_stock_data_update(
            osakedata_db_path="data/osakedata.db",
            analysis_db_path="data/analysis.db",
        )
