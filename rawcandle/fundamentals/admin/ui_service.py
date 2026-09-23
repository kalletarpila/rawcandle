from __future__ import annotations

from dataclasses import dataclass
import fcntl
from importlib import import_module
import json
from pathlib import Path
import re
from contextlib import contextmanager
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, sha256_file
from rawcandle.fundamentals.admin.history import AdminRunHistory, RunProgressSummary
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
WORKFLOW_REPORT_NAME = "workflow_report.md"
CIK_CONFIRMATION_TOKEN = "CONFIRM_PRODUCTION_PROVIDER_CIK_SYNC"


def _admin_callable(module_name: str, function_name: str) -> Callable[..., dict[str, Any]]:
    def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
        module = import_module(f"rawcandle.fundamentals.admin.{module_name}")
        return getattr(module, function_name)(*args, **kwargs)

    return call


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
    trigger_source: str = "MANUAL"

    @property
    def stage(self) -> str:
        return operation_stage(self.mode)


@dataclass(frozen=True)
class _RunHistoryProjection:
    run_dir: Path
    result: Mapping[str, Any] | None
    request: Mapping[str, Any] | None
    status: Mapping[str, Any] | None
    invalid_artifact: bool


def _run_id_timestamp(run_id: str) -> str | None:
    match = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z(?:_|$)", run_id)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    return f"{year}-{month}-{day}T{hour}:{minute}:{second}Z"


class AdminHistoryCursor:
    """Session-local newest-first history scan with one projection per run."""

    def __init__(self, service: "FundamentalsAdminUIService", *, include_technical: bool) -> None:
        self.service = service
        self.include_technical = include_technical
        hidden = service.history.hidden_run_ids()
        try:
            self.candidates = sorted(
                (
                    path for path in service.run_root.iterdir()
                    if path.is_dir() and not path.is_symlink() and path.name not in hidden
                ),
                key=self._candidate_order_key,
                reverse=True,
            ) if service.run_root.exists() else []
        except OSError:
            self.candidates = []
        self.position = 0
        self.entries: list[AdminUIHistoryEntry] = []
        self.projections: dict[Path, _RunHistoryProjection] = {}
        self.exhausted = False

    @staticmethod
    def _candidate_order_key(path: Path) -> tuple[int, str, str]:
        match = re.match(r"^(\d{8}T\d{6}Z)(?:_|$)", path.name)
        # Durable run IDs are the history ordering authority. Unparseable legacy
        # evidence remains deterministic, but follows every timestamped run.
        return (1, match.group(1), path.name) if match else (0, "", path.name)

    def projection(self, run_dir: Path) -> _RunHistoryProjection:
        cached = self.projections.get(run_dir)
        if cached is None:
            cached = self.service._history_projection(run_dir)
            self.projections[run_dir] = cached
        return cached

    def fill(self, limit: int) -> list[AdminUIHistoryEntry]:
        wanted = max(0, int(limit))
        while len(self.entries) < wanted and self.position < len(self.candidates):
            run_dir = self.candidates[self.position]
            self.position += 1
            try:
                entry = self.service._history_entry_from_projection(self.projection(run_dir))
            except (OSError, ValueError, TypeError):
                continue
            if entry is None or (not self.include_technical and entry.category != "Administration run"):
                continue
            self.entries.append(entry)
        self.exhausted = self.position >= len(self.candidates)
        return list(self.entries[:wanted])


_ADMIN_RUN_ID = re.compile(r"^\d{8}T\d{6}Z_(add_tickers|refresh_fundamentals|check_update_sector_industry|check_update_taxonomy|synchronize_provider_cik|resolve_ticker_identity)_[A-Za-z0-9_]+$")
_ADMIN_MODES = {
    "ADD_TICKERS": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL", "FULL_WORKFLOW"},
    "REFRESH_FUNDAMENTALS": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL", "FULL_WORKFLOW"},
    "CHECK_UPDATE_SECTOR_INDUSTRY": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_NO_CHANGE_APPLY", "READ_ONLY_AUDIT", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"},
    "CHECK_UPDATE_TAXONOMY": {"CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "COPY_ONLY_APPLY", "PROTECTED_PRODUCTION_PREVIEW", "PROTECTED_PRODUCTION_NO_CHANGE_VERIFY", "ACTIVE_TAXONOMY_PREVIEW", "PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"},
    "SYNCHRONIZE_PROVIDER_CIK": {"PREVIEW", "COPY_ONLY_APPLY", "PRODUCTION_APPLY"},
    "RESOLVE_TICKER_IDENTITY": {"PREVIEW"},
}


