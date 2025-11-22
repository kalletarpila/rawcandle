from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from reverse import reporting


def test_debug_exports_created():
    params = {"horizon": 10, "top_n": 5, "market": "__all__"}
    results = {
        "top": pd.DataFrame(
            {
                "ticker": ["A", "B"],
                "date": ["2025-01-01", "2025-01-02"],
                "candle_pattern": [1, 2],
                "t10": [1.0, 2.0],
            }
        ),
        "universe": pd.DataFrame(
            {
                "ticker": ["A", "B", "C"],
                "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
                "candle_pattern": [1, 2, 3],
                "t10": [1.0, 2.0, 3.0],
            }
        ),
        "compare": pd.DataFrame({"feature": ["f1"], "diff": [0.1]}),
        "cluster_summary": pd.DataFrame({"cluster_id": [0], "count": [2]}),
        "cluster_profiles": pd.DataFrame({"cluster_id": [0], "feature": ["f1"], "delta_vs_top_mean": [0.1]}),
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = reporting.export_report(results, params, output_dir=tmpdir)
        debug_dir = Path(paths["debug_dir"])
        assert debug_dir.exists()
        for fname in [
            "params.json",
            "used_features.json",
            "run_summary.json",
            "top_sample.csv",
            "compare_top100.csv",
            "cluster_summary.csv",
        ]:
            assert (debug_dir / fname).exists()

