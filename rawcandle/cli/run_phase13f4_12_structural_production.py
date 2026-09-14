from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.phase12d import ROOT
from rawcandle.fundamentals.phase13f4_2_production import run_phase13f4_2


PHASE = "PHASE13F4_12_STRUCTURAL_REGIME_PRODUCTION_ACTIVATION"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13f4_12_structural_production"
BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13f4_12_structural_production"
DEFAULT_RUN_ID = "20260914T_PHASE13F4_12_PRODUCTION_ACTIVATION"
RESULT_FILENAME = "phase13f4_12_result.json"

OUTCOME_A = "OUTCOME A — STRUCTURAL-REGIME PACKAGE AND RELATIVE VALUATION ACTIVE AND STABLE IN PRODUCTION"
OUTCOME_B = "OUTCOME B — PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED"
OUTCOME_C = "OUTCOME C — MATERIAL DEPLOYMENT FAILURE; COMPLETE BACKUP SET RESTORED"
OUTCOME_D = "OUTCOME D — PRODUCTION OR ROLLBACK STATE COULD NOT BE PROVEN"

REQUIRED_COMMITS = ("1c35b1c", "863af30", "7de588e")
FULL_SUITE_ARTIFACT = ROOT / "temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix"
FULL_SUITE_EXPECTED = {
    "exit_code": 0,
    "timed_out": False,
    "summary_fragment": "2961 passed, 14 deselected, 8 warnings",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _git_commit_exists(commit: str) -> bool:
    return subprocess.run(
        ("git", "cat-file", "-e", f"{commit}^{{commit}}"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0


def _full_suite_gate(artifact_dir: Path) -> dict[str, Any]:
    exit_code_path = artifact_dir / "exit_code"
    summary_path = artifact_dir / "summary.json"
    log_path = artifact_dir / "pytest.log"
    heartbeat_path = artifact_dir / "heartbeat.jsonl"
    missing = [
        str(path)
        for path in (exit_code_path, summary_path, log_path, heartbeat_path)
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError("PHASE13F4_12_FULL_SUITE_EVIDENCE_MISSING:" + ",".join(missing))
    exit_code = int(exit_code_path.read_text(encoding="utf-8").strip())
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    log_text = ANSI_RE.sub("", log_path.read_text(encoding="utf-8", errors="replace"))
    summary_fragment = FULL_SUITE_EXPECTED["summary_fragment"]
    if exit_code != FULL_SUITE_EXPECTED["exit_code"] or summary.get("exit_code") != FULL_SUITE_EXPECTED["exit_code"]:
        raise RuntimeError(f"PHASE13F4_12_FULL_SUITE_EXIT_CODE:{exit_code}:{summary.get('exit_code')}")
    if summary.get("timed_out") is not FULL_SUITE_EXPECTED["timed_out"]:
        raise RuntimeError(f"PHASE13F4_12_FULL_SUITE_TIMEOUT:{summary.get('timed_out')}")
    if summary_fragment not in log_text:
        raise RuntimeError("PHASE13F4_12_FULL_SUITE_SUMMARY_NOT_FOUND")
    return {
        "artifact_dir": str(artifact_dir),
        "exit_code": exit_code,
        "summary_exit_code": summary.get("exit_code"),
        "timed_out": summary.get("timed_out"),
        "summary_fragment": summary_fragment,
        "log_path": str(log_path),
        "heartbeat_path": str(heartbeat_path),
    }


def phase13f4_12_pre_gate() -> dict[str, Any]:
    commits = {commit: _git_commit_exists(commit) for commit in REQUIRED_COMMITS}
    if not all(commits.values()):
        raise RuntimeError("PHASE13F4_12_REQUIRED_COMMIT_MISSING:" + json.dumps(commits, sort_keys=True))
    return {
        "required_commits": commits,
        "full_suite": _full_suite_gate(FULL_SUITE_ARTIFACT),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.4.12 structural-regime production activation")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.apply and not args.confirm_production:
        raise SystemExit("--apply requires --confirm-production")
    extra_gate = phase13f4_12_pre_gate()
    result = run_phase13f4_2(
        args.output,
        apply=args.apply,
        phase=PHASE,
        artifact_root=ARTIFACT_ROOT,
        backup_root=BACKUP_ROOT,
        default_run_id=DEFAULT_RUN_ID,
        result_filename=RESULT_FILENAME,
        outcome_a=OUTCOME_A,
        outcome_b=OUTCOME_B,
        outcome_c=OUTCOME_C,
        outcome_d=OUTCOME_D,
    )
    result["phase13f4_12_extra_gate"] = extra_gate
    output = Path(result["artifact_dir"])
    output.mkdir(parents=True, exist_ok=True)
    (output / RESULT_FILENAME).write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
