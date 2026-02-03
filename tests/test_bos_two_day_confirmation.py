import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_bos_requires_two_consecutive_closes():
    base = dt.date(2024, 7, 1)
    values = [
        10.0,
        5.0,  # L
        12.0,  # H
        7.0,  # HL
        15.0,  # HH -> UP
        6.0,  # first close below active_structural_low (7)
        6.0,  # second consecutive close below -> RESET here
        8.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=1)

    reset_dates = [m["date"] for m in markers if m["label"] == "R"]
    assert len(reset_dates) == 1
    assert reset_dates[0] == base + dt.timedelta(days=6)
