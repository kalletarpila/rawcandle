import pandas as pd

from analysis.divergence_engine import compute_divergence_for_date, compute_divergence_series
from analysis.divergence_v1 import compute_bullish_candidate_strength


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
