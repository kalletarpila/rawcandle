"""Compact source-bound lexical fixtures; no authority writer or network calls."""
import hashlib
import json
from pathlib import Path

import pytest

from rawcandle.fundamentals.result_publication import (
    SecClient, SecFiling, SecResultExhibit, _new_context_method,
    match_quarter_context, resolve_sec_filings_detailed,
)
from rawcandle.fundamentals.sec_result_context import (
    lexical_result_fiscal_tokens, result_context,
    result_fiscal_tokens, unsafe_new_event,
)

PARENT = "https://www.sec.gov/Archives/edgar/data/1467858/000146785826000056/gm-20261020.htm"
QUARTER = {"quarter_id": 33934, "company_id": 955, "fiscal_year": 2026,
           "fiscal_quarter": "Q3", "period_end": "2026-09-30"}
FORMS = (
    ("2026 third-quarter", "2026:Q3"),
    ("third-quarter 2026", "2026:Q3"),
    ("second quarter fiscal 2027", "2027:Q2"),
    ("second quarter of fiscal 2027", "2027:Q2"),
    ("Q1 Fiscal 2027", "2027:Q1"),
)


def filing(primary, *, exhibits=(), legacy=False, accession="0001467858-26-000056",
           reference=PARENT, accepted="2026-10-20T11:30:18Z"):
    return SecFiling(accession, "8-K", "2.02,9.01", accepted,
                     reference.rsplit("/", 1)[1], reference, primary,
                     legacy_primary=legacy, result_sections=(primary,),
                     result_exhibits=tuple(exhibits))


def candidates(primary, *, quarter=QUARTER, exhibits=()):
    m, _, d = resolve_sec_filings_detailed([quarter], [filing(primary, exhibits=exhibits)])
    k = (quarter["company_id"], quarter["fiscal_year"], quarter["fiscal_quarter"])
    return m.get(k, []), d[k]


@pytest.mark.parametrize("wording,token", FORMS)
def test_observed_token_forms_are_explicit_matching_only(wording, token):
    assert not result_fiscal_tokens(wording)  # acquisition vocabulary unchanged
    assert lexical_result_fiscal_tokens(wording) == {token}
    text = f"The company reported financial results for the quarter identified as {wording}."
    assert result_context(text) is None
    assert result_context(text, allow_lexical_variants=True) == text
    year, quarter = token.split(":")
    q = {**QUARTER, "fiscal_year": int(year), "fiscal_quarter": quarter}
    rows, _ = candidates(text, quarter=q)
    assert len(rows) == 1
    assert rows[0]["source_timestamp_utc"] == "2026-10-20T11:30:18Z"
    assert rows[0]["source_reference"] == PARENT


@pytest.mark.parametrize("wording,token", FORMS)
@pytest.mark.parametrize("template", (
    "We will announce financial results for its {wording}.",
    "We expect to report financial results for its {wording}.",
    "We plan to release financial results for its {wording}.",
    "We anticipate financial results for its {wording}.",
    "We scheduled the announcement of financial results for its {wording}.",
    "Financial results for its {wording} will be announced tomorrow.",
    "We reported cash receipts and a distribution for its {wording}.",
    "We reported preliminary financial results for its {wording}.",
    "We reported partial financial results for its {wording}.",
    "We reported pro forma financial results for its {wording}.",
))
def test_new_tokens_do_not_bypass_existing_event_guards(wording, token, template):
    text = template.format(wording=wording)
    assert lexical_result_fiscal_tokens(text) == {token}
    assert result_context(text, allow_lexical_variants=True) is None
    assert candidates(text)[0] == []


@pytest.mark.parametrize("text", (
    "2026", "third quarter", "Q1 Fiscal", "Q5 Fiscal 2027", "third-quarter 26",
    "third-quarter 20260", "202 third-quarter", "20260 third-quarter",
    "second quarter of fiscal 202", "second quarter fiscal 20270",
    "second quarterly fiscal 2027", "Q1 Fiscally 2027",
    "annual financial results for fiscal 2026",
    "financial results for the six months ended September 30, 2026",
    "third-quarter-mile sales territory in 2026",
))
def test_no_inferred_partial_or_unrelated_fiscal_tokens(text):
    assert lexical_result_fiscal_tokens(text) == set()


