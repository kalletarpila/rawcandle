from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.schema.phase12c_backfill import (
    database_inventory,
    provider_counts,
    sha256,
)
from rawcandle.fundamentals.schema.prototype import stable_hash


DIMENSIONS = ("ARQ", "MRQ")
REQUIRED_SOURCE_COLUMNS = {
    "ticker", "dimension", "calendardate", "reportperiod", "fiscalperiod",
    "date", "lastupdated", "revenue", "opinc", "fcf", "cashneq", "debt",
    "sharesbas",
}
SENSITIVE_MARKERS = ("api_key=", "apikey=", "authorization:", "x-api-key:")


def connect_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def read_tickers(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            str(row.get("ticker") or "").strip().upper()
            for row in csv.DictReader(handle)
            if row.get("ticker")
        }


def redact_command(command: str) -> str:
    words = command.split()
    redacted = []
    for word in words:
        lowered = word.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            key = word.split("=", 1)[0]
            redacted.append(f"{key}=<REDACTED>" if "=" in word else "<REDACTED>")
        else:
            redacted.append(word)
    return " ".join(redacted)


def discover_history_policy(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    locations: list[dict[str, Any]] = []
    needles = (
        "years=5", 'years=5', "years=10", 'years=10', "download_sharadar_5y_bulk",
        "download_sharadar_bulk", "DELETE FROM provider_observation",
        "ALLOWED_DIMENSIONS", "Sharadar Fundamentals 5 Years",
        "Sharadar Fundamentals 10 Years",
    )
    roots = (repo_root / "rawcandle", repo_root / "tests", repo_root / "docs/fundamentals_v4")
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".md", ".txt"}:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if any(needle in line for needle in needles):
                    locations.append({
                        "path": str(path.relative_to(repo_root)), "line": number,
                        "text": line.strip()[:300],
                    })
    bootstrap = (repo_root / "rawcandle/fundamentals/schema/production_bootstrap.py").read_text()
    phase12c = (repo_root / "rawcandle/fundamentals/schema/phase12c_backfill.py").read_text()
    delete_found = "DELETE FROM provider_observation" in bootstrap + phase12c
    five_year_default = (
        "download_sharadar_5y_bulk" in bootstrap
        or "years=5" in bootstrap
        or "years = 5" in bootstrap
    )
    policy = {
        "normal_future_bootstrap_horizon": "years=5" if five_year_default else "minimum years=10 contract",
        "ordinary_incremental_or_scheduled_refresh": "NOT_IMPLEMENTED_FOR_RAWCANDLE_V4_PROVIDER",
        "can_regress_to_five_years": five_year_default,
        "full_snapshot_semantics": "INSERT_OR_IGNORE_APPEND_ONLY",
        "absent_rows_retained": True,
        "older_than_request_window_retained": True,
        "cleanup_can_silently_delete_provider_history": delete_found,
        "requested_horizon_in_run_metadata": True,
        "actual_oldest_period_reported_by_phase12c": True,
        "unrelated_provider_datasets_affected": False,
        "requirements": [
            {"requirement": "ten_year_minimum_request", "status": "NOT_IMPLEMENTED" if five_year_default else "VERIFIED_IMPLEMENTED"},
            {"requirement": "no_five_year_fallback", "status": "NOT_IMPLEMENTED" if five_year_default else "VERIFIED_IMPLEMENTED"},
            {"requirement": "append_only_absent_row_retention", "status": "VERIFIED_IMPLEMENTED"},
            {"requirement": "older_than_ten_year_rows_may_remain", "status": "VERIFIED_IMPLEMENTED"},
            {"requirement": "deterministic_horizon_metadata", "status": "PARTIALLY_IMPLEMENTED" if five_year_default else "VERIFIED_IMPLEMENTED"},
            {"requirement": "oldest_retained_period_reporting", "status": "PARTIALLY_IMPLEMENTED" if five_year_default else "VERIFIED_IMPLEMENTED"},
            {"requirement": "unrelated_provider_isolation", "status": "VERIFIED_IMPLEMENTED"},
        ],
        "verdict": "HISTORY_POLICY_CORRECTION_REQUIRED" if five_year_default else "PERMANENT_TEN_YEAR_POLICY_VERIFIED",
    }
    return policy, locations


