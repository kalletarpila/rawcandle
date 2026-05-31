import contextlib
import csv
import io
import sqlite3
from pathlib import Path

import dev_tools.run_report_canonical_v2_output as cli
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _create_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
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
    market: str | None = None,
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


def _insert_daily_group_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    group_type: str,
    group_name: str,
    market: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            timing_state, overheat_risk_level, return_5d, return_10d, return_20d,
            pct_above_ema20, pct_above_ma10, group_context_risk_status,
            group_context_readiness_status, synthetic_close, synthetic_trend_classification,
            synthetic_latest_structure_label, synthetic_latest_structure_age_trading_days,
            synthetic_latest_bos_event_type, synthetic_latest_bos_age_trading_days,
            synthetic_latest_bos_freshness, synthetic_latest_reset_reason,
            synthetic_latest_reset_age_trading_days, synthetic_latest_reset_freshness,
            data_quality_status, group_current_status, window_end_date, run_id, created_at_utc
        ) VALUES (?, ?, ?, 'daily', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            group_type,
            group_name,
            "BUY_ZONE",
            "LOW",
            2.0,
            4.0,
            6.0,
            62.5,
            71.0,
            "NO",
            "OK",
            150.0,
            "UP",
            "HL",
            5,
            "BOS_UP",
            1,
            "FRESH",
            "NONE",
            3,
            "STALE",
            "OK",
            "BUY_ZONE",
            "2026-05-30",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_daily_ticker_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    primary_layer: str,
    primary_subindustry: str,
    market: str | None = None,
    current_watchlist_status: str = "BREAKOUT_CANDIDATE",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date, taxonomy_version, market, ticker, primary_layer, primary_subindustry,
            in_datacenter_ecosystem, is_watchlist, current_watchlist_status,
            price_data_status, close, breakout_signal, pullback_signal, exit_risk_signal,
            return_5d, return_10d, return_20d, return_60d, distance_to_ema20_pct,
            trend_state, latest_structure_label, latest_structure_age_trading_days,
            latest_structure_freshness, latest_bos_event_type, latest_bos_age_trading_days,
            latest_bos_freshness, latest_reset_reason, latest_reset_age_trading_days,
            latest_reset_freshness, layer_context_risk_status, subindustry_context_risk_status,
            context_readiness_status, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            1,
            1,
            current_watchlist_status,
            "OK",
            100.0,
            1,
            0,
            0,
            2.0,
            4.0,
            8.0,
            12.0,
            1.2345,
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
            "NO",
            "NO",
            "OK",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_daily_classification_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    market: str | None = None,
    classification_state: str = "BUY_WATCH",
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
            "BULLISH_SETUP_NEEDS_CONFIRMATION",
            "",
            None,
            "MONITOR_FOR_DAILY_CONFIRMATION",
            "REPORT_CANONICAL_CLASSIFICATION_V2",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_window_group_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    horizon: str,
    group_type: str,
    group_name: str,
    market: str | None = None,
    parent_group_type: str | None = None,
    parent_group_name: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            parent_group_type, parent_group_name, timing_state, overheat_risk_level,
            return_2d, return_5d, return_30d, breadth_json, synthetic_close,
            synthetic_ema_distance_json, synthetic_trend_classification,
            synthetic_latest_structure_label, synthetic_latest_bos_event_type,
            synthetic_latest_bos_freshness, synthetic_latest_reset_reason,
            synthetic_latest_reset_freshness, group_context_risk_status,
            group_context_readiness_status, group_current_status, group_window_status,
            group_status_change, window_start_date, window_end_date,
            valid_signal_dates, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            horizon,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            "BUY_ZONE",
            "LOW",
            1.0,
            2.0,
            8.0,
            None,
            150.0,
            None,
            "UP",
            "HL",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
            "NO",
            "OK",
            "BUY_ZONE",
            "BUY_ZONE",
            "UNCHANGED",
            "2026-05-01",
            "2026-05-30",
            {"rolling2": 2, "rolling5": 5, "rolling30": 30}[horizon],
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_window_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    horizon: str,
    ticker: str,
    primary_layer: str,
    primary_subindustry: str,
    market: str | None = None,
    current_watchlist_status: str,
    window_watchlist_status: str,
    latest_exit_reason: str | None,
    exit_risk_severity: str,
) -> None:
    valid_signal_dates = {"rolling2": 2, "rolling5": 5, "rolling30": 30}[horizon]
    row = {
        "signal_date": "2026-05-30",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "market": market,
        "ticker": ticker,
        "horizon": horizon,
        "window_start_date": "2026-05-01",
        "window_end_date": "2026-05-30",
        "valid_signal_dates": valid_signal_dates,
        "incomplete_window": 0,
        "primary_layer": primary_layer,
        "primary_subindustry": primary_subindustry,
        "in_datacenter_ecosystem": 1,
        "is_watchlist": 1,
        "current_watchlist_status": current_watchlist_status,
        "window_watchlist_status": window_watchlist_status,
        "breakout_days": 3,
        "pullback_days": 2,
        "fast_ema10_pullback_days": 1,
        "conservative_ema20_pullback_days": 1,
        "exit_risk_days": 4,
        "high_exit_risk_days": 2,
        "medium_exit_risk_days": 2,
        "first_signal_date": "2026-05-01",
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
        "latest_reset_reason": None,
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
        "fresh_bos_flag": 1,
        "fresh_reset_flag": 0,
        "stale_structure_flag": 0,
        "layer_overheat_risk_flag": 0,
        "subindustry_overheat_risk_flag": 0,
        "severe_exit_risk_flag": 0,
        "context_readiness_status": "OK",
        "run_id": run_id,
        "created_at_utc": "2026-05-30T00:00:00Z",
        "price_data_status": "OK",
        "exit_risk_severity": exit_risk_severity,
        "latest_bearish_relevance_class": "BEARISH_TOKEN",
        "distance_to_ema20_pct": 1.5,
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


def _insert_window_classification_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    horizon: str,
    classification_type: str,
    ticker: str,
    market: str | None = None,
    classification_state: str,
    primary_reason: str,
    blocking_reason: str | None,
    risk_reason: str | None,
    next_action: str | None,
    classification_version: str,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, market, ticker, horizon, classification_type,
            classification_state, primary_reason, blocking_reason, risk_reason, next_action,
            classification_status, classification_version, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OK', ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            ticker,
            horizon,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            classification_version,
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _populate_all_horizons(conn: sqlite3.Connection) -> None:
    _insert_run(conn, run_id="run-null", created_at_utc="2026-05-30T00:00:00Z")
    _insert_run(
        conn,
        run_id="run-alt",
        created_at_utc="2026-05-29T23:59:00Z",
    )

    for group_name in ("Infrastructure", "Semis"):
        _insert_daily_group_row(
            conn,
            run_id="run-null",
            group_type="layer" if group_name == "Infrastructure" else "subindustry",
            group_name=group_name,
        )

    _insert_daily_ticker_row(
        conn,
        run_id="run-null",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis",
    )
    _insert_daily_ticker_row(
        conn,
        run_id="run-alt",
        ticker="MSFT",
        primary_layer="Alt Infrastructure",
        primary_subindustry="Alt Semis",
    )
    _insert_daily_classification_row(conn, run_id="run-null", ticker="NVDA", classification_state="BUY_WATCH")
    _insert_daily_classification_row(conn, run_id="run-alt", ticker="MSFT", classification_state="ALT_BUY")
    _insert_daily_group_row(conn, run_id="run-alt", group_type="layer", group_name="Alt Infrastructure")
    _insert_daily_group_row(conn, run_id="run-alt", group_type="subindustry", group_name="Alt Semis")

    for horizon in ("rolling2", "rolling5", "rolling30"):
        _insert_window_group_row(
            conn,
            run_id="run-null",
            horizon=horizon,
            group_type="layer",
            group_name="Infrastructure",
        )
        _insert_window_group_row(
            conn,
            run_id="run-null",
            horizon=horizon,
            group_type="subindustry",
            group_name="Semis, Accelerators",
            parent_group_type="layer",
            parent_group_name="Infrastructure",
        )

    _insert_window_row(
        conn,
        run_id="run-null",
        horizon="rolling2",
        ticker="NVDA",
        primary_layer="Infrastructure",
        primary_subindustry="Semis, Accelerators",
        current_watchlist_status="CURRENT_ALPHA",
        window_watchlist_status="WINDOW_ALPHA",
        latest_exit_reason="PRICE_BREAK",
        exit_risk_severity="HIGH",
    )
    _insert_window_classification_row(
        conn,
        run_id="run-null",
        horizon="rolling2",
        classification_type="rolling2_sell_pressure",
        ticker="NVDA",
        classification_state="SELL_PRESSURE_X",
        primary_reason="PRIMARY, X",
        blocking_reason=None,
        risk_reason="RISK_X",
        next_action="ACTION_X",
        classification_version="REPORT_ROLLING2_SELL_PRESSURE_CLASSIFIER_V2_1",
    )

    _insert_window_row(
        conn,
        run_id="run-null",
        horizon="rolling5",
        ticker="AMD",
        primary_layer="Infrastructure",
        primary_subindustry="Semis, Accelerators",
        current_watchlist_status="CURRENT_PULLBACK",
        window_watchlist_status="WINDOW_PULLBACK",
        latest_exit_reason="STRUCTURAL_WARNING",
        exit_risk_severity="MEDIUM",
    )
    _insert_window_classification_row(
        conn,
        run_id="run-null",
        horizon="rolling5",
        classification_type="rolling5_pullback",
        ticker="AMD",
        classification_state="PULLBACK_STATE_X",
        primary_reason="PRIMARY_PULLBACK, X",
        blocking_reason="BLOCKING_X",
        risk_reason=None,
        next_action="ACTION_X",
        classification_version="REPORT_ROLLING5_PULLBACK_CLASSIFIER_V2_1",
    )

    _insert_window_row(
        conn,
        run_id="run-null",
        horizon="rolling30",
        ticker="AVGO",
        primary_layer="Infrastructure",
        primary_subindustry="Semis, Accelerators",
        current_watchlist_status="CURRENT_BUY_X",
        window_watchlist_status="WINDOW_BUY_X",
        latest_exit_reason=None,
        exit_risk_severity="HIGH",
    )
    _insert_window_classification_row(
        conn,
        run_id="run-null",
        horizon="rolling30",
        classification_type="rolling30_buy",
        ticker="AVGO",
        classification_state="BUY_STATE_X",
        primary_reason="BUY_PRIMARY, X",
        blocking_reason="BUY_BLOCK_X",
        risk_reason=None,
        next_action=None,
        classification_version="REPORT_ROLLING30_BUY_EXIT_CLASSIFIER_V2_1",
    )
    _insert_window_classification_row(
        conn,
        run_id="run-null",
        horizon="rolling30",
        classification_type="rolling30_exit",
        ticker="AVGO",
        classification_state="EXIT_STATE_X",
        primary_reason="EXIT_PRIMARY_X",
        blocking_reason=None,
        risk_reason="EXIT_RISK_X",
        next_action=None,
        classification_version="REPORT_ROLLING30_BUY_EXIT_CLASSIFIER_V2_1",
    )


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_cli_supports_all_horizon_format_combinations(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    markers = {
        ("daily", "markdown"): "# Datacenter Daily Canonical V2 Report",
        ("daily", "csv"): "daily_trigger_rows",
        ("rolling2", "markdown"): "# Datacenter Rolling2 Canonical V2 Report",
        ("rolling2", "csv"): "rolling2_sell_pressure_rows",
        ("rolling5", "markdown"): "# Datacenter Rolling5 Canonical V2 Report",
        ("rolling5", "csv"): "rolling5_pullback_rows",
        ("rolling30", "markdown"): "# Datacenter Rolling30 Canonical V2 Report",
        ("rolling30", "csv"): "rolling30_buy_rows",
    }

    for (horizon, output_format), marker in markers.items():
        exit_code, stdout, stderr = _run_cli(
            [
                "--db",
                str(db_path),
                "--signal-date",
                "2026-05-30",
                "--taxonomy-version",
                "DC_TAXONOMY_FULL_V1",
                "--horizon",
                horizon,
                "--format",
                output_format,
            ]
        )
        assert exit_code == 0
        assert marker in stdout
        assert stderr == ""


def test_cli_works_with_canonical_v2_tables_only(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "rolling30",
            "--format",
            "csv",
        ]
    )

    assert exit_code == 0
    assert "rolling30_buy_rows" in stdout
    assert stderr == ""


def test_cli_writes_output_file_without_dumping_body_to_stdout(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    output_path = tmp_path / "nested" / "report.md"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "daily",
            "--format",
            "markdown",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("# Datacenter Daily Canonical V2 Report")


def test_cli_writes_body_to_stdout_when_output_not_provided(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "rolling5",
            "--format",
            "markdown",
        ]
    )

    assert exit_code == 0
    assert "# Datacenter Rolling5 Canonical V2 Report" in stdout
    assert stderr == ""


def test_cli_respects_explicit_run_id_selection(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "daily",
            "--format",
            "markdown",
            "--run-id",
            "run-alt",
        ]
    )

    assert exit_code == 0
    assert "selected_run_id: run-alt" in stdout
    assert "MSFT" in stdout
    assert "NVDA" not in stdout
    assert stderr == ""


