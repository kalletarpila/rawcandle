from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from .report_canonical_v2_orchestrator import ALLOWED_HORIZONS
from .swing_daily_report import (
    _build_daily_trigger_rows,
    load_daily_swing_report_data,
)
from .swing_weekly_report import (
    _build_rolling_2_sell_pressure_rows,
    _build_rolling_30_role_rows,
    _build_rolling_5_pullback_rows,
    load_weekly_swing_report_data,
)


CLASSIFICATION_TYPES_BY_HORIZON = {
    "daily": ("daily_trigger",),
    "rolling2": ("rolling2_sell_pressure",),
    "rolling5": ("rolling5_pullback",),
    "rolling30": ("rolling30_buy", "rolling30_exit"),
}

REASON_ACTION_FIELDS = {"primary_reason", "blocking_reason", "risk_reason", "next_action"}


def _normalize_horizons(horizons: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(horizon) for horizon in horizons))
    invalid = [h for h in normalized if h not in ALLOWED_HORIZONS]
    if invalid:
        raise ValueError(f"Unsupported horizons: {', '.join(invalid)}")
    return normalized


def _conn_to_analysis_db_path(conn: sqlite3.Connection) -> tuple[Path, str | None]:
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        if str(row[1]) == "main" and row[2]:
            return Path(str(row[2])), None

    fd, temp_path = tempfile.mkstemp(prefix="rawcandle_v2_parity_", suffix=".sqlite")
    os.close(fd)
    with sqlite3.connect(temp_path) as temp_conn:
        conn.backup(temp_conn)
    return Path(temp_path), temp_path


def _normalize_reason_action_pair(
    field: str,
    current_value: object | None,
    v2_value: object | None,
) -> tuple[object | None, object | None]:
    if field in REASON_ACTION_FIELDS:
        current_normalized = None if current_value == "" else current_value
        v2_normalized = None if v2_value == "" else v2_value
        return current_normalized, v2_normalized
    return current_value, v2_value


