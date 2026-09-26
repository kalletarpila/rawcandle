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
from rawcandle.fundamentals.schema.sharadar_history_policy import MINIMUM_HISTORY_YEARS


CONTRACT_VERSION = "PHASE13G3_10_RETENTION_BOUNDARY_SEMANTICS_V1"
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
RETAINED_OUTSIDE_SOURCE_WINDOW = "RETAINED_OUTSIDE_SOURCE_WINDOW"
AGED_OUT_OF_SOURCE_WINDOW = "AGED_OUT_OF_SOURCE_WINDOW"
TRUE_SOURCE_REMOVAL = "TRUE_SOURCE_REMOVAL"
AMBIGUOUS_SOURCE_REMOVAL = "AMBIGUOUS_SOURCE_REMOVAL"
SOURCE_HISTORY_CHANGE = "SOURCE_HISTORY_CHANGE"
FISCAL_IDENTITY_REVISION = "FISCAL_IDENTITY_REVISION"
REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION = "REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION"
RETENTION_CONTRACT_VERSION = "SHARADAR_ROLLING_SOURCE_WINDOW_RETENTION_V2"
MINIMUM_QUARTER_BOUNDARY_SPAN = MINIMUM_HISTORY_YEARS * 4 + 1
REFRESH_REPLACEMENT_CLASSES = {
    "NEW_QUARTER", "HISTORICAL_REVISION", "NEW_QUARTER_AND_REVISION",
    "SOURCE_REMOVAL", SOURCE_HISTORY_CHANGE,
}
REFRESH_BINDING_FIELDS = (
    "ticker", "classification", "current_effective_fingerprint",
    "source_effective_fingerprint", "source_raw_fingerprints", "added_count",
    "changed_count", "removed_count", "metadata_only_count",
    "current_generation_fingerprint", "merged_generation_fingerprint",
    "retention_plan_fingerprint", "source_history_action",
    "fiscal_identity_revisions",
)

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
        has_active_universe = canonical.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='fundamentals_operational_universe_active_version'"
        ).fetchone() is not None
        if has_active_universe:
            matches = canonical.execute(
                "SELECT DISTINCT s.security_id,s.company_id,s.current_ticker "
                "FROM fundamentals_operational_universe_active_version av "
                "JOIN fundamentals_operational_universe_member m USING(universe_version_id) "
                "JOIN security s ON s.security_id=m.security_id "
                "LEFT JOIN ticker_alias a ON a.security_id=s.security_id "
                "WHERE av.singleton=1 AND (UPPER(s.current_ticker)=? OR UPPER(a.ticker)=?)",
                (ticker, ticker),
            ).fetchall()
        else:
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
        provider_columns = {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(provider_observation)")
        }
        provenance = "po.provenance_json" if "provenance_json" in provider_columns else "'{}' AS provenance_json"
        rows = [dict(row) for row in connection.execute(
            f"SELECT po.observation_id,{provenance},{columns} FROM sharadar_fundamental_observation s "
            "JOIN provider_observation po USING(observation_id) "
            "WHERE UPPER(s.ticker)=? AND s.dimension=? "
            "ORDER BY s.lastupdated,po.observation_id",
            (ticker.upper(), dimension.upper()),
        )]
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    invalid: list[str] = []
    for row in rows:
        try:
            item = normalize_source_row(row, expected_ticker=ticker, expected_dimension=dimension)
            parsed = json.loads(str(row.get("provenance_json") or "{}"))
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
            item["_provider_provenance"] = parsed
            item["_history_retention_status"] = parsed.get("history_retention_status")
            item["_history_retention_evidence"] = parsed.get("history_retention_evidence")
        except HistoryValidationError as exc:
            invalid.append(f"{row.get('observation_id')}:{exc}")
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            invalid.append(f"{row.get('observation_id')}:INVALID_PROVIDER_PROVENANCE:{exc}")
            continue
        grouped.setdefault(source_key(item), []).append(item)
    normalized: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    ambiguities: list[dict[str, Any]] = []
    for key, versions in grouped.items():
        maximum = max(str(item["lastupdated"]) for item in versions)
        latest = [item for item in versions if str(item["lastupdated"]) == maximum]
        effective = {fingerprint(_effective_row(item)) for item in latest}
        if len(effective) > 1:
            ambiguities.append({
                "source_key": source_key_evidence(dict(zip(SOURCE_PRIMARY_KEY, key, strict=True))),
                "maximum_lastupdated": maximum,
                "conflicting_version_count": len(latest),
                "reason": "LEGACY_SOURCE_VERSION_AMBIGUITY",
            })
            continue
        normalized[key] = min(
            latest,
            key=lambda item: (
                item.get("_history_retention_status") == RETAINED_OUTSIDE_SOURCE_WINDOW,
                fingerprint(_raw_row(item)),
            ),
        )
    ordered = tuple(normalized[key] for key in sorted(normalized))
    hashes = history_fingerprints(ordered)
    return {
        "rows": ordered,
        "physical_row_count": len(rows),
        "current_row_count": len(ordered),
        "legacy_versions_collapsed": sum(max(0, len(items) - 1) for items in grouped.values()),
        "legacy_source_version_ambiguities": ambiguities,
        "invalid_rows": invalid,
        **hashes,
    }


