from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from rawcandle.report_canonical_v3_group_freshness_metric_builder import (
    build_canonical_v3_group_freshness_metrics,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
OTHER_RUN_ID = "V3_BASE_DATACENTER_2026_06_03_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-06-04"
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
TARGET_METRICS = (
    "freshness_latest_structure_class",
    "freshness_latest_bos_class",
    "freshness_latest_reset_class",
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _trading_dates(end_date: str, count: int) -> list[str]:
    current = date.fromisoformat(end_date)
    values: list[str] = []
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current.isoformat())
        current -= timedelta(days=1)
    values.reverse()
    return values


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


def _insert_run(conn: sqlite3.Connection, run_id: str, ecosystem_id: int, taxonomy_version_id: int, signal_date: str) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
        ) VALUES (?, ?, ?, ?, 'BUILD', 'OK', 0, 0)
        """,
        (run_id, ecosystem_id, taxonomy_version_id, signal_date),
    )


def _insert_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
    entity_name: str,
) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, status
            ) VALUES (?, ?, ?, ?, 'ACTIVE')
            """,
            (ecosystem_id, entity_type, entity_code, entity_name),
        ).lastrowid
    )


def _insert_coverage(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    signal_date: str,
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
        (run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id),
    )


def _insert_metric_seed(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    signal_date: str,
    window_code: str,
    metric_name: str,
    metric_value_num: float | None,
    metric_value_text: str | None,
    source_run_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OK', ?)
        """,
        (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            metric_name,
            metric_value_num,
            metric_value_text,
            None,
            source_run_id,
        ),
    )


def _insert_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    event_date: str,
    event_type: str,
    event_key: str,
    source_run_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date,
            event_type, source_table, source_run_id, source_event_id, event_key,
            event_label, event_direction, event_status, event_payload_ref
        ) VALUES (?, ?, ?, ?, ?, ?, 'eco_entity_event', ?, NULL, ?, ?, 'NONE', 'ACTIVE', NULL)
        """,
        (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            entity_id,
            event_date,
            event_type,
            source_run_id,
            event_key,
            event_type,
        ),
    )


def _seed_db(db_path: str) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_run(conn, RUN_ID, ecosystem_id, taxonomy_version_id, SIGNAL_DATE)
        _insert_run(conn, OTHER_RUN_ID, ecosystem_id, taxonomy_version_id, "2026-06-03")

        layer_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="LAYER",
            entity_code="AI_COMPUTE",
            entity_name="AI Compute",
        )
        subindustry_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="SUBINDUSTRY",
            entity_code="GPU",
            entity_name="GPU",
        )
        ticker_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="TICKER",
            entity_code="NVDA",
            entity_name="NVIDIA",
        )

        for window_code in TARGET_WINDOWS:
            _insert_coverage(
                conn,
                run_id=RUN_ID,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=layer_id,
                signal_date=SIGNAL_DATE,
                window_code=window_code,
            )
            _insert_coverage(
                conn,
                run_id=RUN_ID,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=subindustry_id,
                signal_date=SIGNAL_DATE,
                window_code=window_code,
            )
            _insert_coverage(
                conn,
                run_id=RUN_ID,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=ticker_id,
                signal_date=SIGNAL_DATE,
                window_code=window_code,
            )

        dates = _trading_dates(SIGNAL_DATE, 62)
        for signal_date in dates:
            _insert_metric_seed(
                conn,
                run_id=RUN_ID,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=layer_id,
                signal_date=signal_date,
                window_code="rolling30",
                metric_name="history_seed",
                metric_value_num=1.0,
                metric_value_text=None,
                source_run_id="history-seed",
            )

        _insert_metric_seed(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=ticker_id,
            signal_date=SIGNAL_DATE,
            window_code="daily",
            metric_name="freshness_latest_structure_class",
            metric_value_num=None,
            metric_value_text="FRESH",
            source_run_id="ticker-source",
        )
        _insert_metric_seed(
            conn,
            run_id=OTHER_RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=layer_id,
            signal_date="2026-06-03",
            window_code="daily",
            metric_name="freshness_latest_structure_class",
            metric_value_num=None,
            metric_value_text="KEEP_OTHER_RUN",
            source_run_id="other-run",
        )

        _insert_event(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=layer_id,
            event_date=SIGNAL_DATE,
            event_type="TREND_STATE_CHANGE",
            event_key="layer-structure",
            source_run_id="group-event-layer-structure",
        )
        _insert_event(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=layer_id,
            event_date=dates[0],
            event_type="RESET",
            event_key="layer-reset",
            source_run_id="group-event-layer-reset",
        )
        _insert_event(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=subindustry_id,
            event_date=dates[30],
            event_type="STRUCTURE_CHANGE",
            event_key="sub-structure",
            source_run_id="group-event-sub-structure",
        )
        _insert_event(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=subindustry_id,
            event_date=dates[0],
            event_type="BOS",
            event_key="sub-bos",
            source_run_id="group-event-sub-bos",
        )
        _insert_event(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=ticker_id,
            event_date=SIGNAL_DATE,
            event_type="BOS",
            event_key="ticker-bos",
            source_run_id="ticker-event",
        )

        conn.commit()
        return {
            "ecosystem_id": ecosystem_id,
            "taxonomy_version_id": taxonomy_version_id,
            "layer_id": layer_id,
            "subindustry_id": subindustry_id,
            "ticker_id": ticker_id,
        }
    finally:
        conn.close()


