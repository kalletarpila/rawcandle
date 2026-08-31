from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.fundamentals.schema.bootstrap_review import read_csv_records, review_paths, run_bootstrap_review


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve Fundamentals V4 production bootstrap review items")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--v4-1b-summary", type=Path)
    parser.add_argument("--tickers-csv", type=Path)
    parser.add_argument("--actions-csv", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = review_paths(Path.cwd(), v4_1b_summary_path=args.v4_1b_summary)
    if args.artifact_root:
        paths = paths.__class__(
            repo_root=paths.repo_root,
            artifact_root=args.artifact_root,
            provider_db=paths.provider_db,
            canonical_db=paths.canonical_db,
            analysis_db=paths.analysis_db,
            v4_1b_summary_path=paths.v4_1b_summary_path,
            v4_1b_bulk_csv=paths.v4_1b_bulk_csv,
        )
    tickers = read_csv_records(args.tickers_csv) if args.tickers_csv else None
    actions = read_csv_records(args.actions_csv) if args.actions_csv else None
    summary = run_bootstrap_review(paths, tickers_records=tickers, actions_records=actions)
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"permaticker_populated={summary['tickers_metadata']['permaticker_populated']}")
    print(f"ttm_input_ready={summary['ttm_readiness']['TTM_INPUT_READY']}")
    print(f"next_action={summary['next_action']}")
    return 0 if summary["classification"] != "V4_BOOTSTRAP_REVIEW_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
