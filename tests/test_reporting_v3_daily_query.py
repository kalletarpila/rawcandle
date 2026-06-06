import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.reporting_v3_query import build_daily_report_query_data


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
WINDOW_CODE = "daily"


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
            ) VALUES (?, 'DC_TAXONOMY_FULL_V1', 'Datacenter Full', 1, 'ACTIVE')
            """,
            (ecosystem_id,),
        ).lastrowid
    )


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    *,
    entity_type: str,
    entity_code: str,
    entity_name: str,
    ticker: str | None = None,
) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, status
            ) VALUES (?, ?, ?, ?, ?, 'ACTIVE')
            """,
            (ecosystem_id, entity_type, entity_code, entity_name, ticker),
        ).lastrowid
    )


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
        ) VALUES (?, ?, ?, ?, 'BUILD', 'OK_WITH_WARNINGS', 1, 0)
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, SIGNAL_DATE),
    )


def _insert_relation(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    ecosystem_id: int,
    parent_entity_id: int,
    child_entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_taxonomy_entity_relation (
            taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id, relation_type, is_primary, status
        ) VALUES (?, ?, ?, ?, 'CONTAINS', 1, 'ACTIVE')
        """,
        (taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id),
    )


def _insert_watchlist(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_watchlist (
                ecosystem_id, watchlist_code, watchlist_name, status
            ) VALUES (?, 'PRIMARY', 'Primary', 'ACTIVE')
            """,
            (ecosystem_id,),
        ).lastrowid
    )


def _insert_watchlist_member(conn: sqlite3.Connection, watchlist_id: int, entity_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_watchlist_member (
            watchlist_id, entity_id, member_role, member_status, effective_from
        ) VALUES (?, ?, 'CORE', 'ACTIVE', ?)
        """,
        (watchlist_id, entity_id, SIGNAL_DATE),
    )


def _insert_coverage(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    coverage_status: str = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_coverage (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
            coverage_status, source_row_count, missing_component_count
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1, 1, 1, 1, ?, 1, 0)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, WINDOW_CODE, entity_id, coverage_status),
    )


def _insert_quality_summary(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    scope_entity_id: int,
    quality_scope: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
            scope_entity_id, quality_status, expected_count, actual_count, missing_count, warning_count, error_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'WARN', 3, 3, 0, 1, 0)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, WINDOW_CODE, quality_scope, scope_entity_id),
    )


def _insert_snapshot(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    snapshot_status: str = "OK",
    timing_state: str | None = None,
    trend_state: str | None = None,
    summary_state: str | None = None,
    classification_state: str | None = None,
    freshness_status: str | None = None,
    quality_status: str | None = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            snapshot_status, timing_state, trend_state, summary_state, classification_state,
            freshness_status, quality_status, asof_observed_at, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SNAPSHOT_SOURCE')
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            WINDOW_CODE,
            entity_id,
            snapshot_status,
            timing_state,
            trend_state,
            summary_state,
            classification_state,
            freshness_status,
            quality_status,
            SIGNAL_DATE,
        ),
    )


def _insert_classification(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    classification_state: str,
    primary_reason: str | None = None,
    blocking_reason: str | None = None,
    risk_reason: str | None = None,
    next_action: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, classification_state, primary_reason, blocking_reason, risk_reason,
            next_action, source_classifier, classification_version, source_run_id, decision_status
        ) VALUES (?, ?, ?, ?, ?, ?, 'daily_trigger', ?, ?, ?, ?, ?, 'daily_query_test', 'V1', 'CLASS_SOURCE', 'OK')
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            WINDOW_CODE,
            entity_id,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
        ),
    )


def _insert_metric_num(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    metric_name: str,
    metric_value_num: float,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'OK', 'METRIC_SOURCE')
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            WINDOW_CODE,
            entity_id,
            metric_name,
            metric_value_num,
        ),
    )


def _insert_metric_text(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    metric_name: str,
    metric_value_text: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, 'OK', 'METRIC_SOURCE')
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            WINDOW_CODE,
            entity_id,
            metric_name,
            metric_value_text,
        ),
    )


def _insert_event(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    event_date: str,
    event_type: str,
    event_key: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type,
            source_run_id, source_event_id, event_key, event_label, event_direction, event_status
        ) VALUES (?, ?, ?, ?, ?, ?, 'EVENT_SOURCE', ?, ?, ?, 'DOWN', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type, event_key, event_key, event_type),
    )


def _insert_signal(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    signal_name: str,
    signal_family: str,
    signal_value: str,
    signal_direction: str = "DOWN",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'eco_signal_source', 'SIG_SOURCE', 'SIG-1', 'ACTIVE')
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            WINDOW_CODE,
            entity_id,
            signal_name,
            signal_family,
            signal_direction,
            signal_value,
            SIGNAL_DATE,
        ),
    )
    return int(cursor.lastrowid)


def _insert_relevance(conn: sqlite3.Connection, signal_observation_id: int, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id, relevance_label, relevance_score, relevance_reason
        ) VALUES (?, 'CONTEXTUAL', 1.0, ?)
        """,
        (signal_observation_id, reason),
    )


