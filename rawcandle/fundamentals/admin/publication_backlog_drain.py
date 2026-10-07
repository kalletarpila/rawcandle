"""Explicit publication-only immutable-generation maintenance."""
from __future__ import annotations

import json
import math
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Sequence
from uuid import uuid4

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.candidate_publication import select_candidate_scope, run_candidate_publication
from rawcandle.fundamentals.admin.production_transaction import production_lock, SimulatedTransactionCrash
from rawcandle.fundamentals.admin.publication_journal import (
    guard_production_writes, prepare_journal, update_journal, activate_prepared_generation,
    restore_old_generation, sqlite_verification, sha256_file,
    load_journal, is_incomplete,
)
from rawcandle.fundamentals.admin.refresh_production import _verified_backups, _candidate_manifest
from rawcandle.fundamentals.generations import resolve_active_generation, active_manifest_path, prepare_generation_from_candidates
from rawcandle.fundamentals.result_publication import SecClient
from rawcandle.fundamentals.admin.publication_allowlist import (
    normalize_allowlist, allowlist_evidence, select_exact_scope, assert_scope_subset,
)
from rawcandle.fundamentals.admin.reviewed_publication_plan import (
    load_plan, revalidate_plan_state, run_plan_candidate, plan_scope_evidence, SCOPE_MODE,
)

ROOT = Path(__file__).resolve().parents[3]
DRAIN_NETWORK_BUDGET_SECONDS = 1800


