from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from analysis.bullish_divergence_core_model import BullishDivergenceModel
from regression import run_regression


def test_list_available_years_reads_distinct_years(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE results_data (date TEXT, market TEXT)"
        )
        conn.executemany(
            "INSERT INTO results_data (date, market) VALUES (?, ?)",
            [
                ("2018-01-02", "usa"),
                ("2019-05-10", "usa"),
                ("2020-12-31", "usa"),
            ],
        )
        conn.commit()

    years = run_regression.list_available_years(db_path=db_path)

    assert years == [2018, 2019, 2020]


def test_apply_year_filter_limits_dataframe():
    df = pd.DataFrame(
        {
            "date": ["2019-01-01", "2020-06-15", "2021-03-03"],
            "value": [1, 2, 3],
        }
    )

    filtered = run_regression.apply_year_filter(df, [2020])

    assert len(filtered) == 1
    assert filtered.iloc[0]["value"] == 2


def test_bullish_divergence_model_applies_year_filter():
    model = BullishDivergenceModel(year_filter=[2019])
    model.date_column = "date"
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-07-01", "2020-08-02"]),
            "kynttila_koodi": [7, 7],
        }
    )

    filtered = model._apply_year_filter(df)

    assert len(filtered) == 1
    assert filtered.iloc[0]["date"].year == 2019
