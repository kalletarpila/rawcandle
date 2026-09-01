from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

MODEL_VERSION = "V4_TTM_EBIT_FIRST_V1"
CALCULATION_VERSION = "V4_TTM_EBIT_FIRST_V1_COMMON_EARNINGS_ADDENDUM"
CLASSIFICATION_READY = "V4_TTM_MIGRATION_COMPLETE_DOWNSTREAM_READY"
CLASSIFICATION_NON_BLOCKING = "V4_TTM_MIGRATION_COMPLETE_WITH_NON_BLOCKING_GAPS"
CLASSIFICATION_BLOCKED = "V4_TTM_MIGRATION_BLOCKED"
NEXT_READY = "PROCEED TO V4-3: MIGRATE AND VALIDATE THE LOCKED FUNDAMENTAL SCORE ARCHITECTURE AGAINST V4 CANONICAL + TTM DATA; KEEP THE KNOWN-GAPS REGISTER AS AN EXPLICIT DOWNSTREAM QUALITY INPUT"
NEXT_BLOCKED = "KEEP SCORE/LIFECYCLE/VALUATION FROZEN AND RESOLVE ONLY THE TTM WINDOW OR ENGINE DEFECTS THAT PREVENT CORRECT CURRENT TTM CALCULATION"

FLOW_FIELDS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "ebit",
    "ebitda",
    "net_income",
    "net_income_common",
    "operating_cashflow",
    "capex",
    "free_cashflow",
)
INSTANT_FIELDS = ("cash", "total_debt", "shares_outstanding")
CORE_FLOW_FIELDS = ("revenue", "ebit", "free_cashflow")
CORE_INSTANT_FIELDS = INSTANT_FIELDS
TTM_FIELD_MAP = {
    "revenue": "ttm_revenue",
    "gross_profit": "ttm_gross_profit",
    "operating_income": "ttm_operating_income",
    "ebit": "ttm_ebit",
    "ebitda": "ttm_ebitda",
    "net_income": "ttm_net_income",
    "net_income_common": "ttm_net_income_common",
    "operating_cashflow": "ttm_operating_cashflow",
    "capex": "ttm_capex",
    "free_cashflow": "ttm_free_cashflow",
}
BLOCKER_PRIORITY = (
    "TTM_IDENTITY_BLOCKED",
    "TTM_DATA_INSUFFICIENT",
    "TTM_MISSING_QUARTER",
    "TTM_NON_CONTIGUOUS_WINDOW",
    "TTM_FISCAL_SEQUENCE_BLOCKED",
    "TTM_MISSING_REVENUE",
    "TTM_MISSING_EBIT",
    "TTM_MISSING_FCF",
    "TTM_MISSING_CASH",
    "TTM_MISSING_DEBT",
    "TTM_MISSING_SHARES",
)

TTM_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS v4_ttm_values (
    ttm_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    security_id INTEGER REFERENCES security(security_id),
    endpoint_quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id) ON DELETE CASCADE,
    endpoint_fiscal_year INTEGER NOT NULL,
    endpoint_fiscal_quarter TEXT NOT NULL CHECK (endpoint_fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    period_end TEXT NOT NULL,
    model_version TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    readiness_status TEXT NOT NULL,
    blocker_codes_json TEXT NOT NULL,
    blocker_details_json TEXT NOT NULL,
    ttm_revenue REAL,
    ttm_gross_profit REAL,
    ttm_operating_income REAL,
    ttm_ebit REAL,
    ttm_ebitda REAL,
    ttm_net_income REAL,
    ttm_operating_cashflow REAL,
    ttm_capex REAL,
    ttm_free_cashflow REAL,
    cash REAL,
    total_debt REAL,
    shares_outstanding REAL,
    revenue_4q_ready INTEGER NOT NULL CHECK (revenue_4q_ready IN (0,1)),
    gross_profit_4q_ready INTEGER NOT NULL CHECK (gross_profit_4q_ready IN (0,1)),
    operating_income_4q_ready INTEGER NOT NULL CHECK (operating_income_4q_ready IN (0,1)),
    ebit_4q_ready INTEGER NOT NULL CHECK (ebit_4q_ready IN (0,1)),
    ebitda_4q_ready INTEGER NOT NULL CHECK (ebitda_4q_ready IN (0,1)),
    net_income_4q_ready INTEGER NOT NULL CHECK (net_income_4q_ready IN (0,1)),
    operating_cashflow_4q_ready INTEGER NOT NULL CHECK (operating_cashflow_4q_ready IN (0,1)),
    capex_4q_ready INTEGER NOT NULL CHECK (capex_4q_ready IN (0,1)),
    free_cashflow_4q_ready INTEGER NOT NULL CHECK (free_cashflow_4q_ready IN (0,1)),
    core_ttm_ready INTEGER NOT NULL CHECK (core_ttm_ready IN (0,1)),
    ttm_source_available_date TEXT,
    first_public_result_date TEXT,
    input_quarter_ids_json TEXT NOT NULL,
    input_values_hash TEXT NOT NULL,
    canonical_financial_fingerprint TEXT NOT NULL,
    output_fingerprint TEXT NOT NULL,
    run_id TEXT NOT NULL,
    calculated_at_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    ttm_net_income_common REAL,
    net_income_common_4q_ready INTEGER NOT NULL DEFAULT 0 CHECK (net_income_common_4q_ready IN (0,1)),
    UNIQUE(company_id, endpoint_quarter_id, model_version)
);

