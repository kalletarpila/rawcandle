from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.schema.phase12c_backfill import sha256
from rawcandle.fundamentals.schema.prototype import stable_hash, write_csv, write_json
from rawcandle.research.phase12c1_audit import production_state

from .contract import CONTRACT, CONTRACT_FINGERPRINT, CONTRACT_VERSION, HORIZONS, MODEL_DATA_RISK
from .engine import (
    choose_latest,
    identity_status,
    label_feasibility,
    model_applicability,
    parse_cik,
    ranges_overlap,
    security_eligibility,
)


SOURCE_SHA256 = "dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36"
SOURCE_SIZE = 235876508
SOURCE_MEMBER = "fundamentals-10Y.csv"
MACHINE_ARTIFACTS = (
    "archive_manifest.json",
    "identity_source_inventory.csv",
    "candidate_identity_registry.csv",
    "identity_resolution_summary.csv",
    "identity_edge_case_sample.csv",
    "security_eligibility_summary.csv",
    "historical_coverage_by_year.csv",
    "price_identity_coverage.csv",
    "benchmark_coverage.csv",
    "forward_label_feasibility.csv",
    "terminal_event_status_summary.csv",
    "decision.json",
)


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def verify_archive(source: Path, archive: Path) -> dict[str, Any]:
    source_hash = sha256(source)
    archive_hash = sha256(archive)
    with zipfile.ZipFile(archive) as handle:
        member = handle.getinfo(SOURCE_MEMBER)
        bad_member = handle.testzip()
    result = {
        "source_path": str(source),
        "archive_path": str(archive),
        "source_size": source.stat().st_size,
        "archive_size": archive.stat().st_size,
        "source_sha256": source_hash,
        "archive_sha256": archive_hash,
        "expected_sha256": SOURCE_SHA256,
        "member": SOURCE_MEMBER,
        "member_size": member.file_size,
        "upstream_request_scope": "GET /data/fundamentals?years=10",
        "acquired_at_utc": "2026-09-10T13:32:21Z",
        "dimensions_present": ["ARQ", "ART", "ARY", "MRQ", "MRT", "MRY"],
        "history_semantics": "CURRENTLY_REVISED_NON_PIT_HISTORY",
        "retention_purpose": "PHASE12C3_HISTORICAL_RESEARCH_SOURCE",
        "verified": (
            source.stat().st_size == archive.stat().st_size == SOURCE_SIZE
            and source_hash == archive_hash == SOURCE_SHA256
            and bad_member is None
        ),
    }
    if not result["verified"]:
        raise RuntimeError("PHASE12C3_ARCHIVE_VERIFICATION_FAILED")
    return result


