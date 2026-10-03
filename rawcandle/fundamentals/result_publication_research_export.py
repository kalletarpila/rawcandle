from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.result_publication_daily_research import RULE_VERSION, YahooEvent
from rawcandle.fundamentals.result_publication_daily_research_service import (
    DailyResearchPublicationService,
    MappingV2CandidateProvider,
    MappingYahooObservationProvider,
    QuarterKey,
    V2CandidateProvider,
    YFinanceYahooObservationProvider,
    YahooObservationProvider,
)


YAHOO_ARTIFACT_VERSION = "result_publication_yahoo_observations_v1"
V2_ARTIFACT_VERSION = "result_publication_v2_candidates_v1"
EXPORT_METADATA_VERSION = "result_publication_research_export_v1"

EXPORT_COLUMNS = (
    "company_id",
    "ticker",
    "fiscal_year",
    "fiscal_quarter",
    "research_status",
    "research_confidence",
    "research_method",
    "research_publication_date",
    "research_publication_session",
    "first_full_post_result_trading_date",
    "canonical_authority_status",
    "canonical_timestamp_utc",
    "is_canonical",
    "selected_candidate_timestamp_utc",
    "selected_candidate_reference",
    "yahoo_event_timestamp",
    "yahoo_event_date",
    "trading_day_distance_to_yahoo",
    "rule_version",
    "warning",
)


@dataclass(frozen=True)
class LoadedArtifact:
    provider: YahooObservationProvider | V2CandidateProvider
    sha256: str
    row_count: int


@dataclass(frozen=True)
class ExportRequest:
    canonical_db: Path
    ohlc_db: Path
    output: Path
    output_format: str = "csv"
    metadata_output: Path | None = None
    tickers: tuple[str, ...] = ()
    company_ids: tuple[int, ...] = ()
    from_fiscal_year: int = 2025
    to_fiscal_year: int | None = None
    include_unusable: bool = False
    yahoo_mode: str = "none"
    yahoo_observations: Path | None = None
    write_yahoo_observations: Path | None = None
    v2_candidates: Path | None = None
    first_full_day_from: str | None = None
    exact_timestamp_from: str | None = None


