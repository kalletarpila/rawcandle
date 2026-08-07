from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.datacenter_taxonomy_structural_draft import (
    ai_software_v3_request,
    build_structural_taxonomy_draft,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the Datacenter V3 AI software structural taxonomy draft."
    )
    parser.add_argument(
        "--base-taxonomy-csv",
        default="data/datacenter_taxonomy_full_v2_1.csv",
        help="Base taxonomy CSV to copy before applying V3 draft additions.",
    )
    parser.add_argument(
        "--output-dir",
        default="temp/datacenter_taxonomy_v3_ai_software_layer",
        help="Directory for draft CSV and validation artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = ai_software_v3_request(
        base_taxonomy_csv=Path(args.base_taxonomy_csv),
        output_dir=Path(args.output_dir),
    )
    result = build_structural_taxonomy_draft(request)
    print(json.dumps(result.validation_summary, indent=2, sort_keys=True))
    return 0 if result.validation_summary.get("validation_status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
