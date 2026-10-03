from rawcandle.research.forecast_revision_research import ordered_observations, summarize_forecast_revision_research


def test_fetch_order_keeps_unchanged_and_no_data_excludes_failures():
    rows = [
        {"fetch_order": i, "fetched_at_utc": "2026-09-28T12:00:00Z", "status": status}
        for i, status in [(4, "TRANSIENT_FAILURE"), (3, "VALID_NO_DATA"),
                          (2, "SUCCESS_UNCHANGED"), (1, "SUCCESS_CHANGED")]
    ]
    assert [row["fetch_order"] for row in ordered_observations(rows)] == [1, 2, 3]


def test_frozen_boundaries_before_history_produce_empty_cohort():
    publications = [{"company_id": "1", "fiscal_year": "2026", "fiscal_quarter": "Q3",
                     "research_status": "HEURISTIC_HIGH", "first_full_post_result_trading_date": "2026-09-25"}]
    fetches = [{"company_id": 1, "fetched_at_utc": "2026-09-27T12:00:00Z", "status": "SUCCESS_UNCHANGED"}]
    summary = summarize_forecast_revision_research(publications, fetches)
    assert summary["events_inside_history_window"] == 0
    assert summary["successful_fiscal_fetches"] == 1


def test_exact_timestamp_takes_precedence_over_daily_boundary():
    publications = [{"company_id": "1", "fiscal_year": "2026", "fiscal_quarter": "Q3",
                     "research_status": "EXACT", "canonical_timestamp_utc": "2026-09-28T20:00:00Z",
                     "first_full_post_result_trading_date": "2026-09-29"}]
    fetches = [{"company_id": 1, "fetched_at_utc": stamp, "status": "SUCCESS_CHANGED"}
               for stamp in ["2026-09-28T12:00:00Z", "2026-09-28T21:00:00Z"]]
    assert summarize_forecast_revision_research(publications, fetches)["events_inside_history_window"] == 1


def test_empty_history_has_no_fabricated_window():
    assert summarize_forecast_revision_research([], []) == {
        "history_start": None, "history_end": None, "events_inside_history_window": 0}
