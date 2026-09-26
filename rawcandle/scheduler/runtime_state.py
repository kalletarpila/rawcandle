from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def scheduler_status_path(log_dir: str) -> str:
    return str(Path(log_dir) / "stock_update_scheduler_status.json")


def read_scheduler_status(log_dir: str) -> dict[str, Any] | None:
    status_path = Path(scheduler_status_path(log_dir))
    if not status_path.exists():
        return None
    with status_path.open("r", encoding="utf-8") as status_file:
        return json.load(status_file)
