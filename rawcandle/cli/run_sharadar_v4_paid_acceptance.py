from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.fundamentals.sharadar_acceptance import AcceptancePaths, run_paid_acceptance, utc_stamp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Sharadar paid 5-year Fundamentals V4 acceptance from RawCandle")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("temp/fundamentals_v4_0d_sharadar_paid_acceptance") / utc_stamp(),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_paid_acceptance(AcceptancePaths(artifact_root=args.artifact_root))
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"network_requests={summary['network_requests']}")
    return 0 if summary["v4_canonical_schema_may_now_be_designed"] == "YES" else 2


if __name__ == "__main__":
    raise SystemExit(main())
