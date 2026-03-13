import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_guardrail_flips_low_above_structural_high():
    base = dt.date(2024, 2, 1)
    values = [
        10.0,
        5.0,  # L
        15.0,  # H
        12.0,
        20.0,
        20.0,
        18.0,  # low pivot above last structural high (15)
        22.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=1)

    target_date = base + dt.timedelta(days=6)
    target_markers = [m for m in markers if m["date"] == target_date]

    assert len(target_markers) == 1
    assert target_markers[0]["label"] not in {"HL", "LL"}
    assert target_markers[0]["label"] in {"H", "HH"}
