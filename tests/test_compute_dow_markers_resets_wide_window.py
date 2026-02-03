# test_compute_dow_markers_resets_wide_window.py
import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_uptrend_regime_reset_window_3():
    """
    UP regime reset with window=3.

    Pivot plan (window=3 requires 3 bars before/after):
    - L at idx 3 (lower than idx 0-2 and 4-6)
    - H at idx 7 (higher than idx 4-6 and 8-10)
    - HL at idx 11 (higher low than idx 3, lower than neighbors)
    - HH at idx 15 (higher high than idx 7, higher than neighbors) -> UP
    - Break at idx 19 where close < active_structural_low (97)
    - Next confirmed H at idx 23 must be labeled "H"
    """
    base = dt.date(2024, 1, 1)
    values = [
        105,
        102,
        100,  # 0-2 (before L)
        95,  # 3 L
        98,
        101,
        103,  # 4-6 (after L)
        110,  # 7 H
        106,
        104,
        102,  # 8-10 (after H)
        97,  # 11 HL (higher than 95)
        100,
        103,
        105,  # 12-14 (after HL)
        115,  # 15 HH (higher than 110)
        110,
        107,
        104,  # 16-18 (after HH)
        90,  # 19 break (val < active_structural_low 97)
        95,
        98,
        100,  # 20-22 (after break)
        108,  # 23 next H -> should be "H" after reset
        103,
        101,
        99,  # 24-26 (after H)
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3)

    target_date = base + dt.timedelta(days=23)
    high_after_break = [
        m
        for m in markers
        if m["date"] == target_date and m["label"] in {"H", "HH", "LH"}
    ]

    assert len(high_after_break) == 1
    assert high_after_break[0]["label"] == "H"


def test_downtrend_regime_reset_window_3():
    """
    DOWN regime reset with window=3.

    Pivot plan (window=3 requires 3 bars before/after):
    - H at idx 3 (higher than idx 0-2 and 4-6)
    - L at idx 7 (lower than idx 4-6 and 8-10)
    - LH at idx 11 (lower high than idx 3, higher than neighbors)
    - LL at idx 15 (lower low than idx 7, lower than neighbors) -> DOWN
    - Break at idx 19 where close > active_structural_low (85)
    - Next confirmed L at idx 23 must be labeled "L"
    """
    base = dt.date(2024, 2, 1)
    values = [
        95,
        98,
        100,  # 0-2 (before H)
        105,  # 3 H
        102,
        100,
        98,  # 4-6 (after H)
        90,  # 7 L
        95,
        97,
        99,  # 8-10 (after L)
        103,  # 11 LH (lower than 105)
        99,
        97,
        95,  # 12-14 (after LH)
        85,  # 15 LL (lower than 90)
        90,
        92,
        94,  # 16-18 (after LL)
        100,  # 19 break (val > active_structural_low 85)
        96,
        94,
        92,  # 20-22 (after break)
        88,  # 23 next L -> should be "L" after reset
        92,
        94,
        96,  # 24-26 (after L)
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3)

    target_date = base + dt.timedelta(days=23)
    low_after_break = [
        m
        for m in markers
        if m["date"] == target_date and m["label"] in {"L", "HL", "LL"}
    ]

    assert len(low_after_break) == 1
    assert low_after_break[0]["label"] == "L"
