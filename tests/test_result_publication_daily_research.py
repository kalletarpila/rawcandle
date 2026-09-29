from __future__ import annotations

from rawcandle.fundamentals.result_publication_daily_research import (
    PublicationCandidate,
    YahooEvent,
    project_daily_research,
)


CALENDAR = [
    "2026-01-15",
    "2026-01-16",
    "2026-01-20",
    "2026-01-21",
    "2026-01-22",
    "2026-01-23",
    "2026-01-26",
]


def authority(status: str = "AMBIGUOUS", timestamp: str | None = None) -> dict[str, object]:
    return {
        "company_id": 7,
        "fiscal_year": 2025,
        "fiscal_quarter": "Q4",
        "status": status,
        "result_publication_timestamp_utc": timestamp,
        "selected_evidence_id": "canonical",
        "result_publication_evidence_reference": "https://example.test/canonical",
    }


def candidate(candidate_id: str, timestamp: str) -> PublicationCandidate:
    return PublicationCandidate(candidate_id, timestamp, f"https://example.test/{candidate_id}")


def test_canonical_verified_is_exact_and_cannot_be_overridden() -> None:
    result = project_daily_research(
        authority("VERIFIED", "2026-01-20T13:00:00Z"),
        [candidate("other", "2026-01-21T22:00:00Z")],
        CALENDAR,
        yahoo_events=[YahooEvent("2026-01-21T06:00:00-05:00")],
        v2_strong_candidate_id="other",
    )
    assert (result.research_status, result.research_method) == ("EXACT", "CANONICAL_VERIFIED")
    assert result.first_full_post_result_trading_date == "2026-01-20"


def test_canonical_verified_remains_exact_when_next_ohlc_day_is_not_observed_yet() -> None:
    result = project_daily_research(
        authority("VERIFIED", "2026-01-26T22:00:00Z"), [], CALENDAR
    )
    assert (result.research_status, result.research_method) == ("EXACT", "CANONICAL_VERIFIED")
    assert result.first_full_post_result_trading_date is None


def test_all_candidates_same_effective_day_keeps_exact_timestamp_unselected() -> None:
    result = project_daily_research(
        authority(),
        [candidate("a", "2026-01-20T13:00:00Z"), candidate("b", "2026-01-18T15:00:00Z")],
        CALENDAR,
    )
    assert result.research_method == "ALL_CANDIDATES_SAME_EFFECTIVE_DAY"
    assert result.first_full_post_result_trading_date == "2026-01-20"
    assert result.selected_candidate_timestamp_utc is None


def test_yahoo_unique_sec_candidate_within_one_trading_day_ignores_global_later() -> None:
    result = project_daily_research(
        authority(),
        [candidate("near", "2026-01-20T22:00:00Z"), candidate("global-later", "2026-01-23T22:00:00Z")],
        CALENDAR,
        yahoo_events=[YahooEvent("2026-01-20T16:00:00-05:00")],
    )
    assert result.research_method == "YAHOO_NEAR_UNIQUE_SEC"
    assert result.selected_candidate_reference.endswith("/near")


def test_yahoo_local_cluster_uses_latest_only_inside_same_effective_day() -> None:
    result = project_daily_research(
        authority(),
        [
            candidate("early", "2026-01-20T21:05:00Z"),
            candidate("late", "2026-01-20T22:05:00Z"),
            candidate("outside", "2026-01-23T22:05:00Z"),
        ],
        CALENDAR,
        yahoo_events=[YahooEvent("2026-01-20T16:00:00-05:00")],
    )
    assert result.research_method == "YAHOO_NEAR_CLUSTER_LATEST"
    assert result.selected_candidate_reference.endswith("/late")


def test_distinct_yahoo_event_clusters_do_not_trigger_global_latest() -> None:
    result = project_daily_research(
        authority(),
        [candidate("first", "2026-01-20T22:00:00Z"), candidate("second", "2026-01-23T22:00:00Z")],
        CALENDAR,
        yahoo_events=[
            YahooEvent("2026-01-20T16:00:00-05:00"),
            YahooEvent("2026-01-23T16:00:00-05:00"),
        ],
    )
    assert (result.research_status, result.research_method) == (
        "UNUSABLE",
        "YAHOO_NO_UNIQUE_LOCAL_CLUSTER",
    )


def test_yahoo_unavailable_sec_cluster_one_day_uses_latest_with_medium_confidence() -> None:
    result = project_daily_research(
        authority(),
        [candidate("a", "2026-01-20T22:00:00Z"), candidate("b", "2026-01-21T22:00:00Z")],
        CALENDAR,
    )
    assert (result.research_status, result.research_method) == (
        "HEURISTIC_MEDIUM",
        "SEC_LOCAL_CLUSTER_LATEST",
    )
    assert result.selected_candidate_reference.endswith("/b")


def test_sec_cluster_over_one_day_is_unusable() -> None:
    result = project_daily_research(
        authority(),
        [candidate("a", "2026-01-20T22:00:00Z"), candidate("b", "2026-01-22T22:00:00Z")],
        CALENDAR,
    )
    assert result.research_status == "UNUSABLE"


def test_same_day_pre_and_after_are_distinct_and_yahoo_session_protects_boundary() -> None:
    result = project_daily_research(
        authority(),
        [candidate("pre", "2026-01-20T13:00:00Z"), candidate("after", "2026-01-20T22:00:00Z")],
        CALENDAR,
        yahoo_events=[YahooEvent("2026-01-20T16:00:00-05:00")],
    )
    assert result.selected_candidate_reference.endswith("/after")
    assert result.first_full_post_result_trading_date == "2026-01-21"


def test_friday_after_market_weekend_and_monday_holiday_use_tuesday() -> None:
    result = project_daily_research(
        authority("VERIFIED", "2026-01-16T22:00:00Z"), [], CALENDAR
    )
    assert result.research_publication_session == "AFTER_MARKET"
    assert result.first_full_post_result_trading_date == "2026-01-20"


def test_weekend_publication_uses_first_observed_trading_day() -> None:
    result = project_daily_research(
        authority("VERIFIED", "2026-01-18T17:00:00Z"), [], CALENDAR
    )
    assert result.first_full_post_result_trading_date == "2026-01-20"


def test_v2_strong_rule_precedes_yahoo_and_sec_cluster() -> None:
    result = project_daily_research(
        authority(),
        [candidate("strong", "2026-01-20T22:00:00Z"), candidate("other", "2026-01-23T22:00:00Z")],
        CALENDAR,
        yahoo_events=[YahooEvent("2026-01-23T16:00:00-05:00")],
        v2_strong_candidate_id="strong",
    )
    assert result.research_method == "SEC_V2_STRONG_INITIAL"
    assert result.selected_candidate_reference.endswith("/strong")


def test_rule_order_is_deterministic_when_inputs_are_reversed() -> None:
    candidates = [candidate("a", "2026-01-20T21:05:00Z"), candidate("b", "2026-01-20T22:05:00Z")]
    events = [YahooEvent("2026-01-20T16:00:00-05:00")]
    first = project_daily_research(authority(), candidates, CALENDAR, yahoo_events=events)
    second = project_daily_research(authority(), list(reversed(candidates)), CALENDAR, yahoo_events=events)
    assert first.to_dict() == second.to_dict()
