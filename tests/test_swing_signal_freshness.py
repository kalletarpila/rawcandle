from __future__ import annotations

from datetime import date, timedelta

from analysis.datacenter_indices.swing_signal_freshness import (
    build_swing_signal_freshness_rows,
)


def _history_row(
    day_index: int,
    *,
    ticker: str = "AAA",
    bullish_candle_signal: int = 0,
    bearish_candle_signal: int = 0,
    bullish_divergence_signal: int = 0,
    bearish_divergence_signal: int = 0,
    hidden_bullish_divergence_signal: int = 0,
    hidden_bearish_divergence_signal: int = 0,
    latest_bos_event_type: str | None = None,
    latest_bos_event_date: str | None = None,
    latest_bos_age_trading_days: int | None = None,
    latest_reset_reason: str | None = None,
    latest_reset_event_date: str | None = None,
    latest_reset_age_trading_days: int | None = None,
) -> dict[str, object]:
    signal_date = (date(2024, 1, 1) + timedelta(days=day_index)).isoformat()
    return {
        "signal_date": signal_date,
        "ticker": ticker,
        "bullish_candle_signal": bullish_candle_signal,
        "bearish_candle_signal": bearish_candle_signal,
        "bullish_divergence_signal": bullish_divergence_signal,
        "bearish_divergence_signal": bearish_divergence_signal,
        "hidden_bullish_divergence_signal": hidden_bullish_divergence_signal,
        "hidden_bearish_divergence_signal": hidden_bearish_divergence_signal,
        "latest_bos_event_type": latest_bos_event_type,
        "latest_bos_event_date": latest_bos_event_date,
        "latest_bos_age_trading_days": latest_bos_age_trading_days,
        "latest_reset_reason": latest_reset_reason,
        "latest_reset_event_date": latest_reset_event_date,
        "latest_reset_age_trading_days": latest_reset_age_trading_days,
    }


def _latest_row(history: list[dict[str, object]]) -> dict[str, object]:
    return {
        "ticker": history[-1]["ticker"],
        "signal_date": history[-1]["signal_date"],
        "latest_bos_event_type": history[-1].get("latest_bos_event_type"),
        "latest_bos_event_date": history[-1].get("latest_bos_event_date"),
        "latest_bos_age_trading_days": history[-1].get("latest_bos_age_trading_days"),
        "latest_reset_reason": history[-1].get("latest_reset_reason"),
        "latest_reset_event_date": history[-1].get("latest_reset_event_date"),
        "latest_reset_age_trading_days": history[-1].get("latest_reset_age_trading_days"),
    }


def _build(history: list[dict[str, object]]) -> dict[str, object]:
    return build_swing_signal_freshness_rows(
        latest_rows=[_latest_row(history)],
        history_rows=history,
        as_of_date=str(history[-1]["signal_date"]),
    )[0]


def test_no_signals_available_is_no_recent_signal():
    history = [_history_row(index) for index in range(5)]
    result = _build(history)

    assert result["freshness_status"] == "NO_RECENT_SIGNAL"


def test_fresh_bullish_candle_only_is_fresh_bullish_signal():
    history = [_history_row(index) for index in range(4)] + [_history_row(4, bullish_candle_signal=1)]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BULLISH_SIGNAL"


def test_fresh_bearish_candle_only_is_fresh_bearish_signal():
    history = [_history_row(index) for index in range(4)] + [_history_row(4, bearish_candle_signal=1)]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BEARISH_SIGNAL"


def test_fresh_bullish_divergence_only_is_fresh_bullish_signal():
    history = [_history_row(index) for index in range(10)] + [_history_row(10, bullish_divergence_signal=1)]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BULLISH_SIGNAL"


def test_fresh_bearish_divergence_only_is_fresh_bearish_signal():
    history = [_history_row(index) for index in range(10)] + [_history_row(10, bearish_divergence_signal=1)]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BEARISH_SIGNAL"


def test_fresh_bos_up_only_is_fresh_bullish_signal():
    history = [_history_row(index) for index in range(10)] + [
        _history_row(10, latest_bos_event_type="BOS_UP", latest_bos_age_trading_days=0)
    ]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BULLISH_SIGNAL"


def test_fresh_bos_down_only_is_fresh_bearish_signal():
    history = [_history_row(index) for index in range(10)] + [
        _history_row(10, latest_bos_event_type="BOS_DOWN", latest_bos_age_trading_days=0)
    ]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BEARISH_SIGNAL"


def test_fresh_reset_only_is_fresh_bearish_signal():
    history = [_history_row(index) for index in range(10)] + [
        _history_row(10, latest_reset_reason="RESET", latest_reset_age_trading_days=0)
    ]
    result = _build(history)

    assert result["freshness_status"] == "FRESH_BEARISH_SIGNAL"


def test_newer_bos_down_overrides_older_bullish_signal():
    history = [
        _history_row(index) for index in range(8)
    ] + [
        _history_row(8, bullish_candle_signal=1),
        _history_row(9),
        _history_row(10, latest_bos_event_type="BOS_DOWN", latest_bos_age_trading_days=0),
    ]
    result = _build(history)

    assert result["freshness_status"] == "STRUCTURE_WARNING_OVERRIDES_BULLISH"


def test_newer_reset_overrides_older_bullish_signal():
    history = [
        _history_row(index) for index in range(8)
    ] + [
        _history_row(8, bullish_candle_signal=1),
        _history_row(9),
        _history_row(10, latest_reset_reason="RESET", latest_reset_age_trading_days=0),
    ]
    result = _build(history)

    assert result["freshness_status"] == "STRUCTURE_WARNING_OVERRIDES_BULLISH"


def test_fresh_bullish_and_bearish_without_override_is_mixed_signals():
    history = [_history_row(index) for index in range(9)] + [
        _history_row(9, bullish_candle_signal=1),
        _history_row(10, bearish_candle_signal=1),
    ]
    result = _build(history)

    assert result["freshness_status"] == "MIXED_SIGNALS"


def test_stale_signals_outside_windows_are_ignored():
    history = [_history_row(index) for index in range(21)] + [_history_row(21)]
    history[0]["bullish_candle_signal"] = 1
    history[0]["bearish_divergence_signal"] = 1
    result = _build(history)

    assert result["freshness_status"] == "NO_RECENT_SIGNAL"


def test_output_is_deterministic():
    history_a = [_history_row(index, ticker="AAA") for index in range(5)]
    history_b = [_history_row(index, ticker="BBB", bullish_candle_signal=1 if index == 4 else 0) for index in range(5)]
    result = build_swing_signal_freshness_rows(
        latest_rows=[_latest_row(history_b), _latest_row(history_a)],
        history_rows=[*history_b, *history_a],
        as_of_date=str(history_a[-1]["signal_date"]),
    )

    assert [row["ticker"] for row in result] == ["AAA", "BBB"]
