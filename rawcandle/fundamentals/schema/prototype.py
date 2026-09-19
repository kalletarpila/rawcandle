from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.schema.contract import SHARADAR_ARQ_FIELD_MAPPING, SHARADAR_SUPPORT_FIELDS, V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.migrations import canonical_field_contract_present, connect
from rawcandle.fundamentals.schema.provenance import count_provenance, read_provenance, write_provenance


PROTOTYPE_TICKERS = ("AAPL", "WDAY", "ASTH", "CECO")
ZERO_OR_NULL = {"", "None", "NULL", "null"}

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_acceptance_root(repo_root: Path) -> Path:
    base = repo_root / "temp" / "fundamentals_v4_0d_sharadar_paid_acceptance"
    summaries = sorted(base.glob("*/sharadar_acceptance_summary.json"))
    if not summaries:
        raise FileNotFoundError(f"No V4-0D acceptance summary found under {base}")
    accepted = []
    for summary_path in summaries:
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("classification") in {
            "SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER",
            "SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER_WITH_GUARDS",
        }:
            accepted.append(summary_path.parent)
    return sorted(accepted or [path.parent for path in summaries])[-1]



def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def stable_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()


def nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if text in ZERO_OR_NULL else text


def int_or_none(value: Any) -> int | None:
    text = nullable_text(value)
    if text is None:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed)


def parse_fiscalperiod(value: Any) -> tuple[int, str]:
    text = str(value or "").strip().upper()
    if "-Q" not in text:
        raise ValueError(f"Invalid fiscalperiod: {value!r}")
    fy_text, quarter_text = text.split("-Q", 1)
    quarter = f"Q{int(quarter_text)}"
    if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError(f"Invalid fiscal quarter: {value!r}")
    return int(fy_text), quarter



