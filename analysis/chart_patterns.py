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


def _level_span(values: pd.Series) -> float:
    midpoint = max(abs(float(values.mean())), 1e-9)
    return (float(values.max()) - float(values.min())) / midpoint


def _strictly_rising(values: pd.Series) -> bool:
    seq = [float(v) for v in values]
    return all(right > left for left, right in zip(seq, seq[1:]))


def _strictly_falling(values: pd.Series) -> bool:
    seq = [float(v) for v in values]
    return all(right < left for left, right in zip(seq, seq[1:]))


def _linear_slope(values: pd.Series) -> float:
    seq = [float(v) for v in values]
    n = len(seq)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(seq) / n
    numerator = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(seq))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


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


def is_ascending_triangle(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 7)
    if window is None or len(window) < 7:
        return False

    triangle = window.iloc[:6]
    breakout = window.iloc[6]

    resistance_tests = triangle.iloc[1::2]["High"]
    rising_lows = triangle.iloc[0::2]["Low"]

    if len(resistance_tests) != 3 or len(rising_lows) != 3:
        return False

    if _level_span(resistance_tests) > 0.02:
        return False

    if not _strictly_rising(rising_lows):
        return False

    if float(triangle.iloc[-1]["Close"]) <= float(triangle.iloc[0]["Close"]):
        return False

    resistance = float(resistance_tests.max())
    return (
        float(breakout["Close"]) > float(breakout["Open"])
        and float(breakout["Close"]) > resistance
    )


def is_descending_triangle(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 7)
    if window is None or len(window) < 7:
        return False

    triangle = window.iloc[:6]
    breakdown = window.iloc[6]

    support_tests = triangle.iloc[1::2]["Low"]
    falling_highs = triangle.iloc[0::2]["High"]

    if len(support_tests) != 3 or len(falling_highs) != 3:
        return False

    if _level_span(support_tests) > 0.02:
        return False

    if not _strictly_falling(falling_highs):
        return False

    if float(triangle.iloc[-1]["Close"]) >= float(triangle.iloc[0]["Close"]):
        return False

    support = float(support_tests.min())
    return (
        float(breakdown["Close"]) < float(breakdown["Open"])
        and float(breakdown["Close"]) < support
    )


def is_bullish_pennant(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 7)
    if window is None or len(window) < 7:
        return False

    pole = window.iloc[:3]
    pennant = window.iloc[3:6]
    breakout = window.iloc[6]

    pole_gain = _pct_change(float(pole.iloc[0]["Open"]), float(pole.iloc[-1]["Close"]))
    if pole_gain < 0.05:
        return False

    highs = pennant["High"]
    lows = pennant["Low"]
    if not _strictly_falling(highs):
        return False
    if not _strictly_rising(lows):
        return False

    if _range_width(pennant) > 0.05:
        return False

    resistance = float(highs.max())
    return (
        float(breakout["Close"]) > float(breakout["Open"])
        and float(breakout["Close"]) > resistance
    )


def is_bearish_pennant(df: pd.DataFrame, idx: int) -> bool:
    window = _window(df, idx, 7)
    if window is None or len(window) < 7:
        return False

    pole = window.iloc[:3]
    pennant = window.iloc[3:6]
    breakdown = window.iloc[6]

    pole_drop = _pct_change(float(pole.iloc[0]["Open"]), float(pole.iloc[-1]["Close"]))
    if pole_drop > -0.05:
        return False

    highs = pennant["High"]
    lows = pennant["Low"]
    if not _strictly_falling(highs):
        return False
    if not _strictly_rising(lows):
        return False

    if _range_width(pennant) > 0.05:
        return False

    support = float(lows.min())
    return (
        float(breakdown["Close"]) < float(breakdown["Open"])
        and float(breakdown["Close"]) < support
    )


