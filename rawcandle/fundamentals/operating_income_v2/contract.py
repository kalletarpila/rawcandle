from __future__ import annotations

import hashlib
import json
from typing import Any


FAMILY_VERSION = "OPERATING_INCOME_MODEL_FAMILY_V2"
TTM_MODEL_VERSION = "V4_TTM_OPERATING_INCOME_V2"
SCORE_MODEL_VERSION = "SIMPLE_FUNDAMENTAL_SCORE_V2"
LIFECYCLE_MODEL_VERSION = "V4_FUNDAMENTAL_LIFECYCLE_V2"
VALUATION_MODEL_VERSION = "ABSOLUTE_VALUATION_SCORE_V2"
DELTA_MODEL_VERSION = "CURRENTLY_REVISED_FUNDAMENTAL_DELTA_V2"
RELATIVE_MODEL_VERSION = "CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V2"
DIAGNOSTIC_MODEL_VERSION = "CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V2"
SNAPSHOT_MODEL_VERSION = "CURRENT_REVISED_COMPANY_SNAPSHOT_V2"

COMPONENTS = (
    "REVENUE_GROWTH",
    "OPERATING_PROFITABILITY",
    "OPERATING_MARGIN_DIRECTION",
    "FCF_MARGIN",
    "BALANCE_SHEET_RESILIENCE",
    "DILUTION",
    "FUNDAMENTAL_TRAJECTORY",
)

OPERATING_MARGIN_ANCHORS = ((0.0, 0.0), (0.10, 7.5), (0.25, 15.0))
OPERATING_DIRECTION_ANCHORS = ((-0.05, 0.0), (0.0, 7.5), (0.05, 15.0))
LEVERAGE_ANCHORS = ((0.0, 15.0), (1.0, 12.0), (2.0, 8.0), (3.0, 4.0), (4.0, 0.0))
OPERATING_YIELD_ANCHORS = (
    (0.0, 0.0), (0.02, 6.0), (0.04, 14.0),
    (0.06, 22.0), (0.09, 31.0), (0.15, 40.0),
)
TRAJECTORY_TOLERANCE = 0.05


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


FAMILY_CONTRACT = {
    "family_version": FAMILY_VERSION,
    "lineage": "Sharadar opinc -> canonical operating_income -> four exact consecutive quarters -> ttm_operating_income",
    "fallback": None,
    "imputation": None,
    "mixed_version_results": "REJECT",
    "models": {
        "ttm": TTM_MODEL_VERSION,
        "score": SCORE_MODEL_VERSION,
        "lifecycle": LIFECYCLE_MODEL_VERSION,
        "valuation": VALUATION_MODEL_VERSION,
        "delta": DELTA_MODEL_VERSION,
        "relative_position": RELATIVE_MODEL_VERSION,
        "diagnostic_flags": DIAGNOSTIC_MODEL_VERSION,
        "snapshot": SNAPSHOT_MODEL_VERSION,
    },
}
FAMILY_FINGERPRINT = fingerprint(FAMILY_CONTRACT)


def model_fingerprint(name: str, contract: dict[str, Any]) -> str:
    return fingerprint({
        "family_version": FAMILY_VERSION,
        "family_fingerprint": FAMILY_FINGERPRINT,
        "model_version": name,
        "contract": contract,
    })