class RecordingYahooObservationProvider:
    def __init__(self, provider: YahooObservationProvider, *, observed_at_utc: str) -> None:
        self.provider = provider
        self.observed_at_utc = _aware_timestamp(observed_at_utc, "observed_at_utc")
        self.observations: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def get_events(self, key: QuarterKey, ticker: str, period_end: str) -> Sequence[YahooEvent]:
        try:
            events = tuple(self.provider.get_events(key, ticker, period_end))
        except Exception as exc:
            self.errors.append(
                {
                    "company_id": key.company_id,
                    "fiscal_year": key.fiscal_year,
                    "fiscal_quarter": key.fiscal_quarter,
                    "ticker_used": ticker,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise
        for event in events:
            parsed = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            self.observations.append(
                {
                    "company_id": key.company_id,
                    "fiscal_year": key.fiscal_year,
                    "fiscal_quarter": key.fiscal_quarter,
                    "ticker_used": ticker,
                    "yahoo_event_timestamp": event.timestamp,
                    "yahoo_event_timezone": str(parsed.tzinfo),
                    "observed_at_utc": self.observed_at_utc,
                    "provider": "YAHOO_FINANCE",
                    "transport": "yfinance",
                }
            )
        return events


def _aware_timestamp(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}:INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}:TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"INVALID_ARTIFACT:{path}:{type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"INVALID_ARTIFACT_ROOT:{path}")
    return payload, _sha256(path)


def _quarter_key(row: Mapping[str, Any], prefix: str) -> QuarterKey:
    try:
        key = QuarterKey(int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{prefix}:INVALID_QUARTER_IDENTITY") from exc
    if key.company_id <= 0 or key.fiscal_year <= 0 or key.fiscal_quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError(f"{prefix}:INVALID_QUARTER_IDENTITY")
    return key


def load_yahoo_observation_artifact(path: str | Path) -> LoadedArtifact:
    artifact_path = Path(path)
    payload, digest = _load_json_object(artifact_path)
    if payload.get("artifact_version") != YAHOO_ARTIFACT_VERSION:
        raise ValueError("YAHOO_ARTIFACT_VERSION_INVALID")
    if payload.get("projection_rule_version") != RULE_VERSION:
        raise ValueError("YAHOO_ARTIFACT_PROJECTION_RULE_INVALID")
    if not isinstance(payload.get("source_scope"), str) or not payload["source_scope"]:
        raise ValueError("YAHOO_ARTIFACT_SOURCE_SCOPE_INVALID")
    _aware_timestamp(str(payload.get("created_at_utc", "")), "created_at_utc")
    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise ValueError("YAHOO_ARTIFACT_OBSERVATIONS_INVALID")

    observations: dict[QuarterKey, list[YahooEvent]] = {}
    seen: set[tuple[QuarterKey, str, str]] = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"YAHOO_ARTIFACT_ROW_INVALID:{index}")
        key = _quarter_key(raw, f"YAHOO_ARTIFACT_ROW:{index}")
        ticker = str(raw.get("ticker_used", "")).strip().upper()
        timestamp = str(raw.get("yahoo_event_timestamp", ""))
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if not ticker or parsed.tzinfo is None:
            raise ValueError(f"YAHOO_ARTIFACT_ROW_INVALID:{index}")
        if not str(raw.get("yahoo_event_timezone", "")).strip():
            raise ValueError(f"YAHOO_ARTIFACT_TIMEZONE_INVALID:{index}")
        _aware_timestamp(str(raw.get("observed_at_utc", "")), f"observed_at_utc:{index}")
        if raw.get("provider") != "YAHOO_FINANCE" or raw.get("transport") != "yfinance":
            raise ValueError(f"YAHOO_ARTIFACT_PROVENANCE_INVALID:{index}")
        identity = (key, ticker, timestamp)
        if identity in seen:
            raise ValueError(f"YAHOO_ARTIFACT_DUPLICATE:{index}")
        seen.add(identity)
        observations.setdefault(key, []).append(YahooEvent(timestamp))
    return LoadedArtifact(MappingYahooObservationProvider(observations), digest, len(rows))


def load_v2_candidate_artifact(path: str | Path) -> LoadedArtifact:
    artifact_path = Path(path)
    payload, digest = _load_json_object(artifact_path)
    if payload.get("artifact_version") != V2_ARTIFACT_VERSION:
        raise ValueError("V2_ARTIFACT_VERSION_INVALID")
    if payload.get("projection_rule_version") != RULE_VERSION:
        raise ValueError("V2_ARTIFACT_PROJECTION_RULE_INVALID")
    _aware_timestamp(str(payload.get("created_at_utc", "")), "created_at_utc")
    rows = payload.get("candidates")
    if not isinstance(rows, list):
        raise ValueError("V2_ARTIFACT_CANDIDATES_INVALID")

    candidates: dict[QuarterKey, str] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"V2_ARTIFACT_ROW_INVALID:{index}")
        key = _quarter_key(raw, f"V2_ARTIFACT_ROW:{index}")
        candidate_id = str(raw.get("selected_candidate_id", "")).strip()
        reference = str(raw.get("selected_evidence_reference", "")).strip()
        timestamp = str(raw.get("selected_candidate_timestamp_utc", ""))
        classifier = str(raw.get("classifier_version", "")).strip()
        _aware_timestamp(timestamp, f"selected_candidate_timestamp_utc:{index}")
        _aware_timestamp(str(raw.get("reviewed_at_utc", "")), f"reviewed_at_utc:{index}")
        if not candidate_id or not reference or not classifier or raw.get("review_status") != "ACCEPTED":
            raise ValueError(f"V2_ARTIFACT_ROW_INVALID:{index}")
        if key in candidates:
            raise ValueError(f"V2_ARTIFACT_DUPLICATE:{index}")
        candidates[key] = candidate_id
    return LoadedArtifact(MappingV2CandidateProvider(candidates), digest, len(rows))


