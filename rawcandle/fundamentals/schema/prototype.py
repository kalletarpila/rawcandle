from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.schema.contract import SHARADAR_ARQ_FIELD_MAPPING, SHARADAR_SUPPORT_FIELDS, V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.migrations import bootstrap_all, canonical_field_contract_present, connect


PROTOTYPE_TICKERS = ("AAPL", "WDAY", "ASTH", "CECO")
V3_CIK_SOURCE = Path("/home/kalle/projects/swingmaster/rc_fundamentals_v3.db")
ZERO_OR_NULL = {"", "None", "NULL", "null"}


@dataclass(frozen=True)
class PrototypePaths:
    artifact_root: Path
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    acceptance_root: Path
    v3_db: Path = V3_CIK_SOURCE


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


def prototype_paths(repo_root: Path, timestamp: str | None = None, acceptance_root: Path | None = None) -> PrototypePaths:
    stamp = timestamp or utc_stamp()
    artifact_root = repo_root / "temp" / "fundamentals_v4_1a_schema_design" / stamp
    return PrototypePaths(
        artifact_root=artifact_root,
        provider_db=artifact_root / "prototype_provider.db",
        canonical_db=artifact_root / "prototype_v4.db",
        analysis_db=artifact_root / "prototype_analysis.db",
        acceptance_root=acceptance_root or default_acceptance_root(repo_root),
    )


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
    return int(float(text))


def parse_fiscalperiod(value: Any) -> tuple[int, str]:
    text = str(value or "").strip().upper()
    if "-Q" not in text:
        raise ValueError(f"Invalid fiscalperiod: {value!r}")
    fy_text, quarter_text = text.split("-Q", 1)
    quarter = f"Q{int(quarter_text)}"
    if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError(f"Invalid fiscal quarter: {value!r}")
    return int(fy_text), quarter