def test_cli_respects_market_filter(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-null", created_at_utc="2026-05-30T00:00:00Z")
        _insert_run(
            conn,
            run_id="run-usa",
            created_at_utc="2026-05-30T00:01:00Z",
            market="usa",
        )
        _insert_daily_group_row(conn, run_id="run-null", group_type="layer", group_name="Infrastructure")
        _insert_daily_group_row(conn, run_id="run-null", group_type="subindustry", group_name="Semis")
        _insert_daily_group_row(conn, run_id="run-usa", group_type="layer", group_name="US Infrastructure", market="usa")
        _insert_daily_group_row(conn, run_id="run-usa", group_type="subindustry", group_name="US Semis", market="usa")
        _insert_daily_ticker_row(
            conn,
            run_id="run-null",
            ticker="NVDA",
            primary_layer="Infrastructure",
            primary_subindustry="Semis",
        )
        _insert_daily_ticker_row(
            conn,
            run_id="run-usa",
            ticker="AMD",
            primary_layer="US Infrastructure",
            primary_subindustry="US Semis",
            market="usa",
            current_watchlist_status="USA_BREAKOUT",
        )
        _insert_daily_classification_row(conn, run_id="run-null", ticker="NVDA", classification_state="BUY_WATCH")
        _insert_daily_classification_row(
            conn,
            run_id="run-usa",
            ticker="AMD",
            market="usa",
            classification_state="USA_BUY",
        )
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "daily",
            "--format",
            "markdown",
            "--market",
            "usa",
        ]
    )

    assert exit_code == 0
    assert "AMD" in stdout
    assert "USA_BUY" in stdout
    assert "NVDA" not in stdout
    assert stderr == ""


