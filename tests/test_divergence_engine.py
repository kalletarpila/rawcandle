import pandas as pd

from analysis.divergence_engine import compute_divergence_for_date, compute_divergence_series
from analysis.divergence_v1 import (
    compute_bullish_candidate_strength,
    compute_hidden_bearish_candidate_strength,
    compute_hidden_bullish_candidate_strength,
)


def test_compute_divergence_for_date_returns_zero_without_min_history():
    dates = [f"2024-01-{day:02d}" for day in range(1, 21)]
    closes = [100.0 - day for day in range(20)]
    rsi_values = [None] * 14 + [40.0] * 6

    result = compute_divergence_for_date(dates, closes, rsi_values, 19)

    assert result["rsi"] is None
    assert result["bullish_strength"] == 0.0
    assert result["bearish_strength"] == 0.0


def test_compute_divergence_for_date_detects_bullish_signal():
    dates = [f"2024-02-{day:02d}" for day in range(1, 36)]
    closes = [110.0] * 25 + [100.0] * 9 + [95.0]
    rsi_values = [50.0] * 25 + [20.0] * 9 + [35.0]

    result = compute_divergence_for_date(dates, closes, rsi_values, 34)

    assert result["bullish_strength"] > 0.0
    assert result["bearish_strength"] == 0.0


def test_compute_divergence_for_date_detects_bearish_signal():
    dates = [f"2024-03-{day:02d}" for day in range(1, 36)]
    closes = [90.0] * 25 + [100.0] * 9 + [105.0]
    rsi_values = [50.0] * 25 + [80.0] * 9 + [65.0]

    result = compute_divergence_for_date(dates, closes, rsi_values, 34)

    assert result["bearish_strength"] > 0.0
    assert result["bullish_strength"] == 0.0


def test_hidden_bullish_strength_positive():
    dates = [f"2024-03-{day:02d}" for day in range(1, 36)]
    closes = [110.0] * 25 + [95.0] * 9 + [100.0]
    rsi_values = [50.0] * 25 + [35.0] * 9 + [20.0]

    result = compute_divergence_for_date(dates, closes, rsi_values, 34)

    assert result["hidden_bullish_strength"] > 0.0
    assert result["bullish_strength"] == 0.0


def test_hidden_bearish_strength_positive():
    dates = [f"2024-04-{day:02d}" for day in range(1, 36)]
    closes = [95.0] * 25 + [110.0] * 9 + [105.0]
    rsi_values = [50.0] * 25 + [60.0] * 9 + [75.0]

    result = compute_divergence_for_date(dates, closes, rsi_values, 34)

    assert result["hidden_bearish_strength"] > 0.0
    assert result["bearish_strength"] == 0.0


def test_compute_divergence_series_returns_rows_for_each_date():
    df = pd.DataFrame(
        {
            "pvm": [f"2024-01-{day:02d}" for day in range(1, 41)],
            "close": [100.0 + day for day in range(40)],
        }
    )

    rows = compute_divergence_series(df)

    assert len(rows) == 40
    assert rows[0]["date"] == "2024-01-01"
    assert rows[-1]["date"] == "2024-01-40"


def test_compute_divergence_for_date_rejects_equality_cases():
    dates = [f"2024-04-{day:02d}" for day in range(1, 36)]
    closes = [120.0] * 25 + [100.0] * 9 + [100.0]
    rsi_values = [50.0] * 25 + [20.0] * 9 + [35.0]

    bullish_result = compute_divergence_for_date(dates, closes, rsi_values, 34)
    assert bullish_result["bullish_strength"] == 0.0

    closes = [90.0] * 25 + [100.0] * 9 + [105.0]
    rsi_values = [50.0] * 25 + [80.0] * 9 + [80.0]

    bearish_result = compute_divergence_for_date(dates, closes, rsi_values, 34)
    assert bearish_result["bearish_strength"] == 0.0


