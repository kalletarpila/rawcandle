import contextlib
import csv
import io
import sqlite3
from pathlib import Path

from dev_tools.run_report_canonical_v2_rolling2_csv import main
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


def _insert_group_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    group_type: str,
    group_name: str,
    market: str | None = None,
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            timing_state, overheat_risk_level, return_2d, return_5d, return_10d, return_20d, return_30d,
            pct_above_ema20, pct_above_ma10, group_context_risk_status, group_context_readiness_status,
            synthetic_close, synthetic_trend_classification, synthetic_latest_structure_label,
            synthetic_latest_structure_age_trading_days, synthetic_latest_bos_event_type,
            synthetic_latest_bos_event_date, synthetic_latest_bos_age_trading_days,
            synthetic_latest_bos_freshness, synthetic_latest_reset_reason,
            synthetic_latest_reset_event_date, synthetic_latest_reset_age_trading_days,
            synthetic_latest_reset_freshness, data_quality_status, group_current_status,
            group_window_status, group_status_change, window_start_date, window_end_date,
            valid_signal_dates, run_id, created_at_utc
        ) VALUES (?, ?, ?, 'rolling2', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            group_type,
            group_name,
            timing_state,
            overheat_risk_level,
            1.0,
            2.0,
            4.0,
            6.0,
            8.0,
            62.5,
            71.0,
            "NO",
            "OK",
            150.0,
            "UP",
            "HL",
            5,
            "BOS_UP",
            "2026-05-29",
            1,
            "FRESH",
            "NONE",
            None,
            3,
            "STALE",
            "OK",
            timing_state,
            timing_state,
            "UNCHANGED",
            "2026-05-29",
            "2026-05-30",
            2,
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
    market: str | None = None,
    current_watchlist_status: str = "CURRENT_ALPHA",
    window_watchlist_status: str = "WINDOW_ALPHA",
    is_watchlist: int = 1,
    latest_exit_reason: str | None = "PRICE_BREAK",
) -> None:
    row = {
        "signal_date": "2026-05-30",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "market": market,
        "ticker": ticker,
        "horizon": "rolling2",
        "window_start_date": "2026-05-29",
        "window_end_date": "2026-05-30",
        "valid_signal_dates": 2,
        "incomplete_window": 0,
        "primary_layer": primary_layer,
        "primary_subindustry": primary_subindustry,
        "in_datacenter_ecosystem": 1,
        "is_watchlist": is_watchlist,
        "current_watchlist_status": current_watchlist_status,
        "window_watchlist_status": window_watchlist_status,
        "breakout_days": 2,
        "pullback_days": 1,
        "fast_ema10_pullback_days": 1,
        "conservative_ema20_pullback_days": 1,
        "exit_risk_days": 3,
        "high_exit_risk_days": 2,
        "medium_exit_risk_days": 1,
        "first_signal_date": "2026-05-29",
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
        "fresh_bos_flag": 1,
        "fresh_reset_flag": 0,
        "stale_structure_flag": 0,
        "layer_overheat_risk_flag": 0,
        "subindustry_overheat_risk_flag": 0,
        "severe_exit_risk_flag": 1,
        "context_readiness_status": "OK",
        "run_id": run_id,
        "created_at_utc": "2026-05-30T00:00:00Z",
        "price_data_status": "OK",
        "exit_risk_severity": "HIGH",
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


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    market: str | None = None,
    classification_state: str = "SELL_PRESSURE_X",
    primary_reason: str = "PRIMARY, X",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date, taxonomy_version, market, ticker, horizon, classification_type,
            classification_state, primary_reason, blocking_reason, risk_reason, next_action,
            classification_status, classification_version, run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, 'rolling2', 'rolling2_sell_pressure', ?, ?, ?, ?, ?, 'OK', ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            ticker,
            classification_state,
            primary_reason,
            None,
            "RISK_X",
            "ACTION_X",
            "REPORT_ROLLING2_SELL_PRESSURE_CLASSIFIER_V2_1",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_cli_writes_csv_to_stdout(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
        _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis, Accelerators")
        _insert_window_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis, Accelerators")
        _insert_classification_row(conn, run_id="run-1", ticker="NVDA", classification_state="SELL_PRESSURE_X")
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    rows = _parse_csv(stdout)
    sections = {row["section"] for row in rows}

    assert exit_code == 0
    assert "metadata" in sections
    assert "rolling2_sell_pressure_rows" in sections
    assert any(row["ticker"] == "NVDA" for row in rows)
    assert any(row["classification_state"] == "SELL_PRESSURE_X" for row in rows)
    assert stderr == ""


def test_cli_can_write_csv_to_output_file(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    output_path = tmp_path / "nested" / "report.csv"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
        _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis, Accelerators")
        _insert_window_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis, Accelerators")
        _insert_classification_row(conn, run_id="run-1", ticker="NVDA")
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--output",
            str(output_path),
        ]
    )

    rows = _parse_csv(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert output_path.exists()
    assert any(row["ticker"] == "NVDA" for row in rows)


def test_cli_respects_explicit_run_id(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-a", created_at_utc="2026-05-30T00:00:00Z")
        _insert_run(conn, run_id="run-b", created_at_utc="2026-05-30T01:00:00Z")
        _insert_group_row(conn, run_id="run-a", group_type="layer", group_name="InfraA")
        _insert_group_row(conn, run_id="run-a", group_type="subindustry", group_name="SemisA")
        _insert_window_row(conn, run_id="run-a", ticker="AMD", primary_layer="InfraA", primary_subindustry="SemisA")
        _insert_classification_row(conn, run_id="run-a", ticker="AMD", classification_state="STATE_A")
        _insert_group_row(conn, run_id="run-b", group_type="layer", group_name="InfraB")
        _insert_group_row(conn, run_id="run-b", group_type="subindustry", group_name="SemisB")
        _insert_window_row(conn, run_id="run-b", ticker="NVDA", primary_layer="InfraB", primary_subindustry="SemisB")
        _insert_classification_row(conn, run_id="run-b", ticker="NVDA", classification_state="STATE_B")
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "run-a",
        ]
    )

    rows = _parse_csv(stdout)
    metadata_row = next(
        row for row in rows if row["section"] == "metadata" and row["key"] == "selected_run_id"
    )

    assert exit_code == 0
    assert metadata_row["value"] == "run-a"
    assert any(row["ticker"] == "AMD" for row in rows)
    assert not any(row["ticker"] == "NVDA" for row in rows)
    assert stderr == ""


def test_cli_applies_market_filter(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="usa-run", created_at_utc="2026-05-30T00:00:00Z", market="usa")
        _insert_run(conn, run_id="omxh-run", created_at_utc="2026-05-30T00:00:00Z", market="omxh")
        _insert_group_row(conn, run_id="usa-run", group_type="layer", group_name="Infrastructure", market="usa")
        _insert_group_row(conn, run_id="usa-run", group_type="subindustry", group_name="Semis", market="usa")
        _insert_group_row(conn, run_id="omxh-run", group_type="layer", group_name="NordicInfra", market="omxh")
        _insert_group_row(conn, run_id="omxh-run", group_type="subindustry", group_name="NordicSemis", market="omxh")
        _insert_window_row(conn, run_id="usa-run", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis", market="usa")
        _insert_window_row(conn, run_id="omxh-run", ticker="NOKIA", primary_layer="NordicInfra", primary_subindustry="NordicSemis", market="omxh")
        _insert_classification_row(conn, run_id="usa-run", ticker="NVDA", market="usa")
        _insert_classification_row(conn, run_id="omxh-run", ticker="NOKIA", market="omxh")
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--market",
            "usa",
        ]
    )

    rows = _parse_csv(stdout)

    assert exit_code == 0
    assert any(row["ticker"] == "NVDA" for row in rows)
    assert not any(row["ticker"] == "NOKIA" for row in rows)
    assert stderr == ""


