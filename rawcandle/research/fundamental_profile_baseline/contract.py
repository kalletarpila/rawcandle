from __future__ import annotations

import hashlib
import json
from typing import Any


CONTRACT_VERSION = "PHASE12B_REVISED_HISTORY_FUNDAMENTAL_PROFILE_BASELINE_V1"
CONTRACT_LOCKED_AT_UTC = "2026-09-10T05:57:32Z"
RANDOM_SEED = 12012

CONTRACT: dict[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "locked_at_utc": CONTRACT_LOCKED_AT_UTC,
    "authoritative_specification": "PHASE 12B - LEAKAGE-CONTROLLED FUNDAMENTAL PROFILE BASELINE",
    "discarded_specifications": ["PHASE 12B - LEAKAGE-CONTROLLED FORWARD-RETURN BASELINE"],
    "research_status": {
        "classification": "REVISED_HISTORY_EXPLORATORY_ONLY",
        "pit_valid": False,
        "investable_backtest": False,
        "production_model": False,
        "technical_entry_system": False,
        "modifies_existing_scores": False,
        "snapshot_prediction_authorized": False,
        "optimization_against_2025_or_2026_authorized": False,
        "mandatory_disclosure": (
            "The feature history is currently revised and was reconstructed from a provider "
            "snapshot obtained in 2026. It is not original point-in-time history. Results "
            "describe retrospective associations and cannot establish real-time historical investability."
        ),
    },
    "periods": {
        "DEVELOPMENT": ["2021-01-01", "2023-12-31"],
        "TEMPORAL_VALIDATION": ["2024-01-01", "2024-12-31"],
        "RETROSPECTIVE_CONFIRMATION": ["2025-01-01", "2025-12-31"],
        "FORWARD_REPORT_ONLY": ["2026-01-01", "2026-12-31"],
        "assignment_date": "tradable_entry_date",
        "prospective_future_name": "PROSPECTIVE_FORWARD_VALIDATION",
    },
    "signal_and_labels": {
        "information_date": "stored_source_availability_date",
        "entry_session": "first_complete_SPY_session_strictly_after_information_date",
        "entry_session_number": 0,
        "company_entry_price": "validated_stored_adjusted_open_same_session",
        "benchmark_entry_price": "validated_stored_adjusted_SPY_open_same_session",
        "exit_session_offsets": [21, 42, 63],
        "company_exit_price": "validated_stored_adjusted_close_exact_offset_session",
        "benchmark_exit_price": "validated_stored_adjusted_SPY_close_same_session",
        "minimum_company_session_coverage": 0.90,
        "substitute_exit": False,
        "forward_fill": False,
        "primary_regression_target": "company_simple_price_return_63_minus_SPY_simple_price_return_63",
        "primary_classification_target": "excess_price_return_63_strictly_greater_than_zero",
        "secondary_horizons": [21, 42],
        "additional_evaluation": ["absolute_price_return", "positive_absolute", "positive_excess", "MFE", "MAE"],
        "return_name": "stored_adjusted_price_return_not_verified_total_return",
    },
    "primary_common_cohort": {
        "required": [
            "SCORE_FULL",
            "VALUATION_FULL",
            "DELTA_READY_TWO_QUARTER",
            "LIFECYCLE_READY",
            "fundamental_score_present",
            "valuation_score_present",
            "delta_2q_present",
            "trajectory_present",
            "confirmed_lifecycle_present",
            "diagnostic_statuses_present",
            "valid_primary_return_label",
            "supported_valuation_applicability",
            "resolved_identity",
        ],
        "imputation": None,
        "diagnostic_flag_count": "count_only_EVALUATED_FLAGGED_preserve_NOT_READY_and_NOT_APPLICABLE",
    },
    "primary_features": [
        "fundamental_score",
        "absolute_valuation_score",
        "fundamental_delta_2q",
        "fundamental_trajectory",
        "confirmed_lifecycle_categorical",
        "active_diagnostic_flag_count",
    ],
    "secondary_diagnostics": [
        "seven_fundamental_component_points_and_raw_metrics",
        "delta_qoq_yoy_and_component_deltas",
        "three_valuation_component_points_and_raw_yields",
        "eight_individual_diagnostic_decisions",
        "lifecycle_candidate_tenure_and_recent_transition",
        "positive_valuation_component_count",
        "existing_point_cap_indicators",
    ],
    "excluded_historical_predictors": [
        "current_relative_position",
        "current_relative_valuation",
        "own_history_relative_valuation",
        "current_peer_percentiles",
        "current_sector_or_industry_percentiles",
        "current_taxonomy_membership",
    ],
    "bands": {
        "fundamental_score": ["<40", "40-<60", "60-<80", "80-100"],
        "absolute_valuation_score": ["<20", "20-<40", "40-<60", "60-<80", "80-100"],
        "fundamental_delta_2q": ["<-10", "-10-<0", "0", ">0-10", ">10"],
        "fundamental_trajectory": ["<4", "4-<6", "6-<8", "8-10"],
        "diagnostic_flag_count": ["0", "1", "2+"],
        "lifecycle": "categorical_no_ordinal_encoding",
    },
    "transforms": {
        "continuous_centering_and_scaling": "DEVELOPMENT_ONLY",
        "bounded_score_winsorization": False,
        "unbounded_secondary_winsorization": False,
        "future_quantiles": False,
        "lifecycle_reference_category": "MATURE",
    },
    "hypotheses": {
        "H1": "higher_fundamental_score_higher_excess_63",
        "H2": "higher_absolute_valuation_score_higher_excess_63",
        "H3": "positive_delta_2q_higher_than_nonpositive",
        "H4": "fundamental_at_least_80_and_valuation_at_least_60_above_common_cohort",
        "H5": "H4_and_delta_2q_positive_above_H4_and_common_cohort",
        "H6": "valuation_and_delta_relationship_differs_by_confirmed_lifecycle",
        "H7": "higher_active_diagnostic_count_lower_excess_63",
        "H8": "fixed_combined_model_adds_stable_information_beyond_simple_models",
    },
    "descriptive_combinations": [
        "fundamental_band_x_valuation_band",
        "fundamental_band_x_delta_2q_band",
        "valuation_band_x_delta_2q_band",
        "lifecycle_x_valuation_band",
        "lifecycle_x_delta_2q_sign",
        "diagnostic_count_x_valuation_band",
        "H4_vs_common",
        "H5_vs_H4_and_common",
    ],
    "models": {
        "B0": ["development_mean", "development_positive_rate"],
        "B1": ["fundamental_score"],
        "B2": ["absolute_valuation_score"],
        "B3": ["fundamental_score", "absolute_valuation_score"],
        "B4": [
            "fundamental_score",
            "absolute_valuation_score",
            "fundamental_delta_2q",
            "fundamental_trajectory",
            "lifecycle_one_hot_reference_MATURE",
            "active_diagnostic_flag_count",
        ],
        "continuous_estimator": "sklearn_LinearRegression_default_no_regularization",
        "classification_estimator": "sklearn_LogisticRegression_L2_C1_lbfgs_max_iter_1000",
        "fit_period": "DEVELOPMENT_ONLY",
        "refit_later_periods": False,
        "hyperparameter_search": False,
    },
    "evaluation": {
        "continuous": [
            "spearman",
            "pearson",
            "predicted_quintile_mean_and_median",
            "top_minus_bottom_quintile_spread",
            "mae",
            "rmse",
            "sign_accuracy",
            "block_bootstrap_confidence_interval",
        ],
        "classification": [
            "base_rate",
            "roc_auc",
            "pr_auc",
            "brier_score",
            "log_loss",
            "fixed_probability_band_calibration",
            "calibration_intercept_and_slope_when_feasible",
            "block_bootstrap_confidence_interval",
        ],
        "ranking": [
            "monthly_spearman_ic",
            "mean_monthly_ic",
            "median_monthly_ic",
            "monthly_ic_standard_deviation",
            "information_ratio_with_dependence_warning",
            "fraction_positive_months",
        ],
        "probability_bands": ["[0,0.2)", "[0.2,0.4)", "[0.4,0.6)", "[0.6,0.8)", "[0.8,1.0]"],
        "primary_model_comparisons": ["B3_vs_B1", "B3_vs_B2", "B4_vs_B3"],
    },
    "missing_exit_sensitivity": {
        "complete_case": "observed_exact_exit_only",
        "neutral": "unresolved_missing_exit_excess_return_zero_bound_only",
        "severe": "unresolved_missing_exit_company_return_minus_one_less_synchronized_SPY_return_bound_only",
        "stress_labels_enter_model_fit": False,
        "verified_terminal_treatment": "only_if_repository_evidence_supports_exact_terminal_return",
    },
    "dependence_controls": {
        "purge": "remove_period_rows_whose_63_session_exit_is_after_period_end",
        "embargo": "remove_first_63_SPY_sessions_of_each_post_development_period",
        "bootstrap": "calendar_time_moving_block_bootstrap_63_sessions",
        "bootstrap_repetitions": 1000,
        "company_cluster_sensitivity": True,
        "random_seed": RANDOM_SEED,
        "iid_bootstrap_authoritative": False,
    },
    "sample_gates": {
        "minimum_labelled_observations": 200,
        "minimum_distinct_companies": 100,
        "minimum_distinct_signal_months": 12,
        "monthly_ic_minimum_observations": 20,
        "quintiles": 5,
        "tie_break": "stable_prediction_then_company_id_then_quarter_id_no_randomness",
    },
    "evidence_classes": {
        "REPEATED_EXPLORATORY_EVIDENCE": "expected_direction_in_development_2024_and_2025_sample_gates_pass_no_material_concentration_and_stress_direction_survives",
        "WEAK_OR_UNCERTAIN_EVIDENCE": "expected_direction_broadly_present_but_interval_includes_zero_or_effect_small_or_stability_incomplete",
        "NO_REPEATED_EVIDENCE": "validation_confirmation_disagree_or_effect_only_development_or_no_incremental_value_or_undersized_or_concentrated",
        "NOT_TESTABLE_WITH_CURRENT_DATA": "label_identity_survivorship_timing_or_revised_history_prevents_responsible_test",
    },
    "multiple_testing": "Benjamini_Hochberg_across_H1_to_H8",
    "decision_outcomes": {
        "A": "stable_baseline_signal_supports_locked_ML_candidate_phase",
        "B": "tentative_association_prospective_collection_before_ML",
        "C": "no_reliable_baseline_signal_do_not_proceed_to_ML",
        "D": "blocked_by_reconciliation_or_implementation_failure",
    },
    "safety": {
        "network_calls": False,
        "production_database_writes": False,
        "production_schema": False,
        "production_model_persistence": False,
        "snapshot_or_scheduler_integration": False,
        "source_open_mode": "SQLite_mode_ro_query_only_WAL_aware",
    },
}


def contract_fingerprint(contract: dict[str, Any] = CONTRACT) -> str:
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


CONTRACT_FINGERPRINT = contract_fingerprint()
