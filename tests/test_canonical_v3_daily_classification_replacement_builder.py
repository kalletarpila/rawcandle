import sqlite3

import pytest

from analysis.datacenter_indices.daily_trigger_classifier import classify_daily_trigger_row
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_daily_classification_replacement_builder import (
    build_canonical_v3_daily_trigger_classifications,
)
import rawcandle.report_canonical_v3_daily_classification_replacement_builder as builder_module


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
OLD_SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"


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


def _insert_ticker_entity(conn: sqlite3.Connection, ecosystem_id: int, ticker: str) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, status
            ) VALUES (?, 'TICKER', ?, ?, ?, 'ACTIVE')
            """,
            (ecosystem_id, ticker, ticker, ticker),
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


def _create_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            primary_layer TEXT,
            primary_subindustry TEXT,
            close REAL,
            distance_to_ema10_pct REAL,
            distance_to_ema20_pct REAL,
            latest_structure_label TEXT,
            breakout_signal INTEGER,
            pullback_signal INTEGER,
            exit_risk_signal INTEGER,
            exit_risk_severity TEXT,
            exit_reason TEXT,
            bullish_candle_signal INTEGER,
            bullish_divergence_signal INTEGER,
            hidden_bullish_divergence_signal INTEGER,
            bearish_candle_signal INTEGER,
            bearish_divergence_signal INTEGER,
            hidden_bearish_divergence_signal INTEGER,
            price_data_status TEXT,
            latest_bos_event_type TEXT,
            latest_bos_freshness TEXT,
            latest_reset_reason TEXT,
            latest_reset_freshness TEXT,
            ticker_trend_state TEXT,
            signal_version TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            timing_state TEXT,
            overheat_risk_level TEXT,
            signal_version TEXT NOT NULL,
            run_id TEXT NOT NULL
        )
        """
    )


