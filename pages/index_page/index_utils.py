from __future__ import annotations

import datetime as dt
from typing import Dict, List, Tuple

IndexSeries = List[Dict[str, object]]


def compute_dow_markers(series: IndexSeries, window: int = 5) -> Tuple[List[Dict], str]:
    """
    Laske pivotit (HH/HL/LH/LL) ja trendiyhteenveto.

    Returns:
        markers: lista dict-olioita (date, value, label)
        summary: lyhyt trenditeksti
    """
    if not series:
        return [], "NEUTRAL"
    values = [row["value"] for row in series]
    dates = [row["date"] for row in series]
    n = len(values)
    pivots: List[Tuple[int, str]] = []
    for i in range(n):
        start = max(0, i - window)
        end = min(n, i + window + 1)
        window_vals = values[start:end]
        if not window_vals:
            continue
        v = values[i]
        if v is None:
            continue
        if v == max(window_vals) and window_vals.count(v) == 1:
            pivots.append((i, "H"))
        elif v == min(window_vals) and window_vals.count(v) == 1:
            pivots.append((i, "L"))

    markers: List[Dict] = []
    last_high = None
    last_low = None
    trend = "NEUTRAL"
    last_change_date = None

    for idx, kind in pivots:
        val = values[idx]
        date = dates[idx]
        if kind == "H":
            if last_high is not None:
                label = "HH" if val > last_high[1] else "LH"
            else:
                label = "H"
            last_high = (date, val)
        else:
            if last_low is not None:
                label = "HL" if val > last_low[1] else "LL"
            else:
                label = "L"
            last_low = (date, val)
        markers.append({"date": date, "value": val, "label": label})
        last_change_date = date

    if markers:
        highs = [m for m in markers if m["label"].startswith("H")]
        lows = [m for m in markers if m["label"].startswith("L")]
        if highs and lows:
            last_high_label = highs[-1]["label"]
            last_low_label = lows[-1]["label"]
            if last_high_label == "HH" and last_low_label == "HL":
                trend = "UP"
            elif last_high_label == "LH" and last_low_label == "LL":
                trend = "DOWN"
    summary = f"{trend} (pivot {last_change_date})" if last_change_date else trend
    return markers, summary
