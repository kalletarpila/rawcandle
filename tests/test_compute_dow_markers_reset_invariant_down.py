# test_compute_dow_markers_reset_invariant_down.py
import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_reset_does_not_reuse_old_down_structure_window_3():
    """
    DOWN-side structural invariant with window=3.

    Plan:
    - Pre-reset DOWN regime: H -> L -> LH -> LL
    - Reset via close > active_structural_low
    - Post-reset: first pivot-low must be "L" (initial)
    - Then a new LH forms
    - Then next pivot-low is "LL" (relative to new low)
    """
    base = dt.date(2024, 5, 1)
    values = [
        110,
        108,
        106,  # 0-2 (before H)
        120,  # 3 H
        112,
        108,
        105,  # 4-6 (after H)
        95,  # 7 L
        100,
        104,
        107,  # 8-10 (after L)
        115,  # 11 LH
        108,
        102,
        98,  # 12-14 (after LH)
        85,  # 15 LL -> DOWN
        92,
        96,
        100,  # 16-18 (after LL)
        110,  # 19 reset break (close > active_structural_low)
        104,
        100,
        96,  # 20-22 (after break)
        80,  # 23 first post-reset L
        88,
        92,
        95,  # 24-26 (after L)
        105,  # 27 new LH
        98,
        94,
        90,  # 28-30 (after LH)
        75,  # 31 new LL
        82,
        86,
        90,  # 32-34 (after LL)
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3)

    first_low_date = base + dt.timedelta(days=23)
    second_low_date = base + dt.timedelta(days=31)

    first_low = [m for m in markers if m["date"] == first_low_date]
    second_low = [m for m in markers if m["date"] == second_low_date]

    assert len(first_low) == 1
    assert first_low[0]["label"] == "L"

    assert len(second_low) == 1
    assert second_low[0]["label"] == "LL"