def _build_fixture_db(db_path: str) -> None:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_run(conn, ecosystem_id, taxonomy_version_id)

        ecosystem_entity_id = _insert_entity(conn, ecosystem_id, entity_type="ECOSYSTEM", entity_code="DATACENTER", entity_name="Datacenter")
        layer_id = _insert_entity(conn, ecosystem_id, entity_type="LAYER", entity_code="INFRA", entity_name="Infrastructure")
        subindustry_id = _insert_entity(conn, ecosystem_id, entity_type="SUBINDUSTRY", entity_code="SEMIS", entity_name="Semis")
        crgy_id = _insert_entity(conn, ecosystem_id, entity_type="TICKER", entity_code="CRGY", entity_name="CRGY", ticker="CRGY")
        nvda_id = _insert_entity(conn, ecosystem_id, entity_type="TICKER", entity_code="NVDA", entity_name="NVIDIA", ticker="NVDA")
        nxpi_id = _insert_entity(conn, ecosystem_id, entity_type="TICKER", entity_code="NXPI", entity_name="NXP Semiconductors", ticker="NXPI")

        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=ecosystem_entity_id, child_entity_id=layer_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=layer_id, child_entity_id=subindustry_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=subindustry_id, child_entity_id=crgy_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=subindustry_id, child_entity_id=nvda_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=subindustry_id, child_entity_id=nxpi_id)

        watchlist_id = _insert_watchlist(conn, ecosystem_id)
        _insert_watchlist_member(conn, watchlist_id, nvda_id)
        _insert_watchlist_member(conn, watchlist_id, nxpi_id)

        for entity_id, coverage_status in (
            (ecosystem_entity_id, "OK"),
            (layer_id, "OK"),
            (subindustry_id, "OK"),
            (crgy_id, "OK"),
            (nvda_id, "OK"),
            (nxpi_id, "OK"),
        ):
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                coverage_status=coverage_status,
            )

        _insert_quality_summary(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, scope_entity_id=ecosystem_entity_id, quality_scope="RUN")
        _insert_quality_summary(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, scope_entity_id=ecosystem_entity_id, quality_scope="WINDOW")

        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=ecosystem_entity_id, timing_state="BUY_ZONE", trend_state="UP", summary_state="HEALTHY", freshness_status="FRESH")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, timing_state="BUY_ZONE", trend_state="UP", summary_state="STRONG", freshness_status="FRESH")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=subindustry_id, timing_state="EXIT_WATCH", trend_state="DOWN", summary_state="MIXED", freshness_status="AGING", quality_status="WARN")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=crgy_id, snapshot_status="WARN", trend_state="DOWN", summary_state="MISSING_DATA", classification_state="WRONG_FROM_SNAPSHOT", quality_status="WARN")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, trend_state="UP", summary_state="READY", classification_state="WRONG_FROM_SNAPSHOT", quality_status="OK")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nxpi_id, trend_state="DOWN", summary_state="SELL_SIGNAL", classification_state="WRONG_FROM_SNAPSHOT", quality_status="OK")

        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=nvda_id,
            classification_state="BUY_WATCH",
            primary_reason="BULLISH_SETUP_NEEDS_CONFIRMATION",
            next_action="MONITOR_FOR_DAILY_CONFIRMATION",
        )
        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=crgy_id,
            classification_state="INSUFFICIENT_DATA",
            primary_reason="MISSING_PRICE_CONTEXT",
            next_action="WAIT_FOR_DATA",
        )
        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=nxpi_id,
            classification_state="SELL_TRIGGER",
            primary_reason="DAILY_SELL_TRIGGER",
            blocking_reason="BEARISH_DAILY_SIGNAL",
            next_action="REVIEW_SELL_OR_TIGHTEN_STOP",
        )

        for entity_id, base in ((nvda_id, 1.0), (nxpi_id, -1.0)):
            for metric_name, metric_value in (
                ("distance_to_ema10_pct", base),
                ("distance_to_ema20_pct", base + 0.5),
                ("return_5d", base + 2.0),
                ("return_10d", base + 3.0),
                ("return_20d", base + 4.0),
                ("return_60d", base + 5.0),
                ("latest_bos_age_trading_days", 2.0),
                ("latest_reset_age_trading_days", 4.0),
                ("latest_structure_age_trading_days", 6.0),
                ("freshness_latest_bos_age_trading_days", 1.0),
                ("freshness_latest_reset_age_trading_days", 3.0),
                ("freshness_latest_structure_age_trading_days", 5.0),
            ):
                _insert_metric_num(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=entity_id, metric_name=metric_name, metric_value_num=metric_value)
            for metric_name, metric_value in (
                ("freshness_latest_bos_class", "FRESH"),
                ("freshness_latest_reset_class", "AGING"),
                ("freshness_latest_structure_class", "STALE"),
            ):
                _insert_metric_text(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=entity_id, metric_name=metric_name, metric_value_text=metric_value)

        for metric_name, metric_value in (
            ("pct_above_ema20", 62.5),
            ("return_5d", 4.0),
            ("synthetic_close", 101.0),
            ("trend_breadth", 70.0),
            ("weakness_breadth", 30.0),
            ("freshness_latest_bos_age_trading_days", 1.0),
            ("freshness_latest_reset_age_trading_days", 2.0),
            ("freshness_latest_structure_age_trading_days", 3.0),
        ):
            _insert_metric_num(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, metric_name=metric_name, metric_value_num=metric_value)
        for metric_name, metric_value in (
            ("group_current_status", "BUY_ZONE"),
            ("group_timing_state", "BUY_ZONE"),
            ("group_timing_reason", "BUY_ZONE:return_5d_pos"),
            ("group_overheat_risk_level", "LOW"),
            ("freshness_latest_bos_class", "FRESH"),
            ("freshness_latest_reset_class", "AGING"),
            ("freshness_latest_structure_class", "STALE"),
        ):
            _insert_metric_text(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, metric_name=metric_name, metric_value_text=metric_value)

        _insert_event(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, event_date=SIGNAL_DATE, event_type="BOS", event_key="nvda-bos")
        _insert_event(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nxpi_id, event_date=SIGNAL_DATE, event_type="STRUCTURE_CHANGE", event_key="nxpi-structure")
        freshness_signal_id = _insert_signal(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, signal_name="RESET_FRESHNESS", signal_family="FRESHNESS", signal_value="FRESH")
        pullback_signal_id = _insert_signal(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, signal_name="REVERSAL_MEDIUM", signal_family="REVERSAL_MEDIUM", signal_value="BULLISH", signal_direction="UP")
        divergence_signal_id = _insert_signal(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nxpi_id, signal_name="REVERSAL_MEDIUM", signal_family="REVERSAL_MEDIUM", signal_value="BEARISH")
        _insert_relevance(conn, freshness_signal_id, "daily freshness")
        _insert_relevance(conn, pullback_signal_id, "daily pullback")
        _insert_relevance(conn, divergence_signal_id, "daily reversal")
        conn.commit()
    finally:
        conn.close()


