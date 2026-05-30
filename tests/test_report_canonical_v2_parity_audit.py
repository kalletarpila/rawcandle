from pathlib import Path
import sqlite3

from analysis.datacenter_indices.report_canonical_v2_orchestrator import (
    run_report_canonical_v2,
)
from analysis.datacenter_indices.report_canonical_v2_parity_audit import (
    audit_report_canonical_v2_parity,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _connect(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "analysis.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            parent_group_type TEXT NULL,
            parent_group_name TEXT NULL,
            timing_state TEXT NULL,
            overheat_risk_level TEXT NULL,
            return_2d REAL NULL,
            return_5d REAL NULL,
            return_30d REAL NULL,
            ema20_breadth_delta_5d REAL NULL,
            ma10_breadth_delta_5d REAL NULL,
            trend_breadth REAL NULL,
            weakness_breadth REAL NULL,
            strength_breadth REAL NULL,
            data_quality_status TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            calc_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            synthetic_close REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            trend_classification TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            ticker TEXT NOT NULL,
            primary_layer TEXT NULL,
            primary_subindustry TEXT NULL,
            close REAL NULL,
            ema20 REAL NULL,
            price_data_status TEXT NULL,
            latest_bullish_relevance_class TEXT NULL,
            latest_bearish_relevance_class TEXT NULL,
            breakout_signal INTEGER NULL,
            pullback_signal INTEGER NULL,
            fast_ema10_pullback_signal INTEGER NULL,
            conservative_ema20_pullback_signal INTEGER NULL,
            exit_risk_signal INTEGER NULL,
            exit_risk_severity TEXT NULL,
            exit_reason TEXT NULL,
            bullish_candle_signal INTEGER NULL,
            bullish_divergence_signal INTEGER NULL,
            hidden_bullish_divergence_signal INTEGER NULL,
            bearish_candle_signal INTEGER NULL,
            bearish_divergence_signal INTEGER NULL,
            hidden_bearish_divergence_signal INTEGER NULL,
            return_5d REAL NULL,
            return_10d REAL NULL,
            return_20d REAL NULL,
            return_60d REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            ticker_trend_state TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_event_date TEXT NULL,
            latest_bos_age_trading_days INTEGER NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_event_date TEXT NULL,
            latest_reset_age_trading_days INTEGER NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    return conn


def _insert_group_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    group_type: str,
    group_name: str,
    parent_group_type: str | None,
    parent_group_name: str | None,
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, signal_version, market, group_type, group_name,
            parent_group_type, parent_group_name, timing_state, overheat_risk_level,
            return_2d, return_5d, return_30d, ema20_breadth_delta_5d, ma10_breadth_delta_5d,
            trend_breadth, weakness_breadth, strength_breadth, data_quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            1.0,
            2.0,
            3.0,
            0.2,
            0.1,
            0.8,
            0.1,
            0.7,
            "OK",
        ),
    )


def _insert_synthetic_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    group_type: str,
    group_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, calc_version, market, group_type, group_name,
            synthetic_close, distance_to_ema20_pct, distance_to_ema50_pct, trend_classification,
            latest_structure_label, latest_bos_event_type, latest_bos_freshness,
            latest_reset_reason, latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_OHLC_V1",
            market,
            group_type,
            group_name,
            150.0,
            1.2,
            3.4,
            "UP",
            "HL",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
        ),
    )


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    ticker: str = "NVDA",
    breakout_signal: int = 0,
    pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, signal_version, market, ticker,
            primary_layer, primary_subindustry, close, ema20, price_data_status,
            latest_bullish_relevance_class, latest_bearish_relevance_class,
            breakout_signal, pullback_signal, fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal, exit_risk_signal, exit_risk_severity,
            exit_reason, bullish_candle_signal, bullish_divergence_signal,
            hidden_bullish_divergence_signal, bearish_candle_signal,
            bearish_divergence_signal, hidden_bearish_divergence_signal,
            return_5d, return_10d, return_20d, return_60d, distance_to_ema20_pct,
            distance_to_ema50_pct, ticker_trend_state, latest_structure_label,
            latest_structure_freshness, latest_bos_event_type, latest_bos_event_date,
            latest_bos_age_trading_days, latest_bos_freshness, latest_reset_reason,
            latest_reset_event_date, latest_reset_age_trading_days, latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            ticker,
            "Infrastructure",
            "Semis",
            100.0,
            98.5,
            "OK",
            "RELEVANT",
            None,
            breakout_signal,
            pullback_signal,
            0,
            0,
            exit_risk_signal,
            exit_risk_severity,
            "reason-token",
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
            3.0,
            "UP",
            "HL",
            "FRESH",
            "BOS_UP",
            signal_date,
            0,
            "FRESH",
            "NONE",
            signal_date,
            0,
            "STALE",
        ),
    )


