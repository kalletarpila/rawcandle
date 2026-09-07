from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.snapshot import renderer, v2_assembler
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths

from . import activation, diagnostic_flags, diagnostic_flags_eight, phase10b, persistence, rehearsal
from .readers import ParallelModelRepository


PHASE10A_FINGERPRINT = "30652d3a1a5f7bf2fb73258f3c715d62addc2713f2fe4c9a16e3329433d1d2c0"
APPLIED_AT = "2026-09-07T00:00:00+00:00"


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _backup(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    source_connection = sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _storage(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        freelist = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        sizes = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT name,SUM(pgsize) FROM dbstat "
                "WHERE name LIKE 'diagnostic_flag_%' GROUP BY name ORDER BY name"
            )
        }
    return {
        "bytes": path.stat().st_size,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist,
        "diagnostic_objects_bytes": sizes,
    }


def _new_flag_rows(calculated: Mapping[str, Any], *, fresh: bool) -> list[dict[str, Any]]:
    source = calculated["diagnostics"] if fresh else calculated["diagnostics_full"]
    return [row for row in source if row["flag_name"] == diagnostic_flags_eight.FLAG_NAME]


def _distribution(calculated: Mapping[str, Any]) -> dict[str, Any]:
    historical = _new_flag_rows(calculated, fresh=False)
    current = _new_flag_rows(calculated, fresh=True)
    current_all = calculated["diagnostics"]
    candidate_evaluable = {
        int(row["company_id"])
        for row in current if row["status"].startswith("EVALUATED")
    }
    existing_union = {
        int(row["company_id"])
        for row in current_all
        if row["flag_name"] in diagnostic_flags.FLAG_NAMES
        and row["status"] == "EVALUATED_FLAGGED"
        and int(row["company_id"]) in candidate_evaluable
    }
    candidate = {
        int(row["company_id"])
        for row in current if row["status"] == "EVALUATED_FLAGGED"
    }
    evaluable = [row for row in current if row["status"].startswith("EVALUATED")]
    directions = Counter(
        row["evidence"].get("gap_direction")
        for row in current if row["status"] == "EVALUATED_FLAGGED"
    )
    union = existing_union | candidate
    fresh_count = len(calculated["fresh"])
    return {
        "phase10a_analysis_fingerprint": PHASE10A_FINGERPRINT,
        "historical": {
            "endpoints": len(historical),
            "evaluable": sum(row["status"].startswith("EVALUATED") for row in historical),
            "flagged": sum(row["status"] == "EVALUATED_FLAGGED" for row in historical),
            "status_counts": Counter(row["status"] for row in historical),
        },
        "current_fresh": {
            "universe": fresh_count,
            "evaluable": len(evaluable),
            "flagged": len(candidate),
            "rate_evaluable": len(candidate) / len(evaluable),
            "rate_entire_universe": len(candidate) / fresh_count,
            "directions": directions,
            "status_counts": Counter(row["status"] for row in current),
        },
        "union": {
            "existing_flagged": len(existing_union),
            "overlap": len(existing_union & candidate),
            "newly_flagged": len(candidate - existing_union),
            "combined": len(union),
            "evaluable_denominator": len(evaluable),
            "rate_evaluable": len(union) / len(evaluable),
            "entire_current_fresh_denominator": fresh_count,
            "rate_entire_current_fresh": len(union) / fresh_count,
        },
    }


def _reference_cases(calculated: Mapping[str, Any]) -> dict[str, Any]:
    current = _new_flag_rows(calculated, fresh=True)
    indexed = {str(row["ticker"]): row for row in current}
    output = {}
    for ticker in ("NVDA", "AMZN", "GOOG"):
        row = indexed[ticker]
        output[ticker] = {
            "status": row["status"],
            "reason_code": row["reason_code"],
            **{
                key: row["evidence"].get(key)
                for key in (
                    "ttm_ebit", "ttm_operating_income", "ttm_revenue", "gap_amount",
                    "gap_direction", "gap_signed_to_revenue", "gap_abs_to_revenue",
                    "revenue_denominator", "activation_threshold",
                )
            },
        }
    return output


