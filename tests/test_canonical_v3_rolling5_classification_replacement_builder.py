import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_rolling5_classification_replacement_builder import (
    build_canonical_v3_rolling5_pullback_classifications,
)
import rawcandle.report_canonical_v3_rolling5_classification_replacement_builder as builder_module


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"
ROLLING2_SOURCE_RUN_ID = "V3_ROLLING2_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29"


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


def _insert_ticker_entity(conn: sqlite3.Connection, ecosystem_id: int, ticker: str) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, status
            ) VALUES (?, 'TICKER', ?, ?, ?, 'ACTIVE')
            """,
            (ecosystem_id, ticker, ticker, ticker),
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
        ("2026-05-23", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.08, "OK", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-26", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.07, "OK", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-27", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 1, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.06, "OK", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-28", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 0, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.05, "OK", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-29", "DC_TAXONOMY_FULL_V1", "AAA", "LAYER_A", "SUB_A", 0, 1, 0, 0, 0, None, None, "BOS_UP", "AGING", None, None, "HH", 0.04, "OK", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-23", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-26", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-27", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-28", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
        ("2026-05-29", "DC_TAXONOMY_FULL_V1", "BBB", "LAYER_B", "SUB_B", 0, 0, 0, 0, 0, None, None, None, None, None, None, None, 0.0, "MISSING_AS_OF_DATE", "UP", None, "DC_SWING_SIGNAL_V1", "DC_TICKER_SWING_RUN"),
    ]
    conn.executemany(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date,
            taxonomy_version,
            ticker,
            primary_layer,
            primary_subindustry,
            breakout_signal,
            pullback_signal,
            fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            exit_reason,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
            latest_structure_label,
            distance_to_ema20_pct,
            price_data_status,
            ticker_trend_state,
            latest_bearish_relevance_class,
            signal_version,
            run_id
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
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
            ]
        )
    conn.executemany("INSERT INTO dc_group_swing_signal_daily VALUES (?,?,?,?,?,?,?,?)", rows)


def _insert_existing_classifications(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_ids: dict[str, int],
) -> None:
    rows = []
    for ticker, entity_id in entity_ids.items():
        rows.extend(
            [
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "daily_trigger", "SELL_TRIGGER", "PR", None, None, "NA", None, None, None, "daily_trigger", "V2", SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling2", entity_id, "rolling2_sell_pressure", "KEEP_STATE", "KEEP_PR", None, "KEEP_RISK", "KEEP_ACTION", None, None, None, "rolling2_sell_pressure_classifier", "V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1", ROLLING2_SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling5", entity_id, "rolling5_pullback", "OLD_STATE", "OLD_PR", "OLD_BLOCK", None, "OLD_ACTION", None, None, None, "rolling5_pullback_classifier", "V2", SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling30", entity_id, "rolling30_buy", "WATCH_ZONE", "PR", "BR", None, None, None, None, None, "rolling30_watchlist_classifier", "V2", SOURCE_RUN_ID, "OK"),
                (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "rolling30", entity_id, "rolling30_exit", "WATCH", "PR", None, "RR", None, None, None, None, "rolling30_watchlist_classifier", "V2", SOURCE_RUN_ID, "OK"),
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
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'unrelated_metric', 1.0, NULL, NULL, 'OK', 'SRC')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_family, signal_name, signal_value, signal_direction, signal_status,
            observed_date, source_table, source_run_id, source_event_id
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'TEST', 'TEST_SIG', 'X', 'NEUTRAL', 'ACTIVE', ?, 'src', 'src_run', 'evt')
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
        ) VALUES (?, ?, ?, ?, 'rolling5', 'TICKER', ?, 'OK', 1, 1, 0, 0, 'ok')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )


def _build_db(db_path: str) -> tuple[sqlite3.Connection, int, int, dict[str, int]]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    entity_ids = {
        "AAA": _insert_ticker_entity(conn, ecosystem_id, "AAA"),
        "BBB": _insert_ticker_entity(conn, ecosystem_id, "BBB"),
    }
    for entity_id in entity_ids.values():
        _insert_coverage(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=entity_id, window_code="rolling5")
    _create_source_tables(conn)
    _insert_ticker_source_rows(conn)
    _insert_group_source_rows(conn)
    _insert_existing_classifications(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_ids=entity_ids,
    )
    _insert_unrelated_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=entity_ids["AAA"],
    )
    conn.commit()
    return conn, ecosystem_id, taxonomy_version_id, entity_ids


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "rolling5_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_rolling5_pullback_classifications(str(db_path), RUN_ID)


def test_builder_replaces_only_rolling5_and_preserves_other_data(tmp_path) -> None:
    db_path = tmp_path / "rolling5_replace.db"
    conn, _, _, _ = _build_db(str(db_path))
    before_counts = {
        "classification": conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0],
        "metrics": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
        "signals": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
        "events": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
        "snapshots": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
        "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
        "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
        "runs": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
    }
    conn.close()

    summary = build_canonical_v3_rolling5_pullback_classifications(
        str(db_path),
        RUN_ID,
        replace_existing=True,
    )

    conn = _connect(str(db_path))
    assert summary["classification_type"] == "rolling5_pullback"
    assert summary["window_code"] == "rolling5"
    assert summary["selected_ticker_entity_count"] == 2
    assert summary["selected_window_dates"] == [
        "2026-05-23",
        "2026-05-26",
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
    ]
    assert summary["context_rows_built"] == 2
    assert summary["classification_rows_inserted"] == 2
    assert summary["classification_state_counts"] == {
        "PULLBACK_CANDIDATE": 1,
        "INSUFFICIENT_DATA": 1,
    }
    assert summary["decision_status_counts"] == {"OK": 2}
    assert summary["field_coverage_counts"] == {
        "primary_reason": 2,
        "blocking_reason": 1,
        "risk_reason": 0,
        "next_action": 2,
        "priority_score": 0,
        "priority_label": 0,
        "sort_rank": 0,
    }
    assert summary["source_dependency_summary"]["runtime_excludes"] == [
        "dc_report_classification_v2",
        "dc_report_context_window_v2",
    ]
    assert summary["rows_deleted_on_replace"] == 2
    assert "replaces only rolling5_pullback" in summary["limitations"]
    assert (
        "does not use dc_report_context_window_v2 as runtime source unless stopped/reported"
        in summary["limitations"]
    )

    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == before_counts["classification"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0] == before_counts["metrics"]
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == before_counts["signals"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == before_counts["events"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == before_counts["snapshots"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == before_counts["coverage"]
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == before_counts["quality"]
    assert conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == before_counts["runs"]

    rows = conn.execute(
        """
        SELECT classification_type, classification_state, primary_reason, blocking_reason, risk_reason,
               next_action, priority_score, priority_label, sort_rank, source_classifier,
               classification_version, source_run_id
        FROM eco_classification_decision
        WHERE classification_type = 'rolling5_pullback'
        ORDER BY entity_id
        """
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["classification_state"] == "PULLBACK_CANDIDATE"
    assert rows[0]["primary_reason"] == "CONFIRMED_EMA10_PULLBACK_CONTEXT"
    assert rows[0]["blocking_reason"] is None
    assert rows[0]["risk_reason"] is None
    assert rows[0]["next_action"] == "REVIEW_FOR_DAILY_TRIGGER"
    assert rows[0]["source_classifier"] == "rolling5_pullback_classifier"
    assert rows[0]["classification_version"] == "V3_ROLLING5_PULLBACK_CLASSIFIER_V1"
    assert rows[0]["source_run_id"] == "V3_ROLLING5_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29"
    assert rows[0]["priority_score"] is None
    assert rows[0]["priority_label"] is None
    assert rows[0]["sort_rank"] is None
    assert rows[1]["classification_state"] == "INSUFFICIENT_DATA"
    assert rows[1]["blocking_reason"] == "price_data_missing"

    rolling2_rows = conn.execute(
        """
        SELECT classification_state, source_classifier, classification_version, source_run_id
        FROM eco_classification_decision
        WHERE classification_type = 'rolling2_sell_pressure'
        ORDER BY entity_id
        """
    ).fetchall()
    assert len(rolling2_rows) == 2
    assert all(row["classification_state"] == "KEEP_STATE" for row in rolling2_rows)
    assert all(row["classification_version"] == "V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1" for row in rolling2_rows)
    assert all(row["source_run_id"] == ROLLING2_SOURCE_RUN_ID for row in rolling2_rows)
    conn.close()


def test_builder_replace_existing_false_rejects_existing_rows(tmp_path) -> None:
    db_path = tmp_path / "rolling5_existing_rows.db"
    conn, _, _, _ = _build_db(str(db_path))
    conn.close()

    with pytest.raises(ValueError, match="rows already exist"):
        build_canonical_v3_rolling5_pullback_classifications(
            str(db_path),
            RUN_ID,
            replace_existing=False,
        )


def test_builder_is_idempotent_and_reuses_classifier(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "rolling5_idempotent.db"
    conn, _, _, _ = _build_db(str(db_path))
    conn.close()

    calls = {"count": 0}
    original = builder_module.classify_rolling_5_pullback_row

    def wrapped(row):
        calls["count"] += 1
        return original(row)

    monkeypatch.setattr(builder_module, "classify_rolling_5_pullback_row", wrapped)

    summary_first = build_canonical_v3_rolling5_pullback_classifications(
        str(db_path),
        RUN_ID,
        replace_existing=True,
    )
    summary_second = build_canonical_v3_rolling5_pullback_classifications(
        str(db_path),
        RUN_ID,
        replace_existing=True,
    )

    conn = _connect(str(db_path))
    assert calls["count"] >= 4
    assert summary_first["classification_rows_inserted"] == 2
    assert summary_second["classification_rows_inserted"] == 2
    assert summary_first["rows_deleted_on_replace"] == 2
    assert summary_second["rows_deleted_on_replace"] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM eco_classification_decision WHERE classification_type = 'rolling5_pullback'"
    ).fetchone()[0] == 2
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_classification_decision
        WHERE classification_type = 'rolling5_pullback'
          AND source_run_id = 'V3_ROLLING5_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29'
        """
    ).fetchone()[0] == 2
    conn.close()
