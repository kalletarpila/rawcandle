import sqlite3

import pytest

from rawcandle.report_canonical_v3_freshness_builder import build_canonical_v3_freshness
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


def _create_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_report_context_daily_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            latest_structure_age_trading_days REAL NULL,
            latest_bos_age_trading_days REAL NULL,
            latest_reset_age_trading_days REAL NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_freshness TEXT NULL,
            freshness_status TEXT NULL,
            run_id TEXT NULL
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
            latest_structure_age_trading_days REAL NULL,
            latest_bos_age_trading_days REAL NULL,
            latest_reset_age_trading_days REAL NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_freshness TEXT NULL,
            freshness_status TEXT NULL,
            run_id TEXT NULL
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
            latest_structure_age_trading_days REAL NULL,
            latest_bos_age_trading_days REAL NULL,
            latest_reset_age_trading_days REAL NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_freshness TEXT NULL,
            calc_version TEXT NULL
        )
        """
    )


def _insert_source_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date, taxonomy_version, ticker,
            latest_structure_age_trading_days, latest_bos_age_trading_days, latest_reset_age_trading_days,
            latest_structure_freshness, latest_bos_freshness, latest_reset_freshness,
            freshness_status, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "NVDA", 2, 3, 4, "FRESH", "AGING", "STALE", "FRESH", "daily-source"),
    )
    for horizon in ("rolling2", "rolling5", "rolling30"):
        conn.execute(
            """
            INSERT INTO dc_report_context_window_v2 (
                signal_date, taxonomy_version, ticker, horizon,
                latest_structure_age_trading_days, latest_bos_age_trading_days, latest_reset_age_trading_days,
                latest_structure_freshness, latest_bos_freshness, latest_reset_freshness,
                freshness_status, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "NVDA", horizon, 5, 6, 7, "AGING", "FRESH", "STALE", "AGING", "window-source"),
        )
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, group_type, group_name,
            latest_structure_age_trading_days, latest_bos_age_trading_days, latest_reset_age_trading_days,
            latest_structure_freshness, latest_bos_freshness, latest_reset_freshness, calc_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "layer", "AI Compute", 8, 9, 10, "FRESH", "AGING", "STALE", "group-v1"),
    )
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, group_type, group_name,
            latest_structure_age_trading_days, latest_bos_age_trading_days, latest_reset_age_trading_days,
            latest_structure_freshness, latest_bos_freshness, latest_reset_freshness, calc_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "subindustry", "GPU", 11, 12, 13, "AGING", "FRESH", "STALE", "group-v1"),
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
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope, scope_entity_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", "TICKER", entity_id, "OK"),
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
    _create_source_tables(conn)
    _insert_source_rows(conn)
    _insert_supporting_fact_rows(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=ticker_id)
    conn.commit()
    return conn


def test_freshness_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_freshness_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_freshness(str(db_path), RUN_ID)


