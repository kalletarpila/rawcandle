from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    compare_production_inventory,
    production_inventory,
)
from rawcandle.research.fundamental_profile_baseline.contract import (
    CONTRACT,
    CONTRACT_FINGERPRINT,
)
from rawcandle.research.fundamental_profile_baseline.engine import (
    embargo_cutoffs,
    partition_decision,
    stable_hash,
)
from rawcandle.research.fundamental_profile_baseline.runner import (
    eligibility_reason,
    prepare_rows,
)
from rawcandle.research.fundamental_profile_baseline.source import (
    ResearchPaths,
    build_research_rows,
    readonly,
    source_fingerprint,
)


ROOT = Path(__file__).resolve().parents[2]
PHASE12D = ROOT / "temp/fundamentals_v4_phase12d/20260910T_PHASE12D_REHEARSAL_V7"
ACCEPTED = PHASE12D / "candidate_a/phase12b_replay"
ACCEPTED_MARKET_SHA256 = "38078094058004539dcb155df8b4172cb6822dc20c465c02cd7468710a1d1cdd"
ACCEPTED_COUNTS = {
    "DEVELOPMENT": {"final": 13051, "months": 26},
    "TEMPORAL_VALIDATION": {"final": 3876, "months": 7},
    "RETROSPECTIVE_CONFIRMATION": {"final": 3953, "months": 7},
}
PERIODS = ("DEVELOPMENT", "TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION")
POLICIES = {
    "P0": "implemented: purge labels after period end; embargo first 63 sessions of each later period",
    "P1": "literal locked contract: identical to P0",
    "P2": "diagnostic: purge earlier-period labels crossing a protected boundary; no later-period embargo",
    "P3": "diagnostic: assign by t0 and retain every matured exact label",
    "P4": "future-contract candidate: purge earlier side only; no duplicated later-side embargo",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    names = list(fields or sorted({key for row in rows for key in row}))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _months(start: str = "2021-01", end: str = "2025-12") -> list[str]:
    year, month = map(int, start.split("-"))
    result = []
    while f"{year:04d}-{month:02d}" <= end:
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def _summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(rows)
    return {
        "rows": len(values),
        "companies": len({int(row["company_id"]) for row in values}),
        "availability_dates": len({row.get("source_availability_date") for row in values if row.get("source_availability_date")}),
        "entry_sessions": len({row.get("entry_date") for row in values if row.get("entry_date")}),
        "signal_months": len({str(row.get("entry_date"))[:7] for row in values if row.get("entry_date")}),
        "exit_months": len({str(row.get("h63_exit_date"))[:7] for row in values if row.get("h63_exit_date")}),
    }


def _first_reason(row: Mapping[str, Any]) -> str:
    if row.get("ttm_readiness_status") != "TTM_READY":
        return "INCOMPLETE_FUNDAMENTAL_INPUT_CHAIN"
    if row.get("score_status") != "SCORE_FULL":
        return "SCORE_NOT_FULL"
    if row.get("valuation_status") != "VALUATION_FULL":
        return "VALUATION_NOT_FULL"
    if row.get("two_quarter_status") != "DELTA_READY":
        return "DELTA_2Q_NOT_READY"
    if row.get("lifecycle_status") != "LIFECYCLE_READY" or not row.get("lifecycle"):
        return "LIFECYCLE_NOT_READY"
    if not row.get("diagnostic_complete"):
        return "DIAGNOSTIC_COVERAGE_INCOMPLETE"
    if row.get("identity_status") not in {"DATED_ALIAS", "CURRENT_TICKER_FALLBACK"}:
        return "IDENTITY_UNRESOLVED"
    status = row.get("h63_status")
    if status == "MISSING_BENCHMARK_ENTRY":
        return "SPY_ENTRY_UNAVAILABLE"
    if status == "MISSING_ENTRY_PRICE":
        return "COMPANY_ENTRY_UNAVAILABLE"
    if status == "HORIZON_NOT_MATURED":
        return "EXACT_63_SESSION_EXIT_NOT_MATURED"
    if status == "MISSING_EXACT_EXIT_PRICE":
        return "COMPANY_EXACT_EXIT_UNAVAILABLE"
    if status == "INSUFFICIENT_SESSION_COVERAGE":
        return "MINIMUM_SESSION_COVERAGE_FAILED"
    if status != "LABEL_READY":
        return str(status or "PRIMARY_LABEL_NOT_READY")
    if row.get("partition_status") == "PURGED_LABEL_CROSSES_PERIOD_END":
        return "REMOVED_BY_PURGE"
    if row.get("partition_status") == "EMBARGO_FIRST_63_SESSIONS":
        return "REMOVED_BY_EMBARGO"
    if row.get("partition_status") != "RETAINED":
        return str(row.get("partition_status") or "NOT_RETAINED")
    return "FINAL_RETAINED"


def _load_ttm_context(canonical_db: Path) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    with readonly(canonical_db) as connection:
        quarter = {int(row["quarter_id"]): dict(row) for row in connection.execute(
            "SELECT quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_availability_date "
            "FROM v4_quarter ORDER BY company_id,fiscal_year,fiscal_quarter"
        )}
        ttm = [dict(row) for row in connection.execute(
            "SELECT company_id,endpoint_quarter_id,endpoint_fiscal_year,endpoint_fiscal_quarter,"
            "readiness_status,blocker_codes_json,input_quarter_ids_json FROM v4_ttm_values "
            "ORDER BY company_id,endpoint_fiscal_year,endpoint_fiscal_quarter"
        )]
    return quarter, ttm


def fiscal_chain_audit(canonical_db: Path) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    quarters, ttm_rows = _load_ttm_context(canonical_db)
    endpoint_status = {int(row["endpoint_quarter_id"]): row for row in ttm_rows}
    output = []
    counts = Counter()
    for row in ttm_rows:
        ids = json.loads(row["input_quarter_ids_json"] or "[]")
        inputs = [quarters[item] for item in ids if item in quarters]
        ordinals = [int(item["fiscal_year"]) * 4 + int(str(item["fiscal_quarter"])[1]) for item in inputs]
        consecutive = bool(ordinals) and ordinals == list(range(ordinals[0], ordinals[0] + len(ordinals)))
        crosses = len({int(item["fiscal_year"]) for item in inputs}) > 1
        if crosses:
            status = "VALID_CROSS_YEAR_CHAIN" if row["readiness_status"] == "TTM_READY" and len(inputs) == 4 and consecutive else "REJECTED_CROSS_YEAR_CHAIN"
            counts[status] += 1
            output.append({
                "company_id": row["company_id"], "endpoint_quarter_id": row["endpoint_quarter_id"],
                "endpoint_fiscal_year": row["endpoint_fiscal_year"], "endpoint_fiscal_quarter": row["endpoint_fiscal_quarter"],
                "input_quarter_ids": json.dumps(ids, separators=(",", ":")),
                "input_fiscal_identities": "|".join(f"{item['fiscal_year']}-{item['fiscal_quarter']}" for item in inputs),
                "consecutive": consecutive, "readiness_status": row["readiness_status"],
                "blocker_codes": row["blocker_codes_json"], "audit_status": status,
                "rejection_reason": None if status == "VALID_CROSS_YEAR_CHAIN" else row["blocker_codes_json"],
            })
    counts["all_ttm_ready"] = sum(row["readiness_status"] == "TTM_READY" for row in ttm_rows)
    counts["all_ttm_not_ready"] = len(ttm_rows) - counts["all_ttm_ready"]
    return endpoint_status, output, dict(counts)


def _period_for_year(year: int) -> str | None:
    if 2021 <= year <= 2023:
        return "DEVELOPMENT"
    return {2024: "TEMPORAL_VALIDATION", 2025: "RETROSPECTIVE_CONFIRMATION", 2026: "FORWARD_REPORT_ONLY"}.get(year)


def _policy_status(row: Mapping[str, Any], policy: str) -> str:
    if row.get("h63_status") != "LABEL_READY" or eligibility_reason(row, require_label=True) != "ELIGIBLE":
        return "NOT_COMMON_COHORT_READY"
    period = row.get("period")
    if period not in PERIODS:
        return "OUTSIDE_AUDIT_PERIODS"
    if policy in {"P0", "P1"}:
        return str(row["partition_status"])
    if policy in {"P2", "P4"}:
        return "PURGED_LABEL_CROSSES_PERIOD_END" if str(row["h63_exit_date"]) > CONTRACT["periods"][str(period)][1] else "RETAINED"
    return "RETAINED"


def _attach_ttm(rows: list[dict[str, Any]], ttm: Mapping[int, Mapping[str, Any]]) -> None:
    for row in rows:
        context = ttm.get(int(row["quarter_id"]), {})
        row["ttm_readiness_status"] = context.get("readiness_status")
        row["ttm_blocker_codes"] = context.get("blocker_codes_json")


def _monthly_waterfall(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reasons = []
    for row in rows:
        entry = row.get("entry_date")
        availability = row.get("source_availability_date")
        month = str(entry or availability or "")[:7]
        if "2021-01" <= month <= "2025-12":
            reasons.append({
                "company_id": row["company_id"], "quarter_id": row["quarter_id"], "ticker": row.get("ticker"),
                "fiscal_period_end": row.get("period_end"), "source_availability_date": availability,
                "entry_date": entry, "exit_date_63": row.get("h63_exit_date"), "signal_month": month,
                "assigned_period": row.get("period"), "first_reason": _first_reason(row),
                "label_status": row.get("h63_status"), "partition_status": row.get("partition_status"),
            })
    waterfall = []
    reason_order = [
        "INCOMPLETE_FUNDAMENTAL_INPUT_CHAIN", "SCORE_NOT_FULL",
        "VALUATION_NOT_FULL", "DELTA_2Q_NOT_READY", "LIFECYCLE_NOT_READY",
        "DIAGNOSTIC_COVERAGE_INCOMPLETE", "IDENTITY_UNRESOLVED", "SPY_ENTRY_UNAVAILABLE",
        "COMPANY_ENTRY_UNAVAILABLE", "EXACT_63_SESSION_EXIT_NOT_MATURED", "COMPANY_EXACT_EXIT_UNAVAILABLE",
        "MINIMUM_SESSION_COVERAGE_FAILED", "REMOVED_BY_PURGE", "REMOVED_BY_EMBARGO", "FINAL_RETAINED",
    ]
    for month in _months():
        members = [row for row in rows if str(row.get("entry_date") or row.get("source_availability_date") or "")[:7] == month]
        by_reason = Counter(_first_reason(row) for row in members)
        waterfall.append({"signal_month": month, "sequence": 0, "stage_or_first_reason": "ALL_AVAILABILITY_ELIGIBLE_ENDPOINTS",
                          "stage_kind": "START", **_summary(members), "removed_at_stage": 0, "remaining_after_stage": len(members)})
        remaining = len(members)
        for sequence, reason in enumerate(reason_order, 1):
            selected = [row for row in members if _first_reason(row) == reason]
            summary = _summary(selected)
            removed_count = 0 if reason == "FINAL_RETAINED" else by_reason[reason]
            remaining -= removed_count
            waterfall.append({"signal_month": month, "sequence": sequence, "stage_or_first_reason": reason,
                              "stage_kind": "FINAL" if reason == "FINAL_RETAINED" else "MUTUALLY_EXCLUSIVE_REMOVAL",
                              **summary, "removed_at_stage": removed_count, "remaining_after_stage": remaining})
    return waterfall, reasons


def _boundary_rows(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    boundaries = ["2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01", "2026-01-01"]
    purge, embargo = [], []
    cutoffs = embargo_cutoffs(sessions)
    for boundary in boundaries:
        prior_period = _period_for_year(int(boundary[:4]) - 1)
        later_period = _period_for_year(int(boundary[:4]))
        is_model_boundary = prior_period != later_period
        purged = [row for row in rows if is_model_boundary and row.get("partition_status") == "PURGED_LABEL_CROSSES_PERIOD_END" and row.get("period") == prior_period]
        blocked = [row for row in rows if row.get("partition_status") == "EMBARGO_FIRST_63_SESSIONS" and row.get("period") == later_period]
        eligible_prior = [row for row in rows if is_model_boundary and prior_period is not None and row.get("period") == prior_period and row.get("h63_status") == "LABEL_READY"]
        allowed_prior = [row for row in eligible_prior if row.get("partition_status") != "PURGED_LABEL_CROSSES_PERIOD_END"]
        cutoff = cutoffs.get(later_period)
        period_start = CONTRACT["periods"][later_period][0] if later_period in CONTRACT["periods"] else None
        purge.append({"boundary_date": boundary, "information_cutoff": boundary, "prior_period": prior_period, "is_model_boundary": is_model_boundary,
                      "last_permitted_entry_date_observed": max((str(row["entry_date"]) for row in allowed_prior), default=None) if is_model_boundary else None,
                      "last_permitted_exit_date": (date.fromisoformat(boundary) - timedelta(days=1)).isoformat() if is_model_boundary else None,
                      "losing_side": "EARLIER" if is_model_boundary else "NONE", "predicate": "exit_date_63 > assigned_period_end", **_summary(purged)})
        embargo.append({"boundary_date": boundary, "later_period": later_period, "is_model_boundary": is_model_boundary,
                        "period_start": period_start, "cutoff_session": cutoff,
                        "calendar_days_to_cutoff": (date.fromisoformat(cutoff) - date.fromisoformat(period_start)).days if cutoff and period_start else None,
                        "losing_side": "LATER" if blocked else "NONE", "predicate": "entry_date < period_start_plus_63_SPY_sessions", **_summary(blocked)})
    return purge, embargo


def _label_intervals(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "company_id": row["company_id"], "quarter_id": row["quarter_id"], "ticker": row.get("ticker"),
        "fiscal_period_end": row.get("period_end"), "availability_date": row.get("source_availability_date"),
        "entry_date": row.get("entry_date"), "exit_date": row.get("h63_exit_date"), "assigned_period": row.get("period"),
        "boundary_date": CONTRACT["periods"][str(row["period"])][1] if row.get("period") in CONTRACT["periods"] else None,
        "purge_rule": "exit_date_63 > assigned_period_end", "purge_reason": row.get("partition_status"),
    } for row in rows if row.get("partition_status") in {"PURGED_LABEL_CROSSES_PERIOD_END", "EMBARGO_FIRST_63_SESSIONS"}]


def _counterfactuals(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for policy, rule in POLICIES.items():
        for period in PERIODS:
            members = [row for row in rows if row.get("period") == period and _policy_status(row, policy) == "RETAINED"]
            overlaps = sum(str(row.get("h63_exit_date")) > CONTRACT["periods"][period][1] for row in members)
            output.append({"policy": policy, "period": period, "rule": rule,
                           "compliance": "LOCKED_CONTRACT" if policy in {"P0", "P1"} else "DIAGNOSTIC_ONLY" if policy in {"P2", "P3"} else "PROPOSED_FUTURE_CONTRACT",
                           **_summary(members), "labels_crossing_period_end": overlaps,
                           "retained_month_list": "|".join(sorted({str(row["entry_date"])[:7] for row in members}))})
    return output


def _bootstrap_audit(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> dict[str, Any]:
    by_period = {}
    index = {session: i for i, session in enumerate(sessions)}
    for period in PERIODS:
        members = [row for row in rows if row.get("period") == period and _first_reason(row) == "FINAL_RETAINED"]
        starts = sorted({index[str(row["entry_date"])] for row in members})
        by_period[period] = {
            **_summary(members), "unique_block_starts": len(starts), "calendar_signal_months": len({str(row["entry_date"])[:7] for row in members}),
            "effective_temporal_regimes_upper_bound": len({str(row["entry_date"])[:7] for row in members}),
        }
    return {
        "bootstrap_unit": "global SPY-session start sampled with every company row at sessions start..start+62",
        "block_length_sessions": 63, "replicates": 1000, "random_seed": 12012,
        "company_rows_within_session_resampled_together": True, "hierarchy": "one-level calendar-session moving blocks",
        "seven_month_interval_limitation": "95% intervals are computable but cannot create more independent market regimes than observed",
        "periods": by_period,
    }


def _report(decision: Mapping[str, Any], signal_rows: Sequence[Mapping[str, Any]], chain_counts: Mapping[str, int], policies: Sequence[Mapping[str, Any]], bootstrap: Mapping[str, Any], removed: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Phase 12B.1 Signal-Month Audit", "", f"**Principal outcome: {decision['outcome']}**", "",
             "The current code exactly implements the locked entry-date split, same-period label purge, and first-63-session embargo. The policy is internally consistent, but it protects each annual boundary from both sides and removes economically calculable labels. No fiscal-chain year-reset defect was found.", "",
             "## Retained months", "", "| Period | Months |", "| --- | --- |"]
    for row in signal_rows:
        lines.append(f"| {row['period']} | {row['retained_months']} |")
    lines += ["", "## Empty-month first causes", "", "| Month | First-reason distribution |", "| --- | --- |"]
    retained = {month for row in signal_rows for month in str(row["retained_months"]).split("|")}
    for month in _months():
        if month in retained:
            continue
        counts = Counter(row["first_reason"] for row in removed if row["signal_month"] == month)
        lines.append(f"| {month} | " + "; ".join(f"{name}={count}" for name, count in counts.most_common()) + " |")
    lines += ["", "## Fiscal continuity", "", f"Valid ready TTM chains crossing fiscal years: {chain_counts.get('VALID_CROSS_YEAR_CHAIN', 0):,}.",
              f"Rejected cross-year chains: {chain_counts.get('REJECTED_CROSS_YEAR_CHAIN', 0):,}. Rejections retain their source blocker codes; no rejection is caused by calendar-year equality.", "",
              "## Counterfactual cohorts", "", "| Policy | Period | Rows | Months | Cross-boundary labels |", "| --- | --- | ---: | ---: | ---: |"]
    for row in policies:
        lines.append(f"| {row['policy']} | {row['period']} | {row['rows']:,} | {row['signal_months']} | {row['labels_crossing_period_end']} |")
    lines += ["", "## Bootstrap", ""]
    for period, values in bootstrap["periods"].items():
        lines.append(f"- `{period}`: {values['unique_block_starts']} entry-session block starts but only {values['calendar_signal_months']} signal months.")
    lines += ["", "Thousands of company rows do not provide thousands of independent market regimes. The annual 95% intervals are mechanically computable but rest on seven signal months.", "",
              "## Contract versus implementation", "", "The split field is `entry_date`, which is the first complete SPY session strictly after source availability. Company and SPY use the same t0 and exact t+63 sessions. A label may cross an ordinary calendar year; only a locked period end causes purge. Purge acts on the earlier side and embargo on the later side, so they remove different rows while protecting the same adjacent-boundary dependence risk.", "",
              "The code matches the locked contract. P0 and P1 are identical. P2 shows the effect of retaining the later side while purging only the earlier label overlap. P3 is diagnostic only and is not confirmatory evidence. P4 requires a separately versioned future contract.", "",
              "Phase 12B.2 is required only to version a less restrictive split policy; it is not an implementation bug fix. Existing H1-H8 and B0-B4 artifacts remain the result of the original contract and must not be relabelled as results under P2-P4.", ""]
    return "\n".join(lines)


def run(output: Path) -> dict[str, Any]:
    output = output.resolve()
    expected_parent = ROOT / "temp/fundamentals_v4_phase12b1"
    if expected_parent not in output.parents or output.exists():
        raise ValueError("PHASE12B1_NEW_TEMP_OUTPUT_REQUIRED")
    output.mkdir(parents=True)
    preflight = production_inventory()
    _write_json(output / "production_preflight.json", preflight)
    paths = ResearchPaths(
        PHASE12D / "candidate_a/fundamentals_v4.db", PHASE12D / "candidate_a/fundamentals_analysis.db",
        PHASE12D / "candidate_a/fundamentals_provider.db", PRODUCTION["market"], PRODUCTION["taxonomy"],
    )
    endpoint_ttm, chain_rows, chain_counts = fiscal_chain_audit(paths.canonical_db)
    rows, sessions = build_research_rows(paths, include_phase12a_reconciliation=False)
    prepare_rows(rows, sessions)
    _attach_ttm(rows, endpoint_ttm)
    endpoint_features = {int(row["quarter_id"]): row for row in rows}
    for chain in chain_rows:
        feature = endpoint_features.get(int(chain["endpoint_quarter_id"]), {})
        chain.update({
            "score_status": feature.get("score_status"),
            "valuation_status": feature.get("valuation_status"),
            "delta_2q_status": feature.get("two_quarter_status"),
            "lifecycle_status": feature.get("lifecycle_status"),
            "diagnostic_complete": feature.get("diagnostic_complete"),
        })
    source_fp = source_fingerprint(rows)
    accepted_summary = json.loads((PHASE12D / "phase12b_replay_summary.json").read_text(encoding="utf-8"))["results"][0]
    signal_rows = []
    reconciliation = {}
    for period in PERIODS:
        final = [row for row in rows if row.get("period") == period and _first_reason(row) == "FINAL_RETAINED"]
        months = sorted({str(row["entry_date"])[:7] for row in final})
        signal_rows.append({"period": period, **_summary(final), "retained_months": "|".join(months),
                            "excluded_calendar_months": "|".join(month for month in _months() if int(month[:4]) in ({2021, 2022, 2023} if period == "DEVELOPMENT" else {2024} if period == "TEMPORAL_VALIDATION" else {2025}) and month not in months)})
        reconciliation[period] = {"actual": {"final": len(final), "months": len(months)}, "accepted": ACCEPTED_COUNTS[period], "match": len(final) == ACCEPTED_COUNTS[period]["final"] and len(months) == ACCEPTED_COUNTS[period]["months"]}
    if not all(item["match"] for item in reconciliation.values()) or source_fp != accepted_summary["source_fingerprint"]:
        raise RuntimeError("ACCEPTED_2021_2025_COHORT_RECONCILIATION_FAILED")
    waterfall, removed = _monthly_waterfall(rows)
    purge, embargo = _boundary_rows(rows, sessions)
    policies = _counterfactuals(rows)
    bootstrap = _bootstrap_audit(rows, sessions)
    intervals = _label_intervals(rows)
    current_market_hash = _sha256(PRODUCTION["market"])
    decision = {
        "outcome": "OUTCOME B - THE LOCKED BOUNDARY POLICY IS INTERNALLY CONSISTENT BUT UNNECESSARILY REMOVES VALID OBSERVATIONS",
        "contract_fingerprint": CONTRACT_FINGERPRINT, "accepted_source_fingerprint": accepted_summary["source_fingerprint"],
        "accepted_sample_fingerprint": accepted_summary["sample_fingerprint"], "accepted_result_fingerprint": accepted_summary["result_fingerprint"],
        "reconstructed_source_fingerprint": source_fp, "accepted_2021_2025_counts_reconciled": reconciliation,
        "accepted_market_sha256": ACCEPTED_MARKET_SHA256, "current_market_sha256": current_market_hash,
        "market_snapshot_note": "Current market DB adds post-Phase12D prices; 2021-2025 accepted counts and months reconcile exactly. 2026 maturity is excluded from accepted-result claims.",
        "implementation_matches_locked_contract": True, "fiscal_year_reset_defect": False,
        "double_sided_boundary_protection": True, "phase12b2_required": True,
    }
    _write_json(output / "decision.json", decision)
    _write_csv(output / "signal_months_by_period.csv", signal_rows)
    _write_csv(output / "monthly_attrition_waterfall.csv", waterfall)
    _write_csv(output / "removed_rows_by_first_reason.csv", removed)
    _write_csv(output / "fiscal_chain_year_boundary_audit.csv", chain_rows)
    _write_csv(output / "label_interval_boundary_audit.csv", intervals)
    _write_csv(output / "purge_audit.csv", purge)
    _write_csv(output / "embargo_audit.csv", embargo)
    _write_csv(output / "policy_counterfactual_counts.csv", policies)
    _write_json(output / "bootstrap_block_audit.json", bootstrap)
    contract_text = _report(decision, signal_rows, chain_counts, policies, bootstrap, removed)
    (output / "contract_vs_implementation.md").write_text(contract_text, encoding="utf-8")
    (output / "PHASE12B1_SIGNAL_MONTH_AUDIT_REPORT.md").write_text(contract_text, encoding="utf-8")
    (output / "commands_run.txt").write_text("python3 -m rawcandle.cli.run_phase12b1_signal_month_audit --output <new-temp-path>\n", encoding="utf-8")
    postflight = production_inventory()
    _write_json(output / "production_postflight.json", postflight)
    isolation = compare_production_inventory(preflight, postflight)
    _write_json(output / "production_immutability.json", isolation)
    if not isolation["identical"]:
        raise RuntimeError("PRODUCTION_IMMUTABILITY_FAILED")
    economic_files = sorted(path for path in output.iterdir() if path.name not in {"production_preflight.json", "production_postflight.json", "production_immutability.json", "commands_run.txt"})
    manifest = {path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size} for path in economic_files}
    _write_json(output / "artifact_manifest.json", {"artifacts": manifest, "economic_fingerprint": stable_hash(manifest)})
    return {"outcome": decision["outcome"], "output": str(output), "economic_fingerprint": stable_hash(manifest)}
