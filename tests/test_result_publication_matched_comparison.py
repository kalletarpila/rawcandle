from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.research.result_publication_matched_comparison import (
    absolute_gap_bucket,
    build_matched_comparison,
    load_event_window,
    market_cap_bucket,
    match_events,
    pre_event_trend_bucket,
    review_same_effective_day_cases,
    write_research_outputs,
)


def _event(
    company_id: int,
    status: str,
    *,
    year: int = 2025,
    gap: float = 2.0,
    trend: float = 2.0,
    method: str = "CANONICAL_VERIFIED",
) -> dict[str, object]:
    return {
        "company_id": company_id,
        "ticker": f"T{company_id}",
        "fiscal_year": year,
        "fiscal_quarter": "Q1",
        "research_status": status,
        "research_method": method,
        "D0_date": f"{year}-05-08",
        "date_Dm1": f"{year}-05-07",
        "date_D0": f"{year}-05-08",
        "date_Dp1": f"{year}-05-09",
        "first_full_post_result_trading_date": f"{year}-05-08",
        "gap_pct": gap,
        "return_Dm5_to_Dm1": trend,
        "D0_close_return_pct": gap + 0.5,
        "return_D5": gap + 1,
        "return_D10": gap + 2,
        "return_D20": gap + 3,
        "relative_return_D5": gap - 1,
        "relative_return_D20": gap - 2,
        "largest_move_day": "D0",
        "Dm1_close": 100,
        "D0_open": 101,
        "D0_close": 102,
        "Dp1_close": 101,
        "D0_abs_close_move_pct": 2,
        "D1_abs_close_move_pct": 1,
    }


def test_bucket_boundaries_are_explicit() -> None:
    assert [absolute_gap_bucket(value) for value in (0, 1, 3, 5, 10)] == [
        "0_TO_1",
        "1_TO_3",
        "3_TO_5",
        "5_TO_10",
        "GT_10",
    ]
    assert [pre_event_trend_bucket(value) for value in (-5, -1, 1, 5)] == [
        "STRONG_NEGATIVE",
        "FLAT",
        "FLAT",
        "STRONG_POSITIVE",
    ]
    assert [market_cap_bucket(value, (100, 200)) for value in (99, 100, 199, 200)] == [
        "SMALL",
        "MID",
        "MID",
        "LARGE",
    ]


def test_matching_is_same_year_nearest_and_deterministic() -> None:
    rows = [
        _event(1, "EXACT", gap=2.1, trend=2.2),
        _event(2, "EXACT", gap=2.7, trend=2.1),
        _event(3, "EXACT", year=2026, gap=2.01, trend=2.0),
        _event(4, "HEURISTIC_HIGH", gap=2.0, trend=2.0, method="YAHOO_NEAR_UNIQUE_SEC"),
        _event(5, "HEURISTIC_HIGH", gap=2.6, trend=2.0, method="SEC_V2_STRONG_INITIAL"),
        _event(6, "EXACT", gap=8.0, trend=-8.0),
        _event(7, "EXACT", gap=0.2, trend=0.0),
        _event(8, "EXACT", gap=12.0, trend=8.0),
        _event(9, "EXACT", year=2026, gap=8.0, trend=-8.0),
    ]
    caps = {company_id: 500.0 for company_id in range(1, 10)}
    first = match_events(rows, caps)
    second = match_events(list(reversed(rows)), caps)
    assert first[0] == second[0]
    assert [(row["high_company_id"], row["exact_company_id"]) for row in first[0]] == [
        (4, 1),
        (5, 2),
    ]
    assert all(row["event_year"] == 2025 for row in first[0])
    assert len({row["exact_company_id"] for row in first[0]}) == 2


def test_tie_break_and_unmatched_high_are_stable() -> None:
    rows = [
        _event(1, "EXACT", gap=2.0, trend=1.5),
        _event(2, "EXACT", gap=2.0, trend=2.5),
        _event(3, "HEURISTIC_HIGH", gap=2.0, trend=2.0),
        _event(4, "HEURISTIC_HIGH", gap=2.0, trend=2.0),
        _event(5, "HEURISTIC_HIGH", gap=2.0, trend=2.0),
        _event(6, "EXACT", gap=8.0, trend=-8.0),
    ]
    caps = {company_id: 500.0 for company_id in range(1, 6)}
    matches, unmatched, _, _ = match_events(rows, caps)
    assert matches[0]["exact_company_id"] == 1
    assert len(matches) == 2
    assert len(unmatched) == 1
    assert unmatched[0]["unmatched_reason"] == "NO_UNUSED_EXACT_IN_STRATUM"


def test_missing_market_cap_is_unmatched() -> None:
    rows = [
        _event(1, "EXACT"),
        _event(2, "HEURISTIC_HIGH"),
        _event(3, "EXACT", gap=8, trend=-8),
        _event(4, "EXACT", gap=12, trend=8),
    ]
    _, unmatched, _, _ = match_events(rows, {1: 100.0, 3: 300.0, 4: 500.0})
    assert [(row["company_id"], row["unmatched_reason"]) for row in unmatched] == [
        (2, "MARKET_CAP_UNAVAILABLE")
    ]


