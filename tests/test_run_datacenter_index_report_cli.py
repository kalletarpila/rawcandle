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
            _sample_row("layer", "Pilvi", return_60d=-0.10, data_quality_status="PARTIAL_DATA", eligible_count=6),
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
        f"SUMMARY output_md={output_md}",
        f"SUMMARY output_csv={output_csv}",
        "SUMMARY report_status=OK",
    ]

    markdown = output_md.read_text(encoding="utf-8")
    csv_report = output_csv.read_text(encoding="utf-8")
    assert "## 6. Top subindustries by 60d return" in markdown
    assert "section;metric;value" in csv_report
    assert "top_subindustry_return_60d;UPS;" in csv_report
