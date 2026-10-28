"""Local pending-event rejection; no authority writer or network is exercised."""
from dataclasses import asdict

import pytest

from rawcandle.fundamentals.result_publication import (
    SecFiling, _new_context_method, resolve_sec_filings_detailed,
)
from rawcandle.fundamentals.sec_result_context import (
    _pending_result_trigger, lexical_result_fiscal_tokens, result_context,
    unsafe_new_event,
)

QUARTER = {"company_id": 2216, "quarter_id": 78864, "fiscal_year": 2026,
           "fiscal_quarter": "Q3", "period_end": "2026-09-30"}
PARENT = "https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/tsla-20261002.htm"


def resolve(text):
    f = SecFiling("0001628280-26-064366", "8-K", "2.02,9.01",
                  "2026-10-02T13:04:26Z", "tsla-20261002.htm", PARENT, text,
                  legacy_primary=False, result_sections=(text,))
    before = asdict(f)
    m, _, d = resolve_sec_filings_detailed([QUARTER], [f])
    assert asdict(f) == before
    return m.get((2216, 2026, "Q3"), []), d[(2216, 2026, "Q3")]


@pytest.mark.parametrize("pending", (
    "Results will be announced next week.",
    "Financial results will be released after market close.",
    "Results will be reported later.",
    "Financial performance will be released next week.",
    "Earnings will be discussed in a future conference call.",
    "Results are expected to be announced next week.",
    "Results are scheduled to be reported next week.",
    "We expect to report results next week.",
    "Management will discuss results in a future conference call.",
    "A conference call to discuss results is scheduled for next week.",
    "Preliminary production metrics; financial results forthcoming.",
    "These metrics are not financial performance; results will be announced later.",
))
@pytest.mark.parametrize("period", (
    "the third-quarter 2026", "the quarter ended September 30, 2026",
))
def test_pending_reference_cannot_borrow_a_nearby_fiscal_token_or_date(pending, period):
    text = f"{pending} The financial results concern {period}."
    assert result_context(text, allow_lexical_variants=True) is None
    assert resolve(text)[0] == []


@pytest.mark.parametrize("conditional", (
    "when we announce", "once the company reports", "until management releases",
    "after the company announces", "before we report",
))
def test_dependent_present_clause_is_not_an_actual_result_assertion(conditional):
    text = f"Financial performance will be available {conditional} Q3 earnings. Financial results concern third-quarter 2026."
    assert result_context(text, allow_lexical_variants=True) is None
    assert resolve(text)[0] == []


@pytest.mark.parametrize("prefix,verb", (
    ("Financial results will be ", "announced"),
    ("Financial results will soon be ", "reported"),
    ("Financial results may have been ", "released"),
    ("Results are expected to be ", "announced"),
    ("We are planning to ", "report"),
    ("when we ", "announce"),
))
def test_only_the_pending_auxiliary_governing_the_trigger_is_rejected(prefix, verb):
    assert _pending_result_trigger(prefix, verb)


@pytest.mark.parametrize("prefix,verb", (
    ("We expect growth; the company ", "reported"),
    ("We will discuss guidance. The company ", "released"),
    ("After we ", "reported"),
    ("When the company ", "announced"),
    ("The company ", "reports"),
))
def test_completed_assertions_are_not_rejected_by_unrelated_future_words(prefix, verb):
    assert not _pending_result_trigger(prefix, verb)


@pytest.mark.parametrize("actual", (
    "The company reports third-quarter 2026 financial results.",
    "The company released third-quarter 2026 financial results.",
    "The company announced actual financial results for the quarter ended September 30, 2026.",
    "The company reported third-quarter 2026 results, including revenue and net income.",
))
@pytest.mark.parametrize("later", (
    "It expects FY growth.",
    "Management will discuss results on a conference call.",
    "It expects financial results will be announced in a later fiscal year.",
    "A conference call to discuss these results follows next week.",
))
def test_current_result_plus_outlook_or_later_call_is_still_current(actual, later):
    rows, diagnostic = resolve(actual + " " + later)
    assert len(rows) == 1
    assert diagnostic["reason"] == "VERIFIED"
    assert rows[0]["source_timestamp_utc"] == "2026-10-02T13:04:26Z"


@pytest.mark.parametrize("pending", (
    "Financial results will be announced next week.",
    "Results are expected to be released tomorrow.",
    "Financial performance is pending when we announce Q3 earnings.",
))
def test_rejected_pending_span_does_not_swallow_a_separate_actual_assertion(pending):
    text = pending + " The company reported third-quarter 2026 financial results."
    rows, diagnostic = resolve(text)
    assert len(rows) == 1
    assert diagnostic["reason"] == "VERIFIED"


def test_existing_positive_with_later_forward_looking_boilerplate_is_preserved():
    actual = "The company reports third-quarter 2026 financial results."
    # Keep the pre-existing lead/context veto boundary: this phase does not
    # resolve the separately frozen HELE global-boilerplate hold.
    text = actual + " Revenue and net income are included in the financial statements." * 25
    text += " Forward-looking statements: management anticipates future demand."
    assert text.index("anticipates") > 1200
    assert len(resolve(text)[0]) == 1


def test_exact_hele_guard_trigger_remains_held_not_reinterpreted():
    # Exact frozen clauses from 0000916789-26-000137. Full source replay is
    # detached in the phase report; this compact fixture preserves the veto.
    text = ("issued a press release announcing the results for the second quarter of fiscal 2027. "
            "Generally, the words “anticipates”, “assumes”, “believes”, “expects” identify forward-looking statements.")
    assert lexical_result_fiscal_tokens(text) == {"2027:Q2"}
    assert unsafe_new_event(text)
    assert result_context(text, allow_lexical_variants=True) is None


def test_current_and_prior_tokens_are_not_filtered_by_modality_guard():
    text = "The company reported third-quarter 2026 and third-quarter 2025 financial results."
    assert lexical_result_fiscal_tokens(text) == {"2026:Q3", "2025:Q3"}
    assert _new_context_method(text, QUARTER) is None
    assert resolve(text)[0] == []


def test_acquisition_context_is_unchanged_but_matching_context_rejects_pending_trigger():
    text = "Our financial performance is pending when we announce Q3 earnings. Financial results concern third quarter 2026."
    assert result_context(text) is not None
    assert result_context(text, allow_lexical_variants=True) is None
