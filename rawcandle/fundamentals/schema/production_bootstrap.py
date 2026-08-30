from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rawcandle.fundamentals.providers.sharadar import (
    SHARADAR_DIRECT_BASE_URL,
    USER_AGENT,
    redact_secret,
    redact_url,
    resolve_api_key,
)
from rawcandle.fundamentals.schema.contract import SHARADAR_ARQ_FIELD_MAPPING, V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.identity_calendar_bootstrap import (
    bootstrap_identity_calendar,
    fiscal_anchor_coverage,
    locate_bootstrap_csv,
    summarize_bootstrap,
)
from rawcandle.fundamentals.schema.migrations import bootstrap_all, canonical_field_contract_present, connect
from rawcandle.fundamentals.schema.prototype import (
    PROTOTYPE_TICKERS,
    int_or_none,
    nullable_text,
    parse_fiscalperiod,
    provider_counts,
    read_csv_rows,
    schema_validation,
    stable_hash,
    stable_id,
    utc_now,
    utc_stamp,
    write_csv,
    write_json,
)


PROVIDER_DB_NAME = "fundamentals_provider.db"
CANONICAL_DB_NAME = "fundamentals_v4.db"
ANALYSIS_DB_NAME = "fundamentals_analysis.db"
PRODUCTION_RUN_TYPE = "SHARADAR_5Y_INITIAL_BOOTSTRAP"
ALLOWED_DIMENSIONS = {"ARQ", "MRQ"}
CRITICAL_FIELDS = ("revenue", "ebit", "free_cashflow", "cash", "total_debt", "shares_outstanding")


@dataclass(frozen=True)
class ProductionPaths:
    repo_root: Path
    artifact_root: Path
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    bootstrap_csv: Path
    bulk_zip_path: Path
    extracted_csv_path: Path


def production_paths(repo_root: Path, timestamp: str | None = None, bootstrap_csv: Path | None = None) -> ProductionPaths:
    stamp = timestamp or utc_stamp()
    artifact_root = repo_root / "temp" / "fundamentals_v4_1b_production_bootstrap" / stamp
    return ProductionPaths(
        repo_root=repo_root,
        artifact_root=artifact_root,
        provider_db=repo_root / "data" / PROVIDER_DB_NAME,
        canonical_db=repo_root / "data" / CANONICAL_DB_NAME,
        analysis_db=repo_root / "data" / ANALYSIS_DB_NAME,
        bootstrap_csv=bootstrap_csv or locate_bootstrap_csv(repo_root),
        bulk_zip_path=artifact_root / "sharadar_fundamentals_5y.zip",
        extracted_csv_path=artifact_root / "sharadar_fundamentals_5y.csv",
    )


def preflight(paths: ProductionPaths, *, api_key_configured: bool, git_status: str) -> dict[str, Any]:
    existing = {
        "provider_db_pre_existing": paths.provider_db.exists(),
        "canonical_db_pre_existing": paths.canonical_db.exists(),
        "analysis_db_pre_existing": paths.analysis_db.exists(),
    }
    bootstrap_csv_found = paths.bootstrap_csv.exists()
    temp_probe = paths.artifact_root / "preflight_schema_probe"
    bootstrap_all(
        temp_probe / "provider.db",
        temp_probe / "canonical.db",
        temp_probe / "analysis.db",
        utc_now(),
    )
    identity_probe = {"counts": {"company_ciks": 0}}
    if bootstrap_csv_found:
        identity_probe = bootstrap_identity_calendar(temp_probe / "canonical.db", paths.bootstrap_csv, utc_now())
    result = {
        **existing,
        "schema_probe_ok": True,
        "identity_calendar_probe_ok": bootstrap_csv_found,
        "identity_calendar_probe_ciks": identity_probe["counts"]["company_ciks"],
        "bootstrap_csv_found": bootstrap_csv_found,
        "bootstrap_csv": str(paths.bootstrap_csv),
        "sharadar_key_configured": api_key_configured,
        "git_status_clean": not bool(git_status.strip()),
        "git_status": git_status,
    }
    blocking = [name for name, value in existing.items() if value]
    if not bootstrap_csv_found:
        blocking.append("bootstrap_csv_missing")
    if not api_key_configured:
        blocking.append("sharadar_key_missing")
    if git_status.strip():
        blocking.append("git_worktree_dirty")
    result["blocking_reasons"] = blocking
    result["ok_to_create"] = not blocking
    return result


def download_sharadar_5y_bulk(
    paths: ProductionPaths,
    *,
    api_key: str | None = None,
    opener: Callable[[Request, float], Any] | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    key = resolve_api_key(api_key)
    opener = opener or (lambda request, timeout: urlopen(request, timeout=timeout))
    endpoint = "/data/fundamentals"
    params = {"years": "5"}
    url = f"{SHARADAR_DIRECT_BASE_URL}{endpoint}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/zip,text/csv,application/json",
            "User-Agent": USER_AGENT,
            "x-api-key": key,
        },
        method="GET",
    )
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    try:
        response = opener(request, timeout_seconds)
        http_status = int(getattr(response, "status", response.getcode()))
        final_url = getattr(response, "url", None) or response.geturl()
        content_type = _header_value(response, "Content-Type")
        saved_path, payload_sha, payload_size = _save_response(response, paths)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "endpoint": endpoint,
            "history_scope": "years=5",
            "http_status": int(exc.code),
            "status": "HTTP_ERROR",
            "error": redact_secret(body[:500], [key]),
            "url": redact_url(url),
        }
    except (TimeoutError, URLError, OSError) as exc:
        return {
            "endpoint": endpoint,
            "history_scope": "years=5",
            "http_status": 0,
            "status": "REQUEST_FAILED",
            "error": redact_secret(f"{type(exc).__name__}:{exc}", [key]),
            "url": redact_url(url),
        }
    extracted = extract_bulk_csv(saved_path, paths.extracted_csv_path)
    manifest = {
        "endpoint": endpoint,
        "history_scope": "years=5",
        "http_status": http_status,
        "status": "SUCCESS",
        "url_class": redact_url(f"{SHARADAR_DIRECT_BASE_URL}{endpoint}?years=5"),
        "final_url_class": _url_class(final_url),
        "content_type": content_type,
        "downloaded_path": str(saved_path),
        "zip_size": payload_size if zipfile.is_zipfile(saved_path) else 0,
        "zip_sha256": payload_sha if zipfile.is_zipfile(saved_path) else "",
        "payload_size": payload_size,
        "payload_sha256": payload_sha,
        **extracted,
        "downloaded_at_utc": utc_now(),
    }
    write_json(paths.artifact_root / "sharadar_5y_bulk_manifest.json", manifest)
    return manifest


def _header_value(response: Any, name: str) -> str:
    headers = getattr(response, "headers", {})
    if hasattr(headers, "get"):
        return str(headers.get(name, ""))
    return ""


def _save_response(response: Any, paths: ProductionPaths) -> tuple[Path, str, int]:
    target = paths.bulk_zip_path
    hasher = hashlib.sha256()
    size = 0
    with target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
            handle.write(chunk)
    if not zipfile.is_zipfile(target):
        csv_target = paths.extracted_csv_path
        target.replace(csv_target)
        return csv_target, hasher.hexdigest(), size
    return target, hasher.hexdigest(), size


