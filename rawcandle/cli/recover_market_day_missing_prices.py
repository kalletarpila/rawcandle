from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from rawcandle.cli.plan_market_day_recovery import (
    PROVIDER_POLYGON_GROUPED_DAILY,
    PROVIDER_STATUS_API_KEY_MISSING_OR_EMPTY_RESULT,
    RecoveryPlanReport,
    build_recovery_plan_report,
)
from services.polygon_massive_grouped_daily_provider import (
    fetch_polygon_massive_grouped_daily_ohlcv_by_ticker,
)
from services.stock_update_service import (
    StockOhlcvRow,
    StockUpdateDateRange,
    execute_ticker_downstream_updates,
)

STATUS_DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"
STATUS_APPLY_COMPLETED = "APPLY_COMPLETED"
STATUS_APPLY_COMPLETED_WITH_WARNINGS = "APPLY_COMPLETED_WITH_WARNINGS"
STATUS_APPLY_BLOCKED_UNSUPPORTED_GAP_MODE = "APPLY_BLOCKED_UNSUPPORTED_GAP_MODE"
STATUS_APPLY_BLOCKED_REQUIRES_FROM_DATE_RECOMPUTE = (
    "APPLY_BLOCKED_REQUIRES_FROM_DATE_RECOMPUTE"
)
STATUS_APPLY_CONFIRMATION_REQUIRED = "APPLY_CONFIRMATION_REQUIRED"
STATUS_PROVIDER_EMPTY_OR_FAILED = "PROVIDER_EMPTY_OR_FAILED"
STATUS_FAILED = "FAILED"


@dataclass(frozen=True)
class RecoveryRuntimeAdapters:
    stock_factory: Callable[[str], Any]
    maybe_update_quarter_state: Callable[[str, str, Any], dict]
    sync_splits: Callable[[str, Any], int]
    maybe_backfill_splits: Callable[[str], bool]
    calculate_divergences: Callable[[str, bool], tuple]
    run_candlestick_analysis: Callable[[str, str, str], tuple]


@dataclass
class RecoveryApplyReport:
    db_path: str
    market: str
    target_date: str
    provider: str
    classification: str
    gap_position: str
    downstream_recompute_mode: str
    dry_run: bool
    apply: bool
    apply_limit: Optional[int]
    missing_before: int
    provider_snapshot_count: int
    recoverable_planned: int
    not_found_in_provider: int
    processed: int
    inserted: int
    already_present_skipped: int
    invalid_ohlc_skipped: int
    insert_failed: int
    quarter_state_attempted: int
    quarter_state_ok: int
    quarter_state_failed: int
    downstream_attempted: int
    downstream_ok: int
    downstream_failed: int
    still_missing_after: int
    commits_done: int
    would_process: int
    would_insert: int
    would_run_downstream: int
    provider_status: str
    status: str
    apply_safety_note: str
    recoverable_tickers: list[str] = field(default_factory=list)
    not_found_in_provider_tickers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual latest/right-edge market day recovery CLI."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--provider", default=PROVIDER_POLYGON_GROUPED_DAILY)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--commit-every", type=int, default=100)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--missing-limit", type=int, default=100)
    parser.add_argument("--reference-window-days", type=int, default=10)
    parser.add_argument("--min-reference-count", type=int, default=1000)
    return parser


def _parse_target_date(value: str) -> date:
    return date.fromisoformat(value)


def _exclusive_end_date(date_str: str) -> str:
    return (_parse_target_date(date_str) + timedelta(days=1)).isoformat()


def _row_has_complete_ohlc(row: StockOhlcvRow) -> bool:
    for value in (row.open, row.high, row.low, row.close):
        if value is None:
            return False
        if isinstance(value, bool):
            return False
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        if math.isnan(numeric):
            return False
    return True


