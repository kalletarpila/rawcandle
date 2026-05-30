import sqlite3

import pytest

from analysis.datacenter_indices.report_canonical_v2_group_context_builder import (
    build_report_group_context_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            parent_group_type TEXT NULL,
            parent_group_name TEXT NULL,
            timing_state TEXT NULL,
            overheat_risk_level TEXT NULL,
            return_2d REAL NULL,
            return_5d REAL NULL,
            return_30d REAL NULL,
            ema20_breadth_delta_5d REAL NULL,
            ma10_breadth_delta_5d REAL NULL,
            trend_breadth REAL NULL,
            weakness_breadth REAL NULL,
            strength_breadth REAL NULL,
            data_quality_status TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            calc_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            synthetic_close REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            trend_classification TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    return conn


def _insert_run(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            market,
            calculation_version,
            source_versions_json,
            created_at_utc,
            status,
            warning_count,
            error_count,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "REPORT_CANONICAL_V2",
            None,
            "2026-05-30T00:00:00Z",
            "OK",
            0,
            0,
            None,
        ),
    )
    conn.commit()


def _insert_group_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    group_type: str = "layer",
    group_name: str = "Infrastructure",
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
    parent_group_type: str | None = "ecosystem",
    parent_group_name: str | None = "Datacenter",
    market: str = "usa",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date,
            taxonomy_version,
            signal_version,
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            return_2d,
            return_5d,
            return_30d,
            ema20_breadth_delta_5d,
            ma10_breadth_delta_5d,
            trend_breadth,
            weakness_breadth,
            strength_breadth,
            data_quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            1.5,
            3.0,
            5.5,
            0.25,
            0.10,
            0.80,
            0.15,
            0.65,
            "OK",
        ),
    )


def _insert_synthetic_row(
    conn: sqlite3.Connection,
    *,
    ohlc_date: str,
    group_type: str = "layer",
    group_name: str = "Infrastructure",
    market: str = "usa",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date,
            taxonomy_version,
            calc_version,
            market,
            group_type,
            group_name,
            synthetic_close,
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            trend_classification,
            latest_structure_label,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ohlc_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_OHLC_V1",
            market,
            group_type,
            group_name,
            150.0,
            1.2,
            3.4,
            "UP",
            "HL",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
        ),
    )


def test_daily_group_context_rows_are_written():
    conn = _connect()
    _insert_run(conn)
    _insert_group_row(conn, signal_date="2026-05-30")
    _insert_synthetic_row(conn, ohlc_date="2026-05-30")
    conn.commit()

    summary = build_report_group_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("daily",),
        created_at_utc="2026-05-30T00:00:00Z",
    )

    row = conn.execute(
        """
        SELECT *
        FROM dc_report_context_group_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ? AND group_type = ? AND group_name = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "daily", "layer", "Infrastructure"),
    ).fetchone()

    assert row is not None
    assert row["window_end_date"] == "2026-05-30"
    assert row["timing_state"] == "BUY_ZONE"
    assert row["overheat_risk_level"] == "LOW"
    assert row["synthetic_close"] == 150.0
    assert row["synthetic_trend_classification"] == "UP"
    assert row["synthetic_latest_structure_label"] == "HL"
    assert row["group_current_status"] == "BUY_ZONE"
    assert row["group_window_status"] is None
    assert summary["daily_rows_written"] == 1
    assert summary["total_rows_written"] == 1


def test_rolling2_window_fields_are_computed():
    conn = _connect()
    _insert_run(conn)
    _insert_group_row(conn, signal_date="2026-05-29", timing_state="BUY_ZONE", overheat_risk_level="LOW")
    _insert_group_row(conn, signal_date="2026-05-30", timing_state="EXIT_ZONE", overheat_risk_level="HIGH")
    _insert_synthetic_row(conn, ohlc_date="2026-05-30")
    conn.commit()

    build_report_group_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
        created_at_utc="2026-05-30T00:00:00Z",
    )

    row = conn.execute(
        """
        SELECT *
        FROM dc_report_context_group_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["window_start_date"] == "2026-05-29"
    assert row["window_end_date"] == "2026-05-30"
    assert row["valid_signal_dates"] == 2
    assert row["group_current_status"] == "EXIT_ZONE"
    assert row["group_window_status"] == "EXIT_ZONE"
    assert row["group_status_change"] == "BUY_ZONE -> EXIT_ZONE"
    assert row["group_context_risk_status"] == "YES"
    assert row["group_context_readiness_status"] == "OK"


def test_rolling5_and_rolling30_can_be_requested_together():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-28", "2026-05-29", "2026-05-30"):
        _insert_group_row(conn, signal_date=date_value)
    _insert_synthetic_row(conn, ohlc_date="2026-05-30")
    conn.commit()

    summary = build_report_group_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling5", "rolling30"),
        created_at_utc="2026-05-30T00:00:00Z",
    )

    rows = conn.execute(
        """
        SELECT horizon, valid_signal_dates, group_context_readiness_status
        FROM dc_report_context_group_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY horizon ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [row["horizon"] for row in rows] == ["rolling30", "rolling5"]
    assert [row["valid_signal_dates"] for row in rows] == [3, 3]
    assert [row["group_context_readiness_status"] for row in rows] == ["PARTIAL_WINDOW", "PARTIAL_WINDOW"]
    assert summary["rolling5_rows_written"] == 1
    assert summary["rolling30_rows_written"] == 1
    assert summary["total_rows_written"] == 2


def test_builder_is_idempotent_for_same_inputs():
    conn = _connect()
    _insert_run(conn)
    _insert_group_row(conn, signal_date="2026-05-30")
    _insert_synthetic_row(conn, ohlc_date="2026-05-30")
    conn.commit()

    build_report_group_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("daily",),
        created_at_utc="2026-05-30T00:00:00Z",
    )
    build_report_group_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("daily",),
        created_at_utc="2026-05-30T00:00:00Z",
    )

    row_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM dc_report_context_group_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "daily"),
    ).fetchone()[0]
    assert row_count == 1


def test_builder_requires_existing_run():
    conn = _connect()
    _insert_group_row(conn, signal_date="2026-05-30")
    _insert_synthetic_row(conn, ohlc_date="2026-05-30")
    conn.commit()

    with pytest.raises(ValueError, match="dc_report_run_v2 row not found"):
        build_report_group_context_v2(
            conn,
            signal_date="2026-05-30",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            run_id="missing-run",
            market="usa",
            horizons=("daily",),
            created_at_utc="2026-05-30T00:00:00Z",
        )


def test_builder_does_not_require_dashboard_tables():
    conn = _connect()
    _insert_run(conn)
    _insert_group_row(conn, signal_date="2026-05-30")
    _insert_synthetic_row(conn, ohlc_date="2026-05-30")
    conn.commit()

    dashboard_tables = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name LIKE 'dc_dashboard_%'
        """
    ).fetchall()
    assert dashboard_tables == []

    summary = build_report_group_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("daily",),
        created_at_utc="2026-05-30T00:00:00Z",
    )

    assert summary["daily_rows_written"] == 1
