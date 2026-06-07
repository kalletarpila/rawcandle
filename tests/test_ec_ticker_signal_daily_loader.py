import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
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
        writer.writerow(["DC_TAXONOMY_FULL_V1", "AMD", "Compute silicon", "GPUs", "WATCH_ONLY", 1, 0.7, ""])


def _create_source_db(path: Path, rows: list[dict[str, object]]) -> None:
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
                primary_layer TEXT NULL,
                primary_subindustry TEXT NULL,
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
                bullish_divergence_signal INTEGER NULL,
                bearish_divergence_signal INTEGER NULL,
                hidden_bullish_divergence_signal INTEGER NULL,
                hidden_bearish_divergence_signal INTEGER NULL,
                bullish_candle_signal INTEGER NULL,
                bearish_candle_signal INTEGER NULL,
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
                structure_epoch_id INTEGER NULL,
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
                PRIMARY KEY (signal_date, taxonomy_version, ticker, signal_version)
            )
            """
        )
        columns = list(rows[0].keys()) if rows else []
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO dc_ticker_swing_signal_daily ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _source_row(
    *,
    ticker: str = "NVDA",
    signal_date: str = "2026-06-05",
    signal_version: str = "DC_SWING_SIGNAL_V1",
    run_id: str = "DC_TICKER_SWING_20260605_DC_SWING_SIGNAL_V1",
    close: float = 144.68,
) -> dict[str, object]:
    return {
        "signal_date": signal_date,
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "ticker": ticker,
        "primary_layer": "Compute silicon",
        "primary_subindustry": "GPUs",
        "close": close,
        "volume": 7117123.0,
        "return_5d": 0.0486,
        "return_10d": 0.1175,
        "return_20d": 0.3400,
        "return_60d": 0.7331,
        "ma10": 140.03,
        "ema10": 140.25,
        "ema20": 130.17,
        "distance_to_ma10_pct": 0.0331,
        "distance_to_ema10_pct": 0.0315,
        "distance_to_ema20_pct": 0.1113,
        "above_ma10": 1,
        "above_ema10": 1,
        "above_ema20": 1,
        "ema10_slope_positive": 1,
        "ema20_slope_positive": 1,
        "ema10_slope_lookback": 3,
        "ema20_slope_lookback": 5,
        "highest_close_20d": 149.67,
        "volume_avg_20d": 5876735.05,
        "volume_vs_avg20": 1.211,
        "latest_structure_label": "HL",
        "latest_structure_confirmed_as_of_date": "2026-06-02",
        "bullish_divergence_signal": 0,
        "bearish_divergence_signal": 0,
        "hidden_bullish_divergence_signal": 0,
        "hidden_bearish_divergence_signal": 0,
        "bullish_candle_signal": 0,
        "bearish_candle_signal": 0,
        "breakout_signal": 0,
        "fast_ema10_pullback_signal": 0,
        "conservative_ema20_pullback_signal": 0,
        "pullback_signal": 0,
        "exit_risk_signal": 0,
        "exit_reason": "",
        "price_data_status": "OK",
        "signal_version": signal_version,
        "run_id": run_id,
        "created_at_utc": "2026-06-07T03:48:05Z",
        "exit_risk_severity": None,
        "latest_structure_age_trading_days": 3,
        "latest_structure_freshness": "FRESH",
        "ticker_trend_state": "NEUTRAL",
        "structure_epoch_id": 12,
        "latest_bos_event_type": "BOS_UP",
        "latest_bos_event_date": "2026-05-04",
        "latest_bos_confirmed_as_of_date": "2026-05-04",
        "latest_bos_age_trading_days": 23,
        "latest_bos_freshness": "AGING",
        "latest_reset_event_date": "2026-01-26",
        "latest_reset_confirmed_as_of_date": "2026-01-26",
        "latest_reset_reason": "DOUBLE_BOS_UP",
        "latest_reset_age_trading_days": 91,
        "latest_reset_freshness": "STALE",
    }


def _setup_target_db(tmp_path) -> tuple[Path, Path]:
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    target_db = tmp_path / "target.db"
    taxonomy_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(target_db))
    _write_taxonomy_csv(taxonomy_path)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(target_db),
        taxonomy_csv_path=str(taxonomy_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    return target_db, taxonomy_path


def test_loader_persists_ticker_fact_rows_lineage_and_signal_run(tmp_path) -> None:
    source_db = tmp_path / "source.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row()])

    summary = load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    conn = _connect(str(target_db))
    try:
        row = conn.execute(
            """
            SELECT
                ticker,
                signal_date,
                signal_version,
                close,
                volume,
                distance_to_ema10_pct,
                latest_structure_date,
                latest_bos_date,
                latest_reset_date,
                primary_group_l1_code,
                primary_group_l2_code,
                source_table,
                source_pk_json,
                source_row_hash,
                source_run_id,
                data_quality_status
            FROM ec_ticker_signal_daily
            """
        ).fetchone()
        assert row[:11] == (
            "NVDA",
            "2026-06-05",
            "DC_SWING_SIGNAL_V1",
            144.68,
            7117123.0,
            0.0315,
            "2026-06-02",
            "2026-05-04",
            "2026-01-26",
            "COMPUTE_SILICON",
            "GPUS",
        )
        assert row[11] == "dc_ticker_swing_signal_daily"
        source_pk = json.loads(row[12])
        assert source_pk == {
            "run_id": "DC_TICKER_SWING_20260605_DC_SWING_SIGNAL_V1",
            "signal_date": "2026-06-05",
            "signal_version": "DC_SWING_SIGNAL_V1",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
            "ticker": "NVDA",
        }
        assert len(row[13]) == 64
        assert row[14] == "DC_TICKER_SWING_20260605_DC_SWING_SIGNAL_V1"
        assert row[15] is None

        signal_run = conn.execute(
            """
            SELECT run_type, signal_version, source_mode, status, started_at_utc, finished_at_utc
            FROM ec_signal_run
            WHERE run_id = 'DC_TICKER_SWING_20260605_DC_SWING_SIGNAL_V1'
            """
        ).fetchone()
        assert signal_run == (
            "TICKER_SIGNAL",
            "DC_SWING_SIGNAL_V1",
            "DC_BACKFILL",
            "OK",
            "2026-06-07T03:48:05Z",
            "2026-06-07T03:48:05Z",
        )

        assert summary == {
            "status": "OK_WITH_WARNINGS",
            "ecosystem_code": "DATACENTER",
            "taxonomy_version_code": "DC_TAXONOMY_FULL_V1",
            "signal_date": "2026-06-05",
            "signal_version": "DC_SWING_SIGNAL_V1",
            "source_table": "dc_ticker_swing_signal_daily",
            "source_row_count": 1,
            "loaded_row_count": 1,
            "failed_row_count": 0,
            "unmapped_source_columns": [
                "fast_ema10_pullback_signal",
                "conservative_ema20_pullback_signal",
            ],
            "unmapped_target_columns": [
                "return_1d",
                "distance_to_sma50_pct",
                "distance_to_sma200_pct",
                "data_quality_status",
            ],
            "missing_ticker_entities": [],
            "missing_primary_memberships": [],
            "multiple_primary_memberships": [],
            "source_run_ids": ["DC_TICKER_SWING_20260605_DC_SWING_SIGNAL_V1"],
            "created_signal_run_count": 1,
            "reused_signal_run_count": 0,
            "warnings": [
                "Source columns not loaded into ec_ticker_signal_daily: fast_ema10_pullback_signal, conservative_ema20_pullback_signal",
                "Target columns left NULL because current dc source has no values: return_1d, distance_to_sma50_pct, distance_to_sma200_pct, data_quality_status",
            ],
        }
    finally:
        conn.close()


def test_loader_fails_when_ticker_entity_is_missing(tmp_path) -> None:
    source_db = tmp_path / "source_missing_ticker.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(ticker="CRGY")])

    summary = load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    with _connect(str(target_db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ec_ticker_signal_daily").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM ec_signal_run WHERE run_id = 'DC_TICKER_SWING_20260605_DC_SWING_SIGNAL_V1'"
        ).fetchone()[0] == 0
    assert summary["status"] == "FAILED"
    assert summary["missing_ticker_entities"] == ["CRGY"]
    assert summary["failed_row_count"] == 1


def test_loader_fails_when_primary_membership_is_missing(tmp_path) -> None:
    source_db = tmp_path / "source_missing_membership.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row()])

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            UPDATE ec_membership
            SET is_primary = 0
            WHERE child_entity_id = (
                SELECT entity_id FROM ec_entity WHERE entity_type = 'TICKER' AND entity_code = 'NVDA'
            )
            """
        )
        conn.commit()

    summary = load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    assert summary["status"] == "FAILED"
    assert summary["missing_primary_memberships"] == ["NVDA"]
    assert summary["failed_row_count"] == 1


