from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import (
    COMPONENT_TABLE,
    HISTORY_MODE,
    LIFECYCLE_TABLE,
    TOTAL_TABLE,
    VALUATION_TABLE,
)


def _require_fingerprint(model_fingerprint: str) -> None:
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError(f"DELTA_MODEL_FINGERPRINT_REJECTED:{model_fingerprint}")


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params)]


class FundamentalDeltaRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        _require_fingerprint(model_fingerprint)
        rows = _rows(self.conn, f"SELECT * FROM {TOTAL_TABLE} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence DESC LIMIT 1", (company_id, model_fingerprint, HISTORY_MODE))
        return rows[0] if rows else None

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require_fingerprint(model_fingerprint)
        return _rows(self.conn, f"SELECT * FROM {TOTAL_TABLE} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence", (company_id, model_fingerprint, HISTORY_MODE))

    def endpoint(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        _require_fingerprint(model_fingerprint)
        rows = _rows(self.conn, f"SELECT * FROM {TOTAL_TABLE} WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=? AND model_fingerprint=? AND history_mode=?", (company_id, fiscal_year, fiscal_quarter, model_fingerprint, HISTORY_MODE))
        return rows[0] if rows else None

    def current_universe(self, *, model_fingerprint: str, as_of_date: str | None = None, freshness_days: int | None = None) -> list[dict[str, Any]]:
        _require_fingerprint(model_fingerprint)
        params: list[Any] = [model_fingerprint, HISTORY_MODE]
        date_filter = ""
        if as_of_date is not None:
            date.fromisoformat(as_of_date)
            date_filter = " AND r.current_available_date<=?"
            params.append(as_of_date)
        rows = _rows(self.conn, f"""SELECT r.* FROM {TOTAL_TABLE} r WHERE r.model_fingerprint=? AND r.history_mode=? {date_filter}
            AND r.fiscal_sequence=(SELECT MAX(x.fiscal_sequence) FROM {TOTAL_TABLE} x WHERE x.company_id=r.company_id AND x.model_fingerprint=r.model_fingerprint AND x.history_mode=r.history_mode {('AND x.current_available_date<=?' if as_of_date else '')}) ORDER BY r.company_id""", tuple(params + ([as_of_date] if as_of_date else [])))
        if as_of_date is not None and freshness_days is not None:
            snapshot = date.fromisoformat(as_of_date)
            rows = [row for row in rows if 0 <= (snapshot-date.fromisoformat(row["current_available_date"])).days <= freshness_days]
        return rows

    def cross_section(self, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require_fingerprint(model_fingerprint)
        return _rows(self.conn, f"SELECT * FROM {TOTAL_TABLE} WHERE fiscal_year=? AND fiscal_quarter=? AND model_fingerprint=? AND history_mode=? ORDER BY company_id", (fiscal_year, fiscal_quarter, model_fingerprint, HISTORY_MODE))

    def with_components(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        total = self.endpoint(company_id, fiscal_year, fiscal_quarter, model_fingerprint=model_fingerprint)
        if total is None:
            return None
        components = _rows(self.conn, f"SELECT * FROM {COMPONENT_TABLE} WHERE fundamental_delta_result_id=? AND model_fingerprint=? ORDER BY component_name", (total["fundamental_delta_result_id"], model_fingerprint))
        return {"total": total, "components": components, "history_mode": HISTORY_MODE}


class LifecycleChangeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None: self.conn = conn
    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        _require_fingerprint(model_fingerprint); rows=_rows(self.conn,f"SELECT * FROM {LIFECYCLE_TABLE} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence DESC LIMIT 1",(company_id,model_fingerprint,HISTORY_MODE)); return rows[0] if rows else None
    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require_fingerprint(model_fingerprint); return _rows(self.conn,f"SELECT * FROM {LIFECYCLE_TABLE} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence",(company_id,model_fingerprint,HISTORY_MODE))


class ValuationChangeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None: self.conn = conn
    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        for prefix in ("qoq","two_quarter","yoy"): row[f"{prefix}_payload"] = json.loads(row[f"{prefix}_payload_json"])
        return row
    def current_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        _require_fingerprint(model_fingerprint); rows=_rows(self.conn,f"SELECT * FROM {VALUATION_TABLE} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence DESC LIMIT 1",(company_id,model_fingerprint,HISTORY_MODE)); return self._decode(rows[0]) if rows else None
    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        _require_fingerprint(model_fingerprint); return [self._decode(row) for row in _rows(self.conn,f"SELECT * FROM {VALUATION_TABLE} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence",(company_id,model_fingerprint,HISTORY_MODE))]
