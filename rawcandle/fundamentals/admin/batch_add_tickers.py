from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZipFile

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminPreview,
    AdminStatus,
    RunStage,
    build_batch_request,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.progress import (
    BATCH_ADD_TICKERS_STAGES,
    ProgressCallback,
    ProgressStage,
    ProgressTracker,
)
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin.rv_identity import active_relative_valuation_identity
from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT, database_inventory, rebuild_ttm, reconcile_canonical, stable_hash, write_json
from rawcandle.fundamentals.phase13b_foundation import database_fingerprint, online_backup
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    reject_production_path,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13d_backend import (
    Phase13DPaths,
    apply_ticker_preview,
    build_ticker_preview,
    reject_production_or_alias,
)
from rawcandle.fundamentals.phase13f3_1_package_recovery import instrumented_package_refresh
from rawcandle.fundamentals.phase13f3_3_structural_break_contract import _events, _structural_evidence, _structural_package_fingerprint
from rawcandle.fundamentals.phase13f3_ticker_transition import REPORT_DATE
from rawcandle.fundamentals.providers.sharadar import FUNDAMENTALS_REQUIRED_FIELDS, SharadarClient, redact_url
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.persistence import (
    RelativeValuationRepository,
    apply_snapshot as apply_rv_snapshot,
    quick_check as rv_quick_check,
    validate_snapshot as validate_rv_snapshot,
)
from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths as RVSourcePaths,
    load_relative_valuation_source,
)
from rawcandle.fundamentals.schema.migrations import PROVIDER_SCHEMA_SQL
from rawcandle.fundamentals.schema.production_bootstrap import insert_production_sharadar_observation
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths


PHASE = "PHASE13G2_BATCH_ADD_TICKERS"
CONTRACT_VERSION = "PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V2"
OUTCOME_B = "OUTCOME B — BATCH ADD TICKERS COPY-ONLY FOUNDATION READY; AUTHORITATIVE FULL DOWNSTREAM GAP REMAINS"
OUTCOME_A = "OUTCOME A — GENERIC BATCH ADD TICKERS AUTHORITATIVE COPY-ONLY PIPELINE VERIFIED AND READY FOR SEPARATELY AUTHORIZED PRODUCTION DEPLOYMENT"
AUTHORITATIVE_DOWNSTREAM_LIMITATION = {
    "status": "NOT_AVAILABLE_FOR_GENERIC_BATCH_ADD_TICKERS",
    "reason": (
        "The current authoritative Phase 13F.4 pipeline is transition-specific: "
        "it stages source rows and identity repairs for the fixed Phase 13F ticker-transition set, "
        "not arbitrary new ticker onboarding batches."
    ),
    "required_adapter": (
        "A generic provider-source and identity adapter must stage accepted ticker fundamentals, "
        "provider identities, canonical identities and aliases before invoking the existing "
        "canonical/TTM/package/RP/RV/dependency sequence."
    ),
}
WRITE_ROLES = ("provider", "canonical", "analysis")
READONLY_COPY_ROLES = ("market", "taxonomy")
ROLE_ORDER = ("provider", "canonical", "analysis", "market", "taxonomy")
DEFAULT_ARCHIVE = ROOT / "data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip"
SUPPORTED_GENERIC_CATEGORIES = {
    "Domestic Common Stock",
    "Domestic Common Stock Primary Class",
    "ADR Common Stock",
    "ADR Common Stock Primary Class",
    "Canadian Common Stock",
}
SUPPORTED_EXCHANGES = {"NASDAQ", "NYSE", "NYSEMKT"}
CIK_RE = re.compile(r"CIK=0*([0-9]+)", re.IGNORECASE)


@dataclass(frozen=True)
class BatchAddTickerPaths:
    provider_db: Path = PRODUCTION["provider"]
    canonical_db: Path = PRODUCTION["canonical"]
    analysis_db: Path = PRODUCTION["analysis"]
    market_db: Path = PRODUCTION["market"]
    taxonomy_db: Path = PRODUCTION["taxonomy"]

    def as_dict(self) -> dict[str, Path]:
        return {
            "provider": self.provider_db,
            "canonical": self.canonical_db,
            "analysis": self.analysis_db,
            "market": self.market_db,
            "taxonomy": self.taxonomy_db,
        }

    def as_phase13d(self) -> Phase13DPaths:
        return Phase13DPaths(
            provider_db=self.provider_db,
            canonical_db=self.canonical_db,
            analysis_db=self.analysis_db,
            market_db=self.market_db,
            taxonomy_db=self.taxonomy_db,
        )


@dataclass(frozen=True)
class CopyLane:
    lane_dir: Path
    paths: BatchAddTickerPaths
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class GenericBatchItemPlan:
    requested_ticker: str
    ticker: str
    status: str
    reason: str
    source_category: str
    provider_metadata: Mapping[str, Any]
    market: Mapping[str, Any]
    classification: Mapping[str, Any]
    canonical: Mapping[str, Any]
    provider_row_count: int
    provider_arq_row_count: int
    source_fingerprint: str
    rows: tuple[Mapping[str, Any], ...] = ()

    @property
    def eligible(self) -> bool:
        return self.status == "ELIGIBLE"

    def safe_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        payload = {
            "requested_ticker": self.requested_ticker,
            "ticker": self.ticker,
            "status": self.status,
            "reason": self.reason,
            "source_category": self.source_category,
            "provider_metadata": dict(self.provider_metadata),
            "market": dict(self.market),
            "classification": dict(self.classification),
            "canonical": dict(self.canonical),
            "provider_row_count": self.provider_row_count,
            "provider_arq_row_count": self.provider_arq_row_count,
            "source_fingerprint": self.source_fingerprint,
        }
        if include_rows:
            payload["rows"] = [dict(row) for row in self.rows]
        return payload


@dataclass(frozen=True)
class GenericBatchPlan:
    contract_version: str
    created_at_utc: str
    network_allowed: bool
    archive_path: str | None
    source_state: Mapping[str, Any]
    items: tuple[GenericBatchItemPlan, ...]
    network: Mapping[str, Any]

    @property
    def accepted_tickers(self) -> tuple[str, ...]:
        return tuple(item.ticker for item in self.items if item.eligible)

    def safe_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        core = {
            "contract_version": self.contract_version,
            "created_at_utc": self.created_at_utc,
            "network_allowed": self.network_allowed,
            "archive_path": self.archive_path,
            "source_state": dict(self.source_state),
            "items": [item.safe_dict(include_rows=include_rows) for item in self.items],
            "network": dict(self.network),
        }
        core["accepted_tickers"] = list(self.accepted_tickers)
        core["plan_fingerprint"] = stable_hash(core)
        return core


def parse_batch_tickers(raw: str | Sequence[str], *, market: str | None = "usa") -> AdminBatchRequest:
    return build_batch_request(AdminOperationType.ADD_TICKERS, raw, market=market, options={"contract_version": CONTRACT_VERSION})


def reject_production_write_targets(paths: BatchAddTickerPaths) -> None:
    reject_production_or_alias(paths.as_phase13d())


def source_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    rv_identity = active_relative_valuation_identity(paths.analysis_db)
    rv_identity_for_fingerprint = {key: value for key, value in rv_identity.items() if key != "database_path"}
    return {
        "contract_version": CONTRACT_VERSION,
        "databases": {role: database_fingerprint(path) for role, path in paths.as_dict().items()},
        "active_relative_valuation": rv_identity_for_fingerprint,
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _extract_cik(value: Any) -> str | None:
    text = str(value or "")
    match = CIK_RE.search(text)
    if not match:
        stripped = re.sub(r"\D", "", text)
        return stripped.lstrip("0") or None
    return match.group(1).lstrip("0") or None


def _provider_metadata(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.provider_db) as conn:
        if not _table_exists(conn, "sharadar_ticker_metadata"):
            return {"status": "MISSING", "source": None}
        columns = _columns(conn, "sharadar_ticker_metadata")
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM sharadar_ticker_metadata WHERE UPPER(ticker)=UPPER(?) ORDER BY "
            "CASE WHEN table_name='fundamentals' THEN 0 WHEN table_name='stocks' THEN 1 ELSE 2 END, lastupdated DESC",
            (ticker,),
        )] if "table_name" in columns else [dict(row) for row in conn.execute(
            "SELECT * FROM sharadar_ticker_metadata WHERE UPPER(ticker)=UPPER(?)",
            (ticker,),
        )]
    if not rows:
        return {"status": "MISSING", "source": None}
    fundamentals = [row for row in rows if str(row.get("table_name") or "fundamentals").lower() == "fundamentals"]
    candidates = fundamentals or rows
    identities = {(str(row.get("permaticker") or ""), str(_extract_cik(row.get("secfilings") or row.get("cik")) or "")) for row in candidates}
    if len(identities) > 1:
        return {"status": "AMBIGUOUS", "source": "sharadar_ticker_metadata", "rows": len(candidates)}
    selected = dict(candidates[0])
    cik = _extract_cik(selected.get("secfilings") or selected.get("cik"))
    if cik:
        selected["cik"] = cik
    return {"status": "FOUND", "source": "sharadar_ticker_metadata", "identity": selected, "candidate_rows": len(candidates)}


