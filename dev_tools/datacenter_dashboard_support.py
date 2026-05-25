from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Optional


@dataclass(frozen=True)
class DatacenterReportStatus:
    horizon: str
    status: str
    path: Optional[str]
    modified_at: Optional[str]


@dataclass(frozen=True)
class DatacenterDashboardStatus:
    overall_status: str
    reports: list[DatacenterReportStatus]


_HORIZON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "rolling 30d",
        re.compile(r"^datacenter_rolling_30(?:_.+)?\.(?:md|csv)$"),
    ),
    (
        "rolling 5d",
        re.compile(r"^datacenter_rolling_5(?:_.+)?\.(?:md|csv)$"),
    ),
    (
        "rolling 2d",
        re.compile(r"^datacenter_rolling_2(?:_.+)?\.(?:md|csv)$"),
    ),
    (
        "daily",
        re.compile(r"^datacenter_daily(?:_.+)?\.(?:md|csv)$"),
    ),
)
_REPORT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _report_sort_key(path: Path) -> tuple[float, int, str]:
    stat_result = path.stat()
    suffix_priority = 1 if path.suffix.lower() == ".md" else 0
    return (stat_result.st_mtime, suffix_priority, path.name)


def _format_modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _find_latest_report(
    reports_dir_path: Path, pattern: re.Pattern[str], *, report_date: str | None = None
) -> Optional[DatacenterReportStatus]:
    candidates = [
        path
        for path in reports_dir_path.iterdir()
        if path.is_file()
        and pattern.match(path.name)
        and (report_date is None or f"_{report_date}_" in path.name)
    ]
    if not candidates:
        return None

    # Prefer the newest file by mtime, then markdown over csv, then filename.
    latest = max(candidates, key=_report_sort_key)
    return DatacenterReportStatus(
        horizon="",
        status="OK",
        path=str(latest),
        modified_at=_format_modified_at(latest),
    )


def discover_datacenter_dashboard_status(
    reports_dir: str,
    report_date: str | None = None,
) -> DatacenterDashboardStatus:
    reports_dir_path = Path(reports_dir.strip())
    report_statuses: list[DatacenterReportStatus] = []

    if report_date is not None and not _REPORT_DATE_RE.match(report_date.strip()):
        raise ValueError(f"invalid report_date format: {report_date}")

    if not reports_dir_path.exists() or not reports_dir_path.is_dir():
        return DatacenterDashboardStatus(
            overall_status="MISSING",
            reports=[
                DatacenterReportStatus(
                    horizon=horizon,
                    status="MISSING",
                    path=None,
                    modified_at=None,
                )
                for horizon, _pattern in _HORIZON_PATTERNS
            ],
        )

    for horizon, pattern in _HORIZON_PATTERNS:
        latest_report = _find_latest_report(
            reports_dir_path,
            pattern,
            report_date=report_date.strip() if report_date is not None else None,
        )
        if latest_report is None:
            report_statuses.append(
                DatacenterReportStatus(
                    horizon=horizon,
                    status="MISSING",
                    path=None,
                    modified_at=None,
                )
            )
            continue
        report_statuses.append(
            DatacenterReportStatus(
                horizon=horizon,
                status="OK",
                path=latest_report.path,
                modified_at=latest_report.modified_at,
            )
        )

    ok_count = sum(1 for report in report_statuses if report.status == "OK")
    if ok_count == 0:
        overall_status = "MISSING"
    elif ok_count == len(report_statuses):
        overall_status = "READY"
    else:
        overall_status = "PARTIAL"

    return DatacenterDashboardStatus(
        overall_status=overall_status,
        reports=report_statuses,
    )
