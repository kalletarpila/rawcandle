from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.fundamentals.admin.production_transaction import production_lock
from rawcandle.fundamentals.admin.publication_journal import guard_production_writes
from rawcandle.fundamentals.generations import PROJECT_ROOT, migrate_flat_layout


CONFIRMATION = "CONFIRM_FUNDAMENTALS_GENERATION_MIGRATION"


def _default_generation_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"migration_{stamp}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explicitly migrate flat Fundamentals production DBs to an atomic generation."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--generation-id", default=None)
    parser.add_argument("--scheduler-log-dir", default=None)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        parser.error(f"--confirm must equal {CONFIRMATION}")
    with production_lock(scheduler_log_dir=args.scheduler_log_dir):
        guard_production_writes(
            args.project_root / "data/.fundamentals_admin_publication_journal.json"
        )
        result = migrate_flat_layout(
            project_root=args.project_root,
            generation_id=args.generation_id or _default_generation_id(),
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
