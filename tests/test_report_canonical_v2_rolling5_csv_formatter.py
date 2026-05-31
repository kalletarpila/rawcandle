import csv
import io

from analysis.datacenter_indices.report_canonical_v2_rolling5_formatter_loader import (
    build_csv_rolling5_canonical_v2_report,
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_reason": "PRIMARY_PULLBACK, X",
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
                "latest_reset_reason": None,
                "latest_reset_freshness": "STALE",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
            }
        ],
        "watchlist_rows": [
            {
                "ticker": "AMD",
                "current_watchlist_status": "CURRENT_PULLBACK",
                "window_watchlist_status": "WINDOW_PULLBACK",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "subindustry": "Semis, Accelerators",
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
                "subindustry": "Semis, Accelerators",
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


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_renders_required_sections():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))
    sections = {row["section"] for row in rows}

    assert "metadata" in sections
    assert "summary_counts" in sections
    assert "rolling5_classification_state_counts" in sections
    assert "current_watchlist_status_counts" in sections
    assert "window_watchlist_status_counts" in sections
    assert "rolling5_pullback_rows" in sections
    assert "watchlist_rows" in sections
    assert "repeated_breakout_rows" in sections
    assert "repeated_pullback_rows" in sections
    assert "repeated_exit_risk_rows" in sections
    assert "taxonomy_listing_preview" in sections
    assert "deferred_sections" in sections


def test_csv_header_is_deterministic():
    csv_text = build_csv_rolling5_canonical_v2_report(_sample_formatter_data())
    first_line = csv_text.splitlines()[0]

    assert first_line == (
        "section,key,value,ticker,classification_state,primary_reason,"
        "blocking_reason,next_action,current_watchlist_status,window_watchlist_status,"
        "primary_layer,primary_subindustry,layer_context_risk_status,"
        "subindustry_context_risk_status,breakout_days,pullback_days,"
        "fast_ema10_pullback_days,conservative_ema20_pullback_days,exit_risk_days,"
        "high_exit_risk_days,medium_exit_risk_days,exit_risk_severity,"
        "latest_exit_reason,first_signal_date,last_signal_date,trend_state,"
        "latest_structure_label,row_type,layer,subindustry,timing_state,"
        "overheat_risk_level,group_current_status,group_window_status,"
        "group_status_change,deferred_section,status,reason"
    )


def test_csv_preserves_stored_classification_values():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "rolling5_pullback_rows")

    assert row["ticker"] == "AMD"
    assert row["classification_state"] == "PULLBACK_STATE_X"
    assert row["primary_reason"] == "PRIMARY_PULLBACK, X"
    assert row["blocking_reason"] == "BLOCKING_X"
    assert row["next_action"] == "ACTION_X"


def test_csv_preserves_stored_watchlist_values():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "watchlist_rows")

    assert row["current_watchlist_status"] == "CURRENT_PULLBACK"
    assert row["window_watchlist_status"] == "WINDOW_PULLBACK"
    assert row["layer_context_risk_status"] == "NO"
    assert row["subindustry_context_risk_status"] == "LOW"


def test_csv_preserves_repeated_row_counts_by_section():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))

    breakout_row = next(row for row in rows if row["section"] == "repeated_breakout_rows")
    pullback_row = next(row for row in rows if row["section"] == "repeated_pullback_rows")
    exit_risk_row = next(row for row in rows if row["section"] == "repeated_exit_risk_rows")

    assert breakout_row["breakout_days"] == "1"
    assert pullback_row["pullback_days"] == "2"
    assert pullback_row["fast_ema10_pullback_days"] == "1"
    assert pullback_row["conservative_ema20_pullback_days"] == "1"
    assert exit_risk_row["exit_risk_days"] == "3"
    assert exit_risk_row["high_exit_risk_days"] == "2"
    assert exit_risk_row["medium_exit_risk_days"] == "1"


