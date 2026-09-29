from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from rawcandle.fundamentals.result_publication_daily_research import (
    EASTERN,
    DailyResearchResult,
    PublicationCandidate,
    YahooEvent,
    project_daily_research,
)


HEURISTIC_RESEARCH_WARNING = (
    "Suitable for hobby daily-OHLC research. Not canonical publication authority "
    "and not intended for precision event studies."
)
UNUSABLE_RESEARCH_WARNING = "No usable daily-research publication boundary is available."


@dataclass(frozen=True, order=True)
class QuarterKey:
    company_id: int
    fiscal_year: int
    fiscal_quarter: str


@dataclass(frozen=True)
class DailyResearchServiceResult:
    result: DailyResearchResult
    tickers: tuple[str, ...]
    calendar_status: str
    yahoo_status: str
    v2_candidate_id: str | None
    is_canonical: bool
    warning: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.result.to_dict(),
            "tickers": list(self.tickers),
            "calendar_status": self.calendar_status,
            "yahoo_status": self.yahoo_status,
            "v2_candidate_id": self.v2_candidate_id,
            "is_canonical": self.is_canonical,
            "warning": self.warning,
        }


class YahooObservationProvider(Protocol):
    def get_events(self, key: QuarterKey, ticker: str, period_end: str) -> Sequence[YahooEvent]: ...


class V2CandidateProvider(Protocol):
    def get_candidate_id(self, key: QuarterKey) -> str | None: ...


class QuarterNotFoundError(LookupError):
    pass


class MappingYahooObservationProvider:
    def __init__(self, observations: Mapping[QuarterKey, Sequence[YahooEvent | str]]) -> None:
        self._observations = {
            key: tuple(value if isinstance(value, YahooEvent) else YahooEvent(value) for value in values)
            for key, values in observations.items()
        }

    def get_events(self, key: QuarterKey, ticker: str, period_end: str) -> Sequence[YahooEvent]:
        del ticker, period_end
        return self._observations.get(key, ())


class MappingV2CandidateProvider:
    def __init__(self, candidates: Mapping[QuarterKey, str]) -> None:
        self._candidates = dict(candidates)

    def get_candidate_id(self, key: QuarterKey) -> str | None:
        return self._candidates.get(key)


class YFinanceYahooObservationProvider:
    def __init__(self, *, limit: int = 12, window_days: int = 180) -> None:
        self.limit = limit
        self.window_days = window_days

    def get_events(self, key: QuarterKey, ticker: str, period_end: str) -> Sequence[YahooEvent]:
        del key
        import yfinance as yf

        frame = yf.Ticker(ticker).get_earnings_dates(limit=self.limit)
        if frame is None or frame.empty:
            return ()
        start = date.fromisoformat(period_end)
        end = start + timedelta(days=self.window_days)
        events: list[YahooEvent] = []
        for value in frame.index:
            candidate = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
            if not isinstance(candidate, datetime) or candidate.tzinfo is None:
                continue
            local_date = candidate.astimezone(EASTERN).date()
            if start <= local_date <= end:
                events.append(YahooEvent(candidate.isoformat()))
        return tuple(sorted(events, key=lambda event: event.timestamp))


