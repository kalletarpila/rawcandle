from __future__ import annotations

import csv
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.schema.migrations import bootstrap_all, connect
from rawcandle.fundamentals.schema.prototype import (
    PROTOTYPE_TICKERS,
    canonical_counts,
    canonicalize_arq,
    default_acceptance_root,
    load_provider_subset,
    nullable_text,
    parse_fiscalperiod,
    provider_counts,
    schema_validation,
    utc_now,
    utc_stamp,
    validate_integrity,
    write_csv,
    write_json,
)


BOOTSTRAP_SOURCE_NAME = "v3_active_tickers_99_27"
BOOTSTRAP_SOURCE_FILENAME = f"{BOOTSTRAP_SOURCE_NAME}.csv"
CIK_URL_PATTERN = re.compile(r"CIK([0-9]{10})\.json")
FY_START_COLUMN_PATTERN = re.compile(r"^FY([0-9]{4}) alkoi$")
IMPORTABLE_CIK_CLASSES = {"CIK_VALID_UNIQUE", "CIK_MULTIPLE_TICKER_EXPECTED_OR_REVIEW"}


@dataclass(frozen=True)
class IdentityCalendarPaths:
    artifact_root: Path
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    acceptance_root: Path
    bootstrap_csv: Path


def identity_calendar_paths(
    repo_root: Path,
    timestamp: str | None = None,
    acceptance_root: Path | None = None,
    bootstrap_csv: Path | None = None,
) -> IdentityCalendarPaths:
    stamp = timestamp or utc_stamp()
    artifact_root = repo_root / "temp" / "fundamentals_v4_1a1_identity_calendar_bootstrap" / stamp
    return IdentityCalendarPaths(
        artifact_root=artifact_root,
        provider_db=artifact_root / "prototype_provider.db",
        canonical_db=artifact_root / "prototype_v4.db",
        analysis_db=artifact_root / "prototype_analysis.db",
        acceptance_root=acceptance_root or default_acceptance_root(repo_root),
        bootstrap_csv=bootstrap_csv or locate_bootstrap_csv(repo_root),
    )


def locate_bootstrap_csv(repo_root: Path) -> Path:
    expected = repo_root / "temp" / BOOTSTRAP_SOURCE_FILENAME
    if expected.exists():
        return expected
    matches = sorted(repo_root.glob(f"**/{BOOTSTRAP_SOURCE_FILENAME}"))
    if not matches:
        raise FileNotFoundError(f"{BOOTSTRAP_SOURCE_FILENAME} not found under {repo_root}")
    return matches[0]


def read_bootstrap_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def detect_column_mapping(fieldnames: Iterable[str]) -> dict[str, Any]:
    headers = list(fieldnames)
    ticker_column = _first_matching(headers, lambda value: value.lower() == "ticker")
    source_column = _first_matching(headers, lambda value: value in {"Lähde", "source", "Source"})
    typical_column = _first_matching(headers, lambda value: value.lower().startswith("tyypillinen") or value == "typical_fiscal_year_start")
    chain_status_column = _first_matching(headers, lambda value: value == "chain_status")
    break_reason_column = _first_matching(headers, lambda value: value == "break_reason")
    fy_start_columns = {
        int(match.group(1)): header
        for header in headers
        if (match := FY_START_COLUMN_PATTERN.match(header))
    }
    missing = [
        name
        for name, value in (
            ("ticker", ticker_column),
            ("source", source_column),
            ("typical_fiscal_year_start", typical_column),
            ("chain_status", chain_status_column),
            ("break_reason", break_reason_column),
        )
        if not value
    ]
    if not fy_start_columns:
        missing.append("fy_start_columns")
    return {
        "valid": not missing,
        "ticker_column": ticker_column,
        "source_column": source_column,
        "typical_fiscal_year_start_column": typical_column,
        "chain_status_column": chain_status_column,
        "break_reason_column": break_reason_column,
        "fy_start_columns": {str(year): column for year, column in sorted(fy_start_columns.items())},
        "missing_required_columns": missing,
    }


def _first_matching(headers: Iterable[str], predicate: Any) -> str | None:
    return next((header for header in headers if predicate(header)), None)


