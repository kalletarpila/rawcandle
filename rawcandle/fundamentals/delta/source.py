from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.delta.context import LifecycleObservation, ValuationObservation
from rawcandle.fundamentals.delta.engine import (
    COMPONENT_MAXIMA,
    FiscalObservation,
    ScoreComponentObservation,
    ScoreObservation,
    fingerprint,
    fiscal_sequence,
)
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_MODEL_FINGERPRINT
from rawcandle.fundamentals.lifecycle.revised_history import HISTORY_MODE
from rawcandle.fundamentals.score.engine import (
    MODEL_FINGERPRINT as SCORE_MODEL_FINGERPRINT,
    TTM_MODEL_VERSION,
)
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_MODEL_FINGERPRINT


DEFAULT_FRESHNESS_DAYS = 180


@dataclass(frozen=True)
class ReadOnlyDeltaPaths:
    analysis_db: Path
    canonical_db: Path


@dataclass(frozen=True)
class DeltaSource:
    score_histories: Mapping[int, tuple[ScoreObservation, ...]]
    lifecycle_histories: Mapping[int, tuple[LifecycleObservation, ...]]
    valuation_histories: Mapping[int, tuple[ValuationObservation, ...]]
    company_tickers: Mapping[int, str | None]
    score_source_fingerprint: str
    lifecycle_source_fingerprint: str
    valuation_source_fingerprint: str
    source_fingerprint: str


def _validate_paths(paths: ReadOnlyDeltaPaths) -> None:
    resolved: list[Path] = []
    for label, path in (("ANALYSIS", paths.analysis_db), ("CANONICAL", paths.canonical_db)):
        if not path.is_absolute():
            raise ValueError(f"{label}_DB_PATH_MUST_BE_ABSOLUTE")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label}_DB_MUST_BE_REGULAR_NON_SYMLINK_FILE")
        resolved.append(path.resolve())
    if len(set(resolved)) != len(resolved):
        raise ValueError("SOURCE_DATABASE_PATHS_MUST_BE_DISTINCT")


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _required_tables(conn: sqlite3.Connection, names: Sequence[str], schema: str = "main") -> None:
    existing = {
        row[0] for row in conn.execute(
            f"SELECT name FROM {schema}.sqlite_schema WHERE type='table'"
        )
    }
    missing = sorted(set(names) - existing)
    if missing:
        raise ValueError(f"SOURCE_TABLES_MISSING:{schema}:{','.join(missing)}")