def test_group_freshness_builder_materializes_group_class_metrics(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_group_freshness_builder.db"
    ids = _seed_db(str(db_path))

    summary = build_canonical_v3_group_freshness_metrics(str(db_path), RUN_ID)

    assert summary["run_id"] == RUN_ID
    assert summary["target_signal_date"] == SIGNAL_DATE
    assert summary["windows"] == list(TARGET_WINDOWS)
    assert summary["inserted_rows"] == 16
    assert summary["deleted_rows"] == 0
    assert summary["skipped_no_event_count"] == 2
    assert summary["missing_event_counts"] == {
        "freshness_latest_bos_class": 1,
        "freshness_latest_reset_class": 1,
    }
    assert summary["entity_count"] == 2
    assert summary["source_tables_used"] == ["eco_entity_event", "eco_entity_metric_value"]
    assert summary["valid_signal_dates_count"] == 62
    assert summary["freshness_class_counts"] == {
        "AGING": 8,
        "FRESH": 4,
        "STALE": 4,
    }
    assert summary["status"] == "OK_WITH_WARNINGS"

    conn = _connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT
                e.entity_type,
                e.entity_code,
                m.window_code,
                m.metric_name,
                m.metric_value_num,
                m.metric_value_text,
                m.source_run_id,
                m.signal_date
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND m.metric_name IN (
                'freshness_latest_structure_class',
                'freshness_latest_bos_class',
                'freshness_latest_reset_class'
              )
            ORDER BY e.entity_type, e.entity_code, m.metric_name, m.window_code
            """,
            (RUN_ID,),
        ).fetchall()

        assert len(rows) == 17
        group_rows = [row for row in rows if row["entity_type"] in ("LAYER", "SUBINDUSTRY")]
        assert len(group_rows) == 16
        assert all(row["metric_value_num"] is None for row in group_rows)
        assert all(row["signal_date"] == SIGNAL_DATE for row in group_rows)
        assert {row["window_code"] for row in group_rows} == set(TARGET_WINDOWS)

        layer_structure = [
            row for row in group_rows
            if row["entity_code"] == "AI_COMPUTE"
            and row["metric_name"] == "freshness_latest_structure_class"
        ]
        assert {row["metric_value_text"] for row in layer_structure} == {"FRESH"}
        assert {row["source_run_id"] for row in layer_structure} == {"group-event-layer-structure"}

        layer_reset = [
            row for row in group_rows
            if row["entity_code"] == "AI_COMPUTE"
            and row["metric_name"] == "freshness_latest_reset_class"
        ]
        assert {row["metric_value_text"] for row in layer_reset} == {"AGING"}

        sub_structure = [
            row for row in group_rows
            if row["entity_code"] == "GPU"
            and row["metric_name"] == "freshness_latest_structure_class"
        ]
        assert {row["metric_value_text"] for row in sub_structure} == {"AGING"}

        sub_bos = [
            row for row in group_rows
            if row["entity_code"] == "GPU"
            and row["metric_name"] == "freshness_latest_bos_class"
        ]
        assert {row["metric_value_text"] for row in sub_bos} == {"STALE"}

        ticker_targeted = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND e.entity_type = 'TICKER'
              AND m.metric_name IN (
                'freshness_latest_structure_class',
                'freshness_latest_bos_class',
                'freshness_latest_reset_class'
              )
            """,
            (RUN_ID,),
        ).fetchone()[0]
        assert ticker_targeted == 1
    finally:
        conn.close()


def test_group_freshness_builder_replace_behavior_is_scoped(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_group_freshness_replace.db"
    ids = _seed_db(str(db_path))

    first_summary = build_canonical_v3_group_freshness_metrics(str(db_path), RUN_ID)
    assert first_summary["inserted_rows"] == 16

    with pytest.raises(ValueError, match="Group freshness builder-owned rows already exist"):
        build_canonical_v3_group_freshness_metrics(str(db_path), RUN_ID, replace_existing=False)

    conn = _connect(str(db_path))
    try:
        _insert_metric_seed(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ids["ecosystem_id"],
            taxonomy_version_id=ids["taxonomy_version_id"],
            entity_id=ids["layer_id"],
            signal_date=SIGNAL_DATE,
            window_code="daily",
            metric_name="unrelated_metric",
            metric_value_num=2.0,
            metric_value_text=None,
            source_run_id="keep-me",
        )
        conn.commit()
    finally:
        conn.close()

    second_summary = build_canonical_v3_group_freshness_metrics(str(db_path), RUN_ID, replace_existing=True)
    assert second_summary["inserted_rows"] == 16
    assert second_summary["deleted_rows"] == 16

    conn = _connect(str(db_path))
    try:
        builder_owned_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
              AND m.metric_name IN (
                'freshness_latest_structure_class',
                'freshness_latest_bos_class',
                'freshness_latest_reset_class'
              )
            """,
            (RUN_ID,),
        ).fetchone()[0]
        assert builder_owned_count == 16

        other_run_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value
            WHERE run_id = ?
              AND metric_name = 'freshness_latest_structure_class'
            """,
            (OTHER_RUN_ID,),
        ).fetchone()[0]
        assert other_run_count == 1

        unrelated_metric_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value
            WHERE run_id = ?
              AND metric_name = 'unrelated_metric'
            """,
            (RUN_ID,),
        ).fetchone()[0]
        assert unrelated_metric_count == 1
    finally:
        conn.close()
