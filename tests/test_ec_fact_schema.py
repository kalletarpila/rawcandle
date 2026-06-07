import sqlite3

import pytest

from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _pk_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    pk_rows = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    return [name for _, name in pk_rows]


def _notnull_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows if int(row[3]) == 1}


def _foreign_key_tables(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return {str(row[2]) for row in rows}


def _insert_base_context(conn: sqlite3.Connection) -> dict[str, object]:
    conn.execute(
        """
        INSERT INTO ec_ecosystem (ecosystem_code, ecosystem_name, status)
        VALUES ('DATACENTER', 'Datacenter', 'ACTIVE')
        """
    )
    ecosystem_id = 1
    conn.execute(
        """
        INSERT INTO ec_taxonomy_version (
            ecosystem_id, taxonomy_version_code, taxonomy_name, source_type, source_reference,
            source_hash, status, is_active, active_from
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', 'Datacenter Full V1', 'CSV', 'taxonomy.csv', 'hash-1', 'ACTIVE', 1, '2026-06-01')
        """,
        (ecosystem_id,),
    )
    taxonomy_version_id = 1
    conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker, entity_role_code, status, active_from
        ) VALUES (?, 'ECOSYSTEM', 'DATACENTER', 'Datacenter', NULL, 'ECOSYSTEM', 'ACTIVE', '2026-06-01')
        """,
        (ecosystem_id,),
    )
    ecosystem_entity_id = 1
    conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker, entity_role_code, status, active_from
        ) VALUES (?, 'GROUP_L1', 'COMPUTE_SILICON', 'Compute silicon', NULL, 'GROUP_L1', 'ACTIVE', '2026-06-01')
        """,
        (ecosystem_id,),
    )
    group_l1_id = 2
    conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker, entity_role_code, status, active_from
        ) VALUES (?, 'GROUP_L2', 'GPUS', 'GPUs', NULL, 'GROUP_L2', 'ACTIVE', '2026-06-01')
        """,
        (ecosystem_id,),
    )
    group_l2_id = 3
    conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker, entity_role_code, status, active_from
        ) VALUES (?, 'TICKER', 'NVDA', 'NVIDIA', 'NVDA', 'TICKER', 'ACTIVE', '2026-06-01')
        """,
        (ecosystem_id,),
    )
    ticker_entity_id = 4
    conn.execute(
        """
        INSERT INTO ec_signal_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, signal_version,
            ohlc_calc_version, source_mode, status, started_at_utc
        ) VALUES (
            'run-1', ?, ?, '2026-06-05', 'FULL_DAILY', 'v1', 'v1', 'TEST', 'OK', '2026-06-05T00:00:00Z'
        )
        """,
        (ecosystem_id, taxonomy_version_id),
    )
    return {
        "ecosystem_id": ecosystem_id,
        "taxonomy_version_id": taxonomy_version_id,
        "ecosystem_entity_id": ecosystem_entity_id,
        "group_l1_id": group_l1_id,
        "group_l2_id": group_l2_id,
        "ticker_entity_id": ticker_entity_id,
        "source_run_id": "run-1",
    }


def test_ec_fact_migration_creates_fact_tables_and_no_metric_bucket(tmp_path) -> None:
    db_path = tmp_path / "ec_fact_schema.db"

    apply_ec_sidecar_migration(str(db_path))
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        expected_tables = {
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
            "ec_pipeline_watermark",
        }
        for table_name in expected_tables:
            assert _table_exists(conn, table_name)
        assert not _table_exists(conn, "ec_entity_metric_value")
    finally:
        conn.close()


