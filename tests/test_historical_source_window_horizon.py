from datetime import date

import pytest

from rawcandle.fundamentals.admin import refresh_fundamentals as r
from rawcandle.fundamentals.admin.refresh_review_queue import partition_changes
from tests.test_fundamentals_admin_source_window_retention import row, paired, current_history, source_history


def compare(old, incoming, **kwargs):
    return r.compare_ticker_histories(
        "TEST", current_history(old, [paired(a) for a in old]),
        source_history(incoming, [paired(a) for a in incoming]),
        as_of_date=date(2026, 10, 4), **kwargs,
    )


@pytest.mark.parametrize("period,expected", [
    ("2023-10-03", "SOURCE_HISTORY_CHANGE"),
    ("2023-10-04", "REVIEW_REQUIRED"),
    ("2023-10-05", "REVIEW_REQUIRED"),
])
def test_strict_cutoff(period, expected):
    old = row(date=period, reportperiod=period, fiscalperiod="2023-Q4")
    latest = row(date="2026-06-30", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    result = compare([old, latest], [latest])
    assert result["classification"] == expected
    if expected == "REVIEW_REQUIRED":
        assert result["review_reason"] == r.AMBIGUOUS_SOURCE_REMOVAL


def test_leap_calendar_cutoff_and_invalid_config():
    assert r.historical_source_window_policy(date(2024, 2, 29))["cutoff_date"] == "2021-02-28"
    for years in (-1, True, 1.5):
        with pytest.raises(ValueError): r.historical_source_window_policy(date(2026, 10, 4), years)


def test_multiple_old_absences_and_returned_financial_revision():
    a = row(date="2016-06-30", reportperiod="2016-06-30", fiscalperiod="2016-Q2")
    b = row(date="2016-09-30", reportperiod="2016-09-30", fiscalperiod="2016-Q3")
    c = row(date="2016-12-31", reportperiod="2016-12-31", fiscalperiod="2016-Q4")
    latest = row(date="2026-06-30", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    result = compare([a, b, c, latest], [dict(c, revenue=150), latest])
    assert result["changed_count"] == 2
    assert result["removed_count"] == 0
    assert result["classification"] == "HISTORICAL_REVISION"
    assert result["source_history_action"]["historical_retained_rows"] == 4
    assert partition_changes([result])["held"] == []
    assert result == compare([a, b, c, latest], [dict(c, revenue=150), latest])


def test_old_interior_disappearance_is_not_relaxed():
    a = row(date="2016-06-30", reportperiod="2016-06-30", fiscalperiod="2016-Q2")
    b = row(date="2016-09-30", reportperiod="2016-09-30", fiscalperiod="2016-Q3")
    c = row(date="2026-06-30", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    result = compare([a, b, c], [a, c])
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == r.TRUE_SOURCE_REMOVAL


def test_old_source_key_replacement_stays_strict():
    a = row(date="2016-09-30", reportperiod="2016-09-30", fiscalperiod="2016-Q3")
    c = row(date="2026-06-30", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    result = compare([a, c], [dict(a, date="2016-10-01"), c])
    assert result["classification"] == "REVIEW_REQUIRED"


def test_old_fiscal_reclassification_stays_strict():
    a = row(date="2016-09-30", reportperiod="2016-09-30", fiscalperiod="2016-Q3")
    c = row(date="2026-06-30", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    result = compare([a, c], [dict(a, fiscalperiod="2016-Q4"), c])
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == r.REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION


def test_disabled_horizon_preserves_short_boundary_blocker():
    a = row(date="2016-09-30", reportperiod="2016-09-30", fiscalperiod="2016-Q3")
    c = row(date="2026-06-30", reportperiod="2026-06-30", fiscalperiod="2026-Q2")
    assert compare([a, c], [c], historical_source_window_review_years=0)["classification"] == "REVIEW_REQUIRED"


def test_preview_queue_and_exact_test_policy_binding(tmp_path):
    import sqlite3
    from copy import deepcopy
    from tests.test_fundamentals_admin_refresh_preview import _create_preview_databases, PreviewClient, row as preview_row
    from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue, queue_path_for_run_root
    from rawcandle.fundamentals.admin.refresh_copy_runtime import revalidate_bound_source, StaleRefreshPreview

    paths = _create_preview_databases(tmp_path / "db")
    old = preview_row(filing_date="2020-09-30", reportperiod="2020-09-30", fiscalperiod="2020-Q3")
    with sqlite3.connect(paths.provider_db) as c:
        for dim in r.REFRESH_DIMENSIONS:
            observation = "old-" + dim
            item = dict(old, dimension=dim)
            c.execute("INSERT INTO provider_observation VALUES(?,?,1,1)", (observation, observation))
            fields = ["observation_id", *r.REFRESH_REQUEST_FIELDS]
            c.execute(f"INSERT INTO sharadar_fundamental_observation({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", [observation, *[item.get(f) for f in r.REFRESH_REQUEST_FIELDS]])
    client = PreviewClient([preview_row(revenue=150)], [preview_row(dimension="MRQ", revenue=150)])
    root = tmp_path / "operational" / "admin_runs"
    strict = r.run_preview(source_paths=paths, run_root=root, client=client, as_of_date=date(2026,10,4), historical_source_window_review_years=0)
    queue = RefreshReviewQueue(queue_path_for_run_root(root))
    old_item = queue.get("TEST")
    assert old_item["status"] == "OPEN"
    relaxed = r.run_preview(source_paths=paths, run_root=root, client=client, as_of_date=date(2026,10,4))["refresh_preview"]
    assert queue.get("TEST") == old_item
    assert relaxed["review_partition"]["held"] == []
    assert relaxed["ticker_changes"][0]["changed_count"] == 2
    actual = revalidate_bound_source(relaxed, paths, client)
    assert actual["changed_tickers"] == ["TEST"]
    drift = deepcopy(relaxed)
    drift["historical_source_window_policy"]["as_of_date"] = "2027-10-04"
    with pytest.raises(StaleRefreshPreview):
        revalidate_bound_source(drift, paths, client)

    clean_root = tmp_path / "clean" / "admin_runs"
    r.run_preview(source_paths=paths, run_root=clean_root, client=client, as_of_date=date(2026,10,4))
    assert RefreshReviewQueue(queue_path_for_run_root(clean_root)).get("TEST") is None
