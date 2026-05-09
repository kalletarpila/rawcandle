from __future__ import annotations

import pandas as pd


def _window(df: pd.DataFrame, idx: int, size: int) -> pd.DataFrame | None:
    start = idx - size + 1
    if start < 0:
        return None
    return df.iloc[start : idx + 1]


def _pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end - start) / abs(start)


def _range_width(window: pd.DataFrame) -> float:
    high = float(window["High"].max())
    low = float(window["Low"].min())
    midpoint = max(abs((high + low) / 2.0), 1e-9)
    return (high - low) / midpoint


def is_bullish_flag(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 6)
    if window is None or len(window) < 6:
        return False

    pole = window.iloc[:3]
    pullback = window.iloc[3:5]
    breakout = window.iloc[5]

    pole_gain = _pct_change(float(pole.iloc[0]["Open"]), float(pole.iloc[-1]["Close"]))
    if pole_gain < 0.05:
        return False

    if not all(float(row["Close"]) > float(row["Open"]) for _, row in pole.iterrows()):
        return False

    if _range_width(pullback) > 0.05:
        return False

    if float(pullback.iloc[-1]["Close"]) >= float(pullback.iloc[0]["Close"]):
        return False

    consolidation_high = float(pullback["High"].max())
    consolidation_low = float(pullback["Low"].min())
    pole_mid = (float(pole.iloc[0]["Open"]) + float(pole.iloc[-1]["Close"])) / 2.0

    return (
        float(breakout["Close"]) > float(breakout["Open"])
        and float(breakout["Close"]) > consolidation_high
        and consolidation_low > pole_mid
    )


def is_bearish_flag(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 6)
    if window is None or len(window) < 6:
        return False

    pole = window.iloc[:3]
    rebound = window.iloc[3:5]
    breakdown = window.iloc[5]

    pole_drop = _pct_change(float(pole.iloc[0]["Open"]), float(pole.iloc[-1]["Close"]))
    if pole_drop > -0.05:
        return False

    if not all(float(row["Close"]) < float(row["Open"]) for _, row in pole.iterrows()):
        return False

    if _range_width(rebound) > 0.05:
        return False

    if float(rebound.iloc[-1]["Close"]) <= float(rebound.iloc[0]["Close"]):
        return False

    consolidation_high = float(rebound["High"].max())
    consolidation_low = float(rebound["Low"].min())
    pole_mid = (float(pole.iloc[0]["Open"]) + float(pole.iloc[-1]["Close"])) / 2.0

    return (
        float(breakdown["Close"]) < float(breakdown["Open"])
        and float(breakdown["Close"]) < consolidation_low
        and consolidation_high < pole_mid
    )


def is_bull_rectangle(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 7)
    if window is None or len(window) < 7:
        return False

    pole = window.iloc[:3]
    rectangle = window.iloc[3:6]
    breakout = window.iloc[6]

    pole_gain = _pct_change(float(pole.iloc[0]["Open"]), float(pole.iloc[-1]["Close"]))
    if pole_gain < 0.04:
        return False

    if _range_width(rectangle) > 0.04:
        return False

    rect_high = float(rectangle["High"].max())
    rect_low = float(rectangle["Low"].min())
    if rect_low <= float(pole.iloc[1]["Close"]):
        return False

    return (
        float(breakout["Close"]) > float(breakout["Open"])
        and float(breakout["Close"]) > rect_high
    )


def is_bear_rectangle(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 7)
    if window is None or len(window) < 7:
        return False

    pole = window.iloc[:3]
    rectangle = window.iloc[3:6]
    breakdown = window.iloc[6]

    pole_drop = _pct_change(float(pole.iloc[0]["Open"]), float(pole.iloc[-1]["Close"]))
    if pole_drop > -0.04:
        return False

    if _range_width(rectangle) > 0.04:
        return False

    rect_high = float(rectangle["High"].max())
    rect_low = float(rectangle["Low"].min())
    if rect_high >= float(pole.iloc[1]["Close"]):
        return False

    return (
        float(breakdown["Close"]) < float(breakdown["Open"])
        and float(breakdown["Close"]) < rect_low
    )
