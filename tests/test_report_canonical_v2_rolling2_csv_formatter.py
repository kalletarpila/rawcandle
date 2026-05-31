import csv
import io

from analysis.datacenter_indices.report_canonical_v2_rolling2_formatter_loader import (
    build_csv_rolling2_canonical_v2_report,
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_reason": "PRIMARY, X",
                "risk_reason": "RISK_X",
                "next_action": "ACTION_X",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "exit_risk_days": 3,
                "high_exit_risk_days": 2,
                "medium_exit_risk_days": 1,
                "exit_risk_severity": "HIGH",
                "latest_exit_reason": "PRICE_BREAK",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
            }
        ],
        "watchlist_rows": [
            {
                "ticker": "NVDA",
                "current_watchlist_status": "CURRENT_ALPHA",
                "window_watchlist_status": "WINDOW_ALPHA",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "current_watchlist_status": None,
                "window_watchlist_status": None,
            },
            {
                "row_type": "TICKER",
                "layer": "Infrastructure",
                "subindustry": "Semis, Accelerators",
                "ticker": "NVDA",
                "timing_state": None,
                "overheat_risk_level": None,
                "group_current_status": None,
                "group_window_status": None,
                "group_status_change": None,
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


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_renders_required_sections():
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))
    sections = {row["section"] for row in rows}

    assert "metadata" in sections
    assert "summary_counts" in sections
    assert "rolling2_classification_state_counts" in sections
    assert "current_watchlist_status_counts" in sections
    assert "window_watchlist_status_counts" in sections
    assert "rolling2_sell_pressure_rows" in sections
    assert "watchlist_rows" in sections
    assert "repeated_breakout_rows" in sections
    assert "repeated_pullback_rows" in sections
    assert "repeated_exit_risk_rows" in sections
    assert "taxonomy_listing_preview" in sections
    assert "deferred_sections" in sections


def test_csv_header_is_deterministic():
    csv_text = build_csv_rolling2_canonical_v2_report(_sample_formatter_data())
    first_line = csv_text.splitlines()[0]

    assert first_line == (
        "section,key,value,ticker,classification_state,primary_reason,"
        "risk_reason,next_action,current_watchlist_status,window_watchlist_status,"
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
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "rolling2_sell_pressure_rows")

    assert row["ticker"] == "NVDA"
    assert row["classification_state"] == "SELL_PRESSURE_X"
    assert row["primary_reason"] == "PRIMARY, X"
    assert row["risk_reason"] == "RISK_X"
    assert row["next_action"] == "ACTION_X"


def test_csv_preserves_stored_watchlist_values():
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "watchlist_rows")

    assert row["current_watchlist_status"] == "CURRENT_ALPHA"
    assert row["window_watchlist_status"] == "WINDOW_ALPHA"
    assert row["layer_context_risk_status"] == "NO"
    assert row["subindustry_context_risk_status"] == "LOW"


def test_csv_preserves_repeated_row_counts_by_section():
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))

    breakout_row = next(row for row in rows if row["section"] == "repeated_breakout_rows")
    pullback_row = next(row for row in rows if row["section"] == "repeated_pullback_rows")
    exit_risk_row = next(row for row in rows if row["section"] == "repeated_exit_risk_rows")

    assert breakout_row["breakout_days"] == "2"
    assert pullback_row["pullback_days"] == "1"
    assert pullback_row["fast_ema10_pullback_days"] == "1"
    assert pullback_row["conservative_ema20_pullback_days"] == "1"
    assert exit_risk_row["exit_risk_days"] == "3"
    assert exit_risk_row["high_exit_risk_days"] == "2"
    assert exit_risk_row["medium_exit_risk_days"] == "1"


def test_csv_preserves_taxonomy_field_semantics():
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))
    group_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "LAYER"
    )
    ticker_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "TICKER"
    )

    assert group_row["group_current_status"] == "GROUP_CURR_X"
    assert group_row["group_window_status"] == "GROUP_WIN_X"
    assert group_row["group_status_change"] == "GROUP_CHANGE_X"
    assert group_row["current_watchlist_status"] == ""
    assert ticker_row["group_current_status"] == ""
    assert ticker_row["group_window_status"] == ""
    assert ticker_row["group_status_change"] == ""
    assert ticker_row["current_watchlist_status"] == "CURRENT_ALPHA"
    assert ticker_row["window_watchlist_status"] == "WINDOW_ALPHA"


def test_csv_none_values_render_as_empty_strings():
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))

    assert all("None" not in row.values() for row in rows)


def test_csv_escaping_round_trips_through_csv_module():
    rows = _parse_csv(build_csv_rolling2_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "rolling2_sell_pressure_rows")

    assert row["primary_reason"] == "PRIMARY, X"
    assert row["primary_subindustry"] == "Semis, Accelerators"


