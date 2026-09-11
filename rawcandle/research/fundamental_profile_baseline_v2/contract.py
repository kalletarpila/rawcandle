from __future__ import annotations

import hashlib
import json
from typing import Any


CONTRACT_VERSION = "PHASE12B2_TWELVE_MONTH_RETROSPECTIVE_BASELINE_V1"
RANDOM_SEED = 120122
BOOTSTRAP_REPETITIONS = 1000
PERMUTATION_REPETITIONS = 999
COMPONENTS = (
    "BALANCE_SHEET_RESILIENCE",
    "DILUTION",
    "FCF_MARGIN",
    "FUNDAMENTAL_TRAJECTORY",
    "OPERATING_MARGIN_DIRECTION",
    "OPERATING_PROFITABILITY",
    "REVENUE_GROWTH",
)


CONTRACT: dict[str, Any] = {
    "version": CONTRACT_VERSION,
    "parent_contract_fingerprint": "26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139",
    "phase12b1_commit": "fa8d27e9bb1d8b26e0ea79ea9bfe0bbac30b0310",
    "status": "REVISED_HISTORY_EXPLORATORY_ONLY",
    "input_identity": {
        "phase12d_commit": "25266922d326702ced76b74c65bbbe1b63246e83",
        "candidate": "candidate_a",
        "accepted_source_fingerprint": "402abff41586358b412f111fda297369b5a1011c5c28e4ffdb7fe308176d661a",
        "accepted_market_sha256": "38078094058004539dcb155df8b4172cb6822dc20c465c02cd7468710a1d1cdd",
        "market_append_note": "later market rows permitted only when pre-2026 label rows reconcile",
    },
    "periods": {
        "assignment_date": "entry_date",
        "development_start": "2021-01-01",
        "development_end_rule": "latest entry whose exact t+63 exit is strictly before 2023-07-03",
        "validation_calendar_window": ["2023-07-01", "2024-06-30"],
        "validation_first_entry_session": "2023-07-03",
        "validation_last_entry_session": "2024-06-28",
        "validation_last_exit_session": "2024-09-27",
        "confirmation_calendar_window": ["2024-10-01", "2025-09-30"],
        "confirmation_first_entry_session": "2024-10-01",
        "confirmation_last_entry_session": "2025-09-30",
        "confirmation_last_exit_session": "2025-12-30",
        "reserved_2026_first_session": "2026-01-02",
        "forward_report_only": ["2026-01-01", "2026-12-31"],
    },
    "boundary_policy": {
        "period_membership": "entry_date_in_calendar_window",
        "earlier_side_rule": "exit_session_index_strictly_less_than_next_period_first_entry_session_index",
        "equality": "purge_when_exit_session_index_greater_than_or_equal_to_next_period_first_entry_session_index",
        "following_period_embargo": None,
        "internal_development_year_boundaries": False,
        "fiscal_year_boundaries": False,
        "unique_signal_endpoint": True,
    },
    "label": {
        "horizon_sessions": 63,
        "entry": "first complete SPY session strictly after source availability date",
        "exit": "entry session index plus 63",
        "company_and_spy_same_sessions": True,
        "regression_target": "company_adjusted_simple_return_minus_SPY_adjusted_simple_return",
        "classification_target": "regression_target_strictly_greater_than_zero",
        "minimum_company_session_coverage": 0.90,
        "exact_exit_required": True,
    },
    "common_cohort": {
        "required": [
            "SCORE_FULL", "VALUATION_FULL", "DELTA_READY_TWO_QUARTER", "LIFECYCLE_READY",
            "all_primary_features_present", "eight_diagnostic_statuses_present",
            "resolved_identity", "mature_exact_h63_label", "supported_valuation_applicability",
        ],
        "imputation": None,
    },
    "hypotheses": {
        "H1": {"effect": "pooled_spearman_fundamental_score_vs_h63_excess", "direction": "POSITIVE"},
        "H2": {"effect": "pooled_spearman_valuation_score_vs_h63_excess", "direction": "POSITIVE"},
        "H3": {"effect": "mean_h63_excess_delta_2q_gt_0_minus_delta_2q_le_0", "direction": "POSITIVE"},
        "H4": {"effect": "mean_h63_excess_fundamental_ge_80_and_valuation_ge_60_minus_complement", "direction": "POSITIVE"},
        "H5": {"effect": "within_H4_mean_h63_excess_delta_2q_gt_0_minus_delta_2q_le_0", "direction": "POSITIVE"},
        "H6": {
            "status": "EXPLORATORY",
            "base_model": "OLS excess ~ standardized valuation + standardized delta + lifecycle main effects",
            "full_model": "base plus valuation:lifecycle and delta:lifecycle interactions",
            "lifecycle_encoding": "one_hot_MATURE_reference",
            "small_group_gate": "same arm gate excluding monthly median requirement",
            "omnibus_statistic": "partial_F_full_vs_base",
            "null": "all valuation and delta lifecycle interaction coefficients equal zero",
            "alternative": "two_sided_heterogeneity",
            "inference": "Freedman-Lane residual permutation in contiguous 63-SPY-session moving blocks",
            "effect_size": "partial_R_squared_and_lifecycle_specific_slopes",
        },
        "H7": {"effect": "pooled_spearman_active_eight_flag_count_vs_h63_excess", "direction": "NEGATIVE"},
        "H8": {
            "comparison": "B4_vs_B3",
            "primary_regression_metric": "spearman_difference",
            "minimum_regression_improvement": 0.02,
            "classification_metric": "Brier_B3_minus_Brier_B4",
            "minimum_classification_improvement": 0.002,
            "required_periods": ["VALIDATION", "CONFIRMATION"],
            "uncertainty": "paired_63_session_moving_block_bootstrap_lower_95_bound_above_zero_for_both_metrics",
            "decision": "both minimum improvements and both positive lower bounds in both required periods",
        },
    },
    "group_sample_gate": {
        "applies_to_each_arm_of": ["H3", "H4", "H5"],
        "minimum_observations": 100,
        "minimum_companies": 50,
        "minimum_calendar_months": 9,
        "minimum_unique_entry_sessions": 30,
        "minimum_median_observations_per_present_month": 3,
        "failure_status": "NOT_TESTABLE_SAMPLE_GATE_FAILED",
        "rationale": "minimum identifiability and broad temporal support under clustered market-time observations",
        "sensitivity_gates": [
            {"observations": 50, "companies": 30, "months": 6, "sessions": 20},
            {"observations": 200, "companies": 100, "months": 10, "sessions": 40},
        ],
    },
    "inference": {
        "bootstrap": "calendar_time_moving_blocks_over_global_SPY_session_index",
        "block_length_sessions": 63,
        "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
        "centered_null_p_value": True,
        "confidence_interval": "percentile_95",
        "company_rows_within_sampled_market_time_move_together": True,
        "random_seed": RANDOM_SEED,
        "concentration_checks": ["largest_company", "largest_sector", "largest_lifecycle", "one_percent_target_winsorization"],
        "missing_exit_stress": ["NEUTRAL_ZERO_EXCESS", "ADVERSE_MINUS_100_PERCENT_COMPANY_RETURN"],
    },
    "multiplicity": {
        "confirmatory_style_replay_family": {
            "members": ["H1", "H2", "H3", "H4", "H5", "H7"],
            "method": "Benjamini-Hochberg",
            "q_threshold": 0.10,
            "direction": "one_sided_predeclared",
            "sample_gate_failures": "excluded_from_test_count_and_have_null_p_q",
        },
        "H6_exploratory_family": {"members": ["H6"], "method": "single_two_sided_permutation_test", "alpha": 0.05},
        "H8_model_gate": {"members": ["H8"], "method": "compound_predeclared_effect_and_paired_interval_gate"},
        "component_family": {"members": list(COMPONENTS), "method": "Benjamini-Hochberg", "q_threshold": 0.10, "direction": "two_sided"},
    },
    "repeated_evidence": {
        "H1_H5_H7": "expected effect direction in development, validation, confirmation; validation and confirmation 95% intervals exclude zero; q<=0.10 in both; sample gates pass; missing-exit and concentration directions survive",
        "H6": "sample gates pass; validation and confirmation permutation p<0.05; partial_R2 positive; lifecycle-specific slopes reported; cannot alone authorize OUTCOME_A",
        "H8": "compound H8 decision passes in validation and confirmation",
    },
    "models": {
        "B0": ["development_mean", "development_positive_rate"],
        "B1": ["fundamental_score"],
        "B2": ["valuation_score"],
        "B3": ["fundamental_score", "valuation_score"],
        "B4": ["fundamental_score", "valuation_score", "two_quarter_delta", "fundamental_trajectory", "lifecycle_one_hot_MATURE_reference", "active_diagnostic_flag_count"],
        "fit_period": "DEVELOPMENT_ONLY",
        "continuous_estimator": "sklearn_LinearRegression_default_no_regularization",
        "classification_estimator": "sklearn_LogisticRegression_L2_C1_lbfgs_max_iter_1000",
        "scaling": "development_only",
        "later_refit": False,
        "hyperparameter_search": False,
    },
    "components": {
        "identities": list(COMPONENTS),
        "analysis": "raw_metric_when_structured_evidence_is_available_and_component_points_separately",
        "quantiles": "fixed within-development quintile cutpoints reused later; ties reported",
        "family": "component_family",
        "status": "DESCRIPTIVE_EXPLORATORY",
        "may_change_score_or_outcome": False,
        "B5": None,
    },
    "outcome_rules": {
        "A": "H8 passes and at least one of H1-H5 or H7 has repeated evidence",
        "B": "at least one repeatable association exists but A does not pass; H6 alone may produce B only as exploratory association",
        "C": "core study is testable but no hypothesis has repeated evidence",
        "D": "core windows, labels, overall common cohort, determinism, or implementation are not testable; an individual group gate failure alone does not force D",
    },
    "disclosures": [
        "provider history is revised and not original PIT",
        "operational universe has survivorship limitations",
        "contract was designed after original Phase12B results were observed",
        "historical taxonomy is not PIT",
        "delisting and terminal-return coverage is incomplete",
        "not production, causal, prospective, or investment evidence",
    ],
    "safety": {
        "production_writes": False, "provider_calls": False, "deployment": False,
        "scheduler_changes": False, "production_reports": False,
    },
}


def stable_fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


CONTRACT_FINGERPRINT = stable_fingerprint(CONTRACT)
