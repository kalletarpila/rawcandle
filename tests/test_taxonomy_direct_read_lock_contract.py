from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from rawcandle import datacenter_taxonomy_operation_log as taxonomy_locking
from rawcandle.cli import activate_datacenter_taxonomy_change
from rawcandle.cli import apply_datacenter_taxonomy_activation
from rawcandle.cli import apply_datacenter_taxonomy_version
from rawcandle.cli import run_datacenter_taxonomy_change
from rawcandle.cli import run_ec_source_layer_build
from rawcandle.fundamentals.admin.production_transaction import production_lock
from rawcandle.scheduler.runner import acquire_scheduler_lock


RUNTIME_TAXONOMY_WRITER_ENTRYPOINTS = (
    run_datacenter_taxonomy_change.main,
    activate_datacenter_taxonomy_change.main,
    apply_datacenter_taxonomy_version.main,
    apply_datacenter_taxonomy_activation.main,
    run_ec_source_layer_build.main,
)


def _taxonomy_lock_context_calls(function: object) -> list[ast.Call]:
    tree = ast.parse(inspect.getsource(function))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "taxonomy_operation_lock_context"
    ]


def test_every_runtime_taxonomy_writer_uses_authoritative_lock() -> None:
    assert len(RUNTIME_TAXONOMY_WRITER_ENTRYPOINTS) == 5
    for entrypoint in RUNTIME_TAXONOMY_WRITER_ENTRYPOINTS:
        calls = _taxonomy_lock_context_calls(entrypoint)
        assert len(calls) == 1, entrypoint.__module__
        assert all(keyword.arg != "evidence_root" for keyword in calls[0].keywords)

    ui_source = Path("dev_tools/stock_update_scheduler_ui.py").read_text(encoding="utf-8")
    ui_calls = [
        node
        for node in ast.walk(ast.parse(ui_source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "taxonomy_operation_lock_context"
    ]
    assert len(ui_calls) == 4
    assert all(
        keyword.arg != "evidence_root"
        for call in ui_calls
        for keyword in call.keywords
    )


def test_supported_admin_scheduler_taxonomy_lock_order_and_reverse_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        taxonomy_locking,
        "DEFAULT_TAXONOMY_OPERATION_ROOT",
        tmp_path / "temp" / "taxonomy",
    )
    scheduler_dir = tmp_path / "scheduler"

    with production_lock(lock_path=tmp_path / "admin.lock", scheduler_log_dir=str(scheduler_dir)):
        with taxonomy_locking.taxonomy_operation_lock_context(
            deployment_id="fixture",
            operation_type="DIRECT_LOCKED_READ",
            operation_id="ordered",
        ):
            assert taxonomy_locking.taxonomy_lock_held_in_process() is True

    with taxonomy_locking.taxonomy_operation_lock_context(
        deployment_id="fixture",
        operation_type="DIRECT_LOCKED_READ",
        operation_id="reverse",
    ):
        with pytest.raises(RuntimeError, match="TAXONOMY_BEFORE_ADMIN_PRODUCTION"):
            with production_lock(
                lock_path=tmp_path / "admin-reverse.lock",
                scheduler_log_dir=str(scheduler_dir),
            ):
                raise AssertionError("reverse admin lock order was accepted")
        with pytest.raises(RuntimeError, match="TAXONOMY_BEFORE_SCHEDULER"):
            acquire_scheduler_lock(str(scheduler_dir))

    assert taxonomy_locking.taxonomy_lock_held_in_process() is False
    assert not taxonomy_locking.authoritative_taxonomy_lock_path().exists()