def _canonical_identity(paths: BatchAddTickerPaths, ticker: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    cik = metadata.get("cik")
    permaticker = metadata.get("permaticker")
    with _readonly(paths.canonical_db) as conn:
        direct = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active "
            "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=UPPER(?) ORDER BY s.active DESC,s.security_id",
            (ticker,),
        )] if _table_exists(conn, "security") else []
        aliases = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,a.ticker alias_ticker "
            "FROM ticker_alias a JOIN security s USING(security_id) JOIN company c USING(company_id) "
            "WHERE UPPER(a.ticker)=UPPER(?) ORDER BY s.active DESC,s.security_id",
            (ticker,),
        )] if _table_exists(conn, "ticker_alias") else []
        cik_rows = [dict(row) for row in conn.execute(
            "SELECT company_id,cik_normalized FROM company_cik WHERE cik_normalized=?",
            (str(cik),),
        )] if cik and _table_exists(conn, "company_cik") else []
        perm_rows = [dict(row) for row in conn.execute(
            "SELECT security_id,provider_security_id FROM provider_security_identity WHERE provider='SHARADAR' AND provider_security_id=?",
            (str(permaticker),),
        )] if permaticker and _table_exists(conn, "provider_security_identity") else []
    rows = direct + aliases
    company_ids = {int(row["company_id"]) for row in rows}
    return {
        "exists": bool(rows),
        "rows": rows,
        "ambiguous": len(company_ids) > 1 or len({int(row["company_id"]) for row in cik_rows}) > 1 or len({int(row["security_id"]) for row in perm_rows}) > 1,
        "company_id": rows[0]["company_id"] if len(company_ids) == 1 else None,
        "security_id": rows[0]["security_id"] if len(company_ids) == 1 and rows else None,
        "cik_conflicts": cik_rows,
        "permaticker_conflicts": perm_rows,
    }


def _market_evidence(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.market_db) as conn:
        if not _table_exists(conn, "osakedata"):
            return {"status": "MISSING", "markets": [], "row_count": 0}
        rows = [dict(row) for row in conn.execute(
            "SELECT LOWER(COALESCE(market,'usa')) market,COUNT(*) row_count,MIN(pvm) first_date,MAX(pvm) latest_date "
            "FROM osakedata WHERE UPPER(osake)=UPPER(?) GROUP BY LOWER(COALESCE(market,'usa')) ORDER BY market",
            (ticker,),
        )]
    if not rows:
        return {"status": "MISSING", "markets": [], "row_count": 0}
    return {
        "status": "FOUND" if len(rows) == 1 else "AMBIGUOUS",
        "markets": [row["market"] for row in rows],
        "row_count": sum(int(row["row_count"]) for row in rows),
        "first_date": min(str(row["first_date"]) for row in rows),
        "latest_date": max(str(row["latest_date"]) for row in rows),
    }


def _classification(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.market_db) as conn:
        if not _table_exists(conn, "ticker_meta"):
            return {"status": "MISSING", "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION"}
        rows = [dict(row) for row in conn.execute(
            "SELECT ticker,LOWER(COALESCE(market,'usa')) market,sector,industry FROM ticker_meta WHERE UPPER(ticker)=UPPER(?) ORDER BY market",
            (ticker,),
        )]
    if not rows:
        return {"status": "MISSING", "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION"}
    row = next((item for item in rows if item.get("market") == "usa"), rows[0])
    ready = bool(row.get("sector") and row.get("industry"))
    return {
        "status": "READY" if ready else "MISSING",
        "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION",
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "market": row.get("market"),
    }


def _local_provider_rows(paths: BatchAddTickerPaths, ticker: str) -> tuple[dict[str, Any], ...]:
    with _readonly(paths.provider_db) as conn:
        if not _table_exists(conn, "sharadar_fundamental_observation"):
            return ()
        return tuple(dict(row) for row in conn.execute(
            "SELECT * FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?) ORDER BY ticker,dimension,reportperiod,fiscalperiod,date",
            (ticker,),
        ))


