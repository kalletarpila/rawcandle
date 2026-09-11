from __future__ import annotations

from rawcandle.research.fundamental_profile_baseline_v2.runner import (
    _ols_f,
    arm_gate,
    arm_rows,
    assign_corrected_periods,
    bootstrap_indices,
    effect_value,
    interval_audit,
)

import numpy as np


def row(company, month, *, fundamental=70.0, valuation=50.0, delta=0.0, excess=0.0):
    return {
        "company_id": company, "quarter_id": company, "entry_date": f"2024-{month:02d}-15",
        "h63_exit_date": f"2024-{min(month + 3, 12):02d}-15", "h63_excess_return": excess,
        "fundamental_score": fundamental, "valuation_score": valuation,
        "two_quarter_delta": delta, "diagnostic_flag_count": 0,
        "sector": "Technology", "lifecycle": "MATURE",
    }


def test_h5_effect_uses_only_within_h4_comparator():
    rows = [
        row(1, 1, fundamental=90, valuation=70, delta=2, excess=.20),
        row(2, 2, fundamental=90, valuation=70, delta=0, excess=.10),
        row(3, 3, fundamental=20, valuation=10, delta=0, excess=-.80),
    ]
    assert abs(effect_value(rows, "H5") - .10) < 1e-12
    treatment, comparator = arm_rows(rows, "H5")
    assert [item["company_id"] for item in treatment] == [1]
    assert [item["company_id"] for item in comparator] == [2]


def test_arm_gate_is_applied_to_each_arm():
    passing = {"rows": 100, "companies": 50, "months": 9, "entry_sessions": 30, "median_per_present_month": 3}
    assert arm_gate(passing)
    for field in ("rows", "companies", "months", "entry_sessions", "median_per_present_month"):
        failing = dict(passing)
        failing[field] -= 1
        assert not arm_gate(failing)


def test_zero_delta_is_h3_comparator():
    rows = [row(1, 1, delta=1), row(2, 2, delta=0), row(3, 3, delta=-1)]
    treatment, comparator = arm_rows(rows, "H3")
    assert [item["company_id"] for item in treatment] == [1]
    assert [item["company_id"] for item in comparator] == [2, 3]


def locked_sessions():
    start = np.datetime64("2023-03-01")
    stop = np.datetime64("2026-01-05")
    days = np.arange(start, stop, dtype="datetime64[D]")
    sessions = [str(day) for day in days if np.is_busday(day)]
    assert "2023-07-03" in sessions
    assert "2024-10-01" in sessions
    assert "2026-01-02" in sessions
    return sessions


def test_boundary_equality_is_purged_and_next_period_has_no_embargo(monkeypatch):
    monkeypatch.setattr(
        "rawcandle.research.fundamental_profile_baseline_v2.runner.eligibility_reason",
        lambda _row, *, require_label: "ELIGIBLE",
    )
    sessions = locked_sessions()
    validation_first = sessions.index("2023-07-03")
    rows = [
        {"entry_date": sessions[validation_first - 64], "h63_exit_date": sessions[validation_first - 1], "h63_status": "LABEL_READY"},
        {"entry_date": sessions[validation_first - 64], "h63_exit_date": sessions[validation_first], "h63_status": "LABEL_READY"},
        {"entry_date": "2023-07-03", "h63_exit_date": sessions[validation_first + 63], "h63_status": "LABEL_READY"},
    ]
    assign_corrected_periods(rows, sessions)
    assert rows[0]["partition_status"] == "RETAINED"
    assert rows[1]["partition_status"] == "PURGED_AT_NEXT_PERIOD_BOUNDARY"
    assert rows[2]["period"] == "TEMPORAL_VALIDATION"
    assert rows[2]["partition_status"] == "RETAINED"


def test_interval_audit_rejects_duplicate_endpoint_assignment():
    sessions = locked_sessions()
    def audit_row(company, quarter, entry, period):
        start = sessions.index(entry)
        return {
            "company_id": company, "quarter_id": quarter, "fiscal_year": 2023, "fiscal_quarter": 2,
            "source_availability_date": entry, "entry_date": entry, "h63_exit_date": sessions[start + 63],
            "period": period, "partition_status": "RETAINED", "common_eligibility": "ELIGIBLE",
            "h63_status": "LABEL_READY",
        }
    development = audit_row(2, 6, "2023-03-01", "DEVELOPMENT")
    validation = audit_row(1, 7, "2023-07-03", "TEMPORAL_VALIDATION")
    confirmation = audit_row(3, 8, "2024-10-01", "RETROSPECTIVE_CONFIRMATION")
    _, checks = interval_audit([development, validation, dict(validation), confirmation], sessions)
    assert checks["duplicate_endpoints"] == 1
    assert not checks["passed"]


def test_block_bootstrap_is_deterministic():
    sessions = locked_sessions()
    rows = [{"entry_date": day} for day in sessions[:100]]
    first = bootstrap_indices(rows, sessions, repetitions=3)
    second = bootstrap_indices(rows, sessions, repetitions=3)
    assert all(np.array_equal(left, right) for left, right in zip(first, second))


def test_partial_f_detects_added_interaction_columns():
    x = np.arange(1.0, 9.0)
    group = np.asarray([0.0] * 4 + [1.0] * 4)
    base = np.column_stack([np.ones(8), x, group])
    full = np.column_stack([base, x * group])
    y = x + 3.0 * x * group
    partial_f, partial_r2, _, _ = _ols_f(y, base, full)
    assert partial_f > 0
    assert partial_r2 > 0.99
