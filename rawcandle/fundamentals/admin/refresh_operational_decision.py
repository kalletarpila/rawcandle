"""Operational presentation of authoritative refresh authorization, not a gate."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def refresh_operational_decision(
    *, safe_effective_changes: int | None, held_items: Sequence[Mapping[str, Any]],
    global_blockers: Sequence[Mapping[str, Any]], future_test_authorized: bool,
    test_reason_code: str, stage: str = "Preview",
    production_state: str | None = None, production_reason_code: str | None = None,
    technical_failure: str | None = None, completed: bool = False,
) -> dict[str, Any]:
    held = [dict(item) for item in held_items]
    blockers = [dict(item) for item in global_blockers]
    hold_text = (
        " " + ", ".join(str(item.get("ticker") or "Unknown ticker") for item in held)
        + " remains quarantined for operator review. The hold did not block any safe peer changes."
        if held else ""
    )
    if technical_failure:
        code, text = "TECHNICAL_FAILURE", technical_failure
        action, action_text = "REVIEW_TECHNICAL_FAILURE", "Review the technical diagnostics and correct the cause before retrying the workflow."
        production_state, production_reason_code = "NOT_AUTHORIZED", "TECHNICAL_FAILURE"
        future_test_authorized, test_reason_code = False, "TECHNICAL_FAILURE"
    elif blockers:
        code, text = "GLOBAL_BLOCKER", "A global blocker prevents workflow progression."
        action, action_text = "RESOLVE_GLOBAL_BLOCKER", "Resolve the global blocker before Test/Production."
        production_state, production_reason_code = "NOT_AUTHORIZED", "GLOBAL_BLOCKER_PRESENT"
    elif safe_effective_changes == 0:
        code, text = "NO_SAFE_CHANGES", "No safe effective changes are available to publish." + hold_text
        action = "REVIEW_HELD_ITEMS" if held else "NO_ACTION_REQUIRED"
        action_text = "No Test or Production run is required." + (" Review quarantined tickers separately when appropriate." if held else "")
        production_state, production_reason_code = "NOT_APPLICABLE", "NO_SAFE_CHANGES_TO_PUBLISH"
    elif completed:
        code, text = "PUBLICATION_COMPLETED", "Safe changes were published successfully." + hold_text
        action, action_text = "REVIEW_HELD_ITEMS" if held else "NO_ACTION_REQUIRED", "Review quarantined tickers separately." if held else "No corrective operator action is required."
    elif stage != "Preview":
        code, text = "TEST_COMPLETED", "Test on copies completed." + hold_text
        action, action_text = (
            ("REVIEW_PRODUCTION_AUTHORIZATION", "Review the bound Test evidence and separately authorize Production update.")
            if production_state == "AUTHORIZED" else
            ("REVIEW_PRODUCTION_GATE", "Review the Production authorization gate: " + str(production_reason_code or "PRODUCTION_BINDING_NOT_EVALUATED") + ".")
        )
    elif future_test_authorized:
        code, text = "SAFE_CHANGES_AUTHORIZED", "Safe peer changes are available and may continue." + hold_text
        action, action_text = "RUN_TEST", "Proceed to Test on copies."
    else:
        code, text = "TEST_NOT_AUTHORIZED", "Safe changes exist, but backend Test authorization was not granted: " + test_reason_code + "." + hold_text
        action, action_text = "REVIEW_TEST_GATE", "Resolve the backend authorization prerequisite: " + test_reason_code + "."
    if production_state is None:
        production_state = "NOT_EVALUATED" if future_test_authorized else "NOT_AUTHORIZED"
        production_reason_code = "TEST_MUST_COMPLETE_FIRST" if future_test_authorized else test_reason_code
    if not future_test_authorized and action == "RUN_TEST":
        raise ValueError("UNAUTHORIZED_TEST_RECOMMENDATION")
    return {
        "schema_version": 1, "authoritative_stage": stage,
        "safe_effective_changes": safe_effective_changes,
        "held_item_count": len(held), "held_items": held,
        "global_blocker_count": len(blockers), "global_blockers": blockers,
        "test_gate": {"authorized": future_test_authorized, "reason_code": test_reason_code},
        "production_gate": {"state": production_state, "reason_code": production_reason_code},
        "decision_code": code, "decision_text": text,
        "recommended_action_code": action, "recommended_action_text": action_text,
        "local_hold_blocked_safe_changes": False if held else None,
    }


def advance_refresh_decision(
    previous: Mapping[str, Any], *, stage: str, technical_failure: str | None = None,
    production_state: str = "NOT_EVALUATED",
    production_reason_code: str = "PRODUCTION_BINDING_NOT_EVALUATED", completed: bool = False,
) -> dict[str, Any]:
    return refresh_operational_decision(
        safe_effective_changes=previous["safe_effective_changes"],
        held_items=previous["held_items"], global_blockers=previous["global_blockers"],
        future_test_authorized=previous["test_gate"]["authorized"],
        test_reason_code=previous["test_gate"]["reason_code"], stage=stage,
        production_state=production_state, production_reason_code=production_reason_code,
        technical_failure=technical_failure, completed=completed,
    )


def operational_decision_rows(decision: Mapping[str, Any]) -> tuple[str, ...]:
    test, production = decision["test_gate"], decision["production_gate"]
    blocked = decision["local_hold_blocked_safe_changes"]
    return (
        f"Safe effective changes: {decision['safe_effective_changes'] if decision['safe_effective_changes'] is not None else 'UNKNOWN'}",
        f"Held / quarantined items: {decision['held_item_count']}",
        f"Global blockers: {decision['global_blocker_count']}",
        f"Test authorized: {'YES' if test['authorized'] else 'NO'}",
        f"Test authorization reason: {test['reason_code']}",
        f"Production authorization state: {production['state']}",
        f"Production authorization reason: {production['reason_code']}",
        f"Local hold blocked safe peer changes: {'NOT_APPLICABLE' if blocked is None else 'YES' if blocked else 'NO'}",
        f"Decision: {decision['decision_text']}",
        f"Recommended next action: {decision['recommended_action_text']}",
    )


def operational_decision_section(decision: Mapping[str, Any] | None) -> list[str]:
    if not decision:
        return []
    return ["", "## Operational Decision", "", *("- " + row for row in operational_decision_rows(decision))]
