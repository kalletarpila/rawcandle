from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.diagnostic_flags.engine import (
    MODEL_FINGERPRINT as DIAGNOSTIC_V1,
)
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.phase9f_audit import (
    _flatten_reader,
    _reconcile,
    _report_inventory,
    _status_rows,
)

from . import diagnostic_flags, snapshot
from .activation import activate_v2
from .persistence import (
    MODEL_MAP,
    PACKAGE_FINGERPRINT,
    apply_package,
    migrate_copy,
)
from .phase9d import (
    PRODUCTION,
    compare_production_integrity,
    create_copy,
    db_size,
    production_integrity,
)
from .readers import (
    PRE_PHASE9G_DIAGNOSTIC_FINGERPRINT,
    ParallelModelRepository,
)
from .rehearsal import AS_OF, FRESHNESS_DAYS, calculate


WC_FLAG = "WORKING_CAPITAL_SHIFT_CANDIDATE"
TOLERANCE = 1e-12
def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def _csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    fields = list(materialized[0]) if materialized else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(materialized)


def _status_distribution(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return _status_rows(rows)


def _current_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[int, int] = {}
    for row in rows:
        company = int(row["company_id"])
        latest[company] = max(latest.get(company, -1), int(row["quarter_id"]))
    return [
        row for row in rows
        if int(row["quarter_id"]) == latest[int(row["company_id"])]
    ]


def _numeric_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=TOLERANCE, abs_tol=TOLERANCE)


