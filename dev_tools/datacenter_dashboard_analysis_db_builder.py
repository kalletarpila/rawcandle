from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
    EcosystemDashboardWatchlistInput,
)
from dev_tools.run_datacenter_dashboard_html import _REPORT_DATE_RE

DEFAULT_TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
WINDOW_STATUS_WARNING = "WINDOW_STATUS_ENRICHMENT_NOT_DIRECT_FROM_ANALYSIS_DB"
WATCHLIST_WARNING = "WATCHLIST_SOURCE_NOT_AVAILABLE"
ACTION_SUMMARY_WARNING = "ACTION_SUMMARY_SOURCE_NOT_AVAILABLE"
DECISION_TRACE_WARNING = "DECISION_TRACE_SOURCE_NOT_AVAILABLE"
_DATE_LIKE_TICKER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VALID_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$")
_GROUP_PRIORITY = {"ecosystem": 0, "layer": 1, "subindustry": 2}
_REQUIRED_TABLES = (
    "dc_ticker_swing_signal_daily",
    "dc_group_swing_signal_daily",
)
_ENRICHMENT_REQUIRED_TABLES = (
    "dc_dashboard_ticker_enrichment_daily",
    "dc_dashboard_group_enrichment_daily",
    "dc_dashboard_action_summary_daily",
    "dc_dashboard_decision_trace_daily",
    "dc_dashboard_enrichment_run_daily",
)
_ENRICHMENT_TABLE_WARNING = "ENRICHMENT_TABLES_MISSING"
_ENRICHMENT_PARTIAL_WARNING = "ENRICHMENT_READINESS_PARTIAL"


@dataclass(frozen=True)
class DatacenterDashboardAnalysisDbBuildResult:
    dashboard_input: EcosystemDashboardInput
    warnings: tuple[str, ...]
    source_row_count: int


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    normalized_path = db_path.strip()
    if not normalized_path:
        raise FileNotFoundError("database path is required")
    if not Path(normalized_path).exists():
        raise FileNotFoundError(f"database not found: {normalized_path}")
    conn = sqlite3.connect(f"file:{normalized_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_report_date(report_date: str) -> str:
    normalized = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized):
        raise ValueError(f"invalid report_date format: {normalized}")
    return normalized


def _normalize_ecosystem_code(ecosystem_code: str) -> str:
    normalized = ecosystem_code.strip().upper()
    if normalized != "DATACENTER":
        raise ValueError(
            f"unsupported ecosystem_code={ecosystem_code}; currently supported: DATACENTER"
        )
    return normalized


def _normalize_taxonomy_version(taxonomy_version: str | None) -> str:
    normalized = (taxonomy_version or DEFAULT_TAXONOMY_VERSION).strip()
    if not normalized:
        raise ValueError("taxonomy_version must be non-empty")
    return normalized


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _require_tables(conn: sqlite3.Connection, table_names: tuple[str, ...]) -> None:
    missing = [table_name for table_name in table_names if not _table_exists(conn, table_name)]
    if missing:
        raise ValueError(f"missing required analysis tables: {', '.join(sorted(missing))}")


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _resolve_version(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    version_column: str,
    report_date: str,
    taxonomy_version: str,
) -> str | None:
    row = conn.execute(
        f"""
        SELECT {version_column}
        FROM {table_name}
        WHERE {date_column} = ? AND taxonomy_version = ?
        ORDER BY {version_column} DESC
        LIMIT 1
        """,
        (report_date, taxonomy_version),
    ).fetchone()
    if row is None or row[0] in {None, ""}:
        return None
    return str(row[0])


def _is_real_ticker(row: sqlite3.Row) -> bool:
    raw_value = row["ticker"]
    if raw_value is None:
        return False
    ticker = str(raw_value).strip().upper()
    if not ticker:
        return False
    if _DATE_LIKE_TICKER_RE.match(ticker):
        return False
    if not _VALID_TICKER_RE.match(ticker):
        return False
    primary_layer = str(row["primary_layer"] or "").strip().upper()
    primary_subindustry = str(row["primary_subindustry"] or "").strip().upper()
    if ticker in {primary_layer, primary_subindustry}:
        return False
    return True


