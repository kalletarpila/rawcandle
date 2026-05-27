import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from dev_tools.run_datacenter_dashboard_ticker_enrichment_write import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_empty_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_source_table_only(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT,
                primary_layer TEXT,
                primary_subindustry TEXT,
                close REAL,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                price_data_status TEXT,
                ticker_trend_state TEXT,
                latest_structure_label TEXT,
                latest_structure_age_trading_days INTEGER,
                latest_structure_freshness TEXT,
                latest_bos_event_type TEXT,
                latest_bos_age_trading_days INTEGER,
                latest_bos_freshness TEXT,
                latest_reset_reason TEXT,
                latest_reset_age_trading_days INTEGER,
                latest_reset_freshness TEXT,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                in_datacenter_ecosystem TEXT,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                exit_reason TEXT,
                high_exit_risk_days_count INTEGER,
                breakout_signal INTEGER,
                pullback_signal INTEGER,
                ma_break_status TEXT
            )
            """
        )


def _create_source_and_destination_db(path: Path) -> None:
    _create_source_table_only(path)
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _insert_source_rows(path: Path) -> None:
    _insert_custom_source_row(
        path,
        ticker="NVDA",
        primary_subindustry="AI Accelerators",
        close=100.5,
        return_5d=1.2,
        return_10d=2.4,
        return_20d=4.5,
        return_60d=12.0,
        price_data_status="OK",
        ticker_trend_state="UP",
        latest_structure_label="HH",
        latest_structure_age_trading_days=3,
        latest_structure_freshness="FRESH",
        latest_bos_event_type="BOS_UP",
        latest_bos_age_trading_days=2,
        latest_bos_freshness="FRESH",
        latest_reset_reason="EMA20_LOST",
        latest_reset_age_trading_days=5,
        bullish_candle_signal=1,
        bullish_divergence_signal=1,
        hidden_bullish_divergence_signal=0,
    )
    _insert_custom_source_row(
        path,
        ticker="ANET",
        primary_subindustry="Networking",
        close=95.0,
        return_5d=0.5,
        return_10d=1.0,
        return_20d=2.0,
        return_60d=6.0,
        price_data_status="OK",
        ticker_trend_state="UP",
        latest_structure_label="HL",
        latest_structure_age_trading_days=4,
        latest_structure_freshness="STALE",
        latest_bos_event_type="BOS_UP",
        latest_bos_age_trading_days=3,
        latest_bos_freshness="STALE",
    )
    _insert_custom_source_row(path, ticker="")
    _insert_custom_source_row(path, ticker="2026-05-22")
    _insert_custom_source_row(path, ticker="Layer Header")


def _insert_custom_source_row(path: Path, **overrides: object) -> None:
    row = {
        "signal_date": "2026-05-22",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "ticker": "AAA",
        "primary_layer": "Infrastructure",
        "primary_subindustry": "AI Accelerators",
        "close": 100.0,
        "return_5d": 1.0,
        "return_10d": 2.0,
        "return_20d": 3.0,
        "return_60d": 4.0,
        "price_data_status": "OK",
        "ticker_trend_state": "UP",
        "latest_structure_label": "HH",
        "latest_structure_age_trading_days": 3,
        "latest_structure_freshness": "STRUCTURE_FRESH",
        "latest_bos_event_type": "BOS_UP",
        "latest_bos_age_trading_days": 2,
        "latest_bos_freshness": "BOS_FRESH",
        "latest_reset_reason": None,
        "latest_reset_age_trading_days": None,
        "latest_reset_freshness": None,
        "bullish_candle_signal": 0,
        "bullish_divergence_signal": 0,
        "hidden_bullish_divergence_signal": 0,
        "in_datacenter_ecosystem": None,
        "exit_risk_signal": 0,
        "exit_risk_severity": None,
        "exit_reason": None,
        "high_exit_risk_days_count": None,
        "breakout_signal": 0,
        "pullback_signal": 0,
        "ma_break_status": None,
    }
    row.update(overrides)
    columns = list(row)
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            INSERT INTO dc_ticker_swing_signal_daily ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            """,
            tuple(row[column] for column in columns),
        )