def _archive_rows(archive: Path, tickers: set[str]) -> dict[str, tuple[dict[str, Any], ...]]:
    if not archive.exists():
        return {ticker: () for ticker in tickers}
    rows: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in tickers}
    with ZipFile(archive) as zf:
        name = next((item for item in zf.namelist() if item.lower().endswith(".csv")), None)
        if name is None:
            return {ticker: () for ticker in tickers}
        with zf.open(name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            for row in csv.DictReader(text):
                ticker = str(row.get("ticker") or "").upper()
                if ticker in rows:
                    rows[ticker].append(dict(row))
    return {ticker: tuple(items) for ticker, items in rows.items()}


def _network_rows(tickers: Sequence[str], *, network_allowed: bool, client: SharadarClient | None = None) -> tuple[dict[str, tuple[dict[str, Any], ...]], dict[str, Any]]:
    if not network_allowed:
        return {ticker: () for ticker in tickers}, {"status": "DISABLED", "request_count": 0}
    client = client or SharadarClient()
    output: dict[str, tuple[dict[str, Any], ...]] = {}
    calls: list[dict[str, Any]] = []
    for ticker in tickers:
        result = client.fundamentals(ticker=ticker, fields=FUNDAMENTALS_REQUIRED_FIELDS, limit=10000)
        calls.append({
            "ticker": ticker,
            "status": result.status,
            "auth_status": result.auth_status,
            "http_status": result.http_status,
            "endpoint": result.endpoint,
            "url": redact_url(result.url),
            "rows": len(result.records),
        })
        output[ticker] = tuple(dict(row) for row in result.records) if result.ok else ()
    return output, {"status": "ALLOWED", "request_count": client.request_count, "calls": calls}


def build_generic_batch_plan(
    paths: BatchAddTickerPaths,
    request: AdminBatchRequest,
    *,
    now: str | None = None,
    network_allowed: bool = False,
    archive_path: Path | None = None,
    network_client: SharadarClient | None = None,
    include_rows: bool = True,
) -> GenericBatchPlan:
    created = now or utc_now()
    tickers = tuple(request.normalized_inputs)
    effective_archive = DEFAULT_ARCHIVE if archive_path is None else archive_path
    archive_rows = _archive_rows(effective_archive, set(tickers)) if effective_archive else {ticker: () for ticker in tickers}
    network_needed: list[str] = []
    local_rows_by_ticker: dict[str, tuple[dict[str, Any], ...]] = {}
    for ticker in tickers:
        local_rows = _local_provider_rows(paths, ticker)
        local_rows_by_ticker[ticker] = local_rows
        if not local_rows and not archive_rows.get(ticker):
            network_needed.append(ticker)
    fetched_rows, network = _network_rows(network_needed, network_allowed=network_allowed, client=network_client)
    items: list[GenericBatchItemPlan] = []
    for ticker in tickers:
        metadata_state = _provider_metadata(paths, ticker)
        metadata = dict(metadata_state.get("identity") or {})
        canonical = _canonical_identity(paths, ticker, metadata)
        market = _market_evidence(paths, ticker)
        classification = _classification(paths, ticker)
        if local_rows_by_ticker[ticker]:
            rows = local_rows_by_ticker[ticker]
            source_category = "local_provider"
        elif archive_rows.get(ticker):
            rows = archive_rows[ticker]
            source_category = "verified_archive"
        else:
            rows = fetched_rows.get(ticker, ())
            source_category = "network" if rows else ("network_unavailable" if network_allowed else "network_required")
        blockers: list[str] = []
        if canonical["ambiguous"]:
            blockers.append("IDENTITY_AMBIGUOUS")
        if metadata_state["status"] == "AMBIGUOUS":
            blockers.append("PROVIDER_IDENTITY_AMBIGUOUS")
        if metadata_state["status"] == "MISSING":
            blockers.append("PROVIDER_METADATA_MISSING")
        if str(metadata.get("isdelisted") or "").upper() == "Y":
            blockers.append("DELISTED_SECURITY")
        if metadata.get("category") and metadata.get("category") not in SUPPORTED_GENERIC_CATEGORIES:
            blockers.append("UNSUPPORTED_SECURITY_TYPE")
        if str(metadata.get("exchange") or "").upper() not in SUPPORTED_EXCHANGES:
            blockers.append("INCOMPATIBLE_EXCHANGE")
        if market["status"] != "FOUND" or market.get("markets") != ["usa"]:
            blockers.append("MARKET_NOT_UNAMBIGUOUS_USA")
        if classification["status"] != "READY":
            blockers.append("MISSING_CLASSIFICATION")
        if not rows:
            blockers.append("FUNDAMENTAL_SOURCE_ROWS_MISSING")
        if canonical["exists"]:
            status = "ALREADY_PRESENT"
            reason = "Ticker is already present in canonical identities."
        elif blockers:
            status = "REVIEW_REQUIRED" if any("AMBIGUOUS" in blocker or blocker in {"PROVIDER_METADATA_MISSING", "FUNDAMENTAL_SOURCE_ROWS_MISSING"} for blocker in blockers) else "REJECTED"
            reason = ",".join(blockers)
        else:
            status = "ELIGIBLE"
            reason = "Eligible from provider identity, price, classification and fundamentals evidence."
        arq_rows = [row for row in rows if str(row.get("dimension") or "").upper() == "ARQ"]
        safe_rows = tuple(dict(row) for row in rows) if include_rows else ()
        items.append(GenericBatchItemPlan(
            requested_ticker=ticker,
            ticker=ticker,
            status=status,
            reason=reason,
            source_category=source_category,
            provider_metadata=metadata_state,
            market=market,
            classification=classification,
            canonical=canonical,
            provider_row_count=len(rows),
            provider_arq_row_count=len(arq_rows),
            source_fingerprint=stable_hash({"ticker": ticker, "source_category": source_category, "rows": rows}),
            rows=safe_rows,
        ))
    return GenericBatchPlan(
        contract_version=CONTRACT_VERSION,
        created_at_utc=created,
        network_allowed=network_allowed,
        archive_path=str(effective_archive) if effective_archive else None,
        source_state=source_state(paths),
        items=tuple(items),
        network=network,
    )


def create_copy_lane(
    paths: BatchAddTickerPaths,
    *,
    lane_dir: Path,
    writer: AdminRunWriter | None = None,
) -> CopyLane:
    lane_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    copied: dict[str, Path] = {}
    for role in ROLE_ORDER:
        source = paths.as_dict()[role]
        destination = lane_dir / f"{role}.db"
        manifest[role] = online_backup(source, destination)
        copied[role] = destination
        if writer is not None:
            writer.append_heartbeat({"stage": "COPY_DATABASE", "role": role, "destination": str(destination)})
    copy_paths = BatchAddTickerPaths(
        provider_db=copied["provider"],
        canonical_db=copied["canonical"],
        analysis_db=copied["analysis"],
        market_db=copied["market"],
        taxonomy_db=copied["taxonomy"],
    )
    reject_production_write_targets(copy_paths)
    return CopyLane(lane_dir=lane_dir, paths=copy_paths, manifest=manifest)


def cleanup_copy_lane(lane: CopyLane) -> dict[str, Any]:
    removed: list[str] = []
    for path in sorted(lane.lane_dir.glob("**/*"), reverse=True):
        if path.is_file() and (
            path.suffix in {".db", ".sqlite", ".sqlite3"}
            or path.name.endswith(("-wal", "-shm", "-journal"))
        ):
            removed.append(str(path))
            path.unlink(missing_ok=True)
    for path in sorted(lane.lane_dir.glob("**/*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        lane.lane_dir.rmdir()
    except OSError:
        pass
    return {"removed_files": removed, "removed_count": len(removed)}


def _status_from_phase13d(row: Mapping[str, Any]) -> AdminStatus:
    status = str(row.get("status") or "")
    ready = bool(row.get("ready_for_apply"))
    if ready:
        return AdminStatus.ELIGIBLE
    if status == "ALREADY_PRESENT":
        return AdminStatus.ALREADY_PRESENT
    if status in {"IDENTITY_AMBIGUOUS", "API_FETCH_REQUIRED", "READY_WITH_LIMITATIONS"}:
        return AdminStatus.REVIEW_REQUIRED
    return AdminStatus.REJECTED


def _reason(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "UNKNOWN")
    eligibility = row.get("eligibility") if isinstance(row.get("eligibility"), Mapping) else {}
    primary = eligibility.get("primary_rejection_reason")
    if primary:
        return f"{status}: {primary}"
    if status == "READY_WITH_LIMITATIONS":
        return "Eligible for copy apply, but taxonomy connectivity is limited."
    if status == "READY_LOCAL_PROVIDER":
        return "Eligible from local provider and market evidence."
    if status == "ALREADY_PRESENT":
        return "Ticker is already present in canonical identities."
    return status.replace("_", " ").title()


def _decision_from_row(row: Mapping[str, Any]) -> AdminItemDecision:
    provider = row.get("provider") if isinstance(row.get("provider"), Mapping) else {}
    identity = provider.get("identity") if isinstance(provider.get("identity"), Mapping) else {}
    market = row.get("market") if isinstance(row.get("market"), Mapping) else {}
    markets = market.get("markets") if isinstance(market.get("markets"), list) else []
    return AdminItemDecision(
        item_key=str(row.get("ticker")),
        requested_value=str(row.get("ticker")),
        normalized_value=str(row.get("ticker")),
        status=_status_from_phase13d(row),
        reason=_reason(row),
        market=str(markets[0]) if len(markets) == 1 else None,
        company_name=identity.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if row.get("ready_for_apply") else None,
        source_category=str(provider.get("source") or provider.get("status") or "local"),
        warnings=tuple(row.get("eligibility", {}).get("rejection_reasons", []) if isinstance(row.get("eligibility"), Mapping) else ()),
        blockers=tuple(row.get("eligibility", {}).get("rejection_reasons", []) if isinstance(row.get("eligibility"), Mapping) else ()),
        applied_action="PENDING_COPY_APPLY" if row.get("ready_for_apply") else None,
        details={
            "phase13d_status": row.get("status"),
            "provider": provider,
            "market": market,
            "canonical": row.get("canonical"),
            "taxonomy": row.get("taxonomy"),
            "estimated_impact": row.get("estimated_impact"),
        },
    )


def _decision_from_plan_item(item: GenericBatchItemPlan) -> AdminItemDecision:
    status = {
        "ELIGIBLE": AdminStatus.ELIGIBLE,
        "ALREADY_PRESENT": AdminStatus.ALREADY_PRESENT,
        "REVIEW_REQUIRED": AdminStatus.REVIEW_REQUIRED,
        "REJECTED": AdminStatus.REJECTED,
    }.get(item.status, AdminStatus.REVIEW_REQUIRED)
    metadata = item.provider_metadata.get("identity") if isinstance(item.provider_metadata.get("identity"), Mapping) else {}
    return AdminItemDecision(
        item_key=item.ticker,
        requested_value=item.requested_ticker,
        normalized_value=item.ticker,
        status=status,
        reason=item.reason,
        market="usa" if item.market.get("markets") == ["usa"] else None,
        company_name=metadata.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if item.eligible else None,
        source_category=item.source_category,
        warnings=(item.reason,) if status == AdminStatus.REVIEW_REQUIRED else (),
        blockers=(item.reason,) if status in {AdminStatus.REVIEW_REQUIRED, AdminStatus.REJECTED} else (),
        applied_action="PENDING_AUTHORITATIVE_COPY_APPLY" if item.eligible else None,
        details=item.safe_dict(include_rows=False),
    )


def _decision_from_plan_mapping(item: Mapping[str, Any]) -> AdminItemDecision:
    status = {
        "ELIGIBLE": AdminStatus.ELIGIBLE,
        "ALREADY_PRESENT": AdminStatus.ALREADY_PRESENT,
        "REVIEW_REQUIRED": AdminStatus.REVIEW_REQUIRED,
        "REJECTED": AdminStatus.REJECTED,
    }.get(str(item.get("status")), AdminStatus.REVIEW_REQUIRED)
    metadata_state = item.get("provider_metadata") if isinstance(item.get("provider_metadata"), Mapping) else {}
    metadata = metadata_state.get("identity") if isinstance(metadata_state.get("identity"), Mapping) else {}
    return AdminItemDecision(
        item_key=str(item.get("ticker")),
        requested_value=str(item.get("requested_ticker") or item.get("ticker")),
        normalized_value=str(item.get("ticker")),
        status=status,
        reason=str(item.get("reason") or item.get("status") or "UNKNOWN"),
        market="usa" if item.get("market", {}).get("markets") == ["usa"] else None,
        company_name=metadata.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if status == AdminStatus.ELIGIBLE else None,
        source_category=str(item.get("source_category") or "unknown"),
        warnings=(str(item.get("reason")),) if status == AdminStatus.REVIEW_REQUIRED else (),
        blockers=(str(item.get("reason")),) if status in {AdminStatus.REVIEW_REQUIRED, AdminStatus.REJECTED} else (),
        applied_action="PENDING_AUTHORITATIVE_COPY_APPLY" if status == AdminStatus.ELIGIBLE else None,
        details={key: value for key, value in item.items() if key != "rows"},
    )


def build_preview_from_copy(
    paths: BatchAddTickerPaths,
    request: AdminBatchRequest,
    *,
    now: str | None = None,
    network_allowed: bool = False,
    network_client: SharadarClient | None = None,
) -> tuple[AdminPreview, dict[str, Any]]:
    raw_preview = build_ticker_preview(paths.as_phase13d(), request.normalized_inputs, now=now)
    generic_plan = build_generic_batch_plan(
        paths,
        request,
        now=now or raw_preview["created_at_utc"],
        network_allowed=network_allowed,
        network_client=network_client,
    )
    rejected_decisions = tuple(
        AdminItemDecision(
            item_key=str(item["requested_value"]),
            requested_value=str(item["requested_value"]),
            normalized_value=str(item["requested_value"]).upper(),
            status=AdminStatus.REJECTED,
            reason=str(item["reason"]),
            source_category="input_parser",
            blockers=(str(item["reason"]),),
        )
        for item in request.rejected_inputs
    )
    if _provider_schema_ready(paths.provider_db):
        decisions = tuple(_decision_from_plan_item(item) for item in generic_plan.items) + rejected_decisions
        proposed = tuple(
            {
                "ticker": item.ticker,
                "action": "ADD_TICKER",
                "status": item.status,
                "ready_for_apply": item.eligible,
                "source_category": item.source_category,
                "provider_row_count": item.provider_row_count,
                "provider_arq_row_count": item.provider_arq_row_count,
            }
            for item in generic_plan.items
            if item.eligible
        )
    else:
        decisions = tuple(_decision_from_row(row) for row in raw_preview["ticker_results"]) + rejected_decisions
        proposed = tuple(
            {
                "ticker": row["ticker"],
                "action": "ADD_TICKER",
                "status": row["status"],
                "ready_for_apply": row["ready_for_apply"],
            }
            for row in raw_preview["ticker_results"]
            if row.get("ready_for_apply")
        )
    preview = AdminPreview(
        operation_type=AdminOperationType.ADD_TICKERS,
        request=request,
        decisions=decisions,
        source_state=generic_plan.source_state,
        proposed_changes=proposed,
        warnings=tuple(
            item.reason for item in generic_plan.items if item.status == "REVIEW_REQUIRED"
        ) + (("Network access enabled for missing archive/provider rows.",) if network_allowed else ()),
    )
    preview_dict = preview.as_dict()
    raw_preview["phase13g2_preview_fingerprint"] = preview_dict["preview_fingerprint"]
    raw_preview["phase13g2_request_fingerprint"] = preview_dict["request_fingerprint"]
    raw_preview["phase13g2_change_set_fingerprint"] = preview_dict["change_set_fingerprint"]
    raw_preview["generic_batch_plan"] = generic_plan.safe_dict(include_rows=True)
    return preview, raw_preview


def _write_preview_payload(path: Path, raw_preview: Mapping[str, Any], phase13g2_preview: Mapping[str, Any]) -> None:
    payload = dict(raw_preview)
    payload["phase13g2_preview"] = dict(phase13g2_preview)
    write_json(path, payload)


def _load_preview_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_preview_not_stale(paths: BatchAddTickerPaths, payload: Mapping[str, Any]) -> None:
    phase_preview = payload.get("phase13g2_preview") if isinstance(payload.get("phase13g2_preview"), Mapping) else {}
    fresh = source_state(paths)
    if fresh != phase_preview.get("source_state"):
        raise ValueError("PHASE13G2_STALE_PREVIEW_SOURCE_STATE_CHANGED")


def _provider_schema_ready(path: Path) -> bool:
    with _readonly(path) as conn:
        return all(_table_exists(conn, table) for table in ("provider_run", "provider_observation", "sharadar_fundamental_observation"))


def _ensure_identity_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS provider_company_identity("
        "provider TEXT NOT NULL, provider_identifier_type TEXT NOT NULL, provider_identifier_value TEXT NOT NULL, "
        "company_id INTEGER NOT NULL, provider_ticker TEXT, source TEXT NOT NULL, source_type TEXT NOT NULL, "
        "source_value TEXT, created_at_utc TEXT NOT NULL, PRIMARY KEY(provider,provider_identifier_type,provider_identifier_value))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS provider_security_identity("
        "provider TEXT NOT NULL, provider_security_id TEXT NOT NULL, security_id INTEGER NOT NULL, "
        "provider_ticker TEXT, source TEXT NOT NULL, created_at_utc TEXT NOT NULL, PRIMARY KEY(provider,provider_security_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS company_cik("
        "company_id INTEGER NOT NULL, cik_normalized TEXT NOT NULL, cik_display TEXT NOT NULL, source TEXT NOT NULL, "
        "source_table TEXT, source_row_id TEXT, status TEXT NOT NULL, created_at_utc TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'LEGACY_BOOTSTRAP', "
        "source_name TEXT, source_field TEXT, source_value TEXT, derivation TEXT, confidence TEXT NOT NULL DEFAULT 'HIGH', "
        "PRIMARY KEY(company_id,cik_normalized))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS phase13g2_applied_plan("
        "plan_fingerprint TEXT PRIMARY KEY, operation TEXT NOT NULL, applied_at_utc TEXT NOT NULL)"
    )


def _next_id(conn: sqlite3.Connection, table: str, column: str) -> int:
    return int(conn.execute(f"SELECT COALESCE(MAX({column}),0)+1 FROM {table}").fetchone()[0])


def _apply_identities(paths: BatchAddTickerPaths, items: Sequence[Mapping[str, Any]], *, applied_at: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(paths.canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _ensure_identity_tables(conn)
            for item in items:
                ticker = str(item["ticker"]).upper()
                metadata_state = item.get("provider_metadata") if isinstance(item.get("provider_metadata"), Mapping) else {}
                metadata = metadata_state.get("identity") if isinstance(metadata_state.get("identity"), Mapping) else {}
                existing = conn.execute(
                    "SELECT c.company_id,s.security_id FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=UPPER(?)",
                    (ticker,),
                ).fetchone()
                if existing:
                    rows.append({"ticker": ticker, "company_id": int(existing["company_id"]), "security_id": int(existing["security_id"]), "status": "ALREADY_PRESENT"})
                    continue
                cik = str(metadata.get("cik") or "").strip()
                permaticker = str(metadata.get("permaticker") or "").strip()
                company_id = _next_id(conn, "company", "company_id")
                security_id = _next_id(conn, "security", "security_id")
                company_key = f"SEC_CIK:{cik}" if cik else f"SHARADAR_PERMATICKER:{permaticker}"
                company_name = metadata.get("name") or ticker
                exchange = metadata.get("exchange") or "usa"
                valid_from = metadata.get("firstpricedate") or item.get("market", {}).get("first_date") or applied_at[:10]
                conn.execute(
                    "INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?)",
                    (company_id, company_key, company_name, "ACTIVE", applied_at, applied_at),
                )
                conn.execute(
                    "INSERT INTO security(security_id,company_id,current_ticker,exchange,active,valid_from,valid_to,created_at_utc,updated_at_utc) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (security_id, company_id, ticker, exchange, 1, valid_from, None, applied_at, applied_at),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES (?,?,?,?,?,?)",
                    (security_id, ticker, "SHARADAR", valid_from, None, PHASE),
                )
                if permaticker:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_security_identity(provider,provider_security_id,security_id,provider_ticker,source,created_at_utc) VALUES('SHARADAR',?,?,?,?,?)",
                        (permaticker, security_id, ticker, PHASE, applied_at),
                    )
                if cik:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_company_identity(provider,provider_identifier_type,provider_identifier_value,company_id,provider_ticker,source,source_type,source_value,created_at_utc) "
                        "VALUES('SEC','CIK',?,?,?,?,?,?,?)",
                        (cik, company_id, ticker, PHASE, "sharadar_ticker_metadata.secfilings", cik, applied_at),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO company_cik(company_id,cik_normalized,cik_display,source,source_table,source_row_id,status,created_at_utc,source_type,source_name,source_field,source_value,derivation,confidence) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (company_id, cik, cik, PHASE, "sharadar_ticker_metadata", ticker, "ACTIVE", applied_at, "PROVIDER_METADATA", "Sharadar ticker metadata", "secfilings", cik, "parsed SEC CIK query parameter", "HIGH"),
                    )
                rows.append({"ticker": ticker, "company_id": company_id, "security_id": security_id, "status": "CREATED"})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"rows": rows, "created": sum(1 for row in rows if row["status"] == "CREATED"), "fingerprint": stable_hash(rows)}


def _stage_generic_provider_rows(paths: BatchAddTickerPaths, items: Sequence[Mapping[str, Any]], *, applied_at: str, inject_failure: bool = False) -> dict[str, Any]:
    identities: dict[str, tuple[int, int]] = {}
    with _readonly(paths.canonical_db) as canonical:
        for row in canonical.execute("SELECT company_id,security_id,current_ticker FROM security"):
            identities[str(row["current_ticker"]).upper()] = (int(row["company_id"]), int(row["security_id"]))
    run_id = "PHASE13G2_" + stable_hash({item["ticker"]: item.get("source_fingerprint") for item in items})[:24]
    inserted = Counter()
    matched = Counter()
    skipped = Counter()
    with sqlite3.connect(paths.provider_db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if not _table_exists(conn, "provider_run"):
            conn.executescript(PROVIDER_SCHEMA_SQL)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,entitlement_scope,source_version,metadata_json) "
                "VALUES(?,'SHARADAR',?,?,'SUCCESS',?,?,?,?)",
                (
                    run_id, applied_at, applied_at, "PHASE13G2_GENERIC_BATCH_ADD_TICKERS",
                    "Sharadar local/archive/network staged batch", CONTRACT_VERSION,
                    json.dumps({"tickers": [item["ticker"] for item in items], "sources": {item["ticker"]: item.get("source_category") for item in items}}, sort_keys=True),
                ),
            )
            seen = 0
            for item in items:
                ticker = str(item["ticker"]).upper()
                identity = identities.get(ticker)
                if identity is None:
                    skipped["identity_not_found"] += len(item.get("rows") or ())
                    continue
                company_id, security_id = identity
                for row in item.get("rows") or ():
                    staged = dict(row)
                    staged["ticker"] = ticker
                    if not staged.get("permaticker"):
                        metadata = item.get("provider_metadata", {}).get("identity", {})
                        staged["permaticker"] = metadata.get("permaticker")
                    dimension = str(staged.get("dimension") or "").upper()
                    if dimension not in {"ARQ", "MRQ", "ART", "MRT", "ARY", "MRY"}:
                        skipped["unsupported_dimension"] += 1
                        continue
                    matched[dimension] += 1
                    if insert_production_sharadar_observation(conn, staged, run_id, applied_at, company_id=company_id, security_id=security_id):
                        inserted[dimension] += 1
                    seen += 1
                    if inject_failure and seen >= 3:
                        raise RuntimeError("PHASE13G2_INJECTED_PROVIDER_STAGING_FAILURE")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "run_id": run_id,
        "matched_by_dimension": dict(sorted(matched.items())),
        "inserted_by_dimension": dict(sorted(inserted.items())),
        "logical_changes": sum(inserted.values()),
        "skipped": dict(sorted(skipped.items())),
    }


