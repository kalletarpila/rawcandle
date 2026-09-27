from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LINK_RULE_VERSION = "fundamentals_v4_fiscal_link_v1"
LINKED = "LINKED"
AMBIGUOUS = "AMBIGUOUS"
UNRESOLVED = "UNRESOLVED"
TARGET_FISCAL_QUARTER = "FISCAL_QUARTER"
TARGET_FISCAL_YEAR = "FISCAL_YEAR"
END_DATE_TOLERANCE_DAYS = 45


@dataclass(frozen=True)
class FiscalLinkDecision:
    link_status: str
    target_type: str | None
    expected_fiscal_year: int | None
    expected_fiscal_quarter: str | None
    canonical_quarter_id: int | None
    reason_codes: tuple[str, ...]
    evidence: dict[str, Any]
    link_rule_version: str = LINK_RULE_VERSION


def _as_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("fiscal-link timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _advance_quarter(fiscal_year: int, fiscal_quarter: str, steps: int) -> tuple[int, str]:
    ordinal = fiscal_year * 4 + int(fiscal_quarter[1]) - 1 + steps
    return ordinal // 4, f"Q{ordinal % 4 + 1}"


def _annual_target(latest_year: int, latest_quarter: str, offset: int) -> int:
    base = latest_year + (1 if latest_quarter == "Q4" else 0)
    return base + offset


class ForecastFiscalLinker:
    """Resolve Yahoo moving horizons from Fundamentals facts known at a cutoff."""

    def __init__(
        self,
        fundamentals_db: str | Path,
        *,
        end_date_tolerance_days: int = END_DATE_TOLERANCE_DAYS,
    ) -> None:
        self.fundamentals_db = Path(fundamentals_db)
        self.end_date_tolerance_days = int(end_date_tolerance_days)

    def _known_quarters(
        self, connection: sqlite3.Connection, company_id: int, as_of_date: str
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT quarter_id,fiscal_year,fiscal_quarter,period_end,
                   source_availability_date,first_public_result_date,
                   COALESCE(first_public_result_date,source_availability_date) knowledge_date
            FROM v4_quarter
            WHERE company_id=?
              AND COALESCE(first_public_result_date,source_availability_date) IS NOT NULL
              AND COALESCE(first_public_result_date,source_availability_date)<=?
            ORDER BY fiscal_year DESC,
                     CAST(SUBSTR(fiscal_quarter,2) AS INTEGER) DESC,
                     quarter_id DESC
            """,
            (company_id, as_of_date),
        ).fetchall()

    @staticmethod
    def _target_rows(
        connection: sqlite3.Connection,
        company_id: int,
        fiscal_year: int,
        fiscal_quarter: str,
        *,
        knowledge_date: str | None,
    ) -> list[sqlite3.Row]:
        boundary = "" if knowledge_date is None else (
            " AND COALESCE(first_public_result_date,source_availability_date) IS NOT NULL"
            " AND COALESCE(first_public_result_date,source_availability_date)<=?"
        )
        parameters: tuple[Any, ...] = (company_id, fiscal_year, fiscal_quarter)
        if knowledge_date is not None:
            parameters += (knowledge_date,)
        return connection.execute(
            "SELECT quarter_id,period_end,source_availability_date,"
            "first_public_result_date FROM v4_quarter "
            "WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?" + boundary +
            " ORDER BY quarter_id",
            parameters,
        ).fetchall()

    def _end_date_evidence(
        self,
        provider_end_date: str,
        expected_end: date | None,
        evidence: dict[str, Any],
    ) -> str | None:
        evidence["provider_end_date"] = provider_end_date
        evidence["end_date_tolerance_days"] = self.end_date_tolerance_days
        if expected_end is None:
            return None
        difference = abs((_as_date(provider_end_date) - expected_end).days)
        evidence["expected_end_date"] = expected_end.isoformat()
        evidence["end_date_difference_days"] = difference
        return (
            "END_DATE_SUPPORT"
            if difference <= self.end_date_tolerance_days
            else "END_DATE_OUTSIDE_TOLERANCE"
        )

    @staticmethod
    def _estimated_quarter_end(latest: sqlite3.Row, steps: int) -> date:
        return _as_date(str(latest["period_end"])) + timedelta(days=91 * steps)

    @staticmethod
    def _estimated_year_end(latest: sqlite3.Row, target_year: int) -> date:
        quarter_number = int(str(latest["fiscal_quarter"])[1])
        latest_year_end = _as_date(str(latest["period_end"])) + timedelta(
            days=91 * (4 - quarter_number)
        )
        return latest_year_end + timedelta(
            days=364 * (target_year - int(latest["fiscal_year"]))
        )

    @staticmethod
    def _anchor_year_end(
        connection: sqlite3.Connection,
        company_id: int,
        target_year: int,
        as_of_utc: str,
    ) -> tuple[date | None, dict[str, Any] | None]:
        row = connection.execute(
            """
            SELECT fiscal_year,fiscal_year_start,confidence,observed_verified,created_at_utc
            FROM company_fiscal_year_anchor
            WHERE company_id=? AND fiscal_year=?
              AND datetime(created_at_utc)<=datetime(?)
            """,
            (company_id, target_year + 1, as_of_utc),
        ).fetchone()
        if row is None:
            return None, None
        start = _as_date(str(row["fiscal_year_start"]))
        return start - timedelta(days=1), dict(row)

    def resolve(
        self,
        *,
        company_id: int,
        provider_horizon: str,
        provider_end_date: str,
        acquisition_timestamp_utc: str,
    ) -> FiscalLinkDecision:
        acquired = _utc(acquisition_timestamp_utc)
        as_of_utc = acquired.isoformat(timespec="microseconds").replace("+00:00", "Z")
        as_of_date = acquired.date().isoformat()
        evidence: dict[str, Any] = {
            "company_id": int(company_id),
            "provider_horizon": provider_horizon,
            "fundamentals_as_of_utc": as_of_utc,
            "knowledge_boundary": "COALESCE(first_public_result_date,source_availability_date)",
        }
        if provider_horizon not in {"0q", "+1q", "0y", "+1y"}:
            return FiscalLinkDecision(
                UNRESOLVED, None, None, None, None,
                ("PROVIDER_HORIZON_UNSUPPORTED",), evidence,
            )

        with _readonly(self.fundamentals_db) as connection:
            profile = connection.execute(
                """
                SELECT typical_fiscal_year_start,chain_status,break_reason,
                       bootstrap_status,source,created_at_utc
                FROM company_fiscal_calendar_profile
                WHERE company_id=? AND datetime(created_at_utc)<=datetime(?)
                """,
                (company_id, as_of_utc),
            ).fetchone()
            if profile is not None:
                evidence["fiscal_calendar_profile"] = dict(profile)
            quarters = self._known_quarters(connection, company_id, as_of_date)
            if not quarters:
                return FiscalLinkDecision(
                    UNRESOLVED, None, None, None, None,
                    ("INSUFFICIENT_FISCAL_CONTEXT",), evidence,
                )
            latest = quarters[0]
            latest_key = (int(latest["fiscal_year"]), str(latest["fiscal_quarter"]))
            latest_rows = [
                row
                for row in quarters
                if (int(row["fiscal_year"]), str(row["fiscal_quarter"])) == latest_key
            ]
            evidence["latest_known_quarter"] = {
                "quarter_id": int(latest["quarter_id"]),
                "fiscal_year": latest_key[0],
                "fiscal_quarter": latest_key[1],
                "period_end": latest["period_end"],
                "knowledge_date": latest["knowledge_date"],
            }
            if len({int(row["quarter_id"]) for row in latest_rows}) > 1:
                return FiscalLinkDecision(
                    AMBIGUOUS, None, None, None, None,
                    ("MULTIPLE_VALID_TARGETS",), evidence,
                )

            reasons = ["SEQUENTIAL_FISCAL_MATCH"]
            if provider_horizon in {"0q", "+1q"}:
                steps = 1 if provider_horizon == "0q" else 2
                fiscal_year, fiscal_quarter = _advance_quarter(*latest_key, steps)
                if fiscal_year != latest_key[0]:
                    reasons.append("FISCAL_YEAR_ROLLOVER")
                target_rows = self._target_rows(
                    connection, company_id, fiscal_year, fiscal_quarter,
                    knowledge_date=as_of_date,
                )
                if len(target_rows) > 1:
                    return FiscalLinkDecision(
                        AMBIGUOUS, TARGET_FISCAL_QUARTER, fiscal_year,
                        fiscal_quarter, None,
                        tuple(reasons + ["MULTIPLE_VALID_TARGETS"]), evidence,
                    )
                canonical_quarter_id = (
                    int(target_rows[0]["quarter_id"]) if target_rows else None
                )
                expected_end = (
                    _as_date(str(target_rows[0]["period_end"]))
                    if target_rows
                    else self._estimated_quarter_end(latest, steps)
                )
                end_reason = self._end_date_evidence(
                    provider_end_date, expected_end, evidence
                )
                if end_reason:
                    reasons.append(end_reason)
                evidence["candidate"] = {
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                    "canonical_quarter_id_as_known": canonical_quarter_id,
                }
                return FiscalLinkDecision(
                    LINKED, TARGET_FISCAL_QUARTER, fiscal_year, fiscal_quarter,
                    canonical_quarter_id, tuple(reasons), evidence,
                )

            annual_offset = 0 if provider_horizon == "0y" else 1
            fiscal_year = _annual_target(*latest_key, annual_offset)
            expected_end, anchor = self._anchor_year_end(
                connection, company_id, fiscal_year, as_of_utc
            )
            if anchor is not None:
                reasons.append("FISCAL_ANCHOR_SUPPORT")
                evidence["fiscal_anchor"] = anchor
            else:
                expected_end = self._estimated_year_end(latest, fiscal_year)
            if fiscal_year != latest_key[0]:
                reasons.append("FISCAL_YEAR_ROLLOVER")
            end_reason = self._end_date_evidence(
                provider_end_date, expected_end, evidence
            )
            if end_reason:
                reasons.append(end_reason)
            evidence["candidate"] = {"fiscal_year": fiscal_year}
            return FiscalLinkDecision(
                LINKED, TARGET_FISCAL_YEAR, fiscal_year, None, None,
                tuple(reasons), evidence,
            )

    def current_canonical_quarter(
        self, company_id: int, fiscal_year: int, fiscal_quarter: str
    ) -> tuple[str, int | None, tuple[str, ...], dict[str, Any]]:
        with _readonly(self.fundamentals_db) as connection:
            rows = self._target_rows(
                connection, company_id, fiscal_year, fiscal_quarter,
                knowledge_date=None,
            )
        evidence = {
            "company_id": company_id,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "candidate_quarter_ids": [int(row["quarter_id"]) for row in rows],
        }
        if len(rows) == 1:
            return LINKED, int(rows[0]["quarter_id"]), (
                "CANONICAL_QUARTER_RECONCILED",
            ), evidence
        if len(rows) > 1:
            return AMBIGUOUS, None, ("MULTIPLE_VALID_TARGETS",), evidence
        return LINKED, None, ("CANONICAL_QUARTER_NOT_YET_AVAILABLE",), evidence
