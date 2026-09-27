from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    persist_datacenter_group_synthetic_ohlc,
)
from rawcandle.cli.run_datacenter_effective_weight_shadow import (
    run_shadow_comparison,
)


def test_shadow_comparison_writes_only_diagnostics_under_allowed_temp_root(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,0,1.0,
""",
        encoding="utf-8",
    )
    price_db = tmp_path / "prices.db"
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(price_db) as conn:
        conn.execute(
            "CREATE TABLE osakedata (osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT)"
        )
        conn.executemany(
            "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("AAA", "2024-01-01", 100, 100, 100, 100, 10, "usa"),
                ("BBB", "2024-01-01", 100, 100, 100, 100, 20, "usa"),
                ("AAA", "2024-01-02", 100, 100, 100, 100, 10, "usa"),
                ("BBB", "2024-01-02", 100, 100, 100, 100, 20, "usa"),
                ("AAA", "2024-01-03", 110, 110, 110, 110, 10, "usa"),
                ("BBB", "2024-01-03", 120, 120, 120, 120, 20, "usa"),
            ],
        )
    DatabaseManager(str(analysis_db)).close()
    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy,
        start_date="2024-01-02",
        end_date="2024-01-03",
        market="usa",
        run_id="baseline",
        created_at_utc="2026-09-27T12:00:00Z",
        write_mode="upsert",
    )
    # Convert the fixture baseline to the former equal-weight close.
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_synthetic_ohlc_daily
            SET synthetic_close = 115.0
            WHERE ohlc_date = '2024-01-03'
            """
        )

    output_dir = Path(
        "temp/datacenter_effective_weight_calculation_only/test"
    )
    summary = run_shadow_comparison(
        analysis_db=analysis_db,
        price_db=price_db,
        taxonomy_csv=taxonomy,
        start_date="2024-01-02",
        end_date="2024-01-03",
        chain_start_date="2024-01-02",
        market="usa",
        calc_version="DC_SWING_OHLC_V1",
        output_dir=output_dir,
    )

    assert summary["status"] == "OK"
    with (output_dir / "summary.json").open(encoding="utf-8") as handle:
        persisted_summary = json.load(handle)
    assert persisted_summary["mode"] == "CALCULATION_ONLY_NO_DB_WRITES"
    with (output_dir / "group_date_comparison.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    power_day3 = next(
        row
        for row in rows
        if row["group_type"] == "layer"
        and row["group_name"] == "Power"
        and row["date"] == "2024-01-03"
    )
    assert float(power_day3["equal_synthetic_close"]) == pytest.approx(115.0)
    assert float(power_day3["weighted_synthetic_close"]) == pytest.approx(112.0)
    assert int(power_day3["eligible_positive_weight_member_count"]) == 2


def test_shadow_rejects_output_outside_dedicated_temp_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="output-dir"):
        run_shadow_comparison(
            analysis_db=tmp_path / "missing.db",
            price_db=tmp_path / "missing-prices.db",
            taxonomy_csv=tmp_path / "missing.csv",
            start_date="2024-01-01",
            end_date="2024-01-02",
            chain_start_date="2024-01-01",
            market="usa",
            calc_version="DC_SWING_OHLC_V1",
            output_dir=Path("other"),
        )
