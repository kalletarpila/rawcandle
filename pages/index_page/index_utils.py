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

    if not hasattr(compute_dow_markers, "_call_seq"):
        compute_dow_markers._call_seq = 0
    compute_dow_markers._call_seq += 1
    call_id = compute_dow_markers._call_seq

    scope_keys = [
        "scope",
        "level",
        "kind",
        "series_scope",
        "series_kind",
        "source_type",
    ]
    name_keys = [
        "name",
        "series_name",
        "symbol",
        "ticker",
        "label",
        "id",
    ]

    scope = None
    name = None
    for row in series[:20]:
        if not isinstance(row, dict):
            continue
        if scope is None:
            for key in scope_keys:
                value = row.get(key)
                if value:
                    scope = value
                    break
        if name is None:
            for key in name_keys:
                value = row.get(key)
                if value:
                    name = value
                    break
        if scope is not None and name is not None:
            break
    if scope is None:
        scope = "UNKNOWN"
    if name is None:
        name = "UNKNOWN"

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
    last_trend_change_date = None
    debug = True
    MEANINGLESS_PCT = 0.0001
    EPS_PCT = 0.0001
    HIGH_LABELS = {"H", "HH", "LH"}
    LOW_LABELS = {"L", "HL", "LL"}

    def _trend_from_markers(
        markers_list: List[Dict],
    ) -> Tuple[str, str | None, str | None]:
        last_reset_idx = None
        for i, marker in enumerate(markers_list):
            if marker.get("label") == "R":
                last_reset_idx = i
        if last_reset_idx is None:
            markers_view = markers_list
        else:
            markers_view = markers_list[last_reset_idx + 1 :]
        highs_so_far = [m for m in markers_view if m.get("label") in HIGH_LABELS]
        lows_so_far = [m for m in markers_view if m.get("label") in LOW_LABELS]
        last_high_label = highs_so_far[-1]["label"] if highs_so_far else None
        last_low_label = lows_so_far[-1]["label"] if lows_so_far else None
        if last_high_label == "HH" and last_low_label == "HL":
            trend_value = "UP"
        elif last_high_label == "LH" and last_low_label == "LL":
            trend_value = "DOWN"
        else:
            trend_value = "NEUTRAL"
        return trend_value, last_high_label, last_low_label

    for idx, kind, pivot_val in pivots:
        val = values[idx] if values[idx] is not None else pivot_val
        date = dates[idx]
        prev_trend = trend
        trend, last_high_label, last_low_label = _trend_from_markers(markers)

        if trend != prev_trend and trend in ("UP", "DOWN"):
            markers.append(
                {
                    "date": date,
                    "value": val,
                    "label": "U" if trend == "UP" else "D",
                }
            )
            if debug:
                print(
                    f"[CALL {call_id}] [MARKER] {scope} | {name} | {date} | {markers[-1]['label']} | price={val}"
                )

        if kind == "H" and active_structural_high is not None:
            ref_price = active_structural_high[1]
            if ref_price:
                rel_diff = abs(pivot_val - ref_price) / ref_price
                if rel_diff < MEANINGLESS_PCT:
                    continue
        if kind == "L" and active_structural_low is not None:
            ref_price = active_structural_low[1]
            if ref_price:
                rel_diff = abs(pivot_val - ref_price) / ref_price
                if rel_diff < MEANINGLESS_PCT:
                    continue

        # Regime-reset logic: check for regime death BEFORE processing pivot
        if (
            trend == "UP"
            and active_structural_low is not None
            and val < active_structural_low[1]
        ):
            # Uptrend regime broken: close breaks active_structural_low downwards
            if debug:
                print(
                    f"[CALL {call_id}] [RESET] {scope} | {name} | {date} | trend={trend} | break_price={val}"
                )
            markers.append({"date": date, "value": val, "label": "R"})
            if debug:
                print(
                    f"[CALL {call_id}] [MARKER] {scope} | {name} | {date} | R | price={val}"
                )
            active_structural_high = None
            updated_trend, last_high_label, last_low_label = _trend_from_markers(
                markers
            )
            if updated_trend != trend:
                last_trend_change_date = date
                if debug:
                    print(
                        f"[CALL {call_id}] [TREND] {scope} | {name} | {date} | {trend} → {updated_trend} | last_high={last_high_label} | last_low={last_low_label}"
                    )
            trend = updated_trend
        elif (
            trend == "DOWN"
            and active_structural_low is not None
            and val > active_structural_low[1]
        ):
            # Downtrend regime broken: close breaks active_structural_low upwards
            if debug:
                print(
                    f"[CALL {call_id}] [RESET] {scope} | {name} | {date} | trend={trend} | break_price={val}"
                )
            markers.append({"date": date, "value": val, "label": "R"})
            if debug:
                print(
                    f"[CALL {call_id}] [MARKER] {scope} | {name} | {date} | R | price={val}"
                )
            active_structural_low = None
            active_structural_high = None
            updated_trend, last_high_label, last_low_label = _trend_from_markers(
                markers
            )
            if updated_trend != trend:
                last_trend_change_date = date
                if debug:
                    print(
                        f"[CALL {call_id}] [TREND] {scope} | {name} | {date} | {trend} → {updated_trend} | last_high={last_high_label} | last_low={last_low_label}"
                    )
            trend = updated_trend

        effective_kind = kind
        if kind == "L" and active_structural_high is not None:
            if pivot_val >= active_structural_high[1] * (1 - EPS_PCT):
                effective_kind = "H"
        elif kind == "H" and active_structural_low is not None:
            if pivot_val <= active_structural_low[1] * (1 + EPS_PCT):
                effective_kind = "L"

        if debug:
            ash_price = active_structural_high[1] if active_structural_high else None
            asl_price = active_structural_low[1] if active_structural_low else None
            print(
                f"[CALL {call_id}] [PIVOT_CTX] {scope} | {name} | {date} | kind={kind} effective={effective_kind} pivot_val={pivot_val} val={val} trend={trend} | ash={ash_price} | asl={asl_price}"
            )

        if effective_kind == "H":
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
        else:  # effective_kind == "L"
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
        if debug:
            print(
                f"[CALL {call_id}] [MARKER] {scope} | {name} | {date} | {label} | price={val}"
            )
        last_change_date = date
        updated_trend, last_high_label, last_low_label = _trend_from_markers(markers)
        if updated_trend != trend:
            last_trend_change_date = date
            if debug:
                print(
                    f"[CALL {call_id}] [TREND] {scope} | {name} | {date} | {trend} → {updated_trend} | last_high={last_high_label} | last_low={last_low_label}"
                )
        trend = updated_trend

    if markers:
        trend, last_high_label, last_low_label = _trend_from_markers(markers)
    summary = f"{trend} (pivot {last_change_date})" if last_change_date else trend
    return markers, summary
