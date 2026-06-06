from __future__ import annotations

from collections import Counter
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


DAILY_WINDOW_CODE = "daily"
ROLLING2_WINDOW_CODE = "rolling2"
ROLLING30_WINDOW_CODE = "rolling30"
ROLLING5_WINDOW_CODE = "rolling5"
WINDOW_DAYS_BY_CODE = {
    DAILY_WINDOW_CODE: 1,
    ROLLING2_WINDOW_CODE: 2,
    ROLLING5_WINDOW_CODE: 5,
    ROLLING30_WINDOW_CODE: 30,
}
REQUIRED_TABLES = (
    "eco_report_run",
    "eco_entity",
    "eco_taxonomy_entity_relation",
    "eco_watchlist",
    "eco_watchlist_member",
    "eco_entity_coverage",
    "eco_quality_summary",
    "eco_entity_window_snapshot",
    "eco_entity_metric_value",
    "eco_classification_decision",
    "eco_signal_observation",
    "eco_signal_relevance",
    "eco_entity_event",
    "eco_report_window",
    "eco_ecosystem",
    "eco_taxonomy_version",
)
ENTITY_TYPE_ORDER = {
    "ECOSYSTEM": 0,
    "LAYER": 1,
    "SUBINDUSTRY": 2,
    "TICKER": 3,
}
QUALITY_SCOPE_ORDER = {
    "RUN": 0,
    "WINDOW": 1,
    "ECOSYSTEM": 2,
    "LAYER": 3,
    "SUBINDUSTRY": 4,
    "TICKER": 5,
    "SOURCE": 6,
}
ROLLING30_BUY_ORDER = {
    "BUY_ZONE": 0,
    "WATCH_ZONE": 1,
    "AVOID": 2,
    "INSUFFICIENT_DATA": 3,
}
ROLLING30_EXIT_ORDER = {
    "EXTREME": 0,
    "EXIT_ZONE": 1,
    "WATCH": 2,
    "NORMAL": 3,
    "INSUFFICIENT_DATA": 4,
}
ROLLING5_PULLBACK_ORDER = {
    "PULLBACK_CANDIDATE": 0,
    "EARLY_PULLBACK": 1,
    "FAILED_PULLBACK": 2,
    "SHORT_TERM_BREAKDOWN": 3,
    "NO_PULLBACK": 4,
    "INSUFFICIENT_DATA": 5,
}
ROLLING2_SELL_PRESSURE_ORDER = {
    "EMERGENCY_SELL_PRESSURE": 0,
    "SHARP_2D_DROP": 1,
    "WATCH_PRESSURE": 2,
    "NO_EMERGENCY": 3,
    "INSUFFICIENT_DATA": 4,
}
DAILY_TRIGGER_ORDER = {
    "BUY_WATCH": 0,
    "SELL_TRIGGER": 1,
    "STOP_TRIGGER": 2,
    "EXIT_WATCH": 3,
    "NO_TRIGGER": 4,
    "INSUFFICIENT_DATA": 5,
}
ROLLING_TICKER_METRIC_NAMES = (
    "breakout_days",
    "pullback_days",
    "exit_risk_days",
    "high_exit_risk_days",
    "medium_exit_risk_days",
    "valid_signal_dates",
    "distance_to_ema20_pct",
)
DAILY_TICKER_METRIC_NAMES = (
    "distance_to_ema10_pct",
    "distance_to_ema20_pct",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "latest_bos_age_trading_days",
    "latest_reset_age_trading_days",
    "latest_structure_age_trading_days",
    "freshness_latest_bos_age_trading_days",
    "freshness_latest_bos_class",
    "freshness_latest_reset_age_trading_days",
    "freshness_latest_reset_class",
    "freshness_latest_structure_age_trading_days",
    "freshness_latest_structure_class",
)
ROLLING_GROUP_METRIC_NAMES = (
    "pct_above_ema20",
    "return_5d",
    "synthetic_close",
    "trend_breadth",
    "weakness_breadth",
    "valid_signal_dates",
    "group_current_status",
    "group_window_status",
    "group_status_change",
    "group_timing_state",
    "group_timing_reason",
    "group_overheat_risk_level",
)
ROLLING_ECOSYSTEM_WINDOW_CHANGE_METRIC_NAMES = (
    "pct_above_ema20",
    "return_5d",
    "synthetic_close",
    "trend_breadth",
    "weakness_breadth",
    "group_timing_state",
    "group_overheat_risk_level",
)
ROLLING_ECOSYSTEM_WINDOW_CHANGE_ROW_LIMIT = 100
ROLLING_RISK_PROGRESSION_ROW_LIMIT = 100
ROLLING_SUBINDUSTRY_TIMING_PERSISTENCE_ROW_LIMIT = 100
ROLLING_SUBINDUSTRY_IMPROVEMENT_DETERIORATION_ROW_LIMIT = 100
DAILY_TICKER_SCANNER_ROW_LIMIT = 100
DAILY_SYNTHETIC_OHLC_STRUCTURE_SUMMARY_ROW_LIMIT = 100
ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_SHARES = {
    "DETERIORATED": 50,
    "IMPROVED": 30,
    "UNCHANGED": 15,
    "n/a": 5,
}
ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_PRIORITY = [
    "DETERIORATED",
    "IMPROVED",
    "UNCHANGED",
    "n/a",
]
ROLLING_SUBINDUSTRY_IMPROVEMENT_DETERIORATION_METRIC_NAMES = (
    "return_5d",
    "return_10d",
    "return_20d",
    "pct_above_ema20",
    "trend_breadth",
    "weakness_breadth",
    "synthetic_close",
)
RISK_LEVEL_ORDER = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
}
RISK_CHANGE_ORDER = {
    "WORSENED": 0,
    "UNCHANGED": 1,
    "IMPROVED": 2,
    "n/a": 3,
}
TIMING_STATE_BUCKETS = {
    "BUY_ZONE": "buy_zone_days",
    "ADD_ON_PULLBACK": "add_on_pullback_days",
    "TRIM_WATCH": "trim_watch_days",
    "EXIT_ZONE": "exit_zone_days",
    "NEUTRAL": "neutral_days",
}
DAILY_GROUP_METRIC_NAMES = (
    "pct_above_ema20",
    "return_5d",
    "synthetic_close",
    "trend_breadth",
    "weakness_breadth",
    "group_current_status",
    "group_timing_state",
    "group_timing_reason",
    "group_overheat_risk_level",
    "freshness_latest_bos_age_trading_days",
    "freshness_latest_bos_class",
    "freshness_latest_reset_age_trading_days",
    "freshness_latest_reset_class",
    "freshness_latest_structure_age_trading_days",
    "freshness_latest_structure_class",
)
STRUCTURAL_EVENT_TYPES = (
    "BOS",
    "RESET",
    "STRUCTURE_CHANGE",
    "TREND_STATE_CHANGE",
)


@dataclass(frozen=True)
class Rolling30ReportHeader:
    run_id: str
    ecosystem_code: str
    taxonomy_version_code: str
    signal_date: str
    window_code: str


@dataclass(frozen=True)
class Rolling30ReportQueryData:
    report_header: Rolling30ReportHeader
    window_summary: dict[str, Any]
    ecosystem_window_change: dict[str, Any]
    overheat_rotation_risk_progression: dict[str, Any]
    subindustry_timing_persistence: dict[str, Any]
    subindustry_improvement_deterioration: dict[str, Any]
    watchlist_summary: dict[str, Any]
    quality_summary: dict[str, Any]
    ecosystem_snapshot: dict[str, Any] | None
    group_snapshots: list[dict[str, Any]]
    ticker_snapshots: list[dict[str, Any]]
    rolling30_buy_classifications: list[dict[str, Any]]
    rolling30_exit_classifications: list[dict[str, Any]]
    ticker_metrics: dict[str, dict[str, Any]]
    group_metrics: list[dict[str, Any]]
    watchlist_members: list[dict[str, Any]]
    structural_events: list[dict[str, Any]]
    signal_observations: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Rolling5ReportQueryData:
    report_header: Rolling30ReportHeader
    window_summary: dict[str, Any]
    ecosystem_window_change: dict[str, Any]
    overheat_rotation_risk_progression: dict[str, Any]
    subindustry_timing_persistence: dict[str, Any]
    subindustry_improvement_deterioration: dict[str, Any]
    watchlist_summary: dict[str, Any]
    quality_summary: dict[str, Any]
    ecosystem_snapshot: dict[str, Any] | None
    group_snapshots: list[dict[str, Any]]
    ticker_snapshots: list[dict[str, Any]]
    rolling5_pullback_classifications: list[dict[str, Any]]
    ticker_metrics: dict[str, dict[str, Any]]
    group_metrics: list[dict[str, Any]]
    watchlist_members: list[dict[str, Any]]
    structural_events: list[dict[str, Any]]
    signal_observations: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Rolling2ReportQueryData:
    report_header: Rolling30ReportHeader
    window_summary: dict[str, Any]
    ecosystem_window_change: dict[str, Any]
    overheat_rotation_risk_progression: dict[str, Any]
    subindustry_timing_persistence: dict[str, Any]
    subindustry_improvement_deterioration: dict[str, Any]
    watchlist_summary: dict[str, Any]
    quality_summary: dict[str, Any]
    ecosystem_snapshot: dict[str, Any] | None
    group_snapshots: list[dict[str, Any]]
    ticker_snapshots: list[dict[str, Any]]
    rolling2_sell_pressure_classifications: list[dict[str, Any]]
    ticker_metrics: dict[str, dict[str, Any]]
    group_metrics: list[dict[str, Any]]
    watchlist_members: list[dict[str, Any]]
    structural_events: list[dict[str, Any]]
    signal_observations: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DailyReportQueryData:
    report_header: Rolling30ReportHeader
    watchlist_summary: dict[str, Any]
    ticker_scanners: dict[str, Any]
    synthetic_ohlc_structure_summary: dict[str, Any]
    quality_summary: dict[str, Any]
    ecosystem_snapshot: dict[str, Any] | None
    group_snapshots: list[dict[str, Any]]
    ticker_snapshots: list[dict[str, Any]]
    daily_trigger_classifications: list[dict[str, Any]]
    ticker_metrics: dict[str, dict[str, Any]]
    group_metrics: list[dict[str, Any]]
    watchlist_members: list[dict[str, Any]]
    structural_events: list[dict[str, Any]]
    signal_observations: list[dict[str, Any]]
    metadata: dict[str, Any]


def build_rolling30_report_query_data(
    db_path: str,
    run_id: str,
) -> Rolling30ReportQueryData:
    return _build_rolling30_report_query_data(db_path=db_path, run_id=run_id)


def build_rolling5_report_query_data(
    db_path: str,
    run_id: str,
) -> Rolling5ReportQueryData:
    return _build_rolling5_report_query_data(db_path=db_path, run_id=run_id)


def build_rolling2_report_query_data(
    db_path: str,
    run_id: str,
) -> Rolling2ReportQueryData:
    return _build_rolling2_report_query_data(db_path=db_path, run_id=run_id)


def build_daily_report_query_data(
    db_path: str,
    run_id: str,
) -> DailyReportQueryData:
    return _build_daily_report_query_data(db_path=db_path, run_id=run_id)


