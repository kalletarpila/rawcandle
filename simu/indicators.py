from __future__ import annotations

import datetime as _dt
from typing import Dict, List

from .db import PriceRow
from . import config


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 0.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_rsi(price_rows: List[PriceRow], period: int = config.RSI_PERIOD) -> Dict[_dt.date, float]:
    """Return RSI values keyed by trading date."""
    if len(price_rows) <= period:
        return {}

    rsi_values: Dict[_dt.date, float] = {}
    gains: List[float] = []
    losses: List[float] = []

    avg_gain = 0.0
    avg_loss = 0.0

    for idx in range(1, len(price_rows)):
        change = price_rows[idx].close - price_rows[idx - 1].close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if idx <= period:
            gains.append(gain)
            losses.append(loss)
            if idx == period:
                avg_gain = sum(gains) / period
                avg_loss = sum(losses) / period
                rsi_values[price_rows[idx].date] = _rsi_value(avg_gain, avg_loss)
        else:
            avg_gain = ((avg_gain * (period - 1)) + gain) / period
            avg_loss = ((avg_loss * (period - 1)) + loss) / period
            rsi_values[price_rows[idx].date] = _rsi_value(avg_gain, avg_loss)

    return rsi_values


def compute_volume_growth(
    price_rows: List[PriceRow],
    window: int = config.VOLUME_SMA_WINDOW,
) -> Dict[_dt.date, float]:
    """Return volume growth percentages keyed by trading date."""
    if len(price_rows) <= window:
        return {}

    result: Dict[_dt.date, float] = {}
    for idx in range(window, len(price_rows)):
        history = price_rows[idx - window : idx]
        avg_volume = sum(row.volume for row in history) / window
        if avg_volume <= 0:
            continue
        growth = ((price_rows[idx].volume / avg_volume) - 1.0) * 100.0
        result[price_rows[idx].date] = growth
    return result
