from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


RULE_VERSION = "result_publication_daily_research_v1"
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PublicationCandidate:
    candidate_id: str
    timestamp_utc: str
    source_reference: str


@dataclass(frozen=True)
class YahooEvent:
    timestamp: str


@dataclass(frozen=True)
class DailyResearchResult:
    company_id: int
    fiscal_year: int
    fiscal_quarter: str
    research_publication_date: str | None
    research_publication_session: str | None
    first_full_post_result_trading_date: str | None
    research_status: str
    research_confidence: str
    research_method: str
    canonical_authority_status: str
    canonical_timestamp_utc: str | None
    source_candidate_count: int
    selected_candidate_timestamp_utc: str | None
    selected_candidate_reference: str | None
    yahoo_event_timestamp: str | None
    yahoo_event_date: str | None
    trading_day_distance_to_yahoo: int | None
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradingCalendar:
    def __init__(self, trading_dates: Sequence[str | date]) -> None:
        self.dates = tuple(sorted({_as_date(value) for value in trading_dates}))
        self._positions = {value: index for index, value in enumerate(self.dates)}

    def contains(self, value: date) -> bool:
        return value in self._positions

    def first_on_or_after(self, value: date) -> date | None:
        index = bisect_left(self.dates, value)
        return self.dates[index] if index < len(self.dates) else None

    def first_after(self, value: date) -> date | None:
        index = bisect_right(self.dates, value)
        return self.dates[index] if index < len(self.dates) else None

    def distance(self, left: date, right: date) -> int | None:
        left_index = self._positions.get(left)
        right_index = self._positions.get(right)
        if left_index is None or right_index is None:
            return None
        return right_index - left_index