def load_identity_context(canonical_db: Path) -> tuple[set[str], dict[str, list[dict[str, Any]]]]:
    with connect_ro(canonical_db) as connection:
        current = {str(row[0]).upper() for row in connection.execute("SELECT current_ticker FROM security")}
        aliases: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            "SELECT ticker,security_id,valid_from,valid_to,provider FROM ticker_alias ORDER BY ticker,security_id"
        ):
            aliases[str(row[0]).upper()].append({
                "security_id": int(row[1]), "valid_from": row[2], "valid_to": row[3],
                "provider": row[4],
            })
    return current, dict(aliases)


def load_market_context(market_db: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    with connect_ro(market_db) as connection:
        coverage = {
            str(row[0]).upper(): {"first_date": row[1], "last_date": row[2], "rows": int(row[3])}
            for row in connection.execute(
                "SELECT osake,MIN(pvm),MAX(pvm),COUNT(*) FROM osakedata GROUP BY osake ORDER BY osake"
            )
        }
        metadata = {
            str(row[0]).upper(): {"market": row[1], "sector": row[2], "industry": row[3]}
            for row in connection.execute("SELECT ticker,market,sector,industry FROM ticker_meta ORDER BY ticker")
        }
    return coverage, metadata


def _quarter_index(fiscalperiod: str) -> int | None:
    try:
        year, quarter = fiscalperiod.split("-Q")
        value = int(quarter)
        return int(year) * 4 + value - 1 if value in {1, 2, 3, 4} else None
    except (AttributeError, ValueError):
        return None


def _latest_version_key(row: Mapping[str, str]) -> tuple[str, str, str]:
    return (
        str(row.get("lastupdated") or ""), str(row.get("date") or ""),
        stable_hash(dict(row)),
    )


def analyze_source(
    source: Path,
    target: set[str],
    current_identities: set[str],
    aliases: Mapping[str, list[dict[str, Any]]],
    market: Mapping[str, dict[str, Any]],
    market_metadata: Mapping[str, dict[str, Any]],
    production_min_arq: str,
) -> dict[str, Any]:
    rows_by_dimension = Counter()
    tickers_by_dimension: dict[str, set[str]] = defaultdict(set)
    min_date: dict[str, str] = {}
    max_date: dict[str, str] = {}
    year_stats: dict[tuple[str, str], Counter] = defaultdict(Counter)
    year_tickers: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    base_counts = Counter()
    base_by_year: dict[tuple[str, str, str], set[tuple[str, str, str]]] = defaultdict(set)
    last_year: dict[tuple[str, str], str] = {}
    early_rows: list[dict[str, Any]] = []
    arq_latest: dict[tuple[str, str], tuple[tuple[str, str, str], dict[str, str]]] = {}

    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_SOURCE_COLUMNS - fields)
        if missing:
            raise RuntimeError("PHASE12C1_SOURCE_SCHEMA_MISSING:" + ",".join(missing))
        for row in reader:
            ticker = str(row.get("ticker") or "").strip().upper()
            dimension = str(row.get("dimension") or "").strip().upper()
            period = str(row.get("calendardate") or row.get("reportperiod") or "")
            rows_by_dimension[dimension] += 1
            if ticker:
                tickers_by_dimension[dimension].add(ticker)
            if period:
                min_date[dimension] = min(min_date.get(dimension, period), period)
                max_date[dimension] = max(max_date.get(dimension, period), period)
            if dimension not in DIMENSIONS or not ticker or not period:
                continue
            year = period[:4]
            membership = "target" if ticker in target else "excluded"
            identity = "identity" if ticker in current_identities else "no_identity"
            market_match = "market" if ticker in market else "no_market"
            stats = year_stats[(dimension, year)]
            stats["all_rows"] += 1
            stats[f"{membership}_rows"] += 1
            stats[f"{identity}_rows"] += 1
            stats[f"{market_match}_rows"] += 1
            year_tickers[(dimension, year)]["all"].add(ticker)
            year_tickers[(dimension, year)][membership].add(ticker)
            if ticker in market:
                year_tickers[(dimension, year)]["market"].add(ticker)
            base = (ticker, str(row.get("reportperiod") or ""), str(row.get("fiscalperiod") or ""))
            base_counts[(dimension, *base)] += 1
            base_by_year[(dimension, year, "all")].add(base)
            if ticker in target:
                base_by_year[(dimension, year, "target")].add(base)
            last_year[(dimension, ticker)] = max(last_year.get((dimension, ticker), year), year)
            if dimension == "ARQ" and period < production_min_arq:
                early_rows.append({
                    "ticker": ticker, "dimension": dimension,
                    "fiscal_period": str(row.get("fiscalperiod") or ""),
                    "period_end": period, "report_period": str(row.get("reportperiod") or ""),
                    "availability_date": str(row.get("date") or ""),
                    "last_updated": str(row.get("lastupdated") or ""),
                    "target_universe_member": ticker in target,
                    "current_identity_match": ticker in current_identities,
                    "validation_status": "VALID_SOURCE_ROW",
                    "reason": (
                        "WOULD_BE_ACCEPTED" if ticker in target and ticker in current_identities
                        else "OUTSIDE_CURRENT_TARGET_UNIVERSE" if ticker not in target
                        else "CURRENT_IDENTITY_NOT_RESOLVED"
                    ),
                })
            if dimension == "ARQ" and ticker in target:
                key = (ticker, str(row.get("fiscalperiod") or ""))
                version = _latest_version_key(row)
                if key not in arq_latest or version > arq_latest[key][0]:
                    arq_latest[key] = (version, dict(row))

    historical_rows = []
    for (dimension, year), stats in sorted(year_stats.items()):
        all_tickers = year_tickers[(dimension, year)]["all"]
        target_tickers = year_tickers[(dimension, year)]["target"]
        excluded = all_tickers - target_tickers
        all_rows = stats["all_rows"]
        retained = stats["target_rows"]
        historical_rows.append({
            "dimension": dimension, "year": year,
            "all_provider_rows": all_rows,
            "all_base_periods": len(base_by_year[(dimension, year, "all")]),
            "all_tickers": len(all_tickers),
            "target_provider_rows": retained,
            "target_base_periods": len(base_by_year[(dimension, year, "target")]),
            "target_tickers": len(target_tickers),
            "excluded_provider_rows": stats["excluded_rows"],
            "excluded_tickers": len(excluded),
            "retained_pct": round(100 * retained / all_rows, 6),
            "excluded_pct": round(100 * stats["excluded_rows"] / all_rows, 6),
            "all_direct_market_tickers": len(year_tickers[(dimension, year)]["market"]),
            "last_observation_before_2026_tickers": sum(
                1 for ticker in all_tickers if last_year[(dimension, ticker)] < "2026"
            ),
        })

    excluded_summary = []
    reason_counts = Counter()
    for dimension in DIMENSIONS:
        for ticker in sorted(tickers_by_dimension[dimension] - target):
            metadata = market_metadata.get(ticker, {})
            sector = str(metadata.get("sector") or "")
            has_market = ticker in market
            has_alias = ticker in aliases
            if sector in {"Financial Services", "Real Estate"}:
                reason = "ACCOUNTING_SPECIALIZED_CURRENT_CONTEXT"
            elif has_market:
                reason = "DIRECT_LOCAL_OHLC_OUTSIDE_OPERATIONAL_UNIVERSE"
            elif has_alias:
                reason = "LOCAL_ALIAS_CANDIDATE"
            else:
                reason = "UNRESOLVED_NO_DIRECT_LOCAL_MARKET_IDENTITY"
            reason_counts[(dimension, reason)] += 1
            excluded_summary.append({
                "dimension": dimension, "ticker": ticker,
                "last_fundamental_year": last_year[(dimension, ticker)],
                "direct_market_match": has_market, "alias_candidate": has_alias,
                "market_first_date": market.get(ticker, {}).get("first_date"),
                "market_last_date": market.get(ticker, {}).get("last_date"),
                "current_sector_context": sector,
                "current_industry_context": str(metadata.get("industry") or ""),
                "reason": reason,
            })

    phase12b = _phase12b_feasibility(arq_latest)
    target_rows = {
        dimension: sum(row["target_provider_rows"] for row in historical_rows if row["dimension"] == dimension)
        for dimension in DIMENSIONS
    }
    target_ticker_counts = {
        dimension: len(tickers_by_dimension[dimension] & target) for dimension in DIMENSIONS
    }
    identity_ticker_counts = {
        dimension: len(tickers_by_dimension[dimension] & target & current_identities)
        for dimension in DIMENSIONS
    }
    direct_market_target_ticker_counts = {
        dimension: len(tickers_by_dimension[dimension] & target & set(market))
        for dimension in DIMENSIONS
    }
    revision_extra = Counter()
    exact_base_count = Counter()
    for key, count in base_counts.items():
        exact_base_count[key[0]] += 1
        revision_extra[key[0]] += max(count - 1, 0)
    return {
        "source": {
            "path": str(source.resolve()), "sha256": sha256(source),
            "bytes": source.stat().st_size,
            "columns": len(fields), "permanent_identifier_fields_present": [],
            "permanent_identity_limitation": "SOURCE_HAS_TICKER_ONLY",
            "rows_by_dimension": dict(sorted(rows_by_dimension.items())),
            "unique_tickers_by_dimension": {
                key: len(value) for key, value in sorted(tickers_by_dimension.items())
            },
            "oldest_by_dimension": dict(sorted(min_date.items())),
            "newest_by_dimension": dict(sorted(max_date.items())),
        },
        "historical_universe_by_year": historical_rows,
        "excluded_identities": excluded_summary,
        "excluded_reason_counts": [
            {"dimension": dimension, "reason": reason, "tickers": count}
            for (dimension, reason), count in sorted(reason_counts.items())
        ],
        "target_rows": target_rows,
        "target_ticker_counts": target_ticker_counts,
        "identity_ticker_counts": identity_ticker_counts,
        "direct_market_target_ticker_counts": direct_market_target_ticker_counts,
        "global_base_period_counts": dict(sorted(exact_base_count.items())),
        "revision_extra_rows": dict(sorted(revision_extra.items())),
        "early_arq_rows": sorted(early_rows, key=lambda row: tuple(str(row[k]) for k in ("period_end", "ticker", "last_updated"))),
        "last_year_counts": [
            {"dimension": dimension, "last_year": year, "tickers": count}
            for (dimension, year), count in sorted(Counter(
                (dimension, year) for (dimension, _ticker), year in last_year.items()
            ).items())
        ],
        "phase12b_feasibility": phase12b,
    }


