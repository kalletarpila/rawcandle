from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminStatus,
    RunStage,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.progress import (
    REFRESH_FUNDAMENTALS_STAGES,
    ProgressCallback,
    ProgressStage,
    ProgressTracker,
)
from rawcandle.fundamentals.providers.sharadar import (
    SharadarClient,
    SharadarResult,
    extract_schema_fields,
)


CONTRACT_VERSION = "PHASE13G3_2_SHARADAR_REFRESH_PREVIEW_V1"
SOURCE_DATASET = "SHARADAR"
SOURCE_TABLE = "fundamentals"
SOURCE_ENDPOINT = "/data/fundamentals"
SOURCE_PRIMARY_KEY = ("ticker", "dimension", "date", "reportperiod")
REFRESH_DIMENSIONS = ("ARQ", "MRQ")
DISCOVERY_LIMIT = 10_000
OVERLAP_DAYS = 3

FISCAL_FIELDS = ("calendardate", "fiscalperiod")
FINANCIAL_FIELDS = (
    "revenue",
    "gp",
    "opinc",
    "ebit",
    "ebitda",
    "netinc",
    "ncfo",
    "capex",
    "fcf",
    "cashneq",
    "debt",
    "debtc",
    "debtnc",
    "sharesbas",
    "shareswa",
    "shareswadil",
    "netinccmn",
    "receivables",
    "inventory",
    "payables",
    "deferredrev",
    "assets",
)
REFRESH_REQUEST_FIELDS = (
    *SOURCE_PRIMARY_KEY,
    "lastupdated",
    *FISCAL_FIELDS,
    *FINANCIAL_FIELDS,
)
DISCOVERY_FIELDS = ("ticker", "dimension", "lastupdated")
DATE_FIELDS = ("date", "reportperiod", "lastupdated", "calendardate")
FISCAL_PERIOD_RE = re.compile(r"^(?P<year>[0-9]{4})-Q(?P<quarter>[1-4])$")

