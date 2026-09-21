from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.contracts import AdminOperationType, RunStage, build_batch_request, fingerprint, utc_now
from rawcandle.fundamentals.admin.provider_cik import extract_sharadar_cik, normalize_cik


CONTRACT_VERSION = "PHASE13G3_18_TICKER_IDENTITY_RESOLUTION_V1"
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


def load_review_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("records"), list):
        raise ValueError("IDENTITY_REVIEW_REGISTRY_SCHEMA_INVALID")
    records: dict[str, Mapping[str, Any]] = {}
    required = {
        "subject_ticker", "resolution_class", "company_continuity", "security_continuity",
        "ticker_relationship", "provider_continuity", "review_status", "reason", "evidence",
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
    reviewed = registry.get(ticker)
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
            reviewed_resolution=dict(reviewed) if reviewed else None,
            mutation=dict(mutation or {}),
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
        mutation = {
            "company_id": referenced_company,
            "security_id": referenced_security,
            "predecessor_ticker": reviewed.get("predecessor_ticker"),
            "effective_date": reviewed.get("effective_date"),
            "action": "UPDATE_CURRENT_TICKER" if same_security else ("CREATE_SECURITY" if referenced_company is not None else "CREATE_COMPANY_AND_SECURITY"),
            "review_identity": {key: reviewed.get(key) for key in ("cik", "provider_permaticker", "exchange")},
        }
        return result(ResolutionClass(str(reviewed["resolution_class"])), str(reviewed["company_continuity"]), str(reviewed["security_continuity"]), str(reviewed["ticker_relationship"]), str(reviewed["provider_continuity"]), AuthorityClass.APPROVED_REVIEW, exchange_status == "EXCHANGE_FROM_APPROVED_REVIEW", ("APPROVED_REVIEW_RESOLUTION",), str(reviewed["reason"]), mutation)

    if reviewed and str(reviewed.get("review_status")).upper() == "PROPOSED":
        return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, str(reviewed["company_continuity"]), str(reviewed["security_continuity"]), str(reviewed["ticker_relationship"]), str(reviewed["provider_continuity"]), AuthorityClass.PROPOSED_REVIEW, False, ("PROPOSED_REVIEW_NOT_AUTHORITY", "PROVIDER_METADATA_MISSING"), "A researched proposal exists, but only an operator-approved record may authorize mutation.")

    return result(ResolutionClass.IDENTITY_REVIEW_REQUIRED, "UNKNOWN", "UNKNOWN", "UNKNOWN", "PROVIDER_METADATA_ABSENT", AuthorityClass.INSUFFICIENT, False, ("PROVIDER_METADATA_MISSING", "NO_APPROVED_REVIEW"), "Provider metadata is absent and no approved reviewed resolution exists.")


def render_preview_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Ticker Identity Resolution Preview",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Contract: `{CONTRACT_VERSION}`",
        "- Database writes: `NO`",
        "- Review registry authority: only `APPROVED` records may authorize mutation.",
        "",
        "## Results",
        "",
    ]
    for item in payload["resolutions"]:
        provider = item["provider_metadata"]
        canonical = item["canonical_evidence"]
        lines.extend([
            f"### {item['requested_ticker']}",
            "",
            f"- Resolution: `{item['resolution_class']}`",
            f"- Authority: `{item['authority_class']}`",
            f"- Automatic mutation permitted: `{'YES' if item['automatic_mutation_permitted'] else 'NO'}`",
            f"- Company continuity: `{item['company_continuity']}`",
            f"- Security continuity: `{item['security_continuity']}`",
            f"- Ticker relationship: `{item['ticker_relationship']}`",
            f"- Provider continuity: `{item['provider_continuity']}`",
            f"- Provider metadata: `{provider.get('status')}` ({provider.get('candidate_rows', 0)} candidate rows)",
            f"- Exchange: `{item['exchange_status']}`",
            f"- Canonical current matches: `{len(canonical['current_ticker_matches'])}`; aliases: `{len(canonical['alias_matches'])}`; permaticker matches: `{len(canonical['provider_security_matches'])}`; CIK company matches: `{len(canonical['company_cik_matches'])}`",
            f"- Reason codes: `{', '.join(item['reason_codes'])}`",
            f"- Explanation: {item['explanation']}",
            "",
        ])
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
        },
        "recommended_next_action": "Review proposed records; change review_status to APPROVED only after an explicit operator decision.",
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
