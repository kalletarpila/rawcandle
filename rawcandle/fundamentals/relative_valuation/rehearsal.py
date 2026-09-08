from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2 import relative_position as active_relative_position
from rawcandle.fundamentals.operating_income_v2 import valuation
from rawcandle.fundamentals.relative_position.engine import RelativeMeasure
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.renderer import render_snapshot
from rawcandle.fundamentals.snapshot.v2_assembler import _current_price_valuation

from .candidate_snapshot import assemble_relative_valuation_candidate_snapshot
from .engine import (
    COMPONENTS,
    MODEL_FINGERPRINT,
    WEIGHTS,
    RelativeValuationSnapshot,
    calculate_current_price_valuation,
    calculate_own_history,
    calculate_relative_valuation,
    historical_percentile,
    select_history,
)
from .source import ReadOnlySourcePaths, RelativeValuationSource, load_relative_valuation_source


PARITY_TICKERS = ("NVDA", "AMZN", "GOOG", "CRMD", "APD", "PLTR", "CLS", "VRT")
REPORT_TICKERS = ("NVDA", "AMZN", "GOOG", "CRMD", "APD", "PLTR", "CLS", "VRT", "AAOI", "BBWI", "O", "AVB", "ALAB", "AA")


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _adapter_parity(source: RelativeValuationSource, market_db: Path, as_of_date: str) -> dict[str, Any]:
    by_ticker = {row.ticker: row for row in source.inputs}
    fields = (
        "valuation_status", "reason_code", "price_date", "price_age_calendar_days",
        "selected_price", "market_cap", "enterprise_value", "operating_income_yield",
        "fcf_yield", "earnings_yield", "operating_income_points", "fcf_points",
        "earnings_points", "total_valuation_score",
    )
    comparisons = []
    with _readonly(market_db) as market:
        for ticker in PARITY_TICKERS:
            row = by_ticker[ticker]
            expected = _current_price_valuation(
                market,
                ticker=ticker,
                report_date=as_of_date,
                anchor={
                    "company_id": row.company_id,
                    "security_id": row.security_id,
                    "endpoint_fiscal_year": row.valuation_observation.fiscal_year,
                    "endpoint_fiscal_quarter": row.valuation_observation.fiscal_quarter,
                    "endpoint_quarter_id": row.valuation_observation.quarter_id,
                    "period_end": row.valuation_observation.period_end,
                    "readiness_status": row.valuation_observation.ttm_readiness_status,
                    "blocker_codes_json": json.dumps(row.valuation_observation.ttm_blocker_codes),
                    "ttm_operating_income": row.valuation_observation.ttm_operating_income,
                    "ttm_free_cashflow": row.valuation_observation.ttm_free_cashflow,
                    "ttm_net_income_common": row.valuation_observation.ttm_net_income_common,
                    "net_income_common_4q_ready": row.valuation_observation.net_income_common_4q_ready,
                    "shares_outstanding": row.valuation_observation.shares_outstanding,
                    "cash": row.valuation_observation.cash,
                    "total_debt": row.valuation_observation.total_debt,
                    "ttm_source_available_date": row.endpoint_available_date,
                },
                classification={"sector": row.sector, "industry": row.industry},
            )
            actual = calculate_current_price_valuation(row.valuation_observation, row.price_bars, as_of_date=as_of_date)
            equal = all(expected.get(field) == actual.get(field) for field in fields)
            comparisons.append({"ticker": ticker, "equal": equal, "expected": {field: expected.get(field) for field in fields}, "actual": {field: actual.get(field) for field in fields}})
    return {"all_equal": all(row["equal"] for row in comparisons), "comparisons": comparisons}


