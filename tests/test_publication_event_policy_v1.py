from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest

from analysis.research.publication_event_policy_v1_replay import acceptance_gate, replay, replay_case
from rawcandle.fundamentals.publication_event_policy import (
    PUBLICATION_EVENT_POLICY_V1 as V1, EVENT_CLASSES, classify_event,
    evidence_binding, evaluate_candidates, fingerprint,
)
from rawcandle.fundamentals.result_publication import (
    SOURCE_RANK, SecFiling, SecResultExhibit, apply_resolution, normalize_utc_timestamp,
    resolve_sec_filings_detailed, resolve_sec_filings_with_event_policy,
)
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema


FIXTURE = Path(__file__).parent / "fixtures/publication_event_policy_v1.json"
BASELINE = json.loads(FIXTURE.read_text())
CASES = BASELINE["cases"]


def case(ticker="GME"):
    return deepcopy(next(row for row in CASES if row["ticker"] == ticker))


def evaluate(c, *, relations=True):
    return evaluate_candidates(
        c["quarter"], [e["evidence"] for e in c["events"]],
        observations={e["evidence"]["evidence_id"]: e["observation"] for e in c["events"]},
        relations=c["relations"] if relations else (), policy_version=V1,
    )


def rebind(c):
    for event in c["events"]:
        event["observation"]["evidence_binding"] = evidence_binding(event["evidence"])
    lookup = {e["evidence"]["evidence_id"]: e for e in c["events"]}
    for edge in c["relations"]:
        for side in ("from", "to"):
            edge[side+"_observation_fingerprint"] = fingerprint(
                lookup[edge[side+"_evidence_id"]]["observation"])


def filings(c):
    return [SecFiling(e["evidence"]["accession_number"], "8-K", "2.02",
                      e["evidence"]["source_timestamp_utc"], e["evidence"]["document_id"],
                      e["evidence"]["source_reference"], e["primary_excerpt"]) for e in c["events"]]


@pytest.mark.parametrize("c", CASES, ids=lambda c: c["ticker"])
def test_exact_26_case_replay_preserves_all_52_legacy_candidates(c):
    before = deepcopy(c)
    row = replay_case(c)
    assert row["original_candidate_count"] == 2
    assert c == before
    result = evaluate(c)
    assert result["retained_candidates"] == [e["evidence"] for e in c["events"]]
    # Legacy apply still rejects the competing timestamps, independently of V1.
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        ensure_result_publication_schema(db)
        assert apply_resolution(db, c["quarter"], result["retained_candidates"]) == "AMBIGUOUS"


def test_exact_partition_is_19_filtering_4_precedence_3_review():
    _, summary = replay()
    assert summary["quarters"] == 26 and summary["events"] == 52
    assert summary["filtering"] == {"UNIQUE": 19, "AMBIGUOUS": 4, "REVIEW": 3}
    assert summary["final"] == {"UNIQUE": 23, "REVIEW": 3}
    assert summary["eligibility"] == {"YES": 28, "NO": 20, "REVIEW": 4}
    assert summary["review_holdouts"] == ["ABAT", "OPTT", "AMR"]
    assert summary["discrepancy_events_reviewed"] == 10


@pytest.mark.parametrize("ticker", ["GME", "TE", "RDVT", "RXT"])
def test_preliminary_completion_needs_source_supported_typed_edge(ticker):
    c = case(ticker)
    result = evaluate(c)
    assert result["eligible_count"] == 2
    assert result["filtering_result"] == "AMBIGUOUS"
    assert result["selected_accession"] == c["events"][0]["evidence"]["accession_number"]
    assert result["selected_timestamp"] == c["events"][0]["evidence"]["source_timestamp_utc"]
    assert evaluate(c, relations=False)["final_result"] == "AMBIGUOUS"
    assert evaluate(c, relations=False)["selected_timestamp"] is None


@pytest.mark.parametrize("ticker", ["ABAT", "OPTT", "AMR"])
def test_review_competitor_blocks_unique(ticker):
    result = evaluate(case(ticker))
    assert result["final_result"] == "REVIEW"
    assert result["selected_timestamp"] is None
    assert any(a["eligibility"] == "REVIEW" for a in result["candidate_evaluations"])


