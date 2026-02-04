# test_compute_dow_markers_resets.py
import datetime as dt
import pytest
from pages.index_page.index_utils import compute_dow_markers


def test_uptrend_regime_reset():
    """
    Test that active_structural_high resets when uptrend regime is broken.

    Scenario:
    - Build series that creates UP trend (HH + HL)
    - Add a pivot where close < active_structural_low
    - Next high pivot should be labeled 'H' (not HH/LH)
    """
    series = [
        {"date": dt.date(2024, 1, 1), "value": 100.0},
        {"date": dt.date(2024, 1, 2), "value": 95.0},  # L (first low)
        {"date": dt.date(2024, 1, 3), "value": 100.0},
        {"date": dt.date(2024, 1, 4), "value": 105.0},  # H (first high)
        {"date": dt.date(2024, 1, 5), "value": 100.0},
        {"date": dt.date(2024, 1, 6), "value": 98.0},  # HL (higher low than 95)
        {"date": dt.date(2024, 1, 7), "value": 105.0},
        {"date": dt.date(2024, 1, 8), "value": 110.0},  # HH (trend = UP now)
        {"date": dt.date(2024, 1, 9), "value": 105.0},
        {
            "date": dt.date(2024, 1, 10),
            "value": 90.0,
        },  # Breaks active_structural_low (98) -> reset
        {"date": dt.date(2024, 1, 11), "value": 90.0},  # confirmation
        {"date": dt.date(2024, 1, 12), "value": 100.0},
        {
            "date": dt.date(2024, 1, 13),
            "value": 105.0,
        },  # Should be 'H' (new initial high)
        {"date": dt.date(2024, 1, 14), "value": 100.0},
    ]

    markers, summary = compute_dow_markers(series, window=1)

    # Find the marker around 2024-01-13 (after regime break)
    high_after_break = [
        m
        for m in markers
        if m["date"] == dt.date(2024, 1, 13) and m["label"] in {"H", "HH", "LH"}
    ]

    # Should be labeled 'H' (initial) not 'HH' or 'LH' because active_structural_high was reset
    assert len(high_after_break) == 1
    assert high_after_break[0]["label"] == "H"


def test_downtrend_regime_reset():
    """
    Test that active_structural_low resets when downtrend regime is broken.

    Scenario:
    - Build series that creates DOWN trend (LH + LL)
    - Add a pivot where close > active_structural_high (breaking upwards)
    - Next low pivot should be labeled 'L' (not HL/LL)
    """
    series = [
        {"date": dt.date(2024, 1, 1), "value": 100.0},
        {"date": dt.date(2024, 1, 2), "value": 105.0},  # H (first high)
        {"date": dt.date(2024, 1, 3), "value": 100.0},
        {"date": dt.date(2024, 1, 4), "value": 95.0},  # L (first low)
        {"date": dt.date(2024, 1, 5), "value": 100.0},
        {"date": dt.date(2024, 1, 6), "value": 102.0},  # LH (lower high than 105)
        {"date": dt.date(2024, 1, 7), "value": 95.0},
        {"date": dt.date(2024, 1, 8), "value": 90.0},  # LL (trend = DOWN now)
        {"date": dt.date(2024, 1, 9), "value": 95.0},
        {
            "date": dt.date(2024, 1, 10),
            "value": 110.0,
        },  # Breaks active_structural_high (105) upwards
        {"date": dt.date(2024, 1, 11), "value": 110.0},  # confirmation
        {"date": dt.date(2024, 1, 12), "value": 90.0},
        {
            "date": dt.date(2024, 1, 13),
            "value": 85.0,
        },  # Should be 'L' (new initial low)
        {"date": dt.date(2024, 1, 14), "value": 90.0},
    ]

    markers, summary = compute_dow_markers(series, window=1)

    # Find the marker around 2024-01-13 (after regime break)
    low_after_break = [
        m
        for m in markers
        if m["date"] == dt.date(2024, 1, 13) and m["label"] in {"L", "HL", "LL"}
    ]

    # Should be labeled 'L' (initial) not 'HL' or 'LL' because active_structural_low was reset
    assert len(low_after_break) == 1
    assert low_after_break[0]["label"] == "L"


def test_sensitive_down_reset_default_off():
    base = dt.date(2024, 2, 1)
    values = [
        100.0,
        110.0,  # H
        100.0,
        90.0,  # L
        100.0,
        105.0,  # LH
        95.0,
        80.0,  # LL -> DOWN
        100.0,
        106.0,  # LH below original ASH (110)
        100.0,
        100.0,
        107.0,  # two closes above 106 but below 110
        107.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=2, sensitive_down_reset=False)

    reset_markers = [m for m in markers if m["label"] == "R"]
    assert not reset_markers


def test_sensitive_down_reset_triggers():
    base = dt.date(2024, 2, 1)
    values = [
        100.0,
        110.0,  # H
        100.0,
        90.0,  # L
        100.0,
        105.0,  # LH
        95.0,
        80.0,  # LL -> DOWN
        100.0,
        106.0,  # LH below original ASH (110), updates ASH when sensitive
        100.0,
        100.0,
        107.0,  # two closes above 106 but below 110
        107.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=2, sensitive_down_reset=True)

    reset_dates = [m["date"] for m in markers if m["label"] == "R"]
    assert reset_dates
    assert reset_dates[0] == base + dt.timedelta(days=13)
