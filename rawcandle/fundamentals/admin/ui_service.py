from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import re
from contextlib import contextmanager
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin import batch_add_tickers, refresh_copy_runtime, refresh_fundamentals, refresh_production, sector_industry, taxonomy_v2_sync
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, sha256_file
from rawcandle.fundamentals.admin.full_workflow import WORKFLOW_REPORT_NAME, run_full_workflow as orchestrate_full_workflow
from rawcandle.fundamentals.admin.history import AdminRunHistory, RunHistoryEntry, RunProgressSummary
from rawcandle.fundamentals.admin.operation_report import (
    OPERATION_REPORT_NAME,
    OperationReportSummary,
    resolve_operation_report_download,
    build_operation_summary,
    final_status_message,
    operation_stage,
    write_operation_report,
    taxonomy_preview_presentation,
)


AdminProgressCallback = Callable[[Mapping[str, Any]], None]


@dataclass(frozen=True)
class AdminOperationCapability:
    operation_type: str
    preview_enabled: bool
    copy_apply_enabled: bool
    production_apply_enabled: bool
    production_confirmation_hint: str | None = None


@dataclass(frozen=True)
class AdminUIRunResult:
    status: str
    message: str
    run_id: str | None = None
    outcome: str | None = None
    mode: str | None = None
    preview_fingerprint: str | None = None
    preview_payload_path: str | None = None
    artifact_dir: str | None = None
    report_filename: str | None = None
    report_sha256: str | None = None
    summary_rows: tuple[str, ...] = ()
    business_outcome: str | None = None
    preview_domain: str | None = None
    copy_actionable: bool | None = None
    production_actionable: bool | None = None
    duration_seconds: float | None = None
    failure_stage: str | None = None
    exception_type: str | None = None
    technical_error: str | None = None
    direct_production_retry_available: bool = False
    preview_test_rerun_required: bool = False
    workflow_stage_run_ids: tuple[str, ...] = ()
    test_run_id: str | None = None
    direct_test_retry_available: bool = False


@dataclass(frozen=True)
class AdminUIHistoryEntry:
    run_id: str
    operation_type: str
    outcome: str
    status: str
    mode: str
    completed_at_utc: str | None
    report_available: bool
    category: str = "Administration run"
    primary_count: int | None = None
    duration_seconds: float | None = None
    count_label: str | None = None
    report_filename: str = OPERATION_REPORT_NAME

    @property
    def stage(self) -> str:
        return operation_stage(self.mode)


_ADMIN_RUN_ID = re.compile(r"^\d{8}T\d{6}Z_(add_tickers|refresh_fundamentals|check_update_sector_industry|check_update_taxonomy)_[A-Za-z0-9_]+$")
_ADMIN_MODES = {
    "ADD_TICKERS": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL", "FULL_WORKFLOW"},
    "REFRESH_FUNDAMENTALS": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"},
    "CHECK_UPDATE_SECTOR_INDUSTRY": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_NO_CHANGE_APPLY", "READ_ONLY_AUDIT", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"},
    "CHECK_UPDATE_TAXONOMY": {"CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "COPY_ONLY_APPLY", "PROTECTED_PRODUCTION_PREVIEW", "PROTECTED_PRODUCTION_NO_CHANGE_VERIFY", "ACTIVE_TAXONOMY_PREVIEW", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"},
}


