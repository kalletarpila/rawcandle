from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence


DEFAULT_DATA_DIR = Path("data") / "reverse"


def ensure_data_dir(path: str | Path | None = None) -> Path:
    """
    Ensure the reverse data directory exists and return it as a Path.
    """
    target = Path(path) if path else DEFAULT_DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def timestamp() -> str:
    """Return a filesystem friendly timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def notify(callback: Callable[[str], None] | None, message: str) -> None:
    """
    Safely invoke log/progress callbacks.
    """
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        logging.getLogger(__name__).debug("Log callback failed", exc_info=True)


def notify_progress(callback: Callable[[float], None] | None, value: float) -> None:
    """
    Send normalized progress updates (0–1) to callbacks.
    """
    if callback is None:
        return
    try:
        callback(max(0.0, min(1.0, value)))
    except Exception:
        logging.getLogger(__name__).debug("Progress callback failed", exc_info=True)


def normalize_feature_list(items: Sequence[str] | None) -> list[str]:
    """
    Normalize user supplied feature names into a clean unique list.
    """
    if not items:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in items:
        name = str(item).strip()
        if not name:
            continue
        if name not in seen:
            normalized.append(name)
            seen.add(name)
    return normalized


def parse_multiline_text(value: str | None) -> list[str]:
    """
    Split multiline text input into feature names.
    """
    if not value:
        return []
    parts = [
        item.strip()
        for line in value.splitlines()
        for item in line.split(",")
        if item.strip()
    ]
    return normalize_feature_list(parts)


def chunk(iterable: Sequence, size: int) -> Iterable[Sequence]:
    """
    Yield chunks from a sequence.
    """
    if size <= 0:
        size = len(iterable)
    for idx in range(0, len(iterable), size):
        yield iterable[idx : idx + size]
