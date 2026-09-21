from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.contracts import AdminOperationType, RunStage, build_batch_request, fingerprint, utc_now
from rawcandle.fundamentals.admin.provider_cik import extract_sharadar_cik, normalize_cik


CONTRACT_VERSION = "PHASE13G3_19_IDENTITY_REVIEW_APPROVAL_V2"
REGISTRY_SCHEMA_VERSION = "2.0"
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("identity_resolutions.json")
SUPPORTED_EXCHANGES = {"NASDAQ", "NYSE", "NYSEMKT"}


class ResolutionClass(str, Enum):
    EXISTING_SECURITY = "EXISTING_SECURITY"
    NEW_SECURITY = "NEW_SECURITY"
    TICKER_TRANSITION_SAME_SECURITY = "TICKER_TRANSITION_SAME_SECURITY"
    BUSINESS_COMBINATION_NEW_SECURITY = "BUSINESS_COMBINATION_NEW_SECURITY"
    REORGANIZATION_SUCCESSOR = "REORGANIZATION_SUCCESSOR"
    IDENTITY_REVIEW_REQUIRED = "IDENTITY_REVIEW_REQUIRED"


class AuthorityClass(str, Enum):
    LOCAL_DETERMINISTIC = "LOCAL_DETERMINISTIC"
    APPROVED_REVIEW = "APPROVED_REVIEW"
    PROPOSED_REVIEW = "PROPOSED_REVIEW"
    INSUFFICIENT = "INSUFFICIENT"


class ReviewReadiness(str, Enum):
    NOT_REVIEWED = "NOT_REVIEWED"
    PROPOSED_NOT_READY = "PROPOSED_NOT_READY"
    PROPOSED_READY_FOR_OPERATOR_APPROVAL = "PROPOSED_READY_FOR_OPERATOR_APPROVAL"
    APPROVED_VALID = "APPROVED_VALID"
    APPROVED_INVALID = "APPROVED_INVALID"
    APPROVED_SUPERSEDED_BY_LOCAL_DETERMINISTIC = "APPROVED_SUPERSEDED_BY_LOCAL_DETERMINISTIC"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class IdentityResolution:
    requested_ticker: str
    resolution_class: str
    company_continuity: str
    security_continuity: str
    ticker_relationship: str
    provider_continuity: str
    authority_class: str
    automatic_mutation_permitted: bool
    exchange_status: str
    reason_codes: tuple[str, ...]
    explanation: str
    provider_metadata: Mapping[str, Any]
    canonical_evidence: Mapping[str, Any]
    reviewed_resolution: Mapping[str, Any] | None
    review_status: str | None
    readiness_state: str
    approval_fingerprint: str | None
    current_state_validation: Mapping[str, Any]
    unresolved_assumptions: tuple[str, ...]
    proposed_mutation: Mapping[str, Any]
    mutation: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _normalized_evidence(evidence: Any) -> list[dict[str, str]]:
    if not isinstance(evidence, list):
        return []
    normalized = []
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        normalized.append({
            key: str(item.get(key) or "").strip()
            for key in ("source_type", "source_authority", "reference", "fact")
        })
    return sorted(normalized, key=lambda item: tuple(item.values()))


def approval_material(record: Mapping[str, Any], *, schema_version: str = REGISTRY_SCHEMA_VERSION) -> dict[str, Any]:
    approved = record.get("approved_resolution")
    source = approved if isinstance(approved, Mapping) else record
    expected = source.get("expected_state") if isinstance(source.get("expected_state"), Mapping) else {}
    return {
        "registry_schema_version": schema_version,
        "subject_ticker": str(source.get("subject_ticker") or record.get("subject_ticker") or "").strip().upper(),
        "resolution_class": source.get("resolution_class"),
        "company_continuity": source.get("company_continuity"),
        "security_continuity": source.get("security_continuity"),
        "ticker_relationship": source.get("ticker_relationship"),
        "provider_continuity": source.get("provider_continuity"),
        "predecessor_ticker": str(source.get("predecessor_ticker") or "").strip().upper() or None,
        "canonical_company_id": source.get("canonical_company_id"),
        "canonical_security_id": source.get("canonical_security_id"),
        "cik": normalize_cik(source.get("cik")),
        "provider_permaticker": str(source.get("provider_permaticker") or "").strip() or None,
        "exchange": str(source.get("exchange") or "").strip().upper() or None,
        "effective_date": source.get("effective_date"),
        "expected_state": {str(key): expected[key] for key in sorted(expected)},
        "evidence": _normalized_evidence(source.get("evidence", record.get("evidence"))),
    }


