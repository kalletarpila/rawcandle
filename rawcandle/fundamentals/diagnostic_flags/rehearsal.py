from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from rawcandle.fundamentals.diagnostic_flags.engine import (
    FLAG_NAMES,
    MODEL_CONTRACT,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    FlagStatus,
    canonical_json,
    evaluate_diagnostic_flags,
)
from rawcandle.fundamentals.diagnostic_flags.source import (
    DiagnosticSource,
    DiagnosticSourceRow,
    ReadOnlyDiagnosticPaths,
    latest_fresh_source_rows,
    load_diagnostic_source,
)


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str] | None = None) -> None:
    materialized = list(rows)
    columns = fields or (list(materialized[0]) if materialized else ["status"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized or [{"status": "NO_ROWS"}])


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _metric(evidence: dict[str, Any], flag: str) -> float | None:
    if flag == "VALUATION_YIELD_OUTLIER":
        median_value = evidence.get("median_yield")
        maximum_value = evidence.get("maximum_yield")
        if median_value is None or maximum_value is None:
            return None
        return max(float(median_value) - 0.25, float(maximum_value) - 0.50)
    value = evidence.get("metric_value")
    return None if value is None else float(value)


def _run_once(
    source: DiagnosticSource,
    path: Path,
    *,
    collect: bool,
    current_ids: set[int] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    digest = hashlib.sha256()
    compact: list[dict[str, Any]] = []
    with path.open("wb") as handle:
        for source_row in source.rows:
            endpoint = source_row.diagnostic_input.current
            for evaluation in evaluate_diagnostic_flags(source_row.diagnostic_input):
                result = evaluation.to_dict()
                payload = {
                    "ticker": source_row.ticker,
                    "sector": source_row.sector,
                    "industry": source_row.industry,
                    "lifecycle": source_row.lifecycle,
                    "lifecycle_status": source_row.lifecycle_status,
                    "market_cap": source_row.market_cap,
                    "fiscal_year": endpoint.fiscal_year,
                    "fiscal_quarter": endpoint.fiscal_quarter,
                    "period_end": endpoint.period_end,
                    **result,
                }
                line = (canonical_json(payload) + "\n").encode("ascii")
                handle.write(line)
                digest.update(line)
                if collect:
                    compact.append(
                        {
                            "company_id": endpoint.company_id,
                            "quarter_id": endpoint.quarter_id,
                            "ticker": source_row.ticker,
                            "fiscal_year": endpoint.fiscal_year,
                            "fiscal_quarter": endpoint.fiscal_quarter,
                            "period_end": endpoint.period_end,
                            "available_date": evaluation.effective_available_date,
                            "flag": evaluation.flag_name,
                            "status": evaluation.status.value,
                            "reason_code": evaluation.reason_code,
                            "triggered": evaluation.triggered,
                            "metric_value": _metric(result["evidence"], evaluation.flag_name),
                            "sector": source_row.sector or "UNKNOWN",
                            "industry": source_row.industry or "UNKNOWN",
                            "lifecycle": source_row.lifecycle or "UNKNOWN",
                            "market_cap": source_row.market_cap,
                            "evidence_json": canonical_json(result["evidence"])
                            if evaluation.triggered or endpoint.quarter_id in (current_ids or set())
                            else "",
                        }
                    )
    return digest.hexdigest(), compact


def _distribution(records: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for flag in FLAG_NAMES:
        selected = [row for row in records if row["flag"] == flag]
        statuses = Counter(str(row["status"]) for row in selected)
        evaluated = statuses[FlagStatus.FLAGGED.value] + statuses[FlagStatus.CLEAR.value]
        flagged = statuses[FlagStatus.FLAGGED.value]
        rows.append(
            {
                "scope": scope,
                "flag": flag,
                "observations": len(selected),
                "evaluated": evaluated,
                "flagged": flagged,
                "clear": statuses[FlagStatus.CLEAR.value],
                "not_ready": statuses[FlagStatus.NOT_READY.value],
                "not_applicable": statuses[FlagStatus.NOT_APPLICABLE.value],
                "flagged_pct_of_evaluated": 100.0 * flagged / evaluated if evaluated else None,
            }
        )
    return rows


def _bias(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(str(row["flag"]), str(row[field]))].append(row)
    output = []
    for (flag, group), values in sorted(grouped.items()):
        evaluated = sum(row["status"] in (FlagStatus.FLAGGED.value, FlagStatus.CLEAR.value) for row in values)
        flagged = sum(row["status"] == FlagStatus.FLAGGED.value for row in values)
        if flagged:
            output.append({"flag": flag, field: group, "evaluated": evaluated, "flagged": flagged, "flagged_pct": 100.0 * flagged / evaluated if evaluated else None})
    return output


def _size(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    number = float(value)
    if number < 300_000_000:
        return "MICRO"
    if number < 2_000_000_000:
        return "SMALL"
    if number < 10_000_000_000:
        return "MID"
    return "LARGE"


def _boundary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for flag in FLAG_NAMES:
        evaluated = [row for row in records if row["flag"] == flag and row["metric_value"] is not None and row["status"] in (FlagStatus.FLAGGED.value, FlagStatus.CLEAR.value)]
        clear = [row for row in evaluated if row["status"] == FlagStatus.CLEAR.value]
        flagged = [row for row in evaluated if row["status"] == FlagStatus.FLAGGED.value]
        threshold = -0.02 if flag == "RECENT_MARGIN_DECELERATION_REVIEW" else 0.0 if flag == "VALUATION_YIELD_OUTLIER" else {
            "ABRUPT_FUNDAMENTAL_SHIFT": 0.20,
            "EARNINGS_CASH_DIVERGENCE_CANDIDATE": 0.20,
            "CAPEX_INTENSITY_SHIFT_CANDIDATE": 0.10,
            "NET_DEBT_SHIFT_CANDIDATE": 0.50,
            "WORKING_CAPITAL_SHIFT_CANDIDATE": 0.10,
        }[flag]
        below = [row for row in evaluated if float(row["metric_value"]) < threshold]
        exact = [row for row in evaluated if abs(float(row["metric_value"]) - threshold) <= 1e-15]
        above = [row for row in evaluated if float(row["metric_value"]) > threshold]
        if flag == "RECENT_MARGIN_DECELERATION_REVIEW":
            strongest = min(flagged, key=lambda row: float(row["metric_value"]), default=None)
        else:
            strongest = max(flagged, key=lambda row: float(row["metric_value"]), default=None)
        selected: list[tuple[str, dict[str, Any] | None]] = [
            ("IMMEDIATELY_BELOW", max(below, key=lambda row: float(row["metric_value"]), default=None)),
            ("EXACT_BOUNDARY", min(exact, key=lambda row: (str(row["ticker"]), int(row["quarter_id"])), default=None)),
            ("IMMEDIATELY_ABOVE", min(above, key=lambda row: float(row["metric_value"]), default=None)),
            ("STRONGEST", strongest),
            ("NOT_READY", next((row for row in records if row["flag"] == flag and row["status"] == FlagStatus.NOT_READY.value), None)),
            ("NOT_APPLICABLE", next((row for row in records if row["flag"] == flag and row["status"] == FlagStatus.NOT_APPLICABLE.value), None)),
        ]
        for sample_type, row in selected:
            output.append({"flag": flag, "sample_type": sample_type, **({key: row.get(key) for key in ("ticker", "quarter_id", "period_end", "status", "reason_code", "metric_value", "sector", "industry", "lifecycle")} if row else {"ticker": "", "quarter_id": "", "period_end": "", "status": "NO_EXACT_OBSERVATION", "reason_code": "", "metric_value": "", "sector": "", "industry": "", "lifecycle": ""})})
    return output


def _union_and_overlap(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    by_company: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in records:
        by_company[int(row["company_id"])][str(row["flag"])] = row
    cohort = {
        company_id: flags
        for company_id, flags in by_company.items()
        if flags["ABRUPT_FUNDAMENTAL_SHIFT"]["status"] in (FlagStatus.FLAGGED.value, FlagStatus.CLEAR.value)
    }
    buckets = Counter()
    maximum = 0
    sets = {flag: set() for flag in FLAG_NAMES}
    for company_id, flags in cohort.items():
        count = sum(row["status"] == FlagStatus.FLAGGED.value for row in flags.values())
        maximum = max(maximum, count)
        buckets["0" if count == 0 else "1" if count == 1 else "2" if count == 2 else "3_OR_MORE"] += 1
        for flag, row in flags.items():
            if row["status"] == FlagStatus.FLAGGED.value:
                sets[flag].add(company_id)
    total = len(cohort)
    union_rows = [{"bucket": key, "companies": buckets[key], "pct": 100.0 * buckets[key] / total if total else None} for key in ("0", "1", "2", "3_OR_MORE")]
    union = total - buckets["0"]
    union_rows.append({"bucket": "AT_LEAST_ONE", "companies": union, "pct": 100.0 * union / total if total else None})
    overlap = []
    for left in FLAG_NAMES:
        for right in FLAG_NAMES:
            intersection = len(sets[left] & sets[right])
            union_count = len(sets[left] | sets[right])
            overlap.append({"left_flag": left, "right_flag": right, "intersection": intersection, "union": union_count, "jaccard": intersection / union_count if union_count else 0.0})
    return union_rows, overlap, {"cohort": total, "at_least_one": union, "union_pct": 100.0 * union / total if total else None, "maximum_flags": maximum, "more_than_half": union > total / 2 if total else False}


def run_full_history_rehearsal(
    paths: ReadOnlyDiagnosticPaths,
    output_dir: Path,
    *,
    as_of: date,
    freshness_days: int = 180,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source1 = load_diagnostic_source(paths)
    current_source = latest_fresh_source_rows(source1.rows, as_of=as_of, freshness_days=freshness_days)
    current_ids = {row.diagnostic_input.current.quarter_id for row in current_source}
    replay1, records = _run_once(
        source1,
        output_dir / "all_flag_evaluations_replay1.jsonl",
        collect=True,
        current_ids=current_ids,
    )
    source2 = load_diagnostic_source(paths)
    replay2, _ = _run_once(source2, output_dir / "all_flag_evaluations_replay2.jsonl", collect=False)
    if replay1 != replay2:
        raise RuntimeError("DIAGNOSTIC_REPLAY_MISMATCH")

    current = [row for row in records if int(row["quarter_id"]) in current_ids]
    flagged = [row for row in records if row["status"] == FlagStatus.FLAGGED.value]
    current_flagged = [row for row in current if row["status"] == FlagStatus.FLAGGED.value]
    _write_csv(output_dir / "flagged_only.csv", flagged)
    _write_csv(output_dir / "current_fresh_flag_results.csv", current)
    _write_csv(output_dir / "flag_status_distribution.csv", _distribution(records, "FULL_HISTORY") + _distribution(current, "CURRENT_FRESH"))
    current_distribution = _distribution(current, "CURRENT_FRESH")
    _write_csv(output_dir / "flag_current_distribution.csv", current_distribution)
    union_rows, overlap, union_summary = _union_and_overlap(current)
    _write_csv(output_dir / "flag_union_distribution.csv", union_rows)
    _write_csv(output_dir / "flag_overlap_matrix.csv", overlap)
    _write_csv(output_dir / "flag_boundary_samples.csv", _boundary(current))
    _write_csv(output_dir / "flag_sector_bias.csv", _bias(current, "sector"))
    _write_csv(output_dir / "flag_industry_bias.csv", _bias(current, "industry"))
    _write_csv(output_dir / "flag_lifecycle_bias.csv", _bias(current, "lifecycle"))
    size_records = [{**row, "size_band": _size(row["market_cap"])} for row in current]
    _write_csv(output_dir / "flag_company_size_bias.csv", _bias(size_records, "size_band"))

    cases: dict[str, dict[str, Any]] = {}
    for ticker in ("CRMD", "APD"):
        ticker_rows = [row for row in current if row["ticker"] == ticker]
        cases[ticker] = {row["flag"]: {key: row[key] for key in ("status", "reason_code", "metric_value", "evidence_json")} for row in ticker_rows}
    lines = ["# CRMD and APD regression", "", "Numerical diagnostics only; no causal event inference.", ""]
    for ticker in ("CRMD", "APD"):
        lines.extend([f"## {ticker}", "", "| Flag | Status | Metric |", "|---|---|---:|"])
        for flag in FLAG_NAMES:
            row = cases[ticker].get(flag, {})
            lines.append(f"| `{flag}` | {row.get('status', 'MISSING')} | {row.get('metric_value', '')} |")
        lines.append("")
    lines.append("`ncfbus`, impairment, acquisition and project-exit causes are not engine inputs or outputs.")
    (output_dir / "crmd_apd_regression.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    result_fingerprint = hashlib.sha256((canonical_json({"replay_sha256": replay1, "model_fingerprint": MODEL_FINGERPRINT}) + "\n").encode("ascii")).hexdigest()
    fingerprints = {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "source_fingerprint_replay1": source1.source_fingerprint,
        "source_fingerprint_replay2": source2.source_fingerprint,
        "source_model_fingerprints": dict(source1.source_model_fingerprints),
        "result_fingerprint": result_fingerprint,
        "replay1_sha256": replay1,
        "replay2_sha256": replay2,
        "byte_identical_replay": replay1 == replay2,
    }
    _write_json(output_dir / "fingerprints.json", fingerprints)
    _write_json(output_dir / "model_contract.json", MODEL_CONTRACT)
    summary = {
        "as_of": as_of.isoformat(),
        "freshness_days": freshness_days,
        "source_rows": len(source1.rows),
        "evaluation_rows": len(records),
        "flagged_rows": len(flagged),
        "current_source_rows": len(current_source),
        "current_evaluation_rows": len(current),
        "current_flagged_rows": len(current_flagged),
        "current_distribution": current_distribution,
        "union": union_summary,
        "fingerprints": fingerprints,
        "cases": cases,
    }
    _write_json(output_dir / "rehearsal_summary.json", summary)
    return summary