def _build_rolling30_report_query_data(
    db_path: str,
    run_id: str,
) -> Rolling30ReportQueryData:
    conn = _connect_read_only(db_path)
    try:
        conn.row_factory = sqlite3.Row
        _check_required_tables(conn)
        _require_window(conn, ROLLING30_WINDOW_CODE)
        run_row = _resolve_run(conn, run_id)
        report_header = Rolling30ReportHeader(
            run_id=str(run_row["run_id"]),
            ecosystem_code=str(run_row["ecosystem_code"]),
            taxonomy_version_code=str(run_row["taxonomy_version_code"]),
            signal_date=str(run_row["signal_date"]),
            window_code=ROLLING30_WINDOW_CODE,
        )
        snapshots = _load_snapshots(conn, run_row, ROLLING30_WINDOW_CODE)
        if not snapshots:
            raise ValueError(f"No {ROLLING30_WINDOW_CODE} snapshot rows found for run_id '{run_id}'")

        buy_rows = _load_classifications(conn, run_row, ROLLING30_WINDOW_CODE, "rolling30_buy")
        exit_rows = _load_classifications(conn, run_row, ROLLING30_WINDOW_CODE, "rolling30_exit")
        if not buy_rows and not exit_rows:
            raise ValueError(f"No {ROLLING30_WINDOW_CODE} classification rows found for run_id '{run_id}'")

        ticker_metrics = _load_ticker_metrics(conn, run_row, ROLLING30_WINDOW_CODE)
        group_metrics = _load_group_metrics(conn, run_row, ROLLING30_WINDOW_CODE)
        watchlist_members = _load_watchlist_members(conn, run_row)
        structural_events = _load_structural_events(conn, run_row, ROLLING30_WINDOW_CODE)
        signal_observations = _load_signal_observations(conn, run_row, ROLLING30_WINDOW_CODE)

        ecosystem_snapshot = next((row for row in snapshots if row["entity_type"] == "ECOSYSTEM"), None)
        group_snapshots = [row for row in snapshots if row["entity_type"] in {"LAYER", "SUBINDUSTRY"}]
        ticker_snapshots = [row for row in snapshots if row["entity_type"] == "TICKER"]

        window_summary = _load_rolling_window_summary(conn, run_row, ROLLING30_WINDOW_CODE)
        return Rolling30ReportQueryData(
            report_header=report_header,
            window_summary=window_summary,
            ecosystem_window_change=_load_rolling_ecosystem_window_change(
                conn,
                run_row,
                ROLLING30_WINDOW_CODE,
                window_summary,
            ),
            overheat_rotation_risk_progression=_load_rolling_overheat_rotation_risk_progression(
                conn,
                run_row,
                ROLLING30_WINDOW_CODE,
                window_summary,
            ),
            subindustry_timing_persistence=_load_rolling_subindustry_timing_persistence(
                conn,
                run_row,
                ROLLING30_WINDOW_CODE,
                window_summary,
            ),
            subindustry_improvement_deterioration=_load_rolling_subindustry_improvement_deterioration(
                conn,
                run_row,
                ROLLING30_WINDOW_CODE,
                window_summary,
            ),
            watchlist_summary=_load_rolling_watchlist_summary(
                conn,
                run_row,
                watchlist_members,
                ticker_metrics,
                group_metrics,
                ticker_snapshots,
            ),
            quality_summary={
                "rows": _load_quality_summary_rows(conn, run_row, ROLLING30_WINDOW_CODE),
                "coverage_counts": _load_coverage_counts(conn, run_row, ROLLING30_WINDOW_CODE),
            },
            ecosystem_snapshot=ecosystem_snapshot,
            group_snapshots=group_snapshots,
            ticker_snapshots=ticker_snapshots,
            rolling30_buy_classifications=buy_rows,
            rolling30_exit_classifications=exit_rows,
            ticker_metrics=ticker_metrics,
            group_metrics=group_metrics,
            watchlist_members=watchlist_members,
            structural_events=structural_events,
            signal_observations=signal_observations,
            metadata=_build_metadata(
                window_code=ROLLING30_WINDOW_CODE,
                ticker_snapshots=ticker_snapshots,
                classification_rows=[*buy_rows, *exit_rows],
                signal_observations=signal_observations,
                structural_events=structural_events,
            ),
        )
    finally:
        conn.close()


def _build_daily_report_query_data(
    db_path: str,
    run_id: str,
) -> DailyReportQueryData:
    conn = _connect_read_only(db_path)
    try:
        conn.row_factory = sqlite3.Row
        _check_required_tables(conn)
        _require_window(conn, DAILY_WINDOW_CODE)
        run_row = _resolve_run(conn, run_id)
        report_header = Rolling30ReportHeader(
            run_id=str(run_row["run_id"]),
            ecosystem_code=str(run_row["ecosystem_code"]),
            taxonomy_version_code=str(run_row["taxonomy_version_code"]),
            signal_date=str(run_row["signal_date"]),
            window_code=DAILY_WINDOW_CODE,
        )
        snapshots = _load_snapshots(conn, run_row, DAILY_WINDOW_CODE)
        if not snapshots:
            raise ValueError(f"No {DAILY_WINDOW_CODE} snapshot rows found for run_id '{run_id}'")

        daily_rows = _load_classifications(conn, run_row, DAILY_WINDOW_CODE, "daily_trigger")
        if not daily_rows:
            raise ValueError(f"No {DAILY_WINDOW_CODE} classification rows found for run_id '{run_id}'")

        ticker_metrics = _load_ticker_metrics(conn, run_row, DAILY_WINDOW_CODE, DAILY_TICKER_METRIC_NAMES)
        group_metrics = _load_group_metrics(conn, run_row, DAILY_WINDOW_CODE, DAILY_GROUP_METRIC_NAMES)
        watchlist_members = _load_watchlist_members(conn, run_row)
        structural_events = _load_structural_events(conn, run_row, DAILY_WINDOW_CODE)
        signal_observations = _load_signal_observations(conn, run_row, DAILY_WINDOW_CODE)

        ecosystem_snapshot = next((row for row in snapshots if row["entity_type"] == "ECOSYSTEM"), None)
        group_snapshots = [row for row in snapshots if row["entity_type"] in {"LAYER", "SUBINDUSTRY"}]
        ticker_snapshots = [row for row in snapshots if row["entity_type"] == "TICKER"]
        watchlist_summary = _load_daily_watchlist_summary(
            conn,
            run_row,
            watchlist_members,
            ticker_metrics,
            group_metrics,
            ticker_snapshots,
            daily_rows,
            signal_observations,
        )

        return DailyReportQueryData(
            report_header=report_header,
            watchlist_summary=watchlist_summary,
            ticker_scanners=_load_daily_ticker_scanners(
                watchlist_summary=watchlist_summary,
                daily_classifications=daily_rows,
                signal_observations=signal_observations,
            ),
            synthetic_ohlc_structure_summary=_load_daily_synthetic_ohlc_structure_summary(
                run_row=run_row,
                group_snapshots=group_snapshots,
                group_metrics=group_metrics,
                structural_events=structural_events,
            ),
            quality_summary={
                "rows": _load_quality_summary_rows(conn, run_row, DAILY_WINDOW_CODE),
                "coverage_counts": _load_coverage_counts(conn, run_row, DAILY_WINDOW_CODE),
            },
            ecosystem_snapshot=ecosystem_snapshot,
            group_snapshots=group_snapshots,
            ticker_snapshots=ticker_snapshots,
            daily_trigger_classifications=daily_rows,
            ticker_metrics=ticker_metrics,
            group_metrics=group_metrics,
            watchlist_members=watchlist_members,
            structural_events=structural_events,
            signal_observations=signal_observations,
            metadata=_build_metadata(
                window_code=DAILY_WINDOW_CODE,
                ticker_snapshots=ticker_snapshots,
                classification_rows=daily_rows,
                signal_observations=signal_observations,
                structural_events=structural_events,
            ),
        )
    finally:
        conn.close()


def _build_rolling2_report_query_data(
    db_path: str,
    run_id: str,
) -> Rolling2ReportQueryData:
    conn = _connect_read_only(db_path)
    try:
        conn.row_factory = sqlite3.Row
        _check_required_tables(conn)
        _require_window(conn, ROLLING2_WINDOW_CODE)
        run_row = _resolve_run(conn, run_id)
        report_header = Rolling30ReportHeader(
            run_id=str(run_row["run_id"]),
            ecosystem_code=str(run_row["ecosystem_code"]),
            taxonomy_version_code=str(run_row["taxonomy_version_code"]),
            signal_date=str(run_row["signal_date"]),
            window_code=ROLLING2_WINDOW_CODE,
        )
        snapshots = _load_snapshots(conn, run_row, ROLLING2_WINDOW_CODE)
        if not snapshots:
            raise ValueError(f"No {ROLLING2_WINDOW_CODE} snapshot rows found for run_id '{run_id}'")

        sell_pressure_rows = _load_classifications(conn, run_row, ROLLING2_WINDOW_CODE, "rolling2_sell_pressure")
        if not sell_pressure_rows:
            raise ValueError(f"No {ROLLING2_WINDOW_CODE} classification rows found for run_id '{run_id}'")

        ticker_metrics = _load_ticker_metrics(conn, run_row, ROLLING2_WINDOW_CODE)
        group_metrics = _load_group_metrics(conn, run_row, ROLLING2_WINDOW_CODE)
        watchlist_members = _load_watchlist_members(conn, run_row)
        structural_events = _load_structural_events(conn, run_row, ROLLING2_WINDOW_CODE)
        signal_observations = _load_signal_observations(conn, run_row, ROLLING2_WINDOW_CODE)

        ecosystem_snapshot = next((row for row in snapshots if row["entity_type"] == "ECOSYSTEM"), None)
        group_snapshots = [row for row in snapshots if row["entity_type"] in {"LAYER", "SUBINDUSTRY"}]
        ticker_snapshots = [row for row in snapshots if row["entity_type"] == "TICKER"]

        window_summary = _load_rolling_window_summary(conn, run_row, ROLLING2_WINDOW_CODE)
        return Rolling2ReportQueryData(
            report_header=report_header,
            window_summary=window_summary,
            ecosystem_window_change=_load_rolling_ecosystem_window_change(
                conn,
                run_row,
                ROLLING2_WINDOW_CODE,
                window_summary,
            ),
            overheat_rotation_risk_progression=_load_rolling_overheat_rotation_risk_progression(
                conn,
                run_row,
                ROLLING2_WINDOW_CODE,
                window_summary,
            ),
            subindustry_timing_persistence=_load_rolling_subindustry_timing_persistence(
                conn,
                run_row,
                ROLLING2_WINDOW_CODE,
                window_summary,
            ),
            subindustry_improvement_deterioration=_load_rolling_subindustry_improvement_deterioration(
                conn,
                run_row,
                ROLLING2_WINDOW_CODE,
                window_summary,
            ),
            watchlist_summary=_load_rolling_watchlist_summary(
                conn,
                run_row,
                watchlist_members,
                ticker_metrics,
                group_metrics,
                ticker_snapshots,
            ),
            quality_summary={
                "rows": _load_quality_summary_rows(conn, run_row, ROLLING2_WINDOW_CODE),
                "coverage_counts": _load_coverage_counts(conn, run_row, ROLLING2_WINDOW_CODE),
            },
            ecosystem_snapshot=ecosystem_snapshot,
            group_snapshots=group_snapshots,
            ticker_snapshots=ticker_snapshots,
            rolling2_sell_pressure_classifications=sell_pressure_rows,
            ticker_metrics=ticker_metrics,
            group_metrics=group_metrics,
            watchlist_members=watchlist_members,
            structural_events=structural_events,
            signal_observations=signal_observations,
            metadata=_build_metadata(
                window_code=ROLLING2_WINDOW_CODE,
                ticker_snapshots=ticker_snapshots,
                classification_rows=sell_pressure_rows,
                signal_observations=signal_observations,
                structural_events=structural_events,
            ),
        )
    finally:
        conn.close()


