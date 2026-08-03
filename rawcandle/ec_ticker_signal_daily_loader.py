from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_SOURCE_TABLE = "dc_ticker_swing_signal_daily"
REQUIRED_TARGET_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_membership",
    "ec_signal_run",
    "ec_ticker_signal_daily",
)
REQUIRED_SOURCE_COLUMNS = (
    "signal_date",
    "taxonomy_version",
    "ticker",
    "primary_layer",
    "primary_subindustry",
    "close",
    "volume",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "ma10",
    "ema10",
    "ema20",
    "distance_to_ma10_pct",
    "distance_to_ema10_pct",
    "distance_to_ema20_pct",
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
    "latest_structure_label",
    "latest_structure_confirmed_as_of_date",
    "breakout_signal",
    "fast_ema10_pullback_signal",
    "conservative_ema20_pullback_signal",
    "pullback_signal",
    "exit_risk_signal",
    "exit_reason",
    "price_data_status",
    "signal_version",
    "run_id",
    "created_at_utc",
    "exit_risk_severity",
    "latest_structure_age_trading_days",
    "latest_structure_freshness",
    "ticker_trend_state",
    "structure_epoch_id",
    "latest_bos_event_type",
    "latest_bos_event_date",
    "latest_bos_confirmed_as_of_date",
    "latest_bos_age_trading_days",
    "latest_bos_freshness",
    "latest_reset_event_date",
    "latest_reset_confirmed_as_of_date",
    "latest_reset_reason",
    "latest_reset_age_trading_days",
    "latest_reset_freshness",
    "bullish_divergence_signal",
    "bearish_divergence_signal",
    "hidden_bullish_divergence_signal",
    "hidden_bearish_divergence_signal",
    "bullish_candle_signal",
    "bearish_candle_signal",
)
TARGET_MAPPED_COLUMNS = (
    "close",
    "volume",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "ma10",
    "ema10",
    "ema20",
    "distance_to_ma10_pct",
    "distance_to_ema10_pct",
    "distance_to_ema20_pct",
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
    "latest_structure_label",
    "latest_structure_date",
    "latest_structure_age_trading_days",
    "latest_structure_freshness",
    "ticker_trend_state",
    "structure_epoch_id",
    "latest_bos_event_type",
    "latest_bos_date",
    "latest_bos_confirmed_as_of_date",
    "latest_bos_age_trading_days",
    "latest_bos_freshness",
    "latest_reset_reason",
    "latest_reset_date",
    "latest_reset_confirmed_as_of_date",
    "latest_reset_age_trading_days",
    "latest_reset_freshness",
    "breakout_signal",
    "pullback_signal",
    "exit_risk_signal",
    "exit_risk_severity",
    "exit_reason",
    "bullish_divergence_signal",
    "bearish_divergence_signal",
    "hidden_bullish_divergence_signal",
    "hidden_bearish_divergence_signal",
    "bullish_candle_signal",
    "bearish_candle_signal",
    "price_data_status",
)
EXPECTED_UNMAPPED_SOURCE_COLUMNS = (
    "fast_ema10_pullback_signal",
    "conservative_ema20_pullback_signal",
)
EXPECTED_UNMAPPED_TARGET_COLUMNS = (
    "return_1d",
    "distance_to_sma50_pct",
    "distance_to_sma200_pct",
    "data_quality_status",
)


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_readwrite(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _require_table(conn: sqlite3.Connection, table_name: str, label: str) -> None:
    if table_name not in _table_names(conn):
        raise ValueError(f"Missing required {label} table: {table_name}")


def _require_tables(conn: sqlite3.Connection, table_names: tuple[str, ...], label: str) -> None:
    existing = _table_names(conn)
    missing = [table_name for table_name in table_names if table_name not in existing]
    if missing:
        raise ValueError(f"Missing required {label} tables: {missing}")


def _require_columns(
    conn: sqlite3.Connection,
    table_name: str,
    required_columns: tuple[str, ...],
    label: str,
) -> None:
    existing = _table_columns(conn, table_name)
    missing = [column for column in required_columns if column not in existing]
    if missing:
        raise ValueError(f"Missing required columns for {label} table {table_name}: {missing}")


def _fetch_single_value(conn: sqlite3.Connection, query: str, params: tuple[object, ...]) -> str | None:
    row = conn.execute(query, params).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _resolve_signal_date(conn: sqlite3.Connection, signal_date: str | None) -> str:
    if signal_date is not None:
        return signal_date
    resolved = _fetch_single_value(
        conn,
        f"SELECT MAX(signal_date) FROM {REQUIRED_SOURCE_TABLE}",
        (),
    )
    if resolved is None:
        raise ValueError("Could not resolve latest signal_date from dc_ticker_swing_signal_daily")
    return resolved


def _resolve_signal_version(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    signal_version: str | None,
) -> str:
    if signal_version is not None:
        row_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM dc_ticker_swing_signal_daily
                WHERE signal_date = ?
                  AND signal_version = ?
                  AND taxonomy_version = ?
                """,
                (signal_date, signal_version, taxonomy_version_code),
            ).fetchone()[0]
        )
        if row_count == 0:
            raise ValueError(
                "No source rows found for requested taxonomy/signal scope: "
                f"signal_date={signal_date!r}, signal_version={signal_version!r}, "
                f"taxonomy_version={taxonomy_version_code!r}"
            )
        return signal_version
    rows = conn.execute(
        """
        SELECT DISTINCT signal_version
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND taxonomy_version = ?
        ORDER BY signal_version
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    versions = [str(row[0]) for row in rows if row[0] is not None]
    if not versions:
        raise ValueError(
            "No source rows found for requested taxonomy/date scope: "
            f"signal_date={signal_date!r}, taxonomy_version={taxonomy_version_code!r}"
        )
    if len(versions) > 1:
        raise ValueError(
            "Multiple signal_version values found for selected taxonomy/date scope; "
            "signal_version must be provided explicitly"
        )
    return versions[0]


def _resolve_target_context(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT e.ecosystem_id, tv.taxonomy_version_id
        FROM ec_ecosystem e
        JOIN ec_taxonomy_version tv ON tv.ecosystem_id = e.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    if row is None:
        raise ValueError(
            "Required ec target context not found for "
            f"ecosystem_code={ecosystem_code!r}, taxonomy_version_code={taxonomy_version_code!r}"
        )
    return int(row[0]), int(row[1])


def _resolve_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
          AND taxonomy_version = ?
        ORDER BY ticker
        """,
        (signal_date, signal_version, taxonomy_version_code),
    ).fetchall()
    if not rows:
        raise ValueError(
            "No source rows found for "
            f"signal_date={signal_date!r}, signal_version={signal_version!r}, "
            f"taxonomy_version={taxonomy_version_code!r}"
        )
    return rows


def _source_validation_summary(
    rows: list[sqlite3.Row],
    *,
    requested_taxonomy_version: str,
) -> dict[str, object]:
    source_taxonomy_versions = sorted({str(row["taxonomy_version"]) for row in rows})
    ticker_counts = {
        ticker: count
        for ticker, count in {
            ticker: sum(1 for row in rows if str(row["ticker"]) == ticker)
            for ticker in sorted({str(row["ticker"]) for row in rows})
        }.items()
        if count > 1
    }
    unexpected_rows = [
        str(row["ticker"])
        for row in rows
        if str(row["taxonomy_version"]) != requested_taxonomy_version
    ]
    duplicate_source_tickers = sorted(ticker_counts)
    return {
        "requested_taxonomy_version": requested_taxonomy_version,
        "source_taxonomy_version": source_taxonomy_versions[0] if len(source_taxonomy_versions) == 1 else None,
        "source_taxonomy_versions": source_taxonomy_versions,
        "source_taxonomy_match": source_taxonomy_versions == [requested_taxonomy_version],
        "source_row_count": len(rows),
        "source_distinct_ticker_count": len({str(row["ticker"]) for row in rows}),
        "duplicate_source_ticker_count": len(duplicate_source_tickers),
        "duplicate_source_tickers": duplicate_source_tickers,
        "unexpected_taxonomy_version_count": len(unexpected_rows),
        "unexpected_taxonomy_version_tickers": sorted(set(unexpected_rows)),
    }


def _target_key_validation_summary(
    target_keys: list[tuple[int | None, int | None, str | None, int | None, str | None]],
) -> dict[str, object]:
    key_counts: dict[tuple[int | None, int | None, str | None, int | None, str | None], int] = {}
    for key in target_keys:
        key_counts[key] = key_counts.get(key, 0) + 1
    duplicate_keys = [
        {
            "ecosystem_id": key[0],
            "taxonomy_version_id": key[1],
            "signal_date": key[2],
            "entity_id": key[3],
            "signal_version": key[4],
            "count": count,
        }
        for key, count in sorted(key_counts.items(), key=lambda item: tuple("" if part is None else str(part) for part in item[0]))
        if count > 1
    ]
    null_keys = [key for key in target_keys if any(part is None for part in key)]
    return {
        "duplicate_target_key_count": len(duplicate_keys),
        "duplicate_target_keys": duplicate_keys,
        "null_target_key_count": len(null_keys),
    }


def _source_scope_failed_summary(
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
    signal_date: str,
    signal_version: str | None,
    error_code: str,
    error: str,
) -> dict[str, object]:
    return {
        "status": "FAILED",
        "loader_status": "FAILED",
        "loader_error_code": error_code,
        "loader_error": error,
        "ticker_loader_error": error,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "requested_taxonomy_version": taxonomy_version_code,
        "signal_date": signal_date,
        "signal_version": signal_version,
        "source_table": REQUIRED_SOURCE_TABLE,
        "source_taxonomy_version": None,
        "source_taxonomy_versions": [],
        "source_taxonomy_match": False,
        "source_row_count": 0,
        "source_distinct_ticker_count": 0,
        "duplicate_source_ticker_count": 0,
        "duplicate_source_tickers": [],
        "unexpected_taxonomy_version_count": 0,
        "unexpected_taxonomy_version_tickers": [],
        "loaded_row_count": 0,
        "failed_row_count": 0,
        "mapped_row_count": 0,
        "unresolved_membership_count": 0,
        "unresolved_tickers": [],
        "missing_ticker_entities": [],
        "missing_primary_memberships": [],
        "multiple_primary_memberships": [],
        "duplicate_target_key_count": 0,
        "duplicate_target_keys": [],
        "null_target_key_count": 0,
        "source_run_ids": [],
        "created_signal_run_count": 0,
        "reused_signal_run_count": 0,
        "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
        "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
        "warnings": [],
    }


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {str(key): row[key] for key in row.keys()}


def _row_hash(row: sqlite3.Row) -> str:
    payload = _canonical_json(_row_to_dict(row))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_pk_json(row: sqlite3.Row) -> str:
    return _canonical_json(
        {
            "run_id": row["run_id"],
            "signal_date": row["signal_date"],
            "signal_version": row["signal_version"],
            "taxonomy_version": row["taxonomy_version"],
            "ticker": row["ticker"],
        }
    )


def _target_scope_row_count(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    signal_version: str,
) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_ticker_signal_daily
            WHERE ecosystem_id = ?
              AND taxonomy_version_id = ?
              AND signal_date = ?
              AND signal_version = ?
              AND source_table = ?
            """,
            (
                ecosystem_id,
                taxonomy_version_id,
                signal_date,
                signal_version,
                REQUIRED_SOURCE_TABLE,
            ),
        ).fetchone()[0]
    )


