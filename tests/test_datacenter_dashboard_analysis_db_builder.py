from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.datacenter_dashboard_analysis_db_builder import (
    build_datacenter_dashboard_input_from_analysis_db,
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.ecosystem_dashboard_structured_json import (
    load_ecosystem_dashboard_input_json,
)
from dev_tools.run_datacenter_dashboard_analysis_db_export import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_price_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                primary_layer TEXT,
                primary_subindustry TEXT,
                close REAL,
                return_5d REAL,
                return_20d REAL,
                return_60d REAL,
                ticker_trend_state TEXT,
                latest_structure_label TEXT,
                latest_structure_age_trading_days INTEGER,
                latest_bos_event_type TEXT,
                latest_bos_age_trading_days INTEGER,
                latest_bos_freshness TEXT,
                latest_reset_reason TEXT,
                latest_reset_age_trading_days INTEGER,
                latest_reset_freshness TEXT,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                price_data_status TEXT,
                signal_version TEXT NOT NULL
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
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                pct_above_ma10 REAL,
                pct_above_ema20 REAL,
                ema20_breadth_delta_5d REAL,
                overheat_risk_level TEXT,
                timing_state TEXT,
                signal_version TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_synthetic_ohlc_daily (
                ohlc_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                latest_structure_label TEXT,
                latest_structure_age_trading_days INTEGER,
                latest_bos_event_type TEXT,
                latest_bos_age_trading_days INTEGER,
                latest_reset_reason TEXT,
                latest_reset_age_trading_days INTEGER,
                trend_classification TEXT,
                calc_version TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_index_daily (
                index_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                return_20d REAL,
                return_60d REAL,
                calc_version TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_20d, return_60d, ticker_trend_state,
                latest_structure_label, latest_structure_age_trading_days,
                latest_bos_event_type, latest_bos_age_trading_days, latest_bos_freshness,
                latest_reset_reason, latest_reset_age_trading_days, latest_reset_freshness,
                bullish_candle_signal, bullish_divergence_signal,
                hidden_bullish_divergence_signal, price_data_status, signal_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "NVDA",
                    "Infrastructure",
                    "AI Accelerators",
                    100.5,
                    1.2,
                    4.5,
                    12.0,
                    "UP",
                    "HH",
                    3,
                    "BOS_UP",
                    2,
                    "FRESH",
                    "EMA20_LOST",
                    5,
                    "STALE",
                    1,
                    1,
                    0,
                    "OK",
                    "DC_SWING_SIGNAL_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "",
                    "Infrastructure",
                    "AI Accelerators",
                    10.0,
                    0.1,
                    0.2,
                    0.3,
                    "UP",
                    "HH",
                    1,
                    "BOS_UP",
                    1,
                    "FRESH",
                    None,
                    None,
                    None,
                    0,
                    0,
                    0,
                    "OK",
                    "DC_SWING_SIGNAL_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "2026-05-22",
                    "Infrastructure",
                    "AI Accelerators",
                    10.0,
                    0.1,
                    0.2,
                    0.3,
                    "UP",
                    "HH",
                    1,
                    "BOS_UP",
                    1,
                    "FRESH",
                    None,
                    None,
                    None,
                    0,
                    0,
                    0,
                    "OK",
                    "DC_SWING_SIGNAL_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "INFRASTRUCTURE",
                    "Infrastructure",
                    "AI Accelerators",
                    10.0,
                    0.1,
                    0.2,
                    0.3,
                    "UP",
                    "HH",
                    1,
                    "BOS_UP",
                    1,
                    "FRESH",
                    None,
                    None,
                    None,
                    0,
                    0,
                    0,
                    "OK",
                    "DC_SWING_SIGNAL_V1",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name, member_count,
                return_5d, return_10d, return_20d, return_60d, pct_above_ma10,
                pct_above_ema20, ema20_breadth_delta_5d, overheat_risk_level,
                timing_state, signal_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "ecosystem",
                    "DC_ECOSYSTEM_TOTAL",
                    1,
                    0.10,
                    0.15,
                    0.20,
                    0.40,
                    55.0,
                    60.0,
                    3.0,
                    "LOW",
                    "BUY_ZONE",
                    "DC_SWING_SIGNAL_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "layer",
                    "Infrastructure",
                    1,
                    0.11,
                    0.16,
                    0.21,
                    0.41,
                    56.0,
                    61.0,
                    4.0,
                    "LOW",
                    "BUY_ZONE",
                    "DC_SWING_SIGNAL_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "subindustry",
                    "AI Accelerators",
                    1,
                    0.12,
                    0.17,
                    0.22,
                    0.42,
                    57.0,
                    62.0,
                    5.0,
                    "MEDIUM",
                    "BREAKOUT_CANDIDATE",
                    "DC_SWING_SIGNAL_V1",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name,
                latest_structure_label, latest_structure_age_trading_days,
                latest_bos_event_type, latest_bos_age_trading_days,
                latest_reset_reason, latest_reset_age_trading_days,
                trend_classification, calc_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "ecosystem",
                    "DC_ECOSYSTEM_TOTAL",
                    "HL",
                    4,
                    "BOS_UP",
                    2,
                    None,
                    None,
                    "UP",
                    "DC_SWING_OHLC_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "layer",
                    "Infrastructure",
                    "HH",
                    3,
                    "BOS_UP",
                    1,
                    None,
                    None,
                    "UP",
                    "DC_SWING_OHLC_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "subindustry",
                    "AI Accelerators",
                    "HH",
                    2,
                    "BOS_UP",
                    1,
                    "PULLBACK_RESET",
                    3,
                    "UP",
                    "DC_SWING_OHLC_V1",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO dc_group_index_daily (
                index_date, taxonomy_version, group_type, group_name,
                return_20d, return_60d, calc_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "ecosystem",
                    "DC_ECOSYSTEM_TOTAL",
                    0.20,
                    0.40,
                    "DC_INDEX_CALC_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "layer",
                    "Infrastructure",
                    0.21,
                    0.41,
                    "DC_INDEX_CALC_V1",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "subindustry",
                    "AI Accelerators",
                    0.22,
                    0.42,
                    "DC_INDEX_CALC_V1",
                ),
            ],
        )


def _row_count(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _create_enrichment_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _insert_enrichment_fixture_rows(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_20d, return_60d, action, current_status,
                trend_state, latest_structure_label, latest_bos_event_type, latest_reset_reason,
                is_watchlist, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "Infrastructure",
                "AI Accelerators",
                100.5,
                1.2,
                4.5,
                12.0,
                "WATCH",
                "BUY_ZONE",
                "UP",
                "HH",
                "BOS_UP",
                "EMA20_LOST",
                1,
                "OK",
                "ENRICH_V1",
                "RUN_ENRICH",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name, layer, subindustry,
                current_status, return_5d, return_20d, return_60d,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "ECOSYSTEM",
                "ECOSYSTEM|DC_ECOSYSTEM_TOTAL",
                "DC_ECOSYSTEM_TOTAL",
                None,
                None,
                "NEUTRAL",
                0.09,
                0.19,
                0.39,
                "OK",
                "ENRICH_V1",
                "RUN_ENRICH",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name, layer, subindustry,
                current_status, return_5d, return_20d, return_60d,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "LAYER",
                "LAYER:Infrastructure",
                "Infrastructure",
                "Infrastructure",
                None,
                "BUY_ZONE",
                0.10,
                0.20,
                0.40,
                "OK",
                "ENRICH_V1",
                "RUN_ENRICH",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date, taxonomy_version, action, count, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "WATCH",
                1,
                "ENRICH_V1",
                "RUN_ENRICH",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_decision_trace_daily (
                signal_date, taxonomy_version, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                1,
                "WATCH",
                "ENRICHMENT_FIELD_PRESENT",
                "daily_status",
                "BUY_ZONE",
                "daily",
                "daily_status",
                "ENRICH_V1",
                "RUN_ENRICH",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_enrichment_run_daily (
                run_id, signal_date, taxonomy_version, status, readiness,
                ticker_rows, group_rows, action_summary_rows, decision_trace_rows,
                warnings, calc_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RUN_ENRICH",
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "OK",
                "READY",
                1,
                1,
                1,
                1,
                None,
                "ENRICH_V1",
                "2026-05-26T10:00:00Z",
            ),
        )


def test_builder_reads_valid_ticker_rows_and_excludes_pseudo_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)

    result = build_datacenter_dashboard_input_from_analysis_db(
        analysis_db=str(analysis_db),
        price_db=str(price_db),
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
        source_mode="raw-v0",
    )

    tickers = result.dashboard_input.tickers
    assert [row.ticker for row in tickers] == ["NVDA"]
    assert tickers[0].last_close == 100.5
    assert tickers[0].return_5d == 1.2
    assert tickers[0].return_20d == 4.5
    assert tickers[0].return_60d == 12.0
    assert tickers[0].layer_name == "Infrastructure"
    assert tickers[0].subindustry_name == "AI Accelerators"
    assert tickers[0].trend_state == "UP"
    assert tickers[0].latest_structure_label == "HH"
    assert tickers[0].latest_bos_event_type == "BOS_UP"
    assert tickers[0].latest_reset_reason == "EMA20_LOST"
    assert tickers[0].bullish_candle_signal == 1
    assert tickers[0].bullish_divergence_signal == 1
    assert tickers[0].hidden_bullish_divergence_signal == 0


def test_builder_produces_market_map_and_structured_source_report(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)

    result = build_datacenter_dashboard_input_from_analysis_db(
        analysis_db=str(analysis_db),
        price_db=str(price_db),
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
        source_mode="raw-v0",
    )

    dashboard_input = result.dashboard_input
    assert dashboard_input.readiness == "PARTIAL"
    assert len(dashboard_input.source_reports) == 1
    assert dashboard_input.source_reports[0].source_report_type == "analysis_db_structured"
    assert dashboard_input.source_reports[0].status == "PARTIAL"
    assert len(dashboard_input.market_map) == 3

    ecosystem_row = dashboard_input.market_map[0]
    layer_row = dashboard_input.market_map[1]
    subindustry_row = dashboard_input.market_map[2]

    assert ecosystem_row.market_level == "ECOSYSTEM"
    assert ecosystem_row.name == "DC_ECOSYSTEM_TOTAL"
    assert ecosystem_row.taxonomy_path == "DC_ECOSYSTEM_TOTAL"
    assert ecosystem_row.avg_return_5d == 0.10
    assert ecosystem_row.avg_return_20d == 0.20
    assert ecosystem_row.avg_return_60d == 0.40
    assert ecosystem_row.dominant_action_bucket == "BUY_ZONE"

    assert layer_row.layer_name == "Infrastructure"
    assert layer_row.layer_order == 1
    assert layer_row.dominant_action_bucket == "BUY_ZONE"
    assert subindustry_row.layer_name == "Infrastructure"
    assert subindustry_row.subindustry_name == "AI Accelerators"
    assert subindustry_row.subindustry_order == 1
    assert subindustry_row.dominant_action_bucket == "BREAKOUT_CANDIDATE"


def test_cli_writes_json_and_prints_partial_warnings_read_only(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    output_json = tmp_path / "dashboard_input.json"
    dashboard_db = tmp_path / "should_not_exist.db"
    html_output = tmp_path / "should_not_exist.html"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)

    before_counts = {
        table_name: _row_count(analysis_db, table_name)
        for table_name in (
            "dc_ticker_swing_signal_daily",
            "dc_group_swing_signal_daily",
            "dc_group_synthetic_ohlc_daily",
            "dc_group_index_daily",
        )
    }

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--source-mode",
            "raw-v0",
            "--output-json",
            str(output_json),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SUMMARY datacenter_dashboard_analysis_db_export.status=OK" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.readiness=PARTIAL" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.source_reports=1" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=0" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.market_map=3" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.watchlist=0" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.tickers=1" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.decision_trace=0" in output
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=WATCHLIST_SOURCE_NOT_AVAILABLE"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=ACTION_SUMMARY_SOURCE_NOT_AVAILABLE"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=DECISION_TRACE_SOURCE_NOT_AVAILABLE"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=WINDOW_STATUS_ENRICHMENT_NOT_DIRECT_FROM_ANALYSIS_DB"
        in output
    )
    assert output_json.exists()
    assert not dashboard_db.exists()
    assert not html_output.exists()
    after_counts = {
        table_name: _row_count(analysis_db, table_name)
        for table_name in before_counts
    }
    assert after_counts == before_counts


def test_exported_json_loads_and_round_trips_to_dashboard_db(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    output_json = tmp_path / "dashboard_input.json"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--source-mode",
            "raw-v0",
            "--output-json",
            str(output_json),
        ]
    )

    assert exit_code == 0
    dashboard_input = load_ecosystem_dashboard_input_json(str(output_json))
    assert dashboard_input.ecosystem_code == "DATACENTER"
    assert dashboard_input.report_date == "2026-05-22"
    assert dashboard_input.market_map[0].market_level == "ECOSYSTEM"
    assert dashboard_input.market_map[0].name == "DC_ECOSYSTEM_TOTAL"
    assert dashboard_input.market_map[0].taxonomy_path == "DC_ECOSYSTEM_TOTAL"
    run_id = persist_ecosystem_dashboard_input(
        dashboard_db=str(dashboard_db),
        dashboard_input=dashboard_input,
        mode="replace-date",
        run_id="RUN_ANALYSIS_DB_V0",
    )
    snapshot = load_dashboard_snapshot(
        dashboard_db=str(dashboard_db),
        ecosystem_code="DATACENTER",
        run_id=run_id,
    )
    assert snapshot.run.run_id == "RUN_ANALYSIS_DB_V0"
    assert len(snapshot.source_reports) == 1
    assert len(snapshot.market_map) == 3
    assert len(snapshot.tickers) == 1
    assert len(snapshot.watchlist) == 0
    assert len(snapshot.decision_trace) == 0


