import sqlite3

from analysis.datacenter_indices.report_canonical_v2_daily_formatter_loader import (
    load_daily_canonical_formatter_data_v2,
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
    market: str | None = "usa",
    timing_state: str = "BUY_ZONE",
    group_context_risk_status: str = "NO",
    synthetic_close: float = 150.0,
    return_5d: float = 2.0,
    return_10d: float = 4.0,
    return_20d: float = 6.0,
    pct_above_ema20: float | None = None,
    pct_above_ma10: float | None = None,
    synthetic_trend_classification: str = "UP",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            timing_state, overheat_risk_level, return_5d, return_10d, return_20d,
            pct_above_ema20, pct_above_ma10,
            group_context_risk_status, group_context_readiness_status,
            synthetic_close, synthetic_trend_classification, synthetic_latest_structure_label,
            synthetic_latest_structure_age_trading_days, synthetic_latest_bos_event_type,
            synthetic_latest_bos_age_trading_days, synthetic_latest_bos_freshness,
            synthetic_latest_reset_reason, synthetic_latest_reset_age_trading_days,
            synthetic_latest_reset_freshness, data_quality_status,
            group_current_status, window_end_date, run_id, created_at_utc
        ) VALUES (?, ?, ?, 'daily', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            group_type,
            group_name,
            timing_state,
            "LOW",
            return_5d,
            return_10d,
            return_20d,
            pct_above_ema20,
            pct_above_ma10,
            group_context_risk_status,
            "OK",
            synthetic_close,
            synthetic_trend_classification,
            "HL",
            5,
            "BOS_UP",
            1,
            "FRESH",
            "NONE",
            3,
            "STALE",
            "OK",
            timing_state,
            "2026-05-30",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    primary_layer: str,
    primary_subindustry: str,
    market: str | None = "usa",
    is_watchlist: int = 1,
    current_watchlist_status: str = "BREAKOUT_CANDIDATE",
    breakout_signal: int = 1,
    pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
    distance_to_ema20_pct: float = 3.0,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date, taxonomy_version, market, ticker, primary_layer, primary_subindustry,
            in_datacenter_ecosystem, is_watchlist, current_watchlist_status,
            price_data_status, close, ema10, ema20, volume_vs_avg20,
            breakout_signal, pullback_signal, fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal, exit_risk_signal, exit_risk_severity,
            latest_exit_reason, latest_bullish_relevance_class, latest_bullish_relevance_reason,
            latest_bearish_relevance_class, latest_bearish_relevance_reason,
            bullish_candle_signal, bullish_divergence_signal, hidden_bullish_divergence_signal,
            bearish_candle_signal, bearish_divergence_signal, hidden_bearish_divergence_signal,
            return_5d, return_10d, return_20d, return_60d,
            distance_to_ema10_pct, distance_to_ema20_pct, distance_to_ema50_pct,
            trend_state, latest_structure_label, latest_structure_age_trading_days,
            latest_structure_freshness, latest_bos_event_type, latest_bos_age_trading_days,
            latest_bos_freshness, latest_reset_reason, latest_reset_age_trading_days,
            latest_reset_freshness, layer_timing_state, layer_overheat_risk_level,
            layer_context_risk_status, subindustry_timing_state, subindustry_overheat_risk_level,
            subindustry_context_risk_status, context_readiness_status, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            1,
            is_watchlist,
            current_watchlist_status,
            "OK",
            100.0,
            98.0,
            96.0,
            1.7,
            breakout_signal,
            pullback_signal,
            0,
            0,
            exit_risk_signal,
            exit_risk_severity,
            "reason-token",
            "RELEVANT",
            "BULLISH_STACK",
            None,
            None,
            1 if breakout_signal else 0,
            0,
            0,
            0,
            0,
            0,
            2.0,
            4.0,
            8.0,
            12.0,
            1.5,
            distance_to_ema20_pct,
            4.0,
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
            "BUY_ZONE",
            "LOW",
            "NO",
            "BUY_ZONE",
            "LOW",
            "NO",
            "OK",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    market: str | None = "usa",
    classification_state: str = "BUY_TRIGGER",
) -> None:
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
            market,
            ticker,
            classification_state,
            "PRIMARY",
            "",
            None,
            "REVIEW",
            "REPORT_CANONICAL_CLASSIFICATION_V2",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def test_loader_reads_canonical_daily_data():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
    _insert_classification_row(conn, run_id="run-1", ticker="NVDA")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert set(data) == {
        "metadata",
        "run",
        "group_rows",
        "ticker_rows",
        "daily_trigger_rows",
        "watchlist_rows",
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

    data = load_daily_canonical_formatter_data_v2(
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

    latest = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )
    explicit = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        run_id="run-a",
    )

    assert latest["run"]["run_id"] == "run-c"
    assert explicit["run"]["run_id"] == "run-a"