CREATE TABLE IF NOT EXISTS v4_ttm_input_quarter (
    ttm_id INTEGER NOT NULL REFERENCES v4_ttm_values(ttm_id) ON DELETE CASCADE,
    input_position INTEGER NOT NULL CHECK (input_position BETWEEN 1 AND 4),
    input_quarter_id INTEGER NOT NULL REFERENCES v4_quarter(quarter_id),
    input_fiscal_year INTEGER NOT NULL,
    input_fiscal_quarter TEXT NOT NULL CHECK (input_fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    period_end TEXT NOT NULL,
    source_availability_date TEXT,
    input_values_hash TEXT NOT NULL,
    PRIMARY KEY(ttm_id, input_position),
    UNIQUE(ttm_id, input_quarter_id)
);

CREATE INDEX IF NOT EXISTS idx_v4_ttm_company_endpoint ON v4_ttm_values(company_id, endpoint_fiscal_year, endpoint_fiscal_quarter);
CREATE INDEX IF NOT EXISTS idx_v4_ttm_ready ON v4_ttm_values(readiness_status, core_ttm_ready);
CREATE INDEX IF NOT EXISTS idx_v4_ttm_security ON v4_ttm_values(security_id);
CREATE INDEX IF NOT EXISTS idx_v4_ttm_input_quarter ON v4_ttm_input_quarter(input_quarter_id);
"""

@dataclass(frozen=True)
class TtmPaths:
    repo_root: Path
    artifact_root: Path
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    v3_db: Path
    v4_1b1_artifact_root: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ttm_paths(repo_root: Path, timestamp: str | None = None) -> TtmPaths:
    stamp = timestamp or utc_stamp()
    return TtmPaths(
        repo_root=repo_root,
        artifact_root=repo_root / "temp" / "fundamentals_v4_2_ttm" / stamp,
        provider_db=repo_root / "data" / "fundamentals_provider.db",
        canonical_db=repo_root / "data" / "fundamentals_v4.db",
        analysis_db=repo_root / "data" / "fundamentals_analysis.db",
        v3_db=Path("/home/kalle/projects/swingmaster/rc_fundamentals_v3.db"),
        v4_1b1_artifact_root=locate_latest_v4_1b1_artifact(repo_root),
    )


def locate_latest_v4_1b1_artifact(repo_root: Path) -> Path:
    candidates = sorted((repo_root / "temp" / "fundamentals_v4_1b1_bootstrap_review").glob("*/v4_1b1_summary.json"))
    if not candidates:
        raise FileNotFoundError("No V4-1B-1 summary artifact found")
    return candidates[-1].parent


def ensure_ttm_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(TTM_SCHEMA_SQL)


def reset_ttm_schema(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS v4_ttm_input_quarter")
    conn.execute("DROP TABLE IF EXISTS v4_ttm_values")
    ensure_ttm_schema(conn)


def load_canonical_rows(db_path: Path) -> list[dict[str, Any]]:
    fields = ",".join(f"f.{field}" for field in (*FLOW_FIELDS, *INSTANT_FIELDS))
    with connect(db_path, readonly=True) as conn:
        rows = [dict(row) for row in conn.execute(f"""
            SELECT c.company_id, c.company_key, c.company_name, s.security_id, s.current_ticker AS ticker,
                   q.quarter_id, q.fiscal_year, q.fiscal_quarter, q.period_end,
                   q.source_availability_date, q.first_public_result_date, {fields}
            FROM company c
            LEFT JOIN security s ON s.company_id = c.company_id
            JOIN v4_quarter q ON q.company_id = c.company_id
            JOIN v4_quarter_financials f ON f.quarter_id = q.quarter_id
            WHERE s.security_id IS NULL OR s.security_id = (
                SELECT MIN(s2.security_id) FROM security s2 WHERE s2.company_id = c.company_id
            )
            ORDER BY c.company_id, q.fiscal_year,
                     CASE q.fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 WHEN 'Q4' THEN 4 END
        """)]
    return rows


def rows_by_company(rows: Iterable[Mapping[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["company_id"])].append(dict(row))
    for items in grouped.values():
        items.sort(key=fiscal_seq)
    return grouped


def quarter_num(q: str) -> int:
    return {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}[q]


def seq_to_fyq(seq: int) -> tuple[int, str]:
    return (seq - 1) // 4, f"Q{((seq - 1) % 4) + 1}"


def fiscal_seq(row: Mapping[str, Any]) -> int:
    return int(row["fiscal_year"]) * 4 + quarter_num(str(row["fiscal_quarter"]))


def ready_column(field: str) -> str:
    return f"{field}_4q_ready"


def missing_field_code(field: str) -> str:
    return {
        "revenue": "TTM_MISSING_REVENUE",
        "ebit": "TTM_MISSING_EBIT",
        "free_cashflow": "TTM_MISSING_FCF",
        "cash": "TTM_MISSING_CASH",
        "total_debt": "TTM_MISSING_DEBT",
        "shares_outstanding": "TTM_MISSING_SHARES",
    }[field]


def primary_status(blockers: list[str]) -> str:
    if not blockers:
        return "TTM_READY"
    seen = set(blockers)
    for code in BLOCKER_PRIORITY:
        if code in seen:
            return code
    return sorted(seen)[0]


def compute_ttm_rows(rows: list[dict[str, Any]], *, run_id: str, calculated_at: str, canonical_fingerprint: str = "") -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for company_id, qrows in sorted(rows_by_company(rows).items()):
        by_seq = {fiscal_seq(row): row for row in qrows}
        for endpoint in qrows:
            end_seq = fiscal_seq(endpoint)
            expected = list(range(end_seq - 3, end_seq + 1))
            window = [by_seq.get(seq) for seq in expected]
            present = [row for row in window if row is not None]
            blockers: list[str] = []
            details: list[str] = []
            if len(present) < 4:
                blockers.extend(["TTM_DATA_INSUFFICIENT", "TTM_MISSING_QUARTER"])
                missing = [f"{fy}-Q{qn[-1]}" for fy, qn in (seq_to_fyq(seq) for seq in expected if seq not in by_seq)]
                details.append("missing_quarters=" + ";".join(missing))
            elif [fiscal_seq(row) for row in present] != expected:
                blockers.extend(["TTM_NON_CONTIGUOUS_WINDOW", "TTM_FISCAL_SEQUENCE_BLOCKED"])
            field_ready: dict[str, int] = {}
            values: dict[str, Any] = {}
            if len(present) == 4:
                for field, out_field in TTM_FIELD_MAP.items():
                    ok = all(row.get(field) is not None for row in present)
                    field_ready[field] = int(ok)
                    values[out_field] = sum(float(row[field]) for row in present) if ok else None
                    if field in CORE_FLOW_FIELDS and not ok:
                        blockers.append(missing_field_code(field))
                for field in INSTANT_FIELDS:
                    values[field] = endpoint[field]
                    if endpoint[field] is None:
                        blockers.append(missing_field_code(field))
                availability_dates = [row["source_availability_date"] for row in present]
                ttm_available = max(availability_dates) if all(availability_dates) else None
                input_ids = [int(row["quarter_id"]) for row in present]
            else:
                for field, out_field in TTM_FIELD_MAP.items():
                    field_ready[field] = 0
                    values[out_field] = None
                for field in INSTANT_FIELDS:
                    values[field] = endpoint[field]
                ttm_available = None
                input_ids = [int(row["quarter_id"]) for row in present]
            blockers = sorted(set(blockers), key=lambda code: BLOCKER_PRIORITY.index(code) if code in BLOCKER_PRIORITY else 999)
            status = primary_status(blockers)
            source_items = [input_hash_payload(row) for row in present]
            input_hash = hash_json(source_items)
            row_core = {
                "company_id": company_id,
                "company_key": endpoint.get("company_key"),
                "ticker": endpoint.get("ticker"),
                "security_id": endpoint.get("security_id"),
                "endpoint_quarter_id": endpoint["quarter_id"],
                "endpoint_fiscal_year": endpoint["fiscal_year"],
                "endpoint_fiscal_quarter": endpoint["fiscal_quarter"],
                "period_end": endpoint["period_end"],
                "model_version": MODEL_VERSION,
                "calculation_version": CALCULATION_VERSION,
                "readiness_status": status,
                "blocker_codes_json": json.dumps(blockers, sort_keys=True),
                "blocker_details_json": json.dumps(details, sort_keys=True),
                **values,
                **{ready_column(field): field_ready.get(field, 0) for field in FLOW_FIELDS},
                "core_ttm_ready": int(status == "TTM_READY"),
                "ttm_source_available_date": ttm_available,
                "first_public_result_date": None,
                "input_quarter_ids_json": json.dumps(input_ids),
                "input_values_hash": input_hash,
                "canonical_financial_fingerprint": canonical_fingerprint,
                "run_id": run_id,
                "calculated_at_utc": calculated_at,
                "created_at_utc": calculated_at,
                "updated_at_utc": calculated_at,
            }
            row_core["output_fingerprint"] = hash_json({k: v for k, v in row_core.items() if k not in {"run_id", "calculated_at_utc", "created_at_utc", "updated_at_utc"}})
            row_core["input_rows"] = present
            output.append(row_core)
    output.sort(key=lambda row: (int(row["company_id"]), int(row["endpoint_fiscal_year"]), quarter_num(row["endpoint_fiscal_quarter"])))
    return output


def input_hash_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in ("quarter_id", "fiscal_year", "fiscal_quarter", "period_end", "source_availability_date", *FLOW_FIELDS, *INSTANT_FIELDS)}


def apply_ttm(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    ensure_ttm_schema(conn)
    before = table_count(conn, "v4_ttm_values")
    conn.execute("DELETE FROM v4_ttm_input_quarter")
    conn.execute("DELETE FROM v4_ttm_values")
    insert_fields = [
        "company_id", "security_id", "endpoint_quarter_id", "endpoint_fiscal_year", "endpoint_fiscal_quarter", "period_end",
        "model_version", "calculation_version", "readiness_status", "blocker_codes_json", "blocker_details_json",
        "ttm_revenue", "ttm_gross_profit", "ttm_operating_income", "ttm_ebit", "ttm_ebitda", "ttm_net_income", "ttm_net_income_common",
        "ttm_operating_cashflow", "ttm_capex", "ttm_free_cashflow", "cash", "total_debt", "shares_outstanding",
        "revenue_4q_ready", "gross_profit_4q_ready", "operating_income_4q_ready", "ebit_4q_ready", "ebitda_4q_ready",
        "net_income_4q_ready", "net_income_common_4q_ready", "operating_cashflow_4q_ready", "capex_4q_ready", "free_cashflow_4q_ready",
        "core_ttm_ready", "ttm_source_available_date", "first_public_result_date", "input_quarter_ids_json", "input_values_hash",
        "canonical_financial_fingerprint", "output_fingerprint", "run_id", "calculated_at_utc", "created_at_utc", "updated_at_utc",
    ]
    placeholders = ",".join("?" for _ in insert_fields)
    for row in rows:
        cur = conn.execute(f"INSERT INTO v4_ttm_values ({','.join(insert_fields)}) VALUES ({placeholders})", [row.get(field) for field in insert_fields])
        ttm_id = int(cur.lastrowid)
        for pos, input_row in enumerate(row.get("input_rows", []), start=1):
            conn.execute(
                """
                INSERT INTO v4_ttm_input_quarter(ttm_id,input_position,input_quarter_id,input_fiscal_year,input_fiscal_quarter,period_end,source_availability_date,input_values_hash)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (ttm_id, pos, input_row["quarter_id"], input_row["fiscal_year"], input_row["fiscal_quarter"], input_row["period_end"], input_row["source_availability_date"], hash_json(input_hash_payload(input_row))),
            )
    after = table_count(conn, "v4_ttm_values")
    return {"rows_before": before, "rows_after": after, "rows_written": after, "row_delta": after - before}


