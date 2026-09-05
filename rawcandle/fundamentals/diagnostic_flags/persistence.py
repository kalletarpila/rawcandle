from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.diagnostic_flags.engine import (
    EVIDENCE_SCHEMA_VERSION,
    FLAG_NAMES,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    REASON_CODES,
    SEMANTIC_MODE,
    FlagStatus,
    canonical_json,
    evaluate_diagnostic_flags,
    fingerprint,
)
from rawcandle.fundamentals.diagnostic_flags.source import DiagnosticSource


PERSISTENCE_VERSION = "DIAGNOSTIC_FLAGS_REVISED_HISTORY_V1"
HISTORY_MODE = "CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_HISTORY"
PACKAGE_TABLE = "diagnostic_flag_package"
FLAG_TABLE = "diagnostic_flag_type"
STATUS_TABLE = "diagnostic_flag_status"
REASON_TABLE = "diagnostic_flag_reason"
SOURCE_STATUS_TABLE = "diagnostic_flag_source_status"
APPLICABILITY_TABLE = "diagnostic_flag_applicability"
ENDPOINT_TABLE = "diagnostic_flag_endpoint"
EVALUATION_TABLE = "diagnostic_flag_evaluation"
NUMERIC_SLOT_COUNT = 16

EVIDENCE_FIELDS: dict[str, tuple[str, ...]] = {
    FLAG_NAMES[0]: ("current_revenue", "prior_revenue", "current_ebit", "prior_ebit", "delta_revenue", "delta_ebit", "revenue_scale", "revenue_shift_ratio", "ebit_shift_ratio", "metric_value", "threshold"),
    FLAG_NAMES[1]: ("current_common_earnings", "prior_common_earnings", "current_operating_cashflow", "prior_operating_cashflow", "delta_common_earnings", "delta_operating_cashflow", "signed_change_difference", "revenue_scale", "metric_value", "threshold"),
    FLAG_NAMES[2]: ("current_capex", "prior_capex", "current_revenue", "prior_revenue", "current_denominator", "prior_denominator", "current_capex_intensity", "prior_capex_intensity", "signed_intensity_change", "metric_value", "threshold"),
    FLAG_NAMES[3]: ("current_cash", "prior_cash", "current_total_debt", "prior_total_debt", "current_net_debt", "prior_net_debt", "signed_net_debt_change", "revenue_scale", "metric_value", "threshold"),
    FLAG_NAMES[4]: ("ebit_yield", "fcf_yield", "earnings_yield", "available_yield_count", "median_yield", "maximum_yield", "median_threshold", "maximum_threshold"),
    FLAG_NAMES[5]: ("current_revenue", "prior_revenue", "current_ebit", "prior_ebit", "current_ebit_margin", "prior_ebit_margin", "signed_margin_change", "current_trajectory", "trajectory_threshold", "margin_change_threshold"),
    FLAG_NAMES[6]: ("current_accounts_receivable", "prior_accounts_receivable", "current_inventory", "prior_inventory", "current_accounts_payable", "prior_accounts_payable", "current_deferred_revenue", "prior_deferred_revenue", "current_total_assets", "prior_total_assets", "current_onwc", "prior_onwc", "signed_delta_onwc", "asset_scale", "metric_value", "threshold"),
}
BOOLEAN_FIELDS: dict[str, tuple[str, ...]] = {
    FLAG_NAMES[0]: ("revenue_trigger", "ebit_trigger"),
    FLAG_NAMES[4]: ("median_trigger", "maximum_trigger"),
    FLAG_NAMES[5]: ("trajectory_trigger", "margin_trigger"),
}

