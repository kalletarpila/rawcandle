from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.calculator import DatacenterGroupIndexRow
from analysis.datacenter_indices import persistence as persistence_module
from analysis.datacenter_indices.persistence import (
    build_datacenter_run_id,
    load_datacenter_taxonomy_for_version,
    read_ohlcv_price_rows,
    resolve_created_at_utc,
    run_datacenter_indices,
    write_datacenter_group_index_rows,
)


TAXONOMY_CSV = """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
"""


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(TAXONOMY_CSV, encoding="utf-8")
    return path


def _create_ohlcv_db(path):
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


def _insert_ohlcv_rows(path, rows):
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _sample_row(index_date: str, taxonomy_version: str = "DC_TAXONOMY_V1", *, group_type: str = "ecosystem", group_name: str = "DC_ECOSYSTEM_TOTAL") -> DatacenterGroupIndexRow:
    return DatacenterGroupIndexRow(
        index_date=index_date,
        taxonomy_version=taxonomy_version,
        group_type=group_type,
        group_name=group_name,
        member_count=2,
        eligible_count=2,
        ma50_eligible_count=0,
        ma200_eligible_count=0,
        daily_return_equal=0.01,
        median_return=0.01,
        pct_positive=50.0,
        pct_above_ma50=None,
        pct_above_ma200=None,
        index_level_equal=100.0,
        return_20d=None,
        return_60d=None,
        return_120d=None,
        volatility_20d=None,
        volatility_60d=None,
        relative_strength_spy_60d=None,
        relative_strength_qqq_60d=None,
        data_quality_status="OK",
        calc_version="DC_INDEX_CALC_V1",
    )


