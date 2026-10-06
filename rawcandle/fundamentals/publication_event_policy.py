"""Copy-only event policy over source-bound, reviewed event observations.

This module evaluates semantic facts, not arbitrary prose or workflow status. An
observation extractor/reviewer must establish the facts; missing proof is REVIEW.
It deliberately has no database writer, network client, or production selector.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from rawcandle.fundamentals.sec_result_context import same_accession_document


PUBLICATION_EVENT_POLICY_V1 = "PUBLICATION_EVENT_POLICY_V1"
EVENT_CLASSES = frozenset({
    "FULL_PERIOD_RESULTS", "PRELIMINARY_RESULTS", "PARTIAL_RESULTS",
    "GUIDANCE_OR_EXPECTATION", "SUPPLEMENTAL_RESULT_INFORMATION",
    "REVISED_OR_CORRECTED_RESULTS", "DUPLICATE_OR_REPEAT_PUBLICATION",
    "PARENT_SUBSIDIARY_OVERLAP", "PRO_FORMA_OR_TRANSACTION_CONTEXT",
    "NON_RESULT_EVENT", "OTHER_OR_INSUFFICIENT_EVENT_EVIDENCE",
})
RELATION_TYPES = frozenset({
    "PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT",
    "INITIAL_RESULT_TO_CORRECTION_OR_REVISION",
    "RESULT_TO_SAME_RESULT_REPEAT",
})
_BINDING_FIELDS = (
    "company_id", "fiscal_year", "fiscal_quarter", "source_type",
    "source_timestamp_utc", "accession_number", "source_reference",
    "document_id", "filing_form", "item_2_02_status", "evidence_hash",
)


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode()).hexdigest()


def evidence_binding(evidence: Mapping[str, Any]) -> str:
    return fingerprint({field: evidence.get(field) for field in _BINDING_FIELDS})


def reviewed_acceptance_gate(evidence: Mapping[str, Any], index: Mapping[str, Any] | None) -> str:
    """Corroborate an explicitly reviewed stored boundary, never replace it."""
    if index is None:
        return "NO_REVIEWED_DISCREPANCY"
    interpreted = datetime.fromisoformat(index["index_accepted_display"]).replace(
        tzinfo=ZoneInfo("America/New_York")
    ).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if not (
        index["accession"] == evidence["accession_number"]
        and interpreted == index["index_interpreted_utc"] == index["stored_utc"] == evidence["source_timestamp_utc"]
        and index["submissions_utc"] != evidence["source_timestamp_utc"]
        and index["matches_stored"] is True
        and re.fullmatch(r"[a-f0-9]{64}", index["index_sha256"])
        and same_accession_document(evidence["source_reference"], index["index_url"])
    ):
        raise ValueError("ACCEPTANCE_SOURCE_DISCREPANCY_NOT_CORROBORATED")
    return "ACCEPTANCE_SOURCE_DISCREPANCY_REVIEWED"


def _key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    return int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])


def _proof_present(observation: Mapping[str, Any]) -> bool:
    documents = observation.get("documents", [])
    return bool(observation.get("review_reference") and documents) and all(
        isinstance(document.get("excerpt"), str) and document["excerpt"].strip()
        and document.get("excerpt_sha256") == sha256(document["excerpt"].encode()).hexdigest()
        and isinstance(document.get("source_sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", document["source_sha256"])
        and document.get("source_reference")
        for document in documents
    )


def classify_event(
    quarter: Mapping[str, Any], evidence: Mapping[str, Any],
    observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply Policy B to reviewed dimensions, retaining their source provenance."""
    facts = deepcopy(dict(observation or {}))
    result = {
        "policy_version": PUBLICATION_EVENT_POLICY_V1,
        "event_class": facts.get("event_class", "OTHER_OR_INSUFFICIENT_EVENT_EVIDENCE"),
        "actual_vs_preliminary": facts.get("actual_vs_preliminary", "UNKNOWN"),
        "financial_scope": facts.get("financial_scope", "UNKNOWN"),
        "entity_confidence": facts.get("entity_confidence", "UNKNOWN"),
        "period_confidence": facts.get("period_confidence", "UNKNOWN"),
        "observations": facts,
        "observation_fingerprint": fingerprint(facts),
        "eligibility": "REVIEW", "eligibility_reason": "REVIEW_REQUIRED_EVENT_SCOPE",
        "review_reason": None,
    }

    def decide(decision: str, reason: str) -> dict[str, Any]:
        result.update(eligibility=decision, eligibility_reason=reason,
                      review_reason=reason if decision == "REVIEW" else None)
        return result

    if not facts or not _proof_present(facts):
        return decide("REVIEW", "REVIEW_REQUIRED_EVENT_EVIDENCE")
    if facts.get("evidence_binding") != evidence_binding(evidence) or _key(evidence) != _key(quarter):
        return decide("REVIEW", "REVIEW_REQUIRED_EVIDENCE_BINDING")
    if any(doc["source_reference"] != evidence["source_reference"]
           and not same_accession_document(str(evidence["source_reference"]), doc["source_reference"])
           for doc in facts["documents"]):
        return decide("REVIEW", "REVIEW_REQUIRED_EVIDENCE_BINDING")
    if (result["event_class"] not in EVENT_CLASSES
            or facts.get("entity_confidence") not in {"PROVEN", "OTHER_ENTITY", "UNCERTAIN"}
            or facts.get("period_confidence") not in {"PROVEN", "OTHER_PERIOD", "UNCERTAIN"}):
        return decide("REVIEW", "REVIEW_REQUIRED_EVENT_SCOPE")
    if (evidence.get("source_type") != "SEC_8K_ITEM_2_02"
            or evidence.get("filing_form") != "8-K"
            or evidence.get("item_2_02_status") != "PRESENT_AND_DOCUMENT_CONFIRMED"):
        return decide("REVIEW", "REVIEW_REQUIRED_SOURCE_AUTHORITY")
    if "UNCERTAIN" in {facts["entity_confidence"], facts["period_confidence"]}:
        return decide("REVIEW", "REVIEW_REQUIRED_EVENT_SCOPE")
    if facts["entity_confidence"] == "OTHER_ENTITY":
        return decide("NO", "OTHER_ENTITY_RESULTS")
    if facts["period_confidence"] == "OTHER_PERIOD":
        return decide("NO", "OTHER_PERIOD_RESULTS")
    if (facts.get("period_end") != quarter["period_end"]
            or facts.get("period_grain") != "QUARTER"):
        return decide("REVIEW", "REVIEW_REQUIRED_EVENT_SCOPE")
    event_class = result["event_class"]
    if event_class in {"GUIDANCE_OR_EXPECTATION", "PRO_FORMA_OR_TRANSACTION_CONTEXT",
                       "NON_RESULT_EVENT"}:
        return decide("NO", event_class)
    if facts.get("actual_vs_preliminary") not in {"ACTUAL", "PRELIMINARY_COMPLETED_PERIOD"}:
        return decide("REVIEW", "REVIEW_REQUIRED_ACTUAL_PERIOD")
    accepted = datetime.fromisoformat(str(evidence["source_timestamp_utc"]).replace("Z", "+00:00"))
    if accepted.date().isoformat() < str(quarter["period_end"]):
        return decide("NO", "PERIOD_NOT_COMPLETED")
    revenue = facts.get("revenue_scope")
    net = facts.get("net_result_scope")
    if revenue not in {"CONSOLIDATED", "EXPLICIT_ZERO", "ABSENT", "SEGMENT", "UNKNOWN"}:
        return decide("REVIEW", "REVIEW_REQUIRED_FINANCIAL_SCOPE")
    if net not in {"GAAP_TOTAL", "GAAP_CONTINUING_OPERATIONS", "ABSENT", "UNKNOWN"}:
        return decide("REVIEW", "REVIEW_REQUIRED_FINANCIAL_SCOPE")
    if "UNKNOWN" in {revenue, net} or (revenue == "SEGMENT" and net != "ABSENT"):
        return decide("REVIEW", "REVIEW_REQUIRED_EVENT_SCOPE")
    if event_class == "OTHER_OR_INSUFFICIENT_EVENT_EVIDENCE":
        return decide("REVIEW", "REVIEW_REQUIRED_EVENT_EVIDENCE")
    if event_class == "DUPLICATE_OR_REPEAT_PUBLICATION":
        # A label alone cannot suppress a competing event. The relation phase
        # must prove the original event before this can be excluded.
        return decide("REVIEW", "REVIEW_REQUIRED_REPEAT_RELATION")
    has_net = net == "GAAP_TOTAL" or (
        net == "GAAP_CONTINUING_OPERATIONS" and facts.get("continuing_operations_explicit") is True
    )
    has_revenue = revenue in {"CONSOLIDATED", "EXPLICIT_ZERO"}
    pre_revenue_full = (
        event_class in {"FULL_PERIOD_RESULTS", "REVISED_OR_CORRECTED_RESULTS"}
        and facts.get("pre_revenue_complete_expense_statement") is True
        and revenue == "ABSENT" and net == "GAAP_TOTAL"
    )
    broad = facts.get("supporting_p_and_l") is True
    if not isinstance(facts.get("supporting_p_and_l"), bool):
        return decide("REVIEW", "REVIEW_REQUIRED_FINANCIAL_SCOPE")
    if not (has_net and (has_revenue or pre_revenue_full) and broad):
        return decide("NO", "INSUFFICIENT_BROAD_EARNINGS_MINIMUM")
    if event_class in {"PARTIAL_RESULTS", "SUPPLEMENTAL_RESULT_INFORMATION",
                       "PARENT_SUBSIDIARY_OVERLAP"}:
        return decide("REVIEW", "REVIEW_REQUIRED_CONTRADICTORY_EVENT_SCOPE")
    if event_class == "PRELIMINARY_RESULTS":
        if facts["actual_vs_preliminary"] != "PRELIMINARY_COMPLETED_PERIOD":
            return decide("REVIEW", "REVIEW_REQUIRED_PRELIMINARY_SCOPE")
        return decide("YES", "BROAD_COMPLETED_PERIOD_PRELIMINARY_EARNINGS")
    if facts["actual_vs_preliminary"] != "ACTUAL":
        return decide("REVIEW", "REVIEW_REQUIRED_FULL_PACKAGE")
    if facts.get("complete_earnings_package") is not True:
        return decide("REVIEW", "REVIEW_REQUIRED_FULL_PACKAGE")
    return decide("YES", "COMPLETE_PERIOD_EARNINGS_PACKAGE")