def parse_cik_from_source_url(source_url: str | None) -> tuple[str | None, str]:
    source = (source_url or "").strip()
    if not source:
        return None, "CIK_MISSING_SOURCE"
    match = CIK_URL_PATTERN.search(source)
    if match:
        return match.group(1), "CIK_VALID_UNIQUE"
    if "CIK" in source and ".json" in source:
        return None, "CIK_FORMAT_INVALID"
    return None, "CIK_PATTERN_NOT_FOUND"


def build_ticker_cik_audit(rows: list[Mapping[str, str]], mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_column = str(mapping["source_column"])
    ticker_column = str(mapping["ticker_column"])
    parsed_rows = []
    ticker_to_ciks: dict[str, set[str]] = defaultdict(set)
    cik_to_tickers: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(rows, start=2):
        ticker = str(row.get(ticker_column) or "").strip().upper()
        source_url = str(row.get(source_column) or "").strip()
        cik, classification = parse_cik_from_source_url(source_url)
        if ticker and cik:
            ticker_to_ciks[ticker].add(cik)
            cik_to_tickers[cik].add(ticker)
        parsed_rows.append(
            {
                "csv_row_number": index,
                "ticker": ticker,
                "source_url": source_url,
                "cik_normalized": cik or "",
                "classification": classification,
                "importable": "",
                "reason": classification.lower(),
            }
        )
    for row in parsed_rows:
        cik = row["cik_normalized"]
        ticker = row["ticker"]
        if not cik:
            row["importable"] = "0"
            continue
        if len(ticker_to_ciks[ticker]) > 1:
            row["classification"] = "TICKER_MULTIPLE_CIK_CONFLICT"
            row["importable"] = "0"
            row["reason"] = "same ticker has multiple CIK values in bootstrap CSV"
        elif len(cik_to_tickers[cik]) > 1:
            row["classification"] = "CIK_MULTIPLE_TICKER_EXPECTED_OR_REVIEW"
            row["importable"] = "1"
            row["reason"] = "same CIK appears for multiple tickers; allowed at company level"
        else:
            row["classification"] = "CIK_VALID_UNIQUE"
            row["importable"] = "1"
            row["reason"] = "strict SEC Companyfacts CIK URL parsed"
    return parsed_rows


def bootstrap_identity_calendar(canonical_db: Path, csv_path: Path, now: str) -> dict[str, Any]:
    rows = read_bootstrap_csv(csv_path)
    mapping = detect_column_mapping(rows[0].keys() if rows else [])
    if not mapping["valid"]:
        raise ValueError(f"Invalid bootstrap CSV columns: {mapping['missing_required_columns']}")
    cik_audit = build_ticker_cik_audit(rows, mapping)
    with connect(canonical_db) as conn:
        row_context = _bootstrap_company_security_and_cik(conn, rows, mapping, cik_audit, now)
        anchor_rows, anchor_conflicts = _normalize_fiscal_anchors(row_context, mapping)
        profile_rows = _bootstrap_fiscal_profiles(conn, row_context, mapping, now)
        imported_anchors = _bootstrap_fiscal_anchors(conn, anchor_rows, now)
    return {
        "rows": rows,
        "mapping": mapping,
        "cik_audit": cik_audit,
        "row_context": row_context,
        "anchor_rows": anchor_rows,
        "anchor_conflicts": anchor_conflicts,
        "profile_rows": profile_rows,
        "imported_anchor_rows": imported_anchors,
        "counts": identity_calendar_counts(canonical_db),
    }


def _bootstrap_company_security_and_cik(
    conn: sqlite3.Connection,
    rows: list[Mapping[str, str]],
    mapping: Mapping[str, Any],
    cik_audit: list[Mapping[str, Any]],
    now: str,
) -> list[dict[str, Any]]:
    ticker_column = str(mapping["ticker_column"])
    source_column = str(mapping["source_column"])
    context = []
    for row, audit in zip(rows, cik_audit):
        ticker = str(row.get(ticker_column) or "").strip().upper()
        cik = str(audit["cik_normalized"] or "")
        importable_cik = audit["classification"] in IMPORTABLE_CIK_CLASSES
        company_key = f"SEC_CIK:{cik}" if importable_cik else f"LOCAL_BOOTSTRAP_TICKER:{ticker}"
        conn.execute(
            """
            INSERT OR IGNORE INTO company(company_key, company_name, status, created_at_utc, updated_at_utc)
            VALUES (?, ?, 'ACTIVE', ?, ?)
            """,
            (company_key, ticker, now, now),
        )
        company_id = conn.execute("SELECT company_id FROM company WHERE company_key=?", (company_key,)).fetchone()[0]
        conn.execute(
            """
            INSERT OR IGNORE INTO security(company_id, current_ticker, active, created_at_utc, updated_at_utc)
            VALUES (?, ?, 1, ?, ?)
            """,
            (company_id, ticker, now, now),
        )
        security = conn.execute("SELECT security_id, company_id FROM security WHERE current_ticker=?", (ticker,)).fetchone()
        security_id = security["security_id"]
        company_id = security["company_id"]
        conn.execute(
            """
            INSERT OR IGNORE INTO ticker_alias(security_id, ticker, provider, source, valid_from)
            VALUES (?, ?, 'LOCAL_VERIFIED_BOOTSTRAP', ?, '')
            """,
            (security_id, ticker, BOOTSTRAP_SOURCE_NAME),
        )
        source_url = str(row.get(source_column) or "").strip()
        if importable_cik:
            conn.execute(
                """
                INSERT OR IGNORE INTO company_cik(
                    company_id, cik_normalized, cik_display, source, source_table, source_row_id, status, created_at_utc,
                    source_type, source_name, source_field, source_value, derivation, confidence
                ) VALUES (?, ?, ?, 'LOCAL_VERIFIED_BOOTSTRAP', ?, ?, 'ACTIVE', ?, 'LOCAL_VERIFIED_BOOTSTRAP',
                          ?, ?, ?, 'PARSED_FROM_SEC_COMPANYFACTS_URL', 'HIGH')
                """,
                (company_id, cik, cik, BOOTSTRAP_SOURCE_FILENAME, audit["csv_row_number"], now, BOOTSTRAP_SOURCE_NAME, source_column, source_url),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO provider_company_identity(
                    provider, provider_identifier_type, provider_identifier_value, company_id, provider_ticker,
                    source, source_type, source_value, created_at_utc
                ) VALUES ('SEC', 'CIK', ?, ?, ?, 'LOCAL_VERIFIED_BOOTSTRAP', 'LOCAL_VERIFIED_BOOTSTRAP', ?, ?)
                """,
                (cik, company_id, ticker, source_url, now),
            )
        context.append(
            {
                "csv_row_number": audit["csv_row_number"],
                "ticker": ticker,
                "company_id": company_id,
                "security_id": security_id,
                "cik_normalized": cik,
                "cik_classification": audit["classification"],
                "source_url": source_url,
                "row": row,
            }
        )
    return context


def _bootstrap_fiscal_profiles(
    conn: sqlite3.Connection,
    row_context: list[Mapping[str, Any]],
    mapping: Mapping[str, Any],
    now: str,
) -> list[dict[str, Any]]:
    profile_rows = []
    typical_column = str(mapping["typical_fiscal_year_start_column"])
    source_column = str(mapping["source_column"])
    chain_column = str(mapping["chain_status_column"])
    break_column = str(mapping["break_reason_column"])
    seen: set[int] = set()
    for context in row_context:
        company_id = int(context["company_id"])
        if company_id in seen:
            continue
        seen.add(company_id)
        row = context["row"]
        payload = {
            "company_id": company_id,
            "ticker": context["ticker"],
            "typical_fiscal_year_start": nullable_text(row.get(typical_column)),
            "chain_status": nullable_text(row.get(chain_column)),
            "break_reason": nullable_text(row.get(break_column)),
            "source_value": nullable_text(row.get(source_column)),
        }
        conn.execute(
            """
            INSERT OR IGNORE INTO company_fiscal_calendar_profile(
                company_id, typical_fiscal_year_start, chain_status, break_reason, source, source_type,
                source_name, source_field, source_value, bootstrap_status, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, 'LOCAL_VERIFIED_BOOTSTRAP', 'LOCAL_VERIFIED_BOOTSTRAP',
                      ?, ?, ?, 'OBSERVED_FROM_CSV', ?, ?)
            """,
            (
                company_id,
                payload["typical_fiscal_year_start"],
                payload["chain_status"],
                payload["break_reason"],
                BOOTSTRAP_SOURCE_NAME,
                typical_column,
                payload["source_value"],
                now,
                now,
            ),
        )
        profile_rows.append(payload)
    return profile_rows


def _normalize_fiscal_anchors(row_context: list[Mapping[str, Any]], mapping: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fy_columns = {int(year): column for year, column in mapping["fy_start_columns"].items()}
    source_column = str(mapping["source_column"])
    candidates: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for context in row_context:
        row = context["row"]
        for fiscal_year, column in sorted(fy_columns.items()):
            fiscal_year_start = nullable_text(row.get(column))
            if fiscal_year_start is None:
                continue
            candidates[(int(context["company_id"]), fiscal_year)].append(
                {
                    "company_id": int(context["company_id"]),
                    "security_id": int(context["security_id"]),
                    "ticker": context["ticker"],
                    "cik_normalized": context["cik_normalized"],
                    "fiscal_year": fiscal_year,
                    "fiscal_year_start": fiscal_year_start,
                    "source": "LOCAL_VERIFIED_BOOTSTRAP",
                    "source_type": "LOCAL_VERIFIED_BOOTSTRAP",
                    "source_name": BOOTSTRAP_SOURCE_NAME,
                    "source_field": column,
                    "source_value": nullable_text(row.get(source_column)),
                    "confidence": "VERIFIED",
                    "observed_verified": 1,
                }
            )
    accepted = []
    conflicts = []
    for (company_id, fiscal_year), rows in sorted(candidates.items()):
        starts = {row["fiscal_year_start"] for row in rows}
        if len(starts) > 1:
            conflicts.extend(dict(row, conflict_reason="multiple starts for company_id + fiscal_year") for row in rows)
        else:
            accepted.append(rows[0])
    return accepted, conflicts


def _bootstrap_fiscal_anchors(conn: sqlite3.Connection, anchor_rows: list[Mapping[str, Any]], now: str) -> int:
    for row in anchor_rows:
        conn.execute(
            """
            INSERT OR IGNORE INTO company_fiscal_year_anchor(
                company_id, fiscal_year, fiscal_year_start, source, source_type, source_name, source_field,
                source_value, confidence, observed_verified, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["company_id"],
                row["fiscal_year"],
                row["fiscal_year_start"],
                row["source"],
                row["source_type"],
                row["source_name"],
                row["source_field"],
                row["source_value"],
                row["confidence"],
                row["observed_verified"],
                now,
            ),
        )
    return len(anchor_rows)


def identity_calendar_counts(canonical_db: Path) -> dict[str, int]:
    with connect(canonical_db) as conn:
        return {
            "companies": conn.execute("SELECT COUNT(*) FROM company").fetchone()[0],
            "securities": conn.execute("SELECT COUNT(*) FROM security").fetchone()[0],
            "company_ciks": conn.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0],
            "provider_company_identities": conn.execute("SELECT COUNT(*) FROM provider_company_identity").fetchone()[0],
            "fiscal_profiles": conn.execute("SELECT COUNT(*) FROM company_fiscal_calendar_profile").fetchone()[0],
            "fiscal_anchors": conn.execute("SELECT COUNT(*) FROM company_fiscal_year_anchor").fetchone()[0],
        }


