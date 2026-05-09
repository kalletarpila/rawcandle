import pandas as pd

from analysis.chart_patterns import (
    is_bear_rectangle,
    is_bearish_flag,
    is_bull_rectangle,
    is_bullish_flag,
)


def _df(rows):
    return pd.DataFrame(rows)


def test_bullish_flag_detected():
    df = _df(
        [
            {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 103.0},
            {"Open": 103.0, "High": 107.0, "Low": 102.0, "Close": 106.0},
            {"Open": 106.0, "High": 111.0, "Low": 105.5, "Close": 110.0},
            {"Open": 109.5, "High": 110.0, "Low": 108.5, "Close": 109.0},
            {"Open": 109.0, "High": 109.2, "Low": 108.0, "Close": 108.6},
            {"Open": 108.8, "High": 111.5, "Low": 108.7, "Close": 111.2},
        ]
    )

    assert is_bullish_flag(df, 5) is True


def test_bearish_flag_detected():
    df = _df(
        [
            {"Open": 110.0, "High": 111.0, "Low": 106.0, "Close": 107.0},
            {"Open": 107.0, "High": 107.5, "Low": 103.0, "Close": 104.0},
            {"Open": 104.0, "High": 104.3, "Low": 99.0, "Close": 100.0},
            {"Open": 100.2, "High": 101.3, "Low": 99.8, "Close": 100.8},
            {"Open": 100.8, "High": 101.8, "Low": 100.5, "Close": 101.3},
            {"Open": 101.0, "High": 101.2, "Low": 97.0, "Close": 97.5},
        ]
    )

    assert is_bearish_flag(df, 5) is True


def test_bull_rectangle_detected():
    df = _df(
        [
            {"Open": 100.0, "High": 103.5, "Low": 99.5, "Close": 103.0},
            {"Open": 103.0, "High": 106.5, "Low": 102.8, "Close": 106.0},
            {"Open": 106.0, "High": 109.5, "Low": 105.8, "Close": 109.0},
            {"Open": 108.8, "High": 109.7, "Low": 108.5, "Close": 109.2},
            {"Open": 109.0, "High": 109.8, "Low": 108.6, "Close": 109.1},
            {"Open": 108.9, "High": 109.6, "Low": 108.4, "Close": 109.0},
            {"Open": 109.2, "High": 111.5, "Low": 109.0, "Close": 111.2},
        ]
    )

    assert is_bull_rectangle(df, 6) is True


def test_bear_rectangle_detected():
    df = _df(
        [
            {"Open": 110.0, "High": 110.5, "Low": 106.5, "Close": 107.0},
            {"Open": 107.0, "High": 107.2, "Low": 103.5, "Close": 104.0},
            {"Open": 104.0, "High": 104.2, "Low": 100.5, "Close": 101.0},
            {"Open": 101.3, "High": 101.6, "Low": 100.6, "Close": 101.0},
            {"Open": 101.2, "High": 101.7, "Low": 100.8, "Close": 101.1},
            {"Open": 101.0, "High": 101.5, "Low": 100.7, "Close": 101.0},
            {"Open": 100.8, "High": 101.0, "Low": 98.0, "Close": 98.4},
        ]
    )

    assert is_bear_rectangle(df, 6) is True


def test_bullish_flag_not_detected_without_breakout():
    df = _df(
        [
            {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 103.0},
            {"Open": 103.0, "High": 107.0, "Low": 102.0, "Close": 106.0},
            {"Open": 106.0, "High": 111.0, "Low": 105.5, "Close": 110.0},
            {"Open": 109.5, "High": 110.0, "Low": 108.5, "Close": 109.0},
            {"Open": 109.0, "High": 109.2, "Low": 108.0, "Close": 108.6},
            {"Open": 108.8, "High": 109.0, "Low": 108.2, "Close": 108.7},
        ]
    )

    assert is_bullish_flag(df, 5) is False
