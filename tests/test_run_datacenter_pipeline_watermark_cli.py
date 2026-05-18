from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark
from run_datacenter_pipeline_watermark import main as run_datacenter_pipeline_watermark_main


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def test_list_mode_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2020-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    exit_code = run_datacenter_pipeline_watermark_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY taxonomy_version=DC_TAXONOMY_FULL_V1"
    assert lines[1] == "SUMMARY component_count=1"
    assert lines[2] == "SUMMARY validation_status=OK"
    assert lines[4].startswith("GROUP_INDEX | usa |  |  | 2020-01-01 | 2026-05-15 | OK |")


def test_component_filter_works(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2020-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="DAILY_REPORT",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2026-05-15",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:10:00Z",
    )

    exit_code = run_datacenter_pipeline_watermark_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--component-name",
            "DAILY_REPORT",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[1] == "SUMMARY component_count=1"
    assert "DAILY_REPORT" in lines[4]
    assert "GROUP_INDEX" not in "\n".join(lines)


def test_cli_is_read_only(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2020-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    with sqlite3.connect(analysis_db) as conn:
        before = conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0]

    exit_code = run_datacenter_pipeline_watermark_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    with sqlite3.connect(analysis_db) as conn:
        after = conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0]

    assert exit_code == 0
    assert before == after
