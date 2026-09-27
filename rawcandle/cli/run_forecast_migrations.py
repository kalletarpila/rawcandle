from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.forecasts.schema import SCHEMA_VERSION, migrate_forecasts_db


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explicitly create or migrate a RawCandle forecasts database."
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Target forecasts.db path; no production path is assumed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.db)
    migrate_forecasts_db(path)
    print(f"SUMMARY status=SUCCESS schema_version={SCHEMA_VERSION} db={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
