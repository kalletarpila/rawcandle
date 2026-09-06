from __future__ import annotations

import json
import sqlite3
from typing import Any

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT as DELTA_V1
from rawcandle.fundamentals.diagnostic_flags.engine import MODEL_FINGERPRINT as DIAGNOSTIC_V1
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_V1
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RELATIVE_V1
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_V1
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_V1

from . import contract, delta, diagnostic_flags, lifecycle, relative_position, score, valuation
from .persistence import DIAGNOSTIC_HISTORY_MODE, EVIDENCE_FIELD_TABLE, HISTORY_MODE, MANIFEST_TABLE, MODEL_MAP, PACKAGE_FINGERPRINT


KNOWN = {
    "score": {SCORE_V1, score.MODEL_FINGERPRINT},
    "lifecycle": {LIFECYCLE_V1, lifecycle.MODEL_FINGERPRINT},
    "valuation": {VALUATION_V1, valuation.MODEL_FINGERPRINT},
    "delta": {DELTA_V1, delta.MODEL_FINGERPRINT},
    "diagnostic": {DIAGNOSTIC_V1, diagnostic_flags.MODEL_FINGERPRINT},
    "relative": {RELATIVE_V1, relative_position.MODEL_FINGERPRINT},
}


def _require(layer: str, fingerprint: str) -> None:
    if fingerprint not in KNOWN[layer]:
        raise ValueError(f"UNKNOWN_{layer.upper()}_MODEL_FINGERPRINT:{fingerprint}")


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params)]


class ParallelModelRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def package_manifest(self) -> dict[str, Any]:
        row=self.conn.execute(f"SELECT * FROM {MANIFEST_TABLE}").fetchone()
        if row is None: raise LookupError("OPERATING_INCOME_V2_PACKAGE_NOT_FOUND")
        return dict(row)

    def score_history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require("score",model_fingerprint)
        rows=_rows(self.conn,"SELECT * FROM score_result WHERE company_id=? AND model_fingerprint=? ORDER BY quarter_id",(company_id,model_fingerprint))
        for row in rows:
            row["components"]=_rows(self.conn,"SELECT component_name,component_score,evidence_json FROM score_component WHERE score_result_id=? ORDER BY component_name",(row["score_result_id"],))
        return rows

    def score_current(self, company_id: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        rows=self.score_history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def score_quarter(self, company_id: int, quarter_id: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        _require("score",model_fingerprint)
        rows=self.score_history(company_id,model_fingerprint=model_fingerprint)
        return next((row for row in rows if row["quarter_id"]==quarter_id),None)

    def lifecycle_history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str,Any]]:
        _require("lifecycle",model_fingerprint)
        return _rows(self.conn,"SELECT * FROM lifecycle_revised_result WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence",(company_id,model_fingerprint,HISTORY_MODE))

    def lifecycle_current(self, company_id: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        rows=self.lifecycle_history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def lifecycle_quarter(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str,Any] | None:
        return next((row for row in self.lifecycle_history(company_id,model_fingerprint=model_fingerprint) if row["fiscal_year"]==fiscal_year and row["fiscal_quarter"]==fiscal_quarter),None)

    def valuation_history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str,Any]]:
        _require("valuation",model_fingerprint)
        return _rows(self.conn,"SELECT * FROM valuation_revised_result WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence",(company_id,model_fingerprint,HISTORY_MODE))

    def valuation_current(self, company_id: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        rows=self.valuation_history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def valuation_quarter(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str,Any] | None:
        return next((row for row in self.valuation_history(company_id,model_fingerprint=model_fingerprint) if row["fiscal_year"]==fiscal_year and row["fiscal_quarter"]==fiscal_quarter),None)

    def delta_history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str,Any]]:
        _require("delta",model_fingerprint)
        return _rows(self.conn,"SELECT r.* FROM fundamental_delta_result r JOIN fundamental_delta_package p USING(package_id) WHERE r.company_id=? AND p.model_fingerprint=? ORDER BY r.fiscal_sequence",(company_id,model_fingerprint))

    def delta_current(self, company_id: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        rows=self.delta_history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def delta_quarter(self, company_id: int, fiscal_year: int, fiscal_quarter: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        return next((row for row in self.delta_history(company_id,model_fingerprint=model_fingerprint) if row["fiscal_year"]==fiscal_year and row["fiscal_quarter"]==fiscal_quarter),None)

    def diagnostic_history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str,Any]]:
        _require("diagnostic",model_fingerprint)
        endpoints=_rows(self.conn,"SELECT e.* FROM diagnostic_flag_endpoint e JOIN diagnostic_flag_package p USING(package_id) WHERE e.company_id=? AND p.model_fingerprint=? AND p.history_mode=? ORDER BY e.fiscal_sequence",(company_id,model_fingerprint,DIAGNOSTIC_HISTORY_MODE))
        for endpoint in endpoints:
            evaluations=_rows(self.conn,"SELECT v.*,f.flag_name,s.status_text,r.reason_text FROM diagnostic_flag_evaluation v JOIN diagnostic_flag_type f USING(flag_id) JOIN diagnostic_flag_status s USING(status_id) JOIN diagnostic_flag_reason r USING(reason_id) WHERE v.endpoint_id=? ORDER BY f.flag_name",(endpoint["endpoint_id"],))
            if model_fingerprint==diagnostic_flags.MODEL_FINGERPRINT:
                for item in evaluations:
                    fields=_rows(self.conn,f"SELECT slot_number,field_name FROM {EVIDENCE_FIELD_TABLE} WHERE model_fingerprint=? AND flag_name=? ORDER BY slot_number",(model_fingerprint,item["flag_name"]))
                    item["evidence"]={field["field_name"]:item[f"n{field['slot_number']:02d}"] for field in fields}
            endpoint["evaluations"]=evaluations
        return endpoints

    def diagnostic_current(self, company_id: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        rows=self.diagnostic_history(company_id,model_fingerprint=model_fingerprint); return rows[-1] if rows else None

    def diagnostic_quarter(self, company_id: int, fiscal_year: int, fiscal_quarter: int, *, model_fingerprint: str) -> dict[str,Any] | None:
        return next((row for row in self.diagnostic_history(company_id,model_fingerprint=model_fingerprint) if row["fiscal_year"]==fiscal_year and row["fiscal_quarter"]==fiscal_quarter),None)

    def relative_current(self, company_id: int, *, model_fingerprint: str) -> list[dict[str,Any]]:
        _require("relative",model_fingerprint)
        return _rows(self.conn,"SELECT r.* FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) WHERE a.model_fingerprint=? AND r.model_fingerprint=? AND r.company_id=? ORDER BY r.measure,r.peer_scope,r.peer_group_id",(model_fingerprint,model_fingerprint,company_id))

    def assert_v2_bundle(self) -> None:
        manifest=self.package_manifest()
        if manifest["family_fingerprint"] != contract.FAMILY_FINGERPRINT:
            raise ValueError("OPERATING_INCOME_V2_PACKAGE_FAMILY_MISMATCH")
        if manifest["persistence_fingerprint"] != PACKAGE_FINGERPRINT:
            raise ValueError("OPERATING_INCOME_V2_PACKAGE_PERSISTENCE_MISMATCH")
        if json.loads(manifest["model_manifest_json"]) != {key: list(value) for key,value in MODEL_MAP.items()}:
            raise ValueError("OPERATING_INCOME_V2_PACKAGE_MODEL_MANIFEST_MISMATCH")
        required=(("score_result",score.MODEL_FINGERPRINT),("lifecycle_revised_result",lifecycle.MODEL_FINGERPRINT),("valuation_revised_result",valuation.MODEL_FINGERPRINT),("fundamental_delta_package",delta.MODEL_FINGERPRINT),("diagnostic_flag_package",diagnostic_flags.MODEL_FINGERPRINT),("relative_position_snapshot",relative_position.MODEL_FINGERPRINT))
        missing=[name for name,fp in required if not self.conn.execute(f"SELECT 1 FROM {name} WHERE model_fingerprint=? LIMIT 1",(fp,)).fetchone()]
        if missing: raise RuntimeError("OPERATING_INCOME_V2_UPSTREAM_LAYER_MISSING:"+",".join(missing))