def test_missing_analysis_db_fails_clearly(tmp_path, capsys):
    price_db = tmp_path / "price.db"
    _create_price_db(price_db)

    exit_code = main(
        [
            "--analysis-db",
            str(tmp_path / "missing-analysis.db"),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--source-mode",
            "raw-v0",
            "--output-json",
            str(tmp_path / "dashboard_input.json"),
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "SUMMARY datacenter_dashboard_analysis_db_export.status=FAILED" in output
    assert "database not found:" in output


def test_enrichment_mode_reads_all_five_tables_and_emits_ready(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    _create_enrichment_analysis_db(analysis_db)
    _create_price_db(price_db)
    _insert_enrichment_fixture_rows(analysis_db)

    result = build_datacenter_dashboard_input_from_analysis_db(
        analysis_db=str(analysis_db),
        price_db=str(price_db),
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
    )

    dashboard_input = result.dashboard_input
    assert dashboard_input.readiness == "READY"
    assert len(dashboard_input.source_reports) == 1
    assert dashboard_input.source_reports[0].source_report_type == "analysis_db_enrichment"
    assert len(dashboard_input.tickers) == 1
    assert len(dashboard_input.market_map) == 2
    assert len(dashboard_input.action_summary) == 1
    assert len(dashboard_input.decision_trace) == 1
    assert len(dashboard_input.watchlist) == 1
    assert dashboard_input.market_map[0].market_level == "ECOSYSTEM"
    assert dashboard_input.market_map[0].name == "DC_ECOSYSTEM_TOTAL"
    assert dashboard_input.market_map[0].taxonomy_path == "DC_ECOSYSTEM_TOTAL"
    assert dashboard_input.decision_trace[0].rule_group == "daily"
    assert dashboard_input.decision_trace[0].input_value == "BUY_ZONE"


def test_enrichment_mode_ticker_action_round_trips_through_persistence(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    _create_enrichment_analysis_db(analysis_db)
    _create_price_db(price_db)
    _insert_enrichment_fixture_rows(analysis_db)

    result = build_datacenter_dashboard_input_from_analysis_db(
        analysis_db=str(analysis_db),
        price_db=str(price_db),
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
    )

    dashboard_input = result.dashboard_input
    assert len(dashboard_input.tickers) == 1
    assert dashboard_input.tickers[0].action_bucket is None
    assert dashboard_input.tickers[0].action_label == "WATCH"

    run_id = persist_ecosystem_dashboard_input(
        dashboard_db=str(dashboard_db),
        dashboard_input=dashboard_input,
        mode="replace-date",
        run_id="RUN_ENRICHMENT_ROUNDTRIP",
    )
    snapshot = load_dashboard_snapshot(
        dashboard_db=str(dashboard_db),
        ecosystem_code="DATACENTER",
        run_id=run_id,
    )

    assert snapshot.tickers[0]["ticker"] == "NVDA"
    assert snapshot.tickers[0]["action"] == "WATCH"


def test_enrichment_mode_partial_when_sections_are_empty(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    output_json = tmp_path / "dashboard_input.json"
    _create_enrichment_analysis_db(analysis_db)
    _create_price_db(price_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, data_quality_status, calc_version, run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "OK",
                "ENRICH_V1",
                "RUN_ENRICH",
                "2026-05-26T10:00:00Z",
                0,
            ),
        )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--output-json",
            str(output_json),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SUMMARY datacenter_dashboard_analysis_db_export.source_mode=enrichment" in output
    assert "SUMMARY datacenter_dashboard_analysis_db_export.readiness=PARTIAL" in output
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=ENRICHMENT_SECTIONS_EMPTY:"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=ENRICHMENT_READINESS_PARTIAL"
        in output
    )


def test_enrichment_mode_missing_tables_fails_clearly(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    output_json = tmp_path / "dashboard_input.json"
    with sqlite3.connect(analysis_db):
        pass
    _create_price_db(price_db)

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--output-json",
            str(output_json),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=ENRICHMENT_TABLES_MISSING"
        in output
    )
    assert "SUMMARY datacenter_dashboard_analysis_db_export.status=FAILED" in output


def test_cli_default_source_mode_is_enrichment(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    output_json = tmp_path / "dashboard_input.json"
    _create_enrichment_analysis_db(analysis_db)
    _create_price_db(price_db)
    _insert_enrichment_fixture_rows(analysis_db)

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--output-json",
            str(output_json),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SUMMARY datacenter_dashboard_analysis_db_export.source_mode=enrichment" in output


def test_cli_explicit_raw_v0_mode_works(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "price.db"
    output_json = tmp_path / "dashboard_input.json"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--source-mode",
            "raw-v0",
            "--output-json",
            str(output_json),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SUMMARY datacenter_dashboard_analysis_db_export.source_mode=raw-v0" in output
    assert (
        "SUMMARY datacenter_dashboard_analysis_db_export.warning=RAW_V0_SOURCE_MODE_USED"
        in output
    )
