from __future__ import annotations

import sqlite3

import pytest

from rawcandle.report_canonical_v3_group_historical_metric_builder import (
    build_canonical_v3_group_historical_metrics,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-06-04"
GROUP_SOURCE_RUN_ID = "DC_GROUP_SWING_20260604_DC_SWING_SIGNAL_V1"
SYNTH_SOURCE_RUN_ID = "DC_GROUP_SYNTH_OHLC_20250801_20260604_DC_SWING_OHLC_V1"
TARGET_WINDOWS = ("rolling2", "rolling5", "rolling30")
TARGET_METRICS = (
    "group_timing_state",
    "group_overheat_risk_level",
    "pct_above_ema20",
    "trend_breadth",
    "weakness_breadth",
    "return_5d",
    "return_10d",
    "return_20d",
    "synthetic_close",
)
ROLLING2_DATES = ["2026-06-03", "2026-06-04"]
ROLLING5_DATES = ["2026-05-30", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]
ROLLING30_DATES = [
    "2026-05-06",
    "2026-05-07",
    "2026-05-08",
    "2026-05-11",
    "2026-05-12",
    "2026-05-13",
    "2026-05-14",
    "2026-05-15",
    "2026-05-18",
    "2026-05-19",
    "2026-05-20",
    "2026-05-21",
    "2026-05-22",
    "2026-05-23",
    "2026-05-26",
    "2026-05-27",
    "2026-05-28",
    "2026-05-29",
    "2026-05-30",
    "2026-06-01",
    "2026-06-02",
    "2026-06-03",
    "2026-06-04",
]


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


def _create_group_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            timing_state TEXT,
            overheat_risk_level TEXT,
            pct_above_ema20 REAL,
            trend_breadth REAL,
            weakness_breadth REAL,
            return_5d REAL,
            return_10d REAL,
            run_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            synthetic_close REAL,
            run_id TEXT
        )
        """
    )


def _insert_group_swing_rows(conn: sqlite3.Connection) -> None:
    all_dates = sorted(set(ROLLING30_DATES + ["2026-05-23", "2026-05-30"]))
    rows = []
    for idx, current_date in enumerate(all_dates):
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "layer",
                "AI_LAYER",
                "BUY_ZONE" if current_date < "2026-06-04" else "TRIM_WATCH",
                "LOW" if current_date < "2026-06-04" else "HIGH",
                50.0 + idx,
                40.0 + idx,
                5.0 + idx,
                0.10 + idx / 100.0,
                0.20 + idx / 100.0,
                GROUP_SOURCE_RUN_ID,
            )
        )
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "subindustry",
                "GPU",
                "EXIT_ZONE" if current_date >= "2026-06-03" else "BUY_ZONE",
                "HIGH" if current_date >= "2026-06-03" else "LOW",
                60.0 + idx,
                50.0 + idx,
                6.0 + idx,
                0.30 + idx / 100.0,
                0.40 + idx / 100.0,
                GROUP_SOURCE_RUN_ID,
            )
        )
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "subindustry",
                "UNRESOLVED_SUB",
                "NEUTRAL",
                "LOW",
                10.0,
                20.0,
                30.0,
                0.01,
                0.02,
                GROUP_SOURCE_RUN_ID,
            )
        )
    conn.executemany(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, group_type, group_name,
            timing_state, overheat_risk_level, pct_above_ema20,
            trend_breadth, weakness_breadth, return_5d, return_10d, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_group_synthetic_rows(conn: sqlite3.Connection) -> None:
    all_dates = sorted(set(ROLLING30_DATES + ["2026-05-23", "2026-05-30"]))
    rows = []
    for idx, current_date in enumerate(all_dates):
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "layer",
                "AI_LAYER",
                100.0 + idx,
                SYNTH_SOURCE_RUN_ID,
            )
        )
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "subindustry",
                "GPU",
                200.0 + idx,
                SYNTH_SOURCE_RUN_ID,
            )
        )
    conn.executemany(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, group_type, group_name, synthetic_close, run_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_preserved_metric_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'distance_to_ema20_pct', 11.0, NULL, 'percent', 'OK', 'KEEP_TICKER')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )


def _insert_existing_builder_scope_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    layer_id: int,
) -> None:
    rows = [
        (
            RUN_ID,
            ecosystem_id,
            "2026-06-03",
            taxonomy_version_id,
            "rolling2",
            layer_id,
            "group_timing_state",
            None,
            "OLD",
            None,
            "OK",
            "OLD_SOURCE",
        ),
        (
            RUN_ID,
            ecosystem_id,
            "2026-06-03",
            taxonomy_version_id,
            "rolling2",
            layer_id,
            "synthetic_close",
            999.0,
            None,
            "points",
            "OK",
            "OLD_SOURCE",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_unit_seed_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    layer_id: int,
    sub_id: int,
) -> None:
    rows = [
        (layer_id, "pct_above_ema20", 1.0, None, "percent"),
        (layer_id, "trend_breadth", 1.0, None, "percent"),
        (layer_id, "weakness_breadth", 1.0, None, "percent"),
        (layer_id, "return_5d", 1.0, None, "percent"),
        (layer_id, "return_10d", 1.0, None, "percent"),
        (layer_id, "return_20d", 1.0, None, "percent"),
        (layer_id, "synthetic_close", 1.0, None, "points"),
        (sub_id, "group_timing_state", None, "BUY_ZONE", None),
        (sub_id, "group_overheat_risk_level", None, "LOW", None),
    ]
    conn.executemany(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling30', ?, ?, ?, ?, ?, 'OK', 'SEED')
        """,
        [
            (
                RUN_ID,
                ecosystem_id,
                SIGNAL_DATE,
                taxonomy_version_id,
                entity_id,
                metric_name,
                metric_value_num,
                metric_value_text,
                metric_unit,
            )
            for entity_id, metric_name, metric_value_num, metric_value_text, metric_unit in rows
        ],
    )


