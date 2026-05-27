from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from analysis.datacenter_indices.swing_ma_break_status import (
    build_swing_ma_break_status_rows,
)

SOURCE_TABLE = "dc_ticker_swing_signal_daily"
DESTINATION_TABLE = "dc_dashboard_ticker_enrichment_daily"
CALC_VERSION = "DATACENTER_DASHBOARD_TICKER_ENRICHMENT_V1"
SOURCE_COMPONENTS = "dc_ticker_swing_signal_daily,dc_ticker_swing_signal_daily:daily_status_mapping_v1"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$")
DISALLOWED_TICKER_LABELS = {
    "LAYER",
    "SUBINDUSTRY",
    "ECOSYSTEM",
    "HEADER",
    "WATCHLIST",
    "MARKET",
    "ACTION",
    "SUMMARY",
    "DECISION",
    "TRACE",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write Datacenter ticker enrichment rows into analysis.db."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("insert-missing", "upsert", "replace-date"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--watchlist-file")
    parser.add_argument("--high-exit-window-rows", type=int, default=30)
    return parser


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_run_id(signal_date: str, explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    return f"DC_DASH_TICKER_ENRICH_{signal_date}_{_utc_now_text()}"


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(f"file:{normalized}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_read_write(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(normalized)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _normalize_signal_date(value: str) -> str:
    normalized = value.strip()
    if not DATE_RE.match(normalized):
        raise ValueError(f"invalid signal_date format: {normalized}")
    return normalized


def _normalize_taxonomy_version(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("taxonomy_version must be non-empty")
    return normalized


def _load_watchlist_tickers(watchlist_file: str | None) -> tuple[set[str], list[str]]:
    if watchlist_file is None:
        return set(), []
    normalized = watchlist_file.strip()
    if not normalized:
        raise ValueError("--watchlist-file must be non-empty when provided")
    path = Path(normalized)
    if not path.exists():
        raise FileNotFoundError(f"watchlist_file not found: {normalized}")
    tickers: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            tickers.add(line.upper())
    warnings: list[str] = []
    if not tickers:
        warnings.append("WATCHLIST_FILE_EMPTY")
    return tickers, warnings


def _is_pseudo_ticker(row: sqlite3.Row) -> bool:
    raw_ticker = row["ticker"]
    if raw_ticker is None:
        return True
    ticker = str(raw_ticker).strip().upper()
    if not ticker:
        return True
    if DATE_RE.match(ticker):
        return True
    if " " in ticker:
        return True
    if not VALID_TICKER_RE.match(ticker):
        return True
    if ticker in DISALLOWED_TICKER_LABELS:
        return True
    primary_layer = str(row["primary_layer"] or "").strip().upper()
    primary_subindustry = str(row["primary_subindustry"] or "").strip().upper()
    if ticker in {primary_layer, primary_subindustry}:
        return True
    return False


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> list[sqlite3.Row]:
    source_columns = _table_columns(conn, SOURCE_TABLE)
    select_fields: list[tuple[str, str]] = [
        ("signal_date", "signal_date"),
        ("taxonomy_version", "taxonomy_version"),
        ("ticker", "ticker"),
        ("primary_layer", "primary_layer"),
        ("primary_subindustry", "primary_subindustry"),
        ("close", "close"),
        ("return_5d", "return_5d"),
        ("return_10d", "return_10d"),
        ("return_20d", "return_20d"),
        ("return_60d", "return_60d"),
        ("distance_to_ema20_pct", "distance_to_ema20_pct"),
        ("price_data_status", "price_data_status"),
        ("ticker_trend_state", "ticker_trend_state"),
        ("latest_structure_label", "latest_structure_label"),
        ("latest_structure_age_trading_days", "latest_structure_age_trading_days"),
        ("latest_structure_freshness", "latest_structure_freshness"),
        ("latest_bos_event_type", "latest_bos_event_type"),
        ("latest_bos_age_trading_days", "latest_bos_age_trading_days"),
        ("latest_bos_freshness", "latest_bos_freshness"),
        ("latest_reset_reason", "latest_reset_reason"),
        ("latest_reset_age_trading_days", "latest_reset_age_trading_days"),
        ("latest_reset_freshness", "latest_reset_freshness"),
        ("bullish_candle_signal", "bullish_candle_signal"),
        ("bullish_divergence_signal", "bullish_divergence_signal"),
        ("hidden_bullish_divergence_signal", "hidden_bullish_divergence_signal"),
        ("in_datacenter_ecosystem", "in_datacenter_ecosystem"),
        ("exit_risk_signal", "exit_risk_signal"),
        ("exit_risk_severity", "exit_risk_severity"),
        ("exit_reason", "exit_reason"),
        ("high_exit_risk_days_count", "high_exit_risk_days_count"),
        ("breakout_signal", "breakout_signal"),
        ("pullback_signal", "pullback_signal"),
        ("ma_break_status", "ma_break_status"),
    ]
    select_sql = ",\n                ".join(
        f"{column} AS {alias}" if column in source_columns else f"NULL AS {alias}"
        for column, alias in select_fields
    )
    return list(
        conn.execute(
            f"""
            SELECT
                {select_sql}
            FROM {SOURCE_TABLE}
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY ticker ASC
            """,
            (signal_date, taxonomy_version),
        ).fetchall()
    )


def _load_source_history_by_ticker(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    tickers: list[str],
    window_rows: int,
) -> dict[str, list[sqlite3.Row]]:
    if not tickers:
        return {}
    source_columns = _table_columns(conn, SOURCE_TABLE)
    placeholders = ", ".join("?" for _ in tickers)
    select_fields: list[tuple[str, str]] = [
        ("signal_date", "signal_date"),
        ("taxonomy_version", "taxonomy_version"),
        ("ticker", "ticker"),
        ("close", "close"),
        ("ema20", "ema20"),
        ("exit_risk_signal", "exit_risk_signal"),
        ("exit_risk_severity", "exit_risk_severity"),
    ]
    select_sql = ",\n                ".join(
        f"{column} AS {alias}" if column in source_columns else f"NULL AS {alias}"
        for column, alias in select_fields
    )
    rows = conn.execute(
        f"""
        SELECT
                {select_sql}
        FROM {SOURCE_TABLE}
        WHERE taxonomy_version = ?
          AND signal_date <= ?
          AND ticker IN ({placeholders})
        ORDER BY ticker ASC, signal_date DESC
        """,
        (taxonomy_version, signal_date, *tickers),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        ticker = str(row["ticker"] or "").strip().upper()
        if not ticker:
            continue
        history = grouped.setdefault(ticker, [])
        if len(history) >= window_rows:
            continue
        history.append(row)
    return {ticker: list(reversed(history)) for ticker, history in grouped.items()}


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_truthy_signal(value: object) -> bool:
    text = _normalized_text(value)
    if text is None:
        return False
    return text not in {"0", "0.0", "FALSE", "false", "NO", "N"}


def _derive_daily_status(row: sqlite3.Row) -> str:
    ecosystem_membership = _normalized_text(row["in_datacenter_ecosystem"])
    if ecosystem_membership is not None and ecosystem_membership.upper() == "NO":
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"

    price_data_status = (_normalized_text(row["price_data_status"]) or "").upper()
    if price_data_status in {"MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}:
        return "MISSING_PRICE"

    exit_risk_severity = (_normalized_text(row["exit_risk_severity"]) or "").upper()
    exit_risk_signal = _is_truthy_signal(row["exit_risk_signal"])
    if exit_risk_severity == "HIGH" or (exit_risk_signal and exit_risk_severity == "HIGH"):
        return "HIGH_EXIT_RISK"
    if exit_risk_severity == "MEDIUM" or (exit_risk_signal and exit_risk_severity == "MEDIUM"):
        return "MEDIUM_EXIT_RISK"

    if _is_truthy_signal(row["breakout_signal"]):
        return "BREAKOUT_CANDIDATE"
    if _is_truthy_signal(row["pullback_signal"]):
        return "PULLBACK_CANDIDATE"
    return "NEUTRAL_MONITOR"


def _derive_primary_reason(row: sqlite3.Row, daily_status: str) -> str | None:
    exit_reason = _normalized_text(row["exit_reason"])
    if daily_status in {"HIGH_EXIT_RISK", "MEDIUM_EXIT_RISK"}:
        return exit_reason
    if _is_truthy_signal(row["breakout_signal"]):
        return exit_reason or "BREAKOUT_SIGNAL"
    if _is_truthy_signal(row["pullback_signal"]):
        return exit_reason or "PULLBACK_SIGNAL"
    return exit_reason


def _derive_freshness_status(row: sqlite3.Row) -> str | None:
    latest_bos_event_type = _normalized_text(row["latest_bos_event_type"])
    latest_bos_freshness = _normalized_text(row["latest_bos_freshness"])
    latest_reset_reason = _normalized_text(row["latest_reset_reason"])
    latest_reset_freshness = _normalized_text(row["latest_reset_freshness"])
    latest_structure_freshness = _normalized_text(row["latest_structure_freshness"])
    if latest_bos_event_type == "BOS_DOWN" and latest_bos_freshness is not None:
        return latest_bos_freshness
    if latest_reset_reason is not None and latest_reset_freshness is not None:
        return latest_reset_freshness
    return latest_structure_freshness


def _derive_rolling_2d_status(row: sqlite3.Row) -> str:
    exit_risk_severity = (_normalized_text(row["exit_risk_severity"]) or "").upper()
    exit_risk_signal = _is_truthy_signal(row["exit_risk_signal"])
    latest_bos_event_type = (_normalized_text(row["latest_bos_event_type"]) or "").upper()
    latest_reset_reason = (_normalized_text(row["latest_reset_reason"]) or "").upper()

    if exit_risk_severity == "HIGH" and (
        latest_bos_event_type == "BOS_DOWN" or "DOUBLE_BOS_DOWN" in latest_reset_reason
    ):
        return "EMERGENCY_SELL_PRESSURE"
    if exit_risk_severity in {"HIGH", "MEDIUM"} or exit_risk_signal:
        return "WATCH_PRESSURE"
    return "NO_EMERGENCY"


def _return_10d_is_below_minus_8pct(value: object) -> bool:
    text = _normalized_text(value)
    if text is None:
        return False
    try:
        numeric = float(text)
    except ValueError:
        return False
    if abs(numeric) <= 1:
        return numeric <= -0.08
    return numeric <= -8


def _derive_window_status_2d(row: sqlite3.Row) -> str | None:
    tokens: list[str] = []
    if _return_10d_is_below_minus_8pct(row["return_10d"]):
        tokens.append("return_10d_lt_minus_8pct")
    distance_to_ema20_pct = row["distance_to_ema20_pct"]
    try:
        below_ema20 = distance_to_ema20_pct is not None and float(distance_to_ema20_pct) < 0
    except (TypeError, ValueError):
        below_ema20 = False
    if below_ema20:
        tokens.append("close_below_ema20")
    if not tokens:
        return None
    return "|".join(tokens)


def _derive_high_exit_risk_days_count_same_day(row: sqlite3.Row) -> int:
    explicit_value = _normalized_text(row["high_exit_risk_days_count"])
    if explicit_value is not None:
        try:
            return int(float(explicit_value))
        except ValueError:
            pass
    exit_risk_severity = (_normalized_text(row["exit_risk_severity"]) or "").upper()
    return 1 if exit_risk_severity == "HIGH" else 0


def _derive_window_high_exit_risk_days_count(
    history_rows: list[sqlite3.Row],
) -> int:
    count = 0
    for row in history_rows:
        exit_risk_signal = _is_truthy_signal(row["exit_risk_signal"])
        exit_risk_severity = (_normalized_text(row["exit_risk_severity"]) or "").upper()
        if exit_risk_signal or exit_risk_severity in {"HIGH", "MEDIUM"}:
            count += 1
    return count


def _resolve_high_exit_risk_days_count(
    row: sqlite3.Row,
    history_rows: list[sqlite3.Row] | None,
) -> tuple[int, bool, bool]:
    explicit_value = _normalized_text(row["high_exit_risk_days_count"])
    if explicit_value is not None:
        try:
            return int(float(explicit_value)), False, False
        except ValueError:
            pass
    if history_rows:
        return _derive_window_high_exit_risk_days_count(history_rows), True, False
    return _derive_high_exit_risk_days_count_same_day(row), False, True


def _resolve_ma_break_status(
    row: sqlite3.Row,
    history_rows: list[sqlite3.Row] | None,
) -> str | None:
    explicit_value = _normalized_text(row["ma_break_status"])
    if explicit_value is not None:
        return explicit_value
    if not history_rows:
        return None
    derived_rows = build_swing_ma_break_status_rows(
        latest_rows=[
            {
                "ticker": row["ticker"],
                "signal_date": row["signal_date"],
                "close": row["close"],
            }
        ],
        history_rows=[
            {key: history_row[key] for key in history_row.keys()}
            for history_row in history_rows
        ],
        as_of_date=str(row["signal_date"]),
    )
    if not derived_rows:
        return None
    derived_value = _normalized_text(derived_rows[0].get("ma_break_status"))
    if derived_value == "INSUFFICIENT_DATA":
        return None
    return derived_value


def _map_destination_row(
    row: sqlite3.Row,
    *,
    run_id: str,
    created_at_utc: str,
    watchlist_tickers: set[str],
    high_exit_risk_days_count: int,
    ma_break_status: str | None,
) -> tuple[object, ...]:
    ticker = str(row["ticker"]).strip().upper()
    daily_status = _derive_daily_status(row)
    primary_reason = _derive_primary_reason(row, daily_status)
    freshness_status = _derive_freshness_status(row)
    rolling_2d_status = _derive_rolling_2d_status(row)
    window_status_2d = _derive_window_status_2d(row)
    values = [
        row["signal_date"],  # signal_date
        row["taxonomy_version"],  # taxonomy_version
        ticker,  # ticker
        row["primary_layer"],  # primary_layer
        row["primary_subindustry"],  # primary_subindustry
        row["close"],  # close
        row["return_5d"],  # return_5d
        row["return_10d"],  # return_10d
        row["return_20d"],  # return_20d
        row["return_60d"],  # return_60d
        None,  # action
        None,  # severity
        primary_reason,  # primary_reason
        daily_status,  # current_status
        None,  # start_status_30d
        None,  # status_change_30d
        None,  # status_change_5d
        None,  # window_status_30d
        None,  # window_status_5d
        window_status_2d,  # window_status_2d
        ma_break_status,  # ma_break_status
        freshness_status,  # freshness_status
        row["ticker_trend_state"],  # trend_state
        None,  # trend_state_age_td
        row["latest_structure_label"],  # latest_structure_label
        row["latest_structure_age_trading_days"],  # latest_structure_age_td
        row["latest_bos_event_type"],  # latest_bos_event_type
        row["latest_bos_age_trading_days"],  # latest_bos_age_td
        row["latest_reset_reason"],  # latest_reset_reason
        row["latest_reset_age_trading_days"],  # latest_reset_age_td
        None,  # latest_candle
        None,  # latest_candle_age_td
        None,  # latest_divergence
        None,  # latest_divergence_age_td
        None,  # latest_chart_pattern
        None,  # latest_chart_pattern_age_td
        None,  # pullback_validity
        None,  # entry_readiness
        None,  # candidate_priority
        None,  # candidate_priority_label
        daily_status,  # daily_status
        rolling_2d_status,  # rolling_2d_status
        None,  # rolling_5d_status
        None,  # rolling_30d_status
        None,  # horizons_present
        high_exit_risk_days_count,  # high_exit_risk_days_count
        None,  # source_run_ids
        SOURCE_COMPONENTS,  # source_components
        1 if ticker in watchlist_tickers else 0,  # is_watchlist
        row["price_data_status"],  # data_quality_status
        CALC_VERSION,  # calc_version
        run_id,  # run_id
        created_at_utc,  # created_at_utc
    ]
    assert len(values) == 53
    return tuple(values)


def _existing_keys(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        f"""
        SELECT signal_date, taxonomy_version, ticker
        FROM {DESTINATION_TABLE}
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version),
    ).fetchall()
    return {
        (str(row["signal_date"]), str(row["taxonomy_version"]), str(row["ticker"])) for row in rows
    }


def _emit_summary(name: str, value: object) -> None:
    print(f"SUMMARY datacenter_dashboard_ticker_enrichment_write.{name}={value}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        signal_date = _normalize_signal_date(args.signal_date)
        taxonomy_version = _normalize_taxonomy_version(args.taxonomy_version)
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")
        if args.high_exit_window_rows <= 0:
            raise ValueError("--high-exit-window-rows must be greater than 0")
        watchlist_tickers, warnings = _load_watchlist_tickers(args.watchlist_file)

        connector = _connect_read_only if args.dry_run else _connect_read_write
        with connector(args.analysis_db) as conn:
            if not _table_exists(conn, SOURCE_TABLE):
                raise ValueError(f"missing required source table: {SOURCE_TABLE}")
            if not _table_exists(conn, DESTINATION_TABLE):
                raise ValueError(f"missing required destination table: {DESTINATION_TABLE}")

            source_rows = _load_source_rows(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
            valid_rows_all = [row for row in source_rows if not _is_pseudo_ticker(row)]
            excluded_pseudo_rows = len(source_rows) - len(valid_rows_all)
            valid_rows = (
                valid_rows_all[: args.limit] if args.limit is not None else valid_rows_all
            )
            history_by_ticker = _load_source_history_by_ticker(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                tickers=[str(row["ticker"]).strip().upper() for row in valid_rows],
                window_rows=args.high_exit_window_rows,
            )
            ma_history_by_ticker = _load_source_history_by_ticker(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                tickers=[str(row["ticker"]).strip().upper() for row in valid_rows],
                window_rows=60,
            )
            watchlist_matches = sum(
                1
                for row in valid_rows
                if str(row["ticker"]).strip().upper() in watchlist_tickers
            )

            run_id = _resolve_run_id(signal_date, args.run_id)
            created_at_utc = _utc_now_text()
            high_exit_window_derived_rows = 0
            high_exit_window_unavailable = 0
            mapped_rows: list[tuple[tuple[str, str, str], tuple[object, ...]]] = []
            for row in valid_rows:
                ticker = str(row["ticker"]).strip().upper()
                high_exit_risk_days_count, used_window, used_fallback = _resolve_high_exit_risk_days_count(
                    row,
                    history_by_ticker.get(ticker),
                )
                ma_break_status = _resolve_ma_break_status(
                    row,
                    ma_history_by_ticker.get(ticker),
                )
                if used_window:
                    high_exit_window_derived_rows += 1
                if used_fallback:
                    high_exit_window_unavailable += 1
                mapped_rows.append(
                    (
                        (
                            str(row["signal_date"]),
                            str(row["taxonomy_version"]),
                            ticker,
                        ),
                        _map_destination_row(
                            row,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                            watchlist_tickers=watchlist_tickers,
                            high_exit_risk_days_count=high_exit_risk_days_count,
                            ma_break_status=ma_break_status,
                        ),
                    )
                )
            if high_exit_window_unavailable > 0:
                warnings.append("HIGH_EXIT_WINDOW_ROWS_UNAVAILABLE")

            existing_keys = _existing_keys(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
            selected_keys = {
                (
                    str(row["signal_date"]),
                    str(row["taxonomy_version"]),
                    str(row["ticker"]).strip().upper(),
                )
                for row in valid_rows
            }

            inserted_rows = 0
            updated_rows = 0
            deleted_existing_rows = 0
            skipped_existing_rows = 0

            if args.mode == "insert-missing":
                inserted_rows = sum(1 for key in selected_keys if key not in existing_keys)
                skipped_existing_rows = sum(1 for key in selected_keys if key in existing_keys)
                rows_to_write = [
                    row
                    for row in valid_rows
                    if (
                        str(row["signal_date"]),
                        str(row["taxonomy_version"]),
                        str(row["ticker"]).strip().upper(),
                    )
                    not in existing_keys
                ]
                if not args.dry_run and rows_to_write:
                    conn.executemany(
                        f"""
                        INSERT INTO {DESTINATION_TABLE} (
                            signal_date,
                            taxonomy_version,
                            ticker,
                            primary_layer,
                            primary_subindustry,
                            close,
                            return_5d,
                            return_10d,
                            return_20d,
                            return_60d,
                            action,
                            severity,
                            primary_reason,
                            current_status,
                            start_status_30d,
                            status_change_30d,
                            status_change_5d,
                            window_status_30d,
                            window_status_5d,
                            window_status_2d,
                            ma_break_status,
                            freshness_status,
                            trend_state,
                            trend_state_age_td,
                            latest_structure_label,
                            latest_structure_age_td,
                            latest_bos_event_type,
                            latest_bos_age_td,
                            latest_reset_reason,
                            latest_reset_age_td,
                            latest_candle,
                            latest_candle_age_td,
                            latest_divergence,
                            latest_divergence_age_td,
                            latest_chart_pattern,
                            latest_chart_pattern_age_td,
                            pullback_validity,
                            entry_readiness,
                            candidate_priority,
                            candidate_priority_label,
                            daily_status,
                            rolling_2d_status,
                            rolling_5d_status,
                            rolling_30d_status,
                            horizons_present,
                            high_exit_risk_days_count,
                            source_run_ids,
                            source_components,
                            is_watchlist,
                            data_quality_status,
                            calc_version,
                            run_id,
                            created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            mapped_tuple
                            for source_key, mapped_tuple in mapped_rows
                            if source_key not in existing_keys
                        ],
                    )
            elif args.mode == "upsert":
                inserted_rows = sum(1 for key in selected_keys if key not in existing_keys)
                updated_rows = sum(1 for key in selected_keys if key in existing_keys)
                if not args.dry_run and valid_rows:
                    conn.executemany(
                        f"""
                        INSERT INTO {DESTINATION_TABLE} (
                            signal_date,
                            taxonomy_version,
                            ticker,
                            primary_layer,
                            primary_subindustry,
                            close,
                            return_5d,
                            return_10d,
                            return_20d,
                            return_60d,
                            action,
                            severity,
                            primary_reason,
                            current_status,
                            start_status_30d,
                            status_change_30d,
                            status_change_5d,
                            window_status_30d,
                            window_status_5d,
                            window_status_2d,
                            ma_break_status,
                            freshness_status,
                            trend_state,
                            trend_state_age_td,
                            latest_structure_label,
                            latest_structure_age_td,
                            latest_bos_event_type,
                            latest_bos_age_td,
                            latest_reset_reason,
                            latest_reset_age_td,
                            latest_candle,
                            latest_candle_age_td,
                            latest_divergence,
                            latest_divergence_age_td,
                            latest_chart_pattern,
                            latest_chart_pattern_age_td,
                            pullback_validity,
                            entry_readiness,
                            candidate_priority,
                            candidate_priority_label,
                            daily_status,
                            rolling_2d_status,
                            rolling_5d_status,
                            rolling_30d_status,
                            horizons_present,
                            high_exit_risk_days_count,
                            source_run_ids,
                            source_components,
                            is_watchlist,
                            data_quality_status,
                            calc_version,
                            run_id,
                            created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(signal_date, taxonomy_version, ticker) DO UPDATE SET
                            primary_layer=excluded.primary_layer,
                            primary_subindustry=excluded.primary_subindustry,
                            close=excluded.close,
                            return_5d=excluded.return_5d,
                            return_10d=excluded.return_10d,
                            return_20d=excluded.return_20d,
                            return_60d=excluded.return_60d,
                            action=excluded.action,
                            severity=excluded.severity,
                            primary_reason=excluded.primary_reason,
                            current_status=excluded.current_status,
                            start_status_30d=excluded.start_status_30d,
                            status_change_30d=excluded.status_change_30d,
                            status_change_5d=excluded.status_change_5d,
                            window_status_30d=excluded.window_status_30d,
                            window_status_5d=excluded.window_status_5d,
                            window_status_2d=excluded.window_status_2d,
                            ma_break_status=excluded.ma_break_status,
                            freshness_status=excluded.freshness_status,
                            trend_state=excluded.trend_state,
                            trend_state_age_td=excluded.trend_state_age_td,
                            latest_structure_label=excluded.latest_structure_label,
                            latest_structure_age_td=excluded.latest_structure_age_td,
                            latest_bos_event_type=excluded.latest_bos_event_type,
                            latest_bos_age_td=excluded.latest_bos_age_td,
                            latest_reset_reason=excluded.latest_reset_reason,
                            latest_reset_age_td=excluded.latest_reset_age_td,
                            latest_candle=excluded.latest_candle,
                            latest_candle_age_td=excluded.latest_candle_age_td,
                            latest_divergence=excluded.latest_divergence,
                            latest_divergence_age_td=excluded.latest_divergence_age_td,
                            latest_chart_pattern=excluded.latest_chart_pattern,
                            latest_chart_pattern_age_td=excluded.latest_chart_pattern_age_td,
                            pullback_validity=excluded.pullback_validity,
                            entry_readiness=excluded.entry_readiness,
                            candidate_priority=excluded.candidate_priority,
                            candidate_priority_label=excluded.candidate_priority_label,
                            daily_status=excluded.daily_status,
                            rolling_2d_status=excluded.rolling_2d_status,
                            rolling_5d_status=excluded.rolling_5d_status,
                            rolling_30d_status=excluded.rolling_30d_status,
                            horizons_present=excluded.horizons_present,
                            high_exit_risk_days_count=excluded.high_exit_risk_days_count,
                            source_run_ids=excluded.source_run_ids,
                            source_components=excluded.source_components,
                            is_watchlist=excluded.is_watchlist,
                            data_quality_status=excluded.data_quality_status,
                            calc_version=excluded.calc_version,
                            run_id=excluded.run_id,
                            created_at_utc=excluded.created_at_utc
                        """,
                        [mapped_tuple for _source_key, mapped_tuple in mapped_rows],
                    )
            else:
                deleted_existing_rows = len(existing_keys)
                inserted_rows = len(valid_rows)
                if not args.dry_run:
                    conn.execute(
                        f"""
                        DELETE FROM {DESTINATION_TABLE}
                        WHERE signal_date = ? AND taxonomy_version = ?
                        """,
                        (signal_date, taxonomy_version),
                    )
                    if valid_rows:
                        conn.executemany(
                            f"""
                            INSERT INTO {DESTINATION_TABLE} (
                                signal_date,
                                taxonomy_version,
                                ticker,
                                primary_layer,
                                primary_subindustry,
                                close,
                                return_5d,
                                return_10d,
                                return_20d,
                                return_60d,
                                action,
                                severity,
                                primary_reason,
                                current_status,
                                start_status_30d,
                                status_change_30d,
                                status_change_5d,
                                window_status_30d,
                                window_status_5d,
                                window_status_2d,
                                ma_break_status,
                                freshness_status,
                                trend_state,
                                trend_state_age_td,
                                latest_structure_label,
                                latest_structure_age_td,
                                latest_bos_event_type,
                                latest_bos_age_td,
                                latest_reset_reason,
                                latest_reset_age_td,
                                latest_candle,
                                latest_candle_age_td,
                                latest_divergence,
                                latest_divergence_age_td,
                                latest_chart_pattern,
                                latest_chart_pattern_age_td,
                                pullback_validity,
                                entry_readiness,
                                candidate_priority,
                                candidate_priority_label,
                                daily_status,
                                rolling_2d_status,
                                rolling_5d_status,
                                rolling_30d_status,
                                horizons_present,
                                high_exit_risk_days_count,
                                source_run_ids,
                                source_components,
                                is_watchlist,
                                data_quality_status,
                                calc_version,
                                run_id,
                                created_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [mapped_tuple for _source_key, mapped_tuple in mapped_rows],
                        )

            if not args.dry_run:
                conn.commit()

        _emit_summary("status", "OK")
        _emit_summary("analysis_db", args.analysis_db)
        _emit_summary("signal_date", signal_date)
        _emit_summary("taxonomy_version", taxonomy_version)
        _emit_summary("mode", args.mode)
        _emit_summary("dry_run", 1 if args.dry_run else 0)
        _emit_summary("high_exit_window_rows", args.high_exit_window_rows)
        _emit_summary("high_exit_window_derived_rows", high_exit_window_derived_rows)
        _emit_summary("watchlist_file", args.watchlist_file or "")
        _emit_summary("watchlist_tickers", len(watchlist_tickers))
        _emit_summary("watchlist_matches", watchlist_matches)
        _emit_summary("source_rows", len(source_rows))
        _emit_summary("valid_ticker_rows", len(valid_rows))
        _emit_summary("excluded_pseudo_rows", excluded_pseudo_rows)
        _emit_summary("inserted_rows", inserted_rows)
        _emit_summary("updated_rows", updated_rows)
        _emit_summary("deleted_existing_rows", deleted_existing_rows)
        _emit_summary("skipped_existing_rows", skipped_existing_rows)
        _emit_summary("run_id", run_id)
        for warning in warnings:
            _emit_summary("warning", warning)
        return 0
    except (FileNotFoundError, sqlite3.Error, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
