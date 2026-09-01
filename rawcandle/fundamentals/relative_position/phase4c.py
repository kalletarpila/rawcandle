from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT,
    RelativeObservation,
    calculate_snapshot,
)
from rawcandle.fundamentals.relative_position.persistence import (
    ApplyReport,
    apply_snapshot,
    ensure_schema,
    quick_check,
)
from rawcandle.fundamentals.relative_position.source import (
    DEFAULT_FRESHNESS_DAYS,
    ReadOnlySourcePaths,
    load_current_relative_source,
)


PRODUCTION_PATHS = {
    Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
    Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"),
    Path("/home/kalle/projects/rawcandle/data/osakedata.db"),
    Path("/home/kalle/projects/rawcandle/data/analysis.db"),
    Path("/home/kalle/projects/rawcandle/swingmaster_rc.db"),
}


def sqlite_online_backup(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("PHASE4C_BACKUP_DESTINATION_ALREADY_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
        destination_conn.commit()
    finally:
        destination_conn.close()
        source_conn.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_evidence(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        objects = [tuple(row) for row in conn.execute(
            "SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"
        )]
        tables = {str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        )}
        counts = {}
        for table in (
            "score_result", "score_component", "lifecycle_revised_result",
            "valuation_revised_result", "relative_position_snapshot",
            "relative_position_result", "relative_position_coverage",
        ):
            if table in tables:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": _sha256(path),
        "schema_sha256": hashlib.sha256(repr(objects).encode("utf-8")).hexdigest(),
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "row_counts": counts,
        "quick_check": quick,
    }


def validate_request(
    paths: ReadOnlySourcePaths,
    *,
    destination: Path,
    model_fingerprint: str,
    full_universe: bool,
    apply: bool,
) -> None:
    all_paths = (
        paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db,
        destination,
    )
    if any(not path.is_absolute() for path in all_paths):
        raise ValueError("PHASE4C_ALL_DATABASE_PATHS_MUST_BE_ABSOLUTE")
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("RELATIVE_POSITION_MODEL_FINGERPRINT_MISMATCH")
    if not full_universe:
        raise ValueError("RELATIVE_POSITION_FULL_UNIVERSE_REQUIRED")
    if destination.is_symlink():
        raise PermissionError("PHASE4C_SYMLINK_DESTINATION_BLOCKED")
    resolved_sources = {
        paths.analysis_db.resolve(), paths.canonical_db.resolve(),
        paths.market_db.resolve(), paths.taxonomy_db.resolve(),
    }
    resolved_destination = destination.resolve()
    if len(resolved_sources) != 4:
        raise ValueError("RELATIVE_POSITION_SOURCE_PATHS_MUST_BE_DISTINCT")
    if resolved_destination in resolved_sources:
        raise PermissionError("PHASE4C_SOURCE_DATABASE_CANNOT_BE_DESTINATION")
    if resolved_destination in {path.resolve() for path in PRODUCTION_PATHS}:
        raise PermissionError("PHASE4C_PRODUCTION_DESTINATION_BLOCKED")
    if apply and destination.exists() and not destination.is_file():
        raise ValueError("PHASE4C_DESTINATION_MUST_BE_A_DATABASE_FILE")


def _changed_observations(
    observations: tuple[RelativeObservation, ...], *, sequence: int
) -> tuple[RelativeObservation, ...]:
    changed = list(observations)
    for index, observation in enumerate(changed):
        if observation.source_eligible and isinstance(observation.score, (int, float)):
            score = min(100.0, max(0.0, float(observation.score) + sequence * 0.000001))
            if score == float(observation.score):
                score = max(0.0, float(observation.score) - sequence * 0.000001)
            changed[index] = replace(
                observation,
                score=score,
                source_result_fingerprint=(
                    f"{observation.source_result_fingerprint}:PHASE4C_CHANGE_{sequence}"
                ),
            )
            return tuple(changed)
    raise RuntimeError("PHASE4C_CHANGED_SOURCE_SIMULATION_HAS_NO_ELIGIBLE_OBSERVATION")


def _apply_dict(report: ApplyReport) -> dict[str, Any]:
    return asdict(report)


def run_phase4c(
    paths: ReadOnlySourcePaths,
    *,
    destination: Path,
    as_of_date: str,
    model_fingerprint: str,
    full_universe: bool,
    apply: bool = False,
    create_online_backup: bool = False,
    verify_idempotency: bool = False,
    exercise_changed_source: bool = False,
    exercise_failures: bool = False,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> dict[str, Any]:
    validate_request(
        paths,
        destination=destination,
        model_fingerprint=model_fingerprint,
        full_universe=full_universe,
        apply=apply,
    )
    source = load_current_relative_source(
        paths, as_of_date=as_of_date, freshness_days=freshness_days
    )
    calculation_args = {
        "snapshot_date": as_of_date,
        "freshness_days": freshness_days,
        "classification_fingerprint": source.classification_fingerprint,
        "taxonomy_fingerprint": source.taxonomy_fingerprint,
    }
    snapshot = calculate_snapshot(source.observations, **calculation_args)
    report: dict[str, Any] = {
        "ok": True,
        "mode": "APPLY" if apply else "DRY_RUN",
        "model_fingerprint": model_fingerprint,
        "snapshot_date": as_of_date,
        "source_fingerprint": snapshot.source_fingerprint,
        "result_fingerprint": snapshot.result_fingerprint,
        "result_rows": len(snapshot.results),
        "coverage_rows": len(snapshot.coverage),
        "destination": str(destination.resolve()),
    }
    if not apply:
        report["destination_exists"] = destination.exists()
        return report
    source_paths = {
        "analysis": paths.analysis_db,
        "canonical": paths.canonical_db,
        "market": paths.market_db,
        "taxonomy": paths.taxonomy_db,
    }
    report["sources_before"] = {
        name: database_evidence(path) for name, path in source_paths.items()
    }
    if create_online_backup:
        sqlite_online_backup(paths.analysis_db, destination)
    if not destination.is_file():
        raise FileNotFoundError("PHASE4C_APPLY_DESTINATION_DOES_NOT_EXIST")

    report["destination_before"] = database_evidence(destination)
    conn = sqlite3.connect(destination)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    applied_at = f"{as_of_date}T23:59:59Z"
    started = time.monotonic()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at)
        conn.commit()
        first = apply_snapshot(conn, snapshot, applied_at_utc=applied_at)
        report["first_apply"] = _apply_dict(first)
        if verify_idempotency:
            report["second_apply"] = _apply_dict(apply_snapshot(
                conn, snapshot, applied_at_utc=applied_at
            ))
        if exercise_changed_source:
            changed = calculate_snapshot(
                _changed_observations(source.observations, sequence=1),
                **calculation_args,
            )
            report["changed_source_apply"] = _apply_dict(apply_snapshot(
                conn, changed, applied_at_utc=applied_at
            ))
        if exercise_failures:
            failures = {}
            for sequence, failure in enumerate(
                ("metadata", "results", "before_activation", "cleanup"), start=2
            ):
                candidate = calculate_snapshot(
                    _changed_observations(source.observations, sequence=sequence),
                    **calculation_args,
                )
                before_id = conn.execute(
                    "SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?",
                    (MODEL_FINGERPRINT,),
                ).fetchone()[0]
                try:
                    apply_snapshot(
                        conn,
                        candidate,
                        applied_at_utc=applied_at,
                        inject_failure_at=failure,
                    )
                except RuntimeError as exc:
                    after_id = conn.execute(
                        "SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?",
                        (MODEL_FINGERPRINT,),
                    ).fetchone()[0]
                    failures[failure] = {
                        "error": str(exc),
                        "previous_active_preserved": before_id == after_id,
                    }
                else:
                    raise RuntimeError(f"PHASE4C_FAILURE_INJECTION_DID_NOT_FAIL:{failure}")
            report["failure_injections"] = failures
        check = quick_check(conn, model_fingerprint=MODEL_FINGERPRINT)
        if not check["ok"]:
            raise RuntimeError(f"PHASE4C_QUICK_CHECK_FAILED:{check['details']}")
        report["quick_check"] = check
    finally:
        conn.close()
    report["apply_duration_seconds"] = time.monotonic() - started
    report["destination_after"] = database_evidence(destination)
    report["sources_after"] = {
        name: database_evidence(path) for name, path in source_paths.items()
    }
    report["sources_unchanged"] = {
        name: report["sources_before"][name] == report["sources_after"][name]
        for name in source_paths
    }
    return report