def _row_order(row: Mapping[str, Any]) -> tuple[str, str, tuple[str, str, str, str]]:
    return str(row.get("reportperiod") or ""), str(row.get("date") or ""), source_key(row)


def _fiscal_quarter_index(value: str) -> int:
    year, quarter = fiscal_identity(value)
    return year * 4 + int(quarter[1])


def _quarter_boundary_span(row: Mapping[str, Any], source_rows: Sequence[Mapping[str, Any]]) -> int:
    if not source_rows:
        return 0
    latest = max(source_rows, key=lambda item: _fiscal_quarter_index(str(item["fiscalperiod"])))
    return _fiscal_quarter_index(str(latest["fiscalperiod"])) - _fiscal_quarter_index(
        str(row["fiscalperiod"])
    ) + 1


def _generation_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    payload = [
        {
            "source": _effective_row(row),
            "history_retention_status": row.get("_history_retention_status"),
            "history_retention_evidence": row.get("_history_retention_evidence"),
        }
        for row in sorted(rows, key=source_key)
    ]
    return fingerprint(payload)


def _retention_evidence(
    row: Mapping[str, Any], *, event: Mapping[str, Any],
) -> dict[str, Any]:
    year, quarter = fiscal_identity(row["fiscalperiod"])
    return {
        "classification": AGED_OUT_OF_SOURCE_WINDOW,
        "classification_reason": event["classification_reason"],
        "source_identity": source_key_evidence(row),
        "fiscal_identity": {"fiscal_year": year, "fiscal_quarter": quarter},
        "source_window_boundary": {
            "dimension": str(row["dimension"]),
            "prior_min_reportperiod": event["prior_min_reportperiod"],
            "current_min_reportperiod": event["current_min_reportperiod"],
            "current_max_reportperiod": event["current_max_reportperiod"],
            "boundary_fiscal_quarter_span": event["boundary_fiscal_quarter_span"],
            "minimum_quarter_boundary_span": MINIMUM_QUARTER_BOUNDARY_SPAN,
            "minimum_requested_history_years": MINIMUM_HISTORY_YEARS,
        },
        "previously_accepted_source": "SHARADAR",
    }


def _is_deterministic_replacement_with_aged_companion(
    ticker: str,
    events: Sequence[Mapping[str, Any]],
    source: Mapping[str, HistoryTrust],
) -> bool:
    if len(events) != 2 or any(
        source[dimension].status != "COMPLETE"
        or source[dimension].ticker != ticker.upper()
        or source[dimension].dimension != dimension
        for dimension in REFRESH_DIMENSIONS
    ):
        return False
    replacement = [
        event for event in events
        if event.get("event") == TRUE_SOURCE_REMOVAL
        and event.get("classification_reason") == "SAME_FISCAL_SOURCE_KEY_REPLACEMENT"
    ]
    aged = [
        event for event in events
        if event.get("event") == AGED_OUT_OF_SOURCE_WINDOW
        and event.get("classification_reason") == "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW"
    ]
    if len(replacement) != 1 or len(aged) != 1:
        return False
    replacement_event = replacement[0]
    aged_event = aged[0]
    event_dimensions = {
        replacement_event.get("dimension"), aged_event.get("dimension"),
    }
    if event_dimensions != set(REFRESH_DIMENSIONS):
        return False
    replacement_keys = replacement_event.get("same_fiscal_current_keys") or []
    if len(replacement_keys) != 1:
        return False
    replacement_dimension = str(replacement_event["dimension"])
    current_source_keys = {
        source_key(row) for row in source[replacement_dimension].rows
    }
    replacement_key = tuple(
        str(replacement_keys[0].get(field) or "") for field in SOURCE_PRIMARY_KEY
    )
    return (
        replacement_event.get("ticker") == ticker
        and aged_event.get("ticker") == ticker
        and bool(replacement_event.get("was_oldest_prefix"))
        and bool(aged_event.get("was_oldest_prefix"))
        and bool(replacement_event.get("expected_quarterly_window_covered"))
        and bool(aged_event.get("expected_quarterly_window_covered"))
        and bool(aged_event.get("chronology_coherent"))
        and not aged_event.get("same_fiscal_current_keys")
        and replacement_key in current_source_keys
    )


