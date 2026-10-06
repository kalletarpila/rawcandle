from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from analysis.research.form6k_authority_v1_replay import load_fixture, replay
from rawcandle.fundamentals.form6k_authority import (
    FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 as V1, SEC_FORM_6K_RESULT,
    FORM6K_SOURCE_RANK, acceptance_gate, candidate_binding,
    evaluate_form6k, natural_key, simulate_authority_state,
)
from rawcandle.fundamentals.result_publication import SOURCE_RANK, apply_resolution
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema

CASES = load_fixture()["cases"]


def case(ticker="WDH"):
    return deepcopy(next(c for c in CASES if c["ticker"] == ticker))


def bind(c):
    for candidate in c["candidates"]:
        candidate["reviewed_binding"] = candidate_binding(candidate)
    lookup = {candidate["candidate_id"]: candidate for candidate in c["candidates"]}
    for edge in c["relations"]:
        for side in ("from", "to"):
            edge[side + "_candidate_fingerprint"] = candidate_binding(lookup[edge[side + "_candidate_id"]])


def evaluate(c, **kwargs):
    return evaluate_form6k(c["quarter"], c["candidates"], relations=c["relations"], authority_version=V1, **kwargs)


def second(c, event_class="FULL_PERIOD_RESULTS", form="6-K"):
    original = c["candidates"][0]
    target = deepcopy(original)
    old = target["accession"]
    new = old[:-6] + "900001"
    target.update(accession=new, candidate_id=new, form=form)
    target["parent_url"] = target["parent_url"].replace(old.replace("-", ""), new.replace("-", ""))
    for doc in target["documents"]:
        doc["source_reference"] = doc["source_reference"].replace(old.replace("-", ""), new.replace("-", ""))
    target["linked_exhibits"] = []
    target["event"]["result_document_urls"] = [u.replace(old.replace("-", ""), new.replace("-", "")) for u in target["event"]["result_document_urls"]]
    target["event"]["event_class"] = event_class
    target["event"]["actual_vs_preliminary"] = "ACTUAL"
    a = target["acceptance"]
    a.update(accession=new, submissions_utc="2026-09-09T11:30:46Z", index_accepted_display="2026-09-09 07:30:46", prior_observations=[])
    a["index_url"] = a["index_url"].replace(old.replace("-", ""), new.replace("-", "")).replace(old, new)
    for key in list(a):
        if key.startswith("full_submission"):
            del a[key]
    c["candidates"].append(target)
    bind(c)
    return original, target


def relation(c, kind):
    source, target = c["candidates"][:2]
    c["relations"] = [{
        "relation_type": kind, "from_candidate_id": source["candidate_id"], "to_candidate_id": target["candidate_id"],
        "same_economic_chain": True, "review_reference": "SYNTHETIC_REVIEWED_RELATION_FIXTURE",
        "relation_reason": "Explicit reviewed economic-chain attribution, not chronology or equal metrics.",
        "documents": [source["documents"][0], target["documents"][0]],
    }]
    bind(c)


@pytest.mark.parametrize("frozen", CASES, ids=lambda c: c["ticker"])
def test_exact_frozen_cases(frozen):
    before = deepcopy(frozen)
    result = evaluate(frozen)
    assert result["final_result"] == frozen["expected_result"]
    assert result["selected_timestamp"] == frozen["expected_timestamp"]
    assert frozen == before
    assert [r["candidate"] for r in result["candidate_evaluations"]] == frozen["candidates"]
    assert result["contract"]["version"] == V1
    if result["final_result"] == "UNIQUE":
        assert result["selected_source"] == SEC_FORM_6K_RESULT
        assert result["source_rank"] == 2 and result["confidence"] == "MEDIUM"


