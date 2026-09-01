from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    PeerScope,
    RelativeMeasure,
    RelativeSnapshot,
    RelativeStatus,
    calculate_snapshot,
)
from rawcandle.fundamentals.relative_position.persistence import (
    PERSISTENCE_SCHEMA_VERSION,
    RelativePositionRepository,
    apply_snapshot,
    ensure_schema,
    quick_check,
    validate_snapshot,
)
from rawcandle.fundamentals.relative_position.source import (
    ReadOnlySourcePaths,
    load_current_relative_source,
)


PRODUCTION_PATHS = {
    "canonical": Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    "provider": Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
    "analysis": Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"),
    "market": Path("/home/kalle/projects/rawcandle/data/osakedata.db"),
    "taxonomy": Path("/home/kalle/projects/rawcandle/data/analysis.db"),
}


@dataclass(frozen=True)
class RelativePositionRefreshReport:
    model_version: str
    model_fingerprint: str
    persistence_version: str
    snapshot_date: str
    source_fingerprint: str
    result_fingerprint: str
    result_rows: int
    coverage_rows: int
    apply: dict[str, Any]
    quick_check: dict[str, Any]


def validate_production_request(
    *,
    canonical_db: Path,
    provider_db: Path,
    analysis_db: Path,
    market_db: Path,
    taxonomy_db: Path,
    model_fingerprint: str,
    full_universe: bool,
    apply: bool,
    confirm_production: bool,
) -> dict[str, str]:
    supplied = {
        "canonical": canonical_db,
        "provider": provider_db,
        "analysis": analysis_db,
        "market": market_db,
        "taxonomy": taxonomy_db,
    }
    resolved: dict[str, str] = {}
    for name, path in supplied.items():
        expected = PRODUCTION_PATHS[name]
        if (
            not path.is_absolute()
            or path != expected
            or path.is_symlink()
            or path.resolve() != expected
            or not path.is_file()
        ):
            raise PermissionError(f"EXACT_RELATIVE_POSITION_PRODUCTION_PATH_REQUIRED:{name}:{expected}")
        resolved[name] = str(path.resolve())
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("RELATIVE_POSITION_PRODUCTION_PATHS_MUST_BE_DISTINCT")
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("RELATIVE_POSITION_MODEL_FINGERPRINT_MISMATCH")
    if not full_universe:
        raise ValueError("RELATIVE_POSITION_PRODUCTION_REQUIRES_FULL_UNIVERSE")
    if confirm_production and not apply:
        raise ValueError("RELATIVE_POSITION_CONFIRM_PRODUCTION_REQUIRES_APPLY")
    if apply and not confirm_production:
        raise PermissionError("RELATIVE_POSITION_APPLY_REQUIRES_CONFIRM_PRODUCTION")
    return resolved


