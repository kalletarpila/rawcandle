from __future__ import annotations

import fcntl
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    ROOT,
    database_inventory,
    stable_hash,
    write_csv,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    candidate_relative_valuation_dependency_state,
    current_universe_rows,
    database_fingerprint,
    online_backup,
    run_candidate_apply,
    stable_json,
    taxonomy_identity,
    universe_identity,
)


PHASE = "PHASE13D_TICKER_ONBOARDING_TAXONOMY_BACKEND_CLI"
OUTCOME_LIMITED = "OUTCOME B — BACKEND READY WITH EXPLICIT SOURCE OR IDENTITY LIMITATIONS"
CONTRACT_VERSION = "PHASE13D_PREVIEW_APPLY_CONTRACT_V1"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13d_backend"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"
PROTECTED_PATHS = {path.resolve() for path in PRODUCTION.values()}
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,15}$")
SUPPORTED_ONBOARDING_CATEGORIES = {
    "Domestic Common Stock",
    "Domestic Common Stock Primary Class",
}
SUPPORTED_ONBOARDING_EXCHANGES = {"NASDAQ", "NYSE", "NYSEMKT"}
MIN_CURRENT_MARKET_DATE = "2026-08-01"


@dataclass(frozen=True)
class Phase13DPaths:
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    market_db: Path
    taxonomy_db: Path

    def as_candidate(self) -> CandidatePaths:
        return CandidatePaths(
            canonical_db=self.canonical_db,
            analysis_db=self.analysis_db,
            taxonomy_db=self.taxonomy_db,
            provider_db=self.provider_db,
            market_db=self.market_db,
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def reject_production_or_alias(paths: Phase13DPaths) -> None:
    seen: dict[Path, str] = {}
    for role, path in paths.__dict__.items():
        if str(path).startswith("file:") or "mode=" in str(path):
            raise PermissionError(f"PHASE13D_SQLITE_URI_REFUSED:{role}")
        resolved = path.resolve()
        if path.is_symlink() or resolved in PROTECTED_PATHS:
            raise PermissionError(f"PHASE13D_PRODUCTION_PATH_REFUSED:{role}:{resolved}")
        if resolved in seen:
            raise PermissionError(f"PHASE13D_DATABASE_ALIAS_REFUSED:{role}:{seen[resolved]}")
        seen[resolved] = role


def parse_ticker_tokens(raw: str | Sequence[str]) -> dict[str, Any]:
    text = raw if isinstance(raw, str) else " ".join(raw)
    tokens = [token.strip().upper() for token in re.split(r"[\s,]+", text or "") if token.strip()]
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for token in tokens:
        if not TICKER_RE.match(token):
            rejected.append({"ticker": token, "reason": "MALFORMED_SYMBOL"})
            continue
        if token in seen:
            continue
        seen.add(token)
        accepted.append(token)
    if not accepted and not rejected:
        raise ValueError("PHASE13D_TICKER_INPUT_EMPTY")
    if len(accepted) > 25:
        raise ValueError("PHASE13D_TOO_MANY_TICKERS")
    return {"requested": tokens, "accepted": accepted, "rejected": rejected}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(str(row[1]) == column for row in conn.execute(f'PRAGMA table_info("{table}")'))


def _source_state(paths: Phase13DPaths) -> dict[str, Any]:
    members, aliases = current_universe_rows(paths.canonical_db, now="PHASE13D_PREVIEW")
    universe = universe_identity(members, aliases, as_of_date="PHASE13D")
    with _readonly(paths.analysis_db) as conn:
        active_package = (
            conn.execute(
                "SELECT persistence_fingerprint FROM fundamentals_active_model_family WHERE singleton=1"
            ).fetchone()
            if _table_exists(conn, "fundamentals_active_model_family")
            else None
        )
        active_rv = (
            conn.execute(
                "SELECT snapshot_id FROM relative_valuation_active_snapshot ORDER BY model_fingerprint LIMIT 1"
            ).fetchone()
            if _table_exists(conn, "relative_valuation_active_snapshot")
            else None
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "databases": {
            role: database_fingerprint(path)
            for role, path in (
                ("provider", paths.provider_db),
                ("canonical", paths.canonical_db),
                ("analysis", paths.analysis_db),
                ("market", paths.market_db),
                ("taxonomy", paths.taxonomy_db),
            )
        },
        "active_universe": universe,
        "taxonomy": taxonomy_identity(paths.taxonomy_db),
        "active_package": str(active_package[0]) if active_package else None,
        "active_relative_valuation_snapshot": str(active_rv[0]) if active_rv else None,
    }


def _canonical_lookup(paths: Phase13DPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.canonical_db) as conn:
        direct = conn.execute(
            "SELECT c.company_id,s.security_id,s.current_ticker,s.exchange,s.active "
            "FROM security s JOIN company c USING(company_id) "
            "WHERE UPPER(s.current_ticker)=UPPER(?) ORDER BY s.active DESC,s.security_id",
            (ticker,),
        ).fetchall() if _table_exists(conn, "security") else []
        alias = conn.execute(
            "SELECT c.company_id,s.security_id,a.ticker,s.current_ticker,s.exchange,s.active "
            "FROM ticker_alias a JOIN security s USING(security_id) JOIN company c USING(company_id) "
            "WHERE UPPER(a.ticker)=UPPER(?) ORDER BY s.active DESC,s.security_id",
            (ticker,),
        ).fetchall() if _table_exists(conn, "ticker_alias") else []
    rows = [dict(row) for row in direct] + [dict(row) for row in alias]
    company_ids = {row["company_id"] for row in rows}
    return {
        "rows": rows,
        "exists": bool(rows),
        "ambiguous": len(company_ids) > 1,
        "company_id": rows[0]["company_id"] if len(company_ids) == 1 else None,
        "security_id": rows[0]["security_id"] if len(company_ids) == 1 and rows else None,
    }


def _market_lookup(paths: Phase13DPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.market_db) as conn:
        if not _table_exists(conn, "osakedata"):
            return {"status": "MARKET_DATA_NOT_FOUND", "markets": [], "latest_date": None, "row_count": 0}
        rows = conn.execute(
            "SELECT market,MAX(pvm) AS latest_date,COUNT(*) AS row_count "
            "FROM osakedata WHERE UPPER(osake)=UPPER(?) GROUP BY market ORDER BY market",
            (ticker,),
        ).fetchall()
    items = [dict(row) for row in rows]
    if not items:
        return {"status": "MARKET_DATA_NOT_FOUND", "markets": [], "latest_date": None, "row_count": 0}
    if len(items) > 1:
        return {"status": "MARKET_AMBIGUOUS", "markets": [row["market"] for row in items], "latest_date": max(row["latest_date"] for row in items), "row_count": sum(int(row["row_count"]) for row in items)}
    return {"status": "FOUND", "markets": [items[0]["market"]], "latest_date": items[0]["latest_date"], "row_count": int(items[0]["row_count"])}


def _provider_lookup(paths: Phase13DPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.provider_db) as conn:
        if _table_exists(conn, "sharadar_ticker_metadata"):
            columns = {str(row[1]) for row in conn.execute('PRAGMA table_info("sharadar_ticker_metadata")')}
            ticker_col = "ticker" if "ticker" in columns else None
            if ticker_col:
                row = conn.execute(
                    f'SELECT * FROM sharadar_ticker_metadata WHERE UPPER("{ticker_col}")=UPPER(?) LIMIT 2',
                    (ticker,),
                ).fetchall()
                if len(row) == 1:
                    data = dict(row[0])
                    return {
                        "status": "FOUND",
                        "source": "sharadar_ticker_metadata",
                        "identity": {
                            key: data.get(key)
                            for key in (
                                "ticker", "permaticker", "cik", "name", "exchange",
                                "isdelisted", "category", "sector", "industry",
                                "firstpricedate", "lastpricedate",
                            )
                            if key in data
                        },
                    }
                if len(row) > 1:
                    return {"status": "IDENTITY_AMBIGUOUS", "source": "sharadar_ticker_metadata", "identity": {}}
        if _table_exists(conn, "provider_company_identity"):
            rows = conn.execute(
                "SELECT * FROM provider_company_identity WHERE UPPER(ticker)=UPPER(?) LIMIT 2",
                (ticker,),
            ).fetchall()
            if len(rows) == 1:
                return {"status": "FOUND", "source": "provider_company_identity", "identity": dict(rows[0])}
            if len(rows) > 1:
                return {"status": "IDENTITY_AMBIGUOUS", "source": "provider_company_identity", "identity": {}}
    return {"status": "API_FETCH_REQUIRED", "source": None, "identity": {}}


def _preview_eligibility_reasons(
    *,
    canonical: Mapping[str, Any],
    market: Mapping[str, Any],
    provider: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    identity = provider.get("identity") if isinstance(provider.get("identity"), Mapping) else {}
    if provider.get("status") == "IDENTITY_AMBIGUOUS" or canonical.get("ambiguous"):
        reasons.append("IDENTITY_AMBIGUOUS")
    elif provider.get("status") == "API_FETCH_REQUIRED":
        reasons.append("PROVIDER_IDENTITY_MISSING")
    if str(identity.get("isdelisted") or "").upper() == "Y":
        reasons.append("DELISTED_SECURITY")
    category = identity.get("category")
    if category in {"ETF", "FUND", "ADR_UNSUPPORTED"} or (
        category is not None and category not in SUPPORTED_ONBOARDING_CATEGORIES
    ):
        reasons.append("UNSUPPORTED_SECURITY_TYPE")
    exchange = str(identity.get("exchange") or "").upper()
    if exchange and exchange not in SUPPORTED_ONBOARDING_EXCHANGES:
        reasons.append("INCOMPATIBLE_EXCHANGE")
    if market.get("status") == "MARKET_DATA_NOT_FOUND":
        reasons.append("MARKET_DATA_NOT_FOUND")
    elif market.get("status") == "MARKET_AMBIGUOUS":
        reasons.append("MARKET_AMBIGUOUS")
    elif market.get("status") == "FOUND":
        markets = [str(item).lower() for item in market.get("markets", [])]
        if markets != ["usa"]:
            reasons.append("MARKET_INCOMPATIBLE")
        if str(market.get("latest_date") or "") < MIN_CURRENT_MARKET_DATE:
            reasons.append("MARKET_OHLC_STALE")
    if canonical.get("ambiguous"):
        reasons.append("TICKER_REUSE_COLLISION")
    return list(dict.fromkeys(reasons))


def _taxonomy_lookup(paths: Phase13DPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.taxonomy_db) as conn:
        if not _table_exists(conn, "ec_entity"):
            return {"status": "SOURCE_NOT_READY", "memberships": []}
        rows = conn.execute(
            "SELECT e.entity_type,e.entity_code,e.entity_name,e.ticker,m.membership_type,m.membership_role,m.is_primary,m.role_weight,m.status "
            "FROM ec_entity e LEFT JOIN ec_membership m ON m.child_entity_id=e.entity_id "
            "WHERE UPPER(e.ticker)=UPPER(?) AND e.status='ACTIVE' ORDER BY e.entity_id,m.membership_id",
            (ticker,),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {"status": "FOUND" if items else "TAXONOMY_LIMITED_OR_NO_MEMBERSHIP", "memberships": items}


def build_ticker_preview(paths: Phase13DPaths, raw_tickers: str | Sequence[str], *, now: str | None = None) -> dict[str, Any]:
    reject_production_or_alias(paths)
    created = now or utc_now()
    parsed = parse_ticker_tokens(raw_tickers)
    source = _source_state(paths)
    per_ticker = []
    accepted: list[str] = []
    for ticker in parsed["accepted"]:
        canonical = _canonical_lookup(paths, ticker)
        market = _market_lookup(paths, ticker)
        provider = _provider_lookup(paths, ticker)
        taxonomy = _taxonomy_lookup(paths, ticker)
        rejection_reasons = _preview_eligibility_reasons(canonical=canonical, market=market, provider=provider)
        if canonical["ambiguous"] or provider["status"] == "IDENTITY_AMBIGUOUS":
            status = "IDENTITY_AMBIGUOUS"
        elif canonical["exists"]:
            status = "ALREADY_PRESENT"
        elif "DELISTED_SECURITY" in rejection_reasons:
            status = "NOT_ELIGIBLE"
        elif market["status"] in {"MARKET_DATA_NOT_FOUND", "MARKET_AMBIGUOUS"}:
            status = market["status"]
        elif provider["status"] == "API_FETCH_REQUIRED":
            status = "API_FETCH_REQUIRED"
        elif provider["identity"].get("category") in {"ETF", "FUND", "ADR_UNSUPPORTED"}:
            status = "UNSUPPORTED_SECURITY_TYPE"
        elif rejection_reasons:
            status = "NOT_ELIGIBLE"
        elif taxonomy["status"] == "TAXONOMY_LIMITED_OR_NO_MEMBERSHIP":
            status = "READY_WITH_LIMITATIONS"
        else:
            status = "READY_LOCAL_PROVIDER"
        ready = status in {"READY_LOCAL_PROVIDER", "READY_LOCAL_ARCHIVE", "READY_WITH_LIMITATIONS"}
        if ready:
            accepted.append(ticker)
        per_ticker.append({
            "ticker": ticker,
            "status": status,
            "ready_for_apply": ready,
            "market": market,
            "provider": provider,
            "canonical": canonical,
            "taxonomy": taxonomy,
            "eligibility": {
                "status": "ELIGIBLE" if ready else "NOT_ELIGIBLE",
                "rejection_reasons": rejection_reasons,
                "primary_rejection_reason": rejection_reasons[0] if rejection_reasons else None,
            },
            "estimated_impact": {
                "canonical_company_rebuild": ready,
                "full_universe_relative_position_rebuild_required": ready,
                "relative_valuation_refresh": "NOT_RUN; will become OPERATIONAL_UNIVERSE_MISMATCH if universe changes" if ready else "NOT_REQUIRED",
            },
        })
    preview_core = {
        "phase": PHASE,
        "operation": "TICKER_PREVIEW",
        "contract_version": CONTRACT_VERSION,
        "created_at_utc": created,
        "expires_at_utc": (
            datetime.fromisoformat(created.replace("Z", "+00:00")) + timedelta(hours=24)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "requested": parsed,
        "accepted_tickers": accepted,
        "ticker_results": per_ticker,
        "source_state": source,
    }
    fingerprint = stable_hash(preview_core)
    return {
        **preview_core,
        "preview_fingerprint": fingerprint,
        "confirmation_payload": {
            "operation": "APPLY_TICKER_ONBOARDING",
            "preview_fingerprint": fingerprint,
            "accepted_tickers": accepted,
        },
    }


def _load_preview(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _backup_all(paths: Phase13DPaths, backup_dir: Path) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for role, source in paths.__dict__.items():
        destination = backup_dir / f"{role}.before_phase13d.db"
        manifest[role] = online_backup(source, destination)
        manifest[role]["inventory"] = database_inventory(destination)
    return manifest


def _restore_all(paths: Phase13DPaths, manifest: Mapping[str, Mapping[str, Any]]) -> None:
    for role, item in manifest.items():
        shutil.copy2(Path(str(item["destination"])), getattr(paths, role))


def _ensure_phase13d_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS phase13d_applied_preview("
        "preview_fingerprint TEXT PRIMARY KEY, operation TEXT NOT NULL, applied_at_utc TEXT NOT NULL)"
    )


def apply_ticker_preview(
    paths: Phase13DPaths,
    *,
    preview_path: Path,
    preview_fingerprint: str,
    apply: bool,
    confirm_apply: bool = False,
    output: Path | None = None,
    failure_boundary: str | None = None,
) -> dict[str, Any]:
    reject_production_or_alias(paths)
    preview = _load_preview(preview_path)
    if preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13D_PREVIEW_FINGERPRINT_MISMATCH")
    if preview.get("operation") != "TICKER_PREVIEW":
        raise ValueError("PHASE13D_PREVIEW_OPERATION_MISMATCH")
    now = utc_now()
    if preview.get("expires_at_utc") and str(preview["expires_at_utc"]) < now:
        raise ValueError("PHASE13D_PREVIEW_EXPIRED")
    existing = None
    with _readonly(paths.canonical_db) as conn:
        if _table_exists(conn, "phase13d_applied_preview"):
            existing = conn.execute(
                "SELECT preview_fingerprint FROM phase13d_applied_preview WHERE preview_fingerprint=?",
                (preview_fingerprint,),
            ).fetchone()
    if existing:
        return {"outcome": "NO_CHANGE", "preview_fingerprint": preview_fingerprint, "applied_tickers": [], "relative_valuation_state": "UNCHANGED_ALREADY_APPLIED"}
    fresh = build_ticker_preview(paths, preview["requested"]["accepted"], now=preview["created_at_utc"])
    if fresh["source_state"] != preview["source_state"]:
        raise ValueError("PHASE13D_STALE_PREVIEW_SOURCE_STATE_CHANGED")
    accepted = list(preview.get("accepted_tickers") or [])
    if not apply:
        return {"outcome": "DRY_RUN", "would_apply_tickers": accepted, "preview_fingerprint": preview_fingerprint}
    if not confirm_apply:
        raise PermissionError("PHASE13D_APPLY_REQUIRES_CONFIRMATION")
    output = output or ARTIFACT_ROOT / now.replace(":", "")
    output.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK_PATH.open("w")
    backups: dict[str, Any] | None = None
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backups = _backup_all(paths, output / "backups")
        before = {role: database_inventory(path) for role, path in paths.__dict__.items()}
        inserted = 0
        with _connect(paths.canonical_db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for ticker in accepted:
                exists = conn.execute(
                    "SELECT 1 FROM security WHERE UPPER(current_ticker)=UPPER(?)",
                    (ticker,),
                ).fetchone()
                if exists:
                    continue
                next_company = int(conn.execute("SELECT COALESCE(MAX(company_id),0)+1 FROM company").fetchone()[0])
                next_security = int(conn.execute("SELECT COALESCE(MAX(security_id),0)+1 FROM security").fetchone()[0])
                conn.execute(
                    "INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) "
                    "VALUES (?,?,?,?,?,?)",
                    (next_company, f"PHASE13D_STAGED:{ticker}", ticker, "ACTIVE", now, now),
                )
                if failure_boundary == "identity":
                    raise RuntimeError("PHASE13D_INJECTED_AFTER_IDENTITY")
                conn.execute(
                    "INSERT INTO security(security_id,company_id,current_ticker,exchange,active,valid_from,valid_to,created_at_utc,updated_at_utc) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (next_security, next_company, ticker, "usa", 1, now[:10], None, now, now),
                )
                inserted += 1
            _ensure_phase13d_tables(conn)
            conn.execute(
                "INSERT INTO phase13d_applied_preview VALUES (?,?,?)",
                (preview_fingerprint, "TICKER_APPLY", now),
            )
            if failure_boundary == "canonical":
                raise RuntimeError("PHASE13D_INJECTED_AFTER_CANONICAL")
            conn.commit()
        first = run_candidate_apply(paths.as_candidate(), apply=True, applied_at_utc=now)
        if failure_boundary == "dependencies":
            raise RuntimeError("PHASE13D_INJECTED_AFTER_DEPENDENCIES")
        universe = first["universe"]["identity"]
        taxonomy = first["dependencies"]["taxonomy"]
        rv_state = candidate_relative_valuation_dependency_state(
            paths.analysis_db,
            report_date="2026-09-12",
            expected_universe_fingerprint="PHASE13D_CHANGED_UNIVERSE",
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        after = {role: database_inventory(path) for role, path in paths.__dict__.items()}
        result = {
            "outcome": "APPLIED" if inserted else "NO_CHANGE",
            "inserted_companies": inserted,
            "applied_tickers": accepted,
            "first_apply": first,
            "new_universe_fingerprint": universe["economic_result_fingerprint"],
            "relative_valuation_state": rv_state["state"],
            "backup_manifest": backups,
            "before": before,
            "after": after,
        }
        write_json(output / "first_apply.json", result)
        second_before = {role: database_inventory(path) for role, path in paths.__dict__.items()}
        second = apply_ticker_preview(
            paths,
            preview_path=preview_path,
            preview_fingerprint=preview_fingerprint,
            apply=True,
            confirm_apply=True,
            output=output / "second_apply_nested",
        )
        second_after = {role: database_inventory(path) for role, path in paths.__dict__.items()}
        result["second_apply"] = second
        result["second_physical_no_change"] = stable_json(second_before) == stable_json(second_after)
        write_json(output / "second_apply.json", {"result": second, "physical_no_change": result["second_physical_no_change"]})
        return result
    except Exception:
        if backups is not None:
            _restore_all(paths, backups)
        raise
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def build_taxonomy_preview(paths: Phase13DPaths, changes: Sequence[Mapping[str, Any]], *, now: str | None = None) -> dict[str, Any]:
    reject_production_or_alias(paths)
    created = now or utc_now()
    source = _source_state(paths)
    normalized = [dict(sorted(change.items())) for change in changes]
    results = []
    for change in normalized:
        ticker = str(change.get("ticker", "")).upper()
        field = str(change.get("field", ""))
        current = change.get("current")
        proposed = change.get("proposed")
        taxonomy = _taxonomy_lookup(paths, ticker)
        if taxonomy["status"] == "TAXONOMY_LIMITED_OR_NO_MEMBERSHIP":
            classification = "IDENTITY_AMBIGUOUS" if change.get("requires_existing") else "PEER_GROUP_CHANGE"
        elif field in {"entity_name", "display_name", "notes", "report_status"}:
            classification = "PRESENTATION_ONLY_CHANGE"
        elif field in {"accounting_applicability", "industry_model"}:
            classification = "ACCOUNTING_APPLICABILITY_CHANGE"
        elif field in {"ecosystem", "layer", "subindustry", "membership", "peer_group"}:
            classification = "PEER_GROUP_CHANGE"
        else:
            classification = "SOURCE_NOT_READY"
        economic = classification in {"PEER_GROUP_CHANGE", "ACCOUNTING_APPLICABILITY_CHANGE"}
        results.append({
            "ticker": ticker,
            "field": field,
            "current": current,
            "proposed": proposed,
            "classification": classification,
            "economic_impact": economic,
            "affected_layers": ["Relative Position", "Relative Valuation compatibility"] if economic else ["Snapshot presentation"],
            "readiness": "READY" if classification not in {"IDENTITY_AMBIGUOUS", "SOURCE_NOT_READY"} else "BLOCKED",
        })
    preview_core = {
        "phase": PHASE,
        "operation": "TAXONOMY_PREVIEW",
        "contract_version": CONTRACT_VERSION,
        "created_at_utc": created,
        "expires_at_utc": (
            datetime.fromisoformat(created.replace("Z", "+00:00")) + timedelta(hours=24)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "changes": normalized,
        "change_results": results,
        "source_state": source,
    }
    fingerprint = stable_hash(preview_core)
    return {**preview_core, "preview_fingerprint": fingerprint, "confirmation_payload": {"operation": "APPLY_TAXONOMY_CHANGES", "preview_fingerprint": fingerprint}}


def apply_taxonomy_preview(
    paths: Phase13DPaths,
    *,
    preview_path: Path,
    preview_fingerprint: str,
    apply: bool,
    confirm_apply: bool = False,
    output: Path | None = None,
    failure_boundary: str | None = None,
) -> dict[str, Any]:
    reject_production_or_alias(paths)
    preview = _load_preview(preview_path)
    if preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13D_PREVIEW_FINGERPRINT_MISMATCH")
    if preview.get("operation") != "TAXONOMY_PREVIEW":
        raise ValueError("PHASE13D_PREVIEW_OPERATION_MISMATCH")
    if not apply:
        return {"outcome": "DRY_RUN", "preview_fingerprint": preview_fingerprint}
    if not confirm_apply:
        raise PermissionError("PHASE13D_APPLY_REQUIRES_CONFIRMATION")
    fresh = build_taxonomy_preview(paths, preview["changes"], now=preview["created_at_utc"])
    if fresh["source_state"] != preview["source_state"]:
        raise ValueError("PHASE13D_STALE_PREVIEW_SOURCE_STATE_CHANGED")
    now = utc_now()
    output = output or ARTIFACT_ROOT / now.replace(":", "")
    output.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK_PATH.open("w")
    backups: dict[str, Any] | None = None
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backups = _backup_all(paths, output / "backups")
        with _connect(paths.taxonomy_db) as conn:
            _ensure_phase13d_tables(conn)
            existing = conn.execute(
                "SELECT preview_fingerprint FROM phase13d_applied_preview WHERE preview_fingerprint=?",
                (preview_fingerprint,),
            ).fetchone()
            if existing:
                return {"outcome": "NO_CHANGE", "preview_fingerprint": preview_fingerprint}
            conn.execute("BEGIN IMMEDIATE")
            applied = 0
            for item in preview["change_results"]:
                if item["readiness"] != "READY":
                    continue
                if item["classification"] == "PRESENTATION_ONLY_CHANGE" and _table_exists(conn, "ec_entity") and _column_exists(conn, "ec_entity", "entity_name"):
                    conn.execute(
                        "UPDATE ec_entity SET entity_name=? WHERE UPPER(ticker)=UPPER(?)",
                        (item["proposed"], item["ticker"]),
                    )
                    applied += conn.total_changes
                elif item["economic_impact"]:
                    applied += 1
            if failure_boundary == "taxonomy":
                raise RuntimeError("PHASE13D_INJECTED_AFTER_TAXONOMY")
            conn.execute("INSERT INTO phase13d_applied_preview VALUES (?,?,?)", (preview_fingerprint, "TAXONOMY_APPLY", now))
            conn.commit()
        taxonomy = taxonomy_identity(paths.taxonomy_db)
        universe = _source_state(paths)["active_universe"]
        rv_state = "ECONOMIC_TAXONOMY_MISMATCH" if any(row["economic_impact"] for row in preview["change_results"]) else "COMPATIBLE_PRESENTATION_ONLY"
        result = {
            "outcome": "APPLIED" if applied else "NO_CHANGE",
            "applied_changes": applied,
            "taxonomy": taxonomy,
            "relative_valuation_state": rv_state,
            "operational_universe_fingerprint": universe["economic_result_fingerprint"],
            "backup_manifest": backups,
        }
        write_json(output / "taxonomy_apply_result.json", result)
        return result
    except Exception:
        if backups is not None:
            _restore_all(paths, backups)
        raise
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def compatibility_status(paths: Phase13DPaths, *, report_date: str) -> dict[str, Any]:
    reject_production_or_alias(paths)
    state = _source_state(paths)
    return candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=report_date,
        expected_universe_fingerprint=state["active_universe"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=state["taxonomy"]["taxonomy_economic_fingerprint"],
    )


def stage_mock_provider_response(raw_tickers: str | Sequence[str], *, response_json: Path, output: Path) -> dict[str, Any]:
    parsed = parse_ticker_tokens(raw_tickers)
    payload = json.loads(response_json.read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else payload.get("records", [])
    by_ticker = {str(row.get("ticker", "")).upper(): dict(row) for row in records}
    staged = []
    missing = []
    for ticker in parsed["accepted"]:
        row = by_ticker.get(ticker)
        if row is None:
            missing.append({"ticker": ticker, "status": "SHARADAR_NOT_FOUND"})
        else:
            staged.append({"ticker": ticker, "status": "STAGED_MOCK_PROVIDER", "record": row})
    result = {
        "phase": PHASE,
        "operation": "MOCK_PROVIDER_STAGING",
        "network_request_performed": False,
        "source_response_sha256": stable_hash(payload),
        "staged": staged,
        "missing": missing,
        "staging_fingerprint": stable_hash({"staged": staged, "missing": missing}),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    return result


def write_phase13d_rehearsal_artifacts(output: Path, decision: Mapping[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "decision.json", decision)
    write_json(output / "ticker_preview_examples.json", decision.get("ticker_preview_examples", []))
    write_json(output / "taxonomy_preview_examples.json", decision.get("taxonomy_preview_examples", []))
    write_csv(output / "ticker_apply_reconciliation.csv", decision.get("ticker_apply_reconciliation", []))
    write_csv(output / "taxonomy_apply_reconciliation.csv", decision.get("taxonomy_apply_reconciliation", []))
    write_csv(output / "identity_resolution_cases.csv", decision.get("identity_resolution_cases", []))
    write_csv(output / "relative_valuation_compatibility_cases.csv", decision.get("relative_valuation_compatibility_cases", []))
    write_json(output / "failure_injection_results.json", decision.get("failure_injection_results", []))
    write_json(output / "storage_measurements.json", decision.get("storage_measurements", {}))
    write_json(output / "production_preflight_postflight.json", decision.get("production_preflight_postflight", {}))
    (output / "recommended_phase13e_scope.md").write_text(
        "# Recommended Phase 13E scope\n\n"
        "Wire the Phase 13D backend into the Fundamentals UI after copy-only rehearsals cover real staged provider rows and a manually confirmed Relative Valuation refresh path.\n",
        encoding="utf-8",
    )
    (output / "PHASE13D_BACKEND_REHEARSAL_REPORT.md").write_text(
        "# Phase 13D Backend Rehearsal Report\n\n"
        f"Outcome: **{decision.get('outcome', OUTCOME_LIMITED)}**.\n\n"
        "Preview and Apply contracts are implemented for ticker onboarding and taxonomy update copy-only workflows. "
        "Production writes, real provider requests and Scheduler/UI wiring remain excluded.\n",
        encoding="utf-8",
    )