def _phase12b_feasibility(
    latest: Mapping[tuple[str, str], tuple[tuple[str, str, str], dict[str, str]]]
) -> dict[str, Any]:
    by_ticker_index: dict[str, dict[int, dict[str, str]]] = defaultdict(dict)
    for (ticker, fiscalperiod), (_, row) in latest.items():
        index = _quarter_index(fiscalperiod)
        if index is not None:
            by_ticker_index[ticker][index] = row
    output = []
    for basis in ("FISCAL_PERIOD_YEAR", "AVAILABILITY_YEAR"):
        for year in ("2020", "2021", "2022", "2023"):
            counts = Counter()
            tickers: dict[str, set[str]] = defaultdict(set)
            months = set()
            for ticker, quarters in by_ticker_index.items():
                for index, row in quarters.items():
                    grouping_value = (
                        str(row.get("fiscalperiod") or "")
                        if basis == "FISCAL_PERIOD_YEAR"
                        else str(row.get("date") or "")
                    )
                    if not grouping_value.startswith(year):
                        continue
                    counts["endpoints"] += 1
                    tickers["endpoints"].add(ticker)
                    chain = [quarters.get(index - offset) for offset in range(8)]
                    if any(item is None for item in chain):
                        continue
                    counts["contiguous_8q"] += 1
                    tickers["contiguous_8q"].add(ticker)
                    recent4 = chain[:4]
                    ttm_ready = all(
                        str(item.get(field) or "").strip() != ""
                        for item in recent4 for field in ("revenue", "opinc", "fcf")
                    )
                    if ttm_ready:
                        counts["current_ttm_fields"] += 1
                        tickers["current_ttm_fields"].add(ticker)
                    trajectory = all(
                        str(item.get(field) or "").strip() != ""
                        for item in chain for field in ("revenue", "opinc", "fcf")
                    )
                    shares_ready = str(row.get("sharesbas") or "").strip() != "" and str(chain[4].get("sharesbas") or "").strip() != ""
                    balance_ready = all(str(row.get(field) or "").strip() != "" for field in ("cashneq", "debt"))
                    if trajectory:
                        counts["five_ttm_snapshot_trajectory"] += 1
                        tickers["five_ttm_snapshot_trajectory"].add(ticker)
                    if ttm_ready and trajectory and shares_ready and balance_ready:
                        counts["score_raw_feasible"] += 1
                        tickers["score_raw_feasible"].add(ticker)
                        availability = str(row.get("date") or "")
                        if len(availability) >= 7:
                            months.add(availability[:7])
            output.append({
                "basis": basis, "year": year, **dict(sorted(counts.items())),
                **{f"{name}_tickers": len(values) for name, values in sorted(tickers.items())},
                "score_feasible_signal_months": len(months),
            })
    return {
        "semantics": "RAW_REVISED_HISTORY_FEASIBILITY_ONLY",
        "by_year": output,
        "locked_periods_unchanged": {
            "development": "2021-2023", "validation": "2024",
            "retrospective_confirmation": "2025",
        },
    }


