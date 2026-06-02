import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_ticker_freshness_replacement_builder import (
    build_canonical_v3_ticker_freshness_from_signal_daily,
)


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_RUN_ID = "DC_TICKER_SWING_20260601_DC_SWING_SIGNAL_V1"


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
    status: str = "ACTIVE",
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
        (ecosystem_id, entity_type, entity_code, entity_name, ticker, None, None, None, status),
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
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            latest_structure_age_trading_days REAL NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_age_trading_days REAL NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_age_trading_days REAL NULL,
            latest_reset_freshness TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_reset_reason TEXT NULL,
            price_data_status TEXT NULL,
            signal_version TEXT NOT NULL,
            run_id TEXT NULL
        )
        """
    )


def _insert_source_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    structure_age: float | None,
    structure_class: str | None,
    bos_age: float | None,
    bos_class: str | None,
    reset_age: float | None,
    reset_class: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, ticker,
            latest_structure_age_trading_days, latest_structure_freshness,
            latest_bos_age_trading_days, latest_bos_freshness,
            latest_reset_age_trading_days, latest_reset_freshness,
            latest_structure_label, latest_bos_event_type, latest_reset_reason,
            price_data_status, signal_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            ticker,
            structure_age,
            structure_class,
            bos_age,
            bos_class,
            reset_age,
            reset_class,
            "UPTREND",
            "BOS_UP",
            "RESET",
            "OK",
            "DC_SWING_SIGNAL_V1",
            SOURCE_RUN_ID,
        ),
    )


def _insert_snapshot_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            snapshot_status,
            timing_state,
            trend_state,
            summary_state,
            classification_state,
            freshness_status,
            quality_status,
            asof_observed_at,
            source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            entity_id,
            "OK",
            None,
            None,
            None,
            None,
            None,
            "OK",
            None,
            "SNAPSHOT_SOURCE",
        ),
    )


def _insert_quality_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            quality_scope,
            scope_entity_id,
            quality_status,
            expected_count,
            actual_count,
            missing_count,
            incomplete_count,
            stale_count,
            warning_count,
            error_count,
            summary_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            "RUN",
            1,
            "OK",
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            None,
        ),
    )


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, decision_status, classification_state, priority_score, priority_label,
            primary_reason, blocking_reason, risk_reason, next_action, sort_rank, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            entity_id,
            "daily_trigger",
            "OK",
            "NO_TRIGGER",
            None,
            None,
            "baseline",
            None,
            None,
            "NONE",
            None,
            "BASELINE",
        ),
    )


def _insert_group_freshness_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    layer_entity_id: int,
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
            "daily",
            layer_entity_id,
            "freshness_latest_structure_class",
            None,
            "FRESH",
            None,
            "OK",
            "GROUP_SOURCE_V1",
        ),
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
            layer_entity_id,
            "STRUCTURE_FRESHNESS",
            "FRESHNESS",
            "UNKNOWN",
            "FRESH",
            SIGNAL_DATE,
            "dc_group_synthetic_ohlc_daily",
            "GROUP_SOURCE_V1",
            "group:layer:STRUCTURE_FRESHNESS",
            "ACTIVE",
        ),
    )


def _insert_existing_ticker_replacement_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    ticker_entity_id: int,
    ticker: str,
) -> None:
    for window_code in ("daily", "rolling2", "rolling5", "rolling30"):
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
                ticker_entity_id,
                "freshness_latest_structure_class",
                None,
                "STALE",
                None,
                "OK",
                "OLD_TICKER_SOURCE",
            ),
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
                window_code,
                ticker_entity_id,
                "STRUCTURE_FRESHNESS",
                "FRESHNESS",
                "UNKNOWN",
                "STALE",
                SIGNAL_DATE,
                "old_source",
                "OLD_TICKER_SOURCE",
                f"old:{ticker}:{window_code}:STRUCTURE_FRESHNESS",
                "ACTIVE",
            ),
        )


def _insert_non_freshness_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    ticker_entity_id: int,
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
            "daily",
            ticker_entity_id,
            "distance_to_ema20_pct",
            1.5,
            None,
            "pct",
            "OK",
            "BASELINE",
        ),
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
            ticker_entity_id,
            "EMA20_STATUS",
            "MA_STATUS",
            "UP",
            "ABOVE_EMA20",
            SIGNAL_DATE,
            "dc_ticker_swing_signal_daily",
            "BASELINE",
            "ma:status",
            "ACTIVE",
        ),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date,
            event_type, source_table, source_run_id, source_event_id,
            event_key, event_label, event_direction, event_status, event_payload_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            taxonomy_version_id,
            ticker_entity_id,
            SIGNAL_DATE,
            "BOS",
            "baseline",
            "BASELINE",
            "event-1",
            "event-key",
            "BOS",
            "UP",
            "ACTIVE",
            None,
        ),
    )


def _seed_db(db_path: str) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_run(conn, ecosystem_id, taxonomy_version_id)

        nvda_entity_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="TICKER",
            entity_code="NVDA",
            entity_name="NVIDIA",
            ticker="NVDA",
        )
        amd_entity_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="TICKER",
            entity_code="AMD",
            entity_name="AMD",
            ticker="AMD",
        )
        crgy_entity_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="TICKER",
            entity_code="CRGY",
            entity_name="Crescent Energy",
            ticker="CRGY",
            status="WATCH_ONLY",
        )
        layer_entity_id = _insert_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="LAYER",
            entity_code="AI_COMPUTE",
            entity_name="AI Compute",
        )

        for entity_id in (nvda_entity_id, amd_entity_id, crgy_entity_id):
            for window_code in ("daily", "rolling2", "rolling5", "rolling30"):
                _insert_coverage(
                    conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    entity_id=entity_id,
                    window_code=window_code,
                )
                _insert_snapshot_row(
                    conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    entity_id=entity_id,
                    window_code=window_code,
                )
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=layer_entity_id,
            window_code="daily",
        )
        _insert_snapshot_row(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=layer_entity_id,
            window_code="daily",
        )
        _insert_quality_row(
            conn,
            run_id=RUN_ID,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
        )
        _insert_classification_row(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=nvda_entity_id,
        )
        _create_source_table(conn)
        _insert_source_row(
            conn,
            ticker="NVDA",
            structure_age=2,
            structure_class="FRESH",
            bos_age=5,
            bos_class="AGING",
            reset_age=9,
            reset_class="STALE",
        )
        _insert_source_row(
            conn,
            ticker="AMD",
            structure_age=3,
            structure_class="AGING",
            bos_age=1,
            bos_class="FRESH",
            reset_age=None,
            reset_class=None,
        )
        _insert_source_row(
            conn,
            ticker="ORCL",
            structure_age=4,
            structure_class="FRESH",
            bos_age=4,
            bos_class="FRESH",
            reset_age=4,
            reset_class="FRESH",
        )
        _insert_group_freshness_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            layer_entity_id=layer_entity_id,
        )
        _insert_non_freshness_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            ticker_entity_id=nvda_entity_id,
        )
        conn.commit()
        return {
            "ecosystem_id": ecosystem_id,
            "taxonomy_version_id": taxonomy_version_id,
            "nvda_entity_id": nvda_entity_id,
            "amd_entity_id": amd_entity_id,
            "crgy_entity_id": crgy_entity_id,
            "layer_entity_id": layer_entity_id,
        }
    finally:
        conn.close()


def test_builder_requires_existing_run(tmp_path):
    db_path = tmp_path / "freshness_replace_run_missing.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=True)


def test_builder_writes_ticker_freshness_and_preserves_other_layers(tmp_path):
    db_path = tmp_path / "freshness_replace_ok.db"
    ids = _seed_db(str(db_path))

    summary = build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=True)

    assert summary["source_classifications"] == {"dc_ticker_swing_signal_daily": "DERIVED_FROM_RAW_SOURCE"}
    assert summary["selected_ticker_entity_count"] == 3
    assert summary["window_count"] == 4
    assert summary["source_rows_read"] == 2
    assert summary["source_rows_mapped"] == 2
    assert summary["source_rows_skipped"] == 0
    assert summary["missing_source_tickers"] == ["CRGY"]
    assert summary["metric_rows_inserted"] == 25
    assert summary["signal_observations_inserted"] == 20
    assert summary["metric_name_counts"] == {
        "freshness_latest_bos_age_trading_days": 2,
        "freshness_latest_bos_class": 8,
        "freshness_latest_reset_age_trading_days": 1,
        "freshness_latest_reset_class": 4,
        "freshness_latest_structure_age_trading_days": 2,
        "freshness_latest_structure_class": 8,
    }
    assert summary["signal_name_counts"] == {
        "BOS_FRESHNESS": 8,
        "RESET_FRESHNESS": 4,
        "STRUCTURE_FRESHNESS": 8,
    }
    assert summary["freshness_class_counts"] == {
        "AGING": 8,
        "FRESH": 8,
        "STALE": 4,
    }
    assert summary["rows_deleted_on_replace"] == 0
    assert "replaces ticker freshness only" in summary["limitations"]
    assert "group freshness rows are preserved" in summary["limitations"]
    assert "source is dc_ticker_swing_signal_daily, not dc_report_context_*_v2" in summary["limitations"]
    assert "metric source_table lineage is unavailable because eco_entity_metric_value has no source_table column" in summary["limitations"]
    assert "no relevance rows are created" in summary["limitations"]
    assert "no event rows are created" in summary["limitations"]
    assert "no OVERALL_FRESHNESS rows are created" in summary["limitations"]

    conn = _connect(str(db_path))
    try:
        ticker_metric_counts = conn.execute(
            """
            SELECT metric_name, window_code, COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE e.entity_type = 'TICKER'
              AND m.metric_name LIKE 'freshness_%'
            GROUP BY metric_name, window_code
            ORDER BY metric_name, window_code
            """
        ).fetchall()
        assert [tuple(row) for row in ticker_metric_counts] == [
            ("freshness_latest_bos_age_trading_days", "daily", 2),
            ("freshness_latest_bos_class", "daily", 2),
            ("freshness_latest_bos_class", "rolling2", 2),
            ("freshness_latest_bos_class", "rolling30", 2),
            ("freshness_latest_bos_class", "rolling5", 2),
            ("freshness_latest_reset_age_trading_days", "daily", 1),
            ("freshness_latest_reset_class", "daily", 1),
            ("freshness_latest_reset_class", "rolling2", 1),
            ("freshness_latest_reset_class", "rolling30", 1),
            ("freshness_latest_reset_class", "rolling5", 1),
            ("freshness_latest_structure_age_trading_days", "daily", 2),
            ("freshness_latest_structure_class", "daily", 2),
            ("freshness_latest_structure_class", "rolling2", 2),
            ("freshness_latest_structure_class", "rolling30", 2),
            ("freshness_latest_structure_class", "rolling5", 2),
        ]

        ticker_signal_counts = conn.execute(
            """
            SELECT signal_name, window_code, COUNT(*)
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE e.entity_type = 'TICKER'
              AND o.signal_family = 'FRESHNESS'
            GROUP BY signal_name, window_code
            ORDER BY signal_name, window_code
            """
        ).fetchall()
        assert [tuple(row) for row in ticker_signal_counts] == [
            ("BOS_FRESHNESS", "daily", 2),
            ("BOS_FRESHNESS", "rolling2", 2),
            ("BOS_FRESHNESS", "rolling30", 2),
            ("BOS_FRESHNESS", "rolling5", 2),
            ("RESET_FRESHNESS", "daily", 1),
            ("RESET_FRESHNESS", "rolling2", 1),
            ("RESET_FRESHNESS", "rolling30", 1),
            ("RESET_FRESHNESS", "rolling5", 1),
            ("STRUCTURE_FRESHNESS", "daily", 2),
            ("STRUCTURE_FRESHNESS", "rolling2", 2),
            ("STRUCTURE_FRESHNESS", "rolling30", 2),
            ("STRUCTURE_FRESHNESS", "rolling5", 2),
        ]

        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE e.entity_type IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM')
              AND m.metric_name IN (
                'freshness_latest_structure_age_trading_days',
                'freshness_latest_bos_age_trading_days',
                'freshness_latest_reset_age_trading_days',
                'freshness_latest_structure_class',
                'freshness_latest_bos_class',
                'freshness_latest_reset_class'
              )
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE e.entity_type IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM')
              AND o.signal_family = 'FRESHNESS'
            """
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 13
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value
            WHERE metric_name = 'distance_to_ema20_pct'
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation
            WHERE signal_family = 'MA_STATUS'
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation
            WHERE signal_family = 'FRESHNESS'
              AND signal_name = 'OVERALL_FRESHNESS'
            """
        ).fetchone()[0] == 0

        sample_signal = conn.execute(
            """
            SELECT source_event_id, source_table, source_run_id
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE e.entity_code = 'NVDA'
              AND o.window_code = 'rolling5'
              AND o.signal_name = 'STRUCTURE_FRESHNESS'
            """
        ).fetchone()
        assert dict(sample_signal) == {
            "source_event_id": "ticker_freshness:NVDA:2026-05-29:rolling5:STRUCTURE_FRESHNESS",
            "source_table": "dc_ticker_swing_signal_daily",
            "source_run_id": SOURCE_RUN_ID,
        }
    finally:
        conn.close()


def test_replace_existing_replaces_only_ticker_scope_and_is_idempotent(tmp_path):
    db_path = tmp_path / "freshness_replace_idempotent.db"
    ids = _seed_db(str(db_path))
    conn = _connect(str(db_path))
    try:
        _insert_existing_ticker_replacement_rows(
            conn,
            ecosystem_id=ids["ecosystem_id"],
            taxonomy_version_id=ids["taxonomy_version_id"],
            ticker_entity_id=ids["nvda_entity_id"],
            ticker="NVDA",
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="Ticker freshness replacement rows already exist"):
        build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=False)

    summary = build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=True)
    assert summary["rows_deleted_on_replace"] == 8

    second_summary = build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=True)
    assert second_summary["rows_deleted_on_replace"] == 45
    assert second_summary["metric_rows_inserted"] == 25
    assert second_summary["signal_observations_inserted"] == 20

    conn = _connect(str(db_path))
    try:
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE e.entity_type = 'TICKER'
              AND m.metric_name IN (
                'freshness_latest_structure_age_trading_days',
                'freshness_latest_bos_age_trading_days',
                'freshness_latest_reset_age_trading_days',
                'freshness_latest_structure_class',
                'freshness_latest_bos_class',
                'freshness_latest_reset_class'
              )
            """
        ).fetchone()[0] == 25
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE e.entity_type = 'TICKER'
              AND o.signal_family = 'FRESHNESS'
              AND o.signal_name IN ('STRUCTURE_FRESHNESS', 'BOS_FRESHNESS', 'RESET_FRESHNESS')
            """
        ).fetchone()[0] == 20
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT run_id, signal_date, taxonomy_version_id, window_code, entity_id, metric_name, COUNT(*) AS n
                FROM eco_entity_metric_value
                WHERE metric_name IN (
                    'freshness_latest_structure_age_trading_days',
                    'freshness_latest_bos_age_trading_days',
                    'freshness_latest_reset_age_trading_days',
                    'freshness_latest_structure_class',
                    'freshness_latest_bos_class',
                    'freshness_latest_reset_class'
                )
                GROUP BY run_id, signal_date, taxonomy_version_id, window_code, entity_id, metric_name
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0] == 0
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT run_id, signal_date, taxonomy_version_id, window_code, entity_id, signal_name, observed_date, COUNT(*) AS n
                FROM eco_signal_observation
                WHERE signal_family = 'FRESHNESS'
                  AND signal_name IN ('STRUCTURE_FRESHNESS', 'BOS_FRESHNESS', 'RESET_FRESHNESS')
                GROUP BY run_id, signal_date, taxonomy_version_id, window_code, entity_id, signal_name, observed_date
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0] == 0
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_metric_value
            WHERE source_run_id = 'GROUP_SOURCE_V1'
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation
            WHERE source_run_id = 'GROUP_SOURCE_V1'
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation
            WHERE signal_family = 'MA_STATUS'
            """
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_replace_existing_blocks_when_relevance_exists(tmp_path):
    db_path = tmp_path / "freshness_replace_relevance.db"
    ids = _seed_db(str(db_path))
    build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=True)

    conn = _connect(str(db_path))
    try:
        observation_id = conn.execute(
            """
            SELECT o.signal_observation_id
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE e.entity_type = 'TICKER'
              AND o.signal_family = 'FRESHNESS'
              AND o.signal_name = 'STRUCTURE_FRESHNESS'
            LIMIT 1
            """
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO eco_signal_relevance (
                signal_observation_id,
                relevance_label,
                relevance_score,
                relevance_reason
            ) VALUES (?, ?, ?, ?)
            """,
            (observation_id, "RELEVANT", 1.0, "test"),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="relevance rows point to replacement-scope TICKER FRESHNESS observations"):
        build_canonical_v3_ticker_freshness_from_signal_daily(str(db_path), RUN_ID, replace_existing=True)