def test_exact_partition_and_copy_only_replay():
    rows, summary = replay()
    assert summary["quarters"] == 23 and summary["candidates"] == 30
    assert summary["partition"] == {"UNIQUE": 9, "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT": 2,
                                    "MULTIPLE_COMPETING_EVENTS": 6, "WRONG_PERIOD": 5, "IDENTITY_TEMPORAL_REVIEW": 1}
    assert summary["actual_adr_cases"] == 11 and summary["provider_security_type_conflicts"] == 10
    assert summary["authority_changes_copy_only"] == 9
    assert summary["network_requests"] == summary["production_writes"] == 0
    assert sum(row["copy_simulation_result"] == "HELD_UNCHANGED" for row in rows) == 14


def test_rank_and_version_do_not_change_default_production_semantics():
    assert SOURCE_RANK == {"ISSUER_EARNINGS_RELEASE": 4, "SEC_8K_ITEM_2_02": 3, "SEC_FILING_FALLBACK": 2, "MANUAL_REVIEW": 1}
    assert SEC_FORM_6K_RESULT not in SOURCE_RANK and FORM6K_SOURCE_RANK == 2
    c = case()
    with pytest.raises(ValueError, match="UNSUPPORTED_FORM6K_AUTHORITY"):
        evaluate_form6k(c["quarter"], c["candidates"], authority_version="PUBLICATION_EVENT_POLICY_V1")
    # The ordinary schema/writer remains unable to persist this new source.
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        ensure_result_publication_schema(db)
        evidence = {"evidence_id": "x", "quarter_id": 1, "company_id": 1, "fiscal_year": 2026,
                    "fiscal_quarter": "Q2", "source_type": SEC_FORM_6K_RESULT, "source_timestamp_utc": "2026-08-01T12:00:00Z",
                    "source_reference": "https://example.invalid", "matching_method": "COPY_ONLY", "rule_version": V1, "evidence_hash": "x"}
        assert apply_resolution(db, evidence, [evidence]) == "NOT_FOUND"
        assert db.execute("SELECT count(*) FROM v4_result_publication_evidence").fetchone()[0] == 0
        assert db.execute("SELECT result_publication_timestamp_utc FROM v4_result_publication_authority").fetchone()[0] is None


@pytest.mark.parametrize("ticker", ["CAMT", "NVMI", "WDH", "PAAS", "WPM", "CAN"])
def test_primary_exhibit_multi_document_and_framework_support(ticker):
    c = case(ticker); result = evaluate(c)
    assert result["final_result"] == "UNIQUE"
    assert result["selected_timestamp"] == c["expected_timestamp"]
    if ticker in {"CAMT", "NVMI"}:
        assert c["candidates"][0]["event"]["result_document_urls"] == [c["candidates"][0]["parent_url"]]
    if ticker == "PAAS":
        assert len(c["candidates"][0]["event"]["result_document_urls"]) > 1


def test_unrelated_exhibit_cannot_supply_result_proof():
    c = case("VNET"); candidate = c["candidates"][0]
    unrelated = next(d for d in candidate["linked_exhibits"] if not d["result_bearing"])
    candidate["event"]["result_document_urls"] = [unrelated["url"]]
    bind(c)
    assert evaluate(c)["final_result"] == "REVIEW"


@pytest.mark.parametrize("ticker", ["MKDW", "MLGO", "HOLO", "SCNI", "BHP"])
def test_h1_is_not_q2_and_fy_is_not_q4(ticker):
    result = evaluate(case(ticker))
    assert result["final_result"] == "WRONG_PERIOD" and result["selected_timestamp"] is None


@pytest.mark.parametrize("field,value", [
    ("revenue_scope", "SEGMENT"), ("revenue_scope", "PRODUCTION_VOLUME"), ("net_scope", "ADJUSTED_EBITDA"),
    ("net_scope", "CASH_BALANCE"), ("supporting_statement", False), ("derived_arithmetic", True),
    ("period_grain", "UNKNOWN"), ("accounting_framework", "UNKNOWN"), ("complete_package", False),
    ("event_class", "PARTIAL_RESULTS"), ("event_class", "PRO_FORMA_OR_TRANSACTION_CONTEXT"),
    ("event_class", "NON_RESULT_EVENT"), ("event_class", "GUIDANCE_OR_EXPECTATION"),
])
def test_minimum_and_negative_event_scope(field, value):
    c = case(); c["candidates"][0]["event"][field] = value; bind(c)
    result = evaluate(c)
    assert result["selected_timestamp"] is None and result["final_result"] != "UNIQUE"