def test_cli_invalid_db_path_returns_two(tmp_path: Path):
    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(tmp_path / "missing.db"),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "daily",
            "--format",
            "markdown",
        ]
    )

    assert exit_code == 2
    assert stdout == ""
    assert "analysis_db not found" in stderr


def test_cli_missing_v2_tables_returns_one(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    sqlite3.connect(db_path).close()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "daily",
            "--format",
            "markdown",
        ]
    )

    assert exit_code == 1
    assert stdout == ""
    assert "no such table" in stderr


def test_cli_writes_summary_output(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    summary_path = tmp_path / "nested" / "summary.txt"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "rolling30",
            "--format",
            "csv",
            "--summary-output",
            str(summary_path),
        ]
    )

    summary_text = summary_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "section,key,value" in stdout
    assert stderr == ""
    assert summary_path.exists()
    assert "SUMMARY status=OK" in summary_text
    assert "SUMMARY horizon=rolling30" in summary_text
    assert "SUMMARY format=csv" in summary_text
    assert "SUMMARY line_count=" in summary_text
    assert "SUMMARY byte_count=" in summary_text


def test_cli_parity_gate_success_and_summary_output(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "analysis.db"
    summary_path = tmp_path / "summary.txt"
    output_path = tmp_path / "report.csv"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    def _audit_ok(conn: sqlite3.Connection, **kwargs: object) -> dict[str, object]:
        return {
            "status": "OK",
            "mismatch_count": 0,
            "mismatches": [],
            "horizons": kwargs["horizons"],
        }

    monkeypatch.setattr(cli, "audit_report_canonical_v2_parity", _audit_ok)

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "rolling2",
            "--format",
            "csv",
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
            "--require-parity-ok",
        ]
    )

    summary_text = summary_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert output_path.exists()
    assert "SUMMARY parity_status=OK" in summary_text
    assert "SUMMARY parity_mismatch_count=0" in summary_text