def run_backlog_drain(*, project_root: Path = ROOT, apply: bool = False,
                      confirm_production: bool = False, retry_days: int = 60,
                      network_budget_seconds: float = DRAIN_NETWORK_BUDGET_SECONDS,
                      client: SecClient | None = None, as_of_date: str | None = None,
                      inject_crash_at: str | None = None,
                      exact_quarter_allowlist: Collection[Sequence[Any]] | None = None,
                      reviewed_apply_plan: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    root = project_root.resolve()
    if not math.isfinite(network_budget_seconds) or network_budget_seconds <= 0:
        raise ValueError("PUBLICATION_NETWORK_BUDGET_INVALID")
    if reviewed_apply_plan is not None and (exact_quarter_allowlist is not None or client is not None):
        raise ValueError("PUBLICATION_PLAN_INPUT_MODES_INCOMPATIBLE")
    plan = load_plan(reviewed_apply_plan) if reviewed_apply_plan is not None else None
    # Form 6-K is authorized only by a fully validated schema-3 reviewed plan.
    # It still passes confirmation, journal/recovery and locked state guards below.
    allowed = (normalize_allowlist(plan["prepared_keys"]) if plan is not None else
               normalize_allowlist(exact_quarter_allowlist) if exact_quarter_allowlist is not None else None)
    journal_path = root / "data/.fundamentals_admin_publication_journal.json"
    prior_journal = load_journal(journal_path) if apply else None
    exact_recovery = bool(prior_journal and prior_journal.get("scope_evidence") and
                          (is_incomplete(prior_journal) or prior_journal["state"] == "RECOVERED"))
    day = as_of_date or datetime.now(timezone.utc).date().isoformat()
    binding = resolve_active_generation(root, require_generation=True)
    if apply and exact_recovery:
        scope = {"quarter_keys": [], "retry_selected": 0}
    elif plan is not None and not apply:
        scope = revalidate_plan_state(plan, binding, as_of_date=day)
    elif allowed is None:
        scope = select_candidate_scope(binding.role_paths()["canonical"], [], as_of_date=day,
                                       retry_days=retry_days, retry_max_quarters=None)
    elif not apply:
        scope = select_exact_scope(binding.role_paths()["canonical"], allowed, as_of_date=day, retry_days=retry_days)
    else:
        # No authoritative selection outside the writer lock in exact apply mode.
        scope = {**allowlist_evidence(allowed), "quarter_keys": [], "retry_selected": 0}
    result: dict[str, Any] = {
        "operation": "RESULT_PUBLICATION_BACKLOG_DRAIN", "apply": apply,
        "as_of_date": day, "source_generation": binding.generation_id,
        "network_budget_seconds": network_budget_seconds, "scope": scope,
        "status": "SKIPPED" if not scope["quarter_keys"] else "DRY_RUN",
        "attempted_current_backlog": 0, "still_open_after_attempt": scope["retry_selected"],
        "rollback": {"status": "NOT_REQUIRED"},
        "scope_mode": SCOPE_MODE if plan is not None else "RECENT_OPEN_DEFAULT" if allowed is None else allowlist_evidence(allowed)["scope_mode"],
    }
    if plan is not None:
        result["reviewed_plan"] = plan_scope_evidence(plan)
    if not apply:
        if allowed is not None and not scope["quarter_keys"]:
            result["skip_reason"] = "NO_PREPARED_PLAN_KEYS" if plan is not None else "NO_ELIGIBLE_ALLOWLIST_ITEMS"
        return result
    if not confirm_production:
        raise PermissionError("PUBLICATION_DRAIN_PRODUCTION_CONFIRMATION_REQUIRED")
    run_id = "publication_drain_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    run_dir = root / "fundamental_reports" / "publication_drains" / run_id
    lane = root / "temp" / run_id
    journal = None
    with production_lock(lock_path=root / "temp/.fundamentals_admin_production.lock",
                         scheduler_log_dir=None if root == ROOT else str(root / "logs")):
        guard_production_writes(journal_path)
        recovered = load_journal(journal_path)
        if recovered and recovered["state"] == "RECOVERED" and recovered.get("scope_evidence"):
            fence = recovered["scope_evidence"]
            if fence.get("scope_mode") == SCOPE_MODE:
                if plan is None or plan["plan_fingerprint"] != fence["plan_fingerprint"]:
                    raise RuntimeError("PUBLICATION_PLAN_RECOVERY_SAME_PLAN_REQUIRED")
                if (fence.get("policy_mode") == "FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1"
                        or plan.get("policy_mode") == "FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1") and any(
                            fence.get(name) != value for name, value in plan_scope_evidence(plan).items()):
                    raise RuntimeError("PUBLICATION_FORM6K_RECOVERY_SAME_PLAN_REQUIRED")
                if plan.get("policy_mode") == "PUBLICATION_EVENT_POLICY_V1" and any(
                    fence.get(name) != value for name,value in plan_scope_evidence(plan).items()
                ):
                    raise RuntimeError("PUBLICATION_POLICY_RECOVERY_SAME_POLICY_PLAN_REQUIRED")
            elif plan is not None or allowed is None or allowlist_evidence(allowed)["allowlist_fingerprint"] != fence["allowlist_fingerprint"]:
                raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_RECOVERY_SCOPE_REQUIRED")
        binding = resolve_active_generation(root, require_generation=True)
        if binding.generation_id != result["source_generation"]:
            raise RuntimeError("PUBLICATION_DRAIN_ACTIVE_GENERATION_DRIFT")
        # Re-select under the writer lock before freezing the exact scope.
        if plan is not None:
            locked_plan = load_plan(reviewed_apply_plan)
            if locked_plan["plan_fingerprint"] != plan["plan_fingerprint"]:
                raise RuntimeError("PUBLICATION_PLAN_ARTIFACT_DRIFT")
        if plan is not None:
            scope = revalidate_plan_state(plan, binding, as_of_date=day)
        elif allowed is None:
            scope = select_candidate_scope(binding.role_paths()["canonical"], [], as_of_date=day,
                                           retry_days=retry_days, retry_max_quarters=None)
        else:
            scope = select_exact_scope(binding.role_paths()["canonical"], allowed, as_of_date=day, retry_days=retry_days)
        if allowed is not None:
            assert_scope_subset(scope["quarter_keys"], allowed)
        result["scope"] = scope
        result["still_open_after_attempt"] = scope["retry_selected"]
        if not scope["quarter_keys"]:
            result["status"] = "SKIPPED"
            if allowed is not None:
                result["skip_reason"] = "NO_PREPARED_PLAN_KEYS" if plan is not None else "NO_ELIGIBLE_ALLOWLIST_ITEMS"
            return result
        run_dir.mkdir(parents=True, exist_ok=False)
        lane.mkdir(parents=True, exist_ok=False)
        def persist() -> None:
            (run_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        result.update(run_id=run_id, report_path=str(run_dir / "result.json"), status="RUNNING")
        persist()
        try:
            old_paths = binding.role_paths()
            original = {role: sqlite_verification(path) for role, path in old_paths.items()}
            size = sum(path.stat().st_size for path in old_paths.values())
            if shutil.disk_usage(root).free < size * 3:
                raise RuntimeError("PUBLICATION_DRAIN_INSUFFICIENT_DISK")
            candidates = {role: lane / path.name for role, path in old_paths.items()}
            for role, path in old_paths.items():
                if any(Path(str(path)+suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
                    raise RuntimeError("PUBLICATION_DRAIN_IMMUTABLE_SOURCE_SIDECAR")
                shutil.copyfile(path, candidates[role])
            result["source_verification"] = original
            if plan is not None:
                result["publication"] = run_plan_candidate(candidates["canonical"], plan, as_of_date=day)
            else:
                result["publication"] = run_candidate_publication(
                    candidates["canonical"], [], as_of_date=day, retry_days=retry_days,
                    retry_max_quarters=None, client=client, network_budget_seconds=network_budget_seconds,
                    **({"exact_quarter_allowlist": allowed} if allowed is not None else {}),
                )
            publication = result["publication"]
            result["attempted_current_backlog"] = publication["total_processed"]
            if allowed is None:
                remaining = select_candidate_scope(candidates["canonical"], [], as_of_date=day,
                                                   retry_days=retry_days, retry_max_quarters=None)
                result["still_open_after_attempt"] = remaining["retry_selected"]
                result["remaining_status_counts"] = remaining["recent_status_counts"]
            else:
                assert_scope_subset(publication["quarter_keys"], scope["quarter_keys"])
                assert_scope_subset(publication["enriched_natural_keys"], scope["quarter_keys"])
                assert_scope_subset(publication["applied_natural_keys"], publication["enriched_natural_keys"])
                if publication["quarter_keys"] != scope["quarter_keys"]:
                    raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_CANDIDATE_SCOPE_DRIFT")
                final_scope = select_exact_scope(candidates["canonical"], scope["quarter_keys"], as_of_date=day, retry_days=retry_days)
                open_counts = Counter(row["current_status"] for row in final_scope["classifications"]
                                      if row["current_status"] != "VERIFIED")
                result["still_open_after_attempt"] = sum(open_counts.values())
                result["remaining_status_counts"] = dict(open_counts)
                result["scope_evidence"] = {
                    **allowlist_evidence(allowed), "selected_count": scope["selected_count"],
                    "selected_natural_keys": scope["quarter_keys"], "skipped_counts": scope["skipped_counts"],
                    "enriched_natural_keys": publication["enriched_natural_keys"],
                    "applied_natural_keys": publication["applied_natural_keys"],
                    "applied_count": publication["applied_count"],
                    "skipped_error_natural_keys": publication["skipped_error_natural_keys"],
                }
                if plan is not None:
                    result["scope_evidence"].update(plan_scope_evidence(plan))
            if publication["unprocessed_selected"]:
                raise RuntimeError("PUBLICATION_DRAIN_INCOMPLETE_SELECTED_SCOPE")
            if publication["network"].get("budget_exhausted"):
                raise RuntimeError("PUBLICATION_DRAIN_NETWORK_BUDGET_EXHAUSTED")
            for role in ("provider", "analysis"):
                if sha256_file(candidates[role]) != original[role]["sha256"]:
                    raise RuntimeError("PUBLICATION_DRAIN_NONPUBLICATION_ROLE_CHANGED")
            for role, path in old_paths.items():
                if sha256_file(path) != original[role]["sha256"]:
                    raise RuntimeError("PUBLICATION_DRAIN_IMMUTABLE_SOURCE_CHANGED")
            paths = BatchAddTickerPaths(old_paths["provider"], old_paths["canonical"], old_paths["analysis"],
                                        root / "data/osakedata.db", root / "data/analysis.db")
            backups = _verified_backups(paths, root / "backups/fundamentals_admin_production" / run_id,
                                        immutable_generation=True)
            result["backups"] = backups
            roles = _candidate_manifest(candidates, backups)
            generation_id = run_id
            journal = prepare_journal(
                path=journal_path, operation_type=result["operation"], run_id=run_id,
                preview_run_id=run_id, test_run_id="PUBLICATION_MAINTENANCE",
                refresh_set_fingerprint=sha256_file(candidates["canonical"]),
                old_source_watermark=None, new_source_watermark="UNCHANGED",
                source_schema_fingerprint="PUBLICATION_ONLY", roles=roles,
                publication_mode="GENERATION_POINTER",
                old_generation=binding.evidence() | {"manifest": dict(binding.manifest)},
                new_generation_id=generation_id, active_generation_manifest_path=active_manifest_path(root),
                **({"scope_evidence": result["scope_evidence"]} if allowed is not None else {}),
            )
            persist()
            if inject_crash_at == "AFTER_PREPARED":
                raise SimulatedTransactionCrash("DRAIN_AFTER_PREPARED")
            prepared = prepare_generation_from_candidates(candidates, generation_id=generation_id,
                                                         project_root=root, source=result["operation"])
            journal = update_journal(journal_path, journal, current_publication_step="NEW_GENERATION_READY",
                                     generation_activation_state="READY", new_generation_manifest=prepared["manifest"],
                                     new_generation_dir=prepared["generation_dir"])
            if inject_crash_at == "AFTER_NEW_GENERATION_READY":
                raise SimulatedTransactionCrash("DRAIN_AFTER_NEW_GENERATION_READY")
            journal = activate_prepared_generation(journal, new_manifest=prepared["manifest"], journal_path=journal_path)
            if inject_crash_at == "AFTER_GENERATION_ACTIVATION":
                raise SimulatedTransactionCrash("DRAIN_AFTER_GENERATION_ACTIVATION")
            active = resolve_active_generation(root, require_generation=True)
            postflight = {role: sqlite_verification(path) for role, path in active.role_paths().items()}
            for role, record in postflight.items():
                if record["sha256"] != roles[role]["candidate_fingerprint"]:
                    raise RuntimeError("PUBLICATION_DRAIN_POSTFLIGHT_HASH_MISMATCH")
            journal = update_journal(journal_path, journal, state="COMPLETED", postflight_state="PASSED",
                                     current_publication_step="COMPLETED", rollback_recovery_state="NOT_REQUIRED")
            result.update(status=publication["status"], activated_generation=active.generation_id,
                          postflight=postflight, journal_state=journal["state"])
        except Exception as exc:
            result.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
            if journal is not None:
                try:
                    restored = restore_old_generation(journal, journal_path=journal_path)
                    result["rollback"] = {"status": restored["status"]}
                except Exception as recovery_error:
                    result["rollback"] = {"status": "RECOVERY_FAILED", "error": str(recovery_error)}
            raise
        finally:
            result["runtime_seconds"] = round(time.perf_counter() - started, 3)
            persist()
            if journal is None or result["status"] in {"SUCCESS", "PARTIAL"}:
                shutil.rmtree(lane, ignore_errors=True)
    return result