def extract_bulk_csv(downloaded_path: Path, extracted_csv_path: Path) -> dict[str, Any]:
    if zipfile.is_zipfile(downloaded_path):
        with zipfile.ZipFile(downloaded_path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("Sharadar bulk ZIP did not contain a CSV file")
            with archive.open(csv_names[0]) as source, extracted_csv_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            extracted_name = csv_names[0]
    else:
        extracted_name = downloaded_path.name
        extracted_csv_path = downloaded_path
    row_count, column_count, dimensions = csv_profile(extracted_csv_path)
    return {
        "extracted_path": str(extracted_csv_path),
        "extracted_name": extracted_name,
        "extraction_size": extracted_csv_path.stat().st_size,
        "extracted_rows": row_count,
        "extracted_columns": column_count,
        "dimensions_present": sorted(dimensions),
    }


def csv_profile(path: Path) -> tuple[int, int, set[str]]:
    dimensions: set[str] = set()
    count = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        for row in reader:
            count += 1
            dimension = str(row.get("dimension") or "").upper()
            if dimension:
                dimensions.add(dimension)
    return count, len(fields), dimensions


def _url_class(url: str) -> str:
    redacted = redact_url(url)
    return redacted.split("?")[0]


def create_production_databases(paths: ProductionPaths, now: str) -> None:
    paths.provider_db.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, now)


def target_tickers(csv_path: Path) -> set[str]:
    rows = read_csv_rows(csv_path)
    return {str(row.get("ticker") or "").strip().upper() for row in rows if row.get("ticker")}