def test_query_requires_existing_run_id(tmp_path) -> None:
    db_path = tmp_path / "daily_query_missing_run.db"
    _build_fixture_db(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_daily_report_query_data(str(db_path), "missing-run")


def test_query_returns_daily_structured_data_from_eco_facts(tmp_path) -> None:
    db_path = tmp_path / "daily_query.db"
    _build_fixture_db(str(db_path))

    data = build_daily_report_query_data(str(db_path), RUN_ID)

    assert data.report_header.run_id == RUN_ID
    assert data.report_header.ecosystem_code == "DATACENTER"
    assert data.report_header.taxonomy_version_code == "DC_TAXONOMY_FULL_V1"
    assert data.report_header.signal_date == SIGNAL_DATE
    assert data.report_header.window_code == WINDOW_CODE

    assert data.ecosystem_snapshot is not None
    assert data.ecosystem_snapshot["entity_code"] == "DATACENTER"
    assert [row["entity_type"] for row in data.group_snapshots] == ["LAYER", "SUBINDUSTRY"]
    assert [row["entity_code"] for row in data.ticker_snapshots] == ["CRGY", "NVDA", "NXPI"]

    assert [row["ticker"] for row in data.daily_trigger_classifications] == ["NVDA", "NXPI", "CRGY"]
    assert data.daily_trigger_classifications[0]["classification_state"] == "BUY_WATCH"
    assert data.daily_trigger_classifications[1]["classification_state"] == "SELL_TRIGGER"
    assert data.daily_trigger_classifications[1]["primary_reason"] == "DAILY_SELL_TRIGGER"
    assert data.daily_trigger_classifications[1]["blocking_reason"] == "BEARISH_DAILY_SIGNAL"
    assert data.daily_trigger_classifications[1]["next_action"] == "REVIEW_SELL_OR_TIGHTEN_STOP"
    assert data.daily_trigger_classifications[2]["classification_state"] == "INSUFFICIENT_DATA"
    assert data.daily_trigger_classifications[2]["primary_reason"] == "MISSING_PRICE_CONTEXT"
    assert data.daily_trigger_classifications[2]["next_action"] == "WAIT_FOR_DATA"

    assert data.ticker_snapshots[2]["classification_state"] == "WRONG_FROM_SNAPSHOT"
    assert data.daily_trigger_classifications[1]["classification_state"] != data.ticker_snapshots[2]["classification_state"]

    assert data.ticker_metrics["NVDA"]["distance_to_ema10_pct"] == 1.0
    assert data.ticker_metrics["NVDA"]["freshness_latest_bos_class"] == "FRESH"
    assert data.group_metrics[0]["entity_code"] == "INFRA"
    assert data.group_metrics[0]["group_current_status"] == "BUY_ZONE"
    assert data.group_metrics[0]["freshness_latest_structure_class"] == "STALE"
    assert data.watchlist_summary["counts"]["active_watchlist_count"] == 2
    assert data.watchlist_summary["counts"]["in_ecosystem_count"] == 2
    assert data.watchlist_summary["counts"]["missing_price_data_count"] == 0
    assert data.watchlist_summary["counts"]["breakout_count"] == 1
    assert data.watchlist_summary["counts"]["pullback_count"] == 0
    assert data.watchlist_summary["counts"]["exit_risk_count"] == 1
    assert data.watchlist_summary["counts"]["high_exit_risk_count"] == 1
    assert data.watchlist_summary["counts"]["medium_exit_risk_count"] == 0
    assert [row["ticker"] for row in data.watchlist_summary["rows"]] == ["NXPI", "NVDA"]
    assert data.watchlist_summary["rows"][0]["watchlist_status"] == "HIGH_EXIT_RISK"
    assert data.watchlist_summary["rows"][0]["exit_risk_signal"] is True
    assert data.watchlist_summary["rows"][0]["primary_layer"] == "INFRA"
    assert data.watchlist_summary["rows"][0]["primary_subindustry"] == "SEMIS"
    assert data.watchlist_summary["rows"][1]["watchlist_status"] == "BREAKOUT"
    assert data.watchlist_summary["rows"][1]["breakout_signal"] is True
    assert data.watchlist_summary["rows"][1]["pullback_signal"] is None

    assert len(data.watchlist_members) == 2
    assert [row["ticker"] for row in data.watchlist_members] == ["NVDA", "NXPI"]

    assert [row["event_type"] for row in data.structural_events] == ["BOS", "STRUCTURE_CHANGE"]
    assert [row["signal_name"] for row in data.signal_observations] == ["RESET_FRESHNESS", "REVERSAL_MEDIUM", "REVERSAL_MEDIUM"]
    bullish_reversal_row = next(
        row
        for row in data.signal_observations
        if row["entity_code"] == "NVDA" and row["signal_name"] == "REVERSAL_MEDIUM"
    )
    assert bullish_reversal_row["signal_direction"] == "UP"
    assert bullish_reversal_row["signal_value"] == "BULLISH"
    assert bullish_reversal_row["relevance_labels"] == "CONTEXTUAL"

    assert set(data.ticker_scanners) == {
        "breakout_rows",
        "pullback_rows",
        "exit_risk_rows",
        "breakout_rows_available",
        "pullback_rows_available",
        "exit_risk_rows_available",
        "breakout_rows_rendered",
        "pullback_rows_rendered",
        "exit_risk_rows_rendered",
        "is_breakout_truncated",
        "is_pullback_truncated",
        "is_exit_risk_truncated",
    }
    assert [row["ticker"] for row in data.ticker_scanners["breakout_rows"]] == ["NVDA"]
    assert data.ticker_scanners["breakout_rows"][0]["scanner_type"] == "breakout"
    assert data.ticker_scanners["breakout_rows"][0]["signal_value"] == "BUY_WATCH"
    assert data.ticker_scanners["breakout_rows"][0]["signal_strength"] is None
    assert data.ticker_scanners["breakout_rows"][0]["primary_layer"] == "INFRA"
    assert data.ticker_scanners["breakout_rows"][0]["primary_subindustry"] == "SEMIS"

    assert [row["ticker"] for row in data.ticker_scanners["pullback_rows"]] == ["NVDA"]
    assert data.ticker_scanners["pullback_rows"][0]["scanner_type"] == "pullback"
    assert data.ticker_scanners["pullback_rows"][0]["signal_value"] == "BULLISH"
    assert data.ticker_scanners["pullback_rows"][0]["signal_strength"] == "REVERSAL_MEDIUM"
    assert data.ticker_scanners["pullback_rows"][0]["distance_to_ema20_pct"] == 1.5
    assert data.ticker_scanners["pullback_rows"][0]["exit_reason"] is None

    assert [row["ticker"] for row in data.ticker_scanners["exit_risk_rows"]] == ["NXPI"]
    assert data.ticker_scanners["exit_risk_rows"][0]["scanner_type"] == "exit_risk"
    assert data.ticker_scanners["exit_risk_rows"][0]["signal_value"] == "SELL_TRIGGER"
    assert data.ticker_scanners["exit_risk_rows"][0]["exit_risk_severity"] == "HIGH"
    assert data.ticker_scanners["exit_risk_rows"][0]["exit_reason"] == "BEARISH_DAILY_SIGNAL"
    assert data.ticker_scanners["breakout_rows_available"] == 1
    assert data.ticker_scanners["pullback_rows_available"] == 1
    assert data.ticker_scanners["exit_risk_rows_available"] == 1
    assert data.ticker_scanners["is_breakout_truncated"] is False
    assert data.ticker_scanners["is_pullback_truncated"] is False
    assert data.ticker_scanners["is_exit_risk_truncated"] is False

    coverage_counts = {(row["entity_type"], row["coverage_status"]): row["row_count"] for row in data.quality_summary["coverage_counts"]}
    assert coverage_counts[("TICKER", "OK")] == 3

    assert data.metadata["used_v2_runtime_tables"] is False
    assert data.metadata["used_generated_reports"] is False
    assert data.metadata["used_dashboard_output"] is False
    assert data.metadata["daily_classification_source"] == "eco_classification_decision"
    assert data.metadata["daily_snapshot_classification_source_used"] is False
    assert data.metadata["daily_signal_scope"] == "daily_signal_observation_and_optional_relevance"
    assert data.metadata["daily_event_window_mode"] == "event_date_range_signal_day_only"
    assert data.metadata["ranking_fields_mostly_null"] is True
    assert "CRGY is intentionally materialized as INSUFFICIENT_DATA in daily_trigger" in data.metadata["limitations"]
    assert "NXPI reflects accepted current lower-level source-truth SELL_TRIGGER semantics" in data.metadata["limitations"]
    assert (
        "eco_entity_window_snapshot.classification_state is not used as the primary daily classification source"
        in data.metadata["limitations"]
    )
