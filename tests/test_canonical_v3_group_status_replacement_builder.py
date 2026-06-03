import sqlite3

import pytest

from rawcandle.report_canonical_v3_group_status_replacement_builder import (
    build_canonical_v3_group_status_from_group_swing,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_RUN_ID = "DC_GROUP_SWING_20260602_DC_SWING_SIGNAL_V1"
WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
REPLACEMENT_METRICS = (
    "group_overheat_risk_level",
    "group_current_status",
    "group_timing_state",
    "group_timing_reason",
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code, ecosystem_name, description, status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id, version_code, version_label, source_type, source_reference,
            effective_from, effective_to, is_active, status
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
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker, exchange, market, currency, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, entity_type, entity_code, entity_name, None, None, None, None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
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
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
            coverage_status, source_row_count, missing_component_count, coverage_notes
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
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            overheat_risk_level TEXT NULL,
            timing_state TEXT NULL,
            timing_reason TEXT NULL,
            signal_version TEXT NOT NULL,
            run_id TEXT NULL
        )
        """
    )


def _insert_source_row(
    conn: sqlite3.Connection,
    *,
    group_type: str,
    group_name: str,
    timing_state: str | None,
    timing_reason: str | None,
    overheat_risk_level: str | None,
    run_id: str | None = SOURCE_RUN_ID,
    signal_version: str = "DC_SWING_SIGNAL_V1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, group_type, group_name, overheat_risk_level,
            timing_state, timing_reason, signal_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            group_type,
            group_name,
            overheat_risk_level,
            timing_state,
            timing_reason,
            signal_version,
            run_id,
        ),
    )


def _insert_metric_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
    metric_name: str,
    metric_value_text: str,
    source_run_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            entity_id,
            metric_name,
            None,
            metric_value_text,
            None,
            "OK",
            source_run_id,
        ),
    )


def _setup_db(db_path: str) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    layer_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="LAYER",
        entity_code="BACKUP_POWER",
        entity_name="Backup power",
    )
    subindustry_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="SUBINDUSTRY",
        entity_code="COLOCATION_DATACENTER_REIT",
        entity_name="Colocation / datacenter REIT",
    )
    ticker_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="TICKER",
        entity_code="NVDA",
        entity_name="NVIDIA",
    )
    missing_layer_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="LAYER",
        entity_code="MISSING_GROUP",
        entity_name="Missing group",
    )
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    for entity_id in (layer_id, subindustry_id, ticker_id, missing_layer_id):
        for window_code in WINDOWS:
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                window_code=window_code,
            )
    _create_source_table(conn)
    _insert_source_row(
        conn,
        group_type="layer",
        group_name="Backup power",
        timing_state="TRIM_WATCH",
        timing_reason="TRIM_WATCH:return_10d_neg",
        overheat_risk_level="LOW",
    )
    _insert_source_row(
        conn,
        group_type="subindustry",
        group_name="Colocation / datacenter REIT",
        timing_state="EXIT_ZONE",
        timing_reason="EXIT_ZONE:return_20d_neg",
        overheat_risk_level="HIGH",
        run_id=None,
        signal_version="DC_SWING_SIGNAL_FALLBACK_V1",
    )
    _insert_metric_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=layer_id,
        window_code="rolling30",
        metric_name="group_window_status",
        metric_value_text="EXIT_ZONE",
        source_run_id="preserve-me",
    )
    _insert_metric_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=layer_id,
        window_code="rolling30",
        metric_name="group_status_change",
        metric_value_text="BUY_ZONE -> TRIM_WATCH",
        source_run_id="preserve-me",
    )
    _insert_metric_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=layer_id,
        window_code="daily",
        metric_name="freshness_latest_structure_class",
        metric_value_text="FRESH",
        source_run_id="freshness-source",
    )
    _insert_metric_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=ticker_id,
        window_code="daily",
        metric_name="distance_to_ema20_pct",
        metric_value_text="1.5",
        source_run_id="other-source",
    )
    conn.commit()
    conn.close()
    return {
        "ecosystem_id": ecosystem_id,
        "taxonomy_version_id": taxonomy_version_id,
        "layer_id": layer_id,
        "subindustry_id": subindustry_id,
        "ticker_id": ticker_id,
        "missing_layer_id": missing_layer_id,
    }


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    apply_report_canonical_v3_migration(db_path)

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID)


def test_builder_writes_only_confirmed_metrics_and_preserves_existing_rows(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    ids = _setup_db(db_path)

    summary = build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID, replace_existing=False)

    assert summary["source_classifications"] == {"dc_group_swing_signal_daily": "DERIVED_FROM_RAW_SOURCE"}
    assert summary["selected_group_entity_count"] == 3
    assert summary["window_count"] == 4
    assert summary["source_rows_read"] == 2
    assert summary["source_rows_mapped"] == 2
    assert summary["source_rows_skipped"] == 0
    assert summary["missing_source_groups"] == ["LAYER:Missing group"]
    assert summary["metric_rows_inserted"] == 32
    assert summary["metric_name_counts"] == {
        "group_current_status": 8,
        "group_overheat_risk_level": 8,
        "group_timing_reason": 8,
        "group_timing_state": 8,
    }
    assert "partial replacement only" in summary["limitations"]
    assert "group_window_status and group_status_change remain transitional" in summary["limitations"]
    assert "no signal rows are created" in summary["limitations"]

    conn = _connect(db_path)
    metric_rows = conn.execute(
        """
        SELECT e.entity_type, e.entity_name, m.window_code, m.metric_name, m.metric_value_text, m.source_run_id
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.metric_name IN (
            'group_overheat_risk_level', 'group_current_status', 'group_timing_state', 'group_timing_reason'
        )
        ORDER BY e.entity_type, e.entity_name, m.window_code, m.metric_name
        """
    ).fetchall()
    assert len(metric_rows) == 32
    assert {row["metric_name"] for row in metric_rows} == set(REPLACEMENT_METRICS)
    assert {row["window_code"] for row in metric_rows} == set(WINDOWS)
    assert {row["entity_type"] for row in metric_rows} == {"LAYER", "SUBINDUSTRY"}
    assert all(row["entity_name"] != "Missing group" for row in metric_rows)

    layer_daily = {
        row["metric_name"]: (row["metric_value_text"], row["source_run_id"])
        for row in metric_rows
        if row["entity_name"] == "Backup power" and row["window_code"] == "daily"
    }
    assert layer_daily == {
        "group_current_status": ("TRIM_WATCH", SOURCE_RUN_ID),
        "group_overheat_risk_level": ("LOW", SOURCE_RUN_ID),
        "group_timing_reason": ("TRIM_WATCH:return_10d_neg", SOURCE_RUN_ID),
        "group_timing_state": ("TRIM_WATCH", SOURCE_RUN_ID),
    }
    sub_daily = {
        row["metric_name"]: (row["metric_value_text"], row["source_run_id"])
        for row in metric_rows
        if row["entity_name"] == "Colocation / datacenter REIT" and row["window_code"] == "daily"
    }
    assert sub_daily == {
        "group_current_status": ("EXIT_ZONE", "DC_SWING_SIGNAL_FALLBACK_V1"),
        "group_overheat_risk_level": ("HIGH", "DC_SWING_SIGNAL_FALLBACK_V1"),
        "group_timing_reason": ("EXIT_ZONE:return_20d_neg", "DC_SWING_SIGNAL_FALLBACK_V1"),
        "group_timing_state": ("EXIT_ZONE", "DC_SWING_SIGNAL_FALLBACK_V1"),
    }

    preserved = conn.execute(
        """
        SELECT metric_name, metric_value_text, source_run_id
        FROM eco_entity_metric_value
        WHERE metric_name IN ('group_window_status', 'group_status_change', 'freshness_latest_structure_class', 'distance_to_ema20_pct')
        ORDER BY metric_name
        """
    ).fetchall()
    assert [(row["metric_name"], row["metric_value_text"], row["source_run_id"]) for row in preserved] == [
        ("distance_to_ema20_pct", "1.5", "other-source"),
        ("freshness_latest_structure_class", "FRESH", "freshness-source"),
        ("group_status_change", "BUY_ZONE -> TRIM_WATCH", "preserve-me"),
        ("group_window_status", "EXIT_ZONE", "preserve-me"),
    ]

    assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_report_run WHERE run_id = ?", (RUN_ID,)).fetchone()[0] == 1
    conn.close()


def test_replace_existing_false_rejects_and_true_replaces_only_scope(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    ids = _setup_db(db_path)
    build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID, replace_existing=False)

    with pytest.raises(ValueError, match="already exist"):
        build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID, replace_existing=False)

    conn = _connect(db_path)
    conn.execute(
        """
        UPDATE eco_entity_metric_value
        SET metric_value_text = 'OLD_VALUE', source_run_id = 'old-source'
        WHERE metric_name = 'group_current_status'
          AND entity_id = ?
          AND window_code = 'daily'
        """,
        (ids["layer_id"],),
    )
    conn.commit()
    conn.close()

    summary = build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID, replace_existing=True)
    assert summary["rows_deleted_on_replace"] == 32

    conn = _connect(db_path)
    replaced = conn.execute(
        """
        SELECT metric_value_text, source_run_id
        FROM eco_entity_metric_value
        WHERE metric_name = 'group_current_status'
          AND entity_id = ?
          AND window_code = 'daily'
        """,
        (ids["layer_id"],),
    ).fetchone()
    assert tuple(replaced) == ("TRIM_WATCH", SOURCE_RUN_ID)

    preserved = conn.execute(
        """
        SELECT metric_value_text, source_run_id
        FROM eco_entity_metric_value
        WHERE metric_name = 'group_window_status'
          AND entity_id = ?
        """,
        (ids["layer_id"],),
    ).fetchone()
    assert tuple(preserved) == ("EXIT_ZONE", "preserve-me")
    conn.close()


def test_replace_existing_true_is_idempotent(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    _setup_db(db_path)

    first = build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID, replace_existing=True)
    second = build_canonical_v3_group_status_from_group_swing(db_path, RUN_ID, replace_existing=True)

    assert first["metric_rows_inserted"] == 32
    assert second["metric_rows_inserted"] == 32
    assert second["rows_deleted_on_replace"] == 32

    conn = _connect(db_path)
    counts = conn.execute(
        """
        SELECT metric_name, COUNT(*)
        FROM eco_entity_metric_value
        WHERE metric_name IN (
            'group_overheat_risk_level', 'group_current_status', 'group_timing_state', 'group_timing_reason',
            'group_window_status', 'group_status_change', 'freshness_latest_structure_class', 'distance_to_ema20_pct'
        )
        GROUP BY metric_name
        ORDER BY metric_name
        """
    ).fetchall()
    assert [(row["metric_name"], row[1]) for row in counts] == [
        ("distance_to_ema20_pct", 1),
        ("freshness_latest_structure_class", 1),
        ("group_current_status", 8),
        ("group_overheat_risk_level", 8),
        ("group_status_change", 1),
        ("group_timing_reason", 8),
        ("group_timing_state", 8),
        ("group_window_status", 1),
    ]
    conn.close()
