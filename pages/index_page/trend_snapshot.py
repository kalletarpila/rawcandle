from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from pages.index_page.trend_models import SwingPoint, TrendSnapshot
from pages.index_page.trend_utils import SeriesPoint, clamp, clamp_lookback


def _swing_points(series: Sequence[SeriesPoint], k: int) -> List[SwingPoint]:
    n = len(series)
    swings: List[SwingPoint] = []
    for i in range(k, n - k):
        val = float(series[i]["value"])
        is_high = all(
            val > float(series[i - j]["value"]) and val > float(series[i + j]["value"])
            for j in range(1, k + 1)
        )
        is_low = all(
            val < float(series[i - j]["value"]) and val < float(series[i + j]["value"])
            for j in range(1, k + 1)
        )
        if is_high:
            swings.append(SwingPoint(series[i]["date"], val, "H"))
        elif is_low:
            swings.append(SwingPoint(series[i]["date"], val, "L"))
    return swings


def _latest_swings(
    swings: List[SwingPoint],
) -> Tuple[
    Optional[SwingPoint],
    Optional[SwingPoint],
    Optional[SwingPoint],
    Optional[SwingPoint],
]:
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    sh1 = highs[-1] if len(highs) >= 1 else None
    sh2 = highs[-2] if len(highs) >= 2 else None
    sl1 = lows[-1] if len(lows) >= 1 else None
    sl2 = lows[-2] if len(lows) >= 2 else None
    return sh1, sh2, sl1, sl2


def compute_snapshot(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    k: int,
) -> TrendSnapshot:
    lookback = clamp_lookback(lookback)
    k = k if k in (2, 3, 4) else 2
    if len(series) < k * 2 + 2:
        return TrendSnapshot(
            object_type,
            object_name,
            "NEUTRAL",
            "WARNING",
            0,
            None,
            None,
            None,
            None,
            "-",
        )

    window = list(series)[-lookback:]
    swings = _swing_points(window, k)
    sh1, sh2, sl1, sl2 = _latest_swings(swings)

    latest_val = float(window[-1]["value"])

    hh_form = False
    lh_form = False
    hl_intact = False
    ll_form = False
    if sh1 and sh2:
        ratio = sh1.value / sh2.value if sh2.value else 1.0
        hh_form = ratio > 1.0
        lh_form = ratio < 1.0
    if sl1 and sl2:
        ratio = sl1.value / sl2.value if sl2.value else 1.0
        hl_intact = ratio > 1.0
        ll_form = ratio < 1.0

    break_signal = "-"
    if sl1 and latest_val < sl1.value:
        break_signal = "Down"
    if sh1 and latest_val > sh1.value:
        break_signal = "Up"

    bias = "NEUTRAL"
    if hh_form and hl_intact:
        bias = "UP"
    elif lh_form and ll_form:
        bias = "DOWN"

    if bias == "UP":
        state = "CONTINUATION" if break_signal != "Down" else "REVERSAL"
    elif bias == "DOWN":
        state = "CONTINUATION" if break_signal != "Up" else "REVERSAL"
    else:
        state = "WARNING"

    confidence = 0
    if sh1 and sh2:
        confidence += 25
    if sl1 and sl2:
        confidence += 25
    if sh1 and sh2 and abs(sh1.value / sh2.value - 1.0) > 0.005:
        confidence += 20
    if sl1 and sl2 and abs(sl1.value / sl2.value - 1.0) > 0.005:
        confidence += 20
    if (bias == "UP" and break_signal == "Down") or (
        bias == "DOWN" and break_signal == "Up"
    ):
        confidence += 10

    confidence = int(clamp(confidence, 0, 100))

    return TrendSnapshot(
        object_type=object_type,
        object_name=object_name,
        bias=bias,
        state=state,
        confidence=confidence,
        sh1=sh1,
        sh2=sh2,
        sl1=sl1,
        sl2=sl2,
        break_signal=break_signal,
    )
