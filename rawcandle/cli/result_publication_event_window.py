from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.research.result_publication_event_window import build_event_window_dataset


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the read-only result-publication event-window V1 dataset.")
    parser.add_argument("--publication-csv", type=Path, required=True)
    parser.add_argument("--publication-metadata", type=Path, required=True)
    parser.add_argument("--ohlc-db", type=Path, default=Path("data/osakedata.db"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    metadata = build_event_window_dataset(
        args.publication_csv,
        args.publication_metadata,
        args.ohlc_db,
        args.output,
        args.metadata_output,
    )
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
