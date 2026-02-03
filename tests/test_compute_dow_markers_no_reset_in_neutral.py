# test_compute_dow_markers_no_reset_in_neutral.py
import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_no_reset_in_neutral_regime_window_3():
    """
    NEUTRAL regime (window=3) should not trigger resets even when crossings occur.

    Structure plan (keep trend NEUTRAL throughout):
    - H at idx 3
    - L at idx 7
    - HH at idx 11 (higher high; last_high=HH, last_low=L -> NEUTRAL)
    - LL at idx 15 (lower low; last_high=HH, last_low=LL -> NEUTRAL)
      * crosses below prior pivot-low while NEUTRAL
    - HH at idx 19 (higher high; still NEUTRAL)
      * crosses above prior pivot-high while NEUTRAL
    """
    base = dt.date(2024, 6, 1)
    values = [
        120,
        115,
        110,  # 0-2 (before H)
        130,  # 3 H
        120,
        118,
        116,  # 4-6 (after H)
        100,  # 7 L
        110,
        112,
        114,  # 8-10 (after L)
        140,  # 11 HH (higher high)
        120,
        118,
        116,  # 12-14 (after HH)
        90,  # 15 LL (lower low) -> cross below prior low while NEUTRAL
        110,
        112,
        114,  # 16-18 (after LL)
        150,  # 19 HH (higher high) -> cross above prior high while NEUTRAL
        130,
        128,
        126,  # 20-22 (after HH)
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3)

    low_after_cross = [m for m in markers if m["date"] == base + dt.timedelta(days=15)]
    high_after_cross = [m for m in markers if m["date"] == base + dt.timedelta(days=19)]

    assert len(low_after_cross) == 1
    assert low_after_cross[0]["label"] == "LL"

    assert len(high_after_cross) == 1
    assert high_after_cross[0]["label"] == "HH"
