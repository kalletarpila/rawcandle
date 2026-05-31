from analysis.datacenter_indices.report_canonical_v2_rolling30_formatter_loader import (
    build_markdown_rolling30_canonical_v2_report,
)


def _sample_formatter_data() -> dict[str, object]:
    return {
        "metadata": {
            "signal_date": "2026-05-30",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
            "market": "usa",
            "requested_run_id": None,
            "selected_run_id": "run-30",
            "horizon": "rolling30",
        },
        "run": {
            "run_id": "run-30",
            "status": "OK",
        },
        "group_rows": [],
        "window_rows": [
            {
                "ticker": "AMD",
                "window_start_date": "2026-05-01",
                "window_end_date": "2026-05-30",
                "valid_signal_dates": 30,
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "breakout_days": 3,
                "pullback_days": 2,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 1,
                "exit_risk_days": 4,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 2,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "EXIT_REASON_X",
                "first_signal_date": "2026-05-01",
                "last_signal_date": "2026-05-30",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "LOW",
            }
        ],
        "rolling30_buy_rows": [
            {
                "ticker": "AMD",
                "classification_state": "BUY_STATE_X",
                "primary_reason": "BUY_PRIMARY_X",
                "blocking_reason": "BUY_BLOCK_X",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "breakout_days": 3,
                "pullback_days": 2,
                "exit_risk_days": 4,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "EXIT_REASON_X",
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
        "rolling30_exit_rows": [
            {
                "ticker": "AMD",
                "classification_state": "EXIT_STATE_X",
                "primary_reason": "EXIT_PRIMARY_X",
                "risk_reason": "EXIT_RISK_X",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "exit_risk_days": 4,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 2,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "EXIT_REASON_X",
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
                "ticker": "AMD",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "LOW",
                "breakout_days": 3,
                "pullback_days": 2,
                "exit_risk_days": 4,
            }
        ],
        "repeated_breakout_rows": [
            {
                "ticker": "AMD",
                "breakout_days": 3,
                "first_signal_date": "2026-05-01",
                "last_signal_date": "2026-05-30",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "repeated_pullback_rows": [
            {
                "ticker": "AMD",
                "pullback_days": 2,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 1,
                "first_signal_date": "2026-05-01",
                "last_signal_date": "2026-05-30",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "repeated_exit_risk_rows": [
            {
                "ticker": "AMD",
                "exit_risk_days": 4,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 2,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "EXIT_REASON_X",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "taxonomy_listing_rows": [
            {
                "row_type": "LAYER",
                "layer": "Compute",
                "subindustry": "",
                "ticker": "",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "group_current_status": "GROUP_CURR_COMPUTE",
                "group_window_status": "GROUP_WIN_COMPUTE",
                "group_status_change": "UNCHANGED",
            },
            {
                "row_type": "SUBINDUSTRY",
                "layer": "Compute",
                "subindustry": "OrphanSub",
                "ticker": "",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "group_current_status": "GROUP_CURR_ORPHAN",
                "group_window_status": "GROUP_WIN_ORPHAN",
                "group_status_change": "UNCHANGED",
            },
            {
                "row_type": "LAYER",
                "layer": "Infrastructure",
                "subindustry": "",
                "ticker": "",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "group_current_status": "GROUP_CURR_INFRA",
                "group_window_status": "GROUP_WIN_INFRA",
                "group_status_change": "GROUP_CHANGE_INFRA",
            },
            {
                "row_type": "SUBINDUSTRY",
                "layer": "Infrastructure",
                "subindustry": "Semis",
                "ticker": "",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "group_current_status": "GROUP_CURR_SEMIS",
                "group_window_status": "GROUP_WIN_SEMIS",
                "group_status_change": "GROUP_CHANGE_SEMIS",
            },
            {
                "row_type": "TICKER",
                "layer": "Infrastructure",
                "subindustry": "Semis",
                "ticker": "AMD",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
            },
        ],
        "section_counts": {
            "group_row_count": 4,
            "window_row_count": 1,
            "rolling30_buy_classification_row_count": 1,
            "rolling30_exit_classification_row_count": 1,
            "watchlist_row_count": 1,
            "repeated_breakout_row_count": 1,
            "repeated_pullback_row_count": 1,
            "repeated_exit_risk_row_count": 1,
            "rolling30_buy_classification_state_counts": {"BUY_STATE_X": 1},
            "rolling30_exit_classification_state_counts": {"EXIT_STATE_X": 1},
            "current_watchlist_status_counts": {"CURRENT_BUY_X": 1},
            "window_watchlist_status_counts": {"WINDOW_BUY_X": 1},
        },
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
            "synthetic_event_history": "DEFERRED",
        },
    }


def test_formatter_renders_required_sections():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "# Datacenter Rolling30 Canonical V2 Report" in markdown
    assert "## 1. Title / metadata" in markdown
    assert "## 2. Summary counts" in markdown
    assert "## 3. Rolling30 buy rows" in markdown
    assert "## 4. Rolling30 exit rows" in markdown
    assert "## 5. Watchlist rows" in markdown
    assert "## 6. Repeated breakout rows" in markdown
    assert "## 7. Repeated pullback rows" in markdown
    assert "## 8. Repeated exit-risk rows" in markdown
    assert "## 9. Taxonomy listing preview" in markdown
    assert "## 10. Deferred sections" in markdown


def test_formatter_uses_stored_buy_classification_values_without_invented_next_action():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "BUY_STATE_X" in markdown
    assert "BUY_PRIMARY_X" in markdown
    assert "BUY_BLOCK_X" in markdown
    assert "next_action" not in markdown


def test_formatter_uses_stored_exit_classification_values_without_invented_next_action():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "EXIT_STATE_X" in markdown
    assert "EXIT_PRIMARY_X" in markdown
    assert "EXIT_RISK_X" in markdown
    assert "next_action" not in markdown


def test_formatter_uses_stored_watchlist_statuses():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "CURRENT_BUY_X" in markdown
    assert "WINDOW_BUY_X" in markdown


def test_formatter_repeated_rows_use_stored_counts():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "| AMD | 3 | 2026-05-01 | 2026-05-30 | CURRENT_BUY_X | WINDOW_BUY_X | UP | HL | Infrastructure | Semis |" in markdown
    assert "| AMD | 2 | 1 | 1 | 2026-05-01 | 2026-05-30 | CURRENT_BUY_X | WINDOW_BUY_X | UP | HL | Infrastructure | Semis |" in markdown
    assert "| AMD | 4 | 2 | 2 | HIGH | EXIT_REASON_X | CURRENT_BUY_X | WINDOW_BUY_X | UP | HL | Infrastructure | Semis |" in markdown


def test_formatter_preserves_taxonomy_listing_semantics_including_orphan_group():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "| SUBINDUSTRY | Compute | OrphanSub |  | BUY_ZONE | LOW | GROUP_CURR_ORPHAN | GROUP_WIN_ORPHAN | UNCHANGED |  |  |" in markdown
    assert "| TICKER | Infrastructure | Semis | AMD |  |  |  |  |  | CURRENT_BUY_X | WINDOW_BUY_X |" in markdown
    assert "OrphanSub | AMD" not in markdown


def test_formatter_marks_deferred_sections_explicitly():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "detailed swing MA break status: DEFERRED" in markdown
    assert "detailed swing signal freshness: DEFERRED" in markdown
    assert "full technical relevance context: DEFERRED" in markdown
    assert "full synthetic event history: DEFERRED" in markdown


def test_formatter_renders_deterministic_no_watchlist_notice():
    formatter_data = _sample_formatter_data()
    formatter_data["watchlist_rows"] = []
    formatter_data["section_counts"] = {
        **dict(formatter_data["section_counts"]),
        "watchlist_row_count": 0,
    }

    markdown = build_markdown_rolling30_canonical_v2_report(formatter_data)

    assert "## 5. Watchlist rows" in markdown
    assert "\n## 5. Watchlist rows\n- none\n\n## 6. Repeated breakout rows\n" in markdown


def test_formatter_is_pure_in_memory_without_db_or_source_tables():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "AMD" in markdown
    assert "BUY_STATE_X" in markdown
    assert "EXIT_STATE_X" in markdown


def test_formatter_full_markdown_output_is_deterministic():
    markdown = build_markdown_rolling30_canonical_v2_report(_sample_formatter_data())

    assert markdown == """# Datacenter Rolling30 Canonical V2 Report

## 1. Title / metadata
signal_date: 2026-05-30
taxonomy_version: DC_TAXONOMY_FULL_V1
selected_run_id: run-30
status: OK
horizon: rolling30
window_start_date: 2026-05-01
window_end_date: 2026-05-30
valid_signal_dates: 30

## 2. Summary counts
- group_count: 4
- window_row_count: 1
- rolling30_buy_classification_count: 1
- rolling30_exit_classification_count: 1
- watchlist_row_count: 1
- repeated_breakout_row_count: 1
- repeated_pullback_row_count: 1
- repeated_exit_risk_row_count: 1

### Rolling30 buy classification state counts
- BUY_STATE_X: 1

### Rolling30 exit classification state counts
- EXIT_STATE_X: 1

### Current watchlist status counts
- CURRENT_BUY_X: 1

### Window watchlist status counts
- WINDOW_BUY_X: 1

## 3. Rolling30 buy rows
| ticker | classification_state | primary_reason | blocking_reason | current_watchlist_status | window_watchlist_status | breakout_days | pullback_days | exit_risk_days | exit_risk_severity | latest_exit_reason | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | BUY_STATE_X | BUY_PRIMARY_X | BUY_BLOCK_X | CURRENT_BUY_X | WINDOW_BUY_X | 3 | 2 | 4 | HIGH | EXIT_REASON_X | UP | HL | Infrastructure | Semis |

## 4. Rolling30 exit rows
| ticker | classification_state | primary_reason | risk_reason | current_watchlist_status | window_watchlist_status | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | exit_risk_severity | latest_exit_reason | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | EXIT_STATE_X | EXIT_PRIMARY_X | EXIT_RISK_X | CURRENT_BUY_X | WINDOW_BUY_X | 4 | 2 | 2 | HIGH | EXIT_REASON_X | UP | HL | Infrastructure | Semis |

## 5. Watchlist rows
| ticker | current_watchlist_status | window_watchlist_status | primary_layer | primary_subindustry | layer_context_risk_status | subindustry_context_risk_status | breakout_days | pullback_days | exit_risk_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | CURRENT_BUY_X | WINDOW_BUY_X | Infrastructure | Semis | NO | LOW | 3 | 2 | 4 |

## 6. Repeated breakout rows
| ticker | breakout_days | first_signal_date | last_signal_date | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | 3 | 2026-05-01 | 2026-05-30 | CURRENT_BUY_X | WINDOW_BUY_X | UP | HL | Infrastructure | Semis |

## 7. Repeated pullback rows
| ticker | pullback_days | fast_ema10_pullback_days | conservative_ema20_pullback_days | first_signal_date | last_signal_date | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | 2 | 1 | 1 | 2026-05-01 | 2026-05-30 | CURRENT_BUY_X | WINDOW_BUY_X | UP | HL | Infrastructure | Semis |

## 8. Repeated exit-risk rows
| ticker | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | exit_risk_severity | latest_exit_reason | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | 4 | 2 | 2 | HIGH | EXIT_REASON_X | CURRENT_BUY_X | WINDOW_BUY_X | UP | HL | Infrastructure | Semis |

## 9. Taxonomy listing preview
| row_type | layer | subindustry | ticker | timing_state | overheat_risk_level | group_current_status | group_window_status | group_status_change | current_watchlist_status | window_watchlist_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Compute |  |  | BUY_ZONE | LOW | GROUP_CURR_COMPUTE | GROUP_WIN_COMPUTE | UNCHANGED |  |  |
| SUBINDUSTRY | Compute | OrphanSub |  | BUY_ZONE | LOW | GROUP_CURR_ORPHAN | GROUP_WIN_ORPHAN | UNCHANGED |  |  |
| LAYER | Infrastructure |  |  | BUY_ZONE | LOW | GROUP_CURR_INFRA | GROUP_WIN_INFRA | GROUP_CHANGE_INFRA |  |  |
| SUBINDUSTRY | Infrastructure | Semis |  | BUY_ZONE | LOW | GROUP_CURR_SEMIS | GROUP_WIN_SEMIS | GROUP_CHANGE_SEMIS |  |  |
| TICKER | Infrastructure | Semis | AMD |  |  |  |  |  | CURRENT_BUY_X | WINDOW_BUY_X |

## 10. Deferred sections
- detailed swing MA break status: DEFERRED
- detailed swing signal freshness: DEFERRED
- full synthetic event history: DEFERRED
- full technical relevance context: DEFERRED
"""
