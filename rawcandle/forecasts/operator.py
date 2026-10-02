from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from rawcandle.forecasts.contracts import (
    FAMILY_FISCAL_ESTIMATE,
    FORECAST_FAMILIES,
    STATUS_TRANSIENT_FAILURE,
)
from rawcandle.forecasts.identity import IDENTITY_RESOLVED, ForecastIdentityResolver
from rawcandle.forecasts.linking import AS_KNOWN, CURRENT_RECONCILED, ForecastLinkService
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import SCHEMA_VERSION, connect_forecasts_db, migrate_forecasts_db
from rawcandle.forecasts.transport import YahooForecastTransport, YahooRawResult, utc_now
from rawcandle.fundamentals.generations import resolve_requested_role_path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORECAST_DB = Path(
    os.environ.get("RAWCANDLE_FORECAST_DB", ROOT / "data" / "forecasts.db")
)
DEFAULT_FUNDAMENTALS_DB = Path(
    os.environ.get("RAWCANDLE_FUNDAMENTALS_DB", ROOT / "data" / "fundamentals_v4.db")
)
DEFAULT_PILOT_SYMBOLS = ("AAPL", "ADBE", "AMZN", "BB", "NVDA", "NUE")
EXPECTED_TABLES = {
    "forecast_schema_version", "forecast_run", "forecast_raw_evidence",
    "forecast_snapshot", "forecast_fetch", "forecast_estimate",
    "forecast_price_target", "forecast_earnings_history_reference",
    "forecast_identity_resolution", "forecast_fiscal_link",
}
EXPECTED_INDEXES = {
    "idx_forecast_fetch_asof", "idx_forecast_fetch_run",
    "idx_forecast_snapshot_identity", "idx_forecast_estimate_snapshot",
    "idx_forecast_price_target_snapshot", "idx_forecast_history_snapshot",
    "idx_forecast_identity_fetch", "idx_forecast_fiscal_link_fetch",
    "idx_forecast_fiscal_link_target",
}
FORBIDDEN_DB_NAMES = {
    "fundamentals_v4.db", "fundamentals_provider.db", "fundamentals_analysis.db",
    "market.db", "ohlcv.db",
}


def _normalized_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(item.strip().upper() for item in symbols if item.strip()))
    if not result:
        raise ValueError("at least one symbol is required")
    return result


def _existing_database_guard(path: Path) -> None:
    if path.name.lower() in FORBIDDEN_DB_NAMES:
        raise ValueError(f"refusing non-forecast database target: {path}")
    if not path.exists() or path.stat().st_size == 0:
        return
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"target is not a valid SQLite database: {path}") from exc
    if tables and "forecast_schema_version" not in tables:
        raise ValueError(f"refusing unrelated existing SQLite database: {path}")


def verify_database(path: str | Path) -> dict[str, Any]:
    database = Path(path)
    with connect_forecasts_db(database) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        schema_version = connection.execute(
            "SELECT version FROM forecast_schema_version WHERE db_name='forecasts'"
        ).fetchone()
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TEMP TABLE forecast_write_probe(value INTEGER)")
        connection.rollback()
    version_value = str(schema_version[0]) if schema_version else None
    missing_tables = sorted(EXPECTED_TABLES - tables)
    missing_indexes = sorted(EXPECTED_INDEXES - indexes)
    if quick_check != "ok" or version_value != SCHEMA_VERSION or missing_tables or missing_indexes:
        raise RuntimeError(
            f"forecast database verification failed: quick_check={quick_check} "
            f"version={version_value} missing_tables={missing_tables} "
            f"missing_indexes={missing_indexes}"
        )
    return {
        "db": str(database), "quick_check": quick_check,
        "schema_version": version_value, "writable": True,
        "tables": len(EXPECTED_TABLES), "indexes": len(EXPECTED_INDEXES),
    }


def migrate_database(path: str | Path = DEFAULT_FORECAST_DB) -> dict[str, Any]:
    database = Path(path)
    _existing_database_guard(database)
    migrate_forecasts_db(database)
    return verify_database(database)


@dataclass(frozen=True)
class AcquisitionOutcome:
    run_id: str
    symbols: tuple[str, ...]
    counters: Mapping[str, int]


