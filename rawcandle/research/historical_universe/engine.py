from __future__ import annotations

import bisect
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


CIK_PATTERN = re.compile(r"[?&]CIK=0*(\d+)", re.IGNORECASE)
ELIGIBLE_CATEGORIES = {
    "Domestic Common Stock",
    "Domestic Common Stock Primary Class",
    "Canadian Common Stock",
    "Canadian Common Stock Primary Class",
    "ADR Common Stock",
    "ADR Common Stock Primary Class",
}


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_cik(secfilings: str | None) -> str | None:
    match = CIK_PATTERN.search(secfilings or "")
    return match.group(1).zfill(10) if match else None


def ranges_overlap(first_a: str | None, last_a: str | None, first_b: str | None, last_b: str | None) -> bool:
    if not all((first_a, last_a, first_b, last_b)):
        return False
    return str(first_a) <= str(last_b) and str(first_b) <= str(last_a)


def identity_status(
    *,
    metadata_count: int,
    permaticker: str | None,
    first_fundamental: str | None,
    last_fundamental: str | None,
    metadata_first_quarter: str | None,
    metadata_last_quarter: str | None,
    market_count: int,
) -> str:
    if metadata_count > 1:
        return "IDENTITY_REUSED_TICKER_RISK"
    if metadata_count == 0 or not permaticker:
        return "IDENTITY_METADATA_REQUIRED"
    if not ranges_overlap(
        first_fundamental, last_fundamental, metadata_first_quarter, metadata_last_quarter
    ):
        return "IDENTITY_REUSED_TICKER_RISK"
    if market_count > 1:
        return "IDENTITY_AMBIGUOUS"
    return "IDENTITY_EXACT_DATED"


def security_eligibility(category: str | None) -> str:
    if not category:
        return "SECURITY_TYPE_METADATA_REQUIRED"
    if category in ELIGIBLE_CATEGORIES:
        return "RESEARCH_SECURITY_ELIGIBLE"
    return "RESEARCH_SECURITY_INELIGIBLE"


def model_applicability(sector: str | None) -> str:
    if not sector:
        return "FUNDAMENTAL_MODEL_METADATA_REQUIRED"
    if sector in {"Financial Services", "Real Estate"}:
        return "FUNDAMENTAL_MODEL_NOT_APPLICABLE_CURRENT_CONTEXT"
    return "FUNDAMENTAL_MODEL_CANDIDATE_CURRENT_CONTEXT_ONLY"


def resolve_dated_alias(as_of: str, aliases: Sequence[Mapping[str, Any]]) -> tuple[str | None, str]:
    eligible = []
    for alias in aliases:
        valid_from = str(alias.get("valid_from") or "")
        valid_to = str(alias.get("valid_to") or "")
        if not valid_from:
            continue
        if valid_from <= as_of and (not valid_to or as_of <= valid_to):
            eligible.append(str(alias.get("ticker") or "").upper())
    unique = sorted(set(eligible))
    if len(unique) == 1:
        return unique[0], "IDENTITY_ALIAS_RESOLVED"
    if len(unique) > 1:
        return None, "IDENTITY_AMBIGUOUS"
    return None, "IDENTITY_METADATA_REQUIRED"


@dataclass(frozen=True)
class HorizonFeasibility:
    horizon: int
    status: str
    event_center: str | None = None
    observable_date: str | None = None
    exit_date: str | None = None
    session_coverage: float | None = None
    qqq_aligned: bool = False


def label_feasibility(
    *,
    availability_date: str | None,
    horizon: int,
    benchmark_sessions: Sequence[str],
    qqq_sessions: set[str],
    company_sessions: set[str],
) -> HorizonFeasibility:
    if not availability_date:
        return HorizonFeasibility(horizon, "MISSING_AVAILABILITY_DATE")
    center = bisect.bisect_right(benchmark_sessions, availability_date)
    if center < 2 or center + 2 >= len(benchmark_sessions):
        return HorizonFeasibility(horizon, "EVENT_WINDOW_OUTSIDE_BENCHMARK")
    event_dates = benchmark_sessions[center - 2:center + 3]
    if any(day not in company_sessions for day in event_dates):
        return HorizonFeasibility(horizon, "MISSING_FIVE_SESSION_EVENT_WINDOW")
    observable_index = center + 2
    exit_index = observable_index + horizon
    if exit_index >= len(benchmark_sessions):
        return HorizonFeasibility(
            horizon, "HORIZON_NOT_MATURED", benchmark_sessions[center],
            benchmark_sessions[observable_index],
        )
    exit_date = benchmark_sessions[exit_index]
    interval = benchmark_sessions[center - 2:exit_index + 1]
    observed = sum(day in company_sessions for day in interval)
    coverage = observed / len(interval)
    if exit_date not in company_sessions:
        later = any(day > exit_date for day in company_sessions)
        status = "MISSING_EXACT_EXIT_TEMPORARY_GAP" if later else "RIGHT_CENSORED_UNRESOLVED_TERMINAL"
    elif coverage < 0.90:
        status = "INSUFFICIENT_SESSION_COVERAGE"
    else:
        status = "LABEL_FEASIBLE"
    qqq_required = (*event_dates, exit_date)
    return HorizonFeasibility(
        horizon, status, benchmark_sessions[center], benchmark_sessions[observable_index],
        exit_date, round(coverage, 8), all(day in qqq_sessions for day in qqq_required),
    )


def finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def choose_latest(existing: Mapping[str, str] | None, candidate: Mapping[str, str]) -> bool:
    if existing is None:
        return True
    fields = ("lastupdated", "date")
    old_key = tuple(str(existing.get(field) or "") for field in fields) + (stable_hash(existing),)
    new_key = tuple(str(candidate.get(field) or "") for field in fields) + (stable_hash(candidate),)
    return new_key > old_key


def deterministic_rows(rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    return sorted((dict(row) for row in rows), key=lambda row: tuple(str(row.get(key) or "") for key in keys))
