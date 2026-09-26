"""Shared validity rules for the canonical ARQ observation authority."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence


class PublicationDateAuthorityError(RuntimeError):
    pass


def valid_publication_authority(
    source_date: Any,
    period_end: Any,
) -> bool:
    try:
        parsed_source = date.fromisoformat(str(source_date))
        parsed_period_end = date.fromisoformat(str(period_end))
    except (TypeError, ValueError):
        return False
    return parsed_source >= parsed_period_end


def select_valid_publication_winner(
    ordered_candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Select the whole canonical observation, preserving valid-row precedence.

    Canonical financial values, provenance, and publication metadata intentionally
    remain bound to one provider observation. An invalid publication date therefore
    disqualifies the observation as a whole instead of creating split authority.
    """
    for candidate in ordered_candidates:
        if valid_publication_authority(candidate.get("date"), candidate.get("reportperiod")):
            return candidate
    raise PublicationDateAuthorityError(
        "CANONICAL_PUBLICATION_DATE_AUTHORITY_REPAIR_REQUIRED"
    )


def classify_first_public_bootstrap(
    *, first_public_result_date: Any, source_availability_date: Any,
    period_end: Any, accepted_winner_date: Any,
) -> dict[str, Any]:
    if first_public_result_date:
        try:
            date.fromisoformat(str(first_public_result_date))
        except (TypeError, ValueError):
            return {"status": "REPAIR_REQUIRED", "reason": "INVALID_EXISTING_FIRST_PUBLIC_RESULT_DATE"}
        return {"status": "ALREADY_ESTABLISHED", "proposed_date": None}
    if not valid_publication_authority(source_availability_date, period_end):
        return {"status": "REPAIR_REQUIRED", "reason": "AVAILABILITY_BEFORE_PERIOD_END"}
    try:
        parsed_winner = date.fromisoformat(str(accepted_winner_date))
    except (TypeError, ValueError):
        return {"status": "REPAIR_REQUIRED", "reason": "VALID_ARQ_WINNER_DATE_MISSING"}
    parsed_availability = date.fromisoformat(str(source_availability_date))
    if parsed_winner != parsed_availability:
        return {"status": "REPAIR_REQUIRED", "reason": "AVAILABILITY_DOES_NOT_MATCH_CURRENT_WINNER_DATE"}
    return {"status": "BOOTSTRAP_ELIGIBLE", "proposed_date": parsed_availability.isoformat()}
