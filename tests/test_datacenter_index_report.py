from __future__ import annotations

import sqlite3
from pathlib import Path

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.reporting import (
    build_csv_report,
    build_markdown_report,
    load_datacenter_ticker_performance_rows,
    load_datacenter_report_rows,
)


def _create_analysis_db(path: Path) -> None:
    DatabaseManager(str(path)).close()


def _insert_rows(path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as conn:
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
            rows,
        )
        conn.commit()


def _write_taxonomy_csv(tmp_path: Path) -> Path:
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                "DC_TAXONOMY_FULL_V1,AAA,LayerA,SubA,CORE,1,1.0,",
                "DC_TAXONOMY_FULL_V1,AAA,LayerB,SubB,CORE,0,1.0,",
                "DC_TAXONOMY_FULL_V1,BBB,LayerA,SubA,CORE,1,1.0,",
                "DC_TAXONOMY_FULL_V1,CCC,LayerC,SubC,CORE,1,1.0,",
                "DC_TAXONOMY_FULL_V1,DDD,LayerD,SubD,CORE,1,1.0,",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _create_ohlcv_db(path: Path) -> None:
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


def _insert_ohlcv_rows(path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _sample_row(
    group_type: str,
    group_name: str,
    *,
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    index_date: str = "2026-05-11",
    member_count: int = 10,
    eligible_count: int = 10,
    daily_return_equal: float | None = 0.01,
    pct_positive: float | None = 60.0,
    pct_above_ma50: float | None = 70.0,
    pct_above_ma200: float | None = 55.0,
    index_level_equal: float | None = 123.45,
    return_20d: float | None = 0.05,
    return_60d: float | None = 0.10,
    return_120d: float | None = 0.20,
    rs_spy: float | None = 0.03,
    rs_qqq: float | None = 0.02,
    data_quality_status: str = "OK",
    calc_version: str = "DC_INDEX_CALC_V1",
    run_id: str = "run_a",
    created_at_utc: str = "2026-05-15T01:02:03Z",
) -> tuple:
    return (
        index_date,
        taxonomy_version,
        group_type,
        group_name,
        member_count,
        eligible_count,
        member_count,
        member_count,
        daily_return_equal,
        daily_return_equal,
        pct_positive,
        pct_above_ma50,
        pct_above_ma200,
        index_level_equal,
        return_20d,
        return_60d,
        return_120d,
        0.1234,
        0.2345,
        rs_spy,
        rs_qqq,
        data_quality_status,
        calc_version,
        run_id,
        created_at_utc,
    )


def _build_report_fixture_db(tmp_path: Path) -> Path:
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_rows(
        analysis_db,
        [
            _sample_row("ecosystem", "DC_ECOSYSTEM_TOTAL", return_60d=0.08),
            _sample_row("layer", "Cooling", return_60d=0.30, pct_above_ma50=80.0, pct_above_ma200=75.0),
            _sample_row("layer", "Pilvi", return_60d=-0.10, pct_above_ma50=40.0, pct_above_ma200=35.0, data_quality_status="PARTIAL_DATA", eligible_count=6),
            _sample_row("layer", "Verkot", return_60d=None, pct_above_ma50=None, pct_above_ma200=None, rs_spy=None, rs_qqq=None),
            _sample_row("subindustry", "UPS", return_60d=0.40, rs_spy=0.20),
            _sample_row("subindustry", "Cooling infra", return_60d=-0.20, rs_spy=-0.15, data_quality_status="NO_DATA", eligible_count=0, member_count=5, pct_above_ma50=None, pct_above_ma200=None, index_level_equal=None, return_20d=None, return_120d=None, rs_qqq=None, daily_return_equal=None, pct_positive=None),
            _sample_row("subindustry", "Networking", return_60d=0.10, rs_spy=0.05),
            _sample_row("subindustry", "Power semis", return_60d=None, rs_spy=None, rs_qqq=None, pct_above_ma50=None, pct_above_ma200=None),
            _sample_row("layer", "OtherVersionLayer", taxonomy_version="OTHER", return_60d=0.99),
            _sample_row("layer", "OtherDateLayer", index_date="2026-05-10", return_60d=0.88),
        ],
    )
    return analysis_db


def test_report_reader_loads_rows_for_exact_taxonomy_version_and_as_of_date(tmp_path):
    analysis_db = _build_report_fixture_db(tmp_path)

    rows = load_datacenter_report_rows(
        analysis_db,
        "DC_TAXONOMY_FULL_V1",
        "2026-05-11",
    )

    assert len(rows) == 8
    assert all(row.taxonomy_version == "DC_TAXONOMY_FULL_V1" for row in rows)
    assert all(row.index_date == "2026-05-11" for row in rows)


def test_report_reader_ignores_other_taxonomy_versions_and_dates(tmp_path):
    analysis_db = _build_report_fixture_db(tmp_path)

    rows = load_datacenter_report_rows(
        analysis_db,
        "DC_TAXONOMY_FULL_V1",
        "2026-05-11",
    )
    names = {row.group_name for row in rows}

    assert "OtherVersionLayer" not in names
    assert "OtherDateLayer" not in names


def test_markdown_report_contains_expected_headings_and_all_ok_message(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_rows(
        analysis_db,
        [
            _sample_row("ecosystem", "DC_ECOSYSTEM_TOTAL"),
            _sample_row("layer", "Cooling"),
            _sample_row("subindustry", "UPS"),
        ],
    )

    rows = load_datacenter_report_rows(analysis_db, "DC_TAXONOMY_FULL_V1", "2026-05-11")
    markdown = build_markdown_report(
        rows,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-05-11",
        top_n=10,
    )

    assert "# Datacenter Ecosystem Index Report" in markdown
    assert "## 1. Metadata" in markdown
    assert "## 11. Data quality summary" in markdown
    assert "All groups have data_quality_status=OK." in markdown
    assert "## 12. Ticker performance by subindustry" not in markdown


def test_csv_report_contains_expected_section_names_and_none_rendering(tmp_path):
    analysis_db = _build_report_fixture_db(tmp_path)

    rows = load_datacenter_report_rows(analysis_db, "DC_TAXONOMY_FULL_V1", "2026-05-11")
    csv_report = build_csv_report(
        rows,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-05-11",
        top_n=2,
    )

    assert "metadata;taxonomy_version;DC_TAXONOMY_FULL_V1" in csv_report
    assert "executive_summary;best_subindustry_by_return_60d;UPS" in csv_report
    assert "layer_performance;Cooling;" in csv_report
    assert "top_subindustry_return_60d;UPS;" in csv_report
    assert "bottom_subindustry_rs_spy_60d;Cooling infra;" in csv_report
    assert "non_ok_groups;layer;Pilvi;10;6;PARTIAL_DATA" in csv_report
    assert "Power semis;10;10;123.45;0.05;;0.2" in csv_report


def test_report_rankings_and_top_n_are_deterministic(tmp_path):
    analysis_db = _build_report_fixture_db(tmp_path)
    rows = load_datacenter_report_rows(analysis_db, "DC_TAXONOMY_FULL_V1", "2026-05-11")

    markdown = build_markdown_report(
        rows,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-05-11",
        top_n=2,
    )

    assert "best_layer_by_return_60d | Cooling" in markdown
    assert "worst_layer_by_return_60d | Pilvi" in markdown
    assert "best_subindustry_by_return_60d | UPS" in markdown
    assert "worst_subindustry_by_return_60d | Cooling infra" in markdown
    assert markdown.count("| UPS | 10 | 10 | 123.45 | 5.00% | 40.00% | 20.00% | 70.00% | 55.00% | 20.00% | 2.00% | OK |") >= 1


def test_ticker_performance_sections_and_rankings_are_correct(tmp_path):
    analysis_db = _build_report_fixture_db(tmp_path)
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    rows = []
    for day in range(131):
        date_value = f"2026-01-{day + 1:02d}" if day < 31 else None
        if date_value is None:
            from datetime import date, timedelta
            date_value = (date(2026, 1, 1) + timedelta(days=day)).isoformat()
        rows.append(("AAA", date_value, 1, 1, 1, 100 + day, 1000, "usa"))
        rows.append(("BBB", date_value, 1, 1, 1, 200 + (day * 2), 1000, "omxh"))
        if day < 40:
            rows.append(("CCC", date_value, 1, 1, 1, 300 + day, 1000, "usa"))
        if day >= 91:
            rows.append(("DDD", date_value, 1, 1, 1, 400 + day, 1000, "usa"))
    _insert_ohlcv_rows(ohlcv_db, rows)

    report_rows = load_datacenter_report_rows(analysis_db, "DC_TAXONOMY_FULL_V1", "2026-05-11")
    ticker_rows = load_datacenter_ticker_performance_rows(
        ohlcv_db_path=ohlcv_db,
        taxonomy_csv=taxonomy_csv,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-05-11",
        market=None,
    )
    markdown = build_markdown_report(
        report_rows,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-05-11",
        top_n=2,
        ticker_performance_rows=ticker_rows,
    )
    csv_report = build_csv_report(
        report_rows,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-05-11",
        top_n=2,
        ticker_performance_rows=ticker_rows,
    )

    assert "## 12. Ticker performance by subindustry" in markdown
    assert "## 13. Top tickers by 60d return" in markdown
    assert "## 14. Bottom tickers by 60d return" in markdown
    assert "### SubA" in markdown
    assert csv_report.count("ticker_performance_by_subindustry;SubA;LayerA;AAA;1;") == 1
    assert csv_report.count("ticker_performance_by_subindustry;SubB;LayerB;AAA;0;") == 1
    assert "ticker_performance_by_subindustry;SubA;LayerA;AAA;1;" in csv_report
    assert "ticker_performance_by_subindustry;SubB;LayerB;AAA;0;" in csv_report
    assert "top_ticker_return_60d;AAA;LayerA;SubA;" in csv_report
    assert "top_ticker_return_60d;BBB;LayerA;SubA;" in csv_report
    assert "bottom_ticker_return_60d;AAA;LayerA;SubA;" in csv_report
    assert "NO_AS_OF_PRICE" in markdown
    assert "INSUFFICIENT_60D" in markdown


def test_ticker_performance_market_filter_and_validation(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    _insert_ohlcv_rows(
        ohlcv_db,
        [
            ("AAA", "2026-05-11", 1, 1, 1, 100, 1000, "usa"),
            ("AAA", "2026-05-11", 1, 1, 1, 101, 1000, "omxh"),
        ],
    )
    try:
        load_datacenter_ticker_performance_rows(
            ohlcv_db_path=ohlcv_db,
            taxonomy_csv=taxonomy_csv,
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            as_of_date="2026-05-11",
            market=None,
        )
        assert False, "expected duplicate ticker+date failure"
    except ValueError as exc:
        assert "Duplicate price row for ticker AAA on 2026-05-11" in str(exc)

    with sqlite3.connect(ohlcv_db) as conn:
        conn.execute("DELETE FROM osakedata")
        conn.execute(
            "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAA", "2026-05-11", 1, 1, 1, None, 1000, "usa"),
        )
        conn.commit()
    try:
        load_datacenter_ticker_performance_rows(
            ohlcv_db_path=ohlcv_db,
            taxonomy_csv=taxonomy_csv,
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            as_of_date="2026-05-11",
            market="usa",
        )
        assert False, "expected null close failure"
    except ValueError as exc:
        assert "NULL close for ticker AAA on 2026-05-11" in str(exc)

    with sqlite3.connect(ohlcv_db) as conn:
        conn.execute("DELETE FROM osakedata")
        conn.execute(
            "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAA", "2026-05-11", 1, 1, 1, 0, 1000, "usa"),
        )
        conn.commit()
    try:
        load_datacenter_ticker_performance_rows(
            ohlcv_db_path=ohlcv_db,
            taxonomy_csv=taxonomy_csv,
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            as_of_date="2026-05-11",
            market="usa",
        )
        assert False, "expected non-positive close failure"
    except ValueError as exc:
        assert "Price row close must be greater than 0 for ticker AAA on 2026-05-11" in str(exc)


def test_ticker_performance_explicit_market_filter_preserves_behavior(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    rows = []
    from datetime import date, timedelta
    start = date(2026, 1, 1)
    for offset in range(61):
        current = (start + timedelta(days=offset)).isoformat()
        rows.append(("AAA", current, 1, 1, 1, 100 + offset, 1000, "usa"))
        rows.append(("BBB", current, 1, 1, 1, 200 + offset, 1000, "omxh"))
    _insert_ohlcv_rows(ohlcv_db, rows)

    ticker_rows = load_datacenter_ticker_performance_rows(
        ohlcv_db_path=ohlcv_db,
        taxonomy_csv=taxonomy_csv,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        as_of_date="2026-03-02",
        market="usa",
    )

    aaa_rows = [row for row in ticker_rows if row.ticker == "AAA"]
    bbb_rows = [row for row in ticker_rows if row.ticker == "BBB"]
    assert aaa_rows[0].price_data_status == "OK"
    assert all(row.price_data_status == "NO_AS_OF_PRICE" for row in bbb_rows)