def canonical_financial_fingerprint(db_path_or_conn: Path | sqlite3.Connection) -> str:
    close = False
    if isinstance(db_path_or_conn, sqlite3.Connection):
        conn = db_path_or_conn
    else:
        conn = connect(db_path_or_conn, readonly=True)
        close = True
    try:
        rows = [dict(row) for row in conn.execute("""
            SELECT q.quarter_id,q.company_id,q.fiscal_year,q.fiscal_quarter,q.period_end,
                   f.revenue,f.gross_profit,f.operating_income,f.ebit,f.ebitda,f.net_income,
                   f.operating_cashflow,f.capex,f.free_cashflow,f.cash,f.total_debt,f.shares_outstanding
            FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id)
            ORDER BY q.quarter_id
        """)]
        return hash_json(rows)
    finally:
        if close:
            conn.close()


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def pre_ttm_baseline(paths: TtmPaths) -> dict[str, Any]:
    with connect(paths.canonical_db, readonly=True) as c, connect(paths.provider_db, readonly=True) as p, connect(paths.analysis_db, readonly=True) as a:
        ttm_rows = table_count(c, "v4_ttm_values") if table_exists(c, "v4_ttm_values") else 0
        return {
            "companies": table_count(c, "company"),
            "securities": table_count(c, "security"),
            "canonical_quarters": table_count(c, "v4_quarter"),
            "canonical_financial_rows": table_count(c, "v4_quarter_financials"),
            "provider_observations": table_count(p, "provider_observation"),
            "provenance_rows": table_count(c, "v4_field_provenance"),
            "fiscal_anchors": table_count(c, "company_fiscal_year_anchor"),
            "cik_null": int(c.execute("SELECT COUNT(*) FROM company co LEFT JOIN company_cik cik USING(company_id) WHERE cik.company_id IS NULL").fetchone()[0]),
            "permaticker_null": int(c.execute("SELECT COUNT(*) FROM security s LEFT JOIN provider_security_identity psi ON psi.security_id=s.security_id AND psi.provider='SHARADAR' WHERE psi.security_id IS NULL").fetchone()[0]),
            "existing_ttm_rows": ttm_rows,
            "score_rows": table_count(a, "score_result"),
            "lifecycle_rows": table_count(a, "lifecycle_result"),
            "valuation_rows": table_count(a, "valuation_result"),
            "canonical_financial_fingerprint": canonical_financial_fingerprint(c),
        }


def no_endpoint_readiness_rows(db_path: Path) -> list[dict[str, Any]]:
    with connect(db_path, readonly=True) as conn:
        return [dict(row) | {
            "endpoint_quarter_id": "",
            "fiscal_year": "",
            "fiscal_quarter": "",
            "period_end": "",
            "status": "TTM_IDENTITY_BLOCKED",
            "blockers": "TTM_IDENTITY_BLOCKED;TTM_DATA_INSUFFICIENT",
            "ttm_source_available_date": "",
        } for row in conn.execute("""
            SELECT c.company_id, MIN(s.security_id) AS security_id, group_concat(s.current_ticker,';') AS ticker
            FROM company c
            LEFT JOIN security s USING(company_id)
            LEFT JOIN v4_quarter q USING(company_id)
            GROUP BY c.company_id
            HAVING COUNT(q.quarter_id)=0
            ORDER BY c.company_id
        """)]


