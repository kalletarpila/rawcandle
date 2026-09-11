from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT, compare_production_inventory, production_inventory


PHASE = "PHASE13A_TICKER_ONBOARDING_READINESS_AUDIT"
OUTCOME_AUTHORITATIVE_UNIVERSE_REQUIRED = (
    "OUTCOME B - AUTHORITATIVE OPERATIONAL UNIVERSE WORK REQUIRED FIRST"
)
CANONICAL_OUTCOME_LABEL = (
    "OUTCOME B — AUTHORITATIVE OPERATIONAL UNIVERSE WORK REQUIRED FIRST"
)
DOC_PATH = ROOT / "docs/fundamentals_v4/fundamentals_v4_phase13a_ticker_onboarding_readiness.md"
ARCHIVE_ROOT = ROOT / "data/source_archives/sharadar/fundamentals"
BOOTSTRAP_CSV = ROOT / "temp/v3_active_tickers_99_27.csv"
SCHEDULER_UI = ROOT / "dev_tools/stock_update_scheduler_ui.py"
SNAPSHOT_PAGE = ROOT / "dev_tools/fundamentals_snapshot_page.py"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"

REQUIRED_STATUSES = (
    "READY_LOCAL_PROVIDER",
    "READY_LOCAL_ARCHIVE",
    "API_FETCH_REQUIRED",
    "ALREADY_PRESENT",
    "PARTIALLY_PRESENT",
    "MARKET_DATA_NOT_FOUND",
    "MARKET_AMBIGUOUS",
    "SHARADAR_NOT_FOUND",
    "IDENTITY_AMBIGUOUS",
    "UNSUPPORTED_SECURITY_TYPE",
    "TAXONOMY_MISSING",
    "ADDED",
    "ADDED_WITH_LIMITATIONS",
    "NO_CHANGE",
    "FAILED_ROLLED_BACK",
)


@dataclass(frozen=True)
class AuditPaths:
    output: Path
    provider_db: Path = PRODUCTION["provider"]
    canonical_db: Path = PRODUCTION["canonical"]
    analysis_db: Path = PRODUCTION["analysis"]
    market_db: Path = PRODUCTION["market"]
    taxonomy_db: Path = PRODUCTION["taxonomy"]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted((dict(row) for row in rows), key=lambda item: stable_json(item)):
            writer.writerow(row)