def _read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _chunks(values: Sequence[Any], size: int = 300) -> list[Sequence[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _key(row: Mapping[str, Any]) -> QuarterKey:
    return QuarterKey(int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"]))


def _coerce_key(value: QuarterKey | tuple[int, int, str]) -> QuarterKey:
    return value if isinstance(value, QuarterKey) else QuarterKey(int(value[0]), int(value[1]), str(value[2]))


def _local_date(timestamp: str) -> date:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.astimezone(EASTERN).date()


class DailyResearchPublicationService:
    def __init__(
        self,
        canonical_db_path: str | Path,
        ohlc_db_path: str | Path,
        *,
        yahoo_provider: YahooObservationProvider | None = None,
        v2_provider: V2CandidateProvider | None = None,
    ) -> None:
        self._canonical = _read_only_connection(Path(canonical_db_path))
        self._ohlc = _read_only_connection(Path(ohlc_db_path))
        self._yahoo_provider = yahoo_provider
        self._v2_provider = v2_provider
        self._calendar_cache: dict[str, tuple[str, ...]] = {}
        self._closed = False

    def __enter__(self) -> DailyResearchPublicationService:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._canonical.close()
        self._ohlc.close()
        self._closed = True

    def get_daily_research_result(
        self, company_id: int, fiscal_year: int, fiscal_quarter: str
    ) -> DailyResearchServiceResult:
        return self.get_daily_research_results(
            [QuarterKey(company_id, fiscal_year, fiscal_quarter)]
        )[0]

    def get_daily_research_results(
        self, keys: Sequence[QuarterKey | tuple[int, int, str]]
    ) -> list[DailyResearchServiceResult]:
        requested = [_coerce_key(value) for value in keys]
        if not requested:
            return []
        if len(set(requested)) != len(requested):
            raise ValueError("DUPLICATE_QUARTER_KEY")

        authority = self._load_authority(requested)
        missing = [key for key in requested if key not in authority]
        if missing:
            rendered = ",".join(
                f"{key.company_id}/{key.fiscal_year}/{key.fiscal_quarter}" for key in missing
            )
            raise QuarterNotFoundError(f"RESULT_PUBLICATION_QUARTER_NOT_FOUND:{rendered}")

        evidence = self._load_evidence(requested)
        tickers = self._load_tickers({key.company_id for key in requested})
        all_tickers = sorted({ticker for values in tickers.values() for ticker in values})
        self._load_calendars(all_tickers)
        return [
            self._assemble(key, authority[key], evidence.get(key, ()), tickers.get(key.company_id, ()))
            for key in requested
        ]

    def _load_authority(self, keys: Sequence[QuarterKey]) -> dict[QuarterKey, dict[str, Any]]:
        result: dict[QuarterKey, dict[str, Any]] = {}
        for chunk in _chunks(keys):
            placeholders = ",".join("(?,?,?)" for _ in chunk)
            parameters = [part for key in chunk for part in asdict(key).values()]
            rows = self._canonical.execute(
                f"""
                SELECT a.*,q.period_end
                FROM v4_result_publication_authority AS a
                JOIN v4_quarter AS q ON q.quarter_id=a.quarter_id
                WHERE (a.company_id,a.fiscal_year,a.fiscal_quarter) IN ({placeholders})
                """,
                parameters,
            )
            for row in rows:
                payload = dict(row)
                result[_key(payload)] = payload
        return result

    def _load_evidence(
        self, keys: Sequence[QuarterKey]
    ) -> dict[QuarterKey, tuple[PublicationCandidate, ...]]:
        result: dict[QuarterKey, list[PublicationCandidate]] = defaultdict(list)
        for chunk in _chunks(keys):
            placeholders = ",".join("(?,?,?)" for _ in chunk)
            parameters = [part for key in chunk for part in asdict(key).values()]
            rows = self._canonical.execute(
                f"""
                SELECT company_id,fiscal_year,fiscal_quarter,evidence_id,
                       accession_number,source_timestamp_utc,source_reference
                FROM v4_result_publication_evidence
                WHERE source_type='SEC_8K_ITEM_2_02'
                  AND disposition IN ('ACCEPTED','CONFLICT')
                  AND (company_id,fiscal_year,fiscal_quarter) IN ({placeholders})
                ORDER BY source_timestamp_utc,evidence_id
                """,
                parameters,
            )
            for row in rows:
                candidate_id = str(row["accession_number"] or row["evidence_id"])
                result[_key(row)].append(
                    PublicationCandidate(
                        candidate_id=candidate_id,
                        timestamp_utc=str(row["source_timestamp_utc"]),
                        source_reference=str(row["source_reference"]),
                    )
                )
        return {key: tuple(values) for key, values in result.items()}

    def _load_tickers(self, company_ids: set[int]) -> dict[int, tuple[str, ...]]:
        result: dict[int, list[str]] = defaultdict(list)
        ordered = sorted(company_ids)
        for chunk in _chunks(ordered, size=800):
            placeholders = ",".join("?" for _ in chunk)
            rows = self._canonical.execute(
                f"""
                SELECT company_id,current_ticker
                FROM security
                WHERE company_id IN ({placeholders})
                ORDER BY company_id,active DESC,security_id
                """,
                chunk,
            )
            for row in rows:
                ticker = str(row["current_ticker"]).upper()
                if ticker not in result[int(row["company_id"])]:
                    result[int(row["company_id"])].append(ticker)
        return {company_id: tuple(values) for company_id, values in result.items()}

    def _load_calendars(self, tickers: Sequence[str]) -> None:
        missing = [ticker for ticker in tickers if ticker not in self._calendar_cache]
        for chunk in _chunks(missing, size=800):
            placeholders = ",".join("?" for _ in chunk)
            collected: dict[str, list[str]] = defaultdict(list)
            rows = self._ohlc.execute(
                f"""
                SELECT osake AS ticker,pvm
                FROM osakedata
                WHERE osake IN ({placeholders})
                ORDER BY osake,pvm
                """,
                chunk,
            )
            for row in rows:
                collected[str(row["ticker"])].append(str(row["pvm"]))
            for ticker in chunk:
                self._calendar_cache[ticker] = tuple(collected.get(ticker, ()))

    def _relevant_tickers(
        self,
        tickers: Sequence[str],
        authority: Mapping[str, Any],
        candidates: Sequence[PublicationCandidate],
    ) -> tuple[str, ...]:
        timestamps = [candidate.timestamp_utc for candidate in candidates]
        if authority.get("result_publication_timestamp_utc"):
            timestamps.append(str(authority["result_publication_timestamp_utc"]))
        publication_dates = [_local_date(timestamp) for timestamp in timestamps]
        available = [ticker for ticker in tickers if self._calendar_cache.get(ticker)]
        if not publication_dates:
            return tuple(available[:1])
        first, last = min(publication_dates), max(publication_dates)
        relevant = []
        for ticker in available:
            calendar = self._calendar_cache[ticker]
            if date.fromisoformat(calendar[0]) <= first and date.fromisoformat(calendar[-1]) >= last:
                relevant.append(ticker)
        return tuple(relevant)

    def _provider_inputs(
        self,
        key: QuarterKey,
        authority: Mapping[str, Any],
        ticker: str,
        *,
        has_candidates: bool,
    ) -> tuple[tuple[YahooEvent, ...], str, str | None]:
        if str(authority["status"]) == "VERIFIED":
            return (), "SKIPPED_EXACT", None
        if not has_candidates:
            return (), "SKIPPED_NO_SEC_CANDIDATE", None

        yahoo_status = "NOT_CONFIGURED"
        events: tuple[YahooEvent, ...] = ()
        if self._yahoo_provider is not None:
            try:
                events = tuple(
                    self._yahoo_provider.get_events(key, ticker, str(authority["period_end"]))
                )
                yahoo_status = "AVAILABLE" if events else "UNAVAILABLE"
            except Exception as exc:
                yahoo_status = f"ERROR:{type(exc).__name__}"

        v2_candidate = self._v2_provider.get_candidate_id(key) if self._v2_provider else None
        return events, yahoo_status, v2_candidate

    def _assemble(
        self,
        key: QuarterKey,
        authority: Mapping[str, Any],
        candidates: Sequence[PublicationCandidate],
        company_tickers: Sequence[str],
    ) -> DailyResearchServiceResult:
        relevant = self._relevant_tickers(company_tickers, authority, candidates)
        projection_tickers = relevant or ("",)
        projections: list[tuple[DailyResearchResult, str, str | None]] = []
        for ticker in projection_tickers:
            events, yahoo_status, v2_candidate = self._provider_inputs(
                key,
                authority,
                ticker,
                has_candidates=bool(candidates),
            )
            result = project_daily_research(
                authority,
                candidates,
                self._calendar_cache.get(ticker, ()),
                yahoo_events=events,
                v2_strong_candidate_id=v2_candidate,
            )
            projections.append((result, yahoo_status, v2_candidate))

        first, yahoo_status, v2_candidate = projections[0]
        signatures = {
            (
                result.research_status,
                result.research_method,
                result.first_full_post_result_trading_date,
                result.selected_candidate_timestamp_utc,
            )
            for result, _, _ in projections
        }
        calendar_status = "AGREED" if relevant and len(signatures) == 1 else "UNAVAILABLE"
        if len(signatures) > 1:
            calendar_status = "DISAGREEMENT"
            if first.research_status == "EXACT":
                first = replace(first, first_full_post_result_trading_date=None)
            else:
                first = replace(
                    first,
                    research_publication_date=None,
                    research_publication_session=None,
                    first_full_post_result_trading_date=None,
                    research_status="UNUSABLE",
                    research_confidence="NONE",
                    research_method="TICKER_CALENDAR_DISAGREEMENT",
                    selected_candidate_timestamp_utc=None,
                    selected_candidate_reference=None,
                    yahoo_event_timestamp=None,
                    yahoo_event_date=None,
                    trading_day_distance_to_yahoo=None,
                )

        is_canonical = first.research_status == "EXACT"
        warning = None if is_canonical else (
            UNUSABLE_RESEARCH_WARNING if first.research_status == "UNUSABLE" else HEURISTIC_RESEARCH_WARNING
        )
        statuses = {status for _, status, _ in projections}
        if len(statuses) > 1:
            yahoo_status = "MIXED"
        return DailyResearchServiceResult(
            result=first,
            tickers=tuple(company_tickers),
            calendar_status=calendar_status,
            yahoo_status=yahoo_status,
            v2_candidate_id=v2_candidate,
            is_canonical=is_canonical,
            warning=warning,
        )
