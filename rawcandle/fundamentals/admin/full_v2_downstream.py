"""Single copy-lane downstream path for Fundamentals Administration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping

from rawcandle.datacenter_taxonomy_operation_log import taxonomy_lock_held_in_process
from rawcandle.fundamentals.operating_income_v2.full_rebuild import rebuild_v2_analysis
from rawcandle.fundamentals.phase12d import PRODUCTION


def run_full_v2_downstream(
    paths: Mapping[str, Path], *, output: Path, as_of_date: str,
    inject_failure_at: str | None = None,
) -> dict[str, Any]:
    """Rebuild V2 and RV from copied authorities; never replace an active DB."""
    date.fromisoformat(as_of_date)
    sources = {role: Path(paths[role]) for role in ("provider", "canonical", "market", "taxonomy")}
    protected_sources = {path.resolve() for path in PRODUCTION.values()}
    for role, path in sources.items():
        direct_locked_taxonomy = (
            role == "taxonomy"
            and path.resolve() == PRODUCTION["taxonomy"].resolve()
            and taxonomy_lock_held_in_process()
        )
        if path.resolve() in protected_sources and not direct_locked_taxonomy:
            raise PermissionError(f"ADMIN_FULL_V2_COPY_SOURCE_REQUIRED:{role}")
    output = Path(output)
    if output.is_symlink() or output.resolve().is_relative_to(PRODUCTION["analysis"].parent.resolve()):
        raise PermissionError("ADMIN_FULL_V2_OUTPUT_MUST_BE_DISPOSABLE")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "analysis_candidate.db"
    result = rebuild_v2_analysis(
        target, sources, as_of_date=as_of_date,
        output=output / "full_v2_rebuild", inject_failure_at=inject_failure_at,
    )
    if result["status"] != "READY":
        raise RuntimeError("ADMIN_FULL_V2_REBUILD_NOT_READY")
    return {
        "action": "FULL_V2_REBUILD",
        "as_of_date": as_of_date,
        "status": result["status"],
        "candidate_analysis_db": str(target),
        "package": result["package"],
        "relative_position": result["validation"]["rp_snapshot_id"],
        "relative_valuation": result["rv"],
        "validation": result["validation"],
        "fingerprints": result["fingerprints"],
        "active_taxonomy": result["taxonomy_dependency"],
        "invocation_counts": {"full_v2_rebuild": 1, "package": 1, "relative_position": 1, "relative_valuation": 1},
    }