def _load_ticker_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
    max_rows: int | None,
) -> tuple[list[EcosystemDashboardTickerStatusInput], dict[str, str], int]:
    signal_version = _resolve_version(
        conn,
        table_name="dc_ticker_swing_signal_daily",
        date_column="signal_date",
        version_column="signal_version",
        report_date=report_date,
        taxonomy_version=taxonomy_version,
    )
    if signal_version is None:
        return [], {}, 0

    rows = list(
        conn.execute(
            """
            SELECT
                ticker,
                primary_layer,
                primary_subindustry,
                close,
                return_5d,
                return_20d,
                return_60d,
                ticker_trend_state,
                latest_structure_label,
                latest_structure_age_trading_days,
                latest_bos_event_type,
                latest_bos_age_trading_days,
                latest_bos_freshness,
                latest_reset_reason,
                latest_reset_age_trading_days,
                latest_reset_freshness,
                bullish_candle_signal,
                bullish_divergence_signal,
                hidden_bullish_divergence_signal,
                price_data_status
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date = ? AND taxonomy_version = ? AND signal_version = ?
            ORDER BY ticker ASC
            """,
            (report_date, taxonomy_version, signal_version),
        ).fetchall()
    )
    raw_row_count = len(rows)
    ticker_rows: list[EcosystemDashboardTickerStatusInput] = []
    subindustry_to_layer: dict[str, str] = {}

    for row in rows:
        if not _is_real_ticker(row):
            continue
        layer_name = str(row["primary_layer"]).strip() if row["primary_layer"] else None
        subindustry_name = (
            str(row["primary_subindustry"]).strip() if row["primary_subindustry"] else None
        )
        if layer_name and subindustry_name and subindustry_name not in subindustry_to_layer:
            subindustry_to_layer[subindustry_name] = layer_name
        ticker_rows.append(
            EcosystemDashboardTickerStatusInput(
                ticker=str(row["ticker"]).strip().upper(),
                company_name=None,
                layer_name=layer_name,
                subindustry_name=subindustry_name,
                last_close=row["close"],
                return_5d=row["return_5d"],
                return_20d=row["return_20d"],
                return_60d=row["return_60d"],
                trend_state=row["ticker_trend_state"],
                latest_structure_label=row["latest_structure_label"],
                latest_bos_event_type=row["latest_bos_event_type"],
                latest_bos_freshness=row["latest_bos_freshness"],
                latest_reset_reason=row["latest_reset_reason"],
                latest_reset_freshness=row["latest_reset_freshness"],
                bullish_candle_signal=row["bullish_candle_signal"],
                bullish_divergence_signal=row["bullish_divergence_signal"],
                hidden_bullish_divergence_signal=row["hidden_bullish_divergence_signal"],
                pullback_validity=None,
                entry_readiness=None,
                candidate_priority=None,
                candidate_priority_label=None,
                action_bucket=None,
                action_label=None,
                data_status=row["price_data_status"],
            )
        )
        if max_rows is not None and len(ticker_rows) >= max_rows:
            break
    return ticker_rows, subindustry_to_layer, raw_row_count


def _load_group_aux_rows(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    version_column: str,
    report_date: str,
    taxonomy_version: str,
    fields: tuple[str, ...],
) -> tuple[dict[tuple[str, str], sqlite3.Row], int]:
    if not _table_exists(conn, table_name):
        return {}, 0
    version = _resolve_version(
        conn,
        table_name=table_name,
        date_column=date_column,
        version_column=version_column,
        report_date=report_date,
        taxonomy_version=taxonomy_version,
    )
    if version is None:
        return {}, 0
    rows = list(
        conn.execute(
            f"""
            SELECT group_type, group_name, {", ".join(fields)}
            FROM {table_name}
            WHERE {date_column} = ? AND taxonomy_version = ? AND {version_column} = ?
            ORDER BY group_type ASC, group_name ASC
            """,
            (report_date, taxonomy_version, version),
        ).fetchall()
    )
    return {(str(row["group_type"]), str(row["group_name"])): row for row in rows}, len(rows)