def inspect_v3_cik_source(v3_db: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conn = sqlite3.connect(f"file:{v3_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        inventory = []
        cik_columns: list[tuple[str, str]] = []
        for table_row in table_rows:
            table = table_row["name"]
            columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
            matches = [column for column in columns if "cik" in column.lower()]
            inventory.append({"table": table, "columns": ",".join(columns), "cik_columns": ",".join(matches)})
            cik_columns.extend((table, column) for column in matches)
        if not cik_columns:
            audit_rows = [
                {
                    "source_table": "v3_company",
                    "source_row_id": str(row["company_id"]),
                    "ticker": row["ticker"],
                    "cik_raw": "",
                    "cik_normalized": "",
                    "classification": "CIK_MISSING",
                    "reason": "no CIK column found in rc_fundamentals_v3.db schema",
                }
                for row in conn.execute("SELECT company_id, ticker FROM v3_company ORDER BY company_id")
            ]
            return inventory, audit_rows
        return inventory, _audit_cik_columns(conn, cik_columns)
    finally:
        conn.close()


def _audit_cik_columns(conn: sqlite3.Connection, cik_columns: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    candidates: dict[str, list[tuple[str, str, str]]] = {}
    for table, column in cik_columns:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        ticker_column = "ticker" if "ticker" in columns else "provider_symbol" if "provider_symbol" in columns else None
        if not ticker_column:
            continue
        rowid_column = "company_id" if "company_id" in columns else "rowid"
        for row in conn.execute(f"SELECT {rowid_column} AS source_row_id, {ticker_column} AS ticker, {column} AS cik FROM {table}"):
            ticker = str(row["ticker"] or "").upper()
            cik = normalize_cik(row["cik"])
            if ticker:
                candidates.setdefault(ticker, []).append((table, str(row["source_row_id"]), cik or ""))
    audit_rows = []
    for ticker, rows in sorted(candidates.items()):
        normalized = {cik for _, _, cik in rows if cik}
        if not normalized:
            classification = "CIK_MISSING"
        elif any(not cik for _, _, cik in rows):
            classification = "TICKER_MAPPING_AMBIGUOUS"
        elif any(len(cik) > 10 or not cik.isdigit() for cik in normalized):
            classification = "CIK_FORMAT_INVALID"
        elif len(normalized) == 1:
            classification = "CIK_VALID_UNIQUE"
        else:
            classification = "CIK_CONFLICT"
        first = rows[0]
        audit_rows.append(
            {
                "source_table": first[0],
                "source_row_id": first[1],
                "ticker": ticker,
                "cik_raw": next((cik for _, _, cik in rows if cik), ""),
                "cik_normalized": next(iter(normalized), ""),
                "classification": classification,
                "reason": classification.lower(),
            }
        )
    return audit_rows


def normalize_cik(value: Any) -> str | None:
    text = nullable_text(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return digits.lstrip("0") or "0"


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
            revenue, gp, opinc, ebit, ebitda, netinc, ncfo, capex, fcf, cashneq, debt, debtc, debtnc,
            sharesbas, shareswa, shareswadil
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def bootstrap_cik_into_canonical(canonical_db: Path, audit_rows: Iterable[Mapping[str, Any]], now: str) -> dict[str, int]:
    counts = Counter()
    with connect(canonical_db) as conn:
        ticker_to_company = {row["current_ticker"]: row["company_id"] for row in conn.execute("SELECT current_ticker, company_id FROM security")}
        for row in audit_rows:
            counts[str(row["classification"])] += 1
            if row["classification"] != "CIK_VALID_UNIQUE":
                continue
            company_id = ticker_to_company.get(str(row["ticker"]).upper())
            if company_id is None:
                counts["REJECTED_NO_V4_SECURITY"] += 1
                continue
            cik_normalized = str(row["cik_normalized"])
            conn.execute(
                """
                INSERT OR IGNORE INTO company_cik(company_id, cik_normalized, cik_display, source, source_table, source_row_id, status, created_at_utc)
                VALUES (?, ?, ?, 'MIGRATED_FROM_V3', ?, ?, 'ACTIVE', ?)
                """,
                (company_id, cik_normalized, cik_normalized.zfill(10), row["source_table"], row["source_row_id"], now),
            )
            counts["IMPORTED"] += 1
    counts["REJECTED"] = sum(counts[key] for key in ("CIK_MISSING", "CIK_CONFLICT", "CIK_FORMAT_INVALID", "TICKER_MAPPING_AMBIGUOUS", "REJECTED_NO_V4_SECURITY"))
    return dict(counts)


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
                canonical_conn.execute(
                    """
                    INSERT OR IGNORE INTO v4_field_provenance(
                        quarter_id, canonical_field, provider, provider_observation_id, source_native_field,
                        transformation, accepted_at_utc, rule_version, confidence
                    ) VALUES (?, ?, 'SHARADAR', ?, ?, 'DIRECT', ?, 'SHARADAR_ARQ_PRIMARY_V1', 'HIGH')
                    """,
                    (quarter_id, canonical_field, row["observation_id"], native_field, now),
                )
    return canonical_counts(canonical_db)


def canonical_counts(canonical_db: Path) -> dict[str, int]:
    with connect(canonical_db) as conn:
        return {
            "companies": conn.execute("SELECT COUNT(*) FROM company").fetchone()[0],
            "securities": conn.execute("SELECT COUNT(*) FROM security").fetchone()[0],
            "canonical_quarters": conn.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0],
            "canonical_financial_rows": conn.execute("SELECT COUNT(*) FROM v4_quarter_financials").fetchone()[0],
            "provenance_rows": conn.execute("SELECT COUNT(*) FROM v4_field_provenance").fetchone()[0],
            "cik_rows": conn.execute("SELECT COUNT(*) FROM company_cik").fetchone()[0],
        }


def validate_integrity(paths: PrototypePaths) -> dict[str, Any]:
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
        output["orphan_provenance_rows"] = conn.execute(
            "SELECT COUNT(*) FROM v4_field_provenance p LEFT JOIN v4_quarter q ON q.quarter_id=p.quarter_id WHERE q.quarter_id IS NULL"
        ).fetchone()[0]
        output["canonical_fields_without_provenance"] = canonical_fields_without_provenance(conn)
        output["canonical_field_contract_present"] = canonical_field_contract_present(conn)
    return output


def canonical_fields_without_provenance(conn: sqlite3.Connection) -> int:
    missing = 0
    rows = conn.execute("SELECT * FROM v4_quarter_financials").fetchall()
    for row in rows:
        quarter_id = row["quarter_id"]
        provenanced = {
            prov["canonical_field"]
            for prov in conn.execute("SELECT canonical_field FROM v4_field_provenance WHERE quarter_id=?", (quarter_id,))
        }
        for field in V4_CANONICAL_FINANCIAL_FIELDS:
            if row[field] is not None and field not in provenanced:
                missing += 1
    return missing


def export_prototype_rows(paths: PrototypePaths) -> None:
    with connect(paths.canonical_db) as conn:
        canonical_rows = [dict(row) for row in conn.execute(
            """
            SELECT s.current_ticker AS ticker, q.fiscal_year, q.fiscal_quarter, q.period_end,
                   f.revenue, f.gross_profit, f.operating_income, f.ebit, f.ebitda, f.net_income,
                   f.operating_cashflow, f.capex, f.free_cashflow, f.cash, f.total_debt, f.shares_outstanding,
                   q.source_availability_date, q.first_public_result_date
            FROM v4_quarter q
            JOIN v4_quarter_financials f ON f.quarter_id=q.quarter_id
            JOIN security s ON s.company_id=q.company_id
            ORDER BY s.current_ticker, q.fiscal_year, q.fiscal_quarter
            """
        )]
        provenance_rows = [dict(row) for row in conn.execute(
            """
            SELECT s.current_ticker AS ticker, q.fiscal_year, q.fiscal_quarter, p.canonical_field, p.provider,
                   p.provider_observation_id, p.source_native_field, p.transformation, p.rule_version
            FROM v4_field_provenance p
            JOIN v4_quarter q ON q.quarter_id=p.quarter_id
            JOIN security s ON s.company_id=q.company_id
            ORDER BY s.current_ticker, q.fiscal_year, q.fiscal_quarter, p.canonical_field
            """
        )]
    with connect(paths.provider_db) as conn:
        arq_mrq_rows = [dict(row) for row in conn.execute(
            """
            SELECT arq.ticker, arq.fiscalperiod, arq.reportperiod,
                   arq.observation_id AS arq_observation_id,
                   mrq.observation_id AS mrq_observation_id
            FROM sharadar_fundamental_observation arq
            JOIN sharadar_fundamental_observation mrq
              ON arq.ticker=mrq.ticker
             AND arq.reportperiod=mrq.reportperiod
             AND arq.fiscalperiod=mrq.fiscalperiod
            WHERE arq.dimension='ARQ' AND mrq.dimension='MRQ'
            ORDER BY arq.ticker, arq.reportperiod
            """
        )]
    write_csv(paths.artifact_root / "prototype_canonical_rows.csv", canonical_rows)
    write_csv(paths.artifact_root / "prototype_field_provenance.csv", provenance_rows)
    write_csv(paths.artifact_root / "prototype_arq_mrq_test.csv", arq_mrq_rows)


def schema_validation(paths: PrototypePaths) -> dict[str, Any]:
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical, connect(paths.analysis_db) as analysis:
        return {
            "provider_schema_version": provider.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_provider'").fetchone()[0],
            "canonical_schema_version": canonical.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_v4'").fetchone()[0],
            "analysis_schema_version": analysis.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_analysis'").fetchone()[0],
            "canonical_financial_fields": sorted(set(V4_CANONICAL_FINANCIAL_FIELDS) & {row["name"] for row in canonical.execute("PRAGMA table_info(v4_quarter_financials)")}),
            "missing_canonical_financial_fields": sorted(set(V4_CANONICAL_FINANCIAL_FIELDS) - {row["name"] for row in canonical.execute("PRAGMA table_info(v4_quarter_financials)")}),
            "sharadar_support_fields": sorted(set(SHARADAR_SUPPORT_FIELDS) & {row["name"] for row in provider.execute("PRAGMA table_info(sharadar_fundamental_observation)")}),
            "score_contract_exists": _table_exists(analysis, "score_result"),
            "lifecycle_contract_exists": _table_exists(analysis, "lifecycle_result"),
            "valuation_contract_exists": _table_exists(analysis, "valuation_result"),
            "ttm_contract_exists": _table_exists(canonical, "v4_ttm_contract"),
        }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def run_schema_prototype(paths: PrototypePaths) -> dict[str, Any]:
    now = utc_now()
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, now)
    inventory_rows, cik_audit_rows = inspect_v3_cik_source(paths.v3_db)
    write_csv(paths.artifact_root / "v3_cik_source_inventory.csv", inventory_rows)
    write_csv(paths.artifact_root / "v3_cik_bootstrap_audit.csv", cik_audit_rows)

    first_provider_counts = load_provider_subset(paths.provider_db, paths.acceptance_root, PROTOTYPE_TICKERS, "v4_1a_prototype_run", now)
    first_canonical_counts = canonicalize_arq(paths.provider_db, paths.canonical_db, now)
    cik_counts = bootstrap_cik_into_canonical(paths.canonical_db, cik_audit_rows, now)
    first_canonical_counts = canonical_counts(paths.canonical_db)

    second_provider_counts = load_provider_subset(paths.provider_db, paths.acceptance_root, PROTOTYPE_TICKERS, "v4_1a_prototype_run", now)
    second_canonical_counts = canonicalize_arq(paths.provider_db, paths.canonical_db, now)

    replay = {
        "first_provider_counts": first_provider_counts,
        "second_provider_counts": second_provider_counts,
        "first_canonical_counts": first_canonical_counts,
        "second_canonical_counts": second_canonical_counts,
        "duplicate_provider_observations": second_provider_counts["provider_observations"] - first_provider_counts["provider_observations"],
        "duplicate_canonical_quarters": second_canonical_counts["canonical_quarters"] - first_canonical_counts["canonical_quarters"],
        "duplicate_provenance": second_canonical_counts["provenance_rows"] - first_canonical_counts["provenance_rows"],
    }
    integrity = validate_integrity(paths)
    validation = schema_validation(paths)
    export_prototype_rows(paths)
    if cik_counts.get("IMPORTED", 0) == 0 and sum(1 for row in cik_audit_rows if row["cik_normalized"]) == 0:
        classification = "V4_SCHEMA_DESIGN_COMPLETE_WITH_OPEN_ARCHITECTURE_ITEMS"
        next_action = (
            "DECIDE V4-1B CIK SOURCE: ACCEPT NULL CIK BOOTSTRAP UNTIL SEC PROVIDER INGEST OR SUPPLY A DETERMINISTIC LOCAL CIK SOURCE; "
            "DO NOT INVENT CIKS"
        )
    else:
        classification = "V4_SCHEMA_DESIGN_COMPLETE_BOOTSTRAP_READY"
        next_action = (
            "PROCEED TO V4-1B: CREATE THE THREE PRODUCTION V4 DATABASES IN RAWCANDLE AND BOOTSTRAP THE PAID 5-YEAR SHARADAR FUNDAMENTALS DATA "
            "USING THE APPROVED SCHEMA; KEEP YAHOO/SEC AS COMPLEMENTARY PROVIDERS AND DO NOT MIGRATE SCORE/LIFECYCLE/VALUATION YET"
        )
    summary = {
        "artifact_root": str(paths.artifact_root),
        "acceptance_root": str(paths.acceptance_root),
        "prototype_tickers": list(PROTOTYPE_TICKERS),
        "provider_counts": second_provider_counts,
        "canonical_counts": second_canonical_counts,
        "cik_bootstrap": {
            "v3_companies_inspected": sum(1 for row in cik_audit_rows if row["source_table"] == "v3_company"),
            "cik_candidates": sum(1 for row in cik_audit_rows if row["cik_normalized"]),
            "valid_unique": cik_counts.get("CIK_VALID_UNIQUE", 0),
            "missing": cik_counts.get("CIK_MISSING", 0),
            "conflicting": cik_counts.get("CIK_CONFLICT", 0),
            "imported": cik_counts.get("IMPORTED", 0),
            "rejected": cik_counts.get("REJECTED", 0),
        },
        "schema_validation": validation,
        "integrity": integrity,
        "replay": replay,
        "safety": {
            "production_v4_dbs_created": 0,
            "v3_writes": 0,
            "bulk_sharadar_download": 0,
            "score_migration": 0,
            "lifecycle_migration": 0,
            "valuation_migration": 0,
            "swingmaster_runtime_dependency": 0,
        },
        "classification": classification,
        "next_action": next_action,
    }
    write_json(paths.artifact_root / "prototype_schema_validation.json", validation)
    write_json(paths.artifact_root / "prototype_integrity.json", integrity)
    write_json(paths.artifact_root / "prototype_replay_test.json", replay)
    write_json(paths.artifact_root / "phase_v4_1a_summary.json", summary)
    (paths.artifact_root / "next_action.md").write_text(summary["next_action"] + "\n", encoding="utf-8")
    write_design_artifacts(paths)
    return summary


def write_design_artifacts(paths: PrototypePaths) -> None:
    design_docs = {
        "provider_db_schema_design.md": "# Provider DB Schema Design\n\nStores provider runs, provider observations, and normalized Sharadar quarterly observation columns while retaining raw JSON and content hashes. ARQ and MRQ coexist because dimension is part of provider record identity.\n",
        "canonical_v4_db_schema_design.md": "# Canonical V4 DB Schema Design\n\nStores company/security identity, fiscal-quarter identity, wide 12-field canonical financial rows, field-level provenance, and a TTM contract placeholder. Fiscal FY/Q is the canonical identity; period_end is critical metadata.\n",
        "analysis_db_schema_design.md": "# Analysis DB Schema Design\n\nDefines rebuildable contracts for Score, Score components, Lifecycle, and Valuation outputs. Engines are not migrated in V4-1A.\n",
        "company_security_identity_design.md": "# Company / Security Identity Design\n\nCompany and security are separate. Ticker is not the stable key. Sharadar permaticker is provider identity metadata. SEC CIK is stored separately when deterministic migration or SEC provider evidence exists.\n",
        "provenance_design.md": "# Provenance Design\n\nEvery non-null canonical financial field has one field-level provenance row pointing to provider, provider observation id, source-native field, transformation, rule version, and confidence.\n",
        "ttm_contract_design.md": "# TTM Contract Design\n\nTTM belongs in fundamentals_v4.db as deterministic financial data derived from canonical quarters. V4-1A creates only the contract placeholder; the EBIT-first engine is not migrated.\n",
        "v4_1b_bootstrap_plan.md": "# V4-1B Bootstrap Plan\n\nCreate production fundamentals_provider.db, fundamentals_v4.db, and fundamentals_analysis.db using the V4-1A schema. Bootstrap targeted 5-year Sharadar ARQ/MRQ data through provider ingestion, canonicalize ARQ only, preserve field-level provenance, and keep Yahoo/SEC complementary. Do not migrate Score/Lifecycle/Valuation yet.\n",
    }
    for name, content in design_docs.items():
        (paths.artifact_root / name).write_text(content, encoding="utf-8")
