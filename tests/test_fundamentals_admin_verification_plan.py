from __future__ import annotations

import json
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.taxonomy_role_aware_closure import (
    PREVIOUS_TIMEOUT,
    TEST_ONLY_VERSION,
    compare_lightweight_to_retained_baseline,
    phase13g42_role_contract,
    reconcile_phase13g42_evidence,
)
from rawcandle.fundamentals.admin.verification_plan import (
    DatabaseRoleDeclaration,
    OperationRoleContract,
    build_verification_plan,
)


def _role(plan: dict, environment: str, semantic_role: str) -> dict:
    return next(row for row in plan["roles"] if row["environment"] == environment and row["semantic_role"] == semantic_role)


def test_production_readonly_gets_targeted_checks_without_heavy_guards(tmp_path: Path) -> None:
    plan = build_verification_plan(
        OperationRoleContract(
            operation_name="readonly",
            declarations=(DatabaseRoleDeclaration("taxonomy", "production", "read-only", tmp_path / "taxonomy.db"),),
        )
    )

    row = _role(plan, "production", "taxonomy")
    assert row["backup_required"] is False
    assert row["rollback_required"] is False
    assert "bounded_targeted_consistency_queries" in row["preflight_checks"]
    assert "full_integrity_quick_check" not in row["preflight_checks"]
    assert "post_write_quick_check" not in row["postflight_checks"]


def test_production_writable_keeps_heavy_protection_after_write_boundary(tmp_path: Path) -> None:
    plan = build_verification_plan(
        OperationRoleContract(
            operation_name="write",
            declarations=(DatabaseRoleDeclaration("taxonomy", "production", "writable", tmp_path / "taxonomy.db"),),
            write_boundary_crossed=True,
        )
    )

    row = _role(plan, "production", "taxonomy")
    assert row["backup_required"] is True
    assert row["rollback_required"] is True
    assert "full_integrity_quick_check" in row["preflight_checks"]
    assert "post_write_quick_check" in row["postflight_checks"]
    assert "protected_logical_inventory" in row["postflight_checks"]


def test_production_writable_without_write_boundary_skips_redundant_postflight(tmp_path: Path) -> None:
    plan = build_verification_plan(
        OperationRoleContract(
            operation_name="guarded-no-write",
            declarations=(DatabaseRoleDeclaration("taxonomy", "production", "writable", tmp_path / "taxonomy.db"),),
            write_boundary_crossed=False,
        )
    )

    row = _role(plan, "production", "taxonomy")
    assert row["backup_required"] is False
    assert row["rollback_required"] is False
    assert row["postflight_checks"] == ["targeted_no_write_confirmation"]
    assert "post_write_quick_check" not in row["postflight_checks"]


def test_copy_writable_gets_apply_repeat_and_rollback_checks(tmp_path: Path) -> None:
    plan = build_verification_plan(
        OperationRoleContract(
            operation_name="copy",
            declarations=(DatabaseRoleDeclaration("analysis", "copy", "writable", tmp_path / "analysis.db"),),
        )
    )

    row = _role(plan, "copy", "analysis")
    assert row["backup_required"] is False
    assert row["rollback_required"] is True
    assert "copy_integrity_after_apply" in row["postflight_checks"]
    assert "repeat_no_change_logical_comparison" in row["postflight_checks"]
    assert "rollback_restores_baseline" in row["postflight_checks"]


def test_unknown_or_conflicting_roles_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="UNKNOWN_ACCESS_MODE"):
        build_verification_plan(OperationRoleContract("bad", (DatabaseRoleDeclaration("x", "production", "maybe", tmp_path / "x.db"),)))

    with pytest.raises(ValueError, match="CONFLICTING_ROLE"):
        build_verification_plan(
            OperationRoleContract(
                "conflict",
                (
                    DatabaseRoleDeclaration("taxonomy", "production", "read-only", tmp_path / "taxonomy.db"),
                    DatabaseRoleDeclaration("taxonomy", "production", "writable", tmp_path / "taxonomy.db"),
                ),
            )
        )


def test_phase13g42_taxonomy_is_readonly_but_future_production_taxonomy_is_writable() -> None:
    current = build_verification_plan(phase13g42_role_contract())
    future = build_verification_plan(phase13g42_role_contract(future_production_taxonomy=True))

    assert "taxonomy" in current["role_matrix"]["production_readonly_roles"]
    assert current["role_matrix"]["production_writable_roles"] == []
    assert "taxonomy" in future["role_matrix"]["production_writable_roles"]
    assert "post_write_quick_check" not in _role(current, "production", "taxonomy")["postflight_checks"]


