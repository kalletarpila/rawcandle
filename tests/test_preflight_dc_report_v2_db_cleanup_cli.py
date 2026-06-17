import json
import sqlite3
from pathlib import Path

from rawcandle.cli import preflight_dc_report_v2_db_cleanup as cli


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


def test_no_v2_tables_text_output_exits_zero(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)

    exit_code = cli.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status=NO_DC_REPORT_V2_TABLES_FOUND" in output
    assert "v2_table_count=0" in output
    assert "total_v2_rows=0" in output


def test_v2_tables_and_row_counts_are_reported(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_report_run_v2 (run_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE dc_report_context_daily_v2 (id INTEGER PRIMARY KEY)")
        conn.execute("insert into dc_report_run_v2 (run_id) values ('RUN1')")
        conn.executemany(
            "insert into dc_report_context_daily_v2 (id) values (?)",
            [(1,), (2,)],
        )

    exit_code = cli.main(["--db", str(db_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "status=DC_REPORT_V2_TABLES_FOUND" in output
    assert "v2_table_count=2" in output
    assert "total_v2_rows=3" in output
    assert "  dc_report_context_daily_v2: 2" in output
    assert "  dc_report_run_v2: 1" in output


def test_current_dc_source_facts_are_preserved_not_v2_tables(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_ticker_swing_signal_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_group_swing_signal_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_group_synthetic_ohlc_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_group_index_daily (id INTEGER)")
        conn.execute("CREATE TABLE dc_pipeline_watermark (id INTEGER)")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "NO_DC_REPORT_V2_TABLES_FOUND"
    assert payload["v2_tables"] == []
    assert payload["preserved_current_tables"]["dc_source_facts"] == [
        {"present": True, "table": "dc_group_index_daily"},
        {"present": True, "table": "dc_group_swing_signal_daily"},
        {"present": True, "table": "dc_group_synthetic_ohlc_daily"},
        {"present": True, "table": "dc_pipeline_watermark"},
        {"present": True, "table": "dc_ticker_swing_signal_daily"},
    ]


def test_current_ec_key_tables_are_preserved_not_v2_tables(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE ec_ticker_signal_daily (id INTEGER)")
        conn.execute("CREATE TABLE ec_group_signal_daily (id INTEGER)")
        conn.execute("CREATE TABLE ec_group_synthetic_ohlc_daily (id INTEGER)")
        conn.execute("CREATE TABLE ec_group_index_daily (id INTEGER)")
        conn.execute("CREATE TABLE ec_pipeline_watermark (id INTEGER)")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "NO_DC_REPORT_V2_TABLES_FOUND"
    assert payload["v2_tables"] == []
    assert payload["preserved_current_tables"]["ec_key_tables"] == [
        {"present": True, "table": "ec_group_index_daily"},
        {"present": True, "table": "ec_group_signal_daily"},
        {"present": True, "table": "ec_group_synthetic_ohlc_daily"},
        {"present": True, "table": "ec_pipeline_watermark"},
        {"present": True, "table": "ec_ticker_signal_daily"},
    ]


def test_json_output_is_valid_and_deterministic(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_report_run_v2 (run_id TEXT)")
        conn.execute("CREATE TABLE dc_report_context_window_v2 (id INTEGER)")
        conn.execute("insert into dc_report_context_window_v2 (id) values (1)")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    first_output = capsys.readouterr().out
    second_exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    second_output = capsys.readouterr().out

    assert exit_code == 0
    assert second_exit_code == 0
    assert first_output == second_output
    payload = json.loads(first_output)
    assert payload["status"] == "DC_REPORT_V2_TABLES_FOUND"
    assert payload["v2_tables"] == [
        {"row_count": 1, "table": "dc_report_context_window_v2"},
        {"row_count": 0, "table": "dc_report_run_v2"},
    ]


def test_fail_if_v2_tables_exits_two_after_report(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_report_run_v2 (run_id TEXT)")

    exit_code = cli.main(["--db", str(db_path), "--fail-if-v2-tables"])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "status=DC_REPORT_V2_TABLES_FOUND" in output


def test_related_indexes_triggers_and_views_are_reported(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_report_run_v2 (run_id TEXT PRIMARY KEY, status TEXT)")
        conn.execute("CREATE INDEX idx_dc_report_run_v2_status ON dc_report_run_v2 (status)")
        conn.execute("CREATE TABLE audit_log (message TEXT)")
        conn.execute(
            """
            CREATE TRIGGER trg_dc_report_run_v2_insert
            AFTER INSERT ON dc_report_run_v2
            BEGIN
                insert into audit_log (message) values ('dc_report_run_v2');
            END
            """
        )
        conn.execute("CREATE VIEW view_dc_report_run_v2 AS SELECT run_id FROM dc_report_run_v2")

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["related_schema_objects"]["indexes"] == [
        {"name": "idx_dc_report_run_v2_status", "table": "dc_report_run_v2"},
        {"name": "sqlite_autoindex_dc_report_run_v2_1", "table": "dc_report_run_v2"},
    ]
    assert payload["related_schema_objects"]["triggers"] == [
        {"name": "trg_dc_report_run_v2_insert", "table": "dc_report_run_v2"}
    ]
    assert payload["related_schema_objects"]["views"] == ["view_dc_report_run_v2"]


def test_missing_db_path_exits_one(capsys, tmp_path):
    missing_path = tmp_path / "missing.db"

    exit_code = cli.main(["--db", str(missing_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "ERROR: Missing db:" in output


def test_read_only_behavior_does_not_modify_schema(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_report_run_v2 (run_id TEXT)")
    before_tables = _table_names(db_path)

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])

    after_tables = _table_names(db_path)
    assert exit_code == 0
    assert after_tables == before_tables


def test_identifier_quoting_handles_unusual_known_table_name(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    unusual_name = 'dc_report_odd"name_v2'
    monkeypatch.setattr(cli, "KNOWN_V2_TABLES", (unusual_name,))
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE "dc_report_odd""name_v2" (id INTEGER)')
        conn.execute('insert into "dc_report_odd""name_v2" (id) values (1)')

    exit_code = cli.main(["--db", str(db_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["v2_tables"] == [{"row_count": 1, "table": unusual_name}]