def _load_market_map_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
    subindustry_to_layer: dict[str, str],
    max_rows: int | None,
) -> tuple[list[EcosystemDashboardMarketMapInput], int]:
    signal_version = _resolve_version(
        conn,
        table_name="dc_group_swing_signal_daily",
        date_column="signal_date",
        version_column="signal_version",
        report_date=report_date,
        taxonomy_version=taxonomy_version,
    )
    if signal_version is None:
        return [], 0

    swing_rows = list(
        conn.execute(
            """
            SELECT
                group_type,
                group_name,
                member_count,
                return_5d,
                return_10d,
                return_20d,
                return_60d,
                pct_above_ma10,
                pct_above_ema20,
                ema20_breadth_delta_5d,
                overheat_risk_level,
                timing_state
            FROM dc_group_swing_signal_daily
            WHERE signal_date = ? AND taxonomy_version = ? AND signal_version = ?
            ORDER BY group_type ASC, group_name ASC
            """,
            (report_date, taxonomy_version, signal_version),
        ).fetchall()
    )
    synthetic_rows, synthetic_row_count = _load_group_aux_rows(
        conn,
        table_name="dc_group_synthetic_ohlc_daily",
        date_column="ohlc_date",
        version_column="calc_version",
        report_date=report_date,
        taxonomy_version=taxonomy_version,
        fields=(
            "latest_structure_label",
            "latest_structure_age_trading_days",
            "latest_bos_event_type",
            "latest_bos_age_trading_days",
            "latest_reset_reason",
            "latest_reset_age_trading_days",
            "trend_classification",
        ),
    )
    index_rows, index_row_count = _load_group_aux_rows(
        conn,
        table_name="dc_group_index_daily",
        date_column="index_date",
        version_column="calc_version",
        report_date=report_date,
        taxonomy_version=taxonomy_version,
        fields=("return_20d", "return_60d"),
    )

    sorted_layers = sorted(
        {str(row["group_name"]).strip() for row in swing_rows if row["group_type"] == "layer"}
    )
    layer_order_map = {layer_name: index + 1 for index, layer_name in enumerate(sorted_layers)}
    subindustry_order_map: dict[str, dict[str, int]] = {}
    for layer_name in sorted_layers:
        names = sorted(
            group_name
            for group_name, mapped_layer in subindustry_to_layer.items()
            if mapped_layer == layer_name
        )
        subindustry_order_map[layer_name] = {
            group_name: index + 1 for index, group_name in enumerate(names)
        }

    market_map_rows: list[EcosystemDashboardMarketMapInput] = []
    for row in swing_rows:
        group_type = str(row["group_type"]).strip()
        group_name = str(row["group_name"]).strip()
        key = (group_type, group_name)
        synthetic_row = synthetic_rows.get(key)
        index_row = index_rows.get(key)
        layer_name: str | None = None
        subindustry_name: str | None = None
        layer_order: int | None = None
        subindustry_order: int | None = None

        if group_type == "layer":
            layer_name = group_name
            layer_order = layer_order_map.get(group_name)
        elif group_type == "subindustry":
            subindustry_name = group_name
            layer_name = subindustry_to_layer.get(group_name)
            layer_order = layer_order_map.get(layer_name) if layer_name else None
            if layer_name:
                subindustry_order = subindustry_order_map.get(layer_name, {}).get(group_name)

        source_tables = ["dc_group_swing_signal_daily"]
        if synthetic_row is not None:
            source_tables.append("dc_group_synthetic_ohlc_daily")
        if index_row is not None:
            source_tables.append("dc_group_index_daily")

        market_map_rows.append(
            EcosystemDashboardMarketMapInput(
                layer_order=layer_order,
                subindustry_order=subindustry_order,
                layer_name=layer_name,
                subindustry_name=subindustry_name,
                ticker_count=row["member_count"],
                watchlist_count=None,
                avg_return_5d=row["return_5d"],
                avg_return_20d=(
                    row["return_20d"] if row["return_20d"] is not None else (
                        index_row["return_20d"] if index_row is not None else None
                    )
                ),
                avg_return_60d=(
                    row["return_60d"] if row["return_60d"] is not None else (
                        index_row["return_60d"] if index_row is not None else None
                    )
                ),
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=row["timing_state"],
                market_level=(
                    "ECOSYSTEM"
                    if group_type == "ecosystem"
                    else ("LAYER" if group_type == "layer" else "SUBINDUSTRY")
                ),
                name=(
                    "DC_ECOSYSTEM_TOTAL"
                    if group_type == "ecosystem"
                    else group_name
                ),
                parent_name=(
                    "DC_ECOSYSTEM_TOTAL"
                    if group_type == "layer"
                    else (layer_name if group_type == "subindustry" and layer_name else None)
                ),
                taxonomy_path=(
                    "DC_ECOSYSTEM_TOTAL"
                    if group_type == "ecosystem"
                    else (
                        f"DC_ECOSYSTEM_TOTAL > {group_name}"
                        if group_type == "layer"
                        else (
                            f"DC_ECOSYSTEM_TOTAL > {layer_name} > {group_name}"
                            if group_type == "subindustry" and layer_name
                            else None
                        )
                    )
                ),
            )
        )
        if max_rows is not None and len(market_map_rows) >= max_rows:
            break

    return market_map_rows, len(swing_rows) + synthetic_row_count + index_row_count


