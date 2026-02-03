import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_trend_scoped_to_last_reset_epoch():
    base = dt.date(2024, 4, 1)
    values = [
        130,
        125,
        120,
        100,  # 3 L
        120,
        130,
        140,
        190,  # 7 H
        170,
        165,
        160,
        150,  # 11 HL
        165,
        170,
        175,
        210,  # 15 HH -> UP
        180,
        170,
        90,  # 18 break below active_structural_low
        90,  # 19 confirmation
        130,
        140,
        110,  # 22 HL after reset (higher than 90)
        120,
        130,
        140,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, summary = compute_dow_markers(series, window=3, use_high_low=False)

    assert any(m["label"] == "R" for m in markers)
    assert summary.startswith("NEUTRAL")