def evaluate_candidates(
    quarter: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *,
    observations: Mapping[str, Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]] = (),
    policy_version: str,
) -> dict[str, Any]:
    """Return an auditable proposal, never an authority write/apply candidate set."""
    if policy_version != PUBLICATION_EVENT_POLICY_V1:
        raise ValueError("UNSUPPORTED_PUBLICATION_EVENT_POLICY")
    retained = [deepcopy(dict(row)) for row in candidates]
    assessed = [{"evidence": row, **classify_event(quarter, row, observations.get(str(row["evidence_id"])))}
                for row in retained]
    by_id = {str(row["evidence"]["evidence_id"]): row for row in assessed}
    relation_results = []
    for original in relations:
        edge = deepcopy(dict(original))
        source = by_id.get(str(edge.get("from_evidence_id")))
        target = by_id.get(str(edge.get("to_evidence_id")))
        valid = bool(source and target and source is not target
                     and edge.get("relation_type") in RELATION_TYPES
                     and edge.get("review_reference") and edge.get("same_economic_chain") is True)
        if valid:
            a, b = source["evidence"], target["evidence"]
            valid = (
                _key(a) == _key(b) == _key(quarter)
                and a["source_type"] == b["source_type"] == "SEC_8K_ITEM_2_02"
                and source["entity_confidence"] == target["entity_confidence"] == "PROVEN"
                and source["period_confidence"] == target["period_confidence"] == "PROVEN"
                and source["observations"].get("period_end") == target["observations"].get("period_end") == quarter["period_end"]
                and source["observations"].get("period_grain") == target["observations"].get("period_grain") == "QUARTER"
                and edge.get("from_observation_fingerprint") == source["observation_fingerprint"]
                and edge.get("to_observation_fingerprint") == target["observation_fingerprint"]
                and a["source_timestamp_utc"] < b["source_timestamp_utc"]
                and bool(edge.get("relation_reason"))
                and all(edge.get(field) and edge[field] in " ".join(
                    doc["excerpt"] for doc in row["observations"].get("documents", []))
                    for field, row in (("from_excerpt", source), ("to_excerpt", target)))
            )
        if valid:
            kind = edge["relation_type"]
            if kind == "PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT":
                valid = (source["event_class"] == "PRELIMINARY_RESULTS"
                         and target["event_class"] == "FULL_PERIOD_RESULTS")
            elif kind == "INITIAL_RESULT_TO_CORRECTION_OR_REVISION":
                valid = target["event_class"] == "REVISED_OR_CORRECTED_RESULTS"
            else:
                valid = target["event_class"] in {
                    "DUPLICATE_OR_REPEAT_PUBLICATION", "SUPPLEMENTAL_RESULT_INFORMATION",
                }
        relation_results.append({**edge, "relation_evidence_fingerprint": fingerprint(original),
                                 "valid": bool(valid), "reason": "PROVEN_TYPED_EVENT_CHAIN" if valid
                                 else "REVIEW_REQUIRED_EVENT_RELATION"})
    # Repeat exclusion is proof-dependent, not a presentation-format veto.
    for edge in relation_results:
        if edge["valid"] and edge["relation_type"] == "RESULT_TO_SAME_RESULT_REPEAT":
            source, target = by_id[edge["from_evidence_id"]], by_id[edge["to_evidence_id"]]
            if source["eligibility"] == "YES" and target["eligibility_reason"] == "REVIEW_REQUIRED_REPEAT_RELATION":
                target.update(eligibility="NO", eligibility_reason="PROVEN_SAME_RESULT_REPEAT",
                              review_reason=None)
    eligible = {key for key, row in by_id.items() if row["eligibility"] == "YES"}
    review = [row for row in assessed if row["eligibility"] == "REVIEW"]
    invalid = any(not edge["valid"] for edge in relation_results)
    if len(by_id) != len(assessed):
        invalid = True
    filtering = "REVIEW" if review or invalid else (
        "UNIQUE" if len(eligible) == 1 else "AMBIGUOUS" if eligible else "NOT_FOUND")
    final, selected, reason = filtering, None, "NO_DETERMINISTIC_FIRST_EVENT"
    if filtering == "UNIQUE":
        selected, reason = next(iter(eligible)), "ONLY_QUALIFYING_EVENT"
    elif filtering == "AMBIGUOUS":
        edges = [(edge["from_evidence_id"], edge["to_evidence_id"])
                 for edge in relation_results if edge["valid"]
                 and edge["from_evidence_id"] in eligible and edge["to_evidence_id"] in eligible]
        successors = {key: set() for key in eligible}
        predecessors = {key: set() for key in eligible}
        for a, b in edges:
            successors[a].add(b)
            predecessors[b].add(a)
        roots = [key for key in eligible if not predecessors[key]]
        # Only a proven, unbranched connected chain can establish first event.
        # Chronology validates edges above; it never constructs them.
        if len(roots) == 1 and all(len(successors[key]) <= 1 and len(predecessors[key]) <= 1 for key in eligible):
            visited, current = set(), roots[0]
            while current not in visited:
                visited.add(current)
                if not successors[current]:
                    break
                current = next(iter(successors[current]))
            if visited == eligible:
                final, selected, reason = "UNIQUE", roots[0], "FIRST_QUALIFYING_EVENT_IN_PROVEN_TYPED_CHAIN"
    chosen = by_id[selected]["evidence"] if selected else None
    for row in assessed:
        event_id = row["evidence"]["evidence_id"]
        row["relations_to_competing_events"] = [
            {field: edge[field] for field in (
                "relation_type", "relation_evidence_fingerprint", "valid", "reason",
            )} for edge in relation_results
            if event_id in {edge.get("from_evidence_id"), edge.get("to_evidence_id")}
        ]
        row["precedence_decision"] = "SELECTED_FIRST_EVENT" if event_id == selected else "RETAINED_NOT_SELECTED"
        row["selected_first_event_reason"] = reason if event_id == selected else None
    return {
        "policy_version": policy_version, "natural_key": list(_key(quarter)),
        "retained_candidates": retained, "candidate_evaluations": assessed,
        "relation_edges": relation_results, "original_candidate_count": len(retained),
        "eligible_count": len(eligible), "filtering_result": filtering,
        "precedence_result": final, "final_result": final,
        "selected_evidence_id": selected,
        "selected_accession": chosen["accession_number"] if chosen else None,
        "selected_timestamp": chosen["source_timestamp_utc"] if chosen else None,
        "selected_first_event_reason": reason,
        "review_reason": "REVIEW_REQUIRED_EVENT_RELATION" if invalid else (
            "REVIEW_REQUIRED_EVENT_SCOPE" if review else None),
    }
