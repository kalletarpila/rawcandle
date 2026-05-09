import pandas as pd

from analysis.chart_patterns import (
    is_ascending_triangle,
    is_bear_rectangle,
    is_bearish_pennant,
    is_bearish_flag,
    is_bull_rectangle,
    is_bullish_pennant,
    is_bullish_flag,
    is_descending_triangle,
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


def test_ascending_triangle_detected():
    df = _df(
        [
            {"Open": 100.0, "High": 104.0, "Low": 99.5, "Close": 103.0},
            {"Open": 103.0, "High": 110.0, "Low": 102.0, "Close": 108.5},
            {"Open": 108.0, "High": 109.5, "Low": 104.0, "Close": 108.7},
            {"Open": 108.5, "High": 110.1, "Low": 105.5, "Close": 109.2},
            {"Open": 109.0, "High": 109.6, "Low": 107.0, "Close": 109.1},
            {"Open": 109.1, "High": 110.2, "Low": 108.3, "Close": 109.8},
            {"Open": 109.9, "High": 112.5, "Low": 109.6, "Close": 112.0},
        ]
    )

    assert is_ascending_triangle(df, 6) is True


def test_descending_triangle_detected():
    df = _df(
        [
            {"Open": 112.0, "High": 113.0, "Low": 108.0, "Close": 109.0},
            {"Open": 109.0, "High": 110.5, "Low": 102.0, "Close": 103.5},
            {"Open": 103.7, "High": 108.5, "Low": 102.5, "Close": 103.3},
            {"Open": 103.5, "High": 106.8, "Low": 102.1, "Close": 102.8},
            {"Open": 102.9, "High": 105.0, "Low": 102.4, "Close": 102.7},
            {"Open": 102.8, "High": 103.5, "Low": 101.9, "Close": 102.2},
            {"Open": 102.1, "High": 102.3, "Low": 99.2, "Close": 99.5},
        ]
    )

    assert is_descending_triangle(df, 6) is True


def test_bullish_pennant_detected():
    df = _df(
        [
            {"Open": 100.0, "High": 104.0, "Low": 99.5, "Close": 103.5},
            {"Open": 103.5, "High": 108.0, "Low": 103.0, "Close": 107.2},
            {"Open": 107.2, "High": 112.0, "Low": 106.8, "Close": 111.0},
            {"Open": 110.8, "High": 111.5, "Low": 109.2, "Close": 110.2},
            {"Open": 110.1, "High": 110.9, "Low": 109.8, "Close": 110.4},
            {"Open": 110.4, "High": 110.6, "Low": 110.1, "Close": 110.3},
            {"Open": 110.5, "High": 113.0, "Low": 110.4, "Close": 112.6},
        ]
    )

    assert is_bullish_pennant(df, 6) is True


def test_bearish_pennant_detected():
    df = _df(
        [
            {"Open": 112.0, "High": 112.5, "Low": 108.0, "Close": 108.5},
            {"Open": 108.5, "High": 108.9, "Low": 104.0, "Close": 104.8},
            {"Open": 104.8, "High": 105.0, "Low": 100.2, "Close": 101.0},
            {"Open": 101.2, "High": 102.0, "Low": 100.5, "Close": 101.5},
            {"Open": 101.5, "High": 101.8, "Low": 100.9, "Close": 101.3},
            {"Open": 101.3, "High": 101.5, "Low": 101.1, "Close": 101.2},
            {"Open": 101.0, "High": 101.2, "Low": 98.0, "Close": 98.4},
        ]
    )

    assert is_bearish_pennant(df, 6) is True
