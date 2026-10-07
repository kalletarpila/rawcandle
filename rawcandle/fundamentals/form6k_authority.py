"""Explicit, offline Form 6-K authority over frozen reviewed facts.

No acquisition, database writer, default resolver dispatch, or production plan
adapter lives here. Hashes bind reviewed assertions; they are not signatures or
an autonomous verifier of financial meaning.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from rawcandle.fundamentals.publication_event_policy import EVENT_CLASSES, fingerprint
from rawcandle.fundamentals.result_publication import SOURCE_RANK, normalize_utc_timestamp


FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 = "FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1"
SEC_FORM_6K_RESULT = "SEC_FORM_6K_RESULT"
FORM6K_SOURCE_RANK = 2
RELATION_TYPES = frozenset({
    "RESULT_TO_SAME_RESULT_REPEAT", "RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION",
    "INITIAL_RESULT_TO_REVISION", "RESULT_TO_XBRL_ONLY_SUPPLEMENT",
    "PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT",
})
CONTRACT = {
    "version": FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1,
    "source_type": SEC_FORM_6K_RESULT, "source_rank": FORM6K_SOURCE_RANK,
    "confidence": "MEDIUM", "forms": ["6-K", "6-K/A_REVIEWED_ROLE_ONLY"],
    "timestamp_rule": "PARENT_SUBMISSIONS_INDEX_AND_AVAILABLE_HEADER_AGREEMENT",
    "identity_rule": "REVIEWED_OFFICIAL_TEMPORAL_UNDERLYING_ISSUER_CHAIN",
    "financial_rule": "EXPLICIT_QUARTER_STATUTORY_CONSOLIDATED_EARNINGS",
    "relation_types": sorted(RELATION_TYPES), "mode": "COPY_ONLY",
}


def natural_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    return int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])


def candidate_binding(candidate: Mapping[str, Any]) -> str:
    return fingerprint({k: v for k, v in candidate.items() if k != "reviewed_binding"})


def _sec_document(url: Any, cik: Any, accession: str) -> bool:
    parsed = urlsplit(str(url or ""))
    parts = parsed.path.split("/")
    return bool(parsed.scheme == "https" and parsed.netloc == "www.sec.gov"
                and not parsed.query and not parsed.fragment and len(parts) == 7
                and parts[1:4] == ["Archives", "edgar", "data"]
                and parts[4].isdigit() and str(int(parts[4])) == str(int(cik))
                and parts[5] == accession.replace("-", "")
                and re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:htm|html|txt|pdf)", parts[6]))


def _proof(documents: Any) -> bool:
    return bool(isinstance(documents, list) and documents) and all(
        isinstance(d, dict) and d.get("source_reference") and d.get("excerpt")
        and isinstance(d.get("excerpt"), str)
        and d.get("excerpt_sha256") == sha256(d["excerpt"].encode()).hexdigest()
        and re.fullmatch(r"[a-f0-9]{64}", str(d.get("source_sha256", "")))
        for d in documents)


def acceptance_gate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Compare observations, never repair one or substitute another source."""
    a = deepcopy(candidate.get("acceptance", {}))
    result = {"observations": a, "status": "REVIEW_ACCEPTANCE_TIMESTAMP_EVIDENCE",
              "selected_timestamp": None}
    if not isinstance(a, dict):
        return result
    try:
        acc, cik = candidate["accession"], candidate["sec_cik"]
        if (a.get("accession") != acc or a.get("index_timezone") != "America/New_York"
                or not _sec_document(a.get("index_url"), cik, acc)
                or urlsplit(a["index_url"]).path.rsplit("/", 1)[-1] != acc + "-index.html"
                or not re.fullmatch(r"[a-f0-9]{64}", str(a.get("index_sha256", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(a.get("submissions_sha256", "")))
                or a.get("submissions_url") != f"https://data.sec.gov/submissions/CIK{str(int(cik)).zfill(10)}.json"
                or not a.get("observed_at_utc")):
            return result
        normalize_utc_timestamp(a["observed_at_utc"])
        display = datetime.strptime(a["index_accepted_display"], "%Y-%m-%d %H:%M:%S")
        index = display.replace(tzinfo=ZoneInfo(a["index_timezone"])).astimezone(timezone.utc)
        # An ambiguous/nonexistent local wall time needs review, not fold guessing.
        zone = ZoneInfo(a["index_timezone"])
        if display.replace(tzinfo=zone, fold=0).utcoffset() != display.replace(tzinfo=zone, fold=1).utcoffset():
            return result
        index_utc = index.strftime("%Y-%m-%dT%H:%M:%SZ")
        values = [normalize_utc_timestamp(a["submissions_utc"]), index_utc]
        header = a.get("full_submission_header")
        if header is not None:
            if (not _sec_document(a.get("full_submission_url"), cik, acc)
                    or urlsplit(a["full_submission_url"]).path.rsplit("/", 1)[-1] != acc + ".txt"
                    or not re.fullmatch(r"[a-f0-9]{64}", str(a.get("full_submission_sha256", "")))):
                return result
            header_display = datetime.strptime(header, "%Y%m%d%H%M%S")
            if header_display != display:
                result["status"] = "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT"
                return result
            values.append(header_display.replace(tzinfo=zone).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        for prior in a.get("prior_observations", []):
            if not prior.get("review_reference") or prior.get("accession") != acc:
                return result
            values.append(normalize_utc_timestamp(prior["timestamp_utc"]))
        result["index_interpreted_utc"] = index_utc
        if len(set(values)) != 1:
            result["status"] = "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT"
        else:
            result.update(status="CONSISTENT_PARENT_ACCEPTANCE", selected_timestamp=values[0])
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    return result


def identity_gate(quarter: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    w = candidate.get("identity", {})
    if not w.get("review_reference") or not _proof(w.get("documents")):
        return "REVIEW_IDENTITY_WITNESS"
    if w.get("filer_role") in {"DEPOSITARY_BANK", "ADR_PROGRAM", "OTHER_ENTITY"}:
        return "WRONG_ENTITY"
    if w.get("perimeter_match") == "OTHER_PERIMETER":
        return "WRONG_ENTITY"
    if (w.get("security_company_id") != quarter.get("company_id")
            or w.get("underlying_company_id") != quarter.get("company_id")
            or w.get("security_id") != quarter.get("security_id")
            or w.get("canonical_cik") != quarter.get("sec_cik")
            or w.get("sec_reporting_cik") != candidate.get("sec_cik")
            or w.get("canonical_cik") != w.get("sec_reporting_cik")
            or w.get("filer_role") != "CONSOLIDATED_REPORTING_ISSUER"
            or w.get("underlying_match") != "PROVEN"
            or w.get("perimeter_match") != "PROVEN_CANONICAL_CONSOLIDATED_GROUP"
            or not w.get("underlying_issuer")
            or w.get("official_security_type") not in {"ADS", "ORDINARY_SHARES", "CLASS_A_ORDINARY_SHARES", "COMMON_SHARES"}
            or w.get("is_adr_or_ads") is not (w.get("official_security_type") == "ADS")):
        return "REVIEW_IDENTITY_CHAIN"
    for doc in w["documents"]:
        p = urlsplit(doc["source_reference"])
        if not (p.scheme == "https" and p.netloc == "www.sec.gov"
                and p.path.startswith(f"/Archives/edgar/data/{int(candidate['sec_cik'])}/")):
            return "REVIEW_IDENTITY_SOURCE"
    try:
        date.fromisoformat(w["valid_from"])
        if w.get("temporal_match") != "PROVEN" or w["valid_from"] > quarter["period_end"]:
            return "IDENTITY_TEMPORAL_REVIEW"
        publication_date = acceptance_gate(candidate).get("index_interpreted_utc", "")[:10]
        if not publication_date:
            publication_date = candidate.get("acceptance", {}).get("submissions_utc", "")[:10]
        date.fromisoformat(publication_date)
        if w["valid_from"] > publication_date or (w.get("valid_to") and w["valid_to"] < publication_date):
            return "IDENTITY_TEMPORAL_REVIEW"
        if w.get("valid_to"):
            date.fromisoformat(w["valid_to"])
    except (KeyError, TypeError, ValueError):
        return "IDENTITY_TEMPORAL_REVIEW"
    return "PROVEN_OFFICIAL_IDENTITY_CHAIN"


def assess_candidate(quarter: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    c = deepcopy(dict(candidate))
    a = acceptance_gate(c)
    out = {"candidate": c, "candidate_fingerprint": candidate_binding(c),
           "identity_result": "NOT_ASSESSED", "acceptance_result": a,
           "eligibility": "REVIEW", "reason": "REVIEW_FROZEN_EVIDENCE_BINDING"}
    w = c.get("identity", {})
    out["provider_security_type_conflict"] = (
        ("ADR" in str(w.get("provider_security_type", ""))) != (w.get("official_security_type") == "ADS"))

    def decide(eligibility: str, reason: str) -> dict[str, Any]:
        out.update(eligibility=eligibility, reason=reason)
        return out

    try:
        if (c.get("reviewed_binding") != candidate_binding(c) or not c.get("review_reference")
                or natural_key(c) != natural_key(quarter)
                or c.get("quarter_id") != quarter.get("quarter_id")
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", c.get("accession", ""))
                or not _sec_document(c.get("parent_url"), c["sec_cik"], c["accession"])
                or not _proof(c.get("documents"))
                or not any(d["source_reference"] == c["parent_url"] for d in c["documents"])
                or any(not _sec_document(d["source_reference"], c["sec_cik"], c["accession"]) for d in c["documents"])):
            return out
        if c.get("source_type") != SEC_FORM_6K_RESULT or c.get("form") not in {"6-K", "6-K/A"}:
            return decide("REVIEW", "REVIEW_SOURCE_AUTHORITY")
        identity = identity_gate(quarter, c)
        out["identity_result"] = identity
        if identity != "PROVEN_OFFICIAL_IDENTITY_CHAIN":
            return decide("NO" if identity == "WRONG_ENTITY" else "REVIEW", identity)
        f = c.get("event", {})
        if f.get("entity_match") == "OTHER_ENTITY":
            return decide("NO", "WRONG_ENTITY")
        if f.get("entity_match") != "PROVEN":
            return decide("REVIEW", "REVIEW_REPORTING_PERIMETER")
        if (f.get("period_match") == "OTHER_PERIOD" or f.get("period_grain") in {"HALF_YEAR", "YEAR"}):
            return decide("NO", "WRONG_PERIOD")
        if (f.get("period_match") != "PROVEN" or f.get("period_grain") != "QUARTER"
                or f.get("period_end") != quarter["period_end"]
                or f.get("fiscal_year") != quarter["fiscal_year"]
                or f.get("fiscal_quarter") != quarter["fiscal_quarter"]):
            return decide("REVIEW", "REVIEW_EXACT_PERIOD")
        if f.get("event_class") not in EVENT_CLASSES:
            return decide("REVIEW", "REVIEW_EVENT_CLASS")
        if f["event_class"] in {"NON_RESULT_EVENT", "GUIDANCE_OR_EXPECTATION", "PRO_FORMA_OR_TRANSACTION_CONTEXT"}:
            return decide("NO", "NON_RESULT_EVENT")
        if c.get("form") == "6-K/A" and c.get("amendment_role") in {"XBRL_ONLY_SUPPLEMENT", "TECHNICAL_SUPPLEMENT"}:
            if f["event_class"] != "SUPPLEMENTAL_RESULT_INFORMATION":
                return decide("REVIEW", "REVIEW_CONTRADICTORY_AMENDMENT_ROLE")
            return decide("RELATED_REVIEW", "REVIEW_AMENDMENT_RELATION")
        if (c.get("form") == "6-K/A" and c.get("amendment_role") == "FIRST_SUBSTANTIVE_RESULT"
                and f["event_class"] not in {"FULL_PERIOD_RESULTS", "PRELIMINARY_RESULTS"}):
            return decide("REVIEW", "REVIEW_CONTRADICTORY_AMENDMENT_ROLE")
        if f["event_class"] in {"DUPLICATE_OR_REPEAT_PUBLICATION", "SUPPLEMENTAL_RESULT_INFORMATION"}:
            return decide("RELATED_REVIEW", "REVIEW_REPEAT_RELATION")
        if f["event_class"] in {"PARTIAL_RESULTS", "PARENT_SUBSIDIARY_OVERLAP"}:
            return decide("NO", "INSUFFICIENT_COMPLETE_RESULT_SCOPE")
        if (f.get("accounting_framework") not in {"GAAP", "IFRS", "TIFRS", "OTHER_STATUTORY"}
                or (f.get("accounting_framework") == "OTHER_STATUTORY" and not f.get("framework_reference"))
                or f.get("revenue_scope") not in {"CONSOLIDATED", "EXPLICIT_ZERO", "STATUTORY_EQUIVALENT_TOP_LINE"}
                or f.get("net_scope") not in {"STATUTORY_CONSOLIDATED", "STATUTORY_ATTRIBUTABLE", "STATUTORY_CONTINUING_OPERATIONS"}
                or not f.get("income_perimeter_reference")
                or f.get("supporting_statement") is not True
                or f.get("completed_period") is not True or f.get("complete_package") is not True
                or f.get("derived_arithmetic") is not False):
            return decide("REVIEW", "REVIEW_STATUTORY_QUARTER_MINIMUM")
        expected_actual = "PRELIMINARY_COMPLETED_PERIOD" if f["event_class"] == "PRELIMINARY_RESULTS" else "ACTUAL"
        if f.get("actual_vs_preliminary") != expected_actual:
            return decide("REVIEW", "REVIEW_COMPLETED_PERIOD_ROLE")
        result_urls = f.get("result_document_urls", [])
        unrelated = {e["url"] for e in c.get("linked_exhibits", []) if e.get("result_bearing") is not True}
        if (not result_urls or any(u not in {d["source_reference"] for d in c["documents"]} for u in result_urls)
                or unrelated.intersection(result_urls)):
            return decide("REVIEW", "REVIEW_RESULT_DOCUMENT_BINDING")
        if a["status"] != "CONSISTENT_PARENT_ACCEPTANCE":
            return decide("TIMESTAMP_REVIEW", a["status"])
        if a["selected_timestamp"][:10] < quarter["period_end"]:
            return decide("NO", "PERIOD_NOT_COMPLETED")
        if c["form"] == "6-K/A" and c.get("amendment_role") != "FIRST_SUBSTANTIVE_RESULT":
            return decide("RELATED_REVIEW", "REVIEW_AMENDMENT_RELATION")
        return decide("YES", "EXPLICIT_STATUTORY_QUARTER_RESULTS")
    except (KeyError, TypeError, ValueError):
        return out


def _relations(quarter: Mapping[str, Any], assessed: list[dict[str, Any]], edges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r["candidate"]["candidate_id"]: r for r in assessed}
    results = []
    for original in edges:
        e = deepcopy(dict(original))
        source, target = by_id.get(e.get("from_candidate_id")), by_id.get(e.get("to_candidate_id"))
        kind = e.get("relation_type")
        valid = bool(source and target and source is not target and kind in RELATION_TYPES
                     and e.get("review_reference") and e.get("same_economic_chain") is True
                     and e.get("relation_reason") and _proof(e.get("documents")))
        if valid:
            ca, cb = source["candidate"], target["candidate"]
            valid = bool(source["identity_result"] == target["identity_result"] == "PROVEN_OFFICIAL_IDENTITY_CHAIN"
                         and natural_key(ca) == natural_key(cb) == natural_key(quarter)
                         and e.get("from_candidate_fingerprint") == source["candidate_fingerprint"]
                         and e.get("to_candidate_fingerprint") == target["candidate_fingerprint"]
                         and ca["event"].get("period_grain") == cb["event"].get("period_grain") == "QUARTER"
                         and ca["event"].get("period_match") == cb["event"].get("period_match") == "PROVEN"
                         and ca["event"].get("period_end") == cb["event"].get("period_end") == quarter["period_end"]
                         and all(d in ca["documents"] + cb["documents"] for d in e["documents"])
                         and any(d in ca["documents"] for d in e["documents"])
                         and any(d in cb["documents"] for d in e["documents"]))
            roles = {
                "RESULT_TO_SAME_RESULT_REPEAT": {"DUPLICATE_OR_REPEAT_PUBLICATION"},
                "RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION": {"FULL_PERIOD_RESULTS", "DUPLICATE_OR_REPEAT_PUBLICATION"},
                "INITIAL_RESULT_TO_REVISION": {"REVISED_OR_CORRECTED_RESULTS"},
                "RESULT_TO_XBRL_ONLY_SUPPLEMENT": {"SUPPLEMENTAL_RESULT_INFORMATION"},
                "PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT": {"FULL_PERIOD_RESULTS"},
            }
            valid = valid and cb["event"].get("event_class") in roles[kind]
            valid = valid and ca["event"].get("event_class") in {
                "FULL_PERIOD_RESULTS", "PRELIMINARY_RESULTS", "PARTIAL_RESULTS", "REVISED_OR_CORRECTED_RESULTS"}
            if kind == "PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT":
                valid = valid and ca["event"].get("event_class") == "PRELIMINARY_RESULTS"
            if kind == "RESULT_TO_XBRL_ONLY_SUPPLEMENT":
                valid = valid and cb.get("form") == "6-K/A" and cb.get("amendment_role") == "XBRL_ONLY_SUPPLEMENT"
            if valid and kind != "RESULT_TO_XBRL_ONLY_SUPPLEMENT":
                aa, ab = source["acceptance_result"], target["acceptance_result"]
                valid = (aa["status"] == ab["status"] == "CONSISTENT_PARENT_ACCEPTANCE"
                         and aa["selected_timestamp"] < ab["selected_timestamp"])
        results.append({**e, "valid": bool(valid), "relation_fingerprint": fingerprint(original)})
    return results


def evaluate_form6k(
    quarter: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *,
    relations: Sequence[Mapping[str, Any]] = (), authority_version: str,
    existing_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Explicit resolver entry point; retain all candidates and all hold reasons."""
    if authority_version != FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1:
        raise ValueError("UNSUPPORTED_FORM6K_AUTHORITY")
    rows = [assess_candidate(quarter, c) for c in candidates]
    relation_results = _relations(quarter, rows, relations)
    by_id = {r["candidate"]["candidate_id"]: r for r in rows}
    invalid = (len(by_id) != len(rows) or len({r['candidate']['accession'] for r in rows}) != len(rows)
               or any(not e["valid"] for e in relation_results))
    for edge in relation_results:
        if not edge["valid"]:
            continue
        source, target = by_id[edge["from_candidate_id"]], by_id[edge["to_candidate_id"]]
        if source["eligibility"] == "YES" and edge["relation_type"] in {
            "RESULT_TO_SAME_RESULT_REPEAT", "RESULT_TO_XBRL_ONLY_SUPPLEMENT"}:
            target.update(eligibility="NO", reason="PROVEN_NON_INDEPENDENT_SUPPLEMENT_OR_REPEAT")
        elif edge["relation_type"] == "INITIAL_RESULT_TO_REVISION" and target["eligibility"] == "RELATED_REVIEW":
            if target["reason"] == "REVIEW_AMENDMENT_RELATION":
                target.update(eligibility="YES", reason="PROVEN_RESULT_REVISION")
    eligible = {key for key, row in by_id.items() if row["eligibility"] == "YES"}
    content = [r for r in rows if r["eligibility"] in {"YES", "TIMESTAMP_REVIEW"}]
    reviews = [r for r in rows if r["eligibility"] in {"REVIEW", "RELATED_REVIEW", "TIMESTAMP_REVIEW"}]
    selected = None
    if invalid:
        status, reason = "REVIEW", "REVIEW_EVENT_RELATION_OR_DUPLICATE_INPUT"
    elif len(content) > 1:
        status, reason = "MULTIPLE_COMPETING_EVENTS", "NO_PROVEN_SINGLE_RESULT_CHAIN"
        links = [(e["from_candidate_id"], e["to_candidate_id"]) for e in relation_results if e["valid"]
                 and e["from_candidate_id"] in eligible and e["to_candidate_id"] in eligible]
        parents = {key: [] for key in eligible}; children = {key: [] for key in eligible}
        for a, b in links:
            children[a].append(b); parents[b].append(a)
        roots = [key for key in eligible if not parents[key]]
        if not reviews and len(roots) == 1 and all(len(parents[k]) <= 1 and len(children[k]) <= 1 for k in eligible):
            visited, current = set(), roots[0]
            while current not in visited:
                visited.add(current)
                if not children[current]:
                    break
                current = children[current][0]
            if visited == eligible:
                selected = by_id[roots[0]]
                status, reason = "UNIQUE", "FIRST_RESULT_IN_PROVEN_TYPED_CHAIN"
    elif reviews:
        temporal = any(r["identity_result"] == "IDENTITY_TEMPORAL_REVIEW" for r in reviews)
        status = "IDENTITY_TEMPORAL_REVIEW" if temporal else "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT" if any(
            r["reason"] == "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT" for r in reviews) else "REVIEW"
        reason = status
    elif len(eligible) == 1:
        selected = by_id[next(iter(eligible))]
        status, reason = "UNIQUE", "ONLY_QUALIFYING_FORM6K_RESULT"
    else:
        status = "WRONG_PERIOD" if rows and all(r["reason"] == "WRONG_PERIOD" for r in rows) else "NOT_FOUND"
        reason = status
    preserved = None
    if existing_authority and existing_authority.get("status") == "VERIFIED":
        if (natural_key(existing_authority) != natural_key(quarter)
                or existing_authority.get("quarter_id") != quarter.get("quarter_id")):
            raise ValueError("EXISTING_AUTHORITY_IDENTITY_MISMATCH")
        source = existing_authority.get("result_publication_source")
        if source not in SOURCE_RANK and source != SEC_FORM_6K_RESULT:
            raise ValueError("EXISTING_AUTHORITY_SOURCE_UNSUPPORTED")
        rank = SOURCE_RANK.get(source, FORM6K_SOURCE_RANK if source == SEC_FORM_6K_RESULT else 0)
        timestamp = normalize_utc_timestamp(str(existing_authority.get("result_publication_timestamp_utc")))
        if rank > FORM6K_SOURCE_RANK:
            preserved = deepcopy(dict(existing_authority))
            status, reason, selected = "PRESERVED_HIGHER_PRIORITY_AUTHORITY", "EXISTING_SOURCE_HIERARCHY", None
        elif selected and rank == FORM6K_SOURCE_RANK and timestamp != selected["acceptance_result"]["selected_timestamp"]:
            status, reason, selected = "REVIEW", "EXISTING_SAME_RANK_AUTHORITY_CONFLICT", None
    chosen = selected["candidate"] if selected else None
    result = {
        "contract": deepcopy(CONTRACT), "contract_fingerprint": fingerprint(CONTRACT),
        "quarter": deepcopy(dict(quarter)), "candidate_evaluations": rows,
        "relation_results": relation_results, "final_result": status, "reason": reason,
        "selected_candidate_id": chosen["candidate_id"] if chosen else None,
        "selected_accession": chosen["accession"] if chosen else None,
        "selected_timestamp": selected["acceptance_result"]["selected_timestamp"] if selected else None,
        "selected_source": SEC_FORM_6K_RESULT if selected else None,
        "source_rank": FORM6K_SOURCE_RANK, "confidence": "MEDIUM" if selected else None,
        "preserved_authority": preserved,
    }
    result["decision_fingerprint"] = fingerprint(result)
    return result


def reviewed_evidence_payload(case: Mapping[str, Any], *, authority_version: str) -> dict[str, Any]:
    """Reproduce event eligibility before supplying evidence to the common writer."""
    import json

    decision = evaluate_form6k(case["quarter"], case["candidates"],
                              relations=case.get("relations", []), authority_version=authority_version)
    if decision["final_result"] != "UNIQUE":
        raise ValueError("FORM6K_REVIEWED_EVIDENCE_NOT_UNIQUE")
    candidate = next(c for c in case["candidates"]
                     if c["candidate_id"] == decision["selected_candidate_id"])
    quarter = case["quarter"]
    stable = {
        "company_id": quarter["company_id"], "fiscal_year": quarter["fiscal_year"],
        "fiscal_quarter": quarter["fiscal_quarter"], "quarter_id": quarter["quarter_id"],
        "source_type": SEC_FORM_6K_RESULT, "source_timestamp_utc": decision["selected_timestamp"],
        "accession_number": candidate["accession"], "filing_form": candidate["form"],
        "document_id": candidate["primary_document"], "source_reference": candidate["parent_url"],
        "security_id": quarter["security_id"], "rule_version": authority_version,
        "matching_method": json.dumps({"authority_version": authority_version, "source_rank": 2,
            "confidence": "MEDIUM", "decision_fingerprint": decision["decision_fingerprint"],
            "frozen_case": dict(case)}, sort_keys=True, separators=(",", ":")),
    }
    digest = fingerprint(stable)
    return {**stable, "evidence_hash": digest, "evidence_id": "rpe_" + digest[:24]}


def simulate_authority_state(
    state: Mapping[tuple[int, int, str], Mapping[str, Any]], cases: Sequence[Mapping[str, Any]], *,
    authority_version: str,
) -> tuple[dict[tuple[int, int, str], dict[str, Any]], list[dict[str, Any]]]:
    """In-memory state simulation only; never accepted as production writer input."""
    copied = deepcopy(dict(state))
    results = []
    seen = set()
    for case in cases:
        q = case["quarter"]; key = natural_key(q)
        if key in seen or key not in copied or copied[key].get("quarter_id") != q["quarter_id"]:
            raise ValueError("COPY_STATE_IDENTITY_DRIFT")
        seen.add(key)
        result = evaluate_form6k(q, case["candidates"], relations=case.get("relations", []),
                                authority_version=authority_version, existing_authority=copied[key])
        results.append(result)
        if result["final_result"] == "UNIQUE":
            copied[key] = {**copied[key], "status": "VERIFIED",
                           "result_publication_source": result["selected_source"],
                           "result_publication_timestamp_utc": result["selected_timestamp"],
                           "result_publication_confidence": result["confidence"],
                           "rule_version": authority_version,
                           "copy_only_decision": deepcopy(result)}
    return copied, results
