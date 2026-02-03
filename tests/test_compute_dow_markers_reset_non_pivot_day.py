# test_compute_dow_markers_reset_non_pivot_day.py
import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_uptrend_reset_on_non_pivot_day_window_3():
    """
    UP regime reset with window=3 where the break happens on a NON-pivot day.

    Pivot plan (window=3 requires 3 bars before/after):
    - L at idx 3
    - H at idx 7
    - HL at idx 11 (higher than idx 3)
        - HH at idx 15 (higher than idx 7) -> UP
        - Break on idx 18 (close < active_structural_low) with a flat low plateau (idx 18-24)
            so none of those days are pivot lows
    - Next confirmed H at idx 25 must be labeled "H"
    """
    base = dt.date(2024, 3, 1)
    values = [
        130,
        125,
        120,  # 0-2 (before L)
        100,  # 3 L
        120,
        130,
        140,  # 4-6 (after L)
        190,  # 7 H
        170,
        165,
        160,  # 8-10 (after H)
        150,  # 11 HL
        165,
        170,
        175,  # 12-14 (after HL)
        210,  # 15 HH -> UP
        180,
        170,  # 16-17 (after HH)
        140,
        140,
        140,
        140,
        140,
        140,
        140,  # 18-24 break plateau (non-pivot lows)
        145,  # 25 next H -> should be "H" after reset
        140,
        140,
        140,  # 26-28 (after H)
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3)

    target_date = base + dt.timedelta(days=25)
    high_after_break = [
        m
        for m in markers
        if m["date"] == target_date and m["label"] in {"H", "HH", "LH"}
    ]

    assert len(high_after_break) == 1
    assert high_after_break[0]["label"] == "H"
