from rawcandle.research.fundamental_profile_baseline_v2.contract import (
    COMPONENTS,
    CONTRACT,
    CONTRACT_FINGERPRINT,
    stable_fingerprint,
)


def test_contract_fingerprint_is_deterministic_and_separate_from_v1():
    assert CONTRACT_FINGERPRINT == stable_fingerprint(CONTRACT)
    assert CONTRACT_FINGERPRINT != CONTRACT["parent_contract_fingerprint"]


def test_windows_are_exact_twelve_month_calendar_ranges():
    periods = CONTRACT["periods"]
    assert periods["validation_calendar_window"] == ["2023-07-01", "2024-06-30"]
    assert periods["confirmation_calendar_window"] == ["2024-10-01", "2025-09-30"]
    assert periods["validation_last_exit_session"] < periods["confirmation_first_entry_session"]
    assert periods["confirmation_last_exit_session"] < periods["reserved_2026_first_session"]


def test_boundary_policy_is_one_sided_and_equality_is_purged():
    policy = CONTRACT["boundary_policy"]
    assert policy["following_period_embargo"] is None
    assert "greater_than_or_equal" in policy["equality"]
    assert not policy["internal_development_year_boundaries"]
    assert not policy["fiscal_year_boundaries"]


def test_h5_comparator_is_within_h4():
    assert CONTRACT["hypotheses"]["H5"]["effect"] == "within_H4_mean_h63_excess_delta_2q_gt_0_minus_delta_2q_le_0"


def test_arm_gates_are_explicit_and_failure_is_not_no_effect():
    gate = CONTRACT["group_sample_gate"]
    assert gate["applies_to_each_arm_of"] == ["H3", "H4", "H5"]
    assert gate["minimum_observations"] == 100
    assert gate["failure_status"] == "NOT_TESTABLE_SAMPLE_GATE_FAILED"


def test_h6_is_two_sided_block_aware_interaction_test():
    h6 = CONTRACT["hypotheses"]["H6"]
    assert h6["omnibus_statistic"] == "partial_F_full_vs_base"
    assert h6["alternative"] == "two_sided_heterogeneity"
    assert "Freedman-Lane" in h6["inference"]


def test_multiplicity_families_are_coherent():
    families = CONTRACT["multiplicity"]
    assert families["confirmatory_style_replay_family"]["members"] == ["H1", "H2", "H3", "H4", "H5", "H7"]
    assert families["H6_exploratory_family"]["members"] == ["H6"]
    assert families["H8_model_gate"]["members"] == ["H8"]
    assert families["component_family"]["members"] == list(COMPONENTS)


def test_h8_requires_material_regression_and_classification_improvement():
    h8 = CONTRACT["hypotheses"]["H8"]
    assert h8["minimum_regression_improvement"] == 0.02
    assert h8["minimum_classification_improvement"] == 0.002
    assert h8["required_periods"] == ["VALIDATION", "CONFIRMATION"]


def test_components_are_authoritative_persisted_identities():
    assert COMPONENTS == (
        "BALANCE_SHEET_RESILIENCE", "DILUTION", "FCF_MARGIN",
        "FUNDAMENTAL_TRAJECTORY", "OPERATING_MARGIN_DIRECTION",
        "OPERATING_PROFITABILITY", "REVENUE_GROWTH",
    )


def test_models_fit_development_only_without_later_refit():
    models = CONTRACT["models"]
    assert models["fit_period"] == "DEVELOPMENT_ONLY"
    assert models["later_refit"] is False
    assert models["hyperparameter_search"] is False