def build_source_history_merge(
    ticker: str,
    current: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, HistoryTrust],
) -> dict[str, Any]:
    """Classify absent source keys and build the deterministic provider generation."""
    dimensions: dict[str, dict[str, Any]] = {}
    missing_events: list[dict[str, Any]] = []
    for dimension in REFRESH_DIMENSIONS:
        old_rows = tuple(current[dimension]["rows"])
        source_rows = tuple(source[dimension].rows)
        old_map = _row_maps(old_rows)
        source_map = _row_maps(source_rows)
        retained_map = {
            key: row for key, row in old_map.items()
            if row.get("_history_retention_status") == RETAINED_OUTSIDE_SOURCE_WINDOW
        }
        source_backed_map = {key: row for key, row in old_map.items() if key not in retained_map}
        missing = set(source_backed_map) - set(source_map)
        ordered_source_backed = sorted(source_backed_map.values(), key=_row_order)
        prefix_keys: list[tuple[str, str, str, str]] = []
        for row in ordered_source_backed:
            key = source_key(row)
            if key not in missing:
                break
            prefix_keys.append(key)
        current_min = min((str(row["reportperiod"]) for row in source_rows), default="")
        current_max = max((str(row["reportperiod"]) for row in source_rows), default="")
        prior_min = min((str(row["reportperiod"]) for row in source_backed_map.values()), default="")
        for key in sorted(missing):
            row = source_backed_map[key]
            boundary = key in prefix_keys
            coherent = bool(current_min and current_max and current_min > str(row["reportperiod"]))
            same_fiscal_current = [
                source_key_evidence(item) for item in source_rows
                if fiscal_identity(str(item["fiscalperiod"])) == fiscal_identity(str(row["fiscalperiod"]))
            ]
            boundary_span = _quarter_boundary_span(row, source_rows)
            expected_window = boundary_span >= MINIMUM_QUARTER_BOUNDARY_SPAN
            if not boundary or same_fiscal_current:
                event = TRUE_SOURCE_REMOVAL
                reason = (
                    "INTERIOR_SOURCE_KEY_REMOVAL" if not boundary
                    else "SAME_FISCAL_SOURCE_KEY_REPLACEMENT"
                )
            elif coherent and expected_window:
                event = AGED_OUT_OF_SOURCE_WINDOW
                reason = "OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW"
            else:
                event = AMBIGUOUS_SOURCE_REMOVAL
                reason = (
                    "BOUNDARY_CHRONOLOGY_INCONSISTENT" if not coherent
                    else "BOUNDARY_FISCAL_WINDOW_TOO_SHORT"
                )
            missing_events.append({
                "ticker": ticker,
                "dimension": dimension,
                "event": event,
                "classification_reason": reason,
                "source_identity": source_key_evidence(row),
                "fiscal_identity": dict(zip(("fiscal_year", "fiscal_quarter"), fiscal_identity(row["fiscalperiod"]), strict=True)),
                "was_oldest_prefix": boundary,
                "chronology_coherent": coherent,
                "same_fiscal_current_keys": same_fiscal_current,
                "boundary_fiscal_quarter_span": boundary_span,
                "minimum_quarter_boundary_span": MINIMUM_QUARTER_BOUNDARY_SPAN,
                "expected_quarterly_window_covered": expected_window,
                "prior_min_reportperiod": prior_min,
                "current_min_reportperiod": current_min,
                "current_max_reportperiod": current_max,
            })
        dimensions[dimension] = {
            "old_map": old_map,
            "source_map": source_map,
            "retained_map": retained_map,
            "already_retained_absent_keys": sorted(set(retained_map) - set(source_map)),
            "reappeared_keys": sorted(set(retained_map) & set(source_map)),
            "prior_min_reportperiod": prior_min,
            "current_min_reportperiod": current_min,
            "current_max_reportperiod": current_max,
        }

    by_fiscal: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for event in missing_events:
        fiscal = event["fiscal_identity"]
        by_fiscal.setdefault((int(fiscal["fiscal_year"]), str(fiscal["fiscal_quarter"])), []).append(event)
    for events in by_fiscal.values():
        classes = {str(event["event"]) for event in events}
        deterministic_pair = _is_deterministic_replacement_with_aged_companion(
            ticker, events, source,
        )
        if (
            len(events) > 1 and AMBIGUOUS_SOURCE_REMOVAL not in classes
            and len(classes) > 1 and not deterministic_pair
        ):
            for event in events:
                event["event"] = AMBIGUOUS_SOURCE_REMOVAL
                event["classification_reason"] = "COMPANION_DIMENSION_CONTRADICTION"
                event["companion_dimension_conflict"] = True

    event_by_key = {
        tuple(event["source_identity"][field] for field in SOURCE_PRIMARY_KEY): event
        for event in missing_events
    }
    merged_rows: dict[str, tuple[dict[str, Any], ...]] = {}
    for dimension in REFRESH_DIMENSIONS:
        detail = dimensions[dimension]
        merged = {key: dict(row) for key, row in detail["source_map"].items()}
        for key in detail["already_retained_absent_keys"]:
            merged[key] = dict(detail["retained_map"][key])
        for key, event in event_by_key.items():
            if key[1] != dimension or event["event"] != AGED_OUT_OF_SOURCE_WINDOW:
                continue
            row = dict(detail["old_map"][key])
            row["_history_retention_status"] = RETAINED_OUTSIDE_SOURCE_WINDOW
            row["_history_retention_evidence"] = _retention_evidence(row, event=event)
            merged[key] = row
        merged_rows[dimension] = tuple(merged[key] for key in sorted(merged))

    aged = [event for event in missing_events if event["event"] == AGED_OUT_OF_SOURCE_WINDOW]
    true_removed = [event for event in missing_events if event["event"] == TRUE_SOURCE_REMOVAL]
    ambiguous = [event for event in missing_events if event["event"] == AMBIGUOUS_SOURCE_REMOVAL]
    carried = sum(len(dimensions[dimension]["already_retained_absent_keys"]) for dimension in REFRESH_DIMENSIONS)
    reappeared = sum(len(dimensions[dimension]["reappeared_keys"]) for dimension in REFRESH_DIMENSIONS)
    current_rows = tuple(row for dimension in REFRESH_DIMENSIONS for row in current[dimension]["rows"])
    target_rows = tuple(row for dimension in REFRESH_DIMENSIONS for row in merged_rows[dimension])
    if ambiguous:
        label = "Review required"
    elif aged:
        label = "Retain outside source window"
    elif true_removed:
        label = "True source removal"
    elif reappeared:
        label = "Current source reappeared"
    elif carried:
        label = "Carry forward retained history"
    else:
        label = "No source-history action"
    return {
        "contract_version": RETENTION_CONTRACT_VERSION,
        "ticker": ticker,
        "dimensions": {
            dimension: {
                "merged_rows": merged_rows[dimension],
                "current_source_keys": [source_key_evidence(row) for row in source[dimension].rows],
                "retained_only_keys": [
                    source_key_evidence(row) for row in merged_rows[dimension]
                    if row.get("_history_retention_status") == RETAINED_OUTSIDE_SOURCE_WINDOW
                ],
                "true_removed_keys": [
                    event["source_identity"] for event in true_removed if event["dimension"] == dimension
                ],
            }
            for dimension in REFRESH_DIMENSIONS
        },
        "events": missing_events,
        "action": {
            "label": label,
            "newly_aged_out_source_rows": len(aged),
            "retained_arq": sum(event["dimension"] == "ARQ" for event in aged),
            "retained_mrq": sum(event["dimension"] == "MRQ" for event in aged),
            "already_retained_carry_forward": carried,
            "true_source_removals": len(true_removed),
            "ambiguous_removals": len(ambiguous),
            "current_source_reappearances": reappeared,
        },
        "current_generation_fingerprint": _generation_fingerprint(current_rows),
        "merged_generation_fingerprint": _generation_fingerprint(target_rows),
    }