def _setup_db(db_path: str) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    _insert_run(conn, ecosystem_id, taxonomy_version_id)

    entity_ids = {
        "AI_LAYER": _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="LAYER",
            entity_code="AI_LAYER",
            entity_name="AI Layer",
        ),
        "GPU_SUB": _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="SUBINDUSTRY",
            entity_code="GPU",
            entity_name="Graphics",
        ),
        "AAA": _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="TICKER",
            entity_code="AAA",
            entity_name="AAA",
        ),
    }

    for entity_key in ("AI_LAYER", "GPU_SUB"):
        for window_code in TARGET_WINDOWS:
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids[entity_key],
                window_code=window_code,
            )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=entity_ids["AAA"],
        window_code="daily",
    )

    _create_group_source_tables(conn)
    _insert_group_swing_rows(conn)
    _insert_group_synthetic_rows(conn)
    _insert_preserved_metric_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=entity_ids["AAA"],
    )
    _insert_unit_seed_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        layer_id=entity_ids["AI_LAYER"],
        sub_id=entity_ids["GPU_SUB"],
    )

    conn.commit()
    conn.close()
    return entity_ids


def _load_rows(db_path: str) -> list[sqlite3.Row]:
    conn = _connect(db_path)
    try:
        return conn.execute(
            """
            SELECT
                m.run_id,
                m.signal_date,
                m.window_code,
                e.entity_type,
                e.entity_code,
                m.metric_name,
                m.metric_value_num,
                m.metric_value_text,
                m.metric_unit,
                m.source_run_id
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND m.window_code IN ('rolling2', 'rolling5', 'rolling30')
              AND m.metric_name IN (
                'group_timing_state', 'group_overheat_risk_level', 'pct_above_ema20',
                'trend_breadth', 'weakness_breadth', 'return_5d', 'return_10d',
                'return_20d', 'synthetic_close'
              )
            ORDER BY m.window_code, m.signal_date, e.entity_type, e.entity_code, m.metric_name
            """,
            (RUN_ID,),
        ).fetchall()
    finally:
        conn.close()


