from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Callable, Mapping, Optional

from rawcandle.cli.check_market_day_coverage import (
    CLASSIFICATION_DAY_LEVEL_GAP,
    CoverageReport,
    build_coverage_report,
)
from services.polygon_massive_grouped_daily_provider import (
    fetch_polygon_massive_grouped_daily_ohlcv_by_ticker,
)
from services.stock_update_service import StockOhlcvRow

PROVIDER_POLYGON_GROUPED_DAILY = "polygon_grouped_daily"
PROVIDER_STATUS_OK = "OK"
PROVIDER_STATUS_SKIPPED = "SKIPPED"
PROVIDER_STATUS_API_KEY_MISSING_OR_EMPTY_RESULT = "API_KEY_MISSING_OR_EMPTY_RESULT"
PROVIDER_STATUS_NO_RECOVERABLE_ROWS = "NO_RECOVERABLE_ROWS"
PROVIDER_STATUS_FAILED = "FAILED"


@dataclass(frozen=True)
class RecoveryPlanReport:
    db_path: str
    market: str
    target_date: str
    provider: str
    classification: str
    gap_position: str
    downstream_recompute_mode: str
    recovery_recommended: bool
    previous_reference_date: Optional[str]
    previous_reference_tickers_count: int
    next_reference_date: Optional[str]
    next_reference_tickers_count: int
    expected_tickers_count: int
    present_tickers_count: int
    missing_tickers_count: int
    coverage_ratio: float
    provider_status: str
    provider_snapshot_tickers_count: int
    recoverable_tickers_count: int
    not_found_in_provider_count: int
    invalid_provider_rows_count: int
    invalid_rows_filtered_by_provider: bool
    apply_safety_note: str
    missing_tickers: list[str]
    recoverable_tickers: list[str]
    not_found_in_provider: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only market day recovery planner."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument(
        "--provider",
        default=PROVIDER_POLYGON_GROUPED_DAILY,
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--missing-limit", type=int, default=100)
    parser.add_argument("--reference-window-days", type=int, default=10)
    parser.add_argument("--min-reference-count", type=int, default=1000)
    parser.add_argument("--skip-provider-fetch", action="store_true")
    return parser


def _parse_target_date(value: str) -> date:
    return date.fromisoformat(value)


def _build_apply_safety_note(coverage: CoverageReport) -> str:
    if (
        coverage.gap_position == "LATEST_OR_RIGHT_EDGE_GAP"
        and coverage.downstream_recompute_mode == "LATEST_DAY_RECOMPUTE_OK"
    ):
        return (
            "Latest/right-edge gap: future apply mode may insert recovered rows "
            "and run normal ticker-level downstream after each insert."
        )
    if (
        coverage.gap_position == "INTERIOR_GAP"
        and coverage.downstream_recompute_mode
        == "FROM_RECOVERED_DATE_FORWARD_REQUIRED"
    ):
        return (
            "Interior historical gap: future apply mode must recompute downstream "
            "from recovered date forward or use a safe full ticker recompute path. "
            "Do not treat as latest-day update."
        )
    return "No safe apply mode without additional reference data."


