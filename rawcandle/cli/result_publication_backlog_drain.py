from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.admin.publication_backlog_drain import ROOT, DRAIN_NETWORK_BUDGET_SECONDS, run_backlog_drain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publication-only candidate-generation recent backlog drain; dry-run by default")
    parser.add_argument("--retry-days", type=int, default=60)
    parser.add_argument("--network-budget-seconds", type=float, default=DRAIN_NETWORK_BUDGET_SECONDS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--rehearsal-root", type=Path)
    args = parser.parse_args(argv)
    root = args.rehearsal_root or ROOT
    if args.rehearsal_root and root.resolve() == ROOT:
        parser.error("Rehearsal root must not be the production root")
    try:
        report = run_backlog_drain(project_root=root, apply=args.apply,
                                  confirm_production=args.confirm_production,
                                  retry_days=args.retry_days, network_budget_seconds=args.network_budget_seconds)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if report["status"] == "PARTIAL" else 0
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
