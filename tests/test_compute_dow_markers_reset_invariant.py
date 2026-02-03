# test_compute_dow_markers_reset_invariant.py
import datetime as dt

from pages.index_page.index_utils import compute_dow_markers


def test_reset_does_not_reuse_old_structure_window_3():
    """
    Structural invariant test with window=3.

    Plan:
    - Pre-reset UP regime: L -> H -> HL -> HH
    - Reset via close < active_structural_low
    - Post-reset: first pivot-high must be "H" even if it exceeds old HH
    - After a new HL forms, a later pivot-high can be "HH"
    """
    base = dt.date(2024, 4, 1)
    values = [
        140,
        135,
        130,  # 0-2 (before L)
        120,  # 3 L
        130,
        140,
        150,  # 4-6 (after L)
        200,  # 7 H
        180,
        170,
        160,  # 8-10 (after H)
        150,  # 11 HL
        165,
        175,
        185,  # 12-14 (after HL)
        210,  # 15 HH -> UP
        190,
        180,
        170,  # 16-18 (after HH)
        100,  # 19 reset break (below active_structural_low)
        100,  # 20 confirmation
        140,
        150,  # 20-22 (after break)
        220,  # 23 first post-reset H (exceeds old HH)
        200,
        190,
        180,  # 24-26 (after H)
        140,  # 27 new HL
        160,
        170,
        180,  # 28-30 (after HL)
        230,  # 31 new HH
        210,
        200,
        190,  # 32-34 (after HH)
    ]
    series = [
        {"date": base + dt.timedelta(days=i), "value": v} for i, v in enumerate(values)
    ]

    markers, _ = compute_dow_markers(series, window=3)

    first_high_date = base + dt.timedelta(days=23)
    second_high_date = base + dt.timedelta(days=31)

    first_high = [m for m in markers if m["date"] == first_high_date]
    second_high = [m for m in markers if m["date"] == second_high_date]

    assert len(first_high) == 1
    assert first_high[0]["label"] == "H"

    assert len(second_high) == 1
    assert second_high[0]["label"] == "HH"
