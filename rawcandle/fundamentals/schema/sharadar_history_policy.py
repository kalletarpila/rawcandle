from __future__ import annotations

import hashlib
import json
from typing import Any


POLICY_VERSION = "SHARADAR_FUNDAMENTALS_HISTORY_POLICY_V1"
MINIMUM_HISTORY_YEARS = 10
RETENTION_MODE = "APPEND_ONLY_NO_WINDOW_PRUNING"
REQUESTED_DIMENSIONS = ("ARQ", "MRQ")
TARGET_UNIVERSE_SCOPE = "BOOTSTRAP_CSV_EXACT_CURRENT_TICKER"

_POLICY_CONTRACT = {
    "policy_version": POLICY_VERSION,
    "minimum_history_years": MINIMUM_HISTORY_YEARS,
    "retention_mode": RETENTION_MODE,
    "observations_older_than_minimum_may_remain": True,
    "absence_from_later_snapshot_authorizes_deletion": False,
    "minimum_history_is_cleanup_cutoff": False,
    "requested_dimensions": list(REQUESTED_DIMENSIONS),
    "target_universe_scope": TARGET_UNIVERSE_SCOPE,
    "unrelated_provider_datasets_unchanged": True,
}
POLICY_FINGERPRINT = hashlib.sha256(
    json.dumps(_POLICY_CONTRACT, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()


def enforce_production_history_years(years: int | None = None) -> int:
    requested = MINIMUM_HISTORY_YEARS if years is None else years
    if isinstance(requested, bool) or not isinstance(requested, int):
        raise ValueError("Sharadar production fundamentals history years must be an integer")
    if requested < MINIMUM_HISTORY_YEARS:
        raise ValueError(
            f"Sharadar production fundamentals requires at least {MINIMUM_HISTORY_YEARS} years; "
            f"requested {requested}"
        )
    return requested


def history_policy_metadata(years: int | None = None) -> dict[str, Any]:
    requested = enforce_production_history_years(years)
    return {
        **_POLICY_CONTRACT,
        "policy_fingerprint": POLICY_FINGERPRINT,
        "requested_history_years": requested,
        "upstream_request_scope": f"GET /data/fundamentals?years={requested}",
    }