def _current_daily_rows(
    *,
    analysis_db_path: Path,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db_path,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        watchlist_file=analysis_db_path.with_suffix(".missing_watchlist"),
    )
    rows = _build_daily_trigger_rows(
        ticker_rows=list(report_data["ticker_rows"]),  # type: ignore[arg-type]
        group_rows=list(report_data["group_rows"]),  # type: ignore[arg-type]
        synthetic_rows=list(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        technical_relevance_context_rows=list(report_data.get("technical_relevance_context_rows") or []),
        technical_relevance_run_id=report_data.get("technical_relevance_run_id"),
    )
    return [
        {
            "horizon": "daily",
            "ticker": row.get("ticker"),
            "classification_type": "daily_trigger",
            "classification_state": row.get("daily_trigger_state"),
            "primary_reason": row.get("primary_reason"),
            "blocking_reason": row.get("blocking_reason"),
            "risk_reason": None,
            "next_action": row.get("next_action"),
        }
        for row in rows
    ]


def _current_rolling2_rows(
    *,
    analysis_db_path: Path,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db_path,
        end_date=signal_date,
        taxonomy_version=taxonomy_version,
        window_size=2,
        watchlist_file=analysis_db_path.with_suffix(".missing_watchlist"),
    )
    rows = _build_rolling_2_sell_pressure_rows(
        ticker_rows=list(report_data["ticker_rows"]),  # type: ignore[arg-type]
        group_rows=list(report_data["group_rows"]),  # type: ignore[arg-type]
        synthetic_rows=list(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        technical_relevance_context_rows=list(report_data.get("technical_relevance_context_rows") or []),
    )
    return [
        {
            "horizon": "rolling2",
            "ticker": row.get("ticker"),
            "classification_type": "rolling2_sell_pressure",
            "classification_state": row.get("rolling_2_sell_pressure_state"),
            "primary_reason": row.get("primary_reason"),
            "blocking_reason": None,
            "risk_reason": row.get("risk_reason"),
            "next_action": row.get("next_action"),
        }
        for row in rows
    ]


def _current_rolling5_rows(
    *,
    analysis_db_path: Path,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db_path,
        end_date=signal_date,
        taxonomy_version=taxonomy_version,
        window_size=5,
        watchlist_file=analysis_db_path.with_suffix(".missing_watchlist"),
    )
    rows = _build_rolling_5_pullback_rows(
        ticker_rows=list(report_data["ticker_rows"]),  # type: ignore[arg-type]
        group_rows=list(report_data["group_rows"]),  # type: ignore[arg-type]
        synthetic_rows=list(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        technical_relevance_context_rows=list(report_data.get("technical_relevance_context_rows") or []),
    )
    return [
        {
            "horizon": "rolling5",
            "ticker": row.get("ticker"),
            "classification_type": "rolling5_pullback",
            "classification_state": row.get("rolling_5_pullback_state"),
            "primary_reason": row.get("primary_reason"),
            "blocking_reason": row.get("blocking_reason"),
            "risk_reason": None,
            "next_action": row.get("next_action"),
        }
        for row in rows
    ]


def _current_rolling30_rows(
    *,
    analysis_db_path: Path,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db_path,
        end_date=signal_date,
        taxonomy_version=taxonomy_version,
        window_size=30,
        watchlist_file=analysis_db_path.with_suffix(".missing_watchlist"),
    )
    buy_rows, exit_rows = _build_rolling_30_role_rows(
        ticker_rows=list(report_data["ticker_rows"]),  # type: ignore[arg-type]
        group_rows=list(report_data["group_rows"]),  # type: ignore[arg-type]
        synthetic_rows=list(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        technical_relevance_context_rows=list(report_data.get("technical_relevance_context_rows") or []),
    )
    current_rows = [
        {
            "horizon": "rolling30",
            "ticker": row.get("ticker"),
            "classification_type": "rolling30_buy",
            "classification_state": row.get("rolling_30_buy_state"),
            "primary_reason": row.get("primary_reason"),
            "blocking_reason": row.get("blocking_reason"),
            "risk_reason": None,
            "next_action": None,
        }
        for row in buy_rows
    ]
    current_rows.extend(
        {
            "horizon": "rolling30",
            "ticker": row.get("ticker"),
            "classification_type": "rolling30_exit",
            "classification_state": row.get("rolling_30_exit_state"),
            "primary_reason": row.get("primary_reason"),
            "blocking_reason": None,
            "risk_reason": row.get("risk_reason"),
            "next_action": None,
        }
        for row in exit_rows
    )
    return current_rows


def _load_current_rows(
    *,
    analysis_db_path: Path,
    signal_date: str,
    taxonomy_version: str,
    horizons: tuple[str, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if "daily" in horizons:
        rows.extend(
            _current_daily_rows(
                analysis_db_path=analysis_db_path,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
        )
    if "rolling2" in horizons:
        rows.extend(
            _current_rolling2_rows(
                analysis_db_path=analysis_db_path,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
        )
    if "rolling5" in horizons:
        rows.extend(
            _current_rolling5_rows(
                analysis_db_path=analysis_db_path,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
        )
    if "rolling30" in horizons:
        rows.extend(
            _current_rolling30_rows(
                analysis_db_path=analysis_db_path,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
        )
    return rows


def _load_v2_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    horizons: tuple[str, ...],
) -> list[dict[str, object]]:
    classification_types = tuple(
        classification_type
        for horizon in horizons
        for classification_type in CLASSIFICATION_TYPES_BY_HORIZON[horizon]
    )
    horizon_placeholders = ", ".join("?" for _ in horizons)
    type_placeholders = ", ".join("?" for _ in classification_types)
    where = [
        "signal_date = ?",
        "taxonomy_version = ?",
        f"horizon IN ({horizon_placeholders})",
        f"classification_type IN ({type_placeholders})",
    ]
    params: list[object] = [signal_date, taxonomy_version, *horizons, *classification_types]
    if market is not None:
        where.append("market = ?")
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT horizon, ticker, classification_type, classification_state,
               primary_reason, blocking_reason, risk_reason, next_action
        FROM dc_report_classification_v2
        WHERE {' AND '.join(where)}
        ORDER BY horizon ASC, classification_type ASC, ticker ASC
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def _mismatch_entry(
    *,
    horizon: str,
    ticker: str,
    classification_type: str,
    field: str,
    current_value: object | None,
    v2_value: object | None,
    reason: str,
) -> dict[str, object]:
    return {
        "horizon": horizon,
        "ticker": ticker,
        "classification_type": classification_type,
        "field": field,
        "current_value": current_value,
        "v2_value": v2_value,
        "reason": reason,
    }


def _comparison_fields(classification_type: str) -> tuple[str, ...]:
    if classification_type == "daily_trigger":
        return ("classification_state", "primary_reason", "blocking_reason", "next_action")
    if classification_type == "rolling2_sell_pressure":
        return ("classification_state", "primary_reason", "risk_reason", "next_action")
    if classification_type == "rolling5_pullback":
        return ("classification_state", "primary_reason", "blocking_reason", "next_action")
    if classification_type == "rolling30_buy":
        return ("classification_state", "primary_reason", "blocking_reason")
    if classification_type == "rolling30_exit":
        return ("classification_state", "primary_reason", "risk_reason")
    raise ValueError(f"Unsupported classification_type: {classification_type}")


def audit_report_canonical_v2_parity(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None = None,
    horizons: tuple[str, ...] = ("daily", "rolling2", "rolling5", "rolling30"),
) -> dict[str, object]:
    normalized_horizons = _normalize_horizons(horizons)
    analysis_db_path, temp_copy_path = _conn_to_analysis_db_path(conn)
    try:
        current_rows = _load_current_rows(
            analysis_db_path=analysis_db_path,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            horizons=normalized_horizons,
        )
    finally:
        if temp_copy_path is not None:
            os.unlink(temp_copy_path)

    v2_rows = _load_v2_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        horizons=normalized_horizons,
    )

    current_by_key = {
        (str(row["horizon"]), str(row["classification_type"]), str(row["ticker"])): row
        for row in current_rows
    }
    v2_by_key = {
        (str(row["horizon"]), str(row["classification_type"]), str(row["ticker"])): row
        for row in v2_rows
    }

    mismatches: list[dict[str, object]] = []
    matched_count = 0
    missing_current_count = 0
    missing_v2_count = 0
    horizon_summaries = {
        horizon: {
            "matched_count": 0,
            "mismatch_count": 0,
            "missing_current_count": 0,
            "missing_v2_count": 0,
        }
        for horizon in normalized_horizons
    }

    for key in sorted(set(current_by_key) | set(v2_by_key)):
        horizon, classification_type, ticker = key
        current_row = current_by_key.get(key)
        v2_row = v2_by_key.get(key)
        if current_row is None:
            missing_current_count += 1
            horizon_summaries[horizon]["missing_current_count"] += 1
            mismatches.append(
                _mismatch_entry(
                    horizon=horizon,
                    ticker=ticker,
                    classification_type=classification_type,
                    field="row_presence",
                    current_value=None,
                    v2_value="PRESENT",
                    reason="missing_current_row",
                )
            )
            continue
        if v2_row is None:
            missing_v2_count += 1
            horizon_summaries[horizon]["missing_v2_count"] += 1
            mismatches.append(
                _mismatch_entry(
                    horizon=horizon,
                    ticker=ticker,
                    classification_type=classification_type,
                    field="row_presence",
                    current_value="PRESENT",
                    v2_value=None,
                    reason="missing_v2_row",
                )
            )
            continue

        row_matched = True
        for field in _comparison_fields(classification_type):
            current_value = current_row.get(field)
            v2_value = v2_row.get(field)
            normalized_current, normalized_v2 = _normalize_reason_action_pair(
                field,
                current_value,
                v2_value,
            )
            if normalized_current != normalized_v2:
                row_matched = False
                mismatches.append(
                    _mismatch_entry(
                        horizon=horizon,
                        ticker=ticker,
                        classification_type=classification_type,
                        field=field,
                        current_value=current_value,
                        v2_value=v2_value,
                        reason="field_mismatch",
                    )
                )
        if row_matched:
            matched_count += 1
            horizon_summaries[horizon]["matched_count"] += 1
        else:
            horizon_summaries[horizon]["mismatch_count"] += 1

    mismatches.sort(
        key=lambda row: (
            str(row["horizon"]),
            str(row["classification_type"]),
            str(row["ticker"]),
            str(row["field"]),
        )
    )

    if not current_rows and not v2_rows:
        status = "NO_CURRENT_DATA"
    elif not current_rows:
        status = "NO_CURRENT_DATA"
    elif not v2_rows:
        status = "NO_V2_DATA"
    elif mismatches:
        status = "MISMATCH"
    else:
        status = "OK"

    return {
        "signal_date": signal_date,
        "taxonomy_version": taxonomy_version,
        "market": market,
        "horizons": normalized_horizons,
        "status": status,
        "mismatch_count": len(mismatches),
        "missing_current_count": missing_current_count,
        "missing_v2_count": missing_v2_count,
        "matched_count": matched_count,
        "mismatches": mismatches,
        "horizon_summaries": horizon_summaries,
    }