def approval_fingerprint(record: Mapping[str, Any], *, schema_version: str = REGISTRY_SCHEMA_VERSION) -> str:
    encoded = json.dumps(
        approval_material(record, schema_version=schema_version),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_review_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != REGISTRY_SCHEMA_VERSION or not isinstance(payload.get("records"), list):
        raise ValueError("IDENTITY_REVIEW_REGISTRY_SCHEMA_INVALID")
    records: dict[str, Mapping[str, Any]] = {}
    required = {
        "subject_ticker", "resolution_class", "company_continuity", "security_continuity",
        "ticker_relationship", "provider_continuity", "review_status", "reason", "evidence",
        "expected_state", "unresolved_assumptions",
    }
    for raw in payload["records"]:
        if not isinstance(raw, Mapping) or not required.issubset(raw):
            raise ValueError("IDENTITY_REVIEW_RECORD_INVALID")
        ticker = str(raw["subject_ticker"]).strip().upper()
        if not ticker or ticker in records:
            raise ValueError("IDENTITY_REVIEW_RECORD_DUPLICATE_OR_EMPTY")
        status = str(raw["review_status"]).upper()
        if status not in {"PROPOSED", "APPROVED", "REJECTED"}:
            raise ValueError("IDENTITY_REVIEW_STATUS_INVALID")
        if str(raw["resolution_class"]) not in {item.value for item in ResolutionClass}:
            raise ValueError("IDENTITY_REVIEW_CLASS_INVALID")
        if not isinstance(raw.get("expected_state"), Mapping) or not isinstance(raw.get("unresolved_assumptions"), list):
            raise ValueError("IDENTITY_REVIEW_BINDING_INVALID")
        if status == "APPROVED":
            if not isinstance(raw.get("approved_resolution"), Mapping) or not raw.get("approval_fingerprint"):
                raise ValueError("IDENTITY_APPROVAL_CONTRACT_MISSING")
        records[ticker] = dict(raw)
    return records


def _provider_metadata(provider_db: Path, ticker: str) -> dict[str, Any]:
    with _readonly(provider_db) as conn:
        if not _table_exists(conn, "sharadar_ticker_metadata"):
            return {"status": "MISSING", "candidate_rows": 0, "identities": []}
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(sharadar_ticker_metadata)")}
        order = (
            "CASE WHEN table_name='fundamentals' THEN 0 WHEN table_name='stocks' THEN 1 ELSE 2 END,lastupdated DESC"
            if "table_name" in columns
            else ("lastupdated DESC" if "lastupdated" in columns else "ticker")
        )
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM sharadar_ticker_metadata WHERE UPPER(ticker)=? ORDER BY {order}",
            (ticker,),
        )]
    if not rows:
        return {"status": "MISSING", "candidate_rows": 0, "identities": []}
    preferred = [row for row in rows if str(row.get("table_name") or "fundamentals").lower() == "fundamentals"] or rows
    identities: dict[tuple[str, str], dict[str, Any]] = {}
    for row in preferred:
        item = dict(row)
        cik = extract_sharadar_cik(item.get("secfilings") or item.get("cik")).cik_normalized
        if cik:
            item["cik"] = cik
        key = (str(item.get("permaticker") or ""), str(cik or ""))
        identities.setdefault(key, item)
    status = "FOUND" if len(identities) == 1 else "AMBIGUOUS"
    result: dict[str, Any] = {
        "status": status,
        "source": "sharadar_ticker_metadata",
        "candidate_rows": len(preferred),
        "identities": [dict(item) for item in identities.values()],
    }
    if status == "FOUND":
        result["identity"] = next(iter(identities.values()))
    return result


def _canonical_evidence(canonical_db: Path, ticker: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    permaticker = str(metadata.get("permaticker") or "")
    cik = normalize_cik(metadata.get("cik"))
    with _readonly(canonical_db) as conn:
        current = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,s.valid_from,s.valid_to "
            "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=? ORDER BY s.security_id",
            (ticker,),
        )] if _table_exists(conn, "security") else []
        aliases = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.active,a.ticker,a.provider,a.valid_from,a.valid_to "
            "FROM ticker_alias a JOIN security s USING(security_id) JOIN company c USING(company_id) WHERE UPPER(a.ticker)=? ORDER BY a.alias_id",
            (ticker,),
        )] if _table_exists(conn, "ticker_alias") else []
        provider_matches = [dict(row) for row in conn.execute(
            "SELECT p.provider,p.provider_security_id,p.provider_ticker,p.security_id,s.company_id,s.current_ticker,s.active "
            "FROM provider_security_identity p JOIN security s USING(security_id) "
            "WHERE p.provider='SHARADAR' AND p.provider_security_id=?",
            (permaticker,),
        )] if permaticker and _table_exists(conn, "provider_security_identity") else []
        company_matches = [dict(row) for row in conn.execute(
            "SELECT cc.company_id,cc.cik_normalized,c.company_key,c.company_name,c.status FROM company_cik cc JOIN company c USING(company_id)"
        ) if normalize_cik(row["cik_normalized"]) == cik] if cik and _table_exists(conn, "company_cik") else []
    return {
        "current_ticker_matches": current,
        "alias_matches": aliases,
        "provider_security_matches": provider_matches,
        "company_cik_matches": company_matches,
    }


