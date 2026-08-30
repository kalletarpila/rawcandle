from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.fundamentals.schema.prototype import default_acceptance_root, prototype_paths, run_schema_prototype, utc_stamp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build disposable Fundamentals V4 schema prototype databases")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--acceptance-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd()
    if args.artifact_root:
        acceptance_root = args.acceptance_root or default_acceptance_root(repo_root)
        paths = prototype_paths(repo_root, timestamp=utc_stamp(), acceptance_root=acceptance_root)
        paths = paths.__class__(
            artifact_root=args.artifact_root,
            provider_db=args.artifact_root / "prototype_provider.db",
            canonical_db=args.artifact_root / "prototype_v4.db",
            analysis_db=args.artifact_root / "prototype_analysis.db",
            acceptance_root=acceptance_root,
            v3_db=paths.v3_db,
        )
    else:
        paths = prototype_paths(repo_root, acceptance_root=args.acceptance_root)
    summary = run_schema_prototype(paths)
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"provider_observations={summary['provider_counts']['provider_observations']}")
    print(f"canonical_quarters={summary['canonical_counts']['canonical_quarters']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
