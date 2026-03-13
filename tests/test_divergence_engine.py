import pandas as pd

from analysis.divergence_engine import compute_divergence_for_date, compute_divergence_series


def test_compute_divergence_for_date_returns_zero_without_min_history():
    dates = [f"2024-01-{day:02d}" for day in range(1, 21)]
    closes = [100.0 - day for day in range(20)]
    rsi_values = [None] * 14 + [40.0] * 6

    result = compute_divergence_for_date(dates, closes, rsi_values, 19)

    assert result["rsi"] == 40.0
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
