from __future__ import annotations

import argparse
from typing import List, Optional

from rawcandle.scheduler.runner import run_scheduler_config
from services.stock_update_service import STATUS_FAILED, STATUS_OK, STATUS_OK_WITH_WARNINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run stock update scheduler config sequentially."
    )
    parser.add_argument("--config", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_scheduler_config(config_path=args.config)

    markets_ok = sum(1 for item in result.market_results if item.summary_status == STATUS_OK)
    markets_ok_with_warnings = sum(
        1 for item in result.market_results if item.summary_status == STATUS_OK_WITH_WARNINGS
    )
    markets_failed = sum(
        1 for item in result.market_results if item.summary_status == STATUS_FAILED
    )

    print(f"SUMMARY scheduler_status={result.overall_status}")
    print(f"SUMMARY markets_enabled={','.join(result.enabled_markets)}")
    print(f"SUMMARY markets_total={len(result.market_results)}")
    print(f"SUMMARY markets_ok={markets_ok}")
    print(f"SUMMARY markets_ok_with_warnings={markets_ok_with_warnings}")
    print(f"SUMMARY markets_failed={markets_failed}")
    print(f"SUMMARY summary_json_path={result.summary_json_path}")
    print(f"SUMMARY scheduler_skipped={1 if result.skipped else 0}")
    print(f"SUMMARY scheduler_skip_reason={result.skip_reason or ''}")

    for market_result in result.market_results:
        print(f"SUMMARY market.{market_result.market}.status={market_result.summary_status}")
        print(f"SUMMARY market.{market_result.market}.log_path={market_result.log_path}")

    return 0 if result.overall_status == STATUS_OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
