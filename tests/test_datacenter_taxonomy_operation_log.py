from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from rawcandle.datacenter_taxonomy_operation_log import (
    append_taxonomy_operation_log,
    complete_taxonomy_change_operation,
    create_taxonomy_change_operation,
    inspect_taxonomy_change_artifacts,
    list_taxonomy_change_operations,
    prepare_taxonomy_change_evidence_package,
    prepare_taxonomy_change_log_download,
    read_taxonomy_change_log,
    write_taxonomy_operation_artifact,
)


def test_taxonomy_operation_log_is_durable_and_rediscoverable(tmp_path):
    root = tmp_path / "repo" / "temp" / "datacenter_taxonomy_changes"
    operation = create_taxonomy_change_operation(
        deployment_id=42,
        operation_type="PREPARE",
        evidence_root=root,
    )
    write_taxonomy_operation_artifact(operation, relative_name="plan.json", payload={"plan_hash": "abc"})
    append_taxonomy_operation_log(operation, phase="PLAN", status="OK", message="planned")
    completed = complete_taxonomy_change_operation(operation, status="OK")

    operations = list_taxonomy_change_operations(deployment_id=42, evidence_root=root)
    artifacts = inspect_taxonomy_change_artifacts(
        deployment_id=42,
        operation_id=operation.operation_id,
        evidence_root=root,
    )
    log = read_taxonomy_change_log(
        deployment_id=42,
        operation_id=operation.operation_id,
        limit=4096,
        evidence_root=root,
    )

    assert operations[0]["operation_id"] == operation.operation_id
    assert operations[0]["status"] == "OK"
    assert completed.completed_at_utc is not None
    assert artifacts["primary_log"]["exists"] is True
    assert artifacts["artifact_manifest"]["artifacts"][0]["path"] == "plan.json"
    assert log["status"] == "OK"
    assert "planned" in log["text"]


def test_failed_and_resumed_taxonomy_operations_keep_separate_logs(tmp_path):
    root = tmp_path / "repo" / "temp" / "datacenter_taxonomy_changes"
    failed = create_taxonomy_change_operation(deployment_id=7, operation_type="REBUILD", evidence_root=root)
    complete_taxonomy_change_operation(failed, status="FAILED", failed_phase="DC", resume_from_phase="DC")
    resumed = create_taxonomy_change_operation(deployment_id=7, operation_type="RESUME", evidence_root=root)
    complete_taxonomy_change_operation(resumed, status="OK")

    operations = list_taxonomy_change_operations(deployment_id=7, evidence_root=root)

    assert {operation["operation_type"] for operation in operations} == {"REBUILD", "RESUME"}
    assert len({operation["primary_log_path"] for operation in operations}) == 2


def test_taxonomy_log_download_and_bounded_read_use_operation_lookup(tmp_path):
    root = tmp_path / "repo" / "temp" / "datacenter_taxonomy_changes"
    operation = create_taxonomy_change_operation(deployment_id=1, operation_type="PREPARE", evidence_root=root)
    append_taxonomy_operation_log(operation, phase="LONG", status="OK", message="x" * 1000)

    first_chunk = read_taxonomy_change_log(
        deployment_id=1,
        operation_id=operation.operation_id,
        limit=80,
        evidence_root=root,
    )
    download = prepare_taxonomy_change_log_download(
        deployment_id=1,
        operation_id=operation.operation_id,
        evidence_root=root,
    )

    assert first_chunk["truncated"] is True
    assert len(first_chunk["text"]) <= 80
    assert download["status"] == "OK"
    assert download["filename"].startswith("datacenter_taxonomy_change_deployment_1_")


def test_taxonomy_evidence_package_manifest_hashes_and_exclusions(tmp_path):
    root = tmp_path / "repo" / "temp" / "datacenter_taxonomy_changes"
    operation = create_taxonomy_change_operation(deployment_id=2, operation_type="PREPARE", evidence_root=root)
    write_taxonomy_operation_artifact(operation, relative_name="plan.json", payload={"ok": True})
    Path(operation.evidence_root, "analysis.db").write_text("db", encoding="utf-8")
    Path(operation.evidence_root, "backup.sqlite").write_text("backup", encoding="utf-8")

    package = prepare_taxonomy_change_evidence_package(
        deployment_id=2,
        operation_id=operation.operation_id,
        evidence_root=root,
    )

    assert package["status"] == "OK"
    with zipfile.ZipFile(package["path"]) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("package_manifest.json").decode("utf-8"))
    assert "plan.json" in names
    assert "analysis.db" not in names
    assert "backup.sqlite" not in names
    assert [item["path"] for item in manifest["included_files"]] == sorted(
        item["path"] for item in manifest["included_files"]
    )
    assert all(item["sha256"] for item in manifest["included_files"])
    assert {item["path"] for item in manifest["excluded_files"]} == {"analysis.db", "backup.sqlite"}


def test_taxonomy_operation_security_rejects_unknown_and_cross_deployment(tmp_path):
    root = tmp_path / "repo" / "temp" / "datacenter_taxonomy_changes"
    operation = create_taxonomy_change_operation(deployment_id=3, operation_type="PREPARE", evidence_root=root)

    with pytest.raises(FileNotFoundError):
        read_taxonomy_change_log(deployment_id=3, operation_id="missing", evidence_root=root)
    with pytest.raises(FileNotFoundError):
        read_taxonomy_change_log(deployment_id=4, operation_id=operation.operation_id, evidence_root=root)


def test_taxonomy_evidence_root_must_be_under_temp(tmp_path):
    with pytest.raises(ValueError):
        create_taxonomy_change_operation(
            deployment_id=1,
            operation_type="PREPARE",
            evidence_root=tmp_path / "outside",
        )


def test_taxonomy_package_rejects_symlink_escape(tmp_path):
    root = tmp_path / "repo" / "temp" / "datacenter_taxonomy_changes"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    operation = create_taxonomy_change_operation(deployment_id=5, operation_type="PREPARE", evidence_root=root)
    Path(operation.evidence_root, "escape.json").symlink_to(outside)

    with pytest.raises(ValueError):
        prepare_taxonomy_change_evidence_package(
            deployment_id=5,
            operation_id=operation.operation_id,
            evidence_root=root,
        )