def _seed_source_rows(conn: sqlite3.Connection) -> None:
    for signal_date in ("2026-05-29", "2026-05-30"):
        _insert_group_row(
            conn,
            signal_date=signal_date,
            market="usa",
            group_type="layer",
            group_name="Infrastructure",
            parent_group_type="ecosystem",
            parent_group_name="Datacenter",
        )
        _insert_group_row(
            conn,
            signal_date=signal_date,
            market="usa",
            group_type="subindustry",
            group_name="Semis",
            parent_group_type="layer",
            parent_group_name="Infrastructure",
        )
        _insert_synthetic_row(
            conn,
            signal_date=signal_date,
            market="usa",
            group_type="layer",
            group_name="Infrastructure",
        )
        _insert_synthetic_row(
            conn,
            signal_date=signal_date,
            market="usa",
            group_type="subindustry",
            group_name="Semis",
        )
    _insert_ticker_row(conn, signal_date="2026-05-29", market="usa", pullback_signal=1)
    _insert_ticker_row(conn, signal_date="2026-05-30", market="usa", breakout_signal=1)
    conn.commit()


def _run_v2(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id=run_id,
        market="usa",
    )


def _insert_run_row(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id, signal_date, taxonomy_version, market, calculation_version,
            source_versions_json, created_at_utc, status, warning_count,
            error_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "TEST",
            None,
            "2026-05-30T00:00:00Z",
            "OK",
            0,
            0,
            None,
        ),
    )


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    horizon: str,
    classification_type: str,
    classification_state: str,
    primary_reason: str | None,
    blocking_reason: str | None = None,
    risk_reason: str | None = None,
    next_action: str | None = None,
    run_id: str = "run-1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, market, ticker, horizon,
            classification_type, classification_state, primary_reason,
            blocking_reason, risk_reason, next_action, classification_status,
            classification_version, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            ticker,
            horizon,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            "OK",
            "TEST",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def test_parity_audit_reports_ok_when_current_and_v2_classifications_match(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
    )

    assert result["status"] == "OK"
    assert result["mismatch_count"] == 0
    assert result["matched_count"] == 5


def test_mismatch_is_detected(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET classification_state = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN", "NVDA", "daily_trigger"),
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("daily",),
    )

    assert result["status"] == "MISMATCH"
    assert result["mismatch_count"] == 1
    assert result["mismatches"] == [
        {
            "horizon": "daily",
            "ticker": "NVDA",
            "classification_type": "daily_trigger",
            "field": "classification_state",
            "current_value": "BUY_TRIGGER",
            "v2_value": "BROKEN",
            "reason": "field_mismatch",
        }
    ]


def test_missing_v2_row_is_detected(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        "DELETE FROM dc_report_classification_v2 WHERE ticker = ? AND classification_type = ?",
        ("NVDA", "rolling5_pullback"),
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("rolling5", "rolling30"),
    )

    assert result["status"] == "MISMATCH"
    assert result["missing_v2_count"] == 1
    assert result["mismatches"][0]["reason"] == "missing_v2_row"
    assert result["mismatches"][0]["classification_type"] == "rolling5_pullback"


