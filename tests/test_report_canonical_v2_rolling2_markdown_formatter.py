from analysis.datacenter_indices.report_canonical_v2_rolling2_formatter_loader import (
    build_markdown_rolling2_canonical_v2_report,
)


def _sample_formatter_data() -> dict[str, object]:
    return {
        "metadata": {
            "signal_date": "2026-05-30",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
            "market": "usa",
            "requested_run_id": None,
            "selected_run_id": "run-1",
            "horizon": "rolling2",
        },
        "run": {
            "run_id": "run-1",
            "status": "OK",
        },
        "group_rows": [],
        "window_rows": [
            {
                "ticker": "NVDA",
                "window_start_date": "2026-05-29",
                "window_end_date": "2026-05-30",
                "valid_signal_dates": 2,
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "breakout_days": 2,
                "pullback_days": 1,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 1,
                "exit_risk_days": 3,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 1,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "PRICE_BREAK",
                "first_signal_date": "2026-05-29",
                "last_signal_date": "2026-05-30",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "LOW",
            }
        ],
        "rolling2_sell_pressure_rows": [
            {
                "ticker": "NVDA",
                "classification_state": "SELL_PRESSURE_X",
                "primary_reason": "PRIMARY_X",
                "risk_reason": "RISK_X",
                "next_action": "ACTION_X",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "exit_risk_days": 3,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 1,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "PRICE_BREAK",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "latest_bos_event_type": "BOS_UP",
                "latest_bos_freshness": "FRESH",
                "latest_reset_reason": "NONE",
                "latest_reset_freshness": "STALE",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "watchlist_rows": [
            {
                "ticker": "NVDA",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "LOW",
                "breakout_days": 2,
                "pullback_days": 1,
                "exit_risk_days": 3,
            }
        ],
        "repeated_breakout_rows": [
            {
                "ticker": "NVDA",
                "breakout_days": 2,
                "first_signal_date": "2026-05-29",
                "last_signal_date": "2026-05-30",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "repeated_pullback_rows": [
            {
                "ticker": "NVDA",
                "pullback_days": 1,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 1,
                "first_signal_date": "2026-05-29",
                "last_signal_date": "2026-05-30",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "repeated_exit_risk_rows": [
            {
                "ticker": "NVDA",
                "exit_risk_days": 3,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 1,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "PRICE_BREAK",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "taxonomy_listing_rows": [
            {
                "row_type": "LAYER",
                "layer": "Infrastructure",
                "subindustry": "",
                "ticker": "",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "group_current_status": "GROUP_CURR_X",
                "group_window_status": "GROUP_WIN_X",
                "group_status_change": "GROUP_CHANGE_X",
            },
            {
                "row_type": "TICKER",
                "layer": "Infrastructure",
                "subindustry": "Semis",
                "ticker": "NVDA",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
            },
        ],
        "section_counts": {
            "group_row_count": 2,
            "window_row_count": 1,
            "rolling2_classification_row_count": 1,
            "watchlist_row_count": 1,
            "repeated_breakout_row_count": 1,
            "repeated_pullback_row_count": 1,
            "repeated_exit_risk_row_count": 1,
            "rolling2_classification_state_counts": {"SELL_PRESSURE_X": 1},
            "current_watchlist_status_counts": {"CURRENT_ALPHA": 1},
            "window_watchlist_status_counts": {"WINDOW_ALPHA": 1},
        },
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
            "synthetic_event_history": "DEFERRED",
        },
    }


def test_formatter_renders_required_sections():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "# Datacenter Rolling2 Canonical V2 Report" in markdown
    assert "## 1. Title / metadata" in markdown
    assert "## 2. Summary counts" in markdown
    assert "## 3. Rolling2 sell pressure rows" in markdown
    assert "## 4. Watchlist rows" in markdown
    assert "## 5. Repeated breakout rows" in markdown
    assert "## 6. Repeated pullback rows" in markdown
    assert "## 7. Repeated exit-risk rows" in markdown
    assert "## 8. Taxonomy listing preview" in markdown
    assert "## 9. Deferred sections" in markdown


def test_formatter_uses_stored_classification_values():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "SELL_PRESSURE_X" in markdown
    assert "PRIMARY_X" in markdown
    assert "RISK_X" in markdown
    assert "ACTION_X" in markdown


def test_formatter_uses_stored_watchlist_statuses():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "CURRENT_ALPHA" in markdown
    assert "WINDOW_ALPHA" in markdown


def test_formatter_repeated_rows_use_stored_counts():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "| NVDA | 2 | 2026-05-29 | 2026-05-30 | CURRENT_ALPHA | WINDOW_ALPHA | UP | HL | Infrastructure | Semis |" in markdown
    assert "| NVDA | 1 | 1 | 1 | 2026-05-29 | 2026-05-30 | CURRENT_ALPHA | WINDOW_ALPHA | UP | HL | Infrastructure | Semis |" in markdown
    assert "| NVDA | 3 | 2 | 1 | HIGH | PRICE_BREAK | CURRENT_ALPHA | WINDOW_ALPHA | UP | HL | Infrastructure | Semis |" in markdown


def test_formatter_preserves_taxonomy_listing_semantics():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "| LAYER | Infrastructure |  |  | BUY_ZONE | LOW | GROUP_CURR_X | GROUP_WIN_X | GROUP_CHANGE_X |  |  |" in markdown
    assert "| TICKER | Infrastructure | Semis | NVDA |  |  |  |  |  | CURRENT_ALPHA | WINDOW_ALPHA |" in markdown


def test_formatter_marks_deferred_sections_explicitly():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "detailed swing MA break status: DEFERRED" in markdown
    assert "detailed swing signal freshness: DEFERRED" in markdown
    assert "full technical relevance context: DEFERRED" in markdown
    assert "full synthetic event history: DEFERRED" in markdown


def test_formatter_is_pure_in_memory_without_db_or_source_tables():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert "NVDA" in markdown
    assert "SELL_PRESSURE_X" in markdown


def test_formatter_full_markdown_output_is_deterministic():
    markdown = build_markdown_rolling2_canonical_v2_report(_sample_formatter_data())

    assert markdown == """# Datacenter Rolling2 Canonical V2 Report

## 1. Title / metadata
signal_date: 2026-05-30
taxonomy_version: DC_TAXONOMY_FULL_V1
selected_run_id: run-1
status: OK
horizon: rolling2
window_start_date: 2026-05-29
window_end_date: 2026-05-30
valid_signal_dates: 2

## 2. Summary counts
- group_count: 2
- window_row_count: 1
- rolling2_classification_count: 1
- watchlist_row_count: 1
- repeated_breakout_row_count: 1
- repeated_pullback_row_count: 1
- repeated_exit_risk_row_count: 1

### Rolling2 classification state counts
- SELL_PRESSURE_X: 1

### Current watchlist status counts
- CURRENT_ALPHA: 1

### Window watchlist status counts
- WINDOW_ALPHA: 1

## 3. Rolling2 sell pressure rows
| ticker | classification_state | primary_reason | risk_reason | next_action | current_watchlist_status | window_watchlist_status | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | exit_risk_severity | latest_exit_reason | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | SELL_PRESSURE_X | PRIMARY_X | RISK_X | ACTION_X | CURRENT_ALPHA | WINDOW_ALPHA | 3 | 2 | 1 | HIGH | PRICE_BREAK | Infrastructure | Semis |

## 4. Watchlist rows
| ticker | current_watchlist_status | window_watchlist_status | primary_layer | primary_subindustry | layer_context_risk_status | subindustry_context_risk_status | breakout_days | pullback_days | exit_risk_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | CURRENT_ALPHA | WINDOW_ALPHA | Infrastructure | Semis | NO | LOW | 2 | 1 | 3 |

## 5. Repeated breakout rows
| ticker | breakout_days | first_signal_date | last_signal_date | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | 2 | 2026-05-29 | 2026-05-30 | CURRENT_ALPHA | WINDOW_ALPHA | UP | HL | Infrastructure | Semis |

## 6. Repeated pullback rows
| ticker | pullback_days | fast_ema10_pullback_days | conservative_ema20_pullback_days | first_signal_date | last_signal_date | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | 1 | 1 | 1 | 2026-05-29 | 2026-05-30 | CURRENT_ALPHA | WINDOW_ALPHA | UP | HL | Infrastructure | Semis |

## 7. Repeated exit-risk rows
| ticker | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | exit_risk_severity | latest_exit_reason | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | 3 | 2 | 1 | HIGH | PRICE_BREAK | CURRENT_ALPHA | WINDOW_ALPHA | UP | HL | Infrastructure | Semis |

## 8. Taxonomy listing preview
| row_type | layer | subindustry | ticker | timing_state | overheat_risk_level | group_current_status | group_window_status | group_status_change | current_watchlist_status | window_watchlist_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Infrastructure |  |  | BUY_ZONE | LOW | GROUP_CURR_X | GROUP_WIN_X | GROUP_CHANGE_X |  |  |
| TICKER | Infrastructure | Semis | NVDA |  |  |  |  |  | CURRENT_ALPHA | WINDOW_ALPHA |

## 9. Deferred sections
- detailed swing MA break status: DEFERRED
- detailed swing signal freshness: DEFERRED
- full synthetic event history: DEFERRED
- full technical relevance context: DEFERRED
"""
