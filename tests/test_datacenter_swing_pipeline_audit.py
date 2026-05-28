from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_pipeline_audit import load_swing_pipeline_audit


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def _insert_ticker_row(
    path,
    *,
    signal_date: str,
    taxonomy_version: str,
    ticker: str,
    signal_version: str = "DC_SWING_SIGNAL_V1",
    price_data_status: str = "OK",
    breakout_signal=0,
    fast_signal=0,
    conservative_signal=0,
    pullback_signal=0,
    exit_risk_signal=0,
    exit_reason=None,
    exit_risk_severity=None,
    latest_structure_label="HH",
    latest_structure_freshness="FRESH",
    ticker_trend_state="UP",
    latest_bos_event_type=None,
    latest_reset_reason=None,
):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_10d, return_20d, return_60d,
                ema10, ema20, ma10, highest_close_20d, volume_vs_avg20,
                latest_structure_label, latest_structure_confirmed_as_of_date,
                latest_structure_age_trading_days, latest_structure_freshness,
                ticker_trend_state, latest_bos_event_type, latest_reset_reason,
                breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date, taxonomy_version, ticker, "LayerA", "SubA",
                100.0, 0.01, 0.02, 0.03, 0.04,
                99.0, 98.0, 99.0, 100.0, 1.5,
                latest_structure_label, signal_date,
                0, latest_structure_freshness,
                ticker_trend_state, latest_bos_event_type, latest_reset_reason,
                breakout_signal, fast_signal, conservative_signal,
                pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity,
                price_data_status, signal_version, "seed", "2026-05-18T10:00:00Z",
            ),
        )
        conn.commit()


def _insert_group_row(
    path,
    *,
    signal_date: str,
    taxonomy_version: str,
    group_type: str,
    group_name: str,
    signal_version: str = "DC_SWING_SIGNAL_V1",
    data_quality_status: str = "OK",
    timing_state: str | None = "BUY_ZONE",
    overheat_risk_level: str | None = "LOW",
):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name,
                return_5d, return_10d, return_20d, return_60d,
                pct_above_ema20, ema20_breadth_delta_5d,
                overheat_risk_level, timing_state, data_quality_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date, taxonomy_version, group_type, group_name,
                0.01, 0.02, 0.03, 0.04,
                60.0, 5.0,
                overheat_risk_level, timing_state, data_quality_status,
                signal_version, "seed", "2026-05-18T10:00:00Z",
            ),
        )
        conn.commit()


def _insert_synthetic_row(
    path,
    *,
    signal_date: str,
    taxonomy_version: str,
    group_type: str,
    group_name: str,
    calc_version: str = "DC_SWING_OHLC_V1",
    data_quality_status: str = "OK",
    latest_structure_label: str | None = "HH",
    latest_structure_freshness: str | None = "FRESH",
    trend_classification: str | None = "UP",
    synthetic_close: float | None = 100.0,
    ema20: float | None = 98.0,
    relative_close_20: float | None = 1.02,
    latest_reset_event_date: str | None = None,
):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name,
                synthetic_close, ema20, relative_close_20,
                latest_structure_label, latest_structure_age_trading_days, latest_structure_freshness,
                latest_reset_event_date, trend_classification, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_date,
                taxonomy_version,
                group_type,
                group_name,
                synthetic_close,
                ema20,
                relative_close_20,
                latest_structure_label, 0 if latest_structure_label is not None else None, latest_structure_freshness,
                latest_reset_event_date,
                trend_classification,
                data_quality_status,
                calc_version,
                "seed",
                "2026-05-18T10:00:00Z",
            ),
        )
        conn.commit()


