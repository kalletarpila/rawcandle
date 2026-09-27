from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    WEIGHTED_CALC_VERSION,
    persist_datacenter_group_relative_ohlc,
    persist_datacenter_group_synthetic_ohlc,
)


def _write_taxonomy(tmp_path, rows: str):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
        + rows,
        encoding="utf-8",
    )
    return path


def _create_databases(price_db, analysis_db):
    with sqlite3.connect(price_db) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT, pvm TEXT, open REAL, high REAL, low REAL,
                close REAL, volume INTEGER, market TEXT
            )
            """
        )
    DatabaseManager(str(analysis_db)).close()


def _insert_prices(price_db, rows):
    with sqlite3.connect(price_db) as conn:
        conn.executemany(
            "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _group_row(analysis_db, group_type, group_name, ohlc_date):
    with sqlite3.connect(analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM dc_group_synthetic_ohlc_daily
            WHERE group_type = ? AND group_name = ? AND ohlc_date = ?
            """,
            (group_type, group_name, ohlc_date),
        ).fetchone()
    assert row is not None
    return row


def test_weighted_base_preserves_counts_volume_and_chain(tmp_path):
    taxonomy = _write_taxonomy(
        tmp_path,
        """DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,EXTENDED,0,9.0,
DC_TAXONOMY_V1,CCC,Power,UPS,WATCH_ONLY,1,1.0,
DC_TAXONOMY_V1,DDD,Power,UPS,TOO_SMALL,1,1.0,
DC_TAXONOMY_V1,EEE,Cooling,Chillers,WATCH_ONLY,1,1.0,
DC_TAXONOMY_V1,FFF,Cooling,Chillers,TOO_SMALL,0,1.0,
""",
    )
    price_db = tmp_path / "prices.db"
    analysis_db = tmp_path / "analysis.db"
    _create_databases(price_db, analysis_db)

    rows = []
    for ticker, volume in (
        ("AAA", 10),
        ("BBB", 20),
        ("CCC", 30),
        ("DDD", 40),
        ("EEE", 50),
        ("FFF", 60),
    ):
        rows.extend(
            [
                (ticker, "2024-01-01", 100, 100, 100, 100, volume, "usa"),
                (ticker, "2024-01-02", 100, 100, 100, 100, volume, "usa"),
            ]
        )
    rows.extend(
        [
            ("AAA", "2024-01-03", 110, 110, 110, 110, 11, "usa"),
            ("BBB", "2024-01-03", 120, 120, 120, 120, 22, "usa"),
            ("CCC", "2024-01-03", 190, 190, 190, 190, 33, "usa"),
            ("DDD", "2024-01-03", 50, 50, 50, 50, 44, "usa"),
            ("EEE", "2024-01-03", 120, 120, 120, 120, 55, "usa"),
            ("FFF", "2024-01-03", 80, 80, 80, 80, 66, "usa"),
            ("BBB", "2024-01-04", 132, 132, 132, 132, 23, "usa"),
            ("CCC", "2024-01-04", 200, 200, 200, 200, 34, "usa"),
            ("DDD", "2024-01-04", 55, 55, 55, 55, 45, "usa"),
        ]
    )
    _insert_prices(price_db, rows)

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy,
        start_date="2024-01-02",
        end_date="2024-01-04",
        market="usa",
        calc_version=WEIGHTED_CALC_VERSION,
        run_id="weighted-run",
        created_at_utc="2026-09-27T12:00:00Z",
        write_mode="upsert",
        min_eligible_count=1,
    )

    power_day2 = _group_row(analysis_db, "layer", "Power", "2024-01-02")
    power_day3 = _group_row(analysis_db, "layer", "Power", "2024-01-03")
    power_day4 = _group_row(analysis_db, "layer", "Power", "2024-01-04")
    cooling_day3 = _group_row(analysis_db, "layer", "Cooling", "2024-01-03")

    assert power_day2["synthetic_close"] == pytest.approx(100.0)
    assert power_day3["synthetic_close"] == pytest.approx(112.0)
    assert power_day3["member_count"] == 4
    assert power_day3["eligible_count"] == 4
    assert power_day3["synthetic_volume"] == pytest.approx(110.0)
    assert power_day4["eligible_count"] == 3
    assert power_day4["synthetic_close"] == pytest.approx(123.2)
    assert power_day4["synthetic_volume"] == pytest.approx(102.0)

    assert cooling_day3["eligible_count"] == 2
    assert cooling_day3["synthetic_open"] is None
    assert cooling_day3["synthetic_close"] is None
    assert cooling_day3["synthetic_volume"] == pytest.approx(121.0)
    assert cooling_day3["data_quality_status"] == "NO_DATA"


def test_relative_ohlc_uses_same_effective_membership_weights(tmp_path):
    taxonomy = _write_taxonomy(
        tmp_path,
        """DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,EXTENDED,0,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,WATCH_ONLY,1,1.0,
""",
    )
    price_db = tmp_path / "prices.db"
    analysis_db = tmp_path / "analysis.db"
    _create_databases(price_db, analysis_db)

    rows = []
    for ticker in ("AAA", "BBB", "CCC"):
        for offset in range(19):
            current_date = (date(2024, 1, 1) + timedelta(days=offset)).isoformat()
            rows.append(
                (ticker, current_date, 100, 100, 100, 100, 10, "usa")
            )
    rows.extend(
        [
            ("AAA", "2024-01-20", 120, 120, 120, 120, 10, "usa"),
            ("BBB", "2024-01-20", 80, 80, 80, 80, 20, "usa"),
            ("CCC", "2024-01-20", 200, 200, 200, 200, 30, "usa"),
        ]
    )
    _insert_prices(price_db, rows)

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        calc_version=WEIGHTED_CALC_VERSION,
        run_id="base-run",
        created_at_utc="2026-09-27T12:00:00Z",
        write_mode="upsert",
    )
    persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        calc_version=WEIGHTED_CALC_VERSION,
        run_id="relative-run",
        created_at_utc="2026-09-27T13:00:00Z",
        write_mode="update-existing",
    )

    row = _group_row(analysis_db, "layer", "Power", "2024-01-20")
    expected = ((120.0 / 101.0) + ((80.0 / 99.0) * 0.25)) / 1.25
    assert row["relative_eligible_count"] == 3
    assert row["relative_open_20"] == pytest.approx(expected)
    assert row["relative_close_20"] == pytest.approx(expected)
