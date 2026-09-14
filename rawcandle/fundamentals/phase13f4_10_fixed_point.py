from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    ROOT,
    compare_production_inventory,
    database_inventory,
    rebuild_ttm,
    reconcile_canonical,
    stable_hash,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    online_backup,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13f3_1_package_recovery import instrumented_package_refresh
from rawcandle.fundamentals.phase13f3_2_successor_recovery import (
    _apply_provider_identity_links,
    archive_reconciliation,
    stage_provider_rows,
    successor_canonical_ttm_report,
)
from rawcandle.fundamentals.phase13f3_3_structural_break_contract import (
    _events,
    _structural_evidence,
    _structural_package_fingerprint,
)
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    APPLIED_AT,
    REPORT_DATE,
    _apply_transition_identities,
    _areb_counts,
    _manual_rv_refresh,
    _snapshot_smoke,
    _valuation_classification_update,
)
from rawcandle.fundamentals.phase13f4_2_production import (
    ACCEPTED,
    _acceptance_blockers,
    _acceptance_view,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position


PHASE = "PHASE13F4_10_IDENTITY_DEPENDENCY_FIXED_POINT_REPAIR"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13f4_10_fixed_point"
DEFAULT_RUN_ID = "20260914T_PHASE13F4_10_FIXED_POINT"
OUTCOME_A = "OUTCOME A — IDENTITY AND DEPENDENCY FIXED POINT VERIFIED; READY FOR SEPARATELY AUTHORIZED PHASE 13F.4.11 PRODUCTION DEPLOYMENT"
OUTCOME_B = "OUTCOME B — ROOT CAUSE IDENTIFIED BUT FIXED POINT NOT YET ACHIEVED; PRODUCTION NOT AUTHORIZED"
OUTCOME_C = "OUTCOME C — PROTECTED LOGICAL DRIFT REMAINS UNEXPLAINED; PRODUCTION NOT AUTHORIZED"
OUTCOME_D = "OUTCOME D — PRODUCTION IMMUTABILITY OR COPY INTEGRITY NOT PROVEN"

WRITE_ROLES = ("provider", "canonical", "analysis")
WATCH_TABLES = {
    "canonical": (
        "company_cik",
        "provider_company_identity",
        "provider_security_identity",
        structural_break.EVENT_TABLE,
    ),
    "analysis": (
        "fundamentals_result_dependency",
        "relative_position_refresh_audit",
    ),
}
SNAPSHOT_TICKERS = ("VMRK", "IA", "VAI", "NXH", "NMAD", "AREB", "NVDA", "SNDK")


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(f"PRAGMA table_info({_quote(table)})")]


def _table_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    columns = _table_columns(conn, table)
    primary = [
        str(row["name"])
        for row in sorted(columns, key=lambda item: int(item["pk"]))
        if int(row["pk"]) > 0
    ]
    return primary or [str(row["name"]) for row in columns]


def _stable_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"blob_hex": value.hex()}
    if isinstance(value, float):
        return {"binary64_hex": value.hex()}
    return value


def _table_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    columns = [str(row["name"]) for row in _table_columns(conn, table)]
    order = _table_key_columns(conn, table)
    select = ",".join(_quote(column) for column in columns)
    order_by = ",".join(_quote(column) for column in order)
    return [
        {column: _stable_value(row[column]) for column in columns}
        for row in conn.execute(f"SELECT {select} FROM {_quote(table)} ORDER BY {order_by}")
    ]


def protected_table_snapshot(paths: CandidatePaths) -> dict[str, Any]:
    by_role = {"canonical": paths.canonical_db, "analysis": paths.analysis_db}
    snapshot: dict[str, Any] = {}
    for role, tables in WATCH_TABLES.items():
        with _readonly(by_role[role]) as conn:
            snapshot[role] = {}
            for table in tables:
                if not _table_exists(conn, table):
                    snapshot[role][table] = {
                        "exists": False,
                        "row_count": 0,
                        "fingerprint": None,
                        "rows": [],
                        "key_columns": [],
                    }
                    continue
                rows = _table_rows(conn, table)
                snapshot[role][table] = {
                    "exists": True,
                    "row_count": len(rows),
                    "fingerprint": stable_hash(rows),
                    "rows": rows,
                    "key_columns": _table_key_columns(conn, table),
                }
    return snapshot