def test_csv_formatter_is_pure_in_memory_without_db_setup():
    formatter_data = _sample_formatter_data()

    csv_text = build_csv_rolling2_canonical_v2_report(formatter_data)
    rows = _parse_csv(csv_text)

    assert csv_text
    assert csv_text.startswith("section,key,value,")

    sell_pressure_row = next(row for row in rows if row["section"] == "rolling2_sell_pressure_rows")
    watchlist_row = next(row for row in rows if row["section"] == "watchlist_rows")
    breakout_row = next(row for row in rows if row["section"] == "repeated_breakout_rows")
    pullback_row = next(row for row in rows if row["section"] == "repeated_pullback_rows")
    exit_risk_row = next(row for row in rows if row["section"] == "repeated_exit_risk_rows")
    deferred_row = next(row for row in rows if row["section"] == "deferred_sections")

    assert sell_pressure_row["classification_state"] == "SELL_PRESSURE_X"
    assert watchlist_row["current_watchlist_status"] == "CURRENT_ALPHA"
    assert breakout_row["breakout_days"] == "2"
    assert pullback_row["conservative_ema20_pullback_days"] == "1"
    assert exit_risk_row["exit_risk_days"] == "3"
    assert deferred_row["deferred_section"] == "swing_ma_break_status"
    assert deferred_row["status"] == "DEFERRED"


def test_csv_zero_watchlist_output_is_deterministic():
    formatter_data = _sample_formatter_data()
    formatter_data["watchlist_rows"] = []
    formatter_data["section_counts"] = {
        **dict(formatter_data["section_counts"]),
        "watchlist_row_count": 0,
    }

    csv_text = build_csv_rolling2_canonical_v2_report(formatter_data)
    rows = _parse_csv(csv_text)
    sections = {row["section"] for row in rows}

    assert csv_text
    assert csv_text.startswith("section,key,value,")
    assert "metadata" in sections
    assert "rolling2_sell_pressure_rows" in sections
    assert "deferred_sections" in sections

    watchlist_summary_row = next(
        row
        for row in rows
        if row["section"] == "summary_counts" and row["key"] == "watchlist_row_count"
    )
    watchlist_data_rows = [row for row in rows if row["section"] == "watchlist_rows"]

    assert watchlist_summary_row["value"] == "0"
    assert watchlist_data_rows == []


def test_csv_full_output_is_deterministic():
    csv_text = build_csv_rolling2_canonical_v2_report(_sample_formatter_data())

    assert csv_text == (
        "section,key,value,ticker,classification_state,primary_reason,risk_reason,"
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
        "metadata,selected_run_id,run-1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,status,OK,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,horizon,rolling2,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,window_start_date,2026-05-29,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,window_end_date,2026-05-30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,valid_signal_dates,2,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,group_count,2,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,window_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,rolling2_classification_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,watchlist_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,repeated_breakout_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,repeated_pullback_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,repeated_exit_risk_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "rolling2_classification_state_counts,SELL_PRESSURE_X,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "current_watchlist_status_counts,CURRENT_ALPHA,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "window_watchlist_status_counts,WINDOW_ALPHA,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "rolling2_sell_pressure_rows,,,NVDA,SELL_PRESSURE_X,\"PRIMARY, X\",RISK_X,ACTION_X,"
        "CURRENT_ALPHA,WINDOW_ALPHA,Infrastructure,\"Semis, Accelerators\",,,,,,,3,2,1,HIGH,PRICE_BREAK,,,,,,,,,,,,,,,\n"
        "watchlist_rows,,,NVDA,,,,,CURRENT_ALPHA,WINDOW_ALPHA,Infrastructure,\"Semis, Accelerators\",NO,LOW,2,1,,,3,,,,,,,,,,,,,,,,,,,\n"
        "repeated_breakout_rows,,,NVDA,,,,,CURRENT_ALPHA,WINDOW_ALPHA,Infrastructure,\"Semis, Accelerators\",,,2,,,,,,,,,2026-05-29,2026-05-30,UP,HL,,,,,,,,,,,\n"
        "repeated_pullback_rows,,,NVDA,,,,,CURRENT_ALPHA,WINDOW_ALPHA,Infrastructure,\"Semis, Accelerators\",,,,"
        "1,1,1,,,,,,2026-05-29,2026-05-30,UP,HL,,,,,,,,,,,\n"
        "repeated_exit_risk_rows,,,NVDA,,,,,CURRENT_ALPHA,WINDOW_ALPHA,Infrastructure,\"Semis, Accelerators\",,,,,,,3,2,1,HIGH,PRICE_BREAK,,,UP,HL,,,,,,,,,,,\n"
        "taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,LAYER,Infrastructure,,BUY_ZONE,LOW,GROUP_CURR_X,GROUP_WIN_X,GROUP_CHANGE_X,,,\n"
        "taxonomy_listing_preview,,,NVDA,,,,,CURRENT_ALPHA,WINDOW_ALPHA,,,,,,,,,,,,,,,,,,TICKER,Infrastructure,\"Semis, Accelerators\",,,,,,,,\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,swing_ma_break_status,DEFERRED,detailed swing MA break status\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,swing_signal_freshness,DEFERRED,detailed swing signal freshness\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,technical_relevance_context,DEFERRED,full technical relevance context\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,synthetic_event_history,DEFERRED,full synthetic event history\n"
    )