@pytest.mark.parametrize("text", (
    "fiscal 2026 fourth quarter", "2026 fourth quarter", "2026 second quarter",
))
def test_unhyphenated_year_before_forms_remain_deferred(text):
    assert not lexical_result_fiscal_tokens(text)
    assert candidates(f"We reported financial results for the {text}.")[0] == []


@pytest.mark.parametrize("text", (
    "first quarter 2026", "third quarter of fiscal year 2026", "Q3 FY2026",
))
def test_original_token_vocabulary_is_preserved(text):
    assert lexical_result_fiscal_tokens(text) == result_fiscal_tokens(text)
    assert result_fiscal_tokens(text)


@pytest.mark.parametrize("wording", (
    "2026 third-quarter and 2025 third-quarter",
    "third-quarter 2026 and third-quarter 2025",
    "third quarter fiscal 2026 and third quarter fiscal 2025",
    "Q3 Fiscal 2026 and Q3 Fiscal 2025",
))
def test_comparative_tokens_are_retained_not_ranked(wording):
    text = f"We reported financial results for {wording}."
    assert lexical_result_fiscal_tokens(text) == {"2026:Q3", "2025:Q3"}
    assert _new_context_method(text, QUARTER) is None
    assert candidates(text)[0] == []


def test_prior_only_token_cannot_match_current_quarter():
    text = "We reported financial results for the 2025 third-quarter."
    assert lexical_result_fiscal_tokens(text) == {"2025:Q3"}
    assert candidates(text)[0] == []


def test_fiscal_convention_mismatch_is_not_remapped():
    q = {**QUARTER, "fiscal_year": 2027, "fiscal_quarter": "Q2", "period_end": "2026-08-01"}
    text = "We reported financial results for the second quarter of fiscal 2026."
    assert lexical_result_fiscal_tokens(text) == {"2026:Q2"}
    assert candidates(text, quarter=q)[0] == []


# Exact frozen fiscal/result clauses in compact sentence frames, not full SEC
# payloads. Parent payload SHA-256s:
# GE 0832a3a1dc2436fe7beb4dbacabaa54e6893a84a14a470290cd643bd386e4b5d
# GM 1f9f17374afbf9ec91121b4771f3179ca4f9256fa3a807c19d78df8f0a260e63
# MMM 72f8ee4edfe376698b445b5afd7b7d99c347b9770aa725815f78a1e91938041b
# Full real-input acquisition/resolver comparison is recorded in the phase report.
@pytest.mark.parametrize("company_id,quarter_id,cik,document,accession,accepted,text", (
    (931, 33069, 40545, "ge-20261020.htm", "0000040545-26-000063", "2026-10-20T10:30:57Z",
     "General Electric Company released its third-quarter 2026 financial results."),
    (1440, 51429, 66740, "mmm-20261020.htm", "0000066740-26-000308", "2026-10-20T10:35:38Z",
     "3M Company issued a press release reporting third-quarter 2026 financial results."),
))
def test_frozen_primary_lexical_clauses_keep_identity_and_acceptance(
    company_id, quarter_id, cik, document, accession, accepted, text,
):
    q = {**QUARTER, "company_id": company_id, "quarter_id": quarter_id}
    reference = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
    assert match_quarter_context(text, q) is None
    assert lexical_result_fiscal_tokens(text) == {"2026:Q3"}
    f = filing(text, accession=accession, reference=reference, accepted=accepted)
    m, _, _ = resolve_sec_filings_detailed([q], [f])
    row, = m[(company_id, 2026, "Q3")]
    assert row["source_timestamp_utc"] == accepted
    assert row["source_reference"] == reference


