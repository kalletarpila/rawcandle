from __future__ import annotations

from regression import run_regression


def test_bullish_divergence_report_includes_success_thresholds():
    payload = {
        "config": {
            "market": "usa",
            "horizons": [2, 5],
            "success_thresholds": {2: 0.11, 5: 0.22},
        },
        "row_counts": {},
        "base_rates": {},
        "logistic": {},
        "ols": {},
    }

    report = run_regression._build_bullish_divergence_report(payload)
    lines = report.splitlines()

    horizon_line = "Horisontit: 2 pv, 5 pv"
    threshold_line = "Success-rajat: success2: 0.110, success5: 0.220"

    assert horizon_line in lines
    assert threshold_line in lines
    assert lines.index(threshold_line) == lines.index(horizon_line) + 1
