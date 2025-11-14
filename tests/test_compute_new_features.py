import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from compute_new_features import (
    compute_gap_body_shadow,
    compute_index_volatility_from_history,
    compute_price_acceleration,
    compute_price_slope,
    compute_reversal_context,
    compute_rsi_slope,
    compute_volume_impulse,
    compute_volatility_ratio,
    compute_bull_divergence_features,
    ensure_columns,
    update_features,
)


def test_compute_rsi_slope_uses_historical_values():
    dates = pd.date_range("2024-01-01", periods=6, freq="B")
    df_results = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "date": [dates[-1], dates[-1]],
            "RSI14_t0": [65.0, 45.0],
        }
    )
    df_div = pd.DataFrame(
        {
            "ticker": ["AAA"] * 6 + ["BBB"] * 6,
            "date": list(dates) * 2,
            "rsi": [40, 45, 50, 55, 60, 65, 20, 25, 30, 35, 40, 45],
        }
    )

    slopes = compute_rsi_slope(df_results, df_div)

    assert slopes.tolist() == [25.0, 25.0]


def test_compute_price_slope_and_acceleration():
    df = pd.DataFrame({"t_5": [95.0], "t_10": [90.0]})

    slope5 = compute_price_slope(df, "t_5", 5)
    slope10 = compute_price_slope(df, "t_10", 10)
    df["Price_slope_5"] = slope5
    df["Price_slope_10"] = slope10
    accel = compute_price_acceleration(df)

    assert float(slope5.iloc[0]) == 1.0
    assert float(slope10.iloc[0]) == 1.0
    assert float(accel.iloc[0]) == 0.0


def test_compute_volatility_ratio_handles_zero_denominator():
    df = pd.DataFrame({"t_10_hajonta": [2.0, 1.0], "t_20_hajonta": [4.0, 0.0]})

    ratio = compute_volatility_ratio(df)

    assert ratio.iloc[0] == 0.5
    assert np.isnan(ratio.iloc[1])


def test_compute_gap_body_shadow_creates_expected_columns():
    df = pd.DataFrame(
        {
            "open_raw": [10.0],
            "close_raw": [12.0],
            "low_raw": [9.0],
            "high_raw": [13.0],
            "prev_close_raw": [11.0],
        }
    )

    compute_gap_body_shadow(df)

    eps = 1e-6
    base_gap = (10.0 - 11.0) / (11.0 + eps)
    expected_gap = np.log1p(abs(base_gap)) * np.sign(base_gap)
    assert np.isclose(df.loc[0, "Gap_down_strength"], expected_gap)
    assert np.isclose(df.loc[0, "Body_ratio"], abs(12 - 10) / (13 - 9))
    upper = 13 - max(10, 12)
    lower = min(10, 12) - 9
    expected_shadow = np.log1p(lower / (upper + 1e-6))
    assert np.isclose(df.loc[0, "Shadow_ratio"], expected_shadow)


def test_compute_index_volatility_from_history_matches_rolling_std():
    dates = pd.date_range("2024-01-01", periods=15, freq="B")
    history = pd.DataFrame(
        {
            "ticker": ["^GSPC"] * len(dates),
            "date": dates,
            "close": np.linspace(100, 114, len(dates)),
        }
    )
    df_results = pd.DataFrame({"date": dates})

    vol = compute_index_volatility_from_history(df_results, history, "SPX_volatility_10")

    expected = history["close"].shift(1).rolling(window=10, min_periods=10).std(ddof=0).tolist()
    assert np.allclose(vol.values, expected, equal_nan=True)


def test_compute_volume_impulse_and_reversal_context():
    df = pd.DataFrame(
        {
            "volume_raw": [200.0],
            "prev10_avg_volume": [100.0],
            "t_10": [92.0],
            "BullDiv_recent_strength": [2.0],
            "t_10_hajonta": [1.5],
        }
    )

    impulse = compute_volume_impulse(df)
    context = compute_reversal_context(df)

    assert impulse.iloc[0] == 2.0
    expected_score = 0.4 * (100 - 92) + 0.4 * 2.0 - 0.2 * 1.5
    assert np.isclose(context.iloc[0], expected_score)


def test_compute_bull_divergence_features_defaults():
    df_results = pd.DataFrame(
        {"ticker": ["AAA"], "date": pd.to_datetime(["2024-01-05"])}
    )
    df_div = pd.DataFrame()
    updated = compute_bull_divergence_features(df_results.copy(), df_div)
    assert updated["BullDiv_strength"].iloc[0] == 0.0
    assert updated["BullDiv_recent_strength"].iloc[0] == 0.0
    assert updated["BullDiv_recent_offset"].iloc[0] == -1
    assert updated["Has_BullDiv_recent"].iloc[0] == 0


def test_compute_bull_divergence_features_from_history():
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    df_results = pd.DataFrame(
        {
            "ticker": ["AAA"] * 3,
            "date": dates[1:4],
        }
    )
    df_div = pd.DataFrame(
        {
            "ticker": ["AAA"] * len(dates),
            "date": dates,
            "bullish_strength": [0.0, 1.5, 0.0, 0.8, 0.0],
        }
    )

    updated = compute_bull_divergence_features(df_results.copy(), df_div)

    strengths = updated["BullDiv_strength"].tolist()
    recent_strengths = updated["BullDiv_recent_strength"].tolist()
    offsets = updated["BullDiv_recent_offset"].tolist()
    flags = updated["Has_BullDiv_recent"].tolist()

    assert strengths == [1.5, 0.0, 0.8]
    assert recent_strengths[0] == 1.5
    assert recent_strengths[1] == 1.5
    assert recent_strengths[2] == 1.5
    assert offsets == [0, 1, 0]
    assert flags == [1, 1, 1]


def test_ensure_columns_and_update_features(tmp_path):
    db_path = Path(tmp_path) / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE results_data (id INTEGER PRIMARY KEY, existing REAL)")

    ensure_columns(conn, {"RSI_slope_5": "REAL", "existing": "REAL"})

    columns = [row[1] for row in conn.execute("PRAGMA table_info(results_data)")]
    assert "RSI_slope_5" in columns

    conn.executemany(
        "INSERT INTO results_data (id, RSI_slope_5) VALUES (?, ?)",
        [(1, 0.0), (2, 0.0)],
    )
    df = pd.DataFrame({"id": [1, 2], "RSI_slope_5": [0.15, 0.25]})

    update_features(conn, df, ["RSI_slope_5"])

    values = conn.execute("SELECT RSI_slope_5 FROM results_data ORDER BY id").fetchall()
    assert values == [(0.15,), (0.25,)]
    conn.close()
