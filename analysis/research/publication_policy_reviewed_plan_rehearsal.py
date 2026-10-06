"""Copy-only reviewed V1 plan proof against an immutable production-shaped clone."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil

from rawcandle.fundamentals.admin.publication_journal import sha256_file
from rawcandle.fundamentals.admin.reviewed_publication_plan import (
    prepare_reviewed_plan,
    rehearse_reviewed_plan,
    load_plan,
    _require_clean_journal,
)
from rawcandle.fundamentals.generations import (
    resolve_active_generation,
    active_manifest_path,
)
from rawcandle.fundamentals.publication_event_policy import (
    PUBLICATION_EVENT_POLICY_V1 as V1,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--policy-evidence", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    source, runtime = args.source_root.resolve(), args.runtime_root.resolve()
    if (
        source == runtime
        or source in runtime.parents
        or runtime in source.parents
        or runtime.exists()
    ):
        raise ValueError("POLICY_REHEARSAL_ROOT_MUST_BE_NEW_AND_ISOLATED")
    _require_clean_journal(source)
    binding = resolve_active_generation(source, require_generation=True)
    paths = {
        **binding.role_paths(),
        "pointer": active_manifest_path(source),
        "journal": source / "data/.fundamentals_admin_publication_journal.json",
        "queue": source / "fundamental_reports/fundamentals_refresh_review_queue.db",
        "scheduler": source / "scheduler_config.json",
    }
    before = {name: sha256_file(path) for name, path in paths.items() if path.is_file()}
    clone = runtime / "source_copy"
    print("COPY_SOURCE_GENERATION", flush=True)
    shutil.copytree(
        binding.generation_dir,
        clone / "data/fundamentals_generations" / binding.generation_id,
    )
    shutil.copyfile(
        binding.generation_dir / "generation_manifest.json", active_manifest_path(clone)
    )
    supplied = json.loads(args.policy_evidence.read_text())
    allowlist = runtime / "reviewed_cohort.csv"
    with allowlist.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("company_id", "fiscal_year", "fiscal_quarter"))
        writer.writerows(
            tuple(
                c["quarter"][k] for k in ("company_id", "fiscal_year", "fiscal_quarter")
            )
            for c in supplied["cases"]
        )
    plan_path = runtime / "reviewed_policy_plan.json"
    print("PREPARE_POLICY_PLAN_ON_COPY", flush=True)
    prepared = prepare_reviewed_plan(
        project_root=clone,
        allowlist_path=allowlist,
        output_plan=plan_path,
        publication_event_policy=V1,
        policy_evidence_path=args.policy_evidence,
        as_of_date=args.as_of_date,
    )
    plan = load_plan(plan_path)
    print("REHEARSE_SAME_IMMUTABLE_PLAN", flush=True)
    result = rehearse_reviewed_plan(
        project_root=clone,
        plan_path=plan_path,
        rehearsal_root=runtime / "rehearsal",
        as_of_date=args.as_of_date,
    )
    after = {name: sha256_file(path) for name, path in paths.items() if path.is_file()}
    if before != after:
        raise RuntimeError("POLICY_REHEARSAL_PRODUCTION_SOURCE_CHANGED")
    labels = {
        tuple(
            c["quarter"][k] for k in ("company_id", "fiscal_year", "fiscal_quarter")
        ): c["ticker"]
        for c in supplied["cases"]
    }
    rows = []
    for c in plan["policy_cases"]:
        key = (c["company_id"], c["fiscal_year"], c["fiscal_quarter"])
        decision = c["policy_decision"]
        rows.append(
            {
                "ticker": labels[key],
                "company_id": key[0],
                "fiscal_year": key[1],
                "fiscal_quarter": key[2],
                "legacy_status": c["prior_status"],
                "policy_version": V1,
                "policy_result": c["policy_result"],
                "prepared": c["policy_result"] == "POLICY_V1_UNIQUE",
                "eligible_candidate_count": decision["eligible_count"],
                "relation_count": len(decision["relation_edges"]),
                "selected_accession": c["parent_accession"],
                "selected_timestamp": c["parent_acceptance_timestamp"],
                "review_reason": decision["review_reason"],
                "plan_id": plan["plan_id"],
                "plan_fingerprint": plan["plan_fingerprint"],
                "policy_decision_fingerprint": c["policy_decision_fingerprint"],
                "rehearsal_result": (
                    "APPLIED_VERIFIED"
                    if c["policy_result"] == "POLICY_V1_UNIQUE"
                    else "UNTOUCHED_REVIEW"
                ),
            }
        )
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "prepared": prepared,
        "rehearsal_status": result["status"],
        "unrelated_changes": result["unrelated_changes"],
        "network_requests": result["writer_result"]["publication"]["network"].get(
            "network_requests", 0
        ),
        "applied_count": result["writer_result"]["publication"]["applied_count"],
        "journal_state": result["writer_result"]["journal_state"],
        "production_hashes_unchanged": before == after,
        "production_hashes": before,
        "filtering": dict(
            Counter(
                c["policy_decision"]["filtering_result"] for c in plan["policy_cases"]
            )
        ),
        "source_generation": binding.generation_id,
        "runtime_root": str(runtime),
        "plan_path": str(plan_path),
    }
    (runtime / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
