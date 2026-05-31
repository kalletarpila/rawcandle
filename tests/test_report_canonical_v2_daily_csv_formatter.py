import csv
import io

from analysis.datacenter_indices.report_canonical_v2_daily_formatter_loader import (
    build_csv_daily_canonical_v2_report,
)


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
        "group_rows": [],
        "ticker_rows": [],
        "daily_trigger_rows": [
            {
                "ticker": "NVDA",
                "classification_state": "BUY_WATCH",
                "primary_reason": "BULLISH, SETUP / NEEDS CONFIRMATION",
                "blocking_reason": None,
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
                "overheat_risk_level": "LOW",
                "pct_above_ema20": 62.5,
                "pct_above_ma10": 71.0,
                "distance_to_ema20_pct": None,
                "current_watchlist_status": None,
            },
            {
                "row_type": "TICKER",
                "layer": "Infrastructure",
                "subindustry": "Semis",
                "ticker": "NVDA",
                "status": None,
                "overheat_risk_level": None,
                "pct_above_ema20": None,
                "pct_above_ma10": None,
                "distance_to_ema20_pct": 1.2345,
                "current_watchlist_status": "BREAKOUT_CANDIDATE",
            },
        ],
        "section_counts": {
            "ticker_row_count": 1,
            "group_row_count": 1,
            "daily_trigger_row_count": 1,
            "watchlist_row_count": 1,
            "taxonomy_listing_row_count": 2,
            "daily_trigger_state_counts": {"BUY_WATCH": 1},
            "watchlist_status_counts": {"BREAKOUT_CANDIDATE": 1},
        },
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
        },
    }


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_renders_required_sections():
    rows = _parse_csv(build_csv_daily_canonical_v2_report(_sample_formatter_data()))
    sections = {row["section"] for row in rows}

    assert "metadata" in sections
    assert "summary_counts" in sections
    assert "trigger_state_counts" in sections
    assert "watchlist_status_counts" in sections
    assert "daily_trigger_rows" in sections
    assert "watchlist_rows" in sections
    assert "taxonomy_listing_preview" in sections
    assert "deferred_sections" in sections


def test_csv_header_is_deterministic():
    csv_text = build_csv_daily_canonical_v2_report(_sample_formatter_data())
    first_line = csv_text.splitlines()[0]

    assert first_line == (
        "section,key,value,ticker,classification_state,primary_reason,"
        "blocking_reason,next_action,current_watchlist_status,primary_layer,"
        "primary_subindustry,layer_context_risk_status,subindustry_context_risk_status,"
        "breakout_signal,pullback_signal,exit_risk_signal,row_type,layer,subindustry,"
        "timing_state,overheat_risk_level,pct_above_ema20,pct_above_ma10,"
        "distance_to_ema20_pct,deferred_section,status,reason"
    )


def test_csv_preserves_stored_classification_values():
    rows = _parse_csv(build_csv_daily_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "daily_trigger_rows")

    assert row["ticker"] == "NVDA"
    assert row["classification_state"] == "BUY_WATCH"
    assert row["primary_reason"] == "BULLISH, SETUP / NEEDS CONFIRMATION"
    assert row["blocking_reason"] == ""
    assert row["next_action"] == "MONITOR_FOR_DAILY_CONFIRMATION"


def test_csv_preserves_stored_watchlist_values():
    rows = _parse_csv(build_csv_daily_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "watchlist_rows")

    assert row["current_watchlist_status"] == "BREAKOUT_CANDIDATE"
    assert row["layer_context_risk_status"] == "NO"
    assert row["subindustry_context_risk_status"] == "NO"


def test_csv_preserves_taxonomy_field_semantics():
    rows = _parse_csv(build_csv_daily_canonical_v2_report(_sample_formatter_data()))
    layer_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "LAYER"
    )
    ticker_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "TICKER"
    )

    assert layer_row["pct_above_ema20"] == "62.5"
    assert layer_row["pct_above_ma10"] == "71.0"
    assert layer_row["distance_to_ema20_pct"] == ""
    assert ticker_row["pct_above_ema20"] == ""
    assert ticker_row["pct_above_ma10"] == ""
    assert ticker_row["distance_to_ema20_pct"] == "1.2345"


