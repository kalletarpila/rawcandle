from rawcandle.research.fundamental_profile_baseline.contract import (
    CONTRACT,
    CONTRACT_FINGERPRINT,
    CONTRACT_VERSION,
    contract_fingerprint,
)


def test_contract_is_stable_and_revised_history_only() -> None:
    assert contract_fingerprint() == CONTRACT_FINGERPRINT
    assert len(CONTRACT_FINGERPRINT) == 64
    assert CONTRACT["contract_version"] == CONTRACT_VERSION
    assert CONTRACT["research_status"]["classification"] == "REVISED_HISTORY_EXPLORATORY_ONLY"
    assert CONTRACT["research_status"]["pit_valid"] is False
    assert CONTRACT["research_status"]["production_model"] is False


def test_contract_contains_only_authoritative_second_prompt_semantics() -> None:
    assert CONTRACT["authoritative_specification"] == "PHASE 12B - LEAKAGE-CONTROLLED FUNDAMENTAL PROFILE BASELINE"
    assert CONTRACT["discarded_specifications"] == ["PHASE 12B - LEAKAGE-CONTROLLED FORWARD-RETURN BASELINE"]
    assert CONTRACT["hypotheses"]["H5"] == "H4_and_delta_2q_positive_above_H4_and_common_cohort"
    assert CONTRACT["bands"]["fundamental_delta_2q"] == ["<-10", "-10-<0", "0", ">0-10", ">10"]


def test_contract_locks_metrics_stress_and_no_stress_fit() -> None:
    assert CONTRACT["evaluation"]["probability_bands"] == [
        "[0,0.2)", "[0.2,0.4)", "[0.4,0.6)", "[0.6,0.8)", "[0.8,1.0]"
    ]
    assert CONTRACT["missing_exit_sensitivity"]["stress_labels_enter_model_fit"] is False
    assert set(CONTRACT["evidence_classes"]) == {
        "REPEATED_EXPLORATORY_EVIDENCE",
        "WEAK_OR_UNCERTAIN_EVIDENCE",
        "NO_REPEATED_EVIDENCE",
        "NOT_TESTABLE_WITH_CURRENT_DATA",
    }


def test_contract_locks_temporal_and_session_semantics() -> None:
    assert CONTRACT["periods"]["RETROSPECTIVE_CONFIRMATION"] == ["2025-01-01", "2025-12-31"]
    assert CONTRACT["signal_and_labels"]["entry_session_number"] == 0
    assert CONTRACT["signal_and_labels"]["exit_session_offsets"] == [21, 42, 63]
    assert CONTRACT["models"]["fit_period"] == "DEVELOPMENT_ONLY"
    assert CONTRACT["dependence_controls"]["bootstrap_repetitions"] == 1000
