from analysis.datacenter_indices.report_canonical_v2_rolling5_formatter_loader import (
    build_markdown_rolling5_canonical_v2_report,
)


def _sample_formatter_data() -> dict[str, object]:
    return {
        "metadata": {
            "signal_date": "2026-05-30",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
            "market": "usa",
            "requested_run_id": None,
            "selected_run_id": "run-5",
            "horizon": "rolling5",
        },
        "run": {
            "run_id": "run-5",
            "status": "OK",
        },
        "group_rows": [],
        "window_rows": [
            {
                "ticker": "AMD",
                "window_start_date": "2026-05-26",
                "window_end_date": "2026-05-30",
                "valid_signal_dates": 5,
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
                "breakout_days": 1,
                "pullback_days": 2,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 1,
                "exit_risk_days": 3,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 1,
                "exit_risk_severity": "MEDIUM",
                "latest_exit_reason": "STRUCTURAL_WARNING",
                "first_signal_date": "2026-05-26",
                "last_signal_date": "2026-05-30",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "LOW",
            }
        ],
        "rolling5_pullback_rows": [
            {
                "ticker": "AMD",
                "classification_state": "PULLBACK_STATE_X",
                "primary_reason": "PRIMARY_PULLBACK_X",
                "blocking_reason": "BLOCKING_X",
                "next_action": "ACTION_X",
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
                "pullback_days": 2,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 1,
                "exit_risk_days": 3,
                "exit_risk_severity": "MEDIUM",
                "latest_exit_reason": "STRUCTURAL_WARNING",
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
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
                "layer_context_risk_status": "NO",
                "subindustry_context_risk_status": "LOW",
                "breakout_days": 1,
                "pullback_days": 2,
                "exit_risk_days": 3,
            }
        ],
        "repeated_breakout_rows": [
            {
                "ticker": "AMD",
                "breakout_days": 1,
                "first_signal_date": "2026-05-26",
                "last_signal_date": "2026-05-30",
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
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
                "first_signal_date": "2026-05-26",
                "last_signal_date": "2026-05-30",
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
                "trend_state": "UP",
                "latest_structure_label": "HL",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis",
            }
        ],
        "repeated_exit_risk_rows": [
            {
                "ticker": "AMD",
                "exit_risk_days": 3,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 1,
                "exit_risk_severity": "MEDIUM",
                "latest_exit_reason": "STRUCTURAL_WARNING",
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
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
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
            },
        ],
        "section_counts": {
            "group_row_count": 4,
            "window_row_count": 1,
            "rolling5_classification_row_count": 1,
            "watchlist_row_count": 1,
            "repeated_breakout_row_count": 1,
            "repeated_pullback_row_count": 1,
            "repeated_exit_risk_row_count": 1,
            "rolling5_classification_state_counts": {"PULLBACK_STATE_X": 1},
            "current_watchlist_status_counts": {"CURRENT_PULLBACK": 1},
            "window_watchlist_status_counts": {"WINDOW_PULLBACK": 1},
        },
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
            "synthetic_event_history": "DEFERRED",
        },
    }


def test_formatter_renders_required_sections():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert "# Datacenter Rolling5 Canonical V2 Report" in markdown
    assert "## 1. Title / metadata" in markdown
    assert "## 2. Summary counts" in markdown
    assert "## 3. Rolling5 pullback rows" in markdown
    assert "## 4. Watchlist rows" in markdown
    assert "## 5. Repeated breakout rows" in markdown
    assert "## 6. Repeated pullback rows" in markdown
    assert "## 7. Repeated exit-risk rows" in markdown
    assert "## 8. Taxonomy listing preview" in markdown
    assert "## 9. Deferred sections" in markdown


def test_formatter_uses_stored_classification_values():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert "PULLBACK_STATE_X" in markdown
    assert "PRIMARY_PULLBACK_X" in markdown
    assert "BLOCKING_X" in markdown
    assert "ACTION_X" in markdown


def test_formatter_uses_stored_watchlist_statuses():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert "CURRENT_PULLBACK" in markdown
    assert "WINDOW_PULLBACK" in markdown


def test_formatter_repeated_rows_use_stored_counts():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert "| AMD | 1 | 2026-05-26 | 2026-05-30 | CURRENT_PULLBACK | WINDOW_PULLBACK | UP | HL | Infrastructure | Semis |" in markdown
    assert "| AMD | 2 | 1 | 1 | 2026-05-26 | 2026-05-30 | CURRENT_PULLBACK | WINDOW_PULLBACK | UP | HL | Infrastructure | Semis |" in markdown
    assert "| AMD | 3 | 2 | 1 | MEDIUM | STRUCTURAL_WARNING | CURRENT_PULLBACK | WINDOW_PULLBACK | UP | HL | Infrastructure | Semis |" in markdown


def test_formatter_preserves_taxonomy_listing_semantics_including_orphan_group():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert "| SUBINDUSTRY | Compute | OrphanSub |  | BUY_ZONE | LOW | GROUP_CURR_ORPHAN | GROUP_WIN_ORPHAN | UNCHANGED |  |  |" in markdown
    assert "| TICKER | Infrastructure | Semis | AMD |  |  |  |  |  | CURRENT_PULLBACK | WINDOW_PULLBACK |" in markdown
    assert "OrphanSub | AMD" not in markdown