def acquire_run(
    *,
    forecast_db: str | Path = DEFAULT_FORECAST_DB,
    fundamentals_db: str | Path = DEFAULT_FUNDAMENTALS_DB,
    symbols: Iterable[str] | None = None,
    families: Iterable[str] = FORECAST_FAMILIES,
    transport: YahooForecastTransport | None = None,
    run_id: str | None = None,
    resume_run_id: str | None = None,
    scope_metadata: Mapping[str, Any] | None = None,
) -> AcquisitionOutcome:
    database = Path(forecast_db)
    fundamentals_db = resolve_requested_role_path("canonical", fundamentals_db)
    verify_database(database)
    selected_families = tuple(dict.fromkeys(families))
    if not selected_families or not set(selected_families) <= set(FORECAST_FAMILIES):
        raise ValueError("unsupported or empty forecast family selection")
    resolver = ForecastIdentityResolver(fundamentals_db)
    yahoo = transport or YahooForecastTransport()
    adapter_version = version("yfinance")
    repository = ForecastRepository(
        database,
        adapter_version=adapter_version,
        raw_retention_days=yahoo.config.raw_retention_days,
    )
    completed_attempts: set[tuple[str, str]] = set()
    if resume_run_id is not None:
        if run_id is not None:
            raise ValueError("run_id and resume_run_id are mutually exclusive")
        if scope_metadata is not None:
            raise ValueError("scope_metadata cannot change a resumed run")
        with connect_forecasts_db(database) as connection:
            existing = connection.execute(
                "SELECT scope_json FROM forecast_run WHERE run_id=?", (resume_run_id,)
            ).fetchone()
            if existing is None:
                raise LookupError(f"forecast run not found: {resume_run_id}")
            scope = json.loads(existing["scope_json"])
            selected_symbols = _normalized_symbols(
                symbols if symbols is not None else scope.get("symbols", ())
            )
            if tuple(scope.get("symbols", ())) != selected_symbols or tuple(scope.get("families", ())) != selected_families:
                raise ValueError("resume scope differs from the stored run scope")
            completed_attempts = {
                (str(row[0]), str(row[1])) for row in connection.execute(
                    "SELECT provider_symbol,forecast_family FROM forecast_fetch WHERE run_id=?",
                    (resume_run_id,),
                )
            }
            connection.execute(
                "UPDATE forecast_run SET status='RUNNING',completed_at_utc=NULL WHERE run_id=?",
                (resume_run_id,),
            )
        active_run = resume_run_id
    else:
        selected_symbols = _normalized_symbols(
            DEFAULT_PILOT_SYMBOLS if symbols is None else symbols
        )
        scope = {
            "symbols": selected_symbols,
            "families": selected_families,
            "mode": "OPERATOR",
        }
        if scope_metadata:
            overlap = set(scope).intersection(scope_metadata)
            if overlap:
                raise ValueError(f"scope metadata uses reserved keys: {sorted(overlap)}")
            scope.update(scope_metadata)
        active_run = repository.start_run(run_id=run_id, scope=scope)
    for symbol in selected_symbols:
        identity = resolver.resolve(symbol, utc_now())
        company_id = identity.company_id if identity.identity_status == IDENTITY_RESOLVED else None
        security_id = identity.security_id if identity.identity_status == IDENTITY_RESOLVED else None
        for family in selected_families:
            if (symbol, family) in completed_attempts:
                continue
            try:
                raw = yahoo.fetch(symbol, family)
                repository.record_fetch(
                    active_run, raw, company_id=company_id, security_id=security_id
                )
            except Exception as exc:
                failed_at = utc_now()
                fallback = YahooRawResult(
                    requested_at_utc=failed_at, fetched_at_utc=failed_at,
                    provider_symbol=symbol, forecast_family=family, http_status=None,
                    status=STATUS_TRANSIENT_FAILURE, success=False,
                    error_class=type(exc).__name__, error_code="OPERATOR_EXCEPTION",
                    error_message=str(exc), raw_payload=None, raw_body=None,
                    raw_hash=None, attempt_count=1,
                )
                repository.record_fetch(
                    active_run, fallback, company_id=company_id, security_id=security_id
                )
    counters = repository.complete_run(active_run)
    return AcquisitionOutcome(active_run, selected_symbols, counters)


