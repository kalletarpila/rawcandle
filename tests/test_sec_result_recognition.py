from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.result_publication import (
    SecClient, SecFiling, apply_resolution, is_item_2_02, match_quarter_context,
    resolve_sec_filings_detailed,
)
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema
from rawcandle.fundamentals.sec_result_context import item_202_sections, linked_result_exhibits


PARENT = "https://www.sec.gov/Archives/edgar/data/8858/000000885826000066/avt-20260805x8k.htm"
ACCEPTED = "2026-08-05T20:30:00Z"
QUARTER = {"quarter_id": 1, "company_id": 1, "fiscal_year": 2026,
           "fiscal_quarter": "Q4", "period_end": "2026-06-27"}
HEADING = "<p>Item 2.02 - Results of Operations and Financial Condition.</p>"
RESULTS = "Avnet Reports Fourth Quarter and Fiscal 2026 Financial Results. Avnet today announced results for its fourth quarter and fiscal year 2026 ended June 27, 2026."
FIXTURES = Path(__file__).parent / "fixtures/sec_result_recognition"


def filings(primary: str, exhibits: dict[str, str] | None = None, *, form: str = "8-K", items: str = "2.02"):
    documents = {PARENT: primary, **{PARENT.rsplit('/', 1)[0] + '/' + name: text
                                   for name, text in (exhibits or {}).items()}}
    fetched = []

    def fetch(url):
        fetched.append(url)
        return documents[url]

    client = SecClient(fetch_json=lambda _: {"filings": {"recent": {
        "form": [form], "items": [items], "acceptanceDateTime": [ACCEPTED],
        "accessionNumber": ["0000008858-26-000066"], "primaryDocument": [PARENT.rsplit('/', 1)[1]],
    }}}, fetch_text=fetch, minimum_interval_seconds=0)
    return client.item_2_02_filings("8858"), fetched


def candidates(primary: str, exhibits: dict[str, str] | None = None):
    found, fetched = filings(primary, exhibits)
    matches, unresolved, diagnostics = resolve_sec_filings_detailed([QUARTER], found)
    return matches.get((1, 2026, "Q4"), []), unresolved, fetched


@pytest.mark.parametrize("heading", [
    HEADING,
    "<p>Item 2.02 &#8212; Results of Operations and Financial Condition.</p>",
    "<p><b>Item 2.02</b> <b>Results of Operati</b><b>ons and Financial Condition.</b></p>",
    "<p>Item 2.02</p><p>Results of Operation and Financial Condition.</p>",
    "<p>Item\n2.02: Result of Operations and Financial Condition.</p>",
    "<p>Item 2.02 Results of Financial Operations and Financial Condition.</p>",
    "<p>Items 2.02 and 7.01 Results of Operations and Financial Condition and Regulation FD Disclosure.</p>",
])
def test_normalized_section_headings(heading):
    assert item_202_sections(heading + "<p>" + RESULTS + "</p>")
    rows, _, fetched = candidates(heading + "<p>" + RESULTS + "</p>")
    assert len(rows) == 1
    assert rows[0]["source_timestamp_utc"] == ACCEPTED
    assert fetched == [PARENT]


def test_avt_linked_context_keeps_parent_timestamp_and_durable_provenance():
    primary = "<p>Item 2.02 Results of Operations and Financial Condition.</p><p>We issued our earnings release, attached as <a href='avt-20260805xex99d1.htm'>Exhibit 99.1</a>.</p>"
    rows, _, fetched = candidates(primary, {"avt-20260805xex99d1.htm": RESULTS})
    assert len(rows) == 1
    row = rows[0]
    assert row["source_timestamp_utc"] == ACCEPTED
    assert row["source_reference"] == PARENT
    assert row["source_type"] == "SEC_8K_ITEM_2_02"
    context = json.loads(row["matching_method"].split(":", 1)[1])
    assert context["parent_accession"] == "0000008858-26-000066"
    assert len(context["exhibits"][0]["sha256"]) == 64
    assert len(fetched) == 2