REFRESH_STATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sharadar_refresh_state (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    source_dataset TEXT NOT NULL,
    source_table TEXT NOT NULL,
    published_source_watermark TEXT NOT NULL,
    provider_semantic_fingerprint TEXT NOT NULL,
    source_schema_fingerprint TEXT NOT NULL,
    successful_run_id TEXT NOT NULL,
    completed_at_utc TEXT NOT NULL
)
"""


class RefreshPreviewError(RuntimeError):
    pass


class DiscoveryIncompleteError(RefreshPreviewError):
    pass


class HistoryValidationError(RefreshPreviewError):
    pass


@dataclass(frozen=True)
class RefreshState:
    mode: str
    published_watermark: str | None
    derived_watermark: str | None
    query_start_date: str
    source_dataset: str = SOURCE_DATASET
    source_table: str = SOURCE_TABLE
    provider_semantic_fingerprint: str | None = None
    source_schema_fingerprint: str | None = None
    successful_run_id: str | None = None
    completed_at_utc: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class HistoryTrust:
    status: str
    ticker: str
    dimension: str
    row_count: int
    raw_fingerprint: str | None
    effective_fingerprint: str | None
    rows: tuple[Mapping[str, Any], ...]
    errors: tuple[str, ...] = ()

    def evidence(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ticker": self.ticker,
            "dimension": self.dimension,
            "row_count": self.row_count,
            "raw_fingerprint": self.raw_fingerprint,
            "effective_fingerprint": self.effective_fingerprint,
            "errors": list(self.errors),
        }


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def ensure_refresh_state_schema(connection: sqlite3.Connection) -> None:
    """Create the future singleton state table on a fixture or candidate DB only."""
    connection.execute(REFRESH_STATE_SCHEMA_SQL)


def source_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(field) or "").strip().upper() if field in {"ticker", "dimension"} else str(row.get(field) or "").strip() for field in SOURCE_PRIMARY_KEY)  # type: ignore[return-value]


def source_key_evidence(row: Mapping[str, Any]) -> dict[str, str]:
    key = source_key(row)
    return dict(zip(SOURCE_PRIMARY_KEY, key, strict=True))


def _normalize_number(value: Any, field: str) -> int | str | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, float) and not math.isfinite(value):
        raise HistoryValidationError(f"NON_FINITE_FINANCIAL_FIELD:{field}")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise HistoryValidationError(f"INVALID_FINANCIAL_FIELD:{field}") from exc
    if not number.is_finite():
        raise HistoryValidationError(f"NON_FINITE_FINANCIAL_FIELD:{field}")
    integral = number.to_integral_value()
    if number == integral:
        return int(integral)
    return format(number.normalize(), "f")


def _iso_date(value: Any, field: str, *, required: bool = True) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise HistoryValidationError(f"MISSING_DATE:{field}")
        return None
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise HistoryValidationError(f"INVALID_DATE:{field}:{text}") from exc
    return text


def fiscal_identity(value: Any) -> tuple[int, str]:
    text = str(value or "").strip().upper()
    match = FISCAL_PERIOD_RE.fullmatch(text)
    if not match:
        raise HistoryValidationError(f"INVALID_FISCAL_PERIOD:{text}")
    return int(match.group("year")), f"Q{match.group('quarter')}"


def normalize_source_row(
    row: Mapping[str, Any],
    *,
    expected_ticker: str | None = None,
    expected_dimension: str | None = None,
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    dimension = str(row.get("dimension") or "").strip().upper()
    if not ticker:
        raise HistoryValidationError("MISSING_TICKER")
    if dimension not in REFRESH_DIMENSIONS:
        raise HistoryValidationError(f"UNEXPECTED_DIMENSION:{dimension}")
    if expected_ticker and ticker != expected_ticker.strip().upper():
        raise HistoryValidationError(f"WRONG_TICKER:{ticker}")
    if expected_dimension and dimension != expected_dimension.strip().upper():
        raise HistoryValidationError(f"WRONG_DIMENSION:{dimension}")
    normalized: dict[str, Any] = {
        "ticker": ticker,
        "dimension": dimension,
        "date": _iso_date(row.get("date"), "date"),
        "reportperiod": _iso_date(row.get("reportperiod"), "reportperiod"),
        "lastupdated": _iso_date(row.get("lastupdated"), "lastupdated"),
        "calendardate": _iso_date(row.get("calendardate"), "calendardate"),
        "fiscalperiod": str(row.get("fiscalperiod") or "").strip().upper(),
    }
    fiscal_identity(normalized["fiscalperiod"])
    if normalized["date"] < normalized["reportperiod"]:
        raise HistoryValidationError("FILING_DATE_BEFORE_REPORT_PERIOD")
    normalized.update({field: _normalize_number(row.get(field), field) for field in FINANCIAL_FIELDS})
    return normalized


def _effective_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in (*SOURCE_PRIMARY_KEY, *FISCAL_FIELDS, *FINANCIAL_FIELDS)}


def _raw_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in (*SOURCE_PRIMARY_KEY, "lastupdated", *FISCAL_FIELDS, *FINANCIAL_FIELDS)}


def semantic_row_fingerprints(row: Mapping[str, Any]) -> dict[str, str]:
    normalized = normalize_source_row(row)
    return {
        "raw_source_fingerprint": fingerprint(_raw_row(normalized)),
        "effective_content_fingerprint": fingerprint(_effective_row(normalized)),
    }


def history_fingerprints(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    normalized = [normalize_source_row(row) for row in rows]
    ordered = sorted(normalized, key=source_key)
    return {
        "raw_source_fingerprint": fingerprint([_raw_row(row) for row in ordered]),
        "effective_content_fingerprint": fingerprint([_effective_row(row) for row in ordered]),
    }


def validate_complete_history(
    rows: Sequence[Mapping[str, Any]],
    *,
    ticker: str,
    dimension: str,
    response_reached_limit: bool = False,
) -> HistoryTrust:
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    if not rows:
        errors.append("EMPTY_HISTORY_RESPONSE")
    if response_reached_limit:
        errors.append("EXACT_LIMIT_RESPONSE_NOT_PROVEN_COMPLETE")
    for index, row in enumerate(rows):
        try:
            normalized.append(normalize_source_row(row, expected_ticker=ticker, expected_dimension=dimension))
        except HistoryValidationError as exc:
            errors.append(f"ROW_{index}:{exc}")
    keys = [source_key(row) for row in normalized]
    if len(keys) != len(set(keys)):
        errors.append("DUPLICATE_SOURCE_PRIMARY_KEY")
    ordered = tuple(sorted(normalized, key=source_key))
    hashes = history_fingerprints(ordered) if ordered else {
        "raw_source_fingerprint": fingerprint([]),
        "effective_content_fingerprint": fingerprint([]),
    }
    return HistoryTrust(
        status="COMPLETE" if not errors else "INCOMPLETE",
        ticker=ticker.upper(),
        dimension=dimension.upper(),
        row_count=len(ordered),
        raw_fingerprint=hashes["raw_source_fingerprint"],
        effective_fingerprint=hashes["effective_content_fingerprint"],
        rows=ordered,
        errors=tuple(errors),
    )


def combined_effective_history_fingerprint(histories: Mapping[str, HistoryTrust]) -> str:
    return fingerprint({dimension: histories[dimension].effective_fingerprint for dimension in sorted(histories)})


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def resolve_refresh_state(provider_db: Path) -> RefreshState:
    with _readonly(provider_db) as connection:
        if _table_exists(connection, "sharadar_refresh_state"):
            row = connection.execute("SELECT * FROM sharadar_refresh_state WHERE singleton_id=1").fetchone()
            if row is not None:
                published = _iso_date(row["published_source_watermark"], "published_source_watermark")
                query_start = (date.fromisoformat(published) - timedelta(days=OVERLAP_DAYS)).isoformat()
                return RefreshState(
                    mode="ESTABLISHED",
                    published_watermark=published,
                    derived_watermark=None,
                    query_start_date=query_start,
                    provider_semantic_fingerprint=row["provider_semantic_fingerprint"],
                    source_schema_fingerprint=row["source_schema_fingerprint"],
                    successful_run_id=row["successful_run_id"],
                    completed_at_utc=row["completed_at_utc"],
                )
        row = connection.execute(
            "SELECT MAX(lastupdated) FROM sharadar_fundamental_observation WHERE dimension IN ('ARQ','MRQ')"
        ).fetchone()
    derived = _iso_date(row[0] if row else None, "bootstrap_lastupdated")
    query_start = (date.fromisoformat(derived) - timedelta(days=OVERLAP_DAYS)).isoformat()
    return RefreshState(
        mode="BOOTSTRAP_BASELINE",
        published_watermark=None,
        derived_watermark=derived,
        query_start_date=query_start,
    )


def _require_api_success(result: SharadarResult, context: str) -> list[dict[str, Any]]:
    if not result.ok:
        raise RefreshPreviewError(
            f"SHARADAR_{context}_FAILED:{result.status}:HTTP_{result.http_status}:{result.error}"
        )
    return result.records


def source_schema(client: SharadarClient) -> dict[str, Any]:
    result = client.schema(SOURCE_TABLE)
    _require_api_success(result, "SCHEMA")
    fields = extract_schema_fields(result.payload)
    missing = sorted(set(REFRESH_REQUEST_FIELDS) - fields)
    if missing:
        raise RefreshPreviewError("SHARADAR_REFRESH_SCHEMA_MISSING:" + ",".join(missing))
    return {
        "dataset": SOURCE_DATASET,
        "table": SOURCE_TABLE,
        "endpoint": SOURCE_ENDPOINT,
        "field_count": len(fields),
        "required_fields": list(REFRESH_REQUEST_FIELDS),
        "schema_fingerprint": fingerprint(sorted(fields)),
    }


def _discovery_call(
    client: SharadarClient,
    *,
    dimension: str,
    filters: Mapping[str, str],
) -> list[dict[str, Any]]:
    result = client.fundamentals(
        dimension=dimension,
        fields=DISCOVERY_FIELDS,
        limit=DISCOVERY_LIMIT,
        filters=filters,
    )
    return _require_api_success(result, f"DISCOVERY_{dimension}")


def discover_changed_tickers(
    client: SharadarClient,
    *,
    query_start_date: str,
    today: date | None = None,
) -> dict[str, Any]:
    start = date.fromisoformat(query_start_date)
    end = today or datetime.now(timezone.utc).date()
    if start > end:
        raise RefreshPreviewError("DISCOVERY_START_AFTER_TODAY")
    rows: list[dict[str, Any]] = []
    partitioned = False
    for dimension in REFRESH_DIMENSIONS:
        initial = _discovery_call(
            client,
            dimension=dimension,
            filters={"lastupdated.gte": start.isoformat()},
        )
        if len(initial) < DISCOVERY_LIMIT:
            rows.extend(initial)
            continue
        partitioned = True
        current = start
        while current <= end:
            partition = _discovery_call(
                client,
                dimension=dimension,
                filters={"lastupdated": current.isoformat()},
            )
            if len(partition) >= DISCOVERY_LIMIT:
                raise DiscoveryIncompleteError(
                    f"DISCOVERY_INCOMPLETE:{dimension}:{current.isoformat()}:EXACT_LIMIT"
                )
            rows.extend(partition)
            current += timedelta(days=1)
    normalized: set[tuple[str, str, str]] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        dimension = str(row.get("dimension") or "").strip().upper()
        updated = _iso_date(row.get("lastupdated"), "lastupdated")
        if not ticker or dimension not in REFRESH_DIMENSIONS:
            raise RefreshPreviewError("MALFORMED_DISCOVERY_ROW")
        normalized.add((ticker, dimension, updated))
    ordered = sorted(normalized)
    return {
        "status": "COMPLETE",
        "query_start_date": start.isoformat(),
        "overlap_days": OVERLAP_DAYS,
        "partitioned": partitioned,
        "returned_source_rows": len(ordered),
        "unique_changed_source_tickers": len({row[0] for row in ordered}),
        "changed_tickers": sorted({row[0] for row in ordered}),
        "observed_source_max_lastupdated": max((row[2] for row in ordered), default=None),
        "dimensions": list(REFRESH_DIMENSIONS),
    }


def resolve_identity(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    ticker = ticker.upper()
    with _readonly(paths.canonical_db) as canonical:
        matches = canonical.execute(
            "SELECT DISTINCT s.security_id,s.company_id,s.current_ticker "
            "FROM security s LEFT JOIN ticker_alias a ON a.security_id=s.security_id "
            "WHERE UPPER(s.current_ticker)=? OR UPPER(a.ticker)=?",
            (ticker, ticker),
        ).fetchall()
        if len(matches) != 1:
            return {
                "status": "NOT_IN_CANONICAL_UNIVERSE" if not matches else "REVIEW_REQUIRED",
                "ticker": ticker,
                "reason": "NO_CANONICAL_IDENTITY" if not matches else "AMBIGUOUS_CANONICAL_IDENTITY",
            }
        match = matches[0]
        provider_ids = canonical.execute(
            "SELECT provider_security_id,provider_ticker FROM provider_security_identity "
            "WHERE provider='SHARADAR' AND security_id=?",
            (match["security_id"],),
        ).fetchall()
    with _readonly(paths.provider_db) as provider:
        metadata = provider.execute(
            "SELECT permaticker,isdelisted,relatedtickers,lastupdated FROM sharadar_ticker_metadata "
            "WHERE table_name='fundamentals' AND UPPER(ticker)=?",
            (ticker,),
        ).fetchall()
    metadata_ids = {str(row["permaticker"]) for row in metadata if row["permaticker"]}
    canonical_ids = {str(row["provider_security_id"]) for row in provider_ids if row["provider_security_id"]}
    if len(canonical_ids) != 1:
        return {
            "status": "REVIEW_REQUIRED",
            "ticker": ticker,
            "company_id": int(match["company_id"]),
            "security_id": int(match["security_id"]),
            "reason": "MISSING_OR_AMBIGUOUS_SHARADAR_IDENTITY",
        }
    if metadata_ids and metadata_ids != canonical_ids:
        return {
            "status": "REVIEW_REQUIRED",
            "ticker": ticker,
            "company_id": int(match["company_id"]),
            "security_id": int(match["security_id"]),
            "reason": "SHARADAR_METADATA_IDENTITY_MISMATCH",
        }
    return {
        "status": "KNOWN",
        "ticker": ticker,
        "company_id": int(match["company_id"]),
        "security_id": int(match["security_id"]),
        "current_ticker": str(match["current_ticker"]),
        "provider_security_id": next(iter(canonical_ids)),
        "metadata_available": bool(metadata),
    }


def fetch_complete_history(client: SharadarClient, ticker: str, dimension: str) -> HistoryTrust:
    result = client.fundamentals(
        ticker=ticker,
        dimension=dimension,
        limit=DISCOVERY_LIMIT,
    )
    if not result.ok:
        return HistoryTrust(
            status="FAILED",
            ticker=ticker,
            dimension=dimension,
            row_count=0,
            raw_fingerprint=None,
            effective_fingerprint=None,
            rows=(),
            errors=(f"{result.status}:HTTP_{result.http_status}:{result.error}",),
        )
    return validate_complete_history(
        result.records,
        ticker=ticker,
        dimension=dimension,
        response_reached_limit=len(result.records) >= DISCOVERY_LIMIT,
    )


def load_current_history(provider_db: Path, ticker: str, dimension: str) -> dict[str, Any]:
    columns = ",".join(f"s.{field}" for field in REFRESH_REQUEST_FIELDS)
    with _readonly(provider_db) as connection:
        rows = [dict(row) for row in connection.execute(
            f"SELECT po.observation_id,{columns} FROM sharadar_fundamental_observation s "
            "JOIN provider_observation po USING(observation_id) "
            "WHERE UPPER(s.ticker)=? AND s.dimension=? "
            "ORDER BY s.lastupdated,po.observation_id",
            (ticker.upper(), dimension.upper()),
        )]
    normalized: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    invalid: list[str] = []
    duplicates = 0
    for row in rows:
        try:
            item = normalize_source_row(row, expected_ticker=ticker, expected_dimension=dimension)
        except HistoryValidationError as exc:
            invalid.append(f"{row.get('observation_id')}:{exc}")
            continue
        key = source_key(item)
        if key in normalized:
            duplicates += 1
        normalized[key] = item
    ordered = tuple(normalized[key] for key in sorted(normalized))
    hashes = history_fingerprints(ordered)
    return {
        "rows": ordered,
        "physical_row_count": len(rows),
        "current_row_count": len(ordered),
        "legacy_versions_collapsed": duplicates,
        "invalid_rows": invalid,
        **hashes,
    }


def _row_maps(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str, str, str], Mapping[str, Any]]:
    return {source_key(row): row for row in rows}


def _latest_fiscal(rows: Iterable[Mapping[str, Any]], dimension: str = "ARQ") -> tuple[int, str] | None:
    identities = [fiscal_identity(row["fiscalperiod"]) for row in rows if row.get("dimension") == dimension]
    return max(identities, key=lambda item: (item[0], int(item[1][1]))) if identities else None


def _fiscal_label(value: tuple[int, str] | None) -> str | None:
    return f"{value[0]} {value[1]}" if value else None


def compare_ticker_histories(
    ticker: str,
    current: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, HistoryTrust],
) -> dict[str, Any]:
    if any(source[dimension].status != "COMPLETE" for dimension in REFRESH_DIMENSIONS):
        return {
            "ticker": ticker,
            "classification": "REVIEW_REQUIRED",
            "review_reason": "COMPLETE_HISTORY_NOT_TRUSTED",
            "source_completeness": {dimension: source[dimension].evidence() for dimension in REFRESH_DIMENSIONS},
        }
    if any(current[dimension].get("invalid_rows") for dimension in REFRESH_DIMENSIONS):
        return {
            "ticker": ticker,
            "classification": "REVIEW_REQUIRED",
            "review_reason": "CURRENT_PROVIDER_HISTORY_INVALID",
            "source_completeness": {dimension: source[dimension].evidence() for dimension in REFRESH_DIMENSIONS},
        }
    added: list[tuple[str, str, str, str]] = []
    removed: list[tuple[str, str, str, str]] = []
    effective_changed: list[tuple[str, str, str, str]] = []
    metadata_changed: list[tuple[str, str, str, str]] = []
    for dimension in REFRESH_DIMENSIONS:
        old_map = _row_maps(current[dimension]["rows"])
        new_map = _row_maps(source[dimension].rows)
        added.extend(sorted(new_map.keys() - old_map.keys()))
        removed.extend(sorted(old_map.keys() - new_map.keys()))
        for key in sorted(old_map.keys() & new_map.keys()):
            if fingerprint(_effective_row(old_map[key])) != fingerprint(_effective_row(new_map[key])):
                effective_changed.append(key)
            elif fingerprint(_raw_row(old_map[key])) != fingerprint(_raw_row(new_map[key])):
                metadata_changed.append(key)
    current_rows = tuple(row for dimension in REFRESH_DIMENSIONS for row in current[dimension]["rows"])
    source_rows = tuple(row for dimension in REFRESH_DIMENSIONS for row in source[dimension].rows)
    old_latest = _latest_fiscal(current_rows)
    new_latest = _latest_fiscal(source_rows)
    affected_fiscal = {
        fiscal_identity(old_map[key]["fiscalperiod"])
        for dimension in REFRESH_DIMENSIONS
        for old_map, new_map in [(_row_maps(current[dimension]["rows"]), _row_maps(source[dimension].rows))]
        for key in old_map
        if key not in new_map or (
            key in new_map
            and fingerprint(_effective_row(old_map[key])) != fingerprint(_effective_row(new_map[key]))
        )
    }
    affected_fiscal.update(
        fiscal_identity(new_map[key]["fiscalperiod"])
        for dimension in REFRESH_DIMENSIONS
        for old_map, new_map in [(_row_maps(current[dimension]["rows"]), _row_maps(source[dimension].rows))]
        for key in new_map
        if key not in old_map or (
            key in old_map
            and fingerprint(_effective_row(old_map[key])) != fingerprint(_effective_row(new_map[key]))
        )
    )
    advanced = bool(new_latest and (old_latest is None or (new_latest[0], int(new_latest[1][1])) > (old_latest[0], int(old_latest[1][1]))))
    prior_change = bool(effective_changed or removed or (added and not advanced))
    if not added and not removed and not effective_changed:
        classification = "SOURCE_ONLY_METADATA_CHANGE" if metadata_changed else "NO_EFFECTIVE_CHANGE"
    elif advanced and prior_change:
        classification = "NEW_QUARTER_AND_REVISION"
    elif advanced:
        classification = "NEW_QUARTER"
    elif removed:
        classification = "SOURCE_REMOVAL"
    else:
        classification = "HISTORICAL_REVISION"
    return {
        "ticker": ticker,
        "classification": classification,
        "old_latest_fiscal_quarter": _fiscal_label(old_latest),
        "new_latest_fiscal_quarter": _fiscal_label(new_latest),
        "latest_quarter_advanced": advanced,
        "added_count": len(added),
        "changed_count": len(effective_changed),
        "removed_count": len(removed),
        "metadata_only_count": len(metadata_changed),
        "added_keys": [dict(zip(SOURCE_PRIMARY_KEY, key, strict=True)) for key in added],
        "changed_keys": [dict(zip(SOURCE_PRIMARY_KEY, key, strict=True)) for key in effective_changed],
        "removed_keys": [dict(zip(SOURCE_PRIMARY_KEY, key, strict=True)) for key in removed],
        "metadata_only_keys": [dict(zip(SOURCE_PRIMARY_KEY, key, strict=True)) for key in metadata_changed],
        "affected_fiscal_quarters": [
            {"fiscal_year": item[0], "fiscal_quarter": item[1]} for item in sorted(affected_fiscal)
        ],
        "current_counts": {dimension: int(current[dimension]["current_row_count"]) for dimension in REFRESH_DIMENSIONS},
        "source_counts": {dimension: source[dimension].row_count for dimension in REFRESH_DIMENSIONS},
        "current_effective_fingerprint": fingerprint({dimension: current[dimension]["effective_content_fingerprint"] for dimension in REFRESH_DIMENSIONS}),
        "source_effective_fingerprint": combined_effective_history_fingerprint(source),
        "source_raw_fingerprints": {dimension: source[dimension].raw_fingerprint for dimension in REFRESH_DIMENSIONS},
        "source_completeness": {dimension: source[dimension].evidence() for dimension in REFRESH_DIMENSIONS},
        "legacy_versions_collapsed": sum(int(current[dimension]["legacy_versions_collapsed"]) for dimension in REFRESH_DIMENSIONS),
    }


def _provider_winner_dates(provider_db: Path) -> dict[tuple[int, int, str], str]:
    with _readonly(provider_db) as connection:
        rows = connection.execute(
            "SELECT po.company_id,po.observation_id,s.fiscalperiod,s.reportperiod,s.date,s.lastupdated "
            "FROM sharadar_fundamental_observation s JOIN provider_observation po USING(observation_id) "
            "WHERE s.dimension='ARQ' AND po.company_id IS NOT NULL "
            "ORDER BY po.company_id,s.fiscalperiod,s.reportperiod DESC,COALESCE(s.lastupdated,s.date,'') DESC,po.observation_id"
        ).fetchall()
    winners: dict[tuple[int, int, str], str] = {}
    for row in rows:
        try:
            year, quarter = fiscal_identity(row["fiscalperiod"])
            source_date = _iso_date(row["date"], "date")
        except HistoryValidationError:
            continue
        winners.setdefault((int(row["company_id"]), year, quarter), source_date)
    return winners


def audit_publish_date_bootstrap(paths: BatchAddTickerPaths) -> dict[str, Any]:
    winners = _provider_winner_dates(paths.provider_db)
    counts: Counter[str] = Counter()
    exceptions: list[dict[str, Any]] = []
    with _readonly(paths.canonical_db) as connection:
        rows = connection.execute(
            "SELECT q.quarter_id,q.company_id,q.fiscal_year,q.fiscal_quarter,q.period_end,"
            "q.source_availability_date,q.first_public_result_date,"
            "(SELECT MIN(s.current_ticker) FROM security s WHERE s.company_id=q.company_id AND s.active=1) current_ticker "
            "FROM v4_quarter q "
            "ORDER BY q.company_id,q.fiscal_year,q.fiscal_quarter"
        ).fetchall()
    for row in rows:
        key = (int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"]))
        availability = str(row["source_availability_date"] or "")
        first_public = str(row["first_public_result_date"] or "")
        winner_date = winners.get(key)
        reason = None
        proposed = None
        if first_public:
            try:
                _iso_date(first_public, "first_public_result_date")
                counts["ALREADY_ESTABLISHED"] += 1
            except HistoryValidationError:
                reason = "INVALID_EXISTING_FIRST_PUBLIC_RESULT_DATE"
        else:
            try:
                parsed = _iso_date(availability, "source_availability_date")
                if parsed < str(row["period_end"]):
                    reason = "AVAILABILITY_BEFORE_PERIOD_END"
                elif winner_date != parsed:
                    reason = "AVAILABILITY_DOES_NOT_MATCH_CURRENT_WINNER_DATE"
                else:
                    proposed = parsed
                    counts["BOOTSTRAP_ELIGIBLE"] += 1
            except HistoryValidationError:
                reason = "INVALID_SOURCE_AVAILABILITY_DATE"
        if reason:
            counts["REPAIR_REQUIRED"] += 1
            exceptions.append({
                "quarter_id": int(row["quarter_id"]),
                "company_id": key[0],
                "ticker": row["current_ticker"],
                "fiscal_year": key[1],
                "fiscal_quarter": key[2],
                "source_availability_date": availability or None,
                "first_public_result_date": first_public or None,
                "current_winner_date": winner_date,
                "proposed_first_public_result_date": proposed,
                "status": "REPAIR_REQUIRED",
                "reason": reason,
            })
    return {
        "contract": {
            "stable_quarter_identity": ["company_id", "fiscal_year", "fiscal_quarter"],
            "source_availability_date": "MAY_FOLLOW_CURRENT_WINNING_SHARADAR_DATE",
            "first_public_result_date": "IMMUTABLE_DURING_ROUTINE_REFRESH_AFTER_BOOTSTRAP",
            "explicit_repair_required_to_change_first_public_result_date": True,
        },
        "total_quarters": len(rows),
        "counts": dict(counts),
        "exception_count": len(exceptions),
        "exceptions": exceptions,
        "all_current_quarters_bootstrap_eligible": not exceptions,
    }


def publish_date_impact(
    paths: BatchAddTickerPaths,
    *,
    identity: Mapping[str, Any],
    comparison: Mapping[str, Any],
    source_arq_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    affected = {
        (int(item["fiscal_year"]), str(item["fiscal_quarter"]))
        for item in comparison.get("affected_fiscal_quarters") or []
    }
    with _readonly(paths.canonical_db) as connection:
        existing = {
            (int(row["fiscal_year"]), str(row["fiscal_quarter"])): dict(row)
            for row in connection.execute(
                "SELECT fiscal_year,fiscal_quarter,source_availability_date,first_public_result_date "
                "FROM v4_quarter WHERE company_id=?",
                (identity["company_id"],),
            )
        }
    output: list[dict[str, Any]] = []
    source_winners: dict[tuple[int, str], Mapping[str, Any]] = {}
    for row in sorted(source_arq_rows, key=lambda item: (str(item.get("reportperiod")), str(item.get("lastupdated")), str(item.get("date"))), reverse=True):
        source_winners.setdefault(fiscal_identity(row["fiscalperiod"]), row)
    for fiscal in sorted(affected):
        current = existing.get(fiscal)
        winner = source_winners.get(fiscal, {})
        if current:
            established = current.get("first_public_result_date")
            baseline = established or current.get("source_availability_date")
            policy = "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE" if established else "BOOTSTRAP_FIRST_PUBLIC_RESULT_DATE_ON_COPY"
            output.append({
                "ticker": identity["ticker"],
                "company_id": identity["company_id"],
                "fiscal_year": fiscal[0],
                "fiscal_quarter": fiscal[1],
                "existing_source_availability_date": current.get("source_availability_date"),
                "existing_first_public_result_date": established,
                "proposed_first_public_result_date_baseline": baseline,
                "source_date": winner.get("date"),
                "source_lastupdated": winner.get("lastupdated"),
                "source_availability_date_would_drift": bool(winner.get("date") and winner.get("date") != current.get("source_availability_date")),
                "policy_result": policy,
            })
        else:
            output.append({
                "ticker": identity["ticker"],
                "company_id": identity["company_id"],
                "fiscal_year": fiscal[0],
                "fiscal_quarter": fiscal[1],
                "existing_source_availability_date": None,
                "existing_first_public_result_date": None,
                "proposed_first_public_result_date_baseline": None,
                "source_date": winner.get("date"),
                "source_lastupdated": winner.get("lastupdated"),
                "policy_result": "ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY",
            })
    return output


def provider_key_diagnostics(provider_db: Path) -> dict[str, Any]:
    with _readonly(provider_db) as connection:
        rows = connection.execute(
            "SELECT po.provider_record_key,s.ticker,s.dimension,s.date,s.reportperiod "
            "FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id)"
        ).fetchall()
    legacy = Counter(str(row["provider_record_key"]) for row in rows)
    true_keys: Counter[tuple[str, str, str, str]] = Counter()
    clean = 0
    for row in rows:
        key = source_key(dict(row))
        if all(key):
            clean += 1
            true_keys[key] += 1
    return {
        "provider_observation_count": len(rows),
        "legacy_provider_record_key_groups": len(legacy),
        "repeated_legacy_key_groups": sum(1 for count in legacy.values() if count > 1),
        "rows_mapping_cleanly_to_true_source_key": clean,
        "rows_not_mapping_cleanly_to_true_source_key": len(rows) - clean,
        "true_source_key_groups": len(true_keys),
        "true_source_key_duplicate_groups": sum(1 for count in true_keys.values() if count > 1),
        "true_source_key_extra_versions": sum(count - 1 for count in true_keys.values() if count > 1),
    }


def _production_file_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for role, path in paths.as_dict().items():
        stat = path.stat()
        output[role] = {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return output


def _request() -> AdminBatchRequest:
    return AdminBatchRequest(
        operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
        requested_inputs=(),
        normalized_inputs=(),
        options={"contract_version": CONTRACT_VERSION, "read_only": True},
    )


def _summary_counts(changes: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(change.get("classification") or "UNKNOWN") for change in changes)
    counts["discovered"] = len(changes)
    counts["effective_changed_known"] = sum(
        count for key, count in counts.items()
        if key in {"NEW_QUARTER", "HISTORICAL_REVISION", "NEW_QUARTER_AND_REVISION", "SOURCE_REMOVAL"}
    )
    return dict(counts)


def _render_refresh_report(result: Mapping[str, Any]) -> str:
    counts = result.get("summary_counts") or {}
    discovery = result.get("refresh_preview", {}).get("discovery", {})
    lines = [
        "# Refresh Fundamentals Preview",
        "",
        f"Outcome: **{result.get('outcome')}**",
        "",
        "## Executive Summary",
        "",
        f"- Sharadar discovery rows: `{discovery.get('returned_source_rows', 0)}`",
        f"- Changed source tickers: `{discovery.get('unique_changed_source_tickers', 0)}`",
        f"- Known tickers with effective changes: `{counts.get('effective_changed_known', 0)}`",
        f"- Unknown tickers: `{counts.get('NOT_IN_CANONICAL_UNIVERSE', 0)}`",
        f"- Review required: `{counts.get('REVIEW_REQUIRED', 0)}`",
        "",
        "## Discovery",
        "",
        f"- State: `{result.get('refresh_preview', {}).get('state', {}).get('mode')}`",
        f"- Query start: `{discovery.get('query_start_date')}`",
        f"- Observed source maximum: `{discovery.get('observed_source_max_lastupdated')}`",
        f"- Schema fingerprint: `{result.get('refresh_preview', {}).get('schema', {}).get('schema_fingerprint')}`",
        "",
        "## Effective Known-Ticker Changes",
        "",
        "| Ticker | Current latest Q | Sharadar latest Q | Change | ARQ before/after | Added | Changed | Removed | Publish date |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in result.get("refresh_preview", {}).get("ticker_changes", []):
        if item.get("classification") not in {"NEW_QUARTER", "HISTORICAL_REVISION", "NEW_QUARTER_AND_REVISION", "SOURCE_REMOVAL"}:
            continue
        impacts = item.get("publish_date_impact") or []
        policy = "New Q" if any(row.get("policy_result") == "ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY" for row in impacts) else "Baseline preserved"
        lines.append(
            f"| {item.get('ticker')} | {item.get('old_latest_fiscal_quarter') or '-'} | "
            f"{item.get('new_latest_fiscal_quarter') or '-'} | {str(item.get('classification')).replace('_', ' ').title()} | "
            f"{item.get('current_counts', {}).get('ARQ', 0)}/{item.get('source_counts', {}).get('ARQ', 0)} | "
            f"{item.get('added_count', 0)} | {item.get('changed_count', 0)} | {item.get('removed_count', 0)} | {policy} |"
        )
    lines.extend([
        "",
        "## Publication-Date Contract",
        "",
        "- `source_availability_date` may follow the current winning Sharadar row.",
        "- `first_public_result_date` will be bootstrapped on copies in Phase 13G.3.3.",
        "- After bootstrap, routine Refresh preserves `first_public_result_date` by `(company_id, fiscal_year, fiscal_quarter)`.",
        "- Only an explicit repair operation may change that preserved date.",
        "",
        "## Safety",
        "",
        "- This run was read-only for every production database.",
        "- No refresh state or watermark was advanced.",
        f"- Refresh-set fingerprint: `{result.get('preview_fingerprint')}`",
    ])
    return "\n".join(lines) + "\n"


def run_preview(
    *,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    client: SharadarClient | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    request = _request()
    state = resolve_refresh_state(source_paths.provider_db)
    request_fp = fingerprint({"request": request.as_dict(), "state": state.as_dict()})
    run_id = stable_run_id(AdminOperationType.REFRESH_FUNDAMENTALS, request_fp)
    api = client or SharadarClient()
    writer = AdminRunWriter(run_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=run_root)
    progress = ProgressTracker(
        run_id=run_id,
        operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
        run_dir=writer.run_dir,
        stages=REFRESH_FUNDAMENTALS_STAGES,
        callback=progress_callback,
    )
    started = utc_now()
    before = _production_file_state(source_paths)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Refresh Fundamentals Preview request recorded.")
    writer.write_json("request.json", request.as_dict())
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Read-only Sharadar refresh discovery started.")
    failed_stage = ProgressStage.REFRESH_STATE
    try:
        progress.running(ProgressStage.REFRESH_STATE, "Resolving published or bootstrap refresh state.")
        progress.completed(ProgressStage.REFRESH_STATE, f"Refresh state resolved as {state.mode}.")

        failed_stage = ProgressStage.SOURCE_SCHEMA
        progress.running(ProgressStage.SOURCE_SCHEMA, "Validating the Sharadar Fundamentals source schema.")
        schema = source_schema(api)
        progress.completed(ProgressStage.SOURCE_SCHEMA, "Sharadar source schema validated.")

        failed_stage = ProgressStage.CHANGE_DISCOVERY
        progress.running(ProgressStage.CHANGE_DISCOVERY, "Discovering ARQ/MRQ source changes from the inclusive overlap window.")
        discovery = discover_changed_tickers(api, query_start_date=state.query_start_date)
        progress.completed(
            ProgressStage.CHANGE_DISCOVERY,
            "Sharadar change discovery completed.",
            processed_items=discovery["unique_changed_source_tickers"],
            total_items=discovery["unique_changed_source_tickers"],
            processed_rows=discovery["returned_source_rows"],
        )

        failed_stage = ProgressStage.IDENTITY_RESOLUTION
        tickers = discovery["changed_tickers"]
        progress.running(ProgressStage.IDENTITY_RESOLUTION, "Resolving changed tickers to stable canonical identities.", processed_items=0, total_items=len(tickers))
        identities = {ticker: resolve_identity(source_paths, ticker) for ticker in tickers}
        progress.completed(ProgressStage.IDENTITY_RESOLUTION, "Canonical identity resolution completed.", processed_items=len(tickers), total_items=len(tickers))

        failed_stage = ProgressStage.COMPLETE_HISTORY_FETCH
        known = [ticker for ticker in tickers if identities[ticker]["status"] == "KNOWN"]
        histories: dict[str, dict[str, HistoryTrust]] = {}
        progress.running(ProgressStage.COMPLETE_HISTORY_FETCH, "Fetching complete ARQ/MRQ histories for known changed tickers.", processed_items=0, total_items=len(known))
        for index, ticker in enumerate(known, start=1):
            histories[ticker] = {dimension: fetch_complete_history(api, ticker, dimension) for dimension in REFRESH_DIMENSIONS}
            progress.running(
                ProgressStage.COMPLETE_HISTORY_FETCH,
                f"Fetched complete-history responses for {ticker}.",
                processed_items=index,
                total_items=len(known),
            )
        progress.completed(ProgressStage.COMPLETE_HISTORY_FETCH, "Complete-history acquisition finished.", processed_items=len(known), total_items=len(known))

        failed_stage = ProgressStage.SOURCE_COMPARISON
        progress.running(ProgressStage.SOURCE_COMPARISON, "Comparing current provider state with complete source histories.", processed_items=0, total_items=len(known))
        changes: list[dict[str, Any]] = []
        for index, ticker in enumerate(known, start=1):
            current = {dimension: load_current_history(source_paths.provider_db, ticker, dimension) for dimension in REFRESH_DIMENSIONS}
            comparison = compare_ticker_histories(ticker, current, histories[ticker])
            comparison["identity"] = identities[ticker]
            if comparison["classification"] != "REVIEW_REQUIRED":
                comparison["publish_date_impact"] = publish_date_impact(
                    source_paths,
                    identity=identities[ticker],
                    comparison=comparison,
                    source_arq_rows=histories[ticker]["ARQ"].rows,
                )
            changes.append(comparison)
            progress.running(ProgressStage.SOURCE_COMPARISON, f"Compared {ticker}.", processed_items=index, total_items=len(known))
        for ticker in tickers:
            if identities[ticker]["status"] == "KNOWN":
                continue
            changes.append({
                "ticker": ticker,
                "classification": identities[ticker]["status"],
                "review_reason": identities[ticker].get("reason"),
                "identity": identities[ticker],
            })
        progress.completed(ProgressStage.SOURCE_COMPARISON, "Provider/source comparison completed.", processed_items=len(known), total_items=len(known))

        failed_stage = ProgressStage.CLASSIFICATION
        progress.running(ProgressStage.CLASSIFICATION, "Finalizing classifications and publication-date bootstrap evidence.")
        changes.sort(key=lambda item: str(item.get("ticker")))
        counts = _summary_counts(changes)
        bootstrap = audit_publish_date_bootstrap(source_paths)
        legacy = provider_key_diagnostics(source_paths.provider_db)
        replacement_classes = {"NEW_QUARTER", "HISTORICAL_REVISION", "NEW_QUARTER_AND_REVISION", "SOURCE_REMOVAL"}
        replacement = [item for item in changes if item.get("classification") in replacement_classes]
        review = [item for item in changes if item.get("classification") == "REVIEW_REQUIRED"]
        unknown = [item for item in changes if item.get("classification") == "NOT_IN_CANONICAL_UNIVERSE"]
        binding = {
            "contract_version": CONTRACT_VERSION,
            "dataset": SOURCE_DATASET,
            "table": SOURCE_TABLE,
            "schema_fingerprint": schema["schema_fingerprint"],
            "state_mode": state.mode,
            "published_watermark": state.published_watermark,
            "derived_watermark": state.derived_watermark,
            "query_start_date": state.query_start_date,
            "observed_source_max_lastupdated": discovery["observed_source_max_lastupdated"],
            "ticker_changes": [
                {
                    key: item.get(key)
                    for key in (
                        "ticker", "classification", "current_effective_fingerprint",
                        "source_effective_fingerprint", "source_raw_fingerprints",
                        "added_count", "changed_count", "removed_count", "metadata_only_count",
                    )
                }
                for item in changes
            ],
        }
        refresh_set_fingerprint = fingerprint(binding)
        progress.completed(ProgressStage.CLASSIFICATION, "Classifications and deterministic binding evidence completed.")

        failed_stage = ProgressStage.REPORT
        progress.running(ProgressStage.REPORT, "Writing durable Preview artifacts and report.")
        preview = {
            "contract_version": CONTRACT_VERSION,
            "read_only": True,
            "state": state.as_dict(),
            "schema": schema,
            "discovery": discovery,
            "ticker_changes": changes,
            "refresh_set_fingerprint": refresh_set_fingerprint,
            "future_test_authorized": not review and discovery["status"] == "COMPLETE",
            "published_watermark_advanced": False,
            "provider_key_diagnostics": legacy,
            "publish_date_bootstrap": {key: value for key, value in bootstrap.items() if key != "exceptions"},
        }
        preview_path = writer.write_json("refresh_preview.json", preview)
        changes_path = writer.write_json("refresh_ticker_changes.json", changes)
        unknown_path = writer.write_json("refresh_unknown_tickers.json", unknown)
        review_path = writer.write_json("refresh_review_required.json", review)
        bootstrap_path = writer.write_json("publish_date_bootstrap_exceptions.json", bootstrap)
        outcome = AdminStatus.NO_CHANGE if not replacement and not review else (AdminStatus.REVIEW_REQUIRED if review else AdminStatus.COMPLETED)
        decisions = tuple(
            AdminItemDecision(
                item_key=str(item["ticker"]),
                requested_value=str(item["ticker"]),
                normalized_value=str(item["ticker"]),
                status=(
                    AdminStatus.REVIEW_REQUIRED if item["classification"] in {"REVIEW_REQUIRED", "NOT_IN_CANONICAL_UNIVERSE"}
                    else AdminStatus.NO_CHANGE if item["classification"] in {"NO_EFFECTIVE_CHANGE", "SOURCE_ONLY_METADATA_CHANGE"}
                    else AdminStatus.ELIGIBLE
                ),
                reason=str(item["classification"]).replace("_", " ").title(),
                source_category="Sharadar current API",
                details=item,
            )
            for item in changes
        )
        result_obj = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
            outcome=outcome,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=refresh_set_fingerprint,
            request=request.as_dict(),
            item_results=decisions,
            summary_counts=counts,
            rollback={"status": "NOT_REQUIRED", "write_boundary_crossed": False},
            downstream={"provider": "READ_ONLY", "canonical": "NOT_RUN", "analysis": "NOT_RUN"},
            artifacts={
                "refresh_preview": str(preview_path),
                "ticker_changes": str(changes_path),
                "unknown_tickers": str(unknown_path),
                "review_required": str(review_path),
                "publish_date_bootstrap": str(bootstrap_path),
            },
            recommended_next_action=(
                "No relevant Sharadar fundamentals changes since the previous successful refresh."
                if outcome == AdminStatus.NO_CHANGE
                else "Resolve review items before a future Test on copies."
                if review
                else "Review the read-only Preview. Test on copies is not implemented until Phase 13G.3.3."
            ),
        )
        result = result_obj.as_dict() | {
            "artifact_dir": str(writer.run_dir),
            "preview_payload_path": str(preview_path),
            "refresh_preview": preview,
            "network_used": True,
            "database_safety": "NO_DATABASE_WRITES",
        }
        after = _production_file_state(source_paths)
        result["production_file_state_unchanged"] = before == after
        if before != after:
            raise RefreshPreviewError("PRODUCTION_FILE_STATE_CHANGED_DURING_READ_ONLY_PREVIEW")
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_refresh_report(result))
        writer.checkpoint(RunStage.PREVIEW_READY, message="Refresh Fundamentals Preview ready.", preview_fingerprint=refresh_set_fingerprint, counters=counts)
        writer.checkpoint(RunStage.COMPLETED, message="Read-only Refresh Fundamentals Preview completed.", preview_fingerprint=refresh_set_fingerprint)
        progress.completed(ProgressStage.REPORT, "Durable Preview artifacts written.")
        progress.running(ProgressStage.COMPLETED, "Refresh Fundamentals Preview completed.")
        progress.completed(ProgressStage.COMPLETED, "Refresh Fundamentals Preview completed.")
        writer.write_exit_code(0)
        writer.write_manifest()
        return result
    except Exception as exc:
        writer.write_error(exc)
        progress.failed(failed_stage, "Refresh Fundamentals Preview failed before any database write.", errors=(f"{type(exc).__name__}: {exc}",))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message="Refresh Fundamentals Preview failed before any write boundary.")
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
            outcome=AdminStatus.FAILED,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            summary_counts={"failed": 1},
            rollback={"status": "NOT_REQUIRED", "write_boundary_crossed": False},
            artifacts={"error": str(writer.run_dir / "error.json")},
            recommended_next_action="Review the sanitized provider error and retry Preview.",
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        ).as_dict() | {
            "artifact_dir": str(writer.run_dir),
            "failed_stage": failed_stage.value,
            "database_safety": "NO_DATABASE_WRITES",
            "production_file_state_unchanged": before == _production_file_state(source_paths),
        }
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_refresh_report(result))
        writer.write_exit_code(2)
        writer.write_manifest()
        return result
