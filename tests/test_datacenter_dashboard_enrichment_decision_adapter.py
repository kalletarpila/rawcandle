from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
    load_ticker_enrichment_rows,
)


def test_adapter_builds_dashboard_rows_from_minimal_enrichment_row():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "NEUTRAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    assert len(rows) == 1
    assert rows[0].ticker == "NVDA"
    assert rows[0].horizon == "daily"
    assert rows[0].raw_status == "NEUTRAL"
    assert rows[0].trend_state == "UP"
    assert rows[0].raw_fields["current_status"] == "NEUTRAL"
    assert rows[0].raw_fields["latest_bos_event_type"] == "BOS_UP"


def test_adapter_expands_horizon_specific_status_fields():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "daily_status": "NEUTRAL_MONITOR",
                "rolling_2d_status": "NO_EMERGENCY",
                "rolling_5d_status": "PULLBACK_CANDIDATE",
                "rolling_30d_status": "BUY_ZONE",
            }
        ]
    )

    assert any(row.horizon == "daily" and row.raw_status == "NEUTRAL_MONITOR" for row in rows)
    assert any(row.horizon == "rolling 2d" and row.raw_status == "NO_EMERGENCY" for row in rows)
    assert any(
        row.horizon == "rolling 5d" and row.raw_status == "PULLBACK_CANDIDATE"
        for row in rows
    )
    assert any(row.horizon == "rolling 30d" and row.raw_status == "BUY_ZONE" for row in rows)


def test_adapter_excludes_invalid_ticker_rows():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {"ticker": "", "current_status": "NEUTRAL"},
            {"ticker": "2026-05-22", "current_status": "NEUTRAL"},
            {"ticker": "NVDA", "current_status": "NEUTRAL"},
        ]
    )

    assert [row.ticker for row in rows] == ["NVDA"]


def test_build_decisions_from_ticker_enrichment_rows_uses_existing_decision_logic():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "NEUTRAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].ticker == "NVDA"
    assert result.decisions[0].action == "NEUTRAL"


def test_multi_horizon_positive_case_produces_buy_now_with_expected_horizons():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "BUY_NOW",
                "daily_status": "BUY_NOW",
                "rolling_5d_status": "PULLBACK_CANDIDATE",
                "rolling_30d_status": "BUY_ZONE",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.ticker == "NVDA"
    assert decision.action == "BUY_NOW"
    assert set(decision.horizons_present) >= {"daily", "rolling 5d", "rolling 30d"}
    assert len(decision.decision_trace) >= 1


def test_pullback_readiness_outputs_come_from_existing_decision_logic():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "NEUTRAL",
                "daily_status": "NEUTRAL_MONITOR",
                "ma_break_status": "OK",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "pullback_days": "2",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.pullback_validity == "VALID_PULLBACK"
    assert decision.entry_readiness == "READY_TO_WATCH"
    assert decision.candidate_priority is not None
    assert decision.candidate_priority_label == "P1_READY_TO_WATCH"


def test_loader_reads_rows_read_only_and_missing_db_fails_clearly(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                current_status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, current_status
            ) VALUES (?, ?, ?, ?)
            """,
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "NVDA", "NEUTRAL"),
        )
        before_count = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    rows = load_ticker_enrichment_rows(
        str(db_path),
        "2026-05-22",
        "DC_TAXONOMY_FULL_V1",
    )

    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"

    with sqlite3.connect(db_path) as conn:
        after_count = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
    assert before_count == after_count

    missing_path = tmp_path / "missing.db"
    try:
        load_ticker_enrichment_rows(
            str(missing_path),
            "2026-05-22",
            "DC_TAXONOMY_FULL_V1",
        )
    except FileNotFoundError as exc:
        assert "analysis_db not found:" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected FileNotFoundError for missing analysis_db")