def _insert_ticker_source_rows(conn: sqlite3.Connection) -> None:
    rows = [
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "AAA",
            "LAYER_A",
            "SUB_A",
            100.0,
            -0.04,
            -0.06,
            "LL",
            0,
            0,
            1,
            "HIGH",
            "close_below_ema20;return_10d_lt_minus_8pct",
            0,
            0,
            0,
            0,
            0,
            0,
            "OK",
            "BOS_DOWN",
            "FRESH",
            "DOUBLE_BOS_DOWN",
            "FRESH",
            "DOWN",
            "DC_SWING_SIGNAL_V1",
            "DC_TICKER_SWING_RUN",
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "BBB",
            "LAYER_B",
            "SUB_B",
            50.0,
            0.01,
            0.02,
            "HL",
            0,
            1,
            0,
            "",
            "",
            0,
            0,
            0,
            0,
            0,
            0,
            "OK",
            "BOS_UP",
            "AGING",
            "DOUBLE_BOS_UP",
            "AGING",
            "UP",
            "DC_SWING_SIGNAL_V1",
            "DC_TICKER_SWING_RUN",
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "CCC",
            "LAYER_C",
            "SUB_C",
            80.0,
            0.08,
            0.09,
            "HL",
            0,
            0,
            0,
            "",
            "",
            0,
            0,
            0,
            0,
            0,
            0,
            "OK",
            "BOS_UP",
            "AGING",
            "DOUBLE_BOS_UP",
            "AGING",
            "NEUTRAL",
            "DC_SWING_SIGNAL_V1",
            "DC_TICKER_SWING_RUN",
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "NXPI",
            "LAYER_N",
            "SUB_N",
            321.35,
            0.0203,
            0.0717,
            "HL",
            0,
            0,
            0,
            "",
            "",
            0,
            0,
            0,
            0,
            1,
            0,
            "OK",
            "BOS_UP",
            "AGING",
            "DOUBLE_BOS_UP",
            "AGING",
            "NEUTRAL",
            "DC_SWING_SIGNAL_V1",
            "DC_TICKER_SWING_RUN",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry, close,
            distance_to_ema10_pct, distance_to_ema20_pct, latest_structure_label, breakout_signal,
            pullback_signal, exit_risk_signal, exit_risk_severity, exit_reason,
            bullish_candle_signal, bullish_divergence_signal, hidden_bullish_divergence_signal,
            bearish_candle_signal, bearish_divergence_signal, hidden_bearish_divergence_signal,
            price_data_status, latest_bos_event_type, latest_bos_freshness, latest_reset_reason,
            latest_reset_freshness, ticker_trend_state, signal_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_group_rows(conn: sqlite3.Connection) -> None:
    rows = [
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_A", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_A", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_B", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_B", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_C", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_C", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "layer", "LAYER_N", "BUY_ZONE", "LOW"),
        (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1", "subindustry", "SUB_N", "BUY_ZONE", "LOW"),
    ]
    conn.executemany(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, group_type, group_name, timing_state,
            overheat_risk_level, signal_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, 'DC_SWING_SIGNAL_V1', 'DC_GROUP_SWING_RUN')
        """,
        rows,
    )


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
    classification_type: str,
    classification_state: str,
    primary_reason: str,
    blocking_reason: str | None,
    risk_reason: str | None,
    next_action: str | None,
    source_classifier: str,
    classification_version: str,
    source_run_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, classification_state, primary_reason, blocking_reason,
            risk_reason, next_action, priority_score, priority_label, sort_rank,
            source_classifier, classification_version, source_run_id, decision_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, 'OK')
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            entity_id,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            source_classifier,
            classification_version,
            source_run_id,
        ),
    )


def _insert_preservation_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    daily_ids: dict[str, int],
) -> None:
    for ticker in daily_ids:
        _insert_classification_row(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=daily_ids[ticker],
            window_code="daily",
            classification_type="daily_trigger",
            classification_state="NO_TRIGGER",
            primary_reason="STALE_V2_ROW",
            blocking_reason=None,
            risk_reason=None,
            next_action="NONE",
            source_classifier="daily_trigger",
            classification_version="REPORT_CANONICAL_CLASSIFICATION_V2_1",
            source_run_id=OLD_SOURCE_RUN_ID,
        )

    _insert_classification_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling2",
        classification_type="rolling2_sell_pressure",
        classification_state="NO_EMERGENCY",
        primary_reason="NO_TWO_DAY_SELL_PRESSURE",
        blocking_reason=None,
        risk_reason=None,
        next_action="NONE",
        source_classifier="rolling2_sell_pressure_classifier",
        classification_version="V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1",
        source_run_id="V3_ROLLING2_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29",
    )
    _insert_classification_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling5",
        classification_type="rolling5_pullback",
        classification_state="NO_PULLBACK",
        primary_reason="NO_MEANINGFUL_PULLBACK_EVIDENCE",
        blocking_reason=None,
        risk_reason=None,
        next_action="NONE",
        source_classifier="rolling5_pullback_classifier",
        classification_version="V3_ROLLING5_PULLBACK_CLASSIFIER_V1",
        source_run_id="V3_ROLLING5_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29",
    )
    _insert_classification_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling30",
        classification_type="rolling30_buy",
        classification_state="WATCH_ZONE",
        primary_reason="BUY_BLOCKED_BY_CONTEXT",
        blocking_reason="CURRENT_HIGH_EXIT_RISK",
        risk_reason=None,
        next_action=None,
        source_classifier="rolling30_watchlist_classifier",
        classification_version="V3_ROLLING30_WATCHLIST_CLASSIFIER_V1",
        source_run_id="V3_ROLLING30_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29",
    )
    _insert_classification_row(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling30",
        classification_type="rolling30_exit",
        classification_state="WATCH",
        primary_reason="MILD_OR_UNCONFIRMED_EXIT_RISK",
        blocking_reason=None,
        risk_reason="CURRENT_HIGH_EXIT_RISK",
        next_action=None,
        source_classifier="rolling30_watchlist_classifier",
        classification_version="V3_ROLLING30_WATCHLIST_CLASSIFIER_V1",
        source_run_id="V3_ROLLING30_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29",
    )


def _insert_non_classification_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            snapshot_status, timing_state, trend_state, summary_state, classification_state,
            freshness_status, quality_status, asof_observed_at, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'OK', 'NEUTRAL', 'UP', 'OK', 'NO_TRIGGER', 'FRESH', 'OK', ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id, SIGNAL_DATE, OLD_SOURCE_RUN_ID),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'metric_x', NULL, 'value_x', NULL, 'OK', ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id, OLD_SOURCE_RUN_ID),
    )
    obs = conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'sig_x', 'REVERSAL_MEDIUM', 'BULLISH', '1', ?, 'technical_signal_relevance', ?, 'evt-x', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id, SIGNAL_DATE, OLD_SOURCE_RUN_ID),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id, relevance_label, relevance_score, relevance_reason,
            trend_alignment, dow_context, bos_context, reset_context, counter_trend_context
        ) VALUES (?, 'RELEVANT', 0.8, 'fixture', 'ALIGNED', 'UP', 'NONE', 'NONE', 'NONE')
        """,
        (int(obs.lastrowid),),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type,
            source_table, source_run_id, source_event_id, event_key, event_label,
            event_direction, event_status, event_payload_ref
        ) VALUES (?, ?, ?, ?, ?, 'UNKNOWN', 'fixture_source', ?, 'event-1', 'event-key', 'Fixture Event', 'UP', 'ACTIVE', NULL)
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, entity_id, SIGNAL_DATE, OLD_SOURCE_RUN_ID),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
            scope_entity_id, quality_status, expected_count, actual_count, missing_count,
            incomplete_count, stale_count, warning_count, error_count, summary_note
        ) VALUES (?, ?, ?, ?, 'daily', 'TICKER', ?, 'OK', 1, 1, 0, 0, 0, 0, 0, 'fixture')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )


