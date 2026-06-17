import json
import sqlite3
from pathlib import Path

from rawcandle.cli import preflight_eco_legacy_db_cleanup as cli


def _create_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def test_no_eco_tables_text_output_exits_zero(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)

    exit_code = cli.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status=NO_ECO_TABLES_FOUND" in output
    assert "eco_table_count=0" in output
    assert "total_eco_rows=0" in output


def test_eco_tables_and_row_counts_are_reported(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE eco_report_run (run_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE eco_entity_metric_value (metric_id INTEGER PRIMARY KEY)")
        conn.execute("insert into eco_report_run (run_id) values ('RUN1')")
        conn.executemany(
            "insert into eco_entity_metric_value (metric_id) values (?)",
            [(1,), (2,)],
        )

    exit_code = cli.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status=ECO_TABLES_FOUND" in output
    assert "eco_table_count=2" in output
    assert "total_eco_rows=3" in output
    assert "  eco_entity_metric_value: 2" in output
    assert "  eco_report_run: 1" in output


def test_json_output_is_valid_and_deterministic(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE eco_b (id INTEGER)")
        conn.execute("CREATE TABLE eco_a (id INTEGER)")
        conn.execute("insert into eco_b (id) values (1)")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    first_output = capsys.readouterr().out
    second_exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    second_output = capsys.readouterr().out

    assert exit_code == 0
    assert second_exit_code == 0
    assert first_output == second_output
    payload = json.loads(first_output)
    assert payload["status"] == "ECO_TABLES_FOUND"
    assert payload["eco_tables"] == [
        {"row_count": 0, "table": "eco_a"},
        {"row_count": 1, "table": "eco_b"},
    ]


def test_fail_if_eco_tables_exits_two_after_report(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE eco_report_run (run_id TEXT)")

    exit_code = cli.main(["--db", str(db_path), "--fail-if-eco-tables"])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "status=ECO_TABLES_FOUND" in output


def test_related_indexes_triggers_and_views_are_reported(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE eco_report_run (run_id TEXT PRIMARY KEY, status TEXT)")
        conn.execute("CREATE INDEX idx_eco_report_run_status ON eco_report_run (status)")
        conn.execute("CREATE TABLE audit_log (message TEXT)")
        conn.execute(
            """
            CREATE TRIGGER trg_eco_report_run_insert
            AFTER INSERT ON eco_report_run
            BEGIN
                insert into audit_log (message) values ('eco_report_run');
            END
            """
        )
        conn.execute("CREATE VIEW view_eco_report_run AS SELECT run_id FROM eco_report_run")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["related_schema_objects"]["indexes"] == [
        {"name": "idx_eco_report_run_status", "table": "eco_report_run"},
        {"name": "sqlite_autoindex_eco_report_run_1", "table": "eco_report_run"},
    ]
    assert payload["related_schema_objects"]["triggers"] == [
        {"name": "trg_eco_report_run_insert", "table": "eco_report_run"}
    ]
    assert payload["related_schema_objects"]["views"] == ["view_eco_report_run"]


def test_missing_db_path_exits_one(capsys, tmp_path):
    missing_path = tmp_path / "missing.db"

    exit_code = cli.main(["--db", str(missing_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "ERROR: Missing db:" in output


def test_read_only_behavior_does_not_modify_schema(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE eco_report_run (run_id TEXT)")
        before_tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])

    with sqlite3.connect(db_path) as conn:
        after_tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]

    assert exit_code == 0
    assert after_tables == before_tables


def test_identifier_quoting_handles_unusual_eco_table_names(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    unusual_name = 'eco_odd"name'
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE "eco_odd""name" (id INTEGER)')
        conn.execute('insert into "eco_odd""name" (id) values (1)')

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["eco_tables"] == [{"row_count": 1, "table": unusual_name}]