def _build_rolling5_report_query_data(
    db_path: str,
    run_id: str,
) -> Rolling5ReportQueryData:
    conn = _connect_read_only(db_path)
    try:
        conn.row_factory = sqlite3.Row
        _check_required_tables(conn)
        _require_window(conn, ROLLING5_WINDOW_CODE)
        run_row = _resolve_run(conn, run_id)
        report_header = Rolling30ReportHeader(
            run_id=str(run_row["run_id"]),
            ecosystem_code=str(run_row["ecosystem_code"]),
            taxonomy_version_code=str(run_row["taxonomy_version_code"]),
            signal_date=str(run_row["signal_date"]),
            window_code=ROLLING5_WINDOW_CODE,
        )
        snapshots = _load_snapshots(conn, run_row, ROLLING5_WINDOW_CODE)
        if not snapshots:
            raise ValueError(f"No {ROLLING5_WINDOW_CODE} snapshot rows found for run_id '{run_id}'")

        pullback_rows = _load_classifications(conn, run_row, ROLLING5_WINDOW_CODE, "rolling5_pullback")
        if not pullback_rows:
            raise ValueError(f"No {ROLLING5_WINDOW_CODE} classification rows found for run_id '{run_id}'")

        ticker_metrics = _load_ticker_metrics(conn, run_row, ROLLING5_WINDOW_CODE)
        group_metrics = _load_group_metrics(conn, run_row, ROLLING5_WINDOW_CODE)
        watchlist_members = _load_watchlist_members(conn, run_row)
        structural_events = _load_structural_events(conn, run_row, ROLLING5_WINDOW_CODE)
        signal_observations = _load_signal_observations(conn, run_row, ROLLING5_WINDOW_CODE)

        ecosystem_snapshot = next((row for row in snapshots if row["entity_type"] == "ECOSYSTEM"), None)
        group_snapshots = [row for row in snapshots if row["entity_type"] in {"LAYER", "SUBINDUSTRY"}]
        ticker_snapshots = [row for row in snapshots if row["entity_type"] == "TICKER"]

        window_summary = _load_rolling_window_summary(conn, run_row, ROLLING5_WINDOW_CODE)
        return Rolling5ReportQueryData(
            report_header=report_header,
            window_summary=window_summary,
            ecosystem_window_change=_load_rolling_ecosystem_window_change(
                conn,
                run_row,
                ROLLING5_WINDOW_CODE,
                window_summary,
            ),
            overheat_rotation_risk_progression=_load_rolling_overheat_rotation_risk_progression(
                conn,
                run_row,
                ROLLING5_WINDOW_CODE,
                window_summary,
            ),
            subindustry_timing_persistence=_load_rolling_subindustry_timing_persistence(
                conn,
                run_row,
                ROLLING5_WINDOW_CODE,
                window_summary,
            ),
            subindustry_improvement_deterioration=_load_rolling_subindustry_improvement_deterioration(
                conn,
                run_row,
                ROLLING5_WINDOW_CODE,
                window_summary,
            ),
            watchlist_summary=_load_rolling_watchlist_summary(
                conn,
                run_row,
                watchlist_members,
                ticker_metrics,
                group_metrics,
                ticker_snapshots,
            ),
            quality_summary={
                "rows": _load_quality_summary_rows(conn, run_row, ROLLING5_WINDOW_CODE),
                "coverage_counts": _load_coverage_counts(conn, run_row, ROLLING5_WINDOW_CODE),
            },
            ecosystem_snapshot=ecosystem_snapshot,
            group_snapshots=group_snapshots,
            ticker_snapshots=ticker_snapshots,
            rolling5_pullback_classifications=pullback_rows,
            ticker_metrics=ticker_metrics,
            group_metrics=group_metrics,
            watchlist_members=watchlist_members,
            structural_events=structural_events,
            signal_observations=signal_observations,
            metadata=_build_metadata(
                window_code=ROLLING5_WINDOW_CODE,
                ticker_snapshots=ticker_snapshots,
                classification_rows=pullback_rows,
                signal_observations=signal_observations,
                structural_events=structural_events,
            ),
        )
    finally:
        conn.close()


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    return sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _check_required_tables(conn: sqlite3.Connection) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    }
    missing = [table_name for table_name in REQUIRED_TABLES if table_name not in existing]
    if missing:
        raise ValueError(f"Missing required Eco tables: {', '.join(sorted(missing))}")


def _require_window(conn: sqlite3.Connection, window_code: str) -> None:
    row = conn.execute(
        """
        SELECT 1
        FROM eco_report_window
        WHERE window_code = ?
        """,
        (window_code,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Missing eco_report_window row for window_code '{window_code}'")


def _resolve_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT
            rr.run_id,
            rr.ecosystem_id,
            rr.taxonomy_version_id,
            rr.signal_date,
            ee.ecosystem_code,
            tv.version_code AS taxonomy_version_code
        FROM eco_report_run rr
        JOIN eco_ecosystem ee ON ee.ecosystem_id = rr.ecosystem_id
        JOIN eco_taxonomy_version tv ON tv.taxonomy_version_id = rr.taxonomy_version_id
        WHERE rr.run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Missing eco_report_run for run_id '{run_id}'")
    return row


def _load_quality_summary_rows(conn: sqlite3.Connection, run_row: sqlite3.Row, window_code: str) -> list[dict[str, Any]]:
    rows = [
        _row_to_dict(row)
        for row in conn.execute(
            """
            SELECT
                qs.window_code,
                qs.quality_scope,
                qs.quality_status,
                qs.scope_entity_id,
                se.entity_type AS scope_entity_type,
                se.entity_code AS scope_entity_code,
                se.entity_name AS scope_entity_name,
                qs.expected_count,
                qs.actual_count,
                qs.missing_count,
                qs.incomplete_count,
                qs.stale_count,
                qs.warning_count,
                qs.error_count,
                qs.summary_note
            FROM eco_quality_summary qs
            JOIN eco_entity se ON se.entity_id = qs.scope_entity_id
            WHERE qs.run_id = ?
              AND qs.signal_date = ?
              AND qs.taxonomy_version_id = ?
              AND qs.window_code = ?
            ORDER BY
                CASE qs.quality_scope
                    WHEN 'RUN' THEN 0
                    WHEN 'WINDOW' THEN 1
                    WHEN 'ECOSYSTEM' THEN 2
                    WHEN 'LAYER' THEN 3
                    WHEN 'SUBINDUSTRY' THEN 4
                    WHEN 'TICKER' THEN 5
                    WHEN 'SOURCE' THEN 6
                    ELSE 99
                END,
                se.entity_code
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                window_code,
            ),
        ).fetchall()
    ]
    rows.sort(
        key=lambda row: (
            QUALITY_SCOPE_ORDER.get(str(row["quality_scope"]), 99),
            str(row.get("scope_entity_code") or ""),
        )
    )
    return rows


def _load_coverage_counts(conn: sqlite3.Connection, run_row: sqlite3.Row, window_code: str) -> list[dict[str, Any]]:
    return [
        _row_to_dict(row)
        for row in conn.execute(
            """
            SELECT
                e.entity_type,
                c.coverage_status,
                COUNT(*) AS row_count
            FROM eco_entity_coverage c
            JOIN eco_entity e ON e.entity_id = c.entity_id
            WHERE c.run_id = ?
              AND c.signal_date = ?
              AND c.taxonomy_version_id = ?
              AND c.window_code = ?
            GROUP BY e.entity_type, c.coverage_status
            ORDER BY
                CASE e.entity_type
                    WHEN 'ECOSYSTEM' THEN 0
                    WHEN 'LAYER' THEN 1
                    WHEN 'SUBINDUSTRY' THEN 2
                    WHEN 'TICKER' THEN 3
                    ELSE 99
                END,
                c.coverage_status
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                window_code,
            ),
        ).fetchall()
    ]


def _load_snapshots(conn: sqlite3.Connection, run_row: sqlite3.Row, window_code: str) -> list[dict[str, Any]]:
    rows = [
        _row_to_dict(row)
        for row in conn.execute(
            """
            SELECT
                e.entity_type,
                e.entity_code,
                e.entity_name,
                s.window_code,
                s.snapshot_status,
                s.timing_state,
                s.trend_state,
                s.summary_state,
                s.classification_state,
                s.freshness_status,
                s.quality_status
            FROM eco_entity_window_snapshot s
            JOIN eco_entity e ON e.entity_id = s.entity_id
            WHERE s.run_id = ?
              AND s.signal_date = ?
              AND s.taxonomy_version_id = ?
              AND s.window_code = ?
            ORDER BY
                CASE e.entity_type
                    WHEN 'ECOSYSTEM' THEN 0
                    WHEN 'LAYER' THEN 1
                    WHEN 'SUBINDUSTRY' THEN 2
                    WHEN 'TICKER' THEN 3
                    ELSE 99
                END,
                e.entity_code
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                window_code,
            ),
        ).fetchall()
    ]
    rows.sort(
        key=lambda row: (
            ENTITY_TYPE_ORDER.get(str(row["entity_type"]), 99),
            str(row["entity_code"]),
        )
    )
    return rows


def _load_classifications(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    classification_type: str,
) -> list[dict[str, Any]]:
    rows = [
        _row_to_dict(row)
        for row in conn.execute(
            """
            SELECT
                e.entity_code AS ticker,
                cd.classification_state,
                cd.primary_reason,
                cd.blocking_reason,
                cd.risk_reason,
                cd.next_action,
                cd.decision_status,
                cd.source_run_id,
                cd.priority_score,
                cd.priority_label,
                cd.sort_rank
            FROM eco_classification_decision cd
            JOIN eco_entity e ON e.entity_id = cd.entity_id
            WHERE cd.run_id = ?
              AND cd.signal_date = ?
              AND cd.taxonomy_version_id = ?
              AND cd.window_code = ?
              AND cd.classification_type = ?
            ORDER BY e.entity_code
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                window_code,
                classification_type,
            ),
        ).fetchall()
    ]
    if classification_type == "rolling30_buy":
        severity_order = ROLLING30_BUY_ORDER
    elif classification_type == "rolling30_exit":
        severity_order = ROLLING30_EXIT_ORDER
    elif classification_type == "rolling2_sell_pressure":
        severity_order = ROLLING2_SELL_PRESSURE_ORDER
    elif classification_type == "daily_trigger":
        severity_order = DAILY_TRIGGER_ORDER
    else:
        severity_order = ROLLING5_PULLBACK_ORDER
    rows.sort(
        key=lambda row: (
            severity_order.get(str(row["classification_state"]), 99),
            str(row["ticker"]),
        )
    )
    return rows


def _load_ticker_metrics(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    metric_names: tuple[str, ...] = ROLLING_TICKER_METRIC_NAMES,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            e.entity_code AS ticker,
            e.entity_name,
            m.metric_name,
            m.metric_value_num,
            m.metric_value_text,
            m.metric_unit,
            m.value_status
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.signal_date = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code = ?
          AND e.entity_type = 'TICKER'
          AND m.metric_name IN ({", ".join("?" for _ in metric_names)})
        ORDER BY e.entity_code, m.metric_name
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            *metric_names,
        ),
    ).fetchall()
    ticker_metrics: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        metric_entry = ticker_metrics.setdefault(
            ticker,
            {
                "ticker": ticker,
                "entity_name": row["entity_name"],
            },
        )
        metric_entry[str(row["metric_name"])] = _metric_value(row)
    return ticker_metrics


def _load_group_metrics(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    metric_names: tuple[str, ...] = ROLLING_GROUP_METRIC_NAMES,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            e.entity_type,
            e.entity_code,
            e.entity_name,
            m.metric_name,
            m.metric_value_num,
            m.metric_value_text,
            m.metric_unit,
            m.value_status
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.signal_date = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code = ?
          AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
          AND m.metric_name IN ({", ".join("?" for _ in metric_names)})
        ORDER BY e.entity_type, e.entity_code, m.metric_name
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            *metric_names,
        ),
    ).fetchall()
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["entity_type"]), str(row["entity_code"]))
        metric_entry = grouped.setdefault(
            key,
            {
                "entity_type": row["entity_type"],
                "entity_code": row["entity_code"],
                "entity_name": row["entity_name"],
            },
        )
        metric_entry[str(row["metric_name"])] = _metric_value(row)
    output = list(grouped.values())
    output.sort(
        key=lambda row: (
            ENTITY_TYPE_ORDER.get(str(row["entity_type"]), 99),
            str(row["entity_code"]),
        )
    )
    return output


def _metric_value(row: sqlite3.Row) -> Any:
    if row["metric_value_num"] is not None:
        return row["metric_value_num"]
    return row["metric_value_text"]