def _readiness_for_sections(
    *,
    source_reports: list[EcosystemDashboardSourceReportInput],
    market_map: list[EcosystemDashboardMarketMapInput],
    tickers: list[EcosystemDashboardTickerStatusInput],
) -> str:
    if not source_reports and not market_map and not tickers:
        return "FAILED"
    return "PARTIAL"


def _load_enrichment_ticker_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
    max_rows: int | None,
) -> tuple[
    list[EcosystemDashboardTickerStatusInput],
    list[EcosystemDashboardWatchlistInput],
    int,
]:
    rows = list(
        conn.execute(
            """
            SELECT
                ticker,
                primary_layer,
                primary_subindustry,
                close,
                return_5d,
                return_20d,
                return_60d,
                trend_state,
                latest_structure_label,
                latest_bos_event_type,
                latest_reset_reason,
                pullback_validity,
                entry_readiness,
                candidate_priority,
                candidate_priority_label,
                action,
                is_watchlist,
                data_quality_status
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY ticker ASC
            """,
            (report_date, taxonomy_version),
        ).fetchall()
    )
    selected_rows = rows[:max_rows] if max_rows is not None else rows
    tickers: list[EcosystemDashboardTickerStatusInput] = []
    watchlist: list[EcosystemDashboardWatchlistInput] = []
    for row in selected_rows:
        action_label = str(row["action"]).strip() if row["action"] not in {None, ""} else None
        ticker_row = EcosystemDashboardTickerStatusInput(
            ticker=str(row["ticker"]).strip(),
            company_name=None,
            layer_name=row["primary_layer"],
            subindustry_name=row["primary_subindustry"],
            last_close=row["close"],
            return_5d=row["return_5d"],
            return_20d=row["return_20d"],
            return_60d=row["return_60d"],
            trend_state=row["trend_state"],
            latest_structure_label=row["latest_structure_label"],
            latest_bos_event_type=row["latest_bos_event_type"],
            latest_bos_freshness=None,
            latest_reset_reason=row["latest_reset_reason"],
            latest_reset_freshness=None,
            bullish_candle_signal=None,
            bullish_divergence_signal=None,
            hidden_bullish_divergence_signal=None,
            pullback_validity=row["pullback_validity"],
            entry_readiness=row["entry_readiness"],
            candidate_priority=_optional_int(row["candidate_priority"]),
            candidate_priority_label=row["candidate_priority_label"],
            action_bucket=None,
            action_label=action_label,
            data_status=row["data_quality_status"],
        )
        tickers.append(ticker_row)
        if int(row["is_watchlist"] or 0) == 1:
            watchlist.append(
                EcosystemDashboardWatchlistInput(
                    ticker=ticker_row.ticker,
                    company_name=None,
                    layer_name=ticker_row.layer_name,
                    subindustry_name=ticker_row.subindustry_name,
                    action_bucket=None,
                    action_label=action_label,
                    watchlist_reason=None,
                    last_close=ticker_row.last_close,
                    return_5d=ticker_row.return_5d,
                    return_20d=ticker_row.return_20d,
                    return_60d=ticker_row.return_60d,
                    trend_state=ticker_row.trend_state,
                    latest_structure_label=ticker_row.latest_structure_label,
                    latest_bos_event_type=ticker_row.latest_bos_event_type,
                    latest_reset_reason=ticker_row.latest_reset_reason,
                    bullish_candle_signal=None,
                    bullish_divergence_signal=None,
                    hidden_bullish_divergence_signal=None,
                    data_status=ticker_row.data_status,
                )
            )
    return tickers, watchlist, len(selected_rows)


