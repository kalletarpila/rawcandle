from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.schema.phase12c_backfill import sha256
from rawcandle.fundamentals.schema.prototype import utc_stamp, write_csv, write_json
from rawcandle.fundamentals.schema.sharadar_history_policy import history_policy_metadata
from rawcandle.research.phase12c1_audit import discover_history_policy, production_state


EXPECTED_SOURCE_SHA256 = "dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36"
PHASE12C1_REFERENCE_FINGERPRINT = "43274d224adb48af0f1101c868dedb592b58dca918b499640dd353ce7933a32d"
EXPECTED_PROVIDER_COUNTS = {"observations": 179853, "ARQ": 89432, "MRQ": 90421}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate read-only Phase 12C.2 policy evidence")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--preflight-inventory", type=Path, default=None)
    parser.add_argument("--verification-status", choices=("PASS", "FAIL", "NOT_RUN"), default="NOT_RUN")
    parser.add_argument("--test-summary", action="append", default=[])
    return parser.parse_args()


def _find_source(repo_root: Path) -> Path:
    matches = sorted(
        (repo_root / "temp/fundamentals_v4_phase12c").glob(
            "*/sharadar_fundamentals_10y.zip"
        )
    )
    if not matches:
        return repo_root / "temp/fundamentals_v4_phase12c/MISSING/sharadar_fundamentals_10y.zip"
    return matches[-1]


def _baseline(repo_root: Path, supplied: Path | None) -> tuple[Path, dict[str, Any]]:
    path = supplied or (
        repo_root / "temp/fundamentals_v4_phase12c1/20260910T_PHASE12C1_FINAL/production_preflight_postflight.json"
    )
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return path, payload["postflight"]