def _load_watchlist_members(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[dict[str, Any]]:
    rows = [
        _row_to_dict(row)
        for row in conn.execute(
            """
            SELECT
                w.watchlist_code,
                w.watchlist_name,
                e.entity_id,
                e.entity_code AS ticker,
                e.entity_name,
                wm.member_role,
                wm.member_status,
                wm.effective_from,
                wm.effective_to,
                wm.sort_order,
                wm.notes
            FROM eco_watchlist w
            JOIN eco_watchlist_member wm ON wm.watchlist_id = w.watchlist_id
            JOIN eco_entity e ON e.entity_id = wm.entity_id
            WHERE w.ecosystem_id = ?
              AND w.status = 'ACTIVE'
              AND wm.member_status = 'ACTIVE'
              AND e.entity_type = 'TICKER'
              AND (wm.effective_from IS NULL OR wm.effective_from <= ?)
              AND (wm.effective_to IS NULL OR wm.effective_to >= ?)
            ORDER BY w.watchlist_code, COALESCE(wm.sort_order, 999999), e.entity_code
            """,
            (
                int(run_row["ecosystem_id"]),
                str(run_row["signal_date"]),
                str(run_row["signal_date"]),
            ),
        ).fetchall()
    ]
    return rows


def _load_rolling_watchlist_summary(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    watchlist_members: list[dict[str, Any]],
    ticker_metrics: dict[str, dict[str, Any]],
    group_metrics: list[dict[str, Any]],
    ticker_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    entity_ids = [int(row["entity_id"]) for row in watchlist_members if row.get("entity_id") is not None]
    group_metric_lookup = {
        (str(row["entity_type"]), str(row["entity_code"])): row
        for row in group_metrics
    }
    coverage_lookup = {
        int(row["entity_id"]): str(row["coverage_status"])
        for row in conn.execute(
            """
            SELECT entity_id, coverage_status
            FROM eco_entity_coverage
            WHERE run_id = ?
              AND signal_date = ?
              AND taxonomy_version_id = ?
              AND window_code = ?
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                str(run_row["window_code"]) if "window_code" in run_row.keys() else "",
            ),
        ).fetchall()
    }
    ticker_snapshot_lookup = {
        str(row["entity_code"]): row
        for row in ticker_snapshots
    }
    taxonomy_rows = conn.execute(
        f"""
        SELECT
            child.entity_id AS ticker_entity_id,
            layer.entity_code AS primary_layer,
            subindustry.entity_code AS primary_subindustry
        FROM eco_taxonomy_entity_relation rel_sub
        JOIN eco_taxonomy_entity_relation rel_layer
          ON rel_layer.child_entity_id = rel_sub.parent_entity_id
         AND rel_layer.taxonomy_version_id = rel_sub.taxonomy_version_id
         AND rel_layer.ecosystem_id = rel_sub.ecosystem_id
        JOIN eco_entity child ON child.entity_id = rel_sub.child_entity_id
        JOIN eco_entity subindustry ON subindustry.entity_id = rel_sub.parent_entity_id
        JOIN eco_entity layer ON layer.entity_id = rel_layer.parent_entity_id
        WHERE rel_sub.taxonomy_version_id = ?
          AND rel_sub.ecosystem_id = ?
          AND child.entity_id IN ({", ".join("?" for _ in entity_ids)}) 
        ORDER BY child.entity_code, layer.entity_code, subindustry.entity_code
        """,
        (
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            *entity_ids,
        ),
    ).fetchall() if entity_ids else []
    taxonomy_lookup: dict[int, dict[str, str]] = {}
    for row in taxonomy_rows:
        ticker_entity_id = int(row["ticker_entity_id"])
        taxonomy_lookup.setdefault(
            ticker_entity_id,
            {
                "primary_layer": str(row["primary_layer"]),
                "primary_subindustry": str(row["primary_subindustry"]),
            },
        )
    rows: list[dict[str, Any]] = []
    for member in watchlist_members:
        entity_id = int(member["entity_id"])
        ticker = str(member["ticker"])
        taxonomy_info = taxonomy_lookup.get(entity_id, {})
        metric_row = ticker_metrics.get(ticker, {})
        subindustry_code = taxonomy_info.get("primary_subindustry")
        layer_code = taxonomy_info.get("primary_layer")
        subindustry_metrics = group_metric_lookup.get(("SUBINDUSTRY", str(subindustry_code))) if subindustry_code else None
        layer_metrics = group_metric_lookup.get(("LAYER", str(layer_code))) if layer_code else None
        high_exit_risk_days = _number_or_zero(metric_row.get("high_exit_risk_days"))
        exit_risk_days = _number_or_zero(metric_row.get("exit_risk_days"))
        pullback_days = _number_or_zero(metric_row.get("pullback_days"))
        breakout_days = _number_or_zero(metric_row.get("breakout_days"))
        if high_exit_risk_days > 0:
            window_watchlist_status = "HIGH_EXIT_RISK"
        elif exit_risk_days > 0:
            window_watchlist_status = "EXIT_RISK"
        elif pullback_days > 0:
            window_watchlist_status = "PULLBACK"
        elif breakout_days > 0:
            window_watchlist_status = "BREAKOUT"
        else:
            window_watchlist_status = "WATCH"
        row = {
            "ticker": ticker,
            "current_watchlist_status": "ACTIVE",
            "window_watchlist_status": window_watchlist_status,
            "in_datacenter_ecosystem": entity_id in taxonomy_lookup,
            "primary_layer": taxonomy_info.get("primary_layer"),
            "primary_subindustry": taxonomy_info.get("primary_subindustry"),
            "breakout_days": metric_row.get("breakout_days"),
            "pullback_days": metric_row.get("pullback_days"),
            "exit_risk_days": metric_row.get("exit_risk_days"),
            "high_exit_risk_days": metric_row.get("high_exit_risk_days"),
            "medium_exit_risk_days": metric_row.get("medium_exit_risk_days"),
            "last_subindustry_timing_state": subindustry_metrics.get("group_timing_state") if subindustry_metrics else None,
            "last_subindustry_overheat_risk_level": subindustry_metrics.get("group_overheat_risk_level") if subindustry_metrics else None,
            "last_layer_timing_state": layer_metrics.get("group_timing_state") if layer_metrics else None,
            "last_layer_overheat_risk_level": layer_metrics.get("group_overheat_risk_level") if layer_metrics else None,
            "last_price_data_status": coverage_lookup.get(entity_id) or ticker_snapshot_lookup.get(ticker, {}).get("quality_status"),
        }
        rows.append(row)
    severity_order = {
        "HIGH_EXIT_RISK": 0,
        "EXIT_RISK": 1,
        "PULLBACK": 2,
        "BREAKOUT": 3,
        "WATCH": 4,
    }
    rows.sort(
        key=lambda row: (
            severity_order.get(str(row["window_watchlist_status"]), 99),
            -_number_or_zero(row.get("high_exit_risk_days")),
            -_number_or_zero(row.get("exit_risk_days")),
            -_number_or_zero(row.get("pullback_days")),
            -_number_or_zero(row.get("breakout_days")),
            str(row["ticker"]),
        )
    )
    counts = {
        "active_watchlist_count": len(rows),
        "in_ecosystem_count": sum(1 for row in rows if row["in_datacenter_ecosystem"]),
        "missing_price_data_count": sum(1 for row in rows if row.get("last_price_data_status") not in (None, "OK")),
        "breakout_count": sum(1 for row in rows if _number_or_zero(row.get("breakout_days")) > 0),
        "pullback_count": sum(1 for row in rows if _number_or_zero(row.get("pullback_days")) > 0),
        "exit_risk_count": sum(1 for row in rows if _number_or_zero(row.get("exit_risk_days")) > 0),
        "high_exit_risk_count": sum(1 for row in rows if _number_or_zero(row.get("high_exit_risk_days")) > 0),
        "medium_exit_risk_count": sum(1 for row in rows if _number_or_zero(row.get("medium_exit_risk_days")) > 0),
    }
    return {
        "counts": counts,
        "rows": rows,
    }


def _number_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _load_daily_watchlist_summary(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    watchlist_members: list[dict[str, Any]],
    ticker_metrics: dict[str, dict[str, Any]],
    group_metrics: list[dict[str, Any]],
    ticker_snapshots: list[dict[str, Any]],
    daily_classifications: list[dict[str, Any]],
    signal_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    entity_ids = [int(row["entity_id"]) for row in watchlist_members if row.get("entity_id") is not None]
    group_metric_lookup = {
        (str(row["entity_type"]), str(row["entity_code"])): row
        for row in group_metrics
    }
    coverage_lookup = {
        int(row["entity_id"]): str(row["coverage_status"])
        for row in conn.execute(
            """
            SELECT entity_id, coverage_status
            FROM eco_entity_coverage
            WHERE run_id = ?
              AND signal_date = ?
              AND taxonomy_version_id = ?
              AND window_code = ?
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                DAILY_WINDOW_CODE,
            ),
        ).fetchall()
    }
    ticker_snapshot_lookup = {
        str(row["entity_code"]): row
        for row in ticker_snapshots
    }
    classification_lookup = {
        str(row["ticker"]): row
        for row in daily_classifications
    }
    taxonomy_rows = conn.execute(
        f"""
        SELECT
            child.entity_id AS ticker_entity_id,
            layer.entity_code AS primary_layer,
            subindustry.entity_code AS primary_subindustry
        FROM eco_taxonomy_entity_relation rel_sub
        JOIN eco_taxonomy_entity_relation rel_layer
          ON rel_layer.child_entity_id = rel_sub.parent_entity_id
         AND rel_layer.taxonomy_version_id = rel_sub.taxonomy_version_id
         AND rel_layer.ecosystem_id = rel_sub.ecosystem_id
        JOIN eco_entity child ON child.entity_id = rel_sub.child_entity_id
        JOIN eco_entity subindustry ON subindustry.entity_id = rel_sub.parent_entity_id
        JOIN eco_entity layer ON layer.entity_id = rel_layer.parent_entity_id
        WHERE rel_sub.taxonomy_version_id = ?
          AND rel_sub.ecosystem_id = ?
          AND child.entity_id IN ({", ".join("?" for _ in entity_ids)})
        ORDER BY child.entity_code, layer.entity_code, subindustry.entity_code
        """,
        (
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            *entity_ids,
        ),
    ).fetchall() if entity_ids else []
    taxonomy_lookup: dict[int, dict[str, str]] = {}
    for row in taxonomy_rows:
        ticker_entity_id = int(row["ticker_entity_id"])
        taxonomy_lookup.setdefault(
            ticker_entity_id,
            {
                "primary_layer": str(row["primary_layer"]),
                "primary_subindustry": str(row["primary_subindustry"]),
            },
        )
    signal_rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in signal_observations:
        signal_rows_by_ticker.setdefault(str(row["entity_code"]), []).append(row)
    rows: list[dict[str, Any]] = []
    for member in watchlist_members:
        entity_id = int(member["entity_id"])
        ticker = str(member["ticker"])
        metric_row = ticker_metrics.get(ticker, {})
        classification_row = classification_lookup.get(ticker, {})
        classification_state = str(classification_row.get("classification_state") or "")
        signals = signal_rows_by_ticker.get(ticker, [])
        breakout_signal = classification_state == "BUY_WATCH"
        pullback_signal = None
        exit_risk_signal = classification_state in {"SELL_TRIGGER", "STOP_TRIGGER", "EXIT_WATCH"}
        if classification_state in {"SELL_TRIGGER", "STOP_TRIGGER"}:
            exit_risk_severity = "HIGH"
        elif classification_state == "EXIT_WATCH":
            exit_risk_severity = "MEDIUM"
        else:
            exit_risk_severity = None
        if exit_risk_signal and exit_risk_severity == "HIGH":
            watchlist_status = "HIGH_EXIT_RISK"
        elif exit_risk_signal:
            watchlist_status = "EXIT_RISK"
        elif pullback_signal:
            watchlist_status = "PULLBACK"
        elif breakout_signal:
            watchlist_status = "BREAKOUT"
        else:
            watchlist_status = "WATCH"
        taxonomy_info = taxonomy_lookup.get(entity_id, {})
        subindustry_code = taxonomy_info.get("primary_subindustry")
        layer_code = taxonomy_info.get("primary_layer")
        subindustry_metrics = group_metric_lookup.get(("SUBINDUSTRY", str(subindustry_code))) if subindustry_code else None
        layer_metrics = group_metric_lookup.get(("LAYER", str(layer_code))) if layer_code else None
        row = {
            "ticker": ticker,
            "watchlist_status": watchlist_status,
            "in_datacenter_ecosystem": entity_id in taxonomy_lookup,
            "primary_layer": taxonomy_info.get("primary_layer"),
            "primary_subindustry": taxonomy_info.get("primary_subindustry"),
            "close": None,
            "return_5d": metric_row.get("return_5d"),
            "return_10d": metric_row.get("return_10d"),
            "return_20d": metric_row.get("return_20d"),
            "distance_to_ema20_pct": metric_row.get("distance_to_ema20_pct"),
            "ticker_trend_state": ticker_snapshot_lookup.get(ticker, {}).get("trend_state"),
            "breakout_signal": breakout_signal,
            "pullback_signal": pullback_signal,
            "exit_risk_signal": exit_risk_signal,
            "exit_risk_severity": exit_risk_severity,
            "exit_reason": classification_row.get("blocking_reason") or classification_row.get("primary_reason"),
            "subindustry_timing_state": subindustry_metrics.get("group_timing_state") if subindustry_metrics else None,
            "subindustry_overheat_risk_level": subindustry_metrics.get("group_overheat_risk_level") if subindustry_metrics else None,
            "layer_timing_state": layer_metrics.get("group_timing_state") if layer_metrics else None,
            "layer_overheat_risk_level": layer_metrics.get("group_overheat_risk_level") if layer_metrics else None,
            "price_data_status": coverage_lookup.get(entity_id) or ticker_snapshot_lookup.get(ticker, {}).get("quality_status"),
        }
        rows.append(row)
    severity_order = {
        "HIGH_EXIT_RISK": 0,
        "EXIT_RISK": 1,
        "PULLBACK": 2,
        "BREAKOUT": 3,
        "WATCH": 4,
    }
    rows.sort(
        key=lambda row: (
            severity_order.get(str(row["watchlist_status"]), 99),
            str(row["ticker"]),
        )
    )
    return {
        "counts": {
            "active_watchlist_count": len(rows),
            "in_ecosystem_count": sum(1 for row in rows if row["in_datacenter_ecosystem"]),
            "missing_price_data_count": sum(1 for row in rows if row.get("price_data_status") not in (None, "OK")),
            "breakout_count": sum(1 for row in rows if row.get("breakout_signal") is True),
            "pullback_count": sum(1 for row in rows if row.get("pullback_signal") is True),
            "exit_risk_count": sum(1 for row in rows if row.get("exit_risk_signal") is True),
            "high_exit_risk_count": sum(1 for row in rows if row.get("exit_risk_severity") == "HIGH"),
            "medium_exit_risk_count": sum(1 for row in rows if row.get("exit_risk_severity") == "MEDIUM"),
        },
        "rows": rows,
    }


def _load_daily_ticker_scanners(
    *,
    watchlist_summary: dict[str, Any],
    daily_classifications: list[dict[str, Any]],
    signal_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    watchlist_rows = [dict(row) for row in list(watchlist_summary.get("rows") or [])]
    watchlist_row_by_ticker = {
        str(row.get("ticker") or ""): row
        for row in watchlist_rows
        if row.get("ticker")
    }
    classification_by_ticker = {
        str(row.get("ticker") or ""): row
        for row in daily_classifications
        if row.get("ticker")
    }
    signal_rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in signal_observations:
        ticker = str(row.get("entity_code") or "")
        if ticker:
            signal_rows_by_ticker.setdefault(ticker, []).append(row)

    breakout_candidates = [
        _build_daily_ticker_scanner_row(
            base_row=base_row,
            scanner_type="breakout",
            signal_value=(classification_by_ticker.get(str(base_row.get("ticker") or "")) or {}).get("classification_state"),
            signal_strength=_daily_classification_signal_strength(
                classification_by_ticker.get(str(base_row.get("ticker") or ""))
            ),
            exit_risk_severity=None,
            exit_reason=None,
        )
        for base_row in watchlist_rows
        if base_row.get("breakout_signal") is True
    ]

    pullback_candidates: list[dict[str, Any]] = []
    for ticker, signals in signal_rows_by_ticker.items():
        base_row = watchlist_row_by_ticker.get(ticker)
        if base_row is None:
            continue
        matching_signals = [row for row in signals if _is_daily_pullback_signal(row)]
        if not matching_signals:
            continue
        matching_signals.sort(
            key=lambda row: (
                -_daily_pullback_signal_strength_rank(row),
                str(row.get("signal_name") or ""),
            )
        )
        signal_row = matching_signals[0]
        pullback_candidates.append(
            _build_daily_ticker_scanner_row(
                base_row=base_row,
                scanner_type="pullback",
                signal_value=signal_row.get("signal_value"),
                signal_strength=signal_row.get("signal_name") or signal_row.get("signal_family"),
                exit_risk_severity=None,
                exit_reason=None,
            )
        )

    exit_risk_candidates = [
        _build_daily_ticker_scanner_row(
            base_row=base_row,
            scanner_type="exit_risk",
            signal_value=(classification_by_ticker.get(str(base_row.get("ticker") or "")) or {}).get("classification_state"),
            signal_strength=_daily_classification_signal_strength(
                classification_by_ticker.get(str(base_row.get("ticker") or ""))
            ),
            exit_risk_severity=base_row.get("exit_risk_severity"),
            exit_reason=base_row.get("exit_reason"),
        )
        for base_row in watchlist_rows
        if base_row.get("exit_risk_signal") is True
    ]

    breakout_candidates.sort(
        key=lambda row: (
            -_daily_scanner_strength_rank(row.get("signal_strength")),
            -_number_or_zero(row.get("return_5d")),
            str(row.get("ticker") or ""),
        )
    )
    pullback_candidates.sort(
        key=lambda row: (
            -_daily_scanner_strength_rank(row.get("signal_strength")),
            _distance_abs_sort_value(row.get("distance_to_ema20_pct")),
            str(row.get("ticker") or ""),
        )
    )
    exit_risk_candidates.sort(
        key=lambda row: (
            _exit_risk_severity_rank(row.get("exit_risk_severity")),
            _number_or_zero(row.get("return_5d")),
            str(row.get("ticker") or ""),
        )
    )

    breakout_rows, breakout_rows_available, breakout_is_truncated = _truncate_daily_scanner_rows(breakout_candidates)
    pullback_rows, pullback_rows_available, pullback_is_truncated = _truncate_daily_scanner_rows(pullback_candidates)
    exit_risk_rows, exit_risk_rows_available, exit_risk_is_truncated = _truncate_daily_scanner_rows(exit_risk_candidates)

    return {
        "breakout_rows": breakout_rows,
        "pullback_rows": pullback_rows,
        "exit_risk_rows": exit_risk_rows,
        "breakout_rows_available": breakout_rows_available,
        "pullback_rows_available": pullback_rows_available,
        "exit_risk_rows_available": exit_risk_rows_available,
        "breakout_rows_rendered": len(breakout_rows),
        "pullback_rows_rendered": len(pullback_rows),
        "exit_risk_rows_rendered": len(exit_risk_rows),
        "is_breakout_truncated": breakout_is_truncated,
        "is_pullback_truncated": pullback_is_truncated,
        "is_exit_risk_truncated": exit_risk_is_truncated,
    }


def _build_daily_ticker_scanner_row(
    *,
    base_row: dict[str, Any],
    scanner_type: str,
    signal_value: Any,
    signal_strength: Any,
    exit_risk_severity: Any,
    exit_reason: Any,
) -> dict[str, Any]:
    return {
        "ticker": base_row.get("ticker"),
        "scanner_type": scanner_type,
        "primary_layer": base_row.get("primary_layer"),
        "primary_subindustry": base_row.get("primary_subindustry"),
        "close": base_row.get("close"),
        "return_5d": base_row.get("return_5d"),
        "return_10d": base_row.get("return_10d"),
        "return_20d": base_row.get("return_20d"),
        "distance_to_ema20_pct": base_row.get("distance_to_ema20_pct"),
        "ticker_trend_state": base_row.get("ticker_trend_state"),
        "signal_value": signal_value,
        "signal_strength": signal_strength,
        "exit_risk_severity": exit_risk_severity,
        "exit_reason": exit_reason,
        "subindustry_timing_state": base_row.get("subindustry_timing_state"),
        "subindustry_overheat_risk_level": base_row.get("subindustry_overheat_risk_level"),
        "layer_timing_state": base_row.get("layer_timing_state"),
        "layer_overheat_risk_level": base_row.get("layer_overheat_risk_level"),
        "price_data_status": base_row.get("price_data_status"),
    }


def _daily_classification_signal_strength(classification_row: dict[str, Any] | None) -> Any:
    if not classification_row:
        return None
    return (
        classification_row.get("priority_label")
        or classification_row.get("priority_score")
        or classification_row.get("sort_rank")
    )


def _is_daily_pullback_signal(signal_row: dict[str, Any]) -> bool:
    signal_family = str(signal_row.get("signal_family") or "")
    signal_direction = str(signal_row.get("signal_direction") or "")
    return signal_family == "REVERSAL_MEDIUM" and signal_direction == "UP"


def _daily_pullback_signal_strength_rank(signal_row: dict[str, Any]) -> int:
    return _daily_scanner_strength_rank(signal_row.get("signal_name") or signal_row.get("signal_family"))


def _daily_scanner_strength_rank(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).upper()
    if "STRONG" in text:
        return 3.0
    if "MEDIUM" in text:
        return 2.0
    if "WEAK" in text:
        return 1.0
    return 0.0


def _distance_abs_sort_value(value: Any) -> float:
    if value is None:
        return float("inf")
    return abs(float(value))


def _exit_risk_severity_rank(value: Any) -> int:
    severity_order = {
        "HIGH": 0,
        "MEDIUM": 1,
        "LOW": 2,
    }
    return severity_order.get(str(value or ""), 3)


def _truncate_daily_scanner_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, bool]:
    rows_available = len(rows)
    rows_rendered = rows[:DAILY_TICKER_SCANNER_ROW_LIMIT]
    return rows_rendered, rows_available, rows_available > len(rows_rendered)


def _load_daily_synthetic_ohlc_structure_summary(
    *,
    run_row: sqlite3.Row,
    group_snapshots: list[dict[str, Any]],
    group_metrics: list[dict[str, Any]],
    structural_events: list[dict[str, Any]],
) -> dict[str, Any]:
    signal_date = str(run_row["signal_date"])
    summary_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    group_metric_lookup = {
        (str(row.get("entity_type") or ""), str(row.get("entity_code") or "")): row
        for row in group_metrics
        if str(row.get("entity_type") or "") in {"LAYER", "SUBINDUSTRY"}
    }

    for snapshot in group_snapshots:
        entity_type = str(snapshot.get("entity_type") or "")
        if entity_type not in {"LAYER", "SUBINDUSTRY"}:
            continue
        entity_code = str(snapshot.get("entity_code") or "")
        key = (entity_type, entity_code)
        metric_row = group_metric_lookup.get(key, {})
        summary_by_key[key] = {
            "entity_type": entity_type,
            "entity_code": entity_code,
            "entity_name": snapshot.get("entity_name"),
            "latest_structure_label": snapshot.get("summary_state"),
            "latest_structure_date": signal_date if snapshot.get("summary_state") else None,
            "latest_bos_event_type": None,
            "latest_bos_date": None,
            "latest_reset_reason": None,
            "latest_reset_date": None,
            "structure_freshness": metric_row.get("freshness_latest_structure_class"),
            "bos_freshness": metric_row.get("freshness_latest_bos_class"),
            "reset_freshness": metric_row.get("freshness_latest_reset_class"),
            "timing_state": metric_row.get("group_timing_state") or snapshot.get("timing_state"),
            "overheat_risk_level": metric_row.get("group_overheat_risk_level"),
        }

    for metric_row in group_metrics:
        entity_type = str(metric_row.get("entity_type") or "")
        if entity_type not in {"LAYER", "SUBINDUSTRY"}:
            continue
        entity_code = str(metric_row.get("entity_code") or "")
        key = (entity_type, entity_code)
        row = summary_by_key.setdefault(
            key,
            {
                "entity_type": entity_type,
                "entity_code": entity_code,
                "entity_name": metric_row.get("entity_name"),
                "latest_structure_label": None,
                "latest_structure_date": None,
                "latest_bos_event_type": None,
                "latest_bos_date": None,
                "latest_reset_reason": None,
                "latest_reset_date": None,
                "structure_freshness": None,
                "bos_freshness": None,
                "reset_freshness": None,
                "timing_state": None,
                "overheat_risk_level": None,
            },
        )
        row["structure_freshness"] = row.get("structure_freshness") or metric_row.get("freshness_latest_structure_class")
        row["bos_freshness"] = row.get("bos_freshness") or metric_row.get("freshness_latest_bos_class")
        row["reset_freshness"] = row.get("reset_freshness") or metric_row.get("freshness_latest_reset_class")
        row["timing_state"] = row.get("timing_state") or metric_row.get("group_timing_state")
        row["overheat_risk_level"] = row.get("overheat_risk_level") or metric_row.get("group_overheat_risk_level")

    for event_row in structural_events:
        entity_type = str(event_row.get("entity_type") or "")
        if entity_type not in {"LAYER", "SUBINDUSTRY"}:
            continue
        entity_code = str(event_row.get("entity_code") or "")
        key = (entity_type, entity_code)
        row = summary_by_key.setdefault(
            key,
            {
                "entity_type": entity_type,
                "entity_code": entity_code,
                "entity_name": event_row.get("entity_name"),
                "latest_structure_label": None,
                "latest_structure_date": None,
                "latest_bos_event_type": None,
                "latest_bos_date": None,
                "latest_reset_reason": None,
                "latest_reset_date": None,
                "structure_freshness": None,
                "bos_freshness": None,
                "reset_freshness": None,
                "timing_state": None,
                "overheat_risk_level": None,
            },
        )
        event_type = str(event_row.get("event_type") or "")
        event_date = event_row.get("event_date")
        if event_type == "STRUCTURE_CHANGE" and row.get("latest_structure_date") is None:
            row["latest_structure_label"] = row.get("latest_structure_label") or event_row.get("event_label") or event_type
            row["latest_structure_date"] = event_date
        elif event_type == "BOS" and row.get("latest_bos_date") is None:
            row["latest_bos_event_type"] = event_row.get("event_label") or event_type
            row["latest_bos_date"] = event_date
        elif event_type == "RESET" and row.get("latest_reset_date") is None:
            row["latest_reset_reason"] = event_row.get("event_label") or event_type
            row["latest_reset_date"] = event_date

    rows = [
        row
        for row in summary_by_key.values()
        if any(
            row.get(field)
            for field in (
                "latest_structure_label",
                "latest_bos_event_type",
                "latest_reset_reason",
                "structure_freshness",
                "bos_freshness",
                "reset_freshness",
                "timing_state",
                "overheat_risk_level",
            )
        )
    ]
    rows.sort(
        key=lambda row: (
            ENTITY_TYPE_ORDER.get(str(row.get("entity_type") or ""), 99),
            str(row.get("entity_code") or ""),
            str(row.get("entity_name") or ""),
        )
    )
    rows_available = len(rows)
    rows_rendered = rows[:DAILY_SYNTHETIC_OHLC_STRUCTURE_SUMMARY_ROW_LIMIT]
    return {
        "rows": rows_rendered,
        "rows_available": rows_available,
        "rows_rendered": len(rows_rendered),
        "is_truncated": rows_available > len(rows_rendered),
    }


def _load_rolling_window_summary(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
) -> dict[str, Any]:
    signal_day = str(run_row["signal_date"])
    window_length = WINDOW_DAYS_BY_CODE[window_code]
    included_dates = _load_rolling_metric_dates(
        conn,
        run_id=str(run_row["run_id"]),
        taxonomy_version_id=int(run_row["taxonomy_version_id"]),
        window_code=window_code,
        signal_day=signal_day,
        window_length=window_length,
    )
    if not included_dates:
        included_dates = _load_rolling_fallback_dates(
            conn,
            run_id=str(run_row["run_id"]),
            taxonomy_version_id=int(run_row["taxonomy_version_id"]),
            window_code=window_code,
            signal_day=signal_day,
        )
    return {
        "requested_end_date": signal_day,
        "window_start_date": included_dates[0] if included_dates else None,
        "window_end_date": included_dates[-1] if included_dates else signal_day,
        "valid_signal_dates_count": len(included_dates),
        "valid_signal_dates_included": included_dates,
        "incomplete_window": len(included_dates) < window_length,
    }


def _load_rolling_metric_dates(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    taxonomy_version_id: int,
    window_code: str,
    signal_day: str,
    window_length: int,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT signal_date
        FROM (
            SELECT DISTINCT signal_date
            FROM eco_entity_metric_value
            WHERE run_id = ?
              AND taxonomy_version_id = ?
              AND window_code = ?
              AND signal_date <= ?
            ORDER BY signal_date DESC
            LIMIT ?
        )
        ORDER BY signal_date
        """,
        (run_id, taxonomy_version_id, window_code, signal_day, window_length),
    ).fetchall()
    return [str(row["signal_date"]) for row in rows if row["signal_date"] is not None]


def _load_rolling_fallback_dates(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    taxonomy_version_id: int,
    window_code: str,
    signal_day: str,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT included_date
        FROM (
            SELECT DISTINCT observed_date AS included_date
            FROM eco_signal_observation
            WHERE run_id = ?
              AND taxonomy_version_id = ?
              AND window_code = ?
              AND observed_date <= ?
            UNION
            SELECT DISTINCT event_date AS included_date
            FROM eco_entity_event
            WHERE run_id = ?
              AND taxonomy_version_id = ?
              AND event_date <= ?
        )
        ORDER BY included_date
        """,
        (
            run_id,
            taxonomy_version_id,
            window_code,
            signal_day,
            run_id,
            taxonomy_version_id,
            signal_day,
        ),
    ).fetchall()
    return [str(row["included_date"]) for row in rows if row["included_date"] is not None]


def _load_rolling_ecosystem_window_change(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    window_summary: dict[str, Any],
) -> dict[str, Any]:
    included_dates = list(window_summary.get("valid_signal_dates_included") or [])
    if not included_dates:
        return _empty_ecosystem_window_change()

    metric_name_placeholders = ", ".join("?" for _ in ROLLING_ECOSYSTEM_WINDOW_CHANGE_METRIC_NAMES)
    date_placeholders = ", ".join("?" for _ in included_dates)

    ecosystem_entity_row = conn.execute(
        """
        SELECT entity_id
        FROM eco_entity
        WHERE ecosystem_id = ?
          AND entity_type = 'ECOSYSTEM'
        ORDER BY entity_id
        LIMIT 1
        """,
        (int(run_row["ecosystem_id"]),),
    ).fetchone()
    ecosystem_rows: list[sqlite3.Row] = []
    if ecosystem_entity_row is not None:
        ecosystem_rows = conn.execute(
            f"""
            SELECT
                e.entity_type,
                e.entity_code,
                e.entity_name,
                m.metric_name,
                m.signal_date,
                m.metric_value_num,
                m.metric_value_text
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND m.taxonomy_version_id = ?
              AND m.window_code = ?
              AND m.entity_id = ?
              AND m.metric_name IN ({metric_name_placeholders})
              AND m.signal_date IN ({date_placeholders})
            ORDER BY e.entity_type, e.entity_code, m.metric_name, m.signal_date
            """,
            (
                str(run_row["run_id"]),
                int(run_row["taxonomy_version_id"]),
                window_code,
                int(ecosystem_entity_row["entity_id"]),
                *ROLLING_ECOSYSTEM_WINDOW_CHANGE_METRIC_NAMES,
                *included_dates,
            ),
        ).fetchall()
    if ecosystem_rows:
        return _build_ecosystem_window_change_payload(ecosystem_rows)

    group_rows = conn.execute(
        f"""
        SELECT
            e.entity_type,
            e.entity_code,
            e.entity_name,
            m.metric_name,
            m.signal_date,
            m.metric_value_num,
            m.metric_value_text
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code = ?
          AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
          AND m.metric_name IN ({metric_name_placeholders})
          AND m.signal_date IN ({date_placeholders})
        ORDER BY e.entity_type, e.entity_code, m.metric_name, m.signal_date
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            *ROLLING_ECOSYSTEM_WINDOW_CHANGE_METRIC_NAMES,
            *included_dates,
        ),
    ).fetchall()
    if not group_rows:
        return _empty_ecosystem_window_change()
    return _build_ecosystem_window_change_payload(group_rows)


def _build_ecosystem_window_change_payload(rows: list[sqlite3.Row]) -> dict[str, Any]:
    rows_by_key: dict[tuple[str, str, str, str], list[sqlite3.Row]] = {}
    for row in rows:
        key = (
            str(row["entity_type"]),
            str(row["entity_code"]),
            str(row["entity_name"]),
            str(row["metric_name"]),
        )
        rows_by_key.setdefault(key, []).append(row)

    output_rows: list[dict[str, Any]] = []
    for entity_type, entity_code, entity_name, metric_name in sorted(
        rows_by_key,
        key=lambda item: (
            ENTITY_TYPE_ORDER.get(item[0], 99),
            item[1],
            item[2],
            item[3],
        ),
    ):
        metric_rows = rows_by_key[(entity_type, entity_code, entity_name, metric_name)]
        first_row = metric_rows[0]
        last_row = metric_rows[-1]
        first_value = _metric_row_value(first_row)
        last_value = _metric_row_value(last_row)
        if isinstance(first_value, (int, float)) and isinstance(last_value, (int, float)):
            change: Any = float(last_value) - float(first_value)
        else:
            change = "n/a"
        output_rows.append(
            {
                "entity_type": entity_type,
                "entity_code": entity_code,
                "entity_name": entity_name,
                "metric_name": metric_name,
                "first_date": str(first_row["signal_date"]),
                "first_value": first_value,
                "last_date": str(last_row["signal_date"]),
                "last_value": last_value,
                "change": change,
            }
        )

    rows_available = len(output_rows)
    rows_available_by_entity_type = dict(Counter(row["entity_type"] for row in output_rows))
    rendered_rows = _select_ecosystem_window_change_rows(output_rows)
    rows_rendered_by_entity_type = dict(Counter(row["entity_type"] for row in rendered_rows))
    return {
        "rows": rendered_rows,
        "rows_available": rows_available,
        "rows_rendered": len(rendered_rows),
        "is_truncated": rows_available > len(rendered_rows),
        "rows_available_by_entity_type": rows_available_by_entity_type,
        "rows_rendered_by_entity_type": rows_rendered_by_entity_type,
    }


def _empty_ecosystem_window_change() -> dict[str, Any]:
    return {
        "rows": [],
        "rows_available": 0,
        "rows_rendered": 0,
        "is_truncated": False,
        "rows_available_by_entity_type": {},
        "rows_rendered_by_entity_type": {},
    }


def _load_rolling_overheat_rotation_risk_progression(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    window_summary: dict[str, Any],
) -> dict[str, Any]:
    included_dates = list(window_summary.get("valid_signal_dates_included") or [])
    if not included_dates:
        return _empty_overheat_rotation_risk_progression()

    date_placeholders = ", ".join("?" for _ in included_dates)
    rows = conn.execute(
        f"""
        SELECT
            e.entity_type,
            e.entity_code,
            e.entity_name,
            m.metric_name,
            m.signal_date,
            m.metric_value_num,
            m.metric_value_text
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code = ?
          AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
          AND m.metric_name IN ('group_overheat_risk_level', 'group_timing_state')
          AND m.signal_date IN ({date_placeholders})
        ORDER BY m.signal_date, e.entity_type, e.entity_code, m.metric_name
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            *included_dates,
        ),
    ).fetchall()
    return _build_overheat_rotation_risk_progression_payload(rows, included_dates)