def test_market_filtering():
    conn = _connect()
    _insert_run(conn, run_id="usa-run", created_at_utc="2026-05-30T00:00:00Z", market="usa")
    _insert_run(conn, run_id="omxh-run", created_at_utc="2026-05-30T00:00:00Z", market="omxh")
    _insert_group_row(conn, run_id="usa-run", group_type="layer", group_name="Infrastructure", market="usa")
    _insert_group_row(conn, run_id="omxh-run", group_type="layer", group_name="NordicInfra", market="omxh")
    _insert_ticker_row(conn, run_id="usa-run", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis", market="usa")
    _insert_ticker_row(conn, run_id="omxh-run", ticker="NOKIA", primary_layer="NordicInfra", primary_subindustry="NordicSemis", market="omxh")
    _insert_classification_row(conn, run_id="usa-run", ticker="NVDA", market="usa")
    _insert_classification_row(conn, run_id="omxh-run", ticker="NOKIA", market="omxh")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert [row["ticker"] for row in data["ticker_rows"]] == ["NVDA"]
    assert [row["ticker"] for row in data["daily_trigger_rows"]] == ["NVDA"]
    assert [row["group_name"] for row in data["group_rows"]] == ["Infrastructure"]


def test_daily_trigger_join_uses_stored_classification():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
    _insert_classification_row(conn, run_id="run-1", ticker="NVDA", classification_state="BUY_WATCH")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    row = data["daily_trigger_rows"][0]
    assert row["ticker"] == "NVDA"
    assert row["classification_state"] == "BUY_WATCH"
    assert row["primary_reason"] == "PRIMARY"
    assert row["blocking_reason"] == ""
    assert row["next_action"] == "REVIEW"
    assert row["primary_layer"] == "Infrastructure"
    assert row["primary_subindustry"] == "Semis"


def test_watchlist_rows_use_stored_status():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_ticker_row(
        conn,
        run_id="run-1",
        ticker="AMD",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        current_watchlist_status="PULLBACK_CANDIDATE",
        breakout_signal=0,
        pullback_signal=1,
    )
    _insert_ticker_row(
        conn,
        run_id="run-1",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        current_watchlist_status="HIGH_EXIT_RISK",
        breakout_signal=0,
        pullback_signal=0,
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
    )
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert [(row["ticker"], row["current_watchlist_status"]) for row in data["watchlist_rows"]] == [
        ("AMD", "PULLBACK_CANDIDATE"),
        ("NVDA", "HIGH_EXIT_RISK"),
    ]


def test_taxonomy_listing_rows_are_deterministic():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="ZLayer")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="BSub")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="ALayer")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="ASub")
    _insert_ticker_row(conn, run_id="run-1", ticker="ZZZ", primary_layer="ZLayer", primary_subindustry="BSub")
    _insert_ticker_row(conn, run_id="run-1", ticker="AAA", primary_layer="ALayer", primary_subindustry="ASub")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
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