def _json_object(value: str | None, *, field: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"INVALID_SOURCE_JSON:{field}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"INVALID_SOURCE_JSON_OBJECT:{field}")
    return parsed


def _group(rows: Sequence[Any]) -> dict[int, tuple[Any, ...]]:
    output: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        output[row.fiscal.company_id].append(row)
    return {
        company_id: tuple(sorted(items, key=lambda row: (row.fiscal.fiscal_sequence, row.fiscal.observation_id)))
        for company_id, items in sorted(output.items())
    }


def _duplicate_guard(rows: Sequence[sqlite3.Row], *, source: str) -> None:
    seen: set[tuple[int, int]] = set()
    for row in rows:
        key = (int(row["company_id"]), fiscal_sequence(int(row["fiscal_year"]), str(row["fiscal_quarter"])))
        if key in seen:
            raise ValueError(f"DUPLICATE_{source}_FISCAL_IDENTITY:{key[0]}:{key[1]}")
        seen.add(key)


def _fiscal(row: Mapping[str, Any], *, result_prefix: str, result_id: int, available_key: str) -> FiscalObservation:
    year = int(row["fiscal_year"])
    quarter = str(row["fiscal_quarter"])
    available = row[available_key]
    return FiscalObservation(
        observation_id=f"{result_prefix}:{result_id}",
        company_id=int(row["company_id"]),
        fiscal_year=year,
        fiscal_quarter=quarter,
        fiscal_sequence=fiscal_sequence(year, quarter),
        period_end=str(row["period_end"]),
        available_date=str(available or ""),
    )


def _score_rows(conn: sqlite3.Connection, score_fingerprint: str) -> tuple[list[ScoreObservation], str]:
    rows = conn.execute(
        """
        SELECT sr.*,q.fiscal_year,q.fiscal_quarter,q.period_end,q.source_availability_date,
               t.readiness_status AS ttm_readiness_status,t.output_fingerprint AS ttm_output_fingerprint
          FROM score_result sr
          JOIN canonical.v4_quarter q ON q.quarter_id=sr.quarter_id AND q.company_id=sr.company_id
          LEFT JOIN canonical.v4_ttm_values t
            ON t.company_id=sr.company_id AND t.endpoint_quarter_id=sr.quarter_id
           AND t.model_version=?
         WHERE sr.model_fingerprint=?
         ORDER BY sr.company_id,q.fiscal_year,
                  CASE q.fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                  sr.score_result_id
        """,
        (TTM_MODEL_VERSION, score_fingerprint),
    ).fetchall()
    _duplicate_guard(rows, source="SCORE")
    component_rows = conn.execute(
        """
        SELECT sc.score_result_id,sc.component_name,sc.component_score,sc.evidence_json
          FROM score_component sc JOIN score_result sr USING(score_result_id)
         WHERE sr.model_fingerprint=?
         ORDER BY sc.score_result_id,sc.component_name
        """,
        (score_fingerprint,),
    ).fetchall()
    components: dict[int, list[ScoreComponentObservation]] = defaultdict(list)
    component_payload: list[dict[str, Any]] = []
    for row in component_rows:
        evidence = _json_object(row["evidence_json"], field="score_component.evidence_json")
        name = str(row["component_name"])
        maximum = COMPONENT_MAXIMA.get(name, -1.0)
        item = ScoreComponentObservation(
            component_name=name,
            points=row["component_score"],
            maximum_points=maximum,
            value_status=str(evidence.get("value_status", "MISSING")),
            imputed=False,
        )
        components[int(row["score_result_id"])].append(item)
        component_payload.append({
            "score_result_id": int(row["score_result_id"]), "component_name": name,
            "component_score": row["component_score"], "evidence": evidence,
        })
    observations: list[ScoreObservation] = []
    source_payload: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        result_id = int(row["score_result_id"])
        missing = _json_object(row.get("missing_input_reason"), field="score_result.missing_input_reason")
        imputed = set(missing.get("imputed_components") or ())
        score_components = tuple(
            ScoreComponentObservation(
                component_name=item.component_name,
                points=item.points,
                maximum_points=item.maximum_points,
                value_status=item.value_status,
                imputed=item.component_name in imputed,
            )
            for item in components.get(result_id, ())
        )
        observation = ScoreObservation(
            fiscal=_fiscal(row, result_prefix="score_result", result_id=result_id, available_key="source_availability_date"),
            score_result_id=result_id,
            model_version=str(row["model_version"]),
            model_fingerprint=str(row["model_fingerprint"]),
            total_score=row["total_score"],
            readiness_status=str(row["readiness_status"]),
            ttm_readiness_status=str(row["ttm_readiness_status"] or "TTM_NOT_READY"),
            components=score_components,
            reweighted=bool(missing.get("reweighted", False)),
        )
        observations.append(observation)
        source_payload.append({
            "score_result_id": result_id, "company_id": observation.fiscal.company_id,
            "fiscal_sequence": observation.fiscal.fiscal_sequence,
            "available_date": observation.fiscal.available_date,
            "model_fingerprint": observation.model_fingerprint,
            "total_score": observation.total_score, "readiness_status": observation.readiness_status,
            "ttm_readiness_status": observation.ttm_readiness_status,
            "ttm_output_fingerprint": row["ttm_output_fingerprint"],
        })
    return observations, fingerprint({"results": source_payload, "components": component_payload})


def _lifecycle_rows(conn: sqlite3.Connection, model_fingerprint: str, company_ids: Sequence[int] = ()) -> tuple[list[LifecycleObservation], str]:
    company_clause = ""
    params: list[Any] = [model_fingerprint, HISTORY_MODE]
    if company_ids:
        selected = tuple(sorted(set(map(int, company_ids))))
        company_clause = f" AND company_id IN ({','.join('?' for _ in selected)})"
        params.extend(selected)
    rows = conn.execute(
        f"""SELECT * FROM lifecycle_revised_result
             WHERE model_fingerprint=? AND history_mode=? {company_clause}
             ORDER BY company_id,fiscal_sequence,lifecycle_revised_result_id""",
        params,
    ).fetchall()
    _duplicate_guard(rows, source="LIFECYCLE")
    output: list[LifecycleObservation] = []
    payload: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        result_id = int(row["lifecycle_revised_result_id"])
        output.append(LifecycleObservation(
            fiscal=_fiscal(row, result_prefix="lifecycle_revised_result", result_id=result_id, available_key="source_available_date"),
            lifecycle_result_id=result_id,
            model_fingerprint=str(row["model_fingerprint"]),
            lifecycle_status=str(row["lifecycle_status"]),
            raw_state=str(row["raw_state"]),
            final_state=row["final_state"],
            last_confirmed_state=row["last_confirmed_state"],
            candidate_state=row["candidate_state"],
            candidate_count=int(row["candidate_count"]),
        ))
        payload.append({key: row.get(key) for key in (
            "lifecycle_revised_result_id", "company_id", "fiscal_sequence", "period_end",
            "source_available_date", "model_fingerprint", "raw_state", "final_state",
            "lifecycle_status", "last_confirmed_state", "candidate_state", "candidate_count",
            "source_input_fingerprint",
        )})
    return output, fingerprint(payload)


def _valuation_rows(conn: sqlite3.Connection, model_fingerprint: str, company_ids: Sequence[int] = ()) -> tuple[list[ValuationObservation], str]:
    company_clause = ""
    params: list[Any] = [model_fingerprint, HISTORY_MODE]
    if company_ids:
        selected = tuple(sorted(set(map(int, company_ids))))
        company_clause = f" AND company_id IN ({','.join('?' for _ in selected)})"
        params.extend(selected)
    rows = conn.execute(
        f"""SELECT * FROM valuation_revised_result
             WHERE model_fingerprint=? AND history_mode=? {company_clause}
             ORDER BY company_id,fiscal_sequence,valuation_revised_result_id""",
        params,
    ).fetchall()
    _duplicate_guard(rows, source="VALUATION")
    output: list[ValuationObservation] = []
    payload: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        result_id = int(row["valuation_revised_result_id"])
        output.append(ValuationObservation(
            fiscal=_fiscal(row, result_prefix="valuation_revised_result", result_id=result_id, available_key="fundamental_available_date"),
            valuation_result_id=result_id,
            model_fingerprint=str(row["model_fingerprint"]),
            valuation_status=str(row["valuation_status"]),
            total_score=row["total_valuation_score"], ebit_points=row["ebit_points"],
            fcf_points=row["fcf_points"], earnings_points=row["earnings_points"],
            price_date=row["price_date"], selected_price=row["selected_price"],
            ebit_yield=row["ebit_yield"], fcf_yield=row["fcf_yield"],
            earnings_yield=row["earnings_yield"], market_cap=row["market_cap"],
            enterprise_value=row["enterprise_value"], result_fingerprint=str(row["result_fingerprint"]),
        ))
        payload.append({key: row.get(key) for key in (
            "valuation_revised_result_id", "company_id", "fiscal_sequence", "period_end",
            "fundamental_available_date", "price_date", "selected_price", "market_cap",
            "enterprise_value", "ebit_yield", "ebit_points", "fcf_yield", "fcf_points",
            "earnings_yield", "earnings_points", "total_valuation_score", "valuation_status",
            "model_fingerprint", "source_fingerprint", "engine_result_fingerprint", "result_fingerprint",
        )})
    return output, fingerprint(payload)


def load_delta_source(
    paths: ReadOnlyDeltaPaths,
    *,
    score_model_fingerprint: str,
    lifecycle_model_fingerprint: str,
    valuation_model_fingerprint: str,
) -> DeltaSource:
    _validate_paths(paths)
    expected = (
        ("SCORE", score_model_fingerprint, SCORE_MODEL_FINGERPRINT),
        ("LIFECYCLE", lifecycle_model_fingerprint, LIFECYCLE_MODEL_FINGERPRINT),
        ("VALUATION", valuation_model_fingerprint, VALUATION_MODEL_FINGERPRINT),
    )
    for label, supplied, locked in expected:
        if supplied != locked:
            raise ValueError(f"{label}_MODEL_FINGERPRINT_REJECTED:{supplied}")
    with _readonly(paths.analysis_db) as conn:
        conn.execute("ATTACH DATABASE ? AS canonical", (f"file:{paths.canonical_db}?mode=ro",))
        _required_tables(conn, ("score_result", "score_component", "lifecycle_revised_result", "valuation_revised_result"))
        _required_tables(conn, ("v4_quarter", "v4_ttm_values"), "canonical")
        scores, score_fp = _score_rows(conn, score_model_fingerprint)
        lifecycle, lifecycle_fp = _lifecycle_rows(conn, lifecycle_model_fingerprint)
        valuation, valuation_fp = _valuation_rows(conn, valuation_model_fingerprint)
        security_columns = {row[1] for row in conn.execute("PRAGMA canonical.table_info(security)")}
        security_order = "active DESC,security_id DESC" if "active" in security_columns else "security_id DESC"
        tickers = {
            int(row["company_id"]): row["current_ticker"]
            for row in conn.execute(
                f"""SELECT s.company_id,s.current_ticker FROM canonical.security s
                      WHERE s.security_id=(
                          SELECT candidate.security_id FROM canonical.security candidate
                          WHERE candidate.company_id=s.company_id
                          ORDER BY candidate.{security_order.replace(',', ',candidate.')} LIMIT 1
                      ) ORDER BY s.company_id"""
            )
        }
    combined = fingerprint({
        "score": score_fp, "lifecycle": lifecycle_fp, "valuation": valuation_fp,
    })
    return DeltaSource(
        score_histories=_group(scores), lifecycle_histories=_group(lifecycle),
        valuation_histories=_group(valuation), company_tickers=tickers,
        score_source_fingerprint=score_fp,
        lifecycle_source_fingerprint=lifecycle_fp, valuation_source_fingerprint=valuation_fp,
        source_fingerprint=combined,
    )


def latest_fresh_observations(
    histories: Mapping[int, Sequence[Any]], *, as_of_date: str, freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> tuple[Any, ...]:
    snapshot = date.fromisoformat(as_of_date)
    if freshness_days < 0:
        raise ValueError("FRESHNESS_DAYS_MUST_BE_NONNEGATIVE")
    output = []
    for company_id in sorted(histories):
        eligible = []
        for observation in histories[company_id]:
            try:
                available = date.fromisoformat(observation.fiscal.available_date)
            except (TypeError, ValueError):
                continue
            age = (snapshot - available).days
            if 0 <= age <= freshness_days:
                eligible.append(observation)
        if eligible:
            output.append(max(eligible, key=lambda row: (row.fiscal.fiscal_sequence, row.fiscal.observation_id)))
    return tuple(output)
