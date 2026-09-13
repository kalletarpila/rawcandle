from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

import pytest

from rawcandle.fundamentals.phase13f4_2_production import (
    ACCEPTED,
    _acceptance_blockers,
    _acceptance_view,
    acceptance_contract_artifact,
    run_phase13f4_2,
)
from rawcandle.fundamentals.relative_valuation.persistence import ApplyReport


def _rv_apply(snapshot_id: str) -> dict[str, object]:
    return asdict(
        ApplyReport(
            outcome="ACTIVATED",
            snapshot_id=snapshot_id,
            physical_content_fingerprint="physical",
            company_rows_inserted=2435,
            peer_rows_inserted=9740,
            own_history_rows_inserted=2435,
            component_rows_inserted=7305,
            bulk_rows_deleted=0,
            snapshots_inserted=1,
            snapshots_deleted=0,
            pointer_changes=1,
            audit_rows_inserted=1,
            retained_snapshot_count=2,
        )
    )


def _accepted_result() -> dict[str, object]:
    return {
        "provider_staging_replay": {"logical_changes": 0},
        "structural_contract": {
            "contract_version": ACCEPTED["structural_contract"],
            "event_count": 5,
            "quarter_regime_count": 197,
            "ttm_regime_count": 197,
            "economic_event_fingerprint": ACCEPTED["event_fingerprint"],
            "regime_fingerprint": ACCEPTED["structural_regime_fingerprint"],
        },
        "structural_package_fingerprint": ACCEPTED["structural_package_fingerprint"],
        "package": {
            "second_physical_no_change": True,
            "first_apply": {
                "outcome": "APPLIED",
                "economic_result_fingerprint": ACCEPTED["package_economic_result_fingerprint"],
                "physical_content_fingerprint": ACCEPTED["package_physical_content_fingerprint"],
                "rows": {"diagnostic_endpoint": 87525, "diagnostic_evaluation": 700200},
            },
            "second_apply": {
                "outcome": "NO_CHANGE",
                "logical_changes": 0,
            }
        },
        "dependencies": {"status": "COMPATIBLE"},
        "relative_valuation": {
            "snapshot": {"result_fingerprint": ACCEPTED["rv_result_fingerprint"]},
            "first_apply": _rv_apply(ACCEPTED["rv_snapshot"]),
            "second_apply": {**_rv_apply(ACCEPTED["rv_snapshot"]), "outcome": "NO_CHANGE"},
            "second_logical_zero_writes": True,
            "second_physical_no_change": True,
            "source_metadata": {"structural_break": {"fingerprint": ACCEPTED["structural_source_fingerprint"]}},
        },
        "post_refresh_compatibility": {"state": "COMPATIBLE"},
        "areb": {"post_delisting_relative_valuation_rows": 0},
    }


def test_acceptance_checker_uses_apply_report_snapshot_id() -> None:
    result = _accepted_result()
    result["relative_valuation"]["snapshot"]["snapshot_id"] = "stale-or-wrong-location"

    assert _acceptance_blockers(result) == []
    assert _acceptance_view(result)["rv_snapshot_id"] == ACCEPTED["rv_snapshot"]


def test_acceptance_checker_distinguishes_structural_source_and_regime_fingerprints() -> None:
    result = _accepted_result()
    result["structural_contract"]["regime_fingerprint"] = ACCEPTED["structural_source_fingerprint"]

    assert "STRUCTURAL_REGIME_FINGERPRINT" in _acceptance_blockers(result)


def test_acceptance_contract_artifact_enumerates_required_fields() -> None:
    rows = acceptance_contract_artifact()
    ids = {row["stable_check_identifier"] for row in rows}

    assert "STRUCTURAL_SOURCE_FINGERPRINT" in ids
    assert "STRUCTURAL_REGIME_FINGERPRINT" in ids
    assert "RV_SNAPSHOT_ID" in ids
    assert all(row["failure_reason"] for row in rows)


def test_acceptance_contract_uses_phase13f4_5_fixed_point_structural_source() -> None:
    assert (
        ACCEPTED["structural_source_fingerprint"]
        == "c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6"
    )
    assert (
        ACCEPTED["structural_source_fingerprint"]
        != "04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f"
    )


def test_acceptance_checker_fails_closed_when_rv_snapshot_identity_missing() -> None:
    result = _accepted_result()
    result["relative_valuation"]["first_apply"].pop("snapshot_id")

    assert "RV_SNAPSHOT_ID_MISSING" in _acceptance_blockers(result)