def test_compute_divergence_for_date_uses_max_over_valid_candidates():
    dates = [f"2024-05-{day:02d}" for day in range(1, 41)]
    closes = [120.0] * 20 + [100.0] + [119.0] * 8 + [98.0] + [118.0] * 9 + [90.0]
    rsi_values = [50.0] * 20 + [20.0] + [45.0] * 8 + [25.0] + [48.0] * 9 + [35.0]

    result = compute_divergence_for_date(dates, closes, rsi_values, 39)

    candidate_one = compute_bullish_candidate_strength(100.0, 90.0, 20.0, 35.0)
    candidate_two = compute_bullish_candidate_strength(98.0, 90.0, 25.0, 35.0)
    expected = max(candidate_one, candidate_two)

    assert result["bullish_strength"] == expected


def test_hidden_strength_formulas_match_expected_candidates():
    bullish = compute_hidden_bullish_candidate_strength(95.0, 100.0, 35.0, 20.0)
    bearish = compute_hidden_bearish_candidate_strength(110.0, 105.0, 60.0, 75.0)

    assert bullish > 0.0
    assert bearish > 0.0


def test_compute_divergence_series_sets_v2_bullish_event_on_confirmed_date(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-06-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 7.0, 6.0, 7.0, 8.0, 9.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, 20.0, 36.0, 37.0, 35.0, 32.0, 30.0, 33.0, 36.0, 38.0],
    )

    rows = compute_divergence_series(df)

    bullish_dates = [row["date"] for row in rows if row["is_bullish_divergence_r2"] == 1]

    assert bullish_dates == ["2024-06-10"]
    assert [row["date"] for row in rows if row["is_bullish_divergence"] == 1] == ["2024-06-10"]
    event_row = next(row for row in rows if row["is_bullish_divergence_r2"] == 1)
    assert event_row["pivot2_date_r2"] == "2024-06-08"
    assert event_row["pivot2_date_r3"] is None


def test_compute_divergence_series_sets_v2_bearish_event_on_confirmed_date(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-07-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [5.0] * 11,
            "high": [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 13.0, 14.0, 13.0, 12.0, 11.0],
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [60.0, 65.0, 80.0, 66.0, 64.0, 65.0, 70.0, 75.0, 72.0, 68.0, 66.0],
    )

    rows = compute_divergence_series(df)

    bearish_dates = [row["date"] for row in rows if row["is_bearish_divergence_r2"] == 1]

    assert bearish_dates == ["2024-07-10"]
    assert [row["date"] for row in rows if row["is_bearish_divergence"] == 1] == ["2024-07-10"]


def test_hidden_bullish_r2_event_flag(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-07-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, 25.0, 36.0, 37.0, 34.0, 30.0, 24.0, 20.0, 30.0, 32.0],
    )

    rows = compute_divergence_series(df)

    assert [row["date"] for row in rows if row["is_hidden_bullish_divergence_r2"] == 1] == [
        "2024-07-11"
    ]


def test_hidden_bearish_r2_event_flag(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-08-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [5.0] * 11,
            "high": [12.0, 13.0, 14.0, 13.0, 12.0, 11.0, 10.0, 11.0, 12.0, 11.0, 10.0],
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [60.0, 65.0, 75.0, 66.0, 64.0, 67.0, 70.0, 74.0, 80.0, 70.0, 68.0],
    )

    rows = compute_divergence_series(df)

    assert [row["date"] for row in rows if row["is_hidden_bearish_divergence_r2"] == 1] == [
        "2024-08-11"
    ]


def test_hidden_generic_flags_mirror_r2(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-09-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [8.0, 7.0, 6.0, 7.0, 8.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, 25.0, 36.0, 37.0, 34.0, 20.0, 24.0, 28.0, 30.0, 32.0],
    )

    rows = compute_divergence_series(df)

    for row in rows:
        assert row["is_hidden_bullish_divergence"] == row["is_hidden_bullish_divergence_r2"]
        assert row["is_hidden_bearish_divergence"] == row["is_hidden_bearish_divergence_r2"]


