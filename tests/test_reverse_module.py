from __future__ import annotations

import pandas as pd

from reverse import analysis, queries


def _build_sample_df() -> pd.DataFrame:
    records = [
        {
            "ticker": f"TICK{i}",
            "market": "usa" if i % 2 == 0 else "fin",
            "candle_pattern": 7,
            "t5": i * 0.5,
            "t10": i * 0.75,
            "t20": i * 1.2,
            "RSI14_t0": 40 + i,
            "t0_volyymi": 1000 + (i * 10),
            "RSI_slope_5": 0.1 * i,
            "Price_acceleration_5_10": 0.05 * i,
            "Gap_down_strength": -0.2 * i,
            "Volume_impulse": 1.5 * i,
            "is_crisis": 0,
        }
        for i in range(1, 11)
    ]
    return pd.DataFrame.from_records(records)


def test_build_universe_query():
    params = {
        "market": "fin",
        "bullish_only": True,
        "exclude_blackout": True,
        "exclude_crisis": True,
    }
    sql, sql_params = queries.build_universe_query(params)
    assert "WHERE" in sql
    assert "candle_pattern IN (0, 7)" in sql
    assert "is_crisis" in sql
    assert sql_params == ["fin"]


def test_select_topN():
    df = _build_sample_df()
    top = analysis.select_topN(df, horizon=10, top_n=3)
    assert len(top) == 3
    assert top.iloc[0]["t10"] >= top.iloc[-1]["t10"]


def test_compute_feature_compare_shapes():
    df = _build_sample_df()
    features = ["RSI14_t0", "t0_volyymi"]
    compare = analysis.compute_feature_compare(df.head(3), df, features)
    assert set(compare.columns) >= {
        "feature",
        "top_mean",
        "universe_mean",
        "diff",
        "pct_change",
    }
    assert len(compare) == len(features)


def test_cluster_top_labels():
    df = _build_sample_df()
    features = ["RSI14_t0", "t0_volyymi", "Volume_impulse"]
    clustered, summary = analysis.cluster_top(
        df, features, horizon=10, n_clusters=3
    )
    assert "cluster_id" in clustered.columns
    assert not summary.empty
    assert summary["cluster_id"].nunique() <= 3