@pytest.mark.parametrize("text", [
    "We announced guidance only for the quarter ended June 27, 2026.",
    "We will announce financial results for the quarter ended June 27, 2026.",
    "June 27, 2026. We reported an investor meeting.",
    "We reported pro forma merger financial results for the quarter ended June 27, 2026.",
    "We reported preliminary financial results for the quarter ended June 27, 2026.",
    "We reported partial financial results for the quarter ended June 27, 2026.",
    "We reported an investor presentation of results for the quarter ended June 27, 2026.",
    "We reported cash receipts and a distribution for the quarter ended June 27, 2026.",
    "We reported monthly performance metrics for the quarter ended June 27, 2026.",
])
def test_new_heading_and_exhibit_paths_reject_non_result_events(text):
    rows, _, _ = candidates(HEADING + "<p>" + text + "</p>")
    assert not rows
    rows, _, _ = candidates(HEADING + "<p>See <a href='ex99-1.htm'>Exhibit 99.1</a>.</p>", {"ex99-1.htm": text})
    assert not rows


def test_late_preliminary_event_does_not_bypass_lead_safety_gate():
    from rawcandle.fundamentals.sec_result_context import result_context
    text = "Corporate background. " * 90 + "We reported preliminary financial results for the quarter ended June 27, 2026."
    assert result_context(text) is None
    rows, _, _ = candidates(HEADING + "<p>See <a href='ex99-1.htm'>Exhibit 99.1</a>.</p>", {"ex99-1.htm": text})
    assert not rows


def test_body_mention_and_unrelated_item_cannot_open_new_path():
    for primary in ["<p>As discussed in Item 2.02 - Results of Operations, " + RESULTS + "</p>",
                    "<p>Item 7.01 Results of Operations.</p><p>" + RESULTS + "</p>"]:
        assert not item_202_sections(primary)
        assert not candidates(primary)[0]


def test_parent_eligibility_and_unrelated_or_foreign_links():
    primary = HEADING + "<p><a href='ex99-1.htm'>Exhibit 99.1</a></p>"
    assert not filings(primary, {"ex99-1.htm": RESULTS}, form="6-K")[0]
    assert not filings(primary, {"ex99-1.htm": RESULTS}, items="7.01")[0]
    for href in ["ex10-1.htm", "https://issuer.test/ex99-1.htm", "../ex99-1.htm",
                 "https://www.sec.gov.evil.test/ex99-1.htm", "ex99-1.htm?redirect=evil"]:
        assert not linked_result_exhibits(f"<a href='{href}'>Unrelated contract</a>", PARENT)


def test_conflicting_quarter_and_conflicting_exhibits_are_not_unique():
    other = "We announced financial results for the third quarter ended March 28, 2026."
    primary = HEADING + "<p><a href='ex99-1.htm'>Exhibit 99.1</a><a href='ex99-2.htm'>Exhibit 99.2</a></p>"
    rows, unresolved, fetched = candidates(primary, {"ex99-1.htm": RESULTS, "ex99-2.htm": other})
    assert not rows and unresolved
    assert len(fetched) == 3
    assert not candidates(HEADING + "<p><a href='ex99-1.htm'>Exhibit 99.1</a></p>", {"ex99-1.htm": other})[0]
    assert not candidates(HEADING + "<p>" + other + "<a href='ex99-1.htm'>Exhibit 99.1</a></p>", {"ex99-1.htm": RESULTS})[0]


def test_bounded_deduplicated_nonrecursive_links():
    links = "<a href='ex99-1.htm'>Exhibit 99.1</a>" * 3
    assert len(linked_result_exhibits(links, PARENT)) == 1
    assert not linked_result_exhibits(links + "<a href='ex99-2.htm'>Exhibit 99.2</a><a href='other-results.htm'>Results</a>", PARENT)
    primary = HEADING + "<p>" + links + "</p>"
    rows, _, fetched = candidates(primary, {"ex99-1.htm": RESULTS + "<a href='nested-results.htm'>Results</a>"})
    assert len(rows) == 1 and len(fetched) == 2