def validate_v2_candidate_artifact(canonical_db: Path, artifact_path: Path) -> LoadedArtifact:
    loaded = load_v2_candidate_artifact(artifact_path)
    payload, _ = _load_json_object(artifact_path)
    connection = sqlite3.connect(f"file:{canonical_db.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        for index, row in enumerate(payload["candidates"]):
            key = _quarter_key(row, f"V2_ARTIFACT_ROW:{index}")
            match = connection.execute(
                """
                SELECT 1
                FROM v4_result_publication_evidence
                WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?
                  AND source_type='SEC_8K_ITEM_2_02'
                  AND disposition IN ('ACCEPTED','CONFLICT')
                  AND COALESCE(accession_number,evidence_id)=?
                  AND source_timestamp_utc=? AND source_reference=?
                """,
                (
                    key.company_id,
                    key.fiscal_year,
                    key.fiscal_quarter,
                    row["selected_candidate_id"],
                    row["selected_candidate_timestamp_utc"],
                    row["selected_evidence_reference"],
                ),
            ).fetchone()
            if match is None:
                raise ValueError(
                    f"V2_CANDIDATE_NOT_CURRENT:{key.company_id}/{key.fiscal_year}/{key.fiscal_quarter}"
                )
    finally:
        connection.close()
    return loaded


def write_yahoo_observation_artifact(
    path: Path,
    provider: RecordingYahooObservationProvider,
    *,
    created_at_utc: str,
    source_scope: str,
) -> None:
    unique_observations = {
        (
            row["company_id"],
            row["fiscal_year"],
            row["fiscal_quarter"],
            row["ticker_used"],
            row["yahoo_event_timestamp"],
        ): row
        for row in provider.observations
    }
    payload = {
        "artifact_version": YAHOO_ARTIFACT_VERSION,
        "created_at_utc": _aware_timestamp(created_at_utc, "created_at_utc"),
        "projection_rule_version": RULE_VERSION,
        "source_scope": source_scope,
        "observations": sorted(
            unique_observations.values(),
            key=lambda row: (
                row["company_id"],
                row["fiscal_year"],
                row["fiscal_quarter"],
                row["ticker_used"],
                row["yahoo_event_timestamp"],
            ),
        ),
        "provider_errors": provider.errors,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def select_quarter_keys(request: ExportRequest) -> list[QuarterKey]:
    if request.from_fiscal_year <= 0:
        raise ValueError("FROM_FISCAL_YEAR_INVALID")
    if request.to_fiscal_year is not None and request.to_fiscal_year < request.from_fiscal_year:
        raise ValueError("FISCAL_YEAR_RANGE_INVALID")
    tickers = tuple(dict.fromkeys(ticker.strip().upper() for ticker in request.tickers if ticker.strip()))
    company_ids = tuple(dict.fromkeys(request.company_ids))
    clauses = ["a.fiscal_year>=?"]
    parameters: list[Any] = [request.from_fiscal_year]
    if request.to_fiscal_year is not None:
        clauses.append("a.fiscal_year<=?")
        parameters.append(request.to_fiscal_year)
    if company_ids:
        clauses.append(f"a.company_id IN ({','.join('?' for _ in company_ids)})")
        parameters.extend(company_ids)
    if tickers:
        clauses.append(
            "EXISTS (SELECT 1 FROM security s WHERE s.company_id=a.company_id "
            f"AND UPPER(s.current_ticker) IN ({','.join('?' for _ in tickers)}))"
        )
        parameters.extend(tickers)
    connection = sqlite3.connect(f"file:{request.canonical_db.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        rows = connection.execute(
            "SELECT a.company_id,a.fiscal_year,a.fiscal_quarter "
            "FROM v4_result_publication_authority a WHERE "
            + " AND ".join(clauses)
            + " ORDER BY a.company_id,a.fiscal_year,a.fiscal_quarter",
            parameters,
        ).fetchall()
    finally:
        connection.close()
    return [QuarterKey(int(row[0]), int(row[1]), str(row[2])) for row in rows]


def _write_export(path: Path, output_format: str, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return
    if output_format == "jsonl":
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
        return
    raise ValueError("OUTPUT_FORMAT_INVALID")


def run_research_export(
    request: ExportRequest,
    *,
    generated_at_utc: str | None = None,
    live_yahoo_provider: YahooObservationProvider | None = None,
) -> dict[str, Any]:
    generated = _aware_timestamp(
        generated_at_utc or datetime.now(timezone.utc).isoformat(), "generated_at_utc"
    )
    if request.first_full_day_from:
        datetime.strptime(request.first_full_day_from, "%Y-%m-%d")
    if request.exact_timestamp_from:
        _aware_timestamp(request.exact_timestamp_from, "exact_timestamp_from")
    if request.yahoo_mode not in {"none", "frozen", "live"}:
        raise ValueError("YAHOO_MODE_INVALID")
    if request.yahoo_mode == "frozen" and request.yahoo_observations is None:
        raise ValueError("YAHOO_FROZEN_ARTIFACT_REQUIRED")
    if request.yahoo_mode != "frozen" and request.yahoo_observations is not None:
        raise ValueError("YAHOO_ARTIFACT_REQUIRES_FROZEN_MODE")
    if request.yahoo_mode != "live" and request.write_yahoo_observations is not None:
        raise ValueError("YAHOO_OBSERVATION_WRITE_REQUIRES_LIVE_MODE")

    yahoo_provider: YahooObservationProvider | None = None
    yahoo_sha: str | None = None
    yahoo_rows = 0
    recorder: RecordingYahooObservationProvider | None = None
    if request.yahoo_mode == "frozen":
        loaded_yahoo = load_yahoo_observation_artifact(request.yahoo_observations)
        yahoo_provider = loaded_yahoo.provider  # type: ignore[assignment]
        yahoo_sha = loaded_yahoo.sha256
        yahoo_rows = loaded_yahoo.row_count
    elif request.yahoo_mode == "live":
        recorder = RecordingYahooObservationProvider(
            live_yahoo_provider or YFinanceYahooObservationProvider(),
            observed_at_utc=generated,
        )
        yahoo_provider = recorder

    v2_provider: V2CandidateProvider | None = None
    v2_sha: str | None = None
    v2_rows = 0
    if request.v2_candidates is not None:
        loaded_v2 = validate_v2_candidate_artifact(request.canonical_db, request.v2_candidates)
        v2_provider = loaded_v2.provider  # type: ignore[assignment]
        v2_sha = loaded_v2.sha256
        v2_rows = loaded_v2.row_count

    keys = select_quarter_keys(request)
    with DailyResearchPublicationService(
        request.canonical_db,
        request.ohlc_db,
        yahoo_provider=yahoo_provider,
        v2_provider=v2_provider,
    ) as service:
        assembled = service.get_daily_research_results(keys)

    all_statuses = Counter(item.result.research_status for item in assembled)
    exported = [item for item in assembled if request.include_unusable or item.result.research_status != "UNUSABLE"]
    if request.first_full_day_from or request.exact_timestamp_from:
        exported = [item for item in exported if (
            bool(request.first_full_day_from and item.result.first_full_post_result_trading_date
                 and item.result.first_full_post_result_trading_date >= request.first_full_day_from)
            or bool(request.exact_timestamp_from and item.result.research_status == "EXACT"
                    and item.result.canonical_timestamp_utc
                    and _aware_timestamp(item.result.canonical_timestamp_utc, "canonical_timestamp_utc")
                    >= _aware_timestamp(request.exact_timestamp_from, "exact_timestamp_from"))
        )]
    rows = []
    for item in exported:
        payload = item.to_dict()
        payload["ticker"] = item.tickers[0] if item.tickers else None
        rows.append({column: payload.get(column) for column in EXPORT_COLUMNS})
    _write_export(request.output, request.output_format, rows)

    source_scope = (
        f"fy={request.from_fiscal_year}:{request.to_fiscal_year or 'latest'};"
        f"tickers={','.join(request.tickers) or 'ALL'};"
        f"company_ids={','.join(str(value) for value in request.company_ids) or 'ALL'}"
    )
    if recorder is not None and request.write_yahoo_observations is not None:
        write_yahoo_observation_artifact(
            request.write_yahoo_observations,
            recorder,
            created_at_utc=generated,
            source_scope=source_scope,
        )

    metadata_path = request.metadata_output or Path(str(request.output) + ".metadata.json")
    metadata = {
        "artifact_version": EXPORT_METADATA_VERSION,
        "generated_at_utc": generated,
        "projection_rule_version": RULE_VERSION,
        "canonical_db": str(request.canonical_db.resolve()),
        "canonical_db_sha256": _sha256(request.canonical_db),
        "ohlc_db": str(request.ohlc_db.resolve()),
        "ohlc_db_sha256": _sha256(request.ohlc_db),
        "yahoo_mode": request.yahoo_mode,
        "yahoo_artifact": str(request.yahoo_observations.resolve()) if request.yahoo_observations else None,
        "yahoo_artifact_sha256": yahoo_sha,
        "yahoo_artifact_rows": yahoo_rows,
        "yahoo_live_observations": len(recorder.observations) if recorder else 0,
        "yahoo_live_errors": recorder.errors if recorder else [],
        "v2_artifact": str(request.v2_candidates.resolve()) if request.v2_candidates else None,
        "v2_artifact_sha256": v2_sha,
        "v2_artifact_rows": v2_rows,
        "filters": {
            "tickers": list(request.tickers),
            "company_ids": list(request.company_ids),
            "from_fiscal_year": request.from_fiscal_year,
            "to_fiscal_year": request.to_fiscal_year,
            "include_unusable": request.include_unusable,
            "first_full_day_from": request.first_full_day_from,
            "exact_timestamp_from": request.exact_timestamp_from,
        },
        "evaluated_rows": len(assembled),
        "exported_rows": len(rows),
        "evaluated_status_counts": dict(sorted(all_statuses.items())),
        "status_counts": dict(sorted(Counter(item.result.research_status for item in exported).items())) if request.first_full_day_from or request.exact_timestamp_from else dict(sorted(all_statuses.items())),
        "output": str(request.output.resolve()),
        "output_format": request.output_format,
        "output_sha256": _sha256(request.output),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata
