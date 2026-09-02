from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.score.methodology import (
    ANCHORS,
    balance_points,
    clamp,
    fiscal_ordinal,
    piecewise_score,
    safe_div,
    safe_growth,
)
from rawcandle.fundamentals.ttm.engine import canonical_financial_fingerprint, ttm_fingerprints


MODEL_VERSION = "SIMPLE_FUNDAMENTAL_SCORE_V1"
TTM_MODEL_VERSION = "V4_TTM_EBIT_FIRST_V1"
COMPONENTS = (
    "REVENUE_GROWTH",
    "EBIT_PROFITABILITY",
    "EBIT_MARGIN_DIRECTION",
    "FCF_MARGIN",
    "BALANCE_SHEET_RESILIENCE",
    "DILUTION",
    "FUNDAMENTAL_TRAJECTORY",
)
TRAJECTORY_TOLERANCES = {
    "revenue_qoq_ttm": 0.05,
    "ebit_margin_change_qoq": 0.05,
    "fcf_change_to_prior_revenue": 0.10,
}
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
        "FUNDAMENTAL_TRAJECTORY": {
            "maximum": 10.0,
            "window_ttm_snapshots": 5,
            "qoq_transitions": 4,
            "neutral_points": 5.0,
            "tolerances": TRAJECTORY_TOLERANCES,
            "imputation": None,
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


def trajectory_points(
    endpoint_ordinal: int,
    rows_by_ordinal: Mapping[int, Mapping[str, Any]],
) -> tuple[float | None, dict[str, Any]]:
    ordinals = list(range(endpoint_ordinal - 4, endpoint_ordinal + 1))
    window = [rows_by_ordinal.get(ordinal) for ordinal in ordinals]
    base_evidence: dict[str, Any] = {
        "required_ttm_snapshots": 5,
        "required_qoq_transitions": 4,
        "fiscal_ordinals": ordinals,
        "tolerances": TRAJECTORY_TOLERANCES,
    }
    if any(row is None for row in window):
        return None, {**base_evidence, "blocker": "NON_CONTIGUOUS_FIVE_SNAPSHOT_WINDOW"}
    snapshots = [row for row in window if row is not None]
    if any(int(row.get("core_ttm_ready") or 0) != 1 for row in snapshots):
        return None, {**base_evidence, "blocker": "WINDOW_TTM_NOT_CORE_READY"}
    if any(_number(row.get("ttm_revenue")) is None or float(row["ttm_revenue"]) <= 0.0 for row in snapshots):
        return None, {**base_evidence, "blocker": "WINDOW_REVENUE_NOT_POSITIVE"}
    if any(_number(row.get("ttm_ebit")) is None or _number(row.get("ttm_free_cashflow")) is None for row in snapshots):
        return None, {**base_evidence, "blocker": "WINDOW_EBIT_OR_FCF_MISSING"}

    transitions: list[dict[str, Any]] = []
    metric_points: dict[str, list[float]] = defaultdict(list)
    for previous, current in zip(snapshots, snapshots[1:]):
        previous_revenue = float(previous["ttm_revenue"])
        current_revenue = float(current["ttm_revenue"])
        revenue_signal = current_revenue / previous_revenue - 1.0
        previous_ebit_margin = float(previous["ttm_ebit"]) / previous_revenue
        current_ebit_margin = float(current["ttm_ebit"]) / current_revenue
        ebit_signal = current_ebit_margin - previous_ebit_margin
        fcf_signal = (float(current["ttm_free_cashflow"]) - float(previous["ttm_free_cashflow"])) / previous_revenue
        signals = {
            "revenue_qoq_ttm": revenue_signal,
            "ebit_margin_change_qoq": ebit_signal,
            "fcf_change_to_prior_revenue": fcf_signal,
        }
        points = {
            metric: clamp(5.0 + 5.0 * signal / TRAJECTORY_TOLERANCES[metric], 0.0, 10.0)
            for metric, signal in signals.items()
        }
        for metric, value in points.items():
            metric_points[metric].append(value)
        transitions.append({
            "from_quarter_id": previous["endpoint_quarter_id"],
            "to_quarter_id": current["endpoint_quarter_id"],
            "from_period_end": previous["period_end"],
            "to_period_end": current["period_end"],
            "signals": signals,
            "points": points,
        })
    metric_averages = {metric: mean(values) for metric, values in metric_points.items()}
    total = mean(metric_averages.values())
    return total, {
        **base_evidence,
        "blocker": None,
        "transition_scoring": "clamp(5 + 5 * signal / tolerance, 0, 10)",
        "metric_average_points": metric_averages,
        "transitions": transitions,
    }


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
            trajectory, trajectory_evidence = trajectory_points(ordinal, by_ordinal)

            scores = {
                "REVENUE_GROWTH": piecewise_score(current["revenue_growth_yoy_ttm"], ANCHORS["revenue_growth_yoy_ttm"]),
                "EBIT_PROFITABILITY": piecewise_score(current["ebit_margin_ttm"], ANCHORS["ebit_margin_ttm"]),
                "EBIT_MARGIN_DIRECTION": piecewise_score(current["ebit_margin_direction"], ANCHORS["ebit_margin_direction"]),
                "FCF_MARGIN": piecewise_score(current["fcf_margin_ttm"], ANCHORS["fcf_margin_ttm"]),
                "BALANCE_SHEET_RESILIENCE": balance_points(row),
                "DILUTION": piecewise_score(share_change_yoy, ANCHORS["share_change_yoy"]),
                "FUNDAMENTAL_TRAJECTORY": trajectory,
            }
            evidence = {
                "REVENUE_GROWTH": _evidence(metric="revenue_growth_yoy_ttm", value=current["revenue_growth_yoy_ttm"], inputs={"ttm_revenue_current": row.get("ttm_revenue"), "ttm_revenue_4q_ago": previous_year.get("ttm_revenue") if previous_year and chain_ok else None}, observed=scores["REVENUE_GROWTH"] is not None, extra={"continuous_fiscal_chain": chain_ok}),
                "EBIT_PROFITABILITY": _evidence(metric="ebit_margin_ttm", value=current["ebit_margin_ttm"], inputs={"ttm_ebit": row.get("ttm_ebit"), "ttm_revenue": row.get("ttm_revenue")}, observed=scores["EBIT_PROFITABILITY"] is not None),
                "EBIT_MARGIN_DIRECTION": _evidence(metric="ebit_margin_direction", value=current["ebit_margin_direction"], inputs={"ebit_margin_current": current["ebit_margin_ttm"], "ebit_margin_4q_ago": levels.get(ordinal - 4, {}).get("ebit_margin_ttm") if chain_ok else None}, observed=scores["EBIT_MARGIN_DIRECTION"] is not None, extra={"continuous_fiscal_chain": chain_ok}),
                "FCF_MARGIN": _evidence(metric="fcf_margin_ttm", value=current["fcf_margin_ttm"], inputs={"ttm_free_cashflow": row.get("ttm_free_cashflow"), "ttm_revenue": row.get("ttm_revenue")}, observed=scores["FCF_MARGIN"] is not None),
                "BALANCE_SHEET_RESILIENCE": _evidence(metric="balance_sheet_resilience", value=scores["BALANCE_SHEET_RESILIENCE"], inputs={"cash": row.get("cash"), "total_debt": row.get("total_debt"), "ttm_ebit": row.get("ttm_ebit"), "ttm_free_cashflow": row.get("ttm_free_cashflow")}, observed=scores["BALANCE_SHEET_RESILIENCE"] is not None),
                "DILUTION": _evidence(metric="share_change_yoy", value=share_change_yoy, inputs={"shares_current": shares, "shares_4q_ago": previous_shares}, observed=scores["DILUTION"] is not None, extra={"share_change_qoq_evidence_only": share_change_qoq, "split_events_evidence_only": split_matches, "split_adjustment_applied": False, "large_positive_change_policy": "ASSUMED_GENUINE_DILUTION_BY_POLICY" if share_change_yoy is not None and share_change_yoy > 0.50 else "NOT_APPLICABLE"}),
                "FUNDAMENTAL_TRAJECTORY": _evidence(metric="fundamental_trajectory_points", value=trajectory, inputs={"window": "five_contiguous_ttm_snapshots", "transition_count": 4}, observed=trajectory is not None, extra=trajectory_evidence),
            }

            current_ready = int(row.get("core_ttm_ready") or 0) == 1 and bool(row.get("ttm_source_available_date"))
            imputed_components: list[str] = []

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


def refresh_lifecycle_after_score(paths: ScorePaths) -> dict[str, Any]:
    from rawcandle.fundamentals.lifecycle.revised_history import refresh_revised_history

    return asdict(refresh_revised_history(paths.canonical_db, paths.analysis_db))


def refresh_valuation_after_lifecycle(paths: ScorePaths) -> dict[str, Any]:
    from rawcandle.fundamentals.valuation.production import refresh_valuation

    return asdict(refresh_valuation(
        paths.canonical_db,
        paths.analysis_db,
        paths.market_db,
        calculated_at=utc_now(),
    ))


def refresh_relative_position_after_valuation(
    paths: ScorePaths,
    *,
    model_fingerprint: str,
) -> dict[str, Any]:
    from rawcandle.fundamentals.relative_position.production import refresh_relative_position

    return asdict(refresh_relative_position(
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        market_db=paths.market_db,
        taxonomy_db=paths.repo_root / "data" / "analysis.db",
        snapshot_date=datetime.now(timezone.utc).date().isoformat(),
        model_fingerprint=model_fingerprint,
        applied_at_utc=utc_now(),
    ))


def refresh_delta_after_valuation(
    paths: ScorePaths,
    *,
    model_fingerprint: str,
    persistence_version: str,
    layout_fingerprint: str,
) -> dict[str, Any]:
    from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT as DELTA_MODEL_FINGERPRINT
    from rawcandle.fundamentals.delta.persistence import LAYOUT_FINGERPRINT, PERSISTENCE_VERSION
    from rawcandle.fundamentals.delta.production import refresh_delta

    if model_fingerprint != DELTA_MODEL_FINGERPRINT:
        raise ValueError("DELTA_MODEL_FINGERPRINT_MISMATCH")
    if persistence_version != PERSISTENCE_VERSION:
        raise ValueError("DELTA_PERSISTENCE_VERSION_MISMATCH")
    if layout_fingerprint != LAYOUT_FINGERPRINT:
        raise ValueError("DELTA_LAYOUT_FINGERPRINT_MISMATCH")
    return asdict(refresh_delta(
        analysis_db=paths.analysis_db,
        canonical_db=paths.canonical_db,
        applied_at_utc=utc_now(),
    ))


class PostValuationRefreshError(RuntimeError):
    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__("POST_VALUATION_REFRESH_STAGES_FAILED")
        self.report = report


def refresh_delta_then_relative_position(
    paths: ScorePaths,
    *,
    delta_model_fingerprint: str,
    delta_persistence_version: str,
    delta_layout_fingerprint: str,
    relative_position_model_fingerprint: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    failed = []
    try:
        delta = refresh_delta_after_valuation(
            paths,
            model_fingerprint=delta_model_fingerprint,
            persistence_version=delta_persistence_version,
            layout_fingerprint=delta_layout_fingerprint,
        )
        report["delta_refresh"] = {"status": "COMPLETE", "scope": "FULL_HISTORY", **delta}
    except Exception as exc:
        failed.append("DELTA")
        report["delta_refresh"] = {
            "status": "FAILED", "scope": "FULL_HISTORY", "error": str(exc),
        }
    try:
        relative = refresh_relative_position_after_valuation(
            paths, model_fingerprint=relative_position_model_fingerprint,
        )
        report["relative_position_refresh"] = {
            "status": "COMPLETE", "scope": "FULL_UNIVERSE", **relative,
        }
    except Exception as exc:
        failed.append("RELATIVE_POSITION")
        report["relative_position_refresh"] = {
            "status": "FAILED", "scope": "FULL_UNIVERSE", "error": str(exc),
        }
    report["failed_stages"] = failed
    if failed:
        raise PostValuationRefreshError(report)
    return report


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_sample(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = ("company_id", "ticker", "quarter_id", "period_end", "total_score", "readiness_status", "missing_input_reason")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows[:1000])


def run_score(
    paths: ScorePaths,
    *,
    write_production: bool = True,
    production_preflight: Mapping[str, Any] | None = None,
    delta_model_fingerprint: str | None = None,
    delta_persistence_version: str | None = None,
    delta_layout_fingerprint: str | None = None,
    relative_position_model_fingerprint: str | None = None,
) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=False)
    if production_preflight is not None:
        _write_json(paths.artifact_root / "production_preflight.json", production_preflight)
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
    if write_production and complete:
        try:
            summary["lifecycle_refresh"] = {
                "status": "COMPLETE",
                **refresh_lifecycle_after_score(paths),
            }
        except Exception as exc:
            summary["classification"] = "V4_SCORE_V1_IMPLEMENTATION_BLOCKED"
            summary["lifecycle_refresh"] = {
                "status": "FAILED",
                "error": str(exc),
            }
            _write_json(paths.artifact_root / "score_v1_summary.json", summary)
            raise RuntimeError("POST_SCORE_LIFECYCLE_REFRESH_FAILED") from exc
        try:
            summary["valuation_refresh"] = {
                "status": "COMPLETE",
                "scope": "FULL_UNIVERSE_FALLBACK",
                **refresh_valuation_after_lifecycle(paths),
            }
            summary["valuation_writes"] = summary["valuation_refresh"]["rows_inserted"]
        except Exception as exc:
            summary["classification"] = "V4_SCORE_V1_IMPLEMENTATION_BLOCKED"
            summary["valuation_refresh"] = {
                "status": "FAILED",
                "scope": "FULL_UNIVERSE_FALLBACK",
                "error": str(exc),
            }
            _write_json(paths.artifact_root / "score_v1_summary.json", summary)
            raise RuntimeError("POST_LIFECYCLE_VALUATION_REFRESH_FAILED") from exc
        try:
            if None in (
                delta_model_fingerprint, delta_persistence_version,
                delta_layout_fingerprint, relative_position_model_fingerprint,
            ):
                raise ValueError("DELTA_AND_RELATIVE_POSITION_CONTRACT_REQUIRED")
            post_valuation = refresh_delta_then_relative_position(
                paths,
                delta_model_fingerprint=str(delta_model_fingerprint),
                delta_persistence_version=str(delta_persistence_version),
                delta_layout_fingerprint=str(delta_layout_fingerprint),
                relative_position_model_fingerprint=str(relative_position_model_fingerprint),
            )
            summary.update(post_valuation)
            summary["delta_writes"] = (
                summary["delta_refresh"]["apply"]["total_inserted"]
                + summary["delta_refresh"]["apply"]["total_updated"]
                + summary["delta_refresh"]["apply"]["total_deleted"]
            )
            summary["relative_position_writes"] = summary["relative_position_refresh"]["apply"]["result_rows_inserted"]
        except PostValuationRefreshError as exc:
            summary["classification"] = "V4_SCORE_V1_IMPLEMENTATION_BLOCKED"
            summary.update(exc.report)
            _write_json(paths.artifact_root / "score_v1_summary.json", summary)
            raise RuntimeError("POST_VALUATION_REFRESH_FAILED") from exc
    else:
        summary["lifecycle_refresh"] = {"status": "SKIPPED"}
        summary["valuation_refresh"] = {"status": "SKIPPED"}
        summary["delta_refresh"] = {"status": "SKIPPED"}
        summary["relative_position_refresh"] = {"status": "SKIPPED"}
    _write_json(paths.artifact_root / "score_v1_summary.json", summary)
    _write_json(paths.artifact_root / "score_v1_model_contract.json", MODEL_CONTRACT)
    _write_sample(paths.artifact_root / "score_v1_sample.csv", rows)
    return summary