def _load_enrichment_market_map_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
    max_rows: int | None,
) -> tuple[list[EcosystemDashboardMarketMapInput], int]:
    rows = list(
        conn.execute(
            """
            SELECT
                market_level,
                name,
                parent_name,
                layer,
                subindustry,
                taxonomy_path,
                current_status,
                return_5d,
                return_20d,
                return_60d
            FROM dc_dashboard_group_enrichment_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY
                CASE market_level
                    WHEN 'ECOSYSTEM' THEN 0
                    WHEN 'LAYER' THEN 1
                    WHEN 'SUBINDUSTRY' THEN 2
                    ELSE 3
                END,
                name ASC
            """,
            (report_date, taxonomy_version),
        ).fetchall()
    )
    selected_rows = rows[:max_rows] if max_rows is not None else rows
    layer_names = sorted(
        {
            str(row["name"]).strip()
            for row in selected_rows
            if str(row["market_level"]).strip().upper() == "LAYER"
        }
    )
    layer_order_map = {layer_name: index + 1 for index, layer_name in enumerate(layer_names)}
    subindustry_order_map: dict[str, dict[str, int]] = {}
    for layer_name in layer_names:
        names = sorted(
            str(row["name"]).strip()
            for row in selected_rows
            if str(row["market_level"]).strip().upper() == "SUBINDUSTRY"
            and str(row["layer"] or "").strip() == layer_name
        )
        subindustry_order_map[layer_name] = {
            name: index + 1 for index, name in enumerate(names)
        }

    market_map: list[EcosystemDashboardMarketMapInput] = []
    for row in selected_rows:
        market_level = str(row["market_level"]).strip().upper()
        name = str(row["name"]).strip()
        layer_name = str(row["layer"] or "").strip() or None
        subindustry_name = str(row["subindustry"] or "").strip() or None
        layer_order: int | None = None
        subindustry_order: int | None = None
        if market_level == "LAYER":
            layer_name = name
            layer_order = layer_order_map.get(name)
        elif market_level == "SUBINDUSTRY":
            subindustry_name = name
            if layer_name:
                layer_order = layer_order_map.get(layer_name)
                subindustry_order = subindustry_order_map.get(layer_name, {}).get(name)
        taxonomy_path = str(row["taxonomy_path"] or "").strip() or None
        if taxonomy_path is None:
            if market_level == "ECOSYSTEM":
                taxonomy_path = "DC_ECOSYSTEM_TOTAL"
            elif market_level == "LAYER":
                taxonomy_path = f"DC_ECOSYSTEM_TOTAL > {name}"
            elif market_level == "SUBINDUSTRY" and layer_name:
                taxonomy_path = f"DC_ECOSYSTEM_TOTAL > {layer_name} > {name}"
        parent_name = str(row["parent_name"] or "").strip() or None
        if parent_name is None:
            if market_level == "LAYER":
                parent_name = "DC_ECOSYSTEM_TOTAL"
            elif market_level == "SUBINDUSTRY" and layer_name:
                parent_name = layer_name
        market_map.append(
            EcosystemDashboardMarketMapInput(
                layer_order=layer_order,
                subindustry_order=subindustry_order,
                layer_name=layer_name,
                subindustry_name=subindustry_name,
                ticker_count=None,
                watchlist_count=None,
                avg_return_5d=row["return_5d"],
                avg_return_20d=row["return_20d"],
                avg_return_60d=row["return_60d"],
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=row["current_status"],
                market_level=market_level,
                name=name,
                parent_name=parent_name,
                taxonomy_path=taxonomy_path,
            )
        )
    return market_map, len(selected_rows)


def _load_enrichment_action_summary_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
) -> tuple[list[EcosystemDashboardActionSummaryInput], int]:
    rows = list(
        conn.execute(
            """
            SELECT action, count
            FROM dc_dashboard_action_summary_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY action ASC
            """,
            (report_date, taxonomy_version),
        ).fetchall()
    )
    return (
        [
            EcosystemDashboardActionSummaryInput(
                action_bucket=None,
                action_label=str(row["action"]).strip(),
                ticker_count=row["count"],
                weight_sum=None,
                notes=None,
            )
            for row in rows
        ],
        len(rows),
    )


