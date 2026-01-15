from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Sequence, Tuple

from pages.index_page.trend_models import SwingPoint, TrendChain, TrendSnapshot

SeriesPoint = Dict[str, object]  # expects keys: date (dt.date), value (float)


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _swing_points(series: Sequence[SeriesPoint], k: int) -> List[SwingPoint]:
    n = len(series)
    swings: List[SwingPoint] = []
    for i in range(k, n - k):
        val = float(series[i]["value"])
        is_high = all(val > float(series[i - j]["value"]) and val > float(series[i + j]["value"]) for j in range(1, k + 1))
        is_low = all(val < float(series[i - j]["value"]) and val < float(series[i + j]["value"]) for j in range(1, k + 1))
        if is_high:
            swings.append(SwingPoint(series[i]["date"], val, "H"))
        elif is_low:
            swings.append(SwingPoint(series[i]["date"], val, "L"))
    return swings


def _latest_swings(swings: List[SwingPoint]) -> Tuple[Optional[SwingPoint], Optional[SwingPoint], Optional[SwingPoint], Optional[SwingPoint]]:
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    sh1 = highs[-1] if len(highs) >= 1 else None
    sh2 = highs[-2] if len(highs) >= 2 else None
    sl1 = lows[-1] if len(lows) >= 1 else None
    sl2 = lows[-2] if len(lows) >= 2 else None
    return sh1, sh2, sl1, sl2


def compute_snapshot(series: Sequence[SeriesPoint], object_type: str, object_name: str, lookback: int, k: int) -> TrendSnapshot:
    if lookback < 5:
        lookback = 5
    if lookback > 120:
        lookback = 120
    k = k if k in (2, 3, 4) else 2
    if len(series) < k * 2 + 2:
        return TrendSnapshot(object_type, object_name, "NEUTRAL", "WARNING", 0, None, None, None, None, "-")

    window = list(series)[-lookback:]
    swings = _swing_points(window, k)
    sh1, sh2, sl1, sl2 = _latest_swings(swings)

    latest = window[-1]
    latest_val = float(latest["value"])

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

    state = "WARNING"
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
    if (bias == "UP" and break_signal == "Down") or (bias == "DOWN" and break_signal == "Up"):
        confidence += 10
    confidence = int(_clamp(confidence, 0, 100))

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


def _label_swings(swings: List[SwingPoint]) -> List[Tuple[dt.date, float, str]]:
    labeled = []
    prev_high: Optional[SwingPoint] = None
    prev_low: Optional[SwingPoint] = None
    for s in swings:
        if s.kind == "H":
            if prev_high:
                label = "HH" if s.value > prev_high.value else "LH"
            else:
                label = "H"
            prev_high = s
        else:
            if prev_low:
                label = "HL" if s.value > prev_low.value else "LL"
            else:
                label = "L"
            prev_low = s
        labeled.append((s.date, s.value, label))
    return labeled


def compute_chains(series: Sequence[SeriesPoint], object_type: str, object_name: str, lookback: int, k: int) -> List[TrendChain]:
    if lookback < 5:
        lookback = 5
    if lookback > 120:
        lookback = 120
    k = k if k in (2, 3, 4) else 2
    window = list(series)[-lookback:]
    swings = _swing_points(window, k)
    labels = _label_swings(swings)
    chains: List[TrendChain] = []
    i = 0
    while i < len(labels):
        date_i, val_i, lab_i = labels[i]
        if lab_i == "HL":
            chain, nxt = _build_chain(labels, i, direction="UP")
            if chain:
                chain.object_type = object_type
                chain.object_name = object_name
                chains.append(chain)
                i = nxt
                continue
        elif lab_i == "LH":
            chain, nxt = _build_chain(labels, i, direction="DOWN")
            if chain:
                chain.object_type = object_type
                chain.object_name = object_name
                chains.append(chain)
                i = nxt
                continue
        i += 1
    chains.sort(key=lambda c: (c.confidence, c.end_date), reverse=True)
    return chains


def _build_chain(labels: List[Tuple[dt.date, float, str]], start_idx: int, direction: str) -> Tuple[Optional[TrendChain], int]:
    qualifying = {"UP": ("HL", "HH"), "DOWN": ("LH", "LL")}
    if direction not in qualifying:
        return None, start_idx + 1
    q = qualifying[direction]
    start_label = labels[start_idx][2]
    if (direction == "UP" and start_label != "HL") or (direction == "DOWN" and start_label != "LH"):
        return None, start_idx + 1

    idx = start_idx
    events: List[Tuple[dt.date, float, str]] = []
    while idx < len(labels) and labels[idx][2] in q:
        events.append(labels[idx])
        idx += 1

    count_hl = sum(1 for _, _, l in events if l == "HL")
    count_hh = sum(1 for _, _, l in events if l == "HH")
    count_lh = sum(1 for _, _, l in events if l == "LH")
    count_ll = sum(1 for _, _, l in events if l == "LL")

    pairs = 0
    if direction == "UP":
        pairs = min(count_hl, count_hh)
    else:
        pairs = min(count_lh, count_ll)

    if pairs < 2:
        return None, idx

    start_date = events[0][0]
    end_date = events[-1][0]
    events_count = len(events)

    structure_score = min(60, pairs * 20)
    confidence = int(_clamp(structure_score, 0, 100))

    return (
        TrendChain(
            object_type="",
            object_name="",
            direction="UP" if direction == "UP" else "DOWN",
            start_date=start_date,
            end_date=end_date,
            events_count=events_count,
            pairs_count=pairs,
            confidence=confidence,
        ),
        idx,
    )
