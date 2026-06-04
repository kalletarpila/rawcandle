import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_window_snapshot_replacement_builder import (
    build_canonical_v3_window_snapshots,
)


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
V2_SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"
REPLACEMENT_SOURCE_RUN_ID = "V3_WINDOW_SNAPSHOT_FROM_ECO_COVERAGE_2026_05_29"
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")


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


def _create_lower_level_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            ticker_trend_state TEXT
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
            calc_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            trend_classification TEXT,
            latest_bos_freshness TEXT,
            latest_reset_freshness TEXT
        )
        """
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
    coverage_status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_coverage (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal,
            has_window_context, coverage_status, source_row_count, missing_component_count
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1, 1, 1, 1, ?, 1, 0)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, window_code, entity_id, coverage_status),
    )


def _insert_quality_summary(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    scope_entity_id: int,
    window_code: str,
    quality_scope: str,
    quality_status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
            scope_entity_id, quality_status, expected_count, actual_count, missing_count, warning_count, error_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            quality_scope,
            scope_entity_id,
            quality_status,
        ),
    )


def _insert_metric_text(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
    metric_name: str,
    metric_value_text: str,
    source_run_id: str = "SOURCE_METRIC",
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, 'OK', ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, window_code, entity_id, metric_name, metric_value_text, source_run_id),
    )


def _insert_metric_num(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
    metric_name: str,
    metric_value_num: float,
    source_run_id: str = "SOURCE_METRIC",
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'OK', ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, window_code, entity_id, metric_name, metric_value_num, source_run_id),
    )


def _insert_classification(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
    classification_type: str,
    classification_state: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, classification_state, decision_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OK', 'CLASS_SRC')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, window_code, entity_id, classification_type, classification_state),
    )


def _insert_snapshot_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
    snapshot_status: str,
    quality_status: str,
    source_run_id: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            snapshot_status, timing_state, trend_state, summary_state, classification_state,
            freshness_status, quality_status, asof_observed_at, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            entity_id,
            snapshot_status,
            quality_status,
            SIGNAL_DATE,
            source_run_id,
        ),
    )


def _insert_ticker_trend_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    trend_state: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, ticker, signal_version, run_id, created_at_utc, ticker_trend_state
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, 'DC_SWING_SIGNAL_V1', 'DC_TICKER_SWING_20260603_DC_SWING_SIGNAL_V1', '2026-06-04T00:00:00Z', ?)
        """,
        (SIGNAL_DATE, ticker, trend_state),
    )


def _insert_group_synthetic_row(
    conn: sqlite3.Connection,
    *,
    group_type: str,
    group_name: str,
    trend_classification: str | None,
    latest_bos_freshness: str | None,
    latest_reset_freshness: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, group_type, group_name, calc_version, run_id, created_at_utc,
            trend_classification, latest_bos_freshness, latest_reset_freshness
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, 'DC_SWING_OHLC_V1', 'DC_GROUP_SYNTH_OHLC_20250801_20260603_DC_SWING_OHLC_V1', '2026-06-04T00:00:00Z', ?, ?, ?)
        """,
        (SIGNAL_DATE, group_type, group_name, trend_classification, latest_bos_freshness, latest_reset_freshness),
    )


def _insert_unrelated_rows(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int, entity_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, observed_date, source_table, source_run_id, signal_status
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'TEST_SIGNAL', 'TEST', ?, 'test_source', 'TEST_SRC', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id, SIGNAL_DATE),
    )
    signal_observation_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id, relevance_label, relevance_score
        ) VALUES (?, 'RELEVANT', 1.0)
        """,
        (signal_observation_id,),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type,
            source_table, source_run_id, event_key, event_status
        ) VALUES (?, ?, ?, ?, ?, 'BOS', 'test_source', 'EVENT_SRC', 'event-key', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, entity_id, SIGNAL_DATE),
    )