def test_compute_divergence_series_collapses_tied_price_pivot_clusters_to_last_row(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-08-{day:02d}" for day in range(1, 14)],
            "close": [100.0] * 13,
            "low": [12.0, 11.0, 10.0, 10.0, 10.0, 11.0, 12.0, 11.0, 9.0, 8.0, 9.0, 10.0, 11.0],
            "high": [20.0] * 13,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [42.0, 38.0, 20.0, 20.0, 20.0, 34.0, 35.0, 33.0, 31.0, 29.0, 32.0, 36.0, 37.0],
    )

    rows = compute_divergence_series(df)

    bullish_dates = [row["date"] for row in rows if row["is_bullish_divergence_r2"] == 1]

    assert bullish_dates == ["2024-08-12"]


def test_compute_divergence_series_accepts_rsi_pivot_at_p2_minus_1(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-09-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 8.0, 7.0, 8.0, 9.0, 10.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 36.0, 30.0, 35.0, 36.0, 34.0, 31.0, 34.0, 35.0, 38.0, 39.0],
    )

    rows = compute_divergence_series(df)

    bullish_dates = [row["date"] for row in rows if row["is_bullish_divergence_r2"] == 1]

    assert bullish_dates == ["2024-09-09"]


def test_compute_divergence_series_rejects_rsi_pivot_outside_locality_window(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-10-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 8.0, 7.0, 8.0, 9.0, 10.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, 30.0, 36.0, 37.0, 38.0, 37.0, 35.0, 34.0, 31.0, 39.0],
    )

    rows = compute_divergence_series(df)

    assert all(row["is_bullish_divergence_r2"] == 0 for row in rows)


def test_compute_divergence_series_uses_only_consecutive_price_pivots(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-11-{day:02d}" for day in range(1, 18)],
            "close": [100.0] * 17,
            "low": [12.0, 11.0, 10.0, 11.0, 12.0, 11.0, 11.0, 9.0, 10.0, 11.0, 10.0, 10.0, 8.0, 9.0, 10.0, 11.0, 12.0],
            "high": [20.0] * 17,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [45.0, 40.0, 20.0, 41.0, 42.0, 50.0, 49.0, 19.0, 45.0, 44.0, 43.0, 42.0, 18.0, 31.0, 32.0, 34.0, 36.0],
    )

    rows = compute_divergence_series(df)

    assert all(row["is_bullish_divergence_r2"] == 0 for row in rows)


def test_compute_divergence_series_rejects_missing_rsi_anchor(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2024-12-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 7.0, 6.0, 7.0, 8.0, 9.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, None, 36.0, 37.0, 35.0, 32.0, 30.0, 33.0, 36.0, 38.0],
    )

    rows = compute_divergence_series(df)

    assert all(row["is_bullish_divergence_r2"] == 0 for row in rows)


def test_compute_divergence_series_does_not_mark_boundary_rows_as_pivots(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-01-{day:02d}" for day in range(1, 9)],
            "close": [100.0] * 8,
            "low": [5.0, 4.0, 6.0, 7.0, 8.0, 7.0, 6.0, 3.0],
            "high": [20.0] * 8,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 30.0, 35.0, 36.0, 37.0, 38.0, 39.0, 25.0],
    )

    rows = compute_divergence_series(df)

    assert all(row["is_bullish_divergence_r2"] == 0 for row in rows)


def test_compute_divergence_series_keeps_event_flag_binary_on_collision(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-02-{day:02d}" for day in range(1, 16)],
            "close": [100.0] * 15,
            "low": [12.0, 11.0, 10.0, 11.0, 12.0, 11.0, 9.0, 8.0, 9.0, 11.0, 8.0, 9.0, 10.0, 11.0, 12.0],
            "high": [20.0] * 15,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [45.0, 40.0, 20.0, 41.0, 42.0, 39.0, 30.0, 25.0, 31.0, 35.0, 26.0, 32.0, 36.0, 37.0, 38.0],
    )

    rows = compute_divergence_series(df)

    flagged_rows = [row for row in rows if row["is_bullish_divergence_r2"] == 1]

    assert len(flagged_rows) == 1
    assert flagged_rows[0]["date"] == "2025-02-10"


