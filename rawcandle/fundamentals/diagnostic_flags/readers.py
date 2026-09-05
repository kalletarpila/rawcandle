from __future__ import annotations

import sqlite3
from typing import Any, Sequence

from rawcandle.fundamentals.diagnostic_flags.engine import FLAG_NAMES, MODEL_FINGERPRINT
from rawcandle.fundamentals.diagnostic_flags.persistence import (
    APPLICABILITY_TABLE,
    ENDPOINT_TABLE,
    EVALUATION_TABLE,
    FLAG_TABLE,
    HISTORY_MODE,
    PACKAGE_TABLE,
    REASON_TABLE,
    SOURCE_STATUS_TABLE,
    STATUS_TABLE,
    evidence_from_row,
)


class DiagnosticFlagRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def _package(self, model_fingerprint: str) -> sqlite3.Row:
        if model_fingerprint != MODEL_FINGERPRINT:
            raise ValueError("DIAGNOSTIC_MODEL_FINGERPRINT_REJECTED")
        row = self.connection.execute(
            f"SELECT * FROM {PACKAGE_TABLE} WHERE model_fingerprint=? AND history_mode=?",
            (model_fingerprint, HISTORY_MODE),
        ).fetchone()
        if row is None:
            raise LookupError("DIAGNOSTIC_PACKAGE_NOT_FOUND")
        return row

    def package_metadata(self, *, model_fingerprint: str) -> dict[str, Any]:
        return dict(self._package(model_fingerprint))

    def _base_query(self) -> str:
        return f"""SELECT e.*,v.*,f.flag_name,s.status_text,r.reason_text,a.applicability_text,ss.source_status_text
                     FROM {ENDPOINT_TABLE} e JOIN {EVALUATION_TABLE} v USING(endpoint_id)
                     JOIN {FLAG_TABLE} f USING(flag_id) JOIN {STATUS_TABLE} s USING(status_id)
                     JOIN {REASON_TABLE} r USING(reason_id)
                     LEFT JOIN {SOURCE_STATUS_TABLE} ss USING(source_status_id)
                     LEFT JOIN {APPLICABILITY_TABLE} a USING(applicability_id)"""

    def _assemble(self, rows: Sequence[sqlite3.Row]) -> dict[str, Any] | None:
        if not rows:
            return None
        first = rows[0]
        evaluations = []
        for row in sorted(rows, key=lambda item: FLAG_NAMES.index(item["flag_name"])):
            evaluations.append({
                "flag_name": row["flag_name"], "status": row["status_text"], "reason_code": row["reason_text"],
                "triggered": None if row["triggered"] is None else bool(row["triggered"]),
                "comparison_quarter_id": row["comparison_quarter_id"],
                "effective_available_date": row["effective_available_date"],
                "applicability_classification": row["applicability_text"],
                "evidence": evidence_from_row(row["flag_name"], row),
            })
        if len(evaluations) != 7:
            raise RuntimeError("DIAGNOSTIC_ENDPOINT_INCOMPLETE_NOT_CLEAR")
        return {
            "company_id": first["company_id"], "quarter_id": first["quarter_id"],
            "fiscal_year": first["fiscal_year"], "fiscal_quarter": f"Q{first['fiscal_quarter']}",
            "fiscal_sequence": first["fiscal_sequence"], "period_end": first["period_end"],
            "source_available_date": first["source_available_date"], "ttm_available_date": first["ttm_available_date"],
            "ttm_status": first["source_status_text"],
            "history_mode": HISTORY_MODE, "evaluations": evaluations,
        }

    def endpoint(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        pid = self._package(model_fingerprint)["package_id"]
        rows = self.connection.execute(self._base_query()+" WHERE e.package_id=? AND e.company_id=? AND e.fiscal_year=? AND e.fiscal_quarter=? ORDER BY v.flag_id",(pid,company_id,fiscal_year,int(fiscal_quarter[1]))).fetchall()
        return self._assemble(rows)

    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        pid=self._package(model_fingerprint)["package_id"]
        eid=self.connection.execute(f"SELECT endpoint_id FROM {ENDPOINT_TABLE} WHERE package_id=? AND company_id=? ORDER BY fiscal_sequence DESC LIMIT 1",(pid,company_id)).fetchone()
        if eid is None: return None
        return self._assemble(self.connection.execute(self._base_query()+" WHERE e.endpoint_id=? ORDER BY v.flag_id",(eid[0],)).fetchall())

    def current_batch(self, company_ids: Sequence[int], *, model_fingerprint: str) -> list[dict[str, Any]]:
        return [row for company_id in sorted(set(company_ids)) if (row:=self.current_company(company_id,model_fingerprint=model_fingerprint)) is not None]

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        pid=self._package(model_fingerprint)["package_id"]
        ids=[row[0] for row in self.connection.execute(f"SELECT endpoint_id FROM {ENDPOINT_TABLE} WHERE package_id=? AND company_id=? ORDER BY fiscal_sequence",(pid,company_id))]
        return [self._assemble(self.connection.execute(self._base_query()+" WHERE e.endpoint_id=? ORDER BY v.flag_id",(eid,)).fetchall()) for eid in ids]

    def cross_section(self, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> list[dict[str, Any]]:
        pid=self._package(model_fingerprint)["package_id"]
        ids=[row[0] for row in self.connection.execute(f"SELECT endpoint_id FROM {ENDPOINT_TABLE} WHERE package_id=? AND fiscal_year=? AND fiscal_quarter=? ORDER BY company_id",(pid,fiscal_year,int(fiscal_quarter[1])))]
        return [self._assemble(self.connection.execute(self._base_query()+" WHERE e.endpoint_id=? ORDER BY v.flag_id",(eid,)).fetchall()) for eid in ids]

    def current_filtered(self, flag_name: str, *, model_fingerprint: str, flagged_only: bool = False) -> list[dict[str, Any]]:
        if flag_name not in FLAG_NAMES: raise ValueError("DIAGNOSTIC_FLAG_REJECTED")
        pid=self._package(model_fingerprint)["package_id"]
        status=" AND s.status_text='EVALUATED_FLAGGED'" if flagged_only else ""
        rows=self.connection.execute(self._base_query()+f" JOIN (SELECT company_id,MAX(fiscal_sequence) seq FROM {ENDPOINT_TABLE} WHERE package_id=? GROUP BY company_id) latest ON latest.company_id=e.company_id AND latest.seq=e.fiscal_sequence WHERE e.package_id=? AND f.flag_name=?{status} ORDER BY e.company_id",(pid,pid,flag_name)).fetchall()
        return [{"company_id":row["company_id"],"quarter_id":row["quarter_id"],"fiscal_year":row["fiscal_year"],"fiscal_quarter":f"Q{row['fiscal_quarter']}","flag_name":row["flag_name"],"status":row["status_text"],"reason_code":row["reason_text"],"triggered":None if row["triggered"] is None else bool(row["triggered"]),"evidence":evidence_from_row(flag_name,row)} for row in rows]

    def current_flagged_universe(self, *, model_fingerprint: str) -> list[dict[str, Any]]:
        pid=self._package(model_fingerprint)["package_id"]
        rows=self.connection.execute(f"""SELECT e.company_id,e.quarter_id,e.fiscal_year,e.fiscal_quarter,f.flag_name
          FROM {ENDPOINT_TABLE} e JOIN {EVALUATION_TABLE} v USING(endpoint_id) JOIN {FLAG_TABLE} f USING(flag_id) JOIN {STATUS_TABLE} s USING(status_id)
          JOIN (SELECT company_id,MAX(fiscal_sequence) seq FROM {ENDPOINT_TABLE} WHERE package_id=? GROUP BY company_id) latest ON latest.company_id=e.company_id AND latest.seq=e.fiscal_sequence
          WHERE e.package_id=? AND s.status_text='EVALUATED_FLAGGED' ORDER BY e.company_id,v.flag_id""",(pid,pid)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            if not result or result[-1]["company_id"] != row["company_id"]:
                result.append({
                    "company_id": row["company_id"], "quarter_id": row["quarter_id"],
                    "fiscal_year": row["fiscal_year"], "fiscal_quarter": f"Q{row['fiscal_quarter']}",
                    "flags": (row["flag_name"],),
                })
            else:
                result[-1]["flags"] += (row["flag_name"],)
        return result