def _ensure_replace_policy(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    signal_version: str,
    replace_existing: bool,
) -> None:
    existing_count = _target_scope_row_count(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
        signal_version=signal_version,
    )
    if existing_count == 0:
        return
    if not replace_existing:
        raise ValueError(
            "Target ticker fact rows already exist for ecosystem/taxonomy/date/version scope; "
            "use replace_existing=True to replace them"
        )
    conn.execute(
        """
        DELETE FROM ec_ticker_signal_daily
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND signal_date = ?
          AND signal_version = ?
        """,
        (ecosystem_id, taxonomy_version_id, signal_date, signal_version),
    )


def _resolve_ticker_entity_id(conn: sqlite3.Connection, *, ecosystem_id: int, ticker: str) -> int | None:
    row = conn.execute(
        """
        SELECT entity_id
        FROM ec_entity
        WHERE ecosystem_id = ?
          AND entity_type = 'TICKER'
          AND entity_code = ?
        """,
        (ecosystem_id, ticker),
    ).fetchone()
    return None if row is None else int(row[0])


def _resolve_primary_membership_context(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    ticker_entity_id: int,
) -> tuple[str, int | None, int | None, str | None, str | None]:
    rows = conn.execute(
        """
        SELECT parent.entity_id, parent.entity_code
        FROM ec_membership m
        JOIN ec_entity parent ON parent.entity_id = m.parent_entity_id
        WHERE m.taxonomy_version_id = ?
          AND m.child_entity_id = ?
          AND m.is_primary = 1
          AND parent.entity_type = 'GROUP_L2'
        ORDER BY parent.entity_code
        """,
        (taxonomy_version_id, ticker_entity_id),
    ).fetchall()
    if not rows:
        return "missing", None, None, None, None
    if len(rows) > 1:
        return "multiple", None, None, None, None

    group_l2_id = int(rows[0][0])
    group_l2_code = str(rows[0][1])
    parent_rows = conn.execute(
        """
        SELECT parent.entity_id, parent.entity_code
        FROM ec_membership m
        JOIN ec_entity parent ON parent.entity_id = m.parent_entity_id
        WHERE m.taxonomy_version_id = ?
          AND m.child_entity_id = ?
          AND parent.entity_type = 'GROUP_L1'
        ORDER BY parent.entity_code
        """,
        (taxonomy_version_id, group_l2_id),
    ).fetchall()
    if len(parent_rows) != 1:
        return "missing", None, None, None, None

    group_l1_id = int(parent_rows[0][0])
    group_l1_code = str(parent_rows[0][1])
    return "ok", group_l1_id, group_l2_id, group_l1_code, group_l2_code


