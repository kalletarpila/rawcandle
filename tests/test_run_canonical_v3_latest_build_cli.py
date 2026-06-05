from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli import run_canonical_v3_latest_build as cli


ACCEPTED_ECO_TARGET_TABLES = (
    "eco_report_run",
    "eco_entity_coverage",
    "eco_quality_summary",
    "eco_entity_window_snapshot",
    "eco_entity_metric_value",
    "eco_classification_decision",
    "eco_signal_observation",
    "eco_signal_relevance",
    "eco_entity_event",
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _create_control_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE eco_ecosystem (
            ecosystem_id INTEGER PRIMARY KEY,
            ecosystem_code TEXT NOT NULL,
            ecosystem_name TEXT,
            status TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE eco_taxonomy_version (
            taxonomy_version_id INTEGER PRIMARY KEY,
            ecosystem_id INTEGER NOT NULL,
            version_code TEXT NOT NULL,
            status TEXT,
            is_active INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO eco_ecosystem (ecosystem_id, ecosystem_code, ecosystem_name, status)
        VALUES (1, 'DATACENTER', 'Datacenter', 'ACTIVE')
        """
    )
    conn.execute(
        """
        INSERT INTO eco_taxonomy_version (taxonomy_version_id, ecosystem_id, version_code, status, is_active)
        VALUES (1, 1, 'DC_TAXONOMY_FULL_V1', 'ACTIVE', 1)
        """
    )


def _create_target_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE eco_report_run (
            run_id TEXT PRIMARY KEY,
            signal_date TEXT,
            status TEXT
        )
        """
    )
    conn.execute("CREATE TABLE eco_entity_coverage (run_id TEXT)")
    conn.execute("CREATE TABLE eco_quality_summary (run_id TEXT)")
    conn.execute("CREATE TABLE eco_entity_window_snapshot (run_id TEXT, source_run_id TEXT)")
    conn.execute("CREATE TABLE eco_entity_metric_value (run_id TEXT, source_run_id TEXT)")
    conn.execute("CREATE TABLE eco_classification_decision (run_id TEXT, source_run_id TEXT)")
    conn.execute(
        """
        CREATE TABLE eco_signal_observation (
            signal_observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            source_table TEXT,
            source_run_id TEXT
        )
        """
    )
    conn.execute("CREATE TABLE eco_signal_relevance (signal_observation_id INTEGER)")
    conn.execute("CREATE TABLE eco_entity_event (run_id TEXT, source_table TEXT, source_run_id TEXT)")


def _create_allowed_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE technical_signal_relevance (
            run_id TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            ticker TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            signal_source_type TEXT NOT NULL,
            signal_source_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            event_date TEXT NOT NULL,
            run_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_index_daily (
            index_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )


def _create_forbidden_tables(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE dc_report_context_daily_v2 (signal_date TEXT NOT NULL)")
    conn.execute("CREATE TABLE dc_report_context_window_v2 (signal_date TEXT NOT NULL)")
    conn.execute("CREATE TABLE dc_report_context_group_v2 (signal_date TEXT NOT NULL)")
    conn.execute("CREATE TABLE dc_report_classification_v2 (signal_date TEXT NOT NULL)")
    conn.execute("CREATE TABLE dc_dashboard_action_summary_daily (signal_date TEXT NOT NULL)")


def _insert_ready_sources(conn: sqlite3.Connection, signal_date: str) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (signal_date, taxonomy_version, ticker, run_id)
        VALUES (?, 'DC_TAXONOMY_FULL_V1', 'NVDA', 'DC_TICKER_SWING_20260604_DC_SWING_SIGNAL_V1')
        """,
        (signal_date,),
    )
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (signal_date, taxonomy_version, group_type, group_name, run_id)
        VALUES (?, 'DC_TAXONOMY_FULL_V1', 'layer', 'AI_INFRA', 'DC_GROUP_SWING_20260604_DC_SWING_SIGNAL_V1')
        """,
        (signal_date,),
    )
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (ohlc_date, taxonomy_version, group_type, group_name, run_id)
        VALUES (?, 'DC_TAXONOMY_FULL_V1', 'layer', 'AI_INFRA', 'DC_GROUP_SYNTH_OHLC_20250801_20260604_DC_SWING_OHLC_V1')
        """,
        (signal_date,),
    )
    conn.execute(
        """
        INSERT INTO technical_signal_relevance (
            run_id, signal_date, timeframe, ticker, signal_name, signal_source_type, signal_source_id
        ) VALUES (
            'DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_06_04', ?, '1d', 'NVDA', 'MA_STATUS', 'TICKER', 'src-1'
        )
        """,
        (signal_date,),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (ticker, event_date, run_id)
        VALUES ('NVDA', ?, 'stock-dow-run')
        """,
        (signal_date,),
    )
    conn.execute(
        """
        INSERT INTO dc_group_index_daily (index_date, taxonomy_version, group_type, group_name, run_id)
        VALUES (?, 'DC_TAXONOMY_FULL_V1', 'layer', 'AI_INFRA', 'DC_INDEX_DC_TAXONOMY_FULL_V1_BASE20200101_20200101_20260604')
        """,
        (signal_date,),
    )
    conn.execute("INSERT INTO dc_report_context_daily_v2 (signal_date) VALUES (?)", (signal_date,))
    conn.execute("INSERT INTO dc_dashboard_action_summary_daily (signal_date) VALUES (?)", (signal_date,))


def _create_fixture_db(db_path: str, *, signal_date: str = "2026-06-04") -> None:
    conn = _connect(db_path)
    try:
        _create_control_tables(conn)
        _create_target_tables(conn)
        _create_allowed_source_tables(conn)
        _create_forbidden_tables(conn)
        _insert_ready_sources(conn, signal_date)
        conn.commit()
    finally:
        conn.close()


def _insert_existing_run(db_path: str, run_id: str, signal_date: str = "2026-06-04") -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO eco_report_run (run_id, signal_date, status) VALUES (?, ?, 'OK')",
            (run_id, signal_date),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_existing_runtime_rows(db_path: str, run_id: str, other_run_id: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute("INSERT INTO eco_entity_coverage (run_id) VALUES (?)", (run_id,))
        conn.execute("INSERT INTO eco_entity_coverage (run_id) VALUES (?)", (other_run_id,))
        conn.execute("INSERT INTO eco_quality_summary (run_id) VALUES (?)", (run_id,))
        conn.execute("INSERT INTO eco_quality_summary (run_id) VALUES (?)", (other_run_id,))
        conn.execute(
            "INSERT INTO eco_entity_window_snapshot (run_id, source_run_id) VALUES (?, 'TARGET_SOURCE')",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO eco_entity_window_snapshot (run_id, source_run_id) VALUES (?, 'OTHER_SOURCE')",
            (other_run_id,),
        )
        conn.execute(
            "INSERT INTO eco_entity_metric_value (run_id, source_run_id) VALUES (?, 'TARGET_SOURCE')",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO eco_entity_metric_value (run_id, source_run_id) VALUES (?, 'OTHER_SOURCE')",
            (other_run_id,),
        )
        conn.execute(
            "INSERT INTO eco_classification_decision (run_id, source_run_id) VALUES (?, 'TARGET_SOURCE')",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO eco_classification_decision (run_id, source_run_id) VALUES (?, 'OTHER_SOURCE')",
            (other_run_id,),
        )
        conn.execute(
            "INSERT INTO eco_signal_observation (run_id, source_table, source_run_id) VALUES (?, 'allowed_source', 'TARGET_SOURCE')",
            (run_id,),
        )
        target_observation_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO eco_signal_observation (run_id, source_table, source_run_id) VALUES (?, 'allowed_source', 'OTHER_SOURCE')",
            (other_run_id,),
        )
        other_observation_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO eco_signal_relevance (signal_observation_id) VALUES (?)",
            (target_observation_id,),
        )
        conn.execute(
            "INSERT INTO eco_signal_relevance (signal_observation_id) VALUES (?)",
            (other_observation_id,),
        )
        conn.execute(
            "INSERT INTO eco_entity_event (run_id, source_table, source_run_id) VALUES (?, 'allowed_source', 'TARGET_SOURCE')",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO eco_entity_event (run_id, source_table, source_run_id) VALUES (?, 'allowed_source', 'OTHER_SOURCE')",
            (other_run_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_ambiguous_technical_relevance_runs(db_path: str, signal_date: str = "2026-06-04") -> None:
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM technical_signal_relevance")
        conn.execute(
            """
            INSERT INTO technical_signal_relevance (
                run_id, signal_date, timeframe, ticker, signal_name, signal_source_type, signal_source_id
            ) VALUES ('ALT_ONE', ?, '1d', 'NVDA', 'MA_STATUS', 'TICKER', 'src-1')
            """,
            (signal_date,),
        )
        conn.execute(
            """
            INSERT INTO technical_signal_relevance (
                run_id, signal_date, timeframe, ticker, signal_name, signal_source_type, signal_source_id
            ) VALUES ('ALT_TWO', ?, '1d', 'NVDA', 'MA_STATUS', 'TICKER', 'src-2')
            """,
            (signal_date,),
        )
        conn.commit()
    finally:
        conn.close()


def _base_args(db_path: Path, backup_dir: Path) -> list[str]:
    run_id = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
    return [
        "--db",
        str(db_path),
        "--ecosystem",
        "DATACENTER",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--signal-date",
        "2026-06-04",
        "--run-id",
        run_id,
        "--confirm-run-id",
        run_id,
        "--backup-dir",
        str(backup_dir),
        "--format",
        "text",
    ]


def _install_success_builder_stubs(monkeypatch: pytest.MonkeyPatch, db_path: Path, call_order: list[str]) -> None:
    target_tables_by_builder = {
        "build_canonical_v3_base_run": ("eco_report_run", "eco_entity_coverage", "eco_quality_summary"),
        "build_canonical_v3_ticker_daily_direct_metrics": ("eco_entity_metric_value",),
        "build_canonical_v3_group_status_from_group_swing": ("eco_entity_metric_value",),
        "build_canonical_v3_group_window_status_from_group_swing": ("eco_entity_metric_value",),
        "build_canonical_v3_ticker_window_metrics": ("eco_entity_metric_value",),
        "build_canonical_v3_group_window_metrics": ("eco_entity_metric_value",),
        "build_canonical_v3_group_historical_metrics": ("eco_entity_metric_value",),
        "build_canonical_v3_ticker_freshness_from_signal_daily": ("eco_entity_metric_value", "eco_signal_observation"),
        "build_canonical_v3_daily_trigger_classifications": ("eco_classification_decision",),
        "build_canonical_v3_rolling2_sell_pressure_classifications": ("eco_classification_decision",),
        "build_canonical_v3_rolling5_pullback_classifications": ("eco_classification_decision",),
        "build_canonical_v3_rolling30_watchlist_classifications": ("eco_classification_decision",),
        "build_canonical_v3_window_snapshots": ("eco_entity_window_snapshot",),
        "build_canonical_v3_ma_status": ("eco_signal_observation",),
        "build_canonical_v3_ma_break_status": ("eco_signal_observation",),
        "build_canonical_v3_signal_relevance": ("eco_signal_observation", "eco_signal_relevance"),
        "build_canonical_v3_ticker_structure_events": ("eco_entity_event",),
        "build_canonical_v3_group_structure_events": ("eco_entity_event",),
    }

    def make_stub(builder_name: str):
        def _stub(**kwargs):
            call_order.append(builder_name)
            conn = _connect(str(db_path))
            try:
                run_id = str(kwargs.get("run_id", ""))
                signal_date = "2026-06-04"
                for table_name in target_tables_by_builder[builder_name]:
                    if table_name == "eco_report_run":
                        conn.execute(
                            "INSERT OR REPLACE INTO eco_report_run (run_id, signal_date, status) VALUES (?, ?, 'OK')",
                            (run_id, signal_date),
                        )
                    elif table_name == "eco_signal_observation":
                        conn.execute(
                            """
                            INSERT INTO eco_signal_observation (run_id, source_table, source_run_id)
                            VALUES (?, 'allowed_source', 'ALLOWED_SOURCE_RUN')
                            """,
                            (run_id,),
                        )
                    elif table_name == "eco_signal_relevance":
                        observation_row = conn.execute(
                            "SELECT signal_observation_id FROM eco_signal_observation WHERE run_id = ? ORDER BY signal_observation_id LIMIT 1",
                            (run_id,),
                        ).fetchone()
                        if observation_row is None:
                            conn.execute(
                                """
                                INSERT INTO eco_signal_observation (run_id, source_table, source_run_id)
                                VALUES (?, 'allowed_source', 'ALLOWED_SOURCE_RUN')
                                """,
                                (run_id,),
                            )
                            observation_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                        else:
                            observation_id = int(observation_row["signal_observation_id"])
                        conn.execute(
                            "INSERT INTO eco_signal_relevance (signal_observation_id) VALUES (?)",
                            (observation_id,),
                        )
                    elif table_name == "eco_entity_event":
                        conn.execute(
                            """
                            INSERT INTO eco_entity_event (run_id, source_table, source_run_id)
                            VALUES (?, 'allowed_source', 'ALLOWED_SOURCE_RUN')
                            """,
                            (run_id,),
                        )
                    else:
                        columns = {
                            str(row["name"])
                            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                        }
                        insert_columns = ["run_id"]
                        insert_values = [run_id]
                        if "source_run_id" in columns:
                            insert_columns.append("source_run_id")
                            insert_values.append("ALLOWED_SOURCE_RUN")
                        placeholders = ", ".join("?" for _ in insert_values)
                        conn.execute(
                            f"INSERT INTO {table_name} ({', '.join(insert_columns)}) VALUES ({placeholders})",
                            tuple(insert_values),
                        )
                conn.commit()
            finally:
                conn.close()
            return {"warning_count": 0}

        return _stub

    for builder_name in target_tables_by_builder:
        monkeypatch.setattr(cli, builder_name, make_stub(builder_name))


def test_refuses_when_confirm_run_id_is_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    run_id = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--db",
                str(db_path),
                "--ecosystem",
                "DATACENTER",
                "--taxonomy-version",
                "DC_TAXONOMY_FULL_V1",
                "--signal-date",
                "2026-06-04",
                "--run-id",
                run_id,
                "--backup-dir",
                str(backup_dir),
                "--format",
                "text",
            ]
        )


def test_refuses_when_confirm_run_id_mismatches(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    args = _base_args(db_path, backup_dir)
    args[args.index("--confirm-run-id") + 1] = "MISMATCH"
    result = cli.main(args)
    captured = capsys.readouterr()
    assert result == 1
    assert "status: BUILD_REFUSED" in captured.out
    assert "confirm_run_id must exactly equal run_id" in captured.out


def test_refuses_when_backup_dir_is_missing(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "build.db"
    _create_fixture_db(str(db_path))
    result = cli.main(_base_args(db_path, tmp_path / "missing-backups"))
    captured = capsys.readouterr()
    assert result == 1
    assert "status: BUILD_REFUSED" in captured.out
    assert "backup_dir does not exist" in captured.out


def test_refuses_when_target_run_exists_without_replace_existing(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    run_id = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
    _insert_existing_run(str(db_path), run_id)
    result = cli.main(_base_args(db_path, backup_dir))
    captured = capsys.readouterr()
    assert result == 1
    assert "status: BUILD_REFUSED" in captured.out
    assert "target run already exists" in captured.out


def test_refuses_when_planner_readiness_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    monkeypatch.setattr(cli, "_evaluate_planner_status", lambda *args, **kwargs: "BLOCKED_MISSING_SOURCE")
    result = cli.main(_base_args(db_path, backup_dir))
    captured = capsys.readouterr()
    assert result == 1
    assert "status: BUILD_REFUSED" in captured.out
    assert "planner readiness blocked: BLOCKED_MISSING_SOURCE" in captured.out


def test_refuses_when_deterministic_technical_relevance_run_id_cannot_be_selected(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    _insert_ambiguous_technical_relevance_runs(str(db_path))
    result = cli.main(_base_args(db_path, backup_dir))
    captured = capsys.readouterr()
    assert result == 1
    assert "status: BUILD_REFUSED" in captured.out
    assert "deterministic technical_relevance_run_id could not be resolved" in captured.out


def test_creates_backup_before_first_builder_call_and_calls_builders_in_exact_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    call_order: list[str] = []
    _install_success_builder_stubs(monkeypatch, db_path, call_order)
    original_create_backup = cli._create_backup

    def _backup_then_record(db_path_value: str, backup_dir_value: Path, run_id_value: str) -> Path:
        path = original_create_backup(db_path_value, backup_dir_value, run_id_value)
        call_order.append("BACKUP_CREATED")
        return path

    monkeypatch.setattr(cli, "_create_backup", _backup_then_record)
    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    captured = capsys.readouterr()

    assert result == 0
    assert call_order[0] == "BACKUP_CREATED"
    assert call_order[1:] == [name for name, _, _ in cli._builder_sequence()]
    assert "status: BUILD_COMPLETED" in captured.out


def test_replace_existing_cleans_target_run_rows_after_backup_and_before_first_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    run_id = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
    other_run_id = "OTHER_RUN"
    _insert_existing_run(str(db_path), run_id)
    _insert_existing_run(str(db_path), other_run_id)
    _insert_existing_runtime_rows(str(db_path), run_id, other_run_id)

    call_order: list[str] = []
    original_create_backup = cli._create_backup

    def _backup_then_record(db_path_value: str, backup_dir_value: Path, run_id_value: str) -> Path:
        path = original_create_backup(db_path_value, backup_dir_value, run_id_value)
        call_order.append("BACKUP_CREATED")
        return path

    def _base_stub(**kwargs):
        call_order.append("build_canonical_v3_base_run")
        conn = _connect(str(db_path))
        try:
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_event WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 1

            assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM eco_entity_event WHERE run_id = ?", (other_run_id,)).fetchone()[0] == 1
        finally:
            conn.close()
        return {"warning_count": 0}

    def _generic_stub(**kwargs):
        call_order.append("GENERIC_BUILDER")
        return {"warning_count": 0}

    monkeypatch.setattr(cli, "_create_backup", _backup_then_record)
    monkeypatch.setattr(cli, "build_canonical_v3_base_run", _base_stub)
    for builder_name, _, _ in cli._builder_sequence()[1:]:
        monkeypatch.setattr(cli, builder_name, _generic_stub)
    monkeypatch.setattr(
        cli,
        "_validate_post_build",
        lambda *args, **kwargs: {
            "run_exists": True,
            "table_counts": {table_name: 1 for table_name in cli.TARGET_TABLES_BY_VALIDATION},
            "forbidden_lineage_counts": {
                "eco_entity_window_snapshot": 0,
                "eco_entity_metric_value": 0,
                "eco_classification_decision": 0,
                "eco_signal_observation": 0,
                "eco_entity_event": 0,
            },
            "latest_eco_signal_date": "2026-06-04",
            "latest_signal_date_ok": True,
        },
    )

    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    captured = capsys.readouterr()

    assert result == 0
    assert call_order[0] == "BACKUP_CREATED"
    assert call_order[1] == "build_canonical_v3_base_run"
    assert "Replace Cleanup" in captured.out
    assert "replace_cleanup_status: OK" in captured.out
    assert f"replace_cleanup_scope: run_id={run_id}" in captured.out
    assert "replace_cleanup_timing: after backup, before builder execution" in captured.out
    assert "replace_cleanup_deleted eco_signal_relevance=1" in captured.out
    assert "replace_cleanup_deleted eco_signal_observation=1" in captured.out
    assert "replace_cleanup_deleted eco_entity_event=1" in captured.out
    assert "replace_cleanup_deleted eco_entity_window_snapshot=1" in captured.out
    assert "replace_cleanup_deleted eco_entity_metric_value=1" in captured.out
    assert "replace_cleanup_deleted eco_classification_decision=1" in captured.out
    assert "replace_cleanup_deleted eco_entity_coverage=1" in captured.out
    assert "replace_cleanup_deleted eco_quality_summary=1" in captured.out


def test_does_not_call_forbidden_builders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    call_order: list[str] = []
    _install_success_builder_stubs(monkeypatch, db_path, call_order)
    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    assert result == 0
    assert all(name not in call_order for name in cli.FORBIDDEN_BUILDERS)


def test_passes_replace_flags_when_replace_existing_is_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    seen_kwargs: dict[str, dict[str, object]] = {}

    def _base_stub(**kwargs):
        seen_kwargs["base"] = kwargs
        return {"warning_count": 0}

    def _generic_stub(**kwargs):
        seen_kwargs.setdefault("generic", kwargs)
        return {"warning_count": 0}

    monkeypatch.setattr(cli, "build_canonical_v3_base_run", _base_stub)
    for builder_name, _, _ in cli._builder_sequence()[1:]:
        monkeypatch.setattr(cli, builder_name, _generic_stub)
    monkeypatch.setattr(
        cli,
        "_validate_post_build",
        lambda *args, **kwargs: {
            "run_exists": True,
            "table_counts": {table_name: 1 for table_name in cli.TARGET_TABLES_BY_VALIDATION},
            "forbidden_lineage_counts": {
                "eco_entity_window_snapshot": 0,
                "eco_entity_metric_value": 0,
                "eco_classification_decision": 0,
                "eco_signal_observation": 0,
                "eco_entity_event": 0,
            },
            "latest_eco_signal_date": "2026-06-04",
            "latest_signal_date_ok": True,
        },
    )
    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    assert result == 0
    assert seen_kwargs["base"]["replace_run"] is True
    assert seen_kwargs["generic"]["replace_existing"] is True


def test_cleanup_failure_stops_before_any_builder_call_and_reports_build_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    run_id = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
    _insert_existing_run(str(db_path), run_id)

    builder_called = {"value": False}
    original_create_backup = cli._create_backup

    def _base_stub(**kwargs):
        builder_called["value"] = True
        return {"warning_count": 0}

    def _cleanup_boom(*args, **kwargs):
        raise RuntimeError("forced cleanup failure")

    monkeypatch.setattr(cli, "build_canonical_v3_base_run", _base_stub)
    monkeypatch.setattr(cli, "_create_backup", original_create_backup)
    monkeypatch.setattr(cli, "_cleanup_existing_run_runtime_rows", _cleanup_boom)

    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    captured = capsys.readouterr()

    assert result == 1
    assert builder_called["value"] is False
    assert "status: BUILD_FAILED" in captured.out
    assert "forced cleanup failure" in captured.out
    assert "backup_path:" in captured.out
    assert "partial_writes_may_exist" in captured.out


def test_call_order_places_group_historical_metrics_between_group_window_metrics_and_ticker_freshness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    call_order: list[str] = []
    _install_success_builder_stubs(monkeypatch, db_path, call_order)

    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])

    assert result == 0
    assert call_order.index("build_canonical_v3_group_window_metrics") < call_order.index(
        "build_canonical_v3_group_historical_metrics"
    )
    assert call_order.index("build_canonical_v3_group_historical_metrics") < call_order.index(
        "build_canonical_v3_ticker_freshness_from_signal_daily"
    )


def test_group_historical_metrics_builder_receives_expected_parameters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    seen_kwargs: dict[str, dict[str, object]] = {}

    def _base_stub(**kwargs):
        return {"warning_count": 0}

    def _historical_stub(**kwargs):
        seen_kwargs["historical"] = kwargs
        return {"warning_count": 0}

    def _generic_stub(**kwargs):
        return {"warning_count": 0}

    monkeypatch.setattr(cli, "build_canonical_v3_base_run", _base_stub)
    monkeypatch.setattr(cli, "build_canonical_v3_group_historical_metrics", _historical_stub)
    for builder_name, _, _ in cli._builder_sequence()[1:]:
        if builder_name == "build_canonical_v3_group_historical_metrics":
            continue
        monkeypatch.setattr(cli, builder_name, _generic_stub)
    monkeypatch.setattr(
        cli,
        "_validate_post_build",
        lambda *args, **kwargs: {
            "run_exists": True,
            "table_counts": {table_name: 1 for table_name in cli.TARGET_TABLES_BY_VALIDATION},
            "forbidden_lineage_counts": {
                "eco_entity_window_snapshot": 0,
                "eco_entity_metric_value": 0,
                "eco_classification_decision": 0,
                "eco_signal_observation": 0,
                "eco_entity_event": 0,
            },
            "latest_eco_signal_date": "2026-06-04",
            "latest_signal_date_ok": True,
        },
    )

    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])

    assert result == 0
    assert seen_kwargs["historical"]["db_path"] == str(db_path)
    assert seen_kwargs["historical"]["run_id"] == "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
    assert seen_kwargs["historical"]["replace_existing"] is True


def test_stops_on_first_builder_failure_and_reports_backup_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))

    monkeypatch.setattr(cli, "build_canonical_v3_base_run", lambda **kwargs: {"warning_count": 0})

    def _boom(**kwargs):
        raise RuntimeError("forced builder failure")

    monkeypatch.setattr(cli, "build_canonical_v3_ticker_daily_direct_metrics", _boom)
    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    captured = capsys.readouterr()
    assert result == 1
    assert "status: BUILD_FAILED" in captured.out
    assert "forced builder failure" in captured.out
    assert "backup_path:" in captured.out
    assert "partial_writes_may_exist" in captured.out


def test_prints_post_build_validation_summary_when_builders_succeed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "build.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_fixture_db(str(db_path))
    call_order: list[str] = []
    _install_success_builder_stubs(monkeypatch, db_path, call_order)
    result = cli.main(_base_args(db_path, backup_dir) + ["--replace-existing"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Post-Build Validation" in captured.out
    assert "eco_report_run_rows:" in captured.out
    assert "eco_signal_relevance_rows:" in captured.out
    assert "latest_eco_signal_date: 2026-06-04" in captured.out
