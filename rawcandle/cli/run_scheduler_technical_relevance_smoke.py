from __future__ import annotations

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from rawcandle.scheduler.runner import (
    _build_technical_relevance_run_id,
    _format_duration_seconds,
    _resolve_latest_valid_ohlcv_date_for_market,
)
from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    read_relevance_run,
    resolve_created_at_utc,
)
from rawcandle.technical_signal_relevance_service import (
    run_technical_signal_relevance_for_tickers,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the scheduler technical relevance post-step logic for a ticker subset "
            "without stock update or datacenter stages."
        )
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--ticker", nargs="+", required=True)
    parser.add_argument("--end-date")
    parser.add_argument("--run-id")
    parser.add_argument("--created-at-utc")
    parser.add_argument("--timeframe", default="1d")
    return parser


def _parse_tickers(raw_ticker_values: list[str]) -> list[str]:
    joined_value = " ".join(str(value) for value in raw_ticker_values)
    return sorted({segment.strip() for segment in joined_value.split(",") if segment.strip()})


def _resolve_sibling_osakedata_db_path(analysis_db_path: str) -> Path:
    return Path(analysis_db_path).resolve().parent / "osakedata.db"


def _resolve_latest_dow_confirmed_as_of_date(analysis_db_path: str) -> str | None:
    try:
        with sqlite3.connect(analysis_db_path) as conn:
            row = conn.execute(
                """
                SELECT MAX(confirmed_as_of_date)
                FROM stock_dow_structure_events
                """
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _resolve_effective_end_date(*, analysis_db_path: str, market: str, explicit_end_date: str | None) -> tuple[str | None, str]:
    if explicit_end_date is not None and explicit_end_date.strip():
        return explicit_end_date.strip(), "EXPLICIT"

    osakedata_db_path = _resolve_sibling_osakedata_db_path(analysis_db_path)
    latest_ohlcv_date = _resolve_latest_valid_ohlcv_date_for_market(
        str(osakedata_db_path),
        market,
    )
    latest_dow_date = _resolve_latest_dow_confirmed_as_of_date(analysis_db_path)

    if latest_ohlcv_date is None:
        return None, "NONE"
    if latest_dow_date is None:
        return latest_ohlcv_date, "LATEST_VALID_OHLCV_DATE"
    return min(latest_ohlcv_date, latest_dow_date), "MIN_LATEST_OHLCV_AND_DOW"


def _print_summary(
    *,
    attempted: int,
    status: str,
    market: str,
    run_id: str,
    ticker_count: int,
    start_date: str,
    end_date: str,
    end_date_source: str,
    records_written: int,
    relevant_count: int,
    weak_context_count: int,
    noise_count: int,
    unknown_signal_count: int,
    missing_dow_context_count: int,
    missing_bar_index_count: int,
    duration_seconds: str,
    skip_reason: str,
    error: str,
) -> None:
    print(f"SUMMARY technical_relevance.attempted={attempted}")
    print("SUMMARY technical_relevance.enabled=true")
    print(f"SUMMARY technical_relevance.status={status}")
    print(f"SUMMARY technical_relevance.market={market}")
    print(f"SUMMARY technical_relevance.run_id={run_id}")
    print(f"SUMMARY technical_relevance.ticker_count={ticker_count}")
    print(f"SUMMARY technical_relevance.start_date={start_date}")
    print(f"SUMMARY technical_relevance.end_date={end_date}")
    print(f"SUMMARY technical_relevance.end_date_source={end_date_source}")
    print(f"SUMMARY technical_relevance.records_written={records_written}")
    print(f"SUMMARY technical_relevance.relevant_count={relevant_count}")
    print(f"SUMMARY technical_relevance.weak_context_count={weak_context_count}")
    print(f"SUMMARY technical_relevance.noise_count={noise_count}")
    print(f"SUMMARY technical_relevance.unknown_signal_count={unknown_signal_count}")
    print(
        "SUMMARY technical_relevance.missing_dow_context_count="
        f"{missing_dow_context_count}"
    )
    print(
        "SUMMARY technical_relevance.missing_bar_index_count="
        f"{missing_bar_index_count}"
    )
    print(f"SUMMARY technical_relevance.duration_seconds={duration_seconds}")
    print(f"SUMMARY technical_relevance.skip_reason={skip_reason}")
    print(f"SUMMARY technical_relevance.error={error}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    market = args.market.strip().lower()
    tickers = _parse_tickers(args.ticker)

    if not market:
        _print_summary(
            attempted=0,
            status="FAILED",
            market="NONE",
            run_id="NONE",
            ticker_count=0,
            start_date="NONE",
            end_date="NONE",
            end_date_source="NONE",
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            duration_seconds="0.000",
            skip_reason="",
            error="market must be non-empty",
        )
        return 1
    if not tickers:
        _print_summary(
            attempted=0,
            status="FAILED",
            market=market,
            run_id="NONE",
            ticker_count=0,
            start_date="NONE",
            end_date="NONE",
            end_date_source="NONE",
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            duration_seconds="0.000",
            skip_reason="",
            error="ticker list must be non-empty",
        )
        return 1

    end_date, end_date_source = _resolve_effective_end_date(
        analysis_db_path=args.analysis_db,
        market=market,
        explicit_end_date=args.end_date,
    )
    if end_date is None:
        _print_summary(
            attempted=0,
            status="FAILED",
            market=market,
            run_id="NONE",
            ticker_count=len(tickers),
            start_date="NONE",
            end_date="NONE",
            end_date_source=end_date_source,
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            duration_seconds="0.000",
            skip_reason="",
            error="NO_VALID_OHLCV_DATE_FOR_MARKET",
        )
        return 1

    start_date = (date.fromisoformat(end_date) - timedelta(days=45)).isoformat()
    if start_date > end_date:
        _print_summary(
            attempted=0,
            status="FAILED",
            market=market,
            run_id="NONE",
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            end_date_source=end_date_source,
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            duration_seconds="0.000",
            skip_reason="",
            error="start_date must be less than or equal to end_date",
        )
        return 1

    run_id = args.run_id.strip() if args.run_id and args.run_id.strip() else _build_technical_relevance_run_id(market, end_date)
    created_at_utc = resolve_created_at_utc(args.created_at_utc)

    conn: sqlite3.Connection | None = None
    started_at = perf_counter()
    try:
        conn = sqlite3.connect(args.analysis_db)
        conn.row_factory = sqlite3.Row
        apply_technical_signal_relevance_migration(conn)
        if read_relevance_run(conn, run_id) is not None:
            _print_summary(
                attempted=1,
                status="SKIPPED_EXISTING_RUN",
                market=market,
                run_id=run_id,
                ticker_count=len(tickers),
                start_date=start_date,
                end_date=end_date,
                end_date_source=end_date_source,
                records_written=0,
                relevant_count=0,
                weak_context_count=0,
                noise_count=0,
                unknown_signal_count=0,
                missing_dow_context_count=0,
                missing_bar_index_count=0,
                duration_seconds=_format_duration_seconds(perf_counter() - started_at),
                skip_reason="RUN_ID_ALREADY_EXISTS",
                error="",
            )
            return 0

        summary = run_technical_signal_relevance_for_tickers(
            conn=conn,
            tickers=tickers,
            timeframe=args.timeframe,
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            created_at_utc=created_at_utc,
            config=None,
        )
        conn.commit()
        _print_summary(
            attempted=1,
            status="OK",
            market=market,
            run_id=run_id,
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            end_date_source=end_date_source,
            records_written=summary.records_written,
            relevant_count=summary.relevant_count,
            weak_context_count=summary.weak_context_count,
            noise_count=summary.noise_count,
            unknown_signal_count=summary.unknown_signal_count,
            missing_dow_context_count=summary.missing_dow_context_count,
            missing_bar_index_count=summary.missing_bar_index_count,
            duration_seconds=_format_duration_seconds(perf_counter() - started_at),
            skip_reason="",
            error="",
        )
        return 0
    except sqlite3.IntegrityError as exc:
        if conn is not None:
            conn.rollback()
        error_text = str(exc)
        status = "FAILED"
        skip_reason = ""
        exit_code = 1
        if "technical_signal_relevance_runs.run_id" in error_text or "UNIQUE constraint failed" in error_text:
            status = "SKIPPED_EXISTING_RUN"
            skip_reason = "RUN_ID_ALREADY_EXISTS"
            exit_code = 0
            error_text = ""
        _print_summary(
            attempted=1,
            status=status,
            market=market,
            run_id=run_id,
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            end_date_source=end_date_source,
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            duration_seconds=_format_duration_seconds(perf_counter() - started_at),
            skip_reason=skip_reason,
            error=error_text,
        )
        return exit_code
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        _print_summary(
            attempted=1,
            status="FAILED",
            market=market,
            run_id=run_id,
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            end_date_source=end_date_source,
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            duration_seconds=_format_duration_seconds(perf_counter() - started_at),
            skip_reason="",
            error=str(exc),
        )
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
