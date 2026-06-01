import sqlite3

import pytest

from rawcandle.report_canonical_v3_base_builder import build_canonical_v3_base_run
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_snapshot_metric_builder import (
    build_canonical_v3_snapshot_metrics,
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


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int, version_code: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id, version_code, version_label, source_type, source_reference,
            effective_from, effective_to, is_active, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, version_code, version_code, None, None, None, None, 1, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    *,
    entity_type: str,
    entity_code: str,
    entity_name: str,
    ticker: str | None = None,
    status: str = "ACTIVE",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker,
            exchange, market, currency, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, entity_type, entity_code, entity_name, ticker, None, None, None, status),
    )
    return int(cursor.lastrowid)


def _insert_relation(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    ecosystem_id: int,
    parent_entity_id: int,
    child_entity_id: int,
    membership_role: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_taxonomy_entity_relation (
            taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
            relation_type, membership_role, weight, is_primary, sort_order,
            effective_from, effective_to, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            taxonomy_version_id,
            ecosystem_id,
            parent_entity_id,
            child_entity_id,
            "CONTAINS",
            membership_role,
            None,
            0,
            None,
            None,
            None,
            "ACTIVE",
        ),
    )


def _insert_watchlist(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_watchlist (
            ecosystem_id, watchlist_code, watchlist_name, description,
            source_type, source_reference, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            "DATACENTER_DEFAULT",
            "Datacenter default watchlist",
            None,
            "TXT",
            "/tmp/watchlist.txt",
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid)


def _insert_watchlist_member(conn: sqlite3.Connection, watchlist_id: int, entity_id: int, member_role: str) -> None:
    conn.execute(
        """
        INSERT INTO eco_watchlist_member (
            watchlist_id, entity_id, member_role, member_status,
            effective_from, effective_to, sort_order, removed_at_utc, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (watchlist_id, entity_id, member_role, "ACTIVE", None, None, None, None, None),
    )


def _create_daily_signal_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            PRIMARY KEY (signal_date, taxonomy_version, ticker)
        )
        """
    )


def _create_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_report_context_daily_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            trend_state TEXT NULL,
            context_readiness_status TEXT NOT NULL,
            freshness_status TEXT NULL,
            return_5d REAL NULL,
            return_10d REAL NULL,
            return_20d REAL NULL,
            return_60d REAL NULL,
            distance_to_ema10_pct REAL NULL,
            distance_to_ema20_pct REAL NULL,
            latest_structure_age_trading_days INTEGER NULL,
            latest_bos_age_trading_days INTEGER NULL,
            latest_reset_age_trading_days INTEGER NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (signal_date, taxonomy_version, ticker)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_report_context_window_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            horizon TEXT NOT NULL,
            trend_state TEXT NULL,
            context_readiness_status TEXT NOT NULL,
            freshness_status TEXT NULL,
            breakout_days INTEGER NULL,
            pullback_days INTEGER NULL,
            exit_risk_days INTEGER NULL,
            high_exit_risk_days INTEGER NULL,
            medium_exit_risk_days INTEGER NULL,
            valid_signal_dates INTEGER NULL,
            distance_to_ema20_pct REAL NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (signal_date, taxonomy_version, ticker, horizon)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_report_context_group_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            horizon TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            timing_state TEXT NULL,
            synthetic_trend_classification TEXT NULL,
            group_current_status TEXT NULL,
            group_window_status TEXT NULL,
            synthetic_latest_bos_freshness TEXT NULL,
            synthetic_latest_reset_freshness TEXT NULL,
            return_2d REAL NULL,
            return_5d REAL NULL,
            return_30d REAL NULL,
            synthetic_close REAL NULL,
            pct_above_ema20 REAL NULL,
            trend_breadth REAL NULL,
            weakness_breadth REAL NULL,
            strength_breadth REAL NULL,
            valid_signal_dates INTEGER NULL,
            window_end_date TEXT NOT NULL,
            run_id TEXT NOT NULL,
            data_quality_status TEXT NULL,
            PRIMARY KEY (signal_date, taxonomy_version, horizon, group_type, group_name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_report_classification_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            horizon TEXT NOT NULL,
            classification_type TEXT NOT NULL,
            classification_state TEXT NOT NULL,
            classification_status TEXT NOT NULL,
            PRIMARY KEY (signal_date, taxonomy_version, ticker, horizon, classification_type)
        )
        """
    )


def _seed_base_state(conn: sqlite3.Connection) -> dict[str, int]:
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id, "DC_TAXONOMY_FULL_V1")
    ecosystem_entity_id = _insert_entity(
        conn,
        ecosystem_id,
        entity_type="ECOSYSTEM",
        entity_code="DATACENTER",
        entity_name="Datacenter",
    )
    layer_entity_id = _insert_entity(
        conn,
        ecosystem_id,
        entity_type="LAYER",
        entity_code="AI_INFRA",
        entity_name="AI Infrastructure",
    )
    subindustry_entity_id = _insert_entity(
        conn,
        ecosystem_id,
        entity_type="SUBINDUSTRY",
        entity_code="GPU",
        entity_name="GPU Platforms",
    )
    active_ticker_id = _insert_entity(
        conn,
        ecosystem_id,
        entity_type="TICKER",
        entity_code="NVDA",
        entity_name="NVIDIA",
        ticker="NVDA",
    )
    watch_only_ticker_id = _insert_entity(
        conn,
        ecosystem_id,
        entity_type="TICKER",
        entity_code="CRGY",
        entity_name="CRGY",
        ticker="CRGY",
        status="WATCH_ONLY",
    )
    _insert_relation(
        conn,
        taxonomy_version_id=taxonomy_version_id,
        ecosystem_id=ecosystem_id,
        parent_entity_id=ecosystem_entity_id,
        child_entity_id=layer_entity_id,
        membership_role="CORE",
    )
    _insert_relation(
        conn,
        taxonomy_version_id=taxonomy_version_id,
        ecosystem_id=ecosystem_id,
        parent_entity_id=layer_entity_id,
        child_entity_id=subindustry_entity_id,
        membership_role="CORE",
    )
    _insert_relation(
        conn,
        taxonomy_version_id=taxonomy_version_id,
        ecosystem_id=ecosystem_id,
        parent_entity_id=subindustry_entity_id,
        child_entity_id=active_ticker_id,
        membership_role="CORE",
    )
    watchlist_id = _insert_watchlist(conn, ecosystem_id)
    _insert_watchlist_member(conn, watchlist_id, active_ticker_id, "CORE")
    _insert_watchlist_member(conn, watchlist_id, watch_only_ticker_id, "WATCH_ONLY")
    _create_daily_signal_table(conn)
    _create_source_tables(conn)
    conn.commit()
    return {
        "ecosystem_id": ecosystem_id,
        "taxonomy_version_id": taxonomy_version_id,
        "ecosystem_entity_id": ecosystem_entity_id,
        "layer_entity_id": layer_entity_id,
        "subindustry_entity_id": subindustry_entity_id,
        "active_ticker_id": active_ticker_id,
        "watch_only_ticker_id": watch_only_ticker_id,
    }


def _insert_daily_signal(conn: sqlite3.Connection, signal_date: str, ticker: str) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (signal_date, taxonomy_version, ticker)
        VALUES (?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", ticker),
    )


def _seed_source_context(conn: sqlite3.Connection, signal_date: str) -> None:
    _insert_daily_signal(conn, signal_date, "NVDA")
    conn.execute(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date, taxonomy_version, ticker, trend_state, context_readiness_status,
            freshness_status, return_5d, return_10d, return_20d, return_60d,
            distance_to_ema10_pct, distance_to_ema20_pct, latest_structure_age_trading_days,
            latest_bos_age_trading_days, latest_reset_age_trading_days, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "NVDA",
            "UP",
            "OK",
            "FRESH",
            0.12,
            0.2,
            0.33,
            0.44,
            0.05,
            0.08,
            3,
            2,
            1,
            "SRC_DAILY_RUN",
        ),
    )
    for horizon, values in {
        "rolling2": (1, 0, 2, 1, 1, 2, 0.09),
        "rolling5": (2, 1, 5, 2, 3, 5, 0.11),
        "rolling30": (8, 4, 20, 7, 13, 30, 0.14),
    }.items():
        conn.execute(
            """
            INSERT INTO dc_report_context_window_v2 (
                signal_date, taxonomy_version, ticker, horizon, trend_state,
                context_readiness_status, freshness_status, breakout_days,
                pullback_days, exit_risk_days, high_exit_risk_days,
                medium_exit_risk_days, valid_signal_dates, distance_to_ema20_pct, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                horizon,
                "UP",
                "OK",
                "FRESH",
                values[0],
                values[1],
                values[2],
                values[3],
                values[4],
                values[5],
                values[6],
                "SRC_WINDOW_RUN",
            ),
        )
    for group_type, group_name in {
        "layer": "AI Infrastructure",
        "subindustry": "GPU Platforms",
    }.items():
        for horizon in ("daily", "rolling2", "rolling5", "rolling30"):
            conn.execute(
                """
                INSERT INTO dc_report_context_group_v2 (
                    signal_date, taxonomy_version, horizon, group_type, group_name,
                    timing_state, synthetic_trend_classification, group_current_status,
                    group_window_status, synthetic_latest_bos_freshness,
                    synthetic_latest_reset_freshness, return_2d, return_5d, return_30d,
                    synthetic_close, pct_above_ema20, trend_breadth, weakness_breadth,
                    strength_breadth, valid_signal_dates, window_end_date, run_id, data_quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date,
                    "DC_TAXONOMY_FULL_V1",
                    horizon,
                    group_type,
                    group_name,
                    "ENTRY",
                    "UP",
                    "LEADING",
                    "LEADING",
                    "FRESH",
                    "FRESH",
                    0.01,
                    0.02,
                    0.05,
                    101.5,
                    67.0,
                    55.0,
                    12.0,
                    43.0,
                    5 if horizon == "rolling5" else 30 if horizon == "rolling30" else 2 if horizon == "rolling2" else 1,
                    signal_date,
                    "SRC_GROUP_RUN",
                    "OK",
                ),
            )
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, ticker, horizon,
            classification_type, classification_state, classification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", "NVDA", "daily", "daily_trigger", "BUY_TRIGGER", "OK"),
    )
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, ticker, horizon,
            classification_type, classification_state, classification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2", "rolling2_sell_pressure", "WATCH_PRESSURE", "OK"),
    )
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, ticker, horizon,
            classification_type, classification_state, classification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", "NVDA", "rolling5", "rolling5_pullback", "ACTIVE_PULLBACK", "OK"),
    )
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, ticker, horizon,
            classification_type, classification_state, classification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", "NVDA", "rolling30", "rolling30_buy", "AVOID", "OK"),
    )
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, ticker, horizon,
            classification_type, classification_state, classification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", "NVDA", "rolling30", "rolling30_exit", "EXIT_ZONE", "OK"),
    )


def _prepare_run(db_path: str) -> dict[str, int]:
    with _connect(db_path) as conn:
        ids = _seed_base_state(conn)
        _seed_source_context(conn, "2026-05-29")
    build_canonical_v3_base_run(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        signal_date="2026-05-29",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_run=True,
    )
    return ids


def test_snapshot_metric_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "snapshot_missing_run.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_snapshot_metrics(str(db_path), "missing-run")


def test_snapshot_metric_builder_creates_rows_for_all_entity_types_and_windows(tmp_path) -> None:
    db_path = tmp_path / "snapshot_metrics.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    ids = _prepare_run(str(db_path))

    summary = build_canonical_v3_snapshot_metrics(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=False,
    )

    assert summary["selected_entity_count"] == 5
    assert summary["window_count"] == 4
    assert summary["snapshot_rows_inserted"] == 20
    assert summary["warning_count"] == 8
    assert summary["snapshot_status_counts"] == {"OK": 12, "WARN": 8}

    with _connect(str(db_path)) as conn:
        snapshot_counts = conn.execute(
            """
            SELECT entity_type, COUNT(*) AS row_count
            FROM eco_entity_window_snapshot s
            JOIN eco_entity e ON e.entity_id = s.entity_id
            GROUP BY entity_type
            ORDER BY entity_type
            """
        ).fetchall()
        assert [tuple(row) for row in snapshot_counts] == [
            ("ECOSYSTEM", 4),
            ("LAYER", 4),
            ("SUBINDUSTRY", 4),
            ("TICKER", 8),
        ]

        crgy_rows = conn.execute(
            """
            SELECT snapshot_status, quality_status
            FROM eco_entity_window_snapshot
            WHERE entity_id = ?
            ORDER BY window_code
            """,
            (ids["watch_only_ticker_id"],),
        ).fetchall()
        assert [tuple(row) for row in crgy_rows] == [
            ("WARN", "WARN"),
            ("WARN", "WARN"),
            ("WARN", "WARN"),
            ("WARN", "WARN"),
        ]

        nvda_daily = conn.execute(
            """
            SELECT snapshot_status, trend_state, summary_state, classification_state, freshness_status
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'daily'
            """,
            (ids["active_ticker_id"],),
        ).fetchone()
        assert tuple(nvda_daily) == ("OK", "UP", "OK", "BUY_TRIGGER", "FRESH")

        nvda_metric_rows = conn.execute(
            """
            SELECT metric_name, metric_value_num
            FROM eco_entity_metric_value
            WHERE entity_id = ? AND window_code = 'rolling5'
            ORDER BY metric_name
            """,
            (ids["active_ticker_id"],),
        ).fetchall()
        assert ("breakout_days", 2.0) in [tuple(row) for row in nvda_metric_rows]
        assert ("valid_signal_dates", 5.0) in [tuple(row) for row in nvda_metric_rows]

        layer_daily = conn.execute(
            """
            SELECT snapshot_status, timing_state, trend_state, summary_state, freshness_status
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'daily'
            """,
            (ids["layer_entity_id"],),
        ).fetchone()
        assert tuple(layer_daily) == ("OK", "ENTRY", "UP", "LEADING", "FRESH")

        layer_metric_rows = conn.execute(
            """
            SELECT metric_name, metric_value_num
            FROM eco_entity_metric_value
            WHERE entity_id = ? AND window_code = 'rolling30'
            ORDER BY metric_name
            """,
            (ids["layer_entity_id"],),
        ).fetchall()
        assert ("return_30d", 0.05) in [tuple(row) for row in layer_metric_rows]
        assert ("synthetic_close", 101.5) in [tuple(row) for row in layer_metric_rows]

        ecosystem_daily = conn.execute(
            """
            SELECT snapshot_status, quality_status
            FROM eco_entity_window_snapshot
            WHERE entity_id = ? AND window_code = 'daily'
            """,
            (ids["ecosystem_entity_id"],),
        ).fetchone()
        assert tuple(ecosystem_daily) == ("WARN", "WARN")

        ecosystem_metrics = conn.execute(
            """
            SELECT metric_name, metric_value_num
            FROM eco_entity_metric_value
            WHERE entity_id = ? AND window_code = 'daily'
            ORDER BY metric_name
            """,
            (ids["ecosystem_entity_id"],),
        ).fetchall()
        assert [tuple(row) for row in ecosystem_metrics] == [
            ("missing_coverage_count", 1.0),
            ("ok_coverage_count", 4.0),
            ("selected_entity_count", 5.0),
            ("warning_count", 1.0),
            ("watchlist_only_count", 1.0),
        ]

        assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == 20
        assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 0


def test_snapshot_metric_builder_replace_existing_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "snapshot_replace.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _prepare_run(str(db_path))

    build_canonical_v3_snapshot_metrics(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=False,
    )

    with pytest.raises(ValueError, match="already exist"):
        build_canonical_v3_snapshot_metrics(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            replace_existing=False,
        )

    summary = build_canonical_v3_snapshot_metrics(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        replace_existing=True,
    )
    assert summary["snapshot_rows_inserted"] == 20

    with _connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 20
        metric_count = conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0]
        assert metric_count == summary["metric_rows_inserted"]
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == 20
        assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 8


def test_snapshot_metric_builder_rolls_back_on_error(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "snapshot_rollback.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _prepare_run(str(db_path))

    from rawcandle import report_canonical_v3_snapshot_metric_builder as builder_module

    def _boom(conn: sqlite3.Connection, metric_rows: list[dict[str, object]]) -> None:
        raise RuntimeError("forced metric insert failure")

    monkeypatch.setattr(builder_module, "_insert_metric_rows", _boom)

    with pytest.raises(RuntimeError, match="forced metric insert failure"):
        build_canonical_v3_snapshot_metrics(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            replace_existing=False,
        )

    with _connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0] == 0