@pytest.mark.parametrize("ticker", ["SMCI", "REKR", "KSCP", "CDXS", "GOSS", "ASTS", "PLUG",
                                         "APA", "DMLP", "PDYN", "RGLD", "SM", "BKD", "KLXE", "ARKO"])
def test_components_and_other_entity_do_not_donate_early_timestamp(ticker):
    c = case(ticker)
    result = evaluate(c)
    assert result["candidate_evaluations"][0]["eligibility"] == "NO"
    assert result["selected_timestamp"] == c["events"][1]["evidence"]["source_timestamp_utc"]


def test_event_unit_not_document_keyword_veto_and_pre_revenue_package():
    c = case("ANRO")
    result = evaluate(c)
    second = result["candidate_evaluations"][1]
    assert second["eligibility"] == "YES"
    assert second["observations"]["revenue_scope"] == "ABSENT"
    assert second["observations"]["pre_revenue_complete_expense_statement"]
    assert "pro forma" in " ".join(d["excerpt"] for d in second["observations"]["documents"]).lower()
    assert evaluate(case("MOVE"))["candidate_evaluations"][0]["eligibility"] == "YES"


@pytest.mark.parametrize("scope", ["ABSENT", "UNKNOWN", "SEGMENT"])
def test_preliminary_cannot_substitute_sector_metrics_for_revenue(scope):
    c = case()
    c["events"][0]["observation"]["revenue_scope"] = scope
    rebind(c)
    result = evaluate(c, relations=False)
    assert result["candidate_evaluations"][0]["eligibility"] == ("NO" if scope == "ABSENT" else "REVIEW")


def test_continuing_operations_requires_explicit_scope():
    c = case("TE")
    assert evaluate(c)["candidate_evaluations"][0]["eligibility"] == "YES"
    c["events"][0]["observation"]["continuing_operations_explicit"] = False
    rebind(c)
    assert evaluate(c, relations=False)["candidate_evaluations"][0]["eligibility"] == "NO"


@pytest.mark.parametrize("event_class", ["GUIDANCE_OR_EXPECTATION", "PRO_FORMA_OR_TRANSACTION_CONTEXT", "NON_RESULT_EVENT"])
def test_non_result_event_unit_not_numeric_substitution(event_class):
    c = case()
    c["events"][0]["observation"]["event_class"] = event_class
    rebind(c)
    assert evaluate(c, relations=False)["candidate_evaluations"][0]["eligibility"] == "NO"


@pytest.mark.parametrize("field,value", [
    ("period_grain", "HALF_YEAR"), ("period_grain", "ANNUAL"),
    ("entity_confidence", "UNCERTAIN"), ("period_confidence", "UNCERTAIN"),
    ("supporting_p_and_l", None), ("complete_earnings_package", False),
])
def test_uncertain_scope_is_review_not_exclusion(field, value):
    c = case()
    c["events"][1]["observation"][field] = value
    rebind(c)
    assert evaluate(c)["final_result"] == "REVIEW"


def test_known_wrong_period_excluded_without_cover_date_proof():
    c = case()
    c["events"][0]["observation"]["period_confidence"] = "OTHER_PERIOD"
    rebind(c)
    assert evaluate(c, relations=False)["candidate_evaluations"][0]["eligibility"] == "NO"


@pytest.mark.parametrize("change", ["entity", "period", "source", "time", "quote", "binding", "unproven"])
def test_relations_cannot_cross_scope_source_or_bind_different_evidence(change):
    c = case()
    event, edge = c["events"][1], c["relations"][0]
    if change == "entity":
        event["evidence"]["company_id"] += 1
    elif change == "period":
        event["observation"]["period_end"] = "2026-01-01"
    elif change == "source":
        event["evidence"]["source_type"] = "ISSUER_EARNINGS_RELEASE"
    elif change == "time":
        event["evidence"]["source_timestamp_utc"] = c["events"][0]["evidence"]["source_timestamp_utc"]
    elif change == "quote":
        edge["from_excerpt"] = "This assertion is not in the frozen source."
    elif change == "unproven":
        edge["same_economic_chain"] = False
    rebind(c)
    if change == "binding":
        edge["from_observation_fingerprint"] = "0" * 64
    result = evaluate(c)
    assert result["final_result"] == "REVIEW"
    assert result["selected_timestamp"] is None
    assert not result["relation_edges"][0]["valid"]


