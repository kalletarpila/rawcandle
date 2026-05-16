from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from main import RawCandleApp, _today_exclusive_end_date
from services.stock_update_service import format_stock_update_summary_lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually runnable stock update CLI using the service path."
    )
    parser.add_argument("--osakedata-db", required=True)
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--start-override")
    parser.add_argument("--today")
    parser.add_argument("--fetch-until-exclusive")
    return parser


def _print_failed(error: str) -> int:
    print("SUMMARY status=FAILED")
    print(f"SUMMARY error={error}")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    osakedata_db_path = Path(args.osakedata_db)
    if not osakedata_db_path.exists():
        return _print_failed(f"Missing osakedata db: {osakedata_db_path}")
    if not osakedata_db_path.is_file():
        return _print_failed(f"osakedata db is not a file: {osakedata_db_path}")

    analysis_db_path = Path(args.analysis_db)
    if not analysis_db_path.exists():
        return _print_failed(f"Missing analysis db: {analysis_db_path}")
    if not analysis_db_path.is_file():
        return _print_failed(f"analysis db is not a file: {analysis_db_path}")

    osakedata_dir = osakedata_db_path.resolve().parent
    analysis_dir = analysis_db_path.resolve().parent
    if osakedata_dir != analysis_dir:
        return _print_failed(
            "osakedata db and analysis db must be in the same directory for data_dir"
        )

    today = args.today or datetime.datetime.now().strftime("%Y-%m-%d")
    fetch_until_exclusive = (
        args.fetch_until_exclusive or _today_exclusive_end_date()
    )

    app = object.__new__(RawCandleApp)
    app.osakedata_db_path = str(osakedata_db_path)
    app.analysis_db_path = str(analysis_db_path)
    app.data_dir = str(osakedata_dir)

    try:
        result = app._run_stock_update_via_service(
            market=args.market,
            start_override=args.start_override,
            today=today,
            fetch_until_exclusive=fetch_until_exclusive,
        )
    except Exception as exc:
        return _print_failed(str(exc))

    for line in format_stock_update_summary_lines(result):
        print(line)

    print("=== UI SUMMARY ===")
    print(app._format_stock_update_service_result_for_ui(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