def _review_current_state(
    paths: Any,
    ticker: str,
    review: Mapping[str, Any],
    provider: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = provider.get("identity") if isinstance(provider.get("identity"), Mapping) else {}
    predecessor_ticker = str(review.get("predecessor_ticker") or "").strip().upper()
    predecessor_provider = _provider_metadata(Path(paths.provider_db), predecessor_ticker) if predecessor_ticker else {}
    predecessor_metadata = (
        predecessor_provider.get("identity")
        if isinstance(predecessor_provider.get("identity"), Mapping)
        else {}
    )
    company_id = review.get("canonical_company_id")
    security_id = review.get("canonical_security_id")
    company_row = None
    security_row = None
    company_ciks: list[str] = []
    with _readonly(Path(paths.canonical_db)) as conn:
        if company_id is not None:
            company_row = conn.execute(
                "SELECT company_id,company_key,company_name,status FROM company WHERE company_id=?",
                (company_id,),
            ).fetchone()
            if _table_exists(conn, "company_cik"):
                company_ciks = sorted(
                    filter(None, (normalize_cik(row[0]) for row in conn.execute(
                        "SELECT cik_normalized FROM company_cik WHERE company_id=?", (company_id,)
                    )))
                )
        if security_id is not None:
            security_row = conn.execute(
                "SELECT security_id,company_id,current_ticker,exchange,active,valid_from,valid_to "
                "FROM security WHERE security_id=?",
                (security_id,),
            ).fetchone()
    actual = {
        "provider_status": provider.get("status"),
        "provider_cik": normalize_cik(metadata.get("cik")),
        "provider_permaticker": str(metadata.get("permaticker") or "") or None,
        "provider_exchange": str(metadata.get("exchange") or "").upper() or None,
        "predecessor_provider_status": predecessor_provider.get("status"),
        "predecessor_provider_cik": normalize_cik(predecessor_metadata.get("cik")),
        "predecessor_provider_permaticker": str(predecessor_metadata.get("permaticker") or "") or None,
        "predecessor_provider_exchange": str(predecessor_metadata.get("exchange") or "").upper() or None,
        "subject_current_security_ids": sorted(int(row["security_id"]) for row in canonical["current_ticker_matches"]),
        "subject_alias_security_ids": sorted(set(int(row["security_id"]) for row in canonical["alias_matches"])),
        "cik_company_ids": sorted(int(row["company_id"]) for row in canonical["company_cik_matches"]),
        "permaticker_security_ids": sorted(int(row["security_id"]) for row in canonical["provider_security_matches"]),
        "canonical_company": dict(company_row) if company_row else None,
        "canonical_company_ciks": company_ciks,
        "canonical_security": dict(security_row) if security_row else None,
    }
    expected = review.get("expected_state") if isinstance(review.get("expected_state"), Mapping) else {}
    mismatches = []
    for key, expected_value in expected.items():
        if key.startswith("canonical_company_") and key != "canonical_company_ciks":
            field = key.removeprefix("canonical_company_")
            actual_value = actual["canonical_company"].get(field) if actual["canonical_company"] else None
        elif key.startswith("canonical_security_"):
            field = key.removeprefix("canonical_security_")
            actual_value = actual["canonical_security"].get(field) if actual["canonical_security"] else None
        else:
            actual_value = actual.get(key)
        if actual_value != expected_value:
            mismatches.append({"field": key, "expected": expected_value, "actual": actual_value})
    return {
        "status": "MATCH" if not mismatches else "CONFLICT",
        "expected": dict(expected),
        "actual": actual,
        "mismatches": mismatches,
    }


def _review_readiness(review: Mapping[str, Any], validation: Mapping[str, Any]) -> tuple[ReviewReadiness, tuple[str, ...]]:
    unresolved = tuple(str(item) for item in review.get("unresolved_assumptions", []) if str(item).strip())
    missing = []
    if not _normalized_evidence(review.get("evidence")):
        missing.append("AUTHORITATIVE_EVIDENCE_REQUIRED")
    if not review.get("effective_date"):
        missing.append("EFFECTIVE_DATE_REQUIRED")
    if not review.get("exchange"):
        missing.append("EXCHANGE_REQUIRED")
    if str(review.get("security_continuity")) == "SAME_SECURITY" and (
        review.get("canonical_company_id") is None or review.get("canonical_security_id") is None
    ):
        missing.append("SAME_SECURITY_CANONICAL_TARGET_REQUIRED")
    if str(review.get("company_continuity")) in {"SAME_COMPANY", "SAME_LEGAL_ISSUER_AFTER_COMBINATION"} and review.get("canonical_company_id") is None:
        missing.append("SAME_COMPANY_CANONICAL_TARGET_REQUIRED")
    if validation.get("status") != "MATCH":
        missing.append("EXPECTED_CURRENT_STATE_CONFLICT")
    reasons = tuple(dict.fromkeys((*unresolved, *missing)))
    if str(review.get("review_status")).upper() == "REJECTED":
        return ReviewReadiness.REJECTED, reasons
    if str(review.get("review_status")).upper() == "APPROVED":
        return (ReviewReadiness.APPROVED_VALID if not reasons else ReviewReadiness.APPROVED_INVALID), reasons
    return (
        ReviewReadiness.PROPOSED_READY_FOR_OPERATOR_APPROVAL if not reasons else ReviewReadiness.PROPOSED_NOT_READY,
        reasons,
    )


def _mutation_plan(ticker: str, review: Mapping[str, Any], *, approved: bool) -> dict[str, Any]:
    company_id = review.get("canonical_company_id")
    security_id = review.get("canonical_security_id")
    same_security = str(review.get("security_continuity")) == "SAME_SECURITY"
    action = "UPDATE_CURRENT_TICKER" if same_security else (
        "CREATE_SECURITY" if company_id is not None else "CREATE_COMPANY_AND_SECURITY"
    )
    operations: list[dict[str, Any]] = []
    if action == "UPDATE_CURRENT_TICKER":
        operations.extend([
            {"operation": "REUSE_COMPANY", "company_id": company_id},
            {"operation": "REUSE_SECURITY", "security_id": security_id},
            {"operation": "CLOSE_TICKER_ALIAS", "ticker": review.get("predecessor_ticker"), "valid_to": review.get("effective_date")},
            {"operation": "ADD_CURRENT_TICKER_ALIAS", "ticker": ticker, "valid_from": review.get("effective_date")},
            {"operation": "UPDATE_SECURITY_CURRENT_TICKER", "security_id": security_id, "before": review.get("predecessor_ticker"), "after": ticker},
        ])
    elif action == "CREATE_SECURITY":
        operations.extend([
            {"operation": "REUSE_COMPANY", "company_id": company_id},
            {"operation": "PRESERVE_PREDECESSOR_SECURITY", "security_id": security_id, "ticker": review.get("predecessor_ticker")},
            {"operation": "CREATE_SECURITY", "company_id": company_id, "candidate_security_id": "ALLOCATE_ON_CANDIDATE"},
            {"operation": "ADD_CURRENT_TICKER_ALIAS", "ticker": ticker, "valid_from": review.get("effective_date")},
        ])
    else:
        operations.extend([
            {"operation": "CREATE_COMPANY", "candidate_company_id": "ALLOCATE_ON_CANDIDATE", "cik": normalize_cik(review.get("cik"))},
            {"operation": "CREATE_SECURITY", "candidate_security_id": "ALLOCATE_ON_CANDIDATE"},
            {"operation": "ADD_CURRENT_TICKER_ALIAS", "ticker": ticker, "valid_from": review.get("effective_date")},
        ])
    if review.get("provider_permaticker"):
        operations.append({"operation": "UPSERT_PROVIDER_SECURITY_IDENTITY", "provider": "SHARADAR", "provider_security_id": str(review["provider_permaticker"])})
    if review.get("cik"):
        operations.append({"operation": "POPULATE_COMPANY_CIK", "cik": normalize_cik(review.get("cik"))})
    return {
        "status": "AUTHORIZED" if approved else "PROPOSED_ONLY",
        "action": action,
        "company_id": company_id,
        "security_id": security_id if same_security else None,
        "predecessor_security_id": security_id if not same_security else None,
        "predecessor_ticker": review.get("predecessor_ticker"),
        "effective_date": review.get("effective_date"),
        "review_identity": {key: review.get(key) for key in ("cik", "provider_permaticker", "exchange")},
        "operations": operations,
    }


def _exchange_status(metadata: Mapping[str, Any], reviewed: Mapping[str, Any] | None) -> str:
    exchange = str(metadata.get("exchange") or "").upper()
    if exchange:
        return "EXCHANGE_CONFIRMED_SUPPORTED" if exchange in SUPPORTED_EXCHANGES else "EXCHANGE_CONFIRMED_UNSUPPORTED"
    if reviewed and str(reviewed.get("review_status")).upper() == "APPROVED" and reviewed.get("exchange"):
        return "EXCHANGE_FROM_APPROVED_REVIEW" if str(reviewed["exchange"]).upper() in SUPPORTED_EXCHANGES else "EXCHANGE_CONFIRMED_UNSUPPORTED"
    return "EXCHANGE_UNKNOWN"


def resolve_ticker_identity(
    paths: Any,
    ticker: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> IdentityResolution:
    ticker = ticker.strip().upper()
    registry = load_review_registry(registry_path)
    review_record = registry.get(ticker)
    reviewed = review_record
    if review_record and str(review_record.get("review_status")).upper() == "APPROVED":
        approved_resolution = review_record.get("approved_resolution")
        if isinstance(approved_resolution, Mapping):
            reviewed = dict(approved_resolution)
            reviewed.setdefault("subject_ticker", ticker)
            reviewed.setdefault("evidence", review_record.get("evidence", []))
            reviewed.setdefault("unresolved_assumptions", [])
            reviewed["review_status"] = "APPROVED"
    provider = _provider_metadata(Path(paths.provider_db), ticker)
    metadata = dict(provider.get("identity") or {})
    evidence_identity = dict(metadata)
    if reviewed:
        evidence_identity.setdefault("cik", reviewed.get("cik"))
        evidence_identity.setdefault("permaticker", reviewed.get("provider_permaticker"))
    canonical = _canonical_evidence(Path(paths.canonical_db), ticker, evidence_identity)
    current = canonical["current_ticker_matches"]
    aliases = canonical["alias_matches"]
    provider_matches = canonical["provider_security_matches"]
    company_matches = canonical["company_cik_matches"]
    exchange_status = _exchange_status(metadata, reviewed)
    review_validation = (
        _review_current_state(paths, ticker, reviewed, provider, canonical)
        if reviewed else {"status": "NOT_APPLICABLE", "expected": {}, "actual": {}, "mismatches": []}
    )
    readiness, readiness_reasons = (
        _review_readiness(reviewed, review_validation)
        if reviewed else (ReviewReadiness.NOT_REVIEWED, ())
    )
    review_fingerprint = approval_fingerprint(reviewed) if reviewed else None
    proposed_plan = (
        _mutation_plan(ticker, reviewed, approved=False)
        if reviewed and readiness in {ReviewReadiness.PROPOSED_READY_FOR_OPERATOR_APPROVAL, ReviewReadiness.APPROVED_VALID}
        else {}
    )

    def result(
        resolution_class: ResolutionClass,
        company: str,
        security: str,
        ticker_relation: str,
        provider_continuity: str,
        authority: AuthorityClass,
        permitted: bool,
        reasons: Sequence[str],
        explanation: str,
        mutation: Mapping[str, Any] | None = None,
    ) -> IdentityResolution:
        return IdentityResolution(
            requested_ticker=ticker,
            resolution_class=resolution_class.value,
            company_continuity=company,
            security_continuity=security,
            ticker_relationship=ticker_relation,
            provider_continuity=provider_continuity,
            authority_class=authority.value,
            automatic_mutation_permitted=permitted,
            exchange_status=exchange_status,
            reason_codes=tuple(reasons),
            explanation=explanation,
            provider_metadata=provider,
            canonical_evidence=canonical,
            reviewed_resolution=dict(review_record) if review_record else None,
            review_status=str(reviewed.get("review_status")) if reviewed else None,
            readiness_state=readiness.value,
            approval_fingerprint=review_fingerprint,
            current_state_validation=review_validation,
            unresolved_assumptions=readiness_reasons,
            proposed_mutation=proposed_plan,
            mutation=dict(mutation or {}),
        )

    if reviewed and str(reviewed.get("review_status")).upper() == "APPROVED":
        stored_fingerprint = str(review_record.get("approval_fingerprint") or "") if review_record else ""
        if stored_fingerprint != review_fingerprint:
            return result(
                ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNKNOWN",
                "REVIEW_EVIDENCE_MISMATCH", AuthorityClass.INSUFFICIENT, False,
                ("APPROVED_REVIEW_EVIDENCE_MISMATCH",),
                "The approved material facts no longer reproduce the stored approval fingerprint; mutation is blocked.",
            )
        if review_validation["status"] != "MATCH":
            mismatch_fields = {str(item.get("field") or "") for item in review_validation.get("mismatches", [])}
            provider_now_available = provider.get("status") == "FOUND" and mismatch_fields == {"provider_status"}
            if provider_now_available:
                # A newly available, non-conflicting provider identity is re-resolved below
                # through the stronger local deterministic path instead of replaying review authority.
                readiness = ReviewReadiness.APPROVED_SUPERSEDED_BY_LOCAL_DETERMINISTIC
            else:
                conflict_code = (
                    "APPROVED_REVIEW_PROVIDER_CONFLICT"
                    if any(field.startswith("provider_") or field.startswith("permaticker_") for field in mismatch_fields)
                    else "APPROVED_REVIEW_CANONICAL_CONFLICT"
                )
                return result(
                    ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNKNOWN",
                    "CURRENT_STATE_CONFLICT", AuthorityClass.INSUFFICIENT, False,
                    ("APPROVED_REVIEW_STALE", conflict_code),
                    "Current canonical/provider state no longer matches the state bound to the approval; mutation is blocked.",
                )

    if reviewed and str(reviewed.get("review_status")).upper() == "APPROVED" and provider["status"] == "FOUND":
        reviewed_cik = normalize_cik(reviewed.get("cik"))
        provider_cik = normalize_cik(metadata.get("cik"))
        reviewed_permaticker = str(reviewed.get("provider_permaticker") or "")
        provider_permaticker = str(metadata.get("permaticker") or "")
        if (reviewed_cik and provider_cik and reviewed_cik != provider_cik) or (
            reviewed_permaticker and provider_permaticker and reviewed_permaticker != provider_permaticker
        ):
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_PROVIDER_CONFLICT",), "Current provider identity conflicts with the approved reviewed resolution; mutation is blocked.")

    if provider["status"] == "AMBIGUOUS" or len(provider_matches) > 1 or len(company_matches) > 1:
        return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "UNKNOWN", "UNKNOWN", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("MULTIPLE_PROVIDER_IDENTITIES",), "Multiple provider or canonical identities prevent deterministic resolution.")

    if current:
        direct = current[0]
        conflicts = (
            (provider_matches and int(provider_matches[0]["security_id"]) != int(direct["security_id"]))
            or (company_matches and int(company_matches[0]["company_id"]) != int(direct["company_id"]))
        )
        if conflicts:
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNCHANGED", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("CURRENT_TICKER_PROVIDER_CONFLICT",), "Ticker text matches canonical state, but stronger provider/company evidence points elsewhere.")
        return result(ResolutionClass.EXISTING_SECURITY, "SAME_COMPANY", "SAME_SECURITY", "UNCHANGED", "SAME_PROVIDER_IDENTITY" if provider_matches else "NOT_REQUIRED", AuthorityClass.LOCAL_DETERMINISTIC, False, ("CURRENT_TICKER_MATCH",), "The requested ticker is already the canonical current ticker.", {"company_id": direct["company_id"], "security_id": direct["security_id"], "action": "NONE"})

    if provider["status"] == "FOUND" and len(provider_matches) == 1:
        match = provider_matches[0]
        if any(int(alias["security_id"]) != int(match["security_id"]) for alias in aliases):
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "REUSED_TICKER", "SAME_PERMATICKER", AuthorityClass.INSUFFICIENT, False, ("TICKER_REUSE_PROVIDER_CONFLICT",), "The provider identity maps to one security, but the requested ticker is a historical alias of another security.")
        if company_matches and int(company_matches[0]["company_id"]) != int(match["company_id"]):
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "UNKNOWN", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("PERMATICKER_CIK_CONFLICT",), "Sharadar permaticker and CIK resolve to different canonical companies.")
        return result(ResolutionClass.TICKER_TRANSITION_SAME_SECURITY, "SAME_COMPANY", "SAME_SECURITY", "RENAMED", "SAME_PERMATICKER", AuthorityClass.LOCAL_DETERMINISTIC, exchange_status == "EXCHANGE_CONFIRMED_SUPPORTED", ("PERMATICKER_MATCH",), "The Sharadar securities-master permaticker maps the new ticker to one existing canonical security.", {"company_id": match["company_id"], "security_id": match["security_id"], "predecessor_ticker": match["current_ticker"], "effective_date": metadata.get("firstpricedate"), "action": "UPDATE_CURRENT_TICKER"})

    if provider["status"] == "FOUND":
        if aliases:
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "UNKNOWN", "UNKNOWN", "REUSED_OR_HISTORICAL_ALIAS", "NEW_OR_UNKNOWN_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("TICKER_REUSE_RISK",), "Ticker text exists as a historical alias but provider identity does not prove that it is the same security.")
        if len(company_matches) == 1:
            company_id = company_matches[0]["company_id"]
            return result(ResolutionClass.NEW_SECURITY, "SAME_COMPANY", "NEW_SECURITY", "NEW_TICKER", "NEW_PERMATICKER", AuthorityClass.LOCAL_DETERMINISTIC, exchange_status == "EXCHANGE_CONFIRMED_SUPPORTED", ("CIK_COMPANY_MATCH_ONLY",), "CIK proves company continuity only; a distinct security will be created.", {"company_id": company_id, "security_id": None, "action": "CREATE_SECURITY"})
        return result(ResolutionClass.NEW_SECURITY, "NEW_COMPANY", "NEW_SECURITY", "NEW_TICKER", "NEW_PROVIDER_IDENTITY", AuthorityClass.LOCAL_DETERMINISTIC, exchange_status == "EXCHANGE_CONFIRMED_SUPPORTED", ("NO_CANONICAL_IDENTITY_MATCH",), "Provider metadata identifies a new company/security with no canonical identity collision.", {"company_id": None, "security_id": None, "action": "CREATE_COMPANY_AND_SECURITY"})

    if reviewed and str(reviewed.get("review_status")).upper() == "APPROVED":
        referenced_company = reviewed.get("canonical_company_id")
        referenced_security = reviewed.get("canonical_security_id")
        same_security = str(reviewed.get("security_continuity")) == "SAME_SECURITY"
        if same_security and (referenced_company is None or referenced_security is None):
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "UNKNOWN", "UNKNOWN", "UNKNOWN", "PROVIDER_METADATA_ABSENT", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_MISSING_CANONICAL_TARGET",), "A same-security approved review must name the canonical company and security it intends to preserve.")
        if referenced_company is not None:
            with _readonly(Path(paths.canonical_db)) as conn:
                company_exists = conn.execute("SELECT 1 FROM company WHERE company_id=?", (referenced_company,)).fetchone()
            if company_exists is None:
                return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "UNKNOWN", "UNKNOWN", "PROVIDER_METADATA_ABSENT", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_CANONICAL_REFERENCE_INVALID",), "The approved review references a canonical company that no longer exists.")
        if referenced_security is not None:
            matches = [row for row in canonical["alias_matches"] + canonical["current_ticker_matches"] if int(row["security_id"]) == int(referenced_security)]
            if not matches:
                with _readonly(Path(paths.canonical_db)) as conn:
                    row = conn.execute("SELECT company_id,current_ticker FROM security WHERE security_id=?", (referenced_security,)).fetchone()
                if row is None or (referenced_company is not None and int(row["company_id"]) != int(referenced_company)):
                    return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNKNOWN", "PROVIDER_METADATA_ABSENT", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_CANONICAL_REFERENCE_INVALID",), "The approved review no longer matches canonical identity state.")
        if provider_matches and referenced_security is not None and int(provider_matches[0]["security_id"]) != int(referenced_security):
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_PROVIDER_CONFLICT",), "The reviewed permaticker maps to a different canonical security.")
        if provider_matches and referenced_security is None:
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "CONFLICTING", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_PROVIDER_CONFLICT",), "The reviewed permaticker is already bound to a canonical security, but the review proposes a new security.")
        if company_matches and referenced_company is not None and int(company_matches[0]["company_id"]) != int(referenced_company):
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "UNKNOWN", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_PROVIDER_CONFLICT",), "The reviewed CIK maps to a different canonical company.")
        if company_matches and referenced_company is None:
            return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "CONFLICTING", "UNKNOWN", "UNKNOWN", "CONFLICTING_PROVIDER_IDENTITY", AuthorityClass.INSUFFICIENT, False, ("APPROVED_REVIEW_PROVIDER_CONFLICT",), "The reviewed CIK is already bound to a canonical company, but the review proposes a new company.")
        mutation = _mutation_plan(ticker, reviewed, approved=True)
        return result(ResolutionClass(str(reviewed["resolution_class"])), str(reviewed["company_continuity"]), str(reviewed["security_continuity"]), str(reviewed["ticker_relationship"]), str(reviewed["provider_continuity"]), AuthorityClass.APPROVED_REVIEW, exchange_status == "EXCHANGE_FROM_APPROVED_REVIEW", ("APPROVED_REVIEW_VALID",), str(reviewed["reason"]), mutation)

    if reviewed and str(reviewed.get("review_status")).upper() == "PROPOSED":
        reasons = ["PROPOSED_REVIEW_NOT_AUTHORITY", "PROVIDER_METADATA_MISSING"]
        if readiness == ReviewReadiness.PROPOSED_NOT_READY:
            reasons.append("PROPOSED_REVIEW_NOT_READY")
        return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, str(reviewed["company_continuity"]), str(reviewed["security_continuity"]), str(reviewed["ticker_relationship"]), str(reviewed["provider_continuity"]), AuthorityClass.PROPOSED_REVIEW, False, reasons, "A researched proposal exists, but readiness is separate from explicit operator approval and cannot authorize mutation.")

    if reviewed and str(reviewed.get("review_status")).upper() == "REJECTED":
        return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, str(reviewed["company_continuity"]), str(reviewed["security_continuity"]), str(reviewed["ticker_relationship"]), str(reviewed["provider_continuity"]), AuthorityClass.INSUFFICIENT, False, ("REJECTED_REVIEW_NOT_AUTHORITY",), "The reviewed interpretation was rejected and cannot authorize mutation.")

    return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "UNKNOWN", "UNKNOWN", "UNKNOWN", "PROVIDER_METADATA_ABSENT", AuthorityClass.INSUFFICIENT, False, ("PROVIDER_METADATA_MISSING", "NO_APPROVED_REVIEW"), "Provider metadata is absent and no approved reviewed resolution exists.")