def build_recovery_plan_report(
    *,
    db_path: str,
    market: str,
    target_date: str,
    provider: str,
    reference_window_days: int,
    min_reference_count: int,
    skip_provider_fetch: bool,
    provider_fetcher: Optional[
        Callable[[str, date], Mapping[str, StockOhlcvRow]]
    ] = None,
) -> RecoveryPlanReport:
    if provider != PROVIDER_POLYGON_GROUPED_DAILY:
        raise ValueError(f"Unsupported provider: {provider}")

    coverage = build_coverage_report(
        db_path=db_path,
        market=market,
        target_date=target_date,
        reference_window_days=reference_window_days,
        min_reference_count=min_reference_count,
    )

    recovery_recommended = coverage.classification == CLASSIFICATION_DAY_LEVEL_GAP
    provider_status = PROVIDER_STATUS_SKIPPED
    provider_snapshot: Mapping[str, StockOhlcvRow] = {}

    if recovery_recommended and not skip_provider_fetch:
        fetcher = provider_fetcher or (
            lambda fetch_market, fetch_date: fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
                fetch_market,
                fetch_date,
            )
        )
        try:
            provider_snapshot = fetcher(market, _parse_target_date(target_date))
        except Exception:
            provider_snapshot = {}
            provider_status = PROVIDER_STATUS_FAILED
        else:
            if provider_snapshot:
                provider_status = PROVIDER_STATUS_OK
            else:
                provider_status = PROVIDER_STATUS_API_KEY_MISSING_OR_EMPTY_RESULT

    missing_set = set(coverage.missing_tickers)
    recoverable_tickers = sorted(
        ticker for ticker in missing_set if ticker in provider_snapshot
    )
    not_found_in_provider = sorted(missing_set - set(provider_snapshot))

    if provider_status == PROVIDER_STATUS_OK and not recoverable_tickers:
        provider_status = PROVIDER_STATUS_NO_RECOVERABLE_ROWS

    return RecoveryPlanReport(
        db_path=coverage.db_path,
        market=coverage.market,
        target_date=coverage.target_date,
        provider=provider,
        classification=coverage.classification,
        gap_position=coverage.gap_position,
        downstream_recompute_mode=coverage.downstream_recompute_mode,
        recovery_recommended=recovery_recommended,
        previous_reference_date=coverage.previous_reference_date,
        previous_reference_tickers_count=coverage.previous_reference_tickers_count,
        next_reference_date=coverage.next_reference_date,
        next_reference_tickers_count=coverage.next_reference_tickers_count,
        expected_tickers_count=coverage.expected_tickers_count,
        present_tickers_count=coverage.present_tickers_count,
        missing_tickers_count=coverage.missing_tickers_count,
        coverage_ratio=coverage.coverage_ratio,
        provider_status=provider_status,
        provider_snapshot_tickers_count=len(provider_snapshot),
        recoverable_tickers_count=len(recoverable_tickers),
        not_found_in_provider_count=len(not_found_in_provider),
        invalid_provider_rows_count=0,
        invalid_rows_filtered_by_provider=True,
        apply_safety_note=_build_apply_safety_note(coverage),
        missing_tickers=coverage.missing_tickers,
        recoverable_tickers=recoverable_tickers,
        not_found_in_provider=not_found_in_provider,
    )


def _print_text_report(report: RecoveryPlanReport, missing_limit: int) -> None:
    print("MARKET_DAY_RECOVERY_PLAN")
    print(f"db: {report.db_path}")
    print(f"market: {report.market}")
    print(f"target_date: {report.target_date}")
    print(f"provider: {report.provider}")
    print()
    print(f"classification: {report.classification}")
    print(f"gap_position: {report.gap_position}")
    print(f"downstream_recompute_mode: {report.downstream_recompute_mode}")
    print(f"recovery_recommended: {str(report.recovery_recommended).lower()}")
    print()
    print(f"previous_reference_date: {report.previous_reference_date or 'NONE'}")
    print(
        f"previous_reference_tickers: {report.previous_reference_tickers_count}"
    )
    print(f"next_reference_date: {report.next_reference_date or 'NONE'}")
    print(f"next_reference_tickers: {report.next_reference_tickers_count}")
    print()
    print(f"expected_tickers: {report.expected_tickers_count}")
    print(f"present_tickers: {report.present_tickers_count}")
    print(f"missing_tickers: {report.missing_tickers_count}")
    print(f"coverage_ratio: {report.coverage_ratio:.4f}")
    print()
    print(f"provider_status: {report.provider_status}")
    print(
        f"provider_snapshot_tickers: {report.provider_snapshot_tickers_count}"
    )
    print(f"recoverable_tickers: {report.recoverable_tickers_count}")
    print(f"not_found_in_provider: {report.not_found_in_provider_count}")
    print(f"invalid_provider_rows: {report.invalid_provider_rows_count}")
    print()
    print("apply_safety_note:")
    print(report.apply_safety_note)
    print()
    print("recoverable_examples:")
    for ticker in report.recoverable_tickers[: max(0, missing_limit)]:
        print(ticker)
    print()
    print("not_found_examples:")
    for ticker in report.not_found_in_provider[: max(0, missing_limit)]:
        print(ticker)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_recovery_plan_report(
            db_path=args.db,
            market=args.market,
            target_date=args.date,
            provider=args.provider,
            reference_window_days=args.reference_window_days,
            min_reference_count=args.min_reference_count,
            skip_provider_fetch=args.skip_provider_fetch,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.format == "json":
        print(json.dumps(asdict(report), ensure_ascii=True, sort_keys=True))
    else:
        _print_text_report(report, args.missing_limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
