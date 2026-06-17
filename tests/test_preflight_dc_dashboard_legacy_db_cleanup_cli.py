import json
import sqlite3
from pathlib import Path

from rawcandle.cli import preflight_dc_dashboard_legacy_db_cleanup as cli


def _create_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _table_names(path: Path) -> list[str]:
    with sqlite3.connect(path) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]


def test_no_legacy_snapshot_tables_text_output_exits_zero(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)

    exit_code = cli.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status=NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND" in output
    assert "legacy_snapshot_table_count=0" in output
    assert "total_legacy_snapshot_rows=0" in output


def test_legacy_snapshot_tables_and_row_counts_are_reported(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_runs (run_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE dc_dashboard_ticker_status (ticker TEXT)")
        conn.execute("insert into dc_dashboard_runs (run_id) values ('RUN1')")
        conn.executemany(
            "insert into dc_dashboard_ticker_status (ticker) values (?)",
            [("AAA",), ("BBB",)],
        )

    exit_code = cli.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status=LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND" in output
    assert "legacy_snapshot_table_count=2" in output
    assert "total_legacy_snapshot_rows=3" in output
    assert "  dc_dashboard_runs: 1" in output
    assert "  dc_dashboard_ticker_status: 2" in output


def test_current_daily_tables_are_preserved_not_legacy_candidates(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_ticker_enrichment_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_dashboard_group_enrichment_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_dashboard_action_summary_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_dashboard_decision_trace_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_dashboard_enrichment_run_daily (id INTEGER)")
        conn.executemany(
            "insert into dc_dashboard_ticker_enrichment_daily (id) values (?)",
            [(1,), (2,)],
        )

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND"
    assert payload["legacy_snapshot_tables"] == []
    assert payload["current_dashboard_table_presence"] == [
        {"present": True, "row_count": 0, "table": "dc_dashboard_action_summary_daily"},
        {"present": True, "row_count": 0, "table": "dc_dashboard_decision_trace_daily"},
        {"present": True, "row_count": 0, "table": "dc_dashboard_enrichment_run_daily"},
        {"present": True, "row_count": 0, "table": "dc_dashboard_group_enrichment_daily"},
        {"present": True, "row_count": 2, "table": "dc_dashboard_ticker_enrichment_daily"},
    ]


def test_other_dc_dashboard_like_tables_are_unknown_review_required(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_ticker_rolling5_pullback_daily (id INTEGER)")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["legacy_snapshot_tables"] == []
    assert payload["other_dc_dashboard_like_tables"] == [
        {
            "classification": "UNKNOWN_REVIEW_REQUIRED",
            "table": "dc_dashboard_ticker_rolling5_pullback_daily",
        }
    ]


def test_json_output_is_valid_and_deterministic(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_source_reports (id INTEGER)")
        conn.execute("CREATE TABLE dc_dashboard_market_map (id INTEGER)")
        conn.execute("insert into dc_dashboard_market_map (id) values (1)")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    first_output = capsys.readouterr().out
    second_exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    second_output = capsys.readouterr().out

    assert exit_code == 0
    assert second_exit_code == 0
    assert first_output == second_output
    payload = json.loads(first_output)
    assert payload["status"] == "LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND"
    assert payload["legacy_snapshot_tables"] == [
        {"row_count": 1, "table": "dc_dashboard_market_map"},
        {"row_count": 0, "table": "dc_dashboard_source_reports"},
    ]


def test_fail_if_legacy_snapshot_tables_exits_two_after_report(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_runs (run_id TEXT)")

    exit_code = cli.main(["--db", str(db_path), "--fail-if-legacy-snapshot-tables"])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "status=LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND" in output


def test_related_indexes_triggers_and_views_are_reported(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_runs (run_id TEXT PRIMARY KEY, status TEXT)")
        conn.execute("CREATE INDEX idx_dc_dashboard_runs_status ON dc_dashboard_runs (status)")
        conn.execute("CREATE TABLE audit_log (message TEXT)")
        conn.execute(
            """
            CREATE TRIGGER trg_dc_dashboard_runs_insert
            AFTER INSERT ON dc_dashboard_runs
            BEGIN
                insert into audit_log (message) values ('dc_dashboard_runs');
            END
            """
        )
        conn.execute("CREATE VIEW view_dc_dashboard_runs AS SELECT run_id FROM dc_dashboard_runs")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["related_schema_objects"]["indexes"] == [
        {"name": "idx_dc_dashboard_runs_status", "table": "dc_dashboard_runs"},
        {"name": "sqlite_autoindex_dc_dashboard_runs_1", "table": "dc_dashboard_runs"},
    ]
    assert payload["related_schema_objects"]["triggers"] == [
        {"name": "trg_dc_dashboard_runs_insert", "table": "dc_dashboard_runs"}
    ]
    assert payload["related_schema_objects"]["views"] == ["view_dc_dashboard_runs"]


def test_current_decision_trace_daily_does_not_match_legacy_decision_trace(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_decision_trace_daily (id INTEGER)")
        conn.execute(
            "CREATE VIEW view_current_decision_trace AS "
            "SELECT id FROM dc_dashboard_decision_trace_daily"
        )

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["legacy_snapshot_tables"] == []
    assert payload["related_schema_objects"]["views"] == []


def test_missing_db_path_exits_one(capsys, tmp_path):
    missing_path = tmp_path / "missing.db"

    exit_code = cli.main(["--db", str(missing_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "ERROR: Missing db:" in output


def test_read_only_behavior_does_not_modify_schema(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_dashboard_runs (run_id TEXT)")
    before_tables = _table_names(db_path)

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])

    after_tables = _table_names(db_path)
    assert exit_code == 0
    assert after_tables == before_tables


def test_identifier_quoting_handles_unusual_known_table_name(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    unusual_name = 'dc_dashboard_odd"name'
    monkeypatch.setattr(cli, "LEGACY_SNAPSHOT_TABLES", (unusual_name,))
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE "dc_dashboard_odd""name" (id INTEGER)')
        conn.execute('insert into "dc_dashboard_odd""name" (id) values (1)')

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["legacy_snapshot_tables"] == [{"row_count": 1, "table": unusual_name}]