def ingest_bulk_provider_rows(paths: ProductionPaths, run_id: str, now: str) -> dict[str, Any]:
    universe = target_tickers(paths.bootstrap_csv)
    universe_hash = stable_hash({"tickers": sorted(universe)})
    rows_read = 0
    rows_matched = 0
    rows_excluded_outside_target = 0
    rows_excluded_dimension = 0
    bulk_permaticker_field_present = False
    bulk_rows_with_permaticker = 0
    matched_rows_with_permaticker = 0
    unmatched_provider_rows: list[dict[str, Any]] = []
    permaticker_conflict_rows: list[dict[str, Any]] = []
    permaticker_conflict_keys: set[tuple[str, int, int]] = set()
    matched_tickers: set[str] = set()
    dimension_counter = Counter()
    inserted_by_dimension = Counter()
    identity_counter = Counter()
    with connect(paths.canonical_db) as canonical, connect(paths.provider_db) as provider:
        security_by_ticker = {
            row["current_ticker"]: (row["security_id"], row["company_id"])
            for row in canonical.execute("SELECT current_ticker, security_id, company_id FROM security")
        }
        ticker_security_collisions = canonical.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT current_ticker, COUNT(*) c FROM security GROUP BY current_ticker HAVING c > 1
            )
            """
        ).fetchone()[0]
        provider.execute(
            """
            INSERT OR IGNORE INTO provider_run(
                run_id, provider, started_at_utc, completed_at_utc, status, request_scope, entitlement_scope,
                source_version, metadata_json
            ) VALUES (?, 'SHARADAR', ?, ?, 'SUCCESS', ?, 'Sharadar Fundamentals 5 Years', 'V4-1B', ?)
            """,
            (
                run_id,
                now,
                now,
                PRODUCTION_RUN_TYPE,
                json.dumps({"universe_hash": universe_hash, "target_tickers": len(universe)}, sort_keys=True),
            ),
        )
        with paths.extracted_csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            bulk_permaticker_field_present = "permaticker" in (reader.fieldnames or [])
            for row in reader:
                rows_read += 1
                ticker = str(row.get("ticker") or "").strip().upper()
                dimension = str(row.get("dimension") or "").strip().upper()
                permaticker = nullable_text(row.get("permaticker"))
                if permaticker:
                    bulk_rows_with_permaticker += 1
                if dimension:
                    dimension_counter[dimension] += 1
                if dimension not in ALLOWED_DIMENSIONS:
                    rows_excluded_dimension += 1
                    continue
                if ticker not in universe:
                    rows_excluded_outside_target += 1
                    if len(unmatched_provider_rows) < 250000:
                        unmatched_provider_rows.append(_unmatched_row(row, "OUTSIDE_TARGET_UNIVERSE"))
                    continue
                identity = security_by_ticker.get(ticker)
                if identity is None:
                    rows_excluded_outside_target += 1
                    unmatched_provider_rows.append(_unmatched_row(row, "TARGET_TICKER_NOT_IN_IDENTITY"))
                    continue
                matched_tickers.add(ticker)
                rows_matched += 1
                if permaticker:
                    matched_rows_with_permaticker += 1
                if permaticker:
                    existing_link = canonical.execute(
                        "SELECT security_id, provider_ticker FROM provider_security_identity WHERE provider='SHARADAR' AND provider_security_id=?",
                        (permaticker,),
                    ).fetchone()
                    if existing_link is None:
                        before_identity = canonical.total_changes
                        canonical.execute(
                            """
                            INSERT OR IGNORE INTO provider_security_identity(
                                provider, provider_security_id, security_id, provider_ticker, source, created_at_utc
                            ) VALUES ('SHARADAR', ?, ?, ?, 'SHARADAR_5Y_INITIAL_BOOTSTRAP', ?)
                            """,
                            (permaticker, identity[0], ticker, now),
                        )
                        identity_counter["permaticker_links_inserted"] += int(canonical.total_changes > before_identity)
                    elif int(existing_link["security_id"]) != int(identity[0]):
                        conflict_key = (permaticker, int(existing_link["security_id"]), int(identity[0]))
                        if conflict_key not in permaticker_conflict_keys:
                            permaticker_conflict_keys.add(conflict_key)
                            permaticker_conflict_rows.append(
                                {
                                    "permaticker": permaticker,
                                    "existing_security_id": existing_link["security_id"],
                                    "existing_provider_ticker": existing_link["provider_ticker"],
                                    "candidate_security_id": identity[0],
                                    "candidate_ticker": ticker,
                                    "reason": "PERMATICKER_ASSIGNED_TO_MULTIPLE_SECURITIES",
                                }
                            )
                    else:
                        identity_counter["permaticker_existing_links"] += 1
                inserted = insert_production_sharadar_observation(provider, row, run_id, now, company_id=identity[1], security_id=identity[0])
                if inserted:
                    inserted_by_dimension[dimension] += 1
    unmatched_target_tickers = sorted(universe - matched_tickers)
    summary = {
        "run_id": run_id,
        "run_type": PRODUCTION_RUN_TYPE,
        "universe_tickers": len(universe),
        "universe_hash": universe_hash,
        "bulk_rows_read": rows_read,
        "rows_matched_to_target_universe": rows_matched,
        "rows_excluded_outside_target": rows_excluded_outside_target,
        "rows_excluded_dimension": rows_excluded_dimension,
        "unmatched_target_tickers": len(unmatched_target_tickers),
        "unmatched_target_ticker_sample": unmatched_target_tickers[:100],
        "inserted_by_dimension": dict(sorted(inserted_by_dimension.items())),
        "identity_match": {
            "bulk_permaticker_field_present": bulk_permaticker_field_present,
            "bulk_rows_with_permaticker": bulk_rows_with_permaticker,
            "matched_rows_with_permaticker": matched_rows_with_permaticker,
            "permaticker_links_inserted": identity_counter["permaticker_links_inserted"],
            "permaticker_existing_links_seen": identity_counter["permaticker_existing_links"],
            "permaticker_conflicts": len(permaticker_conflict_rows),
            "ticker_security_collisions": ticker_security_collisions,
        },
        "provider_counts": provider_counts(paths.provider_db),
    }
    write_json(paths.artifact_root / "provider_ingest_summary.json", summary)
    write_csv(paths.artifact_root / "provider_unmatched_rows.csv", unmatched_provider_rows)
    write_csv(paths.artifact_root / "provider_identity_match_audit.csv", permaticker_conflict_rows)
    write_csv(
        paths.artifact_root / "provider_dimension_summary.csv",
        [{"dimension": key, "rows": value, "inserted": inserted_by_dimension.get(key, 0)} for key, value in sorted(dimension_counter.items())],
    )
    return summary


def _unmatched_row(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "ticker": row.get("ticker", ""),
        "dimension": row.get("dimension", ""),
        "reportperiod": row.get("reportperiod", ""),
        "fiscalperiod": row.get("fiscalperiod", ""),
        "reason": reason,
    }


def insert_production_sharadar_observation(
    conn: Any,
    row: Mapping[str, Any],
    run_id: str,
    now: str,
    *,
    company_id: int,
    security_id: int,
) -> bool:
    ticker = str(row.get("ticker") or "").upper()
    dimension = str(row.get("dimension") or "").upper()
    permaticker = nullable_text(row.get("permaticker"))
    provider_record_key = "|".join(
        [
            permaticker or "",
            ticker,
            dimension,
            str(row.get("reportperiod") or ""),
            str(row.get("fiscalperiod") or ""),
            str(row.get("lastupdated") or row.get("date") or ""),
        ]
    )
    content_hash = stable_hash(dict(row))
    observation_id = stable_id("SHARADAR", "fundamentals", provider_record_key, content_hash)
    before = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO provider_observation(
            observation_id, run_id, provider, provider_record_key, company_id, security_id, provider_ticker,
            provider_security_id, native_table, dimension, calendardate, reportperiod, fiscalperiod,
            source_availability_date, fetched_at_utc, content_hash, provider_status, payload_json, provenance_json
        ) VALUES (?, ?, 'SHARADAR', ?, ?, ?, ?, ?, 'fundamentals', ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', ?, '{}')
        """,
        (
            observation_id,
            run_id,
            provider_record_key,
            company_id,
            security_id,
            ticker,
            permaticker,
            dimension,
            nullable_text(row.get("calendardate")),
            nullable_text(row.get("reportperiod")),
            nullable_text(row.get("fiscalperiod")),
            nullable_text(row.get("date")),
            now,
            content_hash,
            json.dumps(dict(row), sort_keys=True, default=str),
        ),
    )
    inserted = conn.total_changes > before
    conn.execute(
        """
        INSERT OR IGNORE INTO sharadar_fundamental_observation(
            observation_id, ticker, permaticker, dimension, calendardate, reportperiod, fiscalperiod, date, lastupdated,
            revenue, gp, opinc, ebit, ebitda, netinc, ncfo, capex, fcf, cashneq, debt, debtc, debtnc,
            sharesbas, shareswa, shareswadil
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            ticker,
            permaticker,
            dimension,
            nullable_text(row.get("calendardate")),
            nullable_text(row.get("reportperiod")),
            nullable_text(row.get("fiscalperiod")),
            nullable_text(row.get("date")),
            nullable_text(row.get("lastupdated")),
            int_or_none(row.get("revenue")),
            int_or_none(row.get("gp")),
            int_or_none(row.get("opinc")),
            int_or_none(row.get("ebit")),
            int_or_none(row.get("ebitda")),
            int_or_none(row.get("netinc")),
            int_or_none(row.get("ncfo")),
            int_or_none(row.get("capex")),
            int_or_none(row.get("fcf")),
            int_or_none(row.get("cashneq")),
            int_or_none(row.get("debt")),
            int_or_none(row.get("debtc")),
            int_or_none(row.get("debtnc")),
            int_or_none(row.get("sharesbas")),
            int_or_none(row.get("shareswa")),
            int_or_none(row.get("shareswadil")),
        ),
    )
    return inserted


def canonicalize_arq_production(paths: ProductionPaths, now: str) -> dict[str, Any]:
    inserted_quarters = 0
    inserted_financials = 0
    inserted_provenance = 0
    skipped_duplicate_arq = 0
    skipped_invalid_fiscalperiod = 0
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        rows = provider.execute(
            """
            SELECT po.observation_id, po.company_id, po.security_id, sfo.*
            FROM sharadar_fundamental_observation sfo
            JOIN provider_observation po ON po.observation_id = sfo.observation_id
            WHERE sfo.dimension='ARQ'
            ORDER BY sfo.ticker, sfo.fiscalperiod, sfo.reportperiod DESC, COALESCE(sfo.lastupdated, sfo.date, '') DESC, po.observation_id
            """
        ).fetchall()
        seen: set[tuple[int, int, str]] = set()
        for row in rows:
            try:
                fiscal_year, fiscal_quarter = parse_fiscalperiod(row["fiscalperiod"])
            except ValueError:
                skipped_invalid_fiscalperiod += 1
                continue
            key = (int(row["company_id"]), fiscal_year, fiscal_quarter)
            if key in seen:
                skipped_duplicate_arq += 1
                continue
            seen.add(key)
            before_quarter = canonical.total_changes
            canonical.execute(
                """
                INSERT OR IGNORE INTO v4_quarter(
                    company_id, fiscal_year, fiscal_quarter, period_end, source_fiscalperiod, source_reportperiod,
                    identity_provider, identity_status, source_availability_date, first_public_result_date,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, 'SHARADAR_ARQ', 'ACCEPTED', ?, NULL, ?, ?)
                """,
                (row["company_id"], fiscal_year, fiscal_quarter, row["reportperiod"], row["fiscalperiod"], row["reportperiod"], row["date"], now, now),
            )
            inserted_quarters += int(canonical.total_changes > before_quarter)
            quarter_id = canonical.execute(
                "SELECT quarter_id FROM v4_quarter WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?",
                (row["company_id"], fiscal_year, fiscal_quarter),
            ).fetchone()[0]
            if canonical.execute("SELECT 1 FROM v4_quarter_financials WHERE quarter_id=?", (quarter_id,)).fetchone():
                continue
            financial_values = {canonical_field: row[native_field] for canonical_field, native_field in SHARADAR_ARQ_FIELD_MAPPING.items()}
            columns = ", ".join(financial_values)
            placeholders = ", ".join("?" for _ in financial_values)
            before_financials = canonical.total_changes
            canonical.execute(
                f"""
                INSERT OR IGNORE INTO v4_quarter_financials(
                    quarter_id, {columns}, canonical_source_policy, created_at_utc, updated_at_utc
                ) VALUES (?, {placeholders}, 'SHARADAR_ARQ_PRIMARY', ?, ?)
                """,
                (quarter_id, *financial_values.values(), now, now),
            )
            inserted_financials += int(canonical.total_changes > before_financials)
            for canonical_field, native_field in SHARADAR_ARQ_FIELD_MAPPING.items():
                if row[native_field] is None:
                    continue
                before_prov = canonical.total_changes
                canonical.execute(
                    """
                    INSERT OR IGNORE INTO v4_field_provenance(
                        quarter_id, canonical_field, provider, provider_observation_id, source_native_field,
                        transformation, accepted_at_utc, rule_version, confidence
                    ) VALUES (?, ?, 'SHARADAR', ?, ?, 'DIRECT', ?, 'SHARADAR_ARQ_PRIMARY_V1', 'HIGH')
                    """,
                    (quarter_id, canonical_field, row["observation_id"], native_field, now),
                )
                inserted_provenance += int(canonical.total_changes > before_prov)
    summary = {
        "inserted_quarters": inserted_quarters,
        "inserted_financial_rows": inserted_financials,
        "inserted_provenance_rows": inserted_provenance,
        "skipped_duplicate_arq_rows": skipped_duplicate_arq,
        "skipped_invalid_fiscalperiod_rows": skipped_invalid_fiscalperiod,
        "canonical_counts": canonical_counts(paths.canonical_db),
    }
    write_json(paths.artifact_root / "canonicalization_summary.json", summary)
    return summary


def canonical_counts(canonical_db: Path) -> dict[str, int]:
    with connect(canonical_db) as conn:
        return {
            "companies": conn.execute("SELECT COUNT(*) FROM company").fetchone()[0],
            "securities": conn.execute("SELECT COUNT(*) FROM security").fetchone()[0],
            "permatickers": conn.execute("SELECT COUNT(*) FROM provider_security_identity WHERE provider='SHARADAR'").fetchone()[0],
            "canonical_quarters": conn.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0],
            "canonical_financial_rows": conn.execute("SELECT COUNT(*) FROM v4_quarter_financials").fetchone()[0],
            "provenance_rows": conn.execute("SELECT COUNT(*) FROM v4_field_provenance").fetchone()[0],
            "cik_rows": conn.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0],
            "fiscal_profiles": conn.execute("SELECT COUNT(*) FROM company_fiscal_calendar_profile").fetchone()[0],
            "fiscal_anchors": conn.execute("SELECT COUNT(*) FROM company_fiscal_year_anchor").fetchone()[0],
        }


def field_coverage(paths: ProductionPaths) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    overall = []
    latest8, latest4, latest1 = [], [], []
    with connect(paths.canonical_db) as conn:
        total = conn.execute("SELECT COUNT(*) FROM v4_quarter_financials").fetchone()[0]
        for field in V4_CANONICAL_FINANCIAL_FIELDS:
            populated = conn.execute(f"SELECT COUNT(*) FROM v4_quarter_financials WHERE {field} IS NOT NULL").fetchone()[0]
            overall.append({"field": field, "rows": total, "populated": populated, "coverage_pct": _pct(populated, total)})
        companies = conn.execute("SELECT company_id FROM company ORDER BY company_id").fetchall()
        latest8_complete_by_field = Counter()
        latest4_complete_by_field = Counter()
        latest1_complete_by_field = Counter()
        companies_with_8 = 0
        companies_with_4 = 0
        companies_with_1 = 0
        all12_complete_8 = 0
        all12_complete_4 = 0
        all12_complete_1 = 0
        critical6_complete_8 = 0
        critical6_complete_4 = 0
        critical6_complete_1 = 0
        for company in companies:
            rows = conn.execute(
                """
                SELECT f.*
                FROM v4_quarter q JOIN v4_quarter_financials f ON f.quarter_id=q.quarter_id
                WHERE q.company_id=?
                ORDER BY q.fiscal_year DESC, q.fiscal_quarter DESC
                LIMIT 8
                """,
                (company["company_id"],),
            ).fetchall()
            if len(rows) == 8:
                companies_with_8 += 1
            if len(rows) >= 4:
                companies_with_4 += 1
            if rows:
                companies_with_1 += 1
            field_complete_8 = {}
            field_complete_4 = {}
            field_complete_1 = {}
            for field in V4_CANONICAL_FINANCIAL_FIELDS:
                complete8 = len(rows) == 8 and all(row[field] is not None for row in rows)
                complete4 = len(rows) >= 4 and all(row[field] is not None for row in rows[:4])
                complete1 = bool(rows) and rows[0][field] is not None
                field_complete_8[field] = complete8
                field_complete_4[field] = complete4
                field_complete_1[field] = complete1
                latest8_complete_by_field[field] += int(complete8)
                latest4_complete_by_field[field] += int(complete4)
                latest1_complete_by_field[field] += int(complete1)
            all12_complete_8 += int(len(rows) == 8 and all(field_complete_8.values()))
            all12_complete_4 += int(len(rows) >= 4 and all(field_complete_4.values()))
            all12_complete_1 += int(bool(rows) and all(field_complete_1.values()))
            critical6_complete_8 += int(len(rows) == 8 and all(field_complete_8[field] for field in CRITICAL_FIELDS))
            critical6_complete_4 += int(len(rows) >= 4 and all(field_complete_4[field] for field in CRITICAL_FIELDS))
            critical6_complete_1 += int(bool(rows) and all(field_complete_1[field] for field in CRITICAL_FIELDS))
        for field in V4_CANONICAL_FINANCIAL_FIELDS:
            latest8.append({"field": field, "companies_complete_latest8q": latest8_complete_by_field[field]})
            latest4.append({"field": field, "companies_complete_latest4q": latest4_complete_by_field[field]})
            latest1.append({"field": field, "companies_complete_latestq": latest1_complete_by_field[field]})
    summary = {
        "companies_with_8_quarters": companies_with_8,
        "companies_with_4_quarters": companies_with_4,
        "companies_with_latest_quarter": companies_with_1,
        "all_12_fields_complete_latest8q": all12_complete_8,
        "all_12_fields_complete_latest4q": all12_complete_4,
        "all_12_fields_complete_latestq": all12_complete_1,
        "critical_6_fields_complete_latest8q": critical6_complete_8,
        "critical_6_fields_complete_latest4q": critical6_complete_4,
        "critical_6_fields_complete_latestq": critical6_complete_1,
    }
    write_csv(paths.artifact_root / "canonical_field_coverage.csv", overall)
    write_csv(paths.artifact_root / "canonical_latest8q_coverage.csv", latest8)
    write_csv(paths.artifact_root / "canonical_latest4q_coverage.csv", latest4)
    write_csv(paths.artifact_root / "canonical_latestq_coverage.csv", latest1)
    return overall, latest8, latest4, latest1, summary


def _pct(part: int, total: int) -> float:
    return round((part / total * 100.0), 4) if total else 0.0


def provenance_summary(paths: ProductionPaths) -> dict[str, Any]:
    with connect(paths.canonical_db) as conn:
        by_field = [dict(row) for row in conn.execute("SELECT canonical_field, COUNT(*) rows FROM v4_field_provenance GROUP BY canonical_field ORDER BY canonical_field")]
        missing = canonical_fields_without_provenance(conn)
    summary = {"by_field": by_field, "canonical_fields_without_provenance": missing}
    write_json(paths.artifact_root / "canonical_provenance_summary.json", summary)
    return summary


def canonical_fields_without_provenance(conn: Any) -> int:
    missing = 0
    for row in conn.execute("SELECT * FROM v4_quarter_financials"):
        provenanced = {
            prov["canonical_field"]
            for prov in conn.execute("SELECT canonical_field FROM v4_field_provenance WHERE quarter_id=?", (row["quarter_id"],))
        }
        for field in V4_CANONICAL_FINANCIAL_FIELDS:
            if row[field] is not None and field not in provenanced:
                missing += 1
    return missing


def fiscal_anchor_validation(paths: ProductionPaths) -> list[dict[str, Any]]:
    rows = []
    with connect(paths.canonical_db) as conn:
        for row in conn.execute(
            """
            SELECT s.current_ticker AS ticker, q.company_id, q.fiscal_year, q.fiscal_quarter, q.period_end, q.source_fiscalperiod
            FROM v4_quarter q
            JOIN security s ON s.company_id=q.company_id
            ORDER BY s.current_ticker, q.fiscal_year, q.fiscal_quarter
            """
        ):
            anchor = conn.execute(
                "SELECT fiscal_year_start FROM company_fiscal_year_anchor WHERE company_id=? AND fiscal_year=?",
                (row["company_id"], row["fiscal_year"]),
            ).fetchone()
            next_anchor = conn.execute(
                "SELECT fiscal_year_start FROM company_fiscal_year_anchor WHERE company_id=? AND fiscal_year=?",
                (row["company_id"], row["fiscal_year"] + 1),
            ).fetchone()
            classification = classify_anchor(row["period_end"], anchor, next_anchor)
            rows.append(
                {
                    "ticker": row["ticker"],
                    "fiscal_year": row["fiscal_year"],
                    "fiscal_quarter": row["fiscal_quarter"],
                    "source_fiscalperiod": row["source_fiscalperiod"],
                    "period_end": row["period_end"],
                    "classification": classification,
                }
            )
    write_csv(paths.artifact_root / "fiscal_anchor_validation.csv", rows)
    return rows


def classify_anchor(period_end_text: str, anchor: Any, next_anchor: Any) -> str:
    if anchor is None:
        return "ANCHOR_NOT_AVAILABLE"
    period_end = date.fromisoformat(period_end_text)
    start = date.fromisoformat(anchor["fiscal_year_start"])
    if period_end < start:
        return "ANCHOR_MISMATCH"
    if next_anchor is None:
        return "ANCHOR_VALIDATED"
    next_start = date.fromisoformat(next_anchor["fiscal_year_start"])
    if period_end < next_start:
        return "ANCHOR_VALIDATED"
    return "ANCHOR_MISMATCH"


def quarter_continuity(paths: ProductionPaths) -> tuple[list[dict[str, Any]], dict[str, int]]:
    audit = []
    counts = Counter()
    with connect(paths.canonical_db) as conn:
        for company in conn.execute("SELECT company_id FROM company ORDER BY company_id"):
            rows = conn.execute(
                "SELECT fiscal_year, fiscal_quarter FROM v4_quarter WHERE company_id=? ORDER BY fiscal_year, fiscal_quarter",
                (company["company_id"],),
            ).fetchall()
            if not rows:
                continue
            indexes = [_quarter_index(row["fiscal_year"], row["fiscal_quarter"]) for row in rows]
            duplicate = len(indexes) != len(set(indexes))
            gaps = sum(max(0, b - a - 1) for a, b in zip(indexes, indexes[1:]))
            if duplicate:
                status = "DUPLICATE_FISCALPERIOD"
            elif gaps:
                status = "GAP"
            elif rows[0]["fiscal_quarter"] != "Q1":
                status = "HISTORY_WINDOW_TRUNCATED"
            else:
                status = "CONTINUOUS"
            counts[status] += 1
            audit.append({"company_id": company["company_id"], "quarters": len(rows), "status": status, "gap_count": gaps})
    write_csv(paths.artifact_root / "quarter_continuity_audit.csv", audit)
    return audit, dict(counts)


def _quarter_index(fiscal_year: int, fiscal_quarter: str) -> int:
    return fiscal_year * 4 + int(fiscal_quarter[1])


def q4_global_coverage(paths: ProductionPaths) -> dict[str, Any]:
    rows_out = []
    counts = Counter()
    with connect(paths.canonical_db) as conn:
        for company in conn.execute("SELECT company_id FROM company ORDER BY company_id"):
            years = defaultdict(set)
            for row in conn.execute("SELECT fiscal_year, fiscal_quarter FROM v4_quarter WHERE company_id=?", (company["company_id"],)):
                years[row["fiscal_year"]].add(row["fiscal_quarter"])
            for fiscal_year, quarters in years.items():
                if quarters == {"Q1", "Q2", "Q3", "Q4"}:
                    status = "FULL_Q1_Q4_SEQUENCE"
                elif "Q4" not in quarters and len(quarters) >= 3:
                    status = "Q4_MISSING"
                elif "Q4" in quarters:
                    status = "TRANSITION_OR_STUB"
                else:
                    status = "OTHER_GAP"
                counts[status] += 1
                rows_out.append({"company_id": company["company_id"], "fiscal_year": fiscal_year, "quarters": ",".join(sorted(quarters)), "status": status})
    write_csv(paths.artifact_root / "q4_global_coverage.csv", rows_out)
    evaluated = counts["FULL_Q1_Q4_SEQUENCE"] + counts["Q4_MISSING"]
    return {
        **dict(counts),
        "completed_fys_evaluated": evaluated,
        "explicit_q4_present": counts["FULL_Q1_Q4_SEQUENCE"],
        "q4_missing": counts["Q4_MISSING"],
        "q4_coverage_pct": _pct(counts["FULL_Q1_Q4_SEQUENCE"], evaluated),
    }


def fcf_reconciliation(paths: ProductionPaths) -> dict[str, int]:
    rows, counts = [], Counter()
    with connect(paths.provider_db) as conn:
        for row in conn.execute("SELECT ticker, dimension, reportperiod, fiscalperiod, ncfo, capex, fcf FROM sharadar_fundamental_observation"):
            classification = _classify_sum(row["ncfo"], row["capex"], row["fcf"])
            counts[classification] += 1
            rows.append(dict(row, classification=classification))
    write_csv(paths.artifact_root / "fcf_global_reconciliation.csv", rows)
    return dict(counts)


def debt_reconciliation(paths: ProductionPaths) -> dict[str, int]:
    rows, counts = [], Counter()
    with connect(paths.provider_db) as conn:
        for row in conn.execute("SELECT ticker, dimension, reportperiod, fiscalperiod, debt, debtc, debtnc FROM sharadar_fundamental_observation"):
            classification = _classify_debt(row["debt"], row["debtc"], row["debtnc"])
            counts[classification] += 1
            rows.append(dict(row, classification=classification))
    write_csv(paths.artifact_root / "debt_global_reconciliation.csv", rows)
    return dict(counts)


def _classify_sum(left: int | None, right: int | None, total: int | None) -> str:
    if left is None or right is None or total is None:
        return "MISSING_COMPONENT"
    diff = (left + right) - total
    if diff == 0:
        return "EXACT"
    if abs(diff) <= 1:
        return "ROUNDING"
    return "DIFFERENT"


def _classify_debt(debt: int | None, debtc: int | None, debtnc: int | None) -> str:
    if debt is None or debtc is None or debtnc is None:
        return "MISSING_COMPONENT"
    diff = (debtc + debtnc) - debt
    if diff == 0:
        return "EXACT"
    if abs(diff) <= 1:
        return "ROUNDING"
    if debt >= debtc + debtnc:
        return "OTHER_COMPONENT"
    return "DIFFERENT"


def sharesbas_audit(paths: ProductionPaths) -> dict[str, int]:
    rows, counts = [], Counter()
    with connect(paths.provider_db) as conn:
        grouped: dict[str, list[Any]] = defaultdict(list)
        for row in conn.execute(
            "SELECT ticker, dimension, reportperiod, fiscalperiod, sharesbas FROM sharadar_fundamental_observation WHERE dimension='ARQ' ORDER BY ticker, reportperiod"
        ):
            grouped[row["ticker"]].append(row)
            if row["sharesbas"] is not None:
                counts["populated"] += 1
            if row["sharesbas"] == 0:
                counts["zero"] += 1
            if row["sharesbas"] is not None and row["sharesbas"] < 0:
                counts["negative"] += 1
        for ticker, items in grouped.items():
            previous = None
            for row in items:
                classification = "OK"
                if previous and row["sharesbas"] and previous["sharesbas"]:
                    ratio = row["sharesbas"] / previous["sharesbas"]
                    if ratio >= 4.0 or ratio <= 0.25:
                        classification = "UNEXPLAINED_SHARE_DISCONTINUITY"
                        counts["unexplained_discontinuities"] += 1
                rows.append(dict(row, classification=classification))
                previous = row
    write_csv(paths.artifact_root / "sharesbas_global_audit.csv", rows)
    return dict(counts)


def production_integrity(paths: ProductionPaths) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    provider, canonical, analysis = {}, {}, {}
    with connect(paths.provider_db) as conn:
        provider["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
        provider["foreign_key_errors"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        provider["duplicate_provider_observation_identity"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT provider, native_table, provider_record_key, content_hash, COUNT(*) c
              FROM provider_observation GROUP BY provider, native_table, provider_record_key, content_hash HAVING c > 1
            )
            """
        ).fetchone()[0]
        provider["orphan_provider_observations"] = conn.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation s LEFT JOIN provider_observation p ON p.observation_id=s.observation_id WHERE p.observation_id IS NULL"
        ).fetchone()[0]
    with connect(paths.canonical_db) as conn:
        canonical["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
        canonical["foreign_key_errors"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        canonical["canonical_field_contract_present"] = canonical_field_contract_present(conn)
        canonical["duplicate_canonical_fyq"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT company_id, fiscal_year, fiscal_quarter, COUNT(*) c
              FROM v4_quarter GROUP BY company_id, fiscal_year, fiscal_quarter HAVING c > 1
            )
            """
        ).fetchone()[0]
        canonical["orphan_securities"] = conn.execute("SELECT COUNT(*) FROM security s LEFT JOIN company c ON c.company_id=s.company_id WHERE c.company_id IS NULL").fetchone()[0]
        canonical["orphan_financials"] = conn.execute("SELECT COUNT(*) FROM v4_quarter_financials f LEFT JOIN v4_quarter q ON q.quarter_id=f.quarter_id WHERE q.quarter_id IS NULL").fetchone()[0]
        canonical["orphan_provenance"] = conn.execute("SELECT COUNT(*) FROM v4_field_provenance p LEFT JOIN v4_quarter q ON q.quarter_id=p.quarter_id WHERE q.quarter_id IS NULL").fetchone()[0]
        canonical["canonical_fields_without_provenance"] = canonical_fields_without_provenance(conn)
        canonical["invalid_fiscal_quarters"] = conn.execute("SELECT COUNT(*) FROM v4_quarter WHERE fiscal_quarter NOT IN ('Q1','Q2','Q3','Q4')").fetchone()[0]
        canonical["invalid_cik_format"] = conn.execute("SELECT COUNT(*) FROM company_cik WHERE cik_normalized NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'").fetchone()[0]
        canonical["duplicate_fiscal_anchors"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT company_id, fiscal_year, COUNT(*) c
              FROM company_fiscal_year_anchor GROUP BY company_id, fiscal_year HAVING c > 1
            )
            """
        ).fetchone()[0]
        canonical["ttm_rows"] = conn.execute("SELECT COUNT(*) FROM v4_ttm_contract").fetchone()[0]
    with connect(paths.analysis_db) as conn:
        analysis["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
        analysis["foreign_key_errors"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        analysis["score_rows"] = conn.execute("SELECT COUNT(*) FROM score_result").fetchone()[0]
        analysis["lifecycle_rows"] = conn.execute("SELECT COUNT(*) FROM lifecycle_result").fetchone()[0]
        analysis["valuation_rows"] = conn.execute("SELECT COUNT(*) FROM valuation_result").fetchone()[0]
    cross = cross_db_integrity(paths)
    write_json(paths.artifact_root / "provider_integrity.json", provider)
    write_json(paths.artifact_root / "canonical_integrity.json", canonical)
    write_json(paths.artifact_root / "analysis_integrity.json", analysis)
    write_json(paths.artifact_root / "cross_db_integrity.json", cross)
    return provider, canonical, analysis, cross


def cross_db_integrity(paths: ProductionPaths) -> dict[str, int]:
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical, connect(paths.analysis_db) as analysis:
        canonical_security_ids = {row["security_id"] for row in canonical.execute("SELECT security_id FROM security")}
        provider_security_ids = {row["security_id"] for row in provider.execute("SELECT DISTINCT security_id FROM provider_observation WHERE security_id IS NOT NULL")}
        provider_observation_ids = {row["observation_id"] for row in provider.execute("SELECT observation_id FROM provider_observation")}
        provenance_observation_ids = {row["provider_observation_id"] for row in canonical.execute("SELECT DISTINCT provider_observation_id FROM v4_field_provenance")}
        canonical_company_ids = {row["company_id"] for row in canonical.execute("SELECT company_id FROM company")}
        analysis_company_ids = {
            row["company_id"]
            for table in ("score_result", "lifecycle_result", "valuation_result")
            for row in analysis.execute(f"SELECT DISTINCT company_id FROM {table}")
        }
    return {
        "provider_observation_security_missing_in_canonical": len(provider_security_ids - canonical_security_ids),
        "canonical_provenance_provider_observation_missing": len(provenance_observation_ids - provider_observation_ids),
        "analysis_company_ids_missing_in_canonical": len(analysis_company_ids - canonical_company_ids),
        "dangling_provider_observation_links": len(provider_security_ids - canonical_security_ids),
    }


def baseline_fingerprints(paths: ProductionPaths) -> dict[str, str]:
    return {
        "company_security_identity": sqlite_query_hash(paths.canonical_db, "SELECT company_id, company_key FROM company ORDER BY company_id")
        + sqlite_query_hash(paths.canonical_db, "SELECT security_id, company_id, current_ticker FROM security ORDER BY security_id"),
        "fiscal_calendar_anchors": sqlite_query_hash(paths.canonical_db, "SELECT company_id, fiscal_year, fiscal_year_start FROM company_fiscal_year_anchor ORDER BY company_id, fiscal_year"),
        "provider_observations": sqlite_query_hash(paths.provider_db, "SELECT observation_id, provider_record_key, content_hash FROM provider_observation ORDER BY observation_id"),
        "canonical_quarter_identity": sqlite_query_hash(paths.canonical_db, "SELECT quarter_id, company_id, fiscal_year, fiscal_quarter, period_end FROM v4_quarter ORDER BY quarter_id"),
        "canonical_financial_values": sqlite_query_hash(paths.canonical_db, "SELECT * FROM v4_quarter_financials ORDER BY quarter_id"),
        "field_provenance": sqlite_query_hash(paths.canonical_db, "SELECT quarter_id, canonical_field, provider_observation_id, source_native_field FROM v4_field_provenance ORDER BY quarter_id, canonical_field"),
    }


def sqlite_query_hash(db_path: Path, query: str) -> str:
    hasher = hashlib.sha256()
    with connect(db_path) as conn:
        for row in conn.execute(query):
            hasher.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode("utf-8"))
            hasher.update(b"\n")
    return hasher.hexdigest()


def replay(paths: ProductionPaths, before_fingerprints: Mapping[str, str], now: str) -> dict[str, Any]:
    before_counts = {"provider": provider_counts(paths.provider_db), "canonical": canonical_counts(paths.canonical_db)}
    bootstrap_identity_calendar(paths.canonical_db, paths.bootstrap_csv, now)
    ingest_bulk_provider_rows(paths, "v4_1b_production_bootstrap", now)
    canonicalize_arq_production(paths, now)
    after_counts = {"provider": provider_counts(paths.provider_db), "canonical": canonical_counts(paths.canonical_db)}
    after_fingerprints = baseline_fingerprints(paths)
    summary = {
        "before_counts": before_counts,
        "after_counts": after_counts,
        "provider_observations_before_after": [
            before_counts["provider"]["provider_observations"],
            after_counts["provider"]["provider_observations"],
        ],
        "canonical_quarters_before_after": [
            before_counts["canonical"]["canonical_quarters"],
            after_counts["canonical"]["canonical_quarters"],
        ],
        "canonical_financial_rows_before_after": [
            before_counts["canonical"]["canonical_financial_rows"],
            after_counts["canonical"]["canonical_financial_rows"],
        ],
        "provenance_before_after": [
            before_counts["canonical"]["provenance_rows"],
            after_counts["canonical"]["provenance_rows"],
        ],
        "changed_canonical_values": int(before_fingerprints["canonical_financial_values"] != after_fingerprints["canonical_financial_values"]),
        "duplicate_rows_created": (
            after_counts["provider"]["provider_observations"] - before_counts["provider"]["provider_observations"]
            + after_counts["canonical"]["canonical_quarters"] - before_counts["canonical"]["canonical_quarters"]
            + after_counts["canonical"]["canonical_financial_rows"] - before_counts["canonical"]["canonical_financial_rows"]
            + after_counts["canonical"]["provenance_rows"] - before_counts["canonical"]["provenance_rows"]
        ),
        "fingerprints_identical": before_fingerprints == after_fingerprints,
        "before_fingerprints": dict(before_fingerprints),
        "after_fingerprints": after_fingerprints,
    }
    write_json(paths.artifact_root / "production_replay_summary.json", summary)
    write_json(paths.artifact_root / "production_replay_fingerprints.json", {"before": before_fingerprints, "after": after_fingerprints})
    return summary


def hard_case_validation(paths: ProductionPaths) -> list[dict[str, Any]]:
    expected = {
        "AAPL": ("2025-12-27", "2026-Q1"),
        "WDAY": ("2026-04-30", "2027-Q1"),
        "ASTH": ("2026-03-31", "2026-Q1"),
        "CECO": ("2026-03-31", "2026-Q1"),
    }
    rows = []
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        for ticker, (period_end, fiscalperiod) in expected.items():
            provider_row = provider.execute(
                """
                SELECT *
                FROM sharadar_fundamental_observation
                WHERE ticker=? AND dimension='ARQ' AND reportperiod=? AND fiscalperiod=?
                """,
                (ticker, period_end, fiscalperiod),
            ).fetchone()
            identity = canonical.execute(
                """
                SELECT s.current_ticker, psi.provider_security_id AS permaticker, cc.cik_normalized
                FROM security s
                LEFT JOIN provider_security_identity psi ON psi.security_id=s.security_id AND psi.provider='SHARADAR'
                LEFT JOIN company_cik cc ON cc.company_id=s.company_id
                WHERE s.current_ticker=?
                """,
                (ticker,),
            ).fetchone()
            q4 = provider.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE ticker=? AND dimension='ARQ' AND fiscalperiod LIKE '%-Q4'", (ticker,)).fetchone()[0]
            rows.append(
                {
                    "ticker": ticker,
                    "expected_reportperiod": period_end,
                    "expected_fiscalperiod": fiscalperiod,
                    "found": int(provider_row is not None),
                    "permaticker": identity["permaticker"] if identity else "",
                    "cik": identity["cik_normalized"] if identity else "",
                    "recent_q4_rows": q4,
                    "result": "PASS" if provider_row is not None else "FAIL",
                }
            )
    write_csv(paths.artifact_root / "hard_case_production_validation.csv", rows)
    return rows


def snapshot_databases(paths: ProductionPaths) -> Path:
    target = paths.artifact_root / "baseline_before_replay"
    target.mkdir(parents=True, exist_ok=True)
    for path in (paths.provider_db, paths.canonical_db, paths.analysis_db):
        shutil.copy2(path, target / path.name)
    return target


def write_identity_artifacts(paths: ProductionPaths, identity_bootstrap: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    bootstrap_summary = summarize_bootstrap(paths.bootstrap_csv, identity_bootstrap)
    fiscal_summary = fiscal_anchor_coverage(
        identity_bootstrap["rows"],
        identity_bootstrap["mapping"],
        identity_bootstrap["anchor_rows"],
        identity_bootstrap["profile_rows"],
    )
    write_json(paths.artifact_root / "production_identity_bootstrap_summary.json", bootstrap_summary)
    write_csv(paths.artifact_root / "production_cik_summary.csv", identity_bootstrap["cik_audit"])
    write_json(paths.artifact_root / "production_fiscal_calendar_summary.json", fiscal_summary)
    return bootstrap_summary, fiscal_summary


def run_production_bootstrap(paths: ProductionPaths, *, api_key: str | None = None, git_status: str = "", opener: Callable[[Request, float], Any] | None = None) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    key_configured = bool(api_key)
    preflight_result = preflight(paths, api_key_configured=key_configured, git_status=git_status)
    write_json(paths.artifact_root / "production_preflight.json", preflight_result)
    if not preflight_result["ok_to_create"]:
        summary = {
            "classification": "V4_PRODUCTION_BOOTSTRAP_BLOCKED",
            "blocking_reasons": preflight_result["blocking_reasons"],
            "preflight": preflight_result,
            "next_action": "RESOLVE PREFLIGHT BLOCKERS BEFORE CREATING PRODUCTION V4 DATABASES",
        }
        write_json(paths.artifact_root / "v4_1b_summary.json", summary)
        return summary
    manifest = download_sharadar_5y_bulk(paths, api_key=api_key, opener=opener)
    if manifest.get("status") != "SUCCESS":
        summary = {
            "classification": "V4_PRODUCTION_BOOTSTRAP_BLOCKED",
            "bulk_manifest": manifest,
            "preflight": preflight_result,
            "next_action": "RESOLVE SHARADAR 5Y BULK DOWNLOAD FAILURE BEFORE PRODUCTION BOOTSTRAP",
        }
        write_json(paths.artifact_root / "v4_1b_summary.json", summary)
        return summary
    now = utc_now()
    create_production_databases(paths, now)
    identity_bootstrap = bootstrap_identity_calendar(paths.canonical_db, paths.bootstrap_csv, now)
    identity_summary, fiscal_summary = write_identity_artifacts(paths, identity_bootstrap)
    provider_summary = ingest_bulk_provider_rows(paths, "v4_1b_production_bootstrap", now)
    canonical_summary = canonicalize_arq_production(paths, now)
    coverage, latest8, latest4, latest1, coverage_summary = field_coverage(paths)
    provenance = provenance_summary(paths)
    fiscal_rows = fiscal_anchor_validation(paths)
    continuity_rows, continuity_summary = quarter_continuity(paths)
    q4_summary = q4_global_coverage(paths)
    fcf = fcf_reconciliation(paths)
    debt = debt_reconciliation(paths)
    shares = sharesbas_audit(paths)
    hard_cases = hard_case_validation(paths)
    provider_integrity, canonical_integrity, analysis_integrity, cross_db = production_integrity(paths)
    fingerprints = baseline_fingerprints(paths)
    write_json(paths.artifact_root / "v4_production_baseline_fingerprints.json", fingerprints)
    snapshot_path = snapshot_databases(paths)
    replay_summary = replay(paths, fingerprints, utc_now())
    provider_integrity, canonical_integrity, analysis_integrity, cross_db = production_integrity(paths)
    review_items = {
        "cik_missing": identity_summary["companies_still_cik_null"],
        "cik_pattern_not_found": identity_summary["pattern_not_found"],
        "fiscal_anchor_mismatch": sum(1 for row in fiscal_rows if row["classification"] == "ANCHOR_MISMATCH"),
        "hard_case_failures": sum(1 for row in hard_cases if row["result"] != "PASS"),
        "fcf_different": fcf.get("DIFFERENT", 0),
        "debt_different": debt.get("DIFFERENT", 0),
        "share_discontinuities": shares.get("unexplained_discontinuities", 0),
        "permaticker_conflicts": provider_summary["identity_match"]["permaticker_conflicts"],
        "permaticker_unavailable_in_bulk": int(not provider_summary["identity_match"]["bulk_permaticker_field_present"]),
    }
    blocking = (
        canonical_integrity["canonical_fields_without_provenance"]
        + canonical_integrity["duplicate_canonical_fyq"]
        + provider_integrity["duplicate_provider_observation_identity"]
        + cross_db["canonical_provenance_provider_observation_missing"]
        + replay_summary["changed_canonical_values"]
        + replay_summary["duplicate_rows_created"]
    )
    if blocking:
        classification = "V4_PRODUCTION_BOOTSTRAP_BLOCKED"
        next_action = "RESOLVE PRODUCTION BOOTSTRAP INTEGRITY OR REPLAY FAILURES BEFORE V4-2"
    elif any(review_items.values()):
        classification = "V4_PRODUCTION_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS"
        next_action = "KEEP THE PRODUCTION V4 BASELINE FROZEN; RESOLVE ONLY THE SPECIFIC IDENTITY / COVERAGE / PROVIDER QUALITY REVIEW ITEMS BEFORE TTM MIGRATION"
    else:
        classification = "V4_PRODUCTION_BOOTSTRAP_COMPLETE"
        next_action = "PROCEED TO V4-2: MIGRATE AND VALIDATE THE EBIT-FIRST TTM ENGINE IN RAWCANDLE AGAINST THE NEW V4 CANONICAL DATABASE; DO NOT MIGRATE SCORE/LIFECYCLE/VALUATION UNTIL TTM PARITY IS PROVEN"
    summary = {
        "classification": classification,
        "next_action": next_action,
        "artifact_root": str(paths.artifact_root),
        "production_paths": {
            "provider_db": str(paths.provider_db),
            "canonical_db": str(paths.canonical_db),
            "analysis_db": str(paths.analysis_db),
        },
        "preflight": preflight_result,
        "bulk_manifest": manifest,
        "identity": identity_summary,
        "fiscal_metadata": fiscal_summary,
        "provider_ingest": provider_summary,
        "canonicalization": canonical_summary,
        "field_coverage": coverage,
        "latest8q": {
            "rows": latest8,
            "companies_with_8_quarters": coverage_summary["companies_with_8_quarters"],
            "all_12_fields_complete_latest8q": coverage_summary["all_12_fields_complete_latest8q"],
            "critical_6_fields_complete_latest8q": coverage_summary["critical_6_fields_complete_latest8q"],
        },
        "latest4q": {
            "rows": latest4,
            "companies_with_4_quarters": coverage_summary["companies_with_4_quarters"],
            "all_12_fields_complete_latest4q": coverage_summary["all_12_fields_complete_latest4q"],
            "critical_6_fields_complete_latest4q": coverage_summary["critical_6_fields_complete_latest4q"],
        },
        "latestq": {
            "rows": latest1,
            "companies_with_latest_quarter": coverage_summary["companies_with_latest_quarter"],
            "all_12_fields_complete_latestq": coverage_summary["all_12_fields_complete_latestq"],
            "critical_6_fields_complete_latestq": coverage_summary["critical_6_fields_complete_latestq"],
        },
        "provenance": provenance,
        "fiscal_anchor_validation": dict(Counter(row["classification"] for row in fiscal_rows)),
        "quarter_continuity": continuity_summary,
        "q4": q4_summary,
        "fcf": fcf,
        "debt": debt,
        "shares": shares,
        "hard_cases": hard_cases,
        "integrity": {
            "provider": provider_integrity,
            "canonical": canonical_integrity,
            "analysis": analysis_integrity,
            "cross_db": cross_db,
        },
        "replay": replay_summary,
        "baseline_fingerprints": fingerprints,
        "snapshot_path": str(snapshot_path),
        "schema_validation": schema_validation(paths),
        "safety": {
            "yahoo_calls": 0,
            "sec_calls": 0,
            "v3_writes": 0,
            "swingmaster_runtime_dependency": 0,
            "api_key_exposure": "NO",
        },
    }
    write_json(paths.artifact_root / "v4_1b_summary.json", summary)
    (paths.artifact_root / "next_action.md").write_text(next_action + "\n", encoding="utf-8")
    write_production_baseline_doc(paths.repo_root / "docs" / "fundamentals_v4" / "fundamentals_v4_production_baseline.md", summary)
    return summary


def write_production_baseline_doc(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Fundamentals V4 Production Baseline\n\n"
        f"Classification: `{summary['classification']}`\n\n"
        f"Artifact root: `{summary['artifact_root']}`\n\n"
        "Production databases:\n\n"
        f"- `{summary['production_paths']['provider_db']}`\n"
        f"- `{summary['production_paths']['canonical_db']}`\n"
        f"- `{summary['production_paths']['analysis_db']}`\n\n"
        "Sharadar history scope: `years=5`.\n\n"
        f"Universe: `{summary['identity']['csv_tickers']}` local bootstrap tickers from `temp/v3_active_tickers_99_27.csv`.\n\n"
        f"Provider observations: `{summary['provider_ingest']['provider_counts']['provider_observations']}`. "
        f"Canonical quarters: `{summary['canonicalization']['canonical_counts']['canonical_quarters']}`. "
        f"Provenance rows: `{summary['canonicalization']['canonical_counts']['provenance_rows']}`.\n\n"
        f"CIK populated: `{summary['identity']['company_ciks_imported']}`. CIK NULL: `{summary['identity']['companies_still_cik_null']}`.\n\n"
        f"Q4 completed FY coverage: `{summary['q4']['q4_coverage_pct']}` percent.\n\n"
        f"Latest8Q all-12 complete: `{summary['latest8q']['all_12_fields_complete_latest8q']}`. "
        f"Latest4Q all-12 complete: `{summary['latest4q']['all_12_fields_complete_latest4q']}`. "
        f"Latest quarter all-12 complete: `{summary['latestq']['all_12_fields_complete_latestq']}`.\n\n"
        "Baseline fingerprints are stored in `v4_production_baseline_fingerprints.json` under the artifact root. "
        "Generated Sharadar bulk files and audit artifacts remain under `temp/` and are not committed.\n\n"
        f"Next action: `{summary['next_action']}`\n",
        encoding="utf-8",
    )
