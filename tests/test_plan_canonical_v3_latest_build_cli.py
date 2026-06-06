from __future__ import annotations

import sqlite3

from rawcandle.cli import plan_canonical_v3_latest_build as cli


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
    for table_name in ACCEPTED_ECO_TARGET_TABLES:
        conn.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)")


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
            event_date TEXT NOT NULL
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
        INSERT INTO stock_dow_structure_events (ticker, event_date)
        VALUES ('NVDA', ?)
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


def _create_fixture_db(db_path: str, *, signal_date: str = "2026-06-04", include_tech_rel: bool = True) -> None:
    conn = _connect(db_path)
    try:
        _create_control_tables(conn)
        _create_target_tables(conn)
        _create_allowed_source_tables(conn)
        _create_forbidden_tables(conn)
        _insert_ready_sources(conn, signal_date)
        if not include_tech_rel:
            conn.execute("DELETE FROM technical_signal_relevance")
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
            ) VALUES (
                'ALT_TECH_REL_ONE', ?, '1d', 'NVDA', 'MA_STATUS', 'TICKER', 'src-1'
            )
            """,
            (signal_date,),
        )
        conn.execute(
            """
            INSERT INTO technical_signal_relevance (
                run_id, signal_date, timeframe, ticker, signal_name, signal_source_type, signal_source_id
            ) VALUES (
                'ALT_TECH_REL_TWO', ?, '1d', 'NVDA', 'MA_STATUS', 'TICKER', 'src-2'
            )
            """,
            (signal_date,),
        )
        conn.commit()
    finally:
        conn.close()


def _eco_target_counts(db_path: str) -> dict[str, int]:
    conn = _connect(db_path)
    try:
        return {
            table_name: int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
            for table_name in ACCEPTED_ECO_TARGET_TABLES
        }
    finally:
        conn.close()


def test_cli_derives_run_id_when_omitted(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "planned_run_id: V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1" in captured.out


def test_cli_prints_provided_run_id(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))

    result = cli.main(
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
            "RUN-EXPLICIT",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "planned_run_id: RUN-EXPLICIT" in captured.out


def test_cli_reports_ready_no_write_plan_when_required_sources_exist(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))
    before_counts = _eco_target_counts(str(db_path))

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    after_counts = _eco_target_counts(str(db_path))
    captured = capsys.readouterr()
    assert result == 0
    assert "status: READY_NO_WRITE_PLAN" in captured.out
    assert before_counts == after_counts


def test_cli_reports_blocked_missing_source_when_required_table_has_no_rows(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path), include_tech_rel=False)

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "technical_signal_relevance | MISSING | 0 |" in captured.out
    assert "status: BLOCKED_MISSING_SOURCE" in captured.out


def test_cli_lists_forbidden_sources_and_bypassed_builders(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "dc_report_context_daily_v2 | yes | 1 | FORBIDDEN_BYPASS |" in captured.out
    assert "dc_dashboard_action_summary_daily | yes | 1 | FORBIDDEN_BYPASS |" in captured.out
    assert "build_canonical_v3_classification_decisions | dc_report_classification_v2 |" in captured.out
    assert "build_canonical_v3_snapshot_metrics | dc_report_context_daily_v2, dc_report_context_window_v2, dc_report_context_group_v2, dc_report_classification_v2 |" in captured.out


def test_cli_includes_allowed_build_sequence_and_no_execution_notes(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "1 | build_canonical_v3_base_run | eco_report_run, eco_entity_coverage, eco_quality_summary |" in captured.out
    assert "7 | build_canonical_v3_group_historical_metrics | eco_entity_metric_value | dc_group_swing_signal_daily, dc_group_synthetic_ohlc_daily |" in captured.out
    assert "13 | build_canonical_v3_window_snapshots | eco_entity_window_snapshot |" in captured.out
    assert "16 | build_canonical_v3_signal_relevance | eco_signal_observation, eco_signal_relevance |" in captured.out
    assert "19 | build_canonical_v3_group_freshness_metrics | eco_entity_metric_value | eco_entity_event, eco_entity_metric_value, eco_entity, eco_report_run |" in captured.out
    assert "technical_relevance_run_id=DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_06_04" in captured.out
    assert "technical_relevance_V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1" not in captured.out
    assert "not executed" in captured.out
    assert captured.out.index(
        "6 | build_canonical_v3_group_window_metrics | eco_entity_metric_value |"
    ) < captured.out.index(
        "7 | build_canonical_v3_group_historical_metrics | eco_entity_metric_value |"
    )
    assert captured.out.index(
        "7 | build_canonical_v3_group_historical_metrics | eco_entity_metric_value |"
    ) < captured.out.index(
        "8 | build_canonical_v3_ticker_freshness_from_signal_daily | eco_entity_metric_value, eco_signal_observation |"
    )
    assert captured.out.index(
        "17 | build_canonical_v3_ticker_structure_events | eco_entity_event |"
    ) < captured.out.index(
        "19 | build_canonical_v3_group_freshness_metrics | eco_entity_metric_value |"
    )
    assert captured.out.index(
        "18 | build_canonical_v3_group_structure_events | eco_entity_event |"
    ) < captured.out.index(
        "19 | build_canonical_v3_group_freshness_metrics | eco_entity_metric_value |"
    )
    assert "19 | build_canonical_v3_group_freshness_metrics | eco_entity_metric_value | dc_" not in captured.out


def test_cli_uses_clear_placeholder_when_no_deterministic_technical_relevance_run_id_exists(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))
    _insert_ambiguous_technical_relevance_runs(str(db_path))

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "technical_relevance_run_id=<SELECT_FROM_READY_TECHNICAL_SIGNAL_RELEVANCE_RUN_IDS>" in captured.out
    assert "technical_relevance_V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1" not in captured.out


def test_cli_output_includes_no_builders_executed_and_no_db_writes_performed(tmp_path, capsys) -> None:
    db_path = tmp_path / "plan.db"
    _create_fixture_db(str(db_path))

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--signal-date",
            "2026-06-04",
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "No builders executed." in captured.out
    assert "No DB writes performed." in captured.out
