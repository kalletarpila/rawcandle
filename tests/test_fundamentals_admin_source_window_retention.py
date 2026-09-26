from __future__ import annotations

from copy import deepcopy

from rawcandle.fundamentals.admin.refresh_fundamentals import (
    AGED_OUT_OF_SOURCE_WINDOW,
    AMBIGUOUS_SOURCE_REMOVAL,
    FINANCIAL_FIELDS,
    RETAINED_OUTSIDE_SOURCE_WINDOW,
    SOURCE_HISTORY_CHANGE,
    TRUE_SOURCE_REMOVAL,
    build_source_history_merge,
    compare_ticker_histories,
    history_fingerprints,
    normalize_source_row,
    source_key,
    validate_complete_history,
)


def row(
    *,
    dimension: str = "ARQ",
    date: str,
    reportperiod: str,
    fiscalperiod: str,
    revenue: int = 100,
) -> dict[str, object]:
    value: dict[str, object] = {
        "ticker": "TEST",
        "dimension": dimension,
        "date": date,
        "reportperiod": reportperiod,
        "calendardate": reportperiod,
        "fiscalperiod": fiscalperiod,
        "lastupdated": "2026-09-20",
    }
    value.update({field: None for field in FINANCIAL_FIELDS})
    value.update({"revenue": revenue, "netinc": 10, "sharesbas": 5})
    return value


def paired(value: dict[str, object]) -> dict[str, object]:
    return dict(value, dimension="MRQ", date=str(value["reportperiod"]))


