import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_meaningless_high_pivot_filtered_spec_v1():
    base = dt.date(2024, 1, 1)
    values = [
        90.0,
        92.0,
        94.0,
        100.0,  # first high pivot
        95.0,
        93.0,
        91.0,
        92.0,
        94.0,
        100.005,  # second high pivot candidate (0.005% above 100.0)
        96.0,
        94.0,
        92.0,
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3, use_high_low=False)

    high_markers = [m for m in markers if m["label"] in ("H", "HH", "LH")]

    assert len(high_markers) == 1
    assert high_markers[0]["label"] == "H"
