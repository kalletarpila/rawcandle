from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from . import delta, diagnostic_flags, lifecycle, relative_position, score, valuation
from .contract import SNAPSHOT_MODEL_VERSION, model_fingerprint


MODEL_VERSION = SNAPSHOT_MODEL_VERSION
TERMINOLOGY = {
    "OPERATING_PROFITABILITY": "Operating Profitability",
    "OPERATING_MARGIN_DIRECTION": "Operating Margin Direction",
    "OPERATING_MARGIN_TRAJECTORY": "Operating Margin Trajectory",
    "OPERATING_INCOME": "Operating Income",
    "OPERATING_MARGIN": "Operating Margin",
    "EV_OPERATING_INCOME": "EV / Operating Income",
    "OPERATING_INCOME_YIELD": "Operating Income Yield",
}
MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "terminology": TERMINOLOGY,
    "primary_operating_measure": "ttm_operating_income",
    "provider_ebit": "optional_diagnostic_only_explicitly_labelled_provider_ebit",
    "required_models": {
        "score": (score.MODEL_VERSION, score.MODEL_FINGERPRINT),
        "lifecycle": (lifecycle.MODEL_VERSION, lifecycle.MODEL_FINGERPRINT),
        "valuation": (valuation.MODEL_VERSION, valuation.MODEL_FINGERPRINT),
        "delta": (delta.MODEL_VERSION, delta.MODEL_FINGERPRINT),
        "relative_position": (relative_position.MODEL_VERSION, relative_position.MODEL_FINGERPRINT),
        "diagnostic_flags": (diagnostic_flags.MODEL_VERSION, diagnostic_flags.MODEL_FINGERPRINT),
    },
    "mixed_version_bundle": "REJECT",
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)


@dataclass(frozen=True)
class ModelIdentity:
    model_version: str
    model_fingerprint: str


def validate_model_bundle(bundle: Mapping[str, ModelIdentity]) -> None:
    expected = MODEL_CONTRACT["required_models"]
    if set(bundle) != set(expected):
        raise ValueError("OPERATING_INCOME_V2_SNAPSHOT_MODEL_BUNDLE_INCOMPLETE")
    for layer, identity in bundle.items():
        if (identity.model_version, identity.model_fingerprint) != tuple(expected[layer]):
            raise ValueError(f"OPERATING_INCOME_V2_SNAPSHOT_MODEL_MISMATCH:{layer}")
