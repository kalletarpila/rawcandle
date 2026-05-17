from __future__ import annotations

import sqlite3

from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    persist_datacenter_group_synthetic_ohlc,
)
from run_datacenter_group_synthetic_ohlc import main as run_datacenter_group_synthetic_ohlc_main


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Cooling,Chillers,CORE,1,1.0,
""",
        encoding="utf-8",
    )
    return path


def _create_price_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-01", 100, 101, 99, 100, 1000, "usa"),
                ("AAA", "2024-01-02", 101, 102, 100, 101, 1100, "usa"),
                ("BBB", "2024-01-01", 200, 202, 198, 200, 900, "usa"),
                ("BBB", "2024-01-02", 202, 204, 201, 203, 950, "usa"),
                ("CCC", "2024-01-01", 300, 303, 297, 300, 800, "usa"),
                ("CCC", "2024-01-02", 303, 306, 300, 304, 850, "usa"),
            ],
        )
        conn.commit()


def test_cli_writes_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)

    exit_code = run_datacenter_group_synthetic_ohlc_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-02",
            "--market",
            "usa",
            "--write-mode",
            "upsert",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-01-01"
    assert lines[1] == "SUMMARY end_date=2024-01-02"
    assert lines[2] == "SUMMARY market=usa"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily").fetchone()[0]
    assert count == 8


def test_cli_relative_only_updates_existing_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)

    with sqlite3.connect(price_db) as conn:
        rows = []
        for day in range(1, 20):
            current_date = f"2024-01-{day:02d}"
            rows.extend(
                [
                    ("AAA", current_date, 100.0, 100.0, 100.0, 100.0, 1000, "usa"),
                    ("BBB", current_date, 100.0, 100.0, 100.0, 100.0, 1000, "usa"),
                    ("CCC", current_date, 100.0, 100.0, 100.0, 100.0, 1000, "usa"),
                ]
            )
        rows.extend(
            [
                ("AAA", "2024-01-20", 120.0, 121.0, 119.0, 120.0, 1000, "usa"),
                ("BBB", "2024-01-20", 110.0, 111.0, 109.0, 110.0, 1000, "usa"),
                ("CCC", "2024-01-20", 130.0, 131.0, 129.0, 130.0, 1000, "usa"),
            ]
        )
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        run_id="base-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    exit_code = run_datacenter_group_synthetic_ohlc_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-20",
            "--end-date",
            "2024-01-20",
            "--market",
            "usa",
            "--write-mode",
            "update-existing",
            "--relative-only",
            "--created-at-utc",
            "2026-05-17T12:30:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-01-20"
    assert lines[1] == "SUMMARY end_date=2024-01-20"
    assert lines[2] == "SUMMARY market=usa"
    assert lines[5] == "SUMMARY relative_base_window=20"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_group_synthetic_ohlc_daily
            WHERE relative_open_20 IS NOT NULL
            """
        ).fetchone()[0]
    assert count == 4


def test_cli_structure_only_updates_existing_rows_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(analysis_db) as conn:
        from analysis.database_manager import DatabaseManager

        DatabaseManager(str(analysis_db)).close()
        rows = []
        highs = [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10]
        lows = [10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 10]
        for day, (high_value, low_value) in enumerate(zip(highs, lows), start=1):
            rows.append(
                (
                    f"2024-06-{day:02d}",
                    "DC_TAXONOMY_V1",
                    "subindustry",
                    "UPS",
                    2,
                    2,
                    100.0,
                    float(high_value),
                    float(low_value),
                    100.0,
                    1000.0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    20,
                    1.1,
                    1.2,
                    0.9,
                    1.0,
                    0.1,
                    0.1,
                    0.0,
                    0.2,
                    -0.1,
                    2,
                    "OK",
                    "DC_SWING_OHLC_V1",
                    "seed",
                    "2026-05-17T10:00:00Z",
                )
            )
        normalized_rows = []
        for row in rows:
            values = list(row)
            if len(values) == 37:
                values[21:21] = [None, None]
            normalized_rows.append(tuple(values))
        conn.executemany(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name, member_count, eligible_count,
                synthetic_open, synthetic_high, synthetic_low, synthetic_close, synthetic_volume,
                ma20, ema20, distance_to_ema20_pct, volatility_20d,
                pivot_radius, latest_pivot_high_date, latest_pivot_high_value,
                latest_pivot_low_date, latest_pivot_low_value, latest_structure_label,
                latest_structure_age_trading_days, latest_structure_freshness,
                trend_classification, relative_base_window, relative_open_20, relative_high_20,
                relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            normalized_rows,
        )
        conn.commit()

    exit_code = run_datacenter_group_synthetic_ohlc_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--start-date",
            "2024-06-01",
            "--end-date",
            "2024-06-11",
            "--write-mode",
            "update-existing",
            "--structure-only",
            "--created-at-utc",
            "2026-05-17T12:30:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-06-01"
    assert lines[1] == "SUMMARY end_date=2024-06-11"
    assert lines[2] == "SUMMARY write_mode=update-existing"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        label_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_group_synthetic_ohlc_daily
            WHERE latest_pivot_high_date IS NOT NULL OR latest_structure_label IS NOT NULL
            """
        ).fetchone()[0]
    assert label_count > 0