def _destination_rows(path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(
                """
                SELECT *
                FROM dc_dashboard_ticker_enrichment_daily
                ORDER BY ticker ASC
                """
            ).fetchall()
        )


def _destination_count(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily").fetchone()
    return int(row[0])


def _create_watchlist_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_missing_analysis_db_fails_clearly_and_does_not_create_file(tmp_path, capsys):
    db_path = tmp_path / "missing-analysis.db"

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not db_path.exists()
    assert captured.out == ""
    assert "analysis_db not found:" in captured.err


def test_missing_source_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_empty_db(db_path)
    with sqlite3.connect(db_path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing required source table: dc_ticker_swing_signal_daily" in captured.err


def test_missing_destination_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_table_only(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert (
        "missing required destination table: dc_dashboard_ticker_enrichment_daily"
        in captured.err
    )


def test_replace_date_inserts_valid_rows_and_excludes_pseudo_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_REPLACE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert [row["ticker"] for row in rows] == ["ANET", "NVDA"]
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.source_rows=5" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.valid_ticker_rows=2" in output
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.excluded_pseudo_rows=3" in output
    )
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=2" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.updated_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.deleted_existing_rows=0" in output
    )


def test_field_mapping_persists_expected_values(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_FIELDS",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    nvda = rows["NVDA"]
    assert nvda["primary_layer"] == "Infrastructure"
    assert nvda["primary_subindustry"] == "AI Accelerators"
    assert nvda["close"] == 100.5
    assert nvda["return_5d"] == 1.2
    assert nvda["return_10d"] == 2.4
    assert nvda["return_20d"] == 4.5
    assert nvda["return_60d"] == 12.0
    assert nvda["trend_state"] == "UP"
    assert nvda["latest_structure_label"] == "HH"
    assert nvda["latest_bos_event_type"] == "BOS_UP"
    assert nvda["latest_reset_reason"] == "EMA20_LOST"
    assert nvda["daily_status"] == "NEUTRAL_MONITOR"
    assert nvda["current_status"] == "NEUTRAL_MONITOR"
    assert nvda["freshness_status"] == "FRESH"
    assert nvda["primary_reason"] is None
    assert nvda["source_components"] == (
        "dc_ticker_swing_signal_daily,dc_ticker_swing_signal_daily:daily_status_mapping_v1"
    )
    assert nvda["data_quality_status"] == "OK"
    assert nvda["calc_version"] == "DATACENTER_DASHBOARD_TICKER_ENRICHMENT_V1"
    assert nvda["run_id"] == "RUN_FIELDS"
    assert nvda["created_at_utc"] not in (None, "")
    assert nvda["is_watchlist"] == 0
    assert nvda["action"] is None
    assert nvda["high_exit_risk_days_count"] == 0


def test_high_exit_risk_maps_to_daily_status_current_status_and_reason(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
        exit_reason="HIGH_EXIT_TEST",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "HIGH_EXIT_RISK"
    assert row["current_status"] == "HIGH_EXIT_RISK"
    assert row["primary_reason"] == "HIGH_EXIT_TEST"
    assert row["action"] is None


def test_medium_exit_risk_maps_to_medium_exit_risk(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        exit_risk_signal=1,
        exit_risk_severity="MEDIUM",
        exit_reason="MEDIUM_EXIT_TEST",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "MEDIUM_EXIT_RISK"
    assert row["current_status"] == "MEDIUM_EXIT_RISK"
    assert row["high_exit_risk_days_count"] == 1
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.high_exit_window_rows=30" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.high_exit_window_derived_rows=1" in output


def test_high_exit_risk_days_count_maps_to_one_for_high_severity(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, exit_risk_severity="HIGH")

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 1


def test_high_exit_risk_days_count_maps_to_zero_for_low_or_empty(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, exit_risk_severity="LOW")

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 0


def test_explicit_high_exit_risk_days_count_is_preferred_over_derived_value(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        exit_risk_severity="HIGH",
        high_exit_risk_days_count=7,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 7


def test_window_derived_high_exit_risk_days_count_counts_earlier_high_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-20",
        ticker="AAA",
        exit_risk_severity="HIGH",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        exit_risk_severity="LOW",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] >= 1
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.high_exit_window_rows=30" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.high_exit_window_derived_rows=1" in output


def test_exit_risk_signal_contributes_to_windowed_high_exit_count(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-20",
        ticker="AAA",
        exit_risk_signal=1,
        exit_risk_severity=None,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        exit_risk_signal=0,
        exit_risk_severity="LOW",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 1


def test_windowed_high_exit_count_respects_taxonomy_version(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-20",
        ticker="AAA",
        taxonomy_version="OTHER_TAXONOMY",
        exit_risk_severity="HIGH",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        exit_risk_severity="LOW",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 0


def test_windowed_high_exit_count_does_not_use_future_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-23",
        ticker="AAA",
        exit_risk_severity="HIGH",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        exit_risk_severity="LOW",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 0


def test_high_exit_window_rows_limit_is_respected(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-18",
        ticker="AAA",
        exit_risk_severity="HIGH",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        exit_risk_severity="LOW",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        exit_risk_severity="LOW",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--high-exit-window-rows",
            "2",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["high_exit_risk_days_count"] == 0
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.high_exit_window_rows=2" in output


def test_breakout_signal_maps_to_breakout_candidate(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, breakout_signal=1)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "BREAKOUT_CANDIDATE"
    assert row["primary_reason"] == "BREAKOUT_SIGNAL"


def test_pullback_signal_maps_to_pullback_candidate(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, pullback_signal=1)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "PULLBACK_CANDIDATE"
    assert row["primary_reason"] == "PULLBACK_SIGNAL"


def test_missing_price_maps_before_other_statuses(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        price_data_status="MISSING_AS_OF_DATE",
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
        breakout_signal=1,
        pullback_signal=1,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "MISSING_PRICE"
    assert row["current_status"] == "MISSING_PRICE"


def test_neutral_source_maps_to_neutral_monitor(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "NEUTRAL_MONITOR"
    assert row["current_status"] == "NEUTRAL_MONITOR"


def test_freshness_status_prefers_bos_down_then_reset_then_structure(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        latest_bos_event_type="BOS_DOWN",
        latest_bos_freshness="BOS_DOWN_FRESH",
        latest_reset_reason="DOUBLE_BOS_DOWN",
        latest_reset_freshness="RESET_FRESH",
        latest_structure_freshness="STRUCTURE_FRESH",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["freshness_status"] == "BOS_DOWN_FRESH"


def test_rolling_2d_status_maps_to_emergency_sell_pressure_from_high_exit_and_bos_down(
    tmp_path, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
        latest_bos_event_type="BOS_DOWN",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["daily_status"] == "HIGH_EXIT_RISK"
    assert row["rolling_2d_status"] == "EMERGENCY_SELL_PRESSURE"


def test_rolling_2d_status_maps_to_watch_pressure_from_medium_risk_without_bos_down(
    tmp_path, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        exit_risk_signal=1,
        exit_risk_severity="MEDIUM",
        latest_bos_event_type="BOS_UP",
        latest_reset_reason=None,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["rolling_2d_status"] == "WATCH_PRESSURE"


def test_rolling_2d_status_maps_to_no_emergency_for_neutral_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["rolling_2d_status"] == "NO_EMERGENCY"


def test_watchlist_file_marks_matching_tickers(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    watchlist_file = _create_watchlist_file(tmp_path / "watchlist.txt", "NVDA\nANET\n")
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_WATCHLIST",
            "--watchlist-file",
            str(watchlist_file),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["is_watchlist"] == 1
    assert rows["ANET"]["is_watchlist"] == 1
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.watchlist_tickers=2" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.watchlist_matches=2" in output


def test_without_watchlist_file_preserves_all_zero_membership(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_NO_WATCHLIST",
        ]
    )

    _ = capsys.readouterr()
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["is_watchlist"] == 0
    assert rows["ANET"]["is_watchlist"] == 0


def test_watchlist_parser_ignores_comments_blanks_uppercases_and_dedupes(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    watchlist_file = _create_watchlist_file(
        tmp_path / "watchlist.txt",
        "\n# comment\nnvda\nANET\nnvda\n",
    )
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_WATCHLIST_PARSE",
            "--watchlist-file",
            str(watchlist_file),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["is_watchlist"] == 1
    assert rows["ANET"]["is_watchlist"] == 1
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.watchlist_tickers=2" in output


def test_missing_watchlist_file_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    missing = tmp_path / "missing_watchlist.txt"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--watchlist-file",
            str(missing),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "watchlist_file not found:" in captured.err


def test_empty_watchlist_file_succeeds_with_warning(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    watchlist_file = _create_watchlist_file(tmp_path / "watchlist.txt", "# only comments\n\n")
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_WATCHLIST_EMPTY",
            "--watchlist-file",
            str(watchlist_file),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["is_watchlist"] == 0
    assert rows["ANET"]["is_watchlist"] == 0
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.watchlist_tickers=0" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.warning=WATCHLIST_FILE_EMPTY" in output


def test_dry_run_does_not_mutate_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_DRY",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.dry_run=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=2" in output


def test_insert_missing_keeps_existing_row_unchanged_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, data_quality_status, calc_version, run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "OldLayer",
                "OldSub",
                1.0,
                "OLD",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
                0,
            ),
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "insert-missing",
            "--run-id",
            "RUN_INSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["primary_layer"] == "OldLayer"
    assert rows["NVDA"]["data_quality_status"] == "OLD"
    assert rows["ANET"]["run_id"] == "RUN_INSERT"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.skipped_existing_rows=1" in output


def test_upsert_updates_existing_row_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, data_quality_status, calc_version, run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "OldLayer",
                "OldSub",
                1.0,
                "OLD",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
                0,
            ),
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "upsert",
            "--run-id",
            "RUN_UPSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["primary_layer"] == "Infrastructure"
    assert rows["NVDA"]["data_quality_status"] == "OK"
    assert rows["NVDA"]["run_id"] == "RUN_UPSERT"
    assert rows["ANET"]["run_id"] == "RUN_UPSERT"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.updated_rows=1" in output


def test_replace_date_deletion_scope_is_exact(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, data_quality_status, calc_version,
                run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "OLD1",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                    0,
                ),
                (
                    "2026-05-21",
                    "DC_TAXONOMY_FULL_V1",
                    "KEEP_DATE",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                    0,
                ),
                (
                    "2026-05-22",
                    "OTHER_TAXONOMY",
                    "KEEP_TAX",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                    0,
                ),
            ],
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_SCOPE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    with sqlite3.connect(db_path) as conn:
        kept_date = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-21' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0]
        kept_tax = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'OTHER_TAXONOMY'
            """
        ).fetchone()[0]
        replaced_same_slice = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0]
    assert kept_date == 1
    assert kept_tax == 1
    assert replaced_same_slice == 2
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.deleted_existing_rows=1" in output
    )


def test_limit_works_deterministically(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_LIMIT",
            "--limit",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "ANET"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.source_rows=5" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.valid_ticker_rows=1" in output
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.excluded_pseudo_rows=3" in output
    )


def test_audit_after_write_reports_ticker_ready_and_overall_partial(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    write_exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_AUDIT",
        ]
    )
    assert write_exit_code == 0
    _ = capsys.readouterr()

    audit_exit_code = audit_main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )
    output = capsys.readouterr().out
    assert audit_exit_code == 0
    assert "section_readiness;ticker_enrichment;READY;2;rows_available" in output
    assert "section_readiness;group_enrichment;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;PARTIAL;2;some_sections_empty" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.ticker_rows=2" in output