def _setup_fixture(db_path: str) -> tuple[sqlite3.Connection, int, int, dict[str, int]]:
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    daily_ids = {
        "AAA": _insert_ticker_entity(conn, ecosystem_id, "AAA"),
        "BBB": _insert_ticker_entity(conn, ecosystem_id, "BBB"),
        "CCC": _insert_ticker_entity(conn, ecosystem_id, "CCC"),
        "NXPI": _insert_ticker_entity(conn, ecosystem_id, "NXPI"),
        "MISS": _insert_ticker_entity(conn, ecosystem_id, "MISS"),
    }
    for entity_id in daily_ids.values():
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
            window_code="daily",
        )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling2",
    )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling5",
    )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
        window_code="rolling30",
    )
    _create_source_tables(conn)
    _insert_ticker_source_rows(conn)
    _insert_group_rows(conn)
    _insert_preservation_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        daily_ids=daily_ids,
    )
    _insert_non_classification_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=daily_ids["AAA"],
    )
    conn.commit()
    return conn, ecosystem_id, taxonomy_version_id, daily_ids


def test_extracted_classifier_reflects_nxpi_drift_case() -> None:
    result = classify_daily_trigger_row(
        {
            "ticker": "NXPI",
            "current_watchlist_status": "NEUTRAL_MONITOR",
            "price_data_status": "OK",
            "close": 321.35,
            "trend_state": "NEUTRAL",
            "exit_risk_severity": None,
            "latest_structure_label": "HL",
            "latest_exit_reason": None,
            "latest_bos_event_type": "BOS_UP",
            "latest_bos_freshness": "AGING",
            "latest_reset_reason": "DOUBLE_BOS_UP",
            "latest_reset_freshness": "AGING",
            "pullback_signal": 0,
            "breakout_signal": 0,
            "exit_risk_signal": 0,
            "latest_bullish_relevance_class": None,
            "latest_bearish_relevance_class": None,
            "bullish_candle_signal": 0,
            "bullish_divergence_signal": 0,
            "hidden_bullish_divergence_signal": 0,
            "bearish_candle_signal": 0,
            "bearish_divergence_signal": 1,
            "hidden_bearish_divergence_signal": 0,
            "distance_to_ema10_pct": 0.0203,
            "distance_to_ema20_pct": 0.0717,
            "distance_to_ema50_pct": None,
        }
    )
    assert result == (
        "SELL_TRIGGER",
        "DAILY_SELL_TRIGGER",
        "BEARISH_DAILY_SIGNAL",
        "REVIEW_SELL_OR_TIGHTEN_STOP",
    )


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "daily_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))
    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_daily_trigger_classifications(str(db_path), RUN_ID)