def test_csv_preserves_taxonomy_field_semantics_including_orphan_group():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))
    orphan_group_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview"
        and row["row_type"] == "SUBINDUSTRY"
        and row["layer"] == "Compute"
        and row["subindustry"] == "OrphanSub"
    )
    ticker_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "TICKER"
    )

    assert orphan_group_row["ticker"] == ""
    assert orphan_group_row["group_current_status"] == "GROUP_CURR_ORPHAN"
    assert orphan_group_row["group_window_status"] == "GROUP_WIN_ORPHAN"
    assert orphan_group_row["group_status_change"] == "UNCHANGED"
    assert orphan_group_row["current_watchlist_status"] == ""
    assert ticker_row["ticker"] == "AMD"
    assert ticker_row["group_current_status"] == ""
    assert ticker_row["group_window_status"] == ""
    assert ticker_row["group_status_change"] == ""
    assert ticker_row["current_watchlist_status"] == "CURRENT_PULLBACK"
    assert ticker_row["window_watchlist_status"] == "WINDOW_PULLBACK"


def test_csv_zero_watchlist_output_is_deterministic():
    formatter_data = _sample_formatter_data()
    formatter_data["watchlist_rows"] = []
    formatter_data["section_counts"] = {
        **dict(formatter_data["section_counts"]),
        "watchlist_row_count": 0,
    }

    csv_text = build_csv_rolling5_canonical_v2_report(formatter_data)
    rows = _parse_csv(csv_text)
    sections = {row["section"] for row in rows}

    assert csv_text
    assert csv_text.startswith("section,key,value,")
    assert "metadata" in sections
    assert "rolling5_pullback_rows" in sections
    assert "deferred_sections" in sections

    watchlist_summary_row = next(
        row
        for row in rows
        if row["section"] == "summary_counts" and row["key"] == "watchlist_row_count"
    )
    watchlist_data_rows = [row for row in rows if row["section"] == "watchlist_rows"]

    assert watchlist_summary_row["value"] == "0"
    assert watchlist_data_rows == []


def test_csv_none_values_render_as_empty_strings():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))

    assert all("None" not in row.values() for row in rows)


def test_csv_escaping_round_trips_through_csv_module():
    rows = _parse_csv(build_csv_rolling5_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "rolling5_pullback_rows")

    assert row["primary_reason"] == "PRIMARY_PULLBACK, X"
    assert row["primary_subindustry"] == "Semis, Accelerators"


def test_csv_formatter_is_pure_in_memory_without_db_setup():
    formatter_data = _sample_formatter_data()

    csv_text = build_csv_rolling5_canonical_v2_report(formatter_data)
    rows = _parse_csv(csv_text)

    assert csv_text
    assert csv_text.startswith("section,key,value,")

    pullback_row = next(row for row in rows if row["section"] == "rolling5_pullback_rows")
    watchlist_row = next(row for row in rows if row["section"] == "watchlist_rows")
    breakout_row = next(row for row in rows if row["section"] == "repeated_breakout_rows")
    pullback_repeat_row = next(row for row in rows if row["section"] == "repeated_pullback_rows")
    exit_risk_row = next(row for row in rows if row["section"] == "repeated_exit_risk_rows")
    deferred_row = next(row for row in rows if row["section"] == "deferred_sections")

    assert pullback_row["classification_state"] == "PULLBACK_STATE_X"
    assert watchlist_row["current_watchlist_status"] == "CURRENT_PULLBACK"
    assert breakout_row["breakout_days"] == "1"
    assert pullback_repeat_row["conservative_ema20_pullback_days"] == "1"
    assert exit_risk_row["exit_risk_days"] == "3"
    assert deferred_row["deferred_section"] == "swing_ma_break_status"
    assert deferred_row["status"] == "DEFERRED"


