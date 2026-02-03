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
        {"date": dt.date(2024, 1, 11), "value": 95.0},
        {"date": dt.date(2024, 1, 12), "value": 100.0},
        {
            "date": dt.date(2024, 1, 13),
            "value": 105.0,
        },  # Should be 'H' (new initial high)
        {"date": dt.date(2024, 1, 14), "value": 100.0},
    ]

    markers, summary = compute_dow_markers(series, window=1)

    # Find the marker around 2024-01-13 (after regime break)
    high_after_break = [m for m in markers if m["date"] == dt.date(2024, 1, 13)]

    # Should be labeled 'H' (initial) not 'HH' or 'LH' because active_structural_high was reset
    assert len(high_after_break) == 1
    assert high_after_break[0]["label"] == "H"


def test_downtrend_regime_reset():
    """
    Test that active_structural_low resets when downtrend regime is broken.

    Scenario:
    - Build series that creates DOWN trend (LH + LL)
    - Add a pivot where close > active_structural_low (breaking upwards)
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
            "value": 100.0,
        },  # Breaks active_structural_low (90) upwards -> reset
        {"date": dt.date(2024, 1, 11), "value": 95.0},
        {"date": dt.date(2024, 1, 12), "value": 90.0},
        {
            "date": dt.date(2024, 1, 13),
            "value": 85.0,
        },  # Should be 'L' (new initial low)
        {"date": dt.date(2024, 1, 14), "value": 90.0},
    ]

    markers, summary = compute_dow_markers(series, window=1)

    # Find the marker around 2024-01-13 (after regime break)
    low_after_break = [m for m in markers if m["date"] == dt.date(2024, 1, 13)]

    # Should be labeled 'L' (initial) not 'HL' or 'LL' because active_structural_low was reset
    assert len(low_after_break) == 1
    assert low_after_break[0]["label"] == "L"