def test_taxonomy_listing_group_rows_preserve_pct_fields_without_distance_aliasing():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(
        conn,
        run_id="run-1",
        group_type="layer",
        group_name="Infrastructure",
        pct_above_ema20=62.5,
        pct_above_ma10=71.0,
    )
    _insert_group_row(
        conn,
        run_id="run-1",
        group_type="subindustry",
        group_name="Semis",
        pct_above_ema20=58.0,
        pct_above_ma10=66.0,
    )
    _insert_ticker_row(
        conn,
        run_id="run-1",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
    )
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    layer_row = data["taxonomy_listing_rows"][0]
    subindustry_row = data["taxonomy_listing_rows"][1]

    assert layer_row["row_type"] == "LAYER"
    assert layer_row["pct_above_ema20"] == 62.5
    assert layer_row["pct_above_ma10"] == 71.0
    assert "distance_to_ema20_pct" not in layer_row

    assert subindustry_row["row_type"] == "SUBINDUSTRY"
    assert subindustry_row["pct_above_ema20"] == 58.0
    assert subindustry_row["pct_above_ma10"] == 66.0
    assert "distance_to_ema20_pct" not in subindustry_row


def test_taxonomy_listing_ticker_rows_preserve_true_distance_to_ema20_pct():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(
        conn,
        run_id="run-1",
        group_type="layer",
        group_name="Infrastructure",
        pct_above_ema20=62.5,
        pct_above_ma10=71.0,
    )
    _insert_group_row(
        conn,
        run_id="run-1",
        group_type="subindustry",
        group_name="Semis",
        pct_above_ema20=58.0,
        pct_above_ma10=66.0,
    )
    _insert_ticker_row(
        conn,
        run_id="run-1",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
        distance_to_ema20_pct=1.2345,
    )
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    ticker_row = next(row for row in data["taxonomy_listing_rows"] if row["row_type"] == "TICKER")
    assert ticker_row["ticker"] == "NVDA"
    assert ticker_row["distance_to_ema20_pct"] == 1.2345
    assert ticker_row["distance_to_ema20_pct"] != 62.5
    assert ticker_row["distance_to_ema20_pct"] != 58.0


def test_section_counts_are_computed_from_canonical_rows():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, run_id="run-1", ticker="AMD", primary_layer="Infrastructure", primary_subindustry="Semis", current_watchlist_status="PULLBACK_CANDIDATE", breakout_signal=0, pullback_signal=1)
    _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis", current_watchlist_status="BREAKOUT_CANDIDATE")
    _insert_classification_row(conn, run_id="run-1", ticker="AMD", classification_state="BUY_WATCH")
    _insert_classification_row(conn, run_id="run-1", ticker="NVDA", classification_state="BUY_TRIGGER")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    counts = data["section_counts"]
    assert counts["group_row_count"] == 2
    assert counts["ticker_row_count"] == 2
    assert counts["daily_trigger_row_count"] == 2
    assert counts["watchlist_row_count"] == 2
    assert counts["daily_trigger_state_counts"] == {"BUY_TRIGGER": 1, "BUY_WATCH": 1}
    assert counts["watchlist_status_counts"] == {
        "BREAKOUT_CANDIDATE": 1,
        "PULLBACK_CANDIDATE": 1,
    }


def test_deferred_sections_are_explicitly_marked():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert data["deferred_sections"] == {
        "swing_ma_break_status": "DEFERRED",
        "swing_signal_freshness": "DEFERRED",
        "technical_relevance_context": "DEFERRED",
    }


def test_missing_run_returns_none_but_loader_still_returns_rows():
    conn = _connect()
    _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
    _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
    _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
    _insert_classification_row(conn, run_id="run-1", ticker="NVDA", classification_state="BUY_TRIGGER")
    conn.commit()

    data = load_daily_canonical_formatter_data_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        run_id="missing-run",
    )

    assert data["run"] is None
    assert data["metadata"]["selected_run_id"] is None
    assert [row["group_name"] for row in data["group_rows"]] == ["Infrastructure", "Semis"]
    assert [row["ticker"] for row in data["ticker_rows"]] == ["NVDA"]
    assert [row["ticker"] for row in data["daily_trigger_rows"]] == ["NVDA"]
