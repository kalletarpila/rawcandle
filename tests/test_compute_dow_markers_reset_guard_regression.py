import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_reset_not_suppressed_on_trend_change_pivot():
    series = [
        {"date": dt.date(2024, 1, 1), "value": 100.0},
        {"date": dt.date(2024, 1, 2), "value": 95.0},  # L
        {"date": dt.date(2024, 1, 3), "value": 100.0},
        {"date": dt.date(2024, 1, 4), "value": 105.0},  # H
        {"date": dt.date(2024, 1, 5), "value": 100.0},
        {"date": dt.date(2024, 1, 6), "value": 98.0},  # HL
        {"date": dt.date(2024, 1, 7), "value": 105.0},
        {"date": dt.date(2024, 1, 8), "value": 110.0},  # HH -> trend becomes UP
        {"date": dt.date(2024, 1, 9), "value": 105.0},
        {
            "date": dt.date(2024, 1, 10),
            "value": 90.0,
        },  # first close below HL
        {"date": dt.date(2024, 1, 11), "value": 90.0},  # confirmation
        {"date": dt.date(2024, 1, 12), "value": 105.0},  # next H should be initial
        {"date": dt.date(2024, 1, 13), "value": 100.0},
    ]

    markers, _ = compute_dow_markers(series, window=1)

    next_high = [m for m in markers if m["date"] == dt.date(2024, 1, 12)]

    assert len(next_high) == 1
    assert next_high[0]["label"] == "H"
