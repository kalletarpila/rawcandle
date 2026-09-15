from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from rawcandle.fundamentals.admin.artifacts import AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminPreview,
    AdminStatus,
    RunStage,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.reporting import render_markdown_report


class PreviewHandler(Protocol):
    def __call__(self, request: AdminBatchRequest) -> AdminPreview: ...


class ApplyHandler(Protocol):
    def __call__(self, preview: AdminPreview, writer: AdminRunWriter) -> AdminFinalResult: ...


RollbackHandler = Callable[[BaseException, AdminRunWriter], dict[str, object]]


@dataclass(frozen=True)
class OrchestrationResult:
    run_id: str
    artifact_dir: str
    result: dict[str, object]


class AdminOrchestrator:
    def __init__(self, *, writer_factory: Callable[[str, object], AdminRunWriter] | None = None) -> None:
        self.writer_factory = writer_factory

    def run_preview(self, request: AdminBatchRequest, preview_handler: PreviewHandler) -> OrchestrationResult:
        request_fp = fingerprint(request)
        run_id = stable_run_id(request.operation_type, request_fp)
        writer = self.writer_factory(run_id, request.operation_type) if self.writer_factory else AdminRunWriter(run_id, request.operation_type)
        writer.checkpoint(RunStage.REQUEST_CREATED, message="Request recorded.")
        writer.write_json("request.json", request.as_dict())
        writer.checkpoint(RunStage.PREVIEW_STARTED, message="Preview calculation started.")
        preview = preview_handler(request)
        preview_dict = preview.as_dict()
        writer.write_json("preview.json", preview_dict)
        writer.write_items_csv([item.as_dict() for item in preview.decisions])
        writer.checkpoint(
            RunStage.PREVIEW_READY,
            message="Preview is ready for review.",
            preview_fingerprint=preview_dict["preview_fingerprint"],
            counters={"items": len(preview.decisions)},
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=request.operation_type,
            outcome=AdminStatus.COMPLETED,
            mode="PREVIEW",
            started_at_utc=utc_now(),
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_dict["preview_fingerprint"],
            request=request.as_dict(),
            item_results=preview.decisions,
            summary_counts=_summary_counts(preview.decisions),
            recommended_next_action="Review the preview. Apply requires a later explicit confirmation.",
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(RunStage.COMPLETED, message="Preview run completed.", preview_fingerprint=preview_dict["preview_fingerprint"])
        writer.write_exit_code(0)
        writer.write_manifest()
        return OrchestrationResult(run_id=run_id, artifact_dir=str(writer.run_dir), result=result_dict)

    def run_apply(
        self,
        preview: AdminPreview,
        *,
        confirmed_preview_fingerprint: str,
        apply_handler: ApplyHandler,
        rollback_handler: RollbackHandler | None = None,
    ) -> OrchestrationResult:
        preview_dict = preview.as_dict()
        if preview_dict["preview_fingerprint"] != confirmed_preview_fingerprint:
            raise ValueError("ADMIN_PREVIEW_FINGERPRINT_MISMATCH")
        run_id = stable_run_id(preview.operation_type, confirmed_preview_fingerprint)
        writer = self.writer_factory(run_id, preview.operation_type) if self.writer_factory else AdminRunWriter(run_id, preview.operation_type)
        writer.checkpoint(RunStage.REQUEST_CREATED, message="Apply request recorded.", preview_fingerprint=confirmed_preview_fingerprint)
        writer.write_json("preview.json", preview_dict)
        writer.checkpoint(RunStage.APPLY_STARTED, message="Apply started.", preview_fingerprint=confirmed_preview_fingerprint)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Pre-write validation running.", preview_fingerprint=confirmed_preview_fingerprint)
        try:
            result = apply_handler(preview, writer)
            result_dict = result.as_dict()
            writer.write_final_result(result)
            writer.write_text("report.md", render_markdown_report(result_dict))
            writer.checkpoint(
                RunStage.COMPLETED if result.outcome == AdminStatus.COMPLETED else RunStage.PARTIALLY_COMPLETED,
                message="Apply run completed.",
                preview_fingerprint=confirmed_preview_fingerprint,
                write_boundary_crossed=True,
            )
            writer.write_exit_code(0 if result.outcome == AdminStatus.COMPLETED else 1)
        except Exception as exc:
            writer.write_error(exc)
            rollback = {}
            if rollback_handler:
                writer.checkpoint(
                    RunStage.ROLLBACK_STARTED,
                    message="Rollback started after apply failure.",
                    preview_fingerprint=confirmed_preview_fingerprint,
                    write_boundary_crossed=True,
                )
                rollback = rollback_handler(exc, writer)
                if rollback.get("status") == "ROLLED_BACK":
                    writer.checkpoint(
                        RunStage.ROLLBACK_COMPLETE,
                        message="Rollback completed.",
                        preview_fingerprint=confirmed_preview_fingerprint,
                        write_boundary_crossed=True,
                    )
            outcome = AdminStatus.ROLLED_BACK if rollback.get("status") == "ROLLED_BACK" else AdminStatus.FAILED
            result = AdminFinalResult(
                run_id=run_id,
                operation_type=preview.operation_type,
                outcome=outcome,
                mode="APPLY",
                started_at_utc=utc_now(),
                completed_at_utc=utc_now(),
                preview_fingerprint=confirmed_preview_fingerprint,
                request=preview.request.as_dict(),
                item_results=preview.decisions,
                summary_counts=_summary_counts(preview.decisions),
                rollback=rollback,
                recommended_next_action="Review the error evidence before retrying.",
                errors=({"type": type(exc).__name__, "message": str(exc)},),
            )
            result_dict = result.as_dict()
            writer.write_final_result(result)
            writer.write_text("report.md", render_markdown_report(result_dict))
            writer.checkpoint(
                RunStage.FAILED_AFTER_WRITE if rollback else RunStage.FAILED_BEFORE_WRITE,
                message="Apply failed.",
                preview_fingerprint=confirmed_preview_fingerprint,
                write_boundary_crossed=bool(rollback),
            )
            writer.write_exit_code(3 if rollback else 2)
        writer.write_manifest()
        return OrchestrationResult(run_id=run_id, artifact_dir=str(writer.run_dir), result=result_dict)


def _summary_counts(decisions) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in decisions:
        counts[item.status.value.lower()] = counts.get(item.status.value.lower(), 0) + 1
    return counts
