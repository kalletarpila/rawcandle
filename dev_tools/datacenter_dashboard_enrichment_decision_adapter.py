from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_parser import DatacenterDashboardRow


ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
SOURCE_FILE = "analysis-db://dashboard-enrichment"
SECTION = "ticker_enrichment"
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
HORIZON_SOURCE_FIELDS: tuple[tuple[str, str], ...] = (
    ("rolling_2d_status", "rolling 2d"),
    ("rolling_5d_status", "rolling 5d"),
    ("rolling_30d_status", "rolling 30d"),
)
RAW_FIELD_NAMES: tuple[str, ...] = (
    "severity",
    "primary_reason",
    "current_status",
    "start_status_30d",
    "status_change_30d",
    "status_change_5d",
    "window_status_30d",
    "window_status_5d",
    "window_status_2d",
    "ma_break_status",
    "freshness_status",
    "trend_state",
    "latest_structure_label",
    "latest_bos_event_type",
    "latest_reset_reason",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "horizons_present",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
    "candidate_priority_label",
    "distance_to_ema20",
    "pullback_days",
    "high_exit_risk_days_count",
    "blocking_reasons",
    "ema20_break_confirmed",
    "sma50_break_confirmed",
    "close_below_ema20",
    "close_below_sma50",
    "consecutive_closes_below_ema20",
    "consecutive_closes_below_sma50",
    "ema20_break_pct",
    "sma50_break_pct",
    "structure_warning_overrides_bullish_signal",
    "latest_bullish_signal_age_td",
    "latest_bearish_signal_age_td",
    "latest_bos_up_age_td",
    "latest_bos_down_age_td",
    "latest_reset_age_td",
)


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_float(value: object) -> float | None:
    text = _normalized_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_int(value: object) -> int | None:
    text = _normalized_text(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _is_valid_ticker(value: object) -> bool:
    ticker = _normalized_text(value)
    if ticker is None:
        return False
    normalized = ticker.upper()
    if DATE_RE.match(normalized):
        return False
    if " " in normalized:
        return False
    if not VALID_TICKER_RE.match(normalized):
        return False
    if normalized in DISALLOWED_TICKER_LABELS:
        return False
    return True


def _raw_fields_from_row(
    row: dict[str, object],
    *,
    horizon_source_field: str | None = None,
) -> dict[str, str]:
    raw_fields: dict[str, str] = {}
    for key in RAW_FIELD_NAMES:
        value = row.get(key)
        text = _normalized_text(value)
        if text is not None:
            raw_fields[key] = text
    if horizon_source_field is not None:
        raw_fields["horizon_source"] = horizon_source_field
    return raw_fields


def _build_row(
    *,
    row: dict[str, object],
    horizon: str,
    row_kind: str,
    raw_status: str | None,
    horizon_source_field: str | None = None,
) -> DatacenterDashboardRow:
    raw_fields = _raw_fields_from_row(row, horizon_source_field=horizon_source_field)
    return DatacenterDashboardRow(
        ticker=str(_normalized_text(row.get("ticker"))).upper(),
        horizon=horizon,
        source_file=SOURCE_FILE,
        section=SECTION,
        row_kind=row_kind,
        raw_action=None,
        raw_status=raw_status,
        reason=_normalized_text(row.get("primary_reason")),
        trend_state=_normalized_text(row.get("trend_state")),
        latest_structure_label=_normalized_text(row.get("latest_structure_label")),
        latest_bos_event_type=_normalized_text(row.get("latest_bos_event_type")),
        latest_reset_reason=_normalized_text(row.get("latest_reset_reason")),
        distance_to_ema20=_safe_float(row.get("distance_to_ema20")),
        high_exit_risk_days_count=_safe_int(row.get("high_exit_risk_days_count")),
        blocking_reasons=_normalized_text(row.get("blocking_reasons")),
        ma_break_status=_normalized_text(row.get("ma_break_status")),
        ema20_break_confirmed=_safe_int(row.get("ema20_break_confirmed")),
        sma50_break_confirmed=_safe_int(row.get("sma50_break_confirmed")),
        close_below_ema20=_safe_int(row.get("close_below_ema20")),
        close_below_sma50=_safe_int(row.get("close_below_sma50")),
        consecutive_closes_below_ema20=_safe_int(row.get("consecutive_closes_below_ema20")),
        consecutive_closes_below_sma50=_safe_int(row.get("consecutive_closes_below_sma50")),
        ema20_break_pct=_safe_float(row.get("ema20_break_pct")),
        sma50_break_pct=_safe_float(row.get("sma50_break_pct")),
        freshness_status=_normalized_text(row.get("freshness_status")),
        structure_warning_overrides_bullish_signal=_safe_int(
            row.get("structure_warning_overrides_bullish_signal")
        ),
        latest_bullish_signal_age_td=_safe_int(row.get("latest_bullish_signal_age_td")),
        latest_bearish_signal_age_td=_safe_int(row.get("latest_bearish_signal_age_td")),
        latest_bos_up_age_td=_safe_int(row.get("latest_bos_up_age_td")),
        latest_bos_down_age_td=_safe_int(row.get("latest_bos_down_age_td")),
        latest_reset_age_td=_safe_int(row.get("latest_reset_age_td")),
        raw_fields=raw_fields,
    )


def build_dashboard_rows_from_ticker_enrichment_rows(
    rows: list[dict[str, object]],
) -> list[DatacenterDashboardRow]:
    dashboard_rows: list[DatacenterDashboardRow] = []
    for row in rows:
        if not _is_valid_ticker(row.get("ticker")):
            continue
        daily_status = _normalized_text(row.get("daily_status"))
        current_status = _normalized_text(row.get("current_status"))
        base_status = daily_status or current_status
        base_horizon_source = None
        if daily_status is not None:
            base_horizon_source = "daily_status"
        elif current_status is not None:
            base_horizon_source = "current_status"
        dashboard_rows.append(
            _build_row(
                row=row,
                horizon="daily",
                row_kind="ticker_enrichment_base",
                raw_status=base_status,
                horizon_source_field=base_horizon_source,
            )
        )
        for source_field, horizon in HORIZON_SOURCE_FIELDS:
            status_value = _normalized_text(row.get(source_field))
            if status_value is None:
                continue
            dashboard_rows.append(
                _build_row(
                    row=row,
                    horizon=horizon,
                    row_kind="ticker_enrichment_horizon",
                    raw_status=status_value,
                    horizon_source_field=source_field,
                )
            )
    return dashboard_rows


def build_decisions_from_ticker_enrichment_rows(rows: list[dict[str, object]]):
    dashboard_rows = build_dashboard_rows_from_ticker_enrichment_rows(rows)
    return build_datacenter_ticker_decisions(dashboard_rows)


def load_ticker_enrichment_rows(
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    normalized = analysis_db.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    db_path = Path(normalized)
    if not db_path.exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    with sqlite3.connect(f"file:{normalized}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table_row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (ENRICHMENT_TABLE,),
        ).fetchone()
        if table_row is None:
            raise ValueError(f"missing required source table: {ENRICHMENT_TABLE}")
        selected_rows = conn.execute(
            f"""
            SELECT *
            FROM {ENRICHMENT_TABLE}
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY ticker ASC
            """,
            (signal_date, taxonomy_version),
        ).fetchall()
    return [dict(row) for row in selected_rows]
