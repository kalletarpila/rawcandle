from __future__ import annotations

import argparse

from dev_tools.datacenter_dashboard_analysis_db_builder import (
    DEFAULT_TAXONOMY_VERSION,
    build_datacenter_dashboard_input_from_analysis_db,
)
from dev_tools.ecosystem_dashboard_structured_json import (
    dump_ecosystem_dashboard_input_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export analysis-db Datacenter dashboard semantics into EcosystemDashboardInput JSON."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--price-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--taxonomy-version", default=DEFAULT_TAXONOMY_VERSION)
    parser.add_argument("--market", default="usa")
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--source-mode", default="enrichment", choices=("enrichment", "raw-v0"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_result = build_datacenter_dashboard_input_from_analysis_db(
            analysis_db=args.analysis_db,
            price_db=args.price_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            taxonomy_version=args.taxonomy_version,
            market=args.market,
            max_rows=args.max_rows,
            source_mode=args.source_mode,
        )
        dump_ecosystem_dashboard_input_json(
            build_result.dashboard_input,
            args.output_json,
        )
    except FileNotFoundError as exc:
        print("SUMMARY datacenter_dashboard_analysis_db_export.status=FAILED")
        print(f"ERROR: {exc}")
        return 1
    except ValueError as exc:
        if args.source_mode == "enrichment":
            print(
                "SUMMARY datacenter_dashboard_analysis_db_export.warning="
                "ENRICHMENT_TABLES_MISSING"
            )
        print("SUMMARY datacenter_dashboard_analysis_db_export.status=FAILED")
        print(f"ERROR: {exc}")
        return 2

    dashboard_input = build_result.dashboard_input
    print("SUMMARY datacenter_dashboard_analysis_db_export.status=OK")
    print(
        "SUMMARY datacenter_dashboard_analysis_db_export.ecosystem_code="
        f"{dashboard_input.ecosystem_code}"
    )
    print(
        f"SUMMARY datacenter_dashboard_analysis_db_export.report_date={dashboard_input.report_date}"
    )
    print(f"SUMMARY datacenter_dashboard_analysis_db_export.analysis_db={args.analysis_db}")
    print(f"SUMMARY datacenter_dashboard_analysis_db_export.price_db={args.price_db}")
    print(f"SUMMARY datacenter_dashboard_analysis_db_export.output_json={args.output_json}")
    print(f"SUMMARY datacenter_dashboard_analysis_db_export.source_mode={args.source_mode}")
    print(
        "SUMMARY datacenter_dashboard_analysis_db_export.source_reports="
        f"{len(dashboard_input.source_reports)}"
    )
    print(
        "SUMMARY datacenter_dashboard_analysis_db_export.action_summary="
        f"{len(dashboard_input.action_summary)}"
    )
    print(
        f"SUMMARY datacenter_dashboard_analysis_db_export.market_map={len(dashboard_input.market_map)}"
    )
    print(
        f"SUMMARY datacenter_dashboard_analysis_db_export.watchlist={len(dashboard_input.watchlist)}"
    )
    print(
        f"SUMMARY datacenter_dashboard_analysis_db_export.tickers={len(dashboard_input.tickers)}"
    )
    print(
        "SUMMARY datacenter_dashboard_analysis_db_export.decision_trace="
        f"{len(dashboard_input.decision_trace)}"
    )
    print(
        f"SUMMARY datacenter_dashboard_analysis_db_export.readiness={dashboard_input.readiness}"
    )
    for warning in build_result.warnings:
        print(f"SUMMARY datacenter_dashboard_analysis_db_export.warning={warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
