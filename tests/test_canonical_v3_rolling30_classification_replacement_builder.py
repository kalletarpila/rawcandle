import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_rolling30_classification_replacement_builder import (
    build_canonical_v3_rolling30_watchlist_classifications,
)
import rawcandle.report_canonical_v3_rolling30_classification_replacement_builder as builder_module


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
ROLLING2_SOURCE_RUN_ID = "V3_ROLLING2_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29"
ROLLING5_SOURCE_RUN_ID = "V3_ROLLING5_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29"
ROLLING30_OLD_SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_ecosystem (ecosystem_code, ecosystem_name, status)
            VALUES ('DATACENTER', 'Datacenter', 'ACTIVE')
            """
        ).lastrowid
    )


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_taxonomy_version (
                ecosystem_id, version_code, version_label, is_active, status
            ) VALUES (?, 'DC_TAXONOMY_FULL_V1', 'V1', 1, 'ACTIVE')
            """,
            (ecosystem_id,),
        ).lastrowid
    )


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
        ) VALUES (?, ?, ?, ?, 'BUILD', 'OK', 0, 0)
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, SIGNAL_DATE),
    )


def _insert_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, status
            ) VALUES (?, ?, ?, ?, ?, 'ACTIVE')
            """,
            (
                ecosystem_id,
                entity_type,
                entity_code,
                entity_code,
                entity_code if entity_type == "TICKER" else None,
            ),
        ).lastrowid
    )


def _insert_coverage(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_coverage (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal,
            has_window_context, coverage_status, source_row_count, missing_component_count
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1, 1, 1, 1, 'OK', 1, 0)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, window_code, entity_id),
    )


def _create_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            primary_layer TEXT,
            primary_subindustry TEXT,
            breakout_signal INTEGER,
            pullback_signal INTEGER,
            fast_ema10_pullback_signal INTEGER,
            conservative_ema20_pullback_signal INTEGER,
            exit_risk_signal INTEGER,
            exit_risk_severity TEXT,
            exit_reason TEXT,
            latest_bos_event_type TEXT,
            latest_bos_freshness TEXT,
            latest_reset_reason TEXT,
            latest_reset_freshness TEXT,
            latest_structure_label TEXT,
            distance_to_ema20_pct REAL,
            price_data_status TEXT,
            ticker_trend_state TEXT,
            latest_bearish_relevance_class TEXT,
            latest_bullish_relevance_class TEXT,
            signal_version TEXT NOT NULL,
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
            timing_state TEXT,
            overheat_risk_level TEXT,
            signal_version TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )


def _insert_ticker_source_rows(conn: sqlite3.Connection) -> None:
    rows = [
        ("2026-05-23", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.08, "OK", "UP", None, "RELEVANT", "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-26", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.07, "OK", "UP", None, "RELEVANT", "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-27", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 1, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.06, "OK", "UP", None, "RELEVANT", "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-28", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.05, "OK", "UP", None, "RELEVANT", "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-29", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 1, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.04, "OK", "UP", None, "RELEVANT", "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-23", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-26", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-27", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-28", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-29", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-23", "DC_TAXONOMY_FULL_V1", "CCC", "LAYER_C", "SUB_C", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.02, "OK", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-26", "DC_TAXONOMY_FULL_V1", "CCC", "LAYER_C", "SUB_C", 0, 0, 0, 0, 1, "MEDIUM", "SOFT_EXIT", "BOS_UP", "AGING", None, None, "HH", 0.01, "OK", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-27", "DC_TAXONOMY_FULL_V1", "CCC", "LAYER_C", "SUB_C", 0, 0, 0, 0, 1, "MEDIUM", "SOFT_EXIT", "BOS_UP", "AGING", None, None, "HH", -0.01, "OK", "UP", None, None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-28", "DC_TAXONOMY_FULL_V1", "CCC", "LAYER_C", "SUB_C", 0, 0, 0, 0, 1, "HIGH", "HARD_EXIT", "BOS_UP", "AGING", None, None, "LH", -0.02, "OK", "DOWN", "RELEVANT", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-29", "DC_TAXONOMY_FULL_V1", "CCC", "LAYER_C", "SUB_C", 0, 0, 0, 0, 1, "HIGH", "HARD_EXIT", "BOS_UP", "AGING", None, None, "LH", -0.03, "OK", "DOWN", "RELEVANT", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
    ]
    conn.executemany(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
            breakout_signal, pullback_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
            exit_risk_signal, exit_risk_severity, exit_reason, latest_bos_event_type, latest_bos_freshness,
            latest_reset_reason, latest_reset_freshness, latest_structure_label, distance_to_ema20_pct,
            price_data_status, ticker_trend_state, latest_bearish_relevance_class, latest_bullish_relevance_class,
            signal_version, run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_group_source_rows(conn: sqlite3.Connection) -> None:
    rows = []
    for signal_date in ("2026-05-23", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"):
        rows.extend(
            [
                (signal_date, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_A", "NEUTRAL", "LOW", "DC_SWING_SIGNAL_V1", "DC_GROUP_SWING_RUN"),
                (signal_date, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_A", "BUY_ZONE", "LOW", "DC_SWING_SIGNAL_V1", "DC_GROUP_SWING_RUN"),
                (signal_date, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_B", "NEUTRAL", "LOW", "DC_SWING_SIGNAL_V1", "DC_GROUP_SWING_RUN"),
                (signal_date, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_B", "NEUTRAL", "LOW", "DC_SWING_SIGNAL_V1", "DC_GROUP_SWING_RUN"),
                (signal_date, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_C", "TRIM_WATCH", "HIGH", "DC_SWING_SIGNAL_V1", "DC_GROUP_SWING_RUN"),
                (signal_date, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_C", "EXIT_ZONE", "HIGH", "DC_SWING_SIGNAL_V1", "DC_GROUP_SWING_RUN"),
            ]
        )
    conn.executemany("INSERT INTO dc_group_swing_signal_daily VALUES (?,?,?,?,?,?,?,?)", rows)


def _insert_existing_classifications(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    ticker_entity_ids: dict[str, int],
) -> None:
    rows = []
    for ticker, entity_id in ticker_entity_ids.items():
        rows.extend(
            [
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "daily_trigger", "SELL_TRIGGER", "PR", None, None, None, None, None, None, "daily_trigger", "REPORT_CANONICAL_CLASSIFICATION_V2_1", ROLLING30_OLD_SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling2", entity_id, "rolling2_sell_pressure", "KEEP_STATE", "KEEP_PR", None, "KEEP_RISK", "KEEP_ACTION", None, None, None, "rolling2_sell_pressure_classifier", "V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1", ROLLING2_SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling5", entity_id, "rolling5_pullback", "KEEP_R5", "KEEP_R5_PR", "KEEP_R5_BLOCK", None, "KEEP_R5_ACTION", None, None, None, "rolling5_pullback_classifier", "V3_ROLLING5_PULLBACK_CLASSIFIER_V1", ROLLING5_SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling30", entity_id, "rolling30_buy", "OLD_BUY", "OLD_BUY_PR", "OLD_BUY_BLOCK", None, None, None, None, None, "rolling30_watchlist_classifier", "REPORT_CANONICAL_CLASSIFICATION_V2_1", ROLLING30_OLD_SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling30", entity_id, "rolling30_exit", "OLD_EXIT", "OLD_EXIT_PR", None, "OLD_EXIT_RISK", None, None, None, None, "rolling30_watchlist_classifier", "REPORT_CANONICAL_CLASSIFICATION_V2_1", ROLLING30_OLD_SOURCE_RUN_ID, "OK"),
            ]
        )
    conn.executemany(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, classification_state, primary_reason, blocking_reason,
            risk_reason, next_action, priority_score, priority_label, sort_rank,
            source_classifier, classification_version, source_run_id, decision_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_unrelated_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id, snapshot_status
        ) VALUES (?, ?, ?, ?, 'rolling30', ?, 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling30', ?, 'unrelated_metric', 1.0, NULL, NULL, 'OK', 'SRC')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_family, signal_name, signal_value, signal_direction, signal_status,
            observed_date, source_table, source_run_id, source_event_id
        ) VALUES (?, ?, ?, ?, 'rolling30', ?, 'TEST', 'TEST_SIG', 'X', 'NEUTRAL', 'ACTIVE', ?, 'src', 'src_run', 'evt')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id, SIGNAL_DATE),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type,
            source_table, source_run_id, source_event_id, event_key, event_label, event_direction, event_status
        ) VALUES (?, ?, ?, ?, ?, 'UNKNOWN', 'src', 'src_run', 'evt', 'evt-key', 'Test event', 'NEUTRAL', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, entity_id, SIGNAL_DATE),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
            scope_entity_id, quality_status, expected_count, actual_count, warning_count, error_count, summary_note
        ) VALUES (?, ?, ?, ?, 'rolling30', 'TICKER', ?, 'OK', 1, 1, 0, 0, 'ok')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )


def _build_db(db_path: str) -> tuple[sqlite3.Connection, int, int, dict[str, int]]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    ticker_entity_ids = {
        "AAA": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="AAA"),
        "BBB": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="BBB"),
        "CCC": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="CCC"),
        "CRGY": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="CRGY"),
    }
    _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="LAYER", entity_code="LAYER_ONLY")
    for entity_id in ticker_entity_ids.values():
        _insert_coverage(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=entity_id, window_code="rolling30")
    _create_source_tables(conn)
    _insert_ticker_source_rows(conn)
    _insert_group_source_rows(conn)
    _insert_existing_classifications(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        ticker_entity_ids=ticker_entity_ids,
    )
    _insert_unrelated_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=ticker_entity_ids["AAA"],
    )
    conn.commit()
    return conn, ecosystem_id, taxonomy_version_id, ticker_entity_ids


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "rolling30_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_rolling30_watchlist_classifications(str(db_path), RUN_ID)


def test_builder_replaces_only_rolling30_and_preserves_other_data(tmp_path) -> None:
    db_path = tmp_path / "rolling30_replace.db"
    conn, _, _, ticker_entity_ids = _build_db(str(db_path))
    before_counts = {
        "classification": conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0],
        "metrics": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
        "signals": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
        "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
        "events": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
        "snapshots": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
        "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
        "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
        "runs": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
    }
    conn.close()

    summary = build_canonical_v3_rolling30_watchlist_classifications(
        str(db_path),
        RUN_ID,
        replace_existing=True,
    )

    conn = _connect(str(db_path))
    assert summary["classification_types"] == ["rolling30_buy", "rolling30_exit"]
    assert summary["window_code"] == "rolling30"
    assert summary["selected_ticker_entity_count"] == 4
    assert summary["selected_window_dates"] == [
        "2026-05-23",
        "2026-05-26",
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
    ]
    assert summary["context_rows_built"] == 3
    assert summary["classification_rows_inserted"] == 6
    assert summary["classification_rows_inserted_by_type"] == {
        "rolling30_buy": 3,
        "rolling30_exit": 3,
    }
    assert summary["classification_state_counts_by_type"] == {
        "rolling30_buy": {"BUY_ZONE": 1, "INSUFFICIENT_DATA": 1, "AVOID": 1},
        "rolling30_exit": {"NORMAL": 1, "INSUFFICIENT_DATA": 1, "EXIT_ZONE": 1},
    }
    assert summary["decision_status_counts_by_type"] == {
        "rolling30_buy": {"OK": 3},
        "rolling30_exit": {"OK": 3},
    }
    assert summary["field_coverage_counts_by_type"] == {
        "rolling30_buy": {
            "primary_reason": 3,
            "blocking_reason": 2,
            "risk_reason": 0,
            "next_action": 0,
            "priority_score": 0,
            "priority_label": 0,
            "sort_rank": 0,
        },
        "rolling30_exit": {
            "primary_reason": 3,
            "blocking_reason": 0,
            "risk_reason": 2,
            "next_action": 0,
            "priority_score": 0,
            "priority_label": 0,
            "sort_rank": 0,
        },
    }
    assert summary["source_dependency_summary"]["runtime_excludes"] == [
        "dc_report_classification_v2",
        "dc_report_context_window_v2",
    ]
    assert summary["rows_deleted_on_replace"] == 8
    assert summary["warning_count"] == 1
    assert summary["warnings"] == ["Missing lower-level ticker history for rolling30 ticker 'CRGY'"]
    assert "replaces only rolling30_buy and rolling30_exit" in summary["limitations"]
    assert "rolling2_sell_pressure and rolling5_pullback remain as-is" in summary["limitations"]

    assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0] == before_counts["metrics"]
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == before_counts["signals"]
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == before_counts["relevance"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == before_counts["events"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == before_counts["snapshots"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == before_counts["coverage"]
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == before_counts["quality"]
    assert conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == before_counts["runs"]
    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == before_counts["classification"] - 2

    rows = conn.execute(
        """
        SELECT e.entity_code, classification_type, classification_state, primary_reason, blocking_reason,
               risk_reason, next_action, source_classifier, classification_version, source_run_id,
               priority_score, priority_label, sort_rank
        FROM eco_classification_decision d
        JOIN eco_entity e ON e.entity_id = d.entity_id
        WHERE classification_type IN ('rolling30_buy', 'rolling30_exit')
        ORDER BY e.entity_code, classification_type
        """
    ).fetchall()
    assert len(rows) == 6
    rows_by_key = {(row["entity_code"], row["classification_type"]): row for row in rows}
    assert rows_by_key[("AAA", "rolling30_buy")]["classification_state"] == "BUY_ZONE"
    assert rows_by_key[("AAA", "rolling30_buy")]["primary_reason"] == "UP_STRUCTURE_WITH_REPEATED_BUY_SIGNAL"
    assert rows_by_key[("AAA", "rolling30_buy")]["blocking_reason"] is None
    assert rows_by_key[("AAA", "rolling30_exit")]["classification_state"] == "NORMAL"
    assert rows_by_key[("AAA", "rolling30_exit")]["risk_reason"] is None
    assert rows_by_key[("BBB", "rolling30_buy")]["classification_state"] == "INSUFFICIENT_DATA"
    assert rows_by_key[("BBB", "rolling30_buy")]["blocking_reason"] == "price_data_missing"
    assert rows_by_key[("BBB", "rolling30_exit")]["classification_state"] == "INSUFFICIENT_DATA"
    assert rows_by_key[("CCC", "rolling30_buy")]["classification_state"] == "AVOID"
    assert rows_by_key[("CCC", "rolling30_buy")]["blocking_reason"] == "CURRENT_HIGH_EXIT_RISK"
    assert rows_by_key[("CCC", "rolling30_exit")]["classification_state"] == "EXIT_ZONE"
    assert rows_by_key[("CCC", "rolling30_exit")]["risk_reason"] == "CURRENT_HIGH_EXIT_RISK"
    assert ("CRGY", "rolling30_buy") not in rows_by_key
    assert ("CRGY", "rolling30_exit") not in rows_by_key

    for row in rows:
        assert row["source_classifier"] == "rolling30_watchlist_classifier"
        assert row["classification_version"] == "V3_ROLLING30_WATCHLIST_CLASSIFIER_V1"
        assert row["source_run_id"] == "V3_ROLLING30_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29"
        assert row["priority_score"] is None
        assert row["priority_label"] is None
        assert row["sort_rank"] is None

    assert conn.execute(
        "SELECT COUNT(*) FROM eco_classification_decision WHERE classification_type = 'daily_trigger'"
    ).fetchone()[0] == len(ticker_entity_ids)
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_classification_decision
        WHERE classification_type = 'rolling2_sell_pressure'
          AND classification_version = 'V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1'
          AND source_run_id = ?
        """,
        (ROLLING2_SOURCE_RUN_ID,),
    ).fetchone()[0] == len(ticker_entity_ids)
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_classification_decision
        WHERE classification_type = 'rolling5_pullback'
          AND classification_version = 'V3_ROLLING5_PULLBACK_CLASSIFIER_V1'
          AND source_run_id = ?
        """,
        (ROLLING5_SOURCE_RUN_ID,),
    ).fetchone()[0] == len(ticker_entity_ids)
    conn.close()


def test_builder_replace_existing_false_rejects_existing_rows(tmp_path) -> None:
    db_path = tmp_path / "rolling30_existing_rows.db"
    conn, _, _, _ = _build_db(str(db_path))
    conn.close()

    with pytest.raises(ValueError, match="rows already exist"):
        build_canonical_v3_rolling30_watchlist_classifications(
            str(db_path),
            RUN_ID,
            replace_existing=False,
        )


def test_builder_is_idempotent_reuses_classifiers_and_avoids_v2_runtime_sources(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "rolling30_idempotent.db"
    conn, _, _, _ = _build_db(str(db_path))
    conn.close()

    calls = {"buy": 0, "exit": 0}
    traced_sql: list[str] = []
    original_buy = builder_module.classify_rolling_30_buy_row
    original_exit = builder_module.classify_rolling_30_exit_row
    original_connect = builder_module._connect

    def wrapped_buy(row):
        calls["buy"] += 1
        return original_buy(row)

    def wrapped_exit(row):
        calls["exit"] += 1
        return original_exit(row)

    def traced_connect(path: str):
        conn = original_connect(path)
        conn.set_trace_callback(traced_sql.append)
        return conn

    monkeypatch.setattr(builder_module, "classify_rolling_30_buy_row", wrapped_buy)
    monkeypatch.setattr(builder_module, "classify_rolling_30_exit_row", wrapped_exit)
    monkeypatch.setattr(builder_module, "_connect", traced_connect)

    summary_first = build_canonical_v3_rolling30_watchlist_classifications(
        str(db_path),
        RUN_ID,
        replace_existing=True,
    )
    summary_second = build_canonical_v3_rolling30_watchlist_classifications(
        str(db_path),
        RUN_ID,
        replace_existing=True,
    )

    conn = _connect(str(db_path))
    assert calls["buy"] >= 6
    assert calls["exit"] >= 6
    assert summary_first["classification_rows_inserted"] == 6
    assert summary_second["classification_rows_inserted"] == 6
    assert summary_first["rows_deleted_on_replace"] == 8
    assert summary_second["rows_deleted_on_replace"] == 6
    assert conn.execute(
        "SELECT COUNT(*) FROM eco_classification_decision WHERE classification_type IN ('rolling30_buy', 'rolling30_exit')"
    ).fetchone()[0] == 6
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_classification_decision
        WHERE classification_type IN ('rolling30_buy', 'rolling30_exit')
          AND source_run_id = 'V3_ROLLING30_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29'
        """
    ).fetchone()[0] == 6
    assert not any("dc_report_classification_v2" in statement.lower() for statement in traced_sql)
    assert not any("dc_report_context_window_v2" in statement.lower() for statement in traced_sql)
    conn.close()
