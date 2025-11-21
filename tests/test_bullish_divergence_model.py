import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.bullish_divergence_core_model import BullishDivergenceModel


CRISIS_START = "2025-03-01"
CRISIS_END = "2025-04-30"


def _build_results_dataframe(rows: int = 80, alias_columns: bool = False) -> pd.DataFrame:
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
        record = {
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
            "has_blackout_data": int(idx % 2 == 0),
        }
        if alias_columns:
            record["candle_pattern"] = record.pop("kynttila_koodi")
            record["signal_strength"] = record["vahvuus"]
        records.append(record)
    return pd.DataFrame.from_records(records)


def _write_results_to_db(df: pd.DataFrame, path: Path, include_blackout: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        df.to_sql("results_data", conn, index=False, if_exists="replace")
        conn.execute("DROP TABLE IF EXISTS blackout_dates")
        conn.execute(
            """
            CREATE TABLE blackout_dates (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                event TEXT NOT NULL
            )
            """
        )
        rows = []
        if include_blackout and "ticker" in df.columns and "date" in df.columns:
            sample = (
                df[["ticker", "date"]]
                .dropna()
                .sort_values("date")
                .groupby("ticker", as_index=False)
                .first()
            )
            for _, row in sample.iterrows():
                rows.append(
                    (
                        str(row["ticker"]),
                        (
                            pd.Timestamp(row["date"]) + pd.Timedelta(days=5)
                        ).strftime("%Y-%m-%d"),
                        "earnings",
                    )
                )
        if include_blackout and not rows:
            rows = [("TEST", "2024-01-01", "earnings")]
        conn.executemany(
            "INSERT INTO blackout_dates (ticker, date, event) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()


def _default_thresholds() -> dict[int, float]:
    return {2: 0.02, 5: 0.08, 10: 0.12, 20: 0.08}


def test_bullish_divergence_model_runs_end_to_end(tmp_path):
    df = _build_results_dataframe(90)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        success_thresholds=_default_thresholds(),
    )
    results = model.run_all()
    total = results["row_counts"]["total"]
    assert total > 0
    assert total <= len(df)
    assert set(results["logistic"].keys()) == {2, 5, 10, 20}
    assert set(results["ols"].keys()) == {2, 5, 10, 20}
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
        success_thresholds=_default_thresholds(),
        exclude_crisis_period=True,
        crisis_start=CRISIS_START,
        crisis_end=CRISIS_END,
    )
    results = model.run_all()
    assert results["row_counts"]["total"] < len(df)
    assert results["row_counts"]["bull_div_rows"] >= 1
    assert results["row_counts"]["downtrend_rows"] >= 1


def test_bullish_divergence_model_supports_alias_columns(tmp_path):
    df = _build_results_dataframe(40, alias_columns=True)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        success_thresholds=_default_thresholds(),
    )
    results = model.run_all()
    total = results["row_counts"]["total"]
    assert total > 0
    assert total <= len(df)


def test_bullish_divergence_model_custom_horizons(tmp_path):
    df = _build_results_dataframe(50)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        horizon_list=[5, 10],
        success_thresholds=_default_thresholds(),
    )
    results = model.run_all()
    assert set(results["logistic"].keys()) == {5, 10}


def test_bullish_divergence_model_blackout_filter(tmp_path):
    df = _build_results_dataframe(40)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        require_blackout_data=True,
        success_thresholds=_default_thresholds(),
    )
    results = model.run_all()
    assert results["row_counts"]["total"] > 0
    assert results["row_counts"]["total"] <= len(df)


def test_bullish_divergence_model_blackout_missing_column_warns(tmp_path):
    df = _build_results_dataframe(20)
    db_path = tmp_path / "analysis.db"
    _write_results_to_db(df, db_path, include_blackout=False)
    model = BullishDivergenceModel(
        market="usa",
        db_path=db_path,
        require_blackout_data=True,
        success_thresholds=_default_thresholds(),
    )
    with pytest.raises(ValueError):
        model.run_all()
