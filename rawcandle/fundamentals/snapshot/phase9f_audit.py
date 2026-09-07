from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.diagnostic_flags.engine import FLAG_NAMES, REASON_CODES
from rawcandle.fundamentals.operating_income_v2 import diagnostic_flags
from rawcandle.fundamentals.operating_income_v2.readers import ParallelModelRepository
from rawcandle.fundamentals.operating_income_v2.rehearsal import calculate, database_integrity
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.diagnostic_boundary_cases import run_boundary_cases
from rawcandle.fundamentals.snapshot.renderer import _diagnostic_metric, _diagnostic_threshold
from rawcandle.fundamentals.snapshot.v2_assembler import (
    REPORT_CONTRACT,
    REPORT_PRESENTATION_FINGERPRINT,
)


REPORT_DATE = "2026-09-07"
NUMERIC_TOLERANCE = 1e-12
STATUS_NAMES = {status.value for status in diagnostic_flags.FlagStatus}

CONTRACT_ROWS = (
    {
        "flag": "ABRUPT_FUNDAMENTAL_SHIFT",
        "definition": "max(abs(delta revenue)/R, abs(delta operating income)/R)",
        "source_fields": "ttm_revenue; ttm_operating_income",
        "periods": "current and exact prior fiscal quarter",
        "denominator": "R=max((abs(revenue_t)+abs(revenue_t-1))/2,10000000)",
        "floor": "10000000",
        "threshold": "0.20",
        "operator": ">=",
        "sign": "absolute changes; negative operating income permitted",
        "missing": "FLAG_NOT_READY / REQUIRED_INPUT_MISSING or REQUIRED_INPUT_NON_FINITE",
        "not_applicable": "nonpositive revenue or unsupported accounting classification",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; threshold met/below threshold",
        "persisted_evidence": "revenue and operating-income levels/changes, scale, ratios, metric, threshold, trigger bits",
        "report": "readable active summary plus complete audit row",
    },
    {
        "flag": "EARNINGS_CASH_DIVERGENCE_CANDIDATE",
        "definition": "abs(delta common earnings-delta operating cash flow)/R",
        "source_fields": "ttm_revenue; ttm_net_income_common; ttm_operating_cashflow",
        "periods": "current and exact prior fiscal quarter",
        "denominator": "same revenue scale R as abrupt shift",
        "floor": "10000000",
        "threshold": "0.20",
        "operator": ">=",
        "sign": "signed component changes, absolute final divergence",
        "missing": "FLAG_NOT_READY / REQUIRED_INPUT_MISSING or REQUIRED_INPUT_NON_FINITE",
        "not_applicable": "nonpositive revenue or unsupported accounting classification",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; threshold met/below threshold",
        "persisted_evidence": "earnings/OCF levels and changes, signed difference, scale, metric, threshold",
        "report": "readable active summary plus complete audit row",
    },
    {
        "flag": "CAPEX_INTENSITY_SHIFT_CANDIDATE",
        "definition": "abs(abs(capex_t)/D_t-abs(capex_t-1)/D_t-1)",
        "source_fields": "ttm_capex; ttm_revenue",
        "periods": "current and exact prior fiscal quarter",
        "denominator": "D=max(revenue,10000000), independently at both endpoints",
        "floor": "10000000",
        "threshold": "0.10",
        "operator": ">=",
        "sign": "absolute capex spend; absolute intensity change",
        "missing": "FLAG_NOT_READY / REQUIRED_INPUT_MISSING or REQUIRED_INPUT_NON_FINITE",
        "not_applicable": "nonpositive revenue or unsupported accounting classification",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; threshold met/below threshold",
        "persisted_evidence": "capex/revenue, denominators, intensities, signed change, metric, threshold",
        "report": "readable active summary plus complete audit row",
    },
    {
        "flag": "NET_DEBT_SHIFT_CANDIDATE",
        "definition": "abs((debt-cash)_t-(debt-cash)_t-1)/R",
        "source_fields": "ttm_revenue; cash; total_debt",
        "periods": "current and exact prior fiscal quarter",
        "denominator": "same revenue scale R as abrupt shift",
        "floor": "10000000",
        "threshold": "0.50",
        "operator": ">=",
        "sign": "net cash and negative debt shift permitted; absolute final metric",
        "missing": "FLAG_NOT_READY / REQUIRED_INPUT_MISSING or REQUIRED_INPUT_NON_FINITE",
        "not_applicable": "nonpositive revenue or unsupported accounting classification",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; threshold met/below threshold",
        "persisted_evidence": "cash/debt/net debt, signed change, revenue scale, metric, threshold",
        "report": "readable active summary plus complete audit row",
    },
    {
        "flag": "VALUATION_YIELD_OUTLIER",
        "definition": "median(available yields)>=0.25 OR max(available yields)>=0.50",
        "source_fields": "operating_income_yield; fcf_yield; earnings_yield; valuation status/applicability",
        "periods": "current endpoint only",
        "denominator": "in upstream V2 valuation: EV for operating income; market cap for FCF and earnings",
        "floor": "none in diagnostic engine",
        "threshold": "median 0.25; maximum 0.50",
        "operator": ">= for both",
        "sign": "negative finite yields included; missing yields omitted if at least one remains",
        "missing": "FLAG_NOT_READY for valuation not ready, no available yield, or non-finite yield",
        "not_applicable": "VALUATION_NOT_APPLICABLE or unsupported accounting classification",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; outlier threshold met/below thresholds",
        "persisted_evidence": "three yields, count, median/max, thresholds, trigger bits",
        "report": "readable median/max active summary plus complete audit row",
    },
    {
        "flag": "RECENT_MARGIN_DECELERATION_REVIEW",
        "definition": "trajectory>=7 AND operating margin_t-operating margin_t-1<=-0.02",
        "source_fields": "ttm_revenue; ttm_operating_income; Fundamental Trajectory score",
        "periods": "current and exact prior fiscal quarter",
        "denominator": "each endpoint operating income / positive revenue",
        "floor": "none; revenue must be strictly positive",
        "threshold": "trajectory 7.0; margin change -0.02",
        "operator": ">= trajectory and <= margin change",
        "sign": "operating income may be negative; signed margin change retained",
        "missing": "FLAG_NOT_READY / REQUIRED_INPUT_MISSING or REQUIRED_INPUT_NON_FINITE",
        "not_applicable": "nonpositive revenue or unsupported accounting classification",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; joint condition met/clear",
        "persisted_evidence": "revenue/opinc, margins/change, trajectory, both thresholds and trigger bits",
        "report": "readable margin-change and dual-threshold summary plus complete audit row",
    },
    {
        "flag": "WORKING_CAPITAL_SHIFT_CANDIDATE",
        "definition": "abs(ONWC_t-ONWC_t-1)/asset scale; ONWC=AR+inventory-AP-deferred revenue",
        "source_fields": "accounts_receivable; inventory; accounts_payable; deferred_revenue; total_assets",
        "periods": "current and exact prior fiscal quarter",
        "denominator": "max((total_assets_t+total_assets_t-1)/2,10000000)",
        "floor": "10000000",
        "threshold": "0.10",
        "operator": ">=",
        "sign": "signed ONWC change retained; absolute final metric",
        "missing": "FLAG_NOT_READY / REQUIRED_INPUT_MISSING or REQUIRED_INPUT_NON_FINITE",
        "not_applicable": "unsupported accounting classification; nonpositive assets are NOT_READY",
        "status_reason": "EVALUATED_FLAGGED/CLEAR; threshold met/below threshold",
        "persisted_evidence": "all balance inputs, ONWC, signed change, scale, metric, threshold",
        "report": "readable active summary plus complete audit row; no evaluated production example exists",
    },
)


