from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from pages.index_page.index_utils import compute_dow_markers

IndexSeries = List[Dict[str, object]]
Marker = Dict[str, object]
TrendChain = Dict[str, object]


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def build_trend_chains_for_series(
    series: IndexSeries,
    object_type: str,
    object_name: str,
    window: int = 5,
) -> List[TrendChain]:
    markers, _ = compute_dow_markers(series, window=window)
    return extract_trend_chains(markers, object_type, object_name)


def extract_trend_chains(
    markers: List[Marker],
    object_type: str,
    object_name: str,
) -> List[TrendChain]:
    """Etsi vahvat nousu-/laskuketjut HL/LH-pohjaisista markkereista."""
    chains: List[TrendChain] = []
    n = len(markers)
    i = 0
    while i < n:
        m = markers[i]
        label = m.get("label")
        if label == "HL":
            chain, next_idx = _build_chain(markers, i, direction="UP")
            if chain:
                chain.update({"object_type": object_type, "object_name": object_name})
                chains.append(chain)
            i = next_idx
        elif label == "LH":
            chain, next_idx = _build_chain(markers, i, direction="DOWN")
            if chain:
                chain.update({"object_type": object_type, "object_name": object_name})
                chains.append(chain)
            i = next_idx
        else:
            i += 1
    # Sortataan confidence DESC, end_date DESC
    chains.sort(key=lambda c: (c.get("confidence", 0), c.get("end_date")), reverse=True)
    return chains


def _build_chain(
    markers: List[Marker],
    start_idx: int,
    direction: str,
) -> tuple[Optional[TrendChain], int]:
    qualifying = {"UP": ("HL", "HH"), "DOWN": ("LH", "LL")}
    break_on = {"UP": "LL", "DOWN": "HH"}

    q_labels = qualifying[direction]
    breaker = break_on[direction]

    start_marker = markers[start_idx]
    start_label = start_marker.get("label")
    if start_label not in q_labels or (direction == "UP" and start_label != "HL") or (
        direction == "DOWN" and start_label != "LH"
    ):
        return None, start_idx + 1

    idx = start_idx
    events: List[Marker] = []
    opposite_counts = {"LH": 0, "HL": 0}
    while idx < len(markers):
        cur = markers[idx]
        lab = cur.get("label")
        if lab == breaker:
            break
        if lab in q_labels:
            events.append(cur)
        if lab in opposite_counts:
            opposite_counts[lab] += 1
        idx += 1

    if len(events) < 2:
        return None, idx

    if direction == "UP":
        count_hl = sum(1 for e in events if e.get("label") == "HL")
        count_hh = sum(1 for e in events if e.get("label") == "HH")
        pairs = min(count_hl, count_hh)
    else:
        count_lh = sum(1 for e in events if e.get("label") == "LH")
        count_ll = sum(1 for e in events if e.get("label") == "LL")
        pairs = min(count_lh, count_ll)

    if pairs < 2:
        return None, idx

    start_date = events[0]["date"]
    end_date = events[-1]["date"]
    start_dt = start_date if isinstance(start_date, dt.date) else dt.date.fromisoformat(str(start_date))
    end_dt = end_date if isinstance(end_date, dt.date) else dt.date.fromisoformat(str(end_date))
    duration_days = (end_dt - start_dt).days

    # Confidence
    structure_score = min(60, pairs * 20)
    duration_score = clamp((duration_days / 90.0) * 25.0, 0, 25)
    penalty = 0
    if direction == "UP" and opposite_counts.get("LH", 0) >= 2:
        penalty = 5
    if direction == "DOWN" and opposite_counts.get("HL", 0) >= 2:
        penalty = 5
    confidence = int(clamp(structure_score + duration_score - penalty, 0, 100))

    chain: TrendChain = {
        "direction": direction,
        "start_date": start_date,
        "end_date": end_date,
        "events_count": len(events),
        "pairs_count": pairs,
        "confidence": confidence,
    }
    return chain, idx
