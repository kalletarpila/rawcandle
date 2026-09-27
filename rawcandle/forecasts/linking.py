from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.forecasts.contracts import (
    FAMILY_FISCAL_ESTIMATE,
    PROVIDER,
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_UNCHANGED,
    STATUS_VALID_NO_DATA,
)
from rawcandle.forecasts.fiscal_linker import (
    AMBIGUOUS,
    LINKED,
    LINK_RULE_VERSION,
    TARGET_FISCAL_QUARTER,
    TARGET_FISCAL_YEAR,
    UNRESOLVED,
    FiscalLinkDecision,
    ForecastFiscalLinker,
)
from rawcandle.forecasts.identity import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_RESOLVED,
    ForecastIdentityResolver,
    IdentityResolution,
)
from rawcandle.forecasts.schema import connect_forecasts_db, utc_now


AS_KNOWN = "AS_KNOWN"
CURRENT_RECONCILED = "CURRENT_RECONCILED"
SUCCESS_STATUSES = (
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_UNCHANGED,
    STATUS_VALID_NO_DATA,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("link timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _target_type(horizon: str) -> str | None:
    if horizon in {"0q", "+1q"}:
        return TARGET_FISCAL_QUARTER
    if horizon in {"0y", "+1y"}:
        return TARGET_FISCAL_YEAR
    return None


class ForecastLinkService:
    """Persist rebuildable fetch-time links and explicit current reconciliation."""

    def __init__(
        self,
        forecast_db: str | Path,
        fundamentals_db: str | Path,
        *,
        identity_resolver: ForecastIdentityResolver | None = None,
        fiscal_linker: ForecastFiscalLinker | None = None,
    ) -> None:
        self.forecast_db = Path(forecast_db)
        self.fundamentals_db = Path(fundamentals_db)
        self.identity_resolver = identity_resolver or ForecastIdentityResolver(
            self.fundamentals_db
        )
        self.fiscal_linker = fiscal_linker or ForecastFiscalLinker(
            self.fundamentals_db
        )

    @staticmethod
    def _fetch(connection: Any, fetch_id: str) -> Any:
        row = connection.execute(
            "SELECT * FROM forecast_fetch WHERE fetch_id=?", (fetch_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"forecast fetch not found: {fetch_id}")
        if row["forecast_family"] != FAMILY_FISCAL_ESTIMATE:
            raise ValueError("only fiscal-estimate fetches can be fiscal-linked")
        return row

    def _store_identity(
        self,
        connection: Any,
        fetch: Any,
        resolution: IdentityResolution,
        resolved_at_utc: str,
    ) -> str:
        material = {
            "fetch_id": fetch["fetch_id"],
            "identity_status": resolution.identity_status,
            "company_id": resolution.company_id,
            "security_id": resolution.security_id,
            "resolution_method": resolution.resolution_method,
            "reason_codes": resolution.reason_codes,
            "identity_rule_version": resolution.identity_rule_version,
            "evidence": resolution.evidence,
        }
        digest = _hash(material)
        resolution_id = f"identity_{digest[:32]}"
        connection.execute(
            """
            INSERT OR IGNORE INTO forecast_identity_resolution(
                resolution_id,resolution_hash,fetch_id,provider,provider_symbol,
                acquisition_timestamp_utc,resolved_at_utc,identity_status,
                company_id,security_id,resolution_method,reason_codes_json,
                identity_rule_version,evidence_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                resolution_id, digest, fetch["fetch_id"], PROVIDER,
                fetch["provider_symbol"], fetch["fetched_at_utc"], resolved_at_utc,
                resolution.identity_status, resolution.company_id,
                resolution.security_id, resolution.resolution_method,
                _json(resolution.reason_codes), resolution.identity_rule_version,
                _json(resolution.evidence),
            ),
        )
        return resolution_id

    @staticmethod
    def _latest_link(
        connection: Any,
        fetch_id: str,
        occurrence_index: int,
        rule_version: str,
        knowledge_mode: str,
    ) -> Any:
        return connection.execute(
            """
            SELECT * FROM forecast_fiscal_link
            WHERE fetch_id=? AND occurrence_index=? AND link_rule_version=?
              AND knowledge_mode=?
            ORDER BY linked_at_utc DESC,rowid DESC LIMIT 1
            """,
            (fetch_id, occurrence_index, rule_version, knowledge_mode),
        ).fetchone()

    def _store_link(
        self,
        connection: Any,
        *,
        fetch: Any,
        resolution_id: str,
        resolution: IdentityResolution,
        occurrence_index: int,
        provider_horizon: str,
        provider_end_date: str,
        decision: FiscalLinkDecision,
        knowledge_mode: str,
        fundamentals_as_of_utc: str,
        linked_at_utc: str,
    ) -> dict[str, Any]:
        previous = self._latest_link(
            connection,
            str(fetch["fetch_id"]),
            occurrence_index,
            decision.link_rule_version,
            knowledge_mode,
        )
        material = {
            "fetch_id": fetch["fetch_id"],
            "snapshot_id": fetch["snapshot_id"],
            "resolution_id": resolution_id,
            "occurrence_index": occurrence_index,
            "provider_horizon": provider_horizon,
            "provider_end_date": provider_end_date,
            "company_id": resolution.company_id,
            "security_id": resolution.security_id,
            "target_type": decision.target_type,
            "expected_fiscal_year": decision.expected_fiscal_year,
            "expected_fiscal_quarter": decision.expected_fiscal_quarter,
            "canonical_quarter_id": decision.canonical_quarter_id,
            "link_status": decision.link_status,
            "reason_codes": decision.reason_codes,
            "link_rule_version": decision.link_rule_version,
            "knowledge_mode": knowledge_mode,
            "fundamentals_as_of_utc": fundamentals_as_of_utc,
            "evidence": decision.evidence,
        }
        digest = _hash(material)
        link_id = f"link_{digest[:32]}"
        connection.execute(
            """
            INSERT OR IGNORE INTO forecast_fiscal_link(
                link_id,link_hash,fetch_id,snapshot_id,resolution_id,
                occurrence_index,provider_horizon,provider_end_date,company_id,
                security_id,target_type,expected_fiscal_year,
                expected_fiscal_quarter,canonical_quarter_id,link_status,
                reason_codes_json,link_rule_version,knowledge_mode,
                fundamentals_as_of_utc,linked_at_utc,supersedes_link_id,evidence_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                link_id, digest, fetch["fetch_id"], fetch["snapshot_id"],
                resolution_id, occurrence_index, provider_horizon,
                provider_end_date, resolution.company_id, resolution.security_id,
                decision.target_type, decision.expected_fiscal_year,
                decision.expected_fiscal_quarter, decision.canonical_quarter_id,
                decision.link_status, _json(decision.reason_codes),
                decision.link_rule_version, knowledge_mode,
                fundamentals_as_of_utc, linked_at_utc,
                previous["link_id"] if previous is not None else None,
                _json(decision.evidence),
            ),
        )
        row = connection.execute(
            "SELECT * FROM forecast_fiscal_link WHERE link_hash=?", (digest,)
        ).fetchone()
        return dict(row)

    @staticmethod
    def _identity_failure_decision(
        horizon: str, resolution: IdentityResolution
    ) -> FiscalLinkDecision:
        status = AMBIGUOUS if resolution.identity_status == IDENTITY_AMBIGUOUS else UNRESOLVED
        reason = (
            "IDENTITY_AMBIGUOUS"
            if resolution.identity_status == IDENTITY_AMBIGUOUS
            else "IDENTITY_UNRESOLVED"
        )
        return FiscalLinkDecision(
            status, _target_type(horizon), None, None, None, (reason,),
            {"identity_evidence": resolution.evidence},
        )

    def link_fetch(
        self, fetch_id: str, *, linked_at_utc: str | None = None
    ) -> list[dict[str, Any]]:
        linked_at = _utc(linked_at_utc or utc_now())
        with connect_forecasts_db(self.forecast_db) as connection:
            fetch = self._fetch(connection, fetch_id)
            resolution = self.identity_resolver.resolve(
                str(fetch["provider_symbol"]), str(fetch["fetched_at_utc"]),
                provider=str(fetch["provider"]),
            )
            resolution_id = self._store_identity(
                connection, fetch, resolution, linked_at
            )
            if fetch["snapshot_id"] is None:
                return []
            observations = connection.execute(
                """
                SELECT occurrence_index,provider_horizon,provider_end_date
                FROM forecast_estimate WHERE snapshot_id=?
                GROUP BY occurrence_index,provider_horizon,provider_end_date
                ORDER BY occurrence_index
                """,
                (fetch["snapshot_id"],),
            ).fetchall()
            links = []
            identity_conflict = (
                resolution.identity_status == IDENTITY_RESOLVED
                and (
                    (fetch["company_id"] is not None and int(fetch["company_id"]) != resolution.company_id)
                    or (fetch["security_id"] is not None and int(fetch["security_id"]) != resolution.security_id)
                )
            )
            for observation in observations:
                horizon = str(observation["provider_horizon"])
                if identity_conflict:
                    decision = FiscalLinkDecision(
                        UNRESOLVED, _target_type(horizon), None, None, None,
                        ("TARGET_CONFLICT",),
                        {
                            "fetch_company_id": fetch["company_id"],
                            "fetch_security_id": fetch["security_id"],
                            "resolved_company_id": resolution.company_id,
                            "resolved_security_id": resolution.security_id,
                        },
                    )
                elif resolution.identity_status != IDENTITY_RESOLVED:
                    decision = self._identity_failure_decision(horizon, resolution)
                else:
                    assert resolution.company_id is not None
                    decision = self.fiscal_linker.resolve(
                        company_id=resolution.company_id,
                        provider_horizon=horizon,
                        provider_end_date=str(observation["provider_end_date"]),
                        acquisition_timestamp_utc=str(fetch["fetched_at_utc"]),
                    )
                links.append(self._store_link(
                    connection,
                    fetch=fetch,
                    resolution_id=resolution_id,
                    resolution=resolution,
                    occurrence_index=int(observation["occurrence_index"]),
                    provider_horizon=horizon,
                    provider_end_date=str(observation["provider_end_date"]),
                    decision=decision,
                    knowledge_mode=AS_KNOWN,
                    fundamentals_as_of_utc=_utc(str(fetch["fetched_at_utc"])),
                    linked_at_utc=linked_at,
                ))
            return links

    def reconcile_fetch(
        self, fetch_id: str, *, reconciled_at_utc: str | None = None
    ) -> list[dict[str, Any]]:
        reconciled_at = _utc(reconciled_at_utc or utc_now())
        with connect_forecasts_db(self.forecast_db) as connection:
            fetch = self._fetch(connection, fetch_id)
            identity_row = connection.execute(
                """
                SELECT * FROM forecast_identity_resolution
                WHERE fetch_id=? ORDER BY resolved_at_utc DESC,rowid DESC LIMIT 1
                """,
                (fetch_id,),
            ).fetchone()
            if identity_row is None:
                raise LookupError("fetch must have an as-known identity resolution first")
            rows = connection.execute(
                """
                SELECT * FROM forecast_fiscal_link
                WHERE fetch_id=? AND knowledge_mode='AS_KNOWN'
                  AND link_rule_version=?
                ORDER BY occurrence_index,linked_at_utc DESC,rowid DESC
                """,
                (fetch_id, LINK_RULE_VERSION),
            ).fetchall()
            latest: dict[int, Any] = {}
            for row in rows:
                latest.setdefault(int(row["occurrence_index"]), row)
            reconciled = []
            for occurrence_index, row in sorted(latest.items()):
                if row["link_status"] != LINKED or row["expected_fiscal_year"] is None:
                    continue
                link_identity = connection.execute(
                    "SELECT * FROM forecast_identity_resolution WHERE resolution_id=?",
                    (row["resolution_id"],),
                ).fetchone()
                if link_identity is None:
                    raise LookupError("as-known link identity resolution is missing")
                resolution = IdentityResolution(
                    str(link_identity["identity_status"]),
                    link_identity["company_id"], link_identity["security_id"],
                    link_identity["resolution_method"],
                    tuple(json.loads(link_identity["reason_codes_json"])),
                    json.loads(link_identity["evidence_json"]),
                    str(link_identity["identity_rule_version"]),
                )
                reasons = list(json.loads(row["reason_codes_json"]))
                evidence = json.loads(row["evidence_json"])
                status = LINKED
                canonical_quarter_id = row["canonical_quarter_id"]
                if row["target_type"] == TARGET_FISCAL_QUARTER:
                    status, canonical_quarter_id, new_reasons, current_evidence = (
                        self.fiscal_linker.current_canonical_quarter(
                            int(row["company_id"]), int(row["expected_fiscal_year"]),
                            str(row["expected_fiscal_quarter"]),
                        )
                    )
                    reasons.extend(new_reasons)
                    evidence["current_reconciliation"] = current_evidence
                decision = FiscalLinkDecision(
                    status, str(row["target_type"]),
                    int(row["expected_fiscal_year"]),
                    row["expected_fiscal_quarter"], canonical_quarter_id,
                    tuple(dict.fromkeys(reasons)), evidence,
                )
                reconciled.append(self._store_link(
                    connection,
                    fetch=fetch,
                    resolution_id=str(link_identity["resolution_id"]),
                    resolution=resolution,
                    occurrence_index=occurrence_index,
                    provider_horizon=str(row["provider_horizon"]),
                    provider_end_date=str(row["provider_end_date"]),
                    decision=decision,
                    knowledge_mode=CURRENT_RECONCILED,
                    fundamentals_as_of_utc=reconciled_at,
                    linked_at_utc=reconciled_at,
                ))
            return reconciled

    def linked_as_known_at(
        self,
        *,
        company_id: int,
        fiscal_year: int,
        timestamp_utc: str,
        fiscal_quarter: str | None = None,
        link_rule_version: str = LINK_RULE_VERSION,
        knowledge_mode: str = AS_KNOWN,
    ) -> dict[str, Any] | None:
        if knowledge_mode not in {AS_KNOWN, CURRENT_RECONCILED}:
            raise ValueError("unsupported link knowledge mode")
        target_type = (
            TARGET_FISCAL_QUARTER if fiscal_quarter is not None else TARGET_FISCAL_YEAR
        )
        timestamp = _utc(timestamp_utc)
        placeholders = ",".join("?" for _ in SUCCESS_STATUSES)
        with connect_forecasts_db(self.forecast_db) as connection:
            fetch = connection.execute(
                f"""
                SELECT DISTINCT f.*
                FROM forecast_fetch f
                JOIN forecast_identity_resolution i ON i.fetch_id=f.fetch_id
                WHERE f.provider=? AND f.forecast_family=?
                  AND f.fetched_at_utc<=? AND f.status IN ({placeholders})
                  AND i.identity_status='RESOLVED' AND i.company_id=?
                ORDER BY f.fetched_at_utc DESC,f.rowid DESC LIMIT 1
                """,
                (PROVIDER, FAMILY_FISCAL_ESTIMATE, timestamp, *SUCCESS_STATUSES, company_id),
            ).fetchone()
            if fetch is None:
                return None
            result: dict[str, Any] = {"fetch": dict(fetch), "matches": []}
            if fetch["snapshot_id"] is None:
                return result
            links = connection.execute(
                """
                SELECT * FROM forecast_fiscal_link
                WHERE fetch_id=? AND link_rule_version=? AND knowledge_mode=?
                ORDER BY occurrence_index,linked_at_utc DESC,rowid DESC
                """,
                (fetch["fetch_id"], link_rule_version, knowledge_mode),
            ).fetchall()
            latest: dict[int, Any] = {}
            for row in links:
                if knowledge_mode == AS_KNOWN and row["fundamentals_as_of_utc"] > fetch["fetched_at_utc"]:
                    continue
                latest.setdefault(int(row["occurrence_index"]), row)
            for row in latest.values():
                if (
                    row["link_status"] != LINKED
                    or row["target_type"] != target_type
                    or int(row["expected_fiscal_year"]) != int(fiscal_year)
                    or row["expected_fiscal_quarter"] != fiscal_quarter
                ):
                    continue
                records = [
                    dict(item)
                    for item in connection.execute(
                        """
                        SELECT * FROM forecast_estimate
                        WHERE snapshot_id=? AND occurrence_index=? ORDER BY estimate_id
                        """,
                        (fetch["snapshot_id"], row["occurrence_index"]),
                    )
                ]
                result["matches"].append({"link": dict(row), "records": records})
            return result
