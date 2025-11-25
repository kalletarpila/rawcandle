from __future__ import annotations

import json
from pathlib import Path

from regression import run_regression


def test_save_and_load_full_selection(monkeypatch, tmp_path: Path):
    store = tmp_path / "regression_feature_selection.json"
    monkeypatch.setattr(run_regression, "FEATURE_SELECTION_STORE", store)

    run_regression.save_feature_selection_preferences(
        ["feat1", "feat2"],
        market="fin",
        horizons=[5, 10],
        thresholds={5: 0.1, 10: 0.2},
        years=[2019, 2020],
    )

    loaded = run_regression.load_feature_selection_preferences()

    assert loaded["features"] == ["feat1", "feat2"]
    assert loaded["market"] == "fin"
    assert loaded["horizons"] == [5, 10]
    assert loaded["thresholds"] == {5: 0.1, 10: 0.2}
    assert loaded["years"] == [2019, 2020]


def test_load_backward_compatible_list(monkeypatch, tmp_path: Path):
    store = tmp_path / "regression_feature_selection.json"
    store.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    monkeypatch.setattr(run_regression, "FEATURE_SELECTION_STORE", store)

    loaded = run_regression.load_feature_selection_preferences()

    assert loaded == ["a", "b"]