def _reader_reconciliation(
    connection: sqlite3.Connection, calculated: Mapping[str, Any]
) -> dict[str, Any]:
    repository = ParallelModelRepository(connection)
    persisted = repository.diagnostic_all(
        model_fingerprint=diagnostic_flags_eight.MODEL_FINGERPRINT
    )
    evaluations = [item for endpoint in persisted for item in endpoint["evaluations"]]
    expected = {
        (int(row["company_id"]), int(row["quarter_id"]), str(row["flag_name"])): row
        for row in calculated["diagnostics_full"]
    }
    differences = 0
    for endpoint in persisted:
        for item in endpoint["evaluations"]:
            key = (int(endpoint["company_id"]), int(endpoint["quarter_id"]), str(item["flag_name"]))
            source = expected[key]
            if (
                item["status_text"] != source["status"]
                or item["reason_text"] != source["reason_code"]
                or item["triggered"] != (None if source["triggered"] is None else int(source["triggered"]))
            ):
                differences += 1
            for field in diagnostic_flags_eight.EVIDENCE_FIELDS[item["flag_name"]]:
                if item["evidence"].get(field) != source["evidence"].get(field):
                    differences += 1
    return {
        "endpoint_rows": len(persisted),
        "evaluation_rows": len(evaluations),
        "differences": differences,
        "direction_decoded": sum(
            item["flag_name"] == diagnostic_flags_eight.FLAG_NAME
            and item["evidence"].get("gap_direction") in {"UPLIFT", "DRAG", "ZERO"}
            for item in evaluations
            if item["status_text"].startswith("EVALUATED")
        ),
    }


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    paths = {
        "canonical": repo_root / "data/fundamentals_v4.db",
        "analysis": repo_root / "data/fundamentals_analysis.db",
        "market": repo_root / "data/osakedata.db",
        "provider": repo_root / "data/fundamentals_provider.db",
        "taxonomy": repo_root / "data/analysis.db",
    }
    before = rehearsal.database_integrity(paths)
    _json(output / "production_integrity_before.json", before)

    started = time.monotonic()
    calculated = phase10b.calculate(paths)
    first_calculation_seconds = time.monotonic() - started
    replay = phase10b.calculate(paths)
    replay_fingerprints_equal = calculated["fingerprints"] == replay["fingerprints"]
    if not replay_fingerprints_equal:
        raise RuntimeError("PHASE10B_CALCULATION_NONDETERMINISTIC")
    del replay

    databases = [output / name for name in ("candidate_a.db", "candidate_b.db", "rollback.db")]
    for destination in databases:
        _backup(paths["analysis"], destination)
    baseline_storage = _storage(databases[0])
    peak_wal = 0

    def record_wal(stage: str, connection: sqlite3.Connection) -> None:
        del stage, connection
        nonlocal peak_wal
        wal = Path(str(databases[0]) + "-wal")
        peak_wal = max(peak_wal, wal.stat().st_size if wal.exists() else 0)

    with sqlite3.connect(databases[0]) as connection:
        first_started = time.monotonic()
        first = phase10b.apply_candidate_package(
            connection, calculated, applied_at=APPLIED_AT, stage_callback=record_wal
        )
        first_seconds = time.monotonic() - first_started
        validation = phase10b.validate_candidate_package(connection)
        reader = _reader_reconciliation(connection, calculated)
        active_after = activation.assert_v2_active(connection)
        archived = ParallelModelRepository(connection).diagnostic_all(
            model_fingerprint=diagnostic_flags.MODEL_FINGERPRINT
        )
        no_op_started = time.monotonic()
        no_op = phase10b.apply_candidate_package(connection, calculated, applied_at=APPLIED_AT)
        no_op_seconds = time.monotonic() - no_op_started

    with sqlite3.connect(databases[1]) as connection:
        independent = phase10b.apply_candidate_package(connection, calculated, applied_at=APPLIED_AT)
        phase10b.validate_candidate_package(connection)

    rollback_before = _sha256(databases[2])
    with sqlite3.connect(databases[2]) as connection:
        try:
            phase10b.apply_candidate_package(
                connection, calculated, applied_at=APPLIED_AT,
                inject_failure_at="diagnostic",
            )
        except RuntimeError as error:
            if str(error) != "INJECTED_PHASE10B_DIAGNOSTIC_FAILURE":
                raise
        else:
            raise RuntimeError("PHASE10B_ROLLBACK_INJECTION_DID_NOT_FIRE")
    rollback_after = _sha256(databases[2])

    if first.outcome != "APPLIED" or independent.outcome != "APPLIED":
        raise RuntimeError("PHASE10B_INITIAL_APPLY_FAILED")
    if no_op.outcome != "NO_CHANGE" or no_op.logical_changes != 0:
        raise RuntimeError("PHASE10B_NO_CHANGE_FAILED")
    if first != independent:
        raise RuntimeError("PHASE10B_INDEPENDENT_APPLY_MISMATCH")
    if rollback_before != rollback_after:
        raise RuntimeError("PHASE10B_ROLLBACK_CHANGED_COPY")
    if reader["differences"] != 0:
        raise RuntimeError("PHASE10B_READER_RECONCILIATION_FAILED")

    distribution = _distribution(calculated)
    references = _reference_cases(calculated)
    expected = distribution["current_fresh"]
    if (
        distribution["historical"]["evaluable"], distribution["historical"]["flagged"],
        expected["evaluable"], expected["flagged"], expected["directions"].get("UPLIFT"),
        expected["directions"].get("DRAG"), distribution["union"]["overlap"],
        distribution["union"]["newly_flagged"],
    ) != (36_893, 5_319, 2_110, 334, 230, 104, 226, 108):
        raise RuntimeError("PHASE10B_PHASE10A_RECONCILIATION_FAILED")

    report_paths = SnapshotPaths(
        canonical_db=paths["canonical"], analysis_db=databases[0], market_db=paths["market"],
        taxonomy_db=paths["taxonomy"], provider_db=paths["provider"],
    )
    fresh_new = _new_flag_rows(calculated, fresh=True)
    examples = ["NVDA", "AMZN", "GOOG"]
    examples.append(next(row["ticker"] for row in fresh_new if row["status"] == "EVALUATED_FLAGGED" and row["evidence"].get("gap_direction") == "DRAG"))
    examples.append(next(row["ticker"] for row in fresh_new if row["status"] == "FLAG_NOT_READY"))
    examples.append(next(row["ticker"] for row in fresh_new if row["status"] == "FLAG_NOT_APPLICABLE"))
    generated = {}
    reports_dir = output / "candidate_reports"
    reports_dir.mkdir()
    for ticker in dict.fromkeys(examples):
        snapshot = v2_assembler.assemble_company_snapshot_v2_candidate(
            report_paths, ticker=ticker, report_date=rehearsal.AS_OF.isoformat(),
            model_map=phase10b.MODEL_MAP, package_fingerprint=phase10b.PACKAGE_FINGERPRINT,
            diagnostic_model_contract=diagnostic_flags_eight.MODEL_CONTRACT,
        )
        rendered = renderer.render_snapshot(snapshot)
        if not renderer.verify_rendered_report(rendered):
            raise RuntimeError(f"PHASE10B_REPORT_FINGERPRINT_FAILED:{ticker}")
        target = reports_dir / f"{ticker}_company_snapshot_v2_candidate.md"
        target.write_text(rendered.markdown, encoding="utf-8")
        generated[ticker] = {
            "path": str(target), "content_fingerprint": rendered.content_fingerprint,
            "diagnostic_count": len(snapshot["diagnostic"]["evaluations"]),
        }

    after = rehearsal.database_integrity(paths)
    _json(output / "production_integrity_after.json", after)
    if before != after:
        raise RuntimeError("PHASE10B_PRODUCTION_IMMUTABILITY_FAILED")

    result = {
        "identities": {
            "diagnostic_model_version": diagnostic_flags_eight.MODEL_VERSION,
            "diagnostic_model_fingerprint": diagnostic_flags_eight.MODEL_FINGERPRINT,
            "evidence_schema_version": diagnostic_flags_eight.EVIDENCE_SCHEMA_VERSION,
            "diagnostic_layout_fingerprint": _diagnostic_layout_fingerprint(),
            "snapshot_model_version": phase10b.snapshot_eight.MODEL_VERSION,
            "snapshot_model_fingerprint": phase10b.snapshot_eight.MODEL_FINGERPRINT,
            "snapshot_report_contract": v2_assembler.CANDIDATE_REPORT_CONTRACT,
            "snapshot_presentation_fingerprint": v2_assembler.CANDIDATE_REPORT_PRESENTATION_FINGERPRINT,
            "candidate_package_fingerprint": phase10b.PACKAGE_FINGERPRINT,
            "active_package_fingerprint": active_after.persistence_fingerprint,
        },
        "distribution": distribution,
        "references": references,
        "calculation": {
            "first_seconds": first_calculation_seconds,
            "deterministic_replay": replay_fingerprints_equal,
            "fingerprints": calculated["fingerprints"],
        },
        "persistence": {
            "first": first.__dict__, "independent": independent.__dict__,
            "no_op": no_op.__dict__, "first_seconds": first_seconds,
            "no_op_seconds": no_op_seconds, "validation": validation,
            "reader_reconciliation": reader,
            "archived_seven_flag_endpoints": len(archived),
            "rollback_hash_unchanged": rollback_before == rollback_after,
            "storage_before": baseline_storage, "storage_after": _storage(databases[0]),
            "peak_wal_bytes": peak_wal,
            "schema_migration_required": False,
            "new_persistence_version_required": True,
        },
        "reports": generated,
        "production_unchanged": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _json(output / "phase10b_rehearsal.json", result)
    _json(output / "phase10b_distribution.json", distribution)
    _json(output / "phase10b_reference_cases.json", references)
    _json(output / "phase10b_identities.json", result["identities"])
    return result


def _diagnostic_layout_fingerprint() -> str:
    return persistence._hash({
        flag: diagnostic_flags_eight.EVIDENCE_FIELDS[flag]
        for flag in sorted(diagnostic_flags_eight.FLAG_NAMES)
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the non-production Phase 10B rehearsal")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.repo_root.resolve(), args.output.resolve())
    print(json.dumps(result["identities"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
