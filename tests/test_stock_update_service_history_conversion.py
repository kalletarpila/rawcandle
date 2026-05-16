from datetime import date, datetime

import pytest

from services.stock_update_service import (
    _format_history_index_date,
    _is_missing_ohlcv_value,
    convert_history_to_ohlcv_rows,
    run_stock_data_update,
)

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


def _build_history(rows, index):
    if pd is None:
        raise RuntimeError("pandas is required for these tests in this environment")
    return pd.DataFrame(rows, index=index)


def test_convert_history_to_ohlcv_rows_returns_empty_for_none_history():
    assert convert_history_to_ohlcv_rows(history=None, ticker="AAA", market="usa") == []


def test_convert_history_to_ohlcv_rows_returns_empty_for_empty_history():
    history = _build_history(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []},
        index=[],
    )
    assert convert_history_to_ohlcv_rows(history=history, ticker="AAA", market="usa") == []


def test_convert_history_to_ohlcv_rows_basic_conversion_preserves_order_and_market():
    history = _build_history(
        {
            "Open": [10.0, 11.5],
            "High": [11.0, 12.5],
            "Low": [9.5, 10.5],
            "Close": [10.8, 12.0],
            "Volume": [200000, 220000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    rows = convert_history_to_ohlcv_rows(
        history=history,
        ticker="AAA",
        market=" USA ",
    )

    assert [row.date for row in rows] == ["2026-01-02", "2026-01-05"]
    assert [row.ticker for row in rows] == ["AAA", "AAA"]
    assert [row.market for row in rows] == [" USA ", " USA "]
    assert rows[0].open == 10.0
    assert rows[0].high == 11.0
    assert rows[0].low == 9.5
    assert rows[0].close == 10.8
    assert rows[0].volume == 200000
    assert rows[1].open == 11.5
    assert rows[1].high == 12.5
    assert rows[1].low == 10.5
    assert rows[1].close == 12.0
    assert rows[1].volume == 220000


def test_format_history_index_date_matches_current_strftime_behavior():
    assert _format_history_index_date(pd.Timestamp("2026-01-02")) == "2026-01-02"
    assert _format_history_index_date(date(2026, 1, 3)) == "2026-01-03"
    assert _format_history_index_date(datetime(2026, 1, 4, 15, 30, 0)) == "2026-01-04"


def test_is_missing_ohlcv_value_behavior():
    assert _is_missing_ohlcv_value(None) is True
    assert _is_missing_ohlcv_value(float("nan")) is True
    assert _is_missing_ohlcv_value(0) is False
    assert _is_missing_ohlcv_value(0.0) is False
    assert _is_missing_ohlcv_value(False) is False
    assert _is_missing_ohlcv_value("") is False


def test_convert_history_to_ohlcv_rows_converts_nan_values_to_none():
    history = _build_history(
        {
            "Open": [float("nan")],
            "High": [float("nan")],
            "Low": [float("nan")],
            "Close": [float("nan")],
            "Volume": [float("nan")],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )

    rows = convert_history_to_ohlcv_rows(
        history=history,
        ticker="AAA",
        market="usa",
    )

    assert len(rows) == 1
    assert rows[0].open is None
    assert rows[0].high is None
    assert rows[0].low is None
    assert rows[0].close is None
    assert rows[0].volume is None


def test_convert_history_to_ohlcv_rows_missing_required_column_propagates():
    history = _build_history(
        {
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )

    with pytest.raises(Exception):
        convert_history_to_ohlcv_rows(
            history=history,
            ticker="AAA",
            market="usa",
        )


def test_convert_history_to_ohlcv_rows_invalid_non_nan_value_propagates():
    history = _build_history(
        {
            "Open": ["bad"],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )

    with pytest.raises(Exception):
        convert_history_to_ohlcv_rows(
            history=history,
            ticker="AAA",
            market="usa",
        )


def test_run_stock_data_update_still_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="run_stock_data_update is not implemented yet"):
        run_stock_data_update(
            osakedata_db_path="data/osakedata.db",
            analysis_db_path="data/analysis.db",
        )
