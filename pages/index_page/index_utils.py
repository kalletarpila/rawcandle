from __future__ import annotations

import datetime as dt
from typing import Dict, List, Tuple

IndexSeries = List[Dict[str, object]]


def compute_dow_markers(
    series: IndexSeries, window: int = 5, use_high_low: bool = False
) -> Tuple[List[Dict], str]:
    """
    Laske pivotit (HH/HL/LH/LL) ja trendiyhteenveto.

    Args:
        series: Datasarja (value tai high/low)
        window: Pivot-ikkuna (N)
        use_high_low: Jos True, käytä 'high' ja 'low' kenttiä, muuten 'value'

    Returns:
        markers: lista dict-olioita (date, value, label)
        summary: lyhyt trenditeksti
    """
    if not series:
        return [], "NEUTRAL"

    if use_high_low:
        highs = [row.get("high") for row in series]
        lows = [row.get("low") for row in series]
        values = [row.get("value") or row.get("close") for row in series]
    else:
        values = [row["value"] for row in series]
        highs = values
        lows = values

    dates = [row["date"] for row in series]
    n = len(values)
    pivots: List[Tuple[int, str, float]] = []

    for i in range(n):
        # Tarkista high-pivot: vertaa taakse ja eteen erikseen
        # high[t0] > max(high[t0-N … t0-1]) AND high[t0] > max(high[t0+1 … t0+N])
        if highs[i] is not None:
            is_high = True
            # Tarkista taakse: kaikki edeltävät arvot pitää olla pienempiä
            for j in range(max(0, i - window), i):
                if highs[j] is not None and highs[j] >= highs[i]:
                    is_high = False
                    break
            # Tarkista eteen: kaikki seuraavat arvot pitää olla pienempiä
            if is_high:
                for j in range(i + 1, min(n, i + window + 1)):
                    if highs[j] is not None and highs[j] >= highs[i]:
                        is_high = False
                        break
            if is_high:
                pivots.append((i, "H", highs[i]))

        # Tarkista low-pivot: vertaa taakse ja eteen erikseen
        # low[t0] < min(low[t0-N … t0-1]) AND low[t0] < min(low[t0+1 … t0+N])
        if lows[i] is not None:
            is_low = True
            # Tarkista taakse: kaikki edeltävät arvot pitää olla suurempia
            for j in range(max(0, i - window), i):
                if lows[j] is not None and lows[j] <= lows[i]:
                    is_low = False
                    break
            # Tarkista eteen: kaikki seuraavat arvot pitää olla suurempia
            if is_low:
                for j in range(i + 1, min(n, i + window + 1)):
                    if lows[j] is not None and lows[j] <= lows[i]:
                        is_low = False
                        break
            if is_low:
                pivots.append((i, "L", lows[i]))

    markers: List[Dict] = []
    active_structural_high = None
    active_structural_low = None
    trend = "NEUTRAL"
    last_change_date = None

    for idx, kind, pivot_val in pivots:
        val = values[idx] if values[idx] is not None else pivot_val
        date = dates[idx]

        # Update trend state based on current markers (before processing new pivot)
        if markers:
            highs_so_far = [
                m for m in markers if m["label"].startswith("H") or m["label"] == "LH"
            ]
            lows_so_far = [
                m for m in markers if m["label"].startswith("L") or m["label"] == "HL"
            ]
            if highs_so_far and lows_so_far:
                last_high_label = highs_so_far[-1]["label"]
                last_low_label = lows_so_far[-1]["label"]
                if last_high_label == "HH" and last_low_label == "HL":
                    trend = "UP"
                elif last_high_label == "LH" and last_low_label == "LL":
                    trend = "DOWN"
                else:
                    trend = "NEUTRAL"

        # Regime-reset logic: check for regime death BEFORE processing pivot
        # Guard: only one reset can trigger per iteration
        if (
            trend == "UP"
            and active_structural_low is not None
            and val < active_structural_low[1]
        ):
            # Uptrend regime broken: close breaks active_structural_low downwards
            active_structural_high = None
        elif (
            trend == "DOWN"
            and active_structural_low is not None
            and val > active_structural_low[1]
        ):
            # Downtrend regime broken: close breaks active_structural_low upwards
            active_structural_low = None

        if kind == "H":
            if active_structural_high is not None:
                if pivot_val > active_structural_high[1]:
                    label = "HH"
                    active_structural_high = (date, pivot_val)  # HH päivittää
                else:
                    label = "LH"
                    # LH EI päivitä active_structural_high
            else:
                label = "H"
                active_structural_high = (date, pivot_val)
        else:  # kind == "L"
            if active_structural_low is not None:
                if pivot_val > active_structural_low[1]:
                    label = "HL"
                else:
                    label = "LL"
                # Molemmat HL ja LL päivittävät active_structural_low
                active_structural_low = (date, pivot_val)
            else:
                label = "L"
                active_structural_low = (date, pivot_val)

        markers.append({"date": date, "value": val, "label": label})
        last_change_date = date

    if markers:
        highs = [m for m in markers if m["label"].startswith("H") or m["label"] == "LH"]
        lows = [m for m in markers if m["label"].startswith("L") or m["label"] == "HL"]
        if highs and lows:
            last_high_label = highs[-1]["label"]
            last_low_label = lows[-1]["label"]
            if last_high_label == "HH" and last_low_label == "HL":
                trend = "UP"
            elif last_high_label == "LH" and last_low_label == "LL":
                trend = "DOWN"
    summary = f"{trend} (pivot {last_change_date})" if last_change_date else trend
    return markers, summary
