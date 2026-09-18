"""Build a disposable, production-shaped V2 analysis database from sources."""

from __future__ import annotations

import argparse
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.delta import persistence as delta_storage
from rawcandle.fundamentals.diagnostic_flags import persistence as diagnostic_storage
from rawcandle.fundamentals.lifecycle import revised_history
from rawcandle.fundamentals.relative_position import persistence as rp_storage
from rawcandle.fundamentals.relative_valuation import persistence as rv_storage
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.source import ReadOnlySourcePaths, load_relative_valuation_source
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL, bootstrap_database
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.v2_assembler import assemble_company_snapshot_v2
from rawcandle.fundamentals.valuation import persistence as valuation_storage

from . import activation, phase10b, persistence, relative_position, score
from .readers import ActiveModelRepository, ParallelModelRepository
from .taxonomy_source import load_active_dc_memberships


PRODUCTION_ANALYSIS = Path(__file__).resolve().parents[3] / "data/fundamentals_analysis.db"
REQUIRED_SOURCES = ("provider", "canonical", "market", "taxonomy")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _event(output: Path, stage: str, status: str, **details: Any) -> None:
    with (output / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at_utc": _utc_now(), "stage": stage, "status": status, **details}, sort_keys=True, default=str) + "\n")


@contextmanager
def _heartbeat(output: Path, stage: str):
    stop = threading.Event()

    def emit() -> None:
        while not stop.wait(15):
            _event(output, stage, "RUNNING")

    thread = threading.Thread(target=emit, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def _schema(conn: sqlite3.Connection, target: Path, applied_at: str) -> None:
    bootstrap_database(target, "fundamentals_analysis", ANALYSIS_SCHEMA_SQL, applied_at)
    conn.executescript(revised_history.SCHEMA_SQL)
    valuation_storage.ensure_schema(conn)
    conn.executescript(delta_storage.SCHEMA_SQL)
    diagnostic_storage.ensure_schema(conn)
    rp_storage.ensure_schema(conn, applied_at_utc=applied_at)
    persistence.ensure_schema(conn)
    rv_storage.ensure_schema(conn, applied_at_utc=applied_at)
    conn.commit()


def validate_rebuild(
    target: Path, *, as_of_date: str, taxonomy_dependency: Mapping[str, str],
    sources: Mapping[str, Path],
) -> dict[str, Any]:
    with sqlite3.connect(f"file:{target.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        active = activation.assert_v2_active(conn)
        if active.persistence_fingerprint != phase10b.PACKAGE_FINGERPRINT:
            raise RuntimeError("V2_REBUILD_ACTIVE_PACKAGE_MISMATCH")
        package = phase10b.validate_candidate_package(conn)
        manifest = ParallelModelRepository(conn).package_manifest(phase10b.PACKAGE_FINGERPRINT)
        physical = persistence.physical_fingerprint(conn, diagnostic_model=phase10b.diagnostic_flags_eight)
        if physical != manifest["physical_content_fingerprint"]:
            raise RuntimeError("V2_REBUILD_PACKAGE_PHYSICAL_MISMATCH")
        rp = conn.execute(
            "SELECT s.snapshot_id,s.snapshot_date,d.taxonomy_domain,d.taxonomy_version,"
            "d.taxonomy_semantic_fingerprint,d.calculation_as_of_date "
            "FROM relative_position_active_snapshot a JOIN relative_position_snapshot s USING(snapshot_id) "
            "JOIN relative_position_v2_taxonomy_dependency d USING(snapshot_id) WHERE a.model_fingerprint=?",
            (relative_position.MODEL_FINGERPRINT,),
        ).fetchone()
        if rp is None or (rp["snapshot_date"], rp["calculation_as_of_date"]) != (as_of_date, as_of_date):
            raise RuntimeError("V2_REBUILD_RP_DATE_MISMATCH")
        if (rp["taxonomy_domain"], rp["taxonomy_version"], rp["taxonomy_semantic_fingerprint"]) != (
            taxonomy_dependency["domain"], taxonomy_dependency["version"], taxonomy_dependency["semantic_fingerprint"]
        ):
            raise RuntimeError("V2_REBUILD_TAXONOMY_MISMATCH")
        rv = rv_storage.RelativeValuationRepository(conn).active_metadata(
            model_fingerprint=rv_storage.MODEL_FINGERPRINT
        )
        if rv is None or rv.get("as_of_date") != as_of_date:
            raise RuntimeError("V2_REBUILD_RV_MISSING_OR_WRONG_DATE")
        company = conn.execute(
            "SELECT company_id FROM score_result WHERE model_fingerprint=? ORDER BY company_id LIMIT 1",
            (score.MODEL_FINGERPRINT,),
        ).fetchone()
        if company is None:
            raise RuntimeError("V2_REBUILD_SCORE_EMPTY")
        reader = ActiveModelRepository(conn)
        if reader.score_current(company[0]) is None or reader.valuation_current(company[0]) is None:
            raise RuntimeError("V2_REBUILD_ACTIVE_READER_FAILED")
        model_tables = {
            "score_result": "score", "lifecycle_revised_result": "lifecycle",
            "valuation_revised_result": "valuation", "fundamental_delta_package": "delta",
            "diagnostic_flag_package": "diagnostic_flags", "relative_position_snapshot": "relative_position",
        }
        for table, component in model_tables.items():
            if conn.execute(
                f"SELECT 1 FROM {table} WHERE model_fingerprint<>? LIMIT 1",
                (phase10b.MODEL_MAP[component][1],),
            ).fetchone():
                raise RuntimeError(f"V2_REBUILD_NON_V2_RESULT:{table}")
        for table in ("lifecycle_result", "valuation_result"):
            if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise RuntimeError(f"V2_REBUILD_LEGACY_RESULT:{table}")
        if conn.execute(
            "SELECT 1 FROM relative_position_active_snapshot WHERE model_fingerprint<>? LIMIT 1",
            (relative_position.MODEL_FINGERPRINT,),
        ).fetchone():
            raise RuntimeError("V2_REBUILD_LEGACY_RP_POINTER")
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("V2_REBUILD_QUICK_CHECK_FAILED")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("V2_REBUILD_FOREIGN_KEY_CHECK_FAILED")
        report = {"package": package, "rp_snapshot_id": rp["snapshot_id"], "rv": rv, "active": asdict(active), "reader_company_id": company[0]}
    rv_source = load_relative_valuation_source(
        ReadOnlySourcePaths(target, sources["canonical"], sources["market"], sources["taxonomy"], sources["provider"]),
        as_of_date=as_of_date,
    )
    expected_rv = calculate_relative_valuation(
        rv_source.inputs, as_of_date=as_of_date,
        classification_fingerprint=rv_source.classification_fingerprint,
        taxonomy_fingerprint=rv_source.taxonomy_fingerprint,
    )
    if (report["rv"]["source_fingerprint"], report["rv"]["result_fingerprint"]) != (
        expected_rv.source_fingerprint, expected_rv.result_fingerprint
    ):
        raise RuntimeError("V2_REBUILD_RV_SOURCE_OR_RESULT_MISMATCH")
    _, current_taxonomy = load_active_dc_memberships(sources["taxonomy"], sources["canonical"])
    if any(current_taxonomy[key] != taxonomy_dependency[key] for key in ("domain", "version", "semantic_fingerprint")):
        raise RuntimeError("V2_REBUILD_ACTIVE_TAXONOMY_CHANGED")
    with sqlite3.connect(f"file:{sources['canonical'].resolve()}?mode=ro", uri=True) as canonical:
        sample = canonical.execute(
            "SELECT s.current_ticker FROM security s JOIN v4_ttm_values t USING(company_id) "
            "WHERE s.active=1 AND t.ttm_source_available_date<=? "
            "ORDER BY s.company_id,t.endpoint_fiscal_year DESC,t.endpoint_fiscal_quarter DESC LIMIT 1",
            (as_of_date,),
        ).fetchone()
    if sample is None:
        raise RuntimeError("V2_REBUILD_NO_SNAPSHOT_READER_SAMPLE")
    ticker = str(sample[0])
    snapshot = assemble_company_snapshot_v2(
        SnapshotPaths(sources["canonical"], target, sources["market"], sources["taxonomy"], sources["provider"]),
        ticker=ticker, report_date=as_of_date,
    )
    if snapshot["identity"]["ticker"] != ticker:
        raise RuntimeError("V2_REBUILD_SNAPSHOT_READER_FAILED")
    report["rv_input_source_fingerprint"] = rv_source.source_fingerprint
    report["rv_input_count"] = len(rv_source.inputs)
    report["snapshot_reader_ticker"] = ticker
    return report


def rebuild_v2_analysis(
    target: Path,
    sources: Mapping[str, Path],
    *,
    as_of_date: str,
    output: Path,
    inject_failure_at: str | None = None,
) -> dict[str, Any]:
    date.fromisoformat(as_of_date)
    target = target.absolute()
    if target.is_symlink() or target.resolve() == PRODUCTION_ANALYSIS.resolve():
        raise PermissionError("V2_REBUILD_PRODUCTION_TARGET_REJECTED")
    if target.exists():
        raise FileExistsError("V2_REBUILD_TARGET_MUST_BE_NEW")
    if set(sources) != set(REQUIRED_SOURCES):
        raise ValueError("V2_REBUILD_SOURCE_ROLES_REQUIRED")
    source_paths = {key: Path(value).resolve(strict=True) for key, value in sources.items()}
    if target.resolve() in source_paths.values() or PRODUCTION_ANALYSIS.resolve() in source_paths.values():
        raise ValueError("V2_REBUILD_ANALYSIS_CANNOT_BE_SOURCE")
    output.mkdir(parents=True, exist_ok=True)
    applied_at = _utc_now()
    state: dict[str, Any] = {"status": "FAILED", "as_of_date": as_of_date, "target": str(target)}
    stage = "bootstrap"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _event(output, stage, "STARTED")
        with sqlite3.connect(target) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            _schema(conn, target, applied_at)
        _event(output, stage, "COMPLETED")
        if inject_failure_at == stage:
            raise RuntimeError("INJECTED_V2_REBUILD_BOOTSTRAP_FAILURE")

        paths = {**source_paths, "analysis": target}
        stage = "v2_calculation"
        _event(output, stage, "STARTED")
        with _heartbeat(output, stage):
            calculated = phase10b.calculate(paths, verify_v1_overlap=False, as_of_date=as_of_date)
        _event(output, stage, "COMPLETED", fingerprints=calculated["fingerprints"])
        if inject_failure_at == stage:
            raise RuntimeError("INJECTED_V2_REBUILD_CALCULATION_FAILURE")

        stage = "v2_persistence"
        _event(output, stage, "STARTED")
        with _heartbeat(output, stage):
            with sqlite3.connect(target) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                package = phase10b.apply_candidate_package(conn, calculated, applied_at=applied_at)
                phase10b.validate_candidate_package(conn)
                activation.activate_package(conn, phase10b.PACKAGE_FINGERPRINT, activated_at=applied_at)
                conn.commit()
        _event(output, stage, "COMPLETED", outcome=package.outcome)
        if inject_failure_at == stage:
            raise RuntimeError("INJECTED_V2_REBUILD_PERSISTENCE_FAILURE")

        stage = "rv"
        _event(output, stage, "STARTED")
        with _heartbeat(output, stage):
            rv_source = load_relative_valuation_source(
                ReadOnlySourcePaths(target, source_paths["canonical"], source_paths["market"], source_paths["taxonomy"], source_paths["provider"]),
                as_of_date=as_of_date,
            )
            rv_snapshot = calculate_relative_valuation(
                rv_source.inputs,
                as_of_date=as_of_date,
                classification_fingerprint=rv_source.classification_fingerprint,
                taxonomy_fingerprint=rv_source.taxonomy_fingerprint,
            )
            rv_storage.validate_snapshot(rv_snapshot, rv_source.inputs)
            with sqlite3.connect(target) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                rv_apply = rv_storage.apply_snapshot(conn, rv_snapshot, rv_source.inputs, applied_at_utc=applied_at)
        _event(output, stage, "COMPLETED", outcome=rv_apply.outcome, source_fingerprint=rv_snapshot.source_fingerprint)
        if inject_failure_at == stage:
            raise RuntimeError("INJECTED_V2_REBUILD_RV_FAILURE")

        stage = "validation"
        _event(output, stage, "STARTED")
        with _heartbeat(output, stage):
            validation = validate_rebuild(
                target, as_of_date=as_of_date, taxonomy_dependency=calculated["taxonomy_dependency"],
                sources=source_paths,
            )
        if inject_failure_at == stage:
            raise RuntimeError("INJECTED_V2_REBUILD_VALIDATION_FAILURE")
        state.update(status="READY", fingerprints=calculated["fingerprints"], taxonomy_dependency=calculated["taxonomy_dependency"], package=asdict(package), rv=asdict(rv_apply), rv_input_count=len(rv_source.inputs), rv_input_source_fingerprint=rv_source.source_fingerprint, rv_source_fingerprint=rv_snapshot.source_fingerprint, rv_result_fingerprint=rv_snapshot.result_fingerprint, validation=validation)
        _event(output, stage, "COMPLETED")
    except Exception as exc:
        state.update(failed_stage=stage, error=f"{type(exc).__name__}: {exc}")
        _event(output, stage, "FAILED", error=state["error"])
        raise
    finally:
        (output / "result.json").write_text(json.dumps(state, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        (output / "operation_report.md").write_text(
            f"# Full V2 analysis rebuild\n\nStatus: {state['status']}\n\nAs-of: {as_of_date}\n\n"
            f"Target: {target}\n\n" + (f"Failed at {state['failed_stage']}: {state['error']}\n" if state["status"] != "READY" else "V2 and RV validated; candidate is ready for later controlled replacement.\n"),
            encoding="utf-8",
        )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a fresh V2 analysis database from authoritative sources")
    for name in ("target", "provider", "canonical", "market", "taxonomy", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    args = parser.parse_args()
    result = rebuild_v2_analysis(args.target, {name: getattr(args, name) for name in REQUIRED_SOURCES}, as_of_date=args.as_of_date, output=args.output)
    print(json.dumps({"status": result["status"], "target": result["target"], "as_of_date": result["as_of_date"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
