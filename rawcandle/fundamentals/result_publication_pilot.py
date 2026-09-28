from __future__ import annotations

import calendar
import hashlib
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


SELECTION_RULE = "result_publication_pilot_100_stratified_v1"
REQUIRED_TICKERS = ("AAPL", "NVDA", "AMZN", "ADBE", "KO", "XOM")


def _stable_order(company_id: int) -> str:
    return hashlib.sha256(f"{SELECTION_RULE}:{company_id}".encode()).hexdigest()


def deterministic_stratified_sample(
    records: Sequence[Mapping[str, Any]],
    *,
    sample_size: int,
    required_company_ids: Sequence[int] = (),
) -> list[dict[str, Any]]:
    by_id = {int(row["company_id"]): dict(row) for row in records}
    required = list(dict.fromkeys(int(value) for value in required_company_ids))
    missing = sorted(set(required) - by_id.keys())
    if missing:
        raise ValueError(f"PILOT_REQUIRED_COMPANIES_NOT_ELIGIBLE:{missing}")
    if sample_size > len(by_id) or len(required) > sample_size:
        raise ValueError("PILOT_SAMPLE_SIZE_INVALID")
    selected: list[dict[str, Any]] = []
    chosen: set[int] = set()
    for company_id in required:
        selected.append({**by_id[company_id], "selection_reason": "REQUIRED_CONTROL"})
        chosen.add(company_id)

    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for company_id, row in by_id.items():
        if company_id in chosen:
            continue
        key = (str(row["size_bucket"]), str(row["fiscal_pattern"]), str(row["sector"]))
        strata[key].append(row)
    for rows in strata.values():
        rows.sort(key=lambda row: (_stable_order(int(row["company_id"])), int(row["company_id"])))
    ordered_strata = sorted(strata)
    offsets = {key: 0 for key in ordered_strata}
    while len(selected) < sample_size:
        advanced = False
        for key in ordered_strata:
            index = offsets[key]
            if index >= len(strata[key]):
                continue
            row = strata[key][index]
            offsets[key] += 1
            selected.append({**row, "selection_reason": "STRATIFIED_HASH_ROUND_ROBIN"})
            chosen.add(int(row["company_id"]))
            advanced = True
            if len(selected) == sample_size:
                break
        if not advanced:
            raise RuntimeError("PILOT_SAMPLE_SELECTION_EXHAUSTED")
    return [{**row, "selection_order": index + 1} for index, row in enumerate(selected)]


def _fiscal_pattern(period_end: str) -> str:
    parsed = date.fromisoformat(period_end)
    month_end = calendar.monthrange(parsed.year, parsed.month)[1]
    if parsed.day != month_end:
        return "WEEK_BASED_52_53"
    return "CALENDAR_YEAR" if parsed.month == 12 else "NON_CALENDAR_YEAR"


def select_pilot_companies(
    canonical_db: Path,
    analysis_db: Path,
    *,
    sample_size: int = 100,
    required_tickers: Sequence[str] = REQUIRED_TICKERS,
) -> list[dict[str, Any]]:
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT m.company_id,m.security_id,m.current_ticker,c.cik_normalized,
                   COUNT(q.quarter_id) AS quarter_count,
                   COALESCE(
                       MAX(CASE WHEN q.fiscal_quarter='Q4' THEN q.period_end END),
                       MAX(q.period_end)
                   ) AS fiscal_anchor_period_end
            FROM fundamentals_operational_universe_active_version av
            JOIN fundamentals_operational_universe_member m USING(universe_version_id)
            JOIN company_cik c ON c.company_id=m.company_id AND c.status='ACTIVE'
            JOIN v4_quarter q ON q.company_id=m.company_id AND q.fiscal_year>=2025
            WHERE av.singleton=1 AND m.membership_status='ACTIVE_SINGLE_SECURITY'
            GROUP BY m.company_id,m.security_id,m.current_ticker
            HAVING COUNT(DISTINCT c.cik_normalized)=1
            ORDER BY m.company_id
            """
        ).fetchall()
    with sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        valuation_rows = connection.execute(
            """
            SELECT company_id,market_cap,sector,industry,fiscal_sequence
            FROM valuation_revised_result
            WHERE market_cap IS NOT NULL
            ORDER BY company_id,fiscal_sequence DESC
            """
        ).fetchall()
    latest: dict[int, sqlite3.Row] = {}
    for row in valuation_rows:
        latest.setdefault(int(row["company_id"]), row)
    market_caps = sorted(float(latest[int(row["company_id"])]["market_cap"]) for row in rows if int(row["company_id"]) in latest)
    low = market_caps[len(market_caps) // 3]
    high = market_caps[(2 * len(market_caps)) // 3]
    records: list[dict[str, Any]] = []
    ticker_to_company: dict[str, int] = {}
    for row in rows:
        company_id = int(row["company_id"])
        valuation = latest.get(company_id)
        market_cap = float(valuation["market_cap"]) if valuation is not None else None
        size_bucket = "UNKNOWN" if market_cap is None else "SMALL" if market_cap < low else "MID" if market_cap < high else "LARGE"
        ticker = str(row["current_ticker"])
        ticker_to_company[ticker.upper()] = company_id
        records.append({
            "company_id": company_id,
            "security_id": int(row["security_id"]),
            "ticker": ticker,
            "cik_normalized": str(row["cik_normalized"]),
            "quarter_count": int(row["quarter_count"]),
            "market_cap": market_cap,
            "size_bucket": size_bucket,
            "sector": str(valuation["sector"] or "UNKNOWN") if valuation is not None else "UNKNOWN",
            "industry": str(valuation["industry"] or "UNKNOWN") if valuation is not None else "UNKNOWN",
            "fiscal_pattern": _fiscal_pattern(str(row["fiscal_anchor_period_end"])),
        })
    required_ids = [ticker_to_company[ticker.upper()] for ticker in required_tickers]
    return deterministic_stratified_sample(records, sample_size=sample_size, required_company_ids=required_ids)