def _load_enrichment_decision_trace_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
    max_rows: int | None,
) -> tuple[list[EcosystemDashboardDecisionTraceInput], int]:
    rows = list(
        conn.execute(
            """
            SELECT ticker, trace_index, matched_rule, matched_value, horizon, action, field
            FROM dc_dashboard_decision_trace_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY ticker ASC, trace_index ASC
            """,
            (report_date, taxonomy_version),
        ).fetchall()
    )
    selected_rows = rows[:max_rows] if max_rows is not None else rows
    return (
        [
            EcosystemDashboardDecisionTraceInput(
                ticker=str(row["ticker"]).strip(),
                trace_order=int(row["trace_index"]),
                rule_group=row["horizon"],
                rule_name=row["matched_rule"],
                input_value=row["matched_value"],
                decision=row["action"],
                reason=row["field"],
            )
            for row in selected_rows
        ],
        len(selected_rows),
    )


def _load_enrichment_run_rows(
    conn: sqlite3.Connection,
    *,
    report_date: str,
    taxonomy_version: str,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT status, readiness
            FROM dc_dashboard_enrichment_run_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY created_at_utc DESC, run_id DESC
            """,
            (report_date, taxonomy_version),
        ).fetchall()
    )


def _build_from_enrichment_tables(
    *,
    analysis_db: str,
    ecosystem_code: str,
    report_date: str,
    taxonomy_version: str,
    max_rows: int | None,
) -> DatacenterDashboardAnalysisDbBuildResult:
    normalized_ecosystem_code = _normalize_ecosystem_code(ecosystem_code)
    normalized_report_date = _normalize_report_date(report_date)
    normalized_taxonomy_version = _normalize_taxonomy_version(taxonomy_version)
    warnings: list[str] = []

    with _connect_read_only(analysis_db) as conn:
        _require_tables(conn, _ENRICHMENT_REQUIRED_TABLES)
        ticker_rows, watchlist_rows, ticker_count = _load_enrichment_ticker_rows(
            conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
            max_rows=max_rows,
        )
        market_map_rows, market_map_count = _load_enrichment_market_map_rows(
            conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
            max_rows=max_rows,
        )
        action_summary_rows, action_summary_count = _load_enrichment_action_summary_rows(
            conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
        )
        decision_trace_rows, decision_trace_count = _load_enrichment_decision_trace_rows(
            conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
            max_rows=max_rows,
        )
        enrichment_run_rows = _load_enrichment_run_rows(
            conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
        )

    empty_sections = [
        name
        for name, count in (
            ("ticker_enrichment", ticker_count),
            ("group_enrichment", market_map_count),
            ("action_summary", action_summary_count),
            ("decision_trace", decision_trace_count),
            ("enrichment_run", len(enrichment_run_rows)),
        )
        if count == 0
    ]
    latest_run = enrichment_run_rows[0] if enrichment_run_rows else None
    all_sections_ready = (
        ticker_count > 0
        and market_map_count > 0
        and action_summary_count > 0
        and decision_trace_count > 0
        and latest_run is not None
        and str(latest_run["status"]).strip().upper() == "OK"
    )
    if all_sections_ready:
        readiness = "READY"
    elif any(
        count > 0
        for count in (
            ticker_count,
            market_map_count,
            action_summary_count,
            decision_trace_count,
        )
    ):
        readiness = "PARTIAL"
    else:
        readiness = "FAILED"

    if empty_sections:
        warnings.append(f"ENRICHMENT_SECTIONS_EMPTY:{','.join(empty_sections)}")
    if readiness == "PARTIAL":
        warnings.append(_ENRICHMENT_PARTIAL_WARNING)

    source_row_count = (
        ticker_count
        + market_map_count
        + action_summary_count
        + decision_trace_count
        + len(enrichment_run_rows)
    )
    source_reports = []
    if readiness != "FAILED":
        source_reports = [
            EcosystemDashboardSourceReportInput(
                source_report_path="analysis-db://dashboard-enrichment",
                source_report_type="analysis_db_enrichment",
                source_report_date=normalized_report_date,
                loaded_row_count=source_row_count,
                status="READY" if readiness == "READY" else "PARTIAL",
            )
        ]

    dashboard_input = EcosystemDashboardInput(
        ecosystem_code=normalized_ecosystem_code,
        report_date=normalized_report_date,
        source_reports=source_reports,
        action_summary=action_summary_rows,
        market_map=market_map_rows,
        watchlist=watchlist_rows,
        tickers=ticker_rows,
        decision_trace=decision_trace_rows,
        readiness=readiness,
        total_parsed_rows=source_row_count,
        total_parse_warnings=len(warnings),
    )
    return DatacenterDashboardAnalysisDbBuildResult(
        dashboard_input=dashboard_input,
        warnings=tuple(warnings),
        source_row_count=source_row_count,
    )


def build_datacenter_dashboard_input_from_analysis_db(
    *,
    analysis_db: str,
    price_db: str,
    ecosystem_code: str,
    report_date: str,
    taxonomy_version: str | None = DEFAULT_TAXONOMY_VERSION,
    market: str = "usa",
    max_rows: int | None = None,
    source_mode: str = "enrichment",
) -> DatacenterDashboardAnalysisDbBuildResult:
    normalized_source_mode = source_mode.strip().lower()
    if normalized_source_mode not in {"enrichment", "raw-v0"}:
        raise ValueError(
            f"unsupported source_mode={source_mode}; currently supported: enrichment, raw-v0"
        )
    if normalized_source_mode == "enrichment":
        return _build_from_enrichment_tables(
            analysis_db=analysis_db,
            ecosystem_code=ecosystem_code,
            report_date=report_date,
            taxonomy_version=taxonomy_version or DEFAULT_TAXONOMY_VERSION,
            max_rows=max_rows,
        )

    del market
    normalized_ecosystem_code = _normalize_ecosystem_code(ecosystem_code)
    normalized_report_date = _normalize_report_date(report_date)
    normalized_taxonomy_version = _normalize_taxonomy_version(taxonomy_version)

    warnings = [
        ACTION_SUMMARY_WARNING,
        DECISION_TRACE_WARNING,
        WATCHLIST_WARNING,
        WINDOW_STATUS_WARNING,
    ]

    with _connect_read_only(analysis_db) as analysis_conn, _connect_read_only(price_db):
        _require_tables(analysis_conn, _REQUIRED_TABLES)
        ticker_rows, subindustry_to_layer, ticker_source_count = _load_ticker_rows(
            analysis_conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
            max_rows=max_rows,
        )
        market_map_rows, market_source_count = _load_market_map_rows(
            analysis_conn,
            report_date=normalized_report_date,
            taxonomy_version=normalized_taxonomy_version,
            subindustry_to_layer=subindustry_to_layer,
            max_rows=max_rows,
        )

    source_row_count = ticker_source_count + market_source_count
    readiness = _readiness_for_sections(
        source_reports=[],
        market_map=market_map_rows,
        tickers=ticker_rows,
    )
    source_reports = [
        EcosystemDashboardSourceReportInput(
            source_report_path=(
                "analysis-db://dc_ticker_swing_signal_daily,"
                "dc_group_swing_signal_daily,"
                "dc_group_synthetic_ohlc_daily,"
                "dc_group_index_daily"
            ),
            source_report_type="analysis_db_structured",
            source_report_date=normalized_report_date,
            loaded_row_count=source_row_count,
            status="OK" if readiness == "READY" else "PARTIAL",
        )
    ]
    if readiness == "FAILED":
        source_reports = []

    dashboard_input = EcosystemDashboardInput(
        ecosystem_code=normalized_ecosystem_code,
        report_date=normalized_report_date,
        source_reports=source_reports,
        action_summary=[],
        market_map=market_map_rows,
        watchlist=[],
        tickers=ticker_rows,
        decision_trace=[],
        readiness=readiness,
        total_parsed_rows=source_row_count,
        total_parse_warnings=len(warnings),
    )
    return DatacenterDashboardAnalysisDbBuildResult(
        dashboard_input=dashboard_input,
        warnings=tuple(sorted(warnings + ["RAW_V0_SOURCE_MODE_USED"])),
        source_row_count=source_row_count,
    )
