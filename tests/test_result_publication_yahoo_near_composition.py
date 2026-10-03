from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.research.result_publication_yahoo_near_composition import (
    YahooNearComposition,
    calculate_pre_event_proxies,
    load_ticker_classifications,
    match_yahoo_near,
    relaxation_level,
    summarize_yahoo_near_composition,
    tertile_bucket,
    tertile_cutoffs,
    write_composition_outputs,
)


def _prepared(
    company_id: int,
    method: str,
    *,
    sector: str = "Technology",
    liquidity: str | None = "MID",
    volatility: str | None = "MID",
    gap: float = 2.0,
    trend: float = 2.0,
) -> dict[str, object]:
    return {
        "company_id": company_id,
        "ticker": f"T{company_id}",
        "fiscal_year": 2025,
        "fiscal_quarter": "Q1",
        "research_method": method,
        "event_year": 2025,
        "sector": sector,
        "industry": "Software",
        "market": "usa",
        "market_cap_bucket": "MID",
        "absolute_gap_bucket": "1_TO_3",
        "pre_event_trend_bucket": "POSITIVE",
        "liquidity_bucket": liquidity,
        "volatility_bucket": volatility,
        "market_cap_proxy": 2_000_000_000.0,
        "absolute_gap_pct": gap,
        "pre_event_trend": trend,
        "median_dollar_volume_Dm20_to_Dm1": 10_000_000.0 * company_id,
        "realized_volatility_Dm20_to_Dm1": float(company_id),
        "D0_date": "2025-05-08",
        "date_Dm1": "2025-05-07",
        "Dm1_close": 100.0,
        "D0_open": 101.0,
        "D0_close": 102.0,
        "date_Dp1": "2025-05-09",
        "Dp1_close": 103.0,
        "largest_move_day": "D0",
        "gap_pct": gap,
        "D0_close_return_pct": gap + 0.5,
        "return_D5": gap + 1,
        "return_D10": gap + 2,
        "return_D20": gap + 3,
        "relative_return_D5": gap - 1,
        "relative_return_D20": gap - 2,
        "post_D0_to_D5": gap + 0.25,
        "post_D0_to_D10": gap + 0.75,
        "post_D0_to_D20": gap + 1.25,
    }


def test_sector_lookup_uses_ticker_meta(tmp_path: Path) -> None:
    database = tmp_path / "ohlc.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ticker_meta (ticker TEXT PRIMARY KEY, market TEXT, sector TEXT, industry TEXT)"
        )
        connection.execute(
            "INSERT INTO ticker_meta VALUES ('AAPL','usa','Technology','Consumer Electronics')"
        )
    result = load_ticker_classifications(database)
    assert result["AAPL"] == {
        "market": "usa",
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }


def test_liquidity_and_volatility_are_pre_event_only() -> None:
    history = [
        {"close": 100.0 + index, "volume": 1000 + index}
        for index in range(22)
    ]
    baseline = calculate_pre_event_proxies(history, 21)
    changed_future = history[:21] + [{"close": 9999.0, "volume": 999999999}]
    repeated = calculate_pre_event_proxies(changed_future, 21)
    assert baseline == repeated
    expected = sorted((100.0 + index) * (1000 + index) for index in range(1, 21))
    assert baseline["median_dollar_volume_Dm20_to_Dm1"] == pytest.approx(
        (expected[9] + expected[10]) / 2
    )
    assert baseline["realized_volatility_Dm20_to_Dm1"] is not None
    assert baseline["liquidity_observation_count"] == 20
    assert baseline["volatility_return_count"] == 20


def test_insufficient_pre_event_history_stays_missing() -> None:
    history = [{"close": 100.0 + index, "volume": 1000} for index in range(10)]
    result = calculate_pre_event_proxies(history, 10)
    assert result["median_dollar_volume_Dm20_to_Dm1"] is None
    assert result["realized_volatility_Dm20_to_Dm1"] is None


def test_tertile_bucket_boundaries() -> None:
    cutoffs = tertile_cutoffs([1, 2, 3, 4, 5, 6])
    assert cutoffs == (3.0, 5.0)
    assert [tertile_bucket(value, cutoffs) for value in (2.9, 3.0, 4.9, 5.0)] == [
        "LOW",
        "MID",
        "MID",
        "HIGH",
    ]


def test_relaxation_keeps_sector_and_fixed_controls_exact() -> None:
    treatment = _prepared(1, "YAHOO_NEAR_UNIQUE_SEC", liquidity="MID", volatility="MID")
    assert relaxation_level(treatment, _prepared(2, "CANONICAL_VERIFIED")) == "A_EXACT_ALL"
    assert (
        relaxation_level(
            treatment, _prepared(3, "CANONICAL_VERIFIED", liquidity="LOW", volatility="MID")
        )
        == "B_ADJACENT_LIQUIDITY"
    )
    assert (
        relaxation_level(
            treatment, _prepared(4, "CANONICAL_VERIFIED", liquidity="LOW", volatility="LOW")
        )
        == "C_ADJACENT_LIQUIDITY_AND_VOLATILITY"
    )
    assert relaxation_level(treatment, _prepared(5, "CANONICAL_VERIFIED", sector="Energy")) is None