def connect_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _fetch_one(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else 0


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone())


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def git_state() -> dict[str, Any]:
    upstream = subprocess.run(
        ("git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    ahead = behind = None
    if upstream.returncode == 0 and upstream.stdout.strip():
        left, right = upstream.stdout.split()
        behind, ahead = int(left), int(right)
    return {
        "branch": _git("branch", "--show-current"),
        "head": _git("rev-parse", "HEAD"),
        "status_porcelain": _git("status", "--porcelain"),
        "upstream_ahead": ahead,
        "upstream_behind": behind,
    }


def normalize_ticker_batch(text: str, *, max_batch_size: int = 25) -> dict[str, Any]:
    tokens = [token.strip().upper() for token in re.split(r"[\s,]+", text or "") if token.strip()]
    seen: set[str] = set()
    normalized: list[str] = []
    duplicates: list[str] = []
    invalid: list[str] = []
    for token in tokens:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,15}", token):
            invalid.append(token)
            continue
        if token in seen:
            duplicates.append(token)
            continue
        seen.add(token)
        normalized.append(token)
    return {
        "input_tokens": tokens,
        "normalized": normalized,
        "duplicates_removed": duplicates,
        "invalid_tokens": invalid,
        "max_batch_size": max_batch_size,
        "within_limit": len(normalized) <= max_batch_size,
    }


def preview_status_contract() -> dict[str, Any]:
    return {
        "version": "PHASE13A_PREVIEW_STATUS_CONTRACT_V1",
        "batch": {
            "parse": "split on comma, whitespace and line breaks; uppercase; keep first occurrence order",
            "maximum_unique_tickers": 25,
            "preview": "each submitted ticker receives an independent public status and reason code",
            "apply": "user confirms the valid subset; the accepted subset is one coherent operational batch",
            "retry": "same confirmed semantic batch returns NO_CHANGE when all durable state is already present",
            "confirmation_token": "hash preview inputs, source inventories, selected ticker identities and policy version",
        },
        "statuses": {
            status: {"public": True, "terminal_preview": status not in {"ADDED", "ADDED_WITH_LIMITATIONS", "FAILED_ROLLED_BACK"}}
            for status in REQUIRED_STATUSES
        },
        "browser_must_never_receive": [
            "API keys",
            "database credentials",
            "unrestricted filesystem paths",
            "raw exception traces",
            "arbitrary SQL",
            "shell commands",
        ],
    }


def database_paths_inventory(paths: AuditPaths) -> list[dict[str, Any]]:
    rows = []
    for role, path in (
        ("provider", paths.provider_db),
        ("canonical", paths.canonical_db),
        ("analysis", paths.analysis_db),
        ("market", paths.market_db),
        ("taxonomy", paths.taxonomy_db),
    ):
        rows.append({
            "role": role,
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "sha256": _file_sha256(path) if path.exists() else "",
        })
    rows.append({"role": "sharadar_archive_root", "path": str(ARCHIVE_ROOT), "exists": ARCHIVE_ROOT.exists(), "size": 0, "sha256": ""})
    rows.append({"role": "bootstrap_csv", "path": str(BOOTSTRAP_CSV), "exists": BOOTSTRAP_CSV.exists(), "size": BOOTSTRAP_CSV.stat().st_size if BOOTSTRAP_CSV.exists() else 0, "sha256": _file_sha256(BOOTSTRAP_CSV) if BOOTSTRAP_CSV.exists() else ""})
    return rows


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_quantitative_evidence(paths: AuditPaths) -> dict[str, Any]:
    with connect_ro(paths.canonical_db) as canonical, connect_ro(paths.provider_db) as provider, connect_ro(paths.analysis_db) as analysis, connect_ro(paths.market_db) as market, connect_ro(paths.taxonomy_db) as taxonomy:
        canonical_counts = {
            "companies": _fetch_one(canonical, "SELECT COUNT(*) FROM company"),
            "securities": _fetch_one(canonical, "SELECT COUNT(*) FROM security"),
            "active_securities": _fetch_one(canonical, "SELECT COUNT(*) FROM security WHERE active=1"),
            "ttm_companies": _fetch_one(canonical, "SELECT COUNT(DISTINCT company_id) FROM v4_ttm_values"),
            "ttm_rows": _fetch_one(canonical, "SELECT COUNT(*) FROM v4_ttm_values"),
            "bootstrap_alias_tickers": _fetch_one(canonical, "SELECT COUNT(DISTINCT ticker) FROM ticker_alias WHERE source='v3_active_tickers_99_27'"),
            "company_ciks": _fetch_one(canonical, "SELECT COUNT(DISTINCT cik_normalized) FROM company_cik WHERE status='ACTIVE'"),
            "sharadar_provider_identities": _fetch_one(canonical, "SELECT COUNT(*) FROM provider_company_identity WHERE provider='SHARADAR'"),
        }
        provider_counts = {
            "observations": _fetch_one(provider, "SELECT COUNT(*) FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals'"),
            "tickers": _fetch_one(provider, "SELECT COUNT(DISTINCT provider_ticker) FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals'"),
            "companies": _fetch_one(provider, "SELECT COUNT(DISTINCT company_id) FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals'"),
            "permatickers": _fetch_one(provider, "SELECT COUNT(DISTINCT permaticker) FROM sharadar_fundamental_observation WHERE permaticker IS NOT NULL AND permaticker<>''"),
        }
        downstream_counts = {
            "score_companies": _fetch_one(analysis, "SELECT COUNT(DISTINCT company_id) FROM score_result"),
            "lifecycle_companies": _fetch_one(analysis, "SELECT COUNT(DISTINCT company_id) FROM lifecycle_revised_result"),
            "valuation_companies": _fetch_one(analysis, "SELECT COUNT(DISTINCT company_id) FROM valuation_revised_result"),
            "delta_companies": _fetch_one(analysis, "SELECT COUNT(DISTINCT company_id) FROM fundamental_delta_result"),
            "relative_position_companies": _fetch_one(analysis, "SELECT COUNT(DISTINCT company_id) FROM relative_position_result"),
            "diagnostic_evaluations_raw_table": _fetch_one(analysis, "SELECT COUNT(*) FROM diagnostic_flag_evaluation"),
            "diagnostic_evaluations_active_package": _fetch_one(
                analysis,
                "SELECT evaluation_count FROM diagnostic_flag_package "
                "WHERE model_fingerprint='0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904' "
                "ORDER BY applied_at_utc DESC LIMIT 1",
            ),
            "relative_valuation_companies": _fetch_one(analysis, "SELECT COUNT(DISTINCT company_id) FROM relative_valuation_company_result"),
        }
        market_counts = {
            "market_tickers": _fetch_one(market, "SELECT COUNT(DISTINCT UPPER(osake)) FROM osakedata"),
            "market_ticker_markets": _fetch_one(market, "SELECT COUNT(*) FROM (SELECT UPPER(osake), market FROM osakedata GROUP BY UPPER(osake), market)"),
            "latest_price_date": _fetch_one(market, "SELECT MAX(pvm) FROM osakedata WHERE close>0"),
            "tickers_with_ohlc": _fetch_one(market, "SELECT COUNT(DISTINCT UPPER(osake)) FROM osakedata WHERE open>0 AND high>0 AND low>0 AND close>0"),
        }
        taxonomy_counts = {
            "ticker_entities": _fetch_one(taxonomy, "SELECT COUNT(*) FROM ec_entity WHERE entity_type='TICKER'"),
            "active_ticker_entities": _fetch_one(taxonomy, "SELECT COUNT(*) FROM ec_entity WHERE entity_type='TICKER' AND status='ACTIVE'"),
            "ticker_alias_rows": _fetch_one(taxonomy, "SELECT COUNT(*) FROM ec_entity_alias") if _table_exists(taxonomy, "ec_entity_alias") else 0,
        }
        active_package = dict(analysis.execute("SELECT * FROM fundamentals_active_model_family WHERE singleton=1").fetchone())
        active_relative = [dict(row) for row in analysis.execute("SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint")]
    return {
        "canonical": canonical_counts,
        "provider": provider_counts,
        "downstream": downstream_counts,
        "market": market_counts,
        "taxonomy": taxonomy_counts,
        "active_package": active_package,
        "active_relative_valuation": active_relative,
    }


def collect_universe_sources(paths: AuditPaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []
    with connect_ro(paths.canonical_db) as canonical, connect_ro(paths.provider_db) as provider, connect_ro(paths.analysis_db) as analysis, connect_ro(paths.market_db) as market, connect_ro(paths.taxonomy_db) as taxonomy:
        sets: dict[str, set[str]] = {}
        sets["canonical.security.active"] = {row["ticker"] for row in canonical.execute("SELECT UPPER(current_ticker) ticker FROM security WHERE active=1")}
        sets["canonical.ticker_alias.bootstrap"] = {row["ticker"] for row in canonical.execute("SELECT UPPER(ticker) ticker FROM ticker_alias WHERE source='v3_active_tickers_99_27'")}
        sets["canonical.ttm.companies"] = {row["ticker"] for row in canonical.execute("SELECT UPPER(s.current_ticker) ticker FROM v4_ttm_values t JOIN security s USING(company_id) GROUP BY UPPER(s.current_ticker)")}
        sets["provider.sharadar.fundamentals"] = {row["ticker"] for row in provider.execute("SELECT UPPER(provider_ticker) ticker FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals' AND provider_ticker IS NOT NULL GROUP BY UPPER(provider_ticker)")}
        sets["market.osakedata"] = {row["ticker"] for row in market.execute("SELECT UPPER(osake) ticker FROM osakedata GROUP BY UPPER(osake)")}
        sets["taxonomy.ec_entity.active_ticker"] = {row["ticker"] for row in taxonomy.execute("SELECT UPPER(ticker) ticker FROM ec_entity WHERE entity_type='TICKER' AND status='ACTIVE' AND ticker IS NOT NULL GROUP BY UPPER(ticker)")}
        analysis_company_ids = {int(row[0]) for row in analysis.execute("SELECT DISTINCT company_id FROM score_result")}
        canonical_company_tickers = {
            int(row["company_id"]): row["ticker"]
            for row in canonical.execute("SELECT company_id,UPPER(current_ticker) ticker FROM security WHERE active=1")
        }
        sets["analysis.score"] = {canonical_company_tickers[value] for value in analysis_company_ids if value in canonical_company_tickers}
        for name, values in sets.items():
            inventory.append({"source": name, "ticker_count": len(values), "sample": " ".join(sorted(values)[:10])})
        active = sets["canonical.security.active"]
        for name, values in sets.items():
            missing_from_active = sorted(values - active)[:100]
            missing_from_source = sorted(active - values)[:100]
            discrepancies.append({
                "comparison": f"{name} vs canonical.security.active",
                "left_only_count": len(values - active),
                "right_only_count": len(active - values),
                "left_only_sample": " ".join(missing_from_active[:20]),
                "right_only_sample": " ".join(missing_from_source[:20]),
            })
    return inventory, discrepancies


def identity_resolution_matrix(paths: AuditPaths) -> list[dict[str, Any]]:
    with connect_ro(paths.canonical_db) as canonical, connect_ro(paths.provider_db) as provider, connect_ro(paths.market_db) as market, connect_ro(paths.taxonomy_db) as taxonomy:
        ambiguous_market = _fetch_one(market, "SELECT COUNT(*) FROM (SELECT UPPER(osake) ticker,COUNT(DISTINCT market) n FROM osakedata GROUP BY UPPER(osake) HAVING n>1)")
        duplicate_alias = _fetch_one(canonical, "SELECT COUNT(*) FROM (SELECT UPPER(ticker),COUNT(DISTINCT security_id) n FROM ticker_alias GROUP BY UPPER(ticker) HAVING n>1)")
        duplicate_provider_ticker_permaticker = _fetch_one(provider, "SELECT COUNT(*) FROM (SELECT UPPER(ticker),COUNT(DISTINCT permaticker) n FROM sharadar_fundamental_observation WHERE permaticker IS NOT NULL AND permaticker<>'' GROUP BY UPPER(ticker) HAVING n>1)")
        one_company_multiple_securities = _fetch_one(canonical, "SELECT COUNT(*) FROM (SELECT company_id,COUNT(*) n FROM security GROUP BY company_id HAVING n>1)")
        active_security_tickers = {row[0] for row in canonical.execute("SELECT UPPER(current_ticker) FROM security WHERE active=1")}
        taxonomy_tickers = {row[0] for row in taxonomy.execute("SELECT UPPER(ticker) FROM ec_entity WHERE entity_type='TICKER' AND status='ACTIVE' AND ticker IS NOT NULL")}
        taxonomy_missing = len(active_security_tickers - taxonomy_tickers)
        active_without_cik = _fetch_one(canonical, "SELECT COUNT(*) FROM company c JOIN security s USING(company_id) WHERE s.active=1 AND NOT EXISTS (SELECT 1 FROM company_cik cc WHERE cc.company_id=c.company_id AND cc.status='ACTIVE')")
    return [
        {"evidence": "CIK", "available": True, "source": "canonical.company_cik", "minimum_use": "required unless provider persistent identifier plus alias history proves same company", "risk_count": active_without_cik},
        {"evidence": "Sharadar permaticker", "available": True, "source": "provider.sharadar_fundamental_observation.permaticker", "minimum_use": "required for Sharadar identity when populated; plain ticker is insufficient", "risk_count": duplicate_provider_ticker_permaticker},
        {"evidence": "current ticker and market", "available": True, "source": "canonical.security + market.osakedata", "minimum_use": "routing key only, not permanent company identity", "risk_count": ambiguous_market},
        {"evidence": "ticker aliases", "available": True, "source": "canonical.ticker_alias", "minimum_use": "resolve submitted aliases and block ambiguous reuse", "risk_count": duplicate_alias},
        {"evidence": "multiple share classes", "available": "partial", "source": "canonical.security.company_id", "minimum_use": "same company_id may own several securities; onboarding must select one security", "risk_count": one_company_multiple_securities},
        {"evidence": "taxonomy classification", "available": True, "source": "taxonomy.ec_entity", "minimum_use": "required for peer-scoped layers, never infer from ticker/name", "risk_count": taxonomy_missing},
    ]


def candidate_coverage_summary(paths: AuditPaths) -> list[dict[str, Any]]:
    with connect_ro(paths.canonical_db) as canonical, connect_ro(paths.provider_db) as provider, connect_ro(paths.market_db) as market, connect_ro(paths.taxonomy_db) as taxonomy:
        active = {row[0] for row in canonical.execute("SELECT UPPER(current_ticker) FROM security WHERE active=1")}
        provider_tickers = {row[0] for row in provider.execute("SELECT UPPER(provider_ticker) FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals' AND provider_ticker IS NOT NULL GROUP BY UPPER(provider_ticker)")}
        market_tickers = {row[0] for row in market.execute("SELECT UPPER(osake) FROM osakedata WHERE open>0 AND high>0 AND low>0 AND close>0 GROUP BY UPPER(osake)")}
        taxonomy_tickers = {row[0] for row in taxonomy.execute("SELECT UPPER(ticker) FROM ec_entity WHERE entity_type='TICKER' AND status='ACTIVE' AND ticker IS NOT NULL GROUP BY UPPER(ticker)")}
    provider_not_active = provider_tickers - active
    market_not_active = market_tickers - active
    local_provider_candidates = provider_not_active & market_tickers
    local_provider_with_taxonomy = local_provider_candidates & taxonomy_tickers
    archive_manifest = sorted(ARCHIVE_ROOT.glob("*/archive_manifest.json"))
    archive_zip = sorted(ARCHIVE_ROOT.glob("*/*.zip"))
    return [
        {"population": "provider_tickers_absent_from_operational_canonical", "count": len(provider_not_active), "sample": " ".join(sorted(provider_not_active)[:20])},
        {"population": "market_price_tickers_absent_from_operational_fundamentals", "count": len(market_not_active), "sample": " ".join(sorted(market_not_active)[:20])},
        {"population": "local_provider_candidates_with_market_ohlc", "count": len(local_provider_candidates), "sample": " ".join(sorted(local_provider_candidates)[:20])},
        {"population": "local_provider_candidates_with_market_and_taxonomy", "count": len(local_provider_with_taxonomy), "sample": " ".join(sorted(local_provider_with_taxonomy)[:20])},
        {"population": "local_archive_manifests", "count": len(archive_manifest), "sample": " ".join(str(path.relative_to(ROOT)) for path in archive_manifest[:5])},
        {"population": "local_archive_zip_files", "count": len(archive_zip), "sample": " ".join(str(path.relative_to(ROOT)) for path in archive_zip[:5])},
    ]


def rebuild_dependency_matrix() -> list[dict[str, Any]]:
    return [
        {"layer": "provider observations", "scope": "ticker/company scoped", "writes": "fundamentals_provider.db", "phase13b_policy": "append-only only; no destructive replacement"},
        {"layer": "canonical quarters", "scope": "ticker/company scoped but identity-sensitive", "writes": "fundamentals_v4.db", "phase13b_policy": "latest accepted ARQ per fiscal identity"},
        {"layer": "TTM", "scope": "ticker/company scoped after canonical", "writes": "fundamentals_v4.db", "phase13b_policy": "rebuild only affected company quarters if invariants prove isolated"},
        {"layer": "Fundamental Score V2", "scope": "ticker/company scoped", "writes": "fundamentals_analysis.db", "phase13b_policy": "replace rows under unchanged fingerprint for affected company"},
        {"layer": "Lifecycle V2", "scope": "ticker/company scoped", "writes": "fundamentals_analysis.db", "phase13b_policy": "depends on company revised history"},
        {"layer": "Absolute Valuation Score V2", "scope": "ticker/company scoped plus price freshness", "writes": "fundamentals_analysis.db", "phase13b_policy": "requires market-data eligibility"},
        {"layer": "Delta V2", "scope": "ticker/company scoped", "writes": "fundamentals_analysis.db", "phase13b_policy": "depends on score history comparability"},
        {"layer": "Relative Position V2", "scope": "full-universe scoped", "writes": "fundamentals_analysis.db", "phase13b_policy": "adding one company can change percentile/rank rows for existing companies"},
        {"layer": "Diagnostic Flags V2", "scope": "ticker/company scoped after package inputs", "writes": "fundamentals_analysis.db", "phase13b_policy": "eight rows per endpoint; statuses explicit"},
        {"layer": "Operating-Income V2 package", "scope": "full coherent package", "writes": "fundamentals_analysis.db", "phase13b_policy": "package fingerprint and active manifest must remain coherent"},
        {"layer": "Relative Valuation V1", "scope": "manual/deferred full-universe snapshot", "writes": "fundamentals_analysis.db", "phase13b_policy": "do not silently refresh during onboarding"},
        {"layer": "Company Snapshot V2", "scope": "ticker/company read/generate after upstream", "writes": "report artifact only on explicit snapshot generation", "phase13b_policy": "new company may show Relative Valuation unavailable until manual refresh"},
    ]


def database_write_and_rollback_matrix() -> list[dict[str, Any]]:
    return [
        {"case": "local_provider_complete", "databases_written": "canonical, analysis", "backup_required": "fundamentals_v4.db, fundamentals_analysis.db", "rollback_boundary": "restore every modified database from verified online backup"},
        {"case": "local_archive_import", "databases_written": "provider, canonical, analysis", "backup_required": "fundamentals_provider.db, fundamentals_v4.db, fundamentals_analysis.db", "rollback_boundary": "restore all three; provider append-only rows cannot be half-accepted"},
        {"case": "future_api_acquisition", "databases_written": "provider, canonical, analysis", "backup_required": "same as archive plus API provenance manifest", "rollback_boundary": "database restore; external API call cannot be undone"},
        {"case": "already_fully_present", "databases_written": "none", "backup_required": "none", "rollback_boundary": "NO_CHANGE with pre/post inventory reconciliation"},
        {"case": "partially_present", "databases_written": "depends on missing layer; normally canonical and/or analysis", "backup_required": "all databases that may change before first write", "rollback_boundary": "coherent batch succeeds or all modified DBs are restored"},
    ]


def production_preflight_postflight(paths: AuditPaths, before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "production_writes_performed": False,
        "external_requests_performed": False,
        "maintenance_lock_path": str(LOCK_PATH),
        "database_paths": database_paths_inventory(paths),
        "inventory_reconciliation": compare_production_inventory(before, after),
        "safe_connection": "SQLite URI mode=ro plus PRAGMA query_only=ON",
    }


def source_inventory(paths: AuditPaths) -> dict[str, Any]:
    files = [
        "rawcandle/fundamentals/schema/identity_calendar_bootstrap.py",
        "rawcandle/fundamentals/schema/production_bootstrap.py",
        "rawcandle/fundamentals/schema/phase12c_backfill.py",
        "rawcandle/fundamentals/providers/sharadar.py",
        "rawcandle/fundamentals/operating_income_v2/pipeline.py",
        "rawcandle/fundamentals/relative_position/production.py",
        "rawcandle/fundamentals/relative_valuation/production.py",
        "dev_tools/stock_update_scheduler_ui.py",
        "dev_tools/fundamentals_snapshot_page.py",
    ]
    rows = [
        {"path": item, "sha256": _file_sha256(ROOT / item), "size": (ROOT / item).stat().st_size}
        for item in files
        if (ROOT / item).exists()
    ]
    rows.extend(database_paths_inventory(paths))
    return {"rows": rows, "fingerprint": stable_hash(rows)}


def build_report(
    *,
    git: Mapping[str, Any],
    evidence: Mapping[str, Any],
    universe_inventory: Sequence[Mapping[str, Any]],
    discrepancies: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> str:
    provider_candidates = next((row for row in candidate_rows if row["population"] == "local_provider_candidates_with_market_ohlc"), {"count": 0})
    return f"""# Phase 13A Ticker-Onboarding Readiness Report

Selected outcome: **{CANONICAL_OUTCOME_LABEL}**.

## Executive finding

RawCandle has enough read-only evidence to define the Phase 13B backend contract, but it should not implement Add Tickers until an authoritative operational-universe registry exists. Current operational membership is effectively derived from canonical active securities and the historical bootstrap CSV/alias lineage; there is no durable production table that records explicit onboarding membership, status, effective dates, source/reason, aliases and versioned history.

## Repository and production state

- Branch: `{git["branch"]}` at `{git["head"]}`.
- Worktree at audit start: `{"clean" if not git["status_porcelain"] else "dirty"}`.
- Upstream ahead/behind at audit start: `{git["upstream_ahead"]}/{git["upstream_behind"]}`.
- Production database roles: provider, canonical, analysis, market and taxonomy under `data/`.
- Active Operating-Income V2 package: `{evidence["active_package"]["persistence_fingerprint"]}`.
- Active Relative Valuation snapshot rows: `{len(evidence["active_relative_valuation"])}`.

## Authoritative universe

The strongest current source is `canonical.security.active`, with {evidence["canonical"]["active_securities"]} active securities and {evidence["canonical"]["ttm_rows"]} TTM endpoint rows. The historical bootstrap alias source has {evidence["canonical"]["bootstrap_alias_tickers"]} distinct tickers. Because the original source lives under `temp/`, adding a ticker to only one source is not durable enough for later bootstraps or coherent rebuilds.

Recommended design: add a production `fundamentals_operational_universe` plus append-only history table keyed by stable company/security identity, storing current ticker, market, membership status, effective start, optional end date, source, reason, created/updated audit fields, alias evidence, deterministic ordering and universe fingerprint. Ticker aliases and ticker reuse must resolve through identity evidence, never through a plain ticker match.

## Identity resolution

Minimum evidence before adding: market ticker/market eligibility, canonical or newly established company/security identity, Sharadar persistent identity when available (`permaticker`), CIK when available, alias history, and taxonomy applicability. Plain ticker equality is only a routing hint. Current identity risk counters are in `identity_resolution_matrix.csv`.

Special cases must block or degrade explicitly: ticker changes, ticker reuse, multiple share classes, ADRs, funds/unsupported securities, stale or delisted securities, one ticker mapping to multiple identities, and an existing company submitted under an alias.

## Market, provider and archive eligibility

Market data must distinguish `FOUND_ELIGIBLE`, `FOUND_STALE`, `FOUND_MULTIPLE_MARKETS`, `FOUND_INSUFFICIENT` and `NOT_FOUND` using ticker/market match, positive OHLC rows, latest usable close, duplicate-key evidence and stale-price policy. No market backfill is part of onboarding.

Sharadar lookup order should be: current provider DB, managed ten-year local archive, then explicit future API acquisition. The current client supports a ticker parameter for `/data/fundamentals`, but Phase 13B still must verify endpoint behavior in a controlled acceptance path before production use. Repeatedly scanning the large ZIP is not operationally sensible; use an ignored deterministic local archive index/staging DB with source ZIP fingerprint and rebuild policy.

## Taxonomy and applicability

Missing or ambiguous taxonomy must not be inferred from ticker or company name. Company-scoped canonical, TTM, Score, Lifecycle, Absolute Valuation and Delta may be calculable when inputs exist, but peer-scoped Relative Position and Relative Valuation must be unavailable or `NOT_READY`/`NOT_APPLICABLE` until supported classification is present.

## Rebuild dependency

```text
provider -> canonical quarters -> TTM -> Score/Lifecycle/Valuation -> Delta
       -> Relative Position full-universe -> Diagnostic Flags -> active OI V2 package -> Snapshot
       -> Relative Valuation stays manual/deferred
```

Relative Position is full-universe scoped in the current production wrapper, and adding one company can change stored percentile/rank rows for existing companies. Relative Valuation remains a separate manual full-universe refresh; a new company may show Relative Valuation unavailable until that refresh.

## Quantitative evidence

- Canonical companies: {evidence["canonical"]["companies"]}; active securities: {evidence["canonical"]["active_securities"]}.
- Provider Sharadar observations: {evidence["provider"]["observations"]}; provider tickers: {evidence["provider"]["tickers"]}.
- Active Diagnostic evaluations: {evidence["downstream"]["diagnostic_evaluations_active_package"]}.
- Market tickers with valid OHLC: {evidence["market"]["tickers_with_ohlc"]}.
- Local provider candidates with market OHLC: {provider_candidates["count"]}.

## Phase 13B contract

Backend operations: parse/normalize, preview, optional explicit Sharadar acquisition authorization, apply, job status, final per-ticker results, reconciliation and retry/no-op. Preview is independent per ticker; valid tickers can be confirmed as a coherent atomic subset; repeated identical apply returns `NO_CHANGE`.

Required protections: preview before write, maintenance lock, writer-process checks, verified online backups for every writable database, independently openable backups, atomic transaction inside each SQLite database, restore all modified DBs on coherent-batch failure, postflight integrity/isolation checks, confirmation tokens, concurrent job protection, traversal/symlink protections and redacted public errors.

## Artifacts

See this run directory for CSV/JSON evidence and deterministic manifests. Production databases and reports were read with `mode=ro` connections only; no external request was made.
"""


def run(paths: AuditPaths) -> dict[str, Any]:
    paths.output.mkdir(parents=True, exist_ok=False)
    before = production_inventory()
    git = git_state()
    commands = [
        "git branch --show-current",
        "git rev-parse HEAD",
        "git status --porcelain",
        "sqlite3 -readonly data/fundamentals_v4.db .tables",
        "sqlite3 -readonly data/fundamentals_provider.db .tables",
        "sqlite3 -readonly data/fundamentals_analysis.db .tables",
        "python -m rawcandle.cli.run_phase13a_ticker_onboarding_audit --output <artifact-dir>",
    ]
    evidence = collect_quantitative_evidence(paths)
    universe_inventory, discrepancies = collect_universe_sources(paths)
    identity_rows = identity_resolution_matrix(paths)
    candidate_rows = candidate_coverage_summary(paths)
    dependency_rows = rebuild_dependency_matrix()
    rollback_rows = database_write_and_rollback_matrix()
    source_manifest = source_inventory(paths)
    decision = {
        "phase": PHASE,
        "outcome": CANONICAL_OUTCOME_LABEL,
        "outcome_code": OUTCOME_AUTHORITATIVE_UNIVERSE_REQUIRED,
        "principal_blocker": "No durable authoritative operational-universe registry separate from temp/bootstrap lineage.",
        "secondary_blockers": [
            "Ticker identity must require CIK/provider persistent identifier/alias evidence, not ticker equality.",
            "Archive scanning needs a deterministic ignored index or staging database before operational use.",
            "Relative Position requires coherent full-universe recalculation.",
        ],
        "relative_valuation_policy": "manual full-universe refresh only; onboarding must not silently refresh it",
        "source_manifest_fingerprint": source_manifest["fingerprint"],
    }
    write_csv(paths.output / "universe_source_inventory.csv", universe_inventory)
    write_csv(paths.output / "universe_discrepancies.csv", discrepancies)
    write_csv(paths.output / "identity_resolution_matrix.csv", identity_rows)
    write_csv(paths.output / "candidate_coverage_summary.csv", candidate_rows)
    write_csv(paths.output / "rebuild_dependency_matrix.csv", dependency_rows)
    write_csv(paths.output / "database_write_and_rollback_matrix.csv", rollback_rows)
    write_json(paths.output / "preview_status_contract.json", preview_status_contract())
    write_json(paths.output / "decision.json", decision)
    write_json(paths.output / "source_manifest.json", source_manifest)
    write_json(paths.output / "commands_executed.json", {"commands": commands, "secrets_omitted": True})
    write_json(paths.output / "quantitative_evidence.json", evidence)
    write_json(paths.output / "batch_parser_examples.json", {
        "input": "aapl, msft\nAAPL  brk.b",
        "result": normalize_ticker_batch("aapl, msft\nAAPL  brk.b"),
    })
    write_json(paths.output / "recommended_backend_contract.json", {
        "phase13b_backend_operations": [
            "parse_normalize",
            "preview",
            "authorize_optional_sharadar_acquisition",
            "apply_confirmed_subset",
            "job_status",
            "final_results",
            "reconcile",
            "retry_noop",
        ],
        "phase13c_ui_navigation": ["Snapshot Generation", "Add Tickers"],
        "public_status_contract": REQUIRED_STATUSES,
    })
    (paths.output / "recommended_phase13b_scope.md").write_text(_phase13b_scope_text(), encoding="utf-8")
    report = build_report(
        git=git,
        evidence=evidence,
        universe_inventory=universe_inventory,
        discrepancies=discrepancies,
        identity_rows=identity_rows,
        candidate_rows=candidate_rows,
    )
    (paths.output / "PHASE13A_TICKER_ONBOARDING_READINESS_REPORT.md").write_text(report, encoding="utf-8")
    after = production_inventory()
    prepost = production_preflight_postflight(paths, before, after)
    write_json(paths.output / "production_preflight_postflight.json", prepost)
    deterministic = {
        "artifact_files": sorted(path.name for path in paths.output.iterdir() if path.is_file()),
        "result_fingerprint": stable_hash({
            "decision": decision,
            "universe_inventory": universe_inventory,
            "discrepancies": discrepancies,
            "identity": identity_rows,
            "candidates": candidate_rows,
            "dependencies": dependency_rows,
            "rollback": rollback_rows,
            "evidence": evidence,
        }),
    }
    write_json(paths.output / "result_manifest.json", deterministic)
    return {
        "ok": True,
        "outcome": CANONICAL_OUTCOME_LABEL,
        "output": str(paths.output),
        "decision": decision,
        "production_unchanged": prepost["inventory_reconciliation"]["identical"],
        "result_fingerprint": deterministic["result_fingerprint"],
    }


def _phase13b_scope_text() -> str:
    return """# Recommended Phase 13B Scope

Implement only a backend/CLI contract for Add Tickers. Do not build Scheduler UI in 13B.

Required operations:

- `parse-normalize`: input text to stable unique ticker list, max 25.
- `preview`: read-only market, identity, provider/archive, taxonomy and dependency classification.
- `authorize-acquisition`: explicit user approval for any future Sharadar API call.
- `apply`: confirmed valid subset only, maintenance lock, writer checks, online backups, per-DB transactions and all-modified-DB rollback.
- `status`: durable job record with redacted public states.
- `reconcile`: postflight row counts, fingerprints and active-package coherence.
- `retry`: `NO_CHANGE` when durable state already matches the confirmed request.

Do not silently refresh Relative Valuation. Do not classify unknown taxonomy by ticker/name. Do not accept plain ticker match as permanent identity.
"""