def _build_overheat_rotation_risk_progression_payload(
    rows: list[Any],
    included_dates: list[str],
) -> dict[str, Any]:
    per_entity: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    risk_counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        entity_type = str(row["entity_type"])
        entity_code = str(row["entity_code"])
        entity_name = str(row["entity_name"])
        metric_name = str(row["metric_name"])
        signal_date = str(row["signal_date"])
        metric_value = _metric_row_value(row)
        per_date = per_entity.setdefault((entity_type, entity_code, entity_name), {})
        per_date.setdefault(signal_date, {})[metric_name] = metric_value
        if metric_name == "group_overheat_risk_level":
            risk_counts[(signal_date, entity_type, str(metric_value))] += 1

    risk_count_rows = [
        {
            "signal_date": signal_date,
            "entity_type": entity_type,
            "risk_level": risk_level,
            "group_count": group_count,
        }
        for signal_date, entity_type, risk_level, group_count in sorted(
            (
                (signal_date, entity_type, risk_level, group_count)
                for (signal_date, entity_type, risk_level), group_count in risk_counts.items()
            ),
            key=lambda item: (
                item[0],
                item[1],
                RISK_LEVEL_ORDER.get(item[2], 99),
                item[2],
            ),
        )
    ]

    progression_rows: list[dict[str, Any]] = []
    for entity_type, entity_code, entity_name in sorted(
        per_entity,
        key=lambda item: (item[0], item[1], item[2]),
    ):
        date_values = per_entity[(entity_type, entity_code, entity_name)]
        risk_dates = [
            signal_date
            for signal_date in included_dates
            if date_values.get(signal_date, {}).get("group_overheat_risk_level") is not None
        ]
        if not risk_dates:
            continue
        first_date = risk_dates[0]
        last_date = risk_dates[-1]
        first_risk_level = date_values[first_date].get("group_overheat_risk_level")
        last_risk_level = date_values[last_date].get("group_overheat_risk_level")
        risk_change = _calculate_risk_change(first_risk_level, last_risk_level)
        row = {
            "entity_type": entity_type,
            "entity_code": entity_code,
            "entity_name": entity_name,
            "first_date": first_date,
            "first_risk_level": first_risk_level,
            "last_date": last_date,
            "last_risk_level": last_risk_level,
            "risk_change": risk_change,
            "first_timing_state": date_values.get(first_date, {}).get("group_timing_state"),
            "last_timing_state": date_values.get(last_date, {}).get("group_timing_state"),
        }
        if str(last_risk_level) != "LOW" or risk_change == "WORSENED":
            progression_rows.append(row)

    progression_rows.sort(
        key=lambda row: (
            RISK_CHANGE_ORDER.get(str(row["risk_change"]), 99),
            _last_risk_sort_value(row["last_risk_level"]),
            row["entity_type"],
            row["entity_code"],
            row["entity_name"],
        )
    )
    progression_rows_available = len(progression_rows)
    rendered_rows = progression_rows[:ROLLING_RISK_PROGRESSION_ROW_LIMIT]
    return {
        "risk_count_rows": risk_count_rows,
        "risk_progression_rows": rendered_rows,
        "progression_rows_available": progression_rows_available,
        "progression_rows_rendered": len(rendered_rows),
        "is_truncated": progression_rows_available > len(rendered_rows),
    }