def _run_fetch_ids(database: Path, run_id: str, *, fiscal_only: bool) -> list[str]:
    with connect_forecasts_db(database) as connection:
        run = connection.execute(
            "SELECT 1 FROM forecast_run WHERE run_id=?", (run_id,)
        ).fetchone()
        if run is None:
            raise LookupError(f"forecast run not found: {run_id}")
        sql = "SELECT fetch_id FROM forecast_fetch WHERE run_id=?"
        params: tuple[Any, ...] = (run_id,)
        if fiscal_only:
            sql += " AND forecast_family=?"
            params += (FAMILY_FISCAL_ESTIMATE,)
        sql += " ORDER BY fetched_at_utc,rowid"
        return [str(row[0]) for row in connection.execute(sql, params)]


def link_run(
    run_id: str,
    *,
    forecast_db: str | Path = DEFAULT_FORECAST_DB,
    fundamentals_db: str | Path = DEFAULT_FUNDAMENTALS_DB,
) -> dict[str, int]:
    database = Path(forecast_db)
    fundamentals_db = resolve_requested_role_path("canonical", fundamentals_db)
    service = ForecastLinkService(database, fundamentals_db)
    counts: Counter[str] = Counter()
    for fetch_id in _run_fetch_ids(database, run_id, fiscal_only=True):
        links = service.link_fetch(fetch_id)
        if not links:
            counts["NO_FISCAL_SNAPSHOT"] += 1
        counts.update(str(item["link_status"]) for item in links)
    return dict(sorted(counts.items()))


def reconcile_run(
    run_id: str,
    *,
    forecast_db: str | Path = DEFAULT_FORECAST_DB,
    fundamentals_db: str | Path = DEFAULT_FUNDAMENTALS_DB,
) -> dict[str, int]:
    database = Path(forecast_db)
    fundamentals_db = resolve_requested_role_path("canonical", fundamentals_db)
    service = ForecastLinkService(database, fundamentals_db)
    counts: Counter[str] = Counter()
    for fetch_id in _run_fetch_ids(database, run_id, fiscal_only=True):
        rows = service.reconcile_fetch(fetch_id)
        for row in rows:
            reasons = set(json.loads(row["reason_codes_json"]))
            if row["link_status"] == "AMBIGUOUS":
                counts["AMBIGUOUS"] += 1
            elif row["canonical_quarter_id"] is not None:
                counts["CANONICAL_QUARTER_ATTACHED"] += 1
            elif row["target_type"] == "FISCAL_QUARTER":
                counts["CANONICAL_QUARTER_NOT_YET_AVAILABLE"] += 1
            else:
                counts["ANNUAL_TARGET"] += 1
            if row["supersedes_link_id"] is not None:
                counts["CHANGED_ATTACHMENT"] += 1
            if "CANONICAL_QUARTER_RECONCILED" in reasons:
                counts["RECONCILED"] += 1
    return dict(sorted(counts.items()))


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def end_date_statistics(differences: Iterable[int]) -> dict[str, int | None]:
    values = [abs(int(value)) for value in differences]
    return {
        "count": len(values),
        "within_45d": sum(value <= 45 for value in values),
        "outside_45d": sum(value > 45 for value in values),
        "median_abs_diff": _percentile(values, 0.5),
        "p90_abs_diff": _percentile(values, 0.9),
        "max_abs_diff": max(values) if values else None,
    }