def _row_key(row: Mapping[str, Any], columns: Sequence[str]) -> str:
    return stable_hash({column: row.get(column) for column in columns})


def diff_protected_tables(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for role in sorted(set(before) | set(after)):
        tables = set((before.get(role) or {})) | set((after.get(role) or {}))
        for table in sorted(tables):
            left = (before.get(role) or {}).get(table, {})
            right = (after.get(role) or {}).get(table, {})
            if left.get("fingerprint") == right.get("fingerprint") and left.get("row_count") == right.get("row_count"):
                continue
            key_columns = list(right.get("key_columns") or left.get("key_columns") or [])
            left_by_key = {_row_key(row, key_columns): row for row in left.get("rows", [])}
            right_by_key = {_row_key(row, key_columns): row for row in right.get("rows", [])}
            inserted = [right_by_key[key] for key in sorted(set(right_by_key) - set(left_by_key))]
            deleted = [left_by_key[key] for key in sorted(set(left_by_key) - set(right_by_key))]
            updated = []
            for key in sorted(set(left_by_key) & set(right_by_key)):
                old = left_by_key[key]
                new = right_by_key[key]
                changed = {
                    column: {"before": old.get(column), "after": new.get(column)}
                    for column in sorted(set(old) | set(new))
                    if old.get(column) != new.get(column)
                }
                if changed:
                    updated.append({"key": {column: new.get(column) for column in key_columns}, "changed_columns": changed})
            diffs.append({
                "role": role,
                "table": table,
                "key_columns": key_columns,
                "before_row_count": left.get("row_count"),
                "after_row_count": right.get("row_count"),
                "before_fingerprint": left.get("fingerprint"),
                "after_fingerprint": right.get("fingerprint"),
                "inserted_count": len(inserted),
                "updated_count": len(updated),
                "deleted_count": len(deleted),
                "inserted_rows": inserted[:20],
                "updated_rows": updated[:20],
                "deleted_rows": deleted[:20],
            })
    return diffs


def _copy_inventory(paths: CandidatePaths) -> dict[str, Any]:
    return {
        "databases": {
            "provider": database_inventory(paths.provider_db),
            "canonical": database_inventory(paths.canonical_db),
            "analysis": database_inventory(paths.analysis_db),
        },
        "reports": {},
        "scheduler": {"exists": False, "sha256": None, "size": None, "mtime_ns": None},
    }


def _stage_marker(paths: CandidatePaths, stage: str) -> dict[str, Any]:
    snapshot = protected_table_snapshot(paths)
    return {
        "stage": stage,
        "fingerprint": stable_hash({
            role: {
                table: {
                    "row_count": item["row_count"],
                    "fingerprint": item["fingerprint"],
                }
                for table, item in tables.items()
            }
            for role, tables in snapshot.items()
        }),
        "tables": {
            role: {
                table: {
                    "row_count": item["row_count"],
                    "fingerprint": item["fingerprint"],
                }
                for table, item in tables.items()
            }
            for role, tables in snapshot.items()
        },
        "snapshot": snapshot,
    }


def _write_diff_csv(path: Path, diffs: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "role",
                "table",
                "before_row_count",
                "after_row_count",
                "inserted_count",
                "updated_count",
                "deleted_count",
                "before_fingerprint",
                "after_fingerprint",
            ],
        )
        writer.writeheader()
        for row in diffs:
            writer.writerow({field: row.get(field) for field in writer.fieldnames})