def _empty_overheat_rotation_risk_progression() -> dict[str, Any]:
    return {
        "risk_count_rows": [],
        "risk_progression_rows": [],
        "progression_rows_available": 0,
        "progression_rows_rendered": 0,
        "is_truncated": False,
    }


def _load_rolling_subindustry_timing_persistence(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    window_summary: dict[str, Any],
) -> dict[str, Any]:
    included_dates = list(window_summary.get("valid_signal_dates_included") or [])
    if not included_dates:
        return _empty_subindustry_timing_persistence(len(included_dates))

    date_placeholders = ", ".join("?" for _ in included_dates)
    rows = conn.execute(
        f"""
        SELECT
            e.entity_type,
            e.entity_code,
            e.entity_name,
            m.metric_name,
            m.signal_date,
            m.metric_value_num,
            m.metric_value_text
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code = ?
          AND e.entity_type = 'SUBINDUSTRY'
          AND m.metric_name IN ('group_timing_state', 'group_overheat_risk_level')
          AND m.signal_date IN ({date_placeholders})
        ORDER BY e.entity_code, m.signal_date, m.metric_name
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            *included_dates,
        ),
    ).fetchall()
    return _build_subindustry_timing_persistence_payload(rows, included_dates)


def _build_subindustry_timing_persistence_payload(
    rows: list[Any],
    included_dates: list[str],
) -> dict[str, Any]:
    by_entity: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        entity_key = (
            str(row["entity_type"]),
            str(row["entity_code"]),
            str(row["entity_name"]),
        )
        signal_date = str(row["signal_date"])
        metric_name = str(row["metric_name"])
        metric_value = _metric_row_value(row)
        by_entity.setdefault(entity_key, {}).setdefault(signal_date, {})[metric_name] = metric_value

    output_rows: list[dict[str, Any]] = []
    selected_dates_count = len(included_dates)
    for entity_type, entity_code, entity_name in by_entity:
        per_date = by_entity[(entity_type, entity_code, entity_name)]
        timing_dates = [
            signal_date
            for signal_date in included_dates
            if per_date.get(signal_date, {}).get("group_timing_state") is not None
        ]
        if not timing_dates:
            continue
        row = {
            "entity_type": entity_type,
            "entity_code": entity_code,
            "entity_name": entity_name,
            "selected_dates_count": selected_dates_count,
            "observed_timing_dates_count": len(timing_dates),
            "buy_zone_days": 0,
            "add_on_pullback_days": 0,
            "trim_watch_days": 0,
            "exit_zone_days": 0,
            "neutral_days": 0,
            "other_timing_days": 0,
            "first_date": timing_dates[0],
            "first_timing_state": per_date[timing_dates[0]].get("group_timing_state"),
            "last_date": timing_dates[-1],
            "last_timing_state": per_date[timing_dates[-1]].get("group_timing_state"),
            "last_overheat_risk_level": _latest_metric_value(per_date, included_dates, "group_overheat_risk_level"),
        }
        for signal_date in timing_dates:
            timing_state = per_date[signal_date].get("group_timing_state")
            bucket_name = TIMING_STATE_BUCKETS.get(str(timing_state))
            if bucket_name is None:
                row["other_timing_days"] += 1
            else:
                row[bucket_name] += 1
        output_rows.append(row)

    output_rows.sort(
        key=lambda row: (
            -int(row["exit_zone_days"]),
            -int(row["trim_watch_days"]),
            -int(row["add_on_pullback_days"]),
            -int(row["buy_zone_days"]),
            -int(row["other_timing_days"]),
            str(row["last_timing_state"]),
            str(row["entity_code"]),
            str(row["entity_name"]),
        )
    )
    rows_available = len(output_rows)
    rendered_rows = output_rows[:ROLLING_SUBINDUSTRY_TIMING_PERSISTENCE_ROW_LIMIT]
    return {
        "rows": rendered_rows,
        "rows_available": rows_available,
        "rows_rendered": len(rendered_rows),
        "is_truncated": rows_available > len(rendered_rows),
        "selected_dates_count": selected_dates_count,
    }


def _empty_subindustry_timing_persistence(selected_dates_count: int) -> dict[str, Any]:
    return {
        "rows": [],
        "rows_available": 0,
        "rows_rendered": 0,
        "is_truncated": False,
        "selected_dates_count": selected_dates_count,
    }


def _load_rolling_subindustry_improvement_deterioration(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    window_code: str,
    window_summary: dict[str, Any],
) -> dict[str, Any]:
    included_dates = list(window_summary.get("valid_signal_dates_included") or [])
    if not included_dates:
        return _empty_subindustry_improvement_deterioration(len(included_dates))

    metric_placeholders = ", ".join("?" for _ in ROLLING_SUBINDUSTRY_IMPROVEMENT_DETERIORATION_METRIC_NAMES)
    date_placeholders = ", ".join("?" for _ in included_dates)
    rows = conn.execute(
        f"""
        SELECT
            e.entity_type,
            e.entity_code,
            e.entity_name,
            m.metric_name,
            m.signal_date,
            m.metric_value_num,
            m.metric_value_text
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code = ?
          AND e.entity_type = 'SUBINDUSTRY'
          AND m.metric_name IN ({metric_placeholders})
          AND m.signal_date IN ({date_placeholders})
        ORDER BY e.entity_code, m.metric_name, m.signal_date
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            *ROLLING_SUBINDUSTRY_IMPROVEMENT_DETERIORATION_METRIC_NAMES,
            *included_dates,
        ),
    ).fetchall()
    return _build_subindustry_improvement_deterioration_payload(rows, included_dates)