def _row_maps(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str, str, str], Mapping[str, Any]]:
    return {source_key(row): row for row in rows}


def detect_fiscal_identity_revisions(
    ticker: str,
    current: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, HistoryTrust],
) -> list[dict[str, Any]]:
    revisions: list[dict[str, Any]] = []
    for dimension in REFRESH_DIMENSIONS:
        old_map = _row_maps(current[dimension]["rows"])
        new_map = _row_maps(source[dimension].rows)
        source_fiscal_keys: dict[tuple[int, str], list[dict[str, str]]] = {}
        for row in source[dimension].rows:
            source_fiscal_keys.setdefault(fiscal_identity(row["fiscalperiod"]), []).append(source_key_evidence(row))
        for key in sorted(old_map.keys() & new_map.keys()):
            old_row, new_row = old_map[key], new_map[key]
            old_fiscal = fiscal_identity(old_row["fiscalperiod"])
            new_fiscal = fiscal_identity(new_row["fiscalperiod"])
            if old_fiscal == new_fiscal:
                continue
            target_keys = source_fiscal_keys.get(new_fiscal, [])
            revisions.append({
                "event": FISCAL_IDENTITY_REVISION,
                "review_status": REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION,
                "ticker": ticker,
                "dimension": dimension,
                "source_identity": source_key_evidence(new_row),
                "old_fiscal_identity": {"fiscal_year": old_fiscal[0], "fiscal_quarter": old_fiscal[1]},
                "current_fiscal_identity": {"fiscal_year": new_fiscal[0], "fiscal_quarter": new_fiscal[1]},
                "old_source_fingerprint": fingerprint(_raw_row(old_row)),
                "current_source_fingerprint": fingerprint(_raw_row(new_row)),
                "old_lastupdated": old_row.get("lastupdated"),
                "current_lastupdated": new_row.get("lastupdated"),
                "financial_payload_changed": fingerprint({field: old_row.get(field) for field in FINANCIAL_FIELDS})
                != fingerprint({field: new_row.get(field) for field in FINANCIAL_FIELDS}),
                "target_fiscal_identity_already_exists": len(target_keys) > 1,
                "duplicate_target_source_keys": target_keys if len(target_keys) > 1 else [],
                "canonical_old_identity": {"fiscal_year": old_fiscal[0], "fiscal_quarter": old_fiscal[1]},
                "canonical_target_identity": {"fiscal_year": new_fiscal[0], "fiscal_quarter": new_fiscal[1]},
            })
    return revisions


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
    if any(current[dimension].get("legacy_source_version_ambiguities") for dimension in REFRESH_DIMENSIONS):
        return {
            "ticker": ticker,
            "classification": "REVIEW_REQUIRED",
            "review_reason": "LEGACY_SOURCE_VERSION_AMBIGUITY",
            "legacy_source_version_ambiguities": {
                dimension: current[dimension].get("legacy_source_version_ambiguities", [])
                for dimension in REFRESH_DIMENSIONS
            },
            "source_completeness": {dimension: source[dimension].evidence() for dimension in REFRESH_DIMENSIONS},
        }
    fiscal_revisions = detect_fiscal_identity_revisions(ticker, current, source)
    merge = build_source_history_merge(ticker, current, source)
    if fiscal_revisions:
        return {
            "ticker": ticker,
            "classification": "REVIEW_REQUIRED",
            "review_reason": REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION,
            "fiscal_identity_revisions": fiscal_revisions,
            "source_history_action": merge["action"],
            "source_history_events": [*merge["events"], *fiscal_revisions],
            "retention_plan_fingerprint": fingerprint({
                "events": merge["events"],
                "merged_generation_fingerprint": merge["merged_generation_fingerprint"],
            }),
            "source_completeness": {
                dimension: source[dimension].evidence() for dimension in REFRESH_DIMENSIONS
            },
        }
    action = merge["action"]
    if action["ambiguous_removals"]:
        return {
            "ticker": ticker,
            "classification": "REVIEW_REQUIRED",
            "review_reason": AMBIGUOUS_SOURCE_REMOVAL,
            "source_history_action": action,
            "source_history_events": merge["events"],
            "retention_plan_fingerprint": fingerprint({
                "events": merge["events"],
                "merged_generation_fingerprint": merge["merged_generation_fingerprint"],
            }),
            "source_completeness": {
                dimension: source[dimension].evidence() for dimension in REFRESH_DIMENSIONS
            },
        }
    added: list[tuple[str, str, str, str]] = []
    removed: list[tuple[str, str, str, str]] = []
    effective_changed: list[tuple[str, str, str, str]] = []
    metadata_changed: list[tuple[str, str, str, str]] = []
    for dimension in REFRESH_DIMENSIONS:
        old_map = _row_maps(current[dimension]["rows"])
        new_map = _row_maps(merge["dimensions"][dimension]["merged_rows"])
        added.extend(sorted(new_map.keys() - old_map.keys()))
        removed.extend(sorted(old_map.keys() - new_map.keys()))
        for key in sorted(old_map.keys() & new_map.keys()):
            if fingerprint(_effective_row(old_map[key])) != fingerprint(_effective_row(new_map[key])):
                effective_changed.append(key)
            elif fingerprint(_raw_row(old_map[key])) != fingerprint(_raw_row(new_map[key])):
                metadata_changed.append(key)
    current_rows = tuple(row for dimension in REFRESH_DIMENSIONS for row in current[dimension]["rows"])
    source_rows = tuple(
        row for dimension in REFRESH_DIMENSIONS
        for row in merge["dimensions"][dimension]["merged_rows"]
    )
    old_latest = _latest_fiscal(current_rows)
    new_latest = _latest_fiscal(source_rows)
    affected_fiscal = {
        fiscal_identity(old_map[key]["fiscalperiod"])
        for dimension in REFRESH_DIMENSIONS
        for old_map, new_map in [(
            _row_maps(current[dimension]["rows"]),
            _row_maps(merge["dimensions"][dimension]["merged_rows"]),
        )]
        for key in old_map
        if key not in new_map or (
            key in new_map
            and fingerprint(_effective_row(old_map[key])) != fingerprint(_effective_row(new_map[key]))
        )
    }
    affected_fiscal.update(
        fiscal_identity(new_map[key]["fiscalperiod"])
        for dimension in REFRESH_DIMENSIONS
        for old_map, new_map in [(
            _row_maps(current[dimension]["rows"]),
            _row_maps(merge["dimensions"][dimension]["merged_rows"]),
        )]
        for key in new_map
        if key not in old_map or (
            key in old_map
            and fingerprint(_effective_row(old_map[key])) != fingerprint(_effective_row(new_map[key]))
        )
    )
    advanced = bool(new_latest and (old_latest is None or (new_latest[0], int(new_latest[1][1])) > (old_latest[0], int(old_latest[1][1]))))
    prior_change = bool(effective_changed or removed or (added and not advanced))
    retention_transition = bool(
        action["newly_aged_out_source_rows"] or action["current_source_reappearances"]
    )
    if not added and not removed and not effective_changed:
        classification = (
            SOURCE_HISTORY_CHANGE if retention_transition
            else "SOURCE_ONLY_METADATA_CHANGE" if metadata_changed
            else "NO_EFFECTIVE_CHANGE"
        )
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
        "merged_counts": {
            dimension: len(merge["dimensions"][dimension]["merged_rows"])
            for dimension in REFRESH_DIMENSIONS
        },
        "current_effective_fingerprint": fingerprint({dimension: current[dimension]["effective_content_fingerprint"] for dimension in REFRESH_DIMENSIONS}),
        "source_effective_fingerprint": combined_effective_history_fingerprint(source),
        "source_raw_fingerprints": {dimension: source[dimension].raw_fingerprint for dimension in REFRESH_DIMENSIONS},
        "source_history_action": action,
        "source_history_events": merge["events"],
        "current_generation_fingerprint": merge["current_generation_fingerprint"],
        "merged_generation_fingerprint": merge["merged_generation_fingerprint"],
        "retention_plan_fingerprint": fingerprint({
            "events": merge["events"],
            "merged_generation_fingerprint": merge["merged_generation_fingerprint"],
        }),
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
    explicit_counts = {
        "ALREADY_ESTABLISHED": int(counts.get("ALREADY_ESTABLISHED", 0)),
        "BOOTSTRAP_ELIGIBLE": int(counts.get("BOOTSTRAP_ELIGIBLE", 0)),
        "REPAIR_REQUIRED": int(counts.get("REPAIR_REQUIRED", 0)),
    }
    return {
        "contract": {
            "stable_quarter_identity": ["company_id", "fiscal_year", "fiscal_quarter"],
            "source_availability_date": "MAY_FOLLOW_CURRENT_WINNING_SHARADAR_DATE",
            "first_public_result_date": "IMMUTABLE_DURING_ROUTINE_REFRESH_AFTER_BOOTSTRAP",
            "explicit_repair_required_to_change_first_public_result_date": True,
        },
        "total_quarters": len(rows),
        "counts": explicit_counts,
        "existing_canonical_quarters": len(rows),
        "established_first_public_dates": explicit_counts["ALREADY_ESTABLISHED"],
        "historical_bootstrap_eligible": explicit_counts["BOOTSTRAP_ELIGIBLE"],
        "historical_preservation_applicable": explicit_counts["ALREADY_ESTABLISHED"],
        "repair_required": explicit_counts["REPAIR_REQUIRED"],
        "exception_count": len(exceptions),
        "exceptions": exceptions,
        "all_current_quarters_bootstrap_eligible": (
            explicit_counts["BOOTSTRAP_ELIGIBLE"] == len(rows) and not exceptions
        ),
        "all_current_quarter_dates_valid": not exceptions,
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
        elif winner.get("date"):
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
        else:
            output.append({
                "ticker": identity["ticker"],
                "company_id": identity["company_id"],
                "fiscal_year": fiscal[0],
                "fiscal_quarter": fiscal[1],
                "existing_source_availability_date": None,
                "existing_first_public_result_date": None,
                "proposed_first_public_result_date_baseline": None,
                "source_date": None,
                "source_lastupdated": None,
                "policy_result": "NO_CANONICAL_DATE_IMPACT",
                "reason": "NO_ARQ_CANONICAL_WINNER_FOR_AFFECTED_SOURCE_FISCAL_IDENTITY",
            })
    return output


def publication_date_status(impacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    new_quarters = sum(
        item.get("policy_result") == "ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY"
        and bool(item.get("source_date"))
        for item in impacts
    )
    preserved = sum(
        item.get("policy_result") == "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE"
        for item in impacts
    )
    no_impact = sum(item.get("policy_result") == "NO_CANONICAL_DATE_IMPACT" for item in impacts)
    if new_quarters and preserved:
        code, label = "NEW_QUARTER_AND_PRESERVED_HISTORY", "New quarter + preserved history"
    elif new_quarters:
        code, label = "NEW_QUARTER", "New quarter"
    elif preserved:
        code, label = "PRESERVED", "Preserved"
    else:
        code, label = "NO_DATE_IMPACT", "No date impact"
    return {
        "status": code,
        "label": label,
        "expected_new_quarter_initializations": int(new_quarters),
        "existing_quarters_preserved": int(preserved),
        "source_only_fiscal_identities_without_canonical_date_impact": int(no_impact),
        "source_availability_date_changes": sum(
            bool(item.get("source_availability_date_would_drift")) for item in impacts
        ),
    }


def _publication_date_state(
    bootstrap: Mapping[str, Any], changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(
        str((item.get("publication_date_status") or {}).get("status") or "NO_DATE_IMPACT")
        for item in changes
        if item.get("classification") in {
            "NEW_QUARTER", "HISTORICAL_REVISION", "NEW_QUARTER_AND_REVISION", "SOURCE_REMOVAL",
        }
    )
    return {
        "existing_canonical_quarters": int(bootstrap.get("existing_canonical_quarters", 0)),
        "established_first_public_dates": int(bootstrap.get("established_first_public_dates", 0)),
        "historical_bootstrap_eligible": int(bootstrap.get("historical_bootstrap_eligible", 0)),
        "historical_preservation_applicable": int(bootstrap.get("historical_preservation_applicable", 0)),
        "repair_required": int(bootstrap.get("repair_required", 0)),
        "expected_new_quarter_initializations": sum(
            int((item.get("publication_date_status") or {}).get("expected_new_quarter_initializations", 0))
            for item in changes
        ),
        "ticker_status_counts": dict(sorted(statuses.items())),
    }


def provider_key_diagnostics(provider_db: Path) -> dict[str, Any]:
    with _readonly(provider_db) as connection:
        rows = connection.execute(
            "SELECT po.provider_record_key,po.observation_id,s.* "
            "FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id)"
        ).fetchall()
    legacy = Counter(str(row["provider_record_key"]) for row in rows)
    true_keys: Counter[tuple[str, str, str, str]] = Counter()
    clean = 0
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        raw = dict(row)
        key = source_key(raw)
        if all(key):
            clean += 1
            true_keys[key] += 1
            if true_keys[key] > 1 or key in grouped:
                grouped.setdefault(key, []).append(raw)
            else:
                grouped[key] = [raw]
    repeated = {key: items for key, items in grouped.items() if true_keys[key] > 1}
    resolution = Counter()
    ambiguous_tickers: set[str] = set()
    for key, versions in repeated.items():
        maximum = max(str(item.get("lastupdated") or "") for item in versions)
        latest = [item for item in versions if str(item.get("lastupdated") or "") == maximum]
        if len(latest) == 1:
            resolution["unique_max_groups"] += 1
            continue
        normalized = []
        for item in latest:
            try:
                normalized.append(normalize_source_row(item))
            except HistoryValidationError:
                normalized.append(item)
        if len({fingerprint(_effective_row(item)) for item in normalized}) == 1:
            resolution["same_max_identical_groups"] += 1
        else:
            resolution["same_max_conflicting_content_groups"] += 1
            ambiguous_tickers.add(key[0])
    return {
        "provider_observation_count": len(rows),
        "legacy_provider_record_key_groups": len(legacy),
        "repeated_legacy_key_groups": sum(1 for count in legacy.values() if count > 1),
        "rows_mapping_cleanly_to_true_source_key": clean,
        "rows_not_mapping_cleanly_to_true_source_key": len(rows) - clean,
        "true_source_key_groups": len(true_keys),
        "true_source_key_duplicate_groups": sum(1 for count in true_keys.values() if count > 1),
        "true_source_key_extra_versions": sum(count - 1 for count in true_keys.values() if count > 1),
        **dict(resolution),
        "same_max_conflicting_affected_tickers": sorted(ambiguous_tickers),
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
        if key in REFRESH_REPLACEMENT_CLASSES
    )
    actions = [change.get("source_history_action") or {} for change in changes]
    for key in (
        "newly_aged_out_source_rows", "retained_arq", "retained_mrq",
        "already_retained_carry_forward", "true_source_removals",
        "ambiguous_removals", "current_source_reappearances",
    ):
        counts[key] = sum(int(action.get(key) or 0) for action in actions)
    counts["fiscal_identity_revisions"] = sum(
        len(change.get("fiscal_identity_revisions") or []) for change in changes
    )
    counts["fiscal_identity_revisions_requiring_review"] = sum(
        1 for change in changes if change.get("review_reason") == REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION
    )
    return dict(counts)


def refresh_binding_change(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in REFRESH_BINDING_FIELDS}


def _render_refresh_report(result: Mapping[str, Any]) -> str:
    counts = result.get("summary_counts") or {}
    discovery = result.get("refresh_preview", {}).get("discovery", {})
    date_state = result.get("refresh_preview", {}).get("publication_date_state", {})
    lines = [
        "# Refresh Fundamentals Preview",
        "",
        f"Outcome: **{result.get('outcome')}**",
        "",
        "## Executive Summary",
        "",
        f"- Trigger: `{result.get('trigger_source', 'MANUAL')}`",
        f"- Sharadar discovery rows: `{discovery.get('returned_source_rows', 0)}`",
        f"- Changed source tickers: `{discovery.get('unique_changed_source_tickers', 0)}`",
        f"- Known tickers with effective changes: `{counts.get('effective_changed_known', 0)}`",
        f"- Unknown tickers: `{counts.get('NOT_IN_CANONICAL_UNIVERSE', 0)}`",
        f"- Review required: `{counts.get('REVIEW_REQUIRED', 0)}`",
        f"- Fiscal identity revisions: `{counts.get('fiscal_identity_revisions', 0)}`",
        f"- Fiscal identity revisions requiring review: `{counts.get('fiscal_identity_revisions_requiring_review', 0)}`",
        "",
        "## Discovery",
        "",
        f"- State: `{result.get('refresh_preview', {}).get('state', {}).get('mode')}`",
        f"- Query start: `{discovery.get('query_start_date')}`",
        f"- Observed source maximum: `{discovery.get('observed_source_max_lastupdated')}`",
        f"- Schema fingerprint: `{result.get('refresh_preview', {}).get('schema', {}).get('schema_fingerprint')}`",
        "",
        "## Fiscal Identity Revisions",
        "",
        "| Ticker | Dimension | True source key | Reclassification | Financial revision | Review |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    fiscal_rows = [
        event
        for item in result.get("refresh_preview", {}).get("ticker_changes", [])
        for event in item.get("fiscal_identity_revisions", [])
    ]
    lines.extend(
        "| {ticker} | {dimension} | {date} / {reportperiod} | {old} -> {new} | {financial} | Required |".format(
            ticker=event["ticker"], dimension=event["dimension"],
            date=event["source_identity"]["date"], reportperiod=event["source_identity"]["reportperiod"],
            old=f"{event['old_fiscal_identity']['fiscal_year']} {event['old_fiscal_identity']['fiscal_quarter']}",
            new=f"{event['current_fiscal_identity']['fiscal_year']} {event['current_fiscal_identity']['fiscal_quarter']}",
            financial="yes" if event["financial_payload_changed"] else "no",
        )
        for event in fiscal_rows
    )
    if not fiscal_rows:
        lines.append("| - | - | - | - | - | None |")
    lines.extend([
        "",
        "## Source-Window Retention",
        "",
        f"- Newly aged-out source rows: `{counts.get('newly_aged_out_source_rows', 0)}`",
        f"- ARQ retained: `{counts.get('retained_arq', 0)}`",
        f"- MRQ retained: `{counts.get('retained_mrq', 0)}`",
        f"- Already-retained rows carried forward: `{counts.get('already_retained_carry_forward', 0)}`",
        f"- True source removals: `{counts.get('true_source_removals', 0)}`",
        f"- Ambiguous removals: `{counts.get('ambiguous_removals', 0)}`",
        "",
        "`RETAINED_OUTSIDE_SOURCE_WINDOW` means that RawCandle preserves the last authoritative "
        "version it observed before the row aged outside the accessible source window. It is not "
        "currently returned data, invented data, or a guarantee that the value is forever final.",
        "",
        "| Ticker | Missing source rows | Source-history action | Reason | Canonical impact |",
        "| --- | ---: | --- | --- | --- |",
    ])
    for item in result.get("refresh_preview", {}).get("ticker_changes", []):
        action = item.get("source_history_action") or {}
        missing = (
            int(action.get("newly_aged_out_source_rows") or 0)
            + int(action.get("true_source_removals") or 0)
            + int(action.get("ambiguous_removals") or 0)
        )
        if not missing and not action.get("already_retained_carry_forward") and not action.get("current_source_reappearances"):
            continue
        canonical = (
            "Historical quarter retained" if action.get("retained_arq")
            else "Quarter evaluated from surviving ARQ" if action.get("true_source_removals")
            else "No new canonical event"
        )
        reasons = ", ".join(sorted({
            str(event.get("classification_reason"))
            for event in item.get("source_history_events", [])
            if event.get("classification_reason")
        })) or "None"
        lines.append(
            f"| {item.get('ticker')} | {missing} | {action.get('label')} | {reasons} | {canonical} |"
        )
    lines.extend([
        "",
        "## Effective Known-Ticker Changes",
        "",
        "| Ticker | Current latest Q | Sharadar latest Q | Change | ARQ before/after | Added | Changed | Removed | Publication-date impact |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ])
    for item in result.get("refresh_preview", {}).get("ticker_changes", []):
        if item.get("classification") not in REFRESH_REPLACEMENT_CLASSES:
            continue
        policy = (item.get("publication_date_status") or {}).get("label", "No date impact")
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
        "- The historical `first_public_result_date` baseline is established in production.",
        "- Routine Refresh preserves established historical values by `(company_id, fiscal_year, fiscal_quarter)`.",
        "- A genuinely new canonical quarter receives its initial first-public date under the accepted canonical policy.",
        "- `source_availability_date` may follow the current winning Sharadar row.",
        "- Routine Refresh does not repair an established first-public date; explicit repair remains separate.",
        "",
        "## Publication-Date State",
        "",
        f"- Existing canonical quarters: `{date_state.get('existing_canonical_quarters', 0)}`",
        f"- Established first-public dates: `{date_state.get('established_first_public_dates', 0)}`",
        f"- Historical bootstrap eligible: `{date_state.get('historical_bootstrap_eligible', 0)}`",
        f"- Historical preservation applicable: `{date_state.get('historical_preservation_applicable', 0)}`",
        f"- Repair required: `{date_state.get('repair_required', 0)}`",
        f"- Expected new-quarter initializations at Preview level: `{date_state.get('expected_new_quarter_initializations', 0)}`",
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
    trigger_source: str = "MANUAL",
) -> dict[str, Any]:
    if trigger_source not in {"MANUAL", "SCHEDULER"}:
        raise ValueError("REFRESH_TRIGGER_SOURCE_INVALID")
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
    writer.write_json("request.json", request.as_dict() | {"trigger_source": trigger_source})
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
                comparison["publication_date_status"] = publication_date_status(
                    comparison["publish_date_impact"]
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
        publication_state = _publication_date_state(bootstrap, changes)
        legacy = provider_key_diagnostics(source_paths.provider_db)
        replacement = [item for item in changes if item.get("classification") in REFRESH_REPLACEMENT_CLASSES]
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
            "ticker_changes": [refresh_binding_change(item) for item in changes],
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
            "future_test_authorized": (
                trigger_source == "MANUAL" and bool(replacement) and not review
                and discovery["status"] == "COMPLETE"
                and publication_state["historical_bootstrap_eligible"] == 0
                and publication_state["repair_required"] == 0
                and counts.get("ambiguous_removals", 0) == 0
            ),
            "published_watermark_advanced": False,
            "provider_key_diagnostics": legacy,
            "publish_date_bootstrap": {key: value for key, value in bootstrap.items() if key != "exceptions"},
            "publication_date_state": publication_state,
            "source_window_retention": {
                key: counts.get(key, 0) for key in (
                    "newly_aged_out_source_rows", "retained_arq", "retained_mrq",
                    "already_retained_carry_forward", "true_source_removals",
                    "ambiguous_removals", "current_source_reappearances",
                )
            },
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
                else "Review the read-only Preview. Use only this exact manual Preview for a separately approved Test on copies."
                if trigger_source == "MANUAL"
                else "Scheduler Preview is informational only; run a fresh manual Preview before Test on copies."
            ),
        )
        result = result_obj.as_dict() | {
            "artifact_dir": str(writer.run_dir),
            "preview_payload_path": str(preview_path),
            "refresh_preview": preview,
            "network_used": True,
            "trigger_source": trigger_source,
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
            "trigger_source": trigger_source,
            "failed_stage": failed_stage.value,
            "database_safety": "NO_DATABASE_WRITES",
            "production_file_state_unchanged": before == _production_file_state(source_paths),
        }
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_refresh_report(result))
        writer.write_exit_code(2)
        writer.write_manifest()
        return result
