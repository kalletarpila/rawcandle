import contextlib
import csv
import io
import sqlite3
from pathlib import Path

from dev_tools.run_report_canonical_v2_daily_csv import main
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
    overheat_risk_level: str = "LOW",
    pct_above_ema20: float = 62.5,
    pct_above_ma10: float = 71.0,
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
            overheat_risk_level,
            2.0,
            4.0,
            6.0,
            pct_above_ema20,
            pct_above_ma10,
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


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    primary_layer: str,
    primary_subindustry: str,
    market: str | None = None,
    current_watchlist_status: str = "BREAKOUT_CANDIDATE",
    latest_bearish_relevance_reason: str | None = None,
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
            1,
            current_watchlist_status,
            "OK",
            100.0,
            98.0,
            96.0,
            1.7,
            1,
            0,
            0,
            0,
            0,
            None,
            "reason-token",
            "RELEVANT",
            "BULLISH, STACK",
            None,
            latest_bearish_relevance_reason,
            1,
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
            1.2345,
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
    market: str | None = None,
    classification_state: str = "BUY_WATCH",
    primary_reason: str = "BULLISH, SETUP / NEEDS CONFIRMATION",
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
            primary_reason,
            "",
            None,
            "MONITOR_FOR_DAILY_CONFIRMATION",
            "REPORT_CANONICAL_CLASSIFICATION_V2",
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
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
        _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
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

    rows = _parse_csv(stdout)
    sections = {row["section"] for row in rows}

    assert exit_code == 0
    assert "metadata" in sections
    assert "daily_trigger_rows" in sections
    assert any(row["ticker"] == "NVDA" for row in rows)
    assert any(row["classification_state"] == "BUY_WATCH" for row in rows)
    assert stderr == ""


def test_cli_can_write_csv_to_output_file(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    output_path = tmp_path / "nested" / "report.csv"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
        _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
        _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
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
        _insert_ticker_row(conn, run_id="run-a", ticker="AMD", primary_layer="InfraA", primary_subindustry="SemisA")
        _insert_classification_row(conn, run_id="run-a", ticker="AMD", classification_state="BUY_TRIGGER")
        _insert_group_row(conn, run_id="run-b", group_type="layer", group_name="InfraB")
        _insert_group_row(conn, run_id="run-b", group_type="subindustry", group_name="SemisB")
        _insert_ticker_row(conn, run_id="run-b", ticker="NVDA", primary_layer="InfraB", primary_subindustry="SemisB")
        _insert_classification_row(conn, run_id="run-b", ticker="NVDA", classification_state="BUY_WATCH")
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
    selected_run_row = next(
        row
        for row in rows
        if row["section"] == "metadata" and row["key"] == "selected_run_id"
    )

    assert exit_code == 0
    assert selected_run_row["value"] == "run-a"
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
        _insert_ticker_row(conn, run_id="usa-run", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis", market="usa")
        _insert_ticker_row(conn, run_id="omxh-run", ticker="NOKIA", primary_layer="NordicInfra", primary_subindustry="NordicSemis", market="omxh")
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
        _insert_ticker_row(conn, run_id="run-1", ticker="NVDA", primary_layer="Infrastructure", primary_subindustry="Semis")
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

    rows = _parse_csv(stdout)

    assert exit_code == 0
    assert any(row["ticker"] == "NVDA" for row in rows)
    assert stderr == ""


def test_cli_returns_error_for_invalid_db_path():
    exit_code, stdout, stderr = _run_cli(
        [
            "--db",
            "/tmp/does-not-exist-report-canonical-v2.db",
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


def test_cli_csv_specific_sanity(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    with _create_db(db_path) as conn:
        _insert_run(conn, run_id="run-1", created_at_utc="2026-05-30T00:00:00Z")
        _insert_group_row(conn, run_id="run-1", group_type="layer", group_name="Infrastructure")
        _insert_group_row(conn, run_id="run-1", group_type="subindustry", group_name="Semis")
        _insert_ticker_row(
            conn,
            run_id="run-1",
            ticker="NVDA",
            primary_layer="Infrastructure",
            primary_subindustry="Semis",
            latest_bearish_relevance_reason=None,
        )
        _insert_classification_row(
            conn,
            run_id="run-1",
            ticker="NVDA",
            primary_reason="BULLISH, SETUP / NEEDS CONFIRMATION",
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
    trigger_row = next(row for row in rows if row["section"] == "daily_trigger_rows")

    assert exit_code == 0
    assert first_line == (
        "section,key,value,ticker,classification_state,primary_reason,"
        "blocking_reason,next_action,current_watchlist_status,primary_layer,"
        "primary_subindustry,layer_context_risk_status,subindustry_context_risk_status,"
        "breakout_signal,pullback_signal,exit_risk_signal,row_type,layer,subindustry,"
        "timing_state,overheat_risk_level,pct_above_ema20,pct_above_ma10,"
        "distance_to_ema20_pct,deferred_section,status,reason"
    )
    assert trigger_row["primary_reason"] == "BULLISH, SETUP / NEEDS CONFIRMATION"
    assert trigger_row["blocking_reason"] == ""
    assert stderr == ""