def test_compute_divergence_series_sets_v2_bullish_event_for_radius_3(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-03-{day:02d}" for day in range(1, 16)],
            "close": [100.0] * 15,
            "low": [15.0, 14.0, 13.0, 12.0, 11.0, 10.0, 11.0, 12.0, 11.0, 9.0, 8.0, 9.0, 10.0, 11.0, 12.0],
            "high": [20.0] * 15,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [50.0, 45.0, 40.0, 35.0, 20.0, 15.0, 18.0, 25.0, 28.0, 30.0, 24.0, 35.0, 38.0, 40.0, 42.0],
    )

    rows = compute_divergence_series(df)

    bullish_dates_r3 = [row["date"] for row in rows if row["is_bullish_divergence_r3"] == 1]

    assert bullish_dates_r3 == ["2025-03-14"]
    event_row = next(row for row in rows if row["is_bullish_divergence_r3"] == 1)
    assert event_row["pivot2_date_r3"] == "2025-03-11"
    assert event_row["pivot2_date_r2"] is None


def test_compute_divergence_series_keeps_r2_and_r3_separate(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-04-{day:02d}" for day in range(1, 15)],
            "close": [100.0] * 14,
            "low": [12.0, 11.0, 10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 7.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "high": [20.0] * 14,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [45.0, 40.0, 35.0, 30.0, 20.0, 31.0, 32.0, 30.0, 29.0, 34.0, 35.0, 36.0, 37.0, 38.0],
    )

    rows = compute_divergence_series(df)

    assert [row["date"] for row in rows if row["is_bullish_divergence_r2"] == 1] == ["2025-04-11"]
    assert [row["date"] for row in rows if row["is_bullish_divergence_r3"] == 1] == ["2025-04-12"]


def test_compute_divergence_series_rejects_v2_pair_with_gap_4(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-05-{day:02d}" for day in range(1, 11)],
            "close": [100.0] * 10,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 8.0, 7.0, 8.0, 9.0, 10.0],
            "high": [20.0] * 10,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 36.0, 30.0, 35.0, 36.0, 31.0, 34.0, 35.0, 38.0, 39.0],
    )

    rows = compute_divergence_series(df)

    assert all(row["is_bullish_divergence_r2"] == 0 for row in rows)


def test_compute_divergence_series_accepts_v2_pair_with_gap_24(monkeypatch):
    lows = [20.0, 19.0, 18.0, 19.0, 20.0] + list(range(21, 42)) + [17.0, 18.0, 19.0, 20.0]
    df = pd.DataFrame(
        {
            "pvm": [f"2025-06-{day:02d}" for day in range(1, 31)],
            "close": [100.0] * 30,
            "low": lows,
            "high": [30.0] * 30,
        }
    )
    rsi = [50.0] * 30
    rsi[2] = 20.0
    rsi[26] = 30.0
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: rsi,
    )

    rows = compute_divergence_series(df)

    assert [row["date"] for row in rows if row["is_bullish_divergence_r2"] == 1] == ["2025-06-29"]


def test_compute_divergence_series_accepts_v2_pair_with_gap_25(monkeypatch):
    lows = [20.0, 19.0, 18.0, 19.0, 20.0] + list(range(21, 43)) + [17.0, 18.0, 19.0, 20.0]
    df = pd.DataFrame(
        {
            "pvm": [f"2025-07-{day:02d}" for day in range(1, 32)],
            "close": [100.0] * 31,
            "low": lows,
            "high": [30.0] * 31,
        }
    )
    rsi = [50.0] * 31
    rsi[2] = 20.0
    rsi[27] = 30.0
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: rsi,
    )

    rows = compute_divergence_series(df)

    event_rows = [row for row in rows if row["is_bullish_divergence_r2"] == 1]
    assert len(event_rows) == 1
    assert event_rows[0]["pivot_gap_r2"] == 25


def test_compute_divergence_series_persists_bullish_geometry(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-08-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 7.0, 6.0, 7.0, 8.0, 9.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, 20.0, 36.0, 37.0, 35.0, 32.0, 30.0, 33.0, 36.0, 38.0],
    )

    rows = compute_divergence_series(df)
    event_row = next(row for row in rows if row["is_bullish_divergence_r2"] == 1)

    assert event_row["pivot_gap"] == 5
    assert event_row["pivot_drop_pct"] == 25.0
    assert event_row["pivot_gap_r2"] == 5
    assert event_row["pivot_drop_pct_r2"] == 25.0
    assert event_row["pivot2_date_r2"] == "2025-08-08"
    assert event_row["pivot_gap_r3"] is None
    assert event_row["pivot_drop_pct_r3"] is None
    assert event_row["pivot2_date_r3"] is None