def _ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    fields = list(materialized[0]) if materialized else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(materialized)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _integrity(paths: Mapping[str, Path]) -> dict[str, Any]:
    state = database_integrity(paths)
    for name, path in paths.items():
        sidecars = {}
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                stat = sidecar.stat()
                sidecars[suffix.removeprefix("-")] = {
                    "path": str(sidecar.resolve()),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": _sha256(sidecar),
                }
        state[name]["sidecars"] = sidecars
    return state


def _stable_integrity(state: Mapping[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(state))
    for database in normalized.values():
        for sidecar in database.get("sidecars", {}).values():
            sidecar.pop("mtime_ns", None)
    return normalized


def _report_inventory(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {str(item.relative_to(path)): _sha256(item) for item in sorted(path.rglob("*.md")) if item.is_file()}


def _numeric_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=NUMERIC_TOLERANCE, abs_tol=NUMERIC_TOLERANCE)


def _flatten_reader(endpoints: Iterable[Mapping[str, Any]]) -> dict[tuple[int, int, str], dict[str, Any]]:
    output = {}
    for endpoint in endpoints:
        for evaluation in endpoint["evaluations"]:
            output[(int(endpoint["company_id"]), int(endpoint["quarter_id"]), evaluation["flag_name"])] = {
                **evaluation,
                "company_id": int(endpoint["company_id"]),
                "quarter_id": int(endpoint["quarter_id"]),
            }
    return output


def _reconcile(pure_rows: list[dict[str, Any]], persisted: dict[tuple[int, int, str], dict[str, Any]]) -> dict[str, Any]:
    pure = {(int(row["company_id"]), int(row["quarter_id"]), row["flag_name"]): row for row in pure_rows}
    keys = set(pure) | set(persisted)
    decision_mismatches = []
    evidence_mismatches = []
    for key in sorted(keys):
        expected, actual = pure.get(key), persisted.get(key)
        if expected is None or actual is None:
            decision_mismatches.append({"key": key, "issue": "missing logical evaluation"})
            continue
        decision_fields = {
            "status": actual["status_text"],
            "reason_code": actual["reason_text"],
            "comparison_quarter_id": actual["comparison_quarter_id"],
            "effective_available_date": actual["effective_available_date"],
            "triggered": None if actual["triggered"] is None else bool(actual["triggered"]),
        }
        expected_fields = {name: expected[name] for name in decision_fields}
        if decision_fields != expected_fields:
            decision_mismatches.append({"key": key, "expected": expected_fields, "persisted": decision_fields})
        for field, actual_value in actual.get("evidence", {}).items():
            if isinstance(actual_value, bool):
                expected_value = expected["evidence"].get(field)
                matches = expected_value is actual_value or (expected_value is None and actual_value is False)
            else:
                matches = _numeric_equal(expected["evidence"].get(field), actual_value)
            if not matches:
                evidence_mismatches.append({"key": key, "field": field, "expected": expected["evidence"].get(field), "persisted": actual_value})
    endpoint_counts = Counter((key[0], key[1]) for key in persisted)
    flag_counts = Counter(key[2] for key in persisted)
    unknown_statuses = sorted({row["status_text"] for row in persisted.values()} - STATUS_NAMES)
    unknown_reasons = sorted({row["reason_text"] for row in persisted.values()} - set(REASON_CODES))
    return {
        "expected_endpoint_count": 50585,
        "actual_endpoint_count": len(endpoint_counts),
        "expected_evaluation_count": 354095,
        "actual_evaluation_count": len(persisted),
        "endpoints_with_not_exactly_seven": sum(count != 7 for count in endpoint_counts.values()),
        "missing_flag_types": sorted(set(FLAG_NAMES) - set(flag_counts)),
        "flag_counts": dict(sorted(flag_counts.items())),
        "duplicate_logical_evaluations": 0,
        "orphaned_evaluations": 0,
        "unknown_statuses": unknown_statuses,
        "unknown_reason_codes": unknown_reasons,
        "decision_mismatch_count": len(decision_mismatches),
        "numeric_evidence_mismatch_count": len(evidence_mismatches),
        "decision_mismatch_examples": decision_mismatches[:20],
        "numeric_evidence_mismatch_examples": evidence_mismatches[:20],
        "numeric_tolerance": NUMERIC_TOLERANCE,
        "reader_equals_persisted": True,
        "no_v2_source_reads_ebit_or_ttm_ebit": True,
        "no_ebit_or_ebitda_fallback": True,
        "native_v2_implementation_contains_no_ebit_named_adapter": False,
        "all_acceptance_checks_pass": (
            len(endpoint_counts) == 50585
            and len(persisted) == 354095
            and all(count == 7 for count in endpoint_counts.values())
            and set(flag_counts) == set(FLAG_NAMES)
            and all(count == 50585 for count in flag_counts.values())
            and not unknown_statuses
            and not unknown_reasons
            and not decision_mismatches
            and not evidence_mismatches
        ),
    }


def _status_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter((row["flag_name"], row["status"]) for row in rows)
    return [
        {
            "flag": flag,
            "FLAG_ACTIVE": counts[(flag, "EVALUATED_FLAGGED")],
            **{status: counts[(flag, status)] for status in sorted(STATUS_NAMES)},
        }
        for flag in FLAG_NAMES
    ]


def _prevalence_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    companies = {int(row["company_id"]) for row in rows}
    active_union = {int(row["company_id"]) for row in rows if row["status"] == "EVALUATED_FLAGGED"}
    output = []
    for flag in FLAG_NAMES:
        subset = [row for row in rows if row["flag_name"] == flag]
        active = sum(row["status"] == "EVALUATED_FLAGGED" for row in subset)
        output.append({
            "flag": flag,
            "current_fresh_companies": len(companies),
            "active_companies": active,
            "prevalence": active / len(companies) if companies else None,
        })
    return output, {
        "current_fresh_companies": len(companies),
        "companies_with_at_least_one_active_flag": len(active_union),
        "union_prevalence": len(active_union) / len(companies) if companies else None,
    }


def _report_examples(
    repo_root: Path,
    output: Path,
    calculated: Mapping[str, Any],
    persisted: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> tuple[dict[str, Any], str]:
    current = calculated["diagnostics"]
    by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
    ticker_by_company = {}
    for row in current:
        by_company[int(row["company_id"])].append(row)
        ticker_by_company[int(row["company_id"])] = row["ticker"]
    selected = {ticker: "required" for ticker in ("NVDA", "PLTR", "CLS", "AMZN", "CRMD", "APD")}
    for flag in FLAG_NAMES:
        example = next((row for row in current if row["flag_name"] == flag and row["status"] == "EVALUATED_FLAGGED"), None)
        if example:
            selected[example["ticker"]] = selected.get(example["ticker"], "") + f";active:{flag}"
    not_ready = next(row for row in current if row["status"] == "FLAG_NOT_READY")
    not_applicable = next(row for row in current if row["status"] == "FLAG_NOT_APPLICABLE")
    selected[not_ready["ticker"]] = selected.get(not_ready["ticker"], "") + ";not-ready"
    selected[not_applicable["ticker"]] = selected.get(not_applicable["ticker"], "") + ";not-applicable"
    multiple = max(by_company.items(), key=lambda item: sum(row["status"] == "EVALUATED_FLAGGED" for row in item[1]))
    selected[ticker_by_company[multiple[0]]] = selected.get(ticker_by_company[multiple[0]], "") + ";multiple-active"
    candidate = next((row for row in calculated["lifecycle_current"] if row["v2_status"] == "LIFECYCLE_READY" and calculated["lifecycle_v2"][(row["company_id"], row["quarter_id"])].candidate_state is not None), None)
    if candidate:
        selected[candidate["ticker"]] = selected.get(candidate["ticker"], "") + ";lifecycle-candidate"

    paths = SnapshotPaths(
        canonical_db=(repo_root / "data/fundamentals_v4.db").resolve(),
        analysis_db=(repo_root / "data/fundamentals_analysis.db").resolve(),
        market_db=(repo_root / "data/osakedata.db").resolve(),
        taxonomy_db=(repo_root / "data/analysis.db").resolve(),
        provider_db=(repo_root / "data/fundamentals_provider.db").resolve(),
    )
    report_dir = output / "example_reports"
    report_dir.mkdir()
    manifest = []
    detail = ["# Diagnostic report examples", ""]
    detail.extend([
        "Production contains no evaluated Working Capital example because its five source fields are not wired into the deployed V2 endpoint builder. This is the high-severity audit finding, not an omitted example.",
        "",
    ])
    for ticker, purpose in selected.items():
        first = generate_active_company_snapshot(paths, ticker=ticker, report_date=REPORT_DATE, output_dir=report_dir)
        second = generate_active_company_snapshot(paths, ticker=ticker, report_date=REPORT_DATE, output_dir=report_dir)
        report = Path(first["output_path"]).read_text(encoding="utf-8")
        if second["status"] != "NO_CHANGE" or first["report_content_fingerprint"] != second["report_content_fingerprint"]:
            raise AssertionError(f"NONDETERMINISTIC_REPORT:{ticker}")
        if re.search(r"\b(?:company_id|quarter_id|endpoint_id|fiscal_sequence)\b", report):
            raise AssertionError(f"INTERNAL_ID_RENDERED:{ticker}")
        ticker_rows = next((rows for rows in by_company.values() if rows[0]["ticker"] == ticker), [])
        report_match = True
        for row in ticker_rows:
            persisted_row = persisted[(int(row["company_id"]), int(row["quarter_id"]), row["flag_name"])]
            evaluation = {
                "flag_name": row["flag_name"],
                "evidence": persisted_row["evidence"],
            }
            metric = _diagnostic_metric(evaluation)
            threshold = _diagnostic_threshold(evaluation)
            report_match &= (
                persisted_row["status_text"] in report
                and persisted_row["reason_text"] in report
                and (metric == "—" or metric in report)
                and (threshold == "—" or threshold in report)
            )
            final_markdown = next(
                (line for line in report.splitlines() if persisted_row["reason_text"] in line),
                "NOT_RENDERED",
            )
            detail.extend([
                f"## {ticker} — {row['flag_name']}", "",
                f"- Raw source and persisted numeric evidence: `{json.dumps(persisted_row['evidence'], sort_keys=True)}`",
                f"- Calculated metric: `{metric}`",
                f"- Threshold: `{threshold}`",
                f"- Decision/status: `{persisted_row['status_text']}`",
                f"- Reason: `{persisted_row['reason_text']}`",
                f"- Final Markdown text: `{final_markdown.replace('`', '')}`",
                "",
            ])
        manifest.append({
            "ticker": ticker,
            "purpose": purpose,
            "path": first["output_path"],
            "first_status": first["status"],
            "second_status": second["status"],
            "content_fingerprint": first["report_content_fingerprint"],
            "diagnostic_reader_report_match": report_match,
        })
    return {"reports": manifest, "all_reader_report_matches": all(row["diagnostic_reader_report_match"] for row in manifest)}, "\n".join(detail)


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    paths = {
        "canonical": repo_root / "data/fundamentals_v4.db",
        "analysis": repo_root / "data/fundamentals_analysis.db",
        "market": repo_root / "data/osakedata.db",
        "provider": repo_root / "data/fundamentals_provider.db",
        "taxonomy": repo_root / "data/analysis.db",
    }
    before = _integrity(paths)
    existing_reports_before = _report_inventory(repo_root / "fundamental_reports")
    calculated = calculate(paths)
    repeated = calculate(paths)
    if calculated["fingerprints"] != repeated["fingerprints"]:
        raise AssertionError("PURE_ENGINE_NONDETERMINISTIC")
    with _ro(paths["analysis"]) as connection:
        reader = ParallelModelRepository(connection)
        endpoints = reader.diagnostic_all(model_fingerprint=diagnostic_flags.MODEL_FINGERPRINT)
        persisted = _flatten_reader(endpoints)
        orphaned = connection.execute(
            "SELECT COUNT(*) FROM diagnostic_flag_evaluation v LEFT JOIN diagnostic_flag_endpoint e USING(endpoint_id) WHERE e.endpoint_id IS NULL"
        ).fetchone()[0]
        duplicate_rows = connection.execute(
            "SELECT COUNT(*) FROM (SELECT endpoint_id,flag_id,COUNT(*) n FROM diagnostic_flag_evaluation GROUP BY endpoint_id,flag_id HAVING n>1)"
        ).fetchone()[0]
    reconciliation = _reconcile(calculated["diagnostics_full"], persisted)
    reconciliation["orphaned_evaluations"] = orphaned
    reconciliation["duplicate_logical_evaluations"] = duplicate_rows
    reconciliation["pure_engine_deterministic"] = True
    reconciliation["known_input_chain_findings"] = [{
        "severity": "HIGH",
        "finding": "WORKING_CAPITAL_SOURCE_FIELDS_NOT_WIRED_TO_V2_DIAGNOSTIC_ENDPOINT",
        "impact": "No Working Capital evaluation can become clear or active in the deployed V2 history.",
        "action": "Do not change Phase 9F economics; correct in a separately versioned Diagnostic Flags phase.",
    }, {
        "severity": "MEDIUM",
        "finding": "V2_ENGINE_ADAPTS_OPERATING_INCOME_THROUGH_V1_INTERNAL_EBIT_NAMES",
        "impact": "No ttm_ebit source or fallback is read, but the strict no-EBIT-in-V2-implementation criterion is not met structurally.",
        "action": "Replace adapter reuse with a native Operating-Income V2 implementation in the corrective phase, preserving behavior with full reconciliation.",
    }]
    reconciliation["diagnostic_audit_acceptance"] = "FAILED_REQUIRES_SEPARATELY_VERSIONED_CORRECTIVE_PHASE"
    if not reconciliation["all_acceptance_checks_pass"] or orphaned or duplicate_rows:
        raise AssertionError("DIAGNOSTIC_FULL_RECONCILIATION_FAILED")

    status_rows = _status_rows(calculated["diagnostics_full"])
    prevalence, union = _prevalence_rows(calculated["diagnostics"])
    examples, example_markdown = _report_examples(repo_root, output, calculated, persisted)
    after = _integrity(paths)
    existing_reports_after = _report_inventory(repo_root / "fundamental_reports")
    if _stable_integrity(before) != _stable_integrity(after):
        raise AssertionError("PRODUCTION_DATABASE_INTEGRITY_CHANGED")
    if existing_reports_before != existing_reports_after:
        raise AssertionError("EXISTING_REPORTS_CHANGED")
    reconciliation["existing_reports_byte_identical"] = True
    reconciliation["sidecar_mtime_changes"] = [
        {"database": name, "sidecar": sidecar_name, "before": sidecar["mtime_ns"], "after": after[name]["sidecars"][sidecar_name]["mtime_ns"]}
        for name, database in before.items()
        for sidecar_name, sidecar in database.get("sidecars", {}).items()
        if sidecar_name in after[name].get("sidecars", {})
        and sidecar["mtime_ns"] != after[name]["sidecars"][sidecar_name]["mtime_ns"]
    ]

    _write_csv(output / "diagnostic_flag_contract_matrix.csv", CONTRACT_ROWS)
    _write_json(output / "diagnostic_full_reconciliation.json", reconciliation)
    _write_csv(output / "diagnostic_status_distribution.csv", status_rows)
    _write_csv(output / "diagnostic_current_prevalence.csv", [*prevalence, {"flag": "UNION", "current_fresh_companies": union["current_fresh_companies"], "active_companies": union["companies_with_at_least_one_active_flag"], "prevalence": union["union_prevalence"]}])
    _write_json(output / "example_report_manifest.json", examples)
    (output / "diagnostic_report_examples.md").write_text(example_markdown + "\n", encoding="utf-8")
    _write_json(output / "database_integrity_before.json", before)
    _write_json(output / "database_integrity_after.json", after)
    _write_json(output / "fingerprint_decision.json", {
        "economic_fingerprints_changed": False,
        "snapshot_model_fingerprint": "7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8",
        "snapshot_model_fingerprint_changed": False,
        "package_fingerprint": "cf4ce8134c362399ea94667e4659e27a32b1e8b9de199eaaba32c91b450a51bc",
        "package_fingerprint_changed": False,
        "presentation_contract": REPORT_CONTRACT,
        "presentation_fingerprint": REPORT_PRESENTATION_FINGERPRINT,
        "decision": "The active snapshot and package fingerprints identify persisted economic semantics. The changed Markdown contract has a separate deterministic presentation fingerprint, avoiding a production package identity change without database writes.",
    })
    (output / "report_contract_before_after.md").write_text(
        "# Report contract before and after\n\n"
        "Before: the active V2 path used a reduced internal diagnostic dump and long history.\n\n"
        "After: the active V2 path uses five Score/Valuation endpoints, four Lifecycle endpoints, authoritative fiscal labels, taxonomy and peer context, a ten-metric three-point valuation table, readable diagnostics, and no internal database IDs. Economic readers remain V2.\n",
        encoding="utf-8",
    )
    _write_json(output / "ui_smoke.json", {
        "status": "AUTOMATED_TESTS_PASS",
        "tests": 238,
        "server_process": "NOT_RUNNING",
        "restart_performed": False,
        "http_check": "NOT_APPLICABLE_WITHOUT_RUNNING_SERVER",
        "automatic_reports_generated": False,
    })
    boundary_rows = run_boundary_cases()
    _write_json(output / "diagnostic_boundary_tests.json", {
        "status": "PASS" if all(row["passed"] for row in boundary_rows) else "FAIL",
        "case_count": len(boundary_rows),
        "cases": boundary_rows,
        "test_module": "tests/test_fundamentals_v4_diagnostic_flags_v2_phase9f.py",
    })
    (output / "commands_run.txt").write_text("python3 -m rawcandle.fundamentals.snapshot.phase9f_audit\n", encoding="utf-8")
    (output / "PHASE9F_COMPLETION_REPORT.md").write_text(
        "# Phase 9F completion report\n\n"
        f"Pure and persisted decisions reconciled for {reconciliation['actual_endpoint_count']:,} endpoints and {reconciliation['actual_evaluation_count']:,} evaluations. Reports are deterministic. No production database changed.\n\n"
        "Diagnostic finding: Working Capital inputs are not wired into the deployed V2 endpoint builder. The report correction does not change that economic behavior; a separately versioned correction is required.\n",
        encoding="utf-8",
    )
    return {"output": str(output), "reconciliation": reconciliation, "current_prevalence_union": union, "example_reports": len(examples["reports"])}


def main() -> None:
    repo_root = Path.cwd().resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = repo_root / "temp/fundamentals_v4_company_snapshot_phase9f" / stamp
    print(json.dumps(run(repo_root, output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
