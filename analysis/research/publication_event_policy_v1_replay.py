"""Offline read-only resolver replay; output is a proposal, not an apply plan."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from rawcandle.fundamentals.publication_event_policy import PUBLICATION_EVENT_POLICY_V1
from rawcandle.fundamentals.result_publication import (
    SecFiling, resolve_sec_filings_detailed, resolve_sec_filings_with_event_policy,
)
from rawcandle.fundamentals.sec_result_context import same_accession_document


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "tests/fixtures/publication_event_policy_v1.json"


def acceptance_gate(event):
    """Corroborate the stored boundary, never normalize/choose a replacement."""
    evidence, index = event["evidence"], event.get("acceptance_index_review")
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


def replay_case(case):
    quarter = case["quarter"]
    key = (quarter["company_id"], quarter["fiscal_year"], quarter["fiscal_quarter"])
    filings = [SecFiling(
        accession_number=e["evidence"]["accession_number"], form=e["evidence"]["filing_form"],
        items="2.02", acceptance_timestamp_utc=e["evidence"]["source_timestamp_utc"],
        primary_document=e["evidence"]["document_id"], source_reference=e["evidence"]["source_reference"],
        text=e["primary_excerpt"],
    ) for e in case["events"]]
    gates = [acceptance_gate(e) for e in case["events"]]
    legacy, unresolved, diagnostics = resolve_sec_filings_detailed([quarter], filings)
    original = {e["evidence"]["evidence_id"] for e in case["events"]}
    assert {e["evidence_id"] for e in legacy[key]} == original, "FROZEN_LEGACY_CANDIDATES_CHANGED"
    assert not unresolved
    proposal = resolve_sec_filings_with_event_policy(
        [quarter], filings, policy_version=PUBLICATION_EVENT_POLICY_V1,
        observations={e["evidence"]["evidence_id"]: e["observation"] for e in case["events"]},
        relations=case["relations"],
    )["event_policy_evaluations"][key]
    for assessment, event in zip(proposal["candidate_evaluations"], case["events"]):
        assert assessment["eligibility"] == event["expected_eligibility"], (
            case["ticker"], assessment["eligibility_reason"])
    assert diagnostics[key]["reason"] == "MULTIPLE_VALID_CANDIDATES"
    assert proposal["filtering_result"] == case["expected_filtering"], case["ticker"]
    assert proposal["final_result"] == case["expected_result"], case["ticker"]
    timestamps = [row["source_timestamp_utc"] for row in legacy[key]]
    return {
        "ticker": case["ticker"], "company_id": quarter["company_id"],
        "fiscal_year": quarter["fiscal_year"], "fiscal_quarter": quarter["fiscal_quarter"],
        "policy_version": PUBLICATION_EVENT_POLICY_V1,
        "legacy_result": "AMBIGUOUS", "legacy_selected_timestamp": None,
        "original_candidate_count": len(legacy[key]), "eligible_count": proposal["eligible_count"],
        "filtering_result": proposal["filtering_result"], "precedence_result": proposal["precedence_result"],
        "final_quarter_result": proposal["final_result"],
        "selected_accession": proposal["selected_accession"], "selected_timestamp": proposal["selected_timestamp"],
        "selected_first_event_reason": proposal["selected_first_event_reason"],
        "review_reason": proposal["review_reason"],
        "hypothetical_earliest_timestamp": min(timestamps),
        "hypothetical_latest_timestamp": max(timestamps),
        "differs_from_hypothetical_earliest": proposal["selected_timestamp"] != min(timestamps) if proposal["selected_timestamp"] else None,
        "differs_from_hypothetical_latest": proposal["selected_timestamp"] != max(timestamps) if proposal["selected_timestamp"] else None,
        "acceptance_gate": gates,
        "candidate_evaluations": proposal["candidate_evaluations"],
        "relation_edges": proposal["relation_edges"],
    }


def replay(fixture=DEFAULT_FIXTURE):
    frozen = json.loads(Path(fixture).read_text())
    rows = [replay_case(case) for case in frozen["cases"]]
    summary = {
        "policy_version": PUBLICATION_EVENT_POLICY_V1,
        "fixture_sha256": hashlib.sha256(Path(fixture).read_bytes()).hexdigest(),
        "quarters": len(rows), "events": sum(row["original_candidate_count"] for row in rows),
        "filtering": dict(Counter(row["filtering_result"] for row in rows)),
        "final": dict(Counter(row["final_quarter_result"] for row in rows)),
        "eligibility": dict(Counter(a["eligibility"] for row in rows for a in row["candidate_evaluations"])),
        "discrepancy_events_reviewed": sum(g == "ACCEPTANCE_SOURCE_DISCREPANCY_REVIEWED" for row in rows for g in row["acceptance_gate"]),
        "deterministic": [row["ticker"] for row in rows if row["final_quarter_result"] == "UNIQUE"],
        "review_holdouts": [row["ticker"] for row in rows if row["final_quarter_result"] == "REVIEW"],
        "authority_writes": 0, "network_requests": 0,
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    rows, summary = replay(args.fixture)
    if args.output_csv:
        compact_rows = []
        for row in rows:
            compact_row = dict(row)
            compact_row["candidate_evaluations"] = [{
                **{key: value for key, value in item.items() if key not in {"observations", "evidence"}},
                "accession": item["evidence"]["accession_number"],
                "acceptance_timestamp": item["evidence"]["source_timestamp_utc"],
            } for item in row["candidate_evaluations"]]
            compact_rows.append(compact_row)
        with args.output_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows({key: json.dumps(value, sort_keys=True, separators=(",", ":"))
                             if isinstance(value, (list, dict)) else value for key, value in row.items()}
                            for row in compact_rows)
    if args.output_json:
        args.output_json.write_text(json.dumps({"summary": summary, "cases": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
