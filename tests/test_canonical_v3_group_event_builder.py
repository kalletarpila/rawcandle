import sqlite3

import pytest

from rawcandle.report_canonical_v3_group_event_builder import (
    build_canonical_v3_group_structure_events,
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


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    *,
    entity_type: str,
    entity_code: str,
    entity_name: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker,
            exchange, market, currency, status
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, 'ACTIVE')
        """,
        (ecosystem_id, entity_type, entity_code, entity_name),
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


def _create_group_source_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            latest_structure_label TEXT NULL,
            trend_classification TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_event_date TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_event_date TEXT NULL,
            calc_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (ohlc_date, taxonomy_version, group_type, group_name, calc_version)
        )
        """
    )


def _insert_group_source_row(
    conn: sqlite3.Connection,
    *,
    ohlc_date: str,
    group_type: str,
    group_name: str,
    latest_structure_label: str | None,
    trend_classification: str | None,
    latest_bos_event_type: str | None = None,
    latest_bos_event_date: str | None = None,
    latest_reset_reason: str | None = None,
    latest_reset_event_date: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, group_type, group_name,
            latest_structure_label, trend_classification,
            latest_bos_event_type, latest_bos_event_date,
            latest_reset_reason, latest_reset_event_date,
            calc_version, run_id
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, ?, ?, ?, ?, ?, ?, 'DC_SWING_OHLC_V1', 'group-run-1')
        """,
        (
            ohlc_date,
            group_type,
            group_name,
            latest_structure_label,
            trend_classification,
            latest_bos_event_type,
            latest_bos_event_date,
            latest_reset_reason,
            latest_reset_event_date,
        ),
    )


def _setup_minimal_state(db_path: str) -> None:
    with _connect(db_path) as conn:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        layer_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="LAYER",
            entity_code="BACKUP_POWER",
            entity_name="Backup power",
        )
        subindustry_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="SUBINDUSTRY",
            entity_code="AI_CLOUD_NEOCLOUD_INFRASTRUCTURE",
            entity_name="AI cloud / neocloud infrastructure",
        )
        ticker_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="TICKER",
            entity_code="NVDA",
            entity_name="NVDA",
        )
        _insert_run(conn, ecosystem_id, taxonomy_version_id)
        _insert_coverage(conn, taxonomy_version_id, layer_id)
        _insert_coverage(conn, taxonomy_version_id, subindustry_id)
        _insert_coverage(conn, taxonomy_version_id, ticker_id)
        _create_group_source_table(conn)

        _insert_group_source_row(
            conn,
            ohlc_date="2026-05-20",
            group_type="layer",
            group_name="Backup power",
            latest_structure_label="LL",
            trend_classification="DOWN",
            latest_bos_event_type="BOS_DOWN",
            latest_bos_event_date="2026-05-19",
        )
        _insert_group_source_row(
            conn,
            ohlc_date="2026-05-21",
            group_type="layer",
            group_name="Backup power",
            latest_structure_label="HH",
            trend_classification="UP",
            latest_bos_event_type="BOS_DOWN",
            latest_bos_event_date="2026-05-19",
        )
        _insert_group_source_row(
            conn,
            ohlc_date="2026-05-22",
            group_type="layer",
            group_name="Backup power",
            latest_structure_label="HH",
            trend_classification="UP",
            latest_reset_reason="DOUBLE_BOS_UP",
            latest_reset_event_date="2026-05-22",
        )
        _insert_group_source_row(
            conn,
            ohlc_date="2026-05-20",
            group_type="subindustry",
            group_name="AI cloud / neocloud infrastructure",
            latest_structure_label="HL",
            trend_classification="NEUTRAL",
            latest_bos_event_type="BOS_UP",
            latest_bos_event_date="2026-05-18",
        )
        _insert_group_source_row(
            conn,
            ohlc_date="2026-05-21",
            group_type="subindustry",
            group_name="AI cloud / neocloud infrastructure",
            latest_structure_label="LH",
            trend_classification="DOWN",
            latest_bos_event_type="BOS_UP",
            latest_bos_event_date="2026-05-18",
        )
        _insert_group_source_row(
            conn,
            ohlc_date="2026-05-23",
            group_type="layer",
            group_name="Missing layer",
            latest_structure_label="HH",
            trend_classification="UP",
            latest_bos_event_type="BOS_UP",
            latest_bos_event_date="2026-05-23",
        )
        _insert_group_source_row(
            conn,
            ohlc_date="2026-06-02",
            group_type="subindustry",
            group_name="AI cloud / neocloud infrastructure",
            latest_structure_label="HH",
            trend_classification="UP",
            latest_bos_event_type="BOS_UP",
            latest_bos_event_date="2026-06-02",
        )
        conn.execute(
            """
            INSERT INTO eco_entity_event (
                run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date,
                event_type, source_table, source_run_id, source_event_id, event_key,
                event_label, event_direction, event_status, event_payload_ref
            ) VALUES (
                'V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1', 1, ?, ?, '2026-05-10',
                'BOS', 'stock_dow_structure_events', 'ticker-run', '1', 'stock_dow_structure_events:1',
                'BOS_UP', 'UP', 'ACTIVE', NULL
            )
            """,
            (taxonomy_version_id, ticker_id),
        )


@pytest.fixture()
def db_path(tmp_path):
    db_path = tmp_path / "group_events.db"
    apply_report_canonical_v3_migration(str(db_path))
    _setup_minimal_state(str(db_path))
    return str(db_path)


def test_builder_requires_existing_run_and_source(db_path, tmp_path):
    missing_source_db = tmp_path / "missing_source.db"
    apply_report_canonical_v3_migration(str(missing_source_db))
    with _connect(str(missing_source_db)) as conn:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_run(conn, ecosystem_id, taxonomy_version_id)
    with pytest.raises(ValueError, match="Missing eligible LAYER/SUBINDUSTRY coverage rows"):
        build_canonical_v3_group_structure_events(
            str(missing_source_db),
            "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        )

    with _connect(db_path) as conn:
        conn.execute("DROP TABLE dc_group_synthetic_ohlc_daily")
        conn.commit()
    with pytest.raises(ValueError, match="Missing source table 'dc_group_synthetic_ohlc_daily'"):
        build_canonical_v3_group_structure_events(
            db_path,
            "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        )


def test_builder_creates_group_events_and_preserves_scope(db_path):
    summary = build_canonical_v3_group_structure_events(
        db_path,
        "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        lookback_calendar_days=120,
        replace_existing=True,
    )

    assert summary["source_rows_read"] == 6
    assert summary["source_rows_mapped"] == 5
    assert summary["source_rows_skipped"] == 1
    assert summary["warning_count"] == 1
    assert "Missing V3 group entity" in summary["warnings"][0]
    assert summary["event_type_counts"] == {
        "BOS": 2,
        "RESET": 1,
        "STRUCTURE_CHANGE": 2,
        "TREND_STATE_CHANGE": 2,
    }

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ent.entity_type, ev.event_type, ev.event_direction, ev.event_label
            FROM eco_entity_event ev
            JOIN eco_entity ent ON ent.entity_id = ev.entity_id
            WHERE ev.source_table = 'dc_group_synthetic_ohlc_daily'
            ORDER BY ent.entity_type, ev.event_type, ev.event_label
            """
        ).fetchall()
        assert {row["entity_type"] for row in rows} == {"LAYER", "SUBINDUSTRY"}
        assert all(row["entity_type"] != "TICKER" for row in rows)
        assert all(row["entity_type"] != "ECOSYSTEM" for row in rows)

        bos_rows = [row for row in rows if row["event_type"] == "BOS"]
        assert {row["event_direction"] for row in bos_rows} == {"DOWN", "UP"}

        reset_row = next(row for row in rows if row["event_type"] == "RESET")
        assert reset_row["event_direction"] == "UP"
        assert reset_row["event_label"] == "DOUBLE_BOS_UP"

        structure_rows = [row for row in rows if row["event_type"] == "STRUCTURE_CHANGE"]
        assert {row["event_label"] for row in structure_rows} == {"HL -> LH", "LL -> HH"}
        assert {row["event_direction"] for row in structure_rows} == {"NONE"}

        trend_rows = [row for row in rows if row["event_type"] == "TREND_STATE_CHANGE"]
        assert {row["event_label"] for row in trend_rows} == {"DOWN -> UP", "NEUTRAL -> DOWN"}
        assert {row["event_direction"] for row in trend_rows} == {"UP", "DOWN"}

        ticker_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE source_table = 'stock_dow_structure_events'
            """
        ).fetchone()[0]
        assert ticker_count == 1


def test_replace_existing_is_idempotent_and_preserves_ticker_events(db_path):
    first_summary = build_canonical_v3_group_structure_events(
        db_path,
        "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=True,
    )
    with pytest.raises(ValueError, match="Group event rows already exist"):
        build_canonical_v3_group_structure_events(
            db_path,
            "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            replace_existing=False,
        )

    second_summary = build_canonical_v3_group_structure_events(
        db_path,
        "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=True,
    )
    assert second_summary["entity_events_inserted"] == first_summary["entity_events_inserted"]

    with _connect(db_path) as conn:
        group_event_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE source_table = 'dc_group_synthetic_ohlc_daily'
            """
        ).fetchone()[0]
        ticker_event_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE source_table = 'stock_dow_structure_events'
            """
        ).fetchone()[0]
        duplicate_event_keys = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT event_key, COUNT(*) AS n
                FROM eco_entity_event
                WHERE source_table = 'dc_group_synthetic_ohlc_daily'
                GROUP BY event_key
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        assert group_event_count == first_summary["entity_events_inserted"]
        assert ticker_event_count == 1
        assert duplicate_event_keys == 0


def test_builder_rolls_back_on_insert_failure(db_path, monkeypatch):
    def boom(_conn, _rows):
        raise sqlite3.IntegrityError("forced failure")

    monkeypatch.setattr(
        "rawcandle.report_canonical_v3_group_event_builder._insert_event_rows",
        boom,
    )

    with pytest.raises(sqlite3.IntegrityError, match="forced failure"):
        build_canonical_v3_group_structure_events(
            db_path,
            "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            replace_existing=True,
        )

    with _connect(db_path) as conn:
        group_event_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE source_table = 'dc_group_synthetic_ohlc_daily'
            """
        ).fetchone()[0]
        ticker_event_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE source_table = 'stock_dow_structure_events'
            """
        ).fetchone()[0]
        assert group_event_count == 0
        assert ticker_event_count == 1
