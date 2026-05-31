import csv
import io

from analysis.datacenter_indices.report_canonical_v2_rolling30_formatter_loader import (
    build_csv_rolling30_canonical_v2_report,
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_reason": "BUY_PRIMARY, X",
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
                "latest_reset_reason": None,
                "latest_reset_freshness": "STALE",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
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
                "latest_reset_reason": None,
                "latest_reset_freshness": "STALE",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
            }
        ],
        "watchlist_rows": [
            {
                "ticker": "AMD",
                "current_watchlist_status": "CURRENT_BUY_X",
                "window_watchlist_status": "WINDOW_BUY_X",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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
                "primary_subindustry": "Semis, Accelerators",
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


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_renders_required_sections():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    sections = {row["section"] for row in rows}

    assert "metadata" in sections
    assert "summary_counts" in sections
    assert "rolling30_buy_classification_state_counts" in sections
    assert "rolling30_exit_classification_state_counts" in sections
    assert "current_watchlist_status_counts" in sections
    assert "window_watchlist_status_counts" in sections
    assert "rolling30_buy_rows" in sections
    assert "rolling30_exit_rows" in sections
    assert "watchlist_rows" in sections
    assert "repeated_breakout_rows" in sections
    assert "repeated_pullback_rows" in sections
    assert "repeated_exit_risk_rows" in sections
    assert "taxonomy_listing_preview" in sections
    assert "deferred_sections" in sections


def test_csv_header_is_deterministic():
    csv_text = build_csv_rolling30_canonical_v2_report(_sample_formatter_data())
    first_line = csv_text.splitlines()[0]

    assert first_line == (
        "section,key,value,ticker,classification_state,primary_reason,"
        "blocking_reason,risk_reason,current_watchlist_status,window_watchlist_status,"
        "primary_layer,primary_subindustry,layer_context_risk_status,"
        "subindustry_context_risk_status,breakout_days,pullback_days,"
        "fast_ema10_pullback_days,conservative_ema20_pullback_days,exit_risk_days,"
        "high_exit_risk_days,medium_exit_risk_days,exit_risk_severity,"
        "latest_exit_reason,first_signal_date,last_signal_date,trend_state,"
        "latest_structure_label,row_type,layer,subindustry,timing_state,"
        "overheat_risk_level,group_current_status,group_window_status,"
        "group_status_change,deferred_section,status,reason"
    )


def test_csv_preserves_stored_buy_classification_values_without_next_action_column():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "rolling30_buy_rows")

    assert row["ticker"] == "AMD"
    assert row["classification_state"] == "BUY_STATE_X"
    assert row["primary_reason"] == "BUY_PRIMARY, X"
    assert row["blocking_reason"] == "BUY_BLOCK_X"
    assert "next_action" not in row


def test_csv_preserves_stored_exit_classification_values_without_next_action_column():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "rolling30_exit_rows")

    assert row["ticker"] == "AMD"
    assert row["classification_state"] == "EXIT_STATE_X"
    assert row["primary_reason"] == "EXIT_PRIMARY_X"
    assert row["risk_reason"] == "EXIT_RISK_X"
    assert "next_action" not in row


def test_csv_preserves_stored_watchlist_values():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "watchlist_rows")

    assert row["current_watchlist_status"] == "CURRENT_BUY_X"
    assert row["window_watchlist_status"] == "WINDOW_BUY_X"
    assert row["layer_context_risk_status"] == "NO"
    assert row["subindustry_context_risk_status"] == "LOW"


def test_csv_repeated_rows_use_stored_counts():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    breakout = next(row for row in rows if row["section"] == "repeated_breakout_rows")
    pullback = next(row for row in rows if row["section"] == "repeated_pullback_rows")
    exit_risk = next(row for row in rows if row["section"] == "repeated_exit_risk_rows")

    assert breakout["breakout_days"] == "3"
    assert pullback["pullback_days"] == "2"
    assert pullback["fast_ema10_pullback_days"] == "1"
    assert pullback["conservative_ema20_pullback_days"] == "1"
    assert exit_risk["exit_risk_days"] == "4"
    assert exit_risk["high_exit_risk_days"] == "2"
    assert exit_risk["medium_exit_risk_days"] == "2"


