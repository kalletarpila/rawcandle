from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminPreview,
    AdminStatus,
    RunStage,
    build_batch_request,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.phase12d import PRODUCTION, database_inventory, write_json
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals.phase13d_backend import (
    Phase13DPaths,
    apply_ticker_preview,
    build_ticker_preview,
    reject_production_or_alias,
)


PHASE = "PHASE13G2_BATCH_ADD_TICKERS"
CONTRACT_VERSION = "PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V1"
OUTCOME_B = "OUTCOME B — BATCH ADD TICKERS COPY-ONLY FOUNDATION READY; AUTHORITATIVE FULL DOWNSTREAM GAP REMAINS"
WRITE_ROLES = ("provider", "canonical", "analysis")
READONLY_COPY_ROLES = ("market", "taxonomy")
ROLE_ORDER = ("provider", "canonical", "analysis", "market", "taxonomy")


@dataclass(frozen=True)
class BatchAddTickerPaths:
    provider_db: Path = PRODUCTION["provider"]
    canonical_db: Path = PRODUCTION["canonical"]
    analysis_db: Path = PRODUCTION["analysis"]
    market_db: Path = PRODUCTION["market"]
    taxonomy_db: Path = PRODUCTION["taxonomy"]

    def as_dict(self) -> dict[str, Path]:
        return {
            "provider": self.provider_db,
            "canonical": self.canonical_db,
            "analysis": self.analysis_db,
            "market": self.market_db,
            "taxonomy": self.taxonomy_db,
        }

    def as_phase13d(self) -> Phase13DPaths:
        return Phase13DPaths(
            provider_db=self.provider_db,
            canonical_db=self.canonical_db,
            analysis_db=self.analysis_db,
            market_db=self.market_db,
            taxonomy_db=self.taxonomy_db,
        )


@dataclass(frozen=True)
class CopyLane:
    lane_dir: Path
    paths: BatchAddTickerPaths
    manifest: Mapping[str, Any]


def parse_batch_tickers(raw: str | Sequence[str], *, market: str | None = "usa") -> AdminBatchRequest:
    return build_batch_request(AdminOperationType.ADD_TICKERS, raw, market=market, options={"contract_version": CONTRACT_VERSION})


def reject_production_write_targets(paths: BatchAddTickerPaths) -> None:
    reject_production_or_alias(paths.as_phase13d())


def source_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "databases": {role: database_inventory(path) for role, path in paths.as_dict().items()},
    }


def create_copy_lane(
    paths: BatchAddTickerPaths,
    *,
    lane_dir: Path,
    writer: AdminRunWriter | None = None,
) -> CopyLane:
    lane_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    copied: dict[str, Path] = {}
    for role in ROLE_ORDER:
        source = paths.as_dict()[role]
        destination = lane_dir / f"{role}.db"
        manifest[role] = online_backup(source, destination)
        copied[role] = destination
        if writer is not None:
            writer.append_heartbeat({"stage": "COPY_DATABASE", "role": role, "destination": str(destination)})
    copy_paths = BatchAddTickerPaths(
        provider_db=copied["provider"],
        canonical_db=copied["canonical"],
        analysis_db=copied["analysis"],
        market_db=copied["market"],
        taxonomy_db=copied["taxonomy"],
    )
    reject_production_write_targets(copy_paths)
    return CopyLane(lane_dir=lane_dir, paths=copy_paths, manifest=manifest)


