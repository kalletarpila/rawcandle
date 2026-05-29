import sqlite3
import json
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
)
from dev_tools.run_datacenter_dashboard_ticker_enrichment_write import main
from analysis.datacenter_indices.rolling2_sell_pressure_classifier import (
    Rolling2SellPressureClassification,
)
from analysis.datacenter_indices.rolling5_pullback_classifier import (
    Rolling5PullbackClassification,
)
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
                signal_version TEXT,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT,
                primary_layer TEXT,
                primary_subindustry TEXT,
                close REAL,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                distance_to_ema20_pct REAL,
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
                latest_bullish_signal_age_td INTEGER,
                latest_bearish_signal_age_td INTEGER,
                bullish_candle_signal INTEGER,
                bearish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                bearish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                hidden_bearish_divergence_signal INTEGER,
                structure_warning_overrides_bullish_signal INTEGER,
                in_datacenter_ecosystem TEXT,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                exit_reason TEXT,
                high_exit_risk_days_count INTEGER,
                breakout_signal INTEGER,
                pullback_signal INTEGER,
                conservative_ema20_pullback_signal INTEGER,
                fast_ema10_pullback_signal INTEGER,
                latest_bos_event_date TEXT,
                latest_reset_event_date TEXT,
                rolling_5d_status TEXT,
                ma_break_status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                member_count INTEGER,
                eligible_count INTEGER,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                pct_above_ma10 REAL,
                pct_above_ema20 REAL,
                pct_above_rising_ema20 REAL,
                ma10_breadth_delta_5d REAL,
                ema20_breadth_delta_5d REAL,
                trend_breadth REAL,
                weakness_breadth REAL,
                overheat_risk_level TEXT,
                timing_state TEXT,
                timing_reason TEXT,
                data_quality_status TEXT,
                signal_version TEXT,
                run_id TEXT,
                created_at_utc TEXT
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
        "signal_version": "DC_SWING_SIGNAL_V1",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "ticker": "AAA",
        "primary_layer": "Infrastructure",
        "primary_subindustry": "AI Accelerators",
        "close": 100.0,
        "return_5d": 1.0,
        "return_10d": 2.0,
        "return_20d": 3.0,
        "return_60d": 4.0,
        "distance_to_ema20_pct": 1.5,
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
        "latest_bullish_signal_age_td": None,
        "latest_bearish_signal_age_td": None,
        "bullish_candle_signal": 0,
        "bearish_candle_signal": 0,
        "bullish_divergence_signal": 0,
        "bearish_divergence_signal": 0,
        "hidden_bullish_divergence_signal": 0,
        "hidden_bearish_divergence_signal": 0,
        "structure_warning_overrides_bullish_signal": 0,
        "in_datacenter_ecosystem": None,
        "exit_risk_signal": 0,
        "exit_risk_severity": None,
        "exit_reason": None,
        "high_exit_risk_days_count": None,
        "breakout_signal": 0,
        "pullback_signal": 0,
        "conservative_ema20_pullback_signal": 0,
        "fast_ema10_pullback_signal": 0,
        "latest_bos_event_date": None,
        "latest_reset_event_date": None,
        "rolling_5d_status": None,
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


def _insert_group_context_row(path: Path, **overrides: object) -> None:
    row = {
        "signal_date": "2026-05-22",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "group_type": "subindustry",
        "group_name": "AI Accelerators",
        "member_count": 1,
        "eligible_count": 1,
        "return_5d": 0.0,
        "return_10d": 0.0,
        "return_20d": 0.0,
        "return_60d": 0.0,
        "pct_above_ma10": 0.0,
        "pct_above_ema20": 0.0,
        "pct_above_rising_ema20": 0.0,
        "ma10_breadth_delta_5d": 0.0,
        "ema20_breadth_delta_5d": 0.0,
        "trend_breadth": 0.0,
        "weakness_breadth": 0.0,
        "overheat_risk_level": "LOW",
        "timing_state": "BUY_ZONE",
        "timing_reason": "TEST",
        "data_quality_status": "OK",
        "signal_version": "DC_SWING_SIGNAL_V1",
        "run_id": "RUN_GROUP",
        "created_at_utc": "2026-05-22T10:00:00Z",
    }
    row.update(overrides)
    columns = list(row)
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            INSERT INTO dc_group_swing_signal_daily ({", ".join(columns)})
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
    assert nvda["freshness_status"] == "MIXED_SIGNALS"
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


