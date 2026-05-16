from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from main import RawCandleApp, _today_exclusive_end_date
from services.stock_update_service import format_stock_update_summary_lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Developer smoke runner for the service-based stock update path."
    )
    parser.add_argument("--osakedata-db", required=True)
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--start-override")
    parser.add_argument("--today")
    parser.add_argument("--fetch-until-exclusive")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print("This is a developer smoke runner. Use copied databases for first tests.")

    osakedata_db_path = Path(args.osakedata_db)
    if not osakedata_db_path.exists():
        print("SUMMARY status=FAILED")
        print(f"SUMMARY error=Missing osakedata db: {osakedata_db_path}")
        return 1

    analysis_db_path = Path(args.analysis_db)
    if not analysis_db_path.exists():
        print("SUMMARY status=FAILED")
        print(f"SUMMARY error=Missing analysis db: {analysis_db_path}")
        return 1

    today = args.today or datetime.datetime.now().strftime("%Y-%m-%d")
    fetch_until_exclusive = (
        args.fetch_until_exclusive or _today_exclusive_end_date()
    )

    app = object.__new__(RawCandleApp)
    app.osakedata_db_path = str(osakedata_db_path)
    app.analysis_db_path = str(analysis_db_path)
    app.data_dir = str(osakedata_db_path.resolve().parent)

    try:
        result = app._run_stock_update_via_service(
            market=args.market,
            start_override=args.start_override,
            today=today,
            fetch_until_exclusive=fetch_until_exclusive,
        )
    except Exception as exc:
        print("SUMMARY status=FAILED")
        print(f"SUMMARY error={exc}")
        return 1

    for line in format_stock_update_summary_lines(result):
        print(line)

    print("=== UI SUMMARY ===")
    print(app._format_stock_update_service_result_for_ui(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