def load_metadata(provider_db: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    metadata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    actions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with readonly(provider_db) as connection:
        for row in connection.execute(
            "SELECT ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,"
            "secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated "
            "FROM sharadar_ticker_metadata WHERE table_name='fundamentals' ORDER BY ticker,permaticker"
        ):
            item = dict(row)
            item["cik"] = parse_cik(item.get("secfilings"))
            metadata[str(row["ticker"]).upper()].append(item)
        for row in connection.execute(
            "SELECT date,action,ticker,value,contraticker,contraname FROM sharadar_action_metadata "
            "ORDER BY ticker,date,action"
        ):
            actions[str(row["ticker"]).upper()].append(dict(row))
    return dict(metadata), dict(actions)


def load_canonical(canonical_db: Path) -> tuple[set[str], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    securities: dict[str, dict[str, Any]] = {}
    aliases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with readonly(canonical_db) as connection:
        operational = {str(row[0]).upper() for row in connection.execute("SELECT current_ticker FROM security")}
        for row in connection.execute(
            "SELECT s.current_ticker,s.security_id,s.company_id,s.active,s.valid_from,s.valid_to,"
            "psi.provider_security_id,cc.cik_normalized FROM security s "
            "LEFT JOIN provider_security_identity psi ON psi.security_id=s.security_id AND psi.provider='SHARADAR' "
            "LEFT JOIN company_cik cc ON cc.company_id=s.company_id ORDER BY s.current_ticker"
        ):
            securities[str(row["current_ticker"]).upper()] = dict(row)
        for row in connection.execute(
            "SELECT a.ticker,a.valid_from,a.valid_to,a.provider,a.source,s.current_ticker,s.security_id "
            "FROM ticker_alias a JOIN security s USING(security_id) ORDER BY a.ticker,a.valid_from,a.security_id"
        ):
            aliases[str(row["ticker"]).upper()].append(dict(row))
    return operational, securities, dict(aliases)


def load_market_context(market_db: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str], set[str]]:
    coverage: dict[str, dict[str, Any]] = {}
    context: dict[str, dict[str, Any]] = {}
    with readonly(market_db) as connection:
        for row in connection.execute(
            "SELECT osake,COUNT(DISTINCT market) markets,MIN(pvm) first_date,MAX(pvm) last_date,"
            "COUNT(*) rows FROM osakedata GROUP BY osake ORDER BY osake"
        ):
            coverage[str(row["osake"]).upper()] = dict(row)
        for row in connection.execute("SELECT ticker,market,sector,industry FROM ticker_meta ORDER BY ticker"):
            context[str(row["ticker"]).upper()] = dict(row)
        spy = [str(row[0]) for row in connection.execute(
            "SELECT pvm FROM osakedata WHERE osake='SPY' AND market='usa' AND close>0 ORDER BY pvm"
        )]
        qqq = {str(row[0]) for row in connection.execute(
            "SELECT pvm FROM osakedata WHERE osake='QQQ' AND market='usa' AND close>0 ORDER BY pvm"
        )}
    return coverage, context, spy, qqq


def scan_source(archive: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, str]]], Counter]:
    candidates: dict[str, dict[str, Any]] = {}
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    dimensions = Counter()
    with zipfile.ZipFile(archive) as zipped, zipped.open(SOURCE_MEMBER) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            for row in csv.DictReader(text):
                dimension = str(row.get("dimension") or "").upper()
                dimensions[dimension] += 1
                if dimension != "ARQ":
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                period = str(row.get("calendardate") or row.get("reportperiod") or "")
                available = str(row.get("date") or "")
                item = candidates.setdefault(ticker, {
                    "ticker": ticker, "dimension": "ARQ", "provider_rows": 0,
                    "first_fundamental_period": period, "last_fundamental_period": period,
                    "first_availability_date": available or None,
                    "last_availability_date": available or None,
                })
                item["provider_rows"] += 1
                item["first_fundamental_period"] = min(item["first_fundamental_period"], period)
                item["last_fundamental_period"] = max(item["last_fundamental_period"], period)
                if available:
                    item["first_availability_date"] = min(item["first_availability_date"] or available, available)
                    item["last_availability_date"] = max(item["last_availability_date"] or available, available)
                key = (ticker, str(row.get("reportperiod") or ""), str(row.get("fiscalperiod") or ""))
                if choose_latest(latest.get(key), row):
                    latest[key] = dict(row)
    endpoints: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (ticker, _, _), row in sorted(latest.items()):
        endpoints[ticker].append(row)
    for ticker, item in candidates.items():
        item["logical_endpoints"] = len(endpoints[ticker])
        item["revision_rows"] = item["provider_rows"] - item["logical_endpoints"]
    return candidates, dict(endpoints), dimensions


def _terminal_status(item: Mapping[str, Any], action_rows: list[dict[str, Any]]) -> str:
    if not item.get("ohlc_first_date"):
        return "NO_LOCAL_MARKET_HISTORY"
    if item.get("provider_isdelisted") != "Y":
        return "ACTIVE_OR_NOT_PROVIDER_DELISTED"
    action_names = {str(row.get("action") or "").lower() for row in action_rows}
    if "bankruptcy" in " ".join(action_names):
        return "BANKRUPTCY_EVENT_NO_TERMINAL_VALUE"
    if any("acquisition" in action for action in action_names):
        return "ACQUISITION_EVENT_NO_CONSIDERATION_VALUE"
    if any("delist" in action for action in action_names):
        return "DELISTING_EVENT_NO_TERMINAL_VALUE"
    return "TERMINAL_EVENT_METADATA_REQUIRED"


