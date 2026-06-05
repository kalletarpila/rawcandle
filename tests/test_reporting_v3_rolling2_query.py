import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.reporting_v3_query import build_rolling2_report_query_data


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
WINDOW_CODE = "rolling2"


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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'WARN', 2, 2, 0, 1, 0)
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
        ) VALUES (?, ?, ?, ?, ?, ?, 'rolling2_sell_pressure', ?, ?, ?, ?, ?, 'rolling2_query_test', 'V1', 'CLASS_SOURCE', 'OK')
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
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, ?, ?, 'RESET_FRESHNESS', 'FRESHNESS', 'DOWN', 'FRESH', ?, 'eco_signal_source', 'SIG_SOURCE', 'SIG-1', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, WINDOW_CODE, entity_id, SIGNAL_DATE),
    )
    return int(cursor.lastrowid)


def _insert_relevance(conn: sqlite3.Connection, signal_observation_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id, relevance_label, relevance_score, relevance_reason
        ) VALUES (?, 'CONTEXTUAL', 1.0, 'rolling2 freshness only')
        """,
        (signal_observation_id,),
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
        nvda_id = _insert_entity(conn, ecosystem_id, entity_type="TICKER", entity_code="NVDA", entity_name="NVIDIA", ticker="NVDA")
        crgy_id = _insert_entity(conn, ecosystem_id, entity_type="TICKER", entity_code="CRGY", entity_name="CRGY", ticker="CRGY")

        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=ecosystem_entity_id, child_entity_id=layer_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=layer_id, child_entity_id=subindustry_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=subindustry_id, child_entity_id=nvda_id)
        _insert_relation(conn, taxonomy_version_id=taxonomy_version_id, ecosystem_id=ecosystem_id, parent_entity_id=subindustry_id, child_entity_id=crgy_id)

        watchlist_id = _insert_watchlist(conn, ecosystem_id)
        _insert_watchlist_member(conn, watchlist_id, nvda_id)

        for entity_id, coverage_status in (
            (ecosystem_entity_id, "OK"),
            (layer_id, "OK"),
            (subindustry_id, "OK"),
            (nvda_id, "OK"),
            (crgy_id, "WATCHLIST_ONLY"),
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

        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=ecosystem_entity_id, timing_state="WATCH_PRESSURE", trend_state="DOWN", summary_state="FRAGILE", freshness_status="FRESH")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, timing_state="WATCH_PRESSURE", trend_state="DOWN", summary_state="FRAGILE", freshness_status="FRESH")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=subindustry_id, timing_state="EMERGENCY_SELL_PRESSURE", trend_state="DOWN", summary_state="HIGH_RISK", freshness_status="AGING", quality_status="WARN")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, trend_state="DOWN", summary_state="UNDER_PRESSURE", classification_state="WRONG_FROM_SNAPSHOT", quality_status="OK")
        _insert_snapshot(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=crgy_id, snapshot_status="WARN", trend_state="DOWN", summary_state="WEAK", classification_state="WRONG_FROM_SNAPSHOT", quality_status="WARN")

        _insert_classification(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=nvda_id,
            classification_state="EMERGENCY_SELL_PRESSURE",
            primary_reason="CURRENT_HIGH_EXIT_RISK",
            blocking_reason="recent_bos_down",
            risk_reason="EXIT_RISK_CLUSTER",
            next_action="REDUCE_OR_EXIT",
        )

        for metric_name, metric_value in (
            ("breakout_days", 0.0),
            ("pullback_days", 1.0),
            ("exit_risk_days", 2.0),
            ("high_exit_risk_days", 2.0),
            ("medium_exit_risk_days", 0.0),
            ("valid_signal_dates", 2.0),
            ("distance_to_ema20_pct", -3.5),
        ):
            _insert_metric_num(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, metric_name=metric_name, metric_value_num=metric_value)

        for metric_name, metric_value in (
            ("pct_above_ema20", 40.0),
            ("return_5d", -6.0),
            ("synthetic_close", 94.0),
            ("trend_breadth", 25.0),
            ("weakness_breadth", 75.0),
            ("valid_signal_dates", 2.0),
        ):
            _insert_metric_num(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, metric_name=metric_name, metric_value_num=metric_value)
        for metric_name, metric_value in (
            ("group_current_status", "WATCH_PRESSURE"),
            ("group_window_status", "EMERGENCY_SELL_PRESSURE"),
            ("group_status_change", "WATCH_PRESSURE -> EMERGENCY_SELL_PRESSURE"),
            ("group_timing_state", "WATCH_PRESSURE"),
            ("group_timing_reason", "WATCH_PRESSURE:exit_risk_cluster"),
            ("group_overheat_risk_level", "LOW"),
        ):
            _insert_metric_text(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=layer_id, metric_name=metric_name, metric_value_text=metric_value)

        _insert_event(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id, event_date="2026-05-29", event_type="BOS", event_key="nvda-bos")
        _insert_event(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=subindustry_id, event_date="2026-05-28", event_type="RESET", event_key="semis-reset")
        signal_observation_id = _insert_signal(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id, entity_id=nvda_id)
        _insert_relevance(conn, signal_observation_id)
        conn.commit()
    finally:
        conn.close()


def test_query_requires_existing_run_id(tmp_path) -> None:
    db_path = tmp_path / "rolling2_query_missing_run.db"
    _build_fixture_db(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_rolling2_report_query_data(str(db_path), "missing-run")


def test_query_returns_rolling2_structured_data_from_eco_facts(tmp_path) -> None:
    db_path = tmp_path / "rolling2_query.db"
    _build_fixture_db(str(db_path))

    data = build_rolling2_report_query_data(str(db_path), RUN_ID)

    assert data.report_header.run_id == RUN_ID
    assert data.report_header.ecosystem_code == "DATACENTER"
    assert data.report_header.taxonomy_version_code == "DC_TAXONOMY_FULL_V1"
    assert data.report_header.signal_date == SIGNAL_DATE
    assert data.report_header.window_code == WINDOW_CODE
    assert data.window_summary["requested_end_date"] == "2026-05-29"
    assert data.window_summary["window_start_date"] == "2026-05-28"
    assert data.window_summary["window_end_date"] == "2026-05-29"
    assert data.window_summary["valid_signal_dates_count"] == 2
    assert data.window_summary["valid_signal_dates_included"] == ["2026-05-28", "2026-05-29"]
    assert data.window_summary["incomplete_window"] is False

    assert data.ecosystem_snapshot is not None
    assert data.ecosystem_snapshot["entity_code"] == "DATACENTER"
    assert [row["entity_type"] for row in data.group_snapshots] == ["LAYER", "SUBINDUSTRY"]
    assert [row["entity_code"] for row in data.ticker_snapshots] == ["CRGY", "NVDA"]

    assert len(data.rolling2_sell_pressure_classifications) == 1
    assert data.rolling2_sell_pressure_classifications[0]["ticker"] == "NVDA"
    assert data.rolling2_sell_pressure_classifications[0]["classification_state"] == "EMERGENCY_SELL_PRESSURE"
    assert data.rolling2_sell_pressure_classifications[0]["blocking_reason"] == "recent_bos_down"
    assert data.rolling2_sell_pressure_classifications[0]["risk_reason"] == "EXIT_RISK_CLUSTER"
    assert data.rolling2_sell_pressure_classifications[0]["next_action"] == "REDUCE_OR_EXIT"

    assert data.ticker_snapshots[1]["classification_state"] == "WRONG_FROM_SNAPSHOT"
    assert data.rolling2_sell_pressure_classifications[0]["classification_state"] != data.ticker_snapshots[1]["classification_state"]

    assert data.ticker_metrics["NVDA"]["breakout_days"] == 0.0
    assert data.ticker_metrics["NVDA"]["distance_to_ema20_pct"] == -3.5
    assert data.group_metrics[0]["entity_code"] == "INFRA"
    assert data.group_metrics[0]["group_window_status"] == "EMERGENCY_SELL_PRESSURE"
    assert data.group_metrics[0]["group_timing_reason"] == "WATCH_PRESSURE:exit_risk_cluster"

    assert len(data.watchlist_members) == 1
    assert data.watchlist_members[0]["ticker"] == "NVDA"
    assert data.watchlist_members[0]["watchlist_code"] == "PRIMARY"

    assert [row["event_type"] for row in data.structural_events] == ["BOS", "RESET"]
    assert len(data.signal_observations) == 1
    assert data.signal_observations[0]["signal_name"] == "RESET_FRESHNESS"
    assert data.signal_observations[0]["relevance_labels"] == "CONTEXTUAL"

    coverage_counts = {(row["entity_type"], row["coverage_status"]): row["row_count"] for row in data.quality_summary["coverage_counts"]}
    assert coverage_counts[("TICKER", "OK")] == 1
    assert coverage_counts[("TICKER", "WATCHLIST_ONLY")] == 1

    assert data.metadata["used_v2_runtime_tables"] is False
    assert data.metadata["used_generated_reports"] is False
    assert data.metadata["used_dashboard_output"] is False
    assert data.metadata["rolling2_classification_source"] == "eco_classification_decision"
    assert data.metadata["rolling2_snapshot_classification_source_used"] is False
    assert data.metadata["rolling2_event_window_mode"] == "event_date_range_within_2d_window"
    assert data.metadata["ranking_fields_mostly_null"] is True
    assert data.metadata["coverage_without_classification_tickers"] == ["CRGY"]
    assert data.metadata["signal_names_present"] == ["RESET_FRESHNESS"]
    assert data.metadata["rolling2_event_window_mode"] != "event_date_range_within_30d_window"
    assert "generated Markdown/CSV reports were not used as source data" in data.metadata["limitations"]
    assert (
        "eco_entity_window_snapshot.classification_state is not used as the primary rolling2 classification source"
        in data.metadata["limitations"]
    )
