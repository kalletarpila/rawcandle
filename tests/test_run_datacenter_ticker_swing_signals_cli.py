from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_ticker_persistence import (
    persist_datacenter_ticker_swing_snapshots,
)
from run_datacenter_ticker_swing_signals import main as run_datacenter_ticker_swing_signals_main


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
        encoding="utf-8",
    )
    return path


def _create_price_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa"),
        )
        conn.commit()


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_dow_structure_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NULL,
                event_date TEXT NOT NULL,
                confirmed_as_of_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                dow_label_high TEXT NULL,
                dow_label_low TEXT NULL,
                trend_state TEXT NULL
            )
            """
        )
        conn.commit()


def test_cli_writes_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--as-of-date",
            "2024-01-10",
            "--market",
            "usa",
            "--write-mode",
            "upsert",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2024-01-10"
    assert lines[1] == "SUMMARY market=usa"
    assert lines[2] == "SUMMARY write_mode=upsert"
    assert lines[3] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"
    assert not any(line.startswith("SUMMARY profile_") for line in lines)

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
    assert count == 1


def test_cli_scanner_only_updates_existing_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="base-run",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET close = 120.0,
                return_5d = 0.02,
                return_10d = 0.03,
                return_20d = 0.10,
                return_60d = 0.20,
                ema10 = 119.0,
                ema20 = 115.0,
                ma10 = 118.0,
                highest_close_20d = 120.0,
                volume_vs_avg20 = 1.6,
                ema10_slope_positive = 1,
                ema20_slope_positive = 1,
                latest_structure_label = 'HH',
                price_data_status = 'OK'
            """
        )
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                trend_breadth, weakness_breadth, overheat_risk_level,
                timing_state, timing_reason, data_quality_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
                1, 1, 0.02, 0.03, 0.10, 0.20,
                80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                "BUY_ZONE", "BUY_ZONE:existing", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--as-of-date",
            "2024-01-10",
            "--write-mode",
            "update-existing",
            "--scanner-only",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-01-10"
    assert lines[1] == "SUMMARY end_date=2024-01-10"
    assert lines[2] == "SUMMARY taxonomy_version=ALL"
    assert lines[3] == "SUMMARY write_mode=update-existing"
    assert lines[4] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        breakout_signal = conn.execute(
            """
            SELECT breakout_signal
            FROM dc_ticker_swing_signal_daily
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        ).fetchone()[0]
    assert breakout_signal == 1


def test_cli_profile_summary_lines_are_emitted_only_when_enabled(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--as-of-date",
            "2024-01-10",
            "--market",
            "usa",
            "--write-mode",
            "upsert",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
            "--profile",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any(line.startswith("SUMMARY ticker_swing_snapshot_profile.total_seconds=") for line in lines)
    assert any(line.startswith("SUMMARY ticker_swing_snapshot_profile.rows_built=") for line in lines)
    assert any(line.startswith("SUMMARY ticker_swing_snapshot_profile.avg_rows_per_ticker=") for line in lines)


def test_cli_base_range_skips_non_trading_dates_and_reports_aggregate_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    with sqlite3.connect(price_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
                ("AAA", "2024-01-15", 101, 102, 100, 101, 1000, "usa"),
            ],
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-12",
            "--end-date",
            "2024-01-15",
            "--market",
            "usa",
            "--write-mode",
            "replace-date",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY signal_date=2024-01-12" in lines
    assert "SUMMARY signal_date=2024-01-15" in lines
    assert "SUMMARY signal_date=2024-01-13" not in lines
    assert "SUMMARY signal_date=2024-01-14" not in lines
    assert "SUMMARY requested_start_date=2024-01-12" in lines
    assert "SUMMARY requested_end_date=2024-01-15" in lines
    assert "SUMMARY valid_trading_dates=2" in lines
    assert "SUMMARY skipped_non_trading_dates=2" in lines

    with sqlite3.connect(analysis_db) as conn:
        dates = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT signal_date FROM dc_ticker_swing_signal_daily ORDER BY signal_date"
            ).fetchall()
        ]
    assert dates == ["2024-01-12", "2024-01-15"]


def test_cli_base_range_profile_emits_aggregate_snapshot_profile_lines(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    with sqlite3.connect(price_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
                ("AAA", "2024-01-15", 101, 102, 100, 101, 1000, "usa"),
            ],
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-12",
            "--end-date",
            "2024-01-15",
            "--market",
            "usa",
            "--write-mode",
            "replace-date",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
            "--profile",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY requested_start_date=2024-01-12" in lines
    assert "SUMMARY requested_end_date=2024-01-15" in lines
    assert "SUMMARY valid_trading_dates=2" in lines
    assert "SUMMARY ticker_swing_snapshot_profile.signal_date_count=2" in lines
    assert "SUMMARY ticker_swing_snapshot_profile.ticker_count=1" in lines
    assert "SUMMARY ticker_swing_snapshot_profile.rows_built=2" in lines
    assert any(line.startswith("SUMMARY ticker_swing_snapshot_profile.total_seconds=") for line in lines)


def test_cli_scanner_range_reports_only_existing_base_dates(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for signal_date in ("2024-01-10", "2024-01-12"):
        with sqlite3.connect(analysis_db) as conn:
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily (
                    signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                    close, volume, return_5d, return_10d, return_20d, return_60d,
                    ma10, ema10, ema20, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                    latest_structure_label,
                    breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                    pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                    signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date, "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
                    120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
                    118.0, 119.0, 115.0, 120.0, 900.0, 1.6,
                    "HH",
                    None, None, None, None, None, None, None, "OK",
                    "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO dc_group_swing_signal_daily (
                    signal_date, taxonomy_version, group_type, group_name,
                    member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                    pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                    ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                    trend_breadth, weakness_breadth, overheat_risk_level,
                    timing_state, timing_reason, data_quality_status,
                    signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date, "DC_TAXONOMY_V1", "subindustry", "UPS",
                    1, 1, 0.02, 0.03, 0.10, 0.20,
                    80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                    "BUY_ZONE", "BUY_ZONE:existing", "OK",
                    "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
                ),
            )
            conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--start-date",
            "2024-01-10",
            "--end-date",
            "2024-01-12",
            "--write-mode",
            "replace-scanner-range",
            "--scanner-only",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY requested_start_date=2024-01-10" in lines
    assert "SUMMARY requested_end_date=2024-01-12" in lines
    assert "SUMMARY valid_trading_dates=2" in lines
    assert "SUMMARY skipped_non_trading_dates=1" in lines
    assert "SUMMARY taxonomy_version=ALL" in lines


def test_cli_scanner_range_with_taxonomy_version_updates_only_selected_taxonomy(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for taxonomy_version, breakout_signal in (("DC_TAXONOMY_V1", None), ("OTHER_TAXONOMY", 7)):
        with sqlite3.connect(analysis_db) as conn:
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily (
                    signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                    close, volume, return_5d, return_10d, return_20d, return_60d,
                    ma10, ema10, ema20, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                    latest_structure_label,
                    breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                    pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                    signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2024-01-10", taxonomy_version, "AAA", "Power", "UPS",
                    120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
                    118.0, 119.0, 115.0, 120.0, 900.0, 1.6,
                    "HH",
                    breakout_signal, breakout_signal, breakout_signal, breakout_signal, breakout_signal, "old", "HIGH", "OK",
                    "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO dc_group_swing_signal_daily (
                    signal_date, taxonomy_version, group_type, group_name,
                    member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                    pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                    ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                    trend_breadth, weakness_breadth, overheat_risk_level,
                    timing_state, timing_reason, data_quality_status,
                    signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2024-01-10", taxonomy_version, "subindustry", "UPS",
                    1, 1, 0.02, 0.03, 0.10, 0.20,
                    80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                    "BUY_ZONE", "BUY_ZONE:existing", "OK",
                    "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
                ),
            )
            conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--start-date",
            "2024-01-10",
            "--end-date",
            "2024-01-10",
            "--signal-version",
            "DC_SWING_SIGNAL_V1",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--write-mode",
            "replace-scanner-range",
            "--scanner-only",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY taxonomy_version=DC_TAXONOMY_V1" in lines


def test_cli_scanner_only_handles_early_null_rows_without_typeerror(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, volume, return_5d, return_10d, return_20d, return_60d,
                ma10, ema10, ema20, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                latest_structure_label,
                breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
                None, 1000.0, None, None, None, None,
                None, None, None, None, None, None,
                None,
                None, None, None, None, None, None, None, "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                trend_breadth, weakness_breadth, overheat_risk_level,
                timing_state, timing_reason, data_quality_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
                1, 1, 0.02, 0.03, 0.10, 0.20,
                80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                "BUY_ZONE", "BUY_ZONE:existing", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--start-date",
            "2024-01-10",
            "--end-date",
            "2024-01-10",
            "--write-mode",
            "replace-scanner-range",
            "--scanner-only",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1] == "SUMMARY validation_status=OK"
    assert "SUMMARY valid_trading_dates=1" in lines
    assert "SUMMARY updated_count=1" in lines
    assert "SUMMARY cleared_count=1" in lines