def _filing_peer_reconciliation(paths: ReadOnlySourcePaths, source: RelativeValuationSource, as_of_date: str) -> dict[str, Any]:
    snapshot_date = source.metadata.get("active_filing_peer_snapshot_date")
    if not snapshot_date:
        raise RuntimeError("ACTIVE_FILING_PEER_SNAPSHOT_MISSING")
    with _readonly(paths.analysis_db) as analysis:
        filing_rows = [dict(row) for row in analysis.execute(
            """WITH ranked AS (
                   SELECT r.*,ROW_NUMBER() OVER (
                       PARTITION BY company_id
                       ORDER BY fiscal_sequence DESC,valuation_revised_result_id DESC
                   ) rank_number
                     FROM valuation_revised_result r
                    WHERE model_fingerprint=? AND history_mode='REVISED_HISTORY'
                      AND fundamental_available_date<=?
               ) SELECT * FROM ranked WHERE rank_number=1 ORDER BY company_id""",
            (valuation.MODEL_FINGERPRINT, snapshot_date),
        )]
    source_by_company = {row.company_id: row for row in source.inputs}
    observations = []
    for filing in filing_rows:
        row = source_by_company[int(filing["company_id"])]
        available = filing.get("fundamental_available_date")
        age = (
            (date.fromisoformat(snapshot_date) - date.fromisoformat(str(available))).days
            if available else None
        )
        status = str(filing.get("valuation_status") or "VALUATION_NOT_READY")
        eligible = age is not None and 0 <= age <= 180 and status == "VALUATION_FULL"
        observations.append(active_relative_position.RelativeObservation(
            source_observation_id=f"valuation_revised_result:{filing.get('valuation_revised_result_id')}",
            company_id=row.company_id,
            security_id=row.security_id,
            ticker=row.ticker,
            measure=active_relative_position.RelativeMeasure.ABSOLUTE_VALUATION_SCORE,
            score=filing.get("total_valuation_score"),
            source_status=status,
            source_eligible=eligible,
            eligibility_reason=(
                "ELIGIBLE" if eligible else
                "SOURCE_OBSERVATION_DATE_INVALID" if age is None else
                "SOURCE_OBSERVATION_STALE" if not 0 <= age <= 180 else status
            ),
            source_observation_date=available,
            source_model_version=valuation.MODEL_VERSION,
            source_model_fingerprint=valuation.MODEL_FINGERPRINT,
            source_result_fingerprint=str(filing.get("result_fingerprint") or "MISSING"),
            sector=row.sector,
            industry=row.industry,
            ecosystem_memberships=row.ecosystem_memberships,
        ))
    calculated = active_relative_position.calculate_snapshot(
        observations,
        snapshot_date=snapshot_date,
        freshness_days=180,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    expected = {
        (row["company_id"], row["peer_scope"], row["peer_group_id"]): (
            row["percentile"], row["peer_count"], row["status"]
        )
        for row in calculated.results
        if row["measure"] == RelativeMeasure.ABSOLUTE_VALUATION_SCORE
    }
    persisted = {
        (item.company_id, str(row["peer_scope"]), str(row["peer_group_id"])): (row["percentile"], row["peer_count"], row["result_status"])
        for item in source.inputs for row in item.filing_peer_results
    }
    shared = sorted(set(expected) & set(persisted))
    mismatches = [key for key in shared if expected[key] != persisted[key]]
    return {
        "active_snapshot_date": snapshot_date,
        "expected_rows": len(expected),
        "persisted_rows": len(persisted),
        "shared_rows": len(shared),
        "mismatch_count": len(mismatches),
        "expected_only": [list(key) for key in sorted(set(expected) - set(persisted))[:20]],
        "persisted_only": [list(key) for key in sorted(set(persisted) - set(expected))[:20]],
        "mismatch_examples": [
            {"key": list(key), "calculated": expected[key], "persisted": persisted[key]}
            for key in mismatches[:20]
        ],
    }


def _component_reference(snapshot: RelativeValuationSnapshot, source: RelativeValuationSource) -> dict[str, Any]:
    inputs = {row.company_id: row for row in source.inputs}
    checked = mismatches = 0
    for company in snapshot.companies:
        source_row = inputs[company.company_id]
        selected, _, _ = select_history(source_row.history, as_of_date=snapshot.as_of_date)
        for result in company.own_history.components:
            if result.historical_percentile is None:
                continue
            values = []
            for endpoint in selected:
                if result.component == "OPERATING_YIELD":
                    numerator, denominator = endpoint.ttm_operating_income, endpoint.enterprise_value
                elif result.component == "FCF_YIELD":
                    numerator, denominator = endpoint.ttm_free_cashflow, endpoint.market_cap
                else:
                    numerator, denominator = endpoint.ttm_reported_common_earnings, endpoint.market_cap
                if numerator is not None and denominator is not None and math.isfinite(float(numerator)) and math.isfinite(float(denominator)) and float(numerator) > 0 and float(denominator) > 0:
                    values.append(float(numerator) / float(denominator))
            expected = historical_percentile(values, float(result.current_yield))
            checked += 1
            mismatches += not math.isclose(expected, result.historical_percentile, abs_tol=1e-12)
        if company.own_history.percentile is not None:
            expected_aggregate = sum(WEIGHTS[row.component] * float(row.historical_percentile) for row in company.own_history.components)
            checked += 1
            mismatches += not math.isclose(expected_aggregate, company.own_history.percentile, abs_tol=1e-12)
    return {"checked_values": checked, "mismatch_count": mismatches}


def _cohort_reconciliation(source: RelativeValuationSource, snapshot: RelativeValuationSnapshot) -> dict[str, Any]:
    current_fresh = sum(row.current_fresh for row in source.inputs)
    peer_eligible = sum(any(result["peer_scope"] == "UNIVERSE" for result in row.current_peer_results) for row in snapshot.companies)
    same_anchor = sum(
        row.current_fresh and row.current_valuation.get("valuation_status") == "VALUATION_FULL"
        and row.filing_valuation and row.filing_valuation.get("valuation_status") == "VALUATION_FULL"
        and int(row.filing_valuation["quarter_id"]) == next(item.valuation_observation.quarter_id for item in source.inputs if item.company_id == row.company_id)
        for row in snapshot.companies
    )
    ready_fresh = sum(row.current_fresh and row.own_history.status == "READY" for row in snapshot.companies)
    limited_fresh = sum(row.current_fresh and row.own_history.status == "LIMITED_HISTORY" for row in snapshot.companies)
    broader_ready = []
    for row in source.inputs:
        if row.current_fresh:
            continue
        current = calculate_current_price_valuation(row.valuation_observation, row.price_bars, as_of_date=snapshot.as_of_date)
        economic = calculate_own_history(current, row.history, as_of_date=snapshot.as_of_date, current_fresh=True)
        if economic.status == "READY":
            broader_ready.append({
                "ticker": row.ticker,
                "endpoint": f"{row.valuation_observation.fiscal_year} {row.valuation_observation.fiscal_quarter}",
                "endpoint_available_date": row.endpoint_available_date,
                "fundamental_age_days": (date.fromisoformat(snapshot.as_of_date) - date.fromisoformat(row.endpoint_available_date)).days,
                "price_date": current.get("price_date"),
                "price_age_calendar_days": current.get("price_age_calendar_days"),
                "minimum_component_positive_history_count": economic.minimum_component_positive_history_count,
            })
    return {
        "COMPLETE_CURRENT": len(source.inputs),
        "CURRENT_FRESH": current_fresh,
        "current_peer_eligible": peer_eligible,
        "same_anchor_filing_current_pairs": same_anchor,
        "OWN_HISTORY_READY_CURRENT_FRESH": ready_fresh,
        "OWN_HISTORY_LIMITED_CURRENT_FRESH": limited_fresh,
        "OWN_HISTORY_READY_ECONOMICALLY_CALCULABLE": ready_fresh + len(broader_ready),
        "broader_only_ready": broader_ready,
    }


def run_full_universe_rehearsal(
    paths: ReadOnlySourcePaths,
    *,
    as_of_date: str,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source = load_relative_valuation_source(paths, as_of_date=as_of_date)
    arguments = {
        "as_of_date": as_of_date,
        "classification_fingerprint": source.classification_fingerprint,
        "taxonomy_fingerprint": source.taxonomy_fingerprint,
    }
    first = calculate_relative_valuation(source.inputs, **arguments)
    second = calculate_relative_valuation(tuple(reversed(source.inputs)), **arguments)
    first_bytes = (first.to_json() + "\n").encode("ascii")
    second_bytes = (second.to_json() + "\n").encode("ascii")
    if first_bytes != second_bytes:
        raise RuntimeError("RELATIVE_VALUATION_DUAL_REPLAY_MISMATCH")
    (output_dir / "relative_valuation_snapshot.json").write_bytes(first_bytes)
    adapter = _adapter_parity(source, paths.market_db, as_of_date)
    filing = _filing_peer_reconciliation(paths, source, as_of_date)
    reference = _component_reference(first, source)
    cohorts = _cohort_reconciliation(source, first)
    status_counts = Counter(row.own_history.status for row in first.companies if row.current_fresh)
    component_counts = Counter((component.component, component.component_history_status) for row in first.companies if row.current_fresh for component in row.own_history.components)
    summary = {
        "as_of_date": as_of_date,
        "model_fingerprint": MODEL_FINGERPRINT,
        "source_fingerprint": first.source_fingerprint,
        "result_fingerprint": first.result_fingerprint,
        "serialized_sha256": hashlib.sha256(first_bytes).hexdigest(),
        "dual_replay_bytes_identical": True,
        "cohorts": cohorts,
        "own_history_status_counts_current_fresh": dict(sorted(status_counts.items())),
        "component_status_counts_current_fresh": {f"{component}:{status}": count for (component, status), count in sorted(component_counts.items())},
        "adapter_parity": adapter,
        "filing_peer_reconciliation": filing,
        "component_reference_reconciliation": reference,
        "source_metadata": source.metadata,
    }
    _write_csv(output_dir / "company_coverage.csv", [{
        "company_id": row.company_id,
        "ticker": row.ticker,
        "current_fresh": row.current_fresh,
        "current_status": row.current_valuation.get("valuation_status"),
        "current_score": row.current_valuation.get("total_valuation_score"),
        "own_history_status": row.own_history.status,
        "own_history_percentile": row.own_history.percentile,
        "minimum_component_positive_history_count": row.own_history.minimum_component_positive_history_count,
    } for row in first.companies])
    report_dir = output_dir / "candidate_reports"
    report_dir.mkdir(exist_ok=True)
    snapshot_paths = SnapshotPaths(paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db, paths.canonical_db.parent / "fundamentals_provider.db")
    report_checks = {}
    for ticker in REPORT_TICKERS:
        candidate = assemble_relative_valuation_candidate_snapshot(snapshot_paths, ticker=ticker, report_date=as_of_date, relative_valuation=first)
        rendered = render_snapshot(candidate)
        (report_dir / f"{ticker}_{as_of_date}.md").write_text(rendered.markdown, encoding="utf-8")
        required_fragments = (
            "## Relative Valuation",
            f"As-of date: `{as_of_date}`",
            "Current-price peer comparison",
            "Own positive-yield history",
            "Positive observations",
            "ei PIT-rekonstruktio",
        )
        report_checks[ticker] = all(fragment in rendered.markdown for fragment in required_fragments)
        if not report_checks[ticker]:
            raise RuntimeError(f"RELATIVE_VALUATION_CASE_REPORT_INCOMPLETE:{ticker}")
        if any(token in rendered.markdown for token in ("company_id", "security_id", "snapshot_id", "package_id")):
            raise RuntimeError(f"RELATIVE_VALUATION_CASE_REPORT_INTERNAL_ID:{ticker}")
    cases = {row.ticker: row for row in first.companies if row.ticker in REPORT_TICKERS}
    category_checks = {
        "score_zero": any(row.current_valuation.get("total_valuation_score") == 0 for row in cases.values()),
        "score_one_hundred": any(row.current_valuation.get("total_valuation_score") == 100 for row in cases.values()),
        "valuation_not_applicable": any(row.current_valuation.get("valuation_status") == "VALUATION_NOT_APPLICABLE" for row in cases.values()),
        "stale_price": any(row.current_valuation.get("reason_code") == "CURRENT_PRICE_FALLBACK_TOO_OLD" for row in cases.values()),
        "insufficient_history": any(row.own_history.status == "INSUFFICIENT_HISTORY" for row in cases.values()),
        "limited_history": any(row.own_history.status == "LIMITED_HISTORY" for row in cases.values()),
        "component_percentile_without_aggregate": any(
            row.own_history.percentile is None
            and any(component.historical_percentile is not None for component in row.own_history.components)
            for row in cases.values()
        ),
        "ecosystem_member": any(
            result["peer_scope"] == "ECOSYSTEM" and result["peer_group_id"] != "NONE"
            for row in cases.values() for result in row.current_peer_results
        ),
        "ecosystem_nonmember": any(
            coverage["peer_scope"] == "ECOSYSTEM"
            and coverage["status"] == "NOT_ECOSYSTEM_MEMBER"
            for row in cases.values()
            for coverage in row.current_peer_coverage
        ),
    }
    if not all(category_checks.values()):
        missing = ",".join(name for name, passed in category_checks.items() if not passed)
        raise RuntimeError(f"RELATIVE_VALUATION_CASE_COVERAGE_INCOMPLETE:{missing}")
    summary["case_report_validation"] = {
        "report_count": len(report_checks),
        "report_content_checks": report_checks,
        "category_checks": category_checks,
    }
    (output_dir / "rehearsal_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary
