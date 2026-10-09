"""Non-executing, exact-selection operator receipts. No runtime integration.

Callers must reproduce source proofs and Policy V1 before supplying snapshots.
Snapshots include quarter/authority/identity, selected evidence, full company
resolver context, reviewed-input hashes and replay result. This module compares
those snapshots, binds the displayed selection and writes only a docs receipt.
It never installs observations or prepares a publication plan.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.publication_event_policy import fingerprint

RULE = "HISTORICAL_PUBLICATION_OPERATOR_REVIEW_V1"
APPROVAL_DIRECTORY = Path("docs/fundamentals_v4/review_approvals")


def _digest(value: dict) -> str:
    return fingerprint({k: v for k, v in value.items() if k != "artifact_fingerprint"})


def _verify(value: dict) -> None:
    if value.get("artifact_fingerprint") != _digest(value):
        raise ValueError("ARTIFACT_FINGERPRINT_CHANGED")


def prepare_candidate(proposal: dict, *, proposal_path: str,
                      expected_proposal_fingerprint: str,
                      baseline_states: dict, current_states: dict,
                      current_global_state: dict) -> dict:
    """Compare independently reproduced snapshots; never infer human approval."""
    actual = fingerprint({k: v for k, v in proposal.items()
                          if k not in {"artifact_fingerprint", "artifact_fingerprint_contract"}})
    if actual != expected_proposal_fingerprint or actual != proposal.get("artifact_fingerprint"):
        raise ValueError("PROPOSAL_FINGERPRINT_CHANGED")
    if (proposal.get("approved") is not False or proposal.get("runtime_use_permitted") is not False
            or proposal.get("status") != "PROPOSED"):
        raise ValueError("NOT_A_NON_AUTHORITATIVE_PROPOSAL")
    bindings = proposal["proposal_bindings"]
    keys = [tuple(b["natural_key"]) for b in bindings]
    if len(set(keys)) != len(keys) or set(keys) != set(baseline_states):
        raise ValueError("EXACT_PROPOSAL_MEMBERSHIP_REQUIRED")
    stable, stale = [], []
    for binding in sorted(bindings, key=lambda b: tuple(b["natural_key"])):
        key = tuple(binding["natural_key"])
        current = current_states.get(key)
        if (current != baseline_states[key] or not current
                or current.get("policy_result") != "UNIQUE"
                or current.get("competing_context") is not False
                or current.get("source_proofs_valid") is not True):
            stale.append({"natural_key": list(key), "state": "STALE_PROPOSAL_REVIEW_REQUIRED"})
        else:
            stable.append({**deepcopy(binding), "current_state_fingerprint": fingerprint(current)})
    result = dict(rule_version=RULE, status="AWAITING_OPERATOR_CONFIRMATION", approved=False,
                  runtime_use_permitted=False, proposal_artifact_fingerprint=actual,
                  proposal_bundle_path=proposal_path,
                  proposal_baseline_fingerprint=proposal["baseline_authority_fingerprint"],
                  baseline_active_generation_id=current_global_state["generation"],
                  current_state_fingerprint=fingerprint(current_global_state),
                  stable_cases=stable, stale_cases=stale,
                  excluded_hold_count=len(proposal["holds"]))
    result["artifact_fingerprint"] = _digest(result)
    return result


def select_cases(candidate: dict, *, approve=(), hold=(), reject=(), approve_all=False) -> dict:
    """Make a displayable selection; omitted cases stay unapproved."""
    _verify(candidate)
    available = {tuple(b["natural_key"]) for b in candidate["stable_cases"]}
    groups = [list(map(tuple, group)) for group in (approve, hold, reject)]
    if any(len(g) != len(set(g)) for g in groups):
        raise ValueError("DUPLICATE_SELECTION")
    a, h, r = map(set, groups)
    if approve_all:
        if a or h or r:
            raise ValueError("APPROVE_ALL_REQUIRES_UNMODIFIED_STABLE_SET")
        a = available
    if not (a | h | r) <= available or a & h or a & r or h & r:
        raise ValueError("INVALID_OR_OVERLAPPING_SELECTION")
    result = dict(candidate_fingerprint=candidate["artifact_fingerprint"],
                  approved_keys=[list(k) for k in sorted(a)],
                  held_keys=[list(k) for k in sorted(h)],
                  rejected_keys=[list(k) for k in sorted(r)],
                  unreviewed_keys=[list(k) for k in sorted(available - a - h - r)])
    result["artifact_fingerprint"] = _digest(result)
    return result


def make_approval(candidate: dict, current_candidate: dict, selection: dict, *,
                  confirmed: bool, confirmed_selection_fingerprint: str,
                  operator: str, note: str, timestamp: str) -> dict:
    """Only explicit confirmation of the displayed exact selection creates a receipt."""
    for value in (candidate, current_candidate, selection):
        _verify(value)
    if current_candidate != candidate:
        raise ValueError("CURRENT_STATE_CHANGED_REVIEW_AGAIN")
    if (confirmed is not True or not operator.strip() or not note.strip() or not timestamp.strip()
            or confirmed_selection_fingerprint != selection["artifact_fingerprint"]):
        raise ValueError("EXPLICIT_EXACT_SELECTION_CONFIRMATION_REQUIRED")
    if selection["candidate_fingerprint"] != candidate["artifact_fingerprint"]:
        raise ValueError("SELECTION_CANDIDATE_CHANGED")
    reconstructed = select_cases(candidate, approve=selection["approved_keys"],
                                 hold=selection["held_keys"], reject=selection["rejected_keys"])
    if reconstructed != selection or not selection["approved_keys"]:
        raise ValueError("EXACT_NONEMPTY_SELECTION_REQUIRED")
    try:
        instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if instant.utcoffset() != timezone.utc.utcoffset(instant):
            raise ValueError("UTC_APPROVAL_TIMESTAMP_REQUIRED")
    except (ValueError, TypeError) as exc:
        raise ValueError("UTC_APPROVAL_TIMESTAMP_REQUIRED") from exc
    chosen = {tuple(k) for k in selection["approved_keys"]}
    result: dict[str, Any] = dict(
        approval_rule_version=RULE, status="OPERATOR_APPROVED_REVIEW_EVIDENCE",
        proposal_artifact_fingerprint=candidate["proposal_artifact_fingerprint"],
        proposal_bundle_path=candidate["proposal_bundle_path"],
        proposal_baseline_fingerprint=candidate["proposal_baseline_fingerprint"],
        baseline_active_generation_id=candidate["baseline_active_generation_id"],
        candidate_fingerprint=candidate["artifact_fingerprint"],
        current_state_fingerprint=candidate["current_state_fingerprint"],
        selection=deepcopy(selection),
        approved_cases=[deepcopy(b) for b in candidate["stable_cases"] if tuple(b["natural_key"]) in chosen],
        operator=operator, operator_note=note, approved_at_utc=timestamp,
        runtime_use_permitted=False, publication_authorized=False,
        production_apply_authorized=False, authority_mutation_authorized=False)
    result["artifact_fingerprint"] = _digest(result)
    return result


def write_approval(repository: Path, approval: dict) -> Path:
    """Exclusive, versioned docs output. Existing receipts cannot be overwritten."""
    _verify(approval)
    if (approval.get("status") != "OPERATOR_APPROVED_REVIEW_EVIDENCE"
            or not approval.get("approved_cases")
            or any(approval.get(k) is not False for k in (
                "runtime_use_permitted", "publication_authorized", "production_apply_authorized",
                "authority_mutation_authorized"))):
        raise ValueError("NON_EXECUTING_APPROVAL_REQUIRED")
    directory = repository.resolve() / APPROVAL_DIRECTORY
    # Fail closed if any component redirects the non-active docs destination.
    if directory.resolve() != directory:
        raise ValueError("APPROVAL_DIRECTORY_REDIRECTED")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"historical_publication_review_approval_v1.{approval['artifact_fingerprint']}.json"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(approval, sort_keys=True, indent=2) + "\n")
    return path


def render_case(case: dict, binding: dict, *, company_name: str, ticker: str) -> str:
    """Grouped exact source quotations, with all hashes and Unicode locators."""
    q = case["quarter"]
    event, = case["events"]
    e, o = event["evidence"], event["observation"]
    esc = lambda value: html.escape(str(value))
    key = "/".join(map(str, binding["natural_key"]))
    lines = [f'<details id="case-{key.replace("/", "-")}">',
             f"<summary>{esc(ticker)} — {esc(company_name)} — {esc(key)}</summary>\n",
             f"Period end: {esc(q['period_end'])}; quarter ID: {q['quarter_id']}. "
             f"{esc(e['filing_form'])}, {esc(e['accession_number'])}, {esc(e['source_timestamp_utc'])}.\n",
             f"Event: {esc(o['event_class'])} / {esc(o['actual_vs_preliminary'])}; "
             f"period: {esc(o['period_grain'])} / {esc(o['period_confidence'])}; "
             f"entity: {esc(o['entity_confidence'])}; revenue: {esc(o['revenue_scope'])}; "
             f"net result: {esc(o['net_result_scope'])}; broad P&amp;L: {o['supporting_p_and_l']}; "
             f"complete package: {o['complete_earnings_package']}.\n",
             f"{esc(o['financial_scope'])}\n",
             "Caution: active security valid_from is absent; issuer proof uses the exact SEC "
             "registrant and linked earnings release. This remains a proposal pending operator review.\n",
             "<p>Exact case bindings:</p><pre>" + esc(json.dumps(binding, sort_keys=True, indent=2)) + "</pre>"]
    for d in o["documents"]:
        loc = d["locator"]
        lines.extend([f"<p><b>{esc(loc['dimension'])}</b> — "
                      f"<a href=\"{esc(d['source_reference'])}\">{esc(d['source_reference'])}</a></p>",
                      f"<blockquote>{esc(d['excerpt'])}</blockquote>",
                      "<pre>" + esc(json.dumps({k: v for k, v in d.items() if k != "excerpt"},
                                               sort_keys=True, indent=2)) + "</pre>"])
    return "\n".join(lines + ["</details>\n"])