@pytest.mark.parametrize("framework,net", [("GAAP", "STATUTORY_CONSOLIDATED"), ("IFRS", "STATUTORY_ATTRIBUTABLE"),
                                          ("TIFRS", "STATUTORY_CONSOLIDATED"), ("GAAP", "STATUTORY_CONTINUING_OPERATIONS")])
def test_statutory_framework_and_income_perimeter(framework, net):
    c = case(); c["candidates"][0]["event"].update(accounting_framework=framework, net_scope=net); bind(c)
    assert evaluate(c)["final_result"] == "UNIQUE"
    c["candidates"][0]["event"]["income_perimeter_reference"] = ""; bind(c)
    assert evaluate(c)["final_result"] == "REVIEW"


@pytest.mark.parametrize("ticker", ["BABA", "BIDU"])
def test_acceptance_conflict_no_blanket_offset_or_prior_override(ticker):
    c = case(ticker); candidate = c["candidates"][0]
    gate = acceptance_gate(candidate)
    assert gate["status"] == "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT" and gate["selected_timestamp"] is None
    assert candidate["acceptance"]["full_submission_header"]
    assert evaluate(c)["selected_timestamp"] is None


def test_iqmx_issuer_time_does_not_repair_sec_or_temporal_identity():
    c = case("IQMX"); result = evaluate(c)
    assert result["final_result"] == "IDENTITY_TEMPORAL_REVIEW" and result["selected_timestamp"] is None
    assert result["candidate_evaluations"][0]["acceptance_result"]["status"] == "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT"
    assert c["independent_issuer_evidence"]["source_type"] == "ISSUER_EARNINGS_RELEASE"
    assert c["independent_issuer_evidence"]["reviewed_handoff"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize("field,value", [("submissions_utc", "2026-09-08"), ("index_timezone", "UTC"),
                                        ("index_accepted_display", "2026-09-08"), ("submissions_utc", "2026-09-08T07:30:46"),
                                        ("submissions_utc", "2026-09-08T15:30:46Z"), ("index_sha256", "bad")])
def test_timestamp_fields_fail_closed(field, value):
    c = case(); c["candidates"][0]["acceptance"][field] = value; bind(c)
    assert evaluate(c)["selected_timestamp"] is None


def test_provider_filing_exhibit_and_issuer_dates_cannot_replace_acceptance():
    c = case(); candidate = c["candidates"][0]
    for field in ("provider_date", "exhibit_timestamp", "filing_date", "issuer_timestamp"):
        candidate[field] = "2026-09-01T00:00:00Z"
    bind(c)
    assert evaluate(c)["selected_timestamp"] == c["expected_timestamp"]
    candidate["acceptance"].pop("submissions_utc"); bind(c)
    assert evaluate(c)["selected_timestamp"] is None


@pytest.mark.parametrize("ticker", ["WDH", "NEGG", "SCNI", "CAMT"])
def test_official_identity_wins_over_provider_type_without_mutation(ticker):
    c = case(ticker); before = deepcopy(c); result = evaluate(c)
    assert c == before
    assert result["candidate_evaluations"][0]["identity_result"] == "PROVEN_OFFICIAL_IDENTITY_CHAIN"
    assert result["candidate_evaluations"][0]["provider_security_type_conflict"] == (ticker in {"NEGG", "SCNI", "CAMT"})


@pytest.mark.parametrize("field,value,reason", [
    ("filer_role", "DEPOSITARY_BANK", "WRONG_ENTITY"), ("filer_role", "ADR_PROGRAM", "WRONG_ENTITY"),
    ("filer_role", "OTHER_ENTITY", "WRONG_ENTITY"), ("perimeter_match", "OTHER_PERIMETER", "WRONG_ENTITY"),
    ("underlying_match", "UNCERTAIN", "REVIEW_IDENTITY_CHAIN"), ("underlying_company_id", 1234567, "REVIEW_IDENTITY_CHAIN"),
    ("temporal_match", "UNCERTAIN", "IDENTITY_TEMPORAL_REVIEW"), ("valid_from", "2026-09-10", "IDENTITY_TEMPORAL_REVIEW"),
    ("valid_to", "2026-07-01", "IDENTITY_TEMPORAL_REVIEW"),
])
def test_identity_failures_same_name_cik_cannot_override_perimeter(field, value, reason):
    c = case(); c["candidates"][0]["identity"][field] = value; bind(c)
    result = evaluate(c)
    assert result["selected_timestamp"] is None
    assert result["candidate_evaluations"][0]["identity_result"] == reason


@pytest.mark.parametrize("source", ["SEC_8K_ITEM_2_02", "SEC_FILING_FALLBACK", "ISSUER_EARNINGS_RELEASE"])
def test_no_alias_or_arbitrary_fallback_source_authorization(source):
    c = case(); c["candidates"][0]["source_type"] = source; bind(c)
    assert evaluate(c)["final_result"] == "REVIEW"


@pytest.mark.parametrize("source", ["ISSUER_EARNINGS_RELEASE", "SEC_8K_ITEM_2_02"])
def test_existing_stronger_source_preserved(source):
    c = case(); authority = {**c["current_authority"], "status": "VERIFIED", "result_publication_source": source,
                            "result_publication_timestamp_utc": "2026-09-07T12:00:00Z"}
    result = evaluate(c, existing_authority=authority)
    assert result["final_result"] == "PRESERVED_HIGHER_PRIORITY_AUTHORITY"
    assert result["preserved_authority"] == authority and result["selected_timestamp"] is None


def test_equal_rank_mixed_source_conflict():
    c = case(); authority = {**c["current_authority"], "status": "VERIFIED", "result_publication_source": "SEC_FILING_FALLBACK",
                            "result_publication_timestamp_utc": "2026-09-07T12:00:00Z"}
    result = evaluate(c, existing_authority=authority)
    assert result["final_result"] == "REVIEW" and result["selected_timestamp"] is None


@pytest.mark.parametrize("ticker", ["TSEM", "TSM", "POET", "GDS", "NBIS", "CLLS"])
def test_cohort_multi_filing_never_uses_chronology_or_equal_values(ticker):
    c = case(ticker)
    assert evaluate(c)["final_result"] == "MULTIPLE_COMPETING_EVENTS"
    c["candidates"].reverse()
    assert evaluate(c)["selected_timestamp"] is None


@pytest.mark.parametrize("kind,event_class,form", [
    ("RESULT_TO_SAME_RESULT_REPEAT", "DUPLICATE_OR_REPEAT_PUBLICATION", "6-K"),
    ("RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION", "FULL_PERIOD_RESULTS", "6-K"),
    ("INITIAL_RESULT_TO_REVISION", "REVISED_OR_CORRECTED_RESULTS", "6-K/A"),
    ("RESULT_TO_XBRL_ONLY_SUPPLEMENT", "SUPPLEMENTAL_RESULT_INFORMATION", "6-K/A"),
    ("PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT", "FULL_PERIOD_RESULTS", "6-K"),
])
def test_proven_typed_chains_select_first_eligible_event(kind, event_class, form):
    c = case(); source, target = second(c, event_class, form)
    if kind == "PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT":
        source["event"].update(event_class="PRELIMINARY_RESULTS", actual_vs_preliminary="PRELIMINARY_COMPLETED_PERIOD")
    if form == "6-K/A":
        target["amendment_role"] = "XBRL_ONLY_SUPPLEMENT" if kind == "RESULT_TO_XBRL_ONLY_SUPPLEMENT" else "CONTENT_REVISION"
    relation(c, kind)
    result = evaluate(c)
    assert result["relation_results"][0]["valid"]
    assert result["final_result"] == "UNIQUE" and result["selected_accession"] == source["accession"]
    assert result["selected_timestamp"] == c["expected_timestamp"]
    assert target["acceptance"]["submissions_utc"] != result["selected_timestamp"]
    c["relations"] = []
    assert evaluate(c)["selected_timestamp"] is None


def test_first_substantive_amendment_requires_explicit_reviewed_role():
    c = case(); target = c["candidates"][0]; target["form"] = "6-K/A"; bind(c)
    assert evaluate(c)["selected_timestamp"] is None
    target["amendment_role"] = "FIRST_SUBSTANTIVE_RESULT"; bind(c)
    assert evaluate(c)["final_result"] == "UNIQUE"


def test_filtered_initial_cannot_donate_time_to_revision():
    c = case(); source, target = second(c, "REVISED_OR_CORRECTED_RESULTS", "6-K/A")
    source["event"]["event_class"] = "PARTIAL_RESULTS"; target["amendment_role"] = "CONTENT_REVISION"
    relation(c, "INITIAL_RESULT_TO_REVISION")
    result = evaluate(c)
    assert result["final_result"] == "UNIQUE"
    assert result["selected_timestamp"] == target["acceptance"]["submissions_utc"]


def test_clls_xbrl_only_amendment_does_not_add_or_reset_event():
    c = case("CLLS"); result = evaluate(c)
    assert len(c["candidates"]) == 3 and result["relation_results"][0]["valid"]
    assert result["candidate_evaluations"][-1]["eligibility"] == "NO"
    assert result["final_result"] == "MULTIPLE_COMPETING_EVENTS" and result["selected_timestamp"] is None


@pytest.mark.parametrize("field,value", [("same_economic_chain", False), ("relation_type", "EARLIEST_WINS"),
                                        ("to_candidate_fingerprint", "bad"), ("relation_reason", ""), ("documents", [])])
def test_invalid_relationship_fails_closed(field, value):
    c = case(); second(c, "DUPLICATE_OR_REPEAT_PUBLICATION"); relation(c, "RESULT_TO_SAME_RESULT_REPEAT")
    c["relations"][0][field] = value
    assert evaluate(c)["final_result"] == "REVIEW"


def test_copy_simulation_changes_only_nine_authorities_no_financial_state():
    state = {natural_key(c["quarter"]): deepcopy(c["current_authority"]) for c in CASES}
    outside = (999999, 2026, "Q1")
    state[outside] = {"company_id": 999999, "fiscal_year": 2026, "fiscal_quarter": "Q1", "status": "VERIFIED"}
    financial = {"quarter_values": [{"company_id": 1, "revenue": 123, "net_income": 45}], "identity": {"untouched": True}}
    before = deepcopy((state, financial, CASES))
    copied, results = simulate_authority_state(state, CASES, authority_version=V1)
    assert (state, financial, CASES) == before and copied[outside] == state[outside]
    changed = {k for k in state if copied[k] != state[k]}
    assert changed == {natural_key(c["quarter"]) for c in CASES if c["expected_result"] == "UNIQUE"}
    assert len(changed) == 9
    for c, result in zip(CASES, results):
        if result["final_result"] != "UNIQUE":
            assert copied[natural_key(c["quarter"])] == state[natural_key(c["quarter"])]
    with pytest.raises(ValueError, match="COPY_STATE_IDENTITY_DRIFT"):
        simulate_authority_state(state, [CASES[0], CASES[0]], authority_version=V1)


def test_unreviewed_or_tampered_frozen_evidence_fails_closed():
    c = case(); c["candidates"][0]["event"]["net_scope"] = "STATUTORY_CONSOLIDATED"
    assert evaluate(c)["final_result"] == "REVIEW"
    c = case(); c["candidates"][0]["documents"][0]["excerpt"] += " tampered"; bind(c)
    assert evaluate(c)["final_result"] == "REVIEW"
    c = case(); c["candidates"][0]["identity"]["documents"] = []; bind(c)
    assert evaluate(c)["selected_timestamp"] is None


def test_fixture_exactly_matches_phase76_natural_keys_and_csv_boundary():
    import csv
    path = Path(__file__).resolve().parents[1] / "docs/fundamentals_v4/fundamentals_v4_phase13g3_76_foreign_6k_c8_cases.csv"
    baseline = list(csv.DictReader(path.open()))
    frozen = load_fixture()
    assert sha256(path.read_bytes()).hexdigest() == frozen["source_csv_sha256"]
    assert {natural_key(c["quarter"]) for c in CASES} == {natural_key(r) for r in baseline}


def test_cross_accession_document_and_missing_minimum_proof_fail_closed():
    c = case(); candidate = c["candidates"][0]
    candidate["documents"][0]["source_reference"] = candidate["parent_url"].replace("105667", "900001")
    bind(c)
    assert evaluate(c)["selected_timestamp"] is None
    c = case(); c["candidates"][0]["identity"]["documents"][0]["source_sha256"] = "bad"; bind(c)
    assert evaluate(c)["selected_timestamp"] is None
    c = case(); c["quarter"]["quarter_id"] += 1
    assert evaluate(c)["selected_timestamp"] is None


def test_same_day_equal_numbers_are_not_relationship_evidence():
    c = case(); source, target = second(c)
    target["acceptance"] = deepcopy(source["acceptance"])
    target["acceptance"]["accession"] = target["accession"]
    target["acceptance"]["index_url"] = target["parent_url"].rsplit("/", 1)[0] + "/" + target["accession"] + "-index.html"
    target["acceptance"]["prior_observations"] = []
    bind(c)
    assert evaluate(c)["final_result"] == "MULTIPLE_COMPETING_EVENTS"
    assert evaluate(c)["selected_timestamp"] is None


def test_duplicate_input_and_divergent_chain_are_not_unique():
    c = case(); c["candidates"].append(deepcopy(c["candidates"][0]))
    assert evaluate(c)["final_result"] == "REVIEW"
    c = case(); second(c); relation(c, "RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION")
    c["relations"].append(deepcopy(c["relations"][0]))
    assert evaluate(c)["final_result"] == "MULTIPLE_COMPETING_EVENTS"


def test_full_submission_header_mismatch_is_not_ignored():
    c = case(); candidate = c["candidates"][0]; a = candidate["acceptance"]
    a.update(full_submission_header="20260908083046", full_submission_url=candidate["parent_url"].rsplit("/", 1)[0] + "/" + candidate["accession"] + ".txt",
             full_submission_sha256="0" * 64)
    bind(c)
    assert evaluate(c)["final_result"] == "REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT"


def test_dst_wall_time_uncertainty_needs_review_not_fold_guessing():
    c = case(); c["candidates"][0]["acceptance"].update(index_accepted_display="2026-11-01 01:30:00", submissions_utc="2026-11-01T05:30:00Z")
    bind(c)
    assert evaluate(c)["selected_timestamp"] is None


def test_invalid_existing_authority_cannot_be_silently_replaced():
    c = case(); authority = {**c["current_authority"], "status": "VERIFIED", "result_publication_source": "UNKNOWN",
                            "result_publication_timestamp_utc": "2026-09-07T12:00:00Z"}
    with pytest.raises(ValueError, match="EXISTING_AUTHORITY_SOURCE_UNSUPPORTED"):
        evaluate(c, existing_authority=authority)
    authority["result_publication_source"] = "ISSUER_EARNINGS_RELEASE"
    authority["quarter_id"] += 1
    with pytest.raises(ValueError, match="EXISTING_AUTHORITY_IDENTITY_MISMATCH"):
        evaluate(c, existing_authority=authority)


def test_revision_relation_cannot_promote_contradictory_xbrl_role_without_financial_minimum():
    c = case(); _, target = second(c, "REVISED_OR_CORRECTED_RESULTS", "6-K/A")
    target["amendment_role"] = "XBRL_ONLY_SUPPLEMENT"
    target["event"]["supporting_statement"] = False
    relation(c, "INITIAL_RESULT_TO_REVISION")
    result = evaluate(c)
    assert result["final_result"] == "REVIEW" and result["selected_timestamp"] is None
    assert result["candidate_evaluations"][1]["reason"] == "REVIEW_CONTRADICTORY_AMENDMENT_ROLE"
