from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IDENTITY_RULE_VERSION = "fundamentals_v4_identity_v1"
IDENTITY_RESOLVED = "RESOLVED"
IDENTITY_AMBIGUOUS = "AMBIGUOUS"
IDENTITY_UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class IdentityResolution:
    identity_status: str
    company_id: int | None
    security_id: int | None
    resolution_method: str | None
    reason_codes: tuple[str, ...]
    evidence: dict[str, Any]
    identity_rule_version: str = IDENTITY_RULE_VERSION


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("identity timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


class ForecastIdentityResolver:
    """Resolve a provider symbol without changing Fundamentals identity state."""

    def __init__(self, fundamentals_db: str | Path) -> None:
        self.fundamentals_db = Path(fundamentals_db)

    @staticmethod
    def _result(
        rows: list[sqlite3.Row], method: str, evidence: dict[str, Any]
    ) -> IdentityResolution | None:
        identities = {
            (int(row["company_id"]), int(row["security_id"])) for row in rows
        }
        evidence["candidate_count"] = len(identities)
        evidence["candidates"] = [
            {"company_id": company_id, "security_id": security_id}
            for company_id, security_id in sorted(identities)
        ]
        if len(identities) == 1:
            company_id, security_id = next(iter(identities))
            return IdentityResolution(
                IDENTITY_RESOLVED,
                company_id,
                security_id,
                method,
                ("IDENTITY_RESOLVED",),
                evidence,
            )
        if len(identities) > 1:
            return IdentityResolution(
                IDENTITY_AMBIGUOUS,
                None,
                None,
                method,
                ("IDENTITY_AMBIGUOUS",),
                evidence,
            )
        return None

    def resolve(
        self,
        provider_symbol: str,
        acquisition_timestamp_utc: str,
        *,
        provider: str = "YAHOO_FINANCE",
    ) -> IdentityResolution:
        symbol = provider_symbol.strip().upper()
        if not symbol:
            raise ValueError("provider symbol is required")
        acquired = _utc(acquisition_timestamp_utc)
        acquired_utc = acquired.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        acquired_date = acquired.date().isoformat()

        with _readonly(self.fundamentals_db) as connection:
            provider_rows = connection.execute(
                """
                SELECT s.company_id,s.security_id,p.provider_security_id,
                       p.provider_ticker,p.created_at_utc
                FROM provider_security_identity p
                JOIN security s USING(security_id)
                WHERE UPPER(p.provider)=?
                  AND (UPPER(p.provider_security_id)=? OR UPPER(p.provider_ticker)=?)
                  AND datetime(p.created_at_utc)<=datetime(?)
                ORDER BY s.security_id
                """,
                (provider.upper(), symbol, symbol, acquired_utc),
            ).fetchall()
            result = self._result(
                provider_rows,
                "PROVIDER_SECURITY_IDENTITY",
                {
                    "provider": provider,
                    "provider_symbol": symbol,
                    "acquisition_timestamp_utc": acquired_utc,
                },
            )
            if result is not None:
                return result

            alias_rows = connection.execute(
                """
                SELECT s.company_id,s.security_id,a.alias_id,a.provider,
                       a.valid_from,a.valid_to,a.source
                FROM ticker_alias a
                JOIN security s USING(security_id)
                WHERE UPPER(a.ticker)=?
                  AND (a.valid_from IS NULL OR a.valid_from<=?)
                  AND (a.valid_to IS NULL OR a.valid_to>=?)
                ORDER BY s.security_id,a.alias_id
                """,
                (symbol, acquired_date, acquired_date),
            ).fetchall()
            result = self._result(
                alias_rows,
                "TICKER_ALIAS_AS_OF",
                {
                    "provider": provider,
                    "provider_symbol": symbol,
                    "acquisition_date": acquired_date,
                    "aliases": [
                        {
                            "alias_id": int(row["alias_id"]),
                            "provider": row["provider"],
                            "valid_from": row["valid_from"],
                            "valid_to": row["valid_to"],
                            "source": row["source"],
                        }
                        for row in alias_rows
                    ],
                },
            )
            if result is not None:
                return result

            current_rows = connection.execute(
                """
                SELECT company_id,security_id,current_ticker,active,valid_from,valid_to
                FROM security
                WHERE UPPER(current_ticker)=?
                  AND (valid_from IS NULL OR valid_from<=?)
                  AND (valid_to IS NULL OR valid_to>=?)
                ORDER BY security_id
                """,
                (symbol, acquired_date, acquired_date),
            ).fetchall()
            result = self._result(
                current_rows,
                "CURRENT_SECURITY_TICKER_AS_OF",
                {
                    "provider": provider,
                    "provider_symbol": symbol,
                    "acquisition_date": acquired_date,
                    "security_validity": [
                        {
                            "security_id": int(row["security_id"]),
                            "active": int(row["active"]),
                            "valid_from": row["valid_from"],
                            "valid_to": row["valid_to"],
                        }
                        for row in current_rows
                    ],
                },
            )
            if result is not None:
                return result

        return IdentityResolution(
            IDENTITY_UNRESOLVED,
            None,
            None,
            None,
            ("IDENTITY_UNRESOLVED",),
            {
                "provider": provider,
                "provider_symbol": symbol,
                "acquisition_timestamp_utc": acquired_utc,
            },
        )
