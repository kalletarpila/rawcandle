import pandas as pd
import numpy as np
import pytest

from analysis.combo_features import (
    CANDLE_PATTERN_TO_SLUG,
    COMBO_FEATURE_COLUMNS,
)
from regression import run_regression as rr


def _sample_dataframe(rows: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    pattern_codes = [0, 1, 2, 3, 4, 5, 6, 7]
    markets = ["usa", "suomi"]
    crisis_start = pd.Timestamp(rr.CRISIS_START)
    crisis_end = pd.Timestamp(rr.CRISIS_END)
    records = []
    for i in range(rows):
        shift = rng.normal(0, 2)
        base_date = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
        if i % 9 == 0:
            base_date = pd.Timestamp("2025-03-01") + pd.Timedelta(days=i % 40)
        is_crisis = int(crisis_start <= base_date <= crisis_end)
        bull_offset_choice = int(rng.integers(-1, 6))
        bull_offset_recent = bull_offset_choice if bull_offset_choice >= 0 else -1
        bull_offset_value = bull_offset_recent if bull_offset_recent >= 0 else 99
        bull_last_1d = int(bull_offset_value == 0)
        bull_last_2d = int(bull_offset_value in {0, 1})
        bull_last_3d = int(bull_offset_value in {0, 1, 2})
        bull_last_3d_any = bull_last_3d
        pattern_code = pattern_codes[i % len(pattern_codes)]
        pattern_label = rr.PATTERN_LABELS.get(pattern_code, "")
        slug = CANDLE_PATTERN_TO_SLUG.get(pattern_label)
        candles = []
        if pattern_code in {1, 2, 3, 4, 5, 6}:
            candles.append(pattern_code)
        extra = int(rng.integers(0, 2))
        for _ in range(extra):
            candles.append(int(rng.integers(1, 7)))
        combo_features = {col: 0 for col in COMBO_FEATURE_COLUMNS}
        if slug:
            base_name = f"is_{slug}"
            combo_features[f"{base_name}_only_t0"] = int(bull_offset_recent == -1)
            combo_features[f"{base_name}_and_BullDiv_t0"] = int(
                bull_offset_recent == 0
            )
            combo_features[f"{base_name}_and_BullDiv_recent_2d"] = int(
                bull_offset_recent != -1 and bull_offset_recent <= 2
            )
            combo_features[f"{base_name}_and_BullDiv_recent_3d"] = int(
                bull_offset_recent != -1 and bull_offset_recent <= 3
            )
            combo_features[f"{base_name}_and_BullDiv_recent_5d"] = int(
                bull_offset_recent != -1 and bull_offset_recent <= 5
            )
        has_bull_div_same_day = int(bull_offset_recent == 0 or pattern_code == 7)
        if not candles and not has_bull_div_same_day:
            combo_code = 0
        elif len(candles) == 1 and not has_bull_div_same_day:
            combo_code = 1
        elif len(candles) >= 2 and not has_bull_div_same_day:
            combo_code = 2
        elif not candles and has_bull_div_same_day:
            combo_code = 4
        else:
            combo_code = 3

        records.append(
            {
                "t2": 100 + rng.normal(1 + shift, 3),
                "t5": 100 + rng.normal(2 + (-1) ** i * 4, 4),
                "t10": 100 + rng.normal(4 + shift, 5),
                "t20": 100 + rng.normal(6 + (-1) ** i * 5, 6),
                "vahvuus": float(np.clip(rng.normal(0.5, 0.2), 0, 1)),
                "RSI14_t0": float(np.clip(rng.normal(50, 15), 0, 100)),
                "t0_volyymi": float(np.clip(rng.normal(120, 30), 10, 400)),
                "t0_close_norm": float(100 + rng.normal(5, 10)),
                "is_divergence_today": int(rng.integers(0, 2)),
                "recent_divergence_min_distance": int(rng.integers(1, 6)),
                "recent_divergence_decay_strength": float(
                    np.clip(rng.normal(0.4, 0.1), 0, 2)
                ),
                "rolling_BullDiv_influence": float(
                    np.clip(rng.normal(0.5, 0.3), 0, 3)
                ),
                "t_10_hajonta": float(abs(rng.normal(5, 2))),
                "t_20_hajonta": float(abs(rng.normal(8, 3))),
                "t_10": 100 + rng.normal(-2, 3),
                "t_20": 100 + rng.normal(-4, 4),
                "t0_50p_liukuva": 100 + rng.normal(-1, 2),
                "t0_200p_liukuva": 100 + rng.normal(-2, 2.5),
                "RSI_slope_5": float(rng.normal(0, 5)),
                "Price_slope_5": float(rng.normal(-0.5, 1)),
                "Price_slope_10": float(rng.normal(-0.3, 1)),
                "Price_acceleration_5_10": float(rng.normal(0, 0.5)),
                "Volatility_ratio_10_20": float(np.clip(rng.normal(0.8, 0.2), 0.1, 2.0)),
                "Gap_down_strength": float(rng.normal(-0.01, 0.05)),
                "Body_ratio": float(np.clip(rng.normal(0.4, 0.2), 0, 1)),
                "Shadow_ratio": float(np.clip(rng.normal(0.1, 0.3), -1, 3)),
                "Volume_impulse": float(np.clip(rng.normal(1.2, 0.5), 0.1, 5)),
                "Reversal_Context_Score": float(rng.normal(5, 2)),
                "is_crisis": is_crisis,
                "bullDiv_offset": bull_offset_value,
                "bullDiv_last_1d": bull_last_1d,
                "bullDiv_last_2d": bull_last_2d,
                "bullDiv_last_3d": bull_last_3d,
                "bullDiv_last_3d_any": bull_last_3d_any,
                "num_candles_same_day": len(candles),
                "has_multi_candle_combo": int(len(candles) >= 2),
                "has_bullish_divergence_same_day": has_bull_div_same_day,
                "signal_combo_code": combo_code,
                "SPX_10": 100 + rng.normal(0, 1),
                "SPX_20": 100 + rng.normal(0, 1.2),
                "SPX_volatility_10": float(abs(rng.normal(1.5, 0.3))),
                "NDX_10": 100 + rng.normal(0, 1.5),
                "NDX_20": 100 + rng.normal(0, 1.7),
                "NDX_volatility_10": float(abs(rng.normal(1.8, 0.4))),
                "BullDiv_strength": float(np.clip(rng.normal(1.0, 0.5), 0, 3)),
                "BullDiv_recent_strength": float(np.clip(rng.normal(1.2, 0.6), 0, 3)),
                "BullDiv_recent_offset": int(rng.integers(-1, 4)),
                "Has_BullDiv_recent": int(rng.integers(0, 2)),
                "has_blackout_data": int(rng.integers(0, 2)),
                "date": base_date,
                "ticker": f"TICK{i:03d}",
                "kynttila_koodi": pattern_code,
                "market": markets[i % len(markets)],
            }
        )
        records[-1].update(combo_features)
    return pd.DataFrame.from_records(records)


def test_add_return_labels_produces_expected_columns():
    df = _sample_dataframe(10)
    df = rr.add_return_labels(df.copy())
    for col in ("y2", "y5", "y10", "y20", "success2", "success5", "success10", "success20"):
        assert col in df.columns
    assert df["y5"].between(-1, 5).all()
    assert set(df["success5"].unique()).issubset({0, 1})


def test_feature_selection_preferences_roundtrip(tmp_path, monkeypatch):
    temp_store = tmp_path / "selection.json"
    monkeypatch.setattr(rr, "FEATURE_SELECTION_STORE", temp_store)
    rr.save_feature_selection_preferences(["feat_a", "feat_b"])
    assert temp_store.exists()
    loaded = rr.load_feature_selection_preferences()
    assert loaded == ["feat_a", "feat_b"]


def test_add_crisis_flag_marks_window():
    dates = [
        pd.Timestamp("2025-03-15"),
        pd.Timestamp("2025-05-10"),
    ]
    df = pd.DataFrame({"date": dates})
    flagged = rr.add_crisis_flag(df.copy())
    assert flagged.loc[0, "is_crisis"] == 1
    assert flagged.loc[1, "is_crisis"] == 0


def test_compute_crisis_success_stats_counts_groups():
    df = pd.DataFrame(
        {
            "is_crisis": [1, 1, 0, 0],
            "success2": [1, 0, 1, 0],
            "success5": [0, 0, 1, 1],
            "success10": [1, 1, 0, 0],
            "success20": [0, 1, 0, 1],
        }
    )
    stats_info = rr.compute_crisis_success_stats(
        df, ["success2", "success5", "success10", "success20"]
    )
    assert stats_info["has_column"] is True
    data = stats_info["stats"]
    assert data["success2"]["crisis_rate"] == pytest.approx(0.5)
    assert data["success5"]["normal_rate"] == pytest.approx(1.0)
    assert data["success10"]["crisis_n"] == 2
    assert data["success20"]["normal_n"] == 2


def test_compute_crisis_success_stats_handles_exclusion():
    df = pd.DataFrame({"success2": [1, 0], "is_crisis": [1, 0]})
    stats_info = rr.compute_crisis_success_stats(
        df, ["success2"], exclude_crisis_period=True
    )
    assert stats_info["excluded"] is True
    assert stats_info["stats"] == {}


def test_build_feature_matrix_creates_dummies_and_is_candle_flag():
    df = rr.add_return_labels(_sample_dataframe(8))
    X, continuous_cols, dummy_cols = rr.build_feature_matrix(df)
    assert "is_candle_day" in X.columns
    pattern_cols = [col for col in X.columns if col.startswith("kynttila_koodi_")]
    market_cols = [col for col in X.columns if col.startswith("market_")]
    assert pattern_cols, "Pattern-ohjaimia ei syntynyt"
    assert market_cols, "Markkina-ohjaimia ei syntynyt"


def test_build_feature_matrix_respects_custom_feature_columns():
    df = rr.add_return_labels(_sample_dataframe(8))
    custom_features = rr.FEATURE_COLUMNS[:5]
    X, continuous_cols, dummy_cols = rr.build_feature_matrix(
        df, feature_columns=custom_features
    )
    assert continuous_cols == custom_features
    base_cols = set(rr.FEATURE_COLUMNS)
    returned_base_cols = set(col for col in X.columns if col in base_cols)
    assert returned_base_cols == set(custom_features)
    assert dummy_cols, "Dummy-sarakkeita pitäisi syntyä edelleen"


def test_build_feature_matrix_can_exclude_is_candle_day_dummy():
    df = rr.add_return_labels(_sample_dataframe(8))
    X, continuous_cols, dummy_cols = rr.build_feature_matrix(
        df,
        feature_columns=rr.FEATURE_COLUMNS[:3],
        include_is_candle_day=False,
    )
    assert "is_candle_day" not in X.columns
    assert all(not col.startswith("is_candle_day") for col in dummy_cols)


def test_run_logistic_regression_returns_metrics():
    df = rr.add_return_labels(_sample_dataframe(60))
    X, continuous_cols, dummy_cols = rr.build_feature_matrix(df)
    y = df["success5"]
    result = rr.run_logistic_regression(X, y, continuous_cols)
    assert 0.0 <= result["auc"] <= 1.0
    assert "precision" in result["classification_report"]
    assert not result["top_positive"].empty
    assert not result["top_negative"].empty


def test_run_linear_regression_returns_summary():
    df = rr.add_return_labels(_sample_dataframe(40))
    X, continuous_cols, dummy_cols = rr.build_feature_matrix(df)
    summary = rr.run_linear_regression(X, df["y5"], continuous_cols)["summary"]
    assert "OLS Regression Results" in summary


def test_run_regression_for_market_uses_loader(monkeypatch):
    sample_df = _sample_dataframe(50)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    monkeypatch.setattr(rr, "load_blackout_dates", lambda *_, **__: pd.DataFrame())
    monkeypatch.setattr(rr, "load_divergence_data", lambda *_, **__: pd.DataFrame())
    result = rr.run_regression_for_market(market="usa")
    assert result["row_count"] == len(sample_df)
    horizons = result["horizons"]
    assert 5 in horizons
    assert 0 <= horizons[5]["logistic"]["auc"] <= 1
    crisis_stats = horizons[5]["crisis_stats"]["stats"]
    assert "success5" in crisis_stats
    assert crisis_stats["success5"]["crisis_n"] >= 0
    assert crisis_stats["success5"]["normal_n"] >= 0
    assert "Kriisijakso poistettu analyyseista" in result["report"]


def test_run_regression_includes_downtrend_control(monkeypatch):
    sample_df = _sample_dataframe(60)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    result = rr.run_regression_for_market(success_horizons=[2])
    assert result["row_count"] == len(sample_df)
    assert result["pattern_code"] is None
    assert result["pattern_label"] == "Kaikki kynttilät (sis. downtrend)"
    assert result["success_horizons"] == [2]


def test_run_regression_pattern_filter_includes_downtrend(monkeypatch):
    sample_df = _sample_dataframe(80)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    target_code = 3
    expected = len(sample_df[sample_df["kynttila_koodi"] == target_code]) + len(
        sample_df[sample_df["kynttila_koodi"] == 0]
    )
    result = rr.run_regression_for_market(pattern_code=target_code, success_horizons=[2])
    assert result["pattern_code"] == target_code
    assert "downtrend" in result["pattern_label"]
    assert result["horizons"][2]["row_count"] == expected


def test_run_regression_respects_custom_thresholds(monkeypatch):
    sample_df = _sample_dataframe(40)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    thresholds = {2: 0.01, 5: 0.02, 10: 0.03, 20: 0.04}
    result = rr.run_regression_for_market(
        market="suomi", success_thresholds=thresholds
    )
    for horizon, value in thresholds.items():
        assert pytest.approx(result["success_thresholds"][horizon], rel=1e-6) == value
    assert result["success_horizons"] == [5]
    assert 5 in result["horizons"]


def test_run_regression_for_market_passes_feature_columns(monkeypatch):
    sample_df = _sample_dataframe(60)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    monkeypatch.setattr(rr, "load_blackout_dates", lambda *_, **__: pd.DataFrame())
    recorded_feature_args = []
    original_build = rr.build_feature_matrix

    def wrapped_build(
        df,
        feature_columns=None,
        include_is_candle_day=True,
        categorical_columns=None,
    ):
        recorded_feature_args.append(
            {
                "features": tuple(feature_columns or ()),
                "include_is_candle_day": include_is_candle_day,
                "categorical_columns": tuple(sorted(categorical_columns or [])),
            }
        )
        return original_build(
            df,
            feature_columns=feature_columns,
            include_is_candle_day=include_is_candle_day,
            categorical_columns=categorical_columns,
        )

    monkeypatch.setattr(rr, "build_feature_matrix", wrapped_build)
    selected_features = (
        rr.FEATURE_COLUMNS[:4]
        + ["is_candle_day", rr.PATTERN_COLUMN, rr.FEATURE_SELECTION_MARKER]
    )
    result = rr.run_regression_for_market(
        market="usa",
        success_horizons=[5],
        feature_columns=selected_features,
    )
    assert result["success_horizons"] == [5]
    assert recorded_feature_args, "build_feature_matrix ei kutsunut valituilla featureilla"
    for call in recorded_feature_args:
        assert call["include_is_candle_day"] is True
        assert list(call["features"]) == rr.FEATURE_COLUMNS[:4]
        assert call["categorical_columns"] == (rr.PATTERN_COLUMN,)
    assert "Pois jätetyt featuret" in result["report"]
    assert rr.FEATURE_COLUMNS[5] in result["report"]


def test_run_regression_can_disable_is_candle_day(monkeypatch):
    sample_df = _sample_dataframe(60)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    monkeypatch.setattr(rr, "load_blackout_dates", lambda *_, **__: pd.DataFrame())
    include_flags = []

    original_build = rr.build_feature_matrix

    def wrapped_build(
        df,
        feature_columns=None,
        include_is_candle_day=True,
        categorical_columns=None,
    ):
        include_flags.append(include_is_candle_day)
        return original_build(
            df,
            feature_columns=feature_columns,
            include_is_candle_day=include_is_candle_day,
            categorical_columns=categorical_columns,
        )

    monkeypatch.setattr(rr, "build_feature_matrix", wrapped_build)
    rr.run_regression_for_market(
        market="suomi",
        success_horizons=[5],
        feature_columns=rr.FEATURE_COLUMNS[:3] + [rr.FEATURE_SELECTION_MARKER],
    )
    assert include_flags
    assert all(flag is False for flag in include_flags)


def test_run_regression_can_disable_dummy_groups(monkeypatch):
    sample_df = _sample_dataframe(60)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    monkeypatch.setattr(rr, "load_blackout_dates", lambda *_, **__: pd.DataFrame())
    recorded_cats = []
    original_build = rr.build_feature_matrix

    def wrapped_build(
        df,
        feature_columns=None,
        include_is_candle_day=True,
        categorical_columns=None,
    ):
        recorded_cats.append(tuple(sorted(categorical_columns or [])))
        return original_build(
            df,
            feature_columns=feature_columns,
            include_is_candle_day=include_is_candle_day,
            categorical_columns=categorical_columns,
        )

    monkeypatch.setattr(rr, "build_feature_matrix", wrapped_build)
    rr.run_regression_for_market(
        market="suomi",
        success_horizons=[5],
        feature_columns=rr.FEATURE_COLUMNS[:3]
        + ["is_candle_day", rr.FEATURE_SELECTION_MARKER],
    )
    assert recorded_cats
    assert all(cat == () for cat in recorded_cats)


def test_run_regression_can_exclude_crisis_period(monkeypatch):
    sample_df = _sample_dataframe(80)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    monkeypatch.setattr(rr, "load_blackout_dates", lambda *_, **__: pd.DataFrame())
    monkeypatch.setattr(rr, "load_divergence_data", lambda *_, **__: pd.DataFrame())
    result = rr.run_regression_for_market(
        success_horizons=[5], exclude_crisis_period=True
    )
    expected_rows = len(sample_df[sample_df["is_crisis"] == 0])
    assert result["row_count"] == expected_rows
    assert "Kriisijakso on poistettu analyyseista" in result["report"]