def _five_year_classification(path: str, text: str) -> str:
    if path.startswith("tests/"):
        return "LOW_LEVEL_SEPARATION_OR_REGRESSION_TEST"
    if path.endswith("sharadar_acceptance.py"):
        return "LEGACY_SINGLE_COMPANY_ACCEPTANCE_LABEL_NO_BULK_HORIZON"
    if path.endswith("phase12c_backfill.py"):
        return "LEGACY_STAGED_FILENAME_DISK_ESTIMATE_ONLY"
    if "phase12c1" in path.lower():
        return "HISTORICAL_PHASE12C1_AUDIT_OR_FIXTURE"
    if path.startswith("docs/"):
        return "HISTORICAL_DOCUMENTATION"
    return "REVIEWED_NON_PRODUCTION_REFERENCE"


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output = repo_root / "temp/fundamentals_v4_phase12c2" / (args.timestamp or utc_stamp())
    output.mkdir(parents=True, exist_ok=False)

    baseline_path, before = _baseline(repo_root, args.preflight_inventory)
    after = production_state(repo_root)
    policy_audit, references = discover_history_policy(repo_root)
    policy = history_policy_metadata()
    source = _find_source(repo_root)
    source_exists = source.exists()
    source_hash = sha256(source) if source_exists else None

    by_dimension = {
        row["dimension"]: row for row in after["provider_counts"]["by_dimension"]
    }
    provider_counts_match = (
        after["provider_counts"]["totals"]["observations"] == EXPECTED_PROVIDER_COUNTS["observations"]
        and by_dimension["ARQ"]["rows"] == EXPECTED_PROVIDER_COUNTS["ARQ"]
        and by_dimension["MRQ"]["rows"] == EXPECTED_PROVIDER_COUNTS["MRQ"]
    )
    immutable = before["aggregate_fingerprint"] == after["aggregate_fingerprint"]
    source_ok = source_exists and source_hash == EXPECTED_SOURCE_SHA256
    policy_ok = policy_audit["verdict"] == "PERMANENT_TEN_YEAR_POLICY_VERIFIED"

    write_json(
        output / "production_preflight_postflight.json",
        {
            "baseline_source": str(baseline_path.relative_to(repo_root)),
            "preflight": before,
            "postflight": after,
            "aggregate_fingerprint_unchanged": immutable,
            "phase12c1_reference_fingerprint": PHASE12C1_REFERENCE_FINGERPRINT,
            "phase12c1_reference_differs_due_to_pre_phase_reports": (
                before["aggregate_fingerprint"] != PHASE12C1_REFERENCE_FINGERPRINT
            ),
            "provider_counts_match_phase12c": provider_counts_match,
        },
    )
    write_csv(
        output / "changed_production_path_map.csv",
        [
            {"path": path, "role": role}
            for path, role in (
                ("rawcandle/fundamentals/schema/sharadar_history_policy.py", "authoritative policy"),
                ("rawcandle/fundamentals/schema/production_bootstrap.py", "production bootstrap/download/ingest"),
                ("rawcandle/cli/run_fundamentals_v4_production_bootstrap.py", "normal bootstrap CLI"),
                ("rawcandle/fundamentals/schema/phase12c_backfill.py", "staged append-only backfill"),
                ("rawcandle/cli/run_phase12c_sharadar_backfill.py", "Phase 12C staging CLI"),
                ("rawcandle/fundamentals/schema/prototype.py", "generated bootstrap-plan wording"),
                ("rawcandle/research/phase12c1_audit.py", "policy discovery audit"),
            )
        ],
    )
    write_csv(
        output / "old_versus_new_behavior.csv",
        [
            {"behavior": "omitted production horizon", "before": "5 years", "after": "10 years minimum"},
            {"behavior": "explicit production horizon below 10", "before": "accepted", "after": "rejected before preflight/network"},
            {"behavior": "production downloader name", "before": "five-year-specific", "after": "neutral fundamentals name"},
            {"behavior": "local retention", "before": "append-only", "after": "append-only unchanged"},
            {"behavior": "universe and dimensions", "before": "current bootstrap ARQ/MRQ", "after": "unchanged"},
        ],
    )
    write_json(output / "history_policy_contract.json", policy)
    five_year_rows = [
        {
            **row,
            "classification": _five_year_classification(row["path"], row["text"]),
        }
        for row in references
        if "5" in row["text"] and (
            "years" in row["text"].lower() or "5 Years" in row["text"] or "5y" in row["text"].lower()
        )
    ]
    write_csv(output / "applicable_five_year_reference_audit.csv", five_year_rows)
    write_json(
        output / "source_archive_verification.json",
        {
            "path": str(source.relative_to(repo_root)),
            "exists": source_exists,
            "size_bytes": source.stat().st_size if source_exists else None,
            "sha256": source_hash,
            "expected_sha256": EXPECTED_SOURCE_SHA256,
            "hash_matches": source_ok,
            "survives_normal_temp_cleanup": False,
            "recommended_action_before_phase12c3": "MOVE_TO_MANAGED_LOCAL_ARCHIVE_UNDER_SEPARATE_AUTHORIZATION",
        },
    )
    write_json(
        output / "deterministic_test_evidence.json",
        {"status": args.verification_status, "summaries": args.test_summary},
    )
    (output / "commands_run.txt").write_text(
        "\n".join([
            "python3 -m rawcandle.cli.run_phase12c2_policy_evidence --verification-status <STATUS>",
            "pytest -q tests/test_phase12c2_sharadar_history_policy.py tests/test_fundamentals_v4_production_bootstrap.py tests/test_phase12c_sharadar_backfill.py tests/test_phase12c1_retention_universe_audit.py",
            "pytest -q tests/test_production_database_isolation.py",
            "pytest -q tests/test_fundamentals_v4*.py tests/test_phase12c*.py",
            "python3 -m compileall -q rawcandle tests",
            "git diff --check",
            "All provider access was mocked; no credentials were loaded or serialized.",
        ]) + "\n",
        encoding="utf-8",
    )

    outcome_a = immutable and provider_counts_match and source_ok and policy_ok and args.verification_status == "PASS"
    decision = {
        "outcome": "OUTCOME A - PERMANENT TEN-YEAR POLICY VERIFIED" if outcome_a else "OUTCOME B - PERMANENT POLICY STILL INCOMPLETE",
        "policy_verified": policy_ok,
        "production_immutable": immutable,
        "provider_counts_match_phase12c": provider_counts_match,
        "source_archive_verified": source_ok,
        "tests": args.verification_status,
        "phase12c1_historical_universe_blocker_retained": True,
        "phase12d_authorized": False,
    }
    write_json(output / "decision.json", decision)
    print(json.dumps({"output": str(output), **decision}, sort_keys=True))
    return 0 if outcome_a else 1


if __name__ == "__main__":
    raise SystemExit(main())
