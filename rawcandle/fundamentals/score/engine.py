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
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.score.methodology import (
    ANCHORS,
    CONSISTENCY_TOLERANCES,
    balance_points,
    consistency_points,
    fiscal_ordinal,
    piecewise_score,
    safe_div,
    safe_growth,
)
from rawcandle.fundamentals.ttm.engine import canonical_financial_fingerprint, ttm_fingerprints


MODEL_VERSION = "SIMPLE_FUNDAMENTAL_SCORE_V1"
TTM_MODEL_VERSION = "V4_TTM_EBIT_FIRST_V1"
CONSISTENCY_IMPUTATION = 6.988540590181791
COMPONENTS = (
    "REVENUE_GROWTH",
    "EBIT_PROFITABILITY",
    "EBIT_MARGIN_DIRECTION",
    "FCF_MARGIN",
    "BALANCE_SHEET_RESILIENCE",
    "DILUTION",
    "CONSISTENCY",
)
CORE_COMPONENTS = COMPONENTS[:5]
MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "ttm_model_version": TTM_MODEL_VERSION,
    "components": {
        "REVENUE_GROWTH": {"maximum": 20.0, "anchors": ANCHORS["revenue_growth_yoy_ttm"]},
        "EBIT_PROFITABILITY": {"maximum": 15.0, "anchors": ANCHORS["ebit_margin_ttm"]},
        "EBIT_MARGIN_DIRECTION": {"maximum": 15.0, "anchors": ANCHORS["ebit_margin_direction"]},
        "FCF_MARGIN": {"maximum": 15.0, "anchors": ANCHORS["fcf_margin_ttm"]},
        "BALANCE_SHEET_RESILIENCE": {"maximum": 15.0, "positive_ebit_floor": 4.0},
        "DILUTION": {"maximum": 10.0, "anchors": ANCHORS["share_change_yoy"]},
        "CONSISTENCY": {
            "maximum": 10.0,
            "tolerances": CONSISTENCY_TOLERANCES,
            "imputation": CONSISTENCY_IMPUTATION,
        },
    },
    "dilution_policy": {
        "scored_metric": "stored_shares_outstanding_yoy",
        "qoq_role": "evidence_only",
        "positive_change_above_50pct": "ASSUMED_GENUINE_DILUTION_BY_POLICY",
        "split_events": "evidence_only_no_second_adjustment",
        "data_quality_blocker": False,
    },
    "statuses": {
        "SCORE_FULL": "all_seven_components_observed",
        "SCORE_READY_ESTIMATED": "five_core_and_dilution_observed_consistency_imputed",
        "SCORE_LIMITED": "usable_current_ttm_but_canonical_score_incomplete",
        "SCORE_NOT_READY": "current_ttm_not_ready_or_availability_date_missing",
    },
    "dynamic_reweighting": False,
}
MODEL_FINGERPRINT = hashlib.sha256(
    json.dumps(MODEL_CONTRACT, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class ScorePaths:
    repo_root: Path
    artifact_root: Path
    canonical_db: Path
    analysis_db: Path
    market_db: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def score_paths(repo_root: Path, timestamp: str | None = None) -> ScorePaths:
    stamp = timestamp or utc_stamp()
    return ScorePaths(
        repo_root=repo_root,
        artifact_root=repo_root / "temp" / "fundamentals_v4_4_score" / stamp,
        canonical_db=repo_root / "data" / "fundamentals_v4.db",
        analysis_db=repo_root / "data" / "fundamentals_analysis.db",
        market_db=repo_root / "data" / "osakedata.db",
    )


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True) if readonly else sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def load_ttm_rows(path: Path) -> list[dict[str, Any]]:
    with connect(path, readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT t.*, s.current_ticker AS ticker
            FROM v4_ttm_values t
            JOIN security s ON s.security_id = t.security_id
            WHERE t.model_version = ?
            ORDER BY t.company_id, t.endpoint_fiscal_year,
                     CASE t.endpoint_fiscal_quarter
                         WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                     t.ttm_id
            """,
            (TTM_MODEL_VERSION,),
        ).fetchall()
    return [dict(row) for row in rows]


def load_split_events(path: Path) -> dict[str, list[dict[str, Any]]]:
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with connect(path, readonly=True) as conn:
        for row in conn.execute(
            "SELECT osake AS ticker, split_date, split_ratio, is_price_data_corrected FROM splits_data ORDER BY osake, split_date"
        ):
            events[str(row["ticker"])].append(dict(row))
    return events


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _continuous_chain(rows: Mapping[int, Mapping[str, Any]], start: int, end: int) -> bool:
    return all(ordinal in rows for ordinal in range(start, end + 1))


def _metric_levels(row: Mapping[str, Any], previous_year: Mapping[str, Any] | None, chain_ok: bool) -> dict[str, float | None]:
    revenue = _number(row.get("ttm_revenue"))
    ebit = _number(row.get("ttm_ebit"))
    fcf = _number(row.get("ttm_free_cashflow"))
    previous_revenue = _number(previous_year.get("ttm_revenue")) if previous_year and chain_ok else None
    previous_ebit = _number(previous_year.get("ttm_ebit")) if previous_year and chain_ok else None
    current_margin = safe_div(ebit, revenue) if revenue is not None and revenue > 0 else None
    previous_margin = safe_div(previous_ebit, previous_revenue) if previous_revenue is not None and previous_revenue > 0 else None
    return {
        "revenue_growth_yoy_ttm": safe_growth(revenue, previous_revenue),
        "ebit_margin_ttm": current_margin,
        "ebit_margin_direction": None if current_margin is None or previous_margin is None else current_margin - previous_margin,
        "fcf_margin_ttm": safe_div(fcf, revenue) if revenue is not None and revenue > 0 else None,
    }


def _split_matches(
    ticker: str,
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    events: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    if previous is None:
        return []
    start = str(previous["period_end"])
    end = str(current["period_end"])
    return [dict(event) for event in events.get(ticker, ()) if start < str(event["split_date"]) <= end]


def _evidence(
    *, metric: str, value: float | None, inputs: Mapping[str, Any], observed: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = {
        "metric": metric,
        "metric_value": value,
        "inputs": dict(inputs),
        "value_status": "OBSERVED" if observed else "MISSING",
    }
    if extra:
        evidence.update(extra)
    return evidence


def compute_score_rows(
    ttm_rows: Sequence[Mapping[str, Any]],
    split_events: Mapping[str, Sequence[Mapping[str, Any]]],
    *, generated_at: str,
    run_id: str,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in ttm_rows:
        grouped[int(row["company_id"])].append(row)
    output: list[dict[str, Any]] = []

    for company_rows in grouped.values():
        ordered = sorted(company_rows, key=lambda row: (fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]), int(row["ttm_id"])))
        by_ordinal = {fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]): row for row in ordered}
        levels: dict[int, dict[str, float | None]] = {}
        for row in ordered:
            ordinal = fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"])
            levels[ordinal] = _metric_levels(row, by_ordinal.get(ordinal - 4), _continuous_chain(by_ordinal, ordinal - 4, ordinal))

        for row in ordered:
            ordinal = fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"])
            previous_year = by_ordinal.get(ordinal - 4)
            previous_quarter = by_ordinal.get(ordinal - 1)
            chain_ok = _continuous_chain(by_ordinal, ordinal - 4, ordinal)
            current = levels[ordinal]
            shares = _number(row.get("shares_outstanding"))
            previous_shares = _number(previous_year.get("shares_outstanding")) if previous_year and chain_ok else None
            prior_quarter_shares = _number(previous_quarter.get("shares_outstanding")) if previous_quarter else None
            share_change_yoy = safe_growth(shares, previous_shares)
            share_change_qoq = safe_growth(shares, prior_quarter_shares)
            ticker = str(row["ticker"])
            split_matches = _split_matches(ticker, previous_year if chain_ok else None, row, split_events)
            consistency = consistency_points(ordinal, by_ordinal, levels)

            scores = {
                "REVENUE_GROWTH": piecewise_score(current["revenue_growth_yoy_ttm"], ANCHORS["revenue_growth_yoy_ttm"]),
                "EBIT_PROFITABILITY": piecewise_score(current["ebit_margin_ttm"], ANCHORS["ebit_margin_ttm"]),
                "EBIT_MARGIN_DIRECTION": piecewise_score(current["ebit_margin_direction"], ANCHORS["ebit_margin_direction"]),
                "FCF_MARGIN": piecewise_score(current["fcf_margin_ttm"], ANCHORS["fcf_margin_ttm"]),
                "BALANCE_SHEET_RESILIENCE": balance_points(row),
                "DILUTION": piecewise_score(share_change_yoy, ANCHORS["share_change_yoy"]),
                "CONSISTENCY": consistency,
            }
            evidence = {
                "REVENUE_GROWTH": _evidence(metric="revenue_growth_yoy_ttm", value=current["revenue_growth_yoy_ttm"], inputs={"ttm_revenue_current": row.get("ttm_revenue"), "ttm_revenue_4q_ago": previous_year.get("ttm_revenue") if previous_year and chain_ok else None}, observed=scores["REVENUE_GROWTH"] is not None, extra={"continuous_fiscal_chain": chain_ok}),
                "EBIT_PROFITABILITY": _evidence(metric="ebit_margin_ttm", value=current["ebit_margin_ttm"], inputs={"ttm_ebit": row.get("ttm_ebit"), "ttm_revenue": row.get("ttm_revenue")}, observed=scores["EBIT_PROFITABILITY"] is not None),
                "EBIT_MARGIN_DIRECTION": _evidence(metric="ebit_margin_direction", value=current["ebit_margin_direction"], inputs={"ebit_margin_current": current["ebit_margin_ttm"], "ebit_margin_4q_ago": levels.get(ordinal - 4, {}).get("ebit_margin_ttm") if chain_ok else None}, observed=scores["EBIT_MARGIN_DIRECTION"] is not None, extra={"continuous_fiscal_chain": chain_ok}),
                "FCF_MARGIN": _evidence(metric="fcf_margin_ttm", value=current["fcf_margin_ttm"], inputs={"ttm_free_cashflow": row.get("ttm_free_cashflow"), "ttm_revenue": row.get("ttm_revenue")}, observed=scores["FCF_MARGIN"] is not None),
                "BALANCE_SHEET_RESILIENCE": _evidence(metric="balance_sheet_resilience", value=scores["BALANCE_SHEET_RESILIENCE"], inputs={"cash": row.get("cash"), "total_debt": row.get("total_debt"), "ttm_ebit": row.get("ttm_ebit"), "ttm_free_cashflow": row.get("ttm_free_cashflow")}, observed=scores["BALANCE_SHEET_RESILIENCE"] is not None),
                "DILUTION": _evidence(metric="share_change_yoy", value=share_change_yoy, inputs={"shares_current": shares, "shares_4q_ago": previous_shares}, observed=scores["DILUTION"] is not None, extra={"share_change_qoq_evidence_only": share_change_qoq, "split_events_evidence_only": split_matches, "split_adjustment_applied": False, "large_positive_change_policy": "ASSUMED_GENUINE_DILUTION_BY_POLICY" if share_change_yoy is not None and share_change_yoy > 0.50 else "NOT_APPLICABLE"}),
                "CONSISTENCY": _evidence(metric="consistency_points", value=consistency, inputs={"required_contiguous_snapshots": "latest_4_else_3", "tolerances": CONSISTENCY_TOLERANCES}, observed=consistency is not None),
            }

            current_ready = int(row.get("core_ttm_ready") or 0) == 1 and bool(row.get("ttm_source_available_date"))
            imputed_components: list[str] = []
            if current_ready and all(scores[name] is not None for name in (*CORE_COMPONENTS, "DILUTION")) and scores["CONSISTENCY"] is None:
                scores["CONSISTENCY"] = CONSISTENCY_IMPUTATION
                imputed_components.append("CONSISTENCY")
                evidence["CONSISTENCY"].update({"metric_value": CONSISTENCY_IMPUTATION, "value_status": "IMPUTED", "imputation_basis": "locked_development_cutoff_median"})

            missing = [name for name in COMPONENTS if scores[name] is None]
            observed = [name for name in COMPONENTS if scores[name] is not None and name not in imputed_components]
            observed_points = sum(float(scores[name]) for name in observed)
            imputed_points = sum(float(scores[name]) for name in imputed_components)
            if not current_ready:
                status = "SCORE_NOT_READY"
                total_score = None
            elif not missing and not imputed_components:
                status = "SCORE_FULL"
                total_score = observed_points
            elif not missing and imputed_components == ["CONSISTENCY"]:
                status = "SCORE_READY_ESTIMATED"
                total_score = observed_points + imputed_points
            else:
                status = "SCORE_LIMITED"
                total_score = observed_points + imputed_points

            status_detail = {
                "missing_components": missing,
                "observed_components": observed,
                "imputed_components": imputed_components,
                "observed_component_count": len(observed),
                "observed_points": observed_points,
                "imputed_points": imputed_points,
                "ttm_core_ready": bool(row.get("core_ttm_ready")),
                "ttm_source_available_date": row.get("ttm_source_available_date"),
            }
            output.append({
                "company_id": int(row["company_id"]),
                "quarter_id": int(row["endpoint_quarter_id"]),
                "ticker": ticker,
                "period_end": row["period_end"],
                "model_version": MODEL_VERSION,
                "model_fingerprint": MODEL_FINGERPRINT,
                "total_score": total_score,
                "readiness_status": status,
                "missing_input_reason": json.dumps(status_detail, sort_keys=True, separators=(",", ":")),
                "generated_at_utc": generated_at,
                "run_id": run_id,
                "components": [
                    {"component_name": name, "component_score": scores[name], "evidence_json": json.dumps(evidence[name], sort_keys=True, separators=(",", ":"))}
                    for name in COMPONENTS
                ],
            })
    return sorted(output, key=lambda item: (item["company_id"], item["quarter_id"]))


def apply_scores(conn: sqlite3.Connection, rows: Sequence[Mapping[str, Any]], *, run_id: str, generated_at: str) -> dict[str, int]:
    before = int(conn.execute("SELECT COUNT(*) FROM score_result WHERE model_version=?", (MODEL_VERSION,)).fetchone()[0])
    conn.execute("DELETE FROM score_result WHERE model_version=?", (MODEL_VERSION,))
    conn.execute("DELETE FROM analysis_model_run WHERE model_type='SCORE' AND model_version=?", (MODEL_VERSION,))
    metadata = {"score_rows": len(rows), "model_contract": MODEL_CONTRACT}
    conn.execute(
        "INSERT INTO analysis_model_run(run_id,model_type,model_version,model_fingerprint,generated_at_utc,status,metadata_json) VALUES (?,?,?,?,?,?,?)",
        (run_id, "SCORE", MODEL_VERSION, MODEL_FINGERPRINT, generated_at, "COMPLETE", json.dumps(metadata, sort_keys=True, separators=(",", ":"))),
    )
    for row in rows:
        cursor = conn.execute(
            """INSERT INTO score_result(company_id,quarter_id,model_version,model_fingerprint,total_score,readiness_status,missing_input_reason,generated_at_utc,run_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            tuple(row[field] for field in ("company_id", "quarter_id", "model_version", "model_fingerprint", "total_score", "readiness_status", "missing_input_reason", "generated_at_utc", "run_id")),
        )
        score_result_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO score_component(score_result_id,component_name,component_score,evidence_json) VALUES (?,?,?,?)",
            [(score_result_id, component["component_name"], component["component_score"], component["evidence_json"]) for component in row["components"]],
        )
    after = int(conn.execute("SELECT COUNT(*) FROM score_result WHERE model_version=?", (MODEL_VERSION,)).fetchone()[0])
    return {"rows_before": before, "rows_after": after, "rows_written": len(rows)}


def score_fingerprint(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = [tuple(row) for row in conn.execute(
        """SELECT company_id,quarter_id,model_version,model_fingerprint,total_score,readiness_status,missing_input_reason
           FROM score_result WHERE model_version=? ORDER BY company_id,quarter_id""",
        (MODEL_VERSION,),
    )]
    components = [tuple(row) for row in conn.execute(
        """SELECT r.company_id,r.quarter_id,c.component_name,c.component_score,c.evidence_json
           FROM score_component c JOIN score_result r USING(score_result_id)
           WHERE r.model_version=? ORDER BY r.company_id,r.quarter_id,c.component_name""",
        (MODEL_VERSION,),
    )]
    payload = json.dumps({"rows": rows, "components": components}, sort_keys=True, separators=(",", ":"), default=str)
    return {"row_count": len(rows), "component_count": len(components), "fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_sample(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = ("company_id", "ticker", "quarter_id", "period_end", "total_score", "readiness_status", "missing_input_reason")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows[:1000])


def run_score(paths: ScorePaths, *, write_production: bool = True) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=False)
    generated_at = utc_now()
    run_id = f"SCORE_V1_{utc_stamp()}"
    canonical_before = canonical_financial_fingerprint(paths.canonical_db)
    with connect(paths.canonical_db, readonly=True) as conn:
        ttm_before = ttm_fingerprints(conn)
    with connect(paths.analysis_db, readonly=True) as conn:
        lifecycle_before = int(conn.execute("SELECT COUNT(*) FROM lifecycle_result").fetchone()[0])
        valuation_before = int(conn.execute("SELECT COUNT(*) FROM valuation_result").fetchone()[0])
    rows = compute_score_rows(load_ttm_rows(paths.canonical_db), load_split_events(paths.market_db), generated_at=generated_at, run_id=run_id)

    rehearsal_db = paths.artifact_root / "rehearsal_fundamentals_analysis.db"
    shutil.copy2(paths.analysis_db, rehearsal_db)
    with connect(rehearsal_db) as conn:
        rehearsal_write = apply_scores(conn, rows, run_id=run_id, generated_at=generated_at)
        rehearsal_fp = score_fingerprint(conn)
        conn.commit()

    replay = {"performed": False, "fingerprints_identical": False}
    production_write = {"rows_before": 0, "rows_after": 0, "rows_written": 0}
    if write_production:
        with connect(paths.analysis_db) as conn:
            production_write = apply_scores(conn, rows, run_id=run_id, generated_at=generated_at)
            first = score_fingerprint(conn)
            conn.commit()
        with connect(paths.analysis_db) as conn:
            apply_scores(conn, rows, run_id=run_id, generated_at=generated_at)
            second = score_fingerprint(conn)
            conn.commit()
        replay = {"performed": True, "fingerprints_identical": first == second, "first": first, "second": second}

    canonical_after = canonical_financial_fingerprint(paths.canonical_db)
    with connect(paths.canonical_db, readonly=True) as conn:
        ttm_after = ttm_fingerprints(conn)
    with connect(paths.analysis_db, readonly=True) as conn:
        status_counts = dict(conn.execute("SELECT readiness_status,COUNT(*) FROM score_result WHERE model_version=? GROUP BY readiness_status", (MODEL_VERSION,)).fetchall()) if write_production else dict(Counter(row["readiness_status"] for row in rows))
        lifecycle_after = int(conn.execute("SELECT COUNT(*) FROM lifecycle_result").fetchone()[0])
        valuation_after = int(conn.execute("SELECT COUNT(*) FROM valuation_result").fetchone()[0])
        foreign_key_errors = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    integrity = {
        "canonical_financial_unchanged": canonical_before == canonical_after,
        "ttm_unchanged": ttm_before == ttm_after,
        "lifecycle_unchanged": lifecycle_before == lifecycle_after,
        "valuation_unchanged": valuation_before == valuation_after,
        "foreign_key_errors": foreign_key_errors,
        "quick_check": quick_check,
    }
    complete = all((integrity["canonical_financial_unchanged"], integrity["ttm_unchanged"], integrity["lifecycle_unchanged"], integrity["valuation_unchanged"], foreign_key_errors == 0, quick_check == "ok", replay["fingerprints_identical"] if write_production else True))
    summary = {
        "classification": "V4_SCORE_V1_IMPLEMENTATION_COMPLETE" if complete else "V4_SCORE_V1_IMPLEMENTATION_BLOCKED",
        "artifact_root": str(paths.artifact_root),
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "input_ttm_model_version": TTM_MODEL_VERSION,
        "computed_rows": len(rows),
        "status_counts": status_counts,
        "production": production_write,
        "rehearsal": {**rehearsal_write, **rehearsal_fp},
        "replay": replay,
        "integrity": integrity,
        "schema_changes": 0,
        "lifecycle_writes": 0,
        "valuation_writes": 0,
        "swingmaster_runtime_dependency": 0,
    }
    _write_json(paths.artifact_root / "score_v1_summary.json", summary)
    _write_json(paths.artifact_root / "score_v1_model_contract.json", MODEL_CONTRACT)
    _write_sample(paths.artifact_root / "score_v1_sample.csv", rows)
    return summary
