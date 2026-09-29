from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path


USABLE_STATUSES = frozenset({"EXACT", "HEURISTIC_HIGH", "HEURISTIC_MEDIUM"})
REQUIRED_COLUMNS = frozenset(
    {
        "company_id",
        "ticker",
        "fiscal_year",
        "fiscal_quarter",
        "research_status",
        "research_confidence",
        "research_method",
        "research_publication_date",
        "research_publication_session",
        "first_full_post_result_trading_date",
        "canonical_authority_status",
        "canonical_timestamp_utc",
        "is_canonical",
        "selected_candidate_timestamp_utc",
        "selected_candidate_reference",
        "yahoo_event_timestamp",
        "yahoo_event_date",
        "trading_day_distance_to_yahoo",
        "rule_version",
        "warning",
    }
)


@dataclass(frozen=True, order=True)
class ResearchQuarterKey:
    company_id: int
    fiscal_year: int
    fiscal_quarter: str


@dataclass(frozen=True)
class ResultPublicationResearchRow:
    key: ResearchQuarterKey
    ticker: str
    first_full_post_result_trading_date: str | None
    research_status: str
    research_method: str
    is_canonical: bool
    rule_version: str
    warning: str | None


@dataclass(frozen=True)
class OhlcDay:
    trading_date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


@dataclass(frozen=True)
class DailyOhlcBoundaryWindow:
    publication: ResultPublicationResearchRow
    availability: str
    previous_day: OhlcDay | None
    boundary_day: OhlcDay | None
    next_day: OhlcDay | None


class ResultPublicationResearchDataset:
    """Read-only quarter lookup over one retained result-publication CSV."""

    def __init__(self, source: Path, rows: dict[ResearchQuarterKey, ResultPublicationResearchRow]) -> None:
        self.source = source
        self._rows = rows

    @classmethod
    def load(cls, source: str | Path) -> ResultPublicationResearchDataset:
        path = Path(source)
        rows: dict[ResearchQuarterKey, ResultPublicationResearchRow] = {}
        try:
            handle = path.open("r", encoding="utf-8", newline="")
        except OSError as exc:
            raise ValueError(f"RESEARCH_EXPORT_UNREADABLE:{path}") from exc
        with handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise ValueError("RESEARCH_EXPORT_COLUMNS_INVALID")
            for line_number, raw in enumerate(reader, start=2):
                row = _parse_row(raw, line_number)
                if row.key in rows:
                    raise ValueError(
                        "RESEARCH_EXPORT_DUPLICATE_QUARTER:"
                        f"{row.key.company_id}/{row.key.fiscal_year}/{row.key.fiscal_quarter}"
                    )
                rows[row.key] = row
        return cls(path.resolve(), rows)

    def __len__(self) -> int:
        return len(self._rows)

    def get(self, company_id: int, fiscal_year: int, fiscal_quarter: str) -> ResultPublicationResearchRow | None:
        return self._rows.get(ResearchQuarterKey(company_id, fiscal_year, fiscal_quarter))

    def require(
        self, company_id: int, fiscal_year: int, fiscal_quarter: str
    ) -> ResultPublicationResearchRow:
        key = ResearchQuarterKey(company_id, fiscal_year, fiscal_quarter)
        try:
            return self._rows[key]
        except KeyError as exc:
            raise KeyError(f"RESEARCH_QUARTER_NOT_FOUND:{company_id}/{fiscal_year}/{fiscal_quarter}") from exc

    def get_ohlc_window(
        self,
        ohlc_db: str | Path,
        company_id: int,
        fiscal_year: int,
        fiscal_quarter: str,
    ) -> DailyOhlcBoundaryWindow:
        publication = self.require(company_id, fiscal_year, fiscal_quarter)
        boundary = publication.first_full_post_result_trading_date
        if boundary is None:
            return DailyOhlcBoundaryWindow(publication, "BOUNDARY_UNAVAILABLE", None, None, None)

        connection = sqlite3.connect(f"file:{Path(ohlc_db).resolve().as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            boundary_row = connection.execute(
                "SELECT pvm,open,high,low,close,volume FROM osakedata WHERE osake=? AND pvm=?",
                (publication.ticker, boundary),
            ).fetchone()
            if boundary_row is None:
                latest = connection.execute(
                    "SELECT MAX(pvm) FROM osakedata WHERE osake=?", (publication.ticker,)
                ).fetchone()[0]
                if latest is None or boundary > str(latest):
                    return DailyOhlcBoundaryWindow(publication, "PENDING_OHLC", None, None, None)
                raise ValueError(
                    f"BOUNDARY_NOT_IN_OHLC_CALENDAR:{publication.ticker}:{boundary}"
                )
            previous = connection.execute(
                "SELECT pvm,open,high,low,close,volume FROM osakedata "
                "WHERE osake=? AND pvm<? ORDER BY pvm DESC LIMIT 1",
                (publication.ticker, boundary),
            ).fetchone()
            following = connection.execute(
                "SELECT pvm,open,high,low,close,volume FROM osakedata "
                "WHERE osake=? AND pvm>? ORDER BY pvm LIMIT 1",
                (publication.ticker, boundary),
            ).fetchone()
        finally:
            connection.close()
        return DailyOhlcBoundaryWindow(
            publication=publication,
            availability="AVAILABLE",
            previous_day=_ohlc_day(previous),
            boundary_day=_ohlc_day(boundary_row),
            next_day=_ohlc_day(following),
        )


