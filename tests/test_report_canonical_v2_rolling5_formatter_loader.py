import sqlite3

from analysis.datacenter_indices.report_canonical_v2_rolling5_formatter_loader import (
    load_rolling5_canonical_formatter_data_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
    return conn


def _insert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    created_at_utc: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    market: str | None = "usa",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id, signal_date, taxonomy_version, market, calculation_version,
            source_versions_json, created_at_utc, status, warning_count, error_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            market,
            "REPORT_CANONICAL_V2",
            None,
            created_at_utc,
            "OK",
            0,
            0,
            None,
        ),
    )


def _insert_group_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    group_type: str,
    group_name: str,
    parent_group_type: str | None = None,
    parent_group_name: str | None = None,
    market: str | None = "usa",
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
    group_context_risk_status: str = "NO",
    group_current_status: str = "BUY_ZONE",
    group_window_status: str = "BUY_ZONE",
    group_status_change: str = "UNCHANGED",
    synthetic_trend_classification: str = "UP",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            parent_group_type, parent_group_name,
            timing_state, overheat_risk_level, return_2d, return_5d, return_30d,
            breadth_json, synthetic_close, synthetic_ema_distance_json,
            synthetic_trend_classification, synthetic_latest_structure_label,
            synthetic_latest_bos_event_type, synthetic_latest_bos_freshness,
            synthetic_latest_reset_reason, synthetic_latest_reset_freshness,
            group_context_risk_status, group_context_readiness_status, group_current_status,
            group_window_status, group_status_change, window_start_date, window_end_date,
            valid_signal_dates, run_id, created_at_utc
        ) VALUES (?, ?, ?, 'rolling5', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            1.0,
            2.0,
            8.0,
            None,
            150.0,
            None,
            synthetic_trend_classification,
            "HL",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
            group_context_risk_status,
            "OK",
            group_current_status,
            group_window_status,
            group_status_change,
            "2026-05-26",
            "2026-05-30",
            5,
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_window_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    primary_layer: str,
    primary_subindustry: str,
    market: str | None = "usa",
    is_watchlist: int = 1,
    in_datacenter_ecosystem: int = 1,
    current_watchlist_status: str = "PULLBACK_CANDIDATE",
    window_watchlist_status: str = "PULLBACK_CANDIDATE",
    breakout_days: int = 0,
    pullback_days: int = 0,
    fast_ema10_pullback_days: int = 0,
    conservative_ema20_pullback_days: int = 0,
    exit_risk_days: int = 0,
    high_exit_risk_days: int = 0,
    medium_exit_risk_days: int = 0,
    latest_exit_reason: str | None = None,
    exit_risk_severity: str | None = None,
) -> None:
    row = {
        "signal_date": "2026-05-30",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "market": market,
        "ticker": ticker,
        "horizon": "rolling5",
        "window_start_date": "2026-05-26",
        "window_end_date": "2026-05-30",
        "valid_signal_dates": 5,
        "incomplete_window": 0,
        "primary_layer": primary_layer,
        "primary_subindustry": primary_subindustry,
        "in_datacenter_ecosystem": in_datacenter_ecosystem,
        "is_watchlist": is_watchlist,
        "current_watchlist_status": current_watchlist_status,
        "window_watchlist_status": window_watchlist_status,
        "breakout_days": breakout_days,
        "pullback_days": pullback_days,
        "fast_ema10_pullback_days": fast_ema10_pullback_days,
        "conservative_ema20_pullback_days": conservative_ema20_pullback_days,
        "exit_risk_days": exit_risk_days,
        "high_exit_risk_days": high_exit_risk_days,
        "medium_exit_risk_days": medium_exit_risk_days,
        "first_signal_date": "2026-05-26",
        "last_signal_date": "2026-05-30",
        "latest_exit_reason": latest_exit_reason,
        "layer_timing_state": "BUY_ZONE",
        "layer_overheat_risk_level": "LOW",
        "layer_context_risk_status": "NO",
        "subindustry_timing_state": "BUY_ZONE",
        "subindustry_overheat_risk_level": "LOW",
        "subindustry_context_risk_status": "NO",
        "trend_state": "UP",
        "latest_structure_label": "HL",
        "latest_structure_freshness": "FRESH",
        "latest_bos_event_type": "BOS_UP",
        "latest_bos_freshness": "FRESH",
        "latest_reset_reason": "NONE",
        "latest_reset_freshness": "STALE",
        "ma_break_status": "ABOVE_MA_STACK",
        "freshness_status": "CURRENT",
        "technical_relevance_status": "RELEVANT",
        "technical_relevance_reason": "token",
        "close_below_ema20_flag": 0,
        "close_below_ema50_flag": 0,
        "return_10d_lt_minus_8pct_flag": 0,
        "double_bos_down_flag": 0,
        "double_bos_up_flag": 0,
        "fresh_bos_flag": 1 if breakout_days > 0 else 0,
        "fresh_reset_flag": 0,
        "stale_structure_flag": 0,
        "layer_overheat_risk_flag": 0,
        "subindustry_overheat_risk_flag": 0,
        "severe_exit_risk_flag": 1 if exit_risk_severity in {"HIGH", "EXTREME", "CRITICAL"} else 0,
        "context_readiness_status": "OK",
        "run_id": run_id,
        "created_at_utc": "2026-05-30T00:00:00Z",
        "price_data_status": "OK",
        "exit_risk_severity": exit_risk_severity,
        "latest_bearish_relevance_class": "BEARISH_TOKEN",
        "distance_to_ema20_pct": 2.5,
        "all_price_rows_missing": 0,
    }
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    conn.execute(
        f"""
        INSERT INTO dc_report_context_window_v2 ({columns})
        VALUES ({placeholders})
        """,
        row,
    )


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    market: str | None = "usa",
    classification_state: str = "PULLBACK_CANDIDATE",
    primary_reason: str = "MULTI_DAY_PULLBACK",
    blocking_reason: str | None = None,
    next_action: str = "MONITOR_FOR_RECLAIM",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, market, ticker, horizon, classification_type,
            classification_state, primary_reason, blocking_reason, risk_reason, next_action,
            classification_status, classification_version, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, 'rolling5', 'rolling5_pullback', ?, ?, ?, ?, ?, 'OK', ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            ticker,
            classification_state,
            primary_reason,
            blocking_reason,
            None,
            next_action,
            "REPORT_ROLLING5_PULLBACK_CLASSIFIER_V2_1",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def test_loader_reads_canonical_rolling5_data():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
    _insert_window_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis", pullback_days=2)
    _insert_classification_row(conn, run_id="run-1", ticker="NVDA")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert set(data) == {
        "metadata",
        "run",
        "group_rows",
        "window_rows",
        "rolling5_pullback_rows",
        "watchlist_rows",
        "repeated_breakout_rows",
        "repeated_pullback_rows",
        "repeated_exit_risk_rows",
        "taxonomy_listing_rows",
        "section_counts",
        "deferred_sections",
    }


