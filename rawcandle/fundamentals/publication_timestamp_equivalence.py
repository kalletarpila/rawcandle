"""Read-only reviewed comparison of two representations of one SEC parent event.

This is not a timestamp repair, evidence fingerprint substitution, or apply gate.
Callers retain both evidence records and all reviewed exclusion/precedence decisions.
"""
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo


RULE_VERSION = "same_sec_parent_timestamp_representation_v1"
IDENTITY_FIELDS = (
    "company_id", "fiscal_year", "fiscal_quarter", "source_type",
    "accession_number", "document_id", "filing_form", "source_reference",
    "item_2_02_status",
)


def compare_timestamp_representations(
    stored, current, *, parent, quarters, independent_conflicts=(),
    reviewed_blockers=(),
):
    """Compare exact parent evidence using a retained SecFiling witness.

    ``quarters`` must contain the complete resolver quarter scope for this company;
    its existing inclusive 0..180 day plausibility window is checked for both
    clocks. Blockers are independent reviewed findings, never inferred away here.
    A linked exhibit can supply context, but cannot replace the parent identity.
    No timestamp is selected and no input is modified.
    """
    old_text = stored.get("source_timestamp_utc")
    new_text = current.get("source_timestamp_utc")
    result = dict(
        rule_version=RULE_VERSION, stored_timestamp=old_text,
        current_timestamp=new_text, offset_seconds=None,
        utc_date_boundary=False, new_york_date_boundary=False,
        eligibility_changed=False, same_parent=False,
        representation_match=False, equivalent=False,
        classification="DOES_NOT_MEET_EQUIVALENCE_RULE", reasons=[],
    )
    failures = []
    if any(stored.get(f) is None or stored.get(f) != current.get(f) for f in IDENTITY_FIELDS):
        failures.append("EVENT_IDENTITY_DIFFERS_OR_MISSING")
    accession = current.get("accession_number", "")
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        failures.append("NONEXACT_ACCESSION")
    if current.get("source_type") != "SEC_8K_ITEM_2_02" or current.get("filing_form") != "8-K":
        failures.append("NOT_ORDINARY_ITEM_2_02_PARENT")
    reference = current.get("source_reference", "")
    if (
        parent.accession_number != accession or parent.form != "8-K"
        or not parent.primary_document or "2.02" not in re.split(r"[,;\s]+", parent.items)
        or parent.source_reference != reference
        or parent.primary_document != current.get("document_id")
        or parent.acceptance_timestamp_utc != new_text
        or not re.fullmatch(
            r"https://www\.sec\.gov/Archives/edgar/data/\d+/"
            + re.escape(accession.replace("-", "")) + r"/" + re.escape(parent.primary_document),
            reference,
        )
    ):
        failures.append("PARENT_WITNESS_MISMATCH")
    scope = tuple(quarters)
    natural_key = lambda q: (q["company_id"], q["fiscal_year"], q["fiscal_quarter"])
    if not scope or any(q["company_id"] != current.get("company_id") for q in scope) or tuple(current.get(f) for f in ("company_id", "fiscal_year", "fiscal_quarter")) not in {natural_key(q) for q in scope}:
        failures.append("QUARTER_SCOPE_MISMATCH")
    try:
        old = datetime.fromisoformat(old_text.replace("Z", "+00:00"))
        new = datetime.fromisoformat(new_text.replace("Z", "+00:00"))
        if old.utcoffset() is None or new.utcoffset() is None:
            raise ValueError("Timezone required")
        # Evidence fields are UTC in the authority contract; do not reinterpret
        # an unqualified or non-UTC clock as UTC.
        if old.utcoffset().total_seconds() or new.utcoffset().total_seconds():
            raise ValueError("UTC evidence required")
        offset = (new - old).total_seconds()
        result["offset_seconds"] = offset
        result["utc_date_boundary"] = old.date() != new.date()
        eastern = ZoneInfo("America/New_York")
        result["new_york_date_boundary"] = old.astimezone(eastern).date() != new.astimezone(eastern).date()
        eligible = lambda instant: sorted(
            natural_key(q) for q in scope
            if 0 <= (instant.date() - date.fromisoformat(q["period_end"])).days <= 180
        )
        result["eligibility_changed"] = eligible(old) != eligible(new)
        if result["eligibility_changed"]:
            failures.append("QUARTER_ELIGIBILITY_CHANGED")
        if offset == 0:
            failures.append("IDENTICAL_TIMESTAMP_UNCHANGED")
        elif abs(offset) not in (14400, 18000):
            failures.append("OFFSET_NOT_EXACTLY_4_OR_5_HOURS")
    except (ValueError, TypeError, AttributeError, KeyError):
        failures.append("INVALID_TIMESTAMP_OR_QUARTER")
    result["same_parent"] = not any(
        f in failures for f in ("EVENT_IDENTITY_DIFFERS_OR_MISSING", "NONEXACT_ACCESSION", "NOT_ORDINARY_ITEM_2_02_PARENT", "PARENT_WITNESS_MISMATCH")
    )
    result["representation_match"] = not failures
    blockers = sorted(set(independent_conflicts) | set(reviewed_blockers))
    result["reasons"] = failures + blockers
    if not failures:
        result["equivalent"] = not blockers
        result["classification"] = (
            "TIMESTAMP_PLUS_INDEPENDENT_AMBIGUITY" if blockers
            else "TIMESTAMP_REPRESENTATION_ONLY"
        )
    return result


def classify_timestamp_case(comparisons):
    """Aggregate pair findings without collapsing distinct accession events."""
    comparisons = tuple(comparisons)
    if not comparisons or any(not c["representation_match"] for c in comparisons):
        return "DOES_NOT_MEET_EQUIVALENCE_RULE"
    if any(not c["equivalent"] for c in comparisons):
        return "TIMESTAMP_PLUS_INDEPENDENT_AMBIGUITY"
    return "TIMESTAMP_REPRESENTATION_ONLY"
