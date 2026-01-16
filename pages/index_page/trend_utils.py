from __future__ import annotations

import datetime as dt
from typing import Dict

SeriesPoint = Dict[str, object]  # expects keys: date (dt.date), value (float)


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def clamp_int(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def clamp_lookback(x: int, lo: int = 5, hi: int = 120, default: int = 15) -> int:
    try:
        x = int(x)
    except Exception:
        x = default
    return clamp_int(x, lo, hi)