def test_independent_full_full_cannot_choose_earliest_or_latest():
    c = case()
    c["events"][0]["observation"].update(event_class="FULL_PERIOD_RESULTS", actual_vs_preliminary="ACTUAL",
                                          complete_earnings_package=True)
    rebind(c)
    assert evaluate(c, relations=False)["final_result"] == "AMBIGUOUS"
    c["events"].reverse()
    assert evaluate(c, relations=False)["final_result"] == "AMBIGUOUS"


def test_revision_retained_without_resetting_first_and_no_backdating_nonqualifying_initial():
    c = case()
    c["events"][1]["observation"]["event_class"] = "REVISED_OR_CORRECTED_RESULTS"
    c["relations"][0]["relation_type"] = "INITIAL_RESULT_TO_CORRECTION_OR_REVISION"
    rebind(c)
    assert evaluate(c)["selected_timestamp"] == c["events"][0]["evidence"]["source_timestamp_utc"]
    c["events"][0]["observation"]["net_result_scope"] = "ABSENT"
    rebind(c)
    assert evaluate(c)["selected_timestamp"] == c["events"][1]["evidence"]["source_timestamp_utc"]


def test_repeat_requires_relation_and_preserves_first_evidence():
    c = case("CF")
    assert evaluate(c, relations=False)["final_result"] == "REVIEW"
    result = evaluate(c)
    assert result["filtering_result"] == "UNIQUE"
    assert result["selected_timestamp"] == c["events"][0]["evidence"]["source_timestamp_utc"]
    assert result["candidate_evaluations"][1]["eligibility_reason"] == "PROVEN_SAME_RESULT_REPEAT"
    assert len(result["retained_candidates"]) == 2


def test_missing_or_tampered_observations_fail_closed():
    c = case()
    c["events"][0]["observation"] = {}
    assert evaluate(c)["final_result"] == "REVIEW"
    c = case()
    c["events"][0]["observation"]["documents"][0]["excerpt"] += " altered"
    rebind(c)
    assert evaluate(c)["final_result"] == "REVIEW"
    c = case()
    c["events"][0]["observation"]["documents"][0]["source_reference"] = c["events"][1]["evidence"]["source_reference"]
    rebind(c)
    assert evaluate(c)["final_result"] == "REVIEW"


@pytest.mark.parametrize("event", [e for c in CASES for e in c["events"] if e["acceptance_index_review"]],
                         ids=lambda e: e["evidence"]["accession_number"])
def test_all_ten_acceptance_discrepancies_retain_stored_boundary(event):
    before = deepcopy(event)
    assert acceptance_gate(event) == "ACCEPTANCE_SOURCE_DISCREPANCY_REVIEWED"
    assert event == before
    assert event["evidence"]["source_timestamp_utc"] != event["acceptance_index_review"]["submissions_utc"]
    broken = deepcopy(event)
    broken["acceptance_index_review"]["index_accepted_display"] = "2026-01-01 12:00:00"
    with pytest.raises(ValueError, match="NOT_CORROBORATED"):
        acceptance_gate(broken)


def test_default_source_rank_and_timestamp_contract_unchanged():
    assert SOURCE_RANK == {"ISSUER_EARNINGS_RELEASE":4, "SEC_8K_ITEM_2_02":3,
                           "SEC_FILING_FALLBACK":2, "MANUAL_REVIEW":1}
    assert normalize_utc_timestamp("2026-08-31T06:23:08-04:00") == "2026-08-31T10:23:08Z"
    with pytest.raises(ValueError):
        evaluate_candidates(case()["quarter"], [], observations={}, policy_version="unversioned")
    assert len(EVENT_CLASSES) == 11


