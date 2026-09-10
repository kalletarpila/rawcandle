from __future__ import annotations

import hashlib
import json
from typing import Any


CONTRACT_VERSION = "HISTORICAL_RESEARCH_UNIVERSE_CANDIDATE_V1"
MODEL_DATA_RISK = "HIGH - CURRENTLY_REVISED_NON_PIT_HISTORY"
HORIZONS = (30, 60, 120, 180)

CONTRACT: dict[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "status": "PROPOSED_NOT_IMPLEMENTED",
    "model_data_risk": MODEL_DATA_RISK,
    "purpose": "screening_candidates_for_further_analysis_not_buy_sell_model",
    "universe": {
        "source": "all_global_ARQ_logical_endpoints_in_verified_Phase12C_snapshot",
        "operational_universe_separate": True,
        "include_inactive_acquired_failed_and_delisted_common_equity": True,
        "current_snapshot_readers_unchanged": True,
    },
    "history": {
        "semantics": "currently_revised_not_original_point_in_time",
        "revisions": "retain_revision_aware_source_identity_select_latest_only_for_candidate_endpoint_view",
        "availability_date": "provider_date_required_no_period_end_fallback",
    },
    "identity": {
        "issuer_key_precedence": [
            "Sharadar_permaticker_with_dated_metadata_range",
            "CIK_with_dated_listing_evidence",
            "dated_canonical_alias",
            "exact_ticker_and_market_with_nonconflicting_date_overlap_candidate_only",
            "unresolved",
        ],
        "company_name_only_mapping": False,
        "future_alias_use": False,
        "ticker_only_is_permanent_identity": False,
        "episode_model": "one_ticker_may_have_multiple_dated_security_issuer_episodes",
    },
    "eligibility": {
        "separate_states": [
            "RESEARCH_SECURITY_ELIGIBLE",
            "FUNDAMENTAL_MODEL_APPLICABLE",
            "RETURN_LABEL_ELIGIBLE",
        ],
        "security_category_evidence": "Sharadar_fundamentals_ticker_metadata_category",
        "do_not_exclude_for_inactive_or_delisted_status": True,
        "specialized_accounting_requires_dated_classification": True,
    },
    "event_and_labels": {
        "event_center_t": "first_complete_SPY_session_strictly_after_provider_availability_date",
        "event_price": "mean_valid_split_adjusted_closes_t_minus_2_through_t_plus_2",
        "observable_after": "t_plus_2_close",
        "exit_offsets_from_observable_session": list(HORIZONS),
        "exact_exit_required": True,
        "minimum_company_session_coverage": 0.90,
        "benchmarks": ["SPY", "QQQ"],
        "adjustment": "stored_prices_treated_as_split_adjusted",
        "dividends": "excluded",
        "return_semantics": "simple_price_return_not_total_return",
    },
    "terminal_policy": {
        "authoritative_exact_exit": "use_exact_exit",
        "authoritative_cash_or_stock_consideration": "separately_sourced_terminal_return",
        "unknown_terminal_value": "explicit_right_censoring",
        "temporary_gap": "missing_exact_exit_not_last_price_carry_forward",
        "automatic_zero_return": False,
        "automatic_last_price_carry_forward": False,
        "sensitivity_bounds": ["complete_case", "neutral_zero_bound", "severe_minus_one_bound"],
    },
    "reproducibility": {
        "source_zip_sha256": "dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36",
        "deterministic_sorting": True,
        "production_writes": False,
        "network": False,
    },
}


def contract_fingerprint(contract: dict[str, Any] = CONTRACT) -> str:
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


CONTRACT_FINGERPRINT = contract_fingerprint()
