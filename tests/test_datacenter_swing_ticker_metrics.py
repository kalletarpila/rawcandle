from __future__ import annotations

from datetime import date, timedelta

import pytest

from analysis.datacenter_indices import (
    TickerOhlcvRow,
    calculate_ticker_swing_metrics,
)


def _row(
    row_date: str,
    *,
    close: float | None,
    volume: float | None = 100.0,
) -> TickerOhlcvRow:
    base_price = close if close is not None else 1.0
    return TickerOhlcvRow(
        date=row_date,
        open=base_price,
        high=base_price,
        low=base_price,
        close=close,
        volume=volume,
    )


def _series(
    closes: list[float | None],
    *,
    start: date = date(2024, 1, 1),
    volumes: list[float | None] | None = None,
) -> list[TickerOhlcvRow]:
    if volumes is None:
        volumes = [100.0] * len(closes)
    return [
        _row(
            (start + timedelta(days=offset)).isoformat(),
            close=close,
            volume=volumes[offset],
        )
        for offset, close in enumerate(closes)
    ]


def test_exact_as_of_date_is_required_without_forward_fill():
    rows = [
        _row("2024-01-01", close=100.0),
        _row("2024-01-03", close=101.0),
    ]

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-02")

    assert metrics.price_data_status == "MISSING_AS_OF_DATE"
    assert metrics.close is None
    assert metrics.ma10 is None


def test_returns_use_valid_observations_not_calendar_days_and_rows_are_sorted():
    rows = [
        _row("2024-01-12", close=111.0),
        _row("2024-01-01", close=100.0),
        _row("2024-01-11", close=110.0),
        _row("2024-01-04", close=103.0),
        _row("2024-01-02", close=101.0),
        _row("2024-01-05", close=104.0),
        _row("2024-01-08", close=107.0),
        _row("2024-01-03", close=None),
        _row("2024-01-06", close=105.0),
        _row("2024-01-10", close=109.0),
        _row("2024-01-09", close=108.0),
        _row("2024-01-07", close=106.0),
    ]

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-12")

    assert metrics.return_5d == pytest.approx((111.0 / 106.0) - 1.0)
    assert metrics.return_10d == pytest.approx((111.0 / 100.0) - 1.0)


def test_ma10_and_distance_to_ma10_pct_are_calculated_from_last_ten_valid_closes():
    rows = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0])

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-10")

    assert metrics.ma10 == pytest.approx(104.5)
    assert metrics.distance_to_ma10_pct == pytest.approx((109.0 / 104.5) - 1.0)
    assert metrics.above_ma10 == 1
    assert metrics.price_data_status == "OK"


def test_ema10_initializes_from_first_ten_valid_closes():
    rows = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0])

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-10")

    assert metrics.ema10 == pytest.approx(104.5)
    assert metrics.distance_to_ema10_pct == pytest.approx((109.0 / 104.5) - 1.0)
    assert metrics.above_ema10 == 1


def test_ema20_initializes_from_first_twenty_valid_closes():
    rows = _series([float(value) for value in range(1, 21)])

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-20")

    assert metrics.ema20 == pytest.approx(10.5)
    assert metrics.distance_to_ema20_pct == pytest.approx((20.0 / 10.5) - 1.0)
    assert metrics.above_ema20 == 1


def test_ema10_slope_uses_three_valid_observation_lookback():
    rows = _series([float(value) for value in range(1, 14)])

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-13")

    assert metrics.ema10_slope_lookback == 3
    assert metrics.ema10_slope_positive == 1


def test_ema20_slope_uses_five_valid_observation_lookback():
    rows = _series([float(value) for value in range(1, 26)])

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-25")

    assert metrics.ema20_slope_lookback == 5
    assert metrics.ema20_slope_positive == 1


def test_missing_close_on_as_of_date_returns_missing_close_status():
    rows = [
        _row("2024-01-01", close=100.0),
        _row("2024-01-02", close=None),
    ]

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-02")

    assert metrics.price_data_status == "MISSING_CLOSE_AS_OF_DATE"
    assert metrics.close is None
    assert metrics.return_5d is None


def test_highest_close_20d_uses_last_twenty_valid_closes():
    rows = _series(
        [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0,
         20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 99.0, 28.0, 29.0, 30.0]
    )

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-21")

    assert metrics.highest_close_20d == pytest.approx(99.0)


def test_volume_avg_20d_and_volume_vs_avg20_use_valid_volume_observations():
    volumes = [
        10.0,
        20.0,
        30.0,
        40.0,
        50.0,
        60.0,
        70.0,
        80.0,
        90.0,
        100.0,
        110.0,
        120.0,
        130.0,
        140.0,
        150.0,
        160.0,
        170.0,
        180.0,
        190.0,
        200.0,
        None,
        400.0,
    ]
    rows = _series([100.0 + float(i) for i in range(len(volumes))], volumes=volumes)

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-22")

    expected_avg = sum(
        value for value in [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0,
                            120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0, 200.0, 400.0]
    ) / 20.0
    assert metrics.volume_avg_20d == pytest.approx(expected_avg)
    assert metrics.volume_vs_avg20 == pytest.approx(400.0 / expected_avg)


def test_insufficient_history_keeps_partial_values_and_missing_long_metrics_safe():
    rows = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])

    metrics = calculate_ticker_swing_metrics(rows, "2024-01-06")

    assert metrics.price_data_status == "INSUFFICIENT_HISTORY"
    assert metrics.close == pytest.approx(105.0)
    assert metrics.return_5d == pytest.approx((105.0 / 100.0) - 1.0)
    assert metrics.return_10d is None
    assert metrics.ma10 is None
    assert metrics.ema10 is None
    assert metrics.highest_close_20d is None
