from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone

from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    resolve_created_at_utc,
)
from rawcandle.technical_signal_relevance_service import (
    run_technical_signal_relevance_for_tickers,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run technical signal relevance classification from analysis sources."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ticker", nargs="+", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--created-at-utc")
    return parser


def _parse_tickers(raw_ticker_values: list[str]) -> list[str]:
    joined_value = " ".join(str(value) for value in raw_ticker_values)
    return [segment.strip() for segment in joined_value.split(",") if segment.strip()]


def _validate_args(args: argparse.Namespace, tickers: list[str]) -> None:
    if not args.run_id.strip():
        raise ValueError("run_id must be non-empty")
    if not tickers:
        raise ValueError("ticker list must be non-empty")
    if args.start_date > args.end_date:
        raise ValueError("start_date must be less than or equal to end_date")


def _default_created_at_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _print_summary(
    *,
    run_id: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    ticker_count: int,
    observations_seen: int,
    records_written: int,
    relevant_count: int,
    weak_context_count: int,
    noise_count: int,
    unknown_signal_count: int,
    missing_dow_context_count: int,
    missing_bar_index_count: int,
    status: str,
) -> None:
    print(f"SUMMARY technical_signal_relevance.run_id={run_id}")
    print(f"SUMMARY technical_signal_relevance.timeframe={timeframe}")
    print(f"SUMMARY technical_signal_relevance.start_date={start_date}")
    print(f"SUMMARY technical_signal_relevance.end_date={end_date}")
    print(f"SUMMARY technical_signal_relevance.ticker_count={ticker_count}")
    print(f"SUMMARY technical_signal_relevance.observations_seen={observations_seen}")
    print(f"SUMMARY technical_signal_relevance.records_written={records_written}")
    print(f"SUMMARY technical_signal_relevance.relevant_count={relevant_count}")
    print(f"SUMMARY technical_signal_relevance.weak_context_count={weak_context_count}")
    print(f"SUMMARY technical_signal_relevance.noise_count={noise_count}")
    print(f"SUMMARY technical_signal_relevance.unknown_signal_count={unknown_signal_count}")
    print(
        "SUMMARY technical_signal_relevance.missing_dow_context_count="
        f"{missing_dow_context_count}"
    )
    print(
        "SUMMARY technical_signal_relevance.missing_bar_index_count="
        f"{missing_bar_index_count}"
    )
    print(f"SUMMARY technical_signal_relevance.status={status}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tickers = _parse_tickers(args.ticker)
    conn: sqlite3.Connection | None = None

    try:
        _validate_args(args, tickers)
        created_at_utc = resolve_created_at_utc(args.created_at_utc or _default_created_at_utc())
        conn = sqlite3.connect(args.analysis_db)
        conn.row_factory = sqlite3.Row
        try:
            apply_technical_signal_relevance_migration(conn)
            summary = run_technical_signal_relevance_for_tickers(
                conn=conn,
                tickers=tickers,
                timeframe=args.timeframe,
                start_date=args.start_date,
                end_date=args.end_date,
                run_id=args.run_id,
                created_at_utc=created_at_utc,
                config=None,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except (ValueError, sqlite3.IntegrityError, sqlite3.Error):
        _print_summary(
            run_id=args.run_id,
            timeframe=args.timeframe,
            start_date=args.start_date,
            end_date=args.end_date,
            ticker_count=len(tickers),
            observations_seen=0,
            records_written=0,
            relevant_count=0,
            weak_context_count=0,
            noise_count=0,
            unknown_signal_count=0,
            missing_dow_context_count=0,
            missing_bar_index_count=0,
            status="FAILED",
        )
        return 1

    _print_summary(
        run_id=args.run_id,
        timeframe=args.timeframe,
        start_date=args.start_date,
        end_date=args.end_date,
        ticker_count=len(set(tickers)),
        observations_seen=summary.observations_seen,
        records_written=summary.records_written,
        relevant_count=summary.relevant_count,
        weak_context_count=summary.weak_context_count,
        noise_count=summary.noise_count,
        unknown_signal_count=summary.unknown_signal_count,
        missing_dow_context_count=summary.missing_dow_context_count,
        missing_bar_index_count=summary.missing_bar_index_count,
        status="OK",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
