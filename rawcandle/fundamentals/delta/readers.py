from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import date
from typing import Any, Sequence

from rawcandle.fundamentals.delta.context import calculate_lifecycle_context, calculate_valuation_diagnostic
from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import (
    COMPONENT_TABLE, COMPONENT_TYPE_TABLE, HISTORY_MODE, PACKAGE_TABLE, REASON_TABLE,
    STATUS_TABLE, TOTAL_TABLE,
)
from rawcandle.fundamentals.delta.source import _group, _lifecycle_rows, _valuation_rows
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_MODEL_FINGERPRINT
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_MODEL_FINGERPRINT


def _require(supplied: str, expected: str, label: str) -> None:
    if supplied != expected:
        raise ValueError(f"{label}_MODEL_FINGERPRINT_REJECTED:{supplied}")


def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params)]


def _package_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(f"SELECT package_id FROM {PACKAGE_TABLE} WHERE model_fingerprint=? AND history_mode=?", (MODEL_FINGERPRINT,HISTORY_MODE)).fetchone()
    if row is None:
        raise LookupError("DELTA_PACKAGE_NOT_FOUND")
    return int(row[0])


_TOTAL_SELECT = f"""SELECT r.*,
 sq.status_text qoq_status,rq.reason_text qoq_reason,
 s2.status_text two_quarter_status,r2.reason_text two_quarter_reason,
 sy.status_text yoy_status,ry.reason_text yoy_reason
 FROM {TOTAL_TABLE} r
 JOIN {STATUS_TABLE} sq ON sq.status_id=r.qoq_status_id JOIN {REASON_TABLE} rq ON rq.reason_id=r.qoq_reason_id
 JOIN {STATUS_TABLE} s2 ON s2.status_id=r.two_quarter_status_id JOIN {REASON_TABLE} r2 ON r2.reason_id=r.two_quarter_reason_id
 JOIN {STATUS_TABLE} sy ON sy.status_id=r.yoy_status_id JOIN {REASON_TABLE} ry ON ry.reason_id=r.yoy_reason_id"""


def _public_total(row: dict[str, Any]) -> dict[str, Any]:
    output=dict(row)
    output["fundamental_delta_result_id"]=output["endpoint_id"]
    output["fiscal_quarter"]=f"Q{output['fiscal_quarter']}"
    output["reconciliation_status"]="RECONCILED" if output["reconciliation_status"] else "NOT_APPLICABLE"
    for prefix in ("qoq","two_quarter","yoy"):
        output.pop(f"{prefix}_status_id",None); output.pop(f"{prefix}_reason_id",None)
    return output


class FundamentalDeltaRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn=conn

    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        _require(model_fingerprint,MODEL_FINGERPRINT,"DELTA")
        rows=_rows(self.conn,_TOTAL_SELECT+" WHERE r.package_id=? AND r.company_id=? ORDER BY r.fiscal_sequence DESC LIMIT 1",(_package_id(self.conn),company_id))
        return _public_total(rows[0]) if rows else None

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require(model_fingerprint,MODEL_FINGERPRINT,"DELTA")
        return [_public_total(row) for row in _rows(self.conn,_TOTAL_SELECT+" WHERE r.package_id=? AND r.company_id=? ORDER BY r.fiscal_sequence",(_package_id(self.conn),company_id))]

    def endpoint(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        _require(model_fingerprint,MODEL_FINGERPRINT,"DELTA")
        if fiscal_quarter not in {"Q1","Q2","Q3","Q4"}: raise ValueError(f"INVALID_FISCAL_QUARTER:{fiscal_quarter}")
        rows=_rows(self.conn,_TOTAL_SELECT+" WHERE r.package_id=? AND r.company_id=? AND r.fiscal_year=? AND r.fiscal_quarter=?",(_package_id(self.conn),company_id,fiscal_year,int(fiscal_quarter[1])))
        return _public_total(rows[0]) if rows else None

    def current_universe(self, *, model_fingerprint: str, as_of_date: str | None=None, freshness_days: int | None=None) -> list[dict[str, Any]]:
        _require(model_fingerprint,MODEL_FINGERPRINT,"DELTA")
        params: list[Any]=[_package_id(self.conn)]; cutoff=""
        if as_of_date is not None:
            date.fromisoformat(as_of_date); cutoff=" AND r.current_available_date<=?"; params.append(as_of_date)
        sql=_TOTAL_SELECT+f" WHERE r.package_id=?{cutoff} AND r.fiscal_sequence=(SELECT MAX(x.fiscal_sequence) FROM {TOTAL_TABLE} x WHERE x.package_id=r.package_id AND x.company_id=r.company_id{(' AND x.current_available_date<=?' if as_of_date else '')}) ORDER BY r.company_id"
        if as_of_date is not None: params.append(as_of_date)
        rows=[_public_total(row) for row in _rows(self.conn,sql,params)]
        if as_of_date is not None and freshness_days is not None:
            snapshot=date.fromisoformat(as_of_date); rows=[row for row in rows if 0 <= (snapshot-date.fromisoformat(row["current_available_date"])).days <= freshness_days]
        return rows

    def cross_section(self, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require(model_fingerprint,MODEL_FINGERPRINT,"DELTA")
        return [_public_total(row) for row in _rows(self.conn,_TOTAL_SELECT+" WHERE r.package_id=? AND r.fiscal_year=? AND r.fiscal_quarter=? ORDER BY r.company_id",(_package_id(self.conn),fiscal_year,int(fiscal_quarter[1])))]

    def with_components(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        total=self.endpoint(company_id,fiscal_year,fiscal_quarter,model_fingerprint=model_fingerprint)
        if total is None: return None
        components=_rows(self.conn,f"""SELECT c.*,t.component_name,t.maximum_points,
          sq.status_text qoq_status,rq.reason_text qoq_reason,s2.status_text two_quarter_status,r2.reason_text two_quarter_reason,
          sy.status_text yoy_status,ry.reason_text yoy_reason FROM {COMPONENT_TABLE} c JOIN {COMPONENT_TYPE_TABLE} t USING(component_id)
          JOIN {STATUS_TABLE} sq ON sq.status_id=c.qoq_status_id JOIN {REASON_TABLE} rq ON rq.reason_id=c.qoq_reason_id
          JOIN {STATUS_TABLE} s2 ON s2.status_id=c.two_quarter_status_id JOIN {REASON_TABLE} r2 ON r2.reason_id=c.two_quarter_reason_id
          JOIN {STATUS_TABLE} sy ON sy.status_id=c.yoy_status_id JOIN {REASON_TABLE} ry ON ry.reason_id=c.yoy_reason_id
          WHERE c.endpoint_id=? ORDER BY t.component_name""",(total["endpoint_id"],))
        return {"total":total,"components":components}


def _source_fp(conn: sqlite3.Connection, field: str) -> str:
    row=conn.execute(f"SELECT {field} FROM {PACKAGE_TABLE} WHERE model_fingerprint=? AND history_mode=?",(MODEL_FINGERPRINT,HISTORY_MODE)).fetchone()
    if row is None: raise LookupError("DELTA_PACKAGE_NOT_FOUND")
    return str(row[0])


class LifecycleChangeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None: self.conn=conn

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require(model_fingerprint,LIFECYCLE_MODEL_FINGERPRINT,"LIFECYCLE")
        observations,_=_lifecycle_rows(self.conn,model_fingerprint,(company_id,)); source=_source_fp(self.conn,"lifecycle_source_fingerprint")
        return [asdict(calculate_lifecycle_context(current,observations,source_fingerprint=source)) for current in observations]

    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        rows=self.history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def current_batch(self, company_ids: Sequence[int], *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require(model_fingerprint,LIFECYCLE_MODEL_FINGERPRINT,"LIFECYCLE")
        observations,_=_lifecycle_rows(self.conn,model_fingerprint,company_ids); source=_source_fp(self.conn,"lifecycle_source_fingerprint")
        return [asdict(calculate_lifecycle_context(rows[-1],rows,source_fingerprint=source)) for _,rows in sorted(_group(observations).items())]


class ValuationChangeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None: self.conn=conn

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require(model_fingerprint,VALUATION_MODEL_FINGERPRINT,"VALUATION")
        observations,_=_valuation_rows(self.conn,model_fingerprint,(company_id,)); source=_source_fp(self.conn,"valuation_source_fingerprint")
        return [asdict(calculate_valuation_diagnostic(current,observations,source_fingerprint=source)) for current in observations]

    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        rows=self.history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def current_batch(self, company_ids: Sequence[int], *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require(model_fingerprint,VALUATION_MODEL_FINGERPRINT,"VALUATION")
        observations,_=_valuation_rows(self.conn,model_fingerprint,company_ids); source=_source_fp(self.conn,"valuation_source_fingerprint")
        return [asdict(calculate_valuation_diagnostic(rows[-1],rows,source_fingerprint=source)) for _,rows in sorted(_group(observations).items())]