def test_loader_does_not_require_source_tables():
    conn = _connect()
    tables = conn.execute(
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
    assert tables == []

    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert data["run"]["run_id"] == "run-1"


def test_run_selection_behavior():
    conn = _connect()
    _insert_run(conn, run_id="run-a", created_at_utc="2026-05-30T00:00:00Z")
    _insert_run(conn, run_id="run-b", created_at_utc="2026-05-30T00:00:00Z")
    _insert_run(conn, run_id="run-c", created_at_utc="2026-05-30T01:00:00Z")
    conn.commit()

    latest = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )
    explicit = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        run_id="run-a",
    )

    assert latest["run"]["run_id"] == "run-c"
    assert explicit["run"]["run_id"] == "run-a"


def test_missing_run_behavior_still_loads_canonical_rows():
    conn = _connect()
    _insert_run(conn, run_id="actual-run", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="actual-run", group_type="layer", group_name="Infrastructure")
    _insert_group_row(
        conn,
        run_id="actual-run",
        group_type="subindustry",
        group_name="Semis",
        parent_group_type="layer",
        parent_group_name="Infrastructure",
    )
    _insert_window_row(
        conn,
        run_id="actual-run",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        pullback_days=2,
    )
    _insert_classification_row(conn, run_id="actual-run", ticker="NVDA")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        run_id="MISSING_RUN_ID",
    )

    assert data["run"] is None
    assert data["metadata"]["selected_run_id"] is None
    assert [row["group_name"] for row in data["group_rows"]] == ["Infrastructure", "Semis"]
    assert [row["ticker"] for row in data["window_rows"]] == ["NVDA"]
    assert [row["ticker"] for row in data["rolling5_pullback_rows"]] == ["NVDA"]


