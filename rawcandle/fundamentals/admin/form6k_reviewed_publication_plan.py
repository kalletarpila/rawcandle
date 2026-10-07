"""Explicit frozen Form 6-K plans; no acquisition and no production enablement."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import date, timedelta
import sqlite3
import time
from uuid import uuid4

from rawcandle.fundamentals.admin import reviewed_publication_plan as plans
from rawcandle.fundamentals.admin.policy_reviewed_publication_plan import policy_scope, _evidence_rows
from rawcandle.fundamentals.admin.publication_allowlist import read_allowlist_csv, normalize_allowlist, allowlist_evidence
from rawcandle.fundamentals.admin.publication_journal import sqlite_verification
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.form6k_authority import (
    FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 as V1, SEC_FORM_6K_RESULT,
    natural_key, evaluate_form6k, reviewed_evidence_payload,
)
from rawcandle.fundamentals.result_publication import apply_resolution
from rawcandle.fundamentals.schema.result_publication import upgrade_form6k_candidate_schema

SCHEMA_VERSION = 3
FIXTURE_VERSION = "FORM6K_REVIEWED_COHORT_V1"
BINDINGS = ("policy_mode", "authority_version", "source_type", "source_rank", "confidence",
            "reviewed_cohort_fingerprint", "frozen_fixture_version", "aggregate_decision_fingerprint")


def reproduce(frozen):
    return evaluate_form6k(frozen["quarter"], frozen["candidates"],
                          relations=frozen["relations"], authority_version=V1,
                          existing_authority=frozen["current_authority"])


def _witness_matches(state, frozen):
    q = frozen["quarter"]
    return (len(state["quarter"]) == len(state["company"]) == 1
            and state["authority"] == [frozen["current_authority"]]
            and state["quarter"][0] == {k: v for k, v in q.items() if k not in {"security_id", "sec_cik"}}
            and {r["cik_normalized"] for r in state["ciks"] if r["status"] == "ACTIVE"} == {q["sec_cik"]}
            and any(r["security_id"] == q["security_id"] and r["company_id"] == q["company_id"]
                    for r in state["securities"]))


def _proof(frozen):
    return {"quarter": frozen["quarter"], "candidates": frozen["candidates"],
            "relations": frozen["relations"], "authority_version": V1}


def _scope(path, plan, day):
    result = policy_scope(path, plan["prepared_keys"], as_of_date=day, retry_days=plan["retry_days"])
    result["policy_mode"] = V1
    if set(result["quarter_keys"]) != set(normalize_allowlist(plan["prepared_keys"])):
        raise RuntimeError("PUBLICATION_FORM6K_OPEN_SCOPE_DRIFT")
    return result


def _check_state(db, plan):
    for case in plan["form6k_cases"]:
        key = natural_key(case)
        if (plans.state_for_key(db, key) != case["state"]
                or _evidence_rows(db, key) != case["original_candidate_evidence"]):
            raise RuntimeError("PUBLICATION_FORM6K_AUTHORITY_IDENTITY_EVIDENCE_DRIFT")


def validate_form6k_plan(plan):
    try:
        if (type(plan["schema_version"]) is not int or plan["schema_version"] != SCHEMA_VERSION
                or plan["policy_mode"] != V1 or plan["authority_version"] != V1
                or plan["source_type"] != SEC_FORM_6K_RESULT or type(plan["source_rank"]) is not int
                or plan["source_rank"] != 2 or plan["confidence"] != "MEDIUM"
                or plan["frozen_fixture_version"] != FIXTURE_VERSION):
            raise ValueError("PUBLICATION_FORM6K_PLAN_CONTRACT_INVALID")
        if plans.fingerprint({k: v for k, v in plan.items() if k != "plan_fingerprint"}) != plan["plan_fingerprint"]:
            raise ValueError("PUBLICATION_FORM6K_PLAN_TAMPERED")
        fixture = plan["frozen_fixture"]
        if (fixture["fixture_version"] != FIXTURE_VERSION
                or plans.fingerprint({k: v for k, v in fixture.items() if k != "fixture_fingerprint"}) != fixture["fixture_fingerprint"]
                or plans.fingerprint(fixture) != plan["reviewed_cohort_fingerprint"]):
            raise ValueError("PUBLICATION_FORM6K_FIXTURE_TAMPERED")
        allowed = normalize_allowlist(plan["source_allowlist_keys"])
        cases = plan["form6k_cases"]
        if (tuple(natural_key(c) for c in cases) != allowed
                or normalize_allowlist([natural_key(c["quarter"]) for c in fixture["cases"]]) != allowed
                or plan["source_allowlist_count"] != len(allowed)
                or plan["source_allowlist_fingerprint"] != allowlist_evidence(allowed)["allowlist_fingerprint"]):
            raise ValueError("PUBLICATION_FORM6K_COHORT_SCOPE_DRIFT")
        frozen_by_key = {natural_key(c["quarter"]): c for c in fixture["cases"]}
        prepared = []
        for case in cases:
            frozen = frozen_by_key[natural_key(case)]
            decision = reproduce(frozen)
            context_date = max(case["state"]["quarter"][0].get("first_public_result_date") or "",
                               case["state"]["quarter"][0].get("source_availability_date") or "")
            cutoff = (date.fromisoformat(plan["as_of_date"]) - timedelta(days=plan["retry_days"])).isoformat()
            member = "INSIDE" if cutoff <= context_date <= plan["as_of_date"] else "OUTSIDE"
            if (case["frozen_case"] != frozen or not _witness_matches(case["state"], frozen)
                    or case["current_status"] != frozen["current_authority"]["status"]
                    or case["current_timestamp"] != frozen["current_authority"]["result_publication_timestamp_utc"]
                    or case["current_60d_scope"] != member
                    or case["decision"] != decision
                    or case["decision_fingerprint"] != decision["decision_fingerprint"]):
                raise ValueError("PUBLICATION_FORM6K_DECISION_OR_CONTEXT_DRIFT")
            if decision["final_result"] == "UNIQUE":
                if (case["evidence"] != reviewed_evidence_payload(_proof(frozen), authority_version=V1)
                        or case["parent_acceptance_timestamp"] != decision["selected_timestamp"]
                        or decision["selected_source"] != SEC_FORM_6K_RESULT
                        or decision["source_rank"] != 2 or decision["confidence"] != "MEDIUM"):
                    raise ValueError("PUBLICATION_FORM6K_SELECTED_EVIDENCE_DRIFT")
                prepared.append(case)
        keys = [list(natural_key(c)) for c in prepared]
        if (plan["per_case"] != prepared or plan["prepared_keys"] != keys
                or plan["prepared_key_count"] != len(keys)
                or plan["prepared_keys_fingerprint"] != plans.fingerprint(keys)
                or plan["canonical_authority_fingerprint"] != plans.fingerprint([c["state"] for c in cases])
                or plan["aggregate_decision_fingerprint"] != plans.fingerprint([c["decision_fingerprint"] for c in cases])):
            raise ValueError("PUBLICATION_FORM6K_PREPARED_OR_AGGREGATE_DRIFT")
        if not plan["plan_id"] or not plan["active_generation_id"] or not plan["active_generation_manifest_fingerprint"]:
            raise ValueError("PUBLICATION_FORM6K_GENERATION_BINDING_MISSING")
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("PUBLICATION_FORM6K_PLAN_INCOMPLETE") from exc
    return plan


def revalidate_form6k_state(plan, binding, *, as_of_date):
    validate_form6k_plan(plan)
    if (binding.generation_id != plan["active_generation_id"]
            or plans.fingerprint(binding.manifest) != plan["active_generation_manifest_fingerprint"]):
        raise RuntimeError("PUBLICATION_PLAN_GENERATION_DRIFT")
    path = binding.role_paths()["canonical"]
    scope = _scope(path, plan, as_of_date)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        _check_state(db, plan)
    return scope


def prepare_form6k_plan(*, project_root, allowlist_path, output_plan, policy_evidence_path, as_of_date, retry_days):
    root = project_root.resolve()
    destination = output_plan.resolve()
    if any(base == destination or base in destination.parents for base in (root / "data", root / "backups")):
        raise ValueError("PUBLICATION_PLAN_OUTPUT_PATH_UNSAFE")
    if output_plan.exists() or output_plan.is_symlink():
        raise FileExistsError("PUBLICATION_PLAN_IMMUTABLE_OUTPUT_EXISTS")
    if policy_evidence_path is None:
        raise ValueError("PUBLICATION_FORM6K_REVIEWED_EVIDENCE_REQUIRED")
    fixture = plans.read_unique_json(policy_evidence_path)
    if (fixture["fixture_version"] != FIXTURE_VERSION
            or plans.fingerprint({k: v for k, v in fixture.items() if k != "fixture_fingerprint"}) != fixture["fixture_fingerprint"]):
        raise ValueError("PUBLICATION_FORM6K_FIXTURE_TAMPERED")
    allowed = read_allowlist_csv(allowlist_path)
    frozen_by_key = {natural_key(c["quarter"]): c for c in fixture["cases"]}
    if len(frozen_by_key) != len(fixture["cases"]) or set(frozen_by_key) != set(allowed):
        raise ValueError("PUBLICATION_FORM6K_REVIEWED_EVIDENCE_SCOPE_INVALID")
    binding = resolve_active_generation(root, require_generation=True)
    plans._require_clean_journal(root)
    # Reuse only the manual reviewed-key identity gate, never the recent retry selector.
    policy_scope(binding.role_paths()["canonical"], allowed, as_of_date=as_of_date, retry_days=retry_days)
    cases = []
    with closing(sqlite3.connect(binding.role_paths()["canonical"].as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        for key in allowed:
            frozen = frozen_by_key[key]
            state = plans.state_for_key(db, key)
            if not _witness_matches(state, frozen):
                raise RuntimeError("PUBLICATION_FORM6K_REVIEWED_WITNESS_DRIFT")
            decision = reproduce(frozen)
            context_date = max(state["quarter"][0].get("first_public_result_date") or "",
                               state["quarter"][0].get("source_availability_date") or "")
            cutoff = (date.fromisoformat(as_of_date) - timedelta(days=retry_days)).isoformat()
            case = {"company_id": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2],
                    "ticker": frozen["ticker"], "state": state, "frozen_case": frozen,
                    "original_candidate_evidence": _evidence_rows(db, key),
                    "current_status": frozen["current_authority"]["status"],
                    "current_timestamp": frozen["current_authority"]["result_publication_timestamp_utc"],
                    "current_60d_scope": "INSIDE" if cutoff <= context_date <= as_of_date else "OUTSIDE",
                    "decision": decision, "decision_fingerprint": decision["decision_fingerprint"]}
            if decision["final_result"] == "UNIQUE":
                case.update(evidence=reviewed_evidence_payload(_proof(frozen), authority_version=V1),
                            parent_acceptance_timestamp=decision["selected_timestamp"])
            cases.append(case)
    prepared = [c for c in cases if c["decision"]["final_result"] == "UNIQUE"]
    keys = [list(natural_key(c)) for c in prepared]
    plan = {"schema_version": SCHEMA_VERSION, "policy_mode": V1, "authority_version": V1,
            "source_type": SEC_FORM_6K_RESULT, "source_rank": 2, "confidence": "MEDIUM",
            "frozen_fixture_version": FIXTURE_VERSION, "frozen_fixture": fixture,
            "reviewed_cohort_fingerprint": plans.fingerprint(fixture),
            "plan_id": "publication_form6k_plan_" + uuid4().hex, "created_at_utc": plans.utc_now(),
            "as_of_date": as_of_date, "retry_days": retry_days,
            "source_allowlist_path": str(allowlist_path.resolve()), "source_allowlist_keys": [list(k) for k in allowed],
            "source_allowlist_count": len(allowed), "source_allowlist_fingerprint": allowlist_evidence(allowed)["allowlist_fingerprint"],
            "active_generation_id": binding.generation_id,
            "active_generation_manifest_fingerprint": plans.fingerprint(binding.manifest),
            "canonical_authority_fingerprint": plans.fingerprint([c["state"] for c in cases]),
            "aggregate_decision_fingerprint": plans.fingerprint([c["decision_fingerprint"] for c in cases]),
            "prepared_keys": keys, "prepared_key_count": len(keys), "prepared_keys_fingerprint": plans.fingerprint(keys),
            "per_case": prepared, "form6k_cases": cases, "prepare_network": {"network_requests": 0}}
    plan["plan_fingerprint"] = plans.fingerprint(plan)
    revalidate_form6k_state(plan, binding, as_of_date=as_of_date)
    if plans.fingerprint(resolve_active_generation(root, require_generation=True).manifest) != plans.fingerprint(binding.manifest):
        raise RuntimeError("PUBLICATION_PLAN_GENERATION_DRIFT")
    plans._require_clean_journal(root)
    plans.publish_plan(plan, output_plan)
    return {"status": "PREPARED" if keys else "SKIPPED", "plan_path": str(destination),
            **plans.plan_scope_evidence(plan),
            "classification_counts": dict(Counter(c["decision"]["final_result"] for c in cases))}


def run_form6k_candidate(candidate_db, plan, *, as_of_date):
    started = time.perf_counter()
    if (candidate_db.resolve().parent / "generation_manifest.json").exists():
        raise ValueError("PUBLICATION_FINALIZED_GENERATION_WRITE_FORBIDDEN")
    validate_form6k_plan(plan)
    scope = _scope(candidate_db, plan, as_of_date)
    keys = normalize_allowlist(plan["prepared_keys"])
    with sqlite3.connect(candidate_db) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        _check_state(db, plan)
        upgrade_form6k_candidate_schema(db)
        for case in plan["per_case"]:
            frozen = case["frozen_case"]
            if reproduce(frozen) != case["decision"]:
                raise RuntimeError("PUBLICATION_FORM6K_REPLAY_DRIFT")
            status = apply_resolution(db, case["state"]["quarter"][0], [case["evidence"]],
                                      form6k_reviewed_case=_proof(frozen), reason_override="REVIEWED_FORM6K_AUTHORITY_V1")
            authority = plans.state_for_key(db, natural_key(case))["authority"][0]
            if (status != "VERIFIED" or authority["selected_evidence_id"] != case["evidence"]["evidence_id"]
                    or authority["result_publication_source"] != SEC_FORM_6K_RESULT
                    or authority["result_publication_timestamp_utc"] != case["decision"]["selected_timestamp"]
                    or authority["result_publication_confidence"] != "MEDIUM" or authority["rule_version"] != V1):
                raise RuntimeError("PUBLICATION_FORM6K_AUTHORITY_RESULT_DRIFT")
        for case in plan["form6k_cases"]:
            key = natural_key(case)
            if key not in keys and plans.state_for_key(db, key) != case["state"]:
                raise RuntimeError("PUBLICATION_FORM6K_HELD_STATE_DRIFT")
            rows = {r["evidence_id"]: r for r in _evidence_rows(db, key)}
            if any(rows.get(r["evidence_id"]) != r for r in case["original_candidate_evidence"]):
                raise RuntimeError("PUBLICATION_FORM6K_RETAINED_EVIDENCE_DRIFT")
    return {**scope, "status": "SUCCESS" if keys else "SKIPPED", "total_processed": len(keys),
            "new_verified": len(keys), "status_counts": {"VERIFIED": len(keys)}, "errors": [],
            "network": {"network_requests": 0}, "unprocessed_selected": 0,
            "enriched_natural_keys": list(keys), "applied_natural_keys": list(keys), "applied_count": len(keys),
            "skipped_error_natural_keys": [], "verification": sqlite_verification(candidate_db),
            "runtime_seconds": round(time.perf_counter() - started, 3)}
