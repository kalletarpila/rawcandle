from __future__ import annotations

from . import delta, diagnostic_flags_eight, lifecycle, relative_position, score, valuation
from .contract import model_fingerprint


MODEL_VERSION = "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_EIGHT_FLAG_V1"
MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "primary_operating_measure": "ttm_operating_income",
    "provider_ebit": "diagnostic_only_explicitly_labelled_provider_ebit",
    "required_models": {
        "score": (score.MODEL_VERSION, score.MODEL_FINGERPRINT),
        "lifecycle": (lifecycle.MODEL_VERSION, lifecycle.MODEL_FINGERPRINT),
        "valuation": (valuation.MODEL_VERSION, valuation.MODEL_FINGERPRINT),
        "delta": (delta.MODEL_VERSION, delta.MODEL_FINGERPRINT),
        "relative_position": (relative_position.MODEL_VERSION, relative_position.MODEL_FINGERPRINT),
        "diagnostic_flags": (diagnostic_flags_eight.MODEL_VERSION, diagnostic_flags_eight.MODEL_FINGERPRINT),
    },
    "diagnostic_count": 8,
    "mixed_version_bundle": "REJECT",
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)
