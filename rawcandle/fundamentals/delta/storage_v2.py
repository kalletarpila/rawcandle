from __future__ import annotations

import math
import sqlite3
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.delta.engine import (
    COMPONENT_MAXIMA,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    RECONCILIATION_TOLERANCE,
    SEMANTIC_MODE,
    DeltaStatus,
    fingerprint,
)


def _persistence() -> Any:
    from rawcandle.fundamentals.delta import persistence

    return persistence


def package_id() -> int:
    p = _persistence()
    return int(fingerprint({"model_fingerprint": MODEL_FINGERPRINT, "history_mode": p.HISTORY_MODE})[:15], 16)


def ensure_schema(conn: sqlite3.Connection, *, applied_at_utc: str) -> None:
    del applied_at_utc
    p = _persistence()
    retired = {
        "fundamental_delta_revised_meta",
        "fundamental_delta_revised_result",
        "fundamental_delta_revised_component",
        p.LIFECYCLE_TABLE,
        p.VALUATION_TABLE,
    }
    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    if retired & existing:
        raise RuntimeError("NEVER_DEPLOYED_DELTA_V1_LAYOUT_REQUIRES_DISPOSABLE_DATABASE_RECREATION")
    for statement in p.SCHEMA_STATEMENTS:
        conn.execute(statement)


def _codebooks(package: Any) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    statuses = {status.value: index for index, status in enumerate(DeltaStatus, 1)}
    reasons = sorted({
        str(row[f"{prefix}_reason"])
        for rows in (package.total_rows, package.component_rows)
        for row in rows
        for prefix in ("qoq", "two_quarter", "yoy")
    })
    components = {name: index for index, name in enumerate(COMPONENT_MAXIMA, 1)}
    return statuses, {reason: index for index, reason in enumerate(reasons, 1)}, components


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    return fingerprint({key: value for key, value in row.items() if key != "result_fingerprint"})


def normalized_rows(package: Any) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], dict[str, int], dict[str, int], dict[str, int]]:
    statuses, reasons, component_ids = _codebooks(package)
    totals: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    for source in package.total_rows:
        row = {
            "endpoint_id": int(source["fundamental_delta_result_id"]),
            "package_id": package_id(),
            "company_id": int(source["company_id"]),
            "fiscal_year": int(source["fiscal_year"]),
            "fiscal_quarter": int(str(source["fiscal_quarter"])[1]),
            "fiscal_sequence": int(source["fiscal_sequence"]),
            "current_available_date": str(source["current_available_date"]),
            "current_score_result_id": int(source["current_score_result_id"]),
            "reconciliation_status": int(source["reconciliation_status"] == "RECONCILED"),
            "maximum_reconciliation_error": source["maximum_reconciliation_error"],
            "engine_result_fingerprint": str(source["engine_result_fingerprint"]),
        }
        for prefix in ("qoq", "two_quarter", "yoy"):
            row.update({
                f"{prefix}_prior_score_result_id": source[f"{prefix}_prior_score_result_id"],
                f"{prefix}_delta": source[f"{prefix}_delta"],
                f"{prefix}_status_id": statuses[str(source[f"{prefix}_status"])],
                f"{prefix}_reason_id": reasons[str(source[f"{prefix}_reason"])],
            })
        row["result_fingerprint"] = _row_fingerprint(row)
        totals.append(row)
    for source in package.component_rows:
        row = {
            "endpoint_id": int(source["fundamental_delta_result_id"]),
            "component_id": component_ids[str(source["component_name"])],
            "current_points": source["current_points"],
        }
        for prefix in ("qoq", "two_quarter", "yoy"):
            row.update({
                f"{prefix}_prior_points": source[f"{prefix}_prior_points"],
                f"{prefix}_delta": source[f"{prefix}_delta"],
                f"{prefix}_status_id": statuses[str(source[f"{prefix}_status"])],
                f"{prefix}_reason_id": reasons[str(source[f"{prefix}_reason"])],
            })
        row["result_fingerprint"] = _row_fingerprint(row)
        components.append(row)
    return tuple(totals), tuple(components), statuses, reasons, component_ids