def test_legacy_preliminary_primary_candidate_is_not_retroactively_rejected():
    primary = "Item 2.02 Results of Operations and Financial Condition. We announced preliminary results for the quarter ended June 27, 2026."
    rows, _, _ = candidates(primary)
    assert len(rows) == 1
    assert rows[0]["matching_method"] == "CIK_ITEM_2_02_EXACT_PERIOD_END"


@pytest.mark.parametrize("case", json.loads((FIXTURES / "positive.json").read_text())["cases"], ids=lambda row: row["ticker"])
def test_exact_frozen_avt_cpb_orcl_audit_excerpts(case):
    url = case["url"]
    documents = {url: case["primary_html"], **{url.rsplit('/', 1)[0] + '/' + name: text
                                               for name, text in case["exhibits"].items()}}
    client = SecClient(fetch_json=lambda _: {"filings": {"recent": {
        "form": ["8-K"], "items": ["2.02"], "accessionNumber": [case["accession"]],
        "acceptanceDateTime": [case["accepted"]], "primaryDocument": [url.rsplit('/', 1)[1]],
    }}}, fetch_text=documents.__getitem__, minimum_interval_seconds=0)
    found = client.item_2_02_filings(case["cik"])
    matches, _, _ = resolve_sec_filings_detailed([case["quarter"]], found)
    rows = next(iter(matches.values()))
    assert len(rows) == 1
    assert rows[0]["accession_number"] == case["accession"]
    assert rows[0]["source_timestamp_utc"] == case["accepted"]
    assert rows[0]["source_reference"] == url


@pytest.mark.parametrize("case", json.loads((FIXTURES / "true_ambiguous.json").read_text())["cases"], ids=lambda row: row["ticker"])
def test_all_22_true_ambiguities_retain_pre_change_candidate_sets(case):
    q = case["quarter"]
    old_set = set()
    found = []
    for original in case["filings"]:
        row = {key: value for key, value in original.items() if key != "source_sha256"}
        assert is_item_2_02(row["form"], row["items"], row["text"])
        assert match_quarter_context(row["text"], q)
        old_set.add((row["accession_number"], row["acceptance_timestamp_utc"]))
        found.append(SecFiling(**row, result_sections=item_202_sections("<p>" + row["text"] + "</p>")))
    matches, _, _ = resolve_sec_filings_detailed([q], found)
    rows = next(iter(matches.values()))
    new_set = {(row["accession_number"], row["source_timestamp_utc"]) for row in rows}
    assert len(old_set) == 2 and old_set <= new_set
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        ensure_result_publication_schema(connection)
        assert apply_resolution(connection, q, rows) == "AMBIGUOUS"
        assert apply_resolution(connection, q, rows) == "AMBIGUOUS"


def test_optional_exhibit_failure_does_not_remove_legacy_primary_candidate():
    primary = "<p>Item 2.02 Results of Operations and Financial Condition.</p><p>We announced preliminary results for the quarter ended June 27, 2026.</p>"
    rows, _, _ = candidates(primary)
    assert len(rows) == 1
    # A cover-date candidate is intentionally preserved under legacy semantics,
    # even when its optional new-context lookup cannot complete.
    primary = "<p>June 27, 2026</p><p>Item 2.02 Results of Operations and Financial Condition.</p><p>See <a href='ex99-1.htm'>Exhibit 99.1</a>.</p>"
    from urllib.error import URLError

    def fetch(url):
        if url == PARENT:
            return primary
        raise URLError("offline fixture")

    client = SecClient(fetch_json=lambda _: {"filings": {"recent": {
        "form": ["8-K"], "items": ["2.02"], "accessionNumber": ["0000008858-26-000066"],
        "acceptanceDateTime": [ACCEPTED], "primaryDocument": [PARENT.rsplit('/', 1)[1]],
    }}}, fetch_text=fetch, minimum_interval_seconds=0)
    matches, _, _ = resolve_sec_filings_detailed([QUARTER], client.item_2_02_filings("8858"))
    assert len(matches[(1, 2026, "Q4")]) == 1
    assert client.stats["result_context_exhibit_failures"] == 1