def test_loader_fails_when_multiple_primary_memberships_exist(tmp_path) -> None:
    source_db = tmp_path / "source_multi_primary.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row()])

    with _connect(str(target_db)) as conn:
        accelerators_id = conn.execute(
            """
            INSERT INTO ec_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, entity_role_code, status
            ) VALUES (1, 'GROUP_L2', 'ACCELERATORS', 'Accelerators', NULL, 'GROUP_L2', 'ACTIVE')
            RETURNING entity_id
            """
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO ec_membership (
                ecosystem_id, taxonomy_version_id, parent_entity_id, child_entity_id,
                membership_type, membership_role, is_primary, role_weight, status
            ) VALUES (
                1,
                1,
                ?,
                (SELECT entity_id FROM ec_entity WHERE entity_type = 'TICKER' AND entity_code = 'NVDA'),
                'CONTAINS',
                'EXTENDED',
                1,
                0.5,
                'ACTIVE'
            )
            """,
            (accelerators_id,),
        )
        conn.commit()

    summary = load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    assert summary["status"] == "FAILED"
    assert summary["multiple_primary_memberships"] == ["NVDA"]
    assert summary["failed_row_count"] == 1


def test_loader_duplicate_scope_requires_replace_existing_and_replace_is_scoped(tmp_path) -> None:
    source_db = tmp_path / "source_replace.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(close=144.68)])

    first_summary = load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )
    assert first_summary["loaded_row_count"] == 1

    with pytest.raises(ValueError, match="Target ticker fact rows already exist"):
        load_ec_ticker_signal_daily_from_dc(
            source_db_path=str(source_db),
            target_db_path=str(target_db),
            replace_existing=False,
        )

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_signal_run (
                run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, signal_version,
                source_mode, status, started_at_utc
            ) VALUES ('legacy-run', 1, 1, '2026-06-04', 'TICKER_SIGNAL', 'DC_SWING_SIGNAL_V1', 'TEST', 'OK', '2026-06-07T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO ec_ticker_signal_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, ticker, signal_version,
                source_table, source_pk_json, source_row_hash, source_run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "2026-06-04",
                1,
                "LEGACY",
                "DC_SWING_SIGNAL_V1",
                "dc_ticker_swing_signal_daily",
                '{"signal_date":"2026-06-04","ticker":"LEGACY"}',
                "legacy-hash",
                "legacy-run",
                "2026-06-07T00:00:00Z",
            ),
        )
        conn.commit()

    _create_source_db(source_db, [_source_row(close=155.55)])
    summary = load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
        replace_existing=True,
    )

    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT signal_date, ticker, close
            FROM ec_ticker_signal_daily
            ORDER BY signal_date, ticker
            """
        ).fetchall()
        assert rows == [
            ("2026-06-04", "LEGACY", None),
            ("2026-06-05", "NVDA", 155.55),
        ]
    assert summary["loaded_row_count"] == 1
    assert summary["reused_signal_run_count"] == 1
    assert summary["created_signal_run_count"] == 0


def test_loader_source_row_hash_is_deterministic(tmp_path) -> None:
    source_db = tmp_path / "source_hash.db"
    target_db_a, _ = _setup_target_db(tmp_path / "a")
    target_db_b, _ = _setup_target_db(tmp_path / "b")
    _create_source_db(source_db, [_source_row()])

    load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db_a),
    )
    load_ec_ticker_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db_b),
    )

    with _connect(str(target_db_a)) as conn_a, _connect(str(target_db_b)) as conn_b:
        hash_a = conn_a.execute("SELECT source_row_hash FROM ec_ticker_signal_daily").fetchone()[0]
        hash_b = conn_b.execute("SELECT source_row_hash FROM ec_ticker_signal_daily").fetchone()[0]
        assert hash_a == hash_b
