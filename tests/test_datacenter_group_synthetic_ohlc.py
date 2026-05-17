from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    persist_datacenter_group_relative_ohlc,
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


def _insert_constant_close_history(
    price_db,
    *,
    ticker: str,
    market: str,
    start: date,
    days: int,
    close_value: float,
):
    rows = []
    for offset in range(days):
        current_date = (start + timedelta(days=offset)).isoformat()
        rows.append(
            (
                ticker,
                current_date,
                close_value,
                close_value,
                close_value,
                close_value,
                1000,
                market,
            )
        )
    _insert_price_rows(price_db, rows)


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


def test_updates_relative_ohlc20_without_overwriting_base_fields_and_uses_taxonomy_membership(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,AAA,Cooling,Cooling services,CORE,0,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    start_history = date(2024, 1, 1)
    _insert_constant_close_history(
        price_db,
        ticker="AAA",
        market="usa",
        start=start_history,
        days=19,
        close_value=100.0,
    )
    _insert_constant_close_history(
        price_db,
        ticker="BBB",
        market="usa",
        start=start_history,
        days=19,
        close_value=100.0,
    )
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-20", 120.0, 110.0, 80.0, 130.0, 1000, "usa"),
            ("BBB", "2024-01-20", 100.0, 95.0, 90.0, 110.0, 1000, "usa"),
        ],
    )

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
    rows_before = _fetch_rows(analysis_db)
    base_row_before = _find_row(rows_before, "layer", "Power", "2024-01-20")

    summary = persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        run_id="relative-run",
        created_at_utc="2026-05-17T13:00:00Z",
        write_mode="update-existing",
    )

    rows_after = _fetch_rows(analysis_db)
    power_row = _find_row(rows_after, "layer", "Power", "2024-01-20")
    cooling_row = _find_row(rows_after, "subindustry", "Cooling services", "2024-01-20")

    aaa_base = ((19.0 * 100.0) + 130.0) / 20.0
    bbb_base = ((19.0 * 100.0) + 110.0) / 20.0
    expected_open = ((120.0 / aaa_base) + (100.0 / bbb_base)) / 2.0
    unclamped_high = ((110.0 / aaa_base) + (95.0 / bbb_base)) / 2.0
    expected_low = ((80.0 / aaa_base) + (90.0 / bbb_base)) / 2.0
    expected_close = ((130.0 / aaa_base) + (110.0 / bbb_base)) / 2.0
    expected_high = max(unclamped_high, expected_open, expected_close)

    assert summary["updated_count"] == 4
    assert summary["missing_base_row_count"] == 0
    assert summary["relative_rows_with_values"] == 4
    assert power_row["synthetic_open"] == pytest.approx(base_row_before["synthetic_open"])
    assert power_row["synthetic_high"] == pytest.approx(base_row_before["synthetic_high"])
    assert power_row["synthetic_low"] == pytest.approx(base_row_before["synthetic_low"])
    assert power_row["synthetic_close"] == pytest.approx(base_row_before["synthetic_close"])
    assert power_row["relative_base_window"] == 20
    assert power_row["relative_open_20"] == pytest.approx(expected_open)
    assert power_row["relative_high_20"] == pytest.approx(expected_high)
    assert power_row["relative_low_20"] == pytest.approx(expected_low)
    assert power_row["relative_close_20"] == pytest.approx(expected_close)
    assert power_row["relative_high_20"] >= max(power_row["relative_open_20"], power_row["relative_close_20"])
    assert power_row["relative_low_20"] <= min(power_row["relative_open_20"], power_row["relative_close_20"])
    assert power_row["relative_upper_wick_20"] == pytest.approx(
        power_row["relative_high_20"] - max(power_row["relative_open_20"], power_row["relative_close_20"])
    )
    assert power_row["relative_lower_wick_20"] == pytest.approx(
        min(power_row["relative_open_20"], power_row["relative_close_20"]) - power_row["relative_low_20"]
    )
    assert power_row["relative_close_extension_20"] == pytest.approx(power_row["relative_close_20"] - 1.0)
    assert power_row["relative_high_extension_20"] == pytest.approx(power_row["relative_high_20"] - 1.0)
    assert power_row["relative_low_extension_20"] == pytest.approx(power_row["relative_low_20"] - 1.0)
    assert power_row["relative_eligible_count"] == 2
    assert power_row["data_quality_status"] == base_row_before["data_quality_status"]
    assert power_row["latest_pivot_high_date"] is None
    assert power_row["latest_structure_label"] is None
    assert cooling_row["relative_eligible_count"] == 1
    assert cooling_row["relative_open_20"] == pytest.approx(120.0 / aaa_base)