def _insert_rows(conn: sqlite3.Connection, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    columns = tuple(rows[0])
    conn.executemany(
        f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        ([row[column] for column in columns] for row in rows),
    )


def content_fingerprint(conn: sqlite3.Connection, target_package_id: int) -> str:
    p = _persistence()
    totals = [row[0] for row in conn.execute(
        f"SELECT result_fingerprint FROM {p.TOTAL_TABLE} WHERE package_id=? ORDER BY company_id,fiscal_sequence",
        (target_package_id,),
    )]
    components = [row[0] for row in conn.execute(
        f"SELECT c.result_fingerprint FROM {p.COMPONENT_TABLE} c JOIN {p.TOTAL_TABLE} r USING(endpoint_id) "
        "WHERE r.package_id=? ORDER BY r.company_id,r.fiscal_sequence,c.component_id",
        (target_package_id,),
    )]
    return fingerprint([totals, components])


def _logical_rows(conn: sqlite3.Connection, target_package_id: int, companies: Sequence[int]) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str]]:
    p = _persistence()
    clause = "r.package_id=?"
    params: list[Any] = [target_package_id]
    if companies:
        clause += f" AND r.company_id IN ({','.join('?' for _ in companies)})"
        params.extend(companies)
    totals = {(int(row[0]), int(row[1])): str(row[2]) for row in conn.execute(
        f"SELECT r.company_id,r.fiscal_sequence,r.result_fingerprint FROM {p.TOTAL_TABLE} r WHERE {clause}", params
    )}
    components = {(int(row[0]), int(row[1])): str(row[2]) for row in conn.execute(
        f"SELECT c.endpoint_id,c.component_id,c.result_fingerprint FROM {p.COMPONENT_TABLE} c "
        f"JOIN {p.TOTAL_TABLE} r USING(endpoint_id) WHERE {clause}", params
    )}
    return totals, components


def _metrics(old: Mapping[Any, str], new: Mapping[Any, str]) -> tuple[int, int, int, int]:
    return (
        len(set(new) - set(old)),
        len(set(old) - set(new)),
        sum(old[key] != new[key] for key in set(old) & set(new)),
        sum(old[key] == new[key] for key in set(old) & set(new)),
    )


