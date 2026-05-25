from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.ecosystem_dashboard_persistence import connect_dashboard_db, ensure_dashboard_schema
from dev_tools.run_ecosystem_dashboard_structured_source_audit import main


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_ticker_signal_snapshot (
                signal_date TEXT,
                ticker TEXT,
                action_bucket TEXT,
                action_label TEXT,
                trend_state TEXT,
                latest_structure_label TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT,
                group_type TEXT,
                group_name TEXT,
                timing_state TEXT,
                risk_state TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_decision_trace_events (
                signal_date TEXT,
                ticker TEXT,
                rule_name TEXT,
                reason TEXT
            )
            """
        )
        conn.execute("INSERT INTO dc_ticker_signal_snapshot VALUES ('2026-05-22', 'NVDA', 'WATCH', 'Watch', 'UP', 'HH')")
        conn.execute("INSERT INTO dc_group_swing_signal_daily VALUES ('2026-05-22', 'LAYER', 'Tech', 'BUY_ZONE', 'LOW')")
        conn.execute("INSERT INTO dc_decision_trace_events VALUES ('2026-05-22', 'NVDA', 'WATCH_MOMENTUM', 'momentum')")
        conn.commit()


def _create_dashboard_db(path: Path) -> None:
    conn = connect_dashboard_db(str(path))
    try:
        ensure_dashboard_schema(conn)
    finally:
        conn.close()


def _section_headers(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("section;")]


def _summary_value(output: str, key: str) -> str:
    prefix = f"SUMMARY structured_source_audit.{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    raise AssertionError(f"missing summary line for {key}")


def test_audit_with_no_db_paths_reports_not_provided_and_status_ok(capsys):
    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "source_databases;analysis_db;;NOT_PROVIDED;;not_provided" in output
    assert "source_databases;price_db;;NOT_PROVIDED;;not_provided" in output
    assert "source_databases;dashboard_db;;NOT_PROVIDED;;not_provided" in output
    assert "section_availability;source_reports;MISSING;;no matching analysis/price tables discovered" in output
    assert "SUMMARY structured_source_audit.status=OK" in output


def test_audit_with_missing_db_path_reports_missing_and_does_not_create_file(tmp_path, capsys):
    missing_db = tmp_path / "missing_analysis.db"

    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--analysis-db",
            str(missing_db),
        ]
    )

    assert exit_code == 0
    assert not missing_db.exists()
    output = capsys.readouterr().out
    assert f"source_databases;analysis_db;{missing_db};MISSING;;file_not_found" in output


def test_audit_opens_db_read_only_and_does_not_mutate_existing_db(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    before_size = analysis_db.stat().st_size

    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--analysis-db",
            str(analysis_db),
        ]
    )

    assert exit_code == 0
    assert analysis_db.stat().st_size == before_size


def test_audit_lists_relevant_tables_and_prints_all_section_availability_rows(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--analysis-db",
            str(analysis_db),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "source_tables;analysis_db;dc_decision_trace_events;1;signal_date,ticker,rule_name,reason" in output
    assert "source_tables;analysis_db;dc_group_swing_signal_daily;1;signal_date,group_type,group_name,timing_state,risk_state" in output
    assert "source_tables;analysis_db;dc_ticker_signal_snapshot;1;signal_date,ticker,action_bucket,action_label,trend_state,latest_structure_label" in output
    for section_name in (
        "source_reports",
        "action_summary",
        "market_map",
        "watchlist",
        "tickers",
        "decision_trace",
    ):
        assert f"section_availability;{section_name};" in output


def test_audit_recognizes_dashboard_db_as_final_snapshot_store_not_direct_source(
    tmp_path, capsys
):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    _create_dashboard_db(dashboard_db)

    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--dashboard-db",
            str(dashboard_db),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert (
        "section_availability;source_reports;PARTIAL_AVAILABLE;dashboard_db:ecosystem_dashboard_source_reports;final_snapshot_store_not_direct_structured_source"
        in output
    )
    assert (
        "section_availability;tickers;PARTIAL_AVAILABLE;dashboard_db:ecosystem_dashboard_ticker_status;final_snapshot_store_not_direct_structured_source"
        in output
    )


def test_output_sections_appear_in_exact_order(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--analysis-db",
            str(analysis_db),
        ]
    )

    assert exit_code == 0
    assert _section_headers(capsys.readouterr().out) == [
        "section;source_databases",
        "section;source_tables",
        "section;section_availability",
        "section;recommended_next_step",
        "section;summary",
    ]


def test_summary_counts_match_section_availability_statuses(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    _create_dashboard_db(dashboard_db)

    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--dashboard-db",
            str(dashboard_db),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    partial_lines = [
        line
        for line in output.splitlines()
        if line.startswith("section_availability;") and ";PARTIAL_AVAILABLE;" in line
    ]
    missing_lines = [
        line
        for line in output.splitlines()
        if line.startswith("section_availability;") and ";MISSING;" in line
    ]
    assert _summary_value(output, "direct_available_sections") == "0"
    assert _summary_value(output, "partial_available_sections") == str(len(partial_lines))
    assert _summary_value(output, "missing_sections") == str(len(missing_lines))


def test_unsupported_format_fails_clearly(capsys):
    exit_code = main(
        [
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--format",
            "csv",
        ]
    )

    assert exit_code == 2
    assert (
        "ERROR: unsupported format=csv; currently supported: text"
        in capsys.readouterr().out
    )