def test_relative_update_requires_20_valid_closes_and_uses_pre_start_history(tmp_path):
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

    start_history = date(2024, 1, 1)
    _insert_constant_close_history(price_db, ticker="AAA", market="usa", start=start_history, days=19, close_value=100.0)
    _insert_constant_close_history(price_db, ticker="BBB", market="usa", start=start_history, days=19, close_value=100.0)
    _insert_constant_close_history(price_db, ticker="CCC", market="usa", start=start_history, days=18, close_value=100.0)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-20", 120.0, 121.0, 119.0, 120.0, 1000, "usa"),
            ("BBB", "2024-01-20", 80.0, 81.0, 79.0, 80.0, 1000, "usa"),
            ("CCC", "2024-01-20", 150.0, 151.0, 149.0, 150.0, 1000, "usa"),
        ],
    )
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

    persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        run_id="relative-run",
        created_at_utc="2026-05-17T13:00:00Z",
        write_mode="update-existing",
    )

    row = _find_row(_fetch_rows(analysis_db), "layer", "Power", "2024-01-20")
    assert row["relative_eligible_count"] == 2
    assert row["relative_open_20"] == pytest.approx(((120.0 / 101.0) + (80.0 / 99.0)) / 2.0)


def test_relative_update_does_not_insert_missing_base_rows_and_leaves_nulls_when_no_ticker_is_eligible(tmp_path):
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

    _insert_constant_close_history(
        price_db,
        ticker="AAA",
        market="usa",
        start=date(2024, 1, 1),
        days=18,
        close_value=100.0,
    )
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-20", 120.0, 121.0, 119.0, 120.0, 1000, "usa")],
    )

    missing_summary = persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        run_id="relative-run",
        created_at_utc="2026-05-17T13:00:00Z",
        write_mode="update-existing",
    )
    assert missing_summary["updated_count"] == 0
    assert missing_summary["missing_base_row_count"] == 2
    assert _fetch_rows(analysis_db) == []

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
    no_eligibility_summary = persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-20",
        end_date="2024-01-20",
        market="usa",
        run_id="relative-run-2",
        created_at_utc="2026-05-17T14:00:00Z",
        write_mode="update-existing",
    )

    row = _find_row(_fetch_rows(analysis_db), "layer", "Power", "2024-01-20")
    assert no_eligibility_summary["relative_rows_without_eligible_tickers"] == 2
    assert row["relative_base_window"] == 20
    assert row["relative_open_20"] is None
    assert row["relative_high_20"] is None
    assert row["relative_low_20"] is None
    assert row["relative_close_20"] is None
    assert row["relative_eligible_count"] == 0


def test_relative_write_modes_update_only_matching_rows_and_replace_relative_range_only_clears_relative_fields(tmp_path):
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

    _insert_constant_close_history(
        price_db,
        ticker="AAA",
        market="usa",
        start=date(2024, 1, 1),
        days=20,
        close_value=100.0,
    )
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-21", 120.0, 121.0, 119.0, 120.0, 1000, "usa"),
            ("AAA", "2024-01-22", 130.0, 131.0, 129.0, 130.0, 1000, "usa"),
        ],
    )
    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-21",
        end_date="2024-01-22",
        market="usa",
        run_id="base-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="upsert",
    )
    persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-21",
        end_date="2024-01-21",
        market="usa",
        run_id="relative-run-1",
        created_at_utc="2026-05-17T13:00:00Z",
        write_mode="update-existing",
    )
    rows_before_replace = _fetch_rows(analysis_db)
    base_day1_before = _find_row(rows_before_replace, "layer", "Power", "2024-01-21")
    base_day2_before = _find_row(rows_before_replace, "layer", "Power", "2024-01-22")

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name, synthetic_open,
                data_quality_status, calc_version, run_id, created_at_utc,
                relative_base_window, relative_open_20, relative_eligible_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2024-01-21",
                "DC_TAXONOMY_V1",
                "layer",
                "Power",
                999.0,
                "OK",
                "OTHER_VERSION",
                "keep",
                "2026-05-17T11:00:00Z",
                20,
                7.77,
                1,
            ),
        )
        conn.commit()

    summary = persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-21",
        end_date="2024-01-22",
        market="usa",
        run_id="relative-run-2",
        created_at_utc="2026-05-17T14:00:00Z",
        write_mode="replace-relative-range",
    )

    rows = _fetch_rows(analysis_db)
    row_day1 = _find_row(rows, "layer", "Power", "2024-01-21")
    row_day2 = _find_row(rows, "layer", "Power", "2024-01-22")
    assert summary["updated_count"] == 4
    assert summary["cleared_count"] == 4
    assert row_day1["synthetic_open"] == pytest.approx(base_day1_before["synthetic_open"])
    assert row_day2["synthetic_open"] == pytest.approx(base_day2_before["synthetic_open"])
    assert row_day1["relative_open_20"] is not None
    assert row_day2["relative_open_20"] is not None

    with sqlite3.connect(analysis_db) as conn:
        other_row = conn.execute(
            """
            SELECT synthetic_open, relative_open_20
            FROM dc_group_synthetic_ohlc_daily
            WHERE ohlc_date = '2024-01-21'
              AND taxonomy_version = 'DC_TAXONOMY_V1'
              AND group_type = 'layer'
              AND group_name = 'Power'
              AND calc_version = 'OTHER_VERSION'
            """
        ).fetchone()
    assert other_row == (999.0, 7.77)