def _setup_fixture_db(db_path: str) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_run(conn, ecosystem_id, taxonomy_version_id)
        _create_lower_level_source_tables(conn)

        entity_ids = {
            "ecosystem": _insert_entity(
                conn,
                ecosystem_id=ecosystem_id,
                entity_type="ECOSYSTEM",
                entity_code="DATACENTER",
                entity_name="Datacenter",
            ),
            "layer": _insert_entity(
                conn,
                ecosystem_id=ecosystem_id,
                entity_type="LAYER",
                entity_code="LAYER_AI",
                entity_name="AI Compute",
            ),
            "subindustry": _insert_entity(
                conn,
                ecosystem_id=ecosystem_id,
                entity_type="SUBINDUSTRY",
                entity_code="SUB_GPU",
                entity_name="GPU",
            ),
            "ticker_ok": _insert_entity(
                conn,
                ecosystem_id=ecosystem_id,
                entity_type="TICKER",
                entity_code="PANW",
                entity_name="Palo Alto Networks",
            ),
            "ticker_warn": _insert_entity(
                conn,
                ecosystem_id=ecosystem_id,
                entity_type="TICKER",
                entity_code="CRGY",
                entity_name="CRGY",
            ),
        }

        for window_code in TARGET_WINDOWS:
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ecosystem"],
                window_code=window_code,
                coverage_status="OK",
            )
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["layer"],
                window_code=window_code,
                coverage_status="OK",
            )
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["subindustry"],
                window_code=window_code,
                coverage_status="OK",
            )
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ticker_ok"],
                window_code=window_code,
                coverage_status="OK",
            )
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ticker_warn"],
                window_code=window_code,
                coverage_status="WATCHLIST_ONLY",
            )
            _insert_quality_summary(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                scope_entity_id=entity_ids["ecosystem"],
                window_code=window_code,
                quality_scope="RUN",
                quality_status="WARN",
            )
            _insert_quality_summary(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                scope_entity_id=entity_ids["ecosystem"],
                window_code=window_code,
                quality_scope="WINDOW",
                quality_status="WARN",
            )

        group_timing = {
            "daily": "TRIM_WATCH",
            "rolling2": "TRIM_WATCH",
            "rolling5": "TRIM_WATCH",
            "rolling30": "TRIM_WATCH",
        }
        group_window = {
            "rolling2": "TRIM_WATCH",
            "rolling5": "TRIM_WATCH",
            "rolling30": "EXIT_ZONE",
        }
        sub_timing = {
            "daily": "BUY_ZONE",
            "rolling2": "BUY_ZONE",
            "rolling5": "BUY_ZONE",
            "rolling30": "BUY_ZONE",
        }
        sub_window = {
            "rolling2": "BUY_ZONE",
            "rolling5": "BUY_ZONE",
            "rolling30": "EXIT_ZONE",
        }
        _insert_group_synthetic_row(
            conn,
            group_type="layer",
            group_name="AI Compute",
            trend_classification="UP",
            latest_bos_freshness="STALE",
            latest_reset_freshness="FRESH",
        )
        _insert_group_synthetic_row(
            conn,
            group_type="subindustry",
            group_name="GPU",
            trend_classification="DOWN",
            latest_bos_freshness=None,
            latest_reset_freshness="AGING",
        )
        _insert_ticker_trend_row(conn, ticker="PANW", trend_state="DOWN")
        _insert_ticker_trend_row(conn, ticker="CRGY", trend_state=None)
        for window_code in TARGET_WINDOWS:
            _insert_metric_text(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["layer"],
                window_code=window_code,
                metric_name="group_timing_state",
                metric_value_text=group_timing[window_code],
            )
            _insert_metric_num(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["layer"],
                window_code=window_code,
                metric_name="unused_numeric_fixture",
                metric_value_num=42.0,
            )
            _insert_metric_text(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["subindustry"],
                window_code=window_code,
                metric_name="group_timing_state",
                metric_value_text=sub_timing[window_code],
            )
            _insert_metric_num(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ticker_ok"],
                window_code=window_code,
                metric_name="unused_ticker_numeric_fixture",
                metric_value_num=0.20,
            )
            _insert_metric_num(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ticker_warn"],
                window_code=window_code,
                metric_name="unused_ticker_numeric_fixture",
                metric_value_num=-0.10,
            )
            if window_code != "daily":
                _insert_metric_text(
                    conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    entity_id=entity_ids["layer"],
                    window_code=window_code,
                    metric_name="group_window_status",
                    metric_value_text=group_window[window_code],
                )
                _insert_metric_text(
                    conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    entity_id=entity_ids["subindustry"],
                    window_code=window_code,
                    metric_name="group_window_status",
                    metric_value_text=sub_window[window_code],
                )

        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["ticker_ok"],
            window_code="daily",
            classification_type="daily_trigger",
            classification_state="BUY_WATCH",
        )
        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["ticker_ok"],
            window_code="rolling2",
            classification_type="rolling2_sell_pressure",
            classification_state="NO_EMERGENCY",
        )
        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["ticker_ok"],
            window_code="rolling5",
            classification_type="rolling5_pullback",
            classification_state="NO_PULLBACK",
        )
        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["ticker_ok"],
            window_code="rolling30",
            classification_type="rolling30_buy",
            classification_state="BUY_ZONE",
        )
        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["ticker_warn"],
            window_code="rolling30",
            classification_type="rolling30_buy",
            classification_state="INSUFFICIENT_DATA",
        )

        for window_code in TARGET_WINDOWS:
            _insert_snapshot_row(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ecosystem"],
                window_code=window_code,
                snapshot_status="WARN",
                quality_status="WARN",
                source_run_id=None,
            )
            _insert_snapshot_row(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["layer"],
                window_code=window_code,
                snapshot_status="OK",
                quality_status="OK",
                source_run_id=V2_SOURCE_RUN_ID,
            )
            _insert_snapshot_row(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["subindustry"],
                window_code=window_code,
                snapshot_status="OK",
                quality_status="OK",
                source_run_id=V2_SOURCE_RUN_ID,
            )
            _insert_snapshot_row(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ticker_ok"],
                window_code=window_code,
                snapshot_status="OK",
                quality_status="OK",
                source_run_id=V2_SOURCE_RUN_ID,
            )
            _insert_snapshot_row(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids["ticker_warn"],
                window_code=window_code,
                snapshot_status="WARN",
                quality_status="WARN",
                source_run_id=None,
            )

        _insert_unrelated_rows(conn, ecosystem_id, taxonomy_version_id, entity_ids["ticker_ok"])
        conn.commit()
        return entity_ids
    finally:
        conn.close()


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "snapshot_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_window_snapshots(str(db_path), RUN_ID, replace_existing=True)