def _optional(value: str | None) -> str | None:
    return value if value else None


def _parse_row(raw: dict[str, str | None], line_number: int) -> ResultPublicationResearchRow:
    try:
        company_id = int(raw["company_id"] or "")
        fiscal_year = int(raw["fiscal_year"] or "")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"RESEARCH_EXPORT_IDENTITY_INVALID:{line_number}") from exc
    quarter = raw.get("fiscal_quarter") or ""
    ticker = (raw.get("ticker") or "").strip().upper()
    if company_id <= 0 or fiscal_year <= 0 or quarter not in {"Q1", "Q2", "Q3", "Q4"} or not ticker:
        raise ValueError(f"RESEARCH_EXPORT_IDENTITY_INVALID:{line_number}")
    status = raw.get("research_status") or ""
    if status not in USABLE_STATUSES:
        raise ValueError(f"RESEARCH_EXPORT_STATUS_REJECTED:{line_number}:{status}")
    canonical_value = raw.get("is_canonical")
    if canonical_value not in {"True", "False"}:
        raise ValueError(f"RESEARCH_EXPORT_CANONICAL_FLAG_INVALID:{line_number}")
    boundary = _optional(raw.get("first_full_post_result_trading_date"))
    if boundary is not None:
        try:
            date.fromisoformat(boundary)
        except ValueError as exc:
            raise ValueError(f"RESEARCH_EXPORT_BOUNDARY_INVALID:{line_number}") from exc
    method = raw.get("research_method") or ""
    rule_version = raw.get("rule_version") or ""
    if not method or not rule_version:
        raise ValueError(f"RESEARCH_EXPORT_PROVENANCE_INVALID:{line_number}")
    return ResultPublicationResearchRow(
        key=ResearchQuarterKey(company_id, fiscal_year, quarter),
        ticker=ticker,
        first_full_post_result_trading_date=boundary,
        research_status=status,
        research_method=method,
        is_canonical=canonical_value == "True",
        rule_version=rule_version,
        warning=_optional(raw.get("warning")),
    )


def _ohlc_day(row: sqlite3.Row | None) -> OhlcDay | None:
    if row is None:
        return None
    return OhlcDay(
        trading_date=str(row["pvm"]),
        open=float(row["open"]) if row["open"] is not None else None,
        high=float(row["high"]) if row["high"] is not None else None,
        low=float(row["low"]) if row["low"] is not None else None,
        close=float(row["close"]) if row["close"] is not None else None,
        volume=int(row["volume"]) if row["volume"] is not None else None,
    )
