from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark
from run_datacenter_swing_pipeline_plan import main as run_datacenter_swing_pipeline_plan_main


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def test_cli_prints_deterministic_summary_lines_and_component_table(tmp_path, capsys):
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

    exit_code = run_datacenter_swing_pipeline_plan_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--market",
            "usa",
            "--signal-date",
            "2026-05-15",
            "--start-date",
            "2026-01-01",
            "--index-base-date",
            "2020-01-01",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2026-05-15"
    assert lines[1] == "SUMMARY start_date=2026-01-01"
    assert lines[2] == "SUMMARY index_base_date=2020-01-01"
    assert lines[12] == "SUMMARY validation_status=OK"
    assert lines[13].startswith("component_name | plan_action |")
    assert lines[14].startswith("GROUP_INDEX | UP_TO_DATE | 2020-01-01 | 2026-05-15 |")


def test_missing_watermark_table_returns_fail_and_nonzero(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(analysis_db) as conn:
        conn.execute("CREATE TABLE placeholder (id INTEGER)")
        conn.commit()

    exit_code = run_datacenter_swing_pipeline_plan_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--market",
            "usa",
            "--signal-date",
            "2026-05-15",
            "--start-date",
            "2026-01-01",
            "--index-base-date",
            "2020-01-01",
        ]
    )

    assert exit_code != 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1] == "SUMMARY validation_status=FAIL"


def test_cli_is_read_only(tmp_path):
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

    with sqlite3.connect(analysis_db) as conn:
        before = conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0]

    exit_code = run_datacenter_swing_pipeline_plan_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--market",
            "usa",
            "--signal-date",
            "2026-05-15",
            "--start-date",
            "2026-01-01",
            "--index-base-date",
            "2020-01-01",
        ]
    )

    with sqlite3.connect(analysis_db) as conn:
        after = conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0]

    assert exit_code == 0
    assert before == after