def run_cycle(paths: CandidatePaths, output: Path, *, source: Mapping[str, Any], cycle: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"cycle": cycle, "applied_at_utc": APPLIED_AT, "stage_markers": []}
    result["stage_markers"].append(_stage_marker(paths, "start"))
    result["transition_identities"] = _apply_transition_identities(paths.canonical_db)
    result["stage_markers"].append(_stage_marker(paths, "after_transition_identities"))
    result["provider_staging"] = stage_provider_rows(paths.provider_db, paths.canonical_db, source["rows_by_ticker"])
    result["stage_markers"].append(_stage_marker(paths, "after_provider_staging"))
    result["provider_identity_links"] = _apply_provider_identity_links(paths.canonical_db, provider_db=paths.provider_db)
    result["stage_markers"].append(_stage_marker(paths, "after_provider_identity_links"))
    result["provider_identity_links_replay"] = _apply_provider_identity_links(paths.canonical_db, provider_db=paths.provider_db)
    result["transition_identities_replay"] = _apply_transition_identities(paths.canonical_db)
    result["stage_markers"].append(_stage_marker(paths, "after_identity_replays"))
    result["provider_staging_replay"] = stage_provider_rows(paths.provider_db, paths.canonical_db, source["rows_by_ticker"])
    result["canonical"] = reconcile_canonical(paths.provider_db, paths.canonical_db, applied_at=APPLIED_AT)
    result["ttm"] = rebuild_ttm(paths.canonical_db, applied_at=APPLIED_AT)
    result["successor_canonical_ttm"] = successor_canonical_ttm_report(paths.canonical_db)
    result["structural_contract"] = structural_break.apply_contract(paths.canonical_db, events=_events(), applied_at_utc=APPLIED_AT)
    result["structural_evidence"] = _structural_evidence(paths.canonical_db)
    structural_package_fingerprint = _structural_package_fingerprint(result["structural_contract"])
    result["structural_package_fingerprint"] = structural_package_fingerprint
    result["stage_markers"].append(_stage_marker(paths, "after_structural_contract"))
    result["valuation_classification"] = _valuation_classification_update(paths.analysis_db, paths.market_db, paths.canonical_db)
    result["schema"] = ensure_candidate_schema(paths, applied_at_utc=APPLIED_AT, apply=True)
    universe = backfill_universe(paths, applied_at_utc=APPLIED_AT, apply=True)
    result["universe"] = universe
    result["package"] = instrumented_package_refresh(
        {
            "provider": paths.provider_db,
            "canonical": paths.canonical_db,
            "analysis": paths.analysis_db,
            "market": paths.market_db,
            "taxonomy": paths.taxonomy_db,
        },
        output,
    )
    result["stage_markers"].append(_stage_marker(paths, "after_package"))
    result["relative_position"] = asdict(refresh_relative_position(
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        market_db=paths.market_db,
        taxonomy_db=paths.taxonomy_db,
        snapshot_date=REPORT_DATE,
        model_fingerprint=RP_MODEL_FINGERPRINT,
        applied_at_utc=APPLIED_AT,
    ))
    result["stage_markers"].append(_stage_marker(paths, "after_relative_position"))
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    result["pre_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["relative_valuation"] = _manual_rv_refresh(paths, output=output)
    result["stage_markers"].append(_stage_marker(paths, "after_relative_valuation"))
    structural_metadata = {
        "structural_contract_version": structural_break.CONTRACT_VERSION,
        "structural_package_fingerprint": structural_package_fingerprint,
        "structural_event_fingerprint": result["structural_contract"]["economic_event_fingerprint"],
        "structural_regime_fingerprint": result["structural_contract"]["regime_fingerprint"],
        "structural_event_count": result["structural_contract"]["event_count"],
        "structural_quarter_regime_count": result["structural_contract"]["quarter_regime_count"],
        "structural_ttm_regime_count": result["structural_contract"]["ttm_regime_count"],
    }
    result["dependencies"] = attach_dependencies(
        paths,
        universe=universe["identity"],
        applied_at_utc=APPLIED_AT,
        apply=True,
        structural_metadata=structural_metadata,
    )
    result["dependencies_replay"] = attach_dependencies(
        paths,
        universe=universe["identity"],
        applied_at_utc=APPLIED_AT,
        apply=True,
        structural_metadata=structural_metadata,
    )
    result["stage_markers"].append(_stage_marker(paths, "after_dependencies"))
    result["post_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["snapshots"] = _snapshot_smoke(paths, output)
    result["areb"] = _areb_counts(paths.analysis_db)
    result["acceptance_view"] = _acceptance_view(result)
    result["acceptance_blockers"] = _acceptance_blockers(result)
    result["final_inventory"] = _copy_inventory(paths)
    write_json(output / "cycle_result.json", result)
    return result


def _copy_lane(output: Path, lane: str) -> CandidatePaths:
    copies = output / lane / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    provider = copies / PRODUCTION["provider"].name
    canonical = copies / PRODUCTION["canonical"].name
    analysis = copies / PRODUCTION["analysis"].name
    online_backup(PRODUCTION["provider"], provider)
    online_backup(PRODUCTION["canonical"], canonical)
    online_backup(PRODUCTION["analysis"], analysis)
    return CandidatePaths(
        canonical,
        analysis,
        PRODUCTION["taxonomy"],
        provider_db=provider,
        market_db=PRODUCTION["market"],
    )


def _lane_summary(lane_dir: Path, paths: CandidatePaths, cycles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "lane_dir": str(lane_dir),
        "cycles": [
            {
                "cycle": cycle["cycle"],
                "provider_staging_changes": cycle["provider_staging"]["logical_changes"],
                "provider_staging_replay_changes": cycle["provider_staging_replay"]["logical_changes"],
                "transition_identity_outcome": cycle["transition_identities"]["outcome"],
                "transition_identity_replay_outcome": cycle["transition_identities_replay"]["outcome"],
                "provider_identity_writes": cycle["provider_identity_links"]["writes"],
                "provider_identity_replay_writes": cycle["provider_identity_links_replay"]["writes"],
                "package_outcome": cycle["package"]["first_apply"]["outcome"],
                "package_logical_changes": cycle["package"]["first_apply"]["logical_changes"],
                "package_second_outcome": cycle["package"]["second_apply"]["outcome"],
                "relative_position_outcome": cycle["relative_position"]["apply"]["outcome"],
                "relative_position_audit_rows_inserted": cycle["relative_position"]["apply"]["audit_rows_inserted"],
                "relative_valuation_outcome": cycle["relative_valuation"]["first_apply"]["outcome"],
                "relative_valuation_second_outcome": cycle["relative_valuation"]["second_apply"]["outcome"],
                "dependencies_outcome": cycle["dependencies"]["outcome"],
                "dependencies_replay_outcome": cycle["dependencies_replay"]["outcome"],
                "acceptance_blockers": cycle["acceptance_blockers"],
            }
            for cycle in cycles
        ],
        "final_integrity": _copy_inventory(paths),
    }


def run_lane(output: Path, lane: str, *, source: Mapping[str, Any], cycle_names: Sequence[str]) -> dict[str, Any]:
    lane_dir = output / lane
    paths = _copy_lane(output, lane)
    result: dict[str, Any] = {"lane": lane, "paths": {
        "provider": str(paths.provider_db),
        "canonical": str(paths.canonical_db),
        "analysis": str(paths.analysis_db),
        "market": str(paths.market_db),
        "taxonomy": str(paths.taxonomy_db),
    }}
    try:
        result["initial_inventory"] = _copy_inventory(paths)
        cycles = []
        cycle_start_snapshots: dict[str, Any] = {}
        cycle_end_snapshots: dict[str, Any] = {}
        cycle_start_inventories: dict[str, Any] = {}
        cycle_end_inventories: dict[str, Any] = {}
        for cycle_name in cycle_names:
            cycle_start_snapshots[cycle_name] = protected_table_snapshot(paths)
            cycle_start_inventories[cycle_name] = _copy_inventory(paths)
            cycle = run_cycle(paths, lane_dir / cycle_name, source=source, cycle=cycle_name)
            cycles.append(cycle)
            cycle_end_snapshots[cycle_name] = protected_table_snapshot(paths)
            cycle_end_inventories[cycle_name] = _copy_inventory(paths)
            diffs = diff_protected_tables(cycle_start_snapshots[cycle_name], cycle_end_snapshots[cycle_name])
            write_json(lane_dir / f"{cycle_name}_protected_table_diffs.json", diffs)
            _write_diff_csv(lane_dir / f"{cycle_name}_protected_table_diffs.csv", diffs)
        result["cycles"] = cycles
        result["cycle_inventory_comparisons"] = {
            name: compare_production_inventory(cycle_start_inventories[name], cycle_end_inventories[name])
            for name in cycle_names
        }
        if len(cycle_names) >= 2:
            previous = cycle_names[-2]
            last = cycle_names[-1]
            result["last_cycle_start_to_end_diffs"] = diff_protected_tables(
                cycle_start_snapshots[last],
                cycle_end_snapshots[last],
            )
            result["previous_end_to_last_end_compare"] = compare_production_inventory(
                cycle_end_inventories[previous],
                cycle_end_inventories[last],
            )
        result["summary"] = _lane_summary(lane_dir, paths, cycles)
        write_json(lane_dir / "lane_result.json", result)
        return result
    finally:
        if paths.provider_db.parent.exists():
            shutil.rmtree(paths.provider_db.parent)
        write_json(lane_dir / "cleanup.json", {
            "transient_copies_removed": not paths.provider_db.parent.exists(),
            "remaining_database_artifacts": [
                str(path) for path in lane_dir.rglob("*")
                if path.suffix in {".db", ".sqlite"} or path.name.endswith(("-wal", "-shm", "-journal"))
            ],
        })


def _active_identity() -> dict[str, Any]:
    with _readonly(PRODUCTION["analysis"]) as conn:
        active = dict(conn.execute("SELECT * FROM fundamentals_active_model_family WHERE singleton=1").fetchone())
        rv = [dict(row) for row in conn.execute("SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint")]
    return {"active_package": active, "active_relative_valuation": rv}


def _production_state() -> dict[str, Any]:
    return {
        "inventory": {
            role: database_inventory(path)
            for role, path in PRODUCTION.items()
        },
        "active_identity": _active_identity(),
    }


def _accepted_by_dimension(source: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rows in (source.get("rows_by_ticker") or {}).values():
        for row in rows:
            dimension = str(row.get("dimension") or "")
            counts[dimension] = counts.get(dimension, 0) + 1
    return dict(sorted(counts.items()))


def run_phase13f4_10(output: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    output.mkdir(parents=True, exist_ok=True)
    pre_production = _production_state()
    source = archive_reconciliation()
    result: dict[str, Any] = {
        "phase": PHASE,
        "artifact_dir": str(output),
        "accepted": ACCEPTED,
        "production_before": pre_production,
        "source_reconciliation": {
            "fingerprint": source["fingerprint"],
            "accepted_by_dimension": _accepted_by_dimension(source),
            "archive_sha256_verified": source["archive_sha256_verified"],
        },
    }
    try:
        primary = run_lane(output, "primary", source=source, cycle_names=("cycle_a", "cycle_b", "cycle_c"))
        replay = run_lane(output, "replay", source=source, cycle_names=("cycle_a", "cycle_b"))
        result["primary"] = primary
        result["replay"] = replay
        primary_fixed = (
            primary["cycle_inventory_comparisons"]["cycle_b"]["identical"]
            and primary["cycle_inventory_comparisons"]["cycle_c"]["identical"]
            and primary["previous_end_to_last_end_compare"]["identical"]
            and not primary.get("last_cycle_start_to_end_diffs")
        )
        replay_fixed = replay["cycle_inventory_comparisons"]["cycle_b"]["identical"]
        result["fixed_point_gates"] = {
            "primary_cycle_b_no_change": primary["cycle_inventory_comparisons"]["cycle_b"]["identical"],
            "primary_cycle_c_no_change": primary["cycle_inventory_comparisons"]["cycle_c"]["identical"],
            "primary_b_c_end_state_identical": primary["previous_end_to_last_end_compare"]["identical"],
            "replay_cycle_b_no_change": replay["cycle_inventory_comparisons"]["cycle_b"]["identical"],
            "primary_cycle_c_protected_diffs": primary.get("last_cycle_start_to_end_diffs", []),
        }
        result["outcome"] = OUTCOME_A if primary_fixed and replay_fixed else OUTCOME_B
    except Exception as exc:
        result["outcome"] = OUTCOME_C
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    post_production = _production_state()
    result["production_after"] = post_production
    result["production_immutability"] = compare_production_inventory(
        {
            "databases": pre_production["inventory"],
            "reports": {},
            "scheduler": {"exists": False, "sha256": None, "size": None, "mtime_ns": None},
            "active_package": pre_production["active_identity"]["active_package"],
            "active_relative_valuation": pre_production["active_identity"]["active_relative_valuation"],
        },
        {
            "databases": post_production["inventory"],
            "reports": {},
            "scheduler": {"exists": False, "sha256": None, "size": None, "mtime_ns": None},
            "active_package": post_production["active_identity"]["active_package"],
            "active_relative_valuation": post_production["active_identity"]["active_relative_valuation"],
        },
    )
    if not result["production_immutability"]["identical"]:
        result["outcome"] = OUTCOME_D
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    write_json(output / "phase13f4_10_result.json", result)
    return result
