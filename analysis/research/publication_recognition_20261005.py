"""Pure 278-case recognition replay; optional bounded read-only SEC acquisition.

Inputs are the Phase 13G.3.64 temporary audit exports, never production writers.
Raw HTML cache and generated results must remain outside the repository.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rawcandle.fundamentals.result_publication import SecClient, resolve_sec_filings_detailed
from rawcandle.fundamentals.sec_result_context import (
    linked_result_exhibits, result_context, result_fiscal_tokens, result_periods, unsafe_new_event,
)

BASELINE = "8b6240730e31294c174ee59664c8831090906a19"
FINGERPRINT = "18d9bde0bb5bde1c332de3f5d03279002c9c11d041adef403c9c80f8618e1179"


def baseline_module():
    module = types.ModuleType("_sec_recognition_baseline")
    sys.modules[module.__name__] = module
    source = subprocess.check_output(
        ["git", "show", BASELINE + ":rawcandle/fundamentals/result_publication.py"], cwd=ROOT, text=True,
    )
    exec(compile(source, "pre_13g3_65_result_publication.py", "exec"), module.__dict__)
    return module


def identity(q):
    return f"{q['company_id']}:{q['fiscal_year']}:{q['fiscal_quarter']}"


def candidate_set(matches):
    return {(row["accession_number"], row["source_timestamp_utc"], row["source_type"])
            for rows in matches.values() for row in rows}


def metadata_for_case(case, external):
    metadata = [row for row in external["metadata"]
                if row["form"] == "8-K" and "2.02" in (row["items"] or "").split(",")]
    known = {row["url"] for row in metadata}
    for evidence in case["evidence"]:
        if evidence["source_type"] == "SEC_8K_ITEM_2_02" and evidence["source_reference"] not in known:
            metadata.append({"form": evidence["filing_form"], "items": "2.02",
                             "accession": evidence["accession_number"], "accepted": evidence["source_timestamp_utc"],
                             "url": evidence["source_reference"]})
    return metadata


def payload_for(metadata):
    return {"filings": {"recent": {
        "form": [row["form"] for row in metadata], "items": [row["items"] for row in metadata],
        "accessionNumber": [row["accession"] for row in metadata],
        "acceptanceDateTime": [row["accepted"] for row in metadata],
        "primaryDocument": [row["url"].rsplit("/", 1)[1] for row in metadata],
    }}}


def safety_hashes(local):
    return {key: hashlib.sha256(Path(value["path"]).read_bytes()).hexdigest()
            for key, value in local["safety_before"].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, default=Path("/tmp/publication_open_audit_local_20261005.json"))
    parser.add_argument("--external", type=Path, default=Path("/tmp/publication_open_external_20261005.json"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/publication_recognition_20261005_html.json"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/publication_recognition_20261005_impact.json"))
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    for target in (args.cache, args.output):
        if target.resolve().is_relative_to(ROOT):
            parser.error("Raw cache/generated output must be outside the repository")
    local = json.loads(args.local.read_text())
    external = json.loads(args.external.read_text())["cases"]
    with (ROOT / "docs/fundamentals_v4/fundamentals_v4_phase13g3_64_persistent_open_publication_cases.csv").open() as source:
        audit = {identity(row): row for row in csv.DictReader(source)}
    fingerprint = hashlib.sha256("\n".join(sorted(
        identity(case["quarter"]) + ":" + case["authority"]["status"] for case in local["cases"]
    )).encode()).hexdigest()
    assert len(audit) == len(local["cases"]) == 278 and fingerprint == FINGERPRINT
    before = safety_hashes(local)
    assert before == {key: value["sha256"] for key, value in local["safety_before"].items()}, "Audit production boundary changed"
    cache = json.loads(args.cache.read_text()) if args.cache.exists() else {}
    if args.download:
        client = SecClient(maximum_runtime_seconds=1200)
        for case in local["cases"]:
            key = identity(case["quarter"])
            for row in metadata_for_case(case, external[key]):
                url = row["url"]
                if url not in cache:
                    cache[url] = client._get_text(url)
                for exhibit_url in linked_result_exhibits(cache[url], url):
                    if exhibit_url not in cache:
                        cache[exhibit_url] = client._get_text(exhibit_url)
                args.cache.write_text(json.dumps(cache))
            print("CACHE", audit[key]["ticker"], len(cache), flush=True)
        print("READ_ONLY_REQUESTS", json.dumps(dict(client.stats)), flush=True)
    baseline = baseline_module()
    verified_document_hashes = 0
    for case in external.values():
        for document in case["documents"]:
            if document["url"] in cache and document.get("sha256"):
                assert hashlib.sha256(cache[document["url"]].encode()).hexdigest() == document["sha256"], document["url"]
                verified_document_hashes += 1
    rows = []
    for case in local["cases"]:
        q = case["quarter"]
        key = identity(q)
        metadata = metadata_for_case(case, external[key])
        payload = payload_for(metadata)
        cik = case["ciks"][0]["cik_normalized"]
        old = baseline.SecClient(fetch_json=lambda _: payload, fetch_text=cache.__getitem__, minimum_interval_seconds=0)
        new = SecClient(fetch_json=lambda _: payload, fetch_text=cache.__getitem__, minimum_interval_seconds=0)
        old_filings = old.item_2_02_filings(cik, from_calendar_year=int(q["period_end"][:4]))
        new_filings = new.item_2_02_filings(cik, from_calendar_year=int(q["period_end"][:4]))
        old_matches, _, _ = baseline.resolve_sec_filings_detailed([q], old_filings)
        new_matches, _, _ = resolve_sec_filings_detailed([q], new_filings)
        old_set, new_set = candidate_set(old_matches), candidate_set(new_matches)
        assert old_set <= new_set, (key, old_set - new_set)
        assert {row["evidence_hash"] for values in old_matches.values() for row in values} <= {
            row["evidence_hash"] for values in new_matches.values() for row in values
        }, "Legacy immutable evidence fingerprint changed: " + key
        durable_set = {(row["accession_number"], row["source_timestamp_utc"], row["source_type"]) for row in case["evidence"]}
        if audit[key]["root_cause_category"] == "TRUE_AMBIGUOUS_PUBLICATION":
            assert durable_set <= old_set <= new_set and len({row[1] for row in new_set}) > 1, key
        outcome = "uniquely_resolvable" if len(new_set) == 1 else "ambiguous" if len(new_set) > 1 else "unchanged"
        if new_set:
            note = "Existing ambiguity retained" if len(old_set) > 1 else "Bounded recognition supplies one parent candidate"
        elif not new_filings:
            note = "No eligible structurally recognized Item 2.02 8-K primary"
        elif any(unsafe_new_event(section) for filing in new_filings for section in filing.result_sections):
            note = "New-event safety gate blocks preliminary/partial or non-result context"
        elif not any(filing.result_exhibits for filing in new_filings):
            note = "No bounded linked results exhibit; primary context does not match safely"
        else:
            contexts = [context for filing in new_filings for exhibit in filing.result_exhibits
                        if (context := result_context(exhibit.text))]
            periods = {period for context in contexts for period in result_periods(context)}
            tokens = {token for context in contexts for token in result_fiscal_tokens(context)}
            note = ("Conflicting result-period/fiscal tokens; no unique context chosen"
                    if len(periods) > 1 or len(tokens) > 1 else
                    "Bounded text lacks a safely matching actual-result period/fiscal identity")
        rows.append({"identity": key, "ticker": audit[key]["ticker"], "category": audit[key]["root_cause_category"],
                     "cluster": audit[key]["cluster_id"], "old_status": case["authority"]["status"],
                     "old_candidates": sorted(old_set), "new_candidates": sorted(new_set), "outcome": outcome,
                     "new_matching_methods": [row["matching_method"] for values in new_matches.values() for row in values],
                     "candidate_added": bool(new_set - old_set), "candidate_lost": bool(old_set - new_set),
                     "coverage_note": note,
                     "documents": [{"url": metadata_row["url"], "sha256": hashlib.sha256(cache[metadata_row["url"]].encode()).hexdigest()}
                                   for metadata_row in metadata]})
    after = safety_hashes(local)
    assert before == after, "Production safety hashes changed"
    summary = {cluster: dict(Counter(row["outcome"] for row in rows if row["cluster"] == cluster))
               for cluster in ("EXHIBIT_QUARTER_CONTEXT", "ITEM202_HEADING_VARIANTS")}
    summary["c8_movement"] = [row["identity"] for row in rows if row["category"] == "INSUFFICIENT_EVIDENCE" and row["candidate_added"]]
    summary["true_ambiguity_collapsed"] = sum(row["outcome"] != "ambiguous" for row in rows if row["category"] == "TRUE_AMBIGUOUS_PUBLICATION")
    summary["lost_candidates"] = sum(row["candidate_lost"] for row in rows)
    summary["audit_document_hashes_verified"] = verified_document_hashes
    args.output.write_text(json.dumps({"baseline": BASELINE, "cohort_fingerprint": fingerprint,
                                     "summary": summary, "cases": rows, "safety_before": before, "safety_after": after}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
