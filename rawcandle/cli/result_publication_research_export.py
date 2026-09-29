from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.result_publication_research_export import ExportRequest, run_research_export


ROOT = Path(__file__).resolve().parents[2]


def _tokens(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(
        token.strip().upper()
        for value in values
        for token in value.split(",")
        if token.strip()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export read-only daily-research result-publication boundaries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  Single ticker:
    --output exports/aapl.csv --tickers AAPL
  Full usable FY2025+ CSV:
    --output exports/result_publication.csv
  Include unusable rows:
    --output exports/all.csv --include-unusable
  Live Yahoo with frozen observations:
    --output exports/live.csv --yahoo-mode live --write-yahoo-observations temp/yahoo.json
  Frozen Yahoo and reviewed V2:
    --output exports/frozen.csv --yahoo-mode frozen --yahoo-observations temp/yahoo.json \\
      --v2-candidates \
        data/research/result_publication/v2_candidates_initial_result_sec_semantic_v2_research_2026-09-29.json
""",
    )
    parser.add_argument("--canonical-db", type=Path, default=ROOT / "data/fundamentals_v4.db")
    parser.add_argument("--ohlc-db", type=Path, default=ROOT / "data/osakedata.db")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--company-ids", nargs="*", type=int, default=[])
    parser.add_argument("--from-fiscal-year", type=int, default=2025)
    parser.add_argument("--to-fiscal-year", type=int)
    parser.add_argument("--include-unusable", action="store_true")
    parser.add_argument("--yahoo-mode", choices=("none", "frozen", "live"), default="none")
    parser.add_argument("--yahoo-observations", type=Path)
    parser.add_argument("--write-yahoo-observations", type=Path)
    parser.add_argument("--v2-candidates", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata = run_research_export(
            ExportRequest(
                canonical_db=args.canonical_db,
                ohlc_db=args.ohlc_db,
                output=args.output,
                output_format=args.format,
                metadata_output=args.metadata_output,
                tickers=_tokens(args.tickers),
                company_ids=tuple(args.company_ids),
                from_fiscal_year=args.from_fiscal_year,
                to_fiscal_year=args.to_fiscal_year,
                include_unusable=args.include_unusable,
                yahoo_mode=args.yahoo_mode,
                yahoo_observations=args.yahoo_observations,
                write_yahoo_observations=args.write_yahoo_observations,
                v2_candidates=args.v2_candidates,
            )
        )
        print(json.dumps(metadata, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
