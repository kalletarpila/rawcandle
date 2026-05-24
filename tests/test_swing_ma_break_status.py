from __future__ import annotations

from datetime import date, timedelta

from analysis.datacenter_indices.swing_ma_break_status import (
    build_swing_ma_break_status_rows,
)


def _build_history(
    closes: list[float | None],
    *,
    ticker: str = "AAA",
    ema20_values: list[float | None] | None = None,
) -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    history: list[dict[str, object]] = []
    for index, close_value in enumerate(closes):
        history.append(
            {
                "signal_date": (start + timedelta(days=index)).isoformat(),
                "ticker": ticker,
                "close": close_value,
                "ema20": None if ema20_values is None else ema20_values[index],
            }
        )
    return history


def _latest_row(history: list[dict[str, object]]) -> dict[str, object]:
    last = history[-1]
    return {
        "ticker": last["ticker"],
        "signal_date": last["signal_date"],
        "close": last["close"],
        "ema20": last.get("ema20"),
    }


def test_close_above_ema20_and_sma50_is_ok():
    history = _build_history([100.0] * 60, ema20_values=[99.0] * 60)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "OK"


def test_close_just_below_ema20_but_not_confirmed_is_ema20_warning():
    closes = [90.0] * 59 + [99.4]
    ema20_values = [89.0] * 59 + [100.0]
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "EMA20_WARNING"


def test_close_below_ema20_by_more_than_1_5_pct_is_confirmed_break():
    closes = [90.0] * 59 + [98.0]
    ema20_values = [89.0] * 59 + [100.0]
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "EMA20_CONFIRMED_BREAK"


def test_two_consecutive_closes_below_ema20_is_confirmed_break():
    closes = [90.0] * 58 + [95.0, 94.0]
    ema20_values = [89.0] * 58 + [100.0, 100.0]
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "EMA20_CONFIRMED_BREAK"
    assert result[0]["consecutive_closes_below_ema20"] == 2


def test_close_just_below_sma50_but_not_confirmed_is_sma50_warning():
    closes = [100.0] * 59 + [99.2]
    ema20_values = [98.5] * 60
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "SMA50_WARNING"


def test_close_below_sma50_by_more_than_2_pct_is_confirmed_break():
    closes = [100.0] * 59 + [97.5]
    ema20_values = [96.0] * 60
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "SMA50_CONFIRMED_BREAK"


def test_two_consecutive_closes_below_sma50_is_confirmed_break():
    closes = [100.0] * 58 + [99.0, 98.5]
    ema20_values = [97.0] * 60
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "SMA50_CONFIRMED_BREAK"
    assert result[0]["consecutive_closes_below_sma50"] == 2


def test_sma50_confirmed_break_outranks_ema20_break():
    closes = [100.0] * 59 + [97.5]
    ema20_values = [100.0] * 60
    history = _build_history(closes, ema20_values=ema20_values)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "SMA50_CONFIRMED_BREAK"


def test_missing_ma_data_is_insufficient_data():
    history = _build_history([100.0] * 10)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )

    assert result[0]["ma_break_status"] == "INSUFFICIENT_DATA"


def test_output_is_sorted_deterministically_by_ticker():
    history_a = _build_history([100.0] * 60, ticker="AAA", ema20_values=[99.0] * 60)
    history_b = _build_history([100.0] * 60, ticker="BBB", ema20_values=[99.0] * 60)
    result = build_swing_ma_break_status_rows(
        latest_rows=[_latest_row(history_b), _latest_row(history_a)],
        history_rows=[*history_b, *history_a],
        as_of_date=str(history_a[-1]["signal_date"]),
    )

    assert [row["ticker"] for row in result] == ["AAA", "BBB"]