def test_csv_preserves_taxonomy_listing_semantics_including_orphan_group():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    orphan = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview"
        and row["row_type"] == "SUBINDUSTRY"
        and row["layer"] == "Compute"
        and row["subindustry"] == "OrphanSub"
    )
    ticker = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview"
        and row["row_type"] == "TICKER"
        and row["ticker"] == "AMD"
    )

    assert orphan["group_current_status"] == "GROUP_CURR_ORPHAN"
    assert orphan["group_window_status"] == "GROUP_WIN_ORPHAN"
    assert orphan["group_status_change"] == "UNCHANGED"
    assert orphan["ticker"] == ""
    assert ticker["current_watchlist_status"] == "CURRENT_BUY_X"
    assert ticker["window_watchlist_status"] == "WINDOW_BUY_X"


def test_csv_renders_deterministic_zero_watchlist_behavior():
    formatter_data = _sample_formatter_data()
    formatter_data["watchlist_rows"] = []
    formatter_data["section_counts"] = {
        **dict(formatter_data["section_counts"]),
        "watchlist_row_count": 0,
    }

    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(formatter_data))
    sections = {row["section"] for row in rows}
    watchlist_rows = [row for row in rows if row["section"] == "watchlist_rows"]
    summary_watchlist = next(
        row for row in rows if row["section"] == "summary_counts" and row["key"] == "watchlist_row_count"
    )

    assert rows
    assert sections >= {"metadata", "rolling30_buy_rows", "rolling30_exit_rows", "deferred_sections"}
    assert summary_watchlist["value"] == "0"
    assert watchlist_rows == []


def test_csv_renders_none_values_as_empty_strings():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    buy_row = next(row for row in rows if row["section"] == "rolling30_buy_rows")
    exit_row = next(row for row in rows if row["section"] == "rolling30_exit_rows")

    assert buy_row["risk_reason"] == ""
    assert exit_row["blocking_reason"] == ""


def test_csv_escaping_round_trips_comma_values():
    rows = _parse_csv(build_csv_rolling30_canonical_v2_report(_sample_formatter_data()))
    buy_row = next(row for row in rows if row["section"] == "rolling30_buy_rows")
    watchlist_row = next(row for row in rows if row["section"] == "watchlist_rows")

    assert buy_row["primary_reason"] == "BUY_PRIMARY, X"
    assert watchlist_row["primary_subindustry"] == "Semis, Accelerators"


def test_csv_is_pure_in_memory_without_db_or_source_tables():
    csv_text = build_csv_rolling30_canonical_v2_report(_sample_formatter_data())

    assert "rolling30_buy_rows" in csv_text
    assert "rolling30_exit_rows" in csv_text
    assert "BUY_STATE_X" in csv_text
    assert "EXIT_STATE_X" in csv_text