def _seed_complete_fixture(path, *, taxonomy_version: str = "DC_TAXONOMY_FULL_V1", signal_version: str = "DC_SWING_SIGNAL_V1"):
    for signal_date in ("2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"):
        _insert_ticker_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, ticker="AAA", signal_version=signal_version, breakout_signal=1, latest_bos_event_type="BOS_UP")
        _insert_ticker_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, ticker="BBB", signal_version=signal_version, exit_risk_signal=1, exit_reason="latest_structure_label_ll", exit_risk_severity="HIGH", latest_reset_reason="DOUBLE_BOS_DOWN")
        _insert_group_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, group_type="ecosystem", group_name="DC_ECOSYSTEM_TOTAL", signal_version=signal_version)
        _insert_group_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, group_type="layer", group_name="LayerA", signal_version=signal_version)
        _insert_group_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, group_type="subindustry", group_name="SubA", signal_version=signal_version)
        _insert_synthetic_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, group_type="layer", group_name="LayerA")
        _insert_synthetic_row(path, signal_date=signal_date, taxonomy_version=taxonomy_version, group_type="subindustry", group_name="SubA")


def test_audit_returns_ok_for_complete_minimal_fixture(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_ticker_count=2,
        expected_group_count=3,
        expected_synthetic_ohlc_count=2,
    )

    assert result["summary"]["daily_ready"] == "YES"
    assert result["summary"]["weekly_ready"] == "YES"
    assert result["summary"]["validation_status"] == "OK"


def test_audit_detects_missing_required_table_and_returns_fail(tmp_path):
    analysis_db = tmp_path / "analysis_missing.db"
    with sqlite3.connect(analysis_db) as conn:
        conn.execute("CREATE TABLE dc_ticker_swing_signal_daily (signal_date TEXT)")
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["validation_status"] == "FAIL"
    assert "dc_group_swing_signal_daily" in result["summary"]["missing_tables"]