def test_ec_fact_schema_keys_columns_indexes_and_foreign_keys(tmp_path) -> None:
    db_path = tmp_path / "ec_fact_shape.db"
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        assert _pk_columns(conn, "ec_ticker_signal_daily") == [
            "ecosystem_id",
            "taxonomy_version_id",
            "signal_date",
            "entity_id",
            "signal_version",
        ]
        assert _pk_columns(conn, "ec_group_signal_daily") == [
            "ecosystem_id",
            "taxonomy_version_id",
            "signal_date",
            "entity_id",
            "signal_version",
        ]
        assert _pk_columns(conn, "ec_group_synthetic_ohlc_daily") == [
            "ecosystem_id",
            "taxonomy_version_id",
            "signal_date",
            "entity_id",
            "ohlc_calc_version",
        ]
        assert _pk_columns(conn, "ec_group_index_daily") == [
            "ecosystem_id",
            "taxonomy_version_id",
            "signal_date",
            "entity_id",
            "calc_version",
        ]
        assert _pk_columns(conn, "ec_pipeline_watermark") == [
            "ecosystem_id",
            "pipeline_name",
            "source_table",
        ]

        assert {
            "ecosystem_id",
            "taxonomy_version_id",
            "signal_date",
            "entity_id",
            "ticker",
            "signal_version",
            "volume",
            "ma10",
            "ema10",
            "ema20",
            "distance_to_ema10_pct",
            "above_ma10",
            "above_ema10",
            "above_ema20",
            "ema10_slope_positive",
            "ema20_slope_positive",
            "ema10_slope_lookback",
            "ema20_slope_lookback",
            "highest_close_20d",
            "volume_avg_20d",
            "volume_vs_avg20",
            "latest_structure_age_trading_days",
            "structure_epoch_id",
            "latest_bos_confirmed_as_of_date",
            "latest_bos_age_trading_days",
            "latest_reset_confirmed_as_of_date",
            "latest_reset_age_trading_days",
            "bullish_divergence_signal",
            "bearish_divergence_signal",
            "hidden_bullish_divergence_signal",
            "hidden_bearish_divergence_signal",
            "bullish_candle_signal",
            "bearish_candle_signal",
            "source_table",
            "source_pk_json",
            "source_row_hash",
            "source_run_id",
            "created_at_utc",
        }.issubset(_table_columns(conn, "ec_ticker_signal_daily"))
        assert "pct_above_rising_ema20" in _table_columns(conn, "ec_group_signal_daily")
        assert {
            "member_count",
            "eligible_count",
            "ma20",
            "ema20",
            "distance_to_ema20_pct",
            "volatility_20d",
            "pivot_radius",
            "latest_pivot_high_date",
            "latest_pivot_high_value",
            "latest_pivot_low_date",
            "latest_pivot_low_value",
            "relative_base_window",
            "relative_open_20",
            "relative_high_20",
            "relative_low_20",
            "relative_close_20",
            "relative_upper_wick_20",
            "relative_lower_wick_20",
            "relative_close_extension_20",
            "relative_high_extension_20",
            "relative_low_extension_20",
            "relative_eligible_count",
            "latest_structure_age_trading_days",
            "latest_bos_confirmed_as_of_date",
            "latest_bos_age_trading_days",
            "latest_reset_confirmed_as_of_date",
            "latest_reset_age_trading_days",
        }.issubset(_table_columns(conn, "ec_group_synthetic_ohlc_daily"))
        assert {
            "member_count",
            "eligible_count",
            "ma50_eligible_count",
            "ma200_eligible_count",
            "median_return",
            "pct_positive",
            "pct_above_ma50",
            "pct_above_ma200",
            "volatility_60d",
            "relative_strength_spy_60d",
            "relative_strength_qqq_60d",
        }.issubset(_table_columns(conn, "ec_group_index_daily"))
        assert "watchlist_status" not in _table_columns(conn, "ec_ticker_signal_daily")
        assert "signal_date" in _table_columns(conn, "ec_group_synthetic_ohlc_daily")
        assert "ohlc_date" not in _table_columns(conn, "ec_group_synthetic_ohlc_daily")
        assert "signal_date" in _table_columns(conn, "ec_group_index_daily")
        assert "index_date" not in _table_columns(conn, "ec_group_index_daily")

        for table_name in (
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
        ):
            assert {
                "source_table",
                "source_pk_json",
                "source_row_hash",
                "source_run_id",
                "created_at_utc",
            }.issubset(_notnull_columns(conn, table_name))

        assert {
            "idx_ec_ticker_signal_daily_ecosystem_signal_date",
            "idx_ec_ticker_signal_daily_entity_signal_date",
            "idx_ec_ticker_signal_daily_ticker_signal_date",
            "idx_ec_ticker_signal_daily_source_run_id",
        }.issubset(_index_names(conn, "ec_ticker_signal_daily"))
        assert {
            "idx_ec_group_signal_daily_ecosystem_signal_date",
            "idx_ec_group_signal_daily_entity_signal_date",
            "idx_ec_group_signal_daily_entity_type_signal_date",
            "idx_ec_group_signal_daily_source_run_id",
        }.issubset(_index_names(conn, "ec_group_signal_daily"))
        assert {
            "idx_ec_group_synthetic_ohlc_daily_ecosystem_signal_date",
            "idx_ec_group_synthetic_ohlc_daily_entity_signal_date",
            "idx_ec_group_synthetic_ohlc_daily_entity_type_signal_date",
            "idx_ec_group_synthetic_ohlc_daily_source_run_id",
        }.issubset(_index_names(conn, "ec_group_synthetic_ohlc_daily"))
        assert {
            "idx_ec_group_index_daily_ecosystem_signal_date",
            "idx_ec_group_index_daily_entity_signal_date",
            "idx_ec_group_index_daily_entity_type_signal_date",
            "idx_ec_group_index_daily_source_run_id",
        }.issubset(_index_names(conn, "ec_group_index_daily"))
        assert "idx_ec_pipeline_watermark_ecosystem_status" in _index_names(conn, "ec_pipeline_watermark")

        assert _foreign_key_tables(conn, "ec_ticker_signal_daily") == {
            "ec_ecosystem",
            "ec_taxonomy_version",
            "ec_entity",
            "ec_signal_run",
        }
        assert _foreign_key_tables(conn, "ec_group_signal_daily") == {
            "ec_ecosystem",
            "ec_taxonomy_version",
            "ec_entity",
            "ec_signal_run",
        }
        assert _foreign_key_tables(conn, "ec_group_synthetic_ohlc_daily") == {
            "ec_ecosystem",
            "ec_taxonomy_version",
            "ec_entity",
            "ec_signal_run",
        }
        assert _foreign_key_tables(conn, "ec_group_index_daily") == {
            "ec_ecosystem",
            "ec_taxonomy_version",
            "ec_entity",
            "ec_signal_run",
        }
        assert _foreign_key_tables(conn, "ec_pipeline_watermark") == {"ec_ecosystem", "ec_signal_run"}
    finally:
        conn.close()