def _build_subindustry_improvement_deterioration_payload(
    rows: list[Any],
    included_dates: list[str],
) -> dict[str, Any]:
    by_entity_metric: dict[tuple[str, str, str, str], dict[str, float]] = {}
    for row in rows:
        if row["metric_value_num"] is None:
            continue
        entity_key = (
            str(row["entity_type"]),
            str(row["entity_code"]),
            str(row["entity_name"]),
            str(row["metric_name"]),
        )
        by_entity_metric.setdefault(entity_key, {})[str(row["signal_date"])] = float(row["metric_value_num"])

    output_rows: list[dict[str, Any]] = []
    selected_dates_count = len(included_dates)
    for entity_type, entity_code, entity_name, metric_name in sorted(
        by_entity_metric,
        key=lambda item: (item[1], item[3], item[2]),
    ):
        per_date = by_entity_metric[(entity_type, entity_code, entity_name, metric_name)]
        metric_dates = [signal_date for signal_date in included_dates if signal_date in per_date]
        if not metric_dates:
            continue
        first_date = metric_dates[0]
        last_date = metric_dates[-1]
        first_value = per_date[first_date]
        last_value = per_date[last_date]
        change = float(last_value - first_value)
        change_pct: float | str
        if first_value == 0:
            change_pct = "n/a"
        else:
            change_pct = float(((last_value - first_value) / abs(first_value)) * 100.0)
        direction = _calculate_numeric_direction(change)
        output_rows.append(
            {
                "entity_type": entity_type,
                "entity_code": entity_code,
                "entity_name": entity_name,
                "metric_name": metric_name,
                "first_date": first_date,
                "first_value": first_value,
                "last_date": last_date,
                "last_value": last_value,
                "change": change,
                "change_pct": change_pct,
                "direction": direction,
                "_abs_change": abs(change),
                "_observed_dates_count": len(metric_dates),
            }
        )

    rows_with_multiple_dates = [row for row in output_rows if int(row["_observed_dates_count"]) >= 2]
    rows_for_render = rows_with_multiple_dates or output_rows
    rows_available = len(rows_for_render)
    rows_available_by_direction = _count_rows_by_direction(rows_for_render)
    selected_rows = _select_subindustry_improvement_deterioration_rows(rows_for_render)
    rendered_rows = selected_rows[:ROLLING_SUBINDUSTRY_IMPROVEMENT_DETERIORATION_ROW_LIMIT]
    rows_rendered_by_direction = _count_rows_by_direction(rendered_rows)
    for row in rendered_rows:
        row.pop("_abs_change", None)
        row.pop("_observed_dates_count", None)
    return {
        "rows": rendered_rows,
        "rows_available": rows_available,
        "rows_available_by_direction": rows_available_by_direction,
        "rows_rendered": len(rendered_rows),
        "rows_rendered_by_direction": rows_rendered_by_direction,
        "is_truncated": rows_available > len(rendered_rows),
        "selected_dates_count": selected_dates_count,
    }


def _empty_subindustry_improvement_deterioration(selected_dates_count: int) -> dict[str, Any]:
    return {
        "rows": [],
        "rows_available": 0,
        "rows_available_by_direction": {},
        "rows_rendered": 0,
        "rows_rendered_by_direction": {},
        "is_truncated": False,
        "selected_dates_count": selected_dates_count,
    }