def test_csv_full_output_is_deterministic():
    csv_text = build_csv_rolling5_canonical_v2_report(_sample_formatter_data())

    assert csv_text == (
        "section,key,value,ticker,classification_state,primary_reason,blocking_reason,"
        "next_action,current_watchlist_status,window_watchlist_status,primary_layer,"
        "primary_subindustry,layer_context_risk_status,subindustry_context_risk_status,"
        "breakout_days,pullback_days,fast_ema10_pullback_days,"
        "conservative_ema20_pullback_days,exit_risk_days,high_exit_risk_days,"
        "medium_exit_risk_days,exit_risk_severity,latest_exit_reason,first_signal_date,"
        "last_signal_date,trend_state,latest_structure_label,row_type,layer,subindustry,"
        "timing_state,overheat_risk_level,group_current_status,group_window_status,"
        "group_status_change,deferred_section,status,reason\n"
        "metadata,signal_date,2026-05-30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,taxonomy_version,DC_TAXONOMY_FULL_V1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,selected_run_id,run-5,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,status,OK,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,horizon,rolling5,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,window_start_date,2026-05-26,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,window_end_date,2026-05-30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,valid_signal_dates,5,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,group_count,4,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,window_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,rolling5_classification_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,watchlist_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,repeated_breakout_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,repeated_pullback_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,repeated_exit_risk_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "rolling5_classification_state_counts,PULLBACK_STATE_X,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "current_watchlist_status_counts,CURRENT_PULLBACK,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "window_watchlist_status_counts,WINDOW_PULLBACK,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "rolling5_pullback_rows,,,AMD,PULLBACK_STATE_X,\"PRIMARY_PULLBACK, X\",BLOCKING_X,ACTION_X,"
        "CURRENT_PULLBACK,WINDOW_PULLBACK,Infrastructure,\"Semis, Accelerators\",,,,2,1,1,3,,,MEDIUM,STRUCTURAL_WARNING,,,,,,,,,,,,,,,\n"
        "watchlist_rows,,,AMD,,,,,CURRENT_PULLBACK,WINDOW_PULLBACK,Infrastructure,\"Semis, Accelerators\",NO,LOW,1,2,,,3,,,,,,,,,,,,,,,,,,,\n"
        "repeated_breakout_rows,,,AMD,,,,,CURRENT_PULLBACK,WINDOW_PULLBACK,Infrastructure,\"Semis, Accelerators\",,,1,,,,,,,,,2026-05-26,2026-05-30,UP,HL,,,,,,,,,,,\n"
        "repeated_pullback_rows,,,AMD,,,,,CURRENT_PULLBACK,WINDOW_PULLBACK,Infrastructure,\"Semis, Accelerators\",,,,2,1,1,,,,,,2026-05-26,2026-05-30,UP,HL,,,,,,,,,,,\n"
        "repeated_exit_risk_rows,,,AMD,,,,,CURRENT_PULLBACK,WINDOW_PULLBACK,Infrastructure,\"Semis, Accelerators\",,,,,,,3,2,1,MEDIUM,STRUCTURAL_WARNING,,,UP,HL,,,,,,,,,,,\n"
        "taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,LAYER,Compute,,BUY_ZONE,LOW,GROUP_CURR_COMPUTE,GROUP_WIN_COMPUTE,UNCHANGED,,,\n"
        "taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,SUBINDUSTRY,Compute,OrphanSub,BUY_ZONE,LOW,GROUP_CURR_ORPHAN,GROUP_WIN_ORPHAN,UNCHANGED,,,\n"
        "taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,LAYER,Infrastructure,,BUY_ZONE,LOW,GROUP_CURR_INFRA,GROUP_WIN_INFRA,GROUP_CHANGE_INFRA,,,\n"
        "taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,SUBINDUSTRY,Infrastructure,\"Semis, Accelerators\",BUY_ZONE,LOW,GROUP_CURR_SEMIS,GROUP_WIN_SEMIS,GROUP_CHANGE_SEMIS,,,\n"
        "taxonomy_listing_preview,,,AMD,,,,,CURRENT_PULLBACK,WINDOW_PULLBACK,,,,,,,,,,,,,,,,,,TICKER,Infrastructure,\"Semis, Accelerators\",,,,,,,,\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,swing_ma_break_status,DEFERRED,detailed swing MA break status\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,swing_signal_freshness,DEFERRED,detailed swing signal freshness\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,technical_relevance_context,DEFERRED,full technical relevance context\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,synthetic_event_history,DEFERRED,full synthetic event history\n"
    )
