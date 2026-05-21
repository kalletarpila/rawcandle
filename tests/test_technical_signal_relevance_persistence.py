import json
import sqlite3

import pytest

from analysis.database_manager import DatabaseManager
from rawcandle.technical_signal_relevance import (
    TechnicalSignalDowSnapshot,
    TechnicalSignalObservation,
    TechnicalSignalRelevanceConfig,
    classify_relevance,
)
from rawcandle.technical_signal_relevance_persistence import (
    MIGRATION_SQL_PATH,
    PERSISTED_UNKNOWN_SOURCE_ID,
    PERSISTED_UNKNOWN_SOURCE_TYPE,
    apply_technical_signal_relevance_migration,
    build_relevance_run_row,
    build_relevance_stored_row,
    insert_relevance_records,
    insert_relevance_run,
    read_relevance_records_for_run,
    read_relevance_run,
    serialize_rule_trace,
)


def _connect():
    conn = sqlite3.connect(":memory:")
    apply_technical_signal_relevance_migration(conn)
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _indexes(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _primary_key_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    ordered = sorted((row for row in rows if int(row[5]) > 0), key=lambda row: int(row[5]))
    return [str(row[1]) for row in ordered]


def _relevant_record():
    return classify_relevance(
        TechnicalSignalObservation(
            ticker="AAA",
            timeframe="1D",
            signal_date="2024-01-10",
            signal_confirmed_as_of_date="2024-01-10",
            signal_name="Bullish Flag",
            signal_close_price=100.0,
        ),
        TechnicalSignalDowSnapshot(trend_state="UP", structure_epoch_id=1),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )


def _unknown_record():
    return classify_relevance(
        TechnicalSignalObservation(
            ticker="BBB",
            timeframe="1D",
            signal_date="2024-01-11",
            signal_confirmed_as_of_date="2024-01-11",
            signal_name="Unknown Signal",
            signal_close_price=90.0,
        ),
        TechnicalSignalDowSnapshot(trend_state="UP", structure_epoch_id=1),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )


def test_migration_file_exists():
    assert MIGRATION_SQL_PATH.is_file()


def test_migration_creates_technical_signal_relevance_runs():
    conn = _connect()
    assert _table_exists(conn, "technical_signal_relevance_runs")


def test_migration_creates_technical_signal_relevance():
    conn = _connect()
    assert _table_exists(conn, "technical_signal_relevance")


def test_migration_creates_required_indexes():
    conn = _connect()
    indexes = _indexes(conn, "technical_signal_relevance")
    assert {
        "idx_technical_signal_relevance_ticker_tf_date",
        "idx_technical_signal_relevance_ticker_tf_class_date",
        "idx_technical_signal_relevance_run_id",
    }.issubset(indexes)


def test_schema_primary_key_includes_run_id_and_source_columns():
    conn = _connect()

    assert _primary_key_columns(conn, "technical_signal_relevance") == [
        "run_id",
        "ticker",
        "timeframe",
        "signal_date",
        "signal_name",
        "signal_source_type",
        "signal_source_id",
        "relevance_rule_version",
    ]


def test_database_manager_initializes_technical_signal_relevance_tables(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    conn = manager.get_connection()

    assert _table_exists(conn, "technical_signal_relevance_runs")
    assert _table_exists(conn, "technical_signal_relevance")
    manager.close()


def test_insert_and_read_one_relevance_run():
    conn = _connect()
    config = TechnicalSignalRelevanceConfig()
    run_row = build_relevance_run_row(
        run_id="RUN_001",
        config=config,
        created_at_utc="2026-05-21T10:00:00Z",
    )

    insert_relevance_run(conn, run_row)
    loaded = read_relevance_run(conn, "RUN_001")

    assert loaded is not None
    assert loaded["run_id"] == "RUN_001"
    assert loaded["config_snapshot_json"] == config.to_snapshot_json()
    assert loaded["relevance_rule_version"] == config.rule_version


def test_insert_and_read_one_relevant_relevance_record():
    conn = _connect()
    run_row = build_relevance_run_row(
        run_id="RUN_002",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:01Z",
    )
    insert_relevance_run(conn, run_row)
    stored_row = build_relevance_stored_row(
        _relevant_record(),
        run_id="RUN_002",
        created_at_utc="2026-05-21T10:00:02Z",
    )

    insert_relevance_records(conn, [stored_row])
    loaded = read_relevance_records_for_run(conn, "RUN_002")

    assert len(loaded) == 1
    assert loaded[0]["ticker"] == "AAA"
    assert loaded[0]["relevance_class"] == "RELEVANT"
    assert loaded[0]["relevance_reason"] == "UP_TREND_BULLISH_CONTINUATION"
    assert loaded[0]["run_id"] == "RUN_002"


def test_unknown_signal_record_persists_with_deterministic_non_null_source_sentinels():
    conn = _connect()
    run_row = build_relevance_run_row(
        run_id="RUN_003",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:03Z",
    )
    insert_relevance_run(conn, run_row)
    stored_row = build_relevance_stored_row(
        _unknown_record(),
        run_id="RUN_003",
        created_at_utc="2026-05-21T10:00:04Z",
    )

    insert_relevance_records(conn, [stored_row])
    loaded = read_relevance_records_for_run(conn, "RUN_003")[0]

    assert loaded["relevance_reason"] == "UNKNOWN_SIGNAL_NAME"
    assert loaded["signal_direction"] is None
    assert loaded["signal_family"] is None
    assert loaded["signal_source_type"] == PERSISTED_UNKNOWN_SOURCE_TYPE
    assert loaded["signal_source_id"] == PERSISTED_UNKNOWN_SOURCE_ID


def test_boolean_like_fields_are_stored_as_zero_one():
    conn = _connect()
    run_row = build_relevance_run_row(
        run_id="RUN_004",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:05Z",
    )
    insert_relevance_run(conn, run_row)
    stored_row = build_relevance_stored_row(
        _relevant_record(),
        run_id="RUN_004",
        created_at_utc="2026-05-21T10:00:06Z",
    )

    insert_relevance_records(conn, [stored_row])
    loaded = read_relevance_records_for_run(conn, "RUN_004")[0]

    assert loaded["near_latest_pivot"] in {0, 1}
    assert loaded["near_active_bos_level"] in {0, 1}
    assert loaded["is_trend_aligned"] in {0, 1}
    assert loaded["is_counter_trend"] in {0, 1}
    assert loaded["is_trend_aligned"] == 1
    assert loaded["is_counter_trend"] == 0


def test_config_snapshot_json_is_stored_only_in_run_table():
    conn = _connect()
    run_columns = _columns(conn, "technical_signal_relevance_runs")
    result_columns = _columns(conn, "technical_signal_relevance")

    assert "config_snapshot_json" in run_columns
    assert "config_snapshot_json" not in result_columns


def test_rule_trace_serialization_is_deterministic():
    record = _relevant_record()

    serialized_a = serialize_rule_trace(record.rule_trace)
    serialized_b = serialize_rule_trace(tuple(record.rule_trace))

    assert serialized_a == serialized_b
    assert serialized_a == stored_json_list(serialized_a)


def stored_json_list(serialized: str | None) -> str:
    assert serialized is not None
    loaded = json.loads(serialized)
    return json.dumps(loaded, ensure_ascii=True, separators=(",", ":"))


def test_duplicate_run_id_insert_fails():
    conn = _connect()
    run_row = build_relevance_run_row(
        run_id="RUN_005",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:07Z",
    )

    insert_relevance_run(conn, run_row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_relevance_run(conn, run_row)


def test_duplicate_relevance_primary_key_insert_fails():
    conn = _connect()
    run_row = build_relevance_run_row(
        run_id="RUN_006",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:08Z",
    )
    insert_relevance_run(conn, run_row)
    stored_row = build_relevance_stored_row(
        _relevant_record(),
        run_id="RUN_006",
        created_at_utc="2026-05-21T10:00:09Z",
    )

    insert_relevance_records(conn, [stored_row])
    with pytest.raises(sqlite3.IntegrityError):
        insert_relevance_records(conn, [stored_row])


def test_same_relevance_identity_can_exist_in_multiple_run_ids():
    conn = _connect()
    run_row_a = build_relevance_run_row(
        run_id="RUN_A",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:09Z",
    )
    run_row_b = build_relevance_run_row(
        run_id="RUN_B",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:10Z",
    )
    insert_relevance_run(conn, run_row_a)
    insert_relevance_run(conn, run_row_b)
    stored_row_a = build_relevance_stored_row(
        _relevant_record(),
        run_id="RUN_A",
        created_at_utc="2026-05-21T10:00:11Z",
    )
    stored_row_b = build_relevance_stored_row(
        _relevant_record(),
        run_id="RUN_B",
        created_at_utc="2026-05-21T10:00:12Z",
    )

    insert_relevance_records(conn, [stored_row_a])
    insert_relevance_records(conn, [stored_row_b])

    assert len(read_relevance_records_for_run(conn, "RUN_A")) == 1
    assert len(read_relevance_records_for_run(conn, "RUN_B")) == 1


def test_read_relevance_records_for_run_returns_only_requested_run_id_rows():
    conn = _connect()
    run_row_a = build_relevance_run_row(
        run_id="RUN_ONLY_A",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:13Z",
    )
    run_row_b = build_relevance_run_row(
        run_id="RUN_ONLY_B",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:14Z",
    )
    insert_relevance_run(conn, run_row_a)
    insert_relevance_run(conn, run_row_b)
    insert_relevance_records(
        conn,
        [
            build_relevance_stored_row(
                _relevant_record(),
                run_id="RUN_ONLY_A",
                created_at_utc="2026-05-21T10:00:15Z",
            ),
            build_relevance_stored_row(
                _relevant_record(),
                run_id="RUN_ONLY_B",
                created_at_utc="2026-05-21T10:00:16Z",
            ),
        ],
    )

    loaded = read_relevance_records_for_run(conn, "RUN_ONLY_A")

    assert len(loaded) == 1
    assert loaded[0]["run_id"] == "RUN_ONLY_A"


def test_migration_rebuilds_old_schema_and_preserves_existing_rows():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE technical_signal_relevance_runs (
            run_id TEXT PRIMARY KEY NOT NULL,
            relevance_rule_version TEXT NOT NULL,
            mapping_version TEXT NOT NULL,
            reason_version TEXT NOT NULL,
            config_snapshot_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE technical_signal_relevance (
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            signal_confirmed_as_of_date TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            signal_close_price REAL NULL,
            signal_direction TEXT NULL,
            signal_family TEXT NULL,
            signal_source_type TEXT NULL,
            signal_source_id TEXT NULL,
            dow_trend_state TEXT NULL,
            dow_context_state TEXT NULL,
            latest_bos_direction TEXT NULL,
            bars_since_latest_bos INTEGER NULL,
            latest_reset_reason TEXT NULL,
            bars_since_latest_reset INTEGER NULL,
            near_latest_pivot INTEGER NOT NULL,
            near_active_bos_level INTEGER NOT NULL,
            is_trend_aligned INTEGER NOT NULL,
            is_counter_trend INTEGER NOT NULL,
            relevance_class TEXT NOT NULL,
            relevance_reason TEXT NOT NULL,
            relevance_rule_version TEXT NOT NULL,
            mapping_version TEXT NOT NULL,
            reason_version TEXT NOT NULL,
            rule_trace TEXT NULL,
            created_at_utc TEXT NOT NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (
                ticker,
                timeframe,
                signal_date,
                signal_name,
                signal_source_type,
                relevance_rule_version
            )
        )
        """
    )
    conn.execute(
        """
        INSERT INTO technical_signal_relevance_runs (
            run_id, relevance_rule_version, mapping_version, reason_version, config_snapshot_json, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("RUN_OLD", "TECH_SIGNAL_RELEVANCE_V1", "TECH_SIGNAL_MAPPING_V1", "TECH_SIGNAL_RELEVANCE_REASON_V1", "{}", "2026-05-21T10:00:17Z"),
    )
    conn.execute(
        """
        INSERT INTO technical_signal_relevance (
            ticker, timeframe, signal_date, signal_confirmed_as_of_date, signal_name,
            signal_close_price, signal_direction, signal_family, signal_source_type, signal_source_id,
            dow_trend_state, dow_context_state, latest_bos_direction, bars_since_latest_bos,
            latest_reset_reason, bars_since_latest_reset, near_latest_pivot, near_active_bos_level,
            is_trend_aligned, is_counter_trend, relevance_class, relevance_reason,
            relevance_rule_version, mapping_version, reason_version, rule_trace, created_at_utc, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "AAA",
            "1D",
            "2024-01-10",
            "2024-01-10",
            "Unknown Signal",
            90.0,
            None,
            None,
            None,
            None,
            "UP",
            "NORMAL",
            None,
            None,
            None,
            None,
            0,
            0,
            0,
            0,
            "WEAK_CONTEXT",
            "UNKNOWN_SIGNAL_NAME",
            "TECH_SIGNAL_RELEVANCE_V1",
            "TECH_SIGNAL_MAPPING_V1",
            "TECH_SIGNAL_RELEVANCE_REASON_V1",
            "[]",
            "2026-05-21T10:00:18Z",
            "RUN_OLD",
        ),
    )

    apply_technical_signal_relevance_migration(conn)
    loaded = read_relevance_records_for_run(conn, "RUN_OLD")

    assert _primary_key_columns(conn, "technical_signal_relevance")[0] == "run_id"
    assert len(loaded) == 1
    assert loaded[0]["signal_source_type"] == PERSISTED_UNKNOWN_SOURCE_TYPE
    assert loaded[0]["signal_source_id"] == PERSISTED_UNKNOWN_SOURCE_ID


def test_read_records_for_run_returns_deterministic_order():
    conn = _connect()
    run_row = build_relevance_run_row(
        run_id="RUN_007",
        config=TechnicalSignalRelevanceConfig(),
        created_at_utc="2026-05-21T10:00:10Z",
    )
    insert_relevance_run(conn, run_row)
    first = build_relevance_stored_row(
        classify_relevance(
            TechnicalSignalObservation(
                ticker="ZZZ",
                timeframe="1D",
                signal_date="2024-01-12",
                signal_confirmed_as_of_date="2024-01-12",
                signal_name="Bullish Flag",
                signal_close_price=100.0,
            ),
            TechnicalSignalDowSnapshot(trend_state="UP"),
            events=[],
            pivots=[],
            config=TechnicalSignalRelevanceConfig(),
        ),
        run_id="RUN_007",
        created_at_utc="2026-05-21T10:00:11Z",
    )
    second = build_relevance_stored_row(
        classify_relevance(
            TechnicalSignalObservation(
                ticker="AAA",
                timeframe="1D",
                signal_date="2024-01-10",
                signal_confirmed_as_of_date="2024-01-10",
                signal_name="Bearish Flag",
                signal_close_price=100.0,
            ),
            TechnicalSignalDowSnapshot(trend_state="UP"),
            events=[],
            pivots=[],
            config=TechnicalSignalRelevanceConfig(),
        ),
        run_id="RUN_007",
        created_at_utc="2026-05-21T10:00:12Z",
    )

    insert_relevance_records(conn, [first, second])
    loaded = read_relevance_records_for_run(conn, "RUN_007")

    assert [row["ticker"] for row in loaded] == ["AAA", "ZZZ"]
    assert [row["signal_name"] for row in loaded] == ["Bearish Flag", "Bullish Flag"]