def test_market_filtering():
    conn = _connect()
    _insert_run(conn, run_id="usa-run", created_at_utc="2026-05-30T00:00:00Z", market="usa")
    _insert_run(conn, run_id="omxh-run", created_at_utc="2026-05-30T00:00:00Z", market="omxh")
    _insert_group_row(conn, run_id="usa-run", group_type="layer", group_name="Infrastructure", market="usa")
    _insert_group_row(conn, run_id="omxh-run", group_type="layer", group_name="NordicInfra", market="omxh")
    _insert_window_row(conn, run_id="usa-run", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis", market="usa")
    _insert_window_row(conn, run_id="omxh-run", ticker="NOKIA", primary_layer="NordicInfra", primary_subindustry="NordicSemis", market="omxh")
    _insert_classification_row(conn, run_id="usa-run", ticker="NVDA", market="usa")
    _insert_classification_row(conn, run_id="omxh-run", ticker="NOKIA", market="omxh")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert [row["ticker"] for row in data["window_rows"]] == ["NVDA"]
    assert [row["ticker"] for row in data["rolling5_pullback_rows"]] == ["NVDA"]
    assert [row["group_name"] for row in data["group_rows"]] == ["Infrastructure"]


def test_rolling5_classification_join_uses_stored_classification():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        current_watchlist_status="PULLBACK_CANDIDATE",
        window_watchlist_status="PULLBACK_CANDIDATE",
        pullback_days=2,
        fast_ema10_pullback_days=1,
        conservative_ema20_pullback_days=1,
        exit_risk_days=1,
        latest_exit_reason="STRUCTURAL_WARNING",
        exit_risk_severity="MEDIUM",
    )
    _insert_classification_row(
        conn,
        run_id="run-1",
        ticker="NVDA",
        classification_state="EARLY_PULLBACK",
        primary_reason="EARLY_PULLBACK_SIGNAL",
        blocking_reason="NEEDS_RECLAIM",
        next_action="WAIT_FOR_CONFIRMATION",
    )
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    row = data["rolling5_pullback_rows"][0]
    assert row["ticker"] == "NVDA"
    assert row["classification_state"] == "EARLY_PULLBACK"
    assert row["primary_reason"] == "EARLY_PULLBACK_SIGNAL"
    assert row["blocking_reason"] == "NEEDS_RECLAIM"
    assert row["next_action"] == "WAIT_FOR_CONFIRMATION"
    assert row["current_watchlist_status"] == "PULLBACK_CANDIDATE"
    assert row["window_watchlist_status"] == "PULLBACK_CANDIDATE"
    assert row["primary_layer"] == "Infrastructure"
    assert row["primary_subindustry"] == "Semis"


def test_watchlist_rows_use_stored_status():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="AMD",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        current_watchlist_status="EARLY_PULLBACK",
        window_watchlist_status="GROUP_RISK",
        pullback_days=1,
    )
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        current_watchlist_status="FAILED_PULLBACK",
        window_watchlist_status="FAILED_PULLBACK",
        exit_risk_days=2,
        high_exit_risk_days=1,
        exit_risk_severity="HIGH",
    )
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert [
        (row["ticker"], row["current_watchlist_status"], row["window_watchlist_status"])
        for row in data["watchlist_rows"]
    ] == [
        ("AMD", "EARLY_PULLBACK", "GROUP_RISK"),
        ("NVDA", "FAILED_PULLBACK", "FAILED_PULLBACK"),
    ]


