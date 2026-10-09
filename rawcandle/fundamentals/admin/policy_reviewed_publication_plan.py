"""Explicit reviewed event-policy handoff; no default resolver or network changes."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict
from datetime import date
import json
import sqlite3
import re
from pathlib import Path
import time
from uuid import uuid4

from rawcandle.fundamentals.admin import reviewed_publication_plan as legacy
from rawcandle.fundamentals.admin import approved_publication_evidence as approved
from rawcandle.fundamentals.admin.publication_allowlist import (
    normalize_allowlist,
    read_allowlist_csv,
    allowlist_evidence,
)
from rawcandle.fundamentals.admin.publication_journal import sqlite_verification
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.publication_event_policy import (
    PUBLICATION_EVENT_POLICY_V1 as V1,
    reviewed_acceptance_gate,
)
from rawcandle.fundamentals.result_publication import (
    SecFiling,
    scoped_quarters,
    resolve_sec_filings_detailed,
    resolve_sec_filings_with_event_policy,
    apply_resolution,
    normalize_utc_timestamp,
)


POLICY_SCHEMA_VERSION = 2
POLICY_EVIDENCE_VERSION = "reviewed_event_observations_v1"
OPEN_STATUSES = {"MISSING", "UNRESOLVED", "NOT_FOUND", "AMBIGUOUS"}


def _key(row):
    return legacy._key(row)


def policy_outcome(decision):
    outcome = decision["final_result"]
    return (
        "POLICY_V1_" + outcome
        if outcome in {"UNIQUE", "AMBIGUOUS", "REVIEW"}
        else "POLICY_V1_ERROR"
    )


def decision_fingerprint(case):
    return legacy.fingerprint(
        {
            "policy_version": V1,
            "evidence_version": POLICY_EVIDENCE_VERSION,
            **{
                name: case[name]
                for name in (
                    "frozen_input_reference",
                    "original_candidate_evidence",
                    "observations",
                    "relations",
                    "acceptance_observations",
                    "policy_decision",
                )
            },
        }
    )


def _evidence_rows(connection, key):
    return legacy._rows(
        connection,
        "SELECT * FROM v4_result_publication_evidence WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=? ORDER BY evidence_id",
        key,
    )


def policy_scope(canonical, keys, *, as_of_date, retry_days):
    """Only explicitly reviewed keys, including reviewed ambiguity/aged history.

    This is not a retry selector. The ordinary 60-day/exact/default selectors are
    untouched. VERIFIED or unknown identity cannot become a policy apply key.
    """
    keys = normalize_allowlist(keys)
    date.fromisoformat(as_of_date)
    if type(retry_days) is not int or retry_days < 0:
        raise ValueError("PUBLICATION_RETRY_CONFIGURATION_INVALID")
    selected, classifications = [], []
    with closing(
        sqlite3.connect(canonical.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        for key in keys:
            state = legacy.state_for_key(db, key)
            prior = state["authority"][0]["status"] if state["authority"] else "MISSING"
            ciks = {
                r["cik_normalized"] for r in state["ciks"] if r["status"] == "ACTIVE"
            }
            eligible = (
                len(state["quarter"]) == 1
                and len(state["company"]) == 1
                and len(ciks) == 1
                and prior in OPEN_STATUSES
            )
            if eligible:
                selected.append(key)
            classifications.append(
                {
                    "natural_key": list(key),
                    "classification": "SELECTED_OPEN" if eligible else "NO_LONGER_OPEN",
                    "current_status": prior,
                    "reason": None,
                }
            )
    return {
        **allowlist_evidence(keys),
        "scope_mode": legacy.SCOPE_MODE,
        "policy_mode": V1,
        "quarter_keys": selected,
        "selected_natural_keys": selected,
        "selected_count": len(selected),
        "retry_selected": len(selected),
        "retry_days": retry_days,
        "retry_max_quarters": None,
        "classifications": classifications,
        "skipped_counts": dict(
            Counter(
                r["classification"]
                for r in classifications
                if r["classification"] != "SELECTED_OPEN"
            )
        ),
    }


def reproduce(case, record):
    filings = [legacy._decode_filing(f) for f in record["filings"]]
    key = _key(case)
    quarter = next(q for q in record["quarters"] if _key(q) == key)
    matches, unresolved, _ = resolve_sec_filings_detailed(record["quarters"], filings)
    original = case["original_candidate_evidence"]
    by_id = {e["evidence_id"]: e for e in original}
    candidates = matches.get(key, [])
    if (
        len(by_id) != len(original)
        or set(by_id) != {e["evidence_id"] for e in candidates}
        or any(
            any(original_row.get(k) != v for k, v in row.items())
            for row in candidates
            for original_row in [by_id[row["evidence_id"]]]
        )
    ):
        raise ValueError("PUBLICATION_POLICY_ORIGINAL_CANDIDATE_DRIFT")
    reviews = case["acceptance_observations"]
    if set(reviews) != set(by_id) or set(case["observations"]) != set(by_id):
        raise ValueError("PUBLICATION_POLICY_EVIDENCE_SCOPE_INVALID")
    for evidence_id, evidence in by_id.items():
        entry = reviews[evidence_id]
        if entry["stored_utc"] != evidence["source_timestamp_utc"]:
            raise ValueError("PUBLICATION_POLICY_ACCEPTANCE_BINDING_INVALID")
        discrepancy = entry["fresh_submissions_utc"] != entry["stored_utc"]
        review = entry["index_review"]
        if discrepancy:
            if (
                not review
                or entry["timezone_interpretation"] != "America/New_York"
                or review["submissions_utc"] != entry["fresh_submissions_utc"]
            ):
                raise ValueError("PUBLICATION_POLICY_ACCEPTANCE_REVIEW_REQUIRED")
            status = reviewed_acceptance_gate(evidence, review)
        else:
            if review is not None:
                raise ValueError("PUBLICATION_POLICY_ACCEPTANCE_BINDING_INVALID")
            status = "NO_REVIEWED_DISCREPANCY"
        if entry["corroboration_status"] != status:
            raise ValueError("PUBLICATION_POLICY_ACCEPTANCE_BINDING_INVALID")
    result = resolve_sec_filings_with_event_policy(
        record["quarters"],
        filings,
        policy_version=V1,
        observations=case["observations"],
        relations=case["relations"],
    )["event_policy_evaluations"][key]
    return result


def validate_policy_plan(plan):
    try:
        if (
            plan["schema_version"] not in {POLICY_SCHEMA_VERSION, approved.PLAN_VERSION}
            or type(plan["schema_version"]) is not int
            or plan["policy_mode"] != V1
            or plan["policy_version"] != V1
            or plan["policy_evidence_version"] != POLICY_EVIDENCE_VERSION
        ):
            raise ValueError("PUBLICATION_POLICY_PLAN_VERSION_INVALID")
        if (
            legacy.fingerprint(
                {k: v for k, v in plan.items() if k != "plan_fingerprint"}
            )
            != plan["plan_fingerprint"]
        ):
            raise ValueError("PUBLICATION_PLAN_TAMPERED")
        normalize_utc_timestamp(plan["created_at_utc"])
        date.fromisoformat(plan["as_of_date"])
        if type(plan["retry_days"]) is not int or plan["retry_days"] < 0:
            raise ValueError("PUBLICATION_RETRY_CONFIGURATION_INVALID")
        if not re.fullmatch(r"[a-f0-9]{64}", plan["policy_evidence_fingerprint"]):
            raise ValueError("PUBLICATION_POLICY_EVIDENCE_FINGERPRINT_INVALID")
        if not isinstance(plan["plan_id"], str) or not plan["plan_id"]:
            raise ValueError("PUBLICATION_PLAN_ID_INVALID")
        if plan["schema_version"] == approved.PLAN_VERSION:
            approved.validate_plan_extension(plan)
        elif any(k in plan for k in ("approved_evidence_handoff", "candidate_evidence_provenance")):
            raise ValueError("PUBLICATION_POLICY_APPROVED_MODE_VERSION_REQUIRED")
        keys, source = normalize_allowlist(plan["prepared_keys"]), normalize_allowlist(
            plan["source_allowlist_keys"]
        )
        cases, inputs = plan["policy_cases"], plan["frozen_inputs"]
        prepared = [c for c in cases if c["policy_result"] == "POLICY_V1_UNIQUE"]
        if (
            plan["prepared_keys"] != [list(k) for k in keys]
            or plan["source_allowlist_keys"] != [list(k) for k in source]
            or [_key(c) for c in cases] != sorted({_key(c) for c in cases})
            or not {_key(c) for c in cases} <= set(source)
            or [_key(c) for c in prepared] != list(keys)
            or plan["per_case"] != prepared
            or plan["prepared_key_count"] != len(keys)
            or type(plan["prepared_key_count"]) is not int
            or plan["source_allowlist_count"] != len(source)
            or type(plan["source_allowlist_count"]) is not int
            or plan["prepared_keys_fingerprint"]
            != legacy.fingerprint(plan["prepared_keys"])
            or plan["source_allowlist_fingerprint"]
            != allowlist_evidence(source)["allowlist_fingerprint"]
            or plan["canonical_authority_fingerprint"]
            != legacy.fingerprint([c["state"] for c in cases])
            or plan["policy_decisions_fingerprint"]
            != legacy.fingerprint([c["policy_decision_fingerprint"] for c in cases])
            or set(inputs) != {c["frozen_input_reference"] for c in cases}
        ):
            raise ValueError("PUBLICATION_POLICY_PLAN_SCOPE_INVALID")
        if sorted(tuple(c["natural_key"]) for c in plan["classifications"]) != list(
            source
        ):
            raise ValueError("PUBLICATION_POLICY_PLAN_CLASSIFICATION_SCOPE_INVALID")
        classification_by_key = {
            tuple(c["natural_key"]): c for c in plan["classifications"]
        }
        for input_id, record in inputs.items():
            if (
                input_id != legacy.fingerprint(record)
                or legacy._request(record["quarters"]) != record["request"]
            ):
                raise ValueError("PUBLICATION_PLAN_INPUT_FINGERPRINT_INVALID")
            if len({q["company_id"] for q in record["quarters"]}) != 1 or (
                plan["schema_version"] != approved.PLAN_VERSION and not {
                    _key(q) for q in record["quarters"]} <= set(source)):
                raise ValueError("PUBLICATION_PLAN_CONTEXT_SCOPE_INVALID")
            if len({_key(q) for q in record["quarters"]}) != len(
                record["quarters"]
            ) or any(
                q["cik_normalized"] != record["request"]["cik"]
                for q in record["quarters"]
            ):
                raise ValueError("PUBLICATION_PLAN_CONTEXT_SCOPE_INVALID")
            for payload in record["filings"]:
                filing = legacy._decode_filing(payload)
                url = f"https://www.sec.gov/Archives/edgar/data/{int(record['request']['cik'])}/{filing.accession_number.replace('-', '')}/{filing.primary_document}"
                if filing.source_reference != url:
                    raise ValueError("PUBLICATION_PLAN_ACCESSION_CONTEXT_INVALID")
        for case in cases:
            key = _key(case)
            state = case["state"]
            record = inputs[case["frozen_input_reference"]]
            q = next(q for q in record["quarters"] if _key(q) == key)
            expected_q = state["quarter"][0]
            prior = state["authority"][0]["status"] if state["authority"] else "MISSING"
            ciks = {
                r["cik_normalized"] for r in state["ciks"] if r["status"] == "ACTIVE"
            }
            if (
                prior != case["prior_status"]
                or prior not in OPEN_STATUSES
                or len(state["quarter"]) != 1
                or len(state["company"]) != 1
                or (
                    state["authority"]
                    and state["authority"][0]["result_publication_source"]
                    not in {None, "SEC_8K_ITEM_2_02"}
                )
                or ciks != {case["parent_cik"]}
                or record["request"]["cik"] != case["parent_cik"]
                or any(
                    q[name] != expected_q[name]
                    for name in (
                        "quarter_id",
                        "company_id",
                        "fiscal_year",
                        "fiscal_quarter",
                        "period_end",
                        "first_public_result_date",
                        "source_availability_date",
                    )
                )
            ):
                raise ValueError("PUBLICATION_POLICY_PLAN_STATE_INVALID")
            decision = reproduce(case, record)
            if (
                decision != case["policy_decision"]
                or decision_fingerprint(case) != case["policy_decision_fingerprint"]
                or case["policy_result"] != policy_outcome(decision)
            ):
                raise ValueError("PUBLICATION_POLICY_DECISION_REPRODUCTION_FAILED")
            classification = classification_by_key[key]
            if (
                classification["fresh_outcome"] != case["policy_result"]
                or classification["review_reason"] != decision["review_reason"]
            ):
                raise ValueError("PUBLICATION_POLICY_PLAN_CLASSIFICATION_DRIFT")
            selected = next(
                (
                    row
                    for row in decision["retained_candidates"]
                    if row["evidence_id"] == decision["selected_evidence_id"]
                ),
                None,
            )
            if (
                case["evidence"] != selected
                or case["parent_acceptance_timestamp"] != decision["selected_timestamp"]
                or case["parent_accession"] != decision["selected_accession"]
            ):
                raise ValueError("PUBLICATION_POLICY_SELECTED_EVENT_DRIFT")
        # Reproduce narrowed apply context as well as full reviewed company context.
        for group in legacy._apply_groups(plan):
            record = inputs[group[0]["frozen_input_reference"]]
            # V3 executes exact approved evidence against its full approved scope.
            # Context-only quarters never become apply keys. V2 remains narrowed.
            narrowed = (record if plan["schema_version"] == approved.PLAN_VERSION else
                        {**record, "quarters": legacy._case_quarters(group, record)})
            if any(reproduce(c, narrowed) != c["policy_decision"] for c in group):
                raise ValueError("PUBLICATION_PLAN_APPLY_CONTEXT_NOT_REPRODUCIBLE")
    except (KeyError, TypeError, IndexError, AttributeError, StopIteration) as exc:
        raise ValueError("PUBLICATION_POLICY_PLAN_SHAPE_INVALID") from exc
    return plan


def prepare_policy_plan(
    *,
    project_root,
    allowlist_path,
    output_plan,
    policy_evidence_path,
    as_of_date,
    retry_days,
    approved_handoff_path=None,
    expected_approval_fingerprint=None,
):
    root = project_root.resolve()
    destination = output_plan.resolve()
    if any(
        base == destination or base in destination.parents
        for base in (root / "data", root / "backups")
    ):
        raise ValueError("PUBLICATION_PLAN_OUTPUT_PATH_UNSAFE")
    if output_plan.exists() or output_plan.is_symlink():
        raise FileExistsError("PUBLICATION_PLAN_IMMUTABLE_OUTPUT_EXISTS")
    handoff = None
    if approved_handoff_path is not None:
        if policy_evidence_path is not None or not expected_approval_fingerprint:
            raise ValueError("PUBLICATION_POLICY_APPROVED_EXPLICIT_INPUT_REQUIRED")
        handoff = legacy.read_unique_json(approved_handoff_path)
        approved_sources, approved_snapshots, approved_companies = approved.validate_handoff(
            handoff, expected_approval_fingerprint)
        approved.check_live_inputs(handoff)
        supplied = handoff["proposal"]["proposed_policy_evidence"]
    else:
        if expected_approval_fingerprint is not None:
            raise ValueError("PUBLICATION_POLICY_APPROVED_EXPLICIT_INPUT_REQUIRED")
        if policy_evidence_path is None:
            raise ValueError("PUBLICATION_POLICY_REVIEWED_EVIDENCE_REQUIRED")
        supplied = legacy.read_unique_json(policy_evidence_path)
    if supplied["policy_version"] != V1:
        raise ValueError("PUBLICATION_POLICY_PLAN_VERSION_INVALID")
    allowed = read_allowlist_csv(allowlist_path)
    source_cases = {_key(c["quarter"]): c for c in supplied["cases"]}
    if handoff is not None:
        if not set(allowed) <= set(approved_snapshots):
            raise ValueError("PUBLICATION_APPROVED_UNAPPROVED_KEY")
        source_cases = {k: approved_sources[k] for k in allowed}
    if (handoff is None and len(source_cases) != len(supplied["cases"])) or set(source_cases) != set(allowed):
        raise ValueError("PUBLICATION_POLICY_REVIEWED_EVIDENCE_SCOPE_INVALID")
    binding = resolve_active_generation(root, require_generation=True)
    legacy._require_clean_journal(root)
    canonical = binding.role_paths()["canonical"]
    scope = policy_scope(
        canonical, allowed, as_of_date=as_of_date, retry_days=retry_days
    )
    cases, inputs, classifications = [], {}, []
    with closing(
        sqlite3.connect(canonical.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        quarters = scoped_quarters(db, 1, (), quarter_keys=scope["quarter_keys"])
        groups = defaultdict(list)
        for q in quarters:
            groups[q["company_id"]].append(q)
        for item in scope["classifications"]:
            if item["classification"] != "SELECTED_OPEN":
                classifications.append(
                    {
                        **item,
                        "fresh_outcome": "POLICY_V1_ERROR",
                        "error": "NO_LONGER_OPEN_OR_IDENTITY_INVALID",
                    }
                )
        for company_quarters in groups.values():
            filings = {}
            if handoff is None:
                for q in company_quarters:
                    for event in source_cases[_key(q)]["events"]:
                        e = event["evidence"]
                        filing = asdict(
                            SecFiling(
                                e["accession_number"],
                                e["filing_form"],
                                "2.02",
                                e["source_timestamp_utc"],
                                e["document_id"],
                                e["source_reference"],
                                event["primary_excerpt"],
                            )
                        )
                        if (
                            e["accession_number"] in filings
                            and filings[e["accession_number"]] != filing
                        ):
                            raise ValueError("PUBLICATION_POLICY_FILING_CONTEXT_CONFLICT")
                        filings[e["accession_number"]] = filing
            if handoff is not None:
                filings = {str(i): f for i, f in enumerate(
                    approved.company_filings(approved_companies[company_quarters[0]["company_id"]]))}
            record = json.loads(
                json.dumps(
                    {
                        "request": legacy._request(approved.resolver_quarters(
                            approved_snapshots[_key(company_quarters[0])]) if handoff is not None else company_quarters),
                        "quarters": (approved.resolver_quarters(approved_snapshots[_key(company_quarters[0])])
                                     if handoff is not None else company_quarters),
                        "filings": list(filings.values()),
                    }
                )
            )
            input_id = legacy.fingerprint(record)
            inputs[input_id] = record
            for q in company_quarters:
                key, source = _key(q), source_cases[_key(q)]
                originals = sorted(
                    [e["evidence"] for e in source["events"]],
                    key=lambda e: e["evidence_id"],
                )
                if handoff is not None:
                    approved.check_current_case(db, key, approved_snapshots[key], originals,
                                                identity_tables=approved.identity_tables_for_case(
                                                    handoff, key, approved_snapshots[key]))
                elif originals != _evidence_rows(db, key):
                    raise ValueError("PUBLICATION_POLICY_STORED_EVIDENCE_DRIFT")
                if any(
                    source["quarter"][name] != q[name]
                    for name in (
                        "quarter_id",
                        "company_id",
                        "fiscal_year",
                        "fiscal_quarter",
                        "period_end",
                    )
                ):
                    raise ValueError("PUBLICATION_POLICY_QUARTER_DRIFT")
                state = legacy.state_for_key(db, key)
                reviews = {}
                for event in source["events"]:
                    e, index = event["evidence"], event.get("acceptance_index_review")
                    reviews[e["evidence_id"]] = {
                        "stored_utc": e["source_timestamp_utc"],
                        "fresh_submissions_utc": (
                            index["submissions_utc"]
                            if index
                            else e["source_timestamp_utc"]
                        ),
                        "index_review": index,
                        "timezone_interpretation": (
                            "America/New_York" if index else None
                        ),
                        "corroboration_status": reviewed_acceptance_gate(e, index),
                    }
                case = {
                    "company_id": key[0],
                    "fiscal_year": key[1],
                    "fiscal_quarter": key[2],
                    "state": state,
                    "prior_status": (
                        state["authority"][0]["status"]
                        if state["authority"]
                        else "MISSING"
                    ),
                    "parent_cik": q["cik_normalized"],
                    "frozen_input_reference": input_id,
                    "original_candidate_evidence": originals,
                    "observations": {
                        e["evidence"]["evidence_id"]: e["observation"]
                        for e in source["events"]
                    },
                    "relations": source["relations"],
                    "acceptance_observations": reviews,
                }
                decision = reproduce(case, record)
                selected = next(
                    (
                        r
                        for r in decision["retained_candidates"]
                        if r["evidence_id"] == decision["selected_evidence_id"]
                    ),
                    None,
                )
                case.update(
                    policy_decision=decision,
                    policy_result=policy_outcome(decision),
                    evidence=selected,
                    parent_acceptance_timestamp=decision["selected_timestamp"],
                    parent_accession=decision["selected_accession"],
                )
                case["policy_decision_fingerprint"] = decision_fingerprint(case)
                cases.append(case)
                classifications.append(
                    {
                        "natural_key": list(key),
                        "fresh_outcome": case["policy_result"],
                        "review_reason": decision["review_reason"],
                    }
                )
    cases.sort(key=_key)
    prepared = [c for c in cases if c["policy_result"] == "POLICY_V1_UNIQUE"]
    keys = [list(_key(c)) for c in prepared]
    plan = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_mode": V1,
        "policy_version": V1,
        "policy_evidence_version": POLICY_EVIDENCE_VERSION,
        "policy_evidence_fingerprint": legacy.fingerprint(supplied),
        "plan_id": "publication_policy_plan_" + uuid4().hex,
        "created_at_utc": legacy.utc_now(),
        "as_of_date": as_of_date,
        "retry_days": retry_days,
        "source_allowlist_path": str(allowlist_path.resolve()),
        "source_allowlist_keys": [list(k) for k in allowed],
        "source_allowlist_count": len(allowed),
        "source_allowlist_fingerprint": allowlist_evidence(allowed)[
            "allowlist_fingerprint"
        ],
        "active_generation_id": binding.generation_id,
        "active_generation_manifest_fingerprint": legacy.fingerprint(binding.manifest),
        "canonical_authority_fingerprint": legacy.fingerprint(
            [c["state"] for c in cases]
        ),
        "policy_decisions_fingerprint": legacy.fingerprint(
            [c["policy_decision_fingerprint"] for c in cases]
        ),
        "prepared_key_count": len(keys),
        "prepared_keys": keys,
        "prepared_keys_fingerprint": legacy.fingerprint(keys),
        "per_case": prepared,
        "policy_cases": cases,
        "frozen_inputs": inputs,
        "classifications": sorted(classifications, key=lambda r: r["natural_key"]),
        "prepare_network": {"network_requests": 0},
    }
    if handoff is not None:
        plan.update(schema_version=approved.PLAN_VERSION,
                    candidate_evidence_provenance=approved.MODE,
                    execution_context='APPROVED_FULL_COMPANY_RESOLVER_CONTEXT_V1',
                    approved_evidence_handoff=handoff,
                    approved_handoff_fingerprint=handoff["handoff_fingerprint"],
                    approval_fingerprint=handoff["approval"]["artifact_fingerprint"],
                    proposal_fingerprint=handoff["proposal"]["artifact_fingerprint"],
                    publication_authorized=False, production_apply_authorized=False, executed=False)
    plan = json.loads(json.dumps(plan))
    plan["plan_fingerprint"] = legacy.fingerprint(plan)
    validate_policy_plan(plan)
    legacy.revalidate_plan_state(plan, binding, as_of_date=as_of_date)
    if legacy.fingerprint(
        resolve_active_generation(root, require_generation=True).manifest
    ) != legacy.fingerprint(binding.manifest):
        raise RuntimeError("PUBLICATION_PLAN_GENERATION_DRIFT")
    legacy._require_clean_journal(root)
    legacy.publish_plan(plan, output_plan)
    return {
        "status": "PREPARED" if keys else "SKIPPED",
        "plan_path": str(output_plan.resolve()),
        **legacy.plan_scope_evidence(plan),
        "classification_counts": dict(
            Counter(c["fresh_outcome"] for c in classifications)
        ),
    }


def run_policy_candidate(candidate_db, plan, *, as_of_date):
    """Reproduce first; existing apply_resolution remains the authority writer."""
    started = time.perf_counter()
    if (candidate_db.resolve().parent / "generation_manifest.json").exists():
        raise ValueError("PUBLICATION_FINALIZED_GENERATION_WRITE_FORBIDDEN")
    validate_policy_plan(plan)
    keys = normalize_allowlist(plan["prepared_keys"])
    scope = policy_scope(
        candidate_db, keys, as_of_date=as_of_date, retry_days=plan["retry_days"]
    )
    if set(scope["quarter_keys"]) != set(keys):
        raise RuntimeError("PUBLICATION_PLAN_OPEN_SCOPE_DRIFT")
    results = []
    with sqlite3.connect(candidate_db) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        # All cohort state/evidence is bound before the first apply call.
        frozen_mode = plan["schema_version"] == approved.PLAN_VERSION
        if frozen_mode:
            approved.revalidate_current(plan, db)
        for case in ([] if frozen_mode else plan["policy_cases"]):
            if (
                legacy.state_for_key(db, _key(case)) != case["state"]
                or _evidence_rows(db, _key(case)) != case["original_candidate_evidence"]
            ):
                raise RuntimeError("PUBLICATION_POLICY_CANDIDATE_STATE_DRIFT")
        for case in plan["per_case"]:
            quarter = case["state"]["quarter"][0]
            status = apply_resolution(
                db,
                quarter,
                [case["evidence"]],
                reason_override="REVIEWED_PUBLICATION_EVENT_POLICY_V1",
            )
            if status != "VERIFIED":
                raise RuntimeError("PUBLICATION_POLICY_APPLY_NOT_VERIFIED")
            # Legacy rows stay unchanged; frozen candidates may become durable only here.
            if (not approved.compatible_evidence(_evidence_rows(db, _key(case)), case["original_candidate_evidence"])
                    if frozen_mode else _evidence_rows(db, _key(case)) != case["original_candidate_evidence"]):
                raise RuntimeError("PUBLICATION_POLICY_RETAINED_EVIDENCE_DRIFT")
            results.append(
                {
                    "company_id": case["company_id"],
                    "fiscal_year": case["fiscal_year"],
                    "fiscal_quarter": case["fiscal_quarter"],
                    "status": status,
                }
            )
    return {
        **scope,
        "status": "SUCCESS" if keys else "SKIPPED",
        "total_processed": len(keys),
        "status_counts": {"VERIFIED": len(keys)},
        "new_verified": len(keys),
        "errors": [],
        "results": results,
        "network": {"network_requests": 0},
        "unprocessed_selected": 0,
        "enriched_natural_keys": list(keys),
        "applied_natural_keys": list(keys),
        "applied_count": len(keys),
        "skipped_error_natural_keys": [],
        "verification": sqlite_verification(candidate_db),
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "policy_decisions": {
            str(_key(c)): c["policy_decision"] for c in plan["per_case"]
        },
    }
