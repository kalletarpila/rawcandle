from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from rawcandle.reporting_v3_markdown import (
    render_daily_markdown_report,
    render_rolling2_markdown_report,
    render_rolling5_markdown_report,
    render_rolling30_markdown_report,
)
from rawcandle.reporting_v3_query import (
    build_daily_report_query_data,
    build_rolling2_report_query_data,
    build_rolling5_report_query_data,
    build_rolling30_report_query_data,
)


VALID_HORIZONS = ("rolling30", "rolling5", "rolling2", "daily")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write V3 Markdown prototype reports for selected horizons."
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database")
    parser.add_argument("--run-id", required=True, help="Eco report run_id")
    parser.add_argument("--out-dir", required=True, help="Output directory for Markdown files")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing Markdown files",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated subset of horizons: rolling30,rolling5,rolling2,daily",
    )
    return parser


def _resolve_horizons(only_value: str | None) -> list[str]:
    if only_value is None:
        return list(VALID_HORIZONS)
    horizons = [part.strip() for part in only_value.split(",") if part.strip()]
    if not horizons:
        raise ValueError("--only must specify at least one horizon")
    unknown = [horizon for horizon in horizons if horizon not in VALID_HORIZONS]
    if unknown:
        raise ValueError(f"unknown horizon(s): {', '.join(unknown)}")
    return horizons


def _line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _filename_for(query_data: Any) -> str:
    header = query_data.report_header
    ecosystem_code = str(header.ecosystem_code).lower()
    return f"{ecosystem_code}_v3_{header.window_code}_{header.signal_date}.md"


def _safe_output_path(out_dir: Path, filename: str) -> Path:
    out_dir_resolved = out_dir.resolve()
    output_path = (out_dir_resolved / filename).resolve()
    if output_path.parent != out_dir_resolved:
        raise ValueError("refusing to write outside the provided output directory")
    return output_path


def _write_report(output_path: Path, markdown: str, overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing file without --overwrite: {output_path}"
        )
    output_path.write_text(markdown, encoding="utf-8")


def _horizon_specs() -> dict[str, tuple[Callable[[str, str], Any], Callable[[Any], str]]]:
    return {
        "rolling30": (
            build_rolling30_report_query_data,
            render_rolling30_markdown_report,
        ),
        "rolling5": (
            build_rolling5_report_query_data,
            render_rolling5_markdown_report,
        ),
        "rolling2": (
            build_rolling2_report_query_data,
            render_rolling2_markdown_report,
        ),
        "daily": (
            build_daily_report_query_data,
            render_daily_markdown_report,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        horizons = _resolve_horizons(args.only)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_dir_resolved = out_dir.resolve()

        written: list[tuple[str, Path, int, int]] = []
        specs = _horizon_specs()
        for horizon in horizons:
            build_query_data, render_markdown = specs[horizon]
            query_data = build_query_data(args.db, args.run_id)
            markdown = render_markdown(query_data)
            output_path = _safe_output_path(out_dir_resolved, _filename_for(query_data))
            _write_report(output_path, markdown, args.overwrite)
            written.append(
                (
                    horizon,
                    output_path,
                    len(markdown.encode("utf-8")),
                    _line_count(markdown),
                )
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"db: {Path(args.db).resolve()}")
    print(f"run_id: {args.run_id}")
    print(f"out_dir: {out_dir_resolved}")
    print(f"overwrite: {args.overwrite}")
    print(f"horizons_written: {', '.join(horizon for horizon, _, _, _ in written)}")
    for horizon, output_path, byte_count, line_count in written:
        print(
            f"{horizon}: path={output_path} bytes={byte_count} lines={line_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
