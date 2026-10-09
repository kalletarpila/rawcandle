from copy import deepcopy
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals.publication_timestamp_equivalence import (
    compare_timestamp_representations, classify_timestamp_case,
)
from rawcandle.fundamentals.result_publication import SecFiling


@pytest.fixture
def event():
    accession = "0001234567-25-000001"
    reference = "https://www.sec.gov/Archives/edgar/data/1234567/000123456725000001/result.htm"
    evidence = dict(company_id=7, fiscal_year=2025, fiscal_quarter="Q2",
                    source_type="SEC_8K_ITEM_2_02", accession_number=accession,
                    source_reference=reference, document_id="result.htm",
                    filing_form="8-K", item_2_02_status="PRESENT_AND_DOCUMENT_CONFIRMED",
                    source_timestamp_utc="2025-08-02T00:00:00Z")
    parent = SecFiling(accession_number=accession, form="8-K", items="2.02,9.01",
                       acceptance_timestamp_utc=evidence["source_timestamp_utc"],
                       primary_document="result.htm", source_reference=reference,
                       text="Quarter ended June 30, 2025")
    quarters = [dict(company_id=7, fiscal_year=2025, fiscal_quarter="Q2", period_end="2025-06-30")]
    return evidence, parent, quarters


def compare(event, hours=4, **kwargs):
    current, parent, quarters = event
    stored = {**current, "source_timestamp_utc": (
        datetime.fromisoformat(current["source_timestamp_utc"].replace("Z", "+00:00"))
        - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")}
    return compare_timestamp_representations(stored, current, parent=parent, quarters=quarters, **kwargs)


@pytest.mark.parametrize("hours", [4, 5, -4, -5])
def test_exact_offsets_are_equivalent(event, hours):
    result = compare(event, hours)
    assert result["equivalent"]
    assert result["offset_seconds"] == hours * 3600


@pytest.mark.parametrize("hours", [3 + 59 / 60, 6])
def test_other_offsets_are_held(event, hours):
    assert not compare(event, hours)["equivalent"]


def test_different_accession_not_collapsed(event):
    current, parent, quarters = event
    stored = {**current, "accession_number": "0001234567-25-000002",
              "source_timestamp_utc": "2025-08-01T20:00:00Z"}
    assert not compare_timestamp_representations(stored, current, parent=parent, quarters=quarters)["same_parent"]


def test_parent_and_amendment_not_collapsed(event):
    current, parent, quarters = event
    amendment = {**current, "filing_form": "8-K/A"}
    assert not compare_timestamp_representations(amendment, current, parent=parent, quarters=quarters)["equivalent"]
    assert not compare((amendment, replace(parent, form="8-K/A"), quarters))["equivalent"]


def test_exhibit_context_retains_parent_identity(event):
    current, parent, quarters = event
    current = {**current, "matching_method": "CIK_ITEM_2_02_LINKED_EXHIBIT_EXACT_PERIOD_END"}
    assert compare((current, parent, quarters))["equivalent"]
    # An exhibit URL is context, not a second parent or a replacement identity.
    exhibit = {**current, "source_reference": parent.source_reference.replace("result.htm", "ex991.htm"),
               "document_id": "ex991.htm"}
    assert not compare((exhibit, parent, quarters))["equivalent"]


def test_identical_timestamp_unchanged(event):
    result = compare(event, 0)
    assert not result["equivalent"]
    assert result["reasons"] == ["IDENTICAL_TIMESTAMP_UNCHANGED"]
    assert result["stored_timestamp"] == result["current_timestamp"]


def test_timestamp_only_ambiguity_removed(event):
    result = compare(event)
    assert classify_timestamp_case([result]) == "TIMESTAMP_REPRESENTATION_ONLY"
    assert result["equivalent"]


def test_independent_context_stays_held(event):
    result = compare(event, independent_conflicts=["DISTINCT_PARENT_ACCESSIONS", "UNRESOLVED_COMPETING_CONTEXT"])
    assert result["representation_match"] and not result["equivalent"]
    assert classify_timestamp_case([result]) == "TIMESTAMP_PLUS_INDEPENDENT_AMBIGUITY"


@pytest.mark.parametrize("blocker", ["REVIEWED_EXCLUDED", "REVIEWED_PRECEDENCE_SELECTS_DIFFERENT_EVENT"])
def test_reviewed_decision_remains_authoritative(event, blocker):
    result = compare(event, reviewed_blockers=[blocker])
    assert not result["equivalent"]
    assert blocker in result["reasons"]


def test_date_boundary_without_eligibility_change_is_nonmaterial(event):
    result = compare(event)
    assert result["utc_date_boundary"]
    assert not result["eligibility_changed"]
    assert result["equivalent"]


@pytest.mark.parametrize("period_end", ["2025-08-02", "2025-02-02"])
def test_real_date_eligibility_change_stays_held(event, period_end):
    current, parent, quarters = event
    quarters = [{**quarters[0], "period_end": period_end}]
    result = compare((current, parent, quarters))
    assert result["eligibility_changed"]
    assert not result["equivalent"]


def test_no_timestamp_or_authority_mutation(event, tmp_path):
    before = deepcopy(event)
    db_path = tmp_path / "authority.db"
    with sqlite3.connect(db_path) as db:
        db.execute("create table authority (status text, timestamp text)")
        db.execute("insert into authority values ('AMBIGUOUS', ?)", (event[0]["source_timestamp_utc"],))
    db_before = db_path.read_bytes()
    compare(event)
    assert event == before
    assert db_path.read_bytes() == db_before


def test_deterministic_comparison(event):
    assert compare(event) == compare(event)


@pytest.mark.parametrize("field,value", [("source_type", "ISSUER_EARNINGS_RELEASE"), ("company_id", 8), ("document_id", "other.htm")])
def test_event_identity_fail_closed(event, field, value):
    current, parent, quarters = event
    current = {**current, field: value}
    assert not compare((current, parent, quarters))["equivalent"]


def test_original_599_artifact_stability_and_held_population():
    docs = Path(__file__).resolve().parents[1] / "docs/fundamentals_v4"
    with (docs / "fundamentals_v4_historical_publication_completeness_audit.csv").open() as f:
        original = list(csv.DictReader(f))
    with (docs / "fundamentals_v4_historical_publication_candidates_after_timestamp_equivalence.csv").open() as f:
        candidates = list(csv.DictReader(f))
    key = lambda r: (r["company_id"], r["fiscal_year"], r["fiscal_quarter"])
    baseline = {key(r): r for r in original if r["primary_classification"] == "CURRENT_RESOLVER_CAN_SOLVE"}
    assert len(candidates) == len(baseline) == 599
    assert {key(r) for r in candidates} == set(baseline)
    for c in candidates:
        b = baseline[key(c)]
        e, = json.loads(b["current_candidate_inventory"])
        assert c["selected_accession"] == b["selected_accession"] == e["accession_number"]
        assert c["selected_timestamp"] == b["event_document_timestamp_utc"] == e["source_timestamp_utc"]
        assert c["selected_evidence_hash"] == e["evidence_hash"]
        assert c["current_quarter_id"] == b["quarter_id"]
        assert c["competing_context_status"] == "NONE"
    with (docs / "fundamentals_v4_publication_timestamp_equivalence_cases.csv").open() as f:
        held = list(csv.DictReader(f))
    assert len(held) == 264
    assert {r["classification"] for r in held} == {"TIMESTAMP_PLUS_INDEPENDENT_AMBIGUITY"}
    assert all(int(r["distinct_parent_accession_count"]) > 1 for r in held)
    assert {r["historical_classification_after"] for r in held} == {"LEGACY_AMBIGUITY"}