def test_deterministic_matching_stages_and_no_control_reuse() -> None:
    rows = [
        _prepared(1, "YAHOO_NEAR_UNIQUE_SEC", liquidity="LOW", volatility="LOW", gap=1.2),
        _prepared(2, "YAHOO_NEAR_UNIQUE_SEC", liquidity="MID", volatility="MID", gap=1.4),
        _prepared(3, "YAHOO_NEAR_UNIQUE_SEC", liquidity="HIGH", volatility="HIGH", gap=1.6),
        _prepared(11, "CANONICAL_VERIFIED", liquidity="LOW", volatility="LOW", gap=1.21),
        _prepared(12, "CANONICAL_VERIFIED", liquidity="LOW", volatility="MID", gap=1.41),
        _prepared(13, "CANONICAL_VERIFIED", liquidity="MID", volatility="MID", gap=1.61),
    ]
    first, unmatched = match_yahoo_near(rows)
    second, _ = match_yahoo_near(list(reversed(rows)))
    assert first == second
    assert unmatched == []
    assert len({row["exact_company_id"] for row in first}) == 3
    assert set(row["relaxation_level"] for row in first) <= {
        "A_EXACT_ALL",
        "B_ADJACENT_LIQUIDITY",
        "C_ADJACENT_LIQUIDITY_AND_VOLATILITY",
    }


def test_missing_proxy_is_ineligible_and_sector_mismatch_unmatched() -> None:
    missing = _prepared(1, "YAHOO_NEAR_UNIQUE_SEC", liquidity=None)
    treatment = _prepared(2, "YAHOO_NEAR_UNIQUE_SEC", sector="Energy")
    control = _prepared(3, "CANONICAL_VERIFIED", sector="Technology")
    matches, unmatched = match_yahoo_near([missing, treatment, control])
    summary = summarize_yahoo_near_composition(matches, unmatched, [missing, treatment, control])
    assert matches == []
    assert summary["coverage"]["fully_eligible"] == 1
    assert summary["coverage"]["ineligible"] == 1
    assert summary["coverage"]["unmatched_after_eligibility"] == 1


def test_paired_difference_and_stratified_summary() -> None:
    treatment = _prepared(1, "YAHOO_NEAR_UNIQUE_SEC", gap=2.5)
    control = _prepared(2, "CANONICAL_VERIFIED", gap=1.5)
    matches, unmatched = match_yahoo_near([treatment, control])
    summary = summarize_yahoo_near_composition(matches, unmatched, [treatment, control])
    paired = summary["paired_differences_yahoo_near_minus_exact"]
    assert paired["D0_close_return_pct"]["median"] == pytest.approx(1.0)
    assert summary["sector_breakdown"]["Technology"]["n"] == 1
    assert summary["liquidity_stratification_all_yahoo_near"]["MID"]["n"] == 1
    assert summary["volatility_stratification_all_yahoo_near"]["MID"]["n"] == 1


def test_output_is_byte_deterministic(tmp_path: Path) -> None:
    treatment = _prepared(1, "YAHOO_NEAR_UNIQUE_SEC", gap=2.5)
    control = _prepared(2, "CANONICAL_VERIFIED", gap=1.5)
    matches, unmatched = match_yahoo_near([treatment, control])
    result = YahooNearComposition(
        rows=matches,
        unmatched=unmatched,
        prepared_rows=[treatment, control],
        summary=summarize_yahoo_near_composition(matches, unmatched, [treatment, control]),
        cutoffs={"market_cap": (1.0, 2.0), "liquidity": (1.0, 2.0), "volatility": (1.0, 2.0)},
    )
    sources = []
    for name in ("event.csv", "event.meta", "prior.csv", "analysis.db", "canonical.db", "ohlc.db", "forecast.db", "publication.csv"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        sources.append(path)
    output = tmp_path / "output.csv"
    metadata = tmp_path / "output.metadata.json"
    kwargs = dict(
        event_csv=sources[0],
        event_metadata=sources[1],
        matched_input=sources[2],
        market_cap_db=sources[3],
        canonical_db=sources[4],
        ohlc_db=sources[5],
        forecasts_db=sources[6],
        publication_csv=sources[7],
        extra_summary={"manual_qa": []},
        generated_at_utc="2026-10-03T00:00:00Z",
    )
    write_composition_outputs(result, output, metadata, **kwargs)
    first = output.read_bytes(), metadata.read_bytes()
    write_composition_outputs(result, output, metadata, **kwargs)
    assert (output.read_bytes(), metadata.read_bytes()) == first