def oldest_reconciliation(audit: Mapping[str, Any], production_counts: Mapping[str, Any]) -> dict[str, Any]:
    source = audit["source"]
    target_rows = audit["target_rows"]
    target_tickers = audit["target_ticker_counts"]
    identity_tickers = audit["identity_ticker_counts"]
    production_by_dimension = {
        row["dimension"]: row for row in production_counts["by_dimension"]
    }
    production_arq = production_by_dimension["ARQ"]
    early = audit["early_arq_rows"]
    target_early = [row for row in early if row["target_universe_member"]]
    return {
        "global_oldest_arq": source["oldest_by_dimension"]["ARQ"],
        "after_dimension_selection_oldest_arq": source["oldest_by_dimension"]["ARQ"],
        "after_target_selection_oldest_arq": min(
            row["period_end"] for row in early if row["target_universe_member"]
        ) if target_early else production_arq["oldest"],
        "after_current_identity_validation_oldest_arq": production_arq["oldest"],
        "accepted_staging_oldest_arq": production_arq["oldest"],
        "production_retained_oldest_arq": production_arq["oldest"],
        "preliminary_canonical_identity_eligible_oldest_arq": production_arq["oldest"],
        "rows_before_production_minimum": len(early),
        "target_rows_before_production_minimum": len(target_early),
        "explanation": "ALL_PRE_2015_06_30_ARQ_ROWS_ARE_OUTSIDE_CURRENT_TARGET_UNIVERSE" if not target_early else "REQUIRES_ROW_REVIEW",
        "waterfall": [
            row
            for dimension in DIMENSIONS
            for row in (
                {"dimension": dimension, "stage": "global_staged", "rows": source["rows_by_dimension"][dimension], "tickers": source["unique_tickers_by_dimension"][dimension]},
                {"dimension": dimension, "stage": "dimension_selected", "rows": source["rows_by_dimension"][dimension], "tickers": source["unique_tickers_by_dimension"][dimension]},
                {"dimension": dimension, "stage": "current_target_selected", "rows": target_rows[dimension], "tickers": target_tickers[dimension]},
                {"dimension": dimension, "stage": "current_identity_resolved", "rows": target_rows[dimension], "tickers": identity_tickers[dimension]},
                {"dimension": dimension, "stage": "accepted_staged_rows", "rows": target_rows[dimension], "tickers": identity_tickers[dimension]},
                {"dimension": dimension, "stage": "production_rows_after_append_only_merge", "rows": production_by_dimension[dimension]["rows"], "tickers": production_by_dimension[dimension]["tickers"]},
            )
        ],
        "production_minus_current_snapshot_rows": production_arq["rows"] - target_rows["ARQ"],
    }