def test_ohlcv_reader_reads_only_selected_taxonomy_tickers_plus_benchmarks(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    taxonomy_rows = load_datacenter_taxonomy_for_version(taxonomy_csv, "DC_TAXONOMY_V1")
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    _insert_ohlcv_rows(
        ohlcv_db,
        [
            ("AAA", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("BBB", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("SPY", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("QQQ", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("ZZZ", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
        ],
    )

    result = read_ohlcv_price_rows(
        ohlcv_db_path=ohlcv_db,
        taxonomy_rows=taxonomy_rows,
        market="usa",
        end_date="2024-01-31",
    )

    assert [row.ticker for row in result.price_rows] == ["AAA", "BBB", "QQQ", "SPY"]
    assert result.requested_tickers == ("AAA", "BBB", "QQQ", "SPY")
    assert result.found_tickers == ("AAA", "BBB", "QQQ", "SPY")


def test_ohlcv_reader_applies_market_filter_and_prior_history_read(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    taxonomy_rows = load_datacenter_taxonomy_for_version(taxonomy_csv, "DC_TAXONOMY_V1")
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    _insert_ohlcv_rows(
        ohlcv_db,
        [
            ("AAA", "2023-12-31", 1, 1, 1, 99, 1000, "usa"),
            ("AAA", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("AAA", "2024-01-02", 1, 1, 1, 101, 1000, "usa"),
            ("AAA", "2024-01-01", 1, 1, 1, 999, 1000, "omxh"),
        ],
    )

    result = read_ohlcv_price_rows(
        ohlcv_db_path=ohlcv_db,
        taxonomy_rows=taxonomy_rows,
        market="usa",
        end_date="2024-01-02",
    )

    assert [row.date for row in result.price_rows if row.ticker == "AAA"] == [
        "2023-12-31",
        "2024-01-01",
        "2024-01-02",
    ]


def test_ohlcv_reader_reads_relevant_tickers_from_all_markets_when_market_is_omitted(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    taxonomy_rows = load_datacenter_taxonomy_for_version(taxonomy_csv, "DC_TAXONOMY_V1")
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    _insert_ohlcv_rows(
        ohlcv_db,
        [
            ("AAA", "2024-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("BBB", "2024-01-01", 1, 1, 1, 101, 1000, "omxh"),
            ("SPY", "2024-01-01", 1, 1, 1, 300, 1000, "usa"),
            ("QQQ", "2024-01-01", 1, 1, 1, 400, 1000, "nasdaq"),
            ("ZZZ", "2024-01-01", 1, 1, 1, 999, 1000, "omxh"),
        ],
    )

    result = read_ohlcv_price_rows(
        ohlcv_db_path=ohlcv_db,
        taxonomy_rows=taxonomy_rows,
        market=None,
        end_date="2024-01-31",
    )

    assert [row.ticker for row in result.price_rows] == ["AAA", "BBB", "QQQ", "SPY"]
    assert result.requested_tickers == ("AAA", "BBB", "QQQ", "SPY")
    assert result.found_tickers == ("AAA", "BBB", "QQQ", "SPY")


def test_ohlcv_reader_fails_on_relevant_null_close_before_write(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    taxonomy_rows = load_datacenter_taxonomy_for_version(taxonomy_csv, "DC_TAXONOMY_V1")
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)

    _insert_ohlcv_rows(
        ohlcv_db,
        [("AAA", "2024-01-01", 1, 1, 1, None, 1000, "usa")],
    )
    with pytest.raises(ValueError, match="AAA.*2024-01-01"):
        read_ohlcv_price_rows(
            ohlcv_db_path=ohlcv_db,
            taxonomy_rows=taxonomy_rows,
            market="usa",
            end_date="2024-01-31",
        )

    with sqlite3.connect(ohlcv_db) as conn:
        conn.execute("DELETE FROM osakedata")
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SPY", "2024-01-01", 1, 1, 1, None, 1000, "usa"),
        )
        conn.commit()
    with pytest.raises(ValueError, match="SPY.*2024-01-01"):
        read_ohlcv_price_rows(
            ohlcv_db_path=ohlcv_db,
            taxonomy_rows=taxonomy_rows,
            market="usa",
            end_date="2024-01-31",
        )

    with sqlite3.connect(ohlcv_db) as conn:
        conn.execute("DELETE FROM osakedata")
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("QQQ", "2024-01-01", 1, 1, 1, None, 1000, "usa"),
        )
        conn.commit()
    with pytest.raises(ValueError, match="QQQ.*2024-01-01"):
        read_ohlcv_price_rows(
            ohlcv_db_path=ohlcv_db,
            taxonomy_rows=taxonomy_rows,
            market="usa",
            end_date="2024-01-31",
        )


def test_replace_range_deletes_only_matching_taxonomy_version_and_date_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    DatabaseManager(str(analysis_db)).close()
    with sqlite3.connect(analysis_db) as conn:
        conn.executemany(
            """
            INSERT INTO dc_group_index_daily (
                index_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, ma50_eligible_count, ma200_eligible_count,
                daily_return_equal, median_return, pct_positive, pct_above_ma50, pct_above_ma200,
                index_level_equal, return_20d, return_60d, return_120d,
                volatility_20d, volatility_60d, relative_strength_spy_60d, relative_strength_qqq_60d,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2024-01-01", "DC_TAXONOMY_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL", 1, 1, 0, 0, 0.0, 0.0, 0.0, None, None, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "old", "2026-05-15T00:00:00Z"),
                ("2024-01-05", "DC_TAXONOMY_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL", 1, 1, 0, 0, 0.0, 0.0, 0.0, None, None, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "old", "2026-05-15T00:00:00Z"),
                ("2024-01-02", "OTHER_VERSION", "ecosystem", "DC_ECOSYSTEM_TOTAL", 1, 1, 0, 0, 0.0, 0.0, 0.0, None, None, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "old", "2026-05-15T00:00:00Z"),
            ],
        )
        conn.commit()

    rows_deleted, rows_inserted = write_datacenter_group_index_rows(
        analysis_db_path=analysis_db,
        rows=[_sample_row("2024-01-02"), _sample_row("2024-01-03")],
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-01-02",
        end_date="2024-01-03",
        run_id="run1",
        created_at_utc="2026-05-15T00:00:00Z",
        write_mode="replace-range",
    )

    assert rows_deleted == 0
    assert rows_inserted == 2
    with sqlite3.connect(analysis_db) as conn:
        rows = conn.execute(
            """
            SELECT index_date, taxonomy_version
            FROM dc_group_index_daily
            ORDER BY taxonomy_version, index_date
            """
        ).fetchall()
    assert rows == [
        ("2024-01-01", "DC_TAXONOMY_V1"),
        ("2024-01-02", "DC_TAXONOMY_V1"),
        ("2024-01-03", "DC_TAXONOMY_V1"),
        ("2024-01-05", "DC_TAXONOMY_V1"),
        ("2024-01-02", "OTHER_VERSION"),
    ]


def test_writer_inserts_all_required_columns_and_respects_explicit_created_at(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    DatabaseManager(str(analysis_db)).close()
    write_datacenter_group_index_rows(
        analysis_db_path=analysis_db,
        rows=[_sample_row("2024-01-02")],
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-01-02",
        end_date="2024-01-02",
        run_id="explicit_run",
        created_at_utc="2026-05-15T01:02:03Z",
        write_mode="replace-range",
    )

    with sqlite3.connect(analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM dc_group_index_daily").fetchone()
    assert row is not None
    assert row["run_id"] == "explicit_run"
    assert row["created_at_utc"] == "2026-05-15T01:02:03Z"
    assert row["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert row["group_type"] == "ecosystem"
    assert row["group_name"] == "DC_ECOSYSTEM_TOTAL"


def test_run_id_and_created_at_helpers_are_deterministic_and_validated():
    assert (
        build_datacenter_run_id("DC_TAXONOMY_V1", "2020-01-01", "2024-01-01", "2026-05-13")
        == "DC_INDEX_DC_TAXONOMY_V1_BASE20200101_20240101_20260513"
    )
    assert resolve_created_at_utc("2026-05-15T01:02:03Z") == "2026-05-15T01:02:03Z"
    with pytest.raises(ValueError, match="created_at_utc"):
        resolve_created_at_utc("2026-05-15")


def test_run_datacenter_indices_passes_index_base_date_to_calculator_and_reads_prior_history(
    tmp_path,
    monkeypatch,
):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    ohlcv_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_ohlcv_db(ohlcv_db)
    DatabaseManager(str(analysis_db)).close()
    _insert_ohlcv_rows(
        ohlcv_db,
        [
            ("AAA", "2019-12-31", 1, 1, 1, 99, 1000, "usa"),
            ("AAA", "2020-01-01", 1, 1, 1, 100, 1000, "usa"),
            ("AAA", "2020-01-02", 1, 1, 1, 101, 1000, "usa"),
            ("BBB", "2019-12-31", 1, 1, 1, 199, 1000, "usa"),
            ("BBB", "2020-01-01", 1, 1, 1, 200, 1000, "usa"),
            ("BBB", "2020-01-02", 1, 1, 1, 202, 1000, "usa"),
            ("SPY", "2019-12-31", 1, 1, 1, 299, 1000, "usa"),
            ("SPY", "2020-01-01", 1, 1, 1, 300, 1000, "usa"),
            ("SPY", "2020-01-02", 1, 1, 1, 301, 1000, "usa"),
            ("QQQ", "2019-12-31", 1, 1, 1, 399, 1000, "usa"),
            ("QQQ", "2020-01-01", 1, 1, 1, 400, 1000, "usa"),
            ("QQQ", "2020-01-02", 1, 1, 1, 401, 1000, "usa"),
        ],
    )

    captured: dict[str, object] = {}

    def fake_calculate_datacenter_group_indices(**kwargs):
        captured["start_date"] = kwargs["start_date"]
        captured["end_date"] = kwargs["end_date"]
        captured["price_dates"] = sorted({row.date for row in kwargs["price_rows"]})
        return [
            DatacenterGroupIndexRow(
                index_date="2020-01-01",
                taxonomy_version="DC_TAXONOMY_V1",
                group_type="ecosystem",
                group_name="DC_ECOSYSTEM_TOTAL",
                member_count=2,
                eligible_count=2,
                ma50_eligible_count=0,
                ma200_eligible_count=0,
                daily_return_equal=0.01,
                median_return=0.01,
                pct_positive=50.0,
                pct_above_ma50=None,
                pct_above_ma200=None,
                index_level_equal=100.0,
                return_20d=None,
                return_60d=None,
                return_120d=None,
                volatility_20d=None,
                volatility_60d=None,
                relative_strength_spy_60d=None,
                relative_strength_qqq_60d=None,
                data_quality_status="OK",
                calc_version="DC_INDEX_CALC_V1",
            ),
            DatacenterGroupIndexRow(
                index_date="2020-01-02",
                taxonomy_version="DC_TAXONOMY_V1",
                group_type="ecosystem",
                group_name="DC_ECOSYSTEM_TOTAL",
                member_count=2,
                eligible_count=2,
                ma50_eligible_count=0,
                ma200_eligible_count=0,
                daily_return_equal=0.01,
                median_return=0.01,
                pct_positive=50.0,
                pct_above_ma50=None,
                pct_above_ma200=None,
                index_level_equal=101.0,
                return_20d=None,
                return_60d=None,
                return_120d=None,
                volatility_20d=None,
                volatility_60d=None,
                relative_strength_spy_60d=None,
                relative_strength_qqq_60d=None,
                data_quality_status="OK",
                calc_version="DC_INDEX_CALC_V1",
            ),
        ]

    monkeypatch.setattr(
        persistence_module,
        "calculate_datacenter_group_indices",
        fake_calculate_datacenter_group_indices,
    )

    summary = run_datacenter_indices(
        ohlcv_db_path=ohlcv_db,
        analysis_db_path=analysis_db,
        taxonomy_csv=taxonomy_csv,
        taxonomy_version="DC_TAXONOMY_V1",
        market="usa",
        index_base_date="2020-01-01",
        start_date="2020-01-02",
        end_date="2020-01-02",
        write_mode="replace-range",
        created_at_utc="2026-05-15T01:02:03Z",
    )

    assert captured["start_date"] == "2020-01-01"
    assert captured["end_date"] == "2020-01-02"
    assert captured["price_dates"] == ["2019-12-31", "2020-01-01", "2020-01-02"]
    assert summary["index_base_date"] == "2020-01-01"
    assert summary["rows_in_write_range"] == 1
