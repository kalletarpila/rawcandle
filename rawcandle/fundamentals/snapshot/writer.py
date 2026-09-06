from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PublishResult:
    status: str
    path: Path


def report_filename(ticker: str, report_date: str) -> str:
    if (
        not ticker
        or ticker.startswith(".")
        or ".." in ticker
        or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for character in ticker)
    ):
        raise ValueError(f"UNSAFE_REPORT_TICKER:{ticker}")
    try:
        parsed = date.fromisoformat(report_date)
    except ValueError as exc:
        raise ValueError(f"INVALID_REPORT_DATE:{report_date}") from exc
    if parsed.isoformat() != report_date:
        raise ValueError(f"INVALID_REPORT_DATE:{report_date}")
    return f"{ticker}_{report_date}.md"


def publish_report(
    *,
    output_dir: Path,
    ticker: str,
    report_date: str,
    markdown: str,
    overwrite: bool = False,
) -> PublishResult:
    directory = output_dir.resolve()
    if directory.exists() and not directory.is_dir():
        raise NotADirectoryError(f"REPORT_OUTPUT_NOT_DIRECTORY:{directory}")
    directory.mkdir(parents=True, exist_ok=True)
    destination = (directory / report_filename(ticker, report_date)).resolve()
    if destination.parent != directory:
        raise PermissionError("REPORT_OUTPUT_ESCAPES_SELECTED_DIRECTORY")

    payload = markdown.encode("utf-8")
    existed = destination.exists()
    if existed:
        if not destination.is_file() or destination.is_symlink():
            raise FileExistsError(f"REPORT_DESTINATION_NOT_REGULAR_FILE:{destination}")
        if destination.read_bytes() == payload:
            return PublishResult("NO_CHANGE", destination)
        if not overwrite:
            raise FileExistsError(f"REPORT_EXISTS_DIFFERENT_USE_OVERWRITE:{destination}")

    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=directory
        )
        temporary_path = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
        return PublishResult("OVERWRITTEN" if existed else "CREATED", destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