def test_builder_rebuilds_window_snapshots_from_v3_facts(tmp_path) -> None:
    db_path = tmp_path / "snapshot_rebuild.db"
    entity_ids = _setup_fixture_db(str(db_path))

    summary = build_canonical_v3_window_snapshots(str(db_path), RUN_ID, replace_existing=True)

    assert summary["replacement_source_run_id"] == REPLACEMENT_SOURCE_RUN_ID
    assert summary["snapshot_rows_inserted"] == 20
    assert summary["rows_deleted_on_replace"] == 20
    assert summary["old_v2_lineage_rows_removed"] == 12
    assert summary["old_null_lineage_rows_replaced"] == 8
    assert summary["rows_by_entity_type"] == {
        "ECOSYSTEM": 4,
        "LAYER": 4,
        "SUBINDUSTRY": 4,
        "TICKER": 8,
    }
    assert summary["rows_by_window_code"] == {
        "daily": 5,
        "rolling2": 5,
        "rolling5": 5,
        "rolling30": 5,
    }
    assert summary["snapshot_status_counts"] == {"WARN": 8, "OK": 12}
    assert summary["quality_status_counts"] == {"WARN": 8, "OK": 12}
    assert summary["source_run_id_counts"] == {REPLACEMENT_SOURCE_RUN_ID: 20}
    assert summary["warning_count"] == 0
    assert "eco_entity_coverage" in summary["source_dependency_summary"]

    conn = _connect(str(db_path))
    try:
        total_rows = conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0]
        assert total_rows == 20
        v2_rows = conn.execute(
            "SELECT COUNT(*) FROM eco_entity_window_snapshot WHERE source_run_id = ?",
            (V2_SOURCE_RUN_ID,),
        ).fetchone()[0]
        assert v2_rows == 0
        null_rows = conn.execute(
            "SELECT COUNT(*) FROM eco_entity_window_snapshot WHERE source_run_id IS NULL"
        ).fetchone()[0]
        assert null_rows == 0

        layer_daily = conn.execute(
            """
            SELECT timing_state, trend_state, summary_state, freshness_status, snapshot_status, quality_status, source_run_id
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'daily'
            """,
            (entity_ids["layer"],),
        ).fetchone()
        assert dict(layer_daily) == {
            "timing_state": "TRIM_WATCH",
            "trend_state": "UP",
            "summary_state": "TRIM_WATCH",
            "freshness_status": "STALE",
            "snapshot_status": "OK",
            "quality_status": "OK",
            "source_run_id": REPLACEMENT_SOURCE_RUN_ID,
        }

        sub_rolling30 = conn.execute(
            """
            SELECT timing_state, trend_state, summary_state, freshness_status
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'rolling30'
            """,
            (entity_ids["subindustry"],),
        ).fetchone()
        assert dict(sub_rolling30) == {
            "timing_state": "BUY_ZONE",
            "trend_state": "DOWN",
            "summary_state": "EXIT_ZONE",
            "freshness_status": "AGING",
        }

        ticker_daily = conn.execute(
            """
            SELECT summary_state, classification_state, trend_state, timing_state, freshness_status
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'daily'
            """,
            (entity_ids["ticker_ok"],),
        ).fetchone()
        assert dict(ticker_daily) == {
            "summary_state": "OK",
            "classification_state": "BUY_WATCH",
            "trend_state": "DOWN",
            "timing_state": None,
            "freshness_status": None,
        }

        ticker_warn = conn.execute(
            """
            SELECT snapshot_status, quality_status, summary_state, classification_state, source_run_id
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'rolling2'
            """,
            (entity_ids["ticker_warn"],),
        ).fetchone()
        assert dict(ticker_warn) == {
            "snapshot_status": "WARN",
            "quality_status": "WARN",
            "summary_state": None,
            "classification_state": None,
            "source_run_id": REPLACEMENT_SOURCE_RUN_ID,
        }

        ecosystem_warn = conn.execute(
            """
            SELECT snapshot_status, quality_status, summary_state, source_run_id
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'rolling5'
            """,
            (entity_ids["ecosystem"],),
        ).fetchone()
        assert dict(ecosystem_warn) == {
            "snapshot_status": "WARN",
            "quality_status": "WARN",
            "summary_state": None,
            "source_run_id": REPLACEMENT_SOURCE_RUN_ID,
        }
    finally:
        conn.close()