def test_builder_replaces_only_daily_trigger_and_reports_drift_summary(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "daily_replace.db"
    conn, _ecosystem_id, _taxonomy_version_id, daily_ids = _setup_fixture(db_path)
    try:
        before_counts = {
            "snapshot": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
            "metric": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
            "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
            "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
            "signal": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
            "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
            "event": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
            "run": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
        }
        original = builder_module.classify_daily_trigger_row
        call_counter = {"count": 0}

        def wrapped(row: dict[str, object]) -> tuple[str, str, str | None, str | None]:
            call_counter["count"] += 1
            return original(row)

        monkeypatch.setattr(builder_module, "classify_daily_trigger_row", wrapped)

        summary = build_canonical_v3_daily_trigger_classifications(
            str(db_path),
            RUN_ID,
            replace_existing=True,
        )

        assert call_counter["count"] == 5
        assert summary["classification_type"] == "daily_trigger"
        assert summary["window_code"] == "daily"
        assert summary["selected_ticker_entity_count"] == 5
        assert summary["context_rows_built"] == 5
        assert summary["classification_rows_inserted"] == 5
        assert summary["classification_state_counts"] == {
            "STOP_TRIGGER": 1,
            "BUY_WATCH": 1,
            "NO_TRIGGER": 1,
            "SELL_TRIGGER": 1,
            "INSUFFICIENT_DATA": 1,
        }
        assert summary["decision_status_counts"] == {"OK": 5}
        assert summary["field_coverage_counts"] == {
            "primary_reason": 5,
            "blocking_reason": 2,
            "risk_reason": 0,
            "next_action": 5,
            "priority_score": 0,
            "priority_label": 0,
            "sort_rank": 0,
        }
        assert summary["source_dependency_summary"]["runtime_excludes"] == [
            "dc_report_classification_v2",
            "dc_report_context_daily_v2",
        ]
        assert summary["known_source_drift_checks"] == {
            "bearish_divergence_signal_truthy": 1,
            "bullish_divergence_signal_truthy": 0,
            "hidden_bullish_divergence_signal_truthy": 0,
            "hidden_bearish_divergence_signal_truthy": 0,
            "relevance_fields_forced_null": 5,
            "distance_to_ema50_pct_forced_null": 5,
            "rows_without_lower_level_source": 1,
        }
        assert summary["rows_deleted_on_replace"] == 5
        assert summary["warning_count"] == 1
        assert "Missing lower-level ticker row for daily ticker 'MISS'" in summary["warnings"][0]
        assert "replaces only daily_trigger" in summary["limitations"]
        assert "does not use dc_report_classification_v2 as runtime source" in summary["limitations"]
        assert "does not use dc_report_context_daily_v2 as runtime source" in summary["limitations"]
        assert "relevance-class fields are intentionally kept NULL to preserve current production behavior" in summary["limitations"]
        assert "source drift may cause parity deltas versus frozen V2 payload" in summary["limitations"]

        daily_rows = conn.execute(
            """
            SELECT e.entity_code AS ticker, classification_state, primary_reason, blocking_reason,
                   risk_reason, next_action, priority_score, priority_label, sort_rank,
                   source_classifier, classification_version, source_run_id
            FROM eco_classification_decision d
            JOIN eco_entity e ON e.entity_id = d.entity_id
            WHERE d.classification_type = 'daily_trigger'
            ORDER BY e.entity_code
            """
        ).fetchall()
        assert len(daily_rows) == 5
        assert {row["source_classifier"] for row in daily_rows} == {"daily_trigger_classifier"}
        assert {row["classification_version"] for row in daily_rows} == {"V3_DAILY_TRIGGER_CLASSIFIER_V1"}
        assert {row["source_run_id"] for row in daily_rows} == {
            "V3_DAILY_TRIGGER_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29"
        }
        nxpi_row = next(row for row in daily_rows if row["ticker"] == "NXPI")
        assert nxpi_row["classification_state"] == "SELL_TRIGGER"
        assert nxpi_row["primary_reason"] == "DAILY_SELL_TRIGGER"
        assert nxpi_row["blocking_reason"] == "BEARISH_DAILY_SIGNAL"
        assert nxpi_row["next_action"] == "REVIEW_SELL_OR_TIGHTEN_STOP"
        miss_row = next(row for row in daily_rows if row["ticker"] == "MISS")
        assert miss_row["classification_state"] == "INSUFFICIENT_DATA"
        assert miss_row["primary_reason"] == "MISSING_PRICE_CONTEXT"
        assert miss_row["blocking_reason"] is None
        assert miss_row["next_action"] == "WAIT_FOR_DATA"
        for row in daily_rows:
            assert row["risk_reason"] is None
            assert row["priority_score"] is None
            assert row["priority_label"] is None
            assert row["sort_rank"] is None

        preserved_counts = dict(
            conn.execute(
                """
                SELECT classification_type, COUNT(*) AS cnt
                FROM eco_classification_decision
                WHERE classification_type <> 'daily_trigger'
                GROUP BY classification_type
                """
            ).fetchall()
        )
        assert preserved_counts == {
            "rolling2_sell_pressure": 1,
            "rolling5_pullback": 1,
            "rolling30_buy": 1,
            "rolling30_exit": 1,
        }
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_classification_decision
            WHERE classification_type = 'rolling2_sell_pressure'
              AND classification_version = 'V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1'
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_classification_decision
            WHERE classification_type = 'rolling30_buy'
              AND source_run_id = 'V3_ROLLING30_CLASSIFICATION_FROM_LOWER_LEVEL_2026_05_29'
            """
        ).fetchone()[0] == 1

        after_counts = {
            "snapshot": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
            "metric": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
            "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
            "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
            "signal": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
            "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
            "event": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
            "run": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
        }
        assert after_counts == before_counts
        assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 9
    finally:
        conn.close()


def test_builder_replace_existing_false_rejects_existing_rows(tmp_path) -> None:
    db_path = tmp_path / "daily_existing.db"
    conn, _ecosystem_id, _taxonomy_version_id, _daily_ids = _setup_fixture(db_path)
    conn.close()

    with pytest.raises(ValueError, match="already exist"):
        build_canonical_v3_daily_trigger_classifications(
            str(db_path),
            RUN_ID,
            replace_existing=False,
        )


def test_builder_replace_existing_true_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "daily_idempotent.db"
    conn, _ecosystem_id, _taxonomy_version_id, _daily_ids = _setup_fixture(db_path)
    try:
        summary_first = build_canonical_v3_daily_trigger_classifications(
            str(db_path),
            RUN_ID,
            replace_existing=True,
        )
        summary_second = build_canonical_v3_daily_trigger_classifications(
            str(db_path),
            RUN_ID,
            replace_existing=True,
        )

        assert summary_first["classification_rows_inserted"] == 5
        assert summary_second["classification_rows_inserted"] == 5
        assert summary_second["rows_deleted_on_replace"] == 5
        assert conn.execute(
            "SELECT COUNT(*) FROM eco_classification_decision WHERE classification_type = 'daily_trigger'"
        ).fetchone()[0] == 5
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_classification_decision
            WHERE classification_type IN (
                'rolling2_sell_pressure', 'rolling5_pullback', 'rolling30_buy', 'rolling30_exit'
            )
            """
        ).fetchone()[0] == 4
    finally:
        conn.close()