def summarize_bootstrap(csv_path: Path, bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    rows = bootstrap["rows"]
    cik_audit = bootstrap["cik_audit"]
    counts = Counter(row["classification"] for row in cik_audit)
    parsable = [row for row in cik_audit if row["cik_normalized"]]
    unique_ciks = {row["cik_normalized"] for row in parsable}
    ticker_conflicts = counts.get("TICKER_MULTIPLE_CIK_CONFLICT", 0)
    same_cik_multi = _same_cik_multi_ticker_count(cik_audit)
    source_column = bootstrap["mapping"]["source_column"]
    source_urls = sum(1 for row in rows if nullable_text(row.get(source_column)))
    companyfacts_urls = sum(1 for row in rows if "companyfacts/" in str(row.get(source_column) or ""))
    return {
        "source_path": str(csv_path),
        "csv_tickers": len({str(row.get(bootstrap["mapping"]["ticker_column"]) or "").strip().upper() for row in rows if row.get(bootstrap["mapping"]["ticker_column"])}),
        "rows": len(rows),
        "source_rows_with_url": source_urls,
        "source_rows_with_sec_companyfacts_url": companyfacts_urls,
        "parsable_cik_rows": len(parsable),
        "unique_ciks": len(unique_ciks),
        "invalid_format": counts.get("CIK_FORMAT_INVALID", 0),
        "missing_cik": counts.get("CIK_MISSING_SOURCE", 0) + counts.get("CIK_PATTERN_NOT_FOUND", 0),
        "pattern_not_found": counts.get("CIK_PATTERN_NOT_FOUND", 0),
        "ticker_multiple_cik_conflicts": ticker_conflicts,
        "legitimate_same_cik_multi_ticker_mappings": same_cik_multi,
        "v4_securities_matched": bootstrap["counts"]["securities"],
        "unmatched_tickers": 0,
        "company_ciks_imported": bootstrap["counts"]["company_ciks"],
        "companies_still_cik_null": bootstrap["counts"]["companies"] - bootstrap["counts"]["company_ciks"],
    }


def _same_cik_multi_ticker_count(cik_audit: Iterable[Mapping[str, Any]]) -> int:
    cik_to_tickers: dict[str, set[str]] = defaultdict(set)
    for row in cik_audit:
        cik = str(row["cik_normalized"] or "")
        if cik:
            cik_to_tickers[cik].add(str(row["ticker"]))
    return sum(1 for tickers in cik_to_tickers.values() if len(tickers) > 1)


def fiscal_anchor_coverage(
    source_rows: list[Mapping[str, str]],
    mapping: Mapping[str, Any],
    anchor_rows: list[Mapping[str, Any]],
    profile_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    fy_columns = {int(year): column for year, column in mapping["fy_start_columns"].items()}
    source_anchor_counter = Counter()
    populated_source_cells = 0
    for row in source_rows:
        for fiscal_year, column in fy_columns.items():
            if nullable_text(row.get(column)):
                populated_source_cells += 1
                source_anchor_counter[fiscal_year] += 1
    anchor_counter = Counter(int(row["fiscal_year"]) for row in anchor_rows)
    return {
        "populated_fy_start_cells": populated_source_cells,
        "normalized_anchor_rows": len(anchor_rows),
        "companies_with_anchors": len({row["company_id"] for row in anchor_rows}),
        "fy2023_coverage": source_anchor_counter.get(2023, 0),
        "fy2024_coverage": source_anchor_counter.get(2024, 0),
        "fy2025_coverage": source_anchor_counter.get(2025, 0),
        "fy2026_coverage": source_anchor_counter.get(2026, 0),
        "fy2027_coverage": source_anchor_counter.get(2027, 0),
        "normalized_fy2023_company_coverage": anchor_counter.get(2023, 0),
        "normalized_fy2024_company_coverage": anchor_counter.get(2024, 0),
        "normalized_fy2025_company_coverage": anchor_counter.get(2025, 0),
        "normalized_fy2026_company_coverage": anchor_counter.get(2026, 0),
        "normalized_fy2027_company_coverage": anchor_counter.get(2027, 0),
        "chain_status_distribution": dict(sorted(Counter(row["chain_status"] or "" for row in profile_rows).items())),
        "break_reason_distribution": dict(sorted(Counter(row["break_reason"] or "" for row in profile_rows).items())),
    }


def validate_hard_cases(paths: IdentityCalendarPaths) -> list[dict[str, Any]]:
    output = []
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        for ticker in PROTOTYPE_TICKERS:
            provider_row = provider.execute(
                """
                SELECT *
                FROM sharadar_fundamental_observation
                WHERE ticker=? AND dimension='ARQ'
                ORDER BY reportperiod DESC
                LIMIT 1
                """,
                (ticker,),
            ).fetchone()
            if provider_row is None:
                continue
            identity = canonical.execute(
                """
                SELECT s.current_ticker, s.security_id, s.company_id, psi.provider_security_id AS permaticker, cc.cik_normalized
                FROM security s
                LEFT JOIN provider_security_identity psi
                  ON psi.security_id=s.security_id AND psi.provider='SHARADAR'
                LEFT JOIN company_cik cc ON cc.company_id=s.company_id
                WHERE s.current_ticker=?
                """,
                (ticker,),
            ).fetchone()
            if identity is None:
                continue
            fiscal_year, _ = parse_fiscalperiod(provider_row["fiscalperiod"])
            anchor = canonical.execute(
                "SELECT fiscal_year_start FROM company_fiscal_year_anchor WHERE company_id=? AND fiscal_year=?",
                (identity["company_id"], fiscal_year),
            ).fetchone()
            next_anchor = canonical.execute(
                "SELECT fiscal_year_start FROM company_fiscal_year_anchor WHERE company_id=? AND fiscal_year=?",
                (identity["company_id"], fiscal_year + 1),
            ).fetchone()
            validation = _validate_anchor_window(provider_row["reportperiod"], anchor, next_anchor)
            output.append(
                {
                    "ticker": ticker,
                    "permaticker": identity["permaticker"] or "",
                    "cik": identity["cik_normalized"] or "",
                    "fiscal_year": fiscal_year,
                    "fiscal_year_start": anchor["fiscal_year_start"] if anchor else "",
                    "sharadar_fiscalperiod": provider_row["fiscalperiod"],
                    "reportperiod": provider_row["reportperiod"],
                    "anchor_validation": validation,
                    "result": "PASS" if validation.startswith("VALID") else "REVIEW",
                }
            )
    return output


def _validate_anchor_window(reportperiod: str, anchor: sqlite3.Row | None, next_anchor: sqlite3.Row | None) -> str:
    if anchor is None:
        return "MISSING_ANCHOR"
    period_end = date.fromisoformat(reportperiod)
    start = date.fromisoformat(anchor["fiscal_year_start"])
    if period_end < start:
        return "PERIOD_BEFORE_FISCAL_YEAR_START"
    if next_anchor is None:
        return "VALID_LOWER_BOUND_ONLY"
    next_start = date.fromisoformat(next_anchor["fiscal_year_start"])
    if period_end < next_start:
        return "VALID_ADJACENT_ANCHORS"
    return "PERIOD_ON_OR_AFTER_NEXT_FISCAL_YEAR_START"


def run_identity_calendar_prototype(paths: IdentityCalendarPaths) -> dict[str, Any]:
    now = utc_now()
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, now)
    first_bootstrap = bootstrap_identity_calendar(paths.canonical_db, paths.bootstrap_csv, now)
    first_counts = identity_calendar_counts(paths.canonical_db)
    load_provider_subset(paths.provider_db, paths.acceptance_root, PROTOTYPE_TICKERS, "v4_1a1_sharadar_subset", now)
    canonicalize_arq(paths.provider_db, paths.canonical_db, now)
    second_bootstrap = bootstrap_identity_calendar(paths.canonical_db, paths.bootstrap_csv, now)
    second_counts = identity_calendar_counts(paths.canonical_db)
    hard_cases = validate_hard_cases(paths)
    bootstrap_summary = summarize_bootstrap(paths.bootstrap_csv, second_bootstrap)
    fiscal_summary = fiscal_anchor_coverage(
        second_bootstrap["rows"],
        second_bootstrap["mapping"],
        second_bootstrap["anchor_rows"],
        second_bootstrap["profile_rows"],
    )
    integrity = validate_identity_calendar_integrity(paths, second_bootstrap["anchor_conflicts"])
    replay = {
        "first_bootstrap_counts": first_counts,
        "second_bootstrap_counts": second_counts,
        "duplicate_cik_mappings": second_counts["company_ciks"] - first_counts["company_ciks"],
        "duplicate_fiscal_anchors": second_counts["fiscal_anchors"] - first_counts["fiscal_anchors"],
        "duplicate_provider_company_identities": second_counts["provider_company_identities"] - first_counts["provider_company_identities"],
    }
    provider = provider_counts(paths.provider_db)
    canonical = canonical_counts(paths.canonical_db)
    safety = {
        "production_v4_dbs_created": 0,
        "v3_writes": 0,
        "sec_network_calls": 0,
        "bulk_sharadar_download": 0,
        "score_migration": 0,
        "lifecycle_migration": 0,
        "valuation_migration": 0,
        "swingmaster_runtime_dependency": 0,
    }
    review_items = bootstrap_summary["pattern_not_found"] + integrity["anchor_conflicts"] + integrity["identity_conflicts"]
    if integrity["anchor_conflicts"] or integrity["identity_conflicts"]:
        classification = "V4_IDENTITY_CALENDAR_BOOTSTRAP_BLOCKED"
        next_action = "RESOLVE IDENTITY OR FISCAL ANCHOR CONFLICTS BEFORE V4-1B"
    elif review_items:
        classification = "V4_IDENTITY_CALENDAR_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS"
        review_count = bootstrap_summary["pattern_not_found"]
        next_action = (
            f"REVIEW {review_count} BOOTSTRAP CSV ROWS WITHOUT PARSABLE SEC COMPANYFACTS CIK; OTHERWISE PROCEED TO V4-1B WITH IMPORTED CIKS, "
            "VERIFIED FISCAL-CALENDAR METADATA, AND NULL CIKS ONLY WHERE THE LOCAL SOURCE LACKS A STRICT COMPANYFACTS CIK"
        )
    else:
        classification = "V4_IDENTITY_CALENDAR_BOOTSTRAP_COMPLETE_1B_READY"
        next_action = (
            "PROCEED TO V4-1B: CREATE THE THREE PRODUCTION V4 DATABASES AND BOOTSTRAP THE PAID SHARADAR 5-YEAR DATA USING THE "
            "APPROVED SCHEMA, CIK MAPPING, AND VERIFIED FISCAL-CALENDAR METADATA"
        )
    summary = {
        "artifact_root": str(paths.artifact_root),
        "acceptance_root": str(paths.acceptance_root),
        "bootstrap_csv": str(paths.bootstrap_csv),
        "bootstrap_source": bootstrap_summary,
        "fiscal_calendar": fiscal_summary,
        "provider_counts": provider,
        "canonical_counts": canonical,
        "identity_calendar_counts": second_counts,
        "schema_validation": schema_validation(paths),
        "integrity": integrity,
        "replay": replay,
        "hard_cases": hard_cases,
        "safety": safety,
        "classification": classification,
        "next_action": next_action,
    }
    write_identity_calendar_artifacts(paths, first_bootstrap, second_bootstrap, summary)
    return summary


def validate_identity_calendar_integrity(paths: IdentityCalendarPaths, anchor_conflicts: list[Mapping[str, Any]]) -> dict[str, Any]:
    output = validate_integrity(paths)
    with connect(paths.canonical_db) as conn:
        output["identity_conflicts"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT company_id, COUNT(DISTINCT cik_normalized) c
                FROM company_cik
                GROUP BY company_id
                HAVING c > 1
            )
            """
        ).fetchone()[0]
        output["anchor_conflicts"] = len(anchor_conflicts)
        output["duplicate_cik_mappings"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT company_id, cik_normalized, COUNT(*) c
                FROM company_cik
                GROUP BY company_id, cik_normalized
                HAVING c > 1
            )
            """
        ).fetchone()[0]
        output["duplicate_fiscal_anchors"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT company_id, fiscal_year, COUNT(*) c
                FROM company_fiscal_year_anchor
                GROUP BY company_id, fiscal_year
                HAVING c > 1
            )
            """
        ).fetchone()[0]
        output["orphan_fiscal_profiles"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM company_fiscal_calendar_profile p
            LEFT JOIN company c ON c.company_id=p.company_id
            WHERE c.company_id IS NULL
            """
        ).fetchone()[0]
        output["orphan_fiscal_anchors"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM company_fiscal_year_anchor a
            LEFT JOIN company c ON c.company_id=a.company_id
            WHERE c.company_id IS NULL
            """
        ).fetchone()[0]
    return output


def write_identity_calendar_artifacts(
    paths: IdentityCalendarPaths,
    first_bootstrap: Mapping[str, Any],
    second_bootstrap: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    mapping = second_bootstrap["mapping"]
    write_json(paths.artifact_root / "bootstrap_csv_validation.json", {
        "source_path": str(paths.bootstrap_csv),
        "valid": mapping["valid"],
        "rows": len(second_bootstrap["rows"]),
        "columns": len(next(iter(second_bootstrap["rows"])).keys()) if second_bootstrap["rows"] else 0,
    })
    write_json(paths.artifact_root / "bootstrap_column_mapping.json", mapping)
    write_csv(paths.artifact_root / "ticker_cik_parse_audit.csv", second_bootstrap["cik_audit"])
    write_csv(
        paths.artifact_root / "cik_conflict_audit.csv",
        [
            row
            for row in second_bootstrap["cik_audit"]
            if row["classification"] in {"TICKER_MULTIPLE_CIK_CONFLICT", "CIK_FORMAT_INVALID", "CIK_PATTERN_NOT_FOUND", "CIK_MISSING_SOURCE"}
        ],
    )
    write_csv(paths.artifact_root / "cik_company_security_mapping.csv", _company_security_mapping_rows(paths.canonical_db))
    write_csv(paths.artifact_root / "fiscal_anchor_normalized.csv", second_bootstrap["anchor_rows"])
    write_csv(paths.artifact_root / "fiscal_anchor_conflict_audit.csv", second_bootstrap["anchor_conflicts"])
    write_csv(paths.artifact_root / "fiscal_calendar_profile_bootstrap.csv", second_bootstrap["profile_rows"])
    write_json(paths.artifact_root / "fiscal_anchor_coverage_summary.json", summary["fiscal_calendar"])
    write_json(paths.artifact_root / "identity_calendar_bootstrap_validation.json", summary["integrity"])
    write_json(paths.artifact_root / "identity_calendar_replay_test.json", summary["replay"])
    write_csv(paths.artifact_root / "hard_case_identity_calendar_validation.csv", summary["hard_cases"])
    (paths.artifact_root / "v4_1b_bootstrap_plan_updated.md").write_text(_v4_1b_plan(summary), encoding="utf-8")
    write_json(paths.artifact_root / "phase_v4_1a1_summary.json", summary)
    (paths.artifact_root / "next_action.md").write_text(str(summary["next_action"]) + "\n", encoding="utf-8")


def _company_security_mapping_rows(canonical_db: Path) -> list[dict[str, Any]]:
    with connect(canonical_db) as conn:
        return [dict(row) for row in conn.execute(
            """
            SELECT s.current_ticker AS ticker, s.security_id, s.company_id, cc.cik_normalized, cc.source,
                   cc.source_name, cc.source_field, cc.derivation
            FROM security s
            LEFT JOIN company_cik cc ON cc.company_id=s.company_id
            ORDER BY s.current_ticker
            """
        )]


def _v4_1b_plan(summary: Mapping[str, Any]) -> str:
    return (
        "# V4-1B Bootstrap Plan Update\n\n"
        f"Use `{summary['bootstrap_csv']}` as the initial local identity/calendar bootstrap source for CIK, "
        "verified fiscal-year starts, chain status, and break reason metadata.\n\n"
        "Keep Sharadar ARQ as the primary source for quarterly fiscalperiod/reportperiod and financial fields. "
        "Use fiscal-year-start anchors as validation/reference metadata only.\n\n"
        "Create production V4 databases in V4-1B only after accepting any remaining local-source CIK review rows. "
        "Do not call SEC during bootstrap and do not invent missing CIKs.\n"
    )