def _valuation_classification_update_generic(paths: BatchAddTickerPaths, *, tickers: Sequence[str], applied_at: str) -> dict[str, Any]:
    reject_production_path(paths.analysis_db, "analysis")
    changed = 0
    classification = {ticker: _classification(paths, ticker) for ticker in tickers}
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("ATTACH DATABASE ? AS canonical", (str(paths.canonical_db),))
        conn.execute("BEGIN IMMEDIATE")
        try:
            marks = ",".join("?" for _ in tickers) or "?"
            params = tuple(tickers) if tickers else ("__none__",)
            if _table_exists(conn, "valuation_revised_result"):
                rows = [dict(row) for row in conn.execute(
                    "SELECT DISTINCT r.company_id,s.current_ticker "
                    "FROM valuation_revised_result r JOIN canonical.security s ON s.security_id=r.security_id "
                    f"WHERE UPPER(s.current_ticker) IN ({marks})",
                    params,
                )]
                for row in rows:
                    source = classification.get(str(row["current_ticker"]).upper())
                    if not source or source.get("status") != "READY":
                        continue
                    before = conn.total_changes
                    conn.execute(
                        "UPDATE valuation_revised_result SET ticker=?,sector=?,industry=? WHERE company_id=?",
                        (row["current_ticker"], source["sector"], source["industry"], int(row["company_id"])),
                    )
                    changed += conn.total_changes - before
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("DETACH DATABASE canonical")
    return {"outcome": "APPLIED" if changed else "NO_CHANGE", "rows_changed": changed, "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION", "applied_at_utc": applied_at}


