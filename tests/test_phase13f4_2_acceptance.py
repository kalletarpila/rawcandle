from __future__ import annotations

from dataclasses import asdict

from rawcandle.fundamentals.phase13f4_2_production import ACCEPTED, _acceptance_blockers
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
            "event_count": 5,
            "quarter_regime_count": 197,
            "ttm_regime_count": 197,
            "economic_event_fingerprint": ACCEPTED["event_fingerprint"],
            "regime_fingerprint": ACCEPTED["structural_regime_fingerprint"],
        },
        "structural_package_fingerprint": ACCEPTED["structural_package_fingerprint"],
        "package": {
            "first_apply": {
                "economic_result_fingerprint": ACCEPTED["package_economic_result_fingerprint"],
                "physical_content_fingerprint": ACCEPTED["package_physical_content_fingerprint"],
            }
        },
        "relative_valuation": {
            "snapshot": {"result_fingerprint": ACCEPTED["rv_result_fingerprint"]},
            "first_apply": _rv_apply(ACCEPTED["rv_snapshot"]),
        },
        "post_refresh_compatibility": {"state": "COMPATIBLE"},
        "areb": {"post_delisting_relative_valuation_rows": 0},
    }


def test_acceptance_checker_uses_apply_report_snapshot_id() -> None:
    result = _accepted_result()
    result["relative_valuation"]["snapshot"]["snapshot_id"] = "stale-or-wrong-location"

    assert _acceptance_blockers(result) == []


def test_acceptance_checker_distinguishes_structural_source_and_regime_fingerprints() -> None:
    result = _accepted_result()
    result["structural_contract"]["regime_fingerprint"] = ACCEPTED["structural_source_fingerprint"]

    assert "STRUCTURAL_REGIME_FINGERPRINT" in _acceptance_blockers(result)


def test_acceptance_checker_fails_closed_when_rv_snapshot_identity_missing() -> None:
    result = _accepted_result()
    result["relative_valuation"]["first_apply"].pop("snapshot_id")

    assert "RV_SNAPSHOT_ID_MISSING" in _acceptance_blockers(result)


def test_acceptance_checker_fails_closed_when_rv_result_missing() -> None:
    result = _accepted_result()
    result["relative_valuation"]["snapshot"].pop("result_fingerprint")

    assert "RV_RESULT_FINGERPRINT_MISSING" in _acceptance_blockers(result)