def _latest_links(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        key = (str(item["fetch_id"]), int(item["occurrence_index"]), str(item["knowledge_mode"]))
        latest.setdefault(key, item)
    return list(latest.values())


def report_run(
    run_id: str,
    *,
    forecast_db: str | Path = DEFAULT_FORECAST_DB,
) -> dict[str, Any]:
    database = Path(forecast_db)
    with connect_forecasts_db(database) as connection:
        run = connection.execute("SELECT * FROM forecast_run WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise LookupError(f"forecast run not found: {run_id}")
        fetches = [dict(row) for row in connection.execute(
            "SELECT * FROM forecast_fetch WHERE run_id=? ORDER BY fetched_at_utc,rowid", (run_id,)
        )]
        fetch_ids = [item["fetch_id"] for item in fetches]
        identities: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        if fetch_ids:
            marks = ",".join("?" for _ in fetch_ids)
            identities = [dict(row) for row in connection.execute(
                f"SELECT * FROM forecast_identity_resolution WHERE fetch_id IN ({marks}) "
                "ORDER BY resolved_at_utc DESC,rowid DESC", fetch_ids
            )]
            links = _latest_links(connection.execute(
                f"SELECT * FROM forecast_fiscal_link WHERE fetch_id IN ({marks}) "
                "ORDER BY linked_at_utc DESC,rowid DESC", fetch_ids
            ))
        snapshot_ids = sorted({item["snapshot_id"] for item in fetches if item["snapshot_id"]})
        drift_paths: list[str] = []
        if snapshot_ids:
            marks = ",".join("?" for _ in snapshot_ids)
            for row in connection.execute(
                f"SELECT schema_drift_json FROM forecast_snapshot WHERE snapshot_id IN ({marks})",
                snapshot_ids,
            ):
                drift_paths.extend(json.loads(row[0]))
        raw_count = connection.execute(
            "SELECT COUNT(DISTINCT raw_evidence_hash) FROM forecast_fetch "
            "WHERE run_id=? AND raw_evidence_hash IS NOT NULL", (run_id,)
        ).fetchone()[0]

    acquisition = Counter(item["status"] for item in fetches)
    by_family: dict[str, dict[str, int]] = {}
    for family in FORECAST_FAMILIES:
        by_family[family] = dict(sorted(Counter(
            item["status"] for item in fetches if item["forecast_family"] == family
        ).items()))
    latest_identity: dict[str, dict[str, Any]] = {}
    for item in identities:
        latest_identity.setdefault(str(item["fetch_id"]), item)
    identity = Counter()
    for item in latest_identity.values():
        if item["identity_status"] != "RESOLVED":
            identity[str(item["identity_status"])] += 1
        else:
            identity[str(item["resolution_method"])] += 1
    as_known = [item for item in links if item["knowledge_mode"] == AS_KNOWN]
    reconciled = [item for item in links if item["knowledge_mode"] == CURRENT_RECONCILED]
    differences = []
    annual = []
    symbol_by_fetch = {item["fetch_id"]: item["provider_symbol"] for item in fetches}
    for item in as_known:
        evidence = json.loads(item["evidence_json"])
        if item["link_status"] == "LINKED" and evidence.get("end_date_difference_days") is not None:
            differences.append(int(evidence["end_date_difference_days"]))
        if item["target_type"] == "FISCAL_YEAR":
            annual.append({
                "symbol": symbol_by_fetch[item["fetch_id"]],
                "provider_horizon": item["provider_horizon"],
                "provider_end_date": item["provider_end_date"],
                "fiscal_year": item["expected_fiscal_year"],
                "status": item["link_status"],
                "reason_codes": json.loads(item["reason_codes_json"]),
            })
    reconciliation = Counter()
    for item in reconciled:
        if item["link_status"] == "AMBIGUOUS":
            reconciliation["AMBIGUOUS"] += 1
        elif item["canonical_quarter_id"] is not None:
            reconciliation["CANONICAL_QUARTER_ATTACHED"] += 1
        elif item["target_type"] == "FISCAL_QUARTER":
            reconciliation["CANONICAL_QUARTER_NOT_YET_AVAILABLE"] += 1
        else:
            reconciliation["ANNUAL_TARGET"] += 1
        if item["supersedes_link_id"] is not None:
            reconciliation["CHANGED_ATTACHMENT"] += 1
    scope = json.loads(run["scope_json"])
    return {
        "run_id": run_id,
        "run_status": run["status"],
        "symbols": scope.get("symbols", []),
        "symbols_attempted": len(scope.get("symbols", [])),
        "family_fetches_attempted": len(fetches),
        "acquisition": dict(sorted(acquisition.items())),
        "acquisition_by_family": by_family,
        "identity": dict(sorted(identity.items())),
        "fiscal_link": dict(sorted(Counter(item["link_status"] for item in as_known).items())),
        "reconciliation": dict(sorted(reconciliation.items())),
        "end_date": end_date_statistics(differences),
        "annual_mappings": sorted(annual, key=lambda item: (item["symbol"], item["provider_horizon"])),
        "provider_quality": {
            "retry_count": sum(max(0, int(item["attempt_count"]) - 1) for item in fetches),
            "rate_limit_count": acquisition.get("RATE_LIMITED", 0),
            "schema_drift_count": len(drift_paths),
            "schema_drift_paths": sorted(set(drift_paths)),
            "schema_drift_path_counts": dict(sorted(Counter(drift_paths).items())),
            "raw_evidence_retained": int(raw_count),
        },
    }
