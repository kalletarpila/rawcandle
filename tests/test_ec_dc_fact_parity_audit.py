import csv
import sqlite3
from pathlib import Path

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_datacenter_watchlist_loader import load_datacenter_watchlist_to_ec_sidecar
from rawcandle.ec_dc_fact_parity_audit import (
    PARITY_POLICY_RSO_REVALIDATION_METADATA,
    PARITY_POLICY_STRICT,
    audit_dc_ec_fact_parity,
    classify_parity_field,
)
from rawcandle.ec_group_index_daily_loader import load_ec_group_index_daily_from_dc
from rawcandle.ec_group_signal_daily_loader import load_ec_group_signal_daily_from_dc
from rawcandle.ec_group_synthetic_ohlc_daily_loader import load_ec_group_synthetic_ohlc_daily_from_dc
from rawcandle.ec_pipeline_watermark_loader import load_ec_pipeline_watermark_from_dc
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration
from rawcandle.ec_ticker_signal_daily_loader import load_ec_ticker_signal_daily_from_dc


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_taxonomy_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerow(["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""])


def _write_watchlist_txt(path: Path) -> None:
    path.write_text("NVDA\nCRGY\n", encoding="utf-8")


def _write_taxonomy_version_csv(path: Path, version: str, tickers: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        for ticker in tickers:
            writer.writerow([version, ticker, "Compute silicon", "GPUs", "CORE", 1, 1.0, ""])

def _insert_source_rows_for_date(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    omit_group_index: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily VALUES (
            ?,'DC_TAXONOMY_FULL_V1','NVDA','Compute silicon','GPUs',
            124.5,1500000,0.02,0.05,0.11,0.22,120.0,121.0,122.0,0.0375,0.0289,0.0205,
            1,1,1,1,1,5,5,126.0,1400000,1.07,'HH',?,1,0,0,1,0,NULL,'OK',
            'DC_SWING_SIGNAL_V1',?,'2026-06-07T06:00:00Z','LOW',1,'FRESH','UP','epoch-1',
            'BOS_UP','2026-06-03','2026-06-03',2,'FRESH',NULL,NULL,NULL,NULL,NULL,0,0,0,0,1,0
        )
        """,
        (signal_date, signal_date, f"TICKER_RUN_{signal_date.replace('-', '')}"),
    )
    for group_type, group_name in (
        ("ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ("layer", "Compute silicon"),
        ("subindustry", "GPUs"),
    ):
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily VALUES (
                ?,'DC_TAXONOMY_FULL_V1',?,?,?,?,0.03,0.07,0.12,0.21,1.0,1.0,1.0,0.1,0.1,1.0,0.0,
                'LOW','READY','All clear','OK','DC_SWING_SIGNAL_V1',?,'2026-06-07T06:05:00Z'
            )
            """,
            (signal_date, group_type, group_name, 1, 1, f"GROUP_SIGNAL_RUN_{signal_date.replace('-', '')}"),
        )
    for group_type, group_name in (
        ("layer", "Compute silicon"),
        ("subindustry", "GPUs"),
    ):
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily VALUES (
                ?,'DC_TAXONOMY_FULL_V1',?,?,?,?,120.0,126.0,119.0,124.0,1000000.0,121.0,122.0,0.0164,0.02,5,
                '2026-06-01',126.0,'2026-05-20',110.0,'HH','UP',20,1.0,1.02,0.98,1.01,0.01,0.02,0.01,0.02,-0.02,1,
                'OK','DC_SWING_OHLC_V1',?,'2026-06-07T06:10:00Z',1,'FRESH','BOS_UP','2026-06-03',
                '2026-06-03',2,'FRESH',NULL,NULL,NULL,NULL,NULL
            )
            """,
            (signal_date, group_type, group_name, 1, 1, f"SYNTH_RUN_{signal_date.replace('-', '')}"),
        )
    if not omit_group_index:
        for group_type, group_name in (
            ("ecosystem", "DC_ECOSYSTEM_TOTAL"),
            ("layer", "Compute silicon"),
            ("subindustry", "GPUs"),
        ):
            conn.execute(
                """
                INSERT INTO dc_group_index_daily VALUES (
                    ?,'DC_TAXONOMY_FULL_V1',?,?,?,?,1,1,0.01,0.01,1.0,100.0,0.05,0.1,0.2,1.0,1.0,0.02,0.03,0.04,0.05,
                    'OK','DC_INDEX_CALC_V1',?,'2026-06-07T06:15:00Z'
                )
                """,
                (signal_date, group_type, group_name, 1, 1, f"GROUP_INDEX_RUN_{signal_date.replace('-', '')}"),
            )


def _create_source_db(
    path: Path,
    *,
    include_historical_date: bool = False,
    omit_historical_group_index: bool = False,
    latest_mismatch_table: str | None = None,
) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                primary_layer TEXT NOT NULL,
                primary_subindustry TEXT NOT NULL,
                close REAL NULL,
                volume REAL NULL,
                return_5d REAL NULL,
                return_10d REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                ma10 REAL NULL,
                ema10 REAL NULL,
                ema20 REAL NULL,
                distance_to_ma10_pct REAL NULL,
                distance_to_ema10_pct REAL NULL,
                distance_to_ema20_pct REAL NULL,
                above_ma10 INTEGER NULL,
                above_ema10 INTEGER NULL,
                above_ema20 INTEGER NULL,
                ema10_slope_positive INTEGER NULL,
                ema20_slope_positive INTEGER NULL,
                ema10_slope_lookback INTEGER NULL,
                ema20_slope_lookback INTEGER NULL,
                highest_close_20d REAL NULL,
                volume_avg_20d REAL NULL,
                volume_vs_avg20 REAL NULL,
                latest_structure_label TEXT NULL,
                latest_structure_confirmed_as_of_date TEXT NULL,
                breakout_signal INTEGER NULL,
                fast_ema10_pullback_signal INTEGER NULL,
                conservative_ema20_pullback_signal INTEGER NULL,
                pullback_signal INTEGER NULL,
                exit_risk_signal INTEGER NULL,
                exit_reason TEXT NULL,
                price_data_status TEXT NULL,
                signal_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                exit_risk_severity TEXT NULL,
                latest_structure_age_trading_days INTEGER NULL,
                latest_structure_freshness TEXT NULL,
                ticker_trend_state TEXT NULL,
                structure_epoch_id TEXT NULL,
                latest_bos_event_type TEXT NULL,
                latest_bos_event_date TEXT NULL,
                latest_bos_confirmed_as_of_date TEXT NULL,
                latest_bos_age_trading_days INTEGER NULL,
                latest_bos_freshness TEXT NULL,
                latest_reset_event_date TEXT NULL,
                latest_reset_confirmed_as_of_date TEXT NULL,
                latest_reset_reason TEXT NULL,
                latest_reset_age_trading_days INTEGER NULL,
                latest_reset_freshness TEXT NULL,
                bullish_divergence_signal INTEGER NULL,
                bearish_divergence_signal INTEGER NULL,
                hidden_bullish_divergence_signal INTEGER NULL,
                hidden_bearish_divergence_signal INTEGER NULL,
                bullish_candle_signal INTEGER NULL,
                bearish_candle_signal INTEGER NULL,
                PRIMARY KEY (signal_date, taxonomy_version, ticker, signal_version)
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
                member_count INTEGER NULL,
                eligible_count INTEGER NULL,
                return_5d REAL NULL,
                return_10d REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                pct_above_ma10 REAL NULL,
                pct_above_ema20 REAL NULL,
                pct_above_rising_ema20 REAL NULL,
                ma10_breadth_delta_5d REAL NULL,
                ema20_breadth_delta_5d REAL NULL,
                trend_breadth REAL NULL,
                weakness_breadth REAL NULL,
                overheat_risk_level TEXT NULL,
                timing_state TEXT NULL,
                timing_reason TEXT NULL,
                data_quality_status TEXT NULL,
                signal_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, group_type, group_name, signal_version)
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
                member_count INTEGER NULL,
                eligible_count INTEGER NULL,
                synthetic_open REAL NULL,
                synthetic_high REAL NULL,
                synthetic_low REAL NULL,
                synthetic_close REAL NULL,
                synthetic_volume REAL NULL,
                ma20 REAL NULL,
                ema20 REAL NULL,
                distance_to_ema20_pct REAL NULL,
                volatility_20d REAL NULL,
                pivot_radius INTEGER NULL,
                latest_pivot_high_date TEXT NULL,
                latest_pivot_high_value REAL NULL,
                latest_pivot_low_date TEXT NULL,
                latest_pivot_low_value REAL NULL,
                latest_structure_label TEXT NULL,
                trend_classification TEXT NULL,
                relative_base_window INTEGER NULL,
                relative_open_20 REAL NULL,
                relative_high_20 REAL NULL,
                relative_low_20 REAL NULL,
                relative_close_20 REAL NULL,
                relative_upper_wick_20 REAL NULL,
                relative_lower_wick_20 REAL NULL,
                relative_close_extension_20 REAL NULL,
                relative_high_extension_20 REAL NULL,
                relative_low_extension_20 REAL NULL,
                relative_eligible_count INTEGER NULL,
                data_quality_status TEXT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                latest_structure_age_trading_days INTEGER NULL,
                latest_structure_freshness TEXT NULL,
                latest_bos_event_type TEXT NULL,
                latest_bos_event_date TEXT NULL,
                latest_bos_confirmed_as_of_date TEXT NULL,
                latest_bos_age_trading_days INTEGER NULL,
                latest_bos_freshness TEXT NULL,
                latest_reset_event_date TEXT NULL,
                latest_reset_confirmed_as_of_date TEXT NULL,
                latest_reset_reason TEXT NULL,
                latest_reset_age_trading_days INTEGER NULL,
                latest_reset_freshness TEXT NULL,
                PRIMARY KEY (ohlc_date, taxonomy_version, group_type, group_name, calc_version)
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
                member_count INTEGER NULL,
                eligible_count INTEGER NULL,
                ma50_eligible_count INTEGER NULL,
                ma200_eligible_count INTEGER NULL,
                daily_return_equal REAL NULL,
                median_return REAL NULL,
                pct_positive REAL NULL,
                index_level_equal REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                return_120d REAL NULL,
                pct_above_ma50 REAL NULL,
                pct_above_ma200 REAL NULL,
                volatility_20d REAL NULL,
                volatility_60d REAL NULL,
                relative_strength_spy_60d REAL NULL,
                relative_strength_qqq_60d REAL NULL,
                data_quality_status TEXT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (index_date, taxonomy_version, group_type, group_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_pipeline_watermark (
                component_name TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                market TEXT NULL,
                signal_version TEXT NULL,
                calc_version TEXT NULL,
                start_date TEXT NULL,
                end_date TEXT NULL,
                row_count INTEGER NULL,
                status TEXT NOT NULL,
                last_successful_run_id TEXT NULL,
                last_successful_at_utc TEXT NULL,
                notes TEXT NULL,
                PRIMARY KEY (component_name, taxonomy_version, market, signal_version, calc_version)
            )
            """
        )

        if include_historical_date:
            _insert_source_rows_for_date(
                conn,
                signal_date="2026-05-29",
                omit_group_index=omit_historical_group_index,
            )
        _insert_source_rows_for_date(conn, signal_date="2026-06-05")

        if latest_mismatch_table == "dc_ticker_swing_signal_daily":
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily VALUES (
                    '2026-06-06','DC_TAXONOMY_FULL_V1','NVDA','Compute silicon','GPUs',
                    124.5,1500000,0.02,0.05,0.11,0.22,120.0,121.0,122.0,0.0375,0.0289,0.0205,
                    1,1,1,1,1,5,5,126.0,1400000,1.07,'HH','2026-06-06',1,0,0,1,0,NULL,'OK',
                    'DC_SWING_SIGNAL_V1','TICKER_RUN_20260606','2026-06-07T06:00:00Z','LOW',1,'FRESH','UP','epoch-1',
                    'BOS_UP','2026-06-03','2026-06-03',2,'FRESH',NULL,NULL,NULL,NULL,NULL,0,0,0,0,1,0
                )
                """
            )
        conn.execute(
            """
            INSERT INTO dc_pipeline_watermark VALUES (
                'TICKER_SWING_BASE','DC_TAXONOMY_FULL_V1','usa','DC_SWING_SIGNAL_V1',NULL,'2020-01-01','2026-06-05',1,'OK',NULL,NULL,NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO dc_pipeline_watermark VALUES (
                'WEEKLY_REPORT','DC_TAXONOMY_FULL_V1','', 'DC_SWING_SIGNAL_V1','DC_SWING_OHLC_V1','2020-01-01','2026-06-05',1,'OK',NULL,NULL,NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _build_target(
    tmp_path,
    *,
    signal_dates: tuple[str, ...] = ("2026-06-05",),
    include_historical_date: bool = False,
    omit_historical_group_index: bool = False,
    latest_mismatch_table: str | None = None,
) -> tuple[Path, Path]:
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    watchlist_txt = tmp_path / "watchlist.txt"

    _create_source_db(
        source_db,
        include_historical_date=include_historical_date,
        omit_historical_group_index=omit_historical_group_index,
        latest_mismatch_table=latest_mismatch_table,
    )
    apply_ec_sidecar_migration(str(target_db))
    _write_taxonomy_csv(taxonomy_csv)
    _write_watchlist_txt(watchlist_txt)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(target_db),
        taxonomy_csv_path=str(taxonomy_csv),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(target_db),
        watchlist_path=str(watchlist_txt),
    )
    for signal_date in signal_dates:
        load_ec_ticker_signal_daily_from_dc(str(source_db), str(target_db), signal_date=signal_date)
        load_ec_group_signal_daily_from_dc(str(source_db), str(target_db), signal_date=signal_date)
        load_ec_group_synthetic_ohlc_daily_from_dc(str(source_db), str(target_db), signal_date=signal_date)
        load_ec_group_index_daily_from_dc(str(source_db), str(target_db), signal_date=signal_date)
    load_ec_pipeline_watermark_from_dc(str(source_db), str(target_db))
    return source_db, target_db


def _build_v2_target_with_same_date_v1_source_rows(tmp_path) -> tuple[Path, Path]:
    source_db = tmp_path / "source_multi.db"
    target_db = tmp_path / "target_multi.db"
    taxonomy_v1_csv = tmp_path / "taxonomy_v1_multi.csv"
    taxonomy_v2_csv = tmp_path / "taxonomy_v2_multi.csv"
    watchlist_txt = tmp_path / "watchlist_multi.txt"

    _create_source_db(source_db)
    with _connect(str(source_db)) as conn:
        for table, date_column in (
            ("dc_ticker_swing_signal_daily", "signal_date"),
            ("dc_group_swing_signal_daily", "signal_date"),
            ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
            ("dc_group_index_daily", "index_date"),
        ):
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            select_exprs = [
                "'DC_TAXONOMY_FULL_V2'" if column == "taxonomy_version" else column
                for column in columns
            ]
            conn.execute(
                f"""
                INSERT INTO {table} ({', '.join(columns)})
                SELECT {', '.join(select_exprs)}
                FROM {table}
                WHERE {date_column} = '2026-06-05'
                  AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
                """
            )
        ticker_columns = [row[1] for row in conn.execute("PRAGMA table_info(dc_ticker_swing_signal_daily)")]
        ticker_select_exprs = [
            "'ABB'" if column == "ticker" else column
            for column in ticker_columns
        ]
        conn.execute(
            f"""
            INSERT INTO dc_ticker_swing_signal_daily ({', '.join(ticker_columns)})
            SELECT {', '.join(ticker_select_exprs)}
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date = '2026-06-05'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
              AND ticker = 'NVDA'
            """
        )
        conn.commit()

    apply_ec_sidecar_migration(str(target_db))
    _write_taxonomy_version_csv(taxonomy_v1_csv, "DC_TAXONOMY_FULL_V1", ("NVDA", "ABB"))
    _write_taxonomy_version_csv(taxonomy_v2_csv, "DC_TAXONOMY_FULL_V2", ("NVDA",))
    _write_watchlist_txt(watchlist_txt)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(target_db),
        taxonomy_csv_path=str(taxonomy_v1_csv),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(target_db),
        taxonomy_csv_path=str(taxonomy_v2_csv),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
    )
    load_datacenter_watchlist_to_ec_sidecar(str(target_db), str(watchlist_txt))
    load_ec_ticker_signal_daily_from_dc(
        str(source_db),
        str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2026-06-05",
    )
    load_ec_group_signal_daily_from_dc(
        str(source_db),
        str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2026-06-05",
    )
    load_ec_group_synthetic_ohlc_daily_from_dc(
        str(source_db),
        str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2026-06-05",
    )
    load_ec_group_index_daily_from_dc(
        str(source_db),
        str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2026-06-05",
    )
    return source_db, target_db


def test_parity_audit_succeeds_for_small_fixture_build(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["total_mismatch_count"] == 0
    assert summary["ticker_parity"]["status"] == "OK_WITH_WARNINGS"
    assert summary["group_signal_parity"]["status"] == "OK_WITH_WARNINGS"
    assert summary["synthetic_ohlc_parity"]["status"] == "OK_WITH_WARNINGS"
    assert summary["group_index_parity"]["status"] == "OK_WITH_WARNINGS"
    assert summary["pipeline_watermark_parity"]["status"] == "OK_WITH_WARNINGS"
    assert summary["pipeline_watermark_parity"]["unknown_components"] == ["WEEKLY_REPORT"]
    assert not any(
        "member_count" in warning or "eligible_count" in warning
        for warning in summary["group_index_parity"]["warnings"]
    )


def test_v2_parity_scopes_dc_sources_by_requested_taxonomy(tmp_path) -> None:
    source_db, target_db = _build_v2_target_with_same_date_v1_source_rows(tmp_path)

    summary = audit_dc_ec_fact_parity(
        str(source_db),
        str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2026-06-05",
        include_pipeline_watermark=False,
    )

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["requested_taxonomy_version"] == "DC_TAXONOMY_FULL_V2"
    assert summary["taxonomy_version_id"] == 2
    assert summary["total_mismatch_count"] == 0
    assert summary["ticker_parity"]["source_row_count"] == 1
    assert summary["ticker_parity"]["target_row_count"] == 1
    assert summary["ticker_parity"]["missing_in_target"] == []
    assert summary["ticker_parity"]["extra_in_target"] == []
    assert summary["group_signal_parity"]["source_row_count"] == 3
    assert summary["synthetic_ohlc_parity"]["source_row_count"] == 2
    assert summary["group_index_parity"]["source_row_count"] == 3


def test_parity_audit_numeric_tolerance_allows_small_difference(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute("UPDATE ec_ticker_signal_daily SET close = close + 0.0000000005 WHERE ticker = 'NVDA'")
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["total_mismatch_count"] == 0


def test_parity_audit_text_mismatch_fails(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute("UPDATE ec_ticker_signal_daily SET price_data_status = 'BAD' WHERE ticker = 'NVDA'")
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "FAILED"
    assert summary["ticker_parity"]["status"] == "FAILED"
    assert summary["ticker_parity"]["field_mismatch_count"] >= 1
    assert summary["semantic_field_mismatch_count"] >= 1


def test_parity_field_policy_classifies_source_run_id_for_rso_metadata_policy() -> None:
    assert (
        classify_parity_field(
            section_name="group_signal",
            field_name="source_run_id",
            comparison_kind="REQUIRED_LINEAGE",
            parity_policy=PARITY_POLICY_STRICT,
        )
        == "REQUIRED_LINEAGE"
    )
    assert (
        classify_parity_field(
            section_name="group_signal",
            field_name="source_run_id",
            comparison_kind="REQUIRED_LINEAGE",
            parity_policy=PARITY_POLICY_RSO_REVALIDATION_METADATA,
        )
        == "OPERATIONAL_METADATA"
    )
    assert (
        classify_parity_field(
            section_name="synthetic_ohlc",
            field_name="source_run_id",
            comparison_kind="REQUIRED_LINEAGE",
            parity_policy=PARITY_POLICY_RSO_REVALIDATION_METADATA,
        )
        == "OPERATIONAL_METADATA"
    )
    assert (
        classify_parity_field(
            section_name="ticker",
            field_name="source_run_id",
            comparison_kind="REQUIRED_LINEAGE",
            parity_policy=PARITY_POLICY_RSO_REVALIDATION_METADATA,
        )
        == "REQUIRED_LINEAGE"
    )


def test_parity_field_policy_rejects_unknown_comparison_class() -> None:
    try:
        classify_parity_field(
            section_name="group_signal",
            field_name="new_field",
            comparison_kind="UNKNOWN_CLASS",
            parity_policy=PARITY_POLICY_RSO_REVALIDATION_METADATA,
        )
    except ValueError as exc:
        assert "unknown parity field class" in str(exc)
    else:
        raise AssertionError("unknown parity field class must fail")


def test_rso_metadata_policy_reports_source_run_id_drift_without_blocking(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(source_db)) as conn:
        conn.execute("UPDATE dc_group_swing_signal_daily SET run_id = run_id || '_NEW'")
        conn.execute("UPDATE dc_group_synthetic_ohlc_daily SET run_id = run_id || '_NEW'")
        conn.commit()

    strict = audit_dc_ec_fact_parity(
        str(source_db),
        str(target_db),
        signal_date="2026-06-05",
        include_pipeline_watermark=False,
    )
    relaxed = audit_dc_ec_fact_parity(
        str(source_db),
        str(target_db),
        signal_date="2026-06-05",
        include_pipeline_watermark=False,
        parity_policy=PARITY_POLICY_RSO_REVALIDATION_METADATA,
    )

    assert strict["status"] == "FAILED"
    assert strict["required_lineage_mismatch_count"] == 5
    assert strict["operational_metadata_drift_count"] == 0
    assert relaxed["status"] == "OK_WITH_WARNINGS"
    assert relaxed["total_mismatch_count"] == 0
    assert relaxed["total_blocking_mismatch_count"] == 0
    assert relaxed["semantic_field_mismatch_count"] == 0
    assert relaxed["required_lineage_mismatch_count"] == 0
    assert relaxed["operational_metadata_drift_count"] == 5
    assert relaxed["metadata_drift_warnings"] == [
        {
            "warning_code": "EC_OPERATIONAL_METADATA_DRIFT",
            "field": "source_run_id",
            "affected_table": "ec_group_signal_daily",
            "difference_count": 3,
            "data_correctness_affected": False,
            "ec_rebuild_required": False,
        },
        {
            "warning_code": "EC_OPERATIONAL_METADATA_DRIFT",
            "field": "source_run_id",
            "affected_table": "ec_group_synthetic_ohlc_daily",
            "difference_count": 2,
            "data_correctness_affected": False,
            "ec_rebuild_required": False,
        },
    ]


def test_rso_metadata_policy_still_blocks_semantic_drift(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(source_db)) as conn:
        conn.execute("UPDATE dc_group_swing_signal_daily SET run_id = run_id || '_NEW'")
        conn.commit()
    with _connect(str(target_db)) as conn:
        conn.execute("UPDATE ec_group_signal_daily SET member_count = member_count + 1 WHERE entity_type = 'GROUP_L1'")
        conn.commit()

    summary = audit_dc_ec_fact_parity(
        str(source_db),
        str(target_db),
        signal_date="2026-06-05",
        include_pipeline_watermark=False,
        parity_policy=PARITY_POLICY_RSO_REVALIDATION_METADATA,
    )

    assert summary["status"] == "FAILED"
    assert summary["semantic_field_mismatch_count"] == 1
    assert summary["operational_metadata_drift_count"] == 3
    assert summary["total_blocking_mismatch_count"] == 1


def test_parity_audit_missing_target_row_fails(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute("DELETE FROM ec_group_index_daily WHERE entity_type = 'GROUP_L2'")
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "FAILED"
    assert summary["group_index_parity"]["status"] == "FAILED"
    assert summary["group_index_parity"]["missing_in_target"]


def test_parity_audit_extra_target_row_fails(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_pipeline_watermark (
                ecosystem_id, pipeline_name, source_table, latest_signal_date, latest_run_id, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "EXTRA_COMPONENT", "UNKNOWN:EXTRA_COMPONENT", "2026-06-05", None, "OK", "2026-06-07T00:00:00Z"),
        )
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "FAILED"
    assert summary["pipeline_watermark_parity"]["status"] == "FAILED"
    assert summary["pipeline_watermark_parity"]["extra_in_target"]


def test_parity_audit_can_skip_pipeline_watermark_for_historical_backfill(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            UPDATE ec_pipeline_watermark
            SET latest_signal_date = '2026-05-29'
            WHERE latest_signal_date = '2026-06-05'
            """
        )
        conn.commit()

    strict_summary = audit_dc_ec_fact_parity(
        str(source_db),
        str(target_db),
        signal_date="2026-06-05",
    )
    assert strict_summary["status"] == "FAILED"
    assert strict_summary["pipeline_watermark_parity"]["status"] == "FAILED"
    assert strict_summary["pipeline_watermark_parity"]["field_mismatch_count"] > 0

    historical_summary = audit_dc_ec_fact_parity(
        str(source_db),
        str(target_db),
        signal_date="2026-06-05",
        include_pipeline_watermark=False,
    )
    assert historical_summary["status"] == "OK_WITH_WARNINGS"
    assert historical_summary["total_mismatch_count"] == 0
    assert historical_summary["pipeline_watermark_parity"]["status"] == "SKIPPED"


def test_parity_audit_missing_lineage_fails(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute("UPDATE ec_group_synthetic_ohlc_daily SET source_row_hash = '' WHERE entity_type = 'GROUP_L1'")
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "FAILED"
    assert summary["synthetic_ohlc_parity"]["status"] == "FAILED"
    assert any(example["field"] == "source_row_hash" for example in summary["synthetic_ohlc_parity"]["field_mismatch_examples"])


def test_parity_audit_group_index_member_count_mismatch_fails(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute("UPDATE ec_group_index_daily SET member_count = member_count + 1 WHERE entity_type = 'GROUP_L1'")
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "FAILED"
    assert summary["group_index_parity"]["status"] == "FAILED"
    assert any(example["field"] == "member_count" for example in summary["group_index_parity"]["field_mismatch_examples"])


def test_parity_audit_group_index_eligible_count_mismatch_fails(tmp_path) -> None:
    source_db, target_db = _build_target(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.execute("UPDATE ec_group_index_daily SET eligible_count = eligible_count + 1 WHERE entity_type = 'GROUP_L2'")
        conn.commit()
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-06-05")
    assert summary["status"] == "FAILED"
    assert summary["group_index_parity"]["status"] == "FAILED"
    assert any(example["field"] == "eligible_count" for example in summary["group_index_parity"]["field_mismatch_examples"])


def test_explicit_historical_signal_date_with_aligned_rows_passes_date_alignment(tmp_path) -> None:
    source_db, target_db = _build_target(
        tmp_path,
        signal_dates=("2026-05-29", "2026-06-05"),
        include_historical_date=True,
    )
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-05-29")
    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["date_alignment"] == "EXPLICIT_DATE_ALIGNED"
    assert summary["signal_date"] == "2026-05-29"
    assert summary["total_mismatch_count"] == 0


def test_explicit_historical_signal_date_older_than_latest_does_not_fail_only_because_latest_is_newer(tmp_path) -> None:
    source_db, target_db = _build_target(
        tmp_path,
        signal_dates=("2026-05-29",),
        include_historical_date=True,
        latest_mismatch_table="dc_ticker_swing_signal_daily",
    )
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-05-29")
    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["date_alignment"] == "EXPLICIT_DATE_ALIGNED"
    assert summary["latest_dates"]["dc_ticker_swing_signal_daily"] == "2026-06-06"
    assert summary["total_mismatch_count"] == 0


def test_explicit_historical_signal_date_missing_one_source_table_returns_failed(tmp_path) -> None:
    source_db, target_db = _build_target(
        tmp_path,
        signal_dates=(),
        include_historical_date=True,
        omit_historical_group_index=True,
    )
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db), signal_date="2026-05-29")
    assert summary["status"] == "FAILED"
    assert summary["date_alignment"] == "EXPLICIT_DATE_MISSING_SOURCE_ROWS"
    assert summary["explicit_date_source_counts"]["dc_group_index_daily"] == 0
    assert "missing rows" in summary["warnings"][0]


def test_no_explicit_signal_date_still_uses_latest_date_alignment_and_fails_on_latest_date_mismatch(tmp_path) -> None:
    source_db, target_db = _build_target(
        tmp_path,
        signal_dates=("2026-06-05",),
        latest_mismatch_table="dc_ticker_swing_signal_daily",
    )
    summary = audit_dc_ec_fact_parity(str(source_db), str(target_db))
    assert summary["status"] == "FAILED"
    assert summary["date_alignment"] == "MISMATCH"
    assert summary["total_mismatch_count"] == 1
