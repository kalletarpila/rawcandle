from __future__ import annotations

import datetime as dt
from typing import List, Sequence, Tuple

from pages.index_page.index_utils import compute_dow_markers
from pages.index_page.trend_calc import compute_structural_relevance
from pages.index_page.trend_models import TrendChain
from pages.index_page.trend_utils import SeriesPoint, clamp_lookback


def _build_chain(
    labels: List[Tuple[dt.date, float, str]],
    start_idx: int,
    direction: str,
) -> Tuple[TrendChain | None, int]:
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
    confidence = int(structure_score)
    relevance = compute_structural_relevance(end_date)

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
            relevance=relevance,
        ),
        idx,
    )


def compute_chains(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    pivot_window: int,
) -> List[TrendChain]:
    lookback = clamp_lookback(lookback)
    window_series = list(series)[-lookback:]
    pivot_win = max(1, int(pivot_window or 1))
    markers, _ = compute_dow_markers(window_series, window=pivot_win)
    labels: List[Tuple[dt.date, float, str]] = [
        (m["date"], float(m["value"]), str(m["label"]))
        for m in markers
        if str(m.get("label")) in {"HH", "HL", "LH", "LL"}
    ]

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
