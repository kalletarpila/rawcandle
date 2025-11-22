from __future__ import annotations

import numpy as np
import pandas as pd

from reverse.analysis import compute_feature_scoring, select_topN


def test_compare_does_not_force_missing_to_zero():
    universe = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "date": ["2025-01-01"] * 3,
            "t10": [120, 110, 105],
            "feat_x": [np.nan, np.nan, np.nan],
            "feat_y": [1.0, 2.0, 3.0],
        }
    )
    top = universe.iloc[:1].copy()
    top["feat_x"] = 5.0  # top has value, universe mostly missing

    cmp = compute_feature_scoring(top, universe, ["feat_x", "feat_y"])
    row_x = cmp[cmp["feature"] == "feat_x"].iloc[0]
    assert np.isnan(row_x["universe_mean"])
    assert row_x["universe_missing_rate"] == 1.0
    assert row_x["top_missing_rate"] == 0.0


def test_select_topN_dedupe_ticker_date():
    df = pd.DataFrame(
        {
            "ticker": ["A", "A", "B"],
            "date": ["2025-01-01", "2025-01-01", "2025-01-02"],
            "candle_pattern": [1, 7, 1],
            "t10": [150.0, 130.0, 140.0],
        }
    )
    top_no = select_topN(df, 10, 2, dedupe_ticker_date=False)
    assert len(top_no) == 2  # could include both A-rows

    top_yes = select_topN(df, 10, 2, dedupe_ticker_date=True)
    # only best A row + B row remain after dedupe
    assert len(top_yes) == 2
    assert (top_yes["ticker"] == "A").sum() == 1
    assert float(top_yes[top_yes["ticker"] == "A"]["t10"].iloc[0]) == 150.0
