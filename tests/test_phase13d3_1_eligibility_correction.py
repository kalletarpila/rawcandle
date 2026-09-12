from __future__ import annotations

from rawcandle.fundamentals.phase13d3_1_eligibility_correction import (
    areb_corrected_decision,
    local_candidate_audit,
    retired_v3_audit,
    sndk_readiness_decision,
)


def test_phase13d3_1_areb_is_rejected_for_delisted_status_before_classification() -> None:
    decision = areb_corrected_decision()

    assert decision["identity_status"] == "RESOLVED"
    assert decision["listing_status"] == "DELISTED"
    assert decision["operational_universe_status"] == "NOT_ELIGIBLE"
    assert decision["operational_universe_reason"] == "DELISTED_SECURITY"
    assert decision["classification_status"] == "SOURCE_CLASSIFICATION_MISMATCH"
    assert decision["datacenter_taxonomy_status"] == "NOT_MEMBER_BY_DESIGN"
    assert decision["supersedes_phase13d3_primary_status"] == "CLASSIFICATION_MISMATCH_REVIEW_REQUIRED"


def test_phase13d3_1_local_candidates_remain_visible_but_delisted_are_not_eligible() -> None:
    audit = local_candidate_audit()

    assert audit["eligible_replacement_exists"] is False
    assert audit["eligible_replacement_ticker"] is None
    assert audit["all_rejection_reasons"]["AREB"][0] == "DELISTED_SECURITY"
    assert all("DELISTED_SECURITY" in reasons for reasons in audit["all_rejection_reasons"].values())


def test_phase13d3_1_sndk_readiness_is_independent_of_areb() -> None:
    readiness = sndk_readiness_decision()

    assert readiness["identity_status"] == "RESOLVED_DISTINCT_SECURITY_WITH_CORPORATE_LINEAGE"
    assert readiness["do_not_merge_with"] == "SNDK1/permaticker 197210"
    assert readiness["archive"]["expected_sha256"] == "dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36"
    assert readiness["checks"]["network_api_dependency"] is False
    assert readiness["checks"]["no_network_api_dependency"] is True
    assert readiness["checks"]["identity_and_sndk1_separation"] is True


def test_phase13d3_1_retired_v3_boundary_has_no_active_runtime_dependency() -> None:
    audit = retired_v3_audit()

    assert audit["retired_v3_count"] == 14
    assert audit["fixture_restored"] is False
    assert audit["active_runtime_dependency"] is False
    assert all("test_fundamentals_v4_identity_calendar_bootstrap.py" in node for node in audit["retired_v3_tests"])