def _count_rows_by_direction(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        direction = str(row.get("direction") or "n/a")
        counts[direction] = counts.get(direction, 0) + 1
    return counts


def _sort_subindustry_improvement_deterioration_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -float(row["_abs_change"]),
            str(row["entity_code"]),
            str(row["metric_name"]),
        ),
    )


def _select_subindustry_improvement_deterioration_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_direction = {
        direction: _sort_subindustry_improvement_deterioration_rows(
            [row for row in rows if str(row.get("direction") or "n/a") == direction]
        )
        for direction in ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_PRIORITY
    }
    selected_rows: list[dict[str, Any]] = []
    selected_counts = {direction: 0 for direction in ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_PRIORITY}

    for direction in ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_PRIORITY:
        direction_rows = rows_by_direction[direction]
        share = ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_SHARES[direction]
        take_count = min(len(direction_rows), share)
        if take_count <= 0:
            continue
        selected_rows.extend(direction_rows[:take_count])
        selected_counts[direction] = take_count

    remaining_capacity = ROLLING_SUBINDUSTRY_IMPROVEMENT_DETERIORATION_ROW_LIMIT - len(selected_rows)
    if remaining_capacity > 0:
        for direction in ROLLING_SUBINDUSTRY_IMPROVEMENT_DIRECTION_PRIORITY:
            if remaining_capacity <= 0:
                break
            direction_rows = rows_by_direction[direction]
            start_index = selected_counts[direction]
            extra_rows = direction_rows[start_index : start_index + remaining_capacity]
            if not extra_rows:
                continue
            selected_rows.extend(extra_rows)
            selected_counts[direction] += len(extra_rows)
            remaining_capacity -= len(extra_rows)

    selected_row_ids = {id(row) for row in selected_rows}
    return sorted(
        [row for row in rows if id(row) in selected_row_ids],
        key=lambda row: (
            _direction_sort_value(row.get("direction")),
            -float(row["_abs_change"]),
            str(row["entity_code"]),
            str(row["metric_name"]),
        ),
    )


def _select_ecosystem_window_change_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) <= ROLLING_ECOSYSTEM_WINDOW_CHANGE_ROW_LIMIT:
        return rows

    rows_by_entity_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_entity_type.setdefault(str(row["entity_type"]), []).append(row)

    layer_rows = rows_by_entity_type.get("LAYER", [])
    subindustry_rows = rows_by_entity_type.get("SUBINDUSTRY", [])
    if layer_rows and subindustry_rows:
        layer_share = ROLLING_ECOSYSTEM_WINDOW_CHANGE_ROW_LIMIT // 2
        subindustry_share = ROLLING_ECOSYSTEM_WINDOW_CHANGE_ROW_LIMIT - layer_share
        selected_layer = layer_rows[:layer_share]
        selected_subindustry = subindustry_rows[:subindustry_share]
        remaining_capacity = ROLLING_ECOSYSTEM_WINDOW_CHANGE_ROW_LIMIT - (
            len(selected_layer) + len(selected_subindustry)
        )
        if remaining_capacity > 0:
            layer_remaining = layer_rows[len(selected_layer) :]
            subindustry_remaining = subindustry_rows[len(selected_subindustry) :]
            if len(selected_layer) < layer_share:
                selected_subindustry.extend(subindustry_remaining[:remaining_capacity])
            else:
                selected_layer.extend(layer_remaining[:remaining_capacity])
        return selected_layer + selected_subindustry

    return rows[:ROLLING_ECOSYSTEM_WINDOW_CHANGE_ROW_LIMIT]


def _metric_row_value(row: sqlite3.Row) -> Any:
    if row["metric_value_num"] is not None:
        return row["metric_value_num"]
    return row["metric_value_text"]


def _calculate_risk_change(first_risk_level: Any, last_risk_level: Any) -> str:
    first_rank = RISK_LEVEL_ORDER.get(str(first_risk_level))
    last_rank = RISK_LEVEL_ORDER.get(str(last_risk_level))
    if first_rank is None or last_rank is None:
        return "n/a"
    if last_rank > first_rank:
        return "WORSENED"
    if last_rank < first_rank:
        return "IMPROVED"
    return "UNCHANGED"


def _calculate_numeric_direction(change: Any) -> str:
    if not isinstance(change, (int, float)):
        return "n/a"
    if change > 0:
        return "IMPROVED"
    if change < 0:
        return "DETERIORATED"
    return "UNCHANGED"


def _direction_sort_value(direction: Any) -> int:
    direction_label = str(direction)
    if direction_label == "DETERIORATED":
        return 0
    if direction_label == "IMPROVED":
        return 1
    if direction_label == "UNCHANGED":
        return 2
    return 3


def _last_risk_sort_value(risk_level: Any) -> tuple[int, str]:
    risk_label = str(risk_level)
    if risk_label in {"HIGH", "MEDIUM", "LOW"}:
        return (-RISK_LEVEL_ORDER[risk_label], risk_label)
    return (99, risk_label)


def _latest_metric_value(
    per_date: dict[str, dict[str, Any]],
    included_dates: list[str],
    metric_name: str,
) -> Any:
    for signal_date in reversed(included_dates):
        value = per_date.get(signal_date, {}).get(metric_name)
        if value is not None:
            return value
    return None


def _load_structural_events(conn: sqlite3.Connection, run_row: sqlite3.Row, window_code: str) -> list[dict[str, Any]]:
    signal_day = date.fromisoformat(str(run_row["signal_date"]))
    start_day = signal_day - timedelta(days=WINDOW_DAYS_BY_CODE[window_code] - 1)
    rows = [
        _row_to_dict(row)
        for row in conn.execute(
            f"""
            SELECT
                e.entity_type,
                e.entity_code,
                e.entity_name,
                ev.event_date,
                ev.event_type,
                ev.event_label,
                ev.event_direction,
                ev.event_status,
                ev.source_run_id,
                ev.source_event_id
            FROM eco_entity_event ev
            JOIN eco_entity e ON e.entity_id = ev.entity_id
            WHERE ev.run_id = ?
              AND ev.taxonomy_version_id = ?
              AND ev.event_type IN ({", ".join("?" for _ in STRUCTURAL_EVENT_TYPES)})
              AND ev.event_date >= ?
              AND ev.event_date <= ?
            ORDER BY ev.event_date DESC, e.entity_code, ev.event_type
            """,
            (
                str(run_row["run_id"]),
                int(run_row["taxonomy_version_id"]),
                *STRUCTURAL_EVENT_TYPES,
                start_day.isoformat(),
                signal_day.isoformat(),
            ),
        ).fetchall()
    ]
    return rows


def _load_signal_observations(conn: sqlite3.Connection, run_row: sqlite3.Row, window_code: str) -> list[dict[str, Any]]:
    rows = [
        _row_to_dict(row)
        for row in conn.execute(
            """
            SELECT
                e.entity_code,
                e.entity_name,
                so.signal_name,
                so.signal_family,
                so.signal_direction,
                so.signal_value,
                so.observed_date,
                so.signal_status,
                so.source_run_id,
                GROUP_CONCAT(sr.relevance_label) AS relevance_labels,
                GROUP_CONCAT(sr.relevance_reason) AS relevance_reasons
            FROM eco_signal_observation so
            JOIN eco_entity e ON e.entity_id = so.entity_id
            LEFT JOIN eco_signal_relevance sr ON sr.signal_observation_id = so.signal_observation_id
            WHERE so.run_id = ?
              AND so.signal_date = ?
              AND so.taxonomy_version_id = ?
              AND so.window_code = ?
            GROUP BY
                so.signal_observation_id,
                e.entity_code,
                e.entity_name,
                so.signal_name,
                so.signal_family,
                so.signal_direction,
                so.signal_value,
                so.observed_date,
                so.signal_status,
                so.source_run_id
            ORDER BY so.observed_date DESC, e.entity_code, so.signal_name
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                window_code,
            ),
        ).fetchall()
    ]
    return rows


def _build_metadata(
    *,
    window_code: str,
    ticker_snapshots: list[dict[str, Any]],
    classification_rows: list[dict[str, Any]],
    signal_observations: list[dict[str, Any]],
    structural_events: list[dict[str, Any]],
) -> dict[str, Any]:
    classified_tickers = {str(row["ticker"]) for row in classification_rows}
    coverage_without_classification = sorted(
        str(row["entity_code"])
        for row in ticker_snapshots
        if str(row["entity_code"]) not in classified_tickers
    )
    ranking_non_null_count = sum(
        1
        for row in classification_rows
        if row.get("priority_score") is not None or row.get("priority_label") is not None or row.get("sort_rank") is not None
    )
    signal_names = sorted({str(row["signal_name"]) for row in signal_observations})
    window_prefix = _window_prefix(window_code)
    signal_scope = "daily_signal_observation_and_optional_relevance" if window_code == DAILY_WINDOW_CODE else "window_native_only"
    limitations = [
        "generated Markdown/CSV reports were not used as source data",
        "dashboard-rendered output was not used as source data",
        f"{window_prefix} classifications are read from eco_classification_decision",
        (
            "eco_entity_window_snapshot.classification_state is not used as the rolling30 classification source"
            if window_prefix == "rolling30"
            else f"eco_entity_window_snapshot.classification_state is not used as the primary {window_prefix} classification source"
        ),
        "ranking fields are mostly NULL; deterministic fallback ordering is used",
        (
            "daily signal observations come from eco_signal_observation and optional eco_signal_relevance"
            if window_code == DAILY_WINDOW_CODE
            else f"{window_prefix} notable technical signals are limited unless a later daily signal join is added"
        ),
        (
            "CRGY is intentionally materialized as INSUFFICIENT_DATA in daily_trigger"
            if window_code == DAILY_WINDOW_CODE
            else f"coverage or snapshot rows can exist without {window_prefix} classification rows, for example CRGY-like cases"
        ),
        (
            "NXPI reflects accepted current lower-level source-truth SELL_TRIGGER semantics"
            if window_code == DAILY_WINDOW_CODE
            else None
        ),
        (
            "daily signal observations may include actual daily-observed technical signals; no signals are invented"
            if window_code == DAILY_WINDOW_CODE
            else (
                f"{window_prefix} signal observations are limited to {window_prefix}-compatible observations; "
                "daily candlestick/divergence semantics are not invented"
            )
        ),
        "no V2 report/context tables were used",
    ]
    return {
        "used_v2_runtime_tables": False,
        "used_generated_reports": False,
        "used_dashboard_output": False,
        f"{window_prefix}_classification_source": "eco_classification_decision",
        f"{window_prefix}_snapshot_classification_source_used": False,
        f"{window_prefix}_event_window_mode": _event_window_mode(window_code),
        f"{window_prefix}_signal_scope": signal_scope,
        "ranking_fields_mostly_null": ranking_non_null_count == 0,
        "coverage_without_classification_tickers": coverage_without_classification,
        "signal_names_present": signal_names,
        "structural_event_types_present": sorted({str(row["event_type"]) for row in structural_events}),
        "limitations": [item for item in limitations if item is not None],
    }


def _window_prefix(window_code: str) -> str:
    if window_code == DAILY_WINDOW_CODE:
        return "daily"
    if window_code == ROLLING30_WINDOW_CODE:
        return "rolling30"
    if window_code == ROLLING5_WINDOW_CODE:
        return "rolling5"
    if window_code == ROLLING2_WINDOW_CODE:
        return "rolling2"
    raise ValueError(f"Unsupported reporting window_code '{window_code}'")


def _event_window_mode(window_code: str) -> str:
    if window_code == DAILY_WINDOW_CODE:
        return "event_date_range_signal_day_only"
    if window_code == ROLLING30_WINDOW_CODE:
        return "event_date_range_within_30d_window"
    if window_code == ROLLING5_WINDOW_CODE:
        return "event_date_range_within_5d_window"
    if window_code == ROLLING2_WINDOW_CODE:
        return "event_date_range_within_2d_window"
    raise ValueError(f"Unsupported reporting window_code '{window_code}'")