def test_audit_detects_scanner_null_count_and_returns_fail(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            "UPDATE dc_ticker_swing_signal_daily SET breakout_signal = NULL WHERE signal_date = '2026-05-15' AND ticker = 'AAA'"
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["scanner_null_count"] == 1
    assert result["summary"]["validation_status"] == "FAIL"


def test_audit_detects_timing_state_null_count_and_returns_fail(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            "UPDATE dc_group_swing_signal_daily SET timing_state = NULL WHERE signal_date = '2026-05-15' AND group_type = 'subindustry'"
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["timing_state_null_count"] == 1
    assert result["summary"]["validation_status"] == "FAIL"


def test_audit_detects_invalid_ticker_structure_label_and_returns_fail(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            "UPDATE dc_ticker_swing_signal_daily SET latest_structure_label = 'H' WHERE signal_date = '2026-05-15' AND ticker = 'AAA'"
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["ticker_structure_label_invalid_count"] == 1
    assert result["summary"]["validation_status"] == "FAIL"


def test_audit_detects_exit_risk_row_missing_severity_and_returns_fail(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            "UPDATE dc_ticker_swing_signal_daily SET exit_risk_severity = NULL WHERE signal_date = '2026-05-15' AND ticker = 'BBB'"
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["exit_risk_severity_missing_for_exit_risk_count"] == 1
    assert result["summary"]["validation_status"] == "FAIL"


def test_audit_reports_missing_as_of_date_but_does_not_fail_solely_because_of_it(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            "UPDATE dc_ticker_swing_signal_daily SET price_data_status = 'MISSING_AS_OF_DATE' WHERE signal_date = '2026-05-15' AND ticker = 'AAA'"
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["missing_as_of_date_count"] == 1
    assert result["summary"]["validation_status"] == "WARN"


def test_audit_reports_synthetic_missing_latest_structure_label_but_does_not_fail_solely_because_of_it(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            "UPDATE dc_group_synthetic_ohlc_daily SET latest_structure_label = NULL, latest_structure_freshness = NULL WHERE ohlc_date = '2026-05-15' AND group_type = 'subindustry'"
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["synthetic_missing_latest_structure_label_count"] == 1
    assert result["summary"]["validation_status"] == "WARN"


def test_valid_reset_state_null_structure_label_is_excluded_from_missing_count(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_synthetic_ohlc_daily
            SET latest_structure_label = NULL,
                latest_structure_freshness = NULL,
                trend_classification = 'NEUTRAL',
                latest_reset_event_date = '2026-05-14'
            WHERE ohlc_date = '2026-05-15' AND group_type = 'subindustry'
            """
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_ticker_count=2,
        expected_group_count=3,
        expected_synthetic_ohlc_count=2,
    )

    assert result["summary"]["synthetic_missing_latest_structure_label_count"] == 0
    assert "synthetic_missing_latest_structure_label_count" not in result["warn_reasons"]
    assert result["summary"]["validation_status"] == "OK"


def test_unexpected_null_structure_label_without_reset_is_still_warned(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_synthetic_ohlc_daily
            SET latest_structure_label = NULL,
                latest_structure_freshness = NULL,
                trend_classification = 'NEUTRAL',
                latest_reset_event_date = NULL
            WHERE ohlc_date = '2026-05-15' AND group_type = 'subindustry'
            """
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["synthetic_missing_latest_structure_label_count"] == 1
    assert "synthetic_missing_latest_structure_label_count" in result["warn_reasons"]
    assert result["summary"]["validation_status"] == "WARN"


def test_incomplete_reset_state_null_structure_label_is_still_warned(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_synthetic_ohlc_daily
            SET latest_structure_label = NULL,
                latest_structure_freshness = NULL,
                trend_classification = 'NEUTRAL',
                latest_reset_event_date = '2026-05-14',
                ema20 = NULL
            WHERE ohlc_date = '2026-05-15' AND group_type = 'subindustry'
            """
        )
        conn.commit()

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["synthetic_missing_latest_structure_label_count"] == 1
    assert "synthetic_missing_latest_structure_label_count" in result["warn_reasons"]
    assert result["summary"]["validation_status"] == "WARN"


def test_non_null_structure_label_is_not_counted_missing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_ticker_count=2,
        expected_group_count=3,
        expected_synthetic_ohlc_count=2,
    )

    assert result["summary"]["synthetic_missing_latest_structure_label_count"] == 0


def test_weekly_readiness_passes_with_exactly_five_valid_signal_dates(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["weekly_valid_signal_dates_count"] == 5
    assert result["summary"]["weekly_incomplete_window"] == "NO"
    assert result["summary"]["weekly_ready"] == "YES"


def test_weekly_readiness_reports_incomplete_window_if_fewer_than_five_dates_exist(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for signal_date in ("2026-05-13", "2026-05-14", "2026-05-15"):
        _insert_ticker_row(analysis_db, signal_date=signal_date, taxonomy_version="DC_TAXONOMY_FULL_V1", ticker="AAA")
        _insert_group_row(analysis_db, signal_date=signal_date, taxonomy_version="DC_TAXONOMY_FULL_V1", group_type="subindustry", group_name="SubA")
        _insert_synthetic_row(analysis_db, signal_date=signal_date, taxonomy_version="DC_TAXONOMY_FULL_V1", group_type="subindustry", group_name="SubA")

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert result["summary"]["weekly_valid_signal_dates_count"] == 3
    assert result["summary"]["weekly_incomplete_window"] == "YES"
    assert result["summary"]["weekly_ready"] == "NO"
    assert result["summary"]["validation_status"] == "WARN"


def test_expected_counts_produce_warn_when_mismatched_without_strict(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_ticker_count=236,
    )

    assert result["summary"]["validation_status"] == "WARN"


def test_expected_counts_produce_fail_when_mismatched_with_strict(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)

    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_ticker_count=236,
        strict=True,
    )

    assert result["summary"]["validation_status"] == "FAIL"


def test_audit_is_read_only_and_does_not_change_table_row_counts(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_complete_fixture(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_ticker_swing_signal_daily",
                "dc_group_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
                "dc_group_index_daily",
            )
        }

    load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    with sqlite3.connect(analysis_db) as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert after == before