LAYOUT_FINGERPRINT = fingerprint({
    "persistence_version": PERSISTENCE_VERSION,
    "history_mode": HISTORY_MODE,
    "tables": (PACKAGE_TABLE, FLAG_TABLE, STATUS_TABLE, REASON_TABLE, SOURCE_STATUS_TABLE, APPLICABILITY_TABLE, ENDPOINT_TABLE, EVALUATION_TABLE),
    "flags": FLAG_NAMES,
    "numeric_slots": NUMERIC_SLOT_COUNT,
    "evidence_fields": EVIDENCE_FIELDS,
    "boolean_fields": BOOLEAN_FIELDS,
    "indexes": ("package-company-sequence-desc", "package-flag-status-company", "package-fiscal-cross-section"),
})

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {PACKAGE_TABLE}(
 package_id INTEGER PRIMARY KEY,persistence_version TEXT NOT NULL,layout_fingerprint TEXT NOT NULL,
 model_version TEXT NOT NULL,model_fingerprint TEXT NOT NULL,semantic_mode TEXT NOT NULL,history_mode TEXT NOT NULL,
 evidence_schema_version TEXT NOT NULL,source_fingerprint TEXT NOT NULL,economic_result_fingerprint TEXT NOT NULL,
 physical_content_fingerprint TEXT NOT NULL,endpoint_count INTEGER NOT NULL,evaluation_count INTEGER NOT NULL,
 applied_at_utc TEXT NOT NULL,UNIQUE(model_fingerprint,history_mode));
