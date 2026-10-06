"""Offline copy-state replay. Produces proposals, never reviewed APPLY plans."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from rawcandle.fundamentals.form6k_authority import (
    FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 as V1, natural_key, simulate_authority_state,
)
from rawcandle.fundamentals.publication_event_policy import fingerprint

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/form6k_authority_v1.json"


def load_fixture(path=DEFAULT_FIXTURE):
    frozen = json.loads(Path(path).read_text())
    binding = frozen.pop("fixture_fingerprint")
    if frozen.get("fixture_version") != "FORM6K_REVIEWED_COHORT_V1" or binding != fingerprint(frozen):
        raise ValueError("INVALID_FROZEN_FORM6K_FIXTURE")
    return frozen


def replay(path=DEFAULT_FIXTURE):
    frozen = load_fixture(path)
    cases = frozen["cases"]
    state = {natural_key(c["quarter"]): c["current_authority"] for c in cases}
    copied, results = simulate_authority_state(state, cases, authority_version=V1)
    rows = []
    for case, result in zip(cases, results):
        if result["final_result"] != case["expected_result"]:
            raise ValueError("FORM6K_COHORT_OUTCOME_DRIFT:" + case["ticker"])
        if result["selected_timestamp"] != case["expected_timestamp"]:
            raise ValueError("FORM6K_COHORT_TIMESTAMP_DRIFT:" + case["ticker"])
        assessments = result["candidate_evaluations"]
        identity = assessments[0]["candidate"]["identity"]
        key = natural_key(case["quarter"])
        assert (copied[key] != state[key]) == (result["final_result"] == "UNIQUE")
        rows.append({
            "ticker": case["ticker"], "company_id": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2],
            "current_status": case["current_status"], "current_60d_scope": case["current_60d_scope"],
            "authority_version": V1, "source_type": result["contract"]["source_type"], "source_rank": result["source_rank"],
            "security_type_reviewed": identity["official_security_type"], "is_adr_or_ads": identity["is_adr_or_ads"],
            "underlying_issuer": identity["underlying_issuer"], "sec_cik": case["quarter"]["sec_cik"],
            "identity_result": ";".join(sorted({a["identity_result"] for a in assessments})),
            "provider_security_type_conflict": any(a["provider_security_type_conflict"] for a in assessments),
            "candidate_6k_count": len(assessments),
            "event_result": ";".join(a["candidate"]["event"]["event_class"] for a in assessments),
            "authority_v1_result": result["final_result"], "selected_accession": result["selected_accession"],
            "selected_timestamp": result["selected_timestamp"],
            "timestamp_conflict": any(a["acceptance_result"]["status"] == "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT" for a in assessments),
            "acceptance_results": ";".join(a["acceptance_result"]["status"] for a in assessments),
            "relation_result": "PROVEN_XBRL_SUPPLEMENT_ONLY" if result["relation_results"] else "NO_REVIEWED_RELATION",
            "review_reason": (";".join(sorted({a["reason"] for a in assessments if a["eligibility"] in {"REVIEW", "RELATED_REVIEW", "TIMESTAMP_REVIEW"}})) or result["reason"]) if result["final_result"] != "UNIQUE" else "",
            "independent_issuer_candidate": bool(case.get("independent_issuer_evidence")),
            "independent_issuer_timestamp": (case.get("independent_issuer_evidence") or {}).get("timestamp_utc"),
            "copy_simulation_result": "VERIFIED_COPY_ONLY" if result["final_result"] == "UNIQUE" else "HELD_UNCHANGED",
            "production_ready": False, "decision_fingerprint": result["decision_fingerprint"],
        })
    summary = {
        "contract_version": V1, "quarters": len(rows), "candidates": sum(r["candidate_6k_count"] for r in rows),
        "partition": dict(Counter(r["authority_v1_result"] for r in rows)),
        "deterministic": [r["ticker"] for r in rows if r["authority_v1_result"] == "UNIQUE"],
        "actual_adr_cases": sum(r["is_adr_or_ads"] for r in rows),
        "provider_security_type_conflicts": sum(r["provider_security_type_conflict"] for r in rows),
        "authority_changes_copy_only": sum(copied[k] != state[k] for k in state),
        "network_requests": 0, "production_writes": 0,
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-csv", type=Path)
    args = parser.parse_args()
    rows, summary = replay(args.fixture)
    if args.output_csv:
        with args.output_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