def current_history(arq: list[dict[str, object]], mrq: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for dimension, values in (("ARQ", arq), ("MRQ", mrq)):
        normalized = []
        for value in values:
            item = normalize_source_row(value)
            for key in ("_history_retention_status", "_history_retention_evidence"):
                if key in value:
                    item[key] = deepcopy(value[key])
            normalized.append(item)
        output[dimension] = {
            "rows": tuple(normalized),
            "current_row_count": len(normalized),
            "legacy_versions_collapsed": 0,
            "legacy_source_version_ambiguities": [],
            "invalid_rows": [],
            **history_fingerprints(normalized),
        }
    return output


def source_history(arq: list[dict[str, object]], mrq: list[dict[str, object]]):
    return {
        "ARQ": validate_complete_history(arq, ticker="TEST", dimension="ARQ"),
        "MRQ": validate_complete_history(mrq, ticker="TEST", dimension="MRQ"),
    }


def boundary_rows():
    old = row(date="2016-08-15", reportperiod="2016-06-30", fiscalperiod="2016-Q2")
    latest = row(date="2026-08-15", reportperiod="2026-06-30", fiscalperiod="2026-Q2", revenue=200)
    return old, latest


def test_oldest_arq_mrq_boundary_pair_is_retained() -> None:
    old, latest = boundary_rows()
    current = current_history([old, latest], [paired(old), paired(latest)])
    source = source_history([latest], [paired(latest)])
    result = compare_ticker_histories("TEST", current, source)
    plan = build_source_history_merge("TEST", current, source)

    assert result["classification"] == SOURCE_HISTORY_CHANGE
    assert result["source_history_action"] == {
        "label": "Retain outside source window",
        "newly_aged_out_source_rows": 2,
        "retained_arq": 1,
        "retained_mrq": 1,
        "already_retained_carry_forward": 0,
        "true_source_removals": 0,
        "ambiguous_removals": 0,
        "current_source_reappearances": 0,
    }
    assert {event["event"] for event in plan["events"]} == {AGED_OUT_OF_SOURCE_WINDOW}
    assert all(
        row["_history_retention_status"] == RETAINED_OUTSIDE_SOURCE_WINDOW
        for dimension in ("ARQ", "MRQ")
        for row in plan["dimensions"][dimension]["merged_rows"]
        if row["reportperiod"] == "2016-06-30"
    )
    retained_arq = next(
        item for item in plan["dimensions"]["ARQ"]["merged_rows"]
        if item["reportperiod"] == "2016-06-30"
    )
    assert {field: retained_arq[field] for field in FINANCIAL_FIELDS} == {
        field: normalize_source_row(old)[field] for field in FINANCIAL_FIELDS
    }


def test_nams_like_interior_key_is_true_removal_and_alternate_arq_survives() -> None:
    oldest = row(date="2020-11-20", reportperiod="2020-10-07", fiscalperiod="2020-Q3")
    alternate = row(date="2022-10-13", reportperiod="2022-06-30", fiscalperiod="2022-Q2", revenue=150)
    obsolete = row(date="2022-11-28", reportperiod="2022-06-30", fiscalperiod="2022-Q2", revenue=151)
    latest = row(date="2026-08-05", reportperiod="2026-06-30", fiscalperiod="2026-Q2", revenue=200)
    mrq = [paired(oldest), paired(alternate), paired(latest)]
    current = current_history([oldest, alternate, obsolete, latest], mrq)
    source = source_history([oldest, alternate, latest], mrq)
    result = compare_ticker_histories("TEST", current, source)
    plan = build_source_history_merge("TEST", current, source)

    assert result["classification"] == "SOURCE_REMOVAL"
    assert result["source_history_action"]["true_source_removals"] == 1
    assert plan["events"][0]["event"] == TRUE_SOURCE_REMOVAL
    merged_keys = {source_key(item) for item in plan["dimensions"]["ARQ"]["merged_rows"]}
    assert source_key(obsolete) not in merged_keys
    assert source_key(alternate) in merged_keys


def test_multi_row_oldest_prefix_is_retained_without_interior_expansion() -> None:
    first = row(date="2015-08-15", reportperiod="2015-06-30", fiscalperiod="2015-Q2")
    second = row(date="2016-08-15", reportperiod="2016-06-30", fiscalperiod="2016-Q2")
    latest = row(date="2026-08-15", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    current = current_history([first, second, latest], [paired(first), paired(second), paired(latest)])
    source = source_history([latest], [paired(latest)])
    plan = build_source_history_merge("TEST", current, source)
    assert len(plan["events"]) == 4
    assert {event["event"] for event in plan["events"]} == {AGED_OUT_OF_SOURCE_WINDOW}
    assert len(plan["dimensions"]["ARQ"]["merged_rows"]) == 3


def test_recent_oldest_boundary_and_companion_conflict_are_ambiguous() -> None:
    recent = row(date="2022-08-15", reportperiod="2022-06-30", fiscalperiod="2022-Q2")
    latest = row(date="2026-08-15", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    current = current_history([recent, latest], [paired(recent), paired(latest)])
    source = source_history([latest], [paired(latest)])
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == AMBIGUOUS_SOURCE_REMOVAL

    older_mrq = row(
        dimension="MRQ", date="2015-03-31", reportperiod="2015-03-31",
        fiscalperiod="2015-Q1",
    )
    old, latest = boundary_rows()
    current = current_history([old, latest], [older_mrq, paired(old), paired(latest)])
    source = source_history([latest], [older_mrq, paired(latest)])
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert all(event["event"] == AMBIGUOUS_SOURCE_REMOVAL for event in result["source_history_events"])


def aytu_style_histories(*, latest_fiscal: str = "2026-Q4"):
    old_arq = row(date="2016-09-01", reportperiod="2016-06-30", fiscalperiod="2016-Q4")
    replacement_arq = row(
        date="2016-10-25", reportperiod="2016-06-30", fiscalperiod="2016-Q4", revenue=101,
    )
    latest_arq = row(
        date="2026-08-15", reportperiod="2026-06-30",
        fiscalperiod=latest_fiscal, revenue=200,
    )
    old_mrq = row(
        dimension="MRQ", date="2016-06-30", reportperiod="2016-06-30",
        fiscalperiod="2016-Q4",
    )
    next_mrq = row(
        dimension="MRQ", date="2016-09-30", reportperiod="2016-09-30",
        fiscalperiod="2017-Q1",
    )
    latest_mrq = paired(latest_arq)
    current = current_history(
        [old_arq, replacement_arq, latest_arq],
        [old_mrq, next_mrq, latest_mrq],
    )
    source = source_history(
        [replacement_arq, latest_arq],
        [next_mrq, latest_mrq],
    )
    return current, source, old_arq, replacement_arq, old_mrq


def test_aytu_style_replacement_and_aged_companion_resolve_independently() -> None:
    current, source, old_arq, replacement_arq, old_mrq = aytu_style_histories()

    result = compare_ticker_histories("TEST", current, source)
    plan = build_source_history_merge("TEST", current, source)

    assert result["classification"] == "SOURCE_REMOVAL"
    assert result["source_history_action"]["true_source_removals"] == 1
    assert result["source_history_action"]["newly_aged_out_source_rows"] == 1
    assert result["source_history_action"]["ambiguous_removals"] == 0
    events = {event["dimension"]: event for event in result["source_history_events"]}
    assert events["ARQ"]["event"] == TRUE_SOURCE_REMOVAL
    assert events["ARQ"]["classification_reason"] == "SAME_FISCAL_SOURCE_KEY_REPLACEMENT"
    assert events["MRQ"]["event"] == AGED_OUT_OF_SOURCE_WINDOW
    assert events["MRQ"]["classification_reason"] == "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW"
    assert all(
        event["classification_reason"] != "COMPANION_DIMENSION_CONTRADICTION"
        for event in events.values()
    )
    merged_arq = {source_key(item) for item in plan["dimensions"]["ARQ"]["merged_rows"]}
    assert source_key(old_arq) not in merged_arq
    assert source_key(replacement_arq) in merged_arq
    retained_mrq = next(
        item for item in plan["dimensions"]["MRQ"]["merged_rows"]
        if source_key(item) == source_key(old_mrq)
    )
    assert retained_mrq["_history_retention_status"] == RETAINED_OUTSIDE_SOURCE_WINDOW


def test_aytu_style_exception_requires_complete_history_and_full_boundary() -> None:
    current, source, *_rows = aytu_style_histories()
    source["MRQ"] = validate_complete_history([], ticker="TEST", dimension="MRQ")
    incomplete = compare_ticker_histories("TEST", current, source)
    assert incomplete["classification"] == "REVIEW_REQUIRED"
    assert incomplete["review_reason"] == "COMPLETE_HISTORY_NOT_TRUSTED"

    current, source, *_rows = aytu_style_histories(latest_fiscal="2026-Q3")
    short = compare_ticker_histories("TEST", current, source)
    assert short["classification"] == "REVIEW_REQUIRED"
    assert short["source_history_action"]["ambiguous_removals"] == 1
    assert any(
        event["classification_reason"] == "BOUNDARY_FISCAL_WINDOW_TOO_SHORT"
        for event in short["source_history_events"]
    )


def test_aytu_style_exception_requires_explicit_current_replacement_key() -> None:
    current, source, old_arq, _replacement_arq, _old_mrq = aytu_style_histories()
    earlier = row(date="2015-08-15", reportperiod="2015-06-30", fiscalperiod="2015-Q4")
    latest_arq = max(source["ARQ"].rows, key=lambda item: str(item["reportperiod"]))
    current["ARQ"] = current_history([earlier, old_arq, latest_arq], [])["ARQ"]
    source["ARQ"] = validate_complete_history(
        [earlier, latest_arq], ticker="TEST", dimension="ARQ",
    )

    assert all(row["fiscalperiod"] != "2016-Q4" for row in source["ARQ"].rows)

    result = compare_ticker_histories("TEST", current, source)

    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["source_history_action"]["ambiguous_removals"] == 2
    assert {event["classification_reason"] for event in result["source_history_events"]} == {
        "COMPANION_DIMENSION_CONTRADICTION"
    }


def test_aytu_style_exception_rejects_competing_replacement_keys() -> None:
    current, source, _old_arq, replacement_arq, _old_mrq = aytu_style_histories()
    competing = dict(replacement_arq, date="2016-11-01", revenue=102)
    latest_arq = max(source["ARQ"].rows, key=lambda item: str(item["reportperiod"]))
    source["ARQ"] = validate_complete_history(
        [replacement_arq, competing, latest_arq], ticker="TEST", dimension="ARQ",
    )

    result = compare_ticker_histories("TEST", current, source)

    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["source_history_action"]["ambiguous_removals"] == 2
    assert {event["classification_reason"] for event in result["source_history_events"]} == {
        "COMPANION_DIMENSION_CONTRADICTION"
    }


def test_yyai_style_short_windows_remain_review_required() -> None:
    arq_specs = [
        ("2017-Q3", "2017-01-31", "2017-03-30"),
        ("2017-Q4", "2017-04-30", "2017-08-03"),
        ("2017-Q4", "2017-04-30", "2017-08-04"),
        ("2018-Q1", "2017-07-31", "2017-09-20"),
        ("2018-Q2", "2017-10-31", "2017-12-18"),
        ("2018-Q3", "2018-01-31", "2018-03-20"),
        ("2018-Q4", "2018-04-30", "2018-08-14"),
        ("2019-Q1", "2018-07-31", "2018-09-17"),
        ("2019-Q2", "2018-10-31", "2018-12-18"),
        ("2019-Q3", "2019-01-31", "2019-03-15"),
        ("2019-Q4", "2019-04-30", "2019-08-06"),
        ("2020-Q1", "2019-07-31", "2019-09-04"),
        ("2020-Q2", "2019-10-31", "2019-12-16"),
    ]
    mrq_specs = [
        ("2017-Q1", "2016-07-31"), ("2017-Q2", "2016-10-31"),
        ("2017-Q3", "2017-01-31"), ("2017-Q4", "2017-04-30"),
        ("2018-Q1", "2017-07-31"), ("2018-Q2", "2017-10-31"),
        ("2018-Q3", "2018-01-31"), ("2018-Q4", "2018-04-30"),
        ("2019-Q1", "2018-07-31"), ("2019-Q2", "2018-10-31"),
    ]
    arq_missing = [
        row(fiscalperiod=fiscal, reportperiod=reportperiod, date=filing_date)
        for fiscal, reportperiod, filing_date in arq_specs
    ]
    mrq_missing = [
        row(dimension="MRQ", fiscalperiod=fiscal, reportperiod=reportperiod, date=reportperiod)
        for fiscal, reportperiod in mrq_specs
    ]
    latest_arq = row(
        fiscalperiod="2027-Q1", reportperiod="2026-07-31", date="2026-09-15",
    )
    latest_mrq = row(
        dimension="MRQ", fiscalperiod="2027-Q1",
        reportperiod="2026-07-31", date="2026-07-31",
    )
    current = current_history([*arq_missing, latest_arq], [*mrq_missing, latest_mrq])
    source = source_history([latest_arq], [latest_mrq])

    result = compare_ticker_histories("TEST", current, source)

    assert result["classification"] == "REVIEW_REQUIRED"
    assert len(result["source_history_events"]) == 23
    assert result["source_history_action"]["newly_aged_out_source_rows"] == 1
    assert result["source_history_action"]["ambiguous_removals"] == 22
    assert {event["classification_reason"] for event in result["source_history_events"]} == {
        "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW",
        "BOUNDARY_FISCAL_WINDOW_TOO_SHORT",
    }


def test_flws_like_week_based_boundary_uses_fiscal_span_not_calendar_days() -> None:
    old = row(date="2016-09-16", reportperiod="2016-07-03", fiscalperiod="2016-Q4")
    next_quarter = row(date="2016-11-14", reportperiod="2016-10-02", fiscalperiod="2017-Q1")
    latest = row(date="2026-09-11", reportperiod="2026-06-28", fiscalperiod="2026-Q4")
    current = current_history([old, next_quarter, latest], [paired(old), paired(next_quarter), paired(latest)])
    source = source_history([next_quarter, latest], [paired(next_quarter), paired(latest)])

    result = compare_ticker_histories("TEST", current, source)

    assert result["classification"] == SOURCE_HISTORY_CHANGE
    assert result["source_history_action"]["newly_aged_out_source_rows"] == 2
    assert {event["boundary_fiscal_quarter_span"] for event in result["source_history_events"]} == {41}
    assert all(event["expected_quarterly_window_covered"] for event in result["source_history_events"])
    assert {event["classification_reason"] for event in result["source_history_events"]} == {
        "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW"
    }


def test_love_like_same_fiscal_boundary_replacement_is_true_removal() -> None:
    old = row(
        dimension="MRQ", date="2017-01-29", reportperiod="2017-01-29",
        fiscalperiod="2017-Q4",
    )
    replacement = row(
        dimension="MRQ", date="2017-02-04", reportperiod="2017-02-04",
        fiscalperiod="2017-Q4", revenue=101,
    )
    latest = row(
        dimension="MRQ", date="2026-08-02", reportperiod="2026-08-02",
        fiscalperiod="2027-Q2", revenue=200,
    )
    arq_latest = row(date="2026-09-10", reportperiod="2026-08-02", fiscalperiod="2027-Q2")
    current = current_history([arq_latest], [old, latest])
    source = source_history([arq_latest], [replacement, latest])

    result = compare_ticker_histories("TEST", current, source)

    assert result["classification"] == "SOURCE_REMOVAL"
    assert result["source_history_action"]["true_source_removals"] == 1
    event = result["source_history_events"][0]
    assert event["event"] == TRUE_SOURCE_REMOVAL
    assert event["classification_reason"] == "SAME_FISCAL_SOURCE_KEY_REPLACEMENT"
    assert event["boundary_fiscal_quarter_span"] == 39
    assert event["same_fiscal_current_keys"] == [{
        "ticker": "TEST", "dimension": "MRQ", "date": "2017-02-04",
        "reportperiod": "2017-02-04",
    }]


def test_arq_and_mrq_boundaries_are_independent_when_not_contradictory() -> None:
    old, latest = boundary_rows()
    older_mrq = row(
        dimension="MRQ", date="2015-03-31", reportperiod="2015-03-31",
        fiscalperiod="2015-Q1",
    )
    current = current_history([old, latest], [older_mrq, paired(latest)])
    source = source_history([latest], [older_mrq, paired(latest)])
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == SOURCE_HISTORY_CHANGE
    assert result["source_history_action"]["retained_arq"] == 1
    assert result["source_history_action"]["retained_mrq"] == 0


def test_untrusted_history_can_never_authorize_retention() -> None:
    old, latest = boundary_rows()
    current = current_history([old, latest], [paired(old), paired(latest)])
    source = source_history([latest], [])
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == "COMPLETE_HISTORY_NOT_TRUSTED"


def test_already_retained_absence_is_stable_and_does_not_repeat_event() -> None:
    old, latest = boundary_rows()
    first_current = current_history([old, latest], [paired(old), paired(latest)])
    source = source_history([latest], [paired(latest)])
    first = build_source_history_merge("TEST", first_current, source)
    second_current = current_history(
        list(first["dimensions"]["ARQ"]["merged_rows"]),
        list(first["dimensions"]["MRQ"]["merged_rows"]),
    )
    second = build_source_history_merge("TEST", second_current, source)
    result = compare_ticker_histories("TEST", second_current, source)

    assert result["classification"] == "NO_EFFECTIVE_CHANGE"
    assert second["action"]["newly_aged_out_source_rows"] == 0
    assert second["action"]["already_retained_carry_forward"] == 2
    assert second["current_generation_fingerprint"] == second["merged_generation_fingerprint"]


def test_reappearing_true_source_key_wins_and_clears_retained_state() -> None:
    old, latest = boundary_rows()
    first_current = current_history([old, latest], [paired(old), paired(latest)])
    first_source = source_history([latest], [paired(latest)])
    first = build_source_history_merge("TEST", first_current, first_source)
    retained_current = current_history(
        list(first["dimensions"]["ARQ"]["merged_rows"]),
        list(first["dimensions"]["MRQ"]["merged_rows"]),
    )
    revised_old = dict(old, revenue=999)
    revised_mrq = dict(paired(old), revenue=998)
    source = source_history([revised_old, latest], [revised_mrq, paired(latest)])
    plan = build_source_history_merge("TEST", retained_current, source)
    result = compare_ticker_histories("TEST", retained_current, source)

    assert plan["action"]["current_source_reappearances"] == 2
    assert result["classification"] == "HISTORICAL_REVISION"
    arq = {source_key(item): item for item in plan["dimensions"]["ARQ"]["merged_rows"]}
    assert arq[source_key(old)]["revenue"] == 999
    assert arq[source_key(old)].get("_history_retention_status") is None


def test_newer_current_key_for_retained_fiscal_quarter_remains_authoritative() -> None:
    old, latest = boundary_rows()
    initial = current_history([old, latest], [paired(old), paired(latest)])
    narrowed = source_history([latest], [paired(latest)])
    retained = build_source_history_merge("TEST", initial, narrowed)
    retained_current = current_history(
        list(retained["dimensions"]["ARQ"]["merged_rows"]),
        list(retained["dimensions"]["MRQ"]["merged_rows"]),
    )
    newer_key = dict(old, date="2016-09-01", revenue=777, lastupdated="2026-09-21")
    source = source_history([newer_key, latest], [paired(latest)])
    plan = build_source_history_merge("TEST", retained_current, source)

    same_quarter = [
        item for item in plan["dimensions"]["ARQ"]["merged_rows"]
        if item["fiscalperiod"] == "2016-Q2"
    ]
    assert len(same_quarter) == 2
    assert next(item for item in same_quarter if item["date"] == "2016-09-01")["revenue"] == 777
    assert next(item for item in same_quarter if item["date"] == "2016-08-15")[
        "_history_retention_status"
    ] == RETAINED_OUTSIDE_SOURCE_WINDOW


def test_trigger_metadata_cannot_change_retention_classification_or_fingerprint() -> None:
    old, latest = boundary_rows()
    current = current_history([old, latest], [paired(old), paired(latest)])
    source = source_history([latest], [paired(latest)])
    manual = build_source_history_merge("TEST", current, source)
    scheduler = build_source_history_merge("TEST", current, source)
    assert manual["events"] == scheduler["events"]
    assert manual["merged_generation_fingerprint"] == scheduler["merged_generation_fingerprint"]