def test_cli_parity_gate_failure_returns_one_and_writes_summary(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "analysis.db"
    summary_path = tmp_path / "summary.txt"
    output_path = tmp_path / "report.csv"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    def _audit_fail(conn: sqlite3.Connection, **kwargs: object) -> dict[str, object]:
        return {
            "status": "MISMATCH",
            "mismatch_count": 1,
            "mismatches": [
                {
                    "horizon": "rolling30",
                    "classification_type": "rolling30_buy",
                    "ticker": "AVGO",
                    "field": "classification_state",
                    "current_value": "A",
                    "v2_value": "B",
                    "reason": "token",
                }
            ],
        }

    monkeypatch.setattr(cli, "audit_report_canonical_v2_parity", _audit_fail)

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "rolling30",
            "--format",
            "csv",
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
            "--require-parity-ok",
        ]
    )

    summary_text = summary_path.read_text(encoding="utf-8")

    assert exit_code == 1
    assert stdout == ""
    assert stderr == ""
    assert not output_path.exists()
    assert "SUMMARY parity_status=MISMATCH" in summary_text
    assert "SUMMARY parity_mismatch_count=1" in summary_text
    assert "MISMATCH horizon=rolling30" in summary_text


def test_cli_invalid_parity_horizons_returns_two(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _populate_all_horizons(conn)
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--horizon",
            "daily",
            "--format",
            "markdown",
            "--require-parity-ok",
            "--parity-horizons",
            "daily,invalid",
        ]
    )

    assert exit_code == 2
    assert stdout == ""
    assert "unsupported parity horizons" in stderr