def test_frozen_gm_exhibit_lexical_clause_keeps_parent_authority():
    primary = ("General Motors Company issued a news release and supplemental materials "
               "on the subject of its 2026 third quarter consolidated earnings.")
    text = "GM releases 2026 third-quarter results and updates full-year 2026 guidance."
    url = PARENT.rsplit("/", 1)[0] + "/gmq32026pressreleaseandfin.htm"
    exhibit = SecResultExhibit(url, "95297ccfe37212db992fb9052fdbce8663c89aec3203fc7f315f84d3c1cab646", text)
    rows, _ = candidates(primary, exhibits=[exhibit])
    row, = rows
    assert row["company_id"] == 955
    assert row["source_timestamp_utc"] == "2026-10-20T11:30:18Z"
    assert row["source_reference"] == PARENT
    assert row["matching_method"].startswith("SEC_LINKED_EXHIBIT:")


def test_hele_and_tlry_still_need_separate_veto_work():
    hele = ('We issued a press release announcing results for the second quarter of fiscal 2027. '
            'Generally, the words “anticipates”, “assumes”, “believes” describe forward-looking statements.')
    tlry = ("International Cannabis, Beverage and Pharmaceutical Distribution. "
            "We reported financial results for its Q1 Fiscal 2027.")
    for text in (hele, tlry):
        assert unsafe_new_event(text)
        assert result_context(text, allow_lexical_variants=True) is None
        assert candidates(text)[0] == []


def test_ge_non_conclusive_date_does_not_fall_back_to_fiscal_token():
    text = ("GE AEROSPACE ANNOUNCES THIRD QUARTER 2026 RESULTS. "
            "GE announced results today for the third quarter ending September 30, 2026.")
    assert match_quarter_context(text, QUARTER) == "CIK_ITEM_2_02_EXACT_PERIOD_END"
    assert lexical_result_fiscal_tokens(text) == {"2026:Q3"}
    assert _new_context_method(text, QUARTER) is None


def test_new_forms_preserve_primary_exhibit_conflict():
    url = PARENT.rsplit("/", 1)[0] + "/ex99-1.htm"
    text = "We reported financial results for the 2025 third-quarter."
    exhibit = SecResultExhibit(url, hashlib.sha256(text.encode()).hexdigest(), text)
    primary = "We reported financial results for the 2026 fourth-quarter."
    assert candidates(primary, exhibits=[exhibit])[0] == []


def test_acquisition_never_uses_matching_only_lexical_tokens(monkeypatch):
    from rawcandle.fundamentals import sec_result_context
    def forbidden(_):
        pytest.fail("matching-only vocabulary changed source acquisition")
    monkeypatch.setattr(sec_result_context, "lexical_result_fiscal_tokens", forbidden)
    html = ("<p>Item 2.02 Results of Operations and Financial Condition.</p>"
            "<p>We reported financial results for the 2026 third-quarter.</p>"
            "<a href='ex99-1.htm'>Exhibit 99.1</a>")
    fetched = []
    def fetch(url):
        fetched.append(url)
        return html if url == PARENT else "We reported financial results for third quarter 2026."
    client = SecClient(fetch_json=lambda _: {"filings": {"recent": {
        "form": ["8-K"], "items": ["2.02"], "acceptanceDateTime": ["2026-10-20T11:30:18Z"],
        "accessionNumber": ["0001467858-26-000056"], "primaryDocument": [PARENT.rsplit('/', 1)[1]],
    }}}, fetch_text=fetch, minimum_interval_seconds=0)
    fs = client.item_2_02_filings("1467858")
    assert len(fs[0].result_exhibits) == 1
    assert fetched == [PARENT, PARENT.rsplit('/', 1)[0] + "/ex99-1.htm"]


def test_legacy_preliminary_compatibility_remains_separate():
    text = "Item 2.02 Results of Operations. We reported preliminary results for the quarter ended September 30, 2026."
    m, _, _ = resolve_sec_filings_detailed([QUARTER], [filing(text, legacy=True)])
    assert len(m[(955, 2026, "Q3")]) == 1