def test_freshness_builder_writes_metrics_and_signals_from_all_sources(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_freshness_builder.db"
    conn = _setup_db(str(db_path))
    conn.close()

    summary = build_canonical_v3_freshness(str(db_path), RUN_ID)

    conn = _connect(str(db_path))
    try:
        metric_names = {
            row["metric_name"]
            for row in conn.execute(
                """
                SELECT DISTINCT metric_name
                FROM eco_entity_metric_value
                WHERE run_id = ?
                  AND metric_name LIKE 'freshness_%'
                """,
                (RUN_ID,),
            ).fetchall()
        }
        assert "freshness_latest_structure_age_trading_days" in metric_names
        assert "freshness_latest_bos_age_trading_days" in metric_names
        assert "freshness_latest_reset_age_trading_days" in metric_names
        assert "freshness_latest_structure_class" in metric_names
        assert "freshness_latest_bos_class" in metric_names
        assert "freshness_latest_reset_class" in metric_names
        assert "freshness_overall_status" in metric_names

        signal_names = {
            row["signal_name"]
            for row in conn.execute(
                """
                SELECT DISTINCT signal_name
                FROM eco_signal_observation
                WHERE run_id = ?
                  AND signal_family = 'FRESHNESS'
                """,
                (RUN_ID,),
            ).fetchall()
        }
        assert signal_names == {
            "STRUCTURE_FRESHNESS",
            "BOS_FRESHNESS",
            "RESET_FRESHNESS",
            "OVERALL_FRESHNESS",
        }

        ticker_daily_metric = conn.execute(
            """
            SELECT metric_value_num, metric_unit, source_run_id
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND mv.window_code = 'daily'
              AND e.entity_type = 'TICKER'
              AND e.entity_code = 'NVDA'
              AND mv.metric_name = 'freshness_latest_structure_age_trading_days'
            """,
            (RUN_ID,),
        ).fetchone()
        assert ticker_daily_metric["metric_value_num"] == 2
        assert ticker_daily_metric["metric_unit"] == "trading_days"
        assert ticker_daily_metric["source_run_id"] == "daily-source"

        ticker_rolling_metric = conn.execute(
            """
            SELECT metric_value_text, source_run_id
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND mv.window_code = 'rolling30'
              AND e.entity_type = 'TICKER'
              AND e.entity_code = 'NVDA'
              AND mv.metric_name = 'freshness_overall_status'
            """,
            (RUN_ID,),
        ).fetchone()
        assert ticker_rolling_metric["metric_value_text"] == "AGING"
        assert ticker_rolling_metric["source_run_id"] == "window-source"

        layer_metric_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND e.entity_type = 'LAYER'
              AND mv.metric_name LIKE 'freshness_%'
            """,
            (RUN_ID,),
        ).fetchone()[0]
        subindustry_metric_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value mv
            JOIN eco_entity e ON e.entity_id = mv.entity_id
            WHERE mv.run_id = ?
              AND e.entity_type = 'SUBINDUSTRY'
              AND mv.metric_name LIKE 'freshness_%'
            """,
            (RUN_ID,),
        ).fetchone()[0]
        assert layer_metric_count > 0
        assert subindustry_metric_count > 0

        relevance_count = conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0]
        assert relevance_count == 0
        assert event_count == 0

        assert summary["source_classifications"] == {
            "dc_report_context_daily_v2": "TRANSITIONAL_V2_SOURCE",
            "dc_report_context_window_v2": "TRANSITIONAL_V2_SOURCE",
            "dc_group_synthetic_ohlc_daily": "DERIVED_FROM_RAW_SOURCE",
        }
        assert "no freshness events are created" in summary["limitations"]
        assert "no signal relevance rows are created" in summary["limitations"]
        assert "ecosystem freshness skipped if no direct source was used" in summary["limitations"]
    finally:
        conn.close()


def test_freshness_builder_preserves_non_freshness_rows_and_other_facts(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_freshness_preserve.db"
    conn = _setup_db(str(db_path))
    conn.close()

    before = _connect(str(db_path))
    try:
        snapshot_count = before.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0]
        coverage_count = before.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0]
        quality_count = before.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0]
        classification_count = before.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0]
        run_count = before.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0]
        non_fresh_metric_count = before.execute(
            "SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name = 'metric_a'"
        ).fetchone()[0]
        non_fresh_signal_count = before.execute(
            "SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'REVERSAL_MEDIUM'"
        ).fetchone()[0]
    finally:
        before.close()

    build_canonical_v3_freshness(str(db_path), RUN_ID)

    after = _connect(str(db_path))
    try:
        assert after.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == snapshot_count
        assert after.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == coverage_count
        assert after.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == quality_count
        assert after.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == classification_count
        assert after.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == run_count
        assert after.execute("SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name = 'metric_a'").fetchone()[0] == non_fresh_metric_count
        assert after.execute(
            "SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'REVERSAL_MEDIUM'"
        ).fetchone()[0] == non_fresh_signal_count
    finally:
        after.close()


def test_freshness_builder_replace_behavior_and_relevance_guard(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_freshness_replace.db"
    conn = _setup_db(str(db_path))
    conn.close()

    first_summary = build_canonical_v3_freshness(str(db_path), RUN_ID)
    assert first_summary["metric_rows_inserted"] > 0
    assert first_summary["signal_observations_inserted"] > 0

    with pytest.raises(ValueError, match="Freshness builder-owned rows already exist"):
        build_canonical_v3_freshness(str(db_path), RUN_ID, replace_existing=False)

    second_summary = build_canonical_v3_freshness(str(db_path), RUN_ID, replace_existing=True)
    assert second_summary["metric_rows_inserted"] == first_summary["metric_rows_inserted"]
    assert second_summary["signal_observations_inserted"] == first_summary["signal_observations_inserted"]

    conn = _connect(str(db_path))
    try:
        freshness_signal_id = conn.execute(
            """
            SELECT signal_observation_id
            FROM eco_signal_observation
            WHERE run_id = ?
              AND signal_family = 'FRESHNESS'
            LIMIT 1
            """,
            (RUN_ID,),
        ).fetchone()["signal_observation_id"]
        conn.execute(
            """
            INSERT INTO eco_signal_relevance (
                signal_observation_id,
                relevance_label,
                relevance_score,
                relevance_reason
            ) VALUES (?, ?, ?, ?)
            """,
            (freshness_signal_id, "RELEVANT", 1.0, "test"),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="Cannot replace freshness signal observations"):
        build_canonical_v3_freshness(str(db_path), RUN_ID, replace_existing=True)