def _manual_rv_refresh_generic(paths: BatchAddTickerPaths, *, output: Path, applied_at: str) -> dict[str, Any]:
    source = load_relative_valuation_source(
        RVSourcePaths(paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db, paths.provider_db),
        as_of_date=REPORT_DATE,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=REPORT_DATE,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_rv_snapshot(snapshot, source.inputs)
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        first = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at)
        second_before = database_inventory(paths.analysis_db)
        second = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at)
        second_after = database_inventory(paths.analysis_db)
        check = rv_quick_check(conn)
        active = RelativeValuationRepository(conn).active_metadata(model_fingerprint=RV_MODEL_FINGERPRINT)
    result = {
        "source_metadata": source.metadata,
        "snapshot": {
            "source_fingerprint": snapshot.source_fingerprint,
            "result_fingerprint": snapshot.result_fingerprint,
            "physical_content_fingerprint": physical,
            "company_count": len(content["companies"]),
            "peer_rows": len(content["peers"]),
            "own_history_rows": len(content["own_history"]),
            "component_rows": len(content["components"]),
        },
        "first_apply": asdict(first),
        "second_apply": asdict(second),
        "second_logical_zero_writes": second.logical_bulk_writes == 0 and second.pointer_changes == 0,
        "second_physical_no_change": second_before == second_after,
        "quick_check": check,
        "active_metadata": active,
    }
    write_json(output / "relative_valuation_manual_refresh.json", result)
    return result


def _snapshot_smoke_generic(paths: BatchAddTickerPaths, output: Path, *, tickers: Sequence[str]) -> dict[str, Any]:
    report_dir = output / "snapshot_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = SnapshotPaths(paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db, paths.provider_db)
    results = {}
    for ticker in tickers:
        try:
            generated = generate_active_company_snapshot(
                snapshot_paths,
                ticker=ticker,
                report_date=REPORT_DATE,
                output_dir=report_dir,
                overwrite=True,
            )
            text = Path(generated["output_path"]).read_text(encoding="utf-8")
            results[ticker] = {
                "status": generated["status"],
                "fingerprint": generated["report_content_fingerprint"],
                "output_path": generated["output_path"],
                "contains_internal_ids": any(term in text for term in ("company_id", "security_id", "quarter_id")),
            }
        except Exception as exc:
            results[ticker] = {"status": "FAILED", "error": type(exc).__name__, "reason": str(exc)}
    return results


