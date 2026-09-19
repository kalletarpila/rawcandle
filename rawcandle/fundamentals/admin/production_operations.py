"""Operation-specific source contracts for the shared production transaction."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.admin import batch_add_tickers as add
from rawcandle.fundamentals.admin import sector_industry as sector
from rawcandle.fundamentals.admin import taxonomy_v2_sync as taxonomy
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import AdminBatchRequest, AdminOperationType, fingerprint, utc_now
from rawcandle.fundamentals.admin.production_transaction import ProductionOperation
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships


def _taxonomy(paths: BatchAddTickerPaths) -> dict[str, Any]:
    _, identity = load_active_dc_memberships(paths.taxonomy_db, paths.canonical_db)
    return identity


def _assert_preview_hash(preview: Mapping[str, Any], expected: str) -> None:
    content = {key: value for key, value in preview.items() if key != "preview_fingerprint"}
    if preview.get("preview_fingerprint") != expected or fingerprint(content) != expected:
        raise ValueError("ADMIN_PRODUCTION_PREVIEW_FINGERPRINT_MISMATCH")


def _add_validate(
    paths: BatchAddTickerPaths,
    payload: Mapping[str, Any],
    expected: str,
    *,
    exact_production_paths: bool = False,
) -> dict[str, Any]:
    preview = payload.get("phase13g2_preview") or {}
    _assert_preview_hash(preview, expected)
    add._assert_preview_not_stale(paths, payload)
    active_taxonomy = _taxonomy(paths)
    if preview.get("source_state", {}).get("active_taxonomy") != active_taxonomy:
        raise ValueError("ADMIN_ADD_TICKERS_PREVIEW_TAXONOMY_MISMATCH")
    plan = payload.get("generic_batch_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("ADMIN_ADD_TICKERS_PLAN_REQUIRED")
    request_payload = preview.get("request") or {}
    request = AdminBatchRequest(
        operation_type=AdminOperationType.ADD_TICKERS,
        requested_inputs=tuple(request_payload.get("requested_inputs") or ()),
        normalized_inputs=tuple(request_payload.get("normalized_inputs") or ()),
        rejected_inputs=tuple(request_payload.get("rejected_inputs") or ()),
        market=request_payload.get("market"), options=request_payload.get("options") or {},
    )
    if not request.normalized_inputs or request.rejected_inputs:
        raise ValueError("ADMIN_ADD_TICKERS_VALID_BATCH_REQUIRED")
    if exact_production_paths:
        add.validate_exact_production_paths(paths)
        rebuilt_plan = add.build_generic_batch_plan(
            paths,
            request,
            now=payload.get("created_at_utc"),
            network_allowed=bool(plan.get("network_allowed")),
        ).safe_dict(include_rows=True)
    else:
        _, raw = add.build_preview_from_copy(
            paths, request, now=payload.get("created_at_utc"),
            network_allowed=bool(plan.get("network_allowed")),
        )
        rebuilt_plan = raw["generic_batch_plan"]
    if rebuilt_plan["plan_fingerprint"] != plan.get("plan_fingerprint"):
        raise ValueError("ADMIN_ADD_TICKERS_STALE_PLAN_CONTENT_CHANGED")
    eligible = [item for item in plan.get("items", []) if item.get("status") == "ELIGIBLE"]
    return {"as_of_date": str(payload["created_at_utc"])[:10], "taxonomy_dependency": active_taxonomy, "plan": plan, "request": request.as_dict(), "no_change": not eligible}


def _add_validate_production(paths: BatchAddTickerPaths, payload: Mapping[str, Any], expected: str) -> dict[str, Any]:
    """Validate the saved plan only after the transaction selected exact production mode."""
    return _add_validate(paths, payload, expected, exact_production_paths=True)


def _add_mutate(paths: BatchAddTickerPaths, preview: Mapping[str, Any]) -> dict[str, Any]:
    plan = preview["plan"]
    items = [item for item in plan["items"] if item.get("status") == "ELIGIBLE"]
    if not items:
        return {"outcome": "NO_CHANGE"}
    if not add._provider_schema_ready(paths.provider_db):
        raise RuntimeError("ADMIN_ADD_TICKERS_PROVIDER_SCHEMA_REQUIRED")
    applied_at = utc_now()
    identities = add._apply_identities(paths, items, applied_at=applied_at)
    staged = add._stage_generic_provider_rows(paths, items, applied_at=applied_at)
    canonical = add.reconcile_canonical(paths.provider_db, paths.canonical_db, applied_at=applied_at)
    ttm = add.rebuild_ttm(paths.canonical_db, applied_at=applied_at)
    structural = add.structural_break.apply_contract(paths.canonical_db, events=add._events(), applied_at_utc=applied_at)
    with sqlite3.connect(paths.canonical_db) as conn:
        add._ensure_identity_tables(conn)
        conn.execute(
            "INSERT OR IGNORE INTO phase13g2_applied_plan(plan_fingerprint,operation,applied_at_utc) VALUES(?,?,?)",
            (plan["plan_fingerprint"], "GENERIC_BATCH_ADD_TICKERS", applied_at),
        )
        conn.commit()
    return {"outcome": "APPLIED", "tickers": [item["ticker"] for item in items], "identities": identities, "provider_staging": staged, "canonical": canonical, "ttm": ttm, "structural": structural}


def _sector_validate(paths: BatchAddTickerPaths, payload: Mapping[str, Any], expected: str) -> dict[str, Any]:
    preview = payload.get("sector_industry_preview") or {}
    _assert_preview_hash(preview, expected)
    sector._assert_preview_fresh(paths, payload)
    plan = payload.get("sector_industry_plan") or {}
    if preview.get("source_state") != plan.get("source_state"):
        raise ValueError("ADMIN_SECTOR_PREVIEW_PLAN_MISMATCH")
    active_taxonomy = _taxonomy(paths)
    if plan.get("source_state", {}).get("active_taxonomy") != active_taxonomy:
        raise ValueError("ADMIN_SECTOR_PREVIEW_TAXONOMY_MISMATCH")
    return {"as_of_date": preview["as_of_date"], "taxonomy_dependency": active_taxonomy, "no_change": not preview.get("proposed_changes"), "requested": preview.get("request")}


def _sector_mutate(paths: BatchAddTickerPaths, preview: Mapping[str, Any]) -> dict[str, Any]:
    return {"outcome": "NOT_REQUIRED", "ticker_meta": "READ_ONLY"}


def _taxonomy_validate(paths: BatchAddTickerPaths, payload: Mapping[str, Any], expected: str) -> dict[str, Any]:
    _assert_preview_hash(payload, expected)
    if payload.get("taxonomy_domain") != "dc_ecosystem" or payload.get("action") != "FULL_V2_REBUILD":
        raise ValueError("ADMIN_TAXONOMY_PREVIEW_INVALID")
    if taxonomy._state(paths) != payload.get("source_state"):
        raise ValueError("ADMIN_TAXONOMY_STALE_PREVIEW")
    return {"as_of_date": payload["as_of_date"], "taxonomy_dependency": payload["source_state"]["active_taxonomy"], "no_change": False}


def _taxonomy_mutate(paths: BatchAddTickerPaths, preview: Mapping[str, Any]) -> dict[str, Any]:
    return {"outcome": "NOT_REQUIRED", "taxonomy": "READ_ONLY_ACTIVE_ANALYSIS_DB"}


ADD_TICKERS = ProductionOperation(
    AdminOperationType.ADD_TICKERS,
    ("provider", "canonical", "analysis"),
    _add_validate,
    _add_mutate,
    production_validate_preview=_add_validate_production,
)
SECTOR_INDUSTRY = ProductionOperation(AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, ("analysis",), _sector_validate, _sector_mutate)
TAXONOMY = ProductionOperation(AdminOperationType.CHECK_UPDATE_TAXONOMY, ("analysis",), _taxonomy_validate, _taxonomy_mutate)