@pytest.mark.parametrize("case", json.loads((Path(__file__).parent / "fixtures/sec_result_recognition/true_ambiguous.json").read_text())["cases"], ids=lambda c: c["ticker"])
def test_22_legacy_ambiguities_remain_two_parent_candidates_without_writer(case):
    fs = [SecFiling(**{k: v for k, v in f.items() if k != "source_sha256"}) for f in case["filings"]]
    m, _, _ = resolve_sec_filings_detailed([case["quarter"]], fs)
    rows = [r for values in m.values() for r in values]
    assert len(rows) == 2
    assert {(r["accession_number"], r["source_timestamp_utc"]) for r in rows} == {
        (f.accession_number, f.acceptance_timestamp_utc) for f in fs}


def test_brc_frozen_primary_stays_held_and_three_links_stay_rejected():
    # 0000746598-26-000043; the full source payload is bound in the replay manifest.
    primary = ("Item 2.02 RESULTS OF OPERATIONS AND FINANCIAL CONDITION "
               "On September 3, 2026, Brady Corporation (the “Company”) issued a press release "
               "announcing its fiscal 2026 fourth quarter financial results.")
    q = {**QUARTER, "company_id": 358, "fiscal_quarter": "Q4", "period_end": "2026-07-31"}
    parent = "https://www.sec.gov/Archives/edgar/data/746598/000074659826000043/brc-20260901.htm"
    f = filing(primary, accession="0000746598-26-000043", reference=parent,
               accepted="2026-09-03T10:59:09Z")
    m, _, _ = resolve_sec_filings_detailed([q], [f])
    assert not m
    from rawcandle.fundamentals.sec_result_context import linked_result_exhibits
    links = ''.join(f"<a href='{name}'>Results</a>" for name in (
        'exhibit991-financialsx2026.htm', 'exhibit992-dividendrelease.htm', 'f26q4conferencecallprese.htm'))
    assert linked_result_exhibits(links, parent) == ()


def test_tsla_frozen_future_defect_is_not_worsened_by_lexical_change():
    # Compact exact disclaimer/primary excerpts. Historical source payload drift
    # and the unimplemented one-candidate expectation are explicit in the report.
    early = ("Our net income and cash flow results will be announced along with the rest of our financial performance "
             "when we announce Q3 earnings. Tesla vehicle deliveries and storage deployments represent only two measures "
             "of the Company’s financial performance and should not be relied on as an indicator of quarterly financial results, "
             "which depend on a variety of factors, including average selling price, cost of sales, foreign exchange movements "
             "and others as to be disclosed in the 10-Q for the quarter ended on September 30, 2026.")
    q = {**QUARTER, "company_id": 2216}
    base = "https://www.sec.gov/Archives/edgar/data/1318605/"
    parent = base + "000162828026064366/tsla-20261002.htm"
    ex = SecResultExhibit(base + "000162828026064366/exhibit991111111.htm", "a" * 64, early)
    first = filing("Item 2.02 Results of Operations. Tesla published a press release.",
                   accession="0001628280-26-064366", reference=parent,
                   accepted="2026-10-02T13:04:26Z", exhibits=[ex])
    later = filing("Item 2.02 Results of Operations. Tesla released its financial results for the quarter ended September 30, 2026.",
                   accession="0001628280-26-066738", reference=base+"000162828026066738/tsla-20261021.htm",
                   accepted="2026-10-21T20:41:42Z", legacy=True)
    assert result_context(early) == result_context(early, allow_lexical_variants=True)
    m, _, d = resolve_sec_filings_detailed([q], [first, later])
    assert len(m[(2216, 2026, 'Q3')]) == 2  # known pre-existing defect, not a claimed fix
    assert d[(2216, 2026, 'Q3')]['reason'] == 'MULTIPLE_VALID_CANDIDATES'
    assert {r['accession_number'] for r in m[(2216, 2026, 'Q3')]} == {
        '0001628280-26-064366', '0001628280-26-066738'}