@dataclass(frozen=True)
class _Boundary:
    timestamp: str
    publication_date: date
    session: str
    effective_date: date | None


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("PUBLICATION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed


def publication_boundary(timestamp: str, calendar: TradingCalendar) -> _Boundary:
    local = _parse_timestamp(timestamp).astimezone(EASTERN)
    local_time = local.timetz().replace(tzinfo=None)
    if local_time < time(9, 30):
        session = "PRE_MARKET"
    elif local_time < time(16, 0):
        session = "REGULAR_HOURS"
    else:
        session = "AFTER_MARKET"

    publication_date = local.date()
    if calendar.contains(publication_date) and session == "PRE_MARKET":
        effective_date = publication_date
    elif calendar.contains(publication_date):
        effective_date = calendar.first_after(publication_date)
    else:
        effective_date = calendar.first_on_or_after(publication_date)
    return _Boundary(timestamp, publication_date, session, effective_date)


def _base_result(
    authority: Mapping[str, Any],
    candidates: Sequence[PublicationCandidate],
    *,
    status: str,
    confidence: str,
    method: str,
    boundary: _Boundary | None = None,
    candidate: PublicationCandidate | None = None,
    yahoo: YahooEvent | None = None,
    yahoo_distance: int | None = None,
    effective_date: date | None = None,
) -> DailyResearchResult:
    resolved_effective_date = boundary.effective_date if boundary else effective_date
    return DailyResearchResult(
        company_id=int(authority["company_id"]),
        fiscal_year=int(authority["fiscal_year"]),
        fiscal_quarter=str(authority["fiscal_quarter"]),
        research_publication_date=boundary.publication_date.isoformat() if boundary else None,
        research_publication_session=boundary.session if boundary else None,
        first_full_post_result_trading_date=(resolved_effective_date.isoformat() if resolved_effective_date else None),
        research_status=status,
        research_confidence=confidence,
        research_method=method,
        canonical_authority_status=str(authority["status"]),
        canonical_timestamp_utc=authority.get("result_publication_timestamp_utc"),
        source_candidate_count=len(candidates),
        selected_candidate_timestamp_utc=candidate.timestamp_utc if candidate else None,
        selected_candidate_reference=candidate.source_reference if candidate else None,
        yahoo_event_timestamp=yahoo.timestamp if yahoo else None,
        yahoo_event_date=(
            _parse_timestamp(yahoo.timestamp).astimezone(EASTERN).date().isoformat() if yahoo else None
        ),
        trading_day_distance_to_yahoo=yahoo_distance,
    )


def _selected_result(
    authority: Mapping[str, Any],
    candidates: Sequence[PublicationCandidate],
    candidate: PublicationCandidate,
    calendar: TradingCalendar,
    *,
    status: str,
    confidence: str,
    method: str,
    yahoo: YahooEvent | None = None,
    yahoo_distance: int | None = None,
) -> DailyResearchResult:
    boundary = publication_boundary(candidate.timestamp_utc, calendar)
    if boundary.effective_date is None and status != "EXACT":
        return _base_result(
            authority, candidates, status="UNUSABLE", confidence="NONE", method="NO_TRADING_DAY"
        )
    return _base_result(
        authority,
        candidates,
        status=status,
        confidence=confidence,
        method=method,
        boundary=boundary,
        candidate=candidate,
        yahoo=yahoo,
        yahoo_distance=yahoo_distance,
    )


def _yahoo_selection(
    candidates: Sequence[PublicationCandidate],
    boundaries: Mapping[str, _Boundary],
    yahoo_events: Sequence[YahooEvent],
    calendar: TradingCalendar,
) -> tuple[PublicationCandidate, YahooEvent, int] | None:
    selections: list[tuple[PublicationCandidate, YahooEvent, int]] = []
    for event in yahoo_events:
        event_boundary = publication_boundary(event.timestamp, calendar)
        if event_boundary.effective_date is None:
            continue
        eligible: list[tuple[PublicationCandidate, int]] = []
        for candidate in candidates:
            effective = boundaries[candidate.candidate_id].effective_date
            if effective is None:
                continue
            distance = calendar.distance(event_boundary.effective_date, effective)
            if distance is not None and abs(distance) <= 1:
                eligible.append((candidate, distance))
        if not eligible:
            continue

        closest_distance = min(abs(distance) for _, distance in eligible)
        closest = [(candidate, distance) for candidate, distance in eligible if abs(distance) == closest_distance]
        effective_days = {boundaries[candidate.candidate_id].effective_date for candidate, _ in closest}
        if len(effective_days) != 1:
            continue
        selected, distance = max(closest, key=lambda item: _parse_timestamp(item[0].timestamp_utc))
        selections.append((selected, event, distance))

    selected_ids = {candidate.candidate_id for candidate, _, _ in selections}
    if len(selected_ids) != 1:
        return None
    return min(selections, key=lambda item: abs(item[2]))


def project_daily_research(
    authority: Mapping[str, Any],
    candidates: Sequence[PublicationCandidate],
    trading_dates: Sequence[str | date],
    *,
    yahoo_events: Sequence[YahooEvent] = (),
    v2_strong_candidate_id: str | None = None,
) -> DailyResearchResult:
    calendar = TradingCalendar(trading_dates)
    canonical_status = str(authority["status"])
    if canonical_status == "VERIFIED":
        timestamp = authority.get("result_publication_timestamp_utc")
        if not timestamp:
            return _base_result(
                authority, candidates, status="UNUSABLE", confidence="NONE", method="VERIFIED_TIMESTAMP_MISSING"
            )
        canonical = PublicationCandidate(
            candidate_id=str(authority.get("selected_evidence_id") or "CANONICAL"),
            timestamp_utc=str(timestamp),
            source_reference=str(authority.get("result_publication_evidence_reference") or ""),
        )
        return _selected_result(
            authority,
            candidates,
            canonical,
            calendar,
            status="EXACT",
            confidence="EXACT",
            method="CANONICAL_VERIFIED",
        )

    if not calendar.dates and candidates:
        return _base_result(
            authority,
            candidates,
            status="UNUSABLE",
            confidence="NONE",
            method="OHLC_CALENDAR_UNAVAILABLE",
        )

    boundaries = {
        candidate.candidate_id: publication_boundary(candidate.timestamp_utc, calendar)
        for candidate in candidates
    }
    usable_candidates = [candidate for candidate in candidates if boundaries[candidate.candidate_id].effective_date]
    if not usable_candidates:
        return _base_result(authority, candidates, status="UNUSABLE", confidence="NONE", method="NO_SEC_CANDIDATE")

    effective_days = {boundaries[candidate.candidate_id].effective_date for candidate in usable_candidates}
    if len(usable_candidates) == len(candidates) and len(effective_days) == 1:
        effective = next(iter(effective_days))
        return _base_result(
            authority,
            candidates,
            status="HEURISTIC_HIGH",
            confidence="HIGH",
            method="ALL_CANDIDATES_SAME_EFFECTIVE_DAY",
            effective_date=effective,
        )

    if v2_strong_candidate_id:
        strong = next(
            (candidate for candidate in usable_candidates if candidate.candidate_id == v2_strong_candidate_id), None
        )
        if strong:
            return _selected_result(
                authority,
                candidates,
                strong,
                calendar,
                status="HEURISTIC_HIGH",
                confidence="HIGH",
                method="SEC_V2_STRONG_INITIAL",
            )

    if yahoo_events:
        selection = _yahoo_selection(usable_candidates, boundaries, yahoo_events, calendar)
        if selection:
            candidate, event, distance = selection
            event_effective = publication_boundary(event.timestamp, calendar).effective_date
            eligible_count = sum(
                1
                for other in usable_candidates
                if (
                    boundaries[other.candidate_id].effective_date
                    == boundaries[candidate.candidate_id].effective_date
                    and event_effective is not None
                    and boundaries[other.candidate_id].effective_date is not None
                    and (
                        distance := calendar.distance(
                            event_effective,
                            boundaries[other.candidate_id].effective_date,
                        )
                    )
                    is not None
                    and abs(distance) <= 1
                )
            )
            method = "YAHOO_NEAR_UNIQUE_SEC" if eligible_count == 1 else "YAHOO_NEAR_CLUSTER_LATEST"
            return _selected_result(
                authority,
                candidates,
                candidate,
                calendar,
                status="HEURISTIC_HIGH",
                confidence="HIGH",
                method=method,
                yahoo=event,
                yahoo_distance=distance,
            )
        return _base_result(
            authority, candidates, status="UNUSABLE", confidence="NONE", method="YAHOO_NO_UNIQUE_LOCAL_CLUSTER"
        )

    ordered = sorted(
        usable_candidates,
        key=lambda candidate: boundaries[candidate.candidate_id].effective_date,  # type: ignore[return-value]
    )
    span = calendar.distance(
        boundaries[ordered[0].candidate_id].effective_date,  # type: ignore[arg-type]
        boundaries[ordered[-1].candidate_id].effective_date,  # type: ignore[arg-type]
    )
    if span is not None and span <= 1:
        selected = max(usable_candidates, key=lambda candidate: _parse_timestamp(candidate.timestamp_utc))
        return _selected_result(
            authority,
            candidates,
            selected,
            calendar,
            status="HEURISTIC_MEDIUM",
            confidence="MEDIUM",
            method="SEC_LOCAL_CLUSTER_LATEST",
        )
    return _base_result(
        authority, candidates, status="UNUSABLE", confidence="NONE", method="SEC_CANDIDATES_TOO_DISPERSED"
    )