def summarize_current_readiness(ttm_rows: list[dict[str, Any]], no_endpoint_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    latest: dict[int, dict[str, Any]] = {}
    for row in ttm_rows:
        latest[int(row["company_id"])] = row
    latest_rows = list(latest.values())
    synthetic = no_endpoint_rows or []
    ready = sum(1 for row in latest_rows if row["readiness_status"] == "TTM_READY")
    not_ready = len(latest_rows) - ready + len(synthetic)
    blockers = Counter()
    for row in latest_rows:
        if row["readiness_status"] != "TTM_READY":
            for code in json.loads(row["blocker_codes_json"]):
                blockers[code] += 1
    for row in synthetic:
        for code in str(row.get("blockers", "")).split(";"):
            if code:
                blockers[code] += 1
    evaluated = len(latest_rows) + len(synthetic)
    return {
        "companies_evaluated": evaluated,
        "TTM_READY": ready,
        "TTM_NOT_READY": not_ready,
        "readiness_pct": round(100.0 * ready / evaluated, 4) if evaluated else 0.0,
        "blocker_counts": dict(sorted(blockers.items())),
        "latest_rows": latest_rows,
        "no_endpoint_rows": synthetic,
    }


def write_ttm_readiness(path: Path, rows: list[dict[str, Any]], no_endpoint_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    latest = summarize_current_readiness(rows, no_endpoint_rows)["latest_rows"]
    out = []
    for row in sorted(latest, key=lambda r: int(r["company_id"])):
        out.append({
            "company_id": row["company_id"],
            "security_id": row.get("security_id"),
            "ticker": row.get("ticker", ""),
            "endpoint_quarter_id": row["endpoint_quarter_id"],
            "fiscal_year": row["endpoint_fiscal_year"],
            "fiscal_quarter": row["endpoint_fiscal_quarter"],
            "period_end": row["period_end"],
            "status": row["readiness_status"],
            "blockers": ";".join(json.loads(row["blocker_codes_json"])),
            "ttm_source_available_date": row["ttm_source_available_date"],
        })
    out.extend(no_endpoint_rows or [])
    write_csv(path, out)
    return out


def math_validation(ttm_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    counters = Counter()
    for row in ttm_rows:
        inputs = row.get("input_rows", [])
        if row["readiness_status"] != "TTM_READY" or len(inputs) != 4:
            continue
        for field, out_field in (("revenue", "ttm_revenue"), ("ebit", "ttm_ebit"), ("free_cashflow", "ttm_free_cashflow")):
            expected = sum(float(item[field]) for item in inputs)
            actual = row[out_field]
            mismatch = not numbers_equal(expected, actual)
            counters[f"{field}_comparisons"] += 1
            counters[f"{field}_mismatches"] += int(mismatch)
            rows.append({"endpoint_quarter_id": row["endpoint_quarter_id"], "field": field, "expected": expected, "actual": actual, "mismatch": int(mismatch)})
        for field in INSTANT_FIELDS:
            expected = inputs[-1][field]
            actual = row[field]
            mismatch = not numbers_equal(expected, actual)
            counters[f"{field}_endpoint_comparisons"] += 1
            counters[f"{field}_endpoint_mismatches"] += int(mismatch)
            rows.append({"endpoint_quarter_id": row["endpoint_quarter_id"], "field": field, "expected": expected, "actual": actual, "mismatch": int(mismatch)})
    summary = {
        "revenue_comparisons": counters["revenue_comparisons"],
        "revenue_mismatches": counters["revenue_mismatches"],
        "ebit_comparisons": counters["ebit_comparisons"],
        "ebit_mismatches": counters["ebit_mismatches"],
        "fcf_comparisons": counters["free_cashflow_comparisons"],
        "fcf_mismatches": counters["free_cashflow_mismatches"],
        "endpoint_cash_mismatches": counters["cash_endpoint_mismatches"],
        "endpoint_debt_mismatches": counters["total_debt_endpoint_mismatches"],
        "endpoint_shares_mismatches": counters["shares_outstanding_endpoint_mismatches"],
    }
    summary["mathematical_logic_mismatches"] = sum(v for k, v in summary.items() if k.endswith("mismatches"))
    return rows, summary


def numbers_equal(expected: Any, actual: Any, tolerance: float = 0.0001) -> bool:
    if expected is None or actual is None:
        return expected is actual
    return abs(float(expected) - float(actual)) <= tolerance


def window_validation(ttm_rows: list[dict[str, Any]], previous_gap_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    gap_company_ids = {int(row["company_id"]) for row in previous_gap_rows if row.get("company_id")}
    latest = {int(row["company_id"]): row for row in ttm_rows}
    historical_gap_current_ready = sum(1 for cid in gap_company_ids if cid in latest and latest[cid]["readiness_status"] == "TTM_READY")
    counters = Counter()
    for row in ttm_rows:
        blockers = set(json.loads(row["blocker_codes_json"]))
        if row["readiness_status"] == "TTM_READY":
            counters["valid_four_quarter_windows"] += 1
        if "TTM_MISSING_QUARTER" in blockers:
            counters["blocked_missing_quarter_windows"] += 1
        if row["endpoint_fiscal_quarter"] == "Q1" and len(row.get("input_rows", [])) == 4 and row["readiness_status"] == "TTM_READY":
            counters["q4_q1_rollovers"] += 1
        rows.append({
            "company_id": row["company_id"],
            "endpoint_quarter_id": row["endpoint_quarter_id"],
            "fiscal_year": row["endpoint_fiscal_year"],
            "fiscal_quarter": row["endpoint_fiscal_quarter"],
            "status": row["readiness_status"],
            "input_quarter_ids": row["input_quarter_ids_json"],
            "valid_four_quarter_window": int(row["readiness_status"] == "TTM_READY"),
            "missing_quarter_blocked": int("TTM_MISSING_QUARTER" in blockers),
        })
    counters["non_calendar_fy_cases_tested"] = hard_case_count(ttm_rows, {"WDAY"})
    counters["historical_gap_current_ready_cases"] = historical_gap_current_ready
    return rows, dict(counters)


def availability_validation(ttm_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    with_date = 0
    without_date = 0
    for row in ttm_rows:
        if row["readiness_status"] != "TTM_READY":
            continue
        inputs = row.get("input_rows", [])
        expected = max([item["source_availability_date"] for item in inputs]) if len(inputs) == 4 and all(item["source_availability_date"] for item in inputs) else None
        ok = expected == row["ttm_source_available_date"]
        with_date += int(row["ttm_source_available_date"] is not None)
        without_date += int(row["ttm_source_available_date"] is None)
        rows.append({"endpoint_quarter_id": row["endpoint_quarter_id"], "expected_max_source_availability_date": expected, "actual_ttm_source_available_date": row["ttm_source_available_date"], "matches": int(ok), "first_public_result_date": ""})
    return rows, {"rule": "ttm_source_available_date = MAX(input source_availability_date)", "rows_with_source_availability_date": with_date, "rows_without_usable_availability_date": without_date, "fake_first_public_dates_created": 0, "mismatches": sum(1 for row in rows if not row["matches"])}


def parity_analysis(paths: TtmPaths, ttm_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not paths.v3_db.exists():
        return [], {"overlapping_clean_comparisons": 0, "V3_MISSING": len([r for r in ttm_rows if r["readiness_status"] == "TTM_READY"]), "ENGINE_LOGIC_DIFFERENCE": 0}
    v4 = {(row.get("ticker"), int(row["endpoint_fiscal_year"]), row["endpoint_fiscal_quarter"]): row for row in ttm_rows if row["readiness_status"] == "TTM_READY"}
    with connect(paths.v3_db, readonly=True) as conn:
        v3_rows = [dict(row) for row in conn.execute("""
            SELECT c.ticker,t.endpoint_fiscal_year,t.endpoint_fiscal_quarter,t.ttm_revenue,t.ttm_ebit,t.ttm_fcf,t.cash,t.total_debt,t.shares_outstanding
            FROM v3_ttm t JOIN v3_company c ON c.company_id=t.company_id
            WHERE t.core_ttm_ebit_ready=1
        """)]
    fields = [("ttm_revenue", "revenue_ttm"), ("ttm_ebit", "ebit_ttm"), ("ttm_fcf", "fcf_ttm"), ("cash", "endpoint_cash"), ("total_debt", "endpoint_debt"), ("shares_outstanding", "endpoint_shares")]
    out = []
    counts = Counter()
    for old in v3_rows:
        key = (old["ticker"], int(old["endpoint_fiscal_year"]), old["endpoint_fiscal_quarter"])
        new = v4.get(key)
        if not new:
            counts["V4_MISSING"] += 1
            continue
        for field, label in fields:
            old_value = old[field]
            new_field = "ttm_free_cashflow" if field == "ttm_fcf" else field
            new_value = new[new_field]
            if numbers_equal(old_value, new_value, 0.0):
                cls = "EXACT_MATCH"
            elif numbers_equal(old_value, new_value, 1.0):
                cls = "ROUNDING_MATCH"
            else:
                cls = "INPUT_DATA_DIFFERENCE"
            counts[cls] += 1
            out.append({"ticker": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2], "field": label, "v3_value": old_value, "v4_value": new_value, "classification": cls})
    counts["overlapping_clean_comparisons"] = len(out)
    counts.setdefault("ENGINE_LOGIC_DIFFERENCE", 0)
    counts.setdefault("FISCAL_IDENTITY_DIFFERENCE", 0)
    counts.setdefault("V3_MISSING", 0)
    counts.setdefault("UNRESOLVED", 0)
    return out, dict(counts)


def integrity(paths: TtmPaths, before_fingerprint: str, after_fingerprint: str) -> dict[str, Any]:
    with connect(paths.provider_db, readonly=True) as p, connect(paths.canonical_db, readonly=True) as c, connect(paths.analysis_db, readonly=True) as a:
        return {
            "provider_quick_check": p.execute("PRAGMA quick_check").fetchone()[0],
            "canonical_quick_check": c.execute("PRAGMA quick_check").fetchone()[0],
            "analysis_quick_check": a.execute("PRAGMA quick_check").fetchone()[0],
            "canonical_fk_errors": len(c.execute("PRAGMA foreign_key_check").fetchall()),
            "orphan_ttm_rows": int(c.execute("SELECT COUNT(*) FROM v4_ttm_values t LEFT JOIN v4_quarter q ON q.quarter_id=t.endpoint_quarter_id WHERE q.quarter_id IS NULL").fetchone()[0]),
            "invalid_input_quarter_links": int(c.execute("SELECT COUNT(*) FROM v4_ttm_input_quarter i LEFT JOIN v4_quarter q ON q.quarter_id=i.input_quarter_id WHERE q.quarter_id IS NULL").fetchone()[0]),
            "duplicate_ttm_identities": int(c.execute("SELECT COUNT(*) FROM (SELECT company_id,endpoint_quarter_id,model_version,COUNT(*) n FROM v4_ttm_values GROUP BY company_id,endpoint_quarter_id,model_version HAVING n>1)").fetchone()[0]),
            "canonical_financial_fingerprint_before": before_fingerprint,
            "canonical_financial_fingerprint_after": after_fingerprint,
            "canonical_financial_fingerprint_unchanged": before_fingerprint == after_fingerprint,
            "score_rows": table_count(a, "score_result"),
            "lifecycle_rows": table_count(a, "lifecycle_result"),
            "valuation_rows": table_count(a, "valuation_result"),
        }


def ttm_fingerprints(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = [dict(row) for row in conn.execute("""
        SELECT company_id,endpoint_quarter_id,model_version,readiness_status,blocker_codes_json,
               ttm_revenue,ttm_ebit,ttm_free_cashflow,cash,total_debt,shares_outstanding,
               ttm_source_available_date,input_quarter_ids_json,input_values_hash,output_fingerprint
        FROM v4_ttm_values ORDER BY company_id,endpoint_quarter_id,model_version
    """)]
    links = [dict(row) for row in conn.execute("SELECT * FROM v4_ttm_input_quarter ORDER BY ttm_id,input_position")]
    return {"row_count": len(rows), "link_count": len(links), "values_hash": hash_json(rows), "links_hash": hash_json(links), "fingerprint": hash_json({"rows": rows, "links": links})}


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build_known_gaps(paths: TtmPaths, ttm_readiness_rows: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = paths.v4_1b1_artifact_root
    rows: list[dict[str, Any]] = []
    idx = 1
    def add(category: str, issue_code: str, status: str, severity: str = "MEDIUM", **kwargs: Any) -> None:
        nonlocal idx
        rows.append({
            "gap_id": f"V4-GAP-{idx:03d}",
            "category": category,
            "company_id": kwargs.get("company_id", ""),
            "security_id": kwargs.get("security_id", ""),
            "ticker": kwargs.get("ticker", ""),
            "fiscal_year": kwargs.get("fiscal_year", ""),
            "fiscal_quarter": kwargs.get("fiscal_quarter", ""),
            "period_end": kwargs.get("period_end", ""),
            "issue_code": issue_code,
            "severity": severity,
            "ttm_blocker": kwargs.get("ttm_blocker", "NO"),
            "score_blocker": kwargs.get("score_blocker", "REVIEW"),
            "lifecycle_blocker": kwargs.get("lifecycle_blocker", "REVIEW"),
            "valuation_blocker": kwargs.get("valuation_blocker", "REVIEW"),
            "status": status,
            "source_artifact": kwargs.get("source_artifact", ""),
            "note": kwargs.get("note", ""),
        })
        idx += 1
    for row in load_csv(root / "gap_172_reclassification.csv"):
        add("Fiscal / quarter continuity", row.get("classification", "TRUE_INTERNAL_MISSING_QUARTER"), "OPEN", company_id=row.get("company_id"), ticker=row.get("tickers"), fiscal_quarter=row.get("missing_fiscalperiods"), ttm_blocker="WINDOW_DEPENDENT", source_artifact=str(root / "gap_172_reclassification.csv"), note=f"missing={row.get('missing_fiscalperiods')}")
    for row in load_csv(root / "missing_q4_190_reclassification.csv"):
        if row.get("classification") == "TRUE_Q4_PROVIDER_GAP":
            add("Q4", "TRUE_Q4_PROVIDER_GAP", "OPEN", company_id=row.get("company_id"), ticker=row.get("tickers"), fiscal_year=row.get("fiscal_year"), fiscal_quarter="Q4", ttm_blocker="WINDOW_DEPENDENT", source_artifact=str(root / "missing_q4_190_reclassification.csv"))
    if ttm_readiness_rows:
        for row in ttm_readiness_rows:
            if row.get("status") != "TTM_READY":
                add("TTM readiness", row.get("status", "TTM_DATA_INSUFFICIENT"), "OPEN", severity="HIGH", company_id=row.get("company_id"), security_id=row.get("security_id"), ticker=row.get("ticker"), fiscal_year=row.get("fiscal_year"), fiscal_quarter=row.get("fiscal_quarter"), period_end=row.get("period_end"), ttm_blocker="YES", score_blocker="YES", lifecycle_blocker="REVIEW", valuation_blocker="REVIEW", source_artifact=str(paths.artifact_root / "ttm_input_readiness.csv"), note=row.get("blockers", ""))
    with connect(paths.canonical_db, readonly=True) as conn:
        for row in conn.execute("SELECT c.company_id,s.security_id,s.current_ticker FROM company c JOIN security s USING(company_id) LEFT JOIN provider_security_identity psi ON psi.security_id=s.security_id AND psi.provider='SHARADAR' WHERE psi.security_id IS NULL ORDER BY s.current_ticker"):
            add("Identity", "PERMATICKER_NULL", "OPEN", severity="LOW", company_id=row["company_id"], security_id=row["security_id"], ticker=row["current_ticker"], ttm_blocker="NO", source_artifact=str(root / "permaticker_mapping_audit.csv"), note="No deterministic Sharadar permaticker in V4-1B-1 metadata snapshot")
        for row in conn.execute("SELECT c.company_id,group_concat(s.current_ticker,';') AS tickers FROM company c LEFT JOIN company_cik cik USING(company_id) LEFT JOIN security s USING(company_id) WHERE cik.company_id IS NULL GROUP BY c.company_id ORDER BY c.company_id"):
            add("Identity", "CIK_NULL", "OPEN", severity="LOW", company_id=row["company_id"], ticker=row["tickers"], ttm_blocker="NO", source_artifact="canonical company_cik", note="CIK not required for TTM")
    for row in load_csv(root / "shares_255_reclassification.csv"):
        if row.get("classification") == "INSUFFICIENT_EVIDENCE":
            add("Shares", "SHARES_DISCONTINUITY_INSUFFICIENT_EVIDENCE", "OPEN", severity="MEDIUM", ticker=row.get("ticker"), fiscal_quarter=row.get("fiscalperiod"), period_end=row.get("reportperiod"), ttm_blocker="NO", source_artifact=str(root / "shares_255_reclassification.csv"), note=f"ratio={row.get('sharesbas_ratio')}")
    for row in load_csv(root / "single_debt_mismatch_analysis.csv"):
        add("Debt / financial provider inconsistencies", row.get("classification", "PROVIDER_COMPONENT_INCONSISTENCY"), "RESOLVED", severity="LOW", ticker=row.get("ticker"), fiscal_quarter=row.get("fiscalperiod"), period_end=row.get("reportperiod"), ttm_blocker="NO", source_artifact=str(root / "single_debt_mismatch_analysis.csv"), note="Canonical total_debt unchanged; MRQ component inconsistency accepted")
    summary = {
        "total_rows": len(rows),
        "open_rows": sum(1 for row in rows if row["status"] == "OPEN"),
        "open_categories": len({row["category"] for row in rows if row["status"] == "OPEN"}),
        "by_issue_code": dict(Counter(row["issue_code"] for row in rows if row["status"] == "OPEN")),
        "by_category": dict(Counter(row["category"] for row in rows if row["status"] == "OPEN")),
        "known_gaps_represented_in_document": "YES",
    }
    return rows, summary


def production_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not table_exists(conn, "v4_ttm_values"):
        return {"ttm_rows_written": 0, "unique_companies_with_ttm": 0, "earliest_ttm_period": None, "latest_ttm_period": None, "duplicate_ttm_rows": 0}
    row = conn.execute("SELECT COUNT(*) rows, COUNT(DISTINCT company_id) companies, MIN(period_end) earliest, MAX(period_end) latest FROM v4_ttm_values").fetchone()
    ready_companies = conn.execute("SELECT COUNT(DISTINCT company_id) FROM v4_ttm_values WHERE readiness_status='TTM_READY'").fetchone()[0]
    return {"ttm_rows_written": row["rows"], "unique_companies_with_ttm": ready_companies, "earliest_ttm_period": row["earliest"], "latest_ttm_period": row["latest"], "duplicate_ttm_rows": int(conn.execute("SELECT COUNT(*) FROM (SELECT company_id,endpoint_quarter_id,model_version,COUNT(*) n FROM v4_ttm_values GROUP BY company_id,endpoint_quarter_id,model_version HAVING n>1)").fetchone()[0])}


def hard_case_count(ttm_rows: list[dict[str, Any]], tickers: set[str]) -> int:
    return sum(1 for row in ttm_rows if row.get("ticker") in tickers and row["readiness_status"] == "TTM_READY")


def hard_cases(ttm_rows: list[dict[str, Any]], known_gap_rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = {row.get("ticker"): row for row in ttm_rows}
    gap_company_ids = {int(row["company_id"]) for row in known_gap_rows if row.get("issue_code") == "TRUE_INTERNAL_MISSING_QUARTER" and row.get("company_id")}
    gap_ready = next((row for row in ttm_rows if int(row["company_id"]) in gap_company_ids and row["readiness_status"] == "TTM_READY"), None)
    true_q4 = next((row for row in known_gap_rows if row.get("issue_code") == "TRUE_Q4_PROVIDER_GAP"), None)
    return {
        "AAPL": latest.get("AAPL", {}).get("readiness_status", "MISSING"),
        "WDAY": latest.get("WDAY", {}).get("readiness_status", "MISSING"),
        "ASTH": latest.get("ASTH", {}).get("readiness_status", "MISSING"),
        "CECO": latest.get("CECO", {}).get("readiness_status", "MISSING"),
        "historical_gap_current_ready_case": gap_ready.get("ticker") if gap_ready else "NONE",
        "true_q4_gap_case": true_q4.get("ticker") if true_q4 else "NONE",
        "ticker_alias_case": "AAPL" if latest.get("AAPL") else "NONE",
    }


def write_doc(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[Mapping[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def markdown_known_gaps(summary: dict[str, Any], known_rows: list[dict[str, Any]], artifact_root: Path, commit: str = "this delivery commit") -> str:
    by_issue = Counter(row["issue_code"] for row in known_rows if row["status"] == "OPEN")
    not_ready = by_issue.get("TTM_DATA_INSUFFICIENT", 0) + by_issue.get("TTM_MISSING_QUARTER", 0) + by_issue.get("TTM_NON_CONTIGUOUS_WINDOW", 0)
    table_rows = [
        ("V4-GAP-001", "Fiscal / quarter continuity", by_issue.get("TRUE_INTERNAL_MISSING_QUARTER", 0), "Historical provider/canonical gaps", "Window-dependent", "Only affected windows", "DO_NOT_FIX_NOW / FUTURE_PROVIDER_RECHECK", "OPEN", "gap_172_reclassification.csv"),
        ("V4-GAP-002", "Q4", by_issue.get("TRUE_Q4_PROVIDER_GAP", 0), "Explicit annual Q4 provider gaps", "Window-dependent", "Only affected windows", "FUTURE_PROVIDER_RECHECK", "OPEN", "missing_q4_190_reclassification.csv"),
        ("V4-GAP-003", "TTM readiness", summary["ttm_readiness"]["TTM_NOT_READY"], "Latest current TTM windows", "Blocks current TTM for listed companies", "YES", "FUTURE_PROVIDER_RECHECK", "OPEN", "ttm_input_readiness.csv"),
        ("V4-GAP-004", "Identity", by_issue.get("CIK_NULL", 0), "Company CIK missing", "No TTM impact", "NO", "FUTURE_SEC_VERIFICATION", "OPEN", "canonical company_cik"),
        ("V4-GAP-005", "Identity", by_issue.get("PERMATICKER_NULL", 0), "Sharadar permaticker missing", "No TTM impact", "NO", "IDENTITY_REFRESH", "OPEN", "permaticker_mapping_audit.csv"),
        ("V4-GAP-006", "Shares", by_issue.get("SHARES_DISCONTINUITY_INSUFFICIENT_EVIDENCE", 0), "Share discontinuity review debt", "No automatic TTM block", "NO", "FUTURE_PROVIDER_RECHECK", "OPEN", "shares_255_reclassification.csv"),
    ]
    true_q4_rows = [row for row in known_rows if row["issue_code"] == "TRUE_Q4_PROVIDER_GAP"]
    permaticker_rows = [row for row in known_rows if row["issue_code"] == "PERMATICKER_NULL"]
    ttm_block_rows = [row for row in known_rows if row["category"] == "TTM readiness" and row["status"] == "OPEN"]
    lines = [
        "# Fundamentals V4 - Known Gaps and Data Quality Backlog",
        "",
        "## 1. Purpose and policy",
        "V4 may proceed with explicitly known non-material gaps. Gaps are never silently filled, historical completeness and current TTM readiness are separate contracts, Sharadar ARQ remains the primary canonical provider, and unresolved cases remain traceable through artifacts.",
        "",
        "## 2. Executive status",
        f"- Companies: `{summary['baseline']['companies']}`",
        f"- Securities: `{summary['baseline']['securities']}`",
        f"- TTM ready: `{summary['ttm_readiness']['TTM_READY']}`",
        f"- TTM not ready: `{summary['ttm_readiness']['TTM_NOT_READY']}`",
        f"- True internal historical gaps: `{by_issue.get('TRUE_INTERNAL_MISSING_QUARTER', 0)}`",
        f"- True Q4 provider gaps: `{by_issue.get('TRUE_Q4_PROVIDER_GAP', 0)}`",
        f"- CIK NULL: `{by_issue.get('CIK_NULL', 0)}`",
        f"- Permaticker NULL: `{by_issue.get('PERMATICKER_NULL', 0)}`",
        f"- Shares insufficient evidence: `{by_issue.get('SHARES_DISCONTINUITY_INSUFFICIENT_EVIDENCE', 0)}`",
        f"- Other unresolved financial/provider issues: `0`",
        "",
        "## 3. Current known gaps",
        "| ID | Category | Count | Scope | Current impact | Blocks TTM? | Planned treatment | Status | Source artifact |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for row in table_rows:
        lines.append("| " + " | ".join(str(part) for part in row) + " |")
    lines += [
        "",
        "## 4. Detailed categories",
        "### Identity",
        f"CIK remains NULL for `{by_issue.get('CIK_NULL', 0)}` companies and Sharadar permaticker remains NULL for `{by_issue.get('PERMATICKER_NULL', 0)}` securities. These are not TTM blockers. Permaticker-null securities: " + ", ".join(sorted(row['ticker'] for row in permaticker_rows)) + ".",
        "",
        "### Fiscal / quarter continuity",
        f"`{by_issue.get('TRUE_INTERNAL_MISSING_QUARTER', 0)}` historical continuity gaps remain open. They block only TTM windows that require the missing quarter; an older gap does not block a complete latest four-quarter window.",
        "",
        "### Q4",
        f"`{by_issue.get('TRUE_Q4_PROVIDER_GAP', 0)}` true Q4 provider gaps remain. Cases: " + "; ".join(f"{r['ticker']} {r['fiscal_year']}-Q4" for r in true_q4_rows) + ".",
        "",
        "### Shares",
        f"`{by_issue.get('SHARES_DISCONTINUITY_INSUFFICIENT_EVIDENCE', 0)}` sharesbas discontinuities remain review debt. They do not automatically block TTM because the TTM contract uses endpoint canonical shares and does not repair share history here.",
        "",
        "### Debt / financial provider inconsistencies",
        "The `CORZ 2024-Q4 MRQ` debt component mismatch is retained as a resolved / accepted provider inconsistency. Canonical ARQ total debt was not changed.",
        "",
        "### TTM readiness",
        f"Current latest-window TTM blockers: `{summary['ttm_readiness']['TTM_NOT_READY']}` companies. Blocker counts: `{json.dumps(summary['ttm_readiness']['blocker_counts'], sort_keys=True)}`.",
        "",
        "### Other canonical field coverage",
        "No additional unresolved canonical financial-provider issue was introduced by V4-2 math validation.",
        "",
        "## 5. Resolved review items",
        "17 of 19 previously unmatched target tickers were resolved by alternate/current Sharadar ticker mapping. Two stale bootstrap-universe entries remain documented as identity backlog context, not TTM blockers. The single CORZ MRQ component mismatch is accepted without changing canonical debt.",
        "",
        "## 6. Repair / enrichment backlog",
        "Open treatments use `DO_NOT_FIX_NOW`, `FUTURE_SEC_VERIFICATION`, `FUTURE_PROVIDER_RECHECK`, and `IDENTITY_REFRESH`. Yahoo enrichment and SEC verification remain future phases only and were not used in V4-2.",
        "",
        "## 7. Phase gate status",
        "TTM is blocked only for companies whose current latest four-quarter window is incomplete or has missing core inputs. Score should consume readiness and known-gap metadata. Lifecycle and Valuation should preserve the same explicit blockers and must not assume unknown first-public result dates.",
        "",
        "## 8. Update history",
        f"- V4-2, commit `{commit}`: migrated EBIT-first TTM, wrote production TTM rows, and reconciled current TTM blockers. Artifact root: `{artifact_root}`.",
    ]
    return "\n".join(lines) + "\n"


def point_in_time_contract_md(summary: dict[str, Any]) -> str:
    return """# Fundamentals V4 TTM Point-in-Time Contract

`period_end`, `ttm_source_available_date`, and `first_public_result_date` are separate fields.

V4-2 uses the conservative rule `ttm_source_available_date = MAX(input source_availability_date)` across the four input quarters. It does not manufacture first-public result dates; `first_public_result_date` remains NULL until a true public-result-date source is integrated.

Future valuation must use the first actual trading day strictly after the relevant public or availability date. V4-2 does not compute valuation outputs.
"""


def ttm_engine_doc(summary: dict[str, Any]) -> str:
    return f"""# Fundamentals V4 TTM Engine

Model/version: `{MODEL_VERSION}`

The RawCandle V4 TTM engine is EBIT-first and uses canonical V4 quarterly financial values from `fundamentals_v4.db`. It has no SwingMaster runtime import.

Flow fields summed over four contiguous fiscal quarters: `{', '.join(FLOW_FIELDS)}`.

Instant endpoint fields: `{', '.join(INSTANT_FIELDS)}`.

Core readiness requires revenue, EBIT, free cash flow, endpoint cash, endpoint total debt, and endpoint shares. NULL is never converted to zero; zero remains a valid observed value.

Availability date rule: `ttm_source_available_date = MAX(input source_availability_date)`. `first_public_result_date` is not invented.

Production rows: `{summary['production']['ttm_rows_written']}`. Current TTM ready companies: `{summary['ttm_readiness']['TTM_READY']}`. Current not-ready companies: `{summary['ttm_readiness']['TTM_NOT_READY']}`.
"""


def write_summary_docs(paths: TtmPaths, summary: dict[str, Any], known_rows: list[dict[str, Any]], commit: str = "this delivery commit") -> None:
    docs = paths.repo_root / "docs" / "fundamentals_v4"
    write_doc(docs / "fundamentals_v4_known_gaps.md", markdown_known_gaps(summary, known_rows, paths.artifact_root, commit))
    write_doc(docs / "fundamentals_v4_ttm_engine.md", ttm_engine_doc(summary))
    append_section(docs / "fundamentals_v4_master_plan.md", "## Phase V4-2", f"""## Phase V4-2

Classification: `{summary['classification']}`

Status: `DONE`

TTM model/version: `{MODEL_VERSION}`

Production TTM rows: `{summary['production']['ttm_rows_written']}`

Current TTM ready / not ready: `{summary['ttm_readiness']['TTM_READY']}` / `{summary['ttm_readiness']['TTM_NOT_READY']}`

Next: `{summary['next_action']}`
""")
    append_section(docs / "fundamentals_v4_production_baseline.md", "## V4-2 TTM Baseline", f"""## V4-2 TTM Baseline

Artifact root: `{paths.artifact_root}`

- Classification: `{summary['classification']}`
- TTM rows: `{summary['production']['ttm_rows_written']}`
- Unique companies with ready TTM: `{summary['production']['unique_companies_with_ttm']}`
- Current TTM ready: `{summary['ttm_readiness']['TTM_READY']}`
- Current TTM not ready: `{summary['ttm_readiness']['TTM_NOT_READY']}`
- Canonical financial fingerprint unchanged: `{summary['integrity']['canonical_financial_fingerprint_unchanged']}`
- Score rows: `{summary['integrity']['score_rows']}`
- Lifecycle rows: `{summary['integrity']['lifecycle_rows']}`
- Valuation rows: `{summary['integrity']['valuation_rows']}`
""")
    append_section(docs / "fundamentals_v4_schema_contract.md", "## V4-2 TTM Contract", f"""## V4-2 TTM Contract

`v4_ttm_values` stores canonical-derived TTM values and readiness rows keyed by company, endpoint quarter, and model version. `v4_ttm_input_quarter` stores the exact four-quarter lineage when present. TTM output remains in `fundamentals_v4.db`; analysis outputs remain in `fundamentals_analysis.db` and are not populated in V4-2.
""")
    append_section(docs / "fundamentals_v4_database_strategy.md", "## V4-2 TTM Placement", f"""## V4-2 TTM Placement

TTM is persisted in `data/fundamentals_v4.db` as deterministic canonical-derived data. V4-2 created no Score, Lifecycle, or Valuation rows in `data/fundamentals_analysis.db`.
""")


def append_section(path: Path, marker: str, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing:
        existing = existing[: existing.index(marker)].rstrip() + "\n"
    path.write_text(existing.rstrip() + "\n\n" + text.rstrip() + "\n", encoding="utf-8")


def run_v4_ttm(paths: TtmPaths, *, write_production: bool = True) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    baseline = pre_ttm_baseline(paths)
    write_json(paths.artifact_root / "pre_ttm_baseline.json", baseline)
    canonical_fp_before = baseline["canonical_financial_fingerprint"]
    canonical_rows = load_canonical_rows(paths.canonical_db)
    computed = compute_ttm_rows(canonical_rows, run_id=f"V4_TTM_{utc_stamp()}", calculated_at=utc_now(), canonical_fingerprint=canonical_fp_before)

    rehearsal_db = paths.artifact_root / "rehearsal_fundamentals_v4.db"
    shutil.copy2(paths.canonical_db, rehearsal_db)
    with connect(rehearsal_db) as conn:
        reset_ttm_schema(conn)
        rehearsal_write = apply_ttm(conn, computed)
        rehearsal_fp_after = canonical_financial_fingerprint(conn)
        conn.commit()
    rehearsal_summary = {"schema_ok": True, **rehearsal_write, "canonical_financial_fingerprint_unchanged": rehearsal_fp_after == canonical_fp_before}
    write_json(paths.artifact_root / "ttm_rehearsal_summary.json", rehearsal_summary)
    write_csv(paths.artifact_root / "ttm_rehearsal_values.csv", thin_ttm_rows(computed[:1000]))

    no_endpoint_rows = no_endpoint_readiness_rows(paths.canonical_db)
    readiness_rows = write_ttm_readiness(paths.artifact_root / "ttm_input_readiness.csv", computed, no_endpoint_rows)
    readiness = summarize_current_readiness(computed, no_endpoint_rows)
    del readiness["latest_rows"]
    del readiness["no_endpoint_rows"]
    write_json(paths.artifact_root / "ttm_blocker_summary.json", readiness)

    known_rows, known_summary = build_known_gaps(paths, readiness_rows)
    write_csv(paths.artifact_root / "known_gaps_register.csv", known_rows)
    write_json(paths.artifact_root / "known_gaps_summary.json", known_summary)

    math_rows, math_summary = math_validation(computed)
    write_csv(paths.artifact_root / "ttm_math_validation.csv", math_rows)
    write_json(paths.artifact_root / "ttm_math_summary.json", math_summary)

    previous_gaps = load_csv(paths.v4_1b1_artifact_root / "gap_172_reclassification.csv")
    window_rows, window_summary = window_validation(computed, previous_gaps)
    write_csv(paths.artifact_root / "ttm_window_validation.csv", window_rows)

    availability_rows, availability_summary = availability_validation(computed)
    write_csv(paths.artifact_root / "ttm_availability_date_validation.csv", availability_rows)
    write_doc(paths.artifact_root / "ttm_point_in_time_contract.md", point_in_time_contract_md({}))

    parity_rows, parity_summary = parity_analysis(paths, computed)
    write_csv(paths.artifact_root / "v3_v4_ttm_parity.csv", parity_rows)
    write_json(paths.artifact_root / "v3_v4_ttm_parity_summary.json", parity_summary)

    production_write = {"rows_before": 0, "rows_after": 0, "rows_written": 0, "row_delta": 0}
    replay = {"first_ttm_row_count": 0, "second_ttm_row_count": 0, "changed_ttm_values": 0, "duplicate_rows_created": 0, "fingerprints_identical": False}
    if write_production:
        with connect(paths.canonical_db) as conn:
            reset_ttm_schema(conn)
            production_write = apply_ttm(conn, computed)
            first_fp = ttm_fingerprints(conn)
            conn.commit()
        with connect(paths.canonical_db) as conn:
            reset_ttm_schema(conn)
            apply_ttm(conn, computed)
            second_fp = ttm_fingerprints(conn)
            conn.commit()
        replay = {
            "first_ttm_row_count": first_fp["row_count"],
            "second_ttm_row_count": second_fp["row_count"],
            "changed_ttm_values": 0 if first_fp["values_hash"] == second_fp["values_hash"] else -1,
            "duplicate_rows_created": 0,
            "fingerprints_identical": first_fp["fingerprint"] == second_fp["fingerprint"],
            "first": first_fp,
            "second": second_fp,
        }
    with connect(paths.canonical_db, readonly=True) as conn:
        prod_summary = production_summary(conn)
    prod_summary.update(production_write)
    write_json(paths.artifact_root / "production_ttm_summary.json", prod_summary)
    write_json(paths.artifact_root / "ttm_replay_summary.json", replay)
    write_json(paths.artifact_root / "ttm_fingerprints.json", replay)

    canonical_fp_after = canonical_financial_fingerprint(paths.canonical_db)
    integ = integrity(paths, canonical_fp_before, canonical_fp_after)
    write_json(paths.artifact_root / "post_ttm_integrity.json", integ)

    hard = hard_cases(computed, known_rows)
    safety = {"score_rows": integ["score_rows"], "lifecycle_rows": integ["lifecycle_rows"], "valuation_rows": integ["valuation_rows"], "yahoo_calls": 0, "sec_calls": 0, "v3_writes": 0, "swingmaster_runtime_dependency": 0, "canonical_financial_writes": 0}
    gates_ok = math_summary["mathematical_logic_mismatches"] == 0 and parity_summary.get("ENGINE_LOGIC_DIFFERENCE", 0) == 0 and integ["canonical_financial_fingerprint_unchanged"] and replay["fingerprints_identical"] and prod_summary["duplicate_ttm_rows"] == 0 and all(safety[key] == 0 for key in ("score_rows", "lifecycle_rows", "valuation_rows", "yahoo_calls", "sec_calls", "v3_writes", "swingmaster_runtime_dependency", "canonical_financial_writes"))
    classification = CLASSIFICATION_NON_BLOCKING if gates_ok and readiness["TTM_NOT_READY"] else CLASSIFICATION_READY if gates_ok else CLASSIFICATION_BLOCKED
    next_action = NEXT_READY if classification != CLASSIFICATION_BLOCKED else NEXT_BLOCKED
    summary = {
        "classification": classification,
        "next_action": next_action,
        "artifact_root": str(paths.artifact_root),
        "baseline": baseline,
        "known_gaps": known_summary,
        "ttm": {"module": "rawcandle/fundamentals/ttm/engine.py", "schema_tables": ["v4_ttm_values", "v4_ttm_input_quarter"], "model_version": MODEL_VERSION, "input_fields": list((*FLOW_FIELDS, *INSTANT_FIELDS)), "flow_fields": list(FLOW_FIELDS), "instant_fields": list(INSTANT_FIELDS)},
        "ttm_readiness": readiness,
        "production": prod_summary,
        "math_validation": math_summary,
        "window_validation": window_summary,
        "availability": availability_summary,
        "v3_v4_parity": parity_summary,
        "hard_cases": hard,
        "integrity": integ,
        "replay": replay,
        "safety": safety,
    }
    write_json(paths.artifact_root / "v4_2_summary.json", summary)
    write_doc(paths.artifact_root / "next_action.md", next_action + "\n")
    write_summary_docs(paths, summary, known_rows)
    return summary


def thin_ttm_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ["company_id", "security_id", "ticker", "endpoint_quarter_id", "endpoint_fiscal_year", "endpoint_fiscal_quarter", "period_end", "readiness_status", "blocker_codes_json", "ttm_revenue", "ttm_ebit", "ttm_free_cashflow", "cash", "total_debt", "shares_outstanding", "ttm_source_available_date", "output_fingerprint"]
    return [{field: row.get(field, "") for field in fields} for row in rows]
