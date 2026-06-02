import sqlite3

import pytest

from rawcandle.report_canonical_v3_group_status_metric_builder import (
    build_canonical_v3_group_status_metrics,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code,
            ecosystem_name,
            description,
            status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id,
            version_code,
            version_label,
            source_type,
            source_reference,
            effective_from,
            effective_to,
            is_active,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, "DC_TAXONOMY_FULL_V1", "V1", None, None, None, None, 1, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
    entity_name: str,
    ticker: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            exchange,
            market,
            currency,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, entity_type, entity_code, entity_name, ticker, None, None, None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            run_type,
            status,
            warning_count,
            error_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, SIGNAL_DATE, "BUILD", "OK", 0, 0),
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
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            in_taxonomy,
            in_watchlist,
            has_instrument,
            has_price_data,
            has_daily_signal,
            has_window_context,
            coverage_status,
            source_row_count,
            missing_component_count,
            coverage_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            entity_id,
            1,
            1,
            1,
            1,
            1,
            1,
            "OK",
            1,
            0,
            None,
        ),
    )


def _create_source_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_report_context_group_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            horizon TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            timing_state TEXT NULL,
            timing_reason TEXT NULL,
            overheat_risk_level TEXT NULL,
            group_current_status TEXT NULL,
            group_window_status TEXT NULL,
            group_status_change TEXT NULL,
            run_id TEXT NOT NULL
        )
        """
    )


def _insert_source_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, horizon, group_type, group_name,
            timing_state, timing_reason, overheat_risk_level,
            group_current_status, group_window_status, group_status_change, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "daily",
            "layer",
            "AI Compute",
            "TRIM_WATCH",
            "breadth_weak",
            "LOW",
            "TRIM_WATCH",
            None,
            None,
            "group-source",
        ),
    )
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, horizon, group_type, group_name,
            timing_state, timing_reason, overheat_risk_level,
            group_current_status, group_window_status, group_status_change, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "rolling5",
            "subindustry",
            "GPU",
            "EXIT_ZONE",
            "weakness_breadth_gt_60",
            "HIGH",
            "EXIT_ZONE",
            "EXIT_ZONE",
            "TRIM_WATCH -> EXIT_ZONE",
            "group-source",
        ),
    )
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, horizon, group_type, group_name,
            timing_state, timing_reason, overheat_risk_level,
            group_current_status, group_window_status, group_status_change, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "rolling30",
            "layer",
            "Unmapped Layer",
            "NEUTRAL",
            "no_state_rule",
            "LOW",
            "NEUTRAL",
            "NEUTRAL",
            None,
            "group-source",
        ),
    )


def _insert_supporting_fact_rows(
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "OK"),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "metric_a", 1.0, None, None, "OK"),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "freshness_latest_bos_class", None, "FRESH", None, "OK"),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope, scope_entity_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", "LAYER", entity_id, "OK"),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            entity_id,
            "sig",
            "REVERSAL_MEDIUM",
            "UP",
            "yes",
            SIGNAL_DATE,
            "technical_signal_relevance",
            "tech-run",
            "sig-1",
            "ACTIVE",
        ),
    )
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, classification_state, decision_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "daily_trigger", "SELL_TRIGGER", "OK"),
    )


def _setup_db(db_path: str) -> sqlite3.Connection:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    ticker_id = _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="NVDA", entity_name="NVDA", ticker="NVDA")
    layer_id = _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="LAYER", entity_code="AI_COMPUTE", entity_name="AI Compute")
    subindustry_id = _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="SUBINDUSTRY", entity_code="GPU", entity_name="GPU")
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    for window_code in ("daily", "rolling2", "rolling5", "rolling30"):
        _insert_coverage(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=ticker_id, window_code=window_code)
        _insert_coverage(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, window_code=window_code)
        _insert_coverage(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=subindustry_id, window_code=window_code)
    _create_source_table(conn)
    _insert_source_rows(conn)
    _insert_supporting_fact_rows(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id)
    conn.commit()
    return conn


def test_group_status_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_group_status_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_group_status_metrics(str(db_path), RUN_ID)


def test_group_status_builder_writes_group_metrics_only(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_group_status_builder.db"
    conn = _setup_db(str(db_path))
    conn.close()

    summary = build_canonical_v3_group_status_metrics(str(db_path), RUN_ID)

    conn = _connect(str(db_path))
    try:
        metric_names = {
            row["metric_name"]
            for row in conn.execute(
                """
                SELECT DISTINCT metric_name
                FROM eco_entity_metric_value
                WHERE run_id = ?
                  AND metric_name IN (
                    'group_overheat_risk_level',
                    'group_current_status',
                    'group_window_status',
                    'group_status_change',
                    'group_timing_state',
                    'group_timing_reason'
                  )
                """,
                (RUN_ID,),
            ).fetchall()
        }
        assert metric_names == {
            "group_overheat_risk_level",
            "group_current_status",
            "group_window_status",
            "group_status_change",
            "group_timing_state",
            "group_timing_reason",
        }

        layer_metric = conn.execute(
            """
            SELECT metric_value_text, source_run_id
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND e.entity_type = 'LAYER'
              AND e.entity_code = 'AI_COMPUTE'
              AND mv.window_code = 'daily'
              AND mv.metric_name = 'group_overheat_risk_level'
            """,
            (RUN_ID,),
        ).fetchone()
        assert layer_metric["metric_value_text"] == "LOW"
        assert layer_metric["source_run_id"] == "group-source"

        subindustry_metric = conn.execute(
            """
            SELECT metric_value_text
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND e.entity_type = 'SUBINDUSTRY'
              AND e.entity_code = 'GPU'
              AND mv.window_code = 'rolling5'
              AND mv.metric_name = 'group_status_change'
            """,
            (RUN_ID,),
        ).fetchone()
        assert subindustry_metric["metric_value_text"] == "TRIM_WATCH -> EXIT_ZONE"

        ticker_targeted = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND e.entity_type = 'TICKER'
              AND mv.metric_name IN (
                'group_overheat_risk_level',
                'group_current_status',
                'group_window_status',
                'group_status_change',
                'group_timing_state',
                'group_timing_reason'
              )
            """,
            (RUN_ID,),
        ).fetchone()[0]
        assert ticker_targeted == 0

        signal_count = conn.execute("SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'GROUP_STATUS'").fetchone()[0]
        relevance_count = conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0]
        assert signal_count == 0
        assert relevance_count == 0
        assert event_count == 0

        assert summary["source_classifications"] == {
            "dc_report_context_group_v2": "TRANSITIONAL_V2_SOURCE",
            "dc_report_context_window_v2": "TRANSITIONAL_V2_SOURCE",
            "dc_group_swing_signal_daily": "DERIVED_FROM_RAW_SOURCE",
        }
        assert "no overheat transition events are created" in summary["limitations"]
        assert "no group rotation events are created" in summary["limitations"]
        assert "empty progression/relative-change support tables were not used" in summary["limitations"]
        assert "metric source_table lineage is not available if eco_entity_metric_value lacks source_table column" in summary["limitations"]
        assert summary["warning_count"] == 1
    finally:
        conn.close()