def cleanup_copy_lane(lane: CopyLane) -> dict[str, Any]:
    removed: list[str] = []
    for path in sorted(lane.lane_dir.glob("**/*"), reverse=True):
        if path.is_file() and (
            path.suffix in {".db", ".sqlite", ".sqlite3"}
            or path.name.endswith(("-wal", "-shm", "-journal"))
        ):
            removed.append(str(path))
            path.unlink(missing_ok=True)
    for path in sorted(lane.lane_dir.glob("**/*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        lane.lane_dir.rmdir()
    except OSError:
        pass
    return {"removed_files": removed, "removed_count": len(removed)}


def _status_from_phase13d(row: Mapping[str, Any]) -> AdminStatus:
    status = str(row.get("status") or "")
    ready = bool(row.get("ready_for_apply"))
    if ready:
        return AdminStatus.ELIGIBLE
    if status == "ALREADY_PRESENT":
        return AdminStatus.ALREADY_PRESENT
    if status in {"IDENTITY_AMBIGUOUS", "API_FETCH_REQUIRED", "READY_WITH_LIMITATIONS"}:
        return AdminStatus.REVIEW_REQUIRED
    return AdminStatus.REJECTED


def _reason(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "UNKNOWN")
    eligibility = row.get("eligibility") if isinstance(row.get("eligibility"), Mapping) else {}
    primary = eligibility.get("primary_rejection_reason")
    if primary:
        return f"{status}: {primary}"
    if status == "READY_WITH_LIMITATIONS":
        return "Eligible for copy apply, but taxonomy connectivity is limited."
    if status == "READY_LOCAL_PROVIDER":
        return "Eligible from local provider and market evidence."
    if status == "ALREADY_PRESENT":
        return "Ticker is already present in canonical identities."
    return status.replace("_", " ").title()


def _decision_from_row(row: Mapping[str, Any]) -> AdminItemDecision:
    provider = row.get("provider") if isinstance(row.get("provider"), Mapping) else {}
    identity = provider.get("identity") if isinstance(provider.get("identity"), Mapping) else {}
    market = row.get("market") if isinstance(row.get("market"), Mapping) else {}
    markets = market.get("markets") if isinstance(market.get("markets"), list) else []
    return AdminItemDecision(
        item_key=str(row.get("ticker")),
        requested_value=str(row.get("ticker")),
        normalized_value=str(row.get("ticker")),
        status=_status_from_phase13d(row),
        reason=_reason(row),
        market=str(markets[0]) if len(markets) == 1 else None,
        company_name=identity.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if row.get("ready_for_apply") else None,
        source_category=str(provider.get("source") or provider.get("status") or "local"),
        warnings=tuple(row.get("eligibility", {}).get("rejection_reasons", []) if isinstance(row.get("eligibility"), Mapping) else ()),
        blockers=tuple(row.get("eligibility", {}).get("rejection_reasons", []) if isinstance(row.get("eligibility"), Mapping) else ()),
        applied_action="PENDING_COPY_APPLY" if row.get("ready_for_apply") else None,
        details={
            "phase13d_status": row.get("status"),
            "provider": provider,
            "market": market,
            "canonical": row.get("canonical"),
            "taxonomy": row.get("taxonomy"),
            "estimated_impact": row.get("estimated_impact"),
        },
    )


def build_preview_from_copy(
    paths: BatchAddTickerPaths,
    request: AdminBatchRequest,
    *,
    now: str | None = None,
) -> tuple[AdminPreview, dict[str, Any]]:
    raw_preview = build_ticker_preview(paths.as_phase13d(), request.normalized_inputs, now=now)
    rejected_decisions = tuple(
        AdminItemDecision(
            item_key=str(item["requested_value"]),
            requested_value=str(item["requested_value"]),
            normalized_value=str(item["requested_value"]).upper(),
            status=AdminStatus.REJECTED,
            reason=str(item["reason"]),
            source_category="input_parser",
            blockers=(str(item["reason"]),),
        )
        for item in request.rejected_inputs
    )
    decisions = tuple(_decision_from_row(row) for row in raw_preview["ticker_results"]) + rejected_decisions
    proposed = tuple(
        {
            "ticker": row["ticker"],
            "action": "ADD_TICKER",
            "status": row["status"],
            "ready_for_apply": row["ready_for_apply"],
        }
        for row in raw_preview["ticker_results"]
        if row.get("ready_for_apply")
    )
    preview = AdminPreview(
        operation_type=AdminOperationType.ADD_TICKERS,
        request=request,
        decisions=decisions,
        source_state=raw_preview["source_state"],
        proposed_changes=proposed,
        warnings=tuple("Network access not used; local evidence only."),
    )
    preview_dict = preview.as_dict()
    raw_preview["phase13g2_preview_fingerprint"] = preview_dict["preview_fingerprint"]
    raw_preview["phase13g2_request_fingerprint"] = preview_dict["request_fingerprint"]
    raw_preview["phase13g2_change_set_fingerprint"] = preview_dict["change_set_fingerprint"]
    return preview, raw_preview


def _write_preview_payload(path: Path, raw_preview: Mapping[str, Any], phase13g2_preview: Mapping[str, Any]) -> None:
    payload = dict(raw_preview)
    payload["phase13g2_preview"] = dict(phase13g2_preview)
    write_json(path, payload)


def _load_preview_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_preview_not_stale(paths: BatchAddTickerPaths, payload: Mapping[str, Any]) -> None:
    phase_preview = payload.get("phase13g2_preview") if isinstance(payload.get("phase13g2_preview"), Mapping) else {}
    request = phase_preview.get("request") if isinstance(phase_preview.get("request"), Mapping) else {}
    tickers = request.get("normalized_inputs") or []
    fresh = build_ticker_preview(paths.as_phase13d(), tickers, now=payload.get("created_at_utc"))
    if fresh.get("source_state") != payload.get("source_state"):
        raise ValueError("PHASE13G2_STALE_PREVIEW_SOURCE_STATE_CHANGED")


def run_preview(
    raw_inputs: str | Sequence[str],
    *,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    network_allowed: bool = False,
    market: str | None = "usa",
) -> dict[str, Any]:
    request = parse_batch_tickers(raw_inputs, market=market)
    run_id = stable_run_id(AdminOperationType.ADD_TICKERS, fingerprint(request))
    writer = AdminRunWriter(run_id, AdminOperationType.ADD_TICKERS, root=run_root)
    started = utc_now()
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Batch Add Tickers preview request recorded.")
    writer.write_json("request.json", request.as_dict() | {"network_allowed": network_allowed})
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Creating copy lane for read-only production-shaped preview.")
    lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "preview_lane", writer=writer)
    try:
        preview, raw_preview = build_preview_from_copy(lane.paths, request)
        preview_dict = preview.as_dict()
        preview_path = writer.write_json("preview.json", preview_dict)
        phase13d_preview_path = writer.run_dir / "phase13d_preview_payload.json"
        _write_preview_payload(phase13d_preview_path, raw_preview, preview_dict)
        writer.write_items_csv([item.as_dict() for item in preview.decisions])
        writer.checkpoint(
            RunStage.PREVIEW_READY,
            message="Batch preview ready. Production was not modified.",
            preview_fingerprint=preview_dict["preview_fingerprint"],
            counters=_counts(preview.decisions),
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.COMPLETED,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_dict["preview_fingerprint"],
            request=request.as_dict(),
            item_results=preview.decisions,
            summary_counts=_counts(preview.decisions),
            downstream={
                "package": "NOT_RUN_IN_PREVIEW",
                "relative_position": "NOT_RUN_IN_PREVIEW",
                "relative_valuation": "NOT_RUN_IN_PREVIEW",
                "network": "ALLOWED" if network_allowed else "DISABLED",
            },
            artifacts={"preview": str(preview_path), "phase13d_preview_payload": str(phase13d_preview_path)},
            recommended_next_action="Review the preview. Copy-only apply requires --apply, --confirm-apply and the preview fingerprint.",
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(RunStage.COMPLETED, message="Preview run completed.", preview_fingerprint=preview_dict["preview_fingerprint"])
        writer.write_exit_code(0)
        writer.write_manifest()
        return result_dict | {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "phase13d_preview_payload_path": str(phase13d_preview_path),
            "cleanup": cleanup_copy_lane(lane),
        }
    except Exception as exc:
        writer.write_error(exc)
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message="Preview failed before any write boundary.")
        writer.write_exit_code(2)
        writer.write_manifest()
        cleanup_copy_lane(lane)
        raise


def run_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    confirm_apply: bool = False,
    failure_boundary: str | None = None,
    keep_copies: bool = False,
) -> dict[str, Any]:
    if not confirm_apply:
        raise PermissionError("PHASE13G2_APPLY_REQUIRES_CONFIRMATION")
    payload = _load_preview_payload(preview_payload_path)
    phase_preview = payload.get("phase13g2_preview") if isinstance(payload.get("phase13g2_preview"), Mapping) else {}
    if phase_preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13G2_PREVIEW_FINGERPRINT_MISMATCH")
    request_payload = phase_preview.get("request") if isinstance(phase_preview.get("request"), Mapping) else {}
    request = AdminBatchRequest(
        operation_type=AdminOperationType.ADD_TICKERS,
        requested_inputs=tuple(request_payload.get("requested_inputs") or ()),
        normalized_inputs=tuple(request_payload.get("normalized_inputs") or ()),
        rejected_inputs=tuple(request_payload.get("rejected_inputs") or ()),
        market=request_payload.get("market"),
        options=request_payload.get("options") or {},
    )
    run_id = stable_run_id(AdminOperationType.ADD_TICKERS, preview_fingerprint, suffix="apply")
    writer = AdminRunWriter(run_id, AdminOperationType.ADD_TICKERS, root=run_root)
    started = utc_now()
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Copy-only apply request recorded.", preview_fingerprint=preview_fingerprint)
    writer.write_json("request.json", request.as_dict())
    writer.write_json("preview.json", phase_preview)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Creating copy lane for copy-only apply.", preview_fingerprint=preview_fingerprint)
    lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "apply_lane", writer=writer)
    rollback: dict[str, Any] = {}
    write_boundary_crossed = False
    try:
        _assert_preview_not_stale(lane.paths, payload)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Preview is fresh on apply copy.", preview_fingerprint=preview_fingerprint)
        copy_preview, raw_preview = build_preview_from_copy(lane.paths, request, now=payload.get("created_at_utc"))
        copy_preview_path = lane.lane_dir / "accepted_preview.json"
        write_json(copy_preview_path, raw_preview)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Applying accepted tickers to database copies.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
        write_boundary_crossed = True
        before = {role: database_inventory(path) for role, path in lane.paths.as_dict().items()}
        applied = apply_ticker_preview(
            lane.paths.as_phase13d(),
            preview_path=copy_preview_path,
            preview_fingerprint=raw_preview["preview_fingerprint"],
            apply=True,
            confirm_apply=True,
            output=lane.lane_dir / "phase13d_apply",
            failure_boundary=failure_boundary,
        )
        after = {role: database_inventory(path) for role, path in lane.paths.as_dict().items()}
        repeated = apply_ticker_preview(
            lane.paths.as_phase13d(),
            preview_path=copy_preview_path,
            preview_fingerprint=raw_preview["preview_fingerprint"],
            apply=True,
            confirm_apply=True,
            output=lane.lane_dir / "phase13d_repeat",
        )
        decisions = _apply_decisions(copy_preview.decisions, applied)
        counts = _counts(decisions)
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.PARTIALLY_COMPLETED if any(item.status in {AdminStatus.REJECTED, AdminStatus.REVIEW_REQUIRED} for item in decisions) else AdminStatus.COMPLETED,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=decisions,
            summary_counts=counts,
            rollback={"status": "NOT_REQUIRED"},
            downstream={
                "phase13d_candidate_apply": "RUN_ONCE_FOR_BATCH",
                "package": "GAP_NOT_AUTHORITATIVELY_REFRESHED_BY_PHASE13D_ADAPTER",
                "relative_position": "GAP_NOT_AUTHORITATIVELY_REFRESHED_BY_PHASE13D_ADAPTER",
                "relative_valuation": applied.get("relative_valuation_state"),
                "repeat_apply_outcome": repeated.get("outcome"),
            },
            artifacts={"phase13d_apply": str(lane.lane_dir / "phase13d_apply")},
            recommended_next_action="Treat this as copy-only backend evidence. Authoritative full downstream refresh integration remains for a later production-deployment-ready phase.",
        )
        result_dict = result.as_dict()
        result_dict["copy_apply"] = {
            "phase13d_result": applied,
            "repeat_result": repeated,
            "before_inventory": before,
            "after_inventory": after,
            "copy_lane": str(lane.lane_dir),
        }
        writer.write_final_result(result)
        writer.write_json("copy_apply_technical.json", result_dict["copy_apply"])
        writer.write_items_csv([item.as_dict() for item in decisions])
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(RunStage.PARTIALLY_COMPLETED if result.outcome == AdminStatus.PARTIALLY_COMPLETED else RunStage.COMPLETED, message="Copy-only apply completed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True, counters=counts)
        writer.write_exit_code(1 if result.outcome == AdminStatus.PARTIALLY_COMPLETED else 0)
        writer.write_manifest()
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup}
    except Exception as exc:
        writer.write_error(exc)
        if write_boundary_crossed:
            writer.checkpoint(RunStage.ROLLBACK_STARTED, message="Copy apply failed; restoring copy lane from fresh source backups.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            rollback = _restore_copy_lane_from_sources(source_paths, lane)
            writer.checkpoint(RunStage.ROLLBACK_COMPLETE, message="Copy lane restored after failure.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            terminal_stage = RunStage.FAILED_AFTER_WRITE
            outcome = AdminStatus.ROLLED_BACK
        else:
            rollback = {"status": "NOT_REQUIRED", "message": "Failure occurred before the copy write boundary."}
            terminal_stage = RunStage.FAILED_BEFORE_WRITE
            outcome = AdminStatus.FAILED
        error_decisions = tuple(
            AdminItemDecision(
                item_key=value,
                requested_value=value,
                normalized_value=value,
                status=AdminStatus.FAILED,
                reason=f"Copy apply failed and was rolled back: {type(exc).__name__}",
            )
            for value in request.normalized_inputs
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=outcome,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=error_decisions,
            summary_counts=_counts(error_decisions),
            rollback=rollback,
            recommended_next_action="Inspect error.json and retry only after resolving the failure.",
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(terminal_stage, message="Copy-only apply failed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(3 if write_boundary_crossed else 2)
        writer.write_manifest()
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup, "error": type(exc).__name__}


def _restore_copy_lane_from_sources(source_paths: BatchAddTickerPaths, lane: CopyLane) -> dict[str, Any]:
    restored: dict[str, Any] = {"status": "ROLLED_BACK", "roles": {}}
    for role in ROLE_ORDER:
        destination = lane.paths.as_dict()[role]
        source = source_paths.as_dict()[role]
        online_backup(source, destination)
        restored["roles"][role] = database_inventory(destination)
    return restored


def _apply_decisions(decisions: Sequence[AdminItemDecision], applied: Mapping[str, Any]) -> tuple[AdminItemDecision, ...]:
    applied_tickers = {str(ticker).upper() for ticker in applied.get("applied_tickers") or ()}
    outcome = str(applied.get("outcome") or "")
    output: list[AdminItemDecision] = []
    for item in decisions:
        if item.status == AdminStatus.ELIGIBLE and item.normalized_value in applied_tickers and outcome == "APPLIED":
            output.append(
                AdminItemDecision(
                    **{**item.__dict__, "status": AdminStatus.APPLIED, "reason": "Applied on copy lane.", "applied_action": "COPY_ONBOARD_APPLIED"}
                )
            )
        elif item.status == AdminStatus.ELIGIBLE and outcome == "NO_CHANGE":
            output.append(
                AdminItemDecision(
                    **{**item.__dict__, "status": AdminStatus.NO_CHANGE, "reason": "No copy-lane change was required.", "applied_action": "NO_CHANGE"}
                )
            )
        else:
            output.append(item)
    return tuple(output)


def _counts(decisions: Sequence[AdminItemDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in decisions:
        key = item.status.value.lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def disk_hygiene_snapshot(path: Path = Path(".")) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {"path": str(path.resolve()), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
