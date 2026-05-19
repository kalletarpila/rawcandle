from __future__ import annotations

import sqlite3
from pathlib import Path

from analysis.database_manager import DatabaseManager
from run_datacenter_index_report import main as run_datacenter_index_report_main


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


def _write_taxonomy_csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                "DC_TAXONOMY_FULL_V1,AAA,LayerA,SubA,CORE,1,1.0,",
                "DC_TAXONOMY_FULL_V1,AAA,LayerB,SubB,CORE,0,1.0,",
                "DC_TAXONOMY_FULL_V1,BBB,LayerA,SubA,CORE,1,1.0,",
                "DC_TAXONOMY_FULL_V1,CCC,LayerC,SubC,CORE,1,1.0,",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _sample_row(
    group_type: str,
    group_name: str,
    *,
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    index_date: str = "2026-05-11",
    return_60d: float | None = 0.10,
    rs_spy: float | None = 0.03,
    pct_above_ma50: float | None = 70.0,
    pct_above_ma200: float | None = 60.0,
    data_quality_status: str = "OK",
    eligible_count: int = 10,
    member_count: int = 10,
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
        0.01,
        0.01,
        60.0,
        pct_above_ma50,
        pct_above_ma200,
        100.0,
        0.05,
        return_60d,
        0.20,
        0.1234,
        0.2345,
        rs_spy,
        0.02,
        data_quality_status,
        "DC_INDEX_CALC_V1",
        "run_a",
        "2026-05-15T01:02:03Z",
    )


def test_report_cli_fails_if_no_rows_exist_for_exact_as_of_date(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    exit_code = run_datacenter_index_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--as-of-date",
            "2026-05-11",
            "--output-md",
            str(tmp_path / "exports" / "report.md"),
            "--output-csv",
            str(tmp_path / "exports" / "report.csv"),
        ]
    )

    assert exit_code == 1
    assert "No dc_group_index_daily rows found" in capsys.readouterr().err


def test_report_cli_creates_output_files_and_parent_directories(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_rows(
        analysis_db,
        [
            _sample_row("ecosystem", "DC_ECOSYSTEM_TOTAL"),
            _sample_row("layer", "Cooling", return_60d=0.30),
            _sample_row("layer", "Cloud", return_60d=-0.10, data_quality_status="PARTIAL_DATA", eligible_count=6),
            _sample_row("subindustry", "UPS", return_60d=0.40, rs_spy=0.20),
            _sample_row("subindustry", "Cooling infra", return_60d=-0.20, rs_spy=-0.15),
        ],
    )

    output_md = tmp_path / "nested" / "exports" / "report.md"
    output_csv = tmp_path / "nested" / "exports" / "report.csv"
    exit_code = run_datacenter_index_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--as-of-date",
            "2026-05-11",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--top-n",
            "1",
        ]
    )

    assert exit_code == 0
    assert output_md.exists()
    assert output_csv.exists()
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [
        "SUMMARY taxonomy_version=DC_TAXONOMY_FULL_V1",
        "SUMMARY as_of_date=2026-05-11",
        "SUMMARY rows_read=5",
        "SUMMARY ecosystem_group_count=1",
        "SUMMARY layer_group_count=2",
        "SUMMARY subindustry_group_count=2",
        "SUMMARY non_ok_group_count=1",
        "SUMMARY top_n=1",
        "SUMMARY include_ticker_performance=0",
        f"SUMMARY output_md={output_md}",
        f"SUMMARY output_csv={output_csv}",
        "SUMMARY report_status=OK",
    ]

    markdown = output_md.read_text(encoding="utf-8")
    csv_report = output_csv.read_text(encoding="utf-8")
    assert "## 6. Top subindustries by 60d return" in markdown
    assert "section;metric;value" in csv_report
    assert "top_subindustry_return_60d;UPS;" in csv_report


def test_report_cli_requires_ohlcv_and_taxonomy_when_ticker_performance_is_enabled(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_rows(analysis_db, [_sample_row("ecosystem", "DC_ECOSYSTEM_TOTAL")])
    output_md = tmp_path / "report.md"
    output_csv = tmp_path / "report.csv"

    exit_code = run_datacenter_index_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--as-of-date",
            "2026-05-11",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--include-ticker-performance",
        ]
    )

    assert exit_code == 1
    assert "--ohlcv-db is required" in capsys.readouterr().err


def test_report_cli_with_ticker_performance_outputs_extended_sections_and_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_rows(
        analysis_db,
        [
            _sample_row("ecosystem", "DC_ECOSYSTEM_TOTAL"),
            _sample_row("layer", "LayerA", return_60d=0.10),
            _sample_row("subindustry", "SubA", return_60d=0.20, rs_spy=0.10),
            _sample_row("subindustry", "SubB", return_60d=-0.10, rs_spy=-0.05),
            _sample_row("subindustry", "SubC", return_60d=0.05, rs_spy=0.01),
        ],
    )
    ohlcv_db = tmp_path / "osakedata.db"
    _create_ohlcv_db(ohlcv_db)
    taxonomy_csv = _write_taxonomy_csv(tmp_path / "taxonomy.csv")
    rows = []
    from datetime import date, timedelta
    start = date(2026, 1, 1)
    for offset in range(131):
        current = (start + timedelta(days=offset)).isoformat()
        rows.append(("AAA", current, 1, 1, 1, 100 + offset, 1000, "usa"))
        rows.append(("BBB", current, 1, 1, 1, 200 + (offset * 2), 1000, "omxh"))
        if offset < 40:
            rows.append(("CCC", current, 1, 1, 1, 300 + offset, 1000, "usa"))
    _insert_ohlcv_rows(ohlcv_db, rows)

    output_md = tmp_path / "nested" / "report.md"
    output_csv = tmp_path / "nested" / "report.csv"
    exit_code = run_datacenter_index_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--as-of-date",
            "2026-05-11",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--include-ticker-performance",
            "--ohlcv-db",
            str(ohlcv_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--top-n",
            "2",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY include_ticker_performance=1" in lines
    assert "SUMMARY ticker_performance_rows=4" in lines
    assert "SUMMARY unique_ticker_count=3" in lines
    assert "SUMMARY ticker_return_60d_non_null=2" in lines
    assert "SUMMARY ticker_no_as_of_price_count=1" in lines
    assert "SUMMARY ticker_insufficient_60d_count=0" in lines

    markdown = output_md.read_text(encoding="utf-8")
    csv_report = output_csv.read_text(encoding="utf-8")
    assert "## 12. Ticker performance by subindustry" in markdown
    assert "## 13. Top tickers by 60d return" in markdown
    assert "## 14. Bottom tickers by 60d return" in markdown
    assert "ticker_performance_by_subindustry;SubA;LayerA;AAA;1;" in csv_report
    assert "top_ticker_return_60d;AAA;LayerA;SubA;" in csv_report
    assert "bottom_ticker_return_60d;AAA;LayerA;SubA;" in csv_report
