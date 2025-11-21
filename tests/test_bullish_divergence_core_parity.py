import pandas as pd

from analysis.regression_shared_utils import (
    apply_blackout_flags,
    preprocess_signals,
)
from analysis.same_day_aggregates import add_same_day_aggregate_features
from analysis.bullish_divergence_core_model import BullishDivergenceModel


def test_threshold_defaults_match_legacy():
    model = BullishDivergenceModel()
    assert model.success_thresholds == {2: 0.02, 5: 0.03, 10: 0.05, 20: 0.08}


def test_apply_blackout_flags_reproduces_legacy_columns():
    df = pd.DataFrame(
        {
            "ticker": ["A", "A", "B"],
            "date": ["2024-01-01", "2024-01-05", "2024-01-01"],
        }
    )
    blackout = pd.DataFrame(
        {
            "ticker": ["A"],
            "date": pd.to_datetime(["2024-01-02"]),
            "event": ["earnings"],
        }
    )
    result = apply_blackout_flags(df.copy(), blackout)
    expected_cols = {
        "has_blackout_data",
        "is_blackout_window",
        "exclude_from_regression",
        "is_blackout_t0",
    }
    assert expected_cols.issubset(set(result.columns))


def test_preprocess_signals_matches_expected_combo_counts():
    df = pd.DataFrame(
        {
            "ticker": ["A", "A", "A"],
            "date": ["2024-01-01"] * 3,
            "kynttila_koodi": [1, 2, 7],
            "vahvuus": [0.2, 0.6, 0.9],
            "is_divergence_today": [0, 0, 1],
        }
    )
    dedup = preprocess_signals(df)
    assert len(dedup) == 1
    row = dedup.iloc[0]
    assert row["num_candles_same_day"] == 2
    assert row["has_multi_candle_combo"] == 1
    assert row["has_bullish_divergence_same_day"] == 1
    enriched = add_same_day_aggregate_features(df, dedup, "kynttila_koodi")
    assert enriched.iloc[0]["num_signals_same_day"] == 3
    assert enriched.iloc[0]["has_same_day_reversal_cluster"] == 1
