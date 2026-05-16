import pytest

from services.stock_update_service import (
    StockUpdateDateRange,
    convert_histories_to_ohlcv_rows,
    fetch_history_for_date_ranges,
    run_stock_data_update,
)

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


class _FakeHistory:
    def __init__(self, empty=False, rows=None):
        self.empty = empty
        self._rows = list(rows or [])

    def iterrows(self):
        return iter(self._rows)


class _FakeStock:
    def __init__(self, results=None, exc=None):
        self.results = list(results or [])
        self.exc = exc
        self.calls = []

    def history(self, start=None, end=None):
        self.calls.append((start, end))
        if self.exc is not None:
            raise self.exc
        return self.results.pop(0)


def test_fetch_history_for_date_ranges_calls_stock_history_with_exact_ranges():
    stock = _FakeStock(
        results=[_FakeHistory(empty=False), _FakeHistory(empty=False)]
    )
    date_ranges = [
        StockUpdateDateRange("2026-01-01", "2026-01-10"),
        StockUpdateDateRange("2026-01-10", "2026-01-20"),
    ]

    result = fetch_history_for_date_ranges(
        stock=stock,
        ticker="AAA",
        date_ranges=date_ranges,
    )

    assert stock.calls == [
        ("2026-01-01", "2026-01-10"),
        ("2026-01-10", "2026-01-20"),
    ]
    assert result.histories[0].empty is False
    assert result.histories[1].empty is False
    assert result.ranges_requested == 2
    assert result.ranges_returned == 2


def test_fetch_history_for_date_ranges_handles_empty_input():
    result = fetch_history_for_date_ranges(
        stock=_FakeStock(),
        ticker="AAA",
        date_ranges=[],
    )

    assert result.histories == []
    assert result.ranges_requested == 0
    assert result.ranges_returned == 0


def test_fetch_history_for_date_ranges_does_not_filter_empty_histories():
    empty_history = _FakeHistory(empty=True)
    stock = _FakeStock(results=[empty_history])

    result = fetch_history_for_date_ranges(
        stock=stock,
        ticker="AAA",
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-10")],
    )

    assert result.histories == [empty_history]
    assert result.ranges_requested == 1
    assert result.ranges_returned == 1


def test_fetch_history_for_date_ranges_propagates_exceptions():
    stock = _FakeStock(exc=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        fetch_history_for_date_ranges(
            stock=stock,
            ticker="AAA",
            date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-10")],
        )


def test_fetch_history_for_date_ranges_does_not_accept_sleep_fn_argument():
    stock = _FakeStock()
    with pytest.raises(TypeError):
        fetch_history_for_date_ranges(
            stock=stock,
            ticker="AAA",
            date_ranges=[],
            sleep_fn=lambda _seconds: None,
        )


def test_convert_histories_to_ohlcv_rows_concatenates_in_input_order():
    if pd is None:
        pytest.skip("pandas not available")

    history1 = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    history2 = pd.DataFrame(
        {
            "Open": [11.0],
            "High": [12.0],
            "Low": [10.5],
            "Close": [11.8],
            "Volume": [210000],
        },
        index=pd.to_datetime(["2026-01-03"]),
    )

    rows = convert_histories_to_ohlcv_rows(
        histories=[history1, history2],
        ticker="AAA",
        market="usa",
    )

    assert [row.date for row in rows] == ["2026-01-02", "2026-01-03"]
    assert [row.ticker for row in rows] == ["AAA", "AAA"]
    assert [row.market for row in rows] == ["usa", "usa"]


def test_convert_histories_to_ohlcv_rows_propagates_conversion_exceptions():
    if pd is None:
        pytest.skip("pandas not available")

    bad_history = pd.DataFrame(
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
        convert_histories_to_ohlcv_rows(
            histories=[bad_history],
            ticker="AAA",
            market="usa",
        )