def test_acceptance_checker_fails_closed_when_rv_result_missing() -> None:
    result = _accepted_result()
    result["relative_valuation"]["snapshot"].pop("result_fingerprint")

    assert "RV_RESULT_FINGERPRINT_MISSING" in _acceptance_blockers(result)


def _set_path(result: dict[str, object], path: tuple[str, ...], value: object) -> None:
    current = result
    for part in path[:-1]:
        current = current[part]  # type: ignore[index,assignment]
    current[path[-1]] = value  # type: ignore[index]


def _pop_path(result: dict[str, object], path: tuple[str, ...]) -> None:
    current = result
    for part in path[:-1]:
        current = current[part]  # type: ignore[index,assignment]
    current.pop(path[-1])  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("relative_valuation", "source_metadata", "structural_break", "fingerprint"), ACCEPTED["structural_regime_fingerprint"], "STRUCTURAL_SOURCE_FINGERPRINT"),
        (("structural_contract", "regime_fingerprint"), ACCEPTED["structural_source_fingerprint"], "STRUCTURAL_REGIME_FINGERPRINT"),
        (("relative_valuation", "first_apply", "snapshot_id"), "wrong", "RV_SNAPSHOT_ID"),
        (("relative_valuation", "snapshot", "result_fingerprint"), "wrong", "RV_RESULT_FINGERPRINT"),
        (("package", "first_apply", "economic_result_fingerprint"), "stale", "PACKAGE_ECONOMIC_FINGERPRINT"),
        (("package", "first_apply", "physical_content_fingerprint"), "stale", "PACKAGE_PHYSICAL_FINGERPRINT"),
        (("dependencies", "status"), "DEPENDENCY_MISMATCH", "DEPENDENCY_ATTACHMENT_STATUS"),
        (("post_refresh_compatibility", "state"), "INCOMPATIBLE", "POST_REFRESH_COMPATIBILITY"),
        (("areb", "post_delisting_relative_valuation_rows"), 1, "AREB_POST_DELISTING_RV_ROWS"),
        (("package", "second_apply", "logical_changes"), 1, "PACKAGE_SECOND_LOGICAL_CHANGES"),
        (("relative_valuation", "second_logical_zero_writes"), False, "RV_SECOND_LOGICAL_ZERO_WRITES"),
    ],
)
def test_acceptance_checker_negative_matrix(path: tuple[str, ...], value: object, reason: str) -> None:
    result = deepcopy(_accepted_result())
    _set_path(result, path, value)

    assert reason in _acceptance_blockers(result)


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (("relative_valuation", "source_metadata", "structural_break", "fingerprint"), "STRUCTURAL_SOURCE_FINGERPRINT_MISSING"),
        (("structural_contract", "regime_fingerprint"), "STRUCTURAL_REGIME_FINGERPRINT_MISSING"),
        (("relative_valuation", "first_apply", "snapshot_id"), "RV_SNAPSHOT_ID_MISSING"),
        (("relative_valuation", "snapshot", "result_fingerprint"), "RV_RESULT_FINGERPRINT_MISSING"),
        (("package", "first_apply", "economic_result_fingerprint"), "PACKAGE_ECONOMIC_FINGERPRINT_MISSING"),
        (("dependencies", "status"), "DEPENDENCY_ATTACHMENT_STATUS_MISSING"),
    ],
)
def test_acceptance_checker_missing_required_field_matrix(path: tuple[str, ...], reason: str) -> None:
    result = deepcopy(_accepted_result())
    _pop_path(result, path)

    assert _acceptance_blockers(result) == [reason]


def test_acceptance_checker_rejects_malformed_result_object() -> None:
    assert _acceptance_blockers({"relative_valuation": {}})[0].startswith("ACCEPTANCE_VIEW_INCOMPLETE:")


def test_runner_accepts_phase_specific_outcome_labels(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("rawcandle.fundamentals.phase13f4_2_production._preflight", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr("rawcandle.fundamentals.phase13f4_2_production.archive_reconciliation", lambda: {"ok": True})

    result = run_phase13f4_2(
        tmp_path / "out",
        apply=False,
        outcome_b="OUTCOME B - CUSTOM",
    )

    assert result["outcome"] == "OUTCOME B - CUSTOM"