def test_exit_reason_is_preserved_in_source_run_ids_payload(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="AAA",
        exit_reason="close_below_ema20;return_10d_lt_minus_8pct",
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
    assert row["source_run_ids"] is not None
    assert '"exit_reason":"close_below_ema20;return_10d_lt_minus_8pct"' in row["source_run_ids"]


def test_full_ma_break_helper_output_is_preserved_in_source_run_ids_payload(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ticker="AAA", ma_break_status=None)

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.build_swing_ma_break_status_rows",
        lambda **kwargs: [
            {
                "ticker": "AAA",
                "as_of_date": "2026-05-22",
                "close": 100.0,
                "ema20": 101.5,
                "sma50": 110.0,
                "dist_ema20_pct": -0.015,
                "dist_sma50_pct": -0.09,
                "close_below_ema20": 1,
                "ema20_break_pct": -1.5,
                "ema20_break_confirmed": 0,
                "consecutive_closes_below_ema20": 2,
                "close_below_sma50": 0,
                "sma50_break_pct": 0.0,
                "sma50_break_confirmed": 0,
                "consecutive_closes_below_sma50": 0,
                "ma_break_status": "EMA20_WARNING",
            }
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
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["ma_break_status"] == "EMA20_WARNING"
    assert row["source_run_ids"] is not None
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["ma_break"]["close_below_ema20"] == 1
    assert payload["ma_break"]["ema20_break_confirmed"] == 0
    assert payload["ma_break"]["consecutive_closes_below_ema20"] == 2
    assert payload["ma_break"]["ema20_break_pct"] == -1.5
    assert payload["ma_break"]["ma_break_status"] == "EMA20_WARNING"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.ma_break_helper_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.ma_break_payload_rows=1" in output


def test_freshness_helper_output_is_preserved_in_source_run_ids_payload(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="AAA",
        bullish_candle_signal=0,
        bullish_divergence_signal=0,
        hidden_bullish_divergence_signal=0,
        latest_bullish_signal_age_td=None,
        structure_warning_overrides_bullish_signal=0,
        latest_structure_freshness="NO_RECENT_SIGNAL",
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.build_swing_signal_freshness_rows",
        lambda **kwargs: [
            {
                "ticker": "AAA",
                "as_of_date": "2026-05-22",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "latest_bullish_signal_age_td": 0,
                "latest_bearish_signal_age_td": None,
                "latest_bos_up_age_td": 1,
                "latest_bos_down_age_td": None,
                "latest_reset_age_td": None,
                "bullish_candle_age_td": 0,
                "bearish_candle_age_td": None,
                "bullish_divergence_age_td": None,
                "bearish_divergence_age_td": None,
                "hidden_bullish_divergence_age_td": None,
                "hidden_bearish_divergence_age_td": None,
                "structure_warning_overrides_bullish_signal": 0,
            }
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
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["freshness_status"] == "FRESH_BULLISH_SIGNAL"
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["freshness"]["freshness_status"] == "FRESH_BULLISH_SIGNAL"
    assert payload["freshness"]["latest_bullish_signal_age_td"] == 0
    assert payload["freshness"]["structure_warning_overrides_bullish_signal"] == 0
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.freshness_helper_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.freshness_payload_rows=1" in output


def test_freshness_helper_output_overrides_local_approximation_when_present(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="AAA",
        bullish_candle_signal=0,
        bullish_divergence_signal=0,
        hidden_bullish_divergence_signal=0,
        latest_bullish_signal_age_td=None,
        latest_structure_freshness="NO_RECENT_SIGNAL",
        structure_warning_overrides_bullish_signal=0,
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.build_swing_signal_freshness_rows",
        lambda **kwargs: [
            {
                "ticker": "AAA",
                "as_of_date": "2026-05-22",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "latest_bullish_signal_age_td": 0,
                "latest_bearish_signal_age_td": None,
                "structure_warning_overrides_bullish_signal": 0,
            }
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
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert row["freshness_status"] == "FRESH_BULLISH_SIGNAL"


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


def test_pullback_signal_maps_to_conservative_rolling_5d_pullback_candidate(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, pullback_signal=1, ma_break_status="OK")

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
    assert row["rolling_5d_status"] == "PULLBACK_CANDIDATE"


def test_default_behavior_keeps_upstream_rolling5_disabled(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, pullback_signal=1, ma_break_status="OK")
    called = {"value": False}

    def _should_not_run(_row):
        called["value"] = True
        raise AssertionError("shared helper should not run without flag")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.classify_rolling_5_pullback_row",
        _should_not_run,
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
    row = _destination_rows(db_path)[0]
    assert exit_code == 0
    assert row["rolling_5d_status"] == "PULLBACK_CANDIDATE"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.use_upstream_rolling5_pullback=0" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.upstream_rolling5_status=SKIPPED" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling5_classifier_source=skipped" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling5_classifier_rows=0" in output
    assert called["value"] is False


def test_shared_helper_is_called_and_maps_to_rolling_5d_status_when_enabled(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ticker="AAA", pullback_signal=0)

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write._extract_upstream_rolling5_rows",
        lambda **kwargs: {
            "AAA": {
                "ticker": "AAA",
                "rolling_5_pullback_state": "EARLY_PULLBACK",
                "pullback_days": 3,
                "fast_ema10_pullback_days": 2,
                "conservative_ema20_pullback_days": 1,
                "current_watchlist_status": "PULLBACK_CANDIDATE",
                "window_watchlist_status": "PULLBACK_CANDIDATE",
                "latest_ticker_trend_state": "UP",
                "exit_risk_days": 0,
            }
        },
    )
    called = {"count": 0}

    def _fake_classify(row):
        called["count"] += 1
        assert row["ticker"] == "AAA"
        return Rolling5PullbackClassification(
            "PULLBACK_CANDIDATE",
            "CONFIRMED_EMA20_PULLBACK_CONTEXT",
            "",
            "REVIEW_FOR_DAILY_TRIGGER",
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.classify_rolling_5_pullback_row",
        _fake_classify,
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
            "--use-upstream-rolling5-pullback",
        ]
    )

    output = capsys.readouterr().out
    row = _destination_rows(db_path)[0]
    assert exit_code == 0
    assert called["count"] == 1
    assert row["rolling_5d_status"] == "PULLBACK_CANDIDATE"
    assert row["source_run_ids"] is not None
    assert '"primary_reason":"CONFIRMED_EMA20_PULLBACK_CONTEXT"' in row["source_run_ids"]
    assert '"next_action":"REVIEW_FOR_DAILY_TRIGGER"' in row["source_run_ids"]
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.use_upstream_rolling5_pullback=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.upstream_rolling5_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.upstream_rolling5_matched_tickers=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.upstream_rolling5_status=OK" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling5_classifier_source=shared_helper" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling5_classifier_rows=1" in output


def test_upstream_primary_reason_does_not_overwrite_existing_reason_unless_empty(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ticker="AAA", pullback_signal=1, exit_reason="SOURCE_REASON")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write._extract_upstream_rolling5_rows",
        lambda **kwargs: {
            "AAA": {
                "ticker": "AAA",
                "rolling_5_pullback_state": "EARLY_PULLBACK",
                "primary_reason": "UPSTREAM_REASON",
                "blocking_reason": "STRUCTURE_BLOCKED",
                "current_watchlist_status": "PULLBACK_CANDIDATE",
                "window_watchlist_status": "PULLBACK_CANDIDATE",
                "latest_ticker_trend_state": "UP",
                "pullback_days": 2,
                "exit_risk_days": 0,
            }
        },
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
            "--use-upstream-rolling5-pullback",
        ]
    )

    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    assert exit_code == 0
    assert row["primary_reason"] == "SOURCE_REASON"


def test_upstream_extraction_failure_fails_clearly(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ticker="AAA")

    def _boom(**kwargs):
        raise ValueError("upstream rolling5 unavailable")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write._extract_upstream_rolling5_rows",
        _boom,
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
            "--use-upstream-rolling5-pullback",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ERROR: upstream rolling5 unavailable" in captured.err
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.upstream_rolling5_status=FAILED" in captured.out


def test_failed_pullback_helper_output_is_exposed_to_adapter_raw_fields(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ticker="AAA", pullback_signal=0)

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write._extract_upstream_rolling5_rows",
        lambda **kwargs: {
            "AAA": {
                "ticker": "AAA",
                "rolling_5_pullback_state": "EARLY_PULLBACK",
                "pullback_days": 2,
                "fast_ema10_pullback_days": 1,
                "conservative_ema20_pullback_days": 0,
                "current_watchlist_status": "PULLBACK_CANDIDATE",
                "window_watchlist_status": "PULLBACK_CANDIDATE",
                "latest_ticker_trend_state": "UP",
                "exit_risk_days": 0,
                "latest_bos_freshness": "FRESH",
            }
        },
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.classify_rolling_5_pullback_row",
        lambda row: Rolling5PullbackClassification(
            "FAILED_PULLBACK",
            "PULLBACK_SETUP_BLOCKED",
            "recent_bos_down",
            "REMOVE_FROM_PULLBACK_LIST",
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
            "replace-date",
            "--use-upstream-rolling5-pullback",
        ]
    )

    _ = capsys.readouterr()
    assert exit_code == 0
    stored_row = dict(_destination_rows(db_path)[0])
    assert stored_row["rolling_5d_status"] == "FAILED_PULLBACK"
    rolling_row = next(
        row
        for row in build_dashboard_rows_from_ticker_enrichment_rows([stored_row])
        if row.horizon == "rolling 5d"
    )
    assert rolling_row.blocking_reasons == "recent_bos_down"
    assert rolling_row.raw_fields["blocking_reason"] == "recent_bos_down"
    assert rolling_row.raw_fields["next_action"] == "REMOVE_FROM_PULLBACK_LIST"


def test_pullback_lookback_signal_maps_to_rolling_5d_status(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        pullback_signal=1,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        pullback_signal=0,
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
    assert row["rolling_5d_status"] == "PULLBACK_CANDIDATE"
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.pullback_window_candidate_rows=1"
        in output
    )


def test_pullback_signal_with_structure_blocker_maps_to_failed_pullback(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        pullback_signal=1,
        latest_bos_event_type="BOS_DOWN",
        latest_bos_freshness="FRESH",
        latest_reset_reason="DOUBLE_BOS_DOWN",
        latest_reset_freshness="FRESH",
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
    assert row["rolling_5d_status"] == "FAILED_PULLBACK"
    assert row["freshness_status"] == "FRESH_BEARISH_SIGNAL"


def test_pullback_lookback_with_structure_blocker_maps_to_failed_pullback(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-20",
        ticker="AAA",
        pullback_signal=1,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        latest_bos_event_type="BOS_DOWN",
        latest_reset_reason="DOUBLE_BOS_DOWN",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        pullback_signal=0,
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
    assert row["rolling_5d_status"] == "FAILED_PULLBACK"
    assert row["freshness_status"] == "FRESH_BULLISH_SIGNAL"
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.pullback_window_structure_override_rows=1"
        in output
    )


def test_same_day_bullish_signal_maps_to_fresh_bullish_signal(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, bullish_candle_signal=1)

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
    assert row["freshness_status"] == "FRESH_BULLISH_SIGNAL"


def test_bullish_signal_from_lookback_maps_to_fresh_bullish_signal(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        bullish_candle_signal=1,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        bullish_candle_signal=0,
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
    assert row["freshness_status"] == "FRESH_BULLISH_SIGNAL"
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.pullback_window_bullish_signal_rows=1"
        in output
    )


def test_pullback_lookback_respects_taxonomy_version(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        taxonomy_version="OTHER_TAXONOMY",
        pullback_signal=1,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        pullback_signal=0,
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
    row = _destination_rows(db_path)[0]
    assert row["rolling_5d_status"] is None


def test_pullback_lookback_does_not_use_future_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-23",
        ticker="AAA",
        pullback_signal=1,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        pullback_signal=0,
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
    row = _destination_rows(db_path)[0]
    assert row["rolling_5d_status"] is None


def test_pullback_lookback_rows_limit_is_respected(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-18",
        ticker="AAA",
        pullback_signal=1,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        pullback_signal=0,
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        pullback_signal=0,
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
            "--pullback-lookback-rows",
            "2",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["rolling_5d_status"] is None
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.pullback_lookback_rows=2" in output


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
    assert row["freshness_status"] == "FRESH_BEARISH_SIGNAL"


def test_rolling_2d_status_maps_to_emergency_sell_pressure_from_high_exit_and_bos_down(
    tmp_path, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-21",
        ticker="AAA",
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
        latest_bos_event_type="BOS_DOWN",
        latest_bos_freshness="FRESH",
        exit_reason="close_below_ema20",
    )
    _insert_custom_source_row(
        db_path,
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
        latest_bos_event_type="BOS_DOWN",
        latest_bos_freshness="FRESH",
        exit_reason="close_below_ema20",
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


def test_shared_rolling2_helper_output_is_preserved_in_source_run_ids_payload(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="AAA",
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
        exit_reason="close_below_ema20;return_10d_lt_minus_8pct",
        latest_bos_event_type="BOS_DOWN",
        latest_bos_freshness="FRESH",
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.classify_rolling_2_sell_pressure_row",
        lambda row: Rolling2SellPressureClassification(
            rolling_2_sell_pressure_state="EMERGENCY_SELL_PRESSURE",
            primary_reason="RECENT_BOS_DOWN",
            risk_reason="high_exit_risk_days",
            next_action="SELL_OR_REMOVE",
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
            "replace-date",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["rolling_2d_status"] == "EMERGENCY_SELL_PRESSURE"
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["rolling2"]["rolling_2_sell_pressure_state"] == "EMERGENCY_SELL_PRESSURE"
    assert payload["rolling2"]["primary_reason"] == "RECENT_BOS_DOWN"
    assert payload["rolling2"]["risk_reason"] == "high_exit_risk_days"
    assert payload["rolling2"]["next_action"] == "SELL_OR_REMOVE"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling2_helper_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling2_payload_rows=1" in output


def test_group_aware_context_can_drive_group_risk_in_shared_rolling2_payload(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="HPQ",
        primary_layer="IT hardware",
        primary_subindustry="Storage",
        exit_risk_signal=0,
        exit_risk_severity=None,
        breakout_signal=0,
        pullback_signal=0,
        latest_structure_label="HL",
        latest_bos_event_type="BOS_UP",
        latest_bos_freshness="STALE",
        latest_reset_reason="DOUBLE_BOS_UP",
        latest_reset_freshness="STALE",
    )
    _insert_group_context_row(
        db_path,
        group_type="subindustry",
        group_name="Storage",
        timing_state="TRIM_WATCH",
        overheat_risk_level="ELEVATED",
    )
    _insert_group_context_row(
        db_path,
        group_type="layer",
        group_name="IT hardware",
        timing_state="BUY_ZONE",
        overheat_risk_level="LOW",
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
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["rolling2"]["rolling_2_sell_pressure_state"] == "WATCH_PRESSURE"
    assert payload["rolling2"]["risk_reason"] == "GROUP_RISK"
    assert payload["rolling2"]["current_watchlist_status"] == "GROUP_RISK"
    assert payload["rolling2"]["window_watchlist_status"] == "GROUP_RISK"


def test_shared_rolling30_helper_output_is_preserved_in_source_run_ids_payload(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="AAA",
        pullback_signal=1,
        ticker_trend_state="UP",
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.build_rolling_30_role_rows_from_base_rows",
        lambda rows: (
            [
                {
                    "ticker": "AAA",
                    "rolling_30_buy_state": "BUY_ZONE",
                    "current_watchlist_status": "PULLBACK_CANDIDATE",
                    "window_watchlist_status": "PULLBACK_CANDIDATE",
                    "breakout_days": 0,
                    "pullback_days": 3,
                    "exit_risk_days": 0,
                    "primary_reason": "UP_STRUCTURE_WITH_PULLBACK_CONTEXT",
                    "blocking_reason": "",
                    "latest_ticker_trend_state": "UP",
                    "latest_structure_label": "HH",
                    "latest_bos_event_type": "BOS_UP",
                    "latest_bos_freshness": "FRESH",
                    "latest_reset_reason": None,
                    "latest_reset_freshness": None,
                    "latest_bullish_relevance_class": "RELEVANT",
                    "latest_bullish_relevance_reason": "ok",
                    "latest_bearish_relevance_class": None,
                    "latest_bearish_relevance_reason": None,
                }
            ],
            [],
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
            "replace-date",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    row = _destination_rows(db_path)[0]
    assert row["rolling_30d_status"] == "BUY_ZONE"
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["rolling30"]["rolling_30_buy_state"] == "BUY_ZONE"
    assert payload["rolling30"]["pullback_days"] == 3
    assert payload["rolling30"]["current_watchlist_status"] == "PULLBACK_CANDIDATE"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling30_helper_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling30_payload_rows=1" in output


def test_group_aware_context_can_drive_group_risk_in_shared_rolling30_payload(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        ticker="HPQ",
        primary_layer="IT hardware",
        primary_subindustry="Storage",
        exit_risk_signal=0,
        exit_risk_severity=None,
        breakout_signal=0,
        pullback_signal=0,
        ticker_trend_state="UP",
        latest_structure_label="HL",
        latest_bos_event_type="BOS_UP",
        latest_bos_freshness="STALE",
        latest_reset_reason="DOUBLE_BOS_UP",
        latest_reset_freshness="STALE",
    )
    _insert_group_context_row(
        db_path,
        group_type="subindustry",
        group_name="Storage",
        timing_state="TRIM_WATCH",
        overheat_risk_level="ELEVATED",
    )
    _insert_group_context_row(
        db_path,
        group_type="layer",
        group_name="IT hardware",
        timing_state="BUY_ZONE",
        overheat_risk_level="LOW",
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
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["rolling30"]["current_watchlist_status"] == "GROUP_RISK"
    assert payload["rolling30"]["window_watchlist_status"] == "GROUP_RISK"


def test_group_aware_writer_payload_can_drive_reduce_before_tighten_stop(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    for signal_date, breakout_signal, pullback_signal, exit_risk_signal, exit_risk_severity in (
        ("2026-05-19", 0, 0, 1, "MEDIUM"),
        ("2026-05-20", 0, 0, 1, "MEDIUM"),
        ("2026-05-21", 0, 0, 0, None),
        ("2026-05-22", 1, 0, 0, None),
        ("2026-05-23", 0, 0, 0, None),
        ("2026-05-26", 0, 1, 0, None),
        ("2026-05-27", 1, 0, 0, None),
        ("2026-05-28", 0, 0, 0, None),
    ):
        _insert_custom_source_row(
            db_path,
            signal_date=signal_date,
            ticker="HPQ",
            primary_layer="IT hardware",
            primary_subindustry="Storage",
            exit_risk_signal=exit_risk_signal,
            exit_risk_severity=exit_risk_severity,
            breakout_signal=breakout_signal,
            pullback_signal=pullback_signal,
            high_exit_risk_days_count=23 if signal_date == "2026-05-28" else None,
            latest_structure_label="HL",
            latest_bos_event_type="BOS_UP",
            latest_bos_freshness="STALE",
            latest_reset_reason="DOUBLE_BOS_UP",
            latest_reset_freshness="STALE",
            bullish_candle_signal=1 if signal_date == "2026-05-28" else 0,
            ma_break_status="OK",
            ticker_trend_state="UP",
            price_data_status="OK",
        )
    _insert_group_context_row(
        db_path,
        signal_date="2026-05-28",
        group_type="subindustry",
        group_name="Storage",
        timing_state="TRIM_WATCH",
        overheat_risk_level="ELEVATED",
    )
    _insert_group_context_row(
        db_path,
        signal_date="2026-05-28",
        group_type="layer",
        group_name="IT hardware",
        timing_state="BUY_ZONE",
        overheat_risk_level="LOW",
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-28",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    row = _destination_rows(db_path)[0]
    decisions = build_decisions_from_ticker_enrichment_rows([dict(row)])
    decision = decisions.decisions[0]
    assert decision.action == "REDUCE"
    assert decision.entry_readiness == "NEEDS_RISK_CLEARANCE"
    assert decision.candidate_priority_label == "P3_RISK_CLEARANCE"


def test_rolling30_helper_fallback_keeps_status_empty_when_helper_output_missing(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ticker="AAA")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.build_rolling_30_role_rows_from_base_rows",
        lambda rows: ([], []),
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
    assert row["rolling_30d_status"] is None
    assert '"rolling30":' not in str(row["source_run_ids"] or "")
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling30_payload_rows=0" in output


def test_missing_group_context_keeps_existing_ticker_only_rolling30_fallback(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-20",
        ticker="AAA",
        exit_risk_signal=1,
        exit_risk_severity="HIGH",
    )
    _insert_custom_source_row(
        db_path,
        signal_date="2026-05-22",
        ticker="AAA",
        exit_risk_signal=0,
        exit_risk_severity=None,
        breakout_signal=0,
        pullback_signal=0,
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
    payload = json.loads(row["source_run_ids"].split(":", 1)[1])
    assert payload["rolling30"]["current_watchlist_status"] == "NEUTRAL_MONITOR"
    assert payload["rolling30"]["window_watchlist_status"] == "HIGH_EXIT_RISK"


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


def test_rolling_2d_shared_helper_fallback_remains_when_helper_output_missing(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(
        db_path,
        exit_risk_signal=1,
        exit_risk_severity="MEDIUM",
        latest_bos_event_type="BOS_UP",
        latest_reset_reason=None,
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_enrichment_write.classify_rolling_2_sell_pressure_row",
        lambda row: None,
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
    assert row["rolling_2d_status"] == "WATCH_PRESSURE"
    assert '"rolling2":' not in str(row["source_run_ids"] or "")
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.rolling2_payload_rows=0" in output


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


def test_return_10d_hard_sell_token_is_written_to_window_status_2d(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, return_10d=-0.09)

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
    assert row["window_status_2d"] == "return_10d_lt_minus_8pct"


def test_close_below_ema20_token_is_written_to_window_status_2d(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, distance_to_ema20_pct=-0.25)

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
    assert row["window_status_2d"] == "close_below_ema20"


def test_hard_sell_tokens_are_not_written_when_thresholds_are_not_met(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, return_10d=-0.05, distance_to_ema20_pct=0.5)

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
    assert row["window_status_2d"] is None


def test_direct_ma_break_status_sma50_maps_to_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ma_break_status="SMA50_CONFIRMED_BREAK")

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
    assert row["ma_break_status"] == "SMA50_CONFIRMED_BREAK"


def test_direct_ma_break_status_ema20_maps_to_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_custom_source_row(db_path, ma_break_status="EMA20_CONFIRMED_BREAK")

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
    assert row["ma_break_status"] == "EMA20_CONFIRMED_BREAK"


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
