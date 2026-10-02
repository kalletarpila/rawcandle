from __future__ import annotations

import argparse
import json
from dataclasses import replace

from rawcandle.scheduler.config import (
    SUPPORTED_FUNDAMENTALS_REFRESH_MODES,
    read_scheduler_config,
    validate_scheduler_config,
    write_scheduler_config,
)


FULL_WORKFLOW_CONFIRMATION = "CONFIRM_SCHEDULER_FULL_WORKFLOW"


def configure_mode(
    *, config_path: str, mode: str, confirmation: str = "",
) -> dict[str, str]:
    if mode not in SUPPORTED_FUNDAMENTALS_REFRESH_MODES:
        raise ValueError("FUNDAMENTALS_REFRESH_SCHEDULER_MODE_INVALID")
    current = read_scheduler_config(config_path)
    if (
        mode == "FULL_WORKFLOW"
        and current.fundamentals_refresh_mode != mode
        and confirmation != FULL_WORKFLOW_CONFIRMATION
    ):
        raise PermissionError(
            "FUNDAMENTALS_REFRESH_FULL_WORKFLOW_CONFIRMATION_REQUIRED"
        )
    updated = validate_scheduler_config(
        replace(current, fundamentals_refresh_mode=mode)
    )
    write_scheduler_config(config_path, updated)
    return {
        "status": (
            "UPDATED"
            if current.fundamentals_refresh_mode != mode
            else "UNCHANGED"
        ),
        "previous_mode": current.fundamentals_refresh_mode,
        "configured_mode": updated.fundamentals_refresh_mode,
        "config_path": config_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure the Fundamentals Refresh scheduler execution mode."
    )
    parser.add_argument("--config", default="scheduler_config.json")
    parser.add_argument(
        "--mode", choices=SUPPORTED_FUNDAMENTALS_REFRESH_MODES, required=True,
    )
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    result = configure_mode(
        config_path=args.config, mode=args.mode, confirmation=args.confirm,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