def _ensure_signal_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    signal_version: str,
    source_created_at_utc: str | None,
    loader_timestamp_utc: str,
) -> bool:
    existing = conn.execute(
        "SELECT 1 FROM ec_signal_run WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if existing is not None:
        return False

    started_at_utc = source_created_at_utc or loader_timestamp_utc
    conn.execute(
        """
        INSERT INTO ec_signal_run (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            run_type,
            signal_version,
            ohlc_calc_version,
            source_mode,
            status,
            started_at_utc,
            finished_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            "TICKER_SIGNAL",
            signal_version,
            None,
            "DC_BACKFILL",
            "OK",
            started_at_utc,
            source_created_at_utc,
        ),
    )
    return True


def _insert_target_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    loader_timestamp_utc: str,
    entity_id: int,
    primary_group_l1_entity_id: int,
    primary_group_l2_entity_id: int,
    primary_group_l1_code: str,
    primary_group_l2_code: str,
    row: sqlite3.Row,
) -> None:
    conn.execute(
        """
        INSERT INTO ec_ticker_signal_daily (
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            entity_id,
            ticker,
            signal_version,
            primary_group_l1_entity_id,
            primary_group_l2_entity_id,
            primary_group_l1_code,
            primary_group_l2_code,
            close,
            volume,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            ma10,
            ema10,
            ema20,
            distance_to_ma10_pct,
            distance_to_ema10_pct,
            distance_to_ema20_pct,
            above_ma10,
            above_ema10,
            above_ema20,
            ema10_slope_positive,
            ema20_slope_positive,
            ema10_slope_lookback,
            ema20_slope_lookback,
            highest_close_20d,
            volume_avg_20d,
            volume_vs_avg20,
            latest_structure_label,
            latest_structure_date,
            latest_structure_age_trading_days,
            latest_structure_freshness,
            ticker_trend_state,
            structure_epoch_id,
            latest_bos_event_type,
            latest_bos_date,
            latest_bos_confirmed_as_of_date,
            latest_bos_age_trading_days,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_date,
            latest_reset_confirmed_as_of_date,
            latest_reset_age_trading_days,
            latest_reset_freshness,
            breakout_signal,
            pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            exit_reason,
            bullish_divergence_signal,
            bearish_divergence_signal,
            hidden_bullish_divergence_signal,
            hidden_bearish_divergence_signal,
            bullish_candle_signal,
            bearish_candle_signal,
            price_data_status,
            data_quality_status,
            source_table,
            source_pk_json,
            source_row_hash,
            source_run_id,
            created_at_utc
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            ecosystem_id,
            taxonomy_version_id,
            row["signal_date"],
            entity_id,
            row["ticker"],
            row["signal_version"],
            primary_group_l1_entity_id,
            primary_group_l2_entity_id,
            primary_group_l1_code,
            primary_group_l2_code,
            row["close"],
            row["volume"],
            row["return_5d"],
            row["return_10d"],
            row["return_20d"],
            row["return_60d"],
            row["ma10"],
            row["ema10"],
            row["ema20"],
            row["distance_to_ma10_pct"],
            row["distance_to_ema10_pct"],
            row["distance_to_ema20_pct"],
            row["above_ma10"],
            row["above_ema10"],
            row["above_ema20"],
            row["ema10_slope_positive"],
            row["ema20_slope_positive"],
            row["ema10_slope_lookback"],
            row["ema20_slope_lookback"],
            row["highest_close_20d"],
            row["volume_avg_20d"],
            row["volume_vs_avg20"],
            row["latest_structure_label"],
            row["latest_structure_confirmed_as_of_date"],
            row["latest_structure_age_trading_days"],
            row["latest_structure_freshness"],
            row["ticker_trend_state"],
            str(row["structure_epoch_id"]) if row["structure_epoch_id"] is not None else None,
            row["latest_bos_event_type"],
            row["latest_bos_event_date"],
            row["latest_bos_confirmed_as_of_date"],
            row["latest_bos_age_trading_days"],
            row["latest_bos_freshness"],
            row["latest_reset_reason"],
            row["latest_reset_event_date"],
            row["latest_reset_confirmed_as_of_date"],
            row["latest_reset_age_trading_days"],
            row["latest_reset_freshness"],
            row["breakout_signal"],
            row["pullback_signal"],
            row["exit_risk_signal"],
            row["exit_risk_severity"],
            row["exit_reason"],
            row["bullish_divergence_signal"],
            row["bearish_divergence_signal"],
            row["hidden_bullish_divergence_signal"],
            row["hidden_bearish_divergence_signal"],
            row["bullish_candle_signal"],
            row["bearish_candle_signal"],
            row["price_data_status"],
            None,
            REQUIRED_SOURCE_TABLE,
            _source_pk_json(row),
            _row_hash(row),
            row["run_id"],
            loader_timestamp_utc,
        ),
    )


def load_ec_ticker_signal_daily_from_dc(
    source_db_path: str,
    target_db_path: str,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    signal_date: str | None = None,
    signal_version: str | None = None,
    replace_existing: bool = False,
) -> dict[str, object]:
    source_conn = _connect_readonly(source_db_path)
    target_conn = _connect_readwrite(target_db_path)
    try:
        _require_table(source_conn, REQUIRED_SOURCE_TABLE, "source")
        _require_columns(source_conn, REQUIRED_SOURCE_TABLE, REQUIRED_SOURCE_COLUMNS, "source")
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")

        selected_signal_date = _resolve_signal_date(source_conn, signal_date)
        try:
            selected_signal_version = _resolve_signal_version(
                source_conn,
                signal_date=selected_signal_date,
                taxonomy_version_code=taxonomy_version_code,
                signal_version=signal_version,
            )
        except ValueError as exc:
            return _source_scope_failed_summary(
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                signal_date=selected_signal_date,
                signal_version=signal_version,
                error_code="SOURCE_SCOPE_UNAVAILABLE",
                error=str(exc),
            )
        rows = _resolve_source_rows(
            source_conn,
            signal_date=selected_signal_date,
            signal_version=selected_signal_version,
            taxonomy_version_code=taxonomy_version_code,
        )
        source_validation = _source_validation_summary(
            rows,
            requested_taxonomy_version=taxonomy_version_code,
        )
        if (
            not source_validation["source_taxonomy_match"]
            or int(source_validation["duplicate_source_ticker_count"]) > 0
            or int(source_validation["unexpected_taxonomy_version_count"]) > 0
        ):
            return {
                "status": "FAILED",
                "loader_status": "FAILED",
                "loader_error_code": "SOURCE_SCOPE_INVALID",
                "loader_error": "Source rows failed taxonomy scope validation",
                "ticker_loader_error": "Source rows failed taxonomy scope validation",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "signal_version": selected_signal_version,
                "source_table": REQUIRED_SOURCE_TABLE,
                **source_validation,
                "loaded_row_count": 0,
                "failed_row_count": int(source_validation["source_row_count"]),
                "mapped_row_count": 0,
                "unresolved_membership_count": 0,
                "unresolved_tickers": [],
                "missing_ticker_entities": [],
                "missing_primary_memberships": [],
                "multiple_primary_memberships": [],
                "duplicate_target_key_count": 0,
                "duplicate_target_keys": [],
                "null_target_key_count": 0,
                "source_run_ids": [],
                "created_signal_run_count": 0,
                "reused_signal_run_count": 0,
                "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                "warnings": [],
            }
        ecosystem_id, taxonomy_version_id = _resolve_target_context(
            target_conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
        )
        loader_timestamp_utc = _now_utc_iso()
        source_run_ids = sorted({str(row["run_id"]) for row in rows})

        warnings: list[str] = []
        missing_ticker_entities: list[str] = []
        missing_primary_memberships: list[str] = []
        multiple_primary_memberships: list[str] = []
        failed_row_count = 0

        with target_conn:
            _ensure_replace_policy(
                target_conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                signal_date=selected_signal_date,
                signal_version=selected_signal_version,
                replace_existing=replace_existing,
            )

            created_signal_run_count = 0
            reused_signal_run_count = 0
            seen_source_runs: set[str] = set()
            pending_rows: list[tuple[sqlite3.Row, int, int, int, str, str]] = []
            target_keys: list[tuple[int | None, int | None, str | None, int | None, str | None]] = []

            for row in rows:
                ticker = str(row["ticker"])
                entity_id = _resolve_ticker_entity_id(
                    target_conn,
                    ecosystem_id=ecosystem_id,
                    ticker=ticker,
                )
                if entity_id is None:
                    missing_ticker_entities.append(ticker)
                    failed_row_count += 1
                    continue

                membership_status, group_l1_id, group_l2_id, group_l1_code, group_l2_code = (
                    _resolve_primary_membership_context(
                        target_conn,
                        taxonomy_version_id=taxonomy_version_id,
                        ticker_entity_id=entity_id,
                    )
                )
                if membership_status == "missing":
                    missing_primary_memberships.append(ticker)
                    failed_row_count += 1
                    continue
                if membership_status == "multiple":
                    multiple_primary_memberships.append(ticker)
                    failed_row_count += 1
                    continue

                run_id = str(row["run_id"])
                if run_id not in seen_source_runs:
                    created = _ensure_signal_run(
                        target_conn,
                        run_id=run_id,
                        ecosystem_id=ecosystem_id,
                        taxonomy_version_id=taxonomy_version_id,
                        signal_date=selected_signal_date,
                        signal_version=selected_signal_version,
                        source_created_at_utc=(
                            str(row["created_at_utc"]) if row["created_at_utc"] is not None else None
                        ),
                        loader_timestamp_utc=loader_timestamp_utc,
                    )
                    if created:
                        created_signal_run_count += 1
                    else:
                        reused_signal_run_count += 1
                    seen_source_runs.add(run_id)

                pending_rows.append(
                    (row, entity_id, int(group_l1_id), int(group_l2_id), str(group_l1_code), str(group_l2_code))
                )
                target_keys.append(
                    (
                        ecosystem_id,
                        taxonomy_version_id,
                        str(row["signal_date"]) if row["signal_date"] is not None else None,
                        entity_id,
                        str(row["signal_version"]) if row["signal_version"] is not None else None,
                    )
                )

            target_key_validation = _target_key_validation_summary(target_keys)
            unresolved_tickers = sorted(
                set(missing_ticker_entities)
                | set(missing_primary_memberships)
                | set(multiple_primary_memberships)
            )
            if failed_row_count > 0:
                target_conn.rollback()
                return {
                    "status": "FAILED",
                    "loader_status": "FAILED",
                    "loader_error_code": "TARGET_MAPPING_UNRESOLVED",
                    "loader_error": "Ticker rows could not be resolved to one V2 primary EC membership",
                    "ticker_loader_error": "Ticker rows could not be resolved to one V2 primary EC membership",
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": selected_signal_date,
                    "signal_version": selected_signal_version,
                    "source_table": REQUIRED_SOURCE_TABLE,
                    **source_validation,
                    "loaded_row_count": 0,
                    "failed_row_count": failed_row_count,
                    "mapped_row_count": len(pending_rows),
                    "unresolved_membership_count": len(unresolved_tickers),
                    "unresolved_tickers": unresolved_tickers,
                    **target_key_validation,
                    "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                    "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                    "missing_ticker_entities": sorted(missing_ticker_entities),
                    "missing_primary_memberships": sorted(missing_primary_memberships),
                    "multiple_primary_memberships": sorted(multiple_primary_memberships),
                    "source_run_ids": source_run_ids,
                    "created_signal_run_count": 0,
                    "reused_signal_run_count": 0,
                    "warnings": warnings,
                }
            if (
                int(target_key_validation["duplicate_target_key_count"]) > 0
                or int(target_key_validation["null_target_key_count"]) > 0
            ):
                target_conn.rollback()
                return {
                    "status": "FAILED",
                    "loader_status": "FAILED",
                    "loader_error_code": "TARGET_KEY_INVALID",
                    "loader_error": "Ticker rows produced duplicate or null EC target keys",
                    "ticker_loader_error": "Ticker rows produced duplicate or null EC target keys",
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": selected_signal_date,
                    "signal_version": selected_signal_version,
                    "source_table": REQUIRED_SOURCE_TABLE,
                    **source_validation,
                    "loaded_row_count": 0,
                    "failed_row_count": len(rows),
                    "mapped_row_count": len(pending_rows),
                    "unresolved_membership_count": 0,
                    "unresolved_tickers": [],
                    **target_key_validation,
                    "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                    "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                    "missing_ticker_entities": [],
                    "missing_primary_memberships": [],
                    "multiple_primary_memberships": [],
                    "source_run_ids": source_run_ids,
                    "created_signal_run_count": 0,
                    "reused_signal_run_count": 0,
                    "warnings": warnings,
                }

            for row, entity_id, group_l1_id, group_l2_id, group_l1_code, group_l2_code in pending_rows:
                _insert_target_row(
                    target_conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    loader_timestamp_utc=loader_timestamp_utc,
                    entity_id=entity_id,
                    primary_group_l1_entity_id=group_l1_id,
                    primary_group_l2_entity_id=group_l2_id,
                    primary_group_l1_code=group_l1_code,
                    primary_group_l2_code=group_l2_code,
                    row=row,
                )

        unmapped_source_columns = list(EXPECTED_UNMAPPED_SOURCE_COLUMNS)
        unmapped_target_columns = list(EXPECTED_UNMAPPED_TARGET_COLUMNS)
        if unmapped_source_columns:
            warnings.append(
                "Source columns not loaded into ec_ticker_signal_daily: "
                + ", ".join(unmapped_source_columns)
            )
        if unmapped_target_columns:
            warnings.append(
                "Target columns left NULL because current dc source has no values: "
                + ", ".join(unmapped_target_columns)
            )

        status = "OK_WITH_WARNINGS" if (unmapped_source_columns or unmapped_target_columns) else "OK"
        return {
            "status": status,
            "loader_status": status,
            "loader_error_code": "NONE",
            "loader_error": None,
            "ticker_loader_error": None,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "signal_date": selected_signal_date,
            "signal_version": selected_signal_version,
            "source_table": REQUIRED_SOURCE_TABLE,
            **source_validation,
            "loaded_row_count": len(rows),
            "failed_row_count": 0,
            "mapped_row_count": len(rows),
            "unresolved_membership_count": 0,
            "unresolved_tickers": [],
            "duplicate_target_key_count": 0,
            "duplicate_target_keys": [],
            "null_target_key_count": 0,
            "unmapped_source_columns": unmapped_source_columns,
            "unmapped_target_columns": unmapped_target_columns,
            "missing_ticker_entities": [],
            "missing_primary_memberships": [],
            "multiple_primary_memberships": [],
            "source_run_ids": source_run_ids,
            "created_signal_run_count": created_signal_run_count,
            "reused_signal_run_count": reused_signal_run_count,
            "warnings": warnings,
        }
    finally:
        source_conn.close()
        target_conn.close()