def test_ec_fact_schema_minimal_insert_paths_and_duplicate_pk_rejection(tmp_path) -> None:
    db_path = tmp_path / "ec_fact_insert.db"
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        ctx = _insert_base_context(conn)
        conn.execute(
            """
            INSERT INTO ec_ticker_signal_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, ticker, signal_version,
                primary_group_l1_entity_id, primary_group_l2_entity_id,
                volume, ma10, ema10, ema20, distance_to_ema10_pct,
                above_ma10, above_ema10, above_ema20,
                ema10_slope_positive, ema20_slope_positive,
                ema10_slope_lookback, ema20_slope_lookback,
                highest_close_20d, volume_avg_20d, volume_vs_avg20,
                latest_structure_age_trading_days, structure_epoch_id,
                latest_bos_confirmed_as_of_date, latest_bos_age_trading_days,
                latest_reset_confirmed_as_of_date, latest_reset_age_trading_days,
                bullish_divergence_signal, bearish_divergence_signal,
                hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                bullish_candle_signal, bearish_candle_signal,
                source_table, source_pk_json, source_row_hash, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["ticker_entity_id"], "NVDA", "v1",
                ctx["group_l1_id"], ctx["group_l2_id"],
                1000.0, 950.0, 960.0, 970.0, 0.04,
                1, 1, 1,
                1, 1,
                3, 5,
                1010.0, 800.0, 1.25,
                4, "epoch-12",
                "2026-06-04", 2,
                "2026-06-01", 5,
                0, 0,
                0, 0,
                1, 0,
                "dc_ticker_swing_signal_daily",
                '{"signal_date":"2026-06-05","ticker":"NVDA"}', "hash-ticker-1", ctx["source_run_id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO ec_group_signal_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, signal_version,
                pct_above_rising_ema20,
                source_table, source_pk_json, source_row_hash, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["group_l1_id"], "GROUP_L1", "v1",
                42.0,
                "dc_group_swing_signal_daily", '{"signal_date":"2026-06-05","group":"COMPUTE_SILICON"}',
                "hash-group-signal-1", ctx["source_run_id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO ec_group_synthetic_ohlc_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, ohlc_calc_version,
                member_count, eligible_count, ma20, ema20, distance_to_ema20_pct, volatility_20d,
                pivot_radius, latest_pivot_high_date, latest_pivot_high_value,
                relative_base_window, relative_open_20, relative_close_20,
                latest_bos_confirmed_as_of_date, latest_bos_age_trading_days,
                source_table, source_pk_json, source_row_hash, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["group_l2_id"], "GROUP_L2", "v1",
                11, 11, 82.1, 82.2, -0.01, 0.02,
                5, "2026-05-29", 87.1,
                20, 1.0, 1.0,
                "2026-02-27", 68,
                "dc_group_synthetic_ohlc_daily", '{"ohlc_date":"2026-06-05","group":"GPUS"}',
                "hash-group-ohlc-1", ctx["source_run_id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO ec_group_index_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, calc_version,
                member_count, eligible_count,
                ma50_eligible_count, ma200_eligible_count, median_return, pct_positive,
                pct_above_ma50, pct_above_ma200, volatility_60d,
                relative_strength_spy_60d, relative_strength_qqq_60d,
                source_table, source_pk_json, source_row_hash, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["ecosystem_entity_id"], "ECOSYSTEM", "v1",
                229, 229,
                229, 229, -0.05, 6.5,
                63.7, 75.9, 0.022,
                0.20, 0.13,
                "dc_group_index_daily", '{"index_date":"2026-06-05","group":"DATACENTER"}',
                "hash-group-index-1", ctx["source_run_id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO ec_pipeline_watermark (
                ecosystem_id, pipeline_name, source_table, latest_signal_date, latest_run_id, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ctx["ecosystem_id"], "EC_PARITY_LOAD", "dc_ticker_swing_signal_daily",
                "2026-06-05", ctx["source_run_id"], "OK",
            ),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_ticker_signal_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, ticker, signal_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["ticker_entity_id"], "NVDA", "v1",
                    "dc_ticker_swing_signal_daily", '{"signal_date":"2026-06-05","ticker":"NVDA"}',
                    "hash-ticker-2", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_group_signal_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, signal_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["group_l1_id"], "GROUP_L1", "v1",
                    "dc_group_swing_signal_daily", '{"signal_date":"2026-06-05","group":"COMPUTE_SILICON"}',
                    "hash-group-signal-2", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_group_synthetic_ohlc_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, ohlc_calc_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["group_l2_id"], "GROUP_L2", "v1",
                    "dc_group_synthetic_ohlc_daily", '{"ohlc_date":"2026-06-05","group":"GPUS"}',
                    "hash-group-ohlc-2", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_group_index_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, calc_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["ecosystem_entity_id"], "ECOSYSTEM", "v1",
                    "dc_group_index_daily", '{"index_date":"2026-06-05","group":"DATACENTER"}',
                    "hash-group-index-2", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_pipeline_watermark (
                    ecosystem_id, pipeline_name, source_table, latest_signal_date, latest_run_id, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], "EC_PARITY_LOAD", "dc_ticker_swing_signal_daily",
                    "2026-06-06", ctx["source_run_id"], "OK",
                ),
            )
    finally:
        conn.close()


def test_ec_fact_schema_foreign_keys_are_enforced(tmp_path) -> None:
    db_path = tmp_path / "ec_fact_fk.db"
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        ctx = _insert_base_context(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_ticker_signal_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, ticker, signal_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], 999, "2026-06-05", ctx["ticker_entity_id"], "NVDA", "v1",
                    "dc_ticker_swing_signal_daily", '{"signal_date":"2026-06-05","ticker":"NVDA"}',
                    "hash-bad-taxonomy", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_group_signal_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, signal_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    999, ctx["taxonomy_version_id"], "2026-06-05", ctx["group_l1_id"], "GROUP_L1", "v1",
                    "dc_group_swing_signal_daily", '{"signal_date":"2026-06-05","group":"COMPUTE_SILICON"}',
                    "hash-bad-ecosystem", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_group_synthetic_ohlc_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, ohlc_calc_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", 999, "GROUP_L2", "v1",
                    "dc_group_synthetic_ohlc_daily", '{"ohlc_date":"2026-06-05","group":"GPUS"}',
                    "hash-bad-entity", ctx["source_run_id"],
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_group_index_daily (
                    ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, calc_version,
                    source_table, source_pk_json, source_row_hash, source_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], ctx["taxonomy_version_id"], "2026-06-05", ctx["ecosystem_entity_id"], "ECOSYSTEM", "v1",
                    "dc_group_index_daily", '{"index_date":"2026-06-05","group":"DATACENTER"}',
                    "hash-bad-run", "missing-run",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_pipeline_watermark (
                    ecosystem_id, pipeline_name, source_table, latest_signal_date, latest_run_id, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx["ecosystem_id"], "EC_PARITY_LOAD", "dc_group_index_daily",
                    "2026-06-05", "missing-run", "OK",
                ),
            )
    finally:
        conn.close()


def test_ec_fact_schema_migration_runner_applies_group_index_count_patch(tmp_path) -> None:
    db_path = tmp_path / "ec_fact_group_index_count_patch.db"
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        columns = _table_columns(conn, "ec_group_index_daily")
        assert "member_count" in columns
        assert "eligible_count" in columns
    finally:
        conn.close()