class FundamentalsAdminUIService:
    def __init__(
        self,
        *,
        run_root: Path = ADMIN_RUN_ROOT,
        history: AdminRunHistory | None = None,
        add_preview: Callable[..., dict[str, Any]] = batch_add_tickers.run_preview,
        add_apply: Callable[..., dict[str, Any]] = batch_add_tickers.run_apply,
        add_production_apply: Callable[..., dict[str, Any]] = batch_add_tickers.run_production_apply,
        refresh_preview: Callable[..., dict[str, Any]] = refresh_fundamentals.run_preview,
        refresh_apply: Callable[..., dict[str, Any]] = refresh_copy_runtime.run_apply,
        refresh_production_apply: Callable[..., dict[str, Any]] = refresh_production.run_production_apply,
        sector_preview: Callable[..., dict[str, Any]] = sector_industry.run_preview,
        sector_apply: Callable[..., dict[str, Any]] = sector_industry.run_apply,
        sector_production_apply: Callable[..., dict[str, Any]] = sector_industry.run_production_apply,
        taxonomy_preview: Callable[..., dict[str, Any]] = taxonomy_v2_sync.run_preview,
        taxonomy_apply: Callable[..., dict[str, Any]] = taxonomy_v2_sync.run_apply,
        taxonomy_production_preview: Callable[..., dict[str, Any]] = taxonomy_v2_sync.run_preview,
        taxonomy_production_apply: Callable[..., dict[str, Any]] = taxonomy_v2_sync.run_production_apply,
        operation_lock_path: Path | None = None,
    ) -> None:
        self.run_root = run_root.resolve()
        self.history = history or AdminRunHistory(self.run_root)
        self._add_preview = add_preview
        self._add_apply = add_apply
        self._add_production_apply = add_production_apply
        self._refresh_preview = refresh_preview
        self._refresh_apply = refresh_apply
        self._refresh_production_apply = refresh_production_apply
        self._sector_preview = sector_preview
        self._sector_apply = sector_apply
        self._sector_production_apply = sector_production_apply
        self._taxonomy_preview = taxonomy_preview
        self._taxonomy_apply = taxonomy_apply
        self._taxonomy_production_preview = taxonomy_production_preview
        self._taxonomy_production_apply = taxonomy_production_apply
        self.operation_lock_path = (
            operation_lock_path
            or (self.run_root.parent / ".fundamentals_admin_ui_operation.lock")
        ).resolve()
        self._publication_safety = {"status": "CLEAR", "production_writes_blocked": False}
        if self.run_root == ADMIN_RUN_ROOT.resolve():
            self._initialize_publication_safety()

    def _initialize_publication_safety(self) -> None:
        from rawcandle.fundamentals.admin.production_transaction import production_lock
        from rawcandle.fundamentals.admin.publication_journal import (
            PublicationRecoveryError,
            guard_production_writes,
            safety_status,
        )

        current = safety_status()
        if not current.get("production_writes_blocked") or current.get("status") == "RECOVERY_FAILED":
            self._publication_safety = current
            return
        try:
            with production_lock():
                guard_production_writes()
        except PublicationRecoveryError as exc:
            if "RECOVERED_RETRY_REQUIRED" not in str(exc):
                self._publication_safety = safety_status() | {"error": str(exc)}
                return
        except Exception as exc:
            self._publication_safety = current | {"error": f"{type(exc).__name__}: {exc}"}
            return
        self._publication_safety = safety_status()

    def publication_safety_status(self) -> Mapping[str, Any]:
        return dict(self._publication_safety)

    @contextmanager
    def _operation_lock(self):
        self.operation_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.operation_lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("ADMIN_OPERATION_ALREADY_RUNNING") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def capabilities(self) -> tuple[AdminOperationCapability, ...]:
        return (
            AdminOperationCapability("ADD_TICKERS", True, True, True),
            AdminOperationCapability(
                "REFRESH_FUNDAMENTALS", True, True, True,
                "CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS",
            ),
            AdminOperationCapability("CHECK_UPDATE_SECTOR_INDUSTRY", True, True, True),
            AdminOperationCapability(
                "CHECK_UPDATE_TAXONOMY",
                True,
                True,
                True,
            ),
        )

    def preview(
        self,
        operation_type: str,
        **kwargs: Any,
    ) -> AdminUIRunResult:
        with self._operation_lock():
            return self._preview_unlocked(operation_type, **kwargs)

    def _preview_unlocked(
        self,
        operation_type: str,
        *,
        raw_inputs: str = "",
        market: str = "usa",
        taxonomy_domain: str = "dc_ecosystem",
        candidate_path: str | None = None,
        candidate_version: str | None = None,
        production_mode: bool = False,
        network_allowed: bool = False,
        progress_callback: AdminProgressCallback | None = None,
    ) -> AdminUIRunResult:
        operation = operation_type.strip().upper()
        if operation == "ADD_TICKERS":
            result = self._add_preview(
                raw_inputs,
                run_root=self.run_root,
                market=market,
                network_allowed=network_allowed,
                progress_callback=progress_callback,
            )
        elif operation == "REFRESH_FUNDAMENTALS":
            result = self._refresh_preview(
                run_root=self.run_root,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            result = self._sector_preview(
                raw_inputs,
                run_root=self.run_root,
                market=market,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_TAXONOMY":
            result = self._taxonomy_preview(
                taxonomy_domain=taxonomy_domain,
                candidate_path=Path(candidate_path) if candidate_path else None,
                candidate_version=candidate_version,
                run_root=self.run_root,
                progress_callback=progress_callback,
            )
        else:
            raise ValueError("UNSUPPORTED_ADMIN_OPERATION")
        return self._finalize(result, default_message="Preview completed.")

    def copy_apply(
        self,
        operation_type: str,
        **kwargs: Any,
    ) -> AdminUIRunResult:
        with self._operation_lock():
            return self._copy_apply_unlocked(operation_type, **kwargs)

    def _copy_apply_unlocked(
        self,
        operation_type: str,
        *,
        preview_payload_path: str,
        preview_fingerprint: str,
        taxonomy_domain: str = "dc_ecosystem",
        progress_callback: AdminProgressCallback | None = None,
    ) -> AdminUIRunResult:
        operation = operation_type.strip().upper()
        payload_path = Path(preview_payload_path)
        if operation == "ADD_TICKERS":
            result = self._add_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_apply=True,
                progress_callback=progress_callback,
            )
        elif operation == "REFRESH_FUNDAMENTALS":
            result = self._refresh_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_apply=True,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            result = self._sector_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_apply=True,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_TAXONOMY":
            result = self._taxonomy_apply(
                taxonomy_domain=taxonomy_domain,
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_apply=True,
                progress_callback=progress_callback,
            )
        else:
            raise ValueError("UNSUPPORTED_ADMIN_OPERATION")
        return self._finalize(result, default_message="Copy-only apply completed.")

    def production_apply(
        self,
        operation_type: str,
        **kwargs: Any,
    ) -> AdminUIRunResult:
        with self._operation_lock():
            return self._production_apply_unlocked(operation_type, **kwargs)

    def _production_apply_unlocked(
        self,
        operation_type: str,
        *,
        preview_payload_path: str,
        preview_fingerprint: str,
        confirmation: str,
        test_run_id: str,
        progress_callback: AdminProgressCallback | None = None,
    ) -> AdminUIRunResult:
        operation = operation_type.strip().upper()
        payload_path = Path(preview_payload_path)
        if operation == "ADD_TICKERS":
            result = self._add_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_production=confirmation == "CONFIRM_PRODUCTION_BATCH_ADD_TICKERS",
                test_run_id=test_run_id,
                progress_callback=progress_callback,
            )
        elif operation == "REFRESH_FUNDAMENTALS":
            result = self._refresh_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_production=confirmation == "CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS",
                production_intent=True,
                test_run_id=test_run_id,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            result = self._sector_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_production=confirmation == "CONFIRM_PRODUCTION_SECTOR_INDUSTRY",
                test_run_id=test_run_id,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_TAXONOMY":
            result = self._taxonomy_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_production=confirmation == "CONFIRM_PRODUCTION_TAXONOMY",
                test_run_id=test_run_id,
                progress_callback=progress_callback,
            )
        else:
            raise ValueError("UNSUPPORTED_ADMIN_OPERATION")
        return self._finalize(result, default_message="Production apply completed.")

    def full_workflow(
        self,
        *,
        raw_inputs: str,
        market: str = "usa",
        progress_callback: AdminProgressCallback | None = None,
    ) -> AdminUIRunResult:
        with self._operation_lock():
            result = orchestrate_full_workflow(
                raw_inputs,
                market=market,
                run_root=self.run_root,
                preview_stage=lambda callback: self._preview_unlocked(
                    "ADD_TICKERS",
                    raw_inputs=raw_inputs,
                    market=market,
                    network_allowed=True,
                    progress_callback=callback,
                ),
                test_stage=lambda preview, callback: self._copy_apply_unlocked(
                    "ADD_TICKERS",
                    preview_payload_path=preview.preview_payload_path or "",
                    preview_fingerprint=preview.preview_fingerprint or "",
                    progress_callback=callback,
                ),
                production_stage=lambda preview, test, callback: self._production_apply_unlocked(
                    "ADD_TICKERS",
                    preview_payload_path=preview.preview_payload_path or "",
                    preview_fingerprint=preview.preview_fingerprint or "",
                    confirmation="CONFIRM_PRODUCTION_BATCH_ADD_TICKERS",
                    test_run_id=test.run_id or "",
                    progress_callback=callback,
                ),
                progress_callback=progress_callback,
            )
        return self._finalize(result, default_message="Full workflow completed.")

    def progress(self, run_id: str) -> RunProgressSummary:
        return self.history.progress(run_id)

    def history_entries(self, *, limit: int = 20, include_technical: bool = False) -> list[AdminUIHistoryEntry]:
        entries: list[AdminUIHistoryEntry] = []
        try:
            run_dirs = [
                path for path in self.run_root.iterdir()
                if path.is_dir() and not path.is_symlink()
            ] if self.run_root.exists() else []
        except Exception:
            return []
        for path in run_dirs:
            try:
                entry = self._history_entry_for_run_dir(path)
            except (OSError, ValueError, TypeError):
                continue
            if entry is None:
                continue
            entries.append(entry)
        def sort_key(entry: AdminUIHistoryEntry) -> tuple[datetime, str]:
            timestamp = entry.completed_at_utc
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                return (parsed.astimezone(timezone.utc), entry.run_id)
            except (TypeError, ValueError):
                return (datetime.min.replace(tzinfo=timezone.utc), entry.run_id)

        administration = sorted((item for item in entries if item.category == "Administration run"), key=sort_key, reverse=True)
        if not include_technical:
            return administration[:limit]
        technical = sorted((item for item in entries if item.category != "Administration run"), key=sort_key, reverse=True)
        return administration[:limit] + technical[:limit]

    def history_result_summary(self, run_id: str) -> tuple[str, ...]:
        result_path = self.history.artifact_path(run_id, "result.json")
        result = self._load_json_file(result_path)
        if result is None:
            raise ValueError("invalid admin result")
        return build_operation_summary(result)

    def resolve_report_download(self, run_id: str) -> Path:
        return resolve_operation_report_download(run_id, root=self.run_root)

    def resolve_named_report_download(self, run_id: str, filename: str) -> Path:
        return resolve_operation_report_download(run_id, filename, root=self.run_root)

    def _artifact_names(self, run_id: str) -> tuple[str, ...]:
        try:
            return self.history.progress(run_id).artifacts
        except Exception:
            return ()

    def _mode_for_entry(self, entry: RunHistoryEntry) -> str:
        try:
            path = self.history.artifact_path(entry.run_id, "result.json")

            result = json.loads(path.read_text(encoding="utf-8"))
            return str(result.get("mode", "UNKNOWN"))
        except Exception:
            return "UNKNOWN"

    def _history_entry_for_run_dir(self, run_dir: Path) -> AdminUIHistoryEntry | None:
        run_id = run_dir.name
        result = self._load_json_file(run_dir / "result.json")
        request = self._load_json_file(run_dir / "request.json")
        status = self._load_json_file(run_dir / "progress_status.json") or self._load_json_file(run_dir / "status.json")
        invalid_artifact = any(
            (run_dir / name).is_symlink() or ((run_dir / name).exists() and parsed is None)
            for name, parsed in (("result.json", result), ("request.json", request))
        )
        category = "Invalid or corrupt run" if invalid_artifact else self._classify_run_dir(run_dir, result=result, request=request, status=status)
        if category == "Invalid or corrupt run":
            return AdminUIHistoryEntry(
                run_id=run_id,
                operation_type="Invalid run",
                outcome="CORRUPT_OR_INCOMPLETE",
                status="corrupt_or_incomplete",
                mode="INVALID",
                completed_at_utc=None,
                report_available=OPERATION_REPORT_NAME in self._artifact_names(run_id),
                category="Invalid or corrupt run",
            )
        if category == "Administration run":
            try:
                item = self.history.summarize(run_id)
            except Exception:
                return AdminUIHistoryEntry(
                    run_id=run_id,
                    operation_type=str((result or request or status or {}).get("operation_type", "Administration")),
                    outcome="CORRUPT_OR_INCOMPLETE",
                    status="corrupt_or_incomplete",
                    mode=str((result or {}).get("mode", "UNKNOWN")),
                    completed_at_utc=None,
                    report_available=OPERATION_REPORT_NAME in self._artifact_names(run_id),
                    category="Invalid or corrupt run",
                    primary_count=self._primary_count(result or request or {}),
                )
            return AdminUIHistoryEntry(
                run_id=item.run_id,
                operation_type=item.operation_type,
                outcome=(taxonomy_preview_presentation(result or {}) or {}).get("business_outcome", item.outcome),
                status=item.status,
                mode=self._mode_for_entry(item),
                completed_at_utc=item.completed_at_utc,
                report_available=OPERATION_REPORT_NAME in self._artifact_names(item.run_id),
                category=category,
                primary_count=self._primary_count(result or request or {}),
                duration_seconds=self._duration_seconds(result or {}),
                count_label=self._count_label(result or request or {}),
                report_filename=WORKFLOW_REPORT_NAME if self._mode_for_entry(item) == "FULL_WORKFLOW" else OPERATION_REPORT_NAME,
            )
        payload = result or request or status or {}
        return AdminUIHistoryEntry(
            run_id=run_id,
            operation_type=str(payload.get("operation_type", category)),
            outcome=str(payload.get("outcome", category.upper().replace(" ", "_"))),
            status=category.lower().replace(" ", "_"),
            mode=str(payload.get("mode", "TECHNICAL")),
            completed_at_utc=payload.get("completed_at_utc") or payload.get("timestamp_utc"),
            report_available=OPERATION_REPORT_NAME in self._artifact_names(run_id),
            category=category,
            primary_count=self._primary_count(payload),
            duration_seconds=self._duration_seconds(payload),
        )

    def _classify_run_dir(
        self,
        run_dir: Path,
        *,
        result: Mapping[str, Any] | None,
        request: Mapping[str, Any] | None,
        status: Mapping[str, Any] | None,
    ) -> str:
        payload = result or request or status or {}
        operation = str(payload.get("operation_type", ""))
        options = (request or {}).get("options")
        mode = str(payload.get("mode") or (options.get("mode") if isinstance(options, Mapping) else "") or "")
        if _ADMIN_RUN_ID.fullmatch(run_dir.name) and mode in _ADMIN_MODES.get(operation, ()):
            return "Administration run"
        names = {path.name for path in run_dir.iterdir() if path.is_file() and not path.is_symlink()}
        if {
            "acceptance_summary.json",
            "phase13h1_1_status.json",
            "phase13h1_1_exit_code.txt",
        } & names or "acceptance" in run_dir.name.lower():
            return "Acceptance/test evidence"
        if "cleanup" in run_dir.name.lower() or "maintenance" in run_dir.name.lower():
            return "Maintenance/cleanup evidence"
        if names:
            return "Legacy evidence"
        return "Invalid or corrupt run"

    def _load_json_file(self, path: Path) -> Mapping[str, Any] | None:
        if path.is_symlink():
            return None
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            return parsed if isinstance(parsed, Mapping) else None
        except Exception:
            return None

    def _primary_count(self, payload: Mapping[str, Any]) -> int | None:
        taxonomy = taxonomy_preview_presentation(payload)
        if taxonomy and taxonomy.get("memberships") is not None:
            return int(taxonomy["memberships"])
        counts = payload.get("summary_counts")
        if isinstance(counts, Mapping):
            mode = str(payload.get("mode") or "")
            preferred = {
                "PREVIEW": ("eligible", "requested", "requested_count", "ELIGIBLE"),
                "COPY_ONLY_APPLY": ("applied", "accepted", "requested", "APPLIED"),
                "PRODUCTION_APPLY": ("applied", "accepted", "requested", "APPLIED"),
            }.get(mode, ())
            for key in (*preferred, "effective_changed_known", "requested", "requested_count", "accepted", "changed", "inspected", "eligible", "applied", "ELIGIBLE", "APPLIED"):
                if key in counts:
                    try:
                        return int(counts[key])
                    except Exception:
                        return None
        request = payload.get("request") or payload.get("requested_change")
        requested = request.get("requested_inputs") if isinstance(request, Mapping) else payload.get("requested_inputs")
        if isinstance(requested, (list, tuple)):
            return len(requested)
        return None

    def _count_label(self, payload: Mapping[str, Any]) -> str | None:
        taxonomy = taxonomy_preview_presentation(payload)
        if taxonomy and taxonomy.get("memberships") is not None:
            return f"{taxonomy['memberships']} memberships"
        count = self._primary_count(payload)
        if count is None:
            return None
        return f"{count} changed tickers" if payload.get("operation_type") == "REFRESH_FUNDAMENTALS" else f"{count} items"

    def _duration_seconds(self, payload: Mapping[str, Any]) -> float | None:
        started = payload.get("started_at_utc")
        completed = payload.get("completed_at_utc")
        if not started or not completed:
            return None
        try:
            from datetime import datetime

            start = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
            return max(0.0, (end - start).total_seconds())
        except Exception:
            return None

    def _finalize(self, result: Mapping[str, Any], *, default_message: str) -> AdminUIRunResult:
        run_id = str(result.get("run_id") or "")
        taxonomy = taxonomy_preview_presentation(result)
        report: OperationReportSummary | None = None
        workflow_mode = result.get("mode") == "FULL_WORKFLOW"
        if run_id and workflow_mode:
            report_path = self.run_root / run_id / WORKFLOW_REPORT_NAME
            if report_path.is_file() and not report_path.is_symlink():
                report = OperationReportSummary(
                    run_id=run_id,
                    operation_type=str(result.get("operation_type") or "ADD_TICKERS"),
                    outcome=str(result.get("outcome") or "RECORDED"),
                    mode="FULL_WORKFLOW",
                    summary_rows=(
                        f"Full workflow: {str(result.get('outcome') or 'RECORDED').replace('_', ' ').title()}.",
                        f"Current stage: {result.get('current_stage') or 'Not recorded'}.",
                        f"Production completed: {'Yes' if result.get('production_completed') else 'No'}.",
                    ),
                    report_path=str(report_path),
                    report_sha256=sha256_file(report_path),
                )
        elif run_id:
            report = write_operation_report(run_id, root=self.run_root)
        payload_path = (
            result.get("phase13d_preview_payload_path")
            or result.get("preview_payload_path")
            or result.get("payload_path")
            or ((result.get("preview") or {}).get("payload") if isinstance(result.get("preview"), Mapping) else None)
        )
        errors = result.get("errors")
        first_error = errors[0] if isinstance(errors, (list, tuple)) and errors and isinstance(errors[0], Mapping) else {}
        return AdminUIRunResult(
            status="FAILED" if result.get("outcome") in {"FAILED", "STOPPED", "ERROR", "INTERRUPTED", "ROLLED_BACK", "FAILED_ROLLED_BACK", "CRITICAL_ROLLBACK_FAILED"} else "COMPLETED",
            message=final_status_message(result) if result.get("mode") else default_message,
            run_id=run_id or None,
            outcome=str(result.get("outcome")) if result.get("outcome") is not None else None,
            mode=str(result.get("mode")) if result.get("mode") is not None else None,
            preview_fingerprint=str(result.get("preview_fingerprint")) if result.get("preview_fingerprint") else None,
            preview_payload_path=str(payload_path) if payload_path else None,
            artifact_dir=str(result.get("artifact_dir")) if result.get("artifact_dir") else None,
            report_filename=(WORKFLOW_REPORT_NAME if workflow_mode else OPERATION_REPORT_NAME) if report else None,
            report_sha256=report.report_sha256 if report else None,
            summary_rows=report.summary_rows if report else (),
            business_outcome=taxonomy["business_outcome"] if taxonomy else None,
            preview_domain=taxonomy["domain"] if taxonomy else None,
            copy_actionable=True if result.get("mode") == "ACTIVE_TAXONOMY_PREVIEW" else (bool(taxonomy["changes"] and taxonomy["eligible"] and not taxonomy["blockers"] and taxonomy["candidate"] and result.get("mode") == "CANDIDATE_PREVIEW" and taxonomy["business_outcome"] == "CHANGES_AVAILABLE") if taxonomy else None),
            production_actionable=result.get("mode") == "ACTIVE_TAXONOMY_PREVIEW" if result.get("operation_type") == "CHECK_UPDATE_TAXONOMY" else None,
            duration_seconds=self._duration_seconds(result),
            failure_stage=str(result.get("failed_stage")) if result.get("failed_stage") else None,
            exception_type=str(first_error.get("type")) if first_error.get("type") else None,
            technical_error=str(first_error.get("message")) if first_error.get("message") else None,
            direct_production_retry_available=bool((result.get("retry_authorization") or {}).get("direct_production_retry_available") or result.get("manual_production_retry_available") or result.get("manual_production_available")),
            preview_test_rerun_required=bool((result.get("retry_authorization") or {}).get("preview_test_rerun_required")),
            workflow_stage_run_ids=tuple(
                str(stage.get("run_id"))
                for stage in (result.get("stages") or [])
                if isinstance(stage, Mapping) and stage.get("run_id")
            ),
            test_run_id=str(result.get("test_run_id")) if result.get("test_run_id") else None,
            direct_test_retry_available=bool(result.get("manual_test_retry_available")),
        )