def apply_package(
    conn: sqlite3.Connection,
    package: Any,
    *,
    applied_at_utc: str,
    company_ids: Sequence[int] = (),
    inject_failure_at: str | None = None,
) -> Any:
    p = _persistence()
    p.validate_package(package)
    if conn.in_transaction:
        raise RuntimeError("DELTA_APPLY_REQUIRES_CLEAN_TRANSACTION")
    if conn.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (p.PACKAGE_TABLE,)).fetchone() is None:
        raise RuntimeError("DELTA_SCHEMA_NOT_MIGRATED")
    selected = tuple(sorted(set(map(int, company_ids))))
    scope = "COMPANY" if selected else "FULL"
    totals, components, statuses, reasons, component_ids = normalized_rows(package)
    if selected:
        endpoint_ids = {row["endpoint_id"] for row in totals if row["company_id"] in selected}
        totals = tuple(row for row in totals if row["company_id"] in selected)
        components = tuple(row for row in components if row["endpoint_id"] in endpoint_ids)
    target_package_id = package_id()
    old_total, old_component = _logical_rows(conn, target_package_id, selected)
    new_total = {(row["company_id"], row["fiscal_sequence"]): row["result_fingerprint"] for row in totals}
    new_component = {(row["endpoint_id"], row["component_id"]): row["result_fingerprint"] for row in components}
    metadata=conn.execute(f"SELECT fundamental_source_fingerprint,fundamental_result_fingerprint,lifecycle_source_fingerprint,lifecycle_result_fingerprint,valuation_source_fingerprint,valuation_result_fingerprint,economic_package_fingerprint,layout_fingerprint FROM {p.PACKAGE_TABLE} WHERE package_id=?",(target_package_id,)).fetchone()
    expected_metadata=(package.fundamental_source_fingerprint,package.fundamental_result_fingerprint,package.lifecycle_source_fingerprint,package.lifecycle_result_fingerprint,package.valuation_source_fingerprint,package.valuation_result_fingerprint,package.package_fingerprint,p.LAYOUT_FINGERPRINT)
    metadata_matches=metadata is not None and tuple(metadata)==expected_metadata
    if old_total == new_total and old_component == new_component and metadata_matches:
        physical = content_fingerprint(conn, target_package_id)
        retained=int(conn.execute(f"SELECT COUNT(*) FROM {p.TOTAL_TABLE} r JOIN {p.PACKAGE_TABLE} m USING(package_id) WHERE m.model_fingerprint<>?",(MODEL_FINGERPRINT,)).fetchone()[0])
        return p.ApplyReport(scope,selected,0,0,0,len(old_total),0,0,0,len(old_component),0,0,0,0,0,0,0,0,retained,physical,"NO_CHANGE")

    conn.execute("BEGIN IMMEDIATE")
    try:
        for text, status_id in statuses.items():
            conn.execute(f"INSERT INTO {p.STATUS_TABLE}(status_id,status_text) VALUES(?,?) ON CONFLICT(status_text) DO NOTHING", (status_id,text))
        for text, reason_id in reasons.items():
            conn.execute(f"INSERT INTO {p.REASON_TABLE}(reason_id,reason_text) VALUES(?,?) ON CONFLICT(reason_text) DO NOTHING", (reason_id,text))
        for name, component_id in component_ids.items():
            conn.execute(f"INSERT INTO {p.COMPONENT_TYPE_TABLE}(component_id,component_name,maximum_points) VALUES(?,?,?) ON CONFLICT(component_name) DO UPDATE SET maximum_points=excluded.maximum_points", (component_id,name,COMPONENT_MAXIMA[name]))
        where = "package_id=?"
        params: list[Any] = [target_package_id]
        if selected:
            where += f" AND company_id IN ({','.join('?' for _ in selected)})"
            params.extend(selected)
        conn.execute(f"DELETE FROM {p.TOTAL_TABLE} WHERE {where}", params)
        if inject_failure_at == "after_delete":
            raise RuntimeError("INJECTED_DELTA_AFTER_DELETE_FAILURE")
        score_fp = str(package.total_rows[0]["score_model_fingerprint"]) if package.total_rows else ""
        values = (
            target_package_id,p.PERSISTENCE_VERSION,p.LAYOUT_FINGERPRINT,MODEL_VERSION,MODEL_FINGERPRINT,
            SEMANTIC_MODE,p.HISTORY_MODE,score_fp,package.fundamental_source_fingerprint,
            package.fundamental_result_fingerprint,p.LIFECYCLE_CONTEXT_FINGERPRINT,
            package.lifecycle_source_fingerprint,package.lifecycle_result_fingerprint,
            p.VALUATION_DIAGNOSTIC_FINGERPRINT,package.valuation_source_fingerprint,
            package.valuation_result_fingerprint,package.package_fingerprint,"PENDING",0,0,applied_at_utc,
        )
        conn.execute(f"""INSERT INTO {p.PACKAGE_TABLE} VALUES({','.join('?' for _ in values)})
            ON CONFLICT(package_id) DO UPDATE SET
            persistence_version=excluded.persistence_version,layout_fingerprint=excluded.layout_fingerprint,
            fundamental_source_fingerprint=excluded.fundamental_source_fingerprint,
            fundamental_result_fingerprint=excluded.fundamental_result_fingerprint,
            lifecycle_source_fingerprint=excluded.lifecycle_source_fingerprint,
            lifecycle_result_fingerprint=excluded.lifecycle_result_fingerprint,
            valuation_source_fingerprint=excluded.valuation_source_fingerprint,
            valuation_result_fingerprint=excluded.valuation_result_fingerprint,
            economic_package_fingerprint=excluded.economic_package_fingerprint,
            applied_at_utc=excluded.applied_at_utc""", values)
        _insert_rows(conn, p.TOTAL_TABLE, totals)
        if inject_failure_at in {"after_total", "after_lifecycle"}:
            raise RuntimeError("INJECTED_DELTA_TOTAL_FAILURE")
        _insert_rows(conn, p.COMPONENT_TABLE, components)
        if inject_failure_at in {"after_component", "after_valuation"}:
            raise RuntimeError("INJECTED_DELTA_COMPONENT_FAILURE")
        physical = content_fingerprint(conn, target_package_id)
        total_count = int(conn.execute(f"SELECT COUNT(*) FROM {p.TOTAL_TABLE} WHERE package_id=?", (target_package_id,)).fetchone()[0])
        component_count = int(conn.execute(f"SELECT COUNT(*) FROM {p.COMPONENT_TABLE} c JOIN {p.TOTAL_TABLE} r USING(endpoint_id) WHERE r.package_id=?", (target_package_id,)).fetchone()[0])
        conn.execute(f"UPDATE {p.PACKAGE_TABLE} SET physical_content_fingerprint=?,total_row_count=?,component_row_count=?,applied_at_utc=? WHERE package_id=?", (physical,total_count,component_count,applied_at_utc,target_package_id))
        if inject_failure_at == "metadata":
            raise RuntimeError("INJECTED_DELTA_METADATA_FAILURE")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    ti,td,tu,tn = _metrics(old_total,new_total)
    ci,cd,cu,cn = _metrics(old_component,new_component)
    retained=int(conn.execute(f"SELECT COUNT(*) FROM {p.TOTAL_TABLE} r JOIN {p.PACKAGE_TABLE} m USING(package_id) WHERE m.model_fingerprint<>?",(MODEL_FINGERPRINT,)).fetchone()[0])
    return p.ApplyReport(scope,selected,ti,td,tu,tn,ci,cd,cu,cn,0,0,0,0,0,0,0,0,retained,physical,"APPLIED")