def test_lightweight_comparator_detects_logical_drift_and_ignores_physical_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "retained"
    run_dir.mkdir()
    baseline = {
        "logical_state": {
            "dc_taxonomy": {
                "active_version": {"taxonomy_version_code": "DC_TAXONOMY_FULL_V2_1"},
                "semantic_fingerprint": "semantic-1",
                "counts": {"rows": 350},
            },
            "taxonomy_identity": {"taxonomy_economic_fingerprint": "econ-1"},
            "active_identities": {
                "operating_income_package": {"family": "oi"},
                "active_relative_position": [{"snapshot_id": "rp"}],
                "active_relative_valuation": {"active_snapshot_id": "rv"},
            },
        }
    }
    (run_dir / "production_logical_baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    current = {
        "state": {
            "taxonomy": {
                "dc_active_version": {"taxonomy_version_code": "DC_TAXONOMY_FULL_V2_1"},
                "dc_semantic_fingerprint": "semantic-1",
                "dc_counts": {"rows": 350},
                "taxonomy_identity": {"taxonomy_economic_fingerprint": "econ-1"},
                "file_size": 123,
            },
            "active_downstream": {
                "operating_income_package": {"family": "oi"},
                "active_relative_position": [{"snapshot_id": "rp"}],
                "active_relative_valuation": {"active_snapshot_id": "rv"},
            },
        }
    }

    assert compare_lightweight_to_retained_baseline(current, run_dir)["status"] == "MATCH"
    drifted = json.loads(json.dumps(current))
    drifted["state"]["taxonomy"]["dc_semantic_fingerprint"] = "semantic-2"
    assert compare_lightweight_to_retained_baseline(drifted, run_dir)["status"] == "MISMATCH"


def test_phase13g42_artifact_parser_validates_core_acceptance_evidence(tmp_path: Path) -> None:
    run_dir = tmp_path / "phase13g42"
    run_dir.mkdir()

    def write(name: str, value: object) -> None:
        (run_dir / name).write_text(json.dumps(value), encoding="utf-8")

    write("result.json", {"outcome": "FAILED", "outcome_text": "OUTCOME C - PRODUCTION UNCHANGED"})
    write("error.json", {"message": PREVIOUS_TIMEOUT})
    write("test_only_candidate.json", {"status": "TEST_ONLY_NOT_FOR_PRODUCTION", "candidate_version": TEST_ONLY_VERSION, "affected_ticker": "AAOI", "change_type": "ROLE_TIER_CHANGED"})
    write(
        "primary_taxonomy_apply.json",
        {
            "taxonomy_apply": {"outcome": "APPLIED", "domain": "dc_ecosystem"},
            "ec_unchanged": True,
            "after": {"ec_status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY"},
        },
    )
    write("change_counters.json", {"semantic_changes": 1, "role_or_tier_changes": 1, "persisted_membership_rows": 350})
    write(
        "primary_downstream.json",
        {
            "invocation_counts": {"package": 1, "relative_position": 1, "relative_valuation": 1, "dependency_attachment": 1, "compatibility_verification": 1, "snapshot": 2},
            "dependencies": {"status": "COMPATIBLE"},
            "fingerprints": {"fingerprint": "downstream", "payload": {"snapshots": {"AAOI": {"fingerprint": "a"}, "NVDA": {"fingerprint": "n"}}}},
        },
    )
    write(
        "fixed_point_repeat.json",
        {
            "outcome": "NO_CHANGE",
            "taxonomy_writes": 0,
            "membership_writes": 0,
            "new_version_rows": 0,
            "dependency_writes": 0,
            "snapshot_regeneration": 0,
            "package_relative_position_relative_valuation_invocations": "0/0/0",
        },
    )
    write("independent_replay.json", {"status": "MATCH", "lane_match": {"taxonomy": True, "downstream": True}, "downstream": {"fingerprints": {"fingerprint": "downstream"}}})
    write(
        "rollback_after_downstream.json",
        {
            "partial_taxonomy_state_existed": True,
            "partial_downstream_state_existed": True,
            "restored_matches_baseline": True,
            "downstream_invocation_counts_before_restore": {"package": 1},
        },
    )
    write("production_logical_baseline.json", {"status": "OK"})
    write("postflight_heartbeat.json", {"events": [{"event": "stage_failed", "details": {"role": "taxonomy", "stage": "quick_check", "error": "BoundedPostflightTimeout"}}]})
    write("artifact_manifest.json", {"artifacts": []})
    (run_dir / "exit_code").write_text("2\n", encoding="utf-8")

    evidence = reconcile_phase13g42_evidence(run_dir)

    assert evidence["status"] == "VALIDATED"
    assert evidence["change_counters"]["semantic_changes"] == 1
    assert evidence["previous_timeout"]["reclassified_as"] == "OVER_BROAD_READ_ONLY_HEAVY_CHECK"
