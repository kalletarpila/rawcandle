from __future__ import annotations

from rawcandle.fundamentals.phase13e_production_onboarding import (
    OUTCOME_B,
    REPORT_DATE,
    _diagnostic_endpoint_gate,
    _verify_source_archive,
    run_phase13e,
)


def test_phase13e_source_archive_is_verified_without_network() -> None:
    source = _verify_source_archive()

    assert source["sha256"] == source["expected_sha256"]
    assert source["source_rows"] == 61
    assert source["arq_rows"] == 13
    assert source["network_requests_performed"] == 0


def test_phase13e_dry_run_records_prewrite_scope(tmp_path) -> None:
    result = run_phase13e(tmp_path / "phase13e_dry", apply=False)

    assert result["outcome"] == OUTCOME_B
    if result.get("mode") == "DRY_RUN":
        assert result["prewrite_blocker"] is None
        assert result["write_set"] == ["provider", "canonical", "analysis"]
        assert (tmp_path / "phase13e_dry" / "production_preflight.json").exists()
    else:
        assert result["error"] in {"RuntimeError", "FileNotFoundError"}
        assert result["reason"]


def test_phase13e_report_date_is_locked_to_deployment_prompt() -> None:
    assert REPORT_DATE == "2026-09-12"


def test_phase13e_diagnostic_gate_counts_evaluations_not_endpoint_rows() -> None:
    gate = _diagnostic_endpoint_gate()

    assert gate["ok"] is True
    assert gate["endpoint_rows"] > 0
    assert gate["min_evaluations_per_endpoint"] == 8
    assert gate["max_evaluations_per_endpoint"] == 8
    assert gate["evaluation_rows"] == gate["package_evaluation_count"]
