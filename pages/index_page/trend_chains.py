from __future__ import annotations

import datetime as dt
from typing import List, Optional, Sequence, Tuple

from pages.index_page.trend_models import SwingPoint, TrendChain
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


def _build_chain(
    labels: List[Tuple[dt.date, float, str]],
    start_idx: int,
    direction: str,
) -> Tuple[Optional[TrendChain], int]:
    qualifying = {"UP": ("HL", "HH"), "DOWN": ("LH", "LL")}
    if direction not in qualifying:
        return None, start_idx + 1
    q = qualifying[direction]

    start_label = labels[start_idx][2]
    if (direction == "UP" and start_label != "HL") or (
        direction == "DOWN" and start_label != "LH"
    ):
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

    pairs = min(count_hl, count_hh) if direction == "UP" else min(count_lh, count_ll)
    if pairs < 2:
        return None, idx

    start_date = events[0][0]
    end_date = events[-1][0]
    events_count = len(events)

    structure_score = min(60, pairs * 20)
    confidence = int(clamp(structure_score, 0, 100))

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


def compute_chains(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    k: int,
) -> List[TrendChain]:
    lookback = clamp_lookback(lookback)
    k = k if k in (2, 3, 4) else 2
    window = list(series)[-lookback:]
    swings = _swing_points(window, k)
    labels = _label_swings(swings)

    chains: List[TrendChain] = []
    i = 0
    while i < len(labels):
        lab_i = labels[i][2]
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
