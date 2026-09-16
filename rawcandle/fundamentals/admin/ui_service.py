from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin import batch_add_tickers, sector_industry, taxonomy
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.history import AdminRunHistory, RunHistoryEntry, RunProgressSummary
from rawcandle.fundamentals.admin.operation_report import (
    OPERATION_REPORT_NAME,
    OperationReportSummary,
    resolve_operation_report_download,
    write_operation_report,
)
from rawcandle.fundamentals.admin.taxonomy import SUPPORTED_TAXONOMY_DOMAINS
from rawcandle.fundamentals.admin.taxonomy_production import (
    CONFIRMATION_TOKEN as TAXONOMY_PRODUCTION_CONFIRMATION_TOKEN,
    run_production_preview as run_taxonomy_production_preview,
    run_protected_production_apply as run_taxonomy_production_apply,
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


@dataclass(frozen=True)
class AdminUIHistoryEntry:
    run_id: str
    operation_type: str
    outcome: str
    status: str
    mode: str
    completed_at_utc: str | None
    report_available: bool


class FundamentalsAdminUIService:
    def __init__(
        self,
        *,
        run_root: Path = ADMIN_RUN_ROOT,
        history: AdminRunHistory | None = None,
        add_preview: Callable[..., dict[str, Any]] = batch_add_tickers.run_preview,
        add_apply: Callable[..., dict[str, Any]] = batch_add_tickers.run_apply,
        add_production_apply: Callable[..., dict[str, Any]] = batch_add_tickers.run_production_apply,
        sector_preview: Callable[..., dict[str, Any]] = sector_industry.run_preview,
        sector_apply: Callable[..., dict[str, Any]] = sector_industry.run_apply,
        sector_production_apply: Callable[..., dict[str, Any]] = sector_industry.run_production_apply,
        taxonomy_preview: Callable[..., dict[str, Any]] = taxonomy.run_preview,
        taxonomy_apply: Callable[..., dict[str, Any]] = taxonomy.run_apply,
        taxonomy_production_preview: Callable[..., dict[str, Any]] = run_taxonomy_production_preview,
        taxonomy_production_apply: Callable[..., dict[str, Any]] = run_taxonomy_production_apply,
    ) -> None:
        self.run_root = run_root.resolve()
        self.history = history or AdminRunHistory(self.run_root)
        self._add_preview = add_preview
        self._add_apply = add_apply
        self._add_production_apply = add_production_apply
        self._sector_preview = sector_preview
        self._sector_apply = sector_apply
        self._sector_production_apply = sector_production_apply
        self._taxonomy_preview = taxonomy_preview
        self._taxonomy_apply = taxonomy_apply
        self._taxonomy_production_preview = taxonomy_production_preview
        self._taxonomy_production_apply = taxonomy_production_apply

    def capabilities(self) -> tuple[AdminOperationCapability, ...]:
        return (
            AdminOperationCapability("ADD_TICKERS", True, True, True),
            AdminOperationCapability("CHECK_UPDATE_SECTOR_INDUSTRY", True, True, True),
            AdminOperationCapability(
                "CHECK_UPDATE_TAXONOMY",
                True,
                True,
                True,
                production_confirmation_hint=TAXONOMY_PRODUCTION_CONFIRMATION_TOKEN,
            ),
        )

    def preview(
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
        elif operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            result = self._sector_preview(
                raw_inputs,
                run_root=self.run_root,
                market=market,
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_TAXONOMY":
            if taxonomy_domain not in SUPPORTED_TAXONOMY_DOMAINS:
                raise ValueError("UNSUPPORTED_TAXONOMY_DOMAIN")
            if production_mode:
                result = self._taxonomy_production_preview(
                    candidate_path=Path(candidate_path) if candidate_path else None,
                    candidate_version=candidate_version,
                    run_root=self.run_root,
                    progress_callback=progress_callback,
                )
            else:
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
        *,
        preview_payload_path: str,
        preview_fingerprint: str,
        confirmation: str,
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
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            result = self._sector_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirm_production=confirmation == "CONFIRM_PRODUCTION_SECTOR_INDUSTRY",
                progress_callback=progress_callback,
            )
        elif operation == "CHECK_UPDATE_TAXONOMY":
            result = self._taxonomy_production_apply(
                preview_payload_path=payload_path,
                preview_fingerprint=preview_fingerprint,
                run_root=self.run_root,
                confirmation=confirmation,
                progress_callback=progress_callback,
            )
        else:
            raise ValueError("UNSUPPORTED_ADMIN_OPERATION")
        return self._finalize(result, default_message="Production apply completed.")

    def progress(self, run_id: str) -> RunProgressSummary:
        return self.history.progress(run_id)

    def history_entries(self, *, limit: int = 20) -> list[AdminUIHistoryEntry]:
        entries: list[AdminUIHistoryEntry] = []
        try:
            history_items = self.history.list_runs()[:limit]
        except Exception:
            return []
        for item in history_items:
            mode = self._mode_for_entry(item)
            report_available = OPERATION_REPORT_NAME in self._artifact_names(item.run_id)
            entries.append(
                AdminUIHistoryEntry(
                    run_id=item.run_id,
                    operation_type=item.operation_type,
                    outcome=item.outcome,
                    status=item.status,
                    mode=mode,
                    completed_at_utc=item.completed_at_utc,
                    report_available=report_available,
                )
            )
        return entries

    def resolve_report_download(self, run_id: str) -> Path:
        return resolve_operation_report_download(run_id, root=self.run_root)

    def _artifact_names(self, run_id: str) -> tuple[str, ...]:
        try:
            return self.history.progress(run_id).artifacts
        except Exception:
            return ()

    def _mode_for_entry(self, entry: RunHistoryEntry) -> str:
        try:
            path = self.history.artifact_path(entry.run_id, "result.json")
            import json

            result = json.loads(path.read_text(encoding="utf-8"))
            return str(result.get("mode", "UNKNOWN"))
        except Exception:
            return "UNKNOWN"

    def _finalize(self, result: Mapping[str, Any], *, default_message: str) -> AdminUIRunResult:
        run_id = str(result.get("run_id") or "")
        report: OperationReportSummary | None = None
        if run_id:
            report = write_operation_report(run_id, root=self.run_root)
        payload_path = (
            result.get("phase13d_preview_payload_path")
            or result.get("preview_payload_path")
            or result.get("payload_path")
        )
        return AdminUIRunResult(
            status="COMPLETED",
            message=default_message,
            run_id=run_id or None,
            outcome=str(result.get("outcome")) if result.get("outcome") is not None else None,
            mode=str(result.get("mode")) if result.get("mode") is not None else None,
            preview_fingerprint=str(result.get("preview_fingerprint")) if result.get("preview_fingerprint") else None,
            preview_payload_path=str(payload_path) if payload_path else None,
            artifact_dir=str(result.get("artifact_dir")) if result.get("artifact_dir") else None,
            report_filename=OPERATION_REPORT_NAME if report else None,
            report_sha256=report.report_sha256 if report else None,
            summary_rows=report.summary_rows if report else (),
        )