def test_copy_universe_no_financial_identity_authority_or_unrelated_state_mutation():
    c = case()
    q = c["quarter"]
    unique = case("ANRO")
    unique["events"] = unique["events"][1:]
    c8 = {**q, "company_id": 99999, "quarter_id": 99999, "period_end":"2026-05-30"}
    not_found = {**q, "company_id": 99998, "quarter_id": 99998, "period_end":"2025-01-01"}
    key = (q["company_id"], q["fiscal_year"], q["fiscal_quarter"])
    authorities = {key:{"status":"VERIFIED", "result_publication_timestamp_utc":"2026-08-31T10:23:08Z"}}
    c8_filing = replace(filings(c)[0], text="Item 2.02 Results of Operations. Unclear period financial results.")
    universe = [q, unique["quarter"], c8, not_found]
    source_filings = [*filings(c), *filings(unique), c8_filing]
    observations = {e["evidence"]["evidence_id"]:e["observation"] for e in unique["events"]}
    before = deepcopy((universe, authorities, observations, source_filings))
    # Independent database state demonstrates the proposal function has no writer.
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE financial_identity_state(value TEXT)")
        db.execute("INSERT INTO financial_identity_state VALUES ('financial/identity/fiscal/source unchanged')")
        ensure_result_publication_schema(db)
        db.row_factory = sqlite3.Row
        apply_resolution(db, q, [c["events"][0]["evidence"]])
        apply_resolution(db, c8, [], unresolved=True)
        apply_resolution(db, not_found, [])
        dump = list(db.iterdump())
        result = resolve_sec_filings_with_event_policy(
            universe, source_filings, policy_version=V1, observations=observations, existing_authorities=authorities)
        assert list(db.iterdump()) == dump
    assert (universe, authorities, observations, source_filings) == before
    assert result["event_policy_evaluations"][key]["final_result"] == "SKIPPED_VERIFIED"
    assert result["event_policy_evaluations"][(99998,q["fiscal_year"],q["fiscal_quarter"])]["final_result"] == "NOT_FOUND"
    assert result["legacy_matches"] == resolve_sec_filings_detailed(universe, source_filings)[0]
    # An ordinary unique SEC event still resolves when invoked in its own
    # issuer context, as the production acquisition contract requires.
    ordinary = resolve_sec_filings_with_event_policy(
        [unique["quarter"]], filings(unique), policy_version=V1, observations=observations)
    ordinary_key = tuple(unique["quarter"][k] for k in ("company_id", "fiscal_year", "fiscal_quarter"))
    assert ordinary["event_policy_evaluations"][ordinary_key]["final_result"] == "UNIQUE"
    unresolved = resolve_sec_filings_with_event_policy([c8], [c8_filing], policy_version=V1, observations={})
    assert unresolved["legacy_unresolved"]
    assert unresolved["event_policy_evaluations"][(99999,q["fiscal_year"],q["fiscal_quarter"])]["final_result"] == "REVIEW"


def test_full_package_cannot_be_mislabeled_actual_from_preliminary_facts():
    c = case()
    c["events"][1]["observation"]["actual_vs_preliminary"] = "PRELIMINARY_COMPLETED_PERIOD"
    rebind(c)
    assert evaluate(c)["final_result"] == "REVIEW"


def test_divergent_chain_and_missing_predecessor_never_force_unique():
    c = case()
    third = deepcopy(c["events"][1])
    third["evidence"].update(evidence_id="synthetic_third", evidence_hash="f"*64,
                             accession_number="0001326380-26-000051",
                             source_timestamp_utc="2026-09-09T13:02:39Z")
    c["events"].append(third)
    second_edge = deepcopy(c["relations"][0])
    second_edge["to_evidence_id"] = "synthetic_third"
    c["relations"].append(second_edge)
    rebind(c)
    result = evaluate(c)
    assert all(edge["valid"] for edge in result["relation_edges"])
    assert result["final_result"] == "AMBIGUOUS"
    c["relations"][0]["from_evidence_id"] = "missing_predecessor"
    assert evaluate(c)["final_result"] == "REVIEW"


@pytest.mark.parametrize("change", ["primary", "exhibit"])
def test_stale_frozen_observation_cannot_follow_changed_resolver_context(change):
    c = case("ANRO")
    c["events"] = c["events"][1:]
    found = filings(c)
    if change == "primary":
        found[0] = replace(found[0], text=found[0].text + " Changed result context.")
    else:
        found[0] = replace(found[0], result_exhibits=(SecResultExhibit(
            found[0].source_reference.rsplit('/', 1)[0] + '/ex99-2.htm', "a"*64, "New context"),))
    key = tuple(c["quarter"][k] for k in ("company_id", "fiscal_year", "fiscal_quarter"))
    assert resolve_sec_filings_detailed([c["quarter"]], found)[0][key]
    result = resolve_sec_filings_with_event_policy(
        [c["quarter"]], found, policy_version=V1,
        observations={e["evidence"]["evidence_id"]:e["observation"] for e in c["events"]})
    assert result["event_policy_evaluations"][key]["final_result"] == "REVIEW"