def test_summary_has_paired_differences_and_zero_post_match_imbalance() -> None:
    rows = [
        _event(1, "EXACT", gap=1.5),
        _event(2, "HEURISTIC_HIGH", gap=2.5, method="YAHOO_NEAR_UNIQUE_SEC"),
        _event(3, "EXACT", gap=8, trend=-8),
    ]
    result = build_matched_comparison(rows, {1: 100.0, 2: 100.0, 3: 300.0})
    paired = result.summary["paired_differences_high_minus_exact"]
    assert paired["D0_close_return_pct"]["median"] == pytest.approx(1.0)
    assert result.summary["coverage"]["control_reuse"]["maximum_uses"] == 1
    assert all(
        value["total_variation_percentage_points"] == 0
        for value in result.summary["balance"]["after"]["categorical"].values()
    )
    assert result.summary["balance"]["after"]["numeric"]["absolute_gap_pct"]["HIGH"]["n"] == 1


def test_same_effective_day_qa_confirms_common_boundary(tmp_path: Path) -> None:
    database = tmp_path / "canonical.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE v4_result_publication_evidence (company_id INTEGER, fiscal_year INTEGER, "
            "fiscal_quarter TEXT, source_type TEXT, disposition TEXT, source_timestamp_utc TEXT, "
            "source_reference TEXT, accession_number TEXT)"
        )
        connection.executemany(
            "INSERT INTO v4_result_publication_evidence VALUES (?,?,?,?,?,?,?,?)",
            [
                (1, 2025, "Q1", "SEC_8K_ITEM_2_02", "CONFLICT", "2025-05-07T20:30:00Z", "a", "1"),
                (1, 2025, "Q1", "SEC_8K_ITEM_2_02", "CONFLICT", "2025-05-08T11:00:00Z", "b", "2"),
            ],
        )
    event = _event(1, "HEURISTIC_HIGH", method="ALL_CANDIDATES_SAME_EFFECTIVE_DAY")
    yahoo = [{**event, "yahoo_event_timestamp": "2025-05-08T07:00:00-04:00"}]
    result = review_same_effective_day_cases([event], database, yahoo)
    assert result[0]["candidate_implies_different_boundary"] is False
    assert result[0]["classification"] == "BOUNDARY_CONFIRMED"


def test_same_effective_day_qa_flags_alternative_boundary(tmp_path: Path) -> None:
    database = tmp_path / "canonical.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE v4_result_publication_evidence (company_id INTEGER, fiscal_year INTEGER, "
            "fiscal_quarter TEXT, source_type TEXT, disposition TEXT, source_timestamp_utc TEXT, "
            "source_reference TEXT, accession_number TEXT)"
        )
        connection.execute(
            "INSERT INTO v4_result_publication_evidence VALUES (1,2025,'Q1','SEC_8K_ITEM_2_02',"
            "'CONFLICT','2025-05-08T20:30:00Z','a','1')"
        )
    event = _event(1, "HEURISTIC_HIGH", method="ALL_CANDIDATES_SAME_EFFECTIVE_DAY")
    result = review_same_effective_day_cases([event], database, [])
    assert result[0]["classification"] == "BOUNDARY_QUESTIONABLE"


def test_malformed_event_metadata_is_rejected(tmp_path: Path) -> None:
    rows = [_event(1, "EXACT"), _event(2, "HEURISTIC_HIGH")]
    source = tmp_path / "events.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = tmp_path / "events.metadata.json"
    metadata.write_text(
        json.dumps({"artifact_version": "wrong", "output_csv_sha256": digest}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="VERSION_INVALID"):
        load_event_window(source, metadata, expected_sha256=digest, expected_rows=2)


def test_repeated_output_is_byte_deterministic(tmp_path: Path) -> None:
    rows = [
        _event(1, "EXACT", gap=1.5),
        _event(2, "HEURISTIC_HIGH", gap=2.5, method="YAHOO_NEAR_UNIQUE_SEC"),
        _event(3, "EXACT", gap=8, trend=-8),
    ]
    result = build_matched_comparison(rows, {1: 100.0, 2: 100.0, 3: 300.0})
    sources = []
    for name in ("event.csv", "event.json", "market.db", "canonical.db", "yahoo.json"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        sources.append(path)
    output = tmp_path / "matched.csv"
    metadata = tmp_path / "matched.metadata.json"
    qa = tmp_path / "qa.csv"
    kwargs = dict(
        input_event_csv=sources[0],
        input_event_metadata=sources[1],
        market_cap_db=sources[2],
        canonical_db=sources[3],
        yahoo_observations_path=sources[4],
        generated_at_utc="2026-10-03T00:00:00Z",
    )
    qa_rows = [{"classification": "BOUNDARY_CONFIRMED", "ticker": "T", "fiscal_year": 2025, "fiscal_quarter": "Q1"}]
    write_research_outputs(result, qa_rows, output, metadata, qa, **kwargs)
    first = output.read_bytes(), metadata.read_bytes(), qa.read_bytes()
    write_research_outputs(result, qa_rows, output, metadata, qa, **kwargs)
    assert (output.read_bytes(), metadata.read_bytes(), qa.read_bytes()) == first
