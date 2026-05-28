from __future__ import annotations

import json
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
    "breakout_days",
    "fast_ema10_pullback_days",
    "conservative_ema20_pullback_days",
    "current_watchlist_status",
    "window_watchlist_status",
    "high_exit_risk_days_count",
    "high_exit_risk_days",
    "medium_exit_risk_days",
    "exit_risk_days",
    "blocking_reasons",
    "rolling_2_sell_pressure_state",
    "risk_reason",
    "latest_exit_risk_severity",
    "latest_bearish_relevance_reason",
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
    "latest_bos_freshness",
    "latest_reset_freshness",
    "latest_bullish_relevance_class",
    "latest_bullish_relevance_reason",
    "latest_bearish_relevance_class",
    "latest_bearish_relevance_reason",
    "rolling_5_pullback_state",
    "rolling_30_buy_state",
    "blocking_reason",
    "next_action",
    "rolling_5d_primary_reason",
    "rolling_5d_blocking_reason",
    "exit_reason",
    "last_exit_reason",
    "latest_exit_reason",
    "latest_bos_up_age_td",
    "latest_bos_down_age_td",
    "latest_reset_age_td",
)
UPSTREAM_ROLLING5_PAYLOAD_PREFIX = "UPSTREAM_ROLLING5_JSON:"
MA_BREAK_PAYLOAD_KEY = "ma_break"
FRESHNESS_PAYLOAD_KEY = "freshness"
ROLLING2_PAYLOAD_KEY = "rolling2"
ROLLING30_PAYLOAD_KEY = "rolling30"


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


