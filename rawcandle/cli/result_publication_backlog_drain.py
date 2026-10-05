from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.admin.publication_backlog_drain import ROOT, DRAIN_NETWORK_BUDGET_SECONDS, run_backlog_drain
from rawcandle.fundamentals.admin.publication_allowlist import read_allowlist_csv, allowlist_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publication-only candidate-generation recent backlog drain; dry-run by default")
    parser.add_argument("--retry-days", type=int, default=60)
    parser.add_argument("--network-budget-seconds", type=float, default=DRAIN_NETWORK_BUDGET_SECONDS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--rehearsal-root", type=Path)
    parser.add_argument("--exact-allowlist", type=Path, help="CSV with company_id,fiscal_year,fiscal_quarter; dry-run by default")
    args = parser.parse_args(argv)
    root = args.rehearsal_root or ROOT
    if args.rehearsal_root and root.resolve() == ROOT:
        parser.error("Rehearsal root must not be the production root")
    try:
        allowed = read_allowlist_csv(args.exact_allowlist) if args.exact_allowlist is not None else None
        if allowed is not None:
            evidence = allowlist_evidence(allowed)
            print(json.dumps({"scope_mode": evidence["scope_mode"], "allowlist_count": evidence["allowlist_count"],
                              "allowlist_fingerprint": evidence["allowlist_fingerprint"]}), file=sys.stderr, flush=True)
        report = run_backlog_drain(project_root=root, apply=args.apply,
                                  confirm_production=args.confirm_production,
                                  retry_days=args.retry_days, network_budget_seconds=args.network_budget_seconds,
                                  **({"exact_quarter_allowlist": allowed} if allowed is not None else {}))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if report["status"] == "PARTIAL" else 0
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