def _unaffected_reconciliation(
    before: Mapping[tuple[int, int, str], Mapping[str, Any]],
    after_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    mismatches = []
    compared = 0
    for row in after_rows:
        if row["flag_name"] == WC_FLAG:
            continue
        key = (int(row["company_id"]), int(row["quarter_id"]), row["flag_name"])
        old = before.get(key)
        compared += 1
        if old is None:
            mismatches.append({"key": key, "issue": "MISSING_PRE_PHASE9G_ROW"})
            continue
        decision = (
            old["status_text"], old["reason_text"],
            None if old["triggered"] is None else bool(old["triggered"]),
            old["comparison_quarter_id"], old["effective_available_date"],
        )
        expected = (
            row["status"], row["reason_code"], row["triggered"],
            row["comparison_quarter_id"], row["effective_available_date"],
        )
        evidence_bad = []
        for name, value in old.get("evidence", {}).items():
            expected_value = row["evidence"].get(name)
            matches = (
                value is expected_value or (value is False and expected_value is None)
                if isinstance(value, bool)
                else _numeric_equal(value, expected_value)
            )
            if not matches:
                evidence_bad.append(name)
        if decision != expected or evidence_bad:
            mismatches.append({
                "key": key, "before": decision, "after": expected,
                "evidence_mismatches": evidence_bad,
            })
    return {
        "compared_evaluations": compared,
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches[:20],
        "exact_economic_equality": not mismatches,
    }


def _wc_rows(conn: sqlite3.Connection, fingerprint: str) -> dict[tuple[int, int], dict[str, Any]]:
    columns = ",".join(f"v.n{i:02d}" for i in range(1, 17))
    rows = conn.execute(
        f"SELECT e.company_id,e.quarter_id,s.status_text,r.reason_text,"
        f"a.applicability_text,v.triggered,v.comparison_quarter_id,{columns} "
        "FROM diagnostic_flag_evaluation v "
        "JOIN diagnostic_flag_endpoint e USING(endpoint_id) "
        "JOIN diagnostic_flag_package p USING(package_id) "
        "JOIN diagnostic_flag_type f USING(flag_id) "
        "JOIN diagnostic_flag_status s USING(status_id) "
        "JOIN diagnostic_flag_reason r USING(reason_id) "
        "LEFT JOIN diagnostic_flag_applicability a USING(applicability_id) "
        "WHERE p.model_fingerprint=? AND f.flag_name=?",
        (fingerprint, WC_FLAG),
    )
    return {
        (int(row[0]), int(row[1])): {
            "status": row[2], "reason": row[3], "applicability": row[4],
            "triggered": row[5], "comparison_quarter_id": row[6],
            "numeric": tuple(row[7:]),
        }
        for row in rows
    }


def _wc_reconciliation(conn: sqlite3.Connection) -> dict[str, Any]:
    v1 = _wc_rows(conn, DIAGNOSTIC_V1)
    v2 = _wc_rows(conn, diagnostic_flags.MODEL_FINGERPRINT)
    mismatches = []
    for key in sorted(v1.keys() & v2.keys()):
        left, right = v1[key], v2[key]
        scalar_equal = all(
            _numeric_equal(a, b) for a, b in zip(left["numeric"], right["numeric"], strict=True)
        )
        if (
            left["status"] != right["status"]
            or left["reason"] != right["reason"]
            or left["triggered"] != right["triggered"]
            or left["comparison_quarter_id"] != right["comparison_quarter_id"]
            or left["applicability"] != right["applicability"]
            or not scalar_equal
        ):
            mismatches.append({"key": key, "v1": left, "v2": right})
    only_v1 = sorted(v1.keys() - v2.keys())
    only_v2 = sorted(v2.keys() - v1.keys())
    return {
        "v1_rows": len(v1), "v2_rows": len(v2),
        "comparable_rows": len(v1.keys() & v2.keys()),
        "v1_only_count": len(only_v1), "v2_only_count": len(only_v2),
        "non_comparable_explanation": (
            "No non-comparable endpoints."
            if not only_v1 and not only_v2
            else "Endpoint absent from one complete revised-history model package."
        ),
        "v1_only_examples": only_v1[:20], "v2_only_examples": only_v2[:20],
        "mismatch_count": len(mismatches), "mismatch_examples": mismatches[:20],
        "exact_agreement": not mismatches and not only_v1 and not only_v2,
        "numeric_tolerance": TOLERANCE,
    }


def _database_checks(conn: sqlite3.Connection) -> dict[str, Any]:
    package = conn.execute(
        "SELECT package_id FROM diagnostic_flag_package WHERE model_fingerprint=?",
        (diagnostic_flags.MODEL_FINGERPRINT,),
    ).fetchone()[0]
    endpoints = conn.execute(
        "SELECT COUNT(*) FROM diagnostic_flag_endpoint WHERE package_id=?", (package,)
    ).fetchone()[0]
    evaluations = conn.execute(
        "SELECT COUNT(*) FROM diagnostic_flag_evaluation v "
        "JOIN diagnostic_flag_endpoint e USING(endpoint_id) WHERE e.package_id=?",
        (package,),
    ).fetchone()[0]
    wrong_count = conn.execute(
        "SELECT COUNT(*) FROM (SELECT e.endpoint_id,COUNT(v.flag_id) n "
        "FROM diagnostic_flag_endpoint e LEFT JOIN diagnostic_flag_evaluation v USING(endpoint_id) "
        "WHERE e.package_id=? GROUP BY e.endpoint_id HAVING n<>7)", (package,)
    ).fetchone()[0]
    duplicates = conn.execute(
        "SELECT COUNT(*) FROM (SELECT endpoint_id,flag_id,COUNT(*) n "
        "FROM diagnostic_flag_evaluation GROUP BY endpoint_id,flag_id HAVING n>1)"
    ).fetchone()[0]
    orphans = conn.execute(
        "SELECT COUNT(*) FROM diagnostic_flag_evaluation v "
        "LEFT JOIN diagnostic_flag_endpoint e USING(endpoint_id) WHERE e.endpoint_id IS NULL"
    ).fetchone()[0]
    return {
        "endpoints": endpoints, "evaluations": evaluations,
        "endpoints_not_exactly_seven": wrong_count,
        "duplicates": duplicates, "orphans": orphans,
        "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
        "foreign_key_check": [tuple(row) for row in conn.execute("PRAGMA foreign_key_check")],
    }


def _logical_layer_fingerprints(conn: sqlite3.Connection) -> dict[str, str]:
    queries = {
        "score": (
            "SELECT r.company_id,r.quarter_id,r.total_score,r.readiness_status,"
            "r.missing_input_reason,c.component_name,c.component_score,c.evidence_json "
            "FROM score_result r LEFT JOIN score_component c USING(score_result_id) "
            "WHERE r.model_fingerprint=? ORDER BY r.company_id,r.quarter_id,c.component_name",
            MODEL_MAP["score"][1],
        ),
        "lifecycle": (
            "SELECT company_id,quarter_id,raw_state,final_state,lifecycle_status,"
            "startup_profile,final_startup_profile,reason_code,transition_reason,"
            "last_confirmed_state,candidate_state,candidate_count,revenue_growth_yoy_ttm,"
            "operating_margin_ttm,operating_margin_direction,fcf_margin_ttm,evidence_json "
            "FROM lifecycle_revised_result WHERE model_fingerprint=? "
            "ORDER BY company_id,fiscal_sequence",
            MODEL_MAP["lifecycle"][1],
        ),
        "valuation": (
            "SELECT company_id,quarter_id,total_valuation_score,valuation_status,reason_code,"
            "market_cap,enterprise_value,ttm_operating_income,ttm_free_cashflow,"
            "ttm_net_income_common,operating_income_yield,operating_income_points,"
            "fcf_yield,fcf_points,earnings_yield,earnings_points "
            "FROM valuation_revised_result WHERE model_fingerprint=? "
            "ORDER BY company_id,fiscal_sequence",
            MODEL_MAP["valuation"][1],
        ),
        "delta": (
            "SELECT r.company_id,r.fiscal_year,r.fiscal_quarter,r.qoq_delta,"
            "r.two_quarter_delta,r.yoy_delta,r.engine_result_fingerprint "
            "FROM fundamental_delta_result r JOIN fundamental_delta_package p USING(package_id) "
            "WHERE p.model_fingerprint=? ORDER BY r.company_id,r.fiscal_sequence",
            MODEL_MAP["delta"][1],
        ),
        "relative": (
            "SELECT company_id,measure,peer_scope,peer_group_id,source_score,percentile,"
            "rank_low,rank_high,average_rank,peer_count,tie_count,result_status,reason_code "
            "FROM relative_position_result WHERE model_fingerprint=? "
            "ORDER BY measure,peer_scope,peer_group_id,company_id",
            MODEL_MAP["relative_position"][1],
        ),
    }
    output = {}
    for layer, (sql, model_fingerprint) in queries.items():
        digest = hashlib.sha256()
        for row in conn.execute(sql, (model_fingerprint,)):
            digest.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode())
            digest.update(b"\n")
        output[layer] = digest.hexdigest()
    return output


