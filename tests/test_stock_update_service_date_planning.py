import pytest

from services.stock_update_service import (
    LONG_FETCH_CHUNK_DAYS,
    LONG_FETCH_RANGE_THRESHOLD_DAYS,
    StockUpdateTickerCandidate,
    plan_ticker_update,
    plan_ticker_updates,
    resolve_effective_update_start_date,
    run_stock_data_update,
    split_fetch_date_range,
)


def test_resolve_effective_update_start_date_handles_override_rules():
    assert (
        resolve_effective_update_start_date(last_date="2026-05-10", start_override=None)
        == "2026-05-11"
    )
    assert (
        resolve_effective_update_start_date(last_date="2026-05-10", start_override="")
        == "2026-05-11"
    )
    assert (
        resolve_effective_update_start_date(last_date="2026-05-10", start_override="   ")
        == "2026-05-11"
    )
    assert (
        resolve_effective_update_start_date(
            last_date="2026-05-10", start_override="2026-05-01"
        )
        == "2026-05-11"
    )
    assert (
        resolve_effective_update_start_date(
            last_date="2026-05-10", start_override="2026-05-15"
        )
        == "2026-05-15"
    )
    with pytest.raises(ValueError):
        resolve_effective_update_start_date(
            last_date="2026-05-10", start_override="2026/05/15"
        )


def test_split_fetch_date_range_handles_empty_short_threshold_and_chunked_ranges():
    assert (
        split_fetch_date_range(
            start_date="2026-05-10",
            end_date_exclusive="2026-05-10",
        )
        == []
    )
    assert (
        split_fetch_date_range(
            start_date="2026-05-11",
            end_date_exclusive="2026-05-10",
        )
        == []
    )

    short_ranges = split_fetch_date_range(
        start_date="2026-01-01",
        end_date_exclusive="2026-01-11",
    )
    assert [(item.start_date, item.end_date_exclusive) for item in short_ranges] == [
        ("2026-01-01", "2026-01-11")
    ]

    threshold_end = "2027-12-31"
    threshold_ranges = split_fetch_date_range(
        start_date="2026-01-01",
        end_date_exclusive=threshold_end,
    )
    assert len(threshold_ranges) == 1
    assert threshold_ranges[0].start_date == "2026-01-01"
    assert threshold_ranges[0].end_date_exclusive == threshold_end

    chunked_ranges = split_fetch_date_range(
        start_date="2026-01-01",
        end_date_exclusive="2028-01-02",
    )
    assert len(chunked_ranges) == 3
    assert chunked_ranges[0].start_date == "2026-01-01"
    assert chunked_ranges[0].end_date_exclusive == "2027-01-01"
    assert chunked_ranges[1].start_date == "2027-01-01"
    assert chunked_ranges[1].end_date_exclusive == "2028-01-01"
    assert chunked_ranges[2].start_date == "2028-01-01"
    assert chunked_ranges[2].end_date_exclusive == "2028-01-02"
    assert chunked_ranges[-1].end_date_exclusive == "2028-01-02"
    assert [item.start_date for item in chunked_ranges] == [
        "2026-01-01",
        "2027-01-01",
        "2028-01-01",
    ]


def test_split_fetch_date_range_exact_threshold_returns_one_range():
    exact_threshold_end = "2027-12-31"
    ranges = split_fetch_date_range(
        start_date="2026-01-01",
        end_date_exclusive=exact_threshold_end,
    )
    assert len(ranges) == 1
    assert ranges[0].start_date == "2026-01-01"
    assert ranges[0].end_date_exclusive == exact_threshold_end


def test_plan_ticker_update_handles_skip_and_update_cases_without_mutating_candidate():
    equal_candidate = StockUpdateTickerCandidate(
        ticker="AAA", first_date="2026-01-01", last_date="2026-05-10", market="usa"
    )
    later_candidate = StockUpdateTickerCandidate(
        ticker="BBB", first_date="2026-01-01", last_date="2026-05-11", market="usa"
    )
    update_candidate = StockUpdateTickerCandidate(
        ticker="CCC", first_date="2026-01-01", last_date="2026-05-09", market="usa"
    )

    equal_plan = plan_ticker_update(
        candidate=equal_candidate,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
    )
    later_plan = plan_ticker_update(
        candidate=later_candidate,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
    )
    update_plan = plan_ticker_update(
        candidate=update_candidate,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
    )
    override_plan = plan_ticker_update(
        candidate=update_candidate,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        start_override="2026-05-15",
    )

    assert equal_plan.needs_update is False
    assert equal_plan.skip_reason == "already_current"
    assert equal_plan.date_ranges == []
    assert equal_plan.update_start_date is None
    assert equal_plan.fetch_until_exclusive is None

    assert later_plan.needs_update is False
    assert later_plan.skip_reason == "already_current"

    assert update_plan.needs_update is True
    assert update_plan.update_start_date == "2026-05-10"
    assert update_plan.fetch_until_exclusive == "2026-05-17"
    assert [(item.start_date, item.end_date_exclusive) for item in update_plan.date_ranges] == [
        ("2026-05-10", "2026-05-17")
    ]
    assert update_plan.skip_reason is None

    assert override_plan.needs_update is True
    assert override_plan.update_start_date == "2026-05-15"
    assert [(item.start_date, item.end_date_exclusive) for item in override_plan.date_ranges] == [
        ("2026-05-15", "2026-05-17")
    ]

    assert update_candidate.last_date == "2026-05-09"
    assert update_candidate.market == "usa"


def test_plan_ticker_updates_preserves_order_and_includes_skipped_and_updates():
    candidates = [
        StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-05-10", "usa"),
        StockUpdateTickerCandidate("BBB", "2026-01-01", "2026-05-09", "omxh"),
        StockUpdateTickerCandidate("CCC", "2026-01-01", "2026-05-11", "usa"),
    ]

    plans = plan_ticker_updates(
        candidates=candidates,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
    )

    assert [plan.candidate.ticker for plan in plans] == ["AAA", "BBB", "CCC"]
    assert [plan.needs_update for plan in plans] == [False, True, False]
    assert [plan.skip_reason for plan in plans] == ["already_current", None, "already_current"]