def test_builder_inserts_historical_rows_for_selected_rolling_windows(tmp_path) -> None:
    db_path = tmp_path / "group-historical.db"
    _setup_db(str(db_path))

    summary = build_canonical_v3_group_historical_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["run_id"] == RUN_ID
    assert summary["target_signal_date"] == SIGNAL_DATE
    assert summary["windows"] == ["rolling2", "rolling5", "rolling30"]
    assert summary["selected_dates_by_window"]["rolling2"] == ROLLING2_DATES
    assert summary["selected_dates_by_window"]["rolling5"] == ROLLING5_DATES
    assert summary["selected_dates_by_window"]["rolling30"] == ROLLING30_DATES[-30:]
    assert summary["source_tables_used"] == [
        "dc_group_swing_signal_daily",
        "dc_group_synthetic_ohlc_daily",
    ]
    assert summary["unresolved_group_rows"] > 0
    assert summary["skipped_missing_source_columns"] == ["return_20d"]
    assert summary["inserted_rows"] > 0

    rows = _load_rows(str(db_path))
    assert rows
    assert {str(row["window_code"]) for row in rows} == set(TARGET_WINDOWS)
    assert {str(row["entity_type"]) for row in rows} == {"LAYER", "SUBINDUSTRY"}

    rolling2_dates = sorted({str(row["signal_date"]) for row in rows if str(row["window_code"]) == "rolling2"})
    rolling5_dates = sorted({str(row["signal_date"]) for row in rows if str(row["window_code"]) == "rolling5"})
    rolling30_dates = sorted({str(row["signal_date"]) for row in rows if str(row["window_code"]) == "rolling30"})
    assert rolling2_dates == ROLLING2_DATES
    assert rolling5_dates == ROLLING5_DATES
    assert rolling30_dates == ROLLING30_DATES[-30:]
    assert SIGNAL_DATE in rolling2_dates
    assert SIGNAL_DATE in rolling5_dates
    assert SIGNAL_DATE in rolling30_dates

    sample_numeric = next(row for row in rows if str(row["metric_name"]) == "pct_above_ema20")
    assert sample_numeric["metric_value_num"] is not None
    assert sample_numeric["metric_value_text"] is None
    assert sample_numeric["metric_unit"] == "percent"
    assert sample_numeric["source_run_id"] == GROUP_SOURCE_RUN_ID

    sample_text = next(row for row in rows if str(row["metric_name"]) == "group_timing_state")
    assert sample_text["metric_value_num"] is None
    assert sample_text["metric_value_text"] is not None
    assert sample_text["source_run_id"] == GROUP_SOURCE_RUN_ID

    sample_overheat = next(row for row in rows if str(row["metric_name"]) == "group_overheat_risk_level")
    assert sample_overheat["metric_value_num"] is None
    assert sample_overheat["metric_value_text"] is not None
    assert sample_overheat["source_run_id"] == GROUP_SOURCE_RUN_ID

    text_rows = [
        row for row in rows
        if str(row["metric_name"]) in {"group_timing_state", "group_overheat_risk_level"}
    ]
    assert {str(row["entity_type"]) for row in text_rows} == {"LAYER", "SUBINDUSTRY"}
    assert {str(row["window_code"]) for row in text_rows} == set(TARGET_WINDOWS)
    assert sorted({str(row["signal_date"]) for row in text_rows if str(row["window_code"]) == "rolling2"}) == ROLLING2_DATES
    assert sorted({str(row["signal_date"]) for row in text_rows if str(row["window_code"]) == "rolling5"}) == ROLLING5_DATES
    assert sorted({str(row["signal_date"]) for row in text_rows if str(row["window_code"]) == "rolling30"}) == ROLLING30_DATES[-30:]

    sample_synth = next(row for row in rows if str(row["metric_name"]) == "synthetic_close")
    assert sample_synth["metric_value_num"] is not None
    assert sample_synth["metric_unit"] == "points"
    assert sample_synth["source_run_id"] == SYNTH_SOURCE_RUN_ID

    conn = _connect(str(db_path))
    try:
        preserved_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM eco_entity_metric_value
                WHERE run_id = ?
                  AND metric_name = 'distance_to_ema20_pct'
                """,
                (RUN_ID,),
            ).fetchone()[0]
        )
    finally:
        conn.close()
    assert preserved_count == 1


def test_builder_refuses_duplicates_without_replace_existing_and_replaces_only_own_scope(tmp_path) -> None:
    db_path = tmp_path / "group-historical-replace.db"
    entity_ids = _setup_db(str(db_path))

    conn = _connect(str(db_path))
    try:
        ecosystem_id = int(
            conn.execute("SELECT ecosystem_id FROM eco_report_run WHERE run_id = ?", (RUN_ID,)).fetchone()[0]
        )
        taxonomy_version_id = int(
            conn.execute("SELECT taxonomy_version_id FROM eco_report_run WHERE run_id = ?", (RUN_ID,)).fetchone()[0]
        )
        _insert_existing_builder_scope_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            layer_id=entity_ids["AI_LAYER"],
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="replace_existing=False"):
        build_canonical_v3_group_historical_metrics(str(db_path), RUN_ID, replace_existing=False)

    summary = build_canonical_v3_group_historical_metrics(str(db_path), RUN_ID, replace_existing=True)
    assert summary["deleted_rows"] >= 2

    conn = _connect(str(db_path))
    try:
        replaced_old_rows = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM eco_entity_metric_value
                WHERE run_id = ?
                  AND source_run_id = 'OLD_SOURCE'
                """,
                (RUN_ID,),
            ).fetchone()[0]
        )
        preserved_unrelated_rows = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM eco_entity_metric_value
                WHERE run_id = ?
                  AND metric_name = 'distance_to_ema20_pct'
                  AND source_run_id = 'KEEP_TICKER'
                """,
                (RUN_ID,),
            ).fetchone()[0]
        )
        duplicated_text_rows = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT window_code, signal_date, entity_id, metric_name, COUNT(*) AS duplicate_count
                    FROM eco_entity_metric_value
                    WHERE run_id = ?
                      AND metric_name IN ('group_timing_state', 'group_overheat_risk_level')
                    GROUP BY window_code, signal_date, entity_id, metric_name
                    HAVING COUNT(*) > 1
                )
                """,
                (RUN_ID,),
            ).fetchone()[0]
        )
    finally:
        conn.close()

    assert replaced_old_rows == 0
    assert preserved_unrelated_rows == 1
    assert duplicated_text_rows == 0