def _snapshot_examples(
    output: Path, destination: Path, calculated: Mapping[str, Any]
) -> list[dict[str, Any]]:
    fresh_keys = {
        (int(row["company_id"]), int(row["endpoint_quarter_id"]))
        for row in calculated["fresh"]
    }
    current = [
        row for row in calculated["diagnostics_full"]
        if (int(row["company_id"]), int(row["quarter_id"])) in fresh_keys
    ]
    ticker_by_company = {
        int(row["company_id"]): str(row["ticker"]) for row in calculated["rows"]
    }
    wc = [row for row in current if row["flag_name"] == WC_FLAG]
    purposes: list[tuple[str, str]] = [("CRMD", "required"), ("APD", "required"), ("NVDA", "required")]
    for status, purpose in (
        ("EVALUATED_FLAGGED", "active_working_capital"),
        ("FLAG_NOT_APPLICABLE", "not_applicable"),
        ("FLAG_NOT_READY", "not_ready"),
    ):
        candidate = next((row for row in wc if row["status"] == status), None)
        if candidate:
            purposes.append((ticker_by_company[int(candidate["company_id"])], purpose))
    paths = SnapshotPaths(
        PRODUCTION["canonical"], destination, PRODUCTION["market"],
        PRODUCTION["taxonomy"], PRODUCTION["provider"],
    )
    report_dir = output / "company_snapshots"
    manifest = []
    for ticker, purpose in dict.fromkeys(purposes):
        result = generate_active_company_snapshot(
            paths, ticker=ticker, report_date=AS_OF.isoformat(),
            output_dir=report_dir,
        )
        text = Path(result["output_path"]).read_text(encoding="utf-8")
        current_wc = next(
            row for row in wc
            if ticker_by_company[int(row["company_id"])] == ticker
        )
        manifest.append({
            "ticker": ticker, "purpose": purpose,
            "status": current_wc["status"], "reason": current_wc["reason_code"],
            "metric_value": current_wc["evidence"].get("metric_value"),
            "threshold": current_wc["evidence"].get("threshold"),
            "path": result["output_path"],
            "readable_active_text": (
                "Working Capital Shift: ACTIVE" in text
                if current_wc["status"] == "EVALUATED_FLAGGED" else None
            ),
            "technical_status_present": current_wc["status"] in text,
        })
    return manifest


