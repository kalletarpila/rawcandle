from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.fundamentals.schema.identity_calendar_bootstrap import identity_calendar_paths, run_identity_calendar_prototype


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build disposable Fundamentals V4 identity/calendar bootstrap prototype")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--acceptance-root", type=Path)
    parser.add_argument("--bootstrap-csv", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd()
    paths = identity_calendar_paths(
        repo_root,
        acceptance_root=args.acceptance_root,
        bootstrap_csv=args.bootstrap_csv,
    )
    if args.artifact_root:
        paths = paths.__class__(
            artifact_root=args.artifact_root,
            provider_db=args.artifact_root / "prototype_provider.db",
            canonical_db=args.artifact_root / "prototype_v4.db",
            analysis_db=args.artifact_root / "prototype_analysis.db",
            acceptance_root=paths.acceptance_root,
            bootstrap_csv=paths.bootstrap_csv,
        )
    summary = run_identity_calendar_prototype(paths)
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"csv_tickers={summary['bootstrap_source']['csv_tickers']}")
    print(f"company_ciks_imported={summary['bootstrap_source']['company_ciks_imported']}")
    print(f"fiscal_anchor_rows={summary['fiscal_calendar']['normalized_anchor_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
