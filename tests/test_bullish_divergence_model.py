import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.bullish_divergence_core_model import BullishDivergenceModel


CRISIS_START = "2025-03-01"
CRISIS_END = "2025-04-30"


def _build_results_dataframe(rows: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(1234)
    base_date = pd.Timestamp("2025-02-01")
    records = []
    for idx in range(rows):
        date = base_date + pd.Timedelta(days=idx)
        pattern = 7 if idx % 3 == 0 else 0
        crisis_flag = int(pd.Timestamp(CRISIS_START) <= date <= pd.Timestamp(CRISIS_END))
        shift = rng.normal(0, 3)
        t2 = 100 + rng.normal(2 + shift, 2)
        strong_move = 12 if idx % 2 == 0 else 4
        t5 = 100 + strong_move + rng.normal(0, 1.5)
        t10 = 100 + (15 if idx % 4 == 0 else 6) + rng.normal(0, 2)
        t20 = 100 + (22 if idx % 5 == 0 else 10) + rng.normal(0, 3)
        records.append(
            {
                "ticker": f"TICK{idx:03d}",
                "market": "usa",
                "date": date,
                "t0_date": date,
                "kynttila_koodi": pattern,
                "t2": t2,
                "t5": t5,
                "t10": t10,
                "t20": t20,
                "vahvuus": float(np.clip(rng.normal(0.5, 0.2), 0, 1)),
                "RSI14_t0": float(np.clip(rng.normal(50, 10), 0, 100)),
                "t0_volyymi": float(abs(rng.normal(150, 40))),
                "t0_close_norm": float(100 + rng.normal(0, 5)),
                "t_10_hajonta": float(abs(rng.normal(5, 1.5))),
                "t_20_hajonta": float(abs(rng.normal(8, 2))),
                "t0_50p_liukuva": float(100 + rng.normal(-1, 2)),
                "t0_200p_liukuva": float(100 + rng.normal(-2, 2.5)),
                "RSI_slope_5": float(rng.normal(0, 5)),
                "Price_acceleration_5_10": float(rng.normal(0, 0.4)),
                "Volatility_ratio_10_20": float(np.clip(rng.normal(0.9, 0.2), 0.2, 2.5)),
                "Gap_down_strength": float(rng.normal(-0.02, 0.04)),
                "Body_ratio": float(np.clip(rng.normal(0.45, 0.15), 0, 1)),
                "Shadow_ratio": float(np.clip(rng.normal(0.2, 0.25), -1, 3)),
                "Volume_impulse": float(np.clip(rng.normal(1.5, 0.5), 0.1, 5)),
                "is_crisis": crisis_flag,
                "SPX_10": float(100 + rng.normal(0, 1)),
                "SPX_20": float(100 + rng.normal(0, 1.2)),
                "SPX_volatility_10": float(abs(rng.normal(1.3, 0.3))),
                "NDX_10": float(100 + rng.normal(0, 1.5)),
                "NDX_20": float(100 + rng.normal(0, 1.8)),
                "NDX_volatility_10": float(abs(rng.normal(1.6, 0.35))),
                "is_divergence_today": int(rng.integers(0, 2)),
            }
        )
    return pd.DataFrame.from_records(records)


def _write_results_to_db(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        df.to_sql("results_data", conn, index=False, if_exists="replace")


def _default_thresholds() -> dict[int, float]:
    return {2: 0.02, 5: 0.08, 10: 0.12, 20: 0.08}


def test_bullish_divergence_model_runs_end_to_end(tmp_path):
    df = _build_results_dataframe(90)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        horizon_list=[5, 10],
        success_thresholds=_default_thresholds(),
    )
    results = model.run_all()
    assert results["row_counts"]["total"] == len(df)
    assert set(results["logistic"].keys()) == {5, 10}
    assert set(results["ols"].keys()) == {5, 10}
    assert results["logistic"][5]["row_count"] > 0
    assert results["ols"][10]["row_count"] > 0
    assert results["vif"]["all"].empty is False
    assert not np.isnan(results["base_rates"][5]["all"])


def test_bullish_divergence_model_crisis_exclusion(tmp_path):
    df = _build_results_dataframe(60)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        horizon_list=[5, 10],
        success_thresholds=_default_thresholds(),
        exclude_crisis_period=True,
        crisis_start=CRISIS_START,
        crisis_end=CRISIS_END,
    )
    results = model.run_all()
    assert results["row_counts"]["total"] < len(df)
    assert results["row_counts"]["bull_div_rows"] >= 1
    assert results["row_counts"]["downtrend_rows"] >= 1
