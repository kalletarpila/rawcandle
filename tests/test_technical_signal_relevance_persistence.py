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


def test_insert_and_read_unknown_signal_record_with_null_mapping_fields():
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
    assert loaded["signal_source_type"] is None
    assert loaded["signal_source_id"] is None


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