def test_compute_divergence_series_persists_bearish_geometry(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-09-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [5.0] * 11,
            "high": [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 13.0, 14.0, 13.0, 12.0, 11.0],
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [60.0, 65.0, 80.0, 66.0, 64.0, 65.0, 70.0, 75.0, 72.0, 68.0, 66.0],
    )

    rows = compute_divergence_series(df)
    event_row = next(row for row in rows if row["is_bearish_divergence_r2"] == 1)

    assert event_row["pivot_gap"] == 5
    assert event_row["pivot_drop_pct"] == 16.666666666666664
    assert event_row["pivot_gap_r2"] == 5
    assert event_row["pivot_drop_pct_r2"] == 16.666666666666664
    assert event_row["pivot2_date_r2"] == "2025-09-08"
    assert event_row["pivot_gap_r3"] is None
    assert event_row["pivot_drop_pct_r3"] is None
    assert event_row["pivot2_date_r3"] is None


def test_compute_divergence_series_keeps_geometry_null_for_non_event_rows(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-10-{day:02d}" for day in range(1, 12)],
            "close": [100.0] * 11,
            "low": [10.0, 9.0, 8.0, 9.0, 10.0, 9.0, 8.0, 7.0, 8.0, 9.0, 10.0],
            "high": [20.0] * 11,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0, 35.0, 30.0, 36.0, 37.0, 38.0, 37.0, 35.0, 34.0, 31.0, 39.0],
    )

    rows = compute_divergence_series(df)

    assert all(row["pivot_gap"] is None for row in rows)
    assert all(row["pivot_drop_pct"] is None for row in rows)
    assert all(row["pivot_gap_r2"] is None for row in rows)
    assert all(row["pivot_drop_pct_r2"] is None for row in rows)
    assert all(row["pivot2_date_r2"] is None for row in rows)
    assert all(row["pivot_gap_r3"] is None for row in rows)
    assert all(row["pivot_drop_pct_r3"] is None for row in rows)
    assert all(row["pivot2_date_r3"] is None for row in rows)


def test_compute_divergence_series_keeps_r2_and_r3_geometry_and_pivot2_dates_separate_on_same_row(monkeypatch):
    df = pd.DataFrame(
        {
            "pvm": [f"2025-11-{day:02d}" for day in range(1, 8)],
            "close": [100.0] * 7,
            "low": [10.0] * 7,
            "high": [20.0] * 7,
        }
    )
    monkeypatch.setattr(
        "analysis.divergence_engine.compute_rsi_wilder",
        lambda closes, period=14: [40.0] * 7,
    )

    def fake_flags(dates, lows, highs, rsi_values, *, radius):
        if radius == 2:
            return (
                [0, 0, 0, 0, 0, 1, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
                [None, None, None, None, None, 5, None],
                [None, None, None, None, None, 25.0, None],
                [None, None, None, None, None, "2025-11-04", None],
            )
        return (
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [None, None, None, None, None, 8, None],
            [None, None, None, None, None, 12.5, None],
            [None, None, None, None, None, "2025-11-03", None],
        )

    monkeypatch.setattr(
        "analysis.divergence_engine._compute_v2_event_flags_for_radius",
        fake_flags,
    )

    rows = compute_divergence_series(df)
    event_row = next(row for row in rows if row["date"] == "2025-11-06")

    assert event_row["is_bullish_divergence_r2"] == 1
    assert event_row["is_bullish_divergence_r3"] == 1
    assert event_row["pivot_gap_r2"] == 5
    assert event_row["pivot_drop_pct_r2"] == 25.0
    assert event_row["pivot2_date_r2"] == "2025-11-04"
    assert event_row["pivot_gap_r3"] == 8
    assert event_row["pivot_drop_pct_r3"] == 12.5
    assert event_row["pivot2_date_r3"] == "2025-11-03"
