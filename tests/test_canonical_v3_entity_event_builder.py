import sqlite3

import pytest

from rawcandle.report_canonical_v3_entity_event_builder import (
    build_canonical_v3_ticker_structure_events,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


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
        (
            ecosystem_id,
            "DC_TAXONOMY_FULL_V1",
            "DC_TAXONOMY_FULL_V1",
            None,
            None,
            None,
            None,
            1,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid)


def _insert_ticker_entity(conn: sqlite3.Connection, ecosystem_id: int, ticker: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker,
            exchange, market, currency, status
        ) VALUES (?, 'TICKER', ?, ?, ?, NULL, NULL, NULL, 'ACTIVE')
        """,
        (ecosystem_id, ticker, ticker, ticker),
    )
    return int(cursor.lastrowid)


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date,
            run_type, status, warning_count, error_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            ecosystem_id,
            taxonomy_version_id,
            "2026-05-29",
            "BUILD",
            "OK",
            0,
            0,
            None,
        ),
    )


def _insert_coverage(conn: sqlite3.Connection, taxonomy_version_id: int, entity_id: int) -> None:
    for window_code in ("daily", "rolling2", "rolling5", "rolling30"):
        conn.execute(
            """
            INSERT INTO eco_entity_coverage (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
                entity_id, in_taxonomy, in_watchlist, has_instrument, has_price_data,
                has_daily_signal, has_window_context, coverage_status, source_row_count,
                missing_component_count, coverage_notes
            ) VALUES (?, 1, '2026-05-29', ?, ?, ?, 1, 0, 1, 1, 1, 1, 'OK', NULL, 0, NULL)
            """,
            (
                "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
                taxonomy_version_id,
                window_code,
                entity_id,
            ),
        )


def _create_source_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            event_date TEXT NOT NULL,
            confirmed_as_of_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trend_state TEXT NOT NULL,
            break_signal TEXT NULL,
            reset_reason TEXT NULL,
            structure_epoch_id INTEGER NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )


def _insert_source_row(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    ticker: str,
    event_date: str,
    confirmed_as_of_date: str,
    event_type: str,
    trend_state: str,
    break_signal: str | None,
    reset_reason: str | None,
    structure_epoch_id: int,
    source_run_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            id, ticker, event_date, confirmed_as_of_date, event_type, trend_state,
            break_signal, reset_reason, structure_epoch_id, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            ticker,
            event_date,
            confirmed_as_of_date,
            event_type,
            trend_state,
            break_signal,
            reset_reason,
            structure_epoch_id,
            source_run_id,
        ),
    )


def _setup_minimal_state(db_path: str) -> None:
    with _connect(db_path) as conn:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        nvda_id = _insert_ticker_entity(conn, ecosystem_id, "NVDA")
        amd_id = _insert_ticker_entity(conn, ecosystem_id, "AMD")
        _insert_run(conn, ecosystem_id, taxonomy_version_id)
        _insert_coverage(conn, taxonomy_version_id, nvda_id)
        _insert_coverage(conn, taxonomy_version_id, amd_id)
        _create_source_table(conn)
        source_run_id = "stock-dow-run-1"
        _insert_source_row(
            conn,
            row_id=1,
            ticker="NVDA",
            event_date="2026-05-20",
            confirmed_as_of_date="2026-05-21",
            event_type="BOS_UP",
            trend_state="UP",
            break_signal="BOS_UP",
            reset_reason=None,
            structure_epoch_id=1,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=2,
            ticker="AMD",
            event_date="2026-05-18",
            confirmed_as_of_date="2026-05-19",
            event_type="BOS_DOWN",
            trend_state="DOWN",
            break_signal="BOS_DOWN",
            reset_reason=None,
            structure_epoch_id=2,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=3,
            ticker="NVDA",
            event_date="2026-05-22",
            confirmed_as_of_date="2026-05-22",
            event_type="RESET",
            trend_state="NEUTRAL",
            break_signal="UP",
            reset_reason="DOUBLE_BOS_UP",
            structure_epoch_id=3,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=4,
            ticker="AMD",
            event_date="2026-05-23",
            confirmed_as_of_date="2026-05-24",
            event_type="TREND_CHANGE",
            trend_state="NEUTRAL",
            break_signal=None,
            reset_reason=None,
            structure_epoch_id=4,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=5,
            ticker="MISSING",
            event_date="2026-05-20",
            confirmed_as_of_date="2026-05-20",
            event_type="BOS_UP",
            trend_state="UP",
            break_signal="BOS_UP",
            reset_reason=None,
            structure_epoch_id=5,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=6,
            ticker="NVDA",
            event_date="2026-06-02",
            confirmed_as_of_date="2026-06-02",
            event_type="BOS_UP",
            trend_state="UP",
            break_signal="BOS_UP",
            reset_reason=None,
            structure_epoch_id=6,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=7,
            ticker="AMD",
            event_date="2026-05-10",
            confirmed_as_of_date="2026-05-10",
            event_type="PIVOT_HIGH",
            trend_state="MIXED",
            break_signal=None,
            reset_reason=None,
            structure_epoch_id=7,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=8,
            ticker="NVDA",
            event_date="2026-05-11",
            confirmed_as_of_date="2026-05-11",
            event_type="PIVOT_LOW",
            trend_state="UP",
            break_signal=None,
            reset_reason=None,
            structure_epoch_id=8,
            source_run_id=source_run_id,
        )
        _insert_source_row(
            conn,
            row_id=9,
            ticker="AMD",
            event_date="2026-05-10",
            confirmed_as_of_date="2026-05-10",
            event_type="ODD_EVENT",
            trend_state="MIXED",
            break_signal=None,
            reset_reason=None,
            structure_epoch_id=9,
            source_run_id=source_run_id,
        )
        conn.commit()


def test_entity_event_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "event_missing_run.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_ticker_structure_events(str(db_path), "missing-run")


def test_entity_event_builder_requires_source_table(tmp_path) -> None:
    db_path = tmp_path / "event_missing_source.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    with _connect(str(db_path)) as conn:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_ticker_entity(conn, ecosystem_id, "NVDA")
        _insert_run(conn, ecosystem_id, taxonomy_version_id)
        conn.commit()
    with pytest.raises(ValueError, match="Missing source table"):
        build_canonical_v3_ticker_structure_events(str(db_path), "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1")


def test_entity_event_builder_maps_and_filters_rows(tmp_path) -> None:
    db_path = tmp_path / "event_builder.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _setup_minimal_state(str(db_path))

    summary = build_canonical_v3_ticker_structure_events(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        lookback_calendar_days=30,
        replace_existing=False,
    )

    assert summary["source_rows_read"] == 7
    assert summary["source_rows_mapped"] == 7
    assert summary["source_rows_skipped"] == 0
    assert summary["entity_events_inserted"] == 7
    assert summary["event_type_counts"] == {
        "BOS": 2,
        "RESET": 1,
        "STRUCTURE_CHANGE": 2,
        "TREND_STATE_CHANGE": 1,
        "UNKNOWN": 1,
    }
    assert summary["event_direction_counts"] == {
        "DOWN": 1,
        "MIXED": 1,
        "NEUTRAL": 1,
        "NONE": 3,
        "UP": 1,
    }
    assert all("Missing V3 ticker entity" not in warning for warning in summary["warnings"])
    assert any("Unknown source event_type 'ODD_EVENT' mapped to UNKNOWN" in warning for warning in summary["warnings"])

    with _connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT event_type, event_direction, event_key, event_label
            FROM eco_entity_event
            ORDER BY event_date, entity_id, event_key
            """
        ).fetchall()
        assert ("BOS", "UP", "stock_dow_structure_events:1", "BOS_UP | BOS_UP") in [tuple(row) for row in rows]
        assert ("BOS", "DOWN", "stock_dow_structure_events:2", "BOS_DOWN | BOS_DOWN") in [tuple(row) for row in rows]
        assert ("RESET", "NONE", "stock_dow_structure_events:3", "RESET | UP | DOUBLE_BOS_UP") in [tuple(row) for row in rows]
        assert ("TREND_STATE_CHANGE", "NEUTRAL", "stock_dow_structure_events:4", "TREND_CHANGE") in [tuple(row) for row in rows]
        assert ("STRUCTURE_CHANGE", "NONE", "stock_dow_structure_events:7", "PIVOT_HIGH") in [tuple(row) for row in rows]
        assert ("STRUCTURE_CHANGE", "NONE", "stock_dow_structure_events:8", "PIVOT_LOW") in [tuple(row) for row in rows]
        assert ("UNKNOWN", "MIXED", "stock_dow_structure_events:9", "ODD_EVENT") in [tuple(row) for row in rows]
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 7
        event_entity_types = conn.execute(
            """
            SELECT DISTINCT e.entity_type
            FROM eco_entity_event ev
            JOIN eco_entity e ON e.entity_id = ev.entity_id
            """
        ).fetchall()
        assert [row["entity_type"] for row in event_entity_types] == ["TICKER"]
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 0


def test_entity_event_builder_replace_existing_and_rollback(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "event_builder_replace.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _setup_minimal_state(str(db_path))

    build_canonical_v3_ticker_structure_events(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=False,
    )

    with pytest.raises(ValueError, match="already exist"):
        build_canonical_v3_ticker_structure_events(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            replace_existing=False,
        )

    summary = build_canonical_v3_ticker_structure_events(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=True,
    )
    assert summary["entity_events_inserted"] == 7

    with _connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 7

    from rawcandle import report_canonical_v3_entity_event_builder as builder_module

    def _boom(conn: sqlite3.Connection, event_rows: list[dict[str, object]]) -> None:
        raise RuntimeError("forced event insert failure")

    monkeypatch.setattr(builder_module, "_insert_event_rows", _boom)

    with pytest.raises(RuntimeError, match="forced event insert failure"):
        build_canonical_v3_ticker_structure_events(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            replace_existing=True,
        )

    with _connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 7
