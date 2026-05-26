import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_audit import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_empty_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_schema_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _count_rows(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def _insert_selected_rows(db_path: Path, *, signal_date: str = "2026-05-22") -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, is_watchlist,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "WATCH",
                0,
                "OK",
                "V1",
                "RUN_001",
                "2026-05-26T10:00:00Z",
            ),
        )


def _insert_all_section_rows(db_path: Path, *, signal_date: str = "2026-05-22") -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, is_watchlist,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "WATCH",
                1,
                "OK",
                "V1",
                "RUN_001",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "LAYER",
                "DC_ECOSYSTEM_TOTAL > Infrastructure",
                "Infrastructure",
                "OK",
                "V1",
                "RUN_001",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date, taxonomy_version, action, count, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "WATCH",
                1,
                "V1",
                "RUN_001",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_decision_trace_daily (
                signal_date, taxonomy_version, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                0,
                "WATCH",
                "WATCH_RULE",
                "signal",
                "1",
                "daily",
                "momentum",
                "V1",
                "RUN_001",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_enrichment_run_daily (
                run_id, signal_date, taxonomy_version, status, readiness,
                ticker_rows, group_rows, action_summary_rows, decision_trace_rows,
                warnings, calc_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RUN_001",
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "OK",
                "READY",
                1,
                1,
                1,
                1,
                None,
                "V1",
                "2026-05-26T10:00:00Z",
            ),
        )


def test_missing_analysis_db_fails_clearly_and_does_not_create_file(tmp_path, capsys):
    db_path = tmp_path / "missing-analysis.db"

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not db_path.exists()
    assert captured.out == ""
    assert "analysis_db not found:" in captured.err


def test_empty_db_with_no_enrichment_tables_reports_missing_tables(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_empty_db(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert f"database;{db_path};OK;0;" in output
    assert "tables;dc_dashboard_ticker_enrichment_daily;0;;;MISSING" in output
    assert "section_readiness;ticker_enrichment;MISSING_TABLE;;expected_table_missing" in output
    assert "section_readiness;overall;MISSING_TABLES;0;missing_expected_tables" in output
    assert (
        "warnings;MISSING_EXPECTED_TABLES;dc_dashboard_ticker_enrichment_daily,"
        "dc_dashboard_group_enrichment_daily,dc_dashboard_action_summary_daily,"
        "dc_dashboard_decision_trace_daily,dc_dashboard_enrichment_run_daily"
    ) in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.readiness=MISSING_TABLES" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.status=OK" in output


def test_schema_applied_but_no_rows_reports_empty(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "tables;dc_dashboard_ticker_enrichment_daily;1;0;0;OK" in output
    assert "section_readiness;ticker_enrichment;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;group_enrichment;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;action_summary;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;decision_trace;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;enrichment_run;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;EMPTY;0;all_sections_empty" in output
    assert "warnings;NO_ENRICHMENT_ROWS_FOR_SELECTION;2026-05-22|DC_TAXONOMY_FULL_V1" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.status=OK" in output


def test_db_with_one_ticker_enrichment_row_only_reports_partial(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)
    _insert_selected_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "section_readiness;ticker_enrichment;READY;1;rows_available" in output
    assert "section_readiness;group_enrichment;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;PARTIAL;1;some_sections_empty" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.ticker_rows=1" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.status=OK" in output


def test_db_with_all_five_sections_ready_reports_ready(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)
    _insert_all_section_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "section_readiness;ticker_enrichment;READY;1;rows_available" in output
    assert "section_readiness;group_enrichment;READY;1;rows_available" in output
    assert "section_readiness;action_summary;READY;1;rows_available" in output
    assert "section_readiness;decision_trace;READY;1;rows_available" in output
    assert "section_readiness;enrichment_run;READY;1;rows_available" in output
    assert "section_readiness;overall;READY;5;all_sections_ready" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.status=OK" in output


def test_rows_for_different_signal_date_report_empty_for_selected_date(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)
    _insert_selected_rows(db_path, signal_date="2026-05-21")

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "tables;dc_dashboard_ticker_enrichment_daily;1;1;0;OK" in output
    assert "section_readiness;ticker_enrichment;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;EMPTY;0;all_sections_empty" in output
    assert "warnings;NO_ENRICHMENT_ROWS_FOR_SELECTION;2026-05-22|DC_TAXONOMY_FULL_V1" in output


def test_old_snapshot_table_warning_is_reported_but_not_deleted(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_runs (run_id TEXT PRIMARY KEY)")

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "warnings;OLD_DASHBOARD_SNAPSHOT_TABLES_PRESENT;dc_dashboard_runs" in output
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dc_dashboard_runs'"
        ).fetchone()
    assert row is not None


def test_unsupported_format_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "unsupported format=json; currently supported: text" in captured.err


def test_audit_is_read_only_and_does_not_mutate_row_counts(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_schema_db(db_path)
    _insert_selected_rows(db_path)
    before_counts = {
        "dc_dashboard_ticker_enrichment_daily": _count_rows(
            db_path, "dc_dashboard_ticker_enrichment_daily"
        ),
        "dc_dashboard_group_enrichment_daily": _count_rows(
            db_path, "dc_dashboard_group_enrichment_daily"
        ),
        "dc_dashboard_action_summary_daily": _count_rows(
            db_path, "dc_dashboard_action_summary_daily"
        ),
        "dc_dashboard_decision_trace_daily": _count_rows(
            db_path, "dc_dashboard_decision_trace_daily"
        ),
        "dc_dashboard_enrichment_run_daily": _count_rows(
            db_path, "dc_dashboard_enrichment_run_daily"
        ),
    }

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    after_counts = {
        table_name: _count_rows(db_path, table_name) for table_name in before_counts
    }
    assert after_counts == before_counts