def test_csv_none_values_render_as_empty_strings():
    rows = _parse_csv(build_csv_daily_canonical_v2_report(_sample_formatter_data()))

    assert all("None" not in row.values() for row in rows)


def test_csv_escaping_round_trips_through_csv_module():
    rows = _parse_csv(build_csv_daily_canonical_v2_report(_sample_formatter_data()))
    row = next(row for row in rows if row["section"] == "daily_trigger_rows")

    assert row["primary_reason"] == "BULLISH, SETUP / NEEDS CONFIRMATION"


def test_csv_formatter_is_pure_in_memory_without_db_setup():
    formatter_data = _sample_formatter_data()

    csv_text = build_csv_daily_canonical_v2_report(formatter_data)
    rows = _parse_csv(csv_text)

    assert csv_text
    assert csv_text.startswith("section,key,value,")

    daily_trigger_row = next(row for row in rows if row["section"] == "daily_trigger_rows")
    watchlist_row = next(row for row in rows if row["section"] == "watchlist_rows")
    group_taxonomy_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "LAYER"
    )
    ticker_taxonomy_row = next(
        row
        for row in rows
        if row["section"] == "taxonomy_listing_preview" and row["row_type"] == "TICKER"
    )
    deferred_row = next(row for row in rows if row["section"] == "deferred_sections")

    assert daily_trigger_row["classification_state"] == "BUY_WATCH"
    assert watchlist_row["current_watchlist_status"] == "BREAKOUT_CANDIDATE"
    assert group_taxonomy_row["pct_above_ema20"] == "62.5"
    assert ticker_taxonomy_row["distance_to_ema20_pct"] == "1.2345"
    assert deferred_row["deferred_section"] == "swing_ma_break_status"
    assert deferred_row["status"] == "DEFERRED"


def test_csv_full_output_is_deterministic():
    csv_text = build_csv_daily_canonical_v2_report(_sample_formatter_data())

    assert csv_text == (
        "section,key,value,ticker,classification_state,primary_reason,blocking_reason,"
        "next_action,current_watchlist_status,primary_layer,primary_subindustry,"
        "layer_context_risk_status,subindustry_context_risk_status,breakout_signal,"
        "pullback_signal,exit_risk_signal,row_type,layer,subindustry,timing_state,"
        "overheat_risk_level,pct_above_ema20,pct_above_ma10,distance_to_ema20_pct,"
        "deferred_section,status,reason\n"
        "metadata,signal_date,2026-05-30,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,taxonomy_version,DC_TAXONOMY_FULL_V1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,selected_run_id,run-1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "metadata,status,OK,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,ticker_count,1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,group_count,1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,daily_trigger_count,1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "summary_counts,watchlist_count,1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "trigger_state_counts,BUY_WATCH,1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "watchlist_status_counts,BREAKOUT_CANDIDATE,1,,,,,,,,,,,,,,,,,,,,,,,,\n"
        "daily_trigger_rows,,,NVDA,BUY_WATCH,\"BULLISH, SETUP / NEEDS CONFIRMATION\",,"
        "MONITOR_FOR_DAILY_CONFIRMATION,BREAKOUT_CANDIDATE,Infrastructure,Semis,,,,,,,,,,,,,,,,\n"
        "watchlist_rows,,,NVDA,,,,,BREAKOUT_CANDIDATE,Infrastructure,Semis,NO,NO,1,0,0,,,,,,,,,,,\n"
        "taxonomy_listing_preview,,,,,,,,,,,,,,,,LAYER,Infrastructure,,BUY_ZONE,LOW,62.5,71.0,,,,\n"
        "taxonomy_listing_preview,,,NVDA,,,,,BREAKOUT_CANDIDATE,,,,,,,,TICKER,Infrastructure,Semis,,,,,1.2345,,,\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,swing_ma_break_status,DEFERRED,detailed swing MA break status\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,swing_signal_freshness,DEFERRED,detailed swing signal freshness\n"
        "deferred_sections,,,,,,,,,,,,,,,,,,,,,,,,technical_relevance_context,DEFERRED,full technical relevance context\n"
    )