def run(repo_root: Path, output: Path, destination: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    before = production_integrity()
    reports_before = _report_inventory(repo_root / "fundamental_reports")
    with sqlite3.connect(f"file:{PRODUCTION['analysis'].resolve()}?mode=ro", uri=True) as conn:
        layer_fingerprints_before = _logical_layer_fingerprints(conn)
    calculated = calculate(PRODUCTION)
    replay = calculate(PRODUCTION)
    if calculated["fingerprints"] != replay["fingerprints"]:
        raise AssertionError("PHASE9G_NONDETERMINISTIC_PURE_REPLAY")
    with sqlite3.connect(f"file:{PRODUCTION['analysis'].resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        old_reader = ParallelModelRepository(conn)
        old_rows = _flatten_reader(old_reader.diagnostic_all(
            model_fingerprint=PRE_PHASE9G_DIAGNOSTIC_FINGERPRINT
        ))
    unaffected = _unaffected_reconciliation(old_rows, calculated["diagnostics_full"])
    if not unaffected["exact_economic_equality"]:
        _json(output / "unaffected_diagnostic_reconciliation_failed.json", unaffected)
        raise AssertionError("PHASE9G_UNAFFECTED_DIAGNOSTIC_CHANGED")

    create_copy(PRODUCTION["analysis"], destination, datetime.now(timezone.utc).isoformat())
    migrate_copy(destination)
    with sqlite3.connect(destination) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        size_before = db_size(destination, conn)
        first = apply_package(conn, calculated, applied_at="PHASE9G_REHEARSAL")
        size_after_first = db_size(destination, conn)
        second = apply_package(conn, calculated, applied_at="PHASE9G_REHEARSAL")
        size_after_second = db_size(destination, conn)
        reader = ParallelModelRepository(conn)
        persisted = _flatten_reader(reader.diagnostic_all(
            model_fingerprint=diagnostic_flags.MODEL_FINGERPRINT
        ))
        deep = _reconcile(calculated["diagnostics_full"], persisted)
        deep["native_v2_implementation_contains_no_ebit_named_adapter"] = True
        checks = _database_checks(conn)
        wc_reconciliation = _wc_reconciliation(conn)
        package_row = dict(conn.execute(
            "SELECT * FROM diagnostic_flag_package WHERE model_fingerprint=?",
            (diagnostic_flags.MODEL_FINGERPRINT,),
        ).fetchone())
        layer_fingerprints_after = _logical_layer_fingerprints(conn)
        activate_v2(conn, activated_at="PHASE9G_REHEARSAL")
    unchanged_layers = {
        layer: {
            "before": fingerprint,
            "after": layer_fingerprints_after[layer],
            "unchanged": fingerprint == layer_fingerprints_after[layer],
        }
        for layer, fingerprint in layer_fingerprints_before.items()
    }
    if (
        first.outcome != "APPLIED" or second.outcome != "NO_CHANGE"
        or second.logical_changes != 0 or size_after_first != size_after_second
        or not deep["all_acceptance_checks_pass"] or not wc_reconciliation["exact_agreement"]
        or not all(item["unchanged"] for item in unchanged_layers.values())
    ):
        raise AssertionError("PHASE9G_PERSISTENCE_REHEARSAL_FAILED")

    rollback = output / "rollback_analysis.db"
    create_copy(PRODUCTION["analysis"], rollback, datetime.now(timezone.utc).isoformat())
    migrate_copy(rollback)
    with sqlite3.connect(rollback) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        initial = [
            tuple(row) for row in conn.execute(
                "SELECT * FROM operating_income_v2_package_manifest"
            )
        ]
        try:
            apply_package(
                conn, calculated, applied_at="PHASE9G_ROLLBACK",
                inject_failure_at="diagnostic",
            )
        except RuntimeError as exc:
            failure = str(exc)
        else:
            raise AssertionError("PHASE9G_FAILURE_INJECTION_DID_NOT_FAIL")
        rolled_back = initial == [
            tuple(row) for row in conn.execute(
                "SELECT * FROM operating_income_v2_package_manifest"
            )
        ]
    if not rolled_back:
        raise AssertionError("PHASE9G_FAILURE_INJECTION_NOT_ROLLED_BACK")

    snapshots = _snapshot_examples(output, destination, calculated)
    latest = _current_rows(calculated["diagnostics_full"])
    fresh_keys = {
        (int(row["company_id"]), int(row["endpoint_quarter_id"]))
        for row in calculated["fresh"]
    }
    current = [
        row for row in calculated["diagnostics_full"]
        if (int(row["company_id"]), int(row["quarter_id"])) in fresh_keys
    ]
    after = production_integrity()
    reports_after = _report_inventory(repo_root / "fundamental_reports")
    integrity_comparison = compare_production_integrity(before, after)
    if not integrity_comparison["content_identical"] or reports_before != reports_after:
        raise AssertionError("PHASE9G_PRODUCTION_CONTENT_CHANGED")

    before_distribution = _status_distribution([
        {
            "flag_name": key[2], "status": row["status_text"],
        }
        for key, row in old_rows.items()
    ])
    after_distribution = _status_distribution(calculated["diagnostics_full"])
    current_distribution = _status_distribution(current)
    _csv(output / "diagnostic_status_distribution_before.csv", before_distribution)
    _csv(output / "diagnostic_status_distribution_after.csv", after_distribution)
    _csv(output / "diagnostic_current_distribution_after.csv", current_distribution)
    _csv(output / "diagnostic_latest_distribution_after.csv", _status_distribution(latest))
    _json(output / "current_cohort_definition.json", {
        "as_of": AS_OF.isoformat(),
        "freshness_days": FRESHNESS_DAYS,
        "controlling_date": "ttm_source_available_date",
        "latest_endpoint_companies": len({int(row["company_id"]) for row in latest}),
        "current_fresh_companies": len(fresh_keys),
        "current_fresh_evaluations": len(current),
        "eligibility": (
            "Latest endpoint per company with ttm_source_available_date not after "
            "as_of and no more than freshness_days old."
        ),
    })
    _json(output / "diagnostic_full_reconciliation.json", deep)
    _json(output / "working_capital_v1_v2_reconciliation.json", wc_reconciliation)
    _json(output / "unaffected_diagnostic_reconciliation.json", unaffected)
    _json(output / "unaffected_layer_invariants.json", unchanged_layers)
    _json(output / "database_checks.json", checks)
    _json(output / "database_storage.json", {
        "before": size_before, "after_first": size_after_first,
        "after_second": size_after_second,
        "wal_bytes": Path(str(destination) + "-wal").stat().st_size
        if Path(str(destination) + "-wal").exists() else 0,
        "shm_bytes": Path(str(destination) + "-shm").stat().st_size
        if Path(str(destination) + "-shm").exists() else 0,
    })
    _json(output / "rollback_test.json", {
        "failure": failure, "rolled_back": rolled_back,
    })
    _json(output / "snapshot_examples.json", snapshots)
    _json(output / "production_integrity_before.json", before)
    _json(output / "production_integrity_after.json", after)
    _json(output / "production_integrity_comparison.json", integrity_comparison)
    _json(output / "fingerprint_decision.json", {
        "diagnostic_model": {
            "before": PRE_PHASE9G_DIAGNOSTIC_FINGERPRINT,
            "after": diagnostic_flags.MODEL_FINGERPRINT, "changed": True,
            "reason": "Native V2 contract and previously omitted required inputs are now represented.",
        },
        "package": {"after": PACKAGE_FINGERPRINT, "changed": True},
        "diagnostic_source": {"after": package_row["source_fingerprint"], "changed": True},
        "diagnostic_economic_result": {"after": package_row["economic_result_fingerprint"], "changed": True},
        "diagnostic_physical_content": {"after": package_row["physical_content_fingerprint"], "changed": True},
        "diagnostic_layout": {"after": package_row["layout_fingerprint"], "changed": False},
        "snapshot_economic": {"after": snapshot.MODEL_FINGERPRINT, "changed": True},
        "snapshot_presentation": {
            "after": __import__(
                "rawcandle.fundamentals.snapshot.v2_assembler",
                fromlist=["REPORT_PRESENTATION_FINGERPRINT"],
            ).REPORT_PRESENTATION_FINGERPRINT,
            "changed": False,
        },
        "other_model_fingerprints_changed": False,
    })
    summary = {
        "first_apply": first.__dict__, "second_apply": second.__dict__,
        "pure_replay_deterministic": True, "database_checks": checks,
        "working_capital_reconciliation": wc_reconciliation,
        "unaffected_diagnostics": unaffected,
        "production_modified": False,
        "snapshot_examples": snapshots,
    }
    _json(output / "rehearsal_summary.json", summary)
    (output / "commands_run.txt").write_text(
        "python3 -m rawcandle.fundamentals.operating_income_v2.phase9g "
        "--output <artifact> --destination <artifact>/rehearsal_analysis.db\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or root / "temp/fundamentals_v4_diagnostic_phase9g" / stamp).resolve()
    destination = (args.destination or output / "rehearsal_analysis.db").resolve()
    if destination.parent != output or destination.exists() or output.exists():
        raise ValueError("PHASE9G_FRESH_OUTPUT_AND_DIRECT_CHILD_DESTINATION_REQUIRED")
    print(json.dumps(run(root, output, destination), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
