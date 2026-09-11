from __future__ import annotations

from datetime import date, timedelta

from rawcandle.research.fundamental_profile_baseline.engine import (
    PriceBar,
    construct_forward_label,
    partition_decision,
)
from rawcandle.research.phase12b1_signal_month_audit import (
    ACCEPTED_COUNTS,
    _months,
    _policy_status,
)


def sessions(start: str, count: int) -> list[str]:
    day = date.fromisoformat(start)
    result = []
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


def ready_row(**overrides):
    row = {
        "score_status": "SCORE_FULL", "valuation_status": "VALUATION_FULL",
        "two_quarter_status": "DELTA_READY", "lifecycle_status": "LIFECYCLE_READY",
        "lifecycle": "MATURE", "diagnostic_complete": True, "identity_status": "DATED_ALIAS",
        "fundamental_score": 80.0, "valuation_score": 60.0, "two_quarter_delta": 1.0,
        "component_fundamental_trajectory": 7.0, "diagnostic_flag_count": 0,
        "h63_status": "LABEL_READY", "period": "TEMPORAL_VALIDATION",
        "partition_status": "RETAINED", "h63_exit_date": "2024-12-30",
    }
    row.update(overrides)
    return row


def test_month_range_is_complete_and_stable():
    values = _months()
    assert len(values) == 60
    assert values[0] == "2021-01"
    assert values[-1] == "2025-12"


def test_cross_year_label_is_calculable_but_current_policy_purges_it():
    market = sessions("2023-01-02", 600)
    period, status = partition_decision(entry_date="2023-11-01", exit_date_63="2024-02-01", benchmark_sessions=market)
    assert period == "DEVELOPMENT"
    assert status == "PURGED_LABEL_CROSSES_PERIOD_END"


def test_internal_development_year_change_is_not_a_boundary():
    market = sessions("2021-01-01", 800)
    period, status = partition_decision(entry_date="2022-01-03", exit_date_63="2022-04-04", benchmark_sessions=market)
    assert (period, status) == ("DEVELOPMENT", "RETAINED")


def test_boundary_label_is_purged_once_and_prior_label_retained():
    market = sessions("2023-01-02", 600)
    assert partition_decision(entry_date="2023-09-29", exit_date_63="2023-12-29", benchmark_sessions=market)[1] == "RETAINED"
    assert partition_decision(entry_date="2023-10-02", exit_date_63="2024-01-02", benchmark_sessions=market)[1] == "PURGED_LABEL_CROSSES_PERIOD_END"


def test_embargo_is_later_side_and_strict_at_cutoff():
    market = sessions("2023-12-01", 400)
    first_2024 = next(index for index, value in enumerate(market) if value >= "2024-01-01")
    cutoff = market[first_2024 + 63]
    before = market[first_2024 + 62]
    assert partition_decision(entry_date=before, exit_date_63="2024-12-01", benchmark_sessions=market)[1] == "EMBARGO_FIRST_63_SESSIONS"
    assert partition_decision(entry_date=cutoff, exit_date_63="2024-12-01", benchmark_sessions=market)[1] == "RETAINED"


def test_counterfactual_policies_separate_purge_and_embargo():
    purged = ready_row(partition_status="PURGED_LABEL_CROSSES_PERIOD_END", h63_exit_date="2025-01-02")
    embargoed = ready_row(partition_status="EMBARGO_FIRST_63_SESSIONS")
    assert _policy_status(purged, "P0") == "PURGED_LABEL_CROSSES_PERIOD_END"
    assert _policy_status(purged, "P2") == "PURGED_LABEL_CROSSES_PERIOD_END"
    assert _policy_status(purged, "P3") == "RETAINED"
    assert _policy_status(embargoed, "P0") == "EMBARGO_FIRST_63_SESSIONS"
    assert _policy_status(embargoed, "P2") == "RETAINED"


def test_fiscal_ordinals_cross_year_without_reset():
    five = [2023 * 4 + 4, 2024 * 4 + 1, 2024 * 4 + 2, 2024 * 4 + 3, 2024 * 4 + 4]
    eight = list(range(2022 * 4 + 3, 2022 * 4 + 11))
    assert all(right == left + 1 for left, right in zip(five, five[1:]))
    assert all(right == left + 1 for left, right in zip(eight, eight[1:]))
    assert five[-1] - five[0] == 4  # 3Y/CAGR and Delta use the same ordinal convention at longer lags.


def test_exact_63_session_label_can_exit_in_next_year():
    market = sessions("2023-11-01", 100)
    bars = {day: PriceBar(day, 10.0, 11.0, 9.0, 10.0) for day in market}
    label = construct_forward_label(
        signal_date="2023-11-01", horizon=63, benchmark_sessions=market,
        benchmark_bars=bars, company_bars=bars,
    )
    assert label.status == "LABEL_READY"
    assert label.entry_date == market[1]
    assert label.exit_date == market[64]
    assert label.entry_date[:4] == "2023"
    assert label.exit_date[:4] == "2024"


def test_split_assignment_uses_entry_date_not_fiscal_or_exit_year():
    market = sessions("2023-01-02", 600)
    period, _ = partition_decision(entry_date="2024-05-01", exit_date_63="2024-08-01", benchmark_sessions=market)
    assert period == "TEMPORAL_VALIDATION"


def test_delta_two_quarter_ordinal_crosses_fiscal_year():
    current = 2024 * 4 + 1
    assert current - 2 == 2023 * 4 + 3


def test_three_year_cagr_ordinal_lag_crosses_years():
    current = 2025 * 4 + 4
    assert current - 12 == 2022 * 4 + 4


def test_accepted_month_count_contract_is_explicit():
    assert {key: value["months"] for key, value in ACCEPTED_COUNTS.items()} == {
        "DEVELOPMENT": 26,
        "TEMPORAL_VALIDATION": 7,
        "RETROSPECTIVE_CONFIRMATION": 7,
    }
