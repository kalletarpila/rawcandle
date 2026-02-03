import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_reset_triggers_on_non_pivot_day():
    base = dt.date(2024, 5, 1)
    values = [
        10.0,
        5.0,  # L
        12.0,  # H
        7.0,  # HL (higher than 5)
        15.0,  # HH -> UP
        4.0,  # break below active_structural_low (7), not a pivot low
        4.0,  # confirmation
        8.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=1)

    break_date = base + dt.timedelta(days=6)
    reset_markers = [
        m for m in markers if m["label"] == "R" and m["date"] == break_date
    ]

    assert reset_markers


def test_downtrend_reset_uses_structural_high():
    base = dt.date(2024, 6, 1)
    values = [
        10.0,
        15.0,  # H
        9.0,  # L
        12.0,  # LH
        6.0,  # LL -> DOWN
        10.0,  # above structural low but below structural high (no reset)
        16.0,  # break above structural high
        16.0,  # confirmation
        14.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=1)

    reset_dates = [m["date"] for m in markers if m["label"] == "R"]
    expected_date = base + dt.timedelta(days=7)

    assert reset_dates
    assert reset_dates[0] == expected_date