def test_group_status_builder_preserves_other_facts_and_metrics(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_group_status_preserve.db"
    conn = _setup_db(str(db_path))
    conn.close()

    before = _connect(str(db_path))
    try:
        snapshot_count = before.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0]
        coverage_count = before.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0]
        quality_count = before.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0]
        classification_count = before.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0]
        run_count = before.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0]
        freshness_metric_count = before.execute(
            "SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name = 'freshness_latest_bos_class'"
        ).fetchone()[0]
        unrelated_metric_count = before.execute(
            "SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name = 'metric_a'"
        ).fetchone()[0]
    finally:
        before.close()

    build_canonical_v3_group_status_metrics(str(db_path), RUN_ID)

    after = _connect(str(db_path))
    try:
        assert after.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == snapshot_count
        assert after.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == coverage_count
        assert after.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == quality_count
        assert after.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == classification_count
        assert after.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == run_count
        assert after.execute(
            "SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name = 'freshness_latest_bos_class'"
        ).fetchone()[0] == freshness_metric_count
        assert after.execute(
            "SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name = 'metric_a'"
        ).fetchone()[0] == unrelated_metric_count
    finally:
        after.close()


def test_group_status_builder_replace_behavior(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_group_status_replace.db"
    conn = _setup_db(str(db_path))
    conn.close()

    first_summary = build_canonical_v3_group_status_metrics(str(db_path), RUN_ID)
    assert first_summary["metric_rows_inserted"] > 0

    with pytest.raises(ValueError, match="Group status builder-owned rows already exist"):
        build_canonical_v3_group_status_metrics(str(db_path), RUN_ID, replace_existing=False)

    second_summary = build_canonical_v3_group_status_metrics(str(db_path), RUN_ID, replace_existing=True)
    assert second_summary["metric_rows_inserted"] == first_summary["metric_rows_inserted"]

    conn = _connect(str(db_path))
    try:
        builder_owned_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value
            WHERE run_id = ?
              AND metric_name IN (
                'group_overheat_risk_level',
                'group_current_status',
                'group_window_status',
                'group_status_change',
                'group_timing_state',
                'group_timing_reason'
              )
            """,
            (RUN_ID,),
        ).fetchone()[0]
        assert builder_owned_count == first_summary["metric_rows_inserted"]
    finally:
        conn.close()