class FundamentalsAdminUIService:
    def __init__(
        self,
        *,
        run_root: Path = ADMIN_RUN_ROOT,
        history: AdminRunHistory | None = None,
        add_preview: Callable[..., dict[str, Any]] | None = None,
        add_apply: Callable[..., dict[str, Any]] | None = None,
        add_production_apply: Callable[..., dict[str, Any]] | None = None,
        refresh_preview: Callable[..., dict[str, Any]] | None = None,
        refresh_apply: Callable[..., dict[str, Any]] | None = None,
        refresh_production_apply: Callable[..., dict[str, Any]] | None = None,
        sector_preview: Callable[..., dict[str, Any]] | None = None,
        sector_apply: Callable[..., dict[str, Any]] | None = None,
        sector_production_apply: Callable[..., dict[str, Any]] | None = None,
        taxonomy_preview: Callable[..., dict[str, Any]] | None = None,
        taxonomy_apply: Callable[..., dict[str, Any]] | None = None,
        taxonomy_production_preview: Callable[..., dict[str, Any]] | None = None,
        taxonomy_production_apply: Callable[..., dict[str, Any]] | None = None,
        cik_preview: Callable[..., dict[str, Any]] | None = None,
        cik_apply: Callable[..., dict[str, Any]] | None = None,
        cik_production_apply: Callable[..., dict[str, Any]] | None = None,
        identity_preview: Callable[..., dict[str, Any]] | None = None,
        identity_paths: Any | None = None,
        cleanup_inspect: Callable[[str], Mapping[str, Any]] | None = None,
        cleanup_apply: Callable[[str], Mapping[str, Any]] | None = None,
        operation_lock_path: Path | None = None,
        recover_publication_on_startup: bool = True,
    ) -> None:
        self.run_root = run_root.resolve()
        self.history = history or AdminRunHistory(self.run_root)
        self._add_preview = add_preview or _admin_callable("batch_add_tickers", "run_preview")
        self._add_apply = add_apply or _admin_callable("batch_add_tickers", "run_apply")
        self._add_production_apply = add_production_apply or _admin_callable("batch_add_tickers", "run_production_apply")
        self._refresh_preview = refresh_preview or _admin_callable("refresh_fundamentals", "run_preview")
        self._refresh_apply = refresh_apply or _admin_callable("refresh_copy_runtime", "run_apply")
        self._refresh_production_apply = refresh_production_apply or _admin_callable("refresh_production", "run_production_apply")
        self._sector_preview = sector_preview or _admin_callable("sector_industry", "run_preview")
        self._sector_apply = sector_apply or _admin_callable("sector_industry", "run_apply")
        self._sector_production_apply = sector_production_apply or _admin_callable("sector_industry", "run_production_apply")
        self._taxonomy_preview = taxonomy_preview or _admin_callable("taxonomy_v2_sync", "run_preview")
        self._taxonomy_apply = taxonomy_apply or _admin_callable("taxonomy_v2_sync", "run_apply")
        self._taxonomy_production_preview = taxonomy_production_preview or _admin_callable("taxonomy_v2_sync", "run_preview")
        self._taxonomy_production_apply = taxonomy_production_apply or _admin_callable("taxonomy_v2_sync", "run_production_apply")
        self._cik_preview = cik_preview or _admin_callable("cik_sync", "run_preview")
        self._cik_apply = cik_apply or _admin_callable("cik_sync", "run_apply")
        self._cik_production_apply = cik_production_apply or _admin_callable("cik_sync", "run_production_apply")
        self._identity_preview = identity_preview or _admin_callable("identity_resolution", "run_preview")
        self._identity_paths = identity_paths
        self._cleanup_inspect = cleanup_inspect
        self._cleanup_apply = cleanup_apply
        self.operation_lock_path = (
            operation_lock_path
            or (self.run_root.parent / ".fundamentals_admin_ui_operation.lock")
        ).resolve()
        self._publication_safety = {"status": "CLEAR", "production_writes_blocked": False}
        self._publication_safety_initialized = False
        if recover_publication_on_startup and self.run_root == ADMIN_RUN_ROOT.resolve():
            self.initialize_publication_safety()

    def initialize_publication_safety(self) -> Mapping[str, Any]:
        if self._publication_safety_initialized:
            return self.publication_safety_status()
        if self.run_root == ADMIN_RUN_ROOT.resolve():
            self._initialize_publication_safety()
        self._publication_safety_initialized = True
        return self.publication_safety_status()

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
            AdminOperationCapability(
                "SYNCHRONIZE_PROVIDER_CIK", True, True, True,
                CIK_CONFIRMATION_TOKEN,
            ),
            AdminOperationCapability("RESOLVE_TICKER_IDENTITY", True, False, False),
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
        trigger_source: str = "MANUAL",
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
                trigger_source=trigger_source,
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
        elif operation == "SYNCHRONIZE_PROVIDER_CIK":
            result = self._cik_preview(
                run_root=self.run_root,
                progress_callback=progress_callback,
            )
        elif operation == "RESOLVE_TICKER_IDENTITY":
            if self._identity_paths is None:
                batch_module = import_module(
                    "rawcandle.fundamentals.admin.batch_add_tickers"
                )
                self._identity_paths = batch_module.BatchAddTickerPaths()
            result = self._identity_preview(
                raw_inputs,
                source_paths=self._identity_paths,
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
        elif operation == "SYNCHRONIZE_PROVIDER_CIK":
            result = self._cik_apply(
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
        elif operation == "SYNCHRONIZE_PROVIDER_CIK":
            result = self._cik_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_production=confirmation == CIK_CONFIRMATION_TOKEN,
                test_run_id=test_run_id,
                progress_callback=progress_callback,
            )
        else:
            raise ValueError("UNSUPPORTED_ADMIN_OPERATION")
        return self._finalize(result, default_message="Production apply completed.")

    def full_workflow(
        self,
        *,
        operation_type: str = "ADD_TICKERS",
        raw_inputs: str,
        market: str = "usa",
        progress_callback: AdminProgressCallback | None = None,
    ) -> AdminUIRunResult:
        with self._operation_lock():
            operation = operation_type.strip().upper()
            workflow_module = import_module(
                "rawcandle.fundamentals.admin.full_workflow"
            )
            if operation == "REFRESH_FUNDAMENTALS":
                result = workflow_module.run_refresh_full_workflow(
                    run_root=self.run_root,
                    preview_stage=lambda callback: self._preview_unlocked(
                        operation, progress_callback=callback,
                    ),
                    test_stage=lambda preview, callback: self._copy_apply_unlocked(
                        operation,
                        preview_payload_path=preview.preview_payload_path or "",
                        preview_fingerprint=preview.preview_fingerprint or "",
                        progress_callback=callback,
                    ),
                    production_stage=lambda preview, test, callback: self._production_apply_unlocked(
                        operation,
                        preview_payload_path=preview.preview_payload_path or "",
                        preview_fingerprint=preview.preview_fingerprint or "",
                        confirmation="CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS",
                        test_run_id=test.run_id or "",
                        progress_callback=callback,
                    ),
                    progress_callback=progress_callback,
                )
            elif operation == "ADD_TICKERS":
                result = workflow_module.run_full_workflow(
                    raw_inputs,
                    market=market,
                    run_root=self.run_root,
                    preview_stage=lambda callback: self._preview_unlocked(
                        operation, raw_inputs=raw_inputs, market=market,
                        network_allowed=True, progress_callback=callback,
                    ),
                    test_stage=lambda preview, callback: self._copy_apply_unlocked(
                        operation,
                        preview_payload_path=preview.preview_payload_path or "",
                        preview_fingerprint=preview.preview_fingerprint or "",
                        progress_callback=callback,
                    ),
                    production_stage=lambda preview, test, callback: self._production_apply_unlocked(
                        operation,
                        preview_payload_path=preview.preview_payload_path or "",
                        preview_fingerprint=preview.preview_fingerprint or "",
                        confirmation="CONFIRM_PRODUCTION_BATCH_ADD_TICKERS",
                        test_run_id=test.run_id or "",
                        progress_callback=callback,
                    ),
                    progress_callback=progress_callback,
                )
            else:
                raise ValueError("FULL_WORKFLOW_UNSUPPORTED_ADMIN_OPERATION")
        return self._finalize(result, default_message="Full workflow completed.")

    def progress(
        self,
        run_id: str,
        *,
        projection_cache: Mapping[Path, _RunHistoryProjection] | None = None,
    ) -> RunProgressSummary:
        projection = self._cached_projection(run_id, projection_cache)
        if projection is None:
            return self.history.progress(run_id)
        return self.history.progress(run_id, result_override=projection.result)

    def history_entries(self, *, limit: int = 20, include_technical: bool = False) -> list[AdminUIHistoryEntry]:
        cursor = self.history_cursor(include_technical=include_technical)
        return cursor.fill(limit)

    def history_cursor(self, *, include_technical: bool = False) -> AdminHistoryCursor:
        return AdminHistoryCursor(self, include_technical=include_technical)

    def remove_history_entry(self, run_id: str) -> Mapping[str, Any]:
        with self._operation_lock():
            retained_path = self.history.hide_run(run_id)
        return {
            "run_id": run_id,
            "status": "REMOVED_FROM_HISTORY",
            "audit_evidence_retained": True,
            "retained_path": str(retained_path),
        }

    def cleanup_eligibility(self, run_id: str) -> Mapping[str, Any]:
        if self._cleanup_inspect is not None:
            return self._cleanup_inspect(run_id)
        module = import_module("rawcandle.fundamentals.admin.run_acceptance_cleanup")
        return module.inspect_cleanup_eligibility(run_id, run_root=self.run_root)

    def accept_run_and_cleanup_backups(self, run_id: str) -> Mapping[str, Any]:
        with self._operation_lock():
            if self._cleanup_apply is not None:
                return self._cleanup_apply(run_id)
            module = import_module("rawcandle.fundamentals.admin.run_acceptance_cleanup")
            return module.accept_run_and_cleanup_backups(run_id, run_root=self.run_root)

    def history_result_summary(
        self,
        run_id: str,
        *,
        projection_cache: Mapping[Path, _RunHistoryProjection] | None = None,
    ) -> tuple[str, ...]:
        projection = self._cached_projection(run_id, projection_cache)
        if projection is None:
            result_path = self.history.artifact_path(run_id, "result.json")
            result = self._load_json_file(result_path)
        else:
            result = projection.result
        if result is None:
            raise ValueError("invalid admin result")
        return build_operation_summary(result)

    @staticmethod
    def _cached_projection(
        run_id: str,
        projection_cache: Mapping[Path, _RunHistoryProjection] | None,
    ) -> _RunHistoryProjection | None:
        if projection_cache is None:
            return None
        return next(
            (projection for path, projection in projection_cache.items() if path.name == run_id),
            None,
        )

    def resolve_report_download(self, run_id: str) -> Path:
        return resolve_operation_report_download(run_id, root=self.run_root)

    def resolve_named_report_download(self, run_id: str, filename: str) -> Path:
        return resolve_operation_report_download(run_id, filename, root=self.run_root)

    def _history_projection(self, run_dir: Path) -> _RunHistoryProjection:
        result = self._load_json_file(run_dir / "result.json")
        request = self._load_json_file(run_dir / "request.json")
        status = self._load_json_file(run_dir / "progress_status.json") or self._load_json_file(run_dir / "status.json")
        invalid_artifact = any(
            (run_dir / name).is_symlink() or ((run_dir / name).exists() and parsed is None)
            for name, parsed in (("result.json", result), ("request.json", request))
        )
        return _RunHistoryProjection(run_dir, result, request, status, invalid_artifact)

    def _history_entry_for_run_dir(self, run_dir: Path) -> AdminUIHistoryEntry | None:
        return self._history_entry_from_projection(self._history_projection(run_dir))

    def _history_entry_from_projection(self, projection: _RunHistoryProjection) -> AdminUIHistoryEntry | None:
        run_dir = projection.run_dir
        run_id = run_dir.name
        result = projection.result
        request = projection.request
        status = projection.status
        invalid_artifact = projection.invalid_artifact
        category = "Invalid or corrupt run" if invalid_artifact else self._classify_run_dir(run_dir, result=result, request=request, status=status)
        if category == "Invalid or corrupt run":
            return AdminUIHistoryEntry(
                run_id=run_id,
                operation_type="Invalid run",
                outcome="CORRUPT_OR_INCOMPLETE",
                status="corrupt_or_incomplete",
                mode="INVALID",
                completed_at_utc=None,
                report_available=(run_dir / OPERATION_REPORT_NAME).is_file(),
                category="Invalid or corrupt run",
            )
        if category == "Administration run":
            payload = result or {}
            if not payload:
                return AdminUIHistoryEntry(
                    run_id=run_id,
                    operation_type=str((request or status or {}).get("operation_type", "Administration")),
                    outcome="CORRUPT_OR_INCOMPLETE",
                    status="corrupt_or_incomplete",
                    mode="UNKNOWN",
                    completed_at_utc=None,
                    report_available=(run_dir / OPERATION_REPORT_NAME).is_file(),
                    category="Invalid or corrupt run",
                    primary_count=self._primary_count(request or {}),
                )
            outcome = str(payload.get("outcome", "UNKNOWN"))
            mode = str(payload.get("mode", "UNKNOWN"))
            return AdminUIHistoryEntry(
                run_id=run_id,
                operation_type=str(payload.get("operation_type", (request or status or {}).get("operation_type", "UNKNOWN"))),
                outcome=(taxonomy_preview_presentation(payload) or {}).get("business_outcome", outcome),
                status="completed" if outcome == "COMPLETED" else outcome.lower(),
                mode=mode,
                completed_at_utc=(
                    payload.get("completed_at_utc")
                    or payload.get("started_at_utc")
                    or (status or {}).get("timestamp_utc")
                    or _run_id_timestamp(run_id)
                ),
                report_available=(run_dir / OPERATION_REPORT_NAME).is_file(),
                category=category,
                primary_count=self._primary_count(payload or request or {}),
                duration_seconds=self._duration_seconds(payload),
                count_label=self._count_label(payload or request or {}),
                report_filename=WORKFLOW_REPORT_NAME if mode == "FULL_WORKFLOW" else OPERATION_REPORT_NAME,
                trigger_source=str(payload.get("trigger_source") or "MANUAL"),
            )
        payload = result or request or status or {}
        return AdminUIHistoryEntry(
            run_id=run_id,
            operation_type=str(payload.get("operation_type", category)),
            outcome=str(payload.get("outcome", category.upper().replace(" ", "_"))),
            status=category.lower().replace(" ", "_"),
            mode=str(payload.get("mode", "TECHNICAL")),
            completed_at_utc=(
                payload.get("completed_at_utc")
                or payload.get("started_at_utc")
                or payload.get("timestamp_utc")
                or _run_id_timestamp(run_id)
            ),
            report_available=(run_dir / OPERATION_REPORT_NAME).is_file(),
            category=category,
            primary_count=self._primary_count(payload),
            duration_seconds=self._duration_seconds(payload),
            trigger_source=str(payload.get("trigger_source") or "MANUAL"),
        )

    def pending_refresh_status(
        self,
        *,
        projection_cache: Mapping[Path, _RunHistoryProjection] | None = None,
    ) -> Mapping[str, Any] | None:
        if not self.run_root.exists():
            return None
        try:
            candidates = sorted(
                (
                    run_dir for run_dir in self.run_root.iterdir()
                    if run_dir.is_dir()
                    and not run_dir.is_symlink()
                    and "_refresh_fundamentals_" in run_dir.name
                ),
                key=lambda path: path.name,
                reverse=True,
            )
        except OSError:
            return {"status": "ERROR", "error": "Refresh history is unavailable."}
        for run_dir in candidates:
            cached = (projection_cache or {}).get(run_dir)
            payload = cached.result if cached is not None else self._load_json_file(run_dir / "result.json")
            if payload is None:
                return {
                    "status": "ERROR",
                    "error": f"Newest Refresh evidence is incomplete or corrupt: {run_dir.name}",
                }
            if payload.get("operation_type") != "REFRESH_FUNDAMENTALS":
                continue
            if (
                payload.get("mode") == "PREVIEW"
                and payload.get("trigger_source") == "SCHEDULER"
            ):
                counts = dict(payload.get("summary_counts") or {})
                if payload.get("outcome") != "COMPLETED" or not int(counts.get("effective_changed_known") or 0):
                    return None
                return {
                    "status": "PENDING",
                    "detected_at_utc": payload.get("completed_at_utc"),
                    "effective_changed_known": int(counts.get("effective_changed_known") or 0),
                    "new_quarter": int(counts.get("NEW_QUARTER") or 0),
                    "historical_revision": int(counts.get("HISTORICAL_REVISION") or 0),
                    "source_removal": int(counts.get("SOURCE_REMOVAL") or 0),
                    "source_history_change": int(counts.get("SOURCE_HISTORY_CHANGE") or 0),
                    "newly_aged_out_source_rows": int(counts.get("newly_aged_out_source_rows") or 0),
                    "retained_arq": int(counts.get("retained_arq") or 0),
                    "retained_mrq": int(counts.get("retained_mrq") or 0),
                    "true_source_removals": int(counts.get("true_source_removals") or 0),
                    "ambiguous_removals": int(counts.get("ambiguous_removals") or 0),
                    "fiscal_identity_revisions": int(counts.get("fiscal_identity_revisions") or 0),
                    "fiscal_identity_revisions_requiring_review": int(counts.get("fiscal_identity_revisions_requiring_review") or 0),
                    "unknown_tickers": int(counts.get("NOT_IN_CANONICAL_UNIVERSE") or 0),
                    "run_id": payload.get("run_id"),
                    "report": str(Path(str(payload.get("artifact_dir") or "")) / OPERATION_REPORT_NAME),
                    "production_authorized": False,
                }
        return None

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
        retry_value = result.get("retry_authorization")
        retry = retry_value if isinstance(retry_value, Mapping) else {}
        report: OperationReportSummary | None = None
        workflow_mode = result.get("mode") == "FULL_WORKFLOW"
        if run_id and workflow_mode:
            report_path = self.run_root / run_id / WORKFLOW_REPORT_NAME
            if report_path.is_file() and not report_path.is_symlink():
                workflow_module = import_module(
                    "rawcandle.fundamentals.admin.full_workflow"
                )
                workflow_rows = workflow_module.workflow_ui_summary(result)
                report = OperationReportSummary(
                    run_id=run_id,
                    operation_type=str(result.get("operation_type") or "ADD_TICKERS"),
                    outcome=str(result.get("outcome") or "RECORDED"),
                    mode="FULL_WORKFLOW",
                    summary_rows=workflow_rows,
                    report_path=str(report_path),
                    report_sha256=sha256_file(report_path),
                )
        elif run_id:
            report = write_operation_report(run_id, root=self.run_root)
        payload_path = (
            result.get("phase13d_preview_payload_path")
            or result.get("identity_preview_path")
            or result.get("preview_payload_path")
            or result.get("payload_path")
            or ((result.get("preview") or {}).get("payload") if isinstance(result.get("preview"), Mapping) else None)
        )
        errors = result.get("errors")
        first_error = errors[0] if isinstance(errors, (list, tuple)) and errors and isinstance(errors[0], Mapping) else {}
        return AdminUIRunResult(
            status="RETRY_REQUIRED" if result.get("outcome") == "RETRY_REQUIRED" else ("FAILED" if result.get("outcome") in {"FAILED", "STOPPED", "ERROR", "INTERRUPTED", "ROLLED_BACK", "FAILED_ROLLED_BACK", "CRITICAL_ROLLBACK_FAILED"} else "COMPLETED"),
            message=(
                str((result.get("terminal_summary") or {}).get("headline"))
                if workflow_mode and (result.get("terminal_summary") or {}).get("headline")
                else final_status_message(result) if result.get("mode") else default_message
            ),
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
            direct_production_retry_available=bool(retry.get("direct_production_retry_available") or result.get("manual_production_retry_available") or result.get("manual_production_available")),
            preview_test_rerun_required=bool(
                retry.get("preview_test_rerun_required")
                or result.get("preview_test_rerun_required")
            ),
            workflow_stage_run_ids=tuple(
                str(stage.get("run_id"))
                for stage in (result.get("stages") or [])
                if isinstance(stage, Mapping) and stage.get("run_id")
            ),
            test_run_id=str(result.get("test_run_id")) if result.get("test_run_id") else None,
            direct_test_retry_available=bool(result.get("manual_test_retry_available")),
        )
