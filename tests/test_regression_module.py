import pandas as pd
import numpy as np
import pytest

from regression import run_regression as rr


def _sample_dataframe(rows: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    pattern_codes = [0, 1, 2, 3, 4, 5, 6]
    markets = ["usa", "suomi"]
    records = []
    for i in range(rows):
        shift = rng.normal(0, 2)
        records.append(
            {
                "t2": 100 + rng.normal(1 + shift, 3),
                "t5": 100 + rng.normal(2 + (-1) ** i * 4, 4),
                "t10": 100 + rng.normal(4 + shift, 5),
                "t20": 100 + rng.normal(6 + (-1) ** i * 5, 6),
                "vahvuus": float(np.clip(rng.normal(0.5, 0.2), 0, 1)),
                "RSI14_t0": float(np.clip(rng.normal(50, 15), 0, 100)),
                "Bullish Divergence": float(np.clip(rng.normal(1.5, 0.7), 0, 3)),
                "t0_volyymi": float(np.clip(rng.normal(120, 30), 10, 400)),
                "t_10_hajonta": float(abs(rng.normal(5, 2))),
                "t_20_hajonta": float(abs(rng.normal(8, 3))),
                "t_10": 100 + rng.normal(-2, 3),
                "t_20": 100 + rng.normal(-4, 4),
                "SPX_10": 100 + rng.normal(0, 1),
                "NDX_10": 100 + rng.normal(0, 1.5),
                "kynttila_koodi": pattern_codes[i % len(pattern_codes)],
                "market": markets[i % len(markets)],
            }
        )
    return pd.DataFrame.from_records(records)


def test_add_return_labels_produces_expected_columns():
    df = _sample_dataframe(10)
    df = rr.add_return_labels(df.copy())
    for col in ("y2", "y5", "y10", "y20", "success2", "success5", "success10", "success20"):
        assert col in df.columns
    assert df["y5"].between(-1, 5).all()
    assert set(df["success5"].unique()).issubset({0, 1})


def test_build_feature_matrix_creates_dummies_and_is_candle_flag():
    df = rr.add_return_labels(_sample_dataframe(8))
    X = rr.build_feature_matrix(df)
    assert "is_candle_day" in X.columns
    pattern_cols = [col for col in X.columns if col.startswith("kynttila_koodi_")]
    market_cols = [col for col in X.columns if col.startswith("market_")]
    assert pattern_cols, "Pattern-ohjaimia ei syntynyt"
    assert market_cols, "Markkina-ohjaimia ei syntynyt"


def test_run_logistic_regression_returns_metrics():
    df = rr.add_return_labels(_sample_dataframe(60))
    X = rr.build_feature_matrix(df)
    y = df["success5"]
    result = rr.run_logistic_regression(X, y)
    assert 0.0 <= result["auc"] <= 1.0
    assert "precision" in result["classification_report"]
    assert not result["top_positive"].empty
    assert not result["top_negative"].empty


def test_run_linear_regression_returns_summary():
    df = rr.add_return_labels(_sample_dataframe(40))
    X = rr.build_feature_matrix(df)
    summary = rr.run_linear_regression(X, df["y5"])["summary"]
    assert "OLS Regression Results" in summary


def test_run_regression_for_market_uses_loader(monkeypatch):
    sample_df = _sample_dataframe(50)

    def fake_loader(db_path=None, market=None):
        return sample_df.copy()

    monkeypatch.setattr(rr, "load_data", fake_loader)
    result = rr.run_regression_for_market(market="usa")
    assert result["row_count"] == len(sample_df)
    horizons = result["horizons"]
    assert 5 in horizons
    assert 0 <= horizons[5]["logistic"]["auc"] <= 1


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
