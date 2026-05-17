from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    persist_datacenter_group_synthetic_ohlc,
)


def _write_taxonomy_csv(tmp_path, content: str):
    path = tmp_path / "taxonomy.csv"
    path.write_text(content, encoding="utf-8")
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
        conn.commit()


def _insert_price_rows(path, rows):
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def _fetch_rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM dc_group_synthetic_ohlc_daily
            ORDER BY taxonomy_version, group_type, group_name, ohlc_date, calc_version
            """
        ).fetchall()


def _find_row(rows, group_type: str, group_name: str, ohlc_date: str):
    for row in rows:
        if (
            row["group_type"] == group_type
            and row["group_name"] == group_name
            and row["ohlc_date"] == ohlc_date
        ):
            return row
    raise AssertionError(f"Missing row for {group_type} {group_name} {ohlc_date}")


def test_inserts_synthetic_ohlc_rows_for_layer_and_subindustry_groups(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Cooling,Chillers,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-01", 100, 101, 99, 100, 1000, "usa"),
            ("AAA", "2024-01-02", 101, 102, 100, 101, 1100, "usa"),
            ("BBB", "2024-01-01", 200, 201, 199, 200, 900, "usa"),
            ("BBB", "2024-01-02", 202, 204, 201, 203, 950, "usa"),
        ],
    )

    summary = persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_rows(analysis_db)
    assert summary["group_rows"] == 8
    assert _find_row(rows, "layer", "Power", "2024-01-01")["group_name"] == "Power"
    assert _find_row(rows, "subindustry", "UPS", "2024-01-02")["group_name"] == "UPS"


def test_uses_taxonomy_membership_not_primary_subindustry_to_build_groups(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,AAA,Cooling,Cooling services,CORE,0,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-01", 100, 101, 99, 100, 1000, "usa"),
            ("AAA", "2024-01-02", 101, 102, 100, 101, 1100, "usa"),
        ],
    )

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    row = _find_row(_fetch_rows(analysis_db), "subindustry", "Cooling services", "2024-01-02")
    assert row["member_count"] == 1
    assert row["eligible_count"] == 1


def test_requires_previous_valid_close_for_ticker_eligibility(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-02", 101, 102, 100, 101, 1100, "usa")],
    )

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-02",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    row = _find_row(_fetch_rows(analysis_db), "layer", "Power", "2024-01-02")
    assert row["eligible_count"] == 0
    assert row["synthetic_close"] is None
    assert row["data_quality_status"] == "NO_DATA"


def test_calculates_equal_weight_group_ohlc_returns_and_chains_from_previous_valid_close(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-01", 100, 101, 99, 100, 10, "usa"),
            ("BBB", "2024-01-01", 200, 202, 198, 200, 20, "usa"),
            ("AAA", "2024-01-02", 110, 115, 90, 105, 11, "usa"),
            ("BBB", "2024-01-02", 220, 230, 180, 190, 22, "usa"),
            ("AAA", "2024-01-03", 105, 110, 100, 108, 13, "usa"),
            ("BBB", "2024-01-03", 190, 200, 185, 195, 24, "usa"),
        ],
    )

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-03",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_rows(analysis_db)
    first_row = _find_row(rows, "layer", "Power", "2024-01-02")
    second_row = _find_row(rows, "layer", "Power", "2024-01-03")
    assert first_row["synthetic_open"] == pytest.approx(100.0)
    assert first_row["synthetic_close"] == pytest.approx(100.0)
    assert first_row["synthetic_volume"] == pytest.approx(33.0)
    expected_close_return_day2 = (((108 / 105) - 1.0) + ((195 / 190) - 1.0)) / 2.0
    assert second_row["synthetic_close"] == pytest.approx(100.0 * (1.0 + expected_close_return_day2))


def test_anchors_only_first_valid_group_row_in_range_at_100(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-02", 110, 115, 90, 105, 11, "usa"),
            ("AAA", "2024-01-03", 105, 110, 100, 108, 13, "usa"),
            ("BBB", "2024-01-02", 220, 230, 180, 190, 22, "usa"),
            ("BBB", "2024-01-03", 190, 200, 185, 195, 24, "usa"),
            ("AAA", "2024-01-01", 100, 101, 99, 100, 10, "usa"),
            ("BBB", "2024-01-01", 200, 202, 198, 200, 20, "usa"),
        ],
    )

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-02",
        end_date="2024-01-03",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_rows(analysis_db)
    assert _find_row(rows, "layer", "Power", "2024-01-02")["synthetic_close"] == pytest.approx(100.0)
    assert _find_row(rows, "layer", "Power", "2024-01-03")["synthetic_close"] != pytest.approx(100.0)


def test_applies_synthetic_candle_clamp(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-01", 100, 101, 99, 100, 10, "usa"),
            ("BBB", "2024-01-01", 100, 101, 99, 100, 10, "usa"),
            ("AAA", "2024-01-02", 120, 105, 80, 130, 10, "usa"),
            ("BBB", "2024-01-02", 120, 105, 80, 130, 10, "usa"),
        ],
    )

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    row = _find_row(_fetch_rows(analysis_db), "layer", "Power", "2024-01-02")
    assert row["synthetic_high"] >= max(row["synthetic_open"], row["synthetic_close"])
    assert row["synthetic_low"] <= min(row["synthetic_open"], row["synthetic_close"])


def test_assigns_member_count_eligible_count_and_data_quality_statuses(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,DDD,Cooling,Chillers,CORE,1,1.0,
DC_TAXONOMY_V1,EEE,Cooling,Chillers,CORE,1,1.0,
DC_TAXONOMY_V1,FFF,Services,Monitoring,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    rows = [
        ("AAA", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
        ("BBB", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
        ("CCC", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
        ("AAA", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
        ("BBB", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
        ("CCC", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
        ("DDD", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
        ("EEE", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
        ("DDD", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
        ("FFF", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
    ]
    _insert_price_rows(price_db, rows)

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-02",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_rows(analysis_db)
    power = _find_row(rows, "layer", "Power", "2024-01-02")
    cooling = _find_row(rows, "layer", "Cooling", "2024-01-02")
    services = _find_row(rows, "layer", "Services", "2024-01-02")
    assert power["member_count"] == 3 and power["eligible_count"] == 3 and power["data_quality_status"] == "OK"
    assert cooling["member_count"] == 2 and cooling["eligible_count"] == 1 and cooling["data_quality_status"] == "TOO_SMALL"
    assert services["member_count"] == 1 and services["eligible_count"] == 0 and services["data_quality_status"] == "NO_DATA"


def test_calculates_ma20_ema20_distance_and_volatility_after_sufficient_history(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    start = date(2024, 1, 1)
    price_rows = []
    for offset in range(22):
        current_date = (start + timedelta(days=offset)).isoformat()
        for idx, ticker in enumerate(["AAA", "BBB", "CCC"]):
            base = 100.0 + idx
            close = base + offset
            price_rows.append((ticker, current_date, close, close + 1, close - 1, close, 10 + idx, "usa"))
    _insert_price_rows(price_db, price_rows)

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-22",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    row = _find_row(_fetch_rows(analysis_db), "layer", "Power", "2024-01-22")
    assert row["ma20"] is not None
    assert row["ema20"] is not None
    assert row["distance_to_ema20_pct"] is not None
    assert row["volatility_20d"] is not None


def test_leaves_pivot_trend_and_relative_fields_null(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
            ("BBB", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
            ("CCC", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
            ("AAA", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
            ("BBB", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
            ("CCC", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
        ],
    )

    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )

    row = _find_row(_fetch_rows(analysis_db), "layer", "Power", "2024-01-02")
    assert row["pivot_radius"] is None
    assert row["latest_pivot_high_date"] is None
    assert row["latest_structure_label"] is None
    assert row["trend_classification"] is None
    assert row["relative_open_20"] is None
    assert row["relative_eligible_count"] is None


def test_write_modes_insert_missing_upsert_and_replace_range(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
            ("BBB", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
            ("CCC", "2024-01-01", 100, 101, 99, 100, 1, "usa"),
            ("AAA", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
            ("BBB", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
            ("CCC", "2024-01-02", 101, 102, 100, 101, 1, "usa"),
        ],
    )
    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )
    insert_missing_summary = persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run2",
        created_at_utc="2026-05-17T13:00:00Z",
        write_mode="insert-missing",
    )
    upsert_summary = persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run3",
        created_at_utc="2026-05-17T14:00:00Z",
        write_mode="upsert",
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name, data_quality_status,
                calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-03", "DC_TAXONOMY_V1", "layer", "Power", "OK", "OTHER_VERSION", "keep", "2026-05-17T11:00:00Z"),
        )
        conn.commit()
    replace_summary = persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-02",
        market="usa",
        run_id="run4",
        created_at_utc="2026-05-17T15:00:00Z",
        write_mode="replace-range",
    )

    rows = _fetch_rows(analysis_db)
    assert insert_missing_summary["skipped_existing_count"] > 0
    assert upsert_summary["updated_count"] > 0
    assert replace_summary["deleted_count"] > 0
    assert any(row["calc_version"] == "OTHER_VERSION" for row in rows)