def test_cli_works_without_source_tables(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
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
        _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
        _insert_window_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
        _insert_classification_row(conn, run_id="run-1", ticker="NVDA")
        conn.commit()

    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            str(db_path),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    assert exit_code == 0
    assert "NVDA" in stdout
    assert stderr == ""


def test_cli_returns_error_for_invalid_db_path():
    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            "/tmp/does-not-exist-report-canonical-v2-rolling2-csv.db",
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    assert exit_code == 2
    assert stdout == ""
    assert "analysis_db not found" in stderr


def test_cli_returns_usage_error_for_missing_required_args():
    exit_code, stdout, stderr = _run_cli(["--db", "/tmp/placeholder.db"])

    assert exit_code == 2
    assert stdout == ""
    assert "usage:" in stderr


def test_cli_csv_header_and_round_trip_sanity(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
        _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis, Accelerators")
        _insert_window_row(
            conn,
            run_id="run-1",
            ticker="NVDA",
            primary_layer="Infrastructure",
            primary_subindustry="Semis, Accelerators",
            latest_exit_reason=None,
        )
        _insert_classification_row(
            conn,
            run_id="run-1",
            ticker="NVDA",
            primary_reason="PRIMARY, X",
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
        ]
    )

    rows = _parse_csv(stdout)
    first_line = stdout.splitlines()[0]
    sell_pressure_row = next(row for row in rows if row["section"] == "rolling2_sell_pressure_rows")

    assert exit_code == 0
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
    assert sell_pressure_row["primary_reason"] == "PRIMARY, X"
    assert sell_pressure_row["primary_subindustry"] == "Semis, Accelerators"
    assert sell_pressure_row["latest_exit_reason"] == ""
    assert "None" not in stdout
    assert stderr == ""