CREATE TABLE IF NOT EXISTS {FLAG_TABLE}(flag_id INTEGER PRIMARY KEY,flag_name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS {STATUS_TABLE}(status_id INTEGER PRIMARY KEY,status_text TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS {REASON_TABLE}(reason_id INTEGER PRIMARY KEY,reason_text TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS {SOURCE_STATUS_TABLE}(source_status_id INTEGER PRIMARY KEY,source_status_text TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS {APPLICABILITY_TABLE}(applicability_id INTEGER PRIMARY KEY,applicability_text TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS {ENDPOINT_TABLE}(
 endpoint_id INTEGER PRIMARY KEY,package_id INTEGER NOT NULL REFERENCES {PACKAGE_TABLE}(package_id),company_id INTEGER NOT NULL,
 quarter_id INTEGER NOT NULL,fiscal_year INTEGER NOT NULL,fiscal_quarter INTEGER NOT NULL CHECK(fiscal_quarter BETWEEN 1 AND 4),
 fiscal_sequence INTEGER NOT NULL,period_end TEXT NOT NULL,source_available_date TEXT,ttm_available_date TEXT,
 source_status_id INTEGER REFERENCES {SOURCE_STATUS_TABLE}(source_status_id),result_fingerprint TEXT NOT NULL,
 UNIQUE(package_id,company_id,fiscal_sequence));
CREATE TABLE IF NOT EXISTS {EVALUATION_TABLE}(
 endpoint_id INTEGER NOT NULL REFERENCES {ENDPOINT_TABLE}(endpoint_id) ON DELETE CASCADE,
 flag_id INTEGER NOT NULL REFERENCES {FLAG_TABLE}(flag_id),status_id INTEGER NOT NULL REFERENCES {STATUS_TABLE}(status_id),
 reason_id INTEGER NOT NULL REFERENCES {REASON_TABLE}(reason_id),applicability_id INTEGER REFERENCES {APPLICABILITY_TABLE}(applicability_id),
 comparison_quarter_id INTEGER,effective_available_date TEXT,triggered INTEGER CHECK(triggered IN(0,1) OR triggered IS NULL),
 bool_mask INTEGER NOT NULL DEFAULT 0,
 {','.join(f'n{i:02d} REAL' for i in range(1,NUMERIC_SLOT_COUNT+1))},result_fingerprint TEXT NOT NULL,
 PRIMARY KEY(endpoint_id,flag_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_diagnostic_flag_current ON {ENDPOINT_TABLE}(package_id,company_id,fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_flag_cross_section ON {ENDPOINT_TABLE}(package_id,fiscal_year,fiscal_quarter,company_id);
CREATE INDEX IF NOT EXISTS idx_diagnostic_flag_filter ON {EVALUATION_TABLE}(flag_id,status_id,endpoint_id);
"""
SCHEMA_STATEMENTS = tuple(item.strip() for item in SCHEMA_SQL.split(";") if item.strip())


@dataclass(frozen=True)
class DiagnosticPersistencePackage:
    endpoints: tuple[dict[str, Any], ...]
    evaluations: tuple[dict[str, Any], ...]
    source_fingerprint: str
    economic_result_fingerprint: str
    package_fingerprint: str


@dataclass(frozen=True)
class ApplyReport:
    scope: str
    companies: tuple[int, ...]
    endpoint_inserted: int
    endpoint_deleted: int
    endpoint_updated: int
    endpoint_unchanged: int
    evaluation_inserted: int
    evaluation_deleted: int
    evaluation_updated: int
    evaluation_unchanged: int
    retained_other_model_endpoints: int
    persisted_content_fingerprint: str
    outcome: str


def package_id(model_fingerprint: str = MODEL_FINGERPRINT) -> int:
    return int(fingerprint({"model_fingerprint": model_fingerprint, "history_mode": HISTORY_MODE})[:15], 16)


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    return fingerprint({key: value for key, value in row.items() if key != "result_fingerprint"})


def _endpoint_id(company_id: int, fiscal_sequence: int) -> int:
    return int(fingerprint({"model": MODEL_FINGERPRINT, "company": company_id, "sequence": fiscal_sequence})[:15], 16)


def _code_id(namespace: str, value: str) -> int:
    return int(fingerprint({"namespace": namespace, "value": value})[:15], 16)


def _mask(evidence: Mapping[str, Any], flag_name: str) -> int:
    mask = 0
    for position, name in enumerate(BOOLEAN_FIELDS.get(flag_name, ())):
        if evidence.get(name) is True:
            mask |= 1 << position
    return mask


def build_persistence_package(source: DiagnosticSource) -> DiagnosticPersistencePackage:
    endpoints: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    engine_rows: list[str] = []
    pid = package_id()
    for source_row in source.rows:
        current = source_row.diagnostic_input.current
        eid = _endpoint_id(current.company_id, current.fiscal_sequence)
        endpoint = {
            "endpoint_id": eid, "package_id": pid, "company_id": current.company_id,
            "quarter_id": current.quarter_id, "fiscal_year": current.fiscal_year,
            "fiscal_quarter": int(current.fiscal_quarter[1]), "fiscal_sequence": current.fiscal_sequence,
            "period_end": current.period_end, "source_available_date": current.source_available_date,
            "ttm_available_date": current.ttm_available_date, "source_status": current.ttm_status,
        }
        endpoint["result_fingerprint"] = _row_fingerprint(endpoint)
        endpoints.append(endpoint)
        for evaluation in evaluate_diagnostic_flags(source_row.diagnostic_input):
            payload = evaluation.to_dict()
            engine_rows.append(evaluation.to_json())
            evidence = payload["evidence"]
            values = [evidence.get(name) for name in EVIDENCE_FIELDS[evaluation.flag_name]]
            row: dict[str, Any] = {
                "endpoint_id": eid, "flag_name": evaluation.flag_name,
                "status": evaluation.status.value, "reason": evaluation.reason_code,
                "applicability": evidence.get("applicability_classification"),
                "comparison_quarter_id": evaluation.comparison_quarter_id,
                "effective_available_date": evaluation.effective_available_date,
                "triggered": None if evaluation.triggered is None else int(evaluation.triggered),
                "bool_mask": _mask(evidence, evaluation.flag_name),
            }
            row.update({f"n{i:02d}": values[i - 1] if i <= len(values) else None for i in range(1, NUMERIC_SLOT_COUNT + 1)})
            row["result_fingerprint"] = _row_fingerprint(row)
            evaluations.append(row)
    endpoints.sort(key=lambda row: (row["company_id"], row["fiscal_sequence"]))
    flag_order = {name: index for index, name in enumerate(FLAG_NAMES)}
    evaluations.sort(key=lambda row: (row["endpoint_id"], flag_order[row["flag_name"]]))
    economic = fingerprint(engine_rows)
    package = rebuild_package(endpoints, evaluations, source_fingerprint=source.source_fingerprint, economic_result_fingerprint=economic)
    return package


def rebuild_package(endpoints: Sequence[Mapping[str, Any]], evaluations: Sequence[Mapping[str, Any]], *,
                    source_fingerprint: str, economic_result_fingerprint: str) -> DiagnosticPersistencePackage:
    endpoints_tuple=tuple(dict(row) for row in endpoints); evaluations_tuple=tuple(dict(row) for row in evaluations)
    package_fp = fingerprint({"model": MODEL_FINGERPRINT, "source": source_fingerprint, "result": economic_result_fingerprint,
                              "endpoints": [r["result_fingerprint"] for r in endpoints_tuple],
                              "evaluations": [r["result_fingerprint"] for r in evaluations_tuple]})
    package = DiagnosticPersistencePackage(endpoints_tuple,evaluations_tuple,source_fingerprint,economic_result_fingerprint,package_fp)
    validate_package(package)
    return package


def validate_package(package: DiagnosticPersistencePackage) -> None:
    if len(package.evaluations) != len(package.endpoints) * len(FLAG_NAMES):
        raise ValueError("DIAGNOSTIC_EXACTLY_SEVEN_EVALUATIONS_REQUIRED")
    endpoint_ids = {row["endpoint_id"] for row in package.endpoints}
    if len(endpoint_ids) != len(package.endpoints):
        raise ValueError("DIAGNOSTIC_DUPLICATE_ENDPOINT")
    grouped: dict[int, set[str]] = {eid: set() for eid in endpoint_ids}
    for row in package.evaluations:
        if row["endpoint_id"] not in grouped or row["flag_name"] in grouped[row["endpoint_id"]]:
            raise ValueError("DIAGNOSTIC_EVALUATION_IDENTITY_INVALID")
        grouped[row["endpoint_id"]].add(row["flag_name"])
        if row["status"] not in {status.value for status in FlagStatus} or row["reason"] not in REASON_CODES:
            raise ValueError("DIAGNOSTIC_STATUS_OR_REASON_INVALID")
        expected = None if row["status"] in {FlagStatus.NOT_READY.value, FlagStatus.NOT_APPLICABLE.value} else int(row["status"] == FlagStatus.FLAGGED.value)
        if row["triggered"] != expected:
            raise ValueError("DIAGNOSTIC_TRIGGER_STATUS_MISMATCH")
        if row["result_fingerprint"] != _row_fingerprint(row):
            raise ValueError("DIAGNOSTIC_EVALUATION_FINGERPRINT_INVALID")
    if any(flags != set(FLAG_NAMES) for flags in grouped.values()):
        raise ValueError("DIAGNOSTIC_FLAG_SET_INVALID")
    if any(row["result_fingerprint"] != _row_fingerprint(row) for row in package.endpoints):
        raise ValueError("DIAGNOSTIC_ENDPOINT_FINGERPRINT_INVALID")
    expected=fingerprint({"model":MODEL_FINGERPRINT,"source":package.source_fingerprint,"result":package.economic_result_fingerprint,
                          "endpoints":[r["result_fingerprint"] for r in package.endpoints],"evaluations":[r["result_fingerprint"] for r in package.evaluations]})
    if package.package_fingerprint != expected:
        raise ValueError("DIAGNOSTIC_PACKAGE_FINGERPRINT_INVALID")


def ensure_schema(conn: sqlite3.Connection, *, inject_failure_at: str | None = None) -> None:
    if conn.in_transaction:
        raise RuntimeError("DIAGNOSTIC_SCHEMA_REQUIRES_CLEAN_TRANSACTION")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for index, statement in enumerate(SCHEMA_STATEMENTS):
            conn.execute(statement)
            if inject_failure_at == "schema_creation" and index == 1:
                raise RuntimeError("INJECTED_DIAGNOSTIC_SCHEMA_CREATION_FAILURE")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _codebooks(package: DiagnosticPersistencePackage) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str | None, int], dict[str | None, int]]:
    flags = {name: index for index, name in enumerate(FLAG_NAMES, 1)}
    statuses = {status.value: index for index, status in enumerate(FlagStatus, 1)}
    reasons = {reason: index for index, reason in enumerate(REASON_CODES, 1)}
    source_values = sorted({row["source_status"] for row in package.endpoints if row["source_status"] is not None})
    applicability_values = sorted({row["applicability"] for row in package.evaluations if row["applicability"] is not None})
    return flags, statuses, reasons, {value: _code_id("source_status", value) for value in source_values}, {value: _code_id("applicability", value) for value in applicability_values}


def _normalized(package: DiagnosticPersistencePackage) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], tuple[dict[str, int], ...]]:
    flags, statuses, reasons, sources, applicability = _codebooks(package)
    endpoints = []
    for raw in package.endpoints:
        row = {key: value for key, value in raw.items() if key != "source_status"}
        row["source_status_id"] = sources.get(raw["source_status"])
        row["result_fingerprint"] = _row_fingerprint(row)
        endpoints.append(row)
    evaluations = []
    for raw in package.evaluations:
        row = {key: value for key, value in raw.items() if key not in {"flag_name", "status", "reason", "applicability"}}
        row.update(flag_id=flags[raw["flag_name"]], status_id=statuses[raw["status"]], reason_id=reasons[raw["reason"]], applicability_id=applicability.get(raw["applicability"]))
        row["result_fingerprint"] = _row_fingerprint(row)
        evaluations.append(row)
    books = tuple({"table": table, "id": ident, "text": str(text)} for table, mapping in ((FLAG_TABLE, flags), (STATUS_TABLE, statuses), (REASON_TABLE, reasons), (SOURCE_STATUS_TABLE, sources), (APPLICABILITY_TABLE, applicability)) for text, ident in mapping.items())
    return tuple(endpoints), tuple(evaluations), books


def _insert(conn: sqlite3.Connection, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    columns = tuple(rows[0])
    conn.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", ([row[c] for c in columns] for row in rows))


def content_fingerprint(conn: sqlite3.Connection, pid: int) -> str:
    endpoints = [row[0] for row in conn.execute(f"SELECT result_fingerprint FROM {ENDPOINT_TABLE} WHERE package_id=? ORDER BY company_id,fiscal_sequence", (pid,))]
    evaluations = [row[0] for row in conn.execute(f"SELECT v.result_fingerprint FROM {EVALUATION_TABLE} v JOIN {ENDPOINT_TABLE} e USING(endpoint_id) WHERE e.package_id=? ORDER BY e.company_id,e.fiscal_sequence,v.flag_id", (pid,))]
    return fingerprint([endpoints, evaluations])


def package_content_fingerprint(package: DiagnosticPersistencePackage) -> str:
    endpoints, evaluations, _ = _normalized(package)
    return fingerprint([
        [row["result_fingerprint"] for row in endpoints],
        [row["result_fingerprint"] for row in evaluations],
    ])


def _logical(conn: sqlite3.Connection, pid: int, companies: Sequence[int]) -> tuple[dict[Any, str], dict[Any, str]]:
    where = "package_id=?"; params: list[Any] = [pid]
    if companies:
        where += f" AND company_id IN ({','.join('?' for _ in companies)})"; params.extend(companies)
    endpoints = {(row[0], row[1]): row[2] for row in conn.execute(f"SELECT company_id,fiscal_sequence,result_fingerprint FROM {ENDPOINT_TABLE} WHERE {where}", params)}
    evaluations = {(row[0], row[1]): row[2] for row in conn.execute(f"SELECT v.endpoint_id,v.flag_id,v.result_fingerprint FROM {EVALUATION_TABLE} v JOIN {ENDPOINT_TABLE} e USING(endpoint_id) WHERE e.{where}", params)}
    return endpoints, evaluations


def _counts(old: Mapping[Any, str], new: Mapping[Any, str]) -> tuple[int, int, int, int]:
    return len(set(new)-set(old)), len(set(old)-set(new)), sum(old[k] != new[k] for k in set(old)&set(new)), sum(old[k] == new[k] for k in set(old)&set(new))


def apply_package(conn: sqlite3.Connection, package: DiagnosticPersistencePackage, *, applied_at_utc: str,
                  company_ids: Sequence[int] = (), inject_failure_at: str | None = None) -> ApplyReport:
    validate_package(package)
    if conn.in_transaction:
        raise RuntimeError("DIAGNOSTIC_APPLY_REQUIRES_CLEAN_TRANSACTION")
    selected = tuple(sorted(set(map(int, company_ids))))
    scope = "COMPANY" if selected else "FULL"; pid = package_id()
    endpoints, evaluations, books = _normalized(package)
    if selected:
        endpoints = tuple(row for row in endpoints if row["company_id"] in selected)
        ids = {row["endpoint_id"] for row in endpoints}; evaluations = tuple(row for row in evaluations if row["endpoint_id"] in ids)
    old_e, old_v = _logical(conn, pid, selected)
    new_e = {(r["company_id"], r["fiscal_sequence"]): r["result_fingerprint"] for r in endpoints}
    new_v = {(r["endpoint_id"], r["flag_id"]): r["result_fingerprint"] for r in evaluations}
    meta = conn.execute(f"SELECT source_fingerprint,economic_result_fingerprint,layout_fingerprint FROM {PACKAGE_TABLE} WHERE package_id=?", (pid,)).fetchone()
    if old_e == new_e and old_v == new_v and meta is not None and tuple(meta) == (package.source_fingerprint, package.economic_result_fingerprint, LAYOUT_FINGERPRINT):
        retained = conn.execute(f"SELECT COUNT(*) FROM {ENDPOINT_TABLE} e JOIN {PACKAGE_TABLE} p USING(package_id) WHERE p.model_fingerprint<>?", (MODEL_FINGERPRINT,)).fetchone()[0]
        return ApplyReport(scope, selected, 0,0,0,len(old_e),0,0,0,len(old_v),retained,content_fingerprint(conn,pid),"NO_CHANGE")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for book in books:
            id_col = {FLAG_TABLE:"flag_id",STATUS_TABLE:"status_id",REASON_TABLE:"reason_id",SOURCE_STATUS_TABLE:"source_status_id",APPLICABILITY_TABLE:"applicability_id"}[book["table"]]
            text_col = {FLAG_TABLE:"flag_name",STATUS_TABLE:"status_text",REASON_TABLE:"reason_text",SOURCE_STATUS_TABLE:"source_status_text",APPLICABILITY_TABLE:"applicability_text"}[book["table"]]
            conn.execute(f"INSERT INTO {book['table']}({id_col},{text_col}) VALUES(?,?) ON CONFLICT({text_col}) DO NOTHING", (book["id"],book["text"]))
        if inject_failure_at == "codebooks": raise RuntimeError("INJECTED_DIAGNOSTIC_CODEBOOK_FAILURE")
        where="package_id=?"; params:list[Any]=[pid]
        if selected: where += f" AND company_id IN ({','.join('?' for _ in selected)})"; params.extend(selected)
        conn.execute(f"DELETE FROM {ENDPOINT_TABLE} WHERE {where}", params)
        if inject_failure_at == "company_delete": raise RuntimeError("INJECTED_DIAGNOSTIC_DELETE_FAILURE")
        values=(pid,PERSISTENCE_VERSION,LAYOUT_FINGERPRINT,MODEL_VERSION,MODEL_FINGERPRINT,SEMANTIC_MODE,HISTORY_MODE,EVIDENCE_SCHEMA_VERSION,package.source_fingerprint,package.economic_result_fingerprint,"PENDING",0,0,applied_at_utc)
        conn.execute(f"INSERT INTO {PACKAGE_TABLE} VALUES({','.join('?' for _ in values)}) ON CONFLICT(package_id) DO UPDATE SET source_fingerprint=excluded.source_fingerprint,economic_result_fingerprint=excluded.economic_result_fingerprint,applied_at_utc=excluded.applied_at_utc",values)
        if inject_failure_at == "package": raise RuntimeError("INJECTED_DIAGNOSTIC_PACKAGE_FAILURE")
        if inject_failure_at == "endpoint_partial":
            _insert(conn,ENDPOINT_TABLE,endpoints[:max(1,len(endpoints)//2)]); raise RuntimeError("INJECTED_DIAGNOSTIC_ENDPOINT_PARTIAL_FAILURE")
        _insert(conn, ENDPOINT_TABLE, endpoints)
        if inject_failure_at == "endpoints": raise RuntimeError("INJECTED_DIAGNOSTIC_ENDPOINT_FAILURE")
        if inject_failure_at == "evaluation_partial":
            _insert(conn,EVALUATION_TABLE,evaluations[:max(1,len(evaluations)//2)]); raise RuntimeError("INJECTED_DIAGNOSTIC_EVALUATION_PARTIAL_FAILURE")
        _insert(conn, EVALUATION_TABLE, evaluations)
        if inject_failure_at == "evaluations": raise RuntimeError("INJECTED_DIAGNOSTIC_EVALUATION_FAILURE")
        physical=content_fingerprint(conn,pid)
        ec=conn.execute(f"SELECT COUNT(*) FROM {ENDPOINT_TABLE} WHERE package_id=?",(pid,)).fetchone()[0]
        vc=conn.execute(f"SELECT COUNT(*) FROM {EVALUATION_TABLE} v JOIN {ENDPOINT_TABLE} e USING(endpoint_id) WHERE e.package_id=?",(pid,)).fetchone()[0]
        conn.execute(f"UPDATE {PACKAGE_TABLE} SET physical_content_fingerprint=?,endpoint_count=?,evaluation_count=? WHERE package_id=?",(physical,ec,vc,pid))
        if inject_failure_at == "final_verification": raise RuntimeError("INJECTED_DIAGNOSTIC_FINAL_VERIFICATION_FAILURE")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    ei,ed,eu,en=_counts(old_e,new_e); vi,vd,vu,vn=_counts(old_v,new_v)
    retained=conn.execute(f"SELECT COUNT(*) FROM {ENDPOINT_TABLE} e JOIN {PACKAGE_TABLE} p USING(package_id) WHERE p.model_fingerprint<>?",(MODEL_FINGERPRINT,)).fetchone()[0]
    return ApplyReport(scope,selected,ei,ed,eu,en,vi,vd,vu,vn,retained,physical,"APPLIED")


def quick_check(conn: sqlite3.Connection, *, model_fingerprint: str = MODEL_FINGERPRINT,
                authoritative_package: DiagnosticPersistencePackage | None = None) -> dict[str, Any]:
    conn.row_factory=sqlite3.Row; details=[]
    if model_fingerprint != MODEL_FINGERPRINT: return {"ok":False,"details":["MODEL_FINGERPRINT_REJECTED"]}
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok": details.append("SQLITE_QUICK_CHECK_FAILED")
    if conn.execute("PRAGMA foreign_key_check").fetchall(): details.append("FOREIGN_KEY_VIOLATIONS")
    meta=conn.execute(f"SELECT * FROM {PACKAGE_TABLE} WHERE model_fingerprint=? AND history_mode=?",(model_fingerprint,HISTORY_MODE)).fetchone()
    if meta is None: details.append("PACKAGE_MISSING"); return {"ok":False,"details":details}
    pid=int(meta["package_id"])
    if meta["layout_fingerprint"] != LAYOUT_FINGERPRINT: details.append("LAYOUT_FINGERPRINT_MISMATCH")
    ec=conn.execute(f"SELECT COUNT(*) FROM {ENDPOINT_TABLE} WHERE package_id=?",(pid,)).fetchone()[0]
    vc=conn.execute(f"SELECT COUNT(*) FROM {EVALUATION_TABLE} v JOIN {ENDPOINT_TABLE} e USING(endpoint_id) WHERE e.package_id=?",(pid,)).fetchone()[0]
    if ec != meta["endpoint_count"] or vc != meta["evaluation_count"]: details.append("COUNT_MISMATCH")
    if vc != ec*7: details.append("SEVEN_FLAG_CONTRACT_FAILED")
    physical=content_fingerprint(conn,pid)
    if physical != meta["physical_content_fingerprint"]: details.append("CONTENT_FINGERPRINT_MISMATCH")
    if authoritative_package is not None:
        expected_e,expected_v,_=_normalized(authoritative_package); actual_e,actual_v=_logical(conn,pid,())
        if actual_e != {(r["company_id"],r["fiscal_sequence"]):r["result_fingerprint"] for r in expected_e} or actual_v != {(r["endpoint_id"],r["flag_id"]):r["result_fingerprint"] for r in expected_v}: details.append("AUTHORITATIVE_REPLAY_MISMATCH")
    return {"ok":not details,"details":details,"endpoint_count":ec,"evaluation_count":vc,"content_fingerprint":physical,"authoritative_replay":authoritative_package is not None}


def evidence_from_row(flag_name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    evidence={name:row[f"n{i:02d}"] for i,name in enumerate(EVIDENCE_FIELDS[flag_name],1)}
    for position,name in enumerate(BOOLEAN_FIELDS.get(flag_name,())): evidence[name]=bool(row["bool_mask"] & (1<<position))
    return evidence