def test_formatter_marks_deferred_sections_explicitly():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

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

    markdown = build_markdown_rolling5_canonical_v2_report(formatter_data)

    assert "## 4. Watchlist rows" in markdown
    assert "\n## 4. Watchlist rows\n- none\n\n## 5. Repeated breakout rows\n" in markdown


def test_formatter_is_pure_in_memory_without_db_or_source_tables():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert "AMD" in markdown
    assert "PULLBACK_STATE_X" in markdown


def test_formatter_full_markdown_output_is_deterministic():
    markdown = build_markdown_rolling5_canonical_v2_report(_sample_formatter_data())

    assert markdown == """# Datacenter Rolling5 Canonical V2 Report

## 1. Title / metadata
signal_date: 2026-05-30
taxonomy_version: DC_TAXONOMY_FULL_V1
selected_run_id: run-5
status: OK
horizon: rolling5
window_start_date: 2026-05-26
window_end_date: 2026-05-30
valid_signal_dates: 5

## 2. Summary counts
- group_count: 4
- window_row_count: 1
- rolling5_classification_count: 1
- watchlist_row_count: 1
- repeated_breakout_row_count: 1
- repeated_pullback_row_count: 1
- repeated_exit_risk_row_count: 1

### Rolling5 classification state counts
- PULLBACK_STATE_X: 1

### Current watchlist status counts
- CURRENT_PULLBACK: 1

### Window watchlist status counts
- WINDOW_PULLBACK: 1

## 3. Rolling5 pullback rows
| ticker | classification_state | primary_reason | blocking_reason | next_action | current_watchlist_status | window_watchlist_status | pullback_days | fast_ema10_pullback_days | conservative_ema20_pullback_days | exit_risk_days | exit_risk_severity | latest_exit_reason | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | PULLBACK_STATE_X | PRIMARY_PULLBACK_X | BLOCKING_X | ACTION_X | CURRENT_PULLBACK | WINDOW_PULLBACK | 2 | 1 | 1 | 3 | MEDIUM | STRUCTURAL_WARNING | Infrastructure | Semis |

## 4. Watchlist rows
| ticker | current_watchlist_status | window_watchlist_status | primary_layer | primary_subindustry | layer_context_risk_status | subindustry_context_risk_status | breakout_days | pullback_days | exit_risk_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | CURRENT_PULLBACK | WINDOW_PULLBACK | Infrastructure | Semis | NO | LOW | 1 | 2 | 3 |

## 5. Repeated breakout rows
| ticker | breakout_days | first_signal_date | last_signal_date | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | 1 | 2026-05-26 | 2026-05-30 | CURRENT_PULLBACK | WINDOW_PULLBACK | UP | HL | Infrastructure | Semis |

## 6. Repeated pullback rows
| ticker | pullback_days | fast_ema10_pullback_days | conservative_ema20_pullback_days | first_signal_date | last_signal_date | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | 2 | 1 | 1 | 2026-05-26 | 2026-05-30 | CURRENT_PULLBACK | WINDOW_PULLBACK | UP | HL | Infrastructure | Semis |

## 7. Repeated exit-risk rows
| ticker | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | exit_risk_severity | latest_exit_reason | current_watchlist_status | window_watchlist_status | trend_state | latest_structure_label | primary_layer | primary_subindustry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMD | 3 | 2 | 1 | MEDIUM | STRUCTURAL_WARNING | CURRENT_PULLBACK | WINDOW_PULLBACK | UP | HL | Infrastructure | Semis |

## 8. Taxonomy listing preview
| row_type | layer | subindustry | ticker | timing_state | overheat_risk_level | group_current_status | group_window_status | group_status_change | current_watchlist_status | window_watchlist_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Compute |  |  | BUY_ZONE | LOW | GROUP_CURR_COMPUTE | GROUP_WIN_COMPUTE | UNCHANGED |  |  |
| SUBINDUSTRY | Compute | OrphanSub |  | BUY_ZONE | LOW | GROUP_CURR_ORPHAN | GROUP_WIN_ORPHAN | UNCHANGED |  |  |
| LAYER | Infrastructure |  |  | BUY_ZONE | LOW | GROUP_CURR_INFRA | GROUP_WIN_INFRA | GROUP_CHANGE_INFRA |  |  |
| SUBINDUSTRY | Infrastructure | Semis |  | BUY_ZONE | LOW | GROUP_CURR_SEMIS | GROUP_WIN_SEMIS | GROUP_CHANGE_SEMIS |  |  |
| TICKER | Infrastructure | Semis | AMD |  |  |  |  |  | CURRENT_PULLBACK | WINDOW_PULLBACK |

## 9. Deferred sections
- detailed swing MA break status: DEFERRED
- detailed swing signal freshness: DEFERRED
- full synthetic event history: DEFERRED
- full technical relevance context: DEFERRED
"""