def test_replace_existing_false_rejects_existing_target_rows(tmp_path) -> None:
    db_path = tmp_path / "snapshot_replace_false.db"
    _setup_fixture_db(str(db_path))

    with pytest.raises(ValueError, match="replace_existing=False"):
        build_canonical_v3_window_snapshots(str(db_path), RUN_ID, replace_existing=False)


def test_builder_is_idempotent_and_preserves_non_target_tables(tmp_path) -> None:
    db_path = tmp_path / "snapshot_idempotent.db"
    _setup_fixture_db(str(db_path))

    conn = _connect(str(db_path))
    try:
        before_counts = {
            "metrics": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
            "signals": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
            "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
            "classifications": conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0],
            "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
            "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
            "runs": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
        }
    finally:
        conn.close()

    first = build_canonical_v3_window_snapshots(str(db_path), RUN_ID, replace_existing=True)
    second = build_canonical_v3_window_snapshots(str(db_path), RUN_ID, replace_existing=True)

    assert first["snapshot_rows_inserted"] == 20
    assert second["snapshot_rows_inserted"] == 20
    assert second["rows_deleted_on_replace"] == 20
    assert second["source_run_id_counts"] == {REPLACEMENT_SOURCE_RUN_ID: 20}

    conn = _connect(str(db_path))
    try:
        after_counts = {
            "metrics": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
            "signals": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
            "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
            "classifications": conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0],
            "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
            "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
            "runs": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
        }
        duplicates = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT run_id, entity_id, window_code, COUNT(*) AS n
                FROM eco_entity_window_snapshot
                GROUP BY run_id, entity_id, window_code
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        assert duplicates == 0
    finally:
        conn.close()

    assert after_counts == before_counts