def is_cup_and_handle(df: pd.DataFrame, idx: int) -> bool:
    if idx < 204:
        return False
    required_columns = {"Close", "High", "Low", "Volume"}
    if not required_columns.issubset(df.columns):
        return False

    closes = df["Close"].astype(float)
    sma200 = closes.rolling(200).mean()
    sma_now = sma200.iloc[idx]
    sma_prev = sma200.iloc[idx - 5]
    close_now = float(closes.iloc[idx])
    if pd.isna(sma_now) or pd.isna(sma_prev):
        return False
    if close_now <= float(sma_now):
        return False
    if float(sma_now) < float(sma_prev):
        return False

    window_start = max(0, idx - 219)
    min_handle_len = 3
    max_handle_len = 50

    for right_idx in range(idx - min_handle_len, max(window_start + 29, idx - max_handle_len) - 1, -1):
        handle = df.iloc[right_idx + 1 : idx]
        handle_len = len(handle)
        if handle_len < min_handle_len:
            continue

        right_price = float(closes.iloc[right_idx])
        recent_right_window = closes.iloc[max(window_start, right_idx - 3) : right_idx + 1]
        if right_price < float(recent_right_window.max()):
            continue
        handle_high = float(handle["High"].max())
        handle_low = float(handle["Low"].min())
        if (right_price - handle_low) / max(right_price, 1e-9) > 0.12:
            continue
        if _linear_slope(handle["Close"]) > right_price * 0.001:
            continue

        breakout_row = df.iloc[idx]
        breakout_volume = float(breakout_row["Volume"])
        avg_handle_volume = float(handle["Volume"].mean())
        if (
            float(breakout_row["Close"]) <= max(right_price, handle_high)
            or breakout_volume < avg_handle_volume
        ):
            continue

        left_min = max(window_start, right_idx - 150)
        left_max = right_idx - 30
        for left_idx in range(left_max, left_min - 1, -1):
            cup = df.iloc[left_idx : right_idx + 1]
            cup_width = right_idx - left_idx
            if cup_width < 30 or cup_width > 150:
                continue
            if handle_len > max(min_handle_len, cup_width // 3):
                continue

            left_price = float(closes.iloc[left_idx])
            avg_rim = (left_price + right_price) / 2.0
            if abs(left_price - right_price) / max(avg_rim, 1e-9) > 0.05:
                continue

            bottom_offset = int(cup["Low"].astype(float).argmin())
            bottom_idx = left_idx + bottom_offset
            cup_low = float(df.iloc[bottom_idx]["Low"])
            bottom_ratio = (bottom_idx - left_idx) / max(cup_width, 1)
            if bottom_ratio < 0.2 or bottom_ratio > 0.8:
                continue

            depth = (avg_rim - cup_low) / max(avg_rim, 1e-9)
            if depth < 0.15 or depth > 0.35:
                continue
            upper_third_floor = cup_low + (avg_rim - cup_low) * 0.65
            if handle_low < upper_third_floor:
                continue

            zone_half_width = max(2, int(cup_width * 0.1))
            bottom_zone_start = max(left_idx, bottom_idx - zone_half_width)
            bottom_zone_end = min(right_idx, bottom_idx + zone_half_width)
            bottom_zone = df.iloc[bottom_zone_start : bottom_zone_end + 1]
            near_low_threshold = cup_low * 1.03
            near_low_count = int((bottom_zone["Close"].astype(float) <= near_low_threshold).sum())
            if near_low_count < 3:
                continue
            local_bottom_window = df.iloc[max(left_idx, bottom_idx - 2) : min(right_idx, bottom_idx + 2) + 1]
            local_bottom_count = int(
                (local_bottom_window["Close"].astype(float) <= near_low_threshold).sum()
            )
            if local_bottom_count < 4:
                continue

            left_leg = df.iloc[left_idx:bottom_idx]
            right_leg = df.iloc[bottom_idx + 1 : right_idx + 1]
            if len(left_leg) < 5 or len(right_leg) < 5:
                continue

            avg_vol_cup = float(cup["Volume"].mean())
            bottom_start = left_idx + int(cup_width * 0.3)
            bottom_end = left_idx + int(cup_width * 0.7)
            bottom_vol_zone = df.iloc[bottom_start : bottom_end + 1]
            right_rise_start = left_idx + int(cup_width * 0.7)
            right_rise = df.iloc[right_rise_start : right_idx + 1]
            if len(bottom_vol_zone) == 0 or len(right_rise) == 0:
                continue

            vol_bottom = float(bottom_vol_zone["Volume"].mean())
            vol_right_rise = float(right_rise["Volume"].mean())
            vol_handle = float(handle["Volume"].mean())
            if vol_bottom > avg_vol_cup * 0.95:
                continue
            if vol_right_rise < vol_bottom * 1.1:
                continue
            if vol_handle > vol_right_rise * 0.9:
                continue

            return True

    return False