def render_preview_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Ticker Identity Resolution Preview",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Contract: `{CONTRACT_VERSION}`",
        "- Database writes: `NO`",
        "- Review registry authority: only a current-state-compatible `APPROVED_VALID` record may authorize mutation.",
        "- `PROPOSED_READY_FOR_OPERATOR_APPROVAL` is not mutation authority.",
        "",
        "## Results",
        "",
    ]
    for item in payload["resolutions"]:
        provider = item["provider_metadata"]
        canonical = item["canonical_evidence"]
        review_record = item.get("reviewed_resolution") or {}
        reviewed = (
            review_record.get("approved_resolution")
            if str(review_record.get("review_status")).upper() == "APPROVED"
            and isinstance(review_record.get("approved_resolution"), Mapping)
            else review_record
        )
        lines.extend([
            f"### {item['requested_ticker']}",
            "",
            f"- Resolution: `{item['resolution_class']}`",
            f"- Review status: `{item['review_status'] or 'NONE'}`",
            f"- Approval readiness: `{item['readiness_state']}`",
            f"- Authority: `{item['authority_class']}`",
            f"- Automatic mutation permitted: `{'YES' if item['automatic_mutation_permitted'] else 'NO'}`",
            f"- Company continuity: `{item['company_continuity']}`",
            f"- Security continuity: `{item['security_continuity']}`",
            f"- Ticker relationship: `{item['ticker_relationship']}`",
            f"- Provider continuity: `{item['provider_continuity']}`",
            f"- Expected canonical company_id: `{reviewed.get('canonical_company_id', 'NONE') if reviewed else 'NONE'}`",
            f"- Expected canonical security_id: `{reviewed.get('canonical_security_id', 'NONE')}`",
            f"- Expected predecessor ticker: `{reviewed.get('predecessor_ticker') or 'NONE'}`",
            f"- Expected CIK: `{normalize_cik(reviewed.get('cik')) or 'NONE'}`",
            f"- Expected provider permaticker: `{reviewed.get('provider_permaticker') or 'NONE'}`",
            f"- Provider metadata: `{provider.get('status')}` ({provider.get('candidate_rows', 0)} candidate rows)",
            f"- Exchange: `{item['exchange_status']}`",
            f"- Canonical current matches: `{len(canonical['current_ticker_matches'])}`; aliases: `{len(canonical['alias_matches'])}`; permaticker matches: `{len(canonical['provider_security_matches'])}`; CIK company matches: `{len(canonical['company_cik_matches'])}`",
            f"- Reason codes: `{', '.join(item['reason_codes'])}`",
            f"- Approval fingerprint: `{item['approval_fingerprint'] or 'NOT_APPLICABLE'}`",
            f"- Current-state validation: `{item['current_state_validation']['status']}`",
            f"- Explanation: {item['explanation']}",
        ])
        if item["unresolved_assumptions"]:
            lines.append("- Unresolved assumptions: " + " | ".join(item["unresolved_assumptions"]))
        evidence = reviewed.get("evidence") or []
        lines.append("- Authoritative evidence:")
        lines.extend(
            f"  - {entry.get('source_authority', 'UNKNOWN')}: {entry.get('reference', 'NO_REFERENCE')} - {entry.get('fact', '')}"
            for entry in evidence
        )
        plan = item.get("proposed_mutation") or item.get("mutation") or {}
        lines.append(f"- Proposed canonical action: `{plan.get('action', 'NONE')}`")
        for operation in plan.get("operations", []):
            lines.append(f"  - `{operation.get('operation')}`: `{json.dumps(operation, sort_keys=True)}`")
        mismatches = item["current_state_validation"].get("mismatches") or []
        for mismatch in mismatches:
            lines.append(
                f"- State conflict `{mismatch['field']}`: expected `{mismatch['expected']}`, actual `{mismatch['actual']}`"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_preview(
    raw_inputs: str | Sequence[str],
    *,
    source_paths: Any,
    run_root: Path = ADMIN_RUN_ROOT,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    request = build_batch_request(AdminOperationType.RESOLVE_TICKER_IDENTITY, raw_inputs, market="usa", options={"contract_version": CONTRACT_VERSION})
    if len(request.normalized_inputs) > 25:
        raise ValueError("IDENTITY_PREVIEW_MAXIMUM_25_TICKERS")
    request_fp = fingerprint(request)
    run_id = stable_run_id(AdminOperationType.RESOLVE_TICKER_IDENTITY, request_fp)
    writer = AdminRunWriter(run_id, AdminOperationType.RESOLVE_TICKER_IDENTITY, root=run_root)
    started = utc_now()
    if progress_callback:
        progress_callback({"current_stage_number": 1, "total_declared_stages": 2, "current_stage_id": "PREFLIGHT", "stage_state": "RUNNING", "message": "Recording identity Preview request."})
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Identity Preview request recorded.")
    writer.write_json("request.json", request.as_dict())
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Resolving local and reviewed identity evidence.")
    if progress_callback:
        progress_callback({"current_stage_number": 2, "total_declared_stages": 2, "current_stage_id": "SOURCE_RESOLUTION", "stage_state": "RUNNING", "message": "Resolving local and reviewed identity evidence."})
    resolutions = [resolve_ticker_identity(source_paths, ticker, registry_path=registry_path).as_dict() for ticker in request.normalized_inputs]
    payload = {
        "run_id": run_id,
        "operation_type": AdminOperationType.RESOLVE_TICKER_IDENTITY.value,
        "mode": "PREVIEW",
        "outcome": "COMPLETED",
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "request": request.as_dict(),
        "resolutions": resolutions,
        "summary_counts": {
            "requested": len(request.normalized_inputs),
            "automatic": sum(bool(item["automatic_mutation_permitted"]) for item in resolutions),
            "review_required": sum(item["resolution_class"] == ResolutionClass.IDENTITY_REVIEW_REQUIRED.value for item in resolutions),
            "proposed_not_ready": sum(item["readiness_state"] == ReviewReadiness.PROPOSED_NOT_READY.value for item in resolutions),
            "ready_for_operator_approval": sum(item["readiness_state"] == ReviewReadiness.PROPOSED_READY_FOR_OPERATOR_APPROVAL.value for item in resolutions),
            "approved_valid": sum(item["readiness_state"] == ReviewReadiness.APPROVED_VALID.value for item in resolutions),
        },
        "recommended_next_action": "Approve none, some, or all PROPOSED_READY_FOR_OPERATOR_APPROVAL records by a version-controlled registry change; never approve PROPOSED_NOT_READY records.",
    }
    payload["preview_fingerprint"] = fingerprint(payload)
    writer.write_json("identity_preview.json", payload)
    writer.write_json("result.json", payload)
    writer.write_text("operation_report.md", render_preview_report(payload))
    writer.checkpoint(RunStage.PREVIEW_READY, message="Identity Preview completed.", preview_fingerprint=payload["preview_fingerprint"])
    writer.checkpoint(RunStage.COMPLETED, message="Read-only identity resolution completed.", preview_fingerprint=payload["preview_fingerprint"])
    writer.write_manifest()
    if progress_callback:
        progress_callback({"current_stage_number": 2, "total_declared_stages": 2, "current_stage_id": "SOURCE_RESOLUTION", "stage_state": "COMPLETED", "message": "Identity Preview completed."})
    return payload | {"artifact_dir": str(writer.run_dir), "identity_preview_path": str(writer.run_dir / "identity_preview.json")}