def test_csv_full_output_is_deterministic():
    csv_text = build_csv_rolling30_canonical_v2_report(_sample_formatter_data())

    assert csv_text == """section,key,value,ticker,classification_state,primary_reason,blocking_reason,risk_reason,current_watchlist_status,window_watchlist_status,primary_layer,primary_subindustry,layer_context_risk_status,subindustry_context_risk_status,breakout_days,pullback_days,fast_ema10_pullback_days,conservative_ema20_pullback_days,exit_risk_days,high_exit_risk_days,medium_exit_risk_days,exit_risk_severity,latest_exit_reason,first_signal_date,last_signal_date,trend_state,latest_structure_label,row_type,layer,subindustry,timing_state,overheat_risk_level,group_current_status,group_window_status,group_status_change,deferred_section,status,reason
metadata,signal_date,2026-05-30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,taxonomy_version,DC_TAXONOMY_FULL_V1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,selected_run_id,run-30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,status,OK,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,horizon,rolling30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,window_start_date,2026-05-01,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,window_end_date,2026-05-30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
metadata,valid_signal_dates,30,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,group_count,4,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,window_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,rolling30_buy_classification_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,rolling30_exit_classification_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,watchlist_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,repeated_breakout_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,repeated_pullback_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
summary_counts,repeated_exit_risk_row_count,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
rolling30_buy_classification_state_counts,BUY_STATE_X,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
rolling30_exit_classification_state_counts,EXIT_STATE_X,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
current_watchlist_status_counts,CURRENT_BUY_X,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
window_watchlist_status_counts,WINDOW_BUY_X,1,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
rolling30_buy_rows,,,AMD,BUY_STATE_X,"BUY_PRIMARY, X",BUY_BLOCK_X,,CURRENT_BUY_X,WINDOW_BUY_X,Infrastructure,"Semis, Accelerators",,,3,2,,,4,,,HIGH,EXIT_REASON_X,,,UP,HL,,,,,,,,,,,
rolling30_exit_rows,,,AMD,EXIT_STATE_X,EXIT_PRIMARY_X,,EXIT_RISK_X,CURRENT_BUY_X,WINDOW_BUY_X,Infrastructure,"Semis, Accelerators",,,,,,,4,2,2,HIGH,EXIT_REASON_X,,,UP,HL,,,,,,,,,,,
watchlist_rows,,,AMD,,,,,CURRENT_BUY_X,WINDOW_BUY_X,Infrastructure,"Semis, Accelerators",NO,LOW,3,2,,,4,,,,,,,,,,,,,,,,,,,
repeated_breakout_rows,,,AMD,,,,,CURRENT_BUY_X,WINDOW_BUY_X,Infrastructure,"Semis, Accelerators",,,3,,,,,,,,,2026-05-01,2026-05-30,UP,HL,,,,,,,,,,,
repeated_pullback_rows,,,AMD,,,,,CURRENT_BUY_X,WINDOW_BUY_X,Infrastructure,"Semis, Accelerators",,,,2,1,1,,,,,,2026-05-01,2026-05-30,UP,HL,,,,,,,,,,,
repeated_exit_risk_rows,,,AMD,,,,,CURRENT_BUY_X,WINDOW_BUY_X,Infrastructure,"Semis, Accelerators",,,,,,,4,2,2,HIGH,EXIT_REASON_X,,,UP,HL,,,,,,,,,,,
taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,LAYER,Compute,,BUY_ZONE,LOW,GROUP_CURR_COMPUTE,GROUP_WIN_COMPUTE,UNCHANGED,,,
taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,SUBINDUSTRY,Compute,OrphanSub,BUY_ZONE,LOW,GROUP_CURR_ORPHAN,GROUP_WIN_ORPHAN,UNCHANGED,,,
taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,LAYER,Infrastructure,,BUY_ZONE,LOW,GROUP_CURR_INFRA,GROUP_WIN_INFRA,GROUP_CHANGE_INFRA,,,
taxonomy_listing_preview,,,,,,,,,,,,,,,,,,,,,,,,,,,SUBINDUSTRY,Infrastructure,"Semis, Accelerators",BUY_ZONE,LOW,GROUP_CURR_SEMIS,GROUP_WIN_SEMIS,GROUP_CHANGE_SEMIS,,,
taxonomy_listing_preview,,,AMD,,,,,CURRENT_BUY_X,WINDOW_BUY_X,,,,,,,,,,,,,,,,,,TICKER,Infrastructure,"Semis, Accelerators",,,,,,,,
deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,swing_ma_break_status,DEFERRED,detailed swing MA break status
deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,swing_signal_freshness,DEFERRED,detailed swing signal freshness
deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,technical_relevance_context,DEFERRED,full technical relevance context
deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,synthetic_event_history,DEFERRED,full synthetic event history
"""