def _still_missing(conn: sqlite3.Connection, *, ticker: str, target_date: str, market: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM osakedata
        WHERE osake = ?
          AND pvm = ?
          AND market = ?
        LIMIT 1
        """,
        (ticker, target_date, market),
    ).fetchone()
    return row is None


def _insert_recovered_ohlcv_row_if_missing(
    conn: sqlite3.Connection,
    *,
    row: StockOhlcvRow,
) -> str:
    if not _still_missing(
        conn,
        ticker=row.ticker,
        target_date=row.date,
        market=row.market,
    ):
        return "already_present_skipped"
    conn.execute(
        """
        INSERT INTO osakedata
        (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.ticker,
            row.date,
            row.open,
            row.high,
            row.low,
            row.close,
            row.volume,
            row.market,
        ),
    )
    return "inserted"


def _build_runtime_adapters(osakedata_db_path: str) -> RecoveryRuntimeAdapters:
    from main import RawCandleApp

    app = RawCandleApp.__new__(RawCandleApp)
    app.osakedata_db_path = osakedata_db_path
    app.analysis_db_path = str(Path(osakedata_db_path).resolve().parent / "analysis.db")
    adapters = app._build_stock_update_service_adapters()
    return RecoveryRuntimeAdapters(
        stock_factory=adapters["stock_factory"],
        maybe_update_quarter_state=adapters["maybe_update_quarter_state"],
        sync_splits=adapters["sync_splits"],
        maybe_backfill_splits=adapters["maybe_backfill_splits"],
        calculate_divergences=adapters["calculate_divergences"],
        run_candlestick_analysis=adapters["run_candlestick_analysis"],
    )


def _build_plan_with_snapshot(
    *,
    db_path: str,
    market: str,
    target_date: str,
    provider: str,
    reference_window_days: int,
    min_reference_count: int,
    skip_provider_fetch: bool,
    provider_fetcher: Optional[Callable[[str, date], Mapping[str, StockOhlcvRow]]] = None,
) -> tuple[RecoveryPlanReport, Mapping[str, StockOhlcvRow]]:
    snapshot_holder: dict[str, Mapping[str, StockOhlcvRow]] = {}

    def capture_fetcher(fetch_market: str, fetch_date: date) -> Mapping[str, StockOhlcvRow]:
        fetch = provider_fetcher or fetch_polygon_massive_grouped_daily_ohlcv_by_ticker
        snapshot = fetch(fetch_market, fetch_date)
        snapshot_holder["snapshot"] = snapshot
        return snapshot

    report = build_recovery_plan_report(
        db_path=db_path,
        market=market,
        target_date=target_date,
        provider=provider,
        reference_window_days=reference_window_days,
        min_reference_count=min_reference_count,
        skip_provider_fetch=skip_provider_fetch,
        provider_fetcher=capture_fetcher if not skip_provider_fetch else provider_fetcher,
    )
    return report, snapshot_holder.get("snapshot", {})