def quick_check(conn: sqlite3.Connection, *, model_fingerprint: str, authoritative_package: Any | None = None) -> dict[str, Any]:
    p = _persistence()
    conn.row_factory = sqlite3.Row
    if model_fingerprint != MODEL_FINGERPRINT:
        return {"ok": False, "details": ["MODEL_FINGERPRINT_REJECTED"]}
    details: list[str] = []
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        details.append("SQLITE_QUICK_CHECK_FAILED")
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        details.append("FOREIGN_KEY_VIOLATIONS")
    retired = {p.LIFECYCLE_TABLE,p.VALUATION_TABLE,"fundamental_delta_revised_result","fundamental_delta_revised_component","fundamental_delta_revised_meta"}
    present = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    if retired & present:
        details.append("RETIRED_V1_OBJECT_PRESENT")
    meta = conn.execute(f"SELECT * FROM {p.PACKAGE_TABLE} WHERE model_fingerprint=? AND history_mode=?", (model_fingerprint,p.HISTORY_MODE)).fetchone()
    target_package_id = package_id()
    if meta is None:
        details.append("PACKAGE_MISSING")
    else:
        target_package_id = int(meta["package_id"])
        if meta["persistence_version"] != p.PERSISTENCE_VERSION:
            details.append("PERSISTENCE_VERSION_MISMATCH")
        if meta["layout_fingerprint"] != p.LAYOUT_FINGERPRINT:
            details.append("LAYOUT_FINGERPRINT_MISMATCH")
        total_count = int(conn.execute(f"SELECT COUNT(*) FROM {p.TOTAL_TABLE} WHERE package_id=?", (target_package_id,)).fetchone()[0])
        component_count = int(conn.execute(f"SELECT COUNT(*) FROM {p.COMPONENT_TABLE} c JOIN {p.TOTAL_TABLE} r USING(endpoint_id) WHERE r.package_id=?", (target_package_id,)).fetchone()[0])
        if total_count != int(meta["total_row_count"]):
            details.append("TOTAL_COUNT_MISMATCH")
        if component_count != int(meta["component_row_count"]):
            details.append("COMPONENT_COUNT_MISMATCH")
        if content_fingerprint(conn,target_package_id) != meta["physical_content_fingerprint"]:
            details.append("CONTENT_FINGERPRINT_MISMATCH")
    bad_seven = int(conn.execute(f"SELECT COUNT(*) FROM (SELECT r.endpoint_id,COUNT(c.component_id) n FROM {p.TOTAL_TABLE} r LEFT JOIN {p.COMPONENT_TABLE} c USING(endpoint_id) WHERE r.package_id=? GROUP BY r.endpoint_id HAVING n<>7)", (target_package_id,)).fetchone()[0])
    if bad_seven:
        details.append("SEVEN_COMPONENT_CONTRACT_FAILED")
    for table in (p.TOTAL_TABLE,p.COMPONENT_TABLE):
        rows=conn.execute(f"SELECT * FROM {table}")
        for raw in rows:
            row=dict(raw)
            if row["result_fingerprint"] != _row_fingerprint(row):
                details.append(f"ROW_FINGERPRINT_MISMATCH:{table}")
                break
    maxima={row[0]:float(row[1]) for row in conn.execute(f"SELECT component_name,maximum_points FROM {p.COMPONENT_TYPE_TABLE}")}
    if maxima != {name:float(value) for name,value in COMPONENT_MAXIMA.items()}:
        details.append("COMPONENT_CODEBOOK_MISMATCH")
    ready = conn.execute(f"SELECT status_id FROM {p.STATUS_TABLE} WHERE status_text=?", (DeltaStatus.READY.value,)).fetchone()
    if ready is None:
        details.append("READY_CODE_MISSING")
    else:
        for prefix in ("qoq", "two_quarter", "yoy"):
            bad = int(conn.execute(f"SELECT COUNT(*) FROM {p.TOTAL_TABLE} WHERE package_id=? AND (({prefix}_status_id=? AND ({prefix}_delta IS NULL OR {prefix}_prior_score_result_id IS NULL OR ABS({prefix}_delta)>1.7976931348623157e308)) OR ({prefix}_status_id<>? AND {prefix}_delta IS NOT NULL))", (target_package_id,ready[0],ready[0])).fetchone()[0])
            if bad:
                details.append(f"{prefix.upper()}_READINESS_INVALID")
            mismatch = conn.execute(f"SELECT 1 FROM {p.TOTAL_TABLE} r JOIN (SELECT endpoint_id,SUM({prefix}_delta) value FROM {p.COMPONENT_TABLE} WHERE {prefix}_status_id=? GROUP BY endpoint_id) c USING(endpoint_id) WHERE r.package_id=? AND r.{prefix}_status_id=? AND ABS(r.{prefix}_delta-c.value)>? LIMIT 1", (ready[0],target_package_id,ready[0],RECONCILIATION_TOLERANCE)).fetchone()
            if mismatch:
                details.append(f"{prefix.upper()}_RECONCILIATION_FAILED")
            lag = {"qoq": 1, "two_quarter": 2, "yoy": 4}[prefix]
            invalid_lag = conn.execute(
                f"""SELECT 1
                      FROM {p.TOTAL_TABLE} r
                      LEFT JOIN {p.TOTAL_TABLE} prior
                        ON prior.package_id=r.package_id
                       AND prior.company_id=r.company_id
                       AND prior.current_score_result_id=r.{prefix}_prior_score_result_id
                     WHERE r.package_id=? AND r.{prefix}_status_id=?
                       AND (prior.endpoint_id IS NULL OR prior.fiscal_sequence<>r.fiscal_sequence-?)
                     LIMIT 1""",
                (target_package_id, ready[0], lag),
            ).fetchone()
            if invalid_lag:
                details.append(f"{prefix.upper()}_ENDPOINT_LAG_INVALID")
            invalid_component = conn.execute(
                f"""SELECT 1 FROM {p.COMPONENT_TABLE} c
                      JOIN {p.TOTAL_TABLE} r USING(endpoint_id)
                     WHERE r.package_id=? AND (
                       (c.{prefix}_status_id=? AND (
                         c.current_points IS NULL OR c.{prefix}_prior_points IS NULL
                         OR c.{prefix}_delta IS NULL
                         OR ABS(c.current_points)>1.7976931348623157e308
                         OR ABS(c.{prefix}_prior_points)>1.7976931348623157e308
                         OR ABS(c.{prefix}_delta)>1.7976931348623157e308
                       )) OR (c.{prefix}_status_id<>? AND c.{prefix}_delta IS NOT NULL)
                     ) LIMIT 1""",
                (target_package_id, ready[0], ready[0]),
            ).fetchone()
            if invalid_component:
                details.append(f"{prefix.upper()}_COMPONENT_VALUE_CONTRACT_INVALID")
    if authoritative_package is not None:
        p.validate_package(authoritative_package)
        expected_totals,expected_components,_,_,_=normalized_rows(authoritative_package)
        actual_total,actual_component=_logical_rows(conn,target_package_id,())
        wanted_total={(row["company_id"],row["fiscal_sequence"]):row["result_fingerprint"] for row in expected_totals}
        wanted_component={(row["endpoint_id"],row["component_id"]):row["result_fingerprint"] for row in expected_components}
        if actual_total != wanted_total or actual_component != wanted_component:
            details.append("AUTHORITATIVE_REPLAY_MISMATCH")
        if meta is not None and meta["economic_package_fingerprint"] != authoritative_package.package_fingerprint:
            details.append("ECONOMIC_PACKAGE_FINGERPRINT_MISMATCH")
    return {
        "ok": not details,
        "details": details,
        "sqlite_quick_check": "ok" if "SQLITE_QUICK_CHECK_FAILED" not in details else "failed",
        "foreign_key_violations": 0 if "FOREIGN_KEY_VIOLATIONS" not in details else 1,
        "content_fingerprint": content_fingerprint(conn,target_package_id) if meta is not None else None,
        "authoritative_replay": authoritative_package is not None,
    }
