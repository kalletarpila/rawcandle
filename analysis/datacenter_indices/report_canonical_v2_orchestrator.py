from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from .report_canonical_v2_daily_classification_writer import (
    write_report_daily_trigger_classification_v2,
)
from .report_canonical_v2_daily_context_builder import build_report_daily_context_v2
from .report_canonical_v2_group_context_builder import build_report_group_context_v2
from .report_canonical_v2_rolling2_classification_writer import (
    write_report_rolling2_sell_pressure_classification_v2,
)
from .report_canonical_v2_rolling30_classification_writer import (
    write_report_rolling30_buy_exit_classification_v2,
)
from .report_canonical_v2_rolling5_classification_writer import (
    write_report_rolling5_pullback_classification_v2,
)
from .report_canonical_v2_window_context_builder import build_report_window_context_v2


ALLOWED_HORIZONS = ("daily", "rolling2", "rolling5", "rolling30")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_horizons(horizons: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(horizon) for horizon in horizons))
    invalid = [horizon for horizon in normalized if horizon not in ALLOWED_HORIZONS]
    if invalid:
        raise ValueError(f"Unsupported horizons: {', '.join(invalid)}")
    return normalized


def _upsert_run_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    calculation_version: str,
    source_versions_json: str | None,
    created_at_utc: str,
    notes: str | None,
    status: str = "OK",
    warning_count: int = 0,
    error_count: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            market,
            calculation_version,
            source_versions_json,
            created_at_utc,
            status,
            warning_count,
            error_count,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            signal_date = excluded.signal_date,
            taxonomy_version = excluded.taxonomy_version,
            market = excluded.market,
            calculation_version = excluded.calculation_version,
            source_versions_json = excluded.source_versions_json,
            created_at_utc = excluded.created_at_utc,
            status = excluded.status,
            warning_count = excluded.warning_count,
            error_count = excluded.error_count,
            notes = excluded.notes
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            market,
            calculation_version,
            source_versions_json,
            created_at_utc,
            status,
            warning_count,
            error_count,
            notes,
        ),
    )
    conn.commit()


def run_report_canonical_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    horizons: tuple[str, ...] = ("daily", "rolling2", "rolling5", "rolling30"),
    ecosystem_tickers: set[str] | None = None,
    watchlist_tickers: set[str] | None = None,
    calculation_version: str = "REPORT_CANONICAL_V2_1",
    classification_version: str = "REPORT_CANONICAL_CLASSIFICATION_V2_1",
    source_versions_json: str | None = None,
    created_at_utc: str | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    normalized_horizons = _normalize_horizons(horizons)
    created_at_value = created_at_utc or _utc_now_iso()

    _upsert_run_row(
        conn,
        run_id=run_id,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        calculation_version=calculation_version,
        source_versions_json=source_versions_json,
        created_at_utc=created_at_value,
        notes=notes,
    )

    group_context_summary: dict[str, int] | None = None
    daily_context_summary: dict[str, int] | None = None
    window_context_summary: dict[str, int] | None = None
    daily_classification_summary: dict[str, int] | None = None
    rolling2_classification_summary: dict[str, int] | None = None
    rolling5_classification_summary: dict[str, int] | None = None
    rolling30_classification_summary: dict[str, int] | None = None

    if normalized_horizons:
        group_context_summary = build_report_group_context_v2(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            run_id=run_id,
            market=market,
            horizons=normalized_horizons,
            calculation_version=calculation_version,
            created_at_utc=created_at_value,
        )

    if "daily" in normalized_horizons:
        daily_context_summary = build_report_daily_context_v2(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            run_id=run_id,
            market=market,
            calculation_version=calculation_version,
            created_at_utc=created_at_value,
            ecosystem_tickers=ecosystem_tickers,
            watchlist_tickers=watchlist_tickers,
        )
        daily_classification_summary = write_report_daily_trigger_classification_v2(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            run_id=run_id,
            market=market,
            classification_version=classification_version,
            created_at_utc=created_at_value,
        )

    rolling_horizons = tuple(h for h in normalized_horizons if h != "daily")
    if rolling_horizons:
        window_context_summary = build_report_window_context_v2(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            run_id=run_id,
            market=market,
            horizons=rolling_horizons,
            calculation_version=calculation_version,
            created_at_utc=created_at_value,
            ecosystem_tickers=ecosystem_tickers,
            watchlist_tickers=watchlist_tickers,
        )

        if "rolling2" in rolling_horizons:
            rolling2_classification_summary = write_report_rolling2_sell_pressure_classification_v2(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                run_id=run_id,
                market=market,
                classification_version=classification_version,
                created_at_utc=created_at_value,
            )
        if "rolling5" in rolling_horizons:
            rolling5_classification_summary = write_report_rolling5_pullback_classification_v2(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                run_id=run_id,
                market=market,
                classification_version=classification_version,
                created_at_utc=created_at_value,
            )
        if "rolling30" in rolling_horizons:
            rolling30_classification_summary = write_report_rolling30_buy_exit_classification_v2(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                run_id=run_id,
                market=market,
                classification_version=classification_version,
                created_at_utc=created_at_value,
            )

    total_context_rows_written = sum(
        int(summary.get("total_rows_written", 0))
        for summary in (
            group_context_summary,
            daily_context_summary,
            window_context_summary,
        )
        if summary is not None
    )
    total_classification_rows_written = sum(
        int(summary.get("total_rows_written", 0))
        for summary in (
            daily_classification_summary,
            rolling2_classification_summary,
            rolling5_classification_summary,
            rolling30_classification_summary,
        )
        if summary is not None
    )
    steps = {
        "group_context": group_context_summary,
        "daily_context": daily_context_summary,
        "window_context": window_context_summary,
        "daily_classification": daily_classification_summary,
        "rolling2_classification": rolling2_classification_summary,
        "rolling5_classification": rolling5_classification_summary,
        "rolling30_classification": rolling30_classification_summary,
    }

    return {
        "run_id": run_id,
        "signal_date": signal_date,
        "taxonomy_version": taxonomy_version,
        "market": market,
        "status": "OK",
        "warning_count": 0,
        "error_count": 0,
        "steps": steps,
        "group_context_summary": group_context_summary,
        "daily_context_summary": daily_context_summary,
        "window_context_summary": window_context_summary,
        "daily_classification_summary": daily_classification_summary,
        "rolling2_classification_summary": rolling2_classification_summary,
        "rolling5_classification_summary": rolling5_classification_summary,
        "rolling30_classification_summary": rolling30_classification_summary,
        "total_context_rows_written": total_context_rows_written,
        "total_classification_rows_written": total_classification_rows_written,
    }