def load_provider_subset(provider_db: Path, acceptance_root: Path, tickers: Iterable[str], run_id: str, now: str) -> dict[str, int]:
    permatickers = read_permaticker_map(acceptance_root)
    arq_rows = [enrich_permaticker(row, permatickers) for row in read_csv_rows(acceptance_root / "acceptance_arq_rows.csv") if row.get("ticker") in tickers]
    mrq_rows = [enrich_permaticker(row, permatickers) for row in read_csv_rows(acceptance_root / "acceptance_mrq_rows.csv") if row.get("ticker") in tickers]
    with connect(provider_db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO provider_run(
                run_id, provider, started_at_utc, completed_at_utc, status, request_scope, entitlement_scope, source_version, metadata_json
            ) VALUES (?, 'SHARADAR', ?, ?, 'SUCCESS', ?, '5Y_TARGETED_ACCEPTANCE_CACHE', 'V4-0D', '{}')
            """,
            (run_id, now, now, ",".join(tickers)),
        )
        for row in arq_rows + mrq_rows:
            insert_sharadar_observation(conn, row, run_id, now)
    return provider_counts(provider_db)


def read_permaticker_map(acceptance_root: Path) -> dict[str, str]:
    path = acceptance_root / "permaticker_identity_validation.csv"
    if not path.exists():
        return {}
    output = {}
    for row in read_csv_rows(path):
        ticker = str(row.get("ticker") or "").upper()
        value = nullable_text(row.get("row_permatickers")) or nullable_text(row.get("metadata_permatickers"))
        if ticker and value:
            output[ticker] = value.split(",")[0].strip()
    return output


def enrich_permaticker(row: Mapping[str, Any], permatickers: Mapping[str, str]) -> dict[str, Any]:
    enriched = dict(row)
    if not nullable_text(enriched.get("permaticker")):
        ticker = str(enriched.get("ticker") or "").upper()
        if ticker in permatickers:
            enriched["permaticker"] = permatickers[ticker]
    return enriched


def insert_sharadar_observation(conn: sqlite3.Connection, row: Mapping[str, Any], run_id: str, now: str) -> str:
    ticker = str(row.get("ticker") or "").upper()
    dimension = str(row.get("dimension") or "").upper()
    provider_record_key = "|".join([ticker, dimension, str(row.get("reportperiod") or ""), str(row.get("fiscalperiod") or "")])
    content_hash = stable_hash(dict(row))
    observation_id = stable_id("SHARADAR", "fundamentals", provider_record_key, content_hash)
    payload_json = json.dumps(dict(row), sort_keys=True, default=str)
    conn.execute(
        """
        INSERT OR IGNORE INTO provider_observation(
            observation_id, run_id, provider, provider_record_key, provider_ticker, provider_security_id, native_table,
            dimension, calendardate, reportperiod, fiscalperiod, source_availability_date, fetched_at_utc,
            content_hash, provider_status, payload_json, provenance_json
        ) VALUES (?, ?, 'SHARADAR', ?, ?, ?, 'fundamentals', ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', ?, '{}')
        """,
        (
            observation_id,
            run_id,
            provider_record_key,
            ticker,
            nullable_text(row.get("permaticker")),
            dimension,
            nullable_text(row.get("calendardate")),
            nullable_text(row.get("reportperiod")),
            nullable_text(row.get("fiscalperiod")),
            nullable_text(row.get("date")),
            now,
            content_hash,
            payload_json,
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO sharadar_fundamental_observation(
            observation_id, ticker, permaticker, dimension, calendardate, reportperiod, fiscalperiod, date, lastupdated,
            revenue, gp, opinc, ebit, ebitda, netinc, netinccmn, ncfo, capex, fcf, cashneq, debt, debtc, debtnc,
            sharesbas, shareswa, shareswadil, receivables, inventory, payables, deferredrev, assets
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            ticker,
            nullable_text(row.get("permaticker")),
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
            int_or_none(row.get("netinccmn")),
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
            int_or_none(row.get("receivables")),
            int_or_none(row.get("inventory")),
            int_or_none(row.get("payables")),
            int_or_none(row.get("deferredrev")),
            int_or_none(row.get("assets")),
        ),
    )
    return observation_id


def provider_counts(provider_db: Path) -> dict[str, int]:
    with connect(provider_db) as conn:
        return {
            "provider_observations": conn.execute("SELECT COUNT(*) FROM provider_observation").fetchone()[0],
            "arq_observations": conn.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE dimension='ARQ'").fetchone()[0],
            "mrq_observations": conn.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE dimension='MRQ'").fetchone()[0],
        }


def ensure_identity(conn: sqlite3.Connection, ticker: str, permaticker: str | None, now: str) -> tuple[int, int]:
    existing_security = conn.execute(
        "SELECT security_id, company_id FROM security WHERE current_ticker=?",
        (ticker,),
    ).fetchone()
    if existing_security is not None:
        security_id = existing_security["security_id"]
        company_id = existing_security["company_id"]
        if permaticker:
            conn.execute(
                """
                INSERT OR IGNORE INTO provider_security_identity(provider, provider_security_id, security_id, provider_ticker, source, created_at_utc)
                VALUES ('SHARADAR', ?, ?, ?, 'PROTOTYPE_ACCEPTANCE_CACHE', ?)
                """,
                (permaticker, security_id, ticker, now),
            )
        return company_id, security_id

    company_key = f"SHARADAR:{permaticker}" if permaticker else f"TICKER:{ticker}"
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
    security_id = conn.execute("SELECT security_id FROM security WHERE current_ticker=?", (ticker,)).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO ticker_alias(security_id, ticker, provider, source, valid_from) VALUES (?, ?, 'SHARADAR', 'PROTOTYPE_ACCEPTANCE_CACHE', '')",
        (security_id, ticker),
    )
    if permaticker:
        conn.execute(
            """
            INSERT OR IGNORE INTO provider_security_identity(provider, provider_security_id, security_id, provider_ticker, source, created_at_utc)
            VALUES ('SHARADAR', ?, ?, ?, 'PROTOTYPE_ACCEPTANCE_CACHE', ?)
            """,
            (permaticker, security_id, ticker, now),
        )
    return company_id, security_id



def canonicalize_arq(provider_db: Path, canonical_db: Path, now: str) -> dict[str, int]:
    with connect(provider_db) as provider_conn, connect(canonical_db) as canonical_conn:
        rows = provider_conn.execute(
            """
            SELECT po.observation_id, sfo.*
            FROM sharadar_fundamental_observation sfo
            JOIN provider_observation po ON po.observation_id = sfo.observation_id
            WHERE sfo.dimension='ARQ'
            ORDER BY sfo.ticker, sfo.reportperiod
            """
        ).fetchall()
        for row in rows:
            ticker = row["ticker"]
            company_id, _ = ensure_identity(canonical_conn, ticker, row["permaticker"], now)
            fiscal_year, fiscal_quarter = parse_fiscalperiod(row["fiscalperiod"])
            canonical_conn.execute(
                """
                INSERT OR IGNORE INTO v4_quarter(
                    company_id, fiscal_year, fiscal_quarter, period_end, source_fiscalperiod, source_reportperiod,
                    identity_provider, identity_status, source_availability_date, first_public_result_date,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, 'SHARADAR_ARQ', 'ACCEPTED', ?, NULL, ?, ?)
                """,
                (company_id, fiscal_year, fiscal_quarter, row["reportperiod"], row["fiscalperiod"], row["reportperiod"], row["date"], now, now),
            )
            quarter_id = canonical_conn.execute(
                "SELECT quarter_id FROM v4_quarter WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?",
                (company_id, fiscal_year, fiscal_quarter),
            ).fetchone()[0]
            financial_values = {canonical: row[native] for canonical, native in SHARADAR_ARQ_FIELD_MAPPING.items()}
            columns = ", ".join(financial_values)
            placeholders = ", ".join("?" for _ in financial_values)
            canonical_conn.execute(
                f"""
                INSERT OR IGNORE INTO v4_quarter_financials(
                    quarter_id, {columns}, canonical_source_policy, created_at_utc, updated_at_utc
                ) VALUES (?, {placeholders}, 'SHARADAR_ARQ_PRIMARY', ?, ?)
                """,
                (quarter_id, *financial_values.values(), now, now),
            )
            for canonical_field, native_field in SHARADAR_ARQ_FIELD_MAPPING.items():
                if row[native_field] is None:
                    continue
                write_provenance(
                    canonical_conn,
                    {
                        "quarter_id": quarter_id, "canonical_field": canonical_field, "provider": "SHARADAR",
                        "provider_observation_id": row["observation_id"], "source_native_field": native_field,
                        "transformation": "DIRECT", "accepted_at_utc": now,
                        "rule_version": "SHARADAR_ARQ_PRIMARY_V1", "confidence": "HIGH",
                    },
                    ignore_duplicate=True,
                )
    return canonical_counts(canonical_db)


def canonical_counts(canonical_db: Path) -> dict[str, int]:
    with connect(canonical_db) as conn:
        return {
            "companies": conn.execute("SELECT COUNT(*) FROM company").fetchone()[0],
            "securities": conn.execute("SELECT COUNT(*) FROM security").fetchone()[0],
            "canonical_quarters": conn.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0],
            "canonical_financial_rows": conn.execute("SELECT COUNT(*) FROM v4_quarter_financials").fetchone()[0],
            "provenance_rows": count_provenance(conn),
            "cik_rows": conn.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0],
        }


def validate_integrity(paths: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, db_path in (("provider", paths.provider_db), ("canonical", paths.canonical_db), ("analysis", paths.analysis_db)):
        with connect(db_path) as conn:
            output[f"{key}_quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
            output[f"{key}_foreign_key_errors"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    with connect(paths.provider_db) as conn:
        output["duplicate_provider_observation_identity"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT provider, native_table, provider_record_key, content_hash, COUNT(*) c
                FROM provider_observation
                GROUP BY provider, native_table, provider_record_key, content_hash
                HAVING c > 1
            )
            """
        ).fetchone()[0]
        output["arq_mrq_matching_quarters"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM sharadar_fundamental_observation arq
            JOIN sharadar_fundamental_observation mrq
              ON arq.ticker=mrq.ticker
             AND arq.reportperiod=mrq.reportperiod
             AND arq.fiscalperiod=mrq.fiscalperiod
            WHERE arq.dimension='ARQ' AND mrq.dimension='MRQ'
            """
        ).fetchone()[0]
    with connect(paths.canonical_db) as conn:
        output["duplicate_fiscal_fyq"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT company_id, fiscal_year, fiscal_quarter, COUNT(*) c
                FROM v4_quarter
                GROUP BY company_id, fiscal_year, fiscal_quarter
                HAVING c > 1
            )
            """
        ).fetchone()[0]
        output["orphan_financial_rows"] = conn.execute(
            "SELECT COUNT(*) FROM v4_quarter_financials f LEFT JOIN v4_quarter q ON q.quarter_id=f.quarter_id WHERE q.quarter_id IS NULL"
        ).fetchone()[0]
        quarter_ids = {row[0] for row in conn.execute("SELECT quarter_id FROM v4_quarter")}
        output["orphan_provenance_rows"] = sum(row["quarter_id"] not in quarter_ids for row in read_provenance(conn))
        output["canonical_fields_without_provenance"] = canonical_fields_without_provenance(conn)
        output["canonical_field_contract_present"] = canonical_field_contract_present(conn)
    return output


def canonical_fields_without_provenance(conn: sqlite3.Connection) -> int:
    missing = 0
    rows = conn.execute("SELECT * FROM v4_quarter_financials").fetchall()
    for row in rows:
        quarter_id = row["quarter_id"]
        provenanced = {prov["canonical_field"] for prov in read_provenance(conn, quarter_id=quarter_id)}
        for field in V4_CANONICAL_FINANCIAL_FIELDS:
            if row[field] is not None and field not in provenanced:
                missing += 1
    return missing



def schema_validation(paths: Any) -> dict[str, Any]:
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical, connect(paths.analysis_db) as analysis:
        return {
            "provider_schema_version": provider.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_provider'").fetchone()[0],
            "canonical_schema_version": canonical.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_v4'").fetchone()[0],
            "analysis_schema_version": analysis.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_analysis'").fetchone()[0],
            "canonical_financial_fields": sorted(set(V4_CANONICAL_FINANCIAL_FIELDS) & {row["name"] for row in canonical.execute("PRAGMA table_info(v4_quarter_financials)")}),
            "missing_canonical_financial_fields": sorted(set(V4_CANONICAL_FINANCIAL_FIELDS) - {row["name"] for row in canonical.execute("PRAGMA table_info(v4_quarter_financials)")}),
            "sharadar_support_fields": sorted(set(SHARADAR_SUPPORT_FIELDS) & {row["name"] for row in provider.execute("PRAGMA table_info(sharadar_fundamental_observation)")}),
            "score_contract_exists": _table_exists(analysis, "score_result"),
            "lifecycle_contract_exists": _table_exists(analysis, "lifecycle_revised_result"),
            "valuation_contract_exists": _table_exists(analysis, "valuation_revised_result"),
            "ttm_contract_exists": _table_exists(canonical, "v4_ttm_contract"),
        }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