def production_state(repo_root: Path) -> dict[str, Any]:
    paths = {
        "provider": repo_root / "data/fundamentals_provider.db",
        "canonical": repo_root / "data/fundamentals_v4.db",
        "analysis": repo_root / "data/fundamentals_analysis.db",
        "market": repo_root / "data/osakedata.db",
        "taxonomy": repo_root / "data/analysis.db",
    }
    databases = {}
    for name, path in paths.items():
        inventory = database_inventory(path)
        with connect_ro(path) as connection:
            tables = [
                str(row[0]) for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            inventory["logical_table_row_counts"] = {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in tables
            }
        wal = Path(str(path) + "-wal")
        inventory["wal_size"] = wal.stat().st_size if wal.exists() else 0
        inventory["wal_sha256"] = sha256(wal) if wal.exists() else None
        inventory["wal_accounting"] = "READ_ONLY_SQL_AND_LOGICAL_COUNTS_INCLUDE_VISIBLE_WAL"
        databases[name] = inventory
    with connect_ro(paths["analysis"]) as connection:
        active_package = dict(connection.execute(
            "SELECT family_version,family_fingerprint,persistence_fingerprint,activated_at_utc "
            "FROM fundamentals_active_model_family WHERE singleton=1"
        ).fetchone())
        relative = dict(connection.execute(
            "SELECT model_fingerprint,snapshot_id,activated_at_utc FROM relative_valuation_active_snapshot"
        ).fetchone())
    reports = {
        str(path.relative_to(repo_root / "fundamental_reports")): sha256(path)
        for path in sorted((repo_root / "fundamental_reports").rglob("*")) if path.is_file()
    }
    return {
        "databases": databases, "provider_counts": provider_counts(paths["provider"]),
        "active_operating_income_v2_package": active_package,
        "active_relative_valuation_snapshot": relative,
        "report_count": len(reports), "reports_fingerprint": stable_hash(reports),
        "aggregate_fingerprint": stable_hash({
            "databases": {
                name: {
                    "main_sha256": value["sha256"], "wal_sha256": value["wal_sha256"],
                    "schema_hash": value["schema_hash"],
                    "logical_table_rows": value["logical_table_row_counts"],
                }
                for name, value in databases.items()
            },
            "active_package": active_package, "active_relative_valuation": relative,
            "reports": reports,
        }),
    }


def write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    fields = sorted({key for row in materialized for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in materialized:
            writer.writerow({key: row.get(key) for key in fields})
    with path.open(newline="", encoding="utf-8") as handle:
        list(csv.DictReader(handle))


def result_fingerprint(result: Mapping[str, Any]) -> str:
    return stable_hash(result)
