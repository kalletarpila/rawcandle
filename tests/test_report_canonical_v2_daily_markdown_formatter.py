import sqlite3

from analysis.datacenter_indices.report_canonical_v2_daily_formatter_loader import (
    build_markdown_daily_canonical_v2_report,
    load_daily_canonical_formatter_data_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _sample_formatter_data() -> dict[str, object]:
    return {
        "metadata": {
            "signal_date": "2026-05-30",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
            "market": "usa",
            "requested_run_id": None,
            "selected_run_id": "run-1",
        },
        "run": {
            "run_id": "run-1",
            "status": "OK",
        },
        "group_rows": [
            {
                "group_type": "layer",
                "group_name": "Infrastructure",
                "overheat_risk_level": "LOW",
            },
            {
                "group_type": "subindustry",
                "group_name": "Semis",
                "overheat_risk_level": "MEDIUM",
            },
        ],
        "ticker_rows": [],
        "daily_trigger_rows": [
            {
                "ticker": "NVDA",
                "classification_state": "BUY_WATCH",
                "primary_reason": "BULLISH_SETUP_NEEDS_CONFIRMATION",
                "blocking_reason": "",
                "next_action": "MONITOR_FOR_DAILY_CONFIRMATION",
                "current_watchlist_status": "BREAKOUT_CANDIDATE",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "watchlist_rows": [
            {
                "ticker": "NVDA",
                "current_watchlist_status": "BREAKOUT_CANDIDATE",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "NO",
                "breakout_signal": 1,
                "pullback_signal": 0,
                "exit_risk_signal": 0,
            }
        ],
        "taxonomy_listing_rows": [
            {
                "row_type": "LAYER",
                "layer": "Infrastructure",
                "subindustry": "",
                "ticker": "",
                "status": "BUY_ZONE",
                "pct_above_ema20": 62.5,
                "pct_above_ma10": 71.0,
            },
            {
                "row_type": "SUBINDUSTRY",
                "layer": "Infrastructure",
                "subindustry": "Semis",
                "ticker": "",
                "status": "ADD_ON_PULLBACK",
                "pct_above_ema20": 58.0,
                "pct_above_ma10": 66.0,
            },
            {
                "row_type": "TICKER",
                "layer": "Infrastructure",
                "subindustry": "Semis",
                "ticker": "NVDA",
                "status": "BREAKOUT_CANDIDATE",
                "distance_to_ema20_pct": 1.2345,
            },
        ],
        "section_counts": {
            "ticker_row_count": 1,
            "group_row_count": 2,
            "daily_trigger_row_count": 1,
            "watchlist_row_count": 1,
            "daily_trigger_state_counts": {"BUY_WATCH": 1},
            "watchlist_status_counts": {"BREAKOUT_CANDIDATE": 1},
        },
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
        },
    }


def test_formatter_renders_required_sections():
    markdown = build_markdown_daily_canonical_v2_report(_sample_formatter_data())

    assert "# Datacenter Daily Canonical V2 Report" in markdown
    assert "## 1. Title / metadata" in markdown
    assert "## 2. Summary counts" in markdown
    assert "## 3. Daily trigger rows" in markdown
    assert "## 4. Watchlist rows" in markdown
    assert "## 5. Taxonomy listing preview" in markdown
    assert "## 6. Deferred sections" in markdown


def test_formatter_uses_stored_classification_values():
    markdown = build_markdown_daily_canonical_v2_report(_sample_formatter_data())

    assert "BUY_WATCH" in markdown
    assert "BULLISH_SETUP_NEEDS_CONFIRMATION" in markdown
    assert "MONITOR_FOR_DAILY_CONFIRMATION" in markdown


def test_formatter_uses_stored_watchlist_status():
    markdown = build_markdown_daily_canonical_v2_report(_sample_formatter_data())

    assert "BREAKOUT_CANDIDATE" in markdown


def test_formatter_preserves_taxonomy_group_and_ticker_semantics():
    markdown = build_markdown_daily_canonical_v2_report(_sample_formatter_data())

    assert "pct_above_ema20" in markdown
    assert "pct_above_ma10" in markdown
    assert "distance_to_ema20_pct" in markdown
    assert "| LAYER | Infrastructure |  |  | BUY_ZONE | LOW | 62.5 | 71.0 |  |  |" in markdown
    assert "| SUBINDUSTRY | Infrastructure | Semis |  | ADD_ON_PULLBACK | MEDIUM | 58.0 | 66.0 |  |  |" in markdown
    assert "| TICKER | Infrastructure | Semis | NVDA |  |  |  |  | 1.2345 | BREAKOUT_CANDIDATE |" in markdown


def test_formatter_marks_deferred_sections_explicitly():
    markdown = build_markdown_daily_canonical_v2_report(_sample_formatter_data())

    assert "detailed swing MA break status: DEFERRED" in markdown
    assert "detailed swing signal freshness: DEFERRED" in markdown
    assert "full technical relevance context: DEFERRED" in markdown


def test_formatter_full_markdown_output_is_deterministic():
    markdown = build_markdown_daily_canonical_v2_report(_sample_formatter_data())

    assert markdown == """# Datacenter Daily Canonical V2 Report

## 1. Title / metadata
signal_date: 2026-05-30
taxonomy_version: DC_TAXONOMY_FULL_V1
selected_run_id: run-1
status: OK

## 2. Summary counts
- ticker_count: 1
- group_count: 2
- daily_trigger_count: 1
- watchlist_count: 1

### Trigger state counts
- BUY_WATCH: 1

### Watchlist status counts
- BREAKOUT_CANDIDATE: 1

## 3. Daily trigger rows
| ticker | classification_state | primary_reason | blocking_reason | next_action | current_watchlist_status | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | BUY_WATCH | BULLISH_SETUP_NEEDS_CONFIRMATION |  | MONITOR_FOR_DAILY_CONFIRMATION | BREAKOUT_CANDIDATE | Infrastructure | Semis |

## 4. Watchlist rows
| ticker | current_watchlist_status | primary_layer | primary_subindustry | layer_context_risk_status | subindustry_context_risk_status | breakout_signal | pullback_signal | exit_risk_signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | BREAKOUT_CANDIDATE | Infrastructure | Semis | NO | NO | 1 | 0 | 0 |

## 5. Taxonomy listing preview
| row_type | layer | subindustry | ticker | timing_state | overheat_risk_level | pct_above_ema20 | pct_above_ma10 | distance_to_ema20_pct | current_watchlist_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Infrastructure |  |  | BUY_ZONE | LOW | 62.5 | 71.0 |  |  |
| SUBINDUSTRY | Infrastructure | Semis |  | ADD_ON_PULLBACK | MEDIUM | 58.0 | 66.0 |  |  |
| TICKER | Infrastructure | Semis | NVDA |  |  |  |  | 1.2345 | BREAKOUT_CANDIDATE |

## 6. Deferred sections
- detailed swing MA break status: DEFERRED
- detailed swing signal freshness: DEFERRED
- full technical relevance context: DEFERRED
"""


def test_formatter_works_without_source_tables_when_loader_is_canonical_only():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)

    source_tables = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name IN (
            'dc_ticker_swing_signal_daily',
            'dc_group_swing_signal_daily',
            'dc_group_synthetic_ohlc_daily'
        )
        """
    ).fetchall()
    assert source_tables == []

    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id, signal_date, taxonomy_version, market, calculation_version,
            source_versions_json, created_at_utc, status, warning_count, error_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-1",
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "REPORT_CANONICAL_V2",
            None,
            "2026-05-30T00:00:00Z",
            "OK",
            0,
            0,
            None,
        ),
    )
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            timing_state, overheat_risk_level, return_5d, return_10d, return_20d,
            pct_above_ema20, pct_above_ma10, group_context_risk_status,
            group_context_readiness_status, synthetic_close, synthetic_trend_classification,
            synthetic_latest_structure_label, synthetic_latest_structure_age_trading_days,
            synthetic_latest_bos_event_type, synthetic_latest_bos_age_trading_days,
            synthetic_latest_bos_freshness, synthetic_latest_reset_reason,
            synthetic_latest_reset_age_trading_days, synthetic_latest_reset_freshness,
            data_quality_status, group_current_status, window_end_date, run_id, created_at_utc
        ) VALUES (?, ?, ?, 'daily', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "layer",
            "Infrastructure",
            "BUY_ZONE",
            "LOW",
            2.0,
            4.0,
            6.0,
            62.5,
            71.0,
            "NO",
            "OK",
            150.0,
            "UP",
            "HL",
            5,
            "BOS_UP",
            1,
            "FRESH",
            "NONE",
            3,
            "STALE",
            "OK",
            "BUY_ZONE",
            "2026-05-30",
            "run-1",
            "2026-05-30T00:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            timing_state, overheat_risk_level, return_5d, return_10d, return_20d,
            pct_above_ema20, pct_above_ma10, group_context_risk_status,
            group_context_readiness_status, synthetic_close, synthetic_trend_classification,
            synthetic_latest_structure_label, synthetic_latest_structure_age_trading_days,
            synthetic_latest_bos_event_type, synthetic_latest_bos_age_trading_days,
            synthetic_latest_bos_freshness, synthetic_latest_reset_reason,
            synthetic_latest_reset_age_trading_days, synthetic_latest_reset_freshness,
            data_quality_status, group_current_status, window_end_date, run_id, created_at_utc
        ) VALUES (?, ?, ?, 'daily', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "subindustry",
            "Semis",
            "ADD_ON_PULLBACK",
            "MEDIUM",
            2.0,
            4.0,
            6.0,
            58.0,
            66.0,
            "NO",
            "OK",
            140.0,
            "UP",
            "HL",
            5,
            "BOS_UP",
            1,
            "FRESH",
            "NONE",
            3,
            "STALE",
            "OK",
            "ADD_ON_PULLBACK",
            "2026-05-30",
            "run-1",
            "2026-05-30T00:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date, taxonomy_version, market, ticker, primary_layer, primary_subindustry,
            in_datacenter_ecosystem, is_watchlist, current_watchlist_status,
            price_data_status, close, breakout_signal, pullback_signal, exit_risk_signal,
            return_5d, return_10d, return_20d, return_60d, distance_to_ema20_pct,
            trend_state, latest_structure_label, latest_structure_age_trading_days,
            latest_structure_freshness, latest_bos_event_type, latest_bos_age_trading_days,
            latest_bos_freshness, latest_reset_reason, latest_reset_age_trading_days,
            latest_reset_freshness, layer_context_risk_status, subindustry_context_risk_status,
            context_readiness_status, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "NVDA",
            "Infrastructure",
            "Semis",
            1,
            1,
            "BREAKOUT_CANDIDATE",
            "OK",
            100.0,
            1,
            0,
            0,
            2.0,
            4.0,
            8.0,
            12.0,
            1.2345,
            "UP",
            "HL",
            6,
            "FRESH",
            "BOS_UP",
            2,
            "FRESH",
            "NONE",
            4,
            "STALE",
            "NO",
            "NO",
            "OK",
            "run-1",
            "2026-05-30T00:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, market, ticker, horizon, classification_type,
            classification_state, primary_reason, blocking_reason, risk_reason, next_action,
            classification_status, classification_version, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, 'daily', 'daily_trigger', ?, ?, ?, ?, ?, 'OK', ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "NVDA",
            "BUY_WATCH",
            "BULLISH_SETUP_NEEDS_CONFIRMATION",
            "",
            None,
            "MONITOR_FOR_DAILY_CONFIRMATION",
            "REPORT_CANONICAL_CLASSIFICATION_V2",
            "run-1",
            "2026-05-30T00:00:00Z",
        ),
    )
    conn.commit()

    formatter_data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )
    markdown = build_markdown_daily_canonical_v2_report(formatter_data)

    assert "NVDA" in markdown
    assert "BUY_WATCH" in markdown