def test_repeated_rows_use_stored_counts():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="EXIT",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        exit_risk_days=2,
        high_exit_risk_days=1,
        medium_exit_risk_days=1,
    )
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="PULL",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        pullback_days=1,
        fast_ema10_pullback_days=1,
        conservative_ema20_pullback_days=1,
    )
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="BRK",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        breakout_days=2,
    )
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="ZERO",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
    )
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert [row["ticker"] for row in data["repeated_breakout_rows"]] == ["BRK"]
    assert [row["ticker"] for row in data["repeated_pullback_rows"]] == ["PULL"]
    assert [row["ticker"] for row in data["repeated_exit_risk_rows"]] == ["EXIT"]


def test_section_counts_watchlist_status_distributions_use_all_window_rows():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="AAA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        is_watchlist=1,
        current_watchlist_status="EARLY_PULLBACK",
        window_watchlist_status="PULLBACK_CANDIDATE",
        pullback_days=1,
    )
    _insert_window_row(
        conn,
        run_id="run-1",
        ticker="BBB",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        is_watchlist=0,
        current_watchlist_status="FAILED_PULLBACK",
        window_watchlist_status="GROUP_RISK",
        exit_risk_days=1,
    )
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    counts = data["section_counts"]
    assert [row["ticker"] for row in data["watchlist_rows"]] == ["AAA"]
    assert counts["watchlist_row_count"] == 1
    assert counts["current_watchlist_status_counts"] == {
        "EARLY_PULLBACK": 1,
        "FAILED_PULLBACK": 1,
    }
    assert counts["window_watchlist_status_counts"] == {
        "GROUP_RISK": 1,
        "PULLBACK_CANDIDATE": 1,
    }


def test_taxonomy_listing_rows_are_deterministic():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="ZLayer")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="BSub")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="ALayer")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="ASub")
    _insert_window_row(conn, run_id="run-1", ticker="ZZZ", primary_layer="ZLayer", primary_subindustry="BSub")
    _insert_window_row(conn, run_id="run-1", ticker="AAA", primary_layer="ALayer", primary_subindustry="ASub")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    rows = data["taxonomy_listing_rows"]
    assert [(row["row_type"], row["layer"], row["subindustry"], row["ticker"]) for row in rows] == [
        ("LAYER", "ALayer", "", ""),
        ("SUBINDUSTRY", "ALayer", "ASub", ""),
        ("TICKER", "ALayer", "ASub", "AAA"),
        ("LAYER", "ZLayer", "", ""),
        ("SUBINDUSTRY", "ZLayer", "BSub", ""),
        ("TICKER", "ZLayer", "BSub", "ZZZ"),
    ]
    assert rows[0]["group_current_status"] == "BUY_ZONE"
    assert rows[2]["current_watchlist_status"] == "PULLBACK_CANDIDATE"
    assert "group_current_status" not in rows[2]


def test_taxonomy_listing_includes_orphan_group_rows_without_fake_tickers():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Compute")
    _insert_group_row(
        conn,
        run_id="run-1",
        group_type="subindustry",
        group_name="OrphanSub",
        parent_group_type="layer",
        parent_group_name="Compute",
    )
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
    _insert_group_row(
        conn,
        run_id="run-1",
        group_type="subindustry",
        group_name="Semis",
        parent_group_type="layer",
        parent_group_name="Infrastructure",
    )
    _insert_window_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    rows = data["taxonomy_listing_rows"]
    assert [(row["row_type"], row["layer"], row["subindustry"], row["ticker"]) for row in rows] == [
        ("LAYER", "Compute", "", ""),
        ("SUBINDUSTRY", "Compute", "OrphanSub", ""),
        ("LAYER", "Infrastructure", "", ""),
        ("SUBINDUSTRY", "Infrastructure", "Semis", ""),
        ("TICKER", "Infrastructure", "Semis", "NVDA"),
    ]


def test_deferred_sections_are_explicit():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    conn.commit()

    data = load_rolling5_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert data["deferred_sections"] == {
        "swing_ma_break_status": "DEFERRED",
        "swing_signal_freshness": "DEFERRED",
        "technical_relevance_context": "DEFERRED",
        "synthetic_event_history": "DEFERRED",
    }