def build_registry(
    candidates: dict[str, dict[str, Any]], metadata: Mapping[str, list[dict[str, Any]]],
    actions: Mapping[str, list[dict[str, Any]]], operational: set[str],
    securities: Mapping[str, dict[str, Any]], aliases: Mapping[str, list[dict[str, Any]]],
    market: Mapping[str, dict[str, Any]], context: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for ticker, source in sorted(candidates.items()):
        identity_rows = metadata.get(ticker, [])
        meta = identity_rows[0] if len(identity_rows) == 1 else {}
        prices = market.get(ticker, {})
        overlap = ranges_overlap(
            source.get("first_availability_date"), source.get("last_availability_date"),
            prices.get("first_date"), prices.get("last_date"),
        )
        identity = identity_status(
            metadata_count=len(identity_rows), permaticker=meta.get("permaticker"),
            first_fundamental=source.get("first_fundamental_period"),
            last_fundamental=source.get("last_fundamental_period"),
            metadata_first_quarter=meta.get("firstquarter"),
            metadata_last_quarter=meta.get("lastquarter"),
            market_count=int(prices.get("markets") or 0),
        )
        market_status = (
            "MARKET_IDENTITY_AMBIGUOUS" if int(prices.get("markets") or 0) > 1
            else "EXACT_TICKER_DATE_OVERLAP_CANDIDATE" if overlap
            else "IDENTITY_NO_MARKET_MATCH" if not prices
            else "MARKET_HISTORY_NO_DATE_OVERLAP"
        )
        current_context = context.get(ticker, {})
        canonical = securities.get(ticker, {})
        alias_rows = aliases.get(ticker, [])
        row = {
            **source,
            "permaticker": meta.get("permaticker"), "possible_cik": meta.get("cik"),
            "provider_name": meta.get("name"), "provider_exchange": meta.get("exchange"),
            "provider_category": meta.get("category"), "provider_isdelisted": meta.get("isdelisted"),
            "provider_first_price_date": meta.get("firstpricedate"),
            "provider_last_price_date": meta.get("lastpricedate"),
            "metadata_rows": len(identity_rows), "identity_resolution_status": identity,
            "canonical_security_id": canonical.get("security_id"),
            "canonical_company_id": canonical.get("company_id"),
            "canonical_cik": canonical.get("cik_normalized"),
            "dated_alias_rows": sum(bool(str(a.get("valid_from") or "").strip()) for a in alias_rows),
            "ohlc_markets": int(prices.get("markets") or 0),
            "ohlc_first_date": prices.get("first_date"), "ohlc_last_date": prices.get("last_date"),
            "fundamental_price_date_overlap": overlap, "market_link_status": market_status,
            "operational_universe_member": ticker in operational,
            "universe_classification": "OPERATIONAL" if ticker in operational else "HISTORICAL_ONLY",
            "security_eligibility_status": security_eligibility(meta.get("category")),
            "fundamental_model_applicability": model_applicability(current_context.get("sector")),
            "current_sector_context_non_pit": current_context.get("sector"),
            "current_industry_context_non_pit": current_context.get("industry"),
            "return_label_eligibility": "RETURN_LABEL_CANDIDATE" if overlap else "RETURN_LABEL_NOT_LINKED",
        }
        row["terminal_event_status"] = _terminal_status(row, actions.get(ticker, []))
        rows.append(row)
    return rows


def evaluate_labels(
    *, market_db: Path, endpoints: Mapping[str, list[dict[str, str]]], registry: list[dict[str, Any]],
    spy: list[str], qqq: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry_by_ticker = {row["ticker"]: row for row in registry}
    coverage = Counter()
    yearly: dict[tuple[str, str], Counter] = defaultdict(Counter)
    with readonly(market_db) as connection:
        for ticker in sorted(endpoints):
            registry_row = registry_by_ticker[ticker]
            company_sessions = {
                str(row[0]) for row in connection.execute(
                    "SELECT pvm FROM osakedata INDEXED BY idx_osake_pvm "
                    "WHERE osake=? AND market='usa' AND close>0 ORDER BY pvm", (ticker,)
                )
            } if registry_row["fundamental_price_date_overlap"] else set()
            for endpoint in endpoints[ticker]:
                available = str(endpoint.get("date") or "") or None
                year = (available or str(endpoint.get("calendardate") or ""))[:4]
                period = (
                    "TRAINING_2020_2023" if "2020" <= year <= "2023" else
                    "VALIDATION_2024" if year == "2024" else
                    "RETROSPECTIVE_2025" if year == "2025" else
                    "REPORT_ONLY_2026" if year == "2026" else "OTHER"
                )
                scope = registry_row["universe_classification"]
                yearly[(year, scope)]["endpoints"] += 1
                yearly[(year, scope)]["tickers_marker"] = 0
                yearly[(year, scope)][f"identity_{str(registry_row['identity_resolution_status']).lower()}"] += 1
                yearly[(year, scope)][f"security_{str(registry_row['security_eligibility_status']).lower()}"] += 1
                yearly[(year, scope)][f"market_{str(registry_row['market_link_status']).lower()}"] += 1
                yearly[(year, scope)][f"terminal_{str(registry_row['terminal_event_status']).lower()}"] += 1
                coverage[(scope, "endpoints")] += 1
                coverage[(period, "endpoints")] += 1
                for horizon in HORIZONS:
                    result = label_feasibility(
                        availability_date=available, horizon=horizon,
                        benchmark_sessions=spy, qqq_sessions=qqq,
                        company_sessions=company_sessions,
                    ) if company_sessions else None
                    status = result.status if result else (
                        "IDENTITY_OR_MARKET_NOT_LINKED" if available else "MISSING_AVAILABILITY_DATE"
                    )
                    coverage[(scope, horizon, status)] += 1
                    coverage[(period, horizon, status)] += 1
                    yearly[(year, scope)][f"h{horizon}_{status}"] += 1
                    if result and result.qqq_aligned and status == "LABEL_FEASIBLE":
                        coverage[(scope, horizon, "QQQ_ALIGNED_LABEL_FEASIBLE")] += 1
                        coverage[(period, horizon, "QQQ_ALIGNED_LABEL_FEASIBLE")] += 1
                        yearly[(year, scope)][f"h{horizon}_qqq_aligned"] += 1
    ticker_sets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ticker, rows in endpoints.items():
        scope = registry_by_ticker[ticker]["universe_classification"]
        for endpoint in rows:
            year = (str(endpoint.get("date") or endpoint.get("calendardate") or ""))[:4]
            ticker_sets[(year, scope)].add(ticker)
    years = sorted({year for year, _ in yearly})
    for year in years:
        yearly[(year, "GLOBAL")] = yearly[(year, "OPERATIONAL")] + yearly[(year, "HISTORICAL_ONLY")]
        ticker_sets[(year, "GLOBAL")] = ticker_sets[(year, "OPERATIONAL")] | ticker_sets[(year, "HISTORICAL_ONLY")]
    yearly_rows = []
    for (year, scope), values in sorted(yearly.items()):
        row = {"year": year, "scope": scope, "endpoints": values["endpoints"], "tickers": len(ticker_sets[(year, scope)])}
        row.update({
            "identity_exact_dated_endpoints": values["identity_identity_exact_dated"],
            "identity_metadata_required_endpoints": values["identity_identity_metadata_required"],
            "security_eligible_endpoints": values["security_research_security_eligible"],
            "security_metadata_required_endpoints": values["security_security_type_metadata_required"],
            "direct_ohlc_overlap_endpoints": values["market_exact_ticker_date_overlap_candidate"],
            "no_market_match_endpoints": values["market_identity_no_market_match"],
            "terminal_metadata_required_endpoints": values["terminal_terminal_event_metadata_required"],
        })
        for horizon in HORIZONS:
            row[f"h{horizon}_label_feasible"] = values[f"h{horizon}_LABEL_FEASIBLE"]
            row[f"h{horizon}_qqq_aligned"] = values[f"h{horizon}_qqq_aligned"]
            row[f"h{horizon}_right_censored"] = values[f"h{horizon}_RIGHT_CENSORED_UNRESOLVED_TERMINAL"]
        yearly_rows.append(row)
    feasibility = []
    for scope in ("ALL", "OPERATIONAL", "HISTORICAL_ONLY", "TRAINING_2020_2023", "VALIDATION_2024", "RETROSPECTIVE_2025", "REPORT_ONLY_2026"):
        members = ("OPERATIONAL", "HISTORICAL_ONLY") if scope == "ALL" else (scope,)
        denominator = sum(coverage[(member, "endpoints")] for member in members)
        for horizon in HORIZONS:
            ready = sum(coverage[(member, horizon, "LABEL_FEASIBLE")] for member in members)
            qqq_ready = sum(coverage[(member, horizon, "QQQ_ALIGNED_LABEL_FEASIBLE")] for member in members)
            censored = sum(coverage[(member, horizon, "RIGHT_CENSORED_UNRESOLVED_TERMINAL")] for member in members)
            feasibility.append({
                "scope": scope, "horizon_sessions": horizon, "endpoints": denominator,
                "label_feasible": ready, "label_feasible_pct": round(100 * ready / denominator, 6) if denominator else 0,
                "qqq_aligned_feasible": qqq_ready, "right_censored": censored,
                "price_return_semantics": "SPLIT_ADJUSTED_PRICE_RETURN_DIVIDENDS_EXCLUDED",
            })
    return yearly_rows, feasibility


def _summary_rows(registry: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts = Counter((row["universe_classification"], str(row.get(field))) for row in registry)
    return [
        {"scope": scope, "status": status, "tickers": count}
        for (scope, status), count in sorted(counts.items())
    ]


def _identity_sources(
    *, registry: list[dict[str, Any]], metadata_count: int, action_count: int,
    operational_count: int, market_count: int,
) -> list[dict[str, Any]]:
    return [
        {"source": "Phase12C fundamentals ZIP", "identifier": "ticker", "stable": "NO", "effective_dates": "period and availability", "security_type": "NO", "terminal_events": "NO", "coverage": len(registry), "role": "AUTHORITATIVE_FINANCIAL_SOURCE"},
        {"source": "sharadar_ticker_metadata", "identifier": "permaticker,ticker,CIK URL", "stable": "PERMATICKER/CIK", "effective_dates": "first/last price and quarter", "security_type": "category", "terminal_events": "current isdelisted only", "coverage": metadata_count, "role": "AUTHORITATIVE_PROVIDER_IDENTITY_CANDIDATE"},
        {"source": "sharadar_action_metadata", "identifier": "ticker", "stable": "NO", "effective_dates": "action date", "security_type": "NO", "terminal_events": "partial recent actions", "coverage": action_count, "role": "SUPPORTING_INCOMPLETE"},
        {"source": "canonical identity", "identifier": "company_id,security_id,CIK,permaticker", "stable": "YES", "effective_dates": "aliases mostly undated", "security_type": "NO", "terminal_events": "NO", "coverage": operational_count, "role": "AUTHORITATIVE_OPERATIONAL_ONLY"},
        {"source": "osakedata", "identifier": "ticker,market", "stable": "NO", "effective_dates": "daily 2018 onward", "security_type": "current sector context", "terminal_events": "NO", "coverage": market_count, "role": "AUTHORITATIVE_LOCAL_PRICE_SUPPORTING_IDENTITY"},
        {"source": "splits_data", "identifier": "ticker,split_date", "stable": "NO", "effective_dates": "YES", "security_type": "NO", "terminal_events": "NO", "coverage": 6344, "role": "SUPPORTING_SPLIT_EVIDENCE"},
        {"source": "current taxonomy", "identifier": "ticker", "stable": "NO", "effective_dates": "NO", "security_type": "current descriptive only", "terminal_events": "NO", "coverage": None, "role": "NOT_HISTORICAL_PIT_TRUTH"},
    ]


def _write_docs(output: Path, registry: list[dict[str, Any]], feasibility: list[dict[str, Any]], decisions: Mapping[str, Any]) -> None:
    counts = Counter(row["universe_classification"] for row in registry)
    identities = Counter(row["identity_resolution_status"] for row in registry)
    market = Counter(row["market_link_status"] for row in registry)
    cik_count = sum(bool(row.get("possible_cik")) for row in registry)
    category_count = sum(bool(row.get("provider_category")) for row in registry)
    historical_ohlc = sum(
        row["universe_classification"] == "HISTORICAL_ONLY" and row["fundamental_price_date_overlap"]
        for row in registry
    )
    lines = [
        "# Phase 12C.3 Historical Research Universe Report", "",
        f"Contract: `{CONTRACT_VERSION}` / `{CONTRACT_FINGERPRINT}`.", "",
        f"Risk: `{MODEL_DATA_RISK}`. This is screening research, not a buy/sell model.", "",
        "## Reconciliation", "",
        f"Global ARQ tickers: {len(registry):,}. Current source/operational intersection: {counts['OPERATIONAL']:,}. Historical-only: {counts['HISTORICAL_ONLY']:,}. Append-only production retains {decisions['production_provider_tickers']:,} tickers, including {decisions['production_only_retained_tickers']:,} absent from this source snapshot.", "",
        f"Identity statuses: `{dict(sorted(identities.items()))}`.", "",
        f"Provider CIK evidence: {cik_count:,}/{len(registry):,}. Security-category evidence: {category_count:,}/{len(registry):,}.", "",
        f"Market-link statuses: `{dict(sorted(market.items()))}`.", "",
        "## Decisions", "",
        f"Operational track: `{decisions['operational_track']}`.", "",
        f"Broad research track: `{decisions['broad_research_track']}`.", "",
        "Broad implementation requires dated listing/issuer episodes, authoritative historical security/accounting classifications, pre-2018 and delisted price coverage, and terminal-event consideration or liquidation values.", "",
        "Current taxonomy is descriptive only. Ticker-only OHLC overlap is not represented as a permanent identity. Returns would be split-adjusted price returns with dividends excluded.", "",
        "## Horizon feasibility", "",
        "| Scope | Horizon | Endpoints | Feasible | Feasible % | QQQ aligned | Right-censored |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in feasibility:
        lines.append(f"| {row['scope']} | {row['horizon_sessions']} | {row['endpoints']:,} | {row['label_feasible']:,} | {row['label_feasible_pct']:.2f}% | {row['qqq_aligned_feasible']:,} | {row['right_censored']:,} |")
    (output / "PHASE12C3_HISTORICAL_RESEARCH_UNIVERSE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "research_universe_contract.md").write_text(
        "# Proposed historical research universe contract\n\n```json\n" + json.dumps(CONTRACT, indent=2, sort_keys=True) + "\n```\n",
        encoding="utf-8",
    )
    (output / "survivorship_bias_assessment.md").write_text(
        f"# Survivorship bias assessment\n\nThe operational universe covers {counts['OPERATIONAL']:,} of {len(registry):,} global ARQ tickers; {counts['HISTORICAL_ONLY']:,} ({100*counts['HISTORICAL_ONLY']/len(registry):.2f}%) are historical-only. The upper feasibility bound is therefore {counts['HISTORICAL_ONLY']:,} additional identities. The lower directly price-linkable bound is {historical_ohlc:,} historical-only tickers with local date-overlapping OHLC. These are coverage bounds, not point estimates of return bias. Exact bias remains unknown until dated identities, security eligibility, delisting prices and terminal returns are authoritative.\n",
        encoding="utf-8",
    )
    (output / "storage_and_architecture_options.md").write_text(
        "# Storage and architecture\n\nRecommend a separate ignored SQLite database at `data/research/historical_fundamentals_research.db`. Keep source manifests and versioned contracts in tracked documentation, but keep row-level registries and source snapshots out of Git. Expected initial storage is roughly 1-2 GB for normalized global fundamentals, identity episodes, label evidence and indexes; allow 3-5 GB working headroom for rebuilds. Do not add these tables to production provider, canonical, analysis or Snapshot readers.\n",
        encoding="utf-8",
    )
    (output / "recommended_phase12d_scope.md").write_text(
        "# Recommended Phase 12D scope\n\nFor the unchanged operational universe only: canonicalize the already imported extended provider history, rebuild TTM and downstream revised-history results, preserve current readers/Snapshot behavior, and rerun the locked Phase 12B with an explicit current-universe survivorship limitation. Require backups, production gates and deterministic replay.\n",
        encoding="utf-8",
    )
    (output / "recommended_broad_research_implementation_scope.md").write_text(
        "# Recommended broad-research implementation scope\n\nAcquire the smallest authoritative metadata package covering dated permaticker/CIK/listing/ticker intervals, security type, exchange transfers, inactive/delisted status, merger consideration, bankruptcy/liquidation outcomes, OTC continuations, historical accounting classification, and split-adjusted prices including delisted securities before 2018. Then implement a separate research database and explicit security episodes. Do not change the operational universe.\n",
        encoding="utf-8",
    )


def run_once(paths: Mapping[str, Path], output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    archive_manifest = verify_archive(paths["source_zip"], paths["archive_zip"])
    metadata, actions = load_metadata(paths["provider_db"])
    operational, securities, aliases = load_canonical(paths["canonical_db"])
    market, context, spy, qqq = load_market_context(paths["market_db"])
    candidates, endpoints, dimensions = scan_source(paths["archive_zip"])
    registry = build_registry(candidates, metadata, actions, operational, securities, aliases, market, context)
    yearly, feasibility = evaluate_labels(
        market_db=paths["market_db"], endpoints=endpoints, registry=registry, spy=spy, qqq=qqq,
    )
    counts = Counter(row["universe_classification"] for row in registry)
    logical_endpoints = sum(int(row["logical_endpoints"]) for row in registry)
    provider_rows = sum(int(row["provider_rows"]) for row in registry)
    with readonly(paths["provider_db"]) as connection:
        production_provider_tickers = int(connection.execute(
            "SELECT COUNT(DISTINCT provider_ticker) FROM provider_observation "
            "WHERE provider='SHARADAR' AND native_table='fundamentals' AND dimension='ARQ'"
        ).fetchone()[0])
    if provider_rows != 227460 or len(registry) != 9017 or counts["OPERATIONAL"] != 2449 or counts["HISTORICAL_ONLY"] != 6568:
        raise RuntimeError("PHASE12C3_UNIVERSE_RECONCILIATION_FAILED")
    decisions = {
        "operational_track": "OPERATIONAL_PHASE12D_READY",
        "broad_research_track": "BROAD_RESEARCH_METADATA_ACQUISITION_REQUIRED",
        "phase12d_authorized_by_this_phase": False,
        "contract_version": CONTRACT_VERSION,
        "contract_fingerprint": CONTRACT_FINGERPRINT,
        "model_data_risk": MODEL_DATA_RISK,
        "global_arq_provider_rows": provider_rows,
        "global_arq_logical_endpoints": logical_endpoints,
        "global_arq_tickers": len(registry),
        "source_operational_tickers": counts["OPERATIONAL"],
        "production_provider_tickers": production_provider_tickers,
        "production_only_retained_tickers": production_provider_tickers - counts["OPERATIONAL"],
        "historical_only_tickers": counts["HISTORICAL_ONLY"],
    }
    identity_summary = _summary_rows(registry, "identity_resolution_status")
    security_summary = _summary_rows(registry, "security_eligibility_status") + _summary_rows(registry, "fundamental_model_applicability")
    price_rows = [{key: row.get(key) for key in (
        "ticker", "universe_classification", "identity_resolution_status", "market_link_status",
        "ohlc_first_date", "ohlc_last_date", "fundamental_price_date_overlap",
        "return_label_eligibility", "provider_isdelisted", "terminal_event_status",
    )} for row in registry]
    samples = []
    sample_counts = Counter()
    for row in registry:
        key = (row["identity_resolution_status"], row["market_link_status"], row["terminal_event_status"])
        if sample_counts[key] < 3:
            samples.append({k: row.get(k) for k in (
                "ticker", "universe_classification", "permaticker", "possible_cik",
                "identity_resolution_status", "market_link_status", "security_eligibility_status",
                "terminal_event_status", "first_fundamental_period", "last_fundamental_period",
                "ohlc_first_date", "ohlc_last_date",
            )})
            sample_counts[key] += 1
    terminal = _summary_rows(registry, "terminal_event_status")
    benchmark = [
        {"ticker": "SPY", "first_date": spy[0], "last_date": spy[-1], "sessions": len(spy), "role": "GENERAL_MARKET_CONTROL"},
        {"ticker": "QQQ", "first_date": min(qqq), "last_date": max(qqq), "sessions": len(qqq), "role": "GROWTH_TECHNOLOGY_CONTROL"},
    ]
    write_json(output / "archive_manifest.json", archive_manifest)
    write_csv(output / "identity_source_inventory.csv", _identity_sources(
        registry=registry, metadata_count=len(metadata), action_count=sum(map(len, actions.values())),
        operational_count=len(operational), market_count=len(market),
    ))
    write_csv(output / "candidate_identity_registry.csv", registry)
    write_csv(output / "identity_resolution_summary.csv", identity_summary)
    write_csv(output / "identity_edge_case_sample.csv", samples)
    write_csv(output / "security_eligibility_summary.csv", security_summary)
    write_csv(output / "historical_coverage_by_year.csv", yearly)
    write_csv(output / "price_identity_coverage.csv", price_rows)
    write_csv(output / "benchmark_coverage.csv", benchmark)
    write_csv(output / "forward_label_feasibility.csv", feasibility)
    write_csv(output / "terminal_event_status_summary.csv", terminal)
    write_json(output / "decision.json", decisions)
    _write_docs(output, registry, feasibility, decisions)
    return {**decisions, "dimensions": dict(sorted(dimensions.items())), "registry_fingerprint": stable_hash(registry)}


def protected_state(repo_root: Path) -> dict[str, Any]:
    state = production_state(repo_root)
    reports_root = repo_root / "fundamental_reports"
    state["report_inventory"] = {
        str(path.relative_to(reports_root)): sha256(path)
        for path in sorted(reports_root.rglob("*")) if path.is_file()
    }
    return state


def run_dual(paths: Mapping[str, Path], output: Path, preflight_path: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    first = run_once(paths, output / "run1")
    second = run_once(paths, output / "run2")
    comparisons = {}
    for name in MACHINE_ARTIFACTS:
        comparisons[name] = sha256(output / "run1" / name) == sha256(output / "run2" / name)
        shutil.copy2(output / "run1" / name, output / name)
    for name in (
        "PHASE12C3_HISTORICAL_RESEARCH_UNIVERSE_REPORT.md", "research_universe_contract.md",
        "survivorship_bias_assessment.md", "storage_and_architecture_options.md",
        "recommended_phase12d_scope.md", "recommended_broad_research_implementation_scope.md",
    ):
        shutil.copy2(output / "run1" / name, output / name)
    if first != second or not all(comparisons.values()):
        raise RuntimeError("PHASE12C3_DUAL_RUN_NOT_DETERMINISTIC")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    postflight = protected_state(paths["repo_root"])
    databases_unchanged = preflight["databases"] == postflight["databases"]
    pointers_unchanged = (
        preflight["active_operating_income_v2_package"] == postflight["active_operating_income_v2_package"]
        and preflight["active_relative_valuation_snapshot"] == postflight["active_relative_valuation_snapshot"]
    )
    pre_reports = preflight.get("report_inventory", {})
    post_reports = postflight["report_inventory"]
    existing_reports_unchanged = all(post_reports.get(path) == digest for path, digest in pre_reports.items())
    added_reports = sorted(set(post_reports) - set(pre_reports))
    removed_reports = sorted(set(pre_reports) - set(post_reports))
    protected_immutable = databases_unchanged and pointers_unchanged and existing_reports_unchanged
    write_json(output / "production_preflight_postflight.json", {
        "preflight_source": str(preflight_path), "preflight": preflight,
        "postflight": postflight,
        "databases_unchanged": databases_unchanged,
        "active_pointers_unchanged": pointers_unchanged,
        "existing_reports_unchanged": existing_reports_unchanged,
        "report_set_fingerprint_unchanged": preflight["reports_fingerprint"] == postflight["reports_fingerprint"],
        "externally_added_reports_during_run": added_reports,
        "removed_reports": removed_reports,
        "protected_baseline_immutable": protected_immutable,
    })
    write_json(output / "determinism.json", {
        "run_results_equal": first == second, "machine_artifacts": comparisons,
        "result_fingerprint": stable_hash(first),
    })
    final = {
        **first, "production_immutable": protected_immutable, "deterministic": True,
        "existing_reports_unchanged": existing_reports_unchanged,
        "external_report_additions_observed": len(added_reports), "output": str(output),
    }
    write_json(output / "decision.json", final)
    (output / "commands_run.txt").write_text(
        "\n".join((
            "cp --reflink=auto --preserve=timestamps <verified-source-zip> <ignored-archive-zip>",
            "cmp -s <verified-source-zip> <ignored-archive-zip>",
            "sha256sum <verified-source-zip> <ignored-archive-zip>",
            "unzip -t <ignored-archive-zip>",
            "python3 -m rawcandle.cli.run_phase12c3_historical_universe_audit --output <temp-output> --preflight <temp-preflight>",
            "pytest -q tests/test_phase12b_research_contract.py tests/test_phase12b_fundamental_profile_baseline.py tests/test_phase12c_sharadar_backfill.py tests/test_phase12c1_retention_universe_audit.py tests/test_phase12c2_sharadar_history_policy.py tests/test_phase12c3_historical_universe.py tests/test_production_database_isolation.py",
            "python3 -m compileall -q rawcandle tests",
            "git diff --check",
            "No credentials loaded; no network command or production writer executed.",
        )) + "\n", encoding="utf-8",
    )
    if not protected_immutable:
        raise RuntimeError("PHASE12C3_PROTECTED_BASELINE_CHANGED")
    return final