def _run_authoritative_downstream(
    paths: BatchAddTickerPaths,
    output: Path,
    *,
    accepted_tickers: Sequence[str],
    applied_at: str,
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    candidate = CandidatePaths(paths.canonical_db, paths.analysis_db, paths.taxonomy_db, provider_db=paths.provider_db, market_db=paths.market_db)
    result: dict[str, Any] = {"applied_at_utc": applied_at, "accepted_tickers": list(accepted_tickers)}
    if progress:
        progress.running(ProgressStage.CANONICAL_REBUILD, "Rebuilding canonical quarters from staged provider rows.")
    result["canonical"] = reconcile_canonical(paths.provider_db, paths.canonical_db, applied_at=applied_at)
    if progress:
        progress.completed(
            ProgressStage.CANONICAL_REBUILD,
            "Canonical rebuild completed.",
            processed_rows=int(result["canonical"].get("canonical_rows") or 0),
        )
        progress.running(ProgressStage.TTM_REBUILD, "Rebuilding TTM endpoints.")
    result["ttm"] = rebuild_ttm(paths.canonical_db, applied_at=applied_at)
    if progress:
        progress.completed(ProgressStage.TTM_REBUILD, "TTM rebuild completed.", processed_rows=int(result["ttm"].get("rows") or 0))
        progress.running(ProgressStage.STRUCTURAL_DEPENDENCIES, "Applying structural dependency contract.")
    result["structural_contract"] = structural_break.apply_contract(paths.canonical_db, events=_events(), applied_at_utc=applied_at)
    result["structural_evidence"] = _structural_evidence(paths.canonical_db)
    structural_package_fingerprint = _structural_package_fingerprint(result["structural_contract"])
    result["structural_package_fingerprint"] = structural_package_fingerprint
    result["valuation_classification"] = _valuation_classification_update_generic(paths, tickers=accepted_tickers, applied_at=applied_at)
    if progress:
        progress.completed(
            ProgressStage.STRUCTURAL_DEPENDENCIES,
            "Structural dependencies applied.",
            processed_rows=int(result["structural_contract"].get("quarter_regime_count") or 0),
        )
    result["schema"] = ensure_candidate_schema(candidate, applied_at_utc=applied_at, apply=True, allow_production=False)
    universe = backfill_universe(candidate, applied_at_utc=applied_at, apply=True, allow_production=False)
    result["universe"] = universe
    if progress:
        progress.running(ProgressStage.PACKAGE_CALCULATION, "Running Operating-Income V2 package calculation.")
    result["package"] = instrumented_package_refresh(paths.as_dict(), output, allow_production=False)
    if progress:
        package_rows = result["package"].get("first_apply", {}).get("rows", {})
        progress.completed(
            ProgressStage.PACKAGE_CALCULATION,
            "Operating-Income V2 package calculation completed.",
            processed_rows=int(package_rows.get("score") or 0) if isinstance(package_rows, Mapping) else None,
        )
        progress.running(ProgressStage.PACKAGE_APPLY, "Operating-Income V2 package apply verified.")
        progress.completed(ProgressStage.PACKAGE_APPLY, "Operating-Income V2 package apply completed.")
        progress.running(ProgressStage.RELATIVE_POSITION, "Refreshing full-universe Relative Position.")
    result["relative_position"] = asdict(refresh_relative_position(
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        market_db=paths.market_db,
        taxonomy_db=paths.taxonomy_db,
        snapshot_date=REPORT_DATE,
        model_fingerprint=RP_MODEL_FINGERPRINT,
        applied_at_utc=applied_at,
    ))
    if progress:
        progress.completed(
            ProgressStage.RELATIVE_POSITION,
            "Relative Position refresh completed.",
            processed_rows=int(result["relative_position"].get("result_rows") or 0),
        )
        progress.running(ProgressStage.RELATIVE_VALUATION, "Refreshing full-universe Relative Valuation.")
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    result["pre_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["relative_valuation"] = _manual_rv_refresh_generic(paths, output=output, applied_at=applied_at)
    if progress:
        progress.completed(
            ProgressStage.RELATIVE_VALUATION,
            "Relative Valuation refresh completed.",
            processed_rows=int(result["relative_valuation"].get("snapshot", {}).get("company_count") or 0),
        )
        progress.running(ProgressStage.DEPENDENCY_ATTACHMENT, "Attaching refreshed dependency identities.")
    structural_metadata = {
        "structural_contract_version": structural_break.CONTRACT_VERSION,
        "structural_package_fingerprint": structural_package_fingerprint,
        "structural_event_fingerprint": result["structural_contract"]["economic_event_fingerprint"],
        "structural_regime_fingerprint": result["structural_contract"]["regime_fingerprint"],
        "structural_event_count": result["structural_contract"]["event_count"],
        "structural_quarter_regime_count": result["structural_contract"]["quarter_regime_count"],
        "structural_ttm_regime_count": result["structural_contract"]["ttm_regime_count"],
    }
    result["dependencies"] = attach_dependencies(
        candidate,
        universe=universe["identity"],
        applied_at_utc=applied_at,
        apply=True,
        allow_production=False,
        structural_metadata=structural_metadata,
    )
    result["post_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    if progress:
        progress.completed(ProgressStage.DEPENDENCY_ATTACHMENT, "Dependency attachment completed.")
        progress.running(ProgressStage.SNAPSHOT_SMOKE, "Generating eligible Snapshot smoke reports.")
    result["snapshots"] = _snapshot_smoke_generic(paths, output, tickers=accepted_tickers)
    if progress:
        progress.completed(ProgressStage.SNAPSHOT_SMOKE, "Snapshot smoke completed.", processed_items=len(result["snapshots"]), total_items=len(accepted_tickers))
    result["invocation_counts"] = {"package": 1, "relative_position": 1, "relative_valuation": 1}
    return result


def _skip_authoritative_downstream_progress(progress: ProgressTracker, *, reason: str) -> None:
    for stage in (
        ProgressStage.CANONICAL_REBUILD,
        ProgressStage.TTM_REBUILD,
        ProgressStage.STRUCTURAL_DEPENDENCIES,
        ProgressStage.PACKAGE_CALCULATION,
        ProgressStage.PACKAGE_APPLY,
        ProgressStage.RELATIVE_POSITION,
        ProgressStage.RELATIVE_VALUATION,
        ProgressStage.DEPENDENCY_ATTACHMENT,
        ProgressStage.SNAPSHOT_SMOKE,
    ):
        progress.skipped(stage, reason)


def _apply_generic_plan(
    paths: BatchAddTickerPaths,
    plan: Mapping[str, Any],
    *,
    output: Path,
    failure_boundary: str | None = None,
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    plan_fingerprint = str(plan.get("plan_fingerprint") or stable_hash(plan))
    items = [item for item in plan.get("items", []) if item.get("status") == "ELIGIBLE"]
    accepted = [str(item["ticker"]).upper() for item in items]
    applied_at = utc_now()
    with sqlite3.connect(paths.canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_identity_tables(conn)
        existing = conn.execute("SELECT 1 FROM phase13g2_applied_plan WHERE plan_fingerprint=?", (plan_fingerprint,)).fetchone()
    if existing:
        if progress:
            progress.running(ProgressStage.NO_CHANGE_VERIFICATION, "Verifying previously applied no-change batch.")
            progress.completed(ProgressStage.NO_CHANGE_VERIFICATION, "No copy-lane changes required.", processed_items=0, total_items=len(accepted))
        return {"outcome": "NO_CHANGE", "preview_fingerprint": plan_fingerprint, "applied_tickers": [], "downstream": {"invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0}}}
    if progress:
        progress.running(ProgressStage.IDENTITY_AND_UNIVERSE, "Persisting canonical and provider identities.", processed_items=0, total_items=len(accepted))
    identities = _apply_identities(paths, items, applied_at=applied_at)
    if progress:
        progress.completed(ProgressStage.IDENTITY_AND_UNIVERSE, "Canonical and provider identities persisted.", processed_items=len(accepted), total_items=len(accepted))
    if failure_boundary == "identity":
        raise RuntimeError("PHASE13G2_INJECTED_AFTER_IDENTITY")
    if progress:
        progress.running(ProgressStage.PROVIDER_STAGING, "Staging provider rows for accepted tickers.", processed_items=0, total_items=len(accepted))
    provider = _stage_generic_provider_rows(paths, items, applied_at=applied_at, inject_failure=failure_boundary == "provider_staging")
    if progress:
        progress.completed(
            ProgressStage.PROVIDER_STAGING,
            "Provider staging completed.",
            processed_items=len(accepted),
            total_items=len(accepted),
            processed_rows=int(provider.get("logical_changes") or 0),
        )
    if failure_boundary == "provider":
        raise RuntimeError("PHASE13G2_INJECTED_AFTER_PROVIDER")
    if accepted:
        downstream = _run_authoritative_downstream(
            paths,
            output,
            accepted_tickers=accepted,
            applied_at=applied_at,
            progress=progress,
        )
    else:
        if progress:
            _skip_authoritative_downstream_progress(progress, reason="No eligible accepted tickers; downstream rebuilds not required.")
        downstream = {"invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0}}
    with sqlite3.connect(paths.canonical_db) as conn:
        _ensure_identity_tables(conn)
        conn.execute(
            "INSERT OR IGNORE INTO phase13g2_applied_plan(plan_fingerprint,operation,applied_at_utc) VALUES(?,?,?)",
            (plan_fingerprint, "GENERIC_BATCH_ADD_TICKERS", applied_at),
        )
        conn.commit()
    return {
        "outcome": "APPLIED" if identities["created"] or provider["logical_changes"] else "NO_CHANGE",
        "preview_fingerprint": plan_fingerprint,
        "applied_tickers": accepted,
        "identities": identities,
        "provider_staging": provider,
        "downstream": downstream,
    }


def run_preview(
    raw_inputs: str | Sequence[str],
    *,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    network_allowed: bool = False,
    market: str | None = "usa",
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    request = parse_batch_tickers(raw_inputs, market=market)
    run_id = stable_run_id(AdminOperationType.ADD_TICKERS, fingerprint(request))
    writer = AdminRunWriter(run_id, AdminOperationType.ADD_TICKERS, root=run_root)
    progress = ProgressTracker(
        run_id=run_id,
        operation_type=AdminOperationType.ADD_TICKERS,
        run_dir=writer.run_dir,
        stages=BATCH_ADD_TICKERS_STAGES,
        callback=progress_callback,
    )
    started = utc_now()
    progress.running(ProgressStage.PREFLIGHT, "Recording Batch Add Tickers preview request.", processed_items=0, total_items=len(request.normalized_inputs))
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Batch Add Tickers preview request recorded.")
    writer.write_json("request.json", request.as_dict() | {"network_allowed": network_allowed})
    progress.completed(ProgressStage.PREFLIGHT, "Preview request recorded.", processed_items=0, total_items=len(request.normalized_inputs))
    progress.running(ProgressStage.PREVIEW_VALIDATION, "Creating copy lane for read-only preview.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Creating copy lane for read-only production-shaped preview.")
    lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "preview_lane", writer=writer)
    try:
        progress.completed(ProgressStage.PREVIEW_VALIDATION, "Preview copy lane ready.")
        progress.running(ProgressStage.SOURCE_RESOLUTION, "Resolving provider, market, identity and classification evidence.", processed_items=0, total_items=len(request.normalized_inputs))
        preview, raw_preview = build_preview_from_copy(lane.paths, request, network_allowed=network_allowed)
        progress.completed(ProgressStage.SOURCE_RESOLUTION, "Source resolution completed.", processed_items=len(request.normalized_inputs), total_items=len(request.normalized_inputs))
        preview_dict = preview.as_dict()
        preview_path = writer.write_json("preview.json", preview_dict)
        phase13d_preview_path = writer.run_dir / "phase13d_preview_payload.json"
        _write_preview_payload(phase13d_preview_path, raw_preview, preview_dict)
        writer.write_items_csv([item.as_dict() for item in preview.decisions])
        writer.checkpoint(
            RunStage.PREVIEW_READY,
            message="Batch preview ready. Production was not modified.",
            preview_fingerprint=preview_dict["preview_fingerprint"],
            counters=_counts(preview.decisions),
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.COMPLETED,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_dict["preview_fingerprint"],
            request=request.as_dict(),
            item_results=preview.decisions,
            summary_counts=_counts(preview.decisions),
            downstream={
                "package": "NOT_RUN_IN_PREVIEW",
                "relative_position": "NOT_RUN_IN_PREVIEW",
                "relative_valuation": "NOT_RUN_IN_PREVIEW",
                "network": "ALLOWED" if network_allowed else "DISABLED",
                "generic_plan": "READY",
            },
            artifacts={"preview": str(preview_path), "phase13d_preview_payload": str(phase13d_preview_path)},
            recommended_next_action="Review the preview. Copy-only apply requires --apply, --confirm-apply and the preview fingerprint.",
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        progress.running(ProgressStage.CLEANUP, "Removing preview copy lane.")
        cleanup = cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Preview copy lane removed.", processed_items=int(cleanup.get("removed_count") or 0))
        progress.running(ProgressStage.COMPLETED, "Preview run completed.")
        progress.completed(ProgressStage.COMPLETED, "Preview run completed.")
        writer.checkpoint(RunStage.COMPLETED, message="Preview run completed.", preview_fingerprint=preview_dict["preview_fingerprint"])
        writer.write_exit_code(0)
        writer.write_manifest()
        return result_dict | {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "phase13d_preview_payload_path": str(phase13d_preview_path),
            "cleanup": cleanup,
        }
    except Exception as exc:
        writer.write_error(exc)
        progress.failed(ProgressStage.SOURCE_RESOLUTION, "Preview failed.", errors=(f"{type(exc).__name__}: {exc}",))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message="Preview failed before any write boundary.")
        writer.write_exit_code(2)
        writer.write_manifest()
        cleanup_copy_lane(lane)
        raise


def run_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    confirm_apply: bool = False,
    failure_boundary: str | None = None,
    keep_copies: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not confirm_apply:
        raise PermissionError("PHASE13G2_APPLY_REQUIRES_CONFIRMATION")
    payload = _load_preview_payload(preview_payload_path)
    phase_preview = payload.get("phase13g2_preview") if isinstance(payload.get("phase13g2_preview"), Mapping) else {}
    if phase_preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13G2_PREVIEW_FINGERPRINT_MISMATCH")
    request_payload = phase_preview.get("request") if isinstance(phase_preview.get("request"), Mapping) else {}
    request = AdminBatchRequest(
        operation_type=AdminOperationType.ADD_TICKERS,
        requested_inputs=tuple(request_payload.get("requested_inputs") or ()),
        normalized_inputs=tuple(request_payload.get("normalized_inputs") or ()),
        rejected_inputs=tuple(request_payload.get("rejected_inputs") or ()),
        market=request_payload.get("market"),
        options=request_payload.get("options") or {},
    )
    run_id = stable_run_id(AdminOperationType.ADD_TICKERS, preview_fingerprint, suffix="apply")
    writer = AdminRunWriter(run_id, AdminOperationType.ADD_TICKERS, root=run_root)
    progress = ProgressTracker(
        run_id=run_id,
        operation_type=AdminOperationType.ADD_TICKERS,
        run_dir=writer.run_dir,
        stages=BATCH_ADD_TICKERS_STAGES,
        callback=progress_callback,
    )
    started = utc_now()
    progress.running(ProgressStage.PREFLIGHT, "Recording Batch Add Tickers apply request.", processed_items=0, total_items=len(request.normalized_inputs))
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Copy-only apply request recorded.", preview_fingerprint=preview_fingerprint)
    writer.write_json("request.json", request.as_dict())
    writer.write_json("preview.json", phase_preview)
    progress.completed(ProgressStage.PREFLIGHT, "Apply request recorded.", processed_items=0, total_items=len(request.normalized_inputs))
    progress.running(ProgressStage.PREVIEW_VALIDATION, "Creating copy lane for copy-only apply.")
    writer.checkpoint(RunStage.APPLY_STARTED, message="Creating copy lane for copy-only apply.", preview_fingerprint=preview_fingerprint)
    lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "apply_lane", writer=writer)
    rollback: dict[str, Any] = {}
    write_boundary_crossed = False
    try:
        progress.completed(ProgressStage.PREVIEW_VALIDATION, "Apply copy lane ready.")
        progress.running(ProgressStage.SOURCE_RESOLUTION, "Validating saved preview freshness and source plan.", processed_items=0, total_items=len(request.normalized_inputs))
        _assert_preview_not_stale(lane.paths, payload)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Preview is fresh on apply copy.", preview_fingerprint=preview_fingerprint)
        copy_preview, raw_preview = build_preview_from_copy(lane.paths, request, now=payload.get("created_at_utc"))
        saved_plan = payload.get("generic_batch_plan") if isinstance(payload.get("generic_batch_plan"), Mapping) else raw_preview["generic_batch_plan"]
        progress.completed(ProgressStage.SOURCE_RESOLUTION, "Saved preview and source plan validated.", processed_items=len(request.normalized_inputs), total_items=len(request.normalized_inputs))
        copy_preview_path = lane.lane_dir / "accepted_preview.json"
        write_json(copy_preview_path, raw_preview)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Applying accepted tickers to database copies.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
        write_boundary_crossed = True
        before = source_state(lane.paths)["databases"]
        if _provider_schema_ready(lane.paths.provider_db):
            applied = _apply_generic_plan(
                lane.paths,
                saved_plan,
                output=lane.lane_dir / "generic_authoritative_apply",
                failure_boundary=failure_boundary,
                progress=progress,
            )
            applied["mode"] = "GENERIC_AUTHORITATIVE_BATCH"
        else:
            applied = apply_ticker_preview(
                lane.paths.as_phase13d(),
                preview_path=copy_preview_path,
                preview_fingerprint=raw_preview["preview_fingerprint"],
                apply=True,
                confirm_apply=True,
                output=lane.lane_dir / "phase13d_apply",
                failure_boundary=failure_boundary,
            )
            applied["mode"] = "PHASE13D_COMPATIBILITY_FALLBACK"
        after = source_state(lane.paths)["databases"]
        if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH":
            repeated = _apply_generic_plan(
                lane.paths,
                saved_plan,
                output=lane.lane_dir / "generic_authoritative_repeat",
                progress=progress,
            )
        else:
            repeated = apply_ticker_preview(
                lane.paths.as_phase13d(),
                preview_path=copy_preview_path,
                preview_fingerprint=raw_preview["preview_fingerprint"],
                apply=True,
                confirm_apply=True,
                output=lane.lane_dir / "phase13d_repeat",
            )
        if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH":
            saved_plan_items = saved_plan.get("items") if isinstance(saved_plan.get("items"), list) else []
            base_decisions = tuple(_decision_from_plan_mapping(item) for item in saved_plan_items) or copy_preview.decisions
        else:
            base_decisions = copy_preview.decisions
        decisions = _apply_decisions(base_decisions, applied)
        counts = _counts(decisions)
        downstream = applied.get("downstream") if isinstance(applied.get("downstream"), Mapping) else {}
        invocation_counts = downstream.get("invocation_counts") if isinstance(downstream, Mapping) else None
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.PARTIALLY_COMPLETED if any(item.status in {AdminStatus.REJECTED, AdminStatus.REVIEW_REQUIRED} for item in decisions) else AdminStatus.COMPLETED,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=decisions,
            summary_counts=counts,
            rollback={"status": "NOT_REQUIRED"},
            downstream={
                "mode": applied.get("mode"),
                "phase13d_candidate_apply": "NOT_USED_GENERIC_AUTHORITATIVE_BATCH" if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH" else "RUN_ONCE_FOR_BATCH",
                "package": downstream.get("package", "NOT_RUN") if isinstance(downstream, Mapping) else "NOT_RUN",
                "relative_position": downstream.get("relative_position", "NOT_RUN") if isinstance(downstream, Mapping) else "NOT_RUN",
                "relative_valuation": downstream.get("relative_valuation", applied.get("relative_valuation_state")) if isinstance(downstream, Mapping) else applied.get("relative_valuation_state"),
                "invocation_counts": invocation_counts or {"package": 0, "relative_position": 0, "relative_valuation": 0},
                "repeat_apply_outcome": repeated.get("outcome"),
                "authoritative_downstream": {
                    "status": "COMPLETED_FOR_GENERIC_BATCH" if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH" else AUTHORITATIVE_DOWNSTREAM_LIMITATION["status"],
                    "accepted_tickers": applied.get("applied_tickers") or [],
                },
            },
            artifacts={"apply": str(lane.lane_dir / ("generic_authoritative_apply" if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH" else "phase13d_apply"))},
            recommended_next_action="Review copy-only evidence. A production run still requires a separate explicit authorization.",
        )
        result_dict = result.as_dict()
        result_dict["copy_apply"] = {
            "phase13d_result": applied,
            "repeat_result": repeated,
            "before_inventory": before,
            "after_inventory": after,
            "copy_lane": str(lane.lane_dir),
        }
        writer.write_final_result(result)
        writer.write_json("copy_apply_technical.json", result_dict["copy_apply"])
        writer.write_items_csv([item.as_dict() for item in decisions])
        writer.write_text("report.md", render_markdown_report(result_dict))
        progress.running(ProgressStage.FINAL_VALIDATION, "Writing final apply artifacts.")
        progress.completed(ProgressStage.FINAL_VALIDATION, "Final apply artifacts written.", processed_items=len(decisions), total_items=len(decisions))
        writer.checkpoint(RunStage.PARTIALLY_COMPLETED if result.outcome == AdminStatus.PARTIALLY_COMPLETED else RunStage.COMPLETED, message="Copy-only apply completed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True, counters=counts)
        writer.write_exit_code(1 if result.outcome == AdminStatus.PARTIALLY_COMPLETED else 0)
        writer.write_manifest()
        progress.running(ProgressStage.CLEANUP, "Cleaning copy lane." if not keep_copies else "Retaining copy lane by request.")
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Copy lane cleanup completed.", processed_items=int(cleanup.get("removed_count") or 0) if "removed_count" in cleanup else None)
        progress.running(ProgressStage.COMPLETED, "Copy-only apply completed.")
        progress.completed(ProgressStage.COMPLETED, "Copy-only apply completed.")
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup}
    except Exception as exc:
        writer.write_error(exc)
        if write_boundary_crossed:
            progress.rolling_back("Copy apply failed after write boundary; restoring copied databases.", errors=(f"{type(exc).__name__}: {exc}",))
            writer.checkpoint(RunStage.ROLLBACK_STARTED, message="Copy apply failed; restoring copy lane from fresh source backups.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            rollback = _restore_copy_lane_from_sources(source_paths, lane)
            progress.rolled_back("Copied databases restored after failure.")
            writer.checkpoint(RunStage.ROLLBACK_COMPLETE, message="Copy lane restored after failure.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            terminal_stage = RunStage.FAILED_AFTER_WRITE
            outcome = AdminStatus.ROLLED_BACK
        else:
            progress.failed(ProgressStage.SOURCE_RESOLUTION, "Copy apply failed before write boundary.", errors=(f"{type(exc).__name__}: {exc}",))
            rollback = {"status": "NOT_REQUIRED", "message": "Failure occurred before the copy write boundary."}
            terminal_stage = RunStage.FAILED_BEFORE_WRITE
            outcome = AdminStatus.FAILED
        error_decisions = tuple(
            AdminItemDecision(
                item_key=value,
                requested_value=value,
                normalized_value=value,
                status=AdminStatus.FAILED,
                reason=f"Copy apply failed and was rolled back: {type(exc).__name__}",
            )
            for value in request.normalized_inputs
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=outcome,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=error_decisions,
            summary_counts=_counts(error_decisions),
            rollback=rollback,
            recommended_next_action="Inspect error.json and retry only after resolving the failure.",
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(terminal_stage, message="Copy-only apply failed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(3 if write_boundary_crossed else 2)
        writer.write_manifest()
        progress.running(ProgressStage.CLEANUP, "Cleaning failed copy lane." if not keep_copies else "Retaining failed copy lane by request.")
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Failed copy lane cleanup completed.", processed_items=int(cleanup.get("removed_count") or 0) if "removed_count" in cleanup else None)
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup, "error": type(exc).__name__}


def _restore_copy_lane_from_sources(source_paths: BatchAddTickerPaths, lane: CopyLane) -> dict[str, Any]:
    restored: dict[str, Any] = {"status": "ROLLED_BACK", "roles": {}}
    for role in ROLE_ORDER:
        destination = lane.paths.as_dict()[role]
        source = source_paths.as_dict()[role]
        online_backup(source, destination)
        restored["roles"][role] = database_fingerprint(destination)
    return restored


def _apply_decisions(decisions: Sequence[AdminItemDecision], applied: Mapping[str, Any]) -> tuple[AdminItemDecision, ...]:
    applied_tickers = {str(ticker).upper() for ticker in applied.get("applied_tickers") or ()}
    outcome = str(applied.get("outcome") or "")
    output: list[AdminItemDecision] = []
    for item in decisions:
        if item.status == AdminStatus.ELIGIBLE and item.normalized_value in applied_tickers and outcome == "APPLIED":
            output.append(
                AdminItemDecision(
                    **{**item.__dict__, "status": AdminStatus.APPLIED, "reason": "Applied on copy lane.", "applied_action": "COPY_ONBOARD_APPLIED"}
                )
            )
        elif item.status == AdminStatus.ELIGIBLE and outcome == "NO_CHANGE":
            output.append(
                AdminItemDecision(
                    **{**item.__dict__, "status": AdminStatus.NO_CHANGE, "reason": "No copy-lane change was required.", "applied_action": "NO_CHANGE"}
                )
            )
        else:
            output.append(item)
    return tuple(output)


def _counts(decisions: Sequence[AdminItemDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in decisions:
        key = item.status.value.lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def disk_hygiene_snapshot(path: Path = Path(".")) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {"path": str(path.resolve()), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