def build_recovery_apply_report(
    *,
    db_path: str,
    market: str,
    target_date: str,
    provider: str,
    apply: bool,
    confirm_write: bool,
    limit: int,
    commit_every: int,
    reference_window_days: int,
    min_reference_count: int,
    provider_fetcher: Optional[Callable[[str, date], Mapping[str, StockOhlcvRow]]] = None,
    runtime_builder: Optional[Callable[[str], RecoveryRuntimeAdapters]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> RecoveryApplyReport:
    if provider != PROVIDER_POLYGON_GROUPED_DAILY:
        raise ValueError(f"Unsupported provider: {provider}")

    progress = progress_callback or (lambda message: None)
    dry_run = not apply

    if apply and not confirm_write:
        plan_report, _ = _build_plan_with_snapshot(
            db_path=db_path,
            market=market,
            target_date=target_date,
            provider=provider,
            reference_window_days=reference_window_days,
            min_reference_count=min_reference_count,
            skip_provider_fetch=True,
        )
        return RecoveryApplyReport(
            db_path=plan_report.db_path,
            market=plan_report.market,
            target_date=plan_report.target_date,
            provider=provider,
            classification=plan_report.classification,
            gap_position=plan_report.gap_position,
            downstream_recompute_mode=plan_report.downstream_recompute_mode,
            dry_run=False,
            apply=True,
            apply_limit=limit or None,
            missing_before=plan_report.missing_tickers_count,
            provider_snapshot_count=0,
            recoverable_planned=0,
            not_found_in_provider=0,
            processed=0,
            inserted=0,
            already_present_skipped=0,
            invalid_ohlc_skipped=0,
            insert_failed=0,
            quarter_state_attempted=0,
            quarter_state_ok=0,
            quarter_state_failed=0,
            downstream_attempted=0,
            downstream_ok=0,
            downstream_failed=0,
            still_missing_after=plan_report.missing_tickers_count,
            commits_done=0,
            would_process=0,
            would_insert=0,
            would_run_downstream=0,
            provider_status="SKIPPED",
            status=STATUS_APPLY_CONFIRMATION_REQUIRED,
            apply_safety_note=plan_report.apply_safety_note,
            recoverable_tickers=[],
            not_found_in_provider_tickers=[],
        )

    plan_report, provider_snapshot = _build_plan_with_snapshot(
        db_path=db_path,
        market=market,
        target_date=target_date,
        provider=provider,
        reference_window_days=reference_window_days,
        min_reference_count=min_reference_count,
        skip_provider_fetch=False,
        provider_fetcher=provider_fetcher,
    )

    if apply:
        if plan_report.gap_position != "LATEST_OR_RIGHT_EDGE_GAP":
            status = (
                STATUS_APPLY_BLOCKED_REQUIRES_FROM_DATE_RECOMPUTE
                if plan_report.gap_position == "INTERIOR_GAP"
                or plan_report.downstream_recompute_mode
                == "FROM_RECOVERED_DATE_FORWARD_REQUIRED"
                else STATUS_APPLY_BLOCKED_UNSUPPORTED_GAP_MODE
            )
            return RecoveryApplyReport(
                db_path=plan_report.db_path,
                market=plan_report.market,
                target_date=plan_report.target_date,
                provider=provider,
                classification=plan_report.classification,
                gap_position=plan_report.gap_position,
                downstream_recompute_mode=plan_report.downstream_recompute_mode,
                dry_run=False,
                apply=True,
                apply_limit=limit or None,
                missing_before=plan_report.missing_tickers_count,
                provider_snapshot_count=0,
                recoverable_planned=0,
                not_found_in_provider=0,
                processed=0,
                inserted=0,
                already_present_skipped=0,
                invalid_ohlc_skipped=0,
                insert_failed=0,
                quarter_state_attempted=0,
                quarter_state_ok=0,
                quarter_state_failed=0,
                downstream_attempted=0,
                downstream_ok=0,
                downstream_failed=0,
                still_missing_after=plan_report.missing_tickers_count,
                commits_done=0,
                would_process=0,
                would_insert=0,
                would_run_downstream=0,
                provider_status="SKIPPED",
                status=status,
                apply_safety_note=plan_report.apply_safety_note,
                recoverable_tickers=[],
                not_found_in_provider_tickers=[],
            )
        if (
            plan_report.classification != "DAY_LEVEL_GAP"
            or plan_report.downstream_recompute_mode != "LATEST_DAY_RECOMPUTE_OK"
        ):
            return RecoveryApplyReport(
                db_path=plan_report.db_path,
                market=plan_report.market,
                target_date=plan_report.target_date,
                provider=provider,
                classification=plan_report.classification,
                gap_position=plan_report.gap_position,
                downstream_recompute_mode=plan_report.downstream_recompute_mode,
                dry_run=False,
                apply=True,
                apply_limit=limit or None,
                missing_before=plan_report.missing_tickers_count,
                provider_snapshot_count=0,
                recoverable_planned=0,
                not_found_in_provider=0,
                processed=0,
                inserted=0,
                already_present_skipped=0,
                invalid_ohlc_skipped=0,
                insert_failed=0,
                quarter_state_attempted=0,
                quarter_state_ok=0,
                quarter_state_failed=0,
                downstream_attempted=0,
                downstream_ok=0,
                downstream_failed=0,
                still_missing_after=plan_report.missing_tickers_count,
                commits_done=0,
                would_process=0,
                would_insert=0,
                would_run_downstream=0,
                provider_status="SKIPPED",
                status=STATUS_APPLY_BLOCKED_UNSUPPORTED_GAP_MODE,
                apply_safety_note=plan_report.apply_safety_note,
                recoverable_tickers=[],
                not_found_in_provider_tickers=[],
            )

    recoverable_tickers = sorted(plan_report.recoverable_tickers)
    to_process = recoverable_tickers[:limit] if limit and limit > 0 else recoverable_tickers
    not_found = list(plan_report.not_found_in_provider)

    base_report = RecoveryApplyReport(
        db_path=plan_report.db_path,
        market=plan_report.market,
        target_date=plan_report.target_date,
        provider=provider,
        classification=plan_report.classification,
        gap_position=plan_report.gap_position,
        downstream_recompute_mode=plan_report.downstream_recompute_mode,
        dry_run=dry_run,
        apply=apply,
        apply_limit=limit or None,
        missing_before=plan_report.missing_tickers_count,
        provider_snapshot_count=plan_report.provider_snapshot_tickers_count,
        recoverable_planned=len(to_process),
        not_found_in_provider=len(not_found),
        processed=0,
        inserted=0,
        already_present_skipped=0,
        invalid_ohlc_skipped=0,
        insert_failed=0,
        quarter_state_attempted=0,
        quarter_state_ok=0,
        quarter_state_failed=0,
        downstream_attempted=0,
        downstream_ok=0,
        downstream_failed=0,
        still_missing_after=plan_report.missing_tickers_count,
        commits_done=0,
        would_process=len(to_process),
        would_insert=len(to_process),
        would_run_downstream=len(to_process),
        provider_status=plan_report.provider_status,
        status=STATUS_DRY_RUN_COMPLETED if dry_run else STATUS_APPLY_COMPLETED,
        apply_safety_note=plan_report.apply_safety_note,
        recoverable_tickers=to_process,
        not_found_in_provider_tickers=not_found,
    )

    if dry_run:
        if not provider_snapshot or plan_report.provider_status == PROVIDER_STATUS_API_KEY_MISSING_OR_EMPTY_RESULT:
            base_report.status = STATUS_PROVIDER_EMPTY_OR_FAILED
            base_report.would_insert = 0
            base_report.would_run_downstream = 0
        return base_report

    if not provider_snapshot:
        base_report.status = STATUS_PROVIDER_EMPTY_OR_FAILED
        return base_report

    adapters = (runtime_builder or _build_runtime_adapters)(db_path)
    commit_threshold = max(1, commit_every)
    processed_since_commit = 0
    date_ranges = [
        StockUpdateDateRange(
            start_date=target_date,
            end_date_exclusive=_exclusive_end_date(target_date),
        )
    ]

    with sqlite3.connect(db_path) as conn:
        for ticker in to_process:
            base_report.processed += 1
            processed_since_commit += 1
            row = provider_snapshot.get(ticker)
            if row is None:
                continue
            if not _still_missing(
                conn,
                ticker=ticker,
                target_date=target_date,
                market=market,
            ):
                base_report.already_present_skipped += 1
            elif not _row_has_complete_ohlc(row):
                base_report.invalid_ohlc_skipped += 1
            else:
                try:
                    insert_status = _insert_recovered_ohlcv_row_if_missing(
                        conn,
                        row=row,
                    )
                except Exception as exc:
                    base_report.insert_failed += 1
                    base_report.errors.append(f"insert_failed {ticker}: {exc}")
                else:
                    if insert_status == "already_present_skipped":
                        base_report.already_present_skipped += 1
                    elif insert_status == "inserted":
                        base_report.inserted += 1
                        stock = adapters.stock_factory(ticker)
                        base_report.quarter_state_attempted += 1
                        try:
                            adapters.maybe_update_quarter_state(ticker, market, stock)
                            base_report.quarter_state_ok += 1
                        except Exception as exc:
                            base_report.quarter_state_failed += 1
                            base_report.errors.append(
                                f"quarter_state_failed {ticker}: {exc}"
                            )
                        base_report.downstream_attempted += 1
                        try:
                            downstream_result = execute_ticker_downstream_updates(
                                ticker=ticker,
                                stock=stock,
                                ohlcv_rows_inserted=1,
                                date_ranges=date_ranges,
                                sync_splits=adapters.sync_splits,
                                maybe_backfill_splits=adapters.maybe_backfill_splits,
                                calculate_divergences=adapters.calculate_divergences,
                                run_candlestick_analysis=adapters.run_candlestick_analysis,
                            )
                        except Exception as exc:
                            base_report.downstream_failed += 1
                            base_report.errors.append(
                                f"downstream_failed {ticker}: {exc}"
                            )
                        else:
                            if downstream_result.candlestick_error or (
                                downstream_result.divergence_attempted
                                and downstream_result.divergence_success is False
                            ):
                                base_report.downstream_failed += 1
                            else:
                                base_report.downstream_ok += 1
                    else:
                        base_report.insert_failed += 1

            if processed_since_commit >= commit_threshold:
                conn.commit()
                base_report.commits_done += 1
                progress(
                    f"PROGRESS processed={base_report.processed} inserted={base_report.inserted} commits_done={base_report.commits_done}"
                )
                processed_since_commit = 0

        conn.commit()
        base_report.commits_done += 1
        remaining_missing = 0
        for ticker in plan_report.missing_tickers:
            if _still_missing(
                conn,
                ticker=ticker,
                target_date=target_date,
                market=market,
            ):
                remaining_missing += 1
        base_report.still_missing_after = remaining_missing

    if base_report.errors or base_report.quarter_state_failed or base_report.downstream_failed:
        base_report.status = STATUS_APPLY_COMPLETED_WITH_WARNINGS
    return base_report


def _print_text_report(report: RecoveryApplyReport, missing_limit: int) -> None:
    print("MARKET_DAY_RECOVERY_APPLY")
    print(f"db: {report.db_path}")
    print(f"market: {report.market}")
    print(f"target_date: {report.target_date}")
    print(f"provider: {report.provider}")
    print()
    print(f"classification: {report.classification}")
    print(f"gap_position: {report.gap_position}")
    print(f"downstream_recompute_mode: {report.downstream_recompute_mode}")
    print(f"dry_run: {str(report.dry_run).lower()}")
    print(f"apply: {str(report.apply).lower()}")
    print(f"apply_limit: {report.apply_limit if report.apply_limit is not None else 'NONE'}")
    print()
    print(f"missing_before: {report.missing_before}")
    print(f"provider_snapshot_count: {report.provider_snapshot_count}")
    print(f"recoverable_planned: {report.recoverable_planned}")
    print(f"not_found_in_provider: {report.not_found_in_provider}")
    print(f"processed: {report.processed}")
    print(f"inserted: {report.inserted}")
    print(f"already_present_skipped: {report.already_present_skipped}")
    print(f"invalid_ohlc_skipped: {report.invalid_ohlc_skipped}")
    print(f"insert_failed: {report.insert_failed}")
    print(f"quarter_state_attempted: {report.quarter_state_attempted}")
    print(f"quarter_state_ok: {report.quarter_state_ok}")
    print(f"quarter_state_failed: {report.quarter_state_failed}")
    print(f"downstream_attempted: {report.downstream_attempted}")
    print(f"downstream_ok: {report.downstream_ok}")
    print(f"downstream_failed: {report.downstream_failed}")
    print(f"still_missing_after: {report.still_missing_after}")
    print(f"commits_done: {report.commits_done}")
    print(f"provider_status: {report.provider_status}")
    print(f"status: {report.status}")
    print()
    print("apply_safety_note:")
    print(report.apply_safety_note)
    print()
    print("recoverable_examples:")
    for ticker in report.recoverable_tickers[: max(0, missing_limit)]:
        print(ticker)
    print()
    print("not_found_examples:")
    for ticker in report.not_found_in_provider_tickers[: max(0, missing_limit)]:
        print(ticker)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        progress = print if args.format == "text" and args.apply and args.confirm_write else None
        report = build_recovery_apply_report(
            db_path=args.db,
            market=args.market,
            target_date=args.date,
            provider=args.provider,
            apply=args.apply,
            confirm_write=args.confirm_write,
            limit=args.limit,
            commit_every=args.commit_every,
            reference_window_days=args.reference_window_days,
            min_reference_count=args.min_reference_count,
            progress_callback=progress,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.format == "json":
        print(json.dumps(asdict(report), ensure_ascii=True, sort_keys=True))
    else:
        _print_text_report(report, args.missing_limit)
    return 0 if report.status != STATUS_FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
