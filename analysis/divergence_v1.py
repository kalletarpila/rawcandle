from __future__ import annotations

from typing import Optional


DIVERGENCE_VERSION = "DIVERGENCE_V1"

RSI_PERIOD = 14
CANDIDATE_WINDOW = 10
LOOKBACK_DAYS = 90
MIN_HISTORY_DAYS = 30


def clamp01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def compute_rsi_wilder(closes: list[float], period: int = RSI_PERIOD) -> list[Optional[float]]:
    size = len(closes)
    if size == 0:
        return []

    rsi: list[Optional[float]] = [None] * size
    if size <= period:
        return rsi

    gains = [0.0] * size
    losses = [0.0] * size
    for idx in range(1, size):
        delta = closes[idx] - closes[idx - 1]
        gains[idx] = max(delta, 0.0)
        losses[idx] = max(-delta, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    rsi[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for idx in range(period + 1, size):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period
        rsi[idx] = _rsi_from_avgs(avg_gain, avg_loss)

    return rsi


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def is_rolling_low_candidate(closes: list[float], idx: int, window: int = CANDIDATE_WINDOW) -> bool:
    if idx < 0 or idx >= len(closes):
        return False
    if idx < window - 1:
        return False
    start = idx - window + 1
    trailing = closes[start : idx + 1]
    if not trailing:
        return False
    return closes[idx] == min(trailing)


def is_rolling_high_candidate(closes: list[float], idx: int, window: int = CANDIDATE_WINDOW) -> bool:
    if idx < 0 or idx >= len(closes):
        return False
    if idx < window - 1:
        return False
    start = idx - window + 1
    trailing = closes[start : idx + 1]
    if not trailing:
        return False
    return closes[idx] == max(trailing)


def bullish_oversold_score(rsi_t: float) -> float:
    if rsi_t <= 30.0:
        return 1.0
    if rsi_t <= 35.0:
        return 0.7
    if rsi_t <= 40.0:
        return 0.4
    return 0.1


def bearish_overbought_score(rsi_t: float) -> float:
    if rsi_t >= 70.0:
        return 1.0
    if rsi_t >= 65.0:
        return 0.7
    if rsi_t >= 60.0:
        return 0.4
    return 0.1


def compute_bullish_candidate_strength(
    close_p: float,
    close_t: float,
    rsi_p: float,
    rsi_t: float,
) -> float:
    if close_p <= 0.0 or close_t <= 0.0:
        return 0.0

    price_drop_pct = (close_p - close_t) / close_p
    price_score = clamp01(price_drop_pct / 0.08)

    rsi_delta = rsi_t - rsi_p
    rsi_score = clamp01(rsi_delta / 10.0)

    oversold_score = bullish_oversold_score(rsi_t)
    score = 0.45 * price_score + 0.45 * rsi_score + 0.10 * oversold_score
    return clamp01(score)


def compute_bearish_candidate_strength(
    close_p: float,
    close_t: float,
    rsi_p: float,
    rsi_t: float,
) -> float:
    if close_p <= 0.0 or close_t <= 0.0:
        return 0.0

    price_rise_pct = (close_t - close_p) / close_p
    price_score = clamp01(price_rise_pct / 0.08)

    rsi_drop = rsi_p - rsi_t
    rsi_score = clamp01(rsi_drop / 10.0)

    overbought_score = bearish_overbought_score(rsi_t)
    score = 0.45 * price_score + 0.45 * rsi_score + 0.10 * overbought_score
    return clamp01(score)