def test_missing_current_row_is_detected(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    _insert_classification_row(
        conn,
        ticker="FAKE",
        horizon="rolling2",
        classification_type="rolling2_sell_pressure",
        classification_state="WATCH_PRESSURE",
        primary_reason="X",
        risk_reason="Y",
        next_action="Z",
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("rolling2",),
    )

    assert result["status"] == "MISMATCH"
    assert result["missing_current_count"] == 1
    assert result["mismatches"][0]["reason"] == "missing_current_row"
    assert result["mismatches"][0]["ticker"] == "FAKE"


def test_no_current_data_status_is_reported_deterministically(tmp_path: Path):
    conn = _connect(tmp_path)
    _insert_run_row(conn)
    _insert_classification_row(
        conn,
        ticker="NVDA",
        horizon="rolling2",
        classification_type="rolling2_sell_pressure",
        classification_state="WATCH_PRESSURE",
        primary_reason="CURRENT_EXIT_RISK",
        risk_reason="ELEVATED_EXIT_RISK",
        next_action="REVIEW_EXIT_RISK",
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("rolling2",),
    )

    assert result["status"] == "NO_CURRENT_DATA"
    assert result["missing_current_count"] == 1
    assert result["mismatch_count"] == len(result["mismatches"]) == 1
    assert result["mismatches"] == [
        {
            "horizon": "rolling2",
            "ticker": "NVDA",
            "classification_type": "rolling2_sell_pressure",
            "field": "row_presence",
            "current_value": None,
            "v2_value": "PRESENT",
            "reason": "missing_current_row",
        }
    ]


def test_no_v2_data_status_is_reported_deterministically(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("daily",),
    )

    assert result["status"] == "NO_V2_DATA"
    assert result["missing_v2_count"] == 1
    assert result["mismatch_count"] == len(result["mismatches"]) == 1
    assert result["mismatches"] == [
        {
            "horizon": "daily",
            "ticker": "NVDA",
            "classification_type": "daily_trigger",
            "field": "row_presence",
            "current_value": "PRESENT",
            "v2_value": None,
            "reason": "missing_v2_row",
        }
    ]


def test_empty_string_vs_null_reason_normalization(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("rolling30",),
    )

    assert result["status"] == "OK"
    assert result["mismatch_count"] == 0


def test_rolling2_reason_action_field_mismatch_is_detected(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET next_action = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN_ACTION", "NVDA", "rolling2_sell_pressure"),
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("rolling2",),
    )

    assert result["status"] == "MISMATCH"
    assert result["mismatch_count"] == 1
    assert result["mismatches"] == [
        {
            "horizon": "rolling2",
            "ticker": "NVDA",
            "classification_type": "rolling2_sell_pressure",
            "field": "next_action",
            "current_value": "NONE",
            "v2_value": "BROKEN_ACTION",
            "reason": "field_mismatch",
        }
    ]


def test_rolling5_reason_action_field_mismatch_is_detected(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET blocking_reason = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN_BLOCKING_REASON", "NVDA", "rolling5_pullback"),
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("rolling5",),
    )

    assert result["status"] == "MISMATCH"
    assert result["mismatch_count"] == 1
    assert result["mismatches"] == [
        {
            "horizon": "rolling5",
            "ticker": "NVDA",
            "classification_type": "rolling5_pullback",
            "field": "blocking_reason",
            "current_value": "",
            "v2_value": "BROKEN_BLOCKING_REASON",
            "reason": "field_mismatch",
        }
    ]


def test_selected_horizon_audit_excludes_other_horizon_mismatches(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET classification_state = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN", "NVDA", "rolling30_buy"),
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("daily",),
    )

    assert result["status"] == "OK"
    assert result["mismatch_count"] == 0


def test_mismatches_are_sorted_deterministically(tmp_path: Path):
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET classification_state = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN_DAILY", "NVDA", "daily_trigger"),
    )
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET blocking_reason = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN_BLOCK", "NVDA", "rolling30_buy"),
    )
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET risk_reason = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN_RISK", "NVDA", "rolling30_exit"),
    )
    conn.commit()

    result = audit_report_canonical_v2_parity(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        horizons=("daily", "rolling30"),
    )

    assert [
        (
            row["horizon"],
            row["classification_type"],
            row["ticker"],
            row["field"],
        )
        for row in result["mismatches"]
    ] == [
        ("daily", "daily_trigger", "NVDA", "classification_state"),
        ("rolling30", "rolling30_buy", "NVDA", "blocking_reason"),
        ("rolling30", "rolling30_exit", "NVDA", "risk_reason"),
    ]