def _decoded_payload(row: dict[str, object]) -> dict[str, object]:
    source_run_ids = _normalized_text(row.get("source_run_ids"))
    if source_run_ids is None or not source_run_ids.startswith(UPSTREAM_ROLLING5_PAYLOAD_PREFIX):
        return {}
    try:
        payload = json.loads(source_run_ids[len(UPSTREAM_ROLLING5_PAYLOAD_PREFIX):])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ma_break_payload(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get(MA_BREAK_PAYLOAD_KEY)
    return value if isinstance(value, dict) else {}


def _freshness_payload(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get(FRESHNESS_PAYLOAD_KEY)
    return value if isinstance(value, dict) else {}


def _rolling2_payload(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get(ROLLING2_PAYLOAD_KEY)
    return value if isinstance(value, dict) else {}


def _rolling30_payload(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get(ROLLING30_PAYLOAD_KEY)
    return value if isinstance(value, dict) else {}


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
    payload = _decoded_payload(row)
    for key, value in payload.items():
        if isinstance(value, dict):
            continue
        text = _normalized_text(value)
        if text is not None:
            raw_fields[key] = text
    ma_break = _ma_break_payload(payload)
    for key, value in ma_break.items():
        text = _normalized_text(value)
        if text is not None:
            raw_fields[key] = text
    freshness = _freshness_payload(payload)
    for key, value in freshness.items():
        text = _normalized_text(value)
        if text is not None:
            raw_fields[key] = text
    for field_name in ("close_below_ema20", "close_below_sma50", "ema20_break_confirmed", "sma50_break_confirmed"):
        if _safe_int(ma_break.get(field_name)) == 1:
            raw_fields[f"{field_name}_token"] = field_name
    rolling_5d_status = _normalized_text(row.get("rolling_5d_status"))
    freshness_status = _normalized_text(row.get("freshness_status"))
    if "pullback_days" not in raw_fields and rolling_5d_status in {
        "PULLBACK_CANDIDATE",
        "FAILED_PULLBACK",
    }:
        raw_fields["pullback_days"] = "1"
    if (
        "latest_bullish_signal_age_td" not in raw_fields
        and freshness_status == "FRESH_BULLISH_SIGNAL"
    ):
        raw_fields["latest_bullish_signal_age_td"] = "0"
    if horizon_source_field is not None:
        raw_fields["horizon_source"] = horizon_source_field
    return raw_fields


def _upstream_rolling5_payload(row: dict[str, object]) -> dict[str, object]:
    payload = _decoded_payload(row)
    if not isinstance(payload, dict):
        return {}
    if any(
        _normalized_text(payload.get(key)) is not None
        for key in (
            "rolling_5_pullback_state",
            "rolling_5d_status",
            "rolling_5d_primary_reason",
            "rolling_5d_blocking_reason",
        )
    ):
        return payload
    return {}


def _resolved_positive_pullback_days(mapping: dict[str, object]) -> object | None:
    direct_pullback_days = _safe_int(mapping.get("pullback_days"))
    if direct_pullback_days is not None and direct_pullback_days > 0:
        return mapping.get("pullback_days")
    for key in ("fast_ema10_pullback_days", "conservative_ema20_pullback_days"):
        value = _safe_int(mapping.get(key))
        if value is not None and value > 0:
            return mapping.get(key)
    return None


def _build_row(
    *,
    row: dict[str, object],
    horizon: str,
    row_kind: str,
    raw_status: str | None,
    horizon_source_field: str | None = None,
    raw_action: str | None = None,
    reason: str | None = None,
    blocking_reasons: str | None = None,
    extra_raw_fields: dict[str, object] | None = None,
    high_exit_risk_days_count_override: object | None = None,
) -> DatacenterDashboardRow:
    raw_fields = _raw_fields_from_row(row, horizon_source_field=horizon_source_field)
    payload = _decoded_payload(row)
    ma_break = _ma_break_payload(payload)
    freshness = _freshness_payload(payload)
    rolling2 = _rolling2_payload(payload)
    if extra_raw_fields:
        for key, value in extra_raw_fields.items():
            text = _normalized_text(value)
            if text is not None:
                raw_fields[key] = text
    return DatacenterDashboardRow(
        ticker=str(_normalized_text(row.get("ticker"))).upper(),
        horizon=horizon,
        source_file=SOURCE_FILE,
        section=SECTION,
        row_kind=row_kind,
        raw_action=raw_action,
        raw_status=raw_status,
        reason=reason if reason is not None else _normalized_text(row.get("primary_reason")),
        trend_state=_normalized_text(row.get("trend_state")),
        latest_structure_label=_normalized_text(row.get("latest_structure_label")),
        latest_bos_event_type=_normalized_text(row.get("latest_bos_event_type")),
        latest_reset_reason=_normalized_text(row.get("latest_reset_reason")),
        distance_to_ema20=_safe_float(row.get("distance_to_ema20")),
        high_exit_risk_days_count=(
            _safe_int(high_exit_risk_days_count_override)
            if _safe_int(high_exit_risk_days_count_override) is not None
            else _safe_int(row.get("high_exit_risk_days_count"))
        ),
        blocking_reasons=(
            blocking_reasons
            if blocking_reasons is not None
            else _normalized_text(row.get("blocking_reasons"))
        ),
        ma_break_status=_normalized_text(row.get("ma_break_status")) or _normalized_text(ma_break.get("ma_break_status")),
        ema20_break_confirmed=_safe_int(row.get("ema20_break_confirmed")) if _safe_int(row.get("ema20_break_confirmed")) is not None else _safe_int(ma_break.get("ema20_break_confirmed")),
        sma50_break_confirmed=_safe_int(row.get("sma50_break_confirmed")) if _safe_int(row.get("sma50_break_confirmed")) is not None else _safe_int(ma_break.get("sma50_break_confirmed")),
        close_below_ema20=_safe_int(row.get("close_below_ema20")) if _safe_int(row.get("close_below_ema20")) is not None else _safe_int(ma_break.get("close_below_ema20")),
        close_below_sma50=_safe_int(row.get("close_below_sma50")) if _safe_int(row.get("close_below_sma50")) is not None else _safe_int(ma_break.get("close_below_sma50")),
        consecutive_closes_below_ema20=_safe_int(row.get("consecutive_closes_below_ema20")) if _safe_int(row.get("consecutive_closes_below_ema20")) is not None else _safe_int(ma_break.get("consecutive_closes_below_ema20")),
        consecutive_closes_below_sma50=_safe_int(row.get("consecutive_closes_below_sma50")) if _safe_int(row.get("consecutive_closes_below_sma50")) is not None else _safe_int(ma_break.get("consecutive_closes_below_sma50")),
        ema20_break_pct=_safe_float(row.get("ema20_break_pct")) if _safe_float(row.get("ema20_break_pct")) is not None else _safe_float(ma_break.get("ema20_break_pct")),
        sma50_break_pct=_safe_float(row.get("sma50_break_pct")) if _safe_float(row.get("sma50_break_pct")) is not None else _safe_float(ma_break.get("sma50_break_pct")),
        freshness_status=_normalized_text(row.get("freshness_status")) or _normalized_text(
            freshness.get("freshness_status")
        ),
        structure_warning_overrides_bullish_signal=_safe_int(
            row.get("structure_warning_overrides_bullish_signal")
        )
        if _safe_int(row.get("structure_warning_overrides_bullish_signal")) is not None
        else _safe_int(freshness.get("structure_warning_overrides_bullish_signal")),
        latest_bullish_signal_age_td=_safe_int(row.get("latest_bullish_signal_age_td"))
        if _safe_int(row.get("latest_bullish_signal_age_td")) is not None
        else _safe_int(freshness.get("latest_bullish_signal_age_td")),
        latest_bearish_signal_age_td=_safe_int(row.get("latest_bearish_signal_age_td"))
        if _safe_int(row.get("latest_bearish_signal_age_td")) is not None
        else _safe_int(freshness.get("latest_bearish_signal_age_td")),
        latest_bos_up_age_td=_safe_int(row.get("latest_bos_up_age_td"))
        if _safe_int(row.get("latest_bos_up_age_td")) is not None
        else _safe_int(freshness.get("latest_bos_up_age_td")),
        latest_bos_down_age_td=_safe_int(row.get("latest_bos_down_age_td"))
        if _safe_int(row.get("latest_bos_down_age_td")) is not None
        else _safe_int(freshness.get("latest_bos_down_age_td")),
        latest_reset_age_td=_safe_int(row.get("latest_reset_age_td"))
        if _safe_int(row.get("latest_reset_age_td")) is not None
        else _safe_int(freshness.get("latest_reset_age_td")),
        raw_fields=raw_fields,
    )


def build_dashboard_rows_from_ticker_enrichment_rows(
    rows: list[dict[str, object]],
) -> list[DatacenterDashboardRow]:
    dashboard_rows: list[DatacenterDashboardRow] = []
    for row in rows:
        if not _is_valid_ticker(row.get("ticker")):
            continue
        decoded_payload = _decoded_payload(row)
        upstream_payload = _upstream_rolling5_payload(row)
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
            extra_raw_fields: dict[str, object] = {}
            rolling2_payload = _rolling2_payload(decoded_payload)
            rolling30_payload = _rolling30_payload(decoded_payload)
            if horizon == "rolling 2d":
                high_exit_risk_days_count = row.get("high_exit_risk_days_count")
                if rolling2_payload:
                    helper_high_exit_risk_days = rolling2_payload.get("high_exit_risk_days")
                    typed_high_exit_risk_days_count = None
                    if _normalized_text(helper_high_exit_risk_days) is not None:
                        extra_raw_fields["high_exit_risk_days_count"] = helper_high_exit_risk_days
                        typed_high_exit_risk_days_count = helper_high_exit_risk_days
                    elif _normalized_text(high_exit_risk_days_count) is not None:
                        extra_raw_fields["high_exit_risk_days_count"] = high_exit_risk_days_count
                        typed_high_exit_risk_days_count = high_exit_risk_days_count
                    rolling2_status = _normalized_text(
                        rolling2_payload.get("rolling_2_sell_pressure_state")
                    ) or status_value
                    rolling2_action = _normalized_text(rolling2_payload.get("next_action"))
                    rolling2_reason = _normalized_text(rolling2_payload.get("risk_reason")) or ""
                    if _normalized_text(rolling2_payload.get("high_exit_risk_days")) is not None:
                        extra_raw_fields["high_exit_risk_days"] = rolling2_payload.get("high_exit_risk_days")
                    if _normalized_text(rolling2_payload.get("medium_exit_risk_days")) is not None:
                        extra_raw_fields["medium_exit_risk_days"] = rolling2_payload.get("medium_exit_risk_days")
                    if _normalized_text(rolling2_payload.get("exit_risk_days")) is not None:
                        extra_raw_fields["exit_risk_days"] = rolling2_payload.get("exit_risk_days")
                    if _normalized_text(rolling2_payload.get("latest_exit_risk_severity")) is not None:
                        extra_raw_fields["latest_exit_risk_severity"] = rolling2_payload.get("latest_exit_risk_severity")
                    if _normalized_text(rolling2_payload.get("latest_exit_reason")) is not None:
                        extra_raw_fields["latest_exit_reason"] = rolling2_payload.get("latest_exit_reason")
                    if _normalized_text(rolling2_payload.get("risk_reason")) is not None:
                        extra_raw_fields["risk_reason"] = rolling2_payload.get("risk_reason")
                    if _normalized_text(rolling2_payload.get("next_action")) is not None:
                        extra_raw_fields["next_action"] = rolling2_payload.get("next_action")
                    if _normalized_text(rolling2_payload.get("latest_bos_event_type")) is not None:
                        extra_raw_fields["latest_bos_event_type"] = rolling2_payload.get("latest_bos_event_type")
                    if _normalized_text(rolling2_payload.get("latest_bos_freshness")) is not None:
                        extra_raw_fields["latest_bos_freshness"] = rolling2_payload.get("latest_bos_freshness")
                    if _normalized_text(rolling2_payload.get("latest_reset_reason")) is not None:
                        extra_raw_fields["latest_reset_reason"] = rolling2_payload.get("latest_reset_reason")
                    if _normalized_text(rolling2_payload.get("latest_reset_freshness")) is not None:
                        extra_raw_fields["latest_reset_freshness"] = rolling2_payload.get("latest_reset_freshness")
                    if _normalized_text(rolling2_payload.get("latest_bearish_relevance_class")) is not None:
                        extra_raw_fields["latest_bearish_relevance_class"] = rolling2_payload.get("latest_bearish_relevance_class")
                    if _normalized_text(rolling2_payload.get("latest_bearish_relevance_reason")) is not None:
                        extra_raw_fields["latest_bearish_relevance_reason"] = rolling2_payload.get("latest_bearish_relevance_reason")
                    extra_raw_fields["rolling_2_sell_pressure_state"] = rolling2_status
                    if (
                        _safe_int(rolling2_payload.get("high_exit_risk_days")) not in {None, 0}
                        or (_normalized_text(rolling2_payload.get("latest_exit_risk_severity")) or "").upper() == "HIGH"
                    ):
                        extra_raw_fields["high_exit_risk_token"] = "high_exit_risk"
                    if (
                        _safe_int(rolling2_payload.get("medium_exit_risk_days")) not in {None, 0}
                        or (_normalized_text(rolling2_payload.get("latest_exit_risk_severity")) or "").upper() == "MEDIUM"
                    ):
                        extra_raw_fields["medium_exit_risk_token"] = "medium_exit_risk"
                    if _normalized_text(rolling2_payload.get("latest_bos_event_type")) == "BOS_DOWN":
                        extra_raw_fields["bos_down_token"] = "bos_down"
                    latest_reset_reason = _normalized_text(rolling2_payload.get("latest_reset_reason"))
                    if latest_reset_reason is not None:
                        extra_raw_fields["reset_token"] = "reset"
                        if "DOUBLE_BOS_DOWN" in latest_reset_reason:
                            extra_raw_fields["double_bos_down_token"] = "double_bos_down"
                    next_action = _normalized_text(rolling2_payload.get("next_action"))
                    if next_action is not None and any(
                        term in next_action.lower() for term in ("sell", "reduce", "stop", "check")
                    ):
                        extra_raw_fields["sell_token"] = "sell"
                    dashboard_rows.append(
                        _build_row(
                            row=row,
                            horizon=horizon,
                            row_kind="ticker_enrichment_horizon",
                            raw_status=rolling2_status,
                            horizon_source_field="rolling_2d_status",
                            raw_action=rolling2_action,
                            reason=rolling2_reason,
                            extra_raw_fields=extra_raw_fields,
                            high_exit_risk_days_count_override=typed_high_exit_risk_days_count,
                        )
                    )
                    continue
                if _normalized_text(high_exit_risk_days_count) is not None:
                    extra_raw_fields["high_exit_risk_days_count"] = high_exit_risk_days_count
            if horizon == "rolling 30d" and rolling30_payload:
                rolling30_row = dict(row)
                rolling30_row.update(rolling30_payload)
                rolling30_status = _normalized_text(
                    rolling30_payload.get("rolling_30_buy_state")
                ) or status_value
                rolling30_reason = _normalized_text(rolling30_payload.get("primary_reason"))
                rolling30_blocking_reasons = _normalized_text(
                    rolling30_payload.get("blocking_reason")
                )
                for key in (
                    "rolling_30_buy_state",
                    "current_watchlist_status",
                    "window_watchlist_status",
                    "breakout_days",
                    "pullback_days",
                    "exit_risk_days",
                    "primary_reason",
                    "blocking_reason",
                    "latest_ticker_trend_state",
                    "latest_structure_label",
                    "latest_bos_event_type",
                    "latest_bos_freshness",
                    "latest_reset_reason",
                    "latest_reset_freshness",
                    "latest_bullish_relevance_class",
                    "latest_bullish_relevance_reason",
                    "latest_bearish_relevance_class",
                    "latest_bearish_relevance_reason",
                ):
                    if _normalized_text(rolling30_payload.get(key)) is not None:
                        extra_raw_fields[key] = rolling30_payload.get(key)
                dashboard_rows.append(
                    _build_row(
                        row=rolling30_row,
                        horizon=horizon,
                        row_kind="ticker_enrichment_horizon",
                        raw_status=rolling30_status,
                        horizon_source_field="rolling_30d_status",
                        reason=rolling30_reason,
                        blocking_reasons=rolling30_blocking_reasons,
                        extra_raw_fields=extra_raw_fields,
                    )
                )
                continue
            if horizon == "rolling 5d" and upstream_payload:
                rolling5_row = dict(row)
                rolling5_row.update(upstream_payload)
                rolling5_status = _normalized_text(
                    upstream_payload.get("rolling_5_pullback_state")
                ) or status_value
                mirrored_rolling5_status = _normalized_text(
                    upstream_payload.get("rolling_5_pullback_state")
                ) or _normalized_text(upstream_payload.get("rolling_5d_status")) or status_value
                rolling5_action = _normalized_text(upstream_payload.get("next_action"))
                rolling5_reason = _normalized_text(upstream_payload.get("primary_reason"))
                rolling5_blocking_reasons = _normalized_text(
                    upstream_payload.get("blocking_reason")
                )
                extra_raw_fields["rolling_5_pullback_state"] = mirrored_rolling5_status
                extra_raw_fields["rolling_5d_status"] = mirrored_rolling5_status
                positive_pullback_days = _resolved_positive_pullback_days(rolling5_row)
                if positive_pullback_days is not None:
                    extra_raw_fields["pullback_days"] = positive_pullback_days
                elif _normalized_text(rolling5_row.get("pullback_days")) is not None:
                    extra_raw_fields["pullback_days"] = rolling5_row.get("pullback_days")
                horizon_source = (
                    "rolling_5_pullback_state"
                    if _normalized_text(upstream_payload.get("rolling_5_pullback_state")) is not None
                    else source_field
                )
                dashboard_rows.append(
                    _build_row(
                        row=rolling5_row,
                        horizon=horizon,
                        row_kind="ticker_enrichment_horizon",
                        raw_status=rolling5_status,
                        horizon_source_field=horizon_source,
                        raw_action=rolling5_action,
                        reason=rolling5_reason,
                        blocking_reasons=rolling5_blocking_reasons,
                        extra_raw_fields=extra_raw_fields,
                    )
                )
                continue
            if horizon == "rolling 5d":
                mirrored_rolling5_status = _normalized_text(row.get("rolling_5_pullback_state")) or status_value
                extra_raw_fields["rolling_5_pullback_state"] = mirrored_rolling5_status
                extra_raw_fields["rolling_5d_status"] = _normalized_text(row.get("rolling_5d_status")) or mirrored_rolling5_status
                positive_pullback_days = _resolved_positive_pullback_days(row)
                if positive_pullback_days is not None:
                    extra_raw_fields["pullback_days"] = positive_pullback_days
                elif _normalized_text(row.get("pullback_days")) is not None:
                    extra_raw_fields["pullback_days"] = row.get("pullback_days")
            dashboard_rows.append(
                _build_row(
                    row=row,
                    horizon=horizon,
                    row_kind="ticker_enrichment_horizon",
                    raw_status=status_value,
                    horizon_source_field=source_field,
                    extra_raw_fields=extra_raw_fields,
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
