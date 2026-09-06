from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from rawcandle.fundamentals.snapshot.assembler import (
    SnapshotPaths,
    generate_company_snapshot,
)
from rawcandle.fundamentals.snapshot.writer import report_filename


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
FUNDAMENTAL_REPORTS_DIR = PROJECT_ROOT / "fundamental_reports"
PRODUCTION_SNAPSHOT_PATHS = SnapshotPaths(
    canonical_db=PROJECT_ROOT / "data/fundamentals_v4.db",
    analysis_db=PROJECT_ROOT / "data/fundamentals_analysis.db",
    market_db=PROJECT_ROOT / "data/osakedata.db",
    taxonomy_db=PROJECT_ROOT / "data/analysis.db",
    provider_db=PROJECT_ROOT / "data/fundamentals_provider.db",
)
REPORT_NAME_RE = re.compile(
    r"^(?P<ticker>[A-Z0-9]+(?:[.-][A-Z0-9]+)*)_"
    r"(?P<report_date>\d{4}-\d{2}-\d{2})\.md$"
)


@dataclass(frozen=True)
class FundamentalsUIResult:
    status: str
    message: str
    ticker: str | None = None
    report_date: str | None = None
    filename: str | None = None
    output_path: str | None = None
    report_content_fingerprint: str | None = None
    publication_status: str | None = None


@dataclass(frozen=True)
class RecentFundamentalsReport:
    ticker: str
    report_date: str
    filename: str
    modified_at_utc: str


def normalize_ticker(value: str | None) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker:
        raise ValueError("TICKER_REQUIRED")
    report_filename(ticker, "2000-01-01")
    return ticker


def normalize_report_date(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("REPORT_DATE_REQUIRED")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("INVALID_REPORT_DATE") from exc
    if parsed.isoformat() != raw:
        raise ValueError("INVALID_REPORT_DATE")
    return raw


def list_recent_fundamentals_reports(
    output_dir: Path = FUNDAMENTAL_REPORTS_DIR,
    *,
    limit: int = 10,
) -> list[RecentFundamentalsReport]:
    if limit <= 0:
        return []
    directory = output_dir.resolve()
    if not directory.is_dir():
        return []
    entries: list[tuple[int, str, RecentFundamentalsReport]] = []
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        match = REPORT_NAME_RE.fullmatch(path.name)
        if not match:
            continue
        try:
            normalized_date = normalize_report_date(match.group("report_date"))
            expected = report_filename(match.group("ticker"), normalized_date)
        except ValueError:
            continue
        if expected != path.name:
            continue
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        report = RecentFundamentalsReport(
            ticker=match.group("ticker"),
            report_date=normalized_date,
            filename=path.name,
            modified_at_utc=modified,
        )
        entries.append((stat.st_mtime_ns, path.name, report))
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in entries[:limit]]


class FundamentalsSnapshotUIService:
    def __init__(
        self,
        *,
        paths: SnapshotPaths = PRODUCTION_SNAPSHOT_PATHS,
        output_dir: Path = FUNDAMENTAL_REPORTS_DIR,
        generator: Callable[..., dict[str, Any]] = generate_company_snapshot,
    ) -> None:
        self.paths = paths
        self.output_dir = output_dir.resolve()
        self._generator = generator

    def generate(
        self,
        *,
        ticker_input: str | None,
        report_date_input: str | None,
        overwrite: bool = False,
    ) -> FundamentalsUIResult:
        try:
            ticker = normalize_ticker(ticker_input)
        except ValueError:
            return FundamentalsUIResult(
                status="INVALID_TICKER",
                message="Enter a valid ticker symbol.",
            )
        try:
            report_date = normalize_report_date(report_date_input)
        except ValueError:
            return FundamentalsUIResult(
                status="INVALID_DATE",
                message="Enter a valid report date in YYYY-MM-DD format.",
                ticker=ticker,
            )

        try:
            generated = self._generator(
                self.paths,
                ticker=ticker,
                report_date=report_date,
                output_dir=self.output_dir,
                overwrite=bool(overwrite),
            )
            snapshot = generated["snapshot"]
            canonical_ticker = normalize_ticker(snapshot["identity"]["ticker"])
            filename = report_filename(canonical_ticker, report_date)
            output_path = Path(generated["output_path"]).resolve()
            if output_path.parent != self.output_dir or output_path.name != filename:
                raise RuntimeError("UNSAFE_REPORT_OUTPUT")
            publication_status = str(generated["status"])
            if publication_status not in {"CREATED", "OVERWRITTEN", "NO_CHANGE"}:
                raise RuntimeError("UNKNOWN_REPORT_PUBLICATION_STATUS")
            status = "NO_CHANGE" if publication_status == "NO_CHANGE" else "GENERATED"
            message = {
                "CREATED": "Report generated.",
                "OVERWRITTEN": "Existing report replaced.",
                "NO_CHANGE": "The existing report is already identical.",
            }.get(publication_status, "Report generated.")
            return FundamentalsUIResult(
                status=status,
                message=message,
                ticker=canonical_ticker,
                report_date=report_date,
                filename=filename,
                output_path=str(output_path),
                report_content_fingerprint=generated.get(
                    "report_content_fingerprint"
                ),
                publication_status=publication_status,
            )
        except FileExistsError:
            return FundamentalsUIResult(
                status="OVERWRITE_REQUIRED",
                message=(
                    "A different report already exists. Enable replacement to "
                    "overwrite only this report."
                ),
                ticker=ticker,
                report_date=report_date,
                filename=report_filename(ticker, report_date),
            )
        except LookupError:
            return FundamentalsUIResult(
                status="INVALID_TICKER",
                message="Ticker was not found in the current fundamentals universe.",
                ticker=ticker,
                report_date=report_date,
            )
        except Exception as exc:
            reason = str(exc).upper()
            if "NO_CANONICAL_TTM_ENDPOINT" in reason or "NOT_READY" in reason:
                return FundamentalsUIResult(
                    status="NOT_READY",
                    message="The fundamentals snapshot is not ready for this ticker and date.",
                    ticker=ticker,
                    report_date=report_date,
                )
            LOGGER.exception(
                "Fundamentals snapshot UI generation failed for ticker=%s report_date=%s",
                ticker,
                report_date,
            )
            return FundamentalsUIResult(
                status="FAILED",
                message="Report generation failed. See the application log for details.",
                ticker=ticker,
                report_date=report_date,
            )

    def recent_reports(self, *, limit: int = 10) -> list[RecentFundamentalsReport]:
        return list_recent_fundamentals_reports(self.output_dir, limit=limit)