def calculate_current_snapshot(
    *,
    canonical_db: Path,
    analysis_db: Path,
    market_db: Path,
    taxonomy_db: Path,
    snapshot_date: str,
) -> RelativeSnapshot:
    source = load_current_relative_source(
        ReadOnlySourcePaths(
            analysis_db=analysis_db,
            canonical_db=canonical_db,
            market_db=market_db,
            taxonomy_db=taxonomy_db,
        ),
        as_of_date=snapshot_date,
        freshness_days=180,
    )
    snapshot = calculate_snapshot(
        source.observations,
        snapshot_date=snapshot_date,
        freshness_days=180,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    validate_required_upstream(snapshot)
    return snapshot


def validate_required_upstream(snapshot: RelativeSnapshot) -> None:
    validate_snapshot(snapshot)
    measures = {result.measure for result in snapshot.results}
    if measures != set(RelativeMeasure):
        raise RuntimeError("RELATIVE_POSITION_REQUIRED_UPSTREAM_RESULTS_MISSING")


def snapshot_summary(snapshot: RelativeSnapshot) -> dict[str, Any]:
    ready: dict[str, int] = {}
    for measure in RelativeMeasure:
        for scope in PeerScope:
            ready[f"{measure.value}:{scope.value}"] = sum(
                result.measure == measure
                and result.peer_scope == scope
                and result.status == RelativeStatus.READY
                for result in snapshot.results
            )
    eligible = {
        measure.value: sum(
            result.measure == measure and result.peer_scope == PeerScope.UNIVERSE
            for result in snapshot.results
        )
        for measure in RelativeMeasure
    }
    return {
        "result_rows": len(snapshot.results),
        "coverage_rows": len(snapshot.coverage),
        "eligible": eligible,
        "ready": ready,
    }


def refresh_relative_position(
    *,
    canonical_db: Path,
    analysis_db: Path,
    market_db: Path,
    taxonomy_db: Path,
    snapshot_date: str,
    model_fingerprint: str,
    applied_at_utc: str,
    expected_source_fingerprint: str | None = None,
    expected_result_fingerprint: str | None = None,
) -> RelativePositionRefreshReport:
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("RELATIVE_POSITION_MODEL_FINGERPRINT_MISMATCH")
    snapshot = calculate_current_snapshot(
        canonical_db=canonical_db,
        analysis_db=analysis_db,
        market_db=market_db,
        taxonomy_db=taxonomy_db,
        snapshot_date=snapshot_date,
    )
    if (
        expected_source_fingerprint is not None
        and snapshot.source_fingerprint != expected_source_fingerprint
    ):
        raise RuntimeError("RELATIVE_POSITION_SOURCE_CHANGED_AFTER_PREFLIGHT")
    if (
        expected_result_fingerprint is not None
        and snapshot.result_fingerprint != expected_result_fingerprint
    ):
        raise RuntimeError("RELATIVE_POSITION_RESULT_CHANGED_AFTER_PREFLIGHT")
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at_utc)
        conn.commit()
        write = apply_snapshot(conn, snapshot, applied_at_utc=applied_at_utc)
        check = quick_check(
            conn,
            model_fingerprint=MODEL_FINGERPRINT,
            expected_snapshot=snapshot,
        )
        if not check["ok"]:
            raise RuntimeError(f"RELATIVE_POSITION_PRODUCTION_QUICK_CHECK_FAILED:{check['details']}")
    finally:
        conn.close()
    return RelativePositionRefreshReport(
        model_version=MODEL_VERSION,
        model_fingerprint=MODEL_FINGERPRINT,
        persistence_version=PERSISTENCE_SCHEMA_VERSION,
        snapshot_date=snapshot.snapshot_date,
        source_fingerprint=snapshot.source_fingerprint,
        result_fingerprint=snapshot.result_fingerprint,
        result_rows=len(snapshot.results),
        coverage_rows=len(snapshot.coverage),
        apply=asdict(write),
        quick_check=check,
    )


def reader_smoke(analysis_db: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        repository = RelativePositionRepository(conn)
        crmd = [
            row for row in repository.current_company(
                566, model_fingerprint=MODEL_FINGERPRINT
            )
            if row["measure"] == RelativeMeasure.ABSOLUTE_VALUATION_SCORE.value
        ]
        zero = repository.current_universe(
            model_fingerprint=MODEL_FINGERPRINT,
            measure=RelativeMeasure.ABSOLUTE_VALUATION_SCORE.value,
            peer_scope=PeerScope.UNIVERSE.value,
        )
        return {
            "active_metadata": repository.active_metadata(model_fingerprint=MODEL_FINGERPRINT),
            "crmd": crmd,
            "valuation_zero_tie": {
                "companies": sum(row["source_score"] == 0.0 for row in zero),
                "percentiles": sorted({row["percentile"] for row in zero if row["source_score"] == 0.0}),
            },
            "valuation_100_tie": {
                "companies": sum(row["source_score"] == 100.0 for row in zero),
                "percentiles": sorted({row["percentile"] for row in zero if row["source_score"] == 100.0}),
            },
            "wrong_fingerprint_rows": len(repository.current_company(
                566, model_fingerprint="WRONG_FINGERPRINT"
            )),
            "quick_check": quick_check(conn, model_fingerprint=MODEL_FINGERPRINT),
        }
    finally:
        conn.close()
