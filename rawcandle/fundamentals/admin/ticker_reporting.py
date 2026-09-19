from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence


REASON_TEXT = {
    "IDENTITY_AMBIGUOUS": "Canonical identity could not be resolved unambiguously",
    "PROVIDER_IDENTITY_AMBIGUOUS": "Provider identity could not be resolved unambiguously",
    "PROVIDER_METADATA_MISSING": "Provider identity metadata is missing",
    "DELISTED_SECURITY": "The security is marked as delisted",
    "UNSUPPORTED_SECURITY_TYPE": "The security type is not supported",
    "INCOMPATIBLE_EXCHANGE": "The exchange is not supported",
    "MARKET_NOT_UNAMBIGUOUS_USA": "USA market listing could not be confirmed unambiguously",
    "MISSING_CLASSIFICATION": "Sector/Industry classification is missing",
    "FUNDAMENTAL_SOURCE_ROWS_MISSING": "No usable fundamental observations were found",
}


def _reason_codes(reason: Any) -> list[str]:
    text = str(reason or "").strip()
    if not text:
        return []
    codes = [part.strip() for part in text.split(",") if part.strip()]
    return codes if all(code.replace("_", "").isalnum() and code.upper() == code for code in codes) else []


def human_reasons(reason: Any) -> list[str]:
    codes = _reason_codes(reason)
    if codes:
        return [REASON_TEXT.get(code, code.replace("_", " ").capitalize()) for code in codes]
    text = str(reason or "").strip().rstrip(".")
    return [text] if text else []


def _preview_action(status: Any, before: Mapping[str, Any]) -> str:
    normalized = str(status or "").upper()
    if normalized == "ELIGIBLE":
        return "Eligible to add"
    if normalized == "ALREADY_PRESENT":
        return "Already present - complete" if before.get("v2_analysis") else "Already present - V2 analysis incomplete"
    if normalized == "REVIEW_REQUIRED":
        return "Review required"
    if normalized == "REJECTED":
        return "Rejected"
    return normalized.replace("_", " ").title() or "Not available"


def reporting_counts(reports: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "requested": len(reports), "new": 0, "eligible": 0, "already_present": 0,
        "review_required": 0, "rejected": 0, "network": 0, "taxonomy": 0,
    }
    for report in reports:
        before = report.get("before") or {}
        status = str((report.get("eligibility") or {}).get("status") or "").upper()
        if not before.get("canonical_identity"):
            counts["new"] += 1
        if status == "ELIGIBLE":
            counts["eligible"] += 1
        elif status == "ALREADY_PRESENT":
            counts["already_present"] += 1
        elif status == "REVIEW_REQUIRED":
            counts["review_required"] += 1
        elif status == "REJECTED":
            counts["rejected"] += 1
        counts["network"] += int(bool((report.get("acquisition") or {}).get("network_requested")))
        counts["taxonomy"] += int(bool((report.get("taxonomy") or {}).get("member")))
    return counts


def summary_rows(reports: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    counts = reporting_counts(reports)
    requested_label = "ticker" if counts["requested"] == 1 else "tickers"
    rows = [f"{counts['requested']} {requested_label} requested: {counts['new']} new, {counts['already_present']} already present."]
    stages = {str((report.get("after") or {}).get("stage") or "PREVIEW") for report in reports}
    actions = [str(report.get("final_action") or "") for report in reports]
    if stages == {"PREVIEW"}:
        rows.append(f"Eligible to add: {counts['eligible']}. Review required: {counts['review_required']}. Rejected: {counts['rejected']}.")
    elif stages == {"COPY_ONLY_APPLY"}:
        tested = sum(action.startswith("Tested successfully") or action.startswith("Existing ticker - V2") for action in actions)
        rows.append(f"Tested successfully: {tested}. Review required: {actions.count('Review required')}. Rejected: {actions.count('Rejected')}.")
    else:
        added = actions.count("Added")
        source_updated = actions.count("Updated")
        rebuilt = actions.count("Existing ticker - analysis rebuilt")
        unchanged = actions.count("Already present - no source change")
        rows.append(f"Added: {added}. Existing tickers included in rebuild: {rebuilt}. Source-data updates: {source_updated}. No source change: {unchanged}.")
        if actions.count("Review required") or actions.count("Rejected"):
            rows.append(f"Review required: {actions.count('Review required')}. Rejected: {actions.count('Rejected')}.")
    rows.append(f"Network access required: {counts['network']}. Active taxonomy members: {counts['taxonomy']}.")
    return tuple(rows)


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _table(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _quarter_label(row: Mapping[str, Any]) -> str | None:
    fiscal = str(row.get("fiscalperiod") or "").upper().strip()
    if len(fiscal) >= 6 and fiscal[:4].isdigit() and fiscal[-2:] in {"Q1", "Q2", "Q3", "Q4"}:
        return f"{fiscal[:4]} {fiscal[-2:]}"
    calendar = str(row.get("calendardate") or row.get("reportperiod") or "")
    if len(calendar) >= 7 and calendar[:4].isdigit() and calendar[5:7].isdigit():
        quarter = (int(calendar[5:7]) - 1) // 3 + 1
        return f"{calendar[:4]} Q{quarter}"
    return None


def _coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    arq = [row for row in rows if str(row.get("dimension") or "").upper() == "ARQ"]
    ordered = sorted(
        arq,
        key=lambda row: (
            str(row.get("reportperiod") or row.get("calendardate") or ""),
            str(row.get("fiscalperiod") or ""),
        ),
    )
    return {
        "provider_rows": len(rows),
        "arq_count": len(arq),
        "first_fiscal_quarter": _quarter_label(ordered[0]) if ordered else None,
        "latest_fiscal_quarter": _quarter_label(ordered[-1]) if ordered else None,
    }


def _company_identity(canonical_db: Path, ticker: str) -> dict[str, Any]:
    try:
        with _readonly(canonical_db) as connection:
            if not _table(connection, "security"):
                return {"exists": False}
            rows = connection.execute(
                "SELECT company_id,security_id,current_ticker,exchange,active FROM security WHERE UPPER(current_ticker)=UPPER(?)",
                (ticker,),
            ).fetchall()
            if len(rows) != 1:
                return {"exists": bool(rows), "ambiguous": len(rows) > 1}
            return {"exists": True, **dict(rows[0])}
    except (OSError, sqlite3.Error):
        return {"exists": False, "unavailable": True}


def _has_v2(analysis_db: Path, company_id: int | None) -> bool:
    if company_id is None:
        return False
    try:
        with _readonly(analysis_db) as connection:
            return any(
                _table(connection, table)
                and connection.execute(f"SELECT 1 FROM {table} WHERE company_id=? LIMIT 1", (company_id,)).fetchone()
                for table in ("score_result", "lifecycle_revised_result", "valuation_revised_result")
            )
    except (OSError, sqlite3.Error):
        return False


def _taxonomy(taxonomy_db: Path, ticker: str) -> dict[str, Any]:
    try:
        with _readonly(taxonomy_db) as connection:
            required = ("ec_ecosystem", "ec_taxonomy_version", "ec_entity", "ec_membership")
            if not all(_table(connection, table) for table in required):
                return {"member": False, "roles": [], "memberships": [], "status": "Not available"}
            rows = connection.execute(
                "SELECT DISTINCT COALESCE(m.membership_role,'UNSPECIFIED') role,"
                "p.entity_type parent_type,p.entity_code parent_code,COALESCE(p.entity_name,p.entity_code) parent_name "
                "FROM ec_entity c JOIN ec_membership m ON m.child_entity_id=c.entity_id "
                "JOIN ec_entity p ON p.entity_id=m.parent_entity_id "
                "JOIN ec_taxonomy_version v ON v.taxonomy_version_id=m.taxonomy_version_id "
                "JOIN ec_ecosystem e ON e.ecosystem_id=v.ecosystem_id "
                "WHERE UPPER(c.ticker)=UPPER(?) AND c.status='ACTIVE' AND m.status='ACTIVE' "
                "AND e.ecosystem_code='DATACENTER' AND e.status='ACTIVE' "
                "AND v.is_active=1 AND v.status='ACTIVE' ORDER BY role,parent_type,parent_code",
                (ticker,),
            ).fetchall()
            memberships = [dict(row) for row in rows]
            roles = sorted({str(row["role"]) for row in rows})
            return {"member": bool(rows), "roles": roles, "memberships": memberships, "status": "Available"}
    except (OSError, sqlite3.Error):
        return {"member": False, "roles": [], "memberships": [], "status": "Not available"}


def _latest(connection: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = connection.execute(query, params).fetchone()
    return dict(row) if row else None


def _status(value: Any, *prefixes: str) -> str:
    text = str(value or "No result").upper().strip().replace(" ", "_")
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def _reason_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.replace("_", " ").lower()


def _score_result(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"status": "No result", "reason": None, "technical_reason": None}
    raw_reason = row.get("reason")
    reason = None
    try:
        evidence = json.loads(str(raw_reason)) if raw_reason else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence = {}
    if isinstance(evidence, Mapping):
        missing = [str(value).replace("_", " ").title() for value in evidence.get("missing_components") or []]
        if evidence.get("ttm_core_ready") is False:
            reason = "TTM core inputs unavailable"
        elif missing:
            reason = "missing " + ", ".join(missing)
    if reason is None and raw_reason and not evidence:
        reason = _reason_text(raw_reason)
    return {"status": row.get("status"), "reason": reason, "technical_reason": raw_reason}


def _integrity_analysis(reason: str) -> dict[str, Any]:
    return {
        "integrity_status": "REPORTING_INTEGRITY_ERROR",
        "integrity_reason": reason,
        "score": {"status": "No result", "reason": None, "technical_reason": None},
        "lifecycle": {"status": "No result", "reason": None, "state": None},
        "valuation": {"status": "No result", "reason": None},
        "rp_v2": {"total_results": 0, "ecosystem_results": 0, "status": "No result", "reason": None},
        "rv": {"included": False, "status": "Not eligible", "reason": None},
    }


def _analysis(analysis_db: Path, company_id: int | None) -> dict[str, Any]:
    if company_id is None:
        return _integrity_analysis("Canonical company identity was not resolved for after-state reporting")
    try:
        with _readonly(analysis_db) as connection:
            score = _latest(connection, "SELECT readiness_status status,missing_input_reason reason FROM score_result WHERE company_id=? ORDER BY quarter_id DESC LIMIT 1", (company_id,)) if _table(connection, "score_result") else None
            lifecycle = _latest(connection, "SELECT lifecycle_status status,final_state state,reason_code reason FROM lifecycle_revised_result WHERE company_id=? ORDER BY fiscal_sequence DESC LIMIT 1", (company_id,)) if _table(connection, "lifecycle_revised_result") else None
            valuation = _latest(connection, "SELECT valuation_status status,reason_code reason FROM valuation_revised_result WHERE company_id=? ORDER BY fiscal_sequence DESC LIMIT 1", (company_id,)) if _table(connection, "valuation_revised_result") else None
            rp = None
            if _table(connection, "relative_position_result") and _table(connection, "relative_position_active_snapshot"):
                rp = _latest(connection, "SELECT COUNT(*) total_results,SUM(CASE WHEN r.peer_scope='ECOSYSTEM' THEN 1 ELSE 0 END) ecosystem_results,"
                    "GROUP_CONCAT(DISTINCT r.result_status) status FROM relative_position_result r "
                    "JOIN relative_position_active_snapshot a ON a.snapshot_id=r.snapshot_id WHERE r.company_id=?", (company_id,))
            rp_reason = None
            if rp and int(rp.get("total_results") or 0) == 0 and _table(connection, "relative_position_coverage") and _table(connection, "relative_position_active_snapshot"):
                reason = connection.execute("SELECT GROUP_CONCAT(DISTINCT c.reason_code) FROM relative_position_coverage c JOIN relative_position_active_snapshot a ON a.snapshot_id=c.snapshot_id WHERE c.company_id=?", (company_id,)).fetchone()
                rp_reason = str(reason[0]) if reason and reason[0] else "No eligible RP V2 source result"
            rv = None
            if _table(connection, "relative_valuation_company_result") and _table(connection, "relative_valuation_active_snapshot"):
                rv = _latest(connection, "SELECT r.valuation_status status,r.valuation_reason reason FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a ON a.snapshot_id=r.snapshot_id WHERE r.company_id=?", (company_id,))
            if not any((score, lifecycle, valuation)):
                return _integrity_analysis("The rebuilt analysis contains no Score, Lifecycle, or Valuation rows for the resolved company")
            lifecycle_result = dict(lifecycle) if lifecycle else {"status": "No result", "reason": None, "state": None}
            valuation_result = dict(valuation) if valuation else {"status": "No result", "reason": None}
            if _status(valuation_result.get("reason"), "VALUATION_") == _status(valuation_result.get("status"), "VALUATION_"):
                valuation_result["reason"] = None
            return {
                "integrity_status": "READY",
                "integrity_reason": None,
                "score": _score_result(score),
                "lifecycle": lifecycle_result,
                "valuation": valuation_result,
                "rp_v2": {
                    "total_results": int((rp or {}).get("total_results") or 0),
                    "ecosystem_results": int((rp or {}).get("ecosystem_results") or 0),
                    "status": (rp or {}).get("status") or ("No results" if rp else "Not available"),
                    "reason": rp_reason,
                },
                "rv": {"included": bool(rv), "status": (rv or {}).get("status") or "Not eligible", "reason": (rv or {}).get("reason")},
            }
    except (OSError, sqlite3.Error) as exc:
        return _integrity_analysis(f"After-state analysis lookup failed: {type(exc).__name__}")


def _before_label(provider: bool, canonical: bool, v2: bool) -> str:
    if provider and canonical and v2:
        return "Already fully present"
    if provider and not canonical:
        return "Provider data already present"
    if canonical and not provider:
        return "Canonical identity already present"
    if provider or canonical or v2:
        return "Existing but incomplete"
    return "New"


def build_preview_reporting(paths: Any, plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    network_calls = {
        str(call.get("ticker", "")).upper(): call
        for call in (plan.get("network") or {}).get("calls", [])
        if isinstance(call, Mapping)
    }
    reports: list[dict[str, Any]] = []
    for item in plan.get("items", []):
        ticker = str(item.get("ticker") or "").upper()
        identity = item.get("provider_metadata", {}).get("identity") or {}
        canonical = item.get("canonical") or {}
        markets = (item.get("market") or {}).get("markets") or []
        company_id = canonical.get("company_id")
        provider_before = item.get("source_category") == "local_provider"
        canonical_before = bool(canonical.get("exists"))
        v2_before = _has_v2(paths.analysis_db, int(company_id) if company_id is not None else None)
        source = {
            "local_provider": "Existing local provider data",
            "verified_archive": "Verified local archive",
            "network": "Network",
            "network_required": "No usable fundamentals found",
            "network_unavailable": "No usable fundamentals found",
        }.get(str(item.get("source_category")), "Not available")
        reports.append({
            "ticker": ticker,
            "company_name": identity.get("name"),
            "market": markets[0] if markets else None,
            "exchange": identity.get("exchange"),
            "before": {
                "category": _before_label(provider_before, canonical_before, v2_before),
                "provider_data": provider_before,
                "canonical_identity": canonical_before,
                "v2_analysis": v2_before,
            },
            "acquisition": {
                "source": source,
                "source_category": item.get("source_category"),
                "network_requested": ticker in network_calls,
                "network_used": item.get("source_category") == "network",
            },
            "coverage": _coverage(item.get("rows") or []),
            "classification": {
                "sector": (item.get("classification") or {}).get("sector"),
                "industry": (item.get("classification") or {}).get("industry"),
                "authority": "ticker_meta",
            },
            "taxonomy": _taxonomy(paths.taxonomy_db, ticker),
            "eligibility": {
                "status": item.get("status"),
                "reason": item.get("reason"),
                "reason_codes": _reason_codes(item.get("reason")),
                "user_reasons": human_reasons(item.get("reason")),
            },
            "after": {"stage": "PREVIEW", "canonical_identity": "Not calculated during Preview", "analysis": "Not calculated during Preview"},
            "final_action": _preview_action(item.get("status"), {
                "provider_data": provider_before,
                "canonical_identity": canonical_before,
                "v2_analysis": v2_before,
            }),
        })
    return reports


def enrich_after_state(
    preview_reports: Sequence[Mapping[str, Any]], paths: Any, *, stage: str,
    final_actions: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    actions = {str(key).upper(): value for key, value in (final_actions or {}).items()}
    for saved in preview_reports:
        report = dict(saved)
        ticker = str(report.get("ticker") or "").upper()
        identity = _company_identity(paths.canonical_db, ticker)
        company_id = identity.get("company_id")
        if identity.get("ambiguous"):
            analysis = _integrity_analysis("Canonical ticker resolved to multiple after-state identities")
        elif not identity.get("exists"):
            analysis = _integrity_analysis("Canonical ticker was not found in the after-state identity database")
        else:
            analysis = _analysis(paths.analysis_db, int(company_id) if company_id is not None else None)
        report["after"] = {
            "stage": stage,
            "canonical_identity": "Present" if identity.get("exists") else "Not present",
            "identity": identity,
            "analysis": analysis,
        }
        report["final_action"] = actions.get(ticker) or ("Tested successfully" if stage == "COPY_ONLY_APPLY" else "Updated")
        output.append(report)
    return output


def _compact(report: Mapping[str, Any]) -> list[str]:
    coverage = report.get("coverage") or {}
    span = "Not available"
    if coverage.get("arq_count") is not None:
        span = f"{coverage['arq_count']} ARQ"
        if coverage.get("first_fiscal_quarter") and coverage.get("latest_fiscal_quarter"):
            span += f", {coverage['first_fiscal_quarter']}-{coverage['latest_fiscal_quarter']}"
    classification = report.get("classification") or {}
    sector = " / ".join(str(value) for value in (classification.get("sector"), classification.get("industry")) if value) or "Classification unavailable"
    taxonomy = report.get("taxonomy") or {}
    tax = "No" if not taxonomy.get("member") else ", ".join(taxonomy.get("roles") or ["Role not specified"])
    after = report.get("after") or {}
    analysis = after.get("analysis") if isinstance(after.get("analysis"), Mapping) else {}
    if not analysis:
        before = report.get("before") or {}
        v2 = "Existing V2 analysis" if before.get("v2_analysis") else "No existing V2 analysis" if before.get("canonical_identity") else "Not calculated during Preview"
        rp = "Existing" if before.get("v2_analysis") else "None" if before.get("canonical_identity") else "Not calculated during Preview"
    else:
        if analysis.get("integrity_status") == "REPORTING_INTEGRITY_ERROR":
            v2 = "Reporting integrity error"
        else:
            v2 = f"Score V2 {_status((analysis.get('score') or {}).get('status'), 'SCORE_')} / Valuation {_status((analysis.get('valuation') or {}).get('status'), 'VALUATION_')}"
        rp = f"{(analysis.get('rp_v2') or {}).get('total_results', 0)} results"
    source = (report.get("acquisition") or {}).get("source") or "Not available"
    if not (report.get("acquisition") or {}).get("network_requested"):
        source += "; no network"
    return [str(report.get("ticker")), str((report.get("before") or {}).get("category", "Not available")), source, span, v2, sector, tax, rp, str(report.get("final_action") or "Not available")]


def _display(value: Any, prefix: str = "") -> str:
    text = str(value or "Not available")
    if prefix and text.startswith(prefix):
        text = text[len(prefix):]
    return text.replace("_", " ")


def _analysis_outcome(reports: Sequence[Mapping[str, Any]]) -> list[str]:
    analyses = [
        (report.get("after") or {}).get("analysis")
        for report in reports
        if isinstance((report.get("after") or {}).get("analysis"), Mapping)
    ]
    if not analyses:
        return []
    rows: list[str] = []
    for label, key, prefixes in (
        ("Score V2", "score", ("SCORE_",)),
        ("Lifecycle", "lifecycle", ("LIFECYCLE_",)),
        ("Valuation", "valuation", ("VALUATION_",)),
    ):
        counts: dict[str, int] = {}
        for analysis in analyses:
            status = _status((analysis.get(key) or {}).get("status"), *prefixes)
            counts[status] = counts.get(status, 0) + 1
        rows.extend(f"{label} {status}: {count}" for status, count in sorted(counts.items()) if status != "NO_RESULT")
    rows.append(f"RP V2 with at least one result: {sum(int((analysis.get('rp_v2') or {}).get('total_results') or 0) > 0 for analysis in analyses)}")
    rv_counts: dict[str, int] = {}
    for analysis in analyses:
        status = _status((analysis.get("rv") or {}).get("status"), "VALUATION_")
        rv_counts[status] = rv_counts.get(status, 0) + 1
    rows.extend(f"RV {status.replace('_', ' ').title() if status == 'NOT_ELIGIBLE' else status}: {count}" for status, count in sorted(rv_counts.items()))
    integrity_errors = sum(analysis.get("integrity_status") == "REPORTING_INTEGRITY_ERROR" for analysis in analyses)
    if integrity_errors:
        rows.append(f"Reporting integrity errors: {integrity_errors}")
    return rows


def _rp_presentation(item: Mapping[str, Any]) -> str:
    total = int(item.get("total_results") or 0)
    ecosystem = int(item.get("ecosystem_results") or 0)
    statuses = {str(value).strip() for value in str(item.get("status") or "").split(",") if value.strip()}
    if total:
        text = f"{total} results ({ecosystem} ecosystem) - "
        text += "READY" if "RELATIVE_POSITION_READY" in statuses else "Results available"
        if "PEER_GROUP_TOO_SMALL" in statuses:
            text += "; some peer groups too small"
        return text
    return "0 results" + (f" - {_reason_text(item.get('reason'))}" if item.get("reason") else "")


def render_ticker_sections(reports: Sequence[Mapping[str, Any]]) -> str:
    if not reports:
        return ""
    lines = ["## Ticker Summary", "", "| Ticker | Before | Data source | Quarter coverage | V2 status | Sector / Industry | Taxonomy | RP V2 | Final action |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for report in reports:
        lines.append("| " + " | ".join(value.replace("|", "/") for value in _compact(report)) + " |")
    outcome_rows = _analysis_outcome(reports)
    if outcome_rows:
        lines.extend(["", "## Analysis Outcome", ""])
        lines.extend(f"- {row}" for row in outcome_rows)
    review_items = [
        report for report in reports
        if str((report.get("eligibility") or {}).get("status") or "").upper() == "REVIEW_REQUIRED"
    ]
    if review_items:
        lines.extend(["", "## Items Requiring Review", ""])
        for report in review_items:
            reasons = (report.get("eligibility") or {}).get("user_reasons") or human_reasons((report.get("eligibility") or {}).get("reason"))
            lines.append(f"- {report.get('ticker')} - " + "; ".join(str(reason) for reason in reasons) + ".")
    lines.extend(["", "## Ticker Details"])
    for report in reports:
        ticker = report.get("ticker") or "Ticker"
        name = report.get("company_name") or "Name not available"
        before = report.get("before") or {}
        acquisition = report.get("acquisition") or {}
        coverage = report.get("coverage") or {}
        classification = report.get("classification") or {}
        taxonomy = report.get("taxonomy") or {}
        after = report.get("after") or {}
        analysis = after.get("analysis") if isinstance(after.get("analysis"), Mapping) else None
        stage = str(after.get("stage") or "PREVIEW")
        if stage == "PREVIEW":
            status = str((report.get("eligibility") or {}).get("status") or "")
            if before.get("canonical_identity"):
                identity_text = "Canonical identity: Present"
            elif status == "ELIGIBLE":
                identity_text = "Canonical identity: Not present - will be created if applied"
            elif status == "REVIEW_REQUIRED":
                identity_text = "Canonical identity: Not present - pending review"
            else:
                identity_text = "Canonical identity: Not present"
        elif stage == "COPY_ONLY_APPLY":
            identity_text = "Canonical identity on copies: " + ("Present" if before.get("canonical_identity") else "Created" if after.get("canonical_identity") == "Present" else "Not present")
        else:
            identity_text = "Canonical identity: " + ("Present" if before.get("canonical_identity") else "Created" if after.get("canonical_identity") == "Present" else "Not present")
        lines.extend(["", f"### {ticker} - {name}", "", "#### Identity", "", f"- Market / exchange: {report.get('market') or 'Not available'} / {report.get('exchange') or 'Not available'}", f"- {identity_text}", "", "#### Before the run", "", f"- State: {before.get('category', 'Not available')}", f"- Provider data: {'Yes' if before.get('provider_data') else 'No'}", f"- Canonical identity: {'Present' if before.get('canonical_identity') else 'Not present'}", f"- Existing V2 analysis: {'Yes' if before.get('v2_analysis') else 'No'}", "", "#### Data acquisition", "", f"- Source: {acquisition.get('source', 'Not available')}", f"- Network request: {'Yes' if acquisition.get('network_requested') else 'No'}", f"- Network result used: {'Yes' if acquisition.get('network_used') else 'No'}", f"- Provider rows: {coverage.get('provider_rows', 'Not available')}", f"- Quarterly coverage: {coverage.get('arq_count', 'Not available')} ARQ", f"- First fiscal quarter: {coverage.get('first_fiscal_quarter') or 'Not available'}", f"- Latest fiscal quarter: {coverage.get('latest_fiscal_quarter') or 'Not available'}"])
        if coverage.get("provider_rows", 0) > 0 and coverage.get("arq_count") == 0:
            lines.append("- Provider data exists, but no usable quarterly ARQ history was identified.")
        lines.extend(["", "#### Classification", "", f"- Sector: {classification.get('sector') or 'Not available'}", f"- Industry: {classification.get('industry') or 'Not available'}", "", "#### Taxonomy", "", f"- Member: {'Yes' if taxonomy.get('member') else 'No'}", f"- Roles: {', '.join(taxonomy.get('roles') or []) or 'Not applicable'}"])
        memberships = taxonomy.get("memberships") or []
        if memberships:
            lines.append("- Memberships: " + ", ".join(str(item.get("parent_name") or item.get("parent_code")) for item in memberships))
        lines.extend(["", "#### V2 analysis", ""])
        if analysis is None:
            if before.get("v2_analysis"):
                lines.append("- Existing V2 analysis")
            elif before.get("canonical_identity"):
                lines.append("- No existing V2 analysis")
            else:
                lines.append("- Not calculated during Preview")
        elif analysis.get("integrity_status") == "REPORTING_INTEGRITY_ERROR":
            lines.append(f"- Reporting integrity error: {analysis.get('integrity_reason') or 'after-state lookup failed'}")
        else:
            score = analysis.get("score") or {}
            score_text = _status(score.get("status"), "SCORE_")
            if score.get("reason"):
                score_text += f" - {score['reason']}"
            lines.append(f"- Score V2: {score_text}")
            lifecycle = analysis.get("lifecycle") or {}
            lifecycle_text = _status(lifecycle.get("status"), "LIFECYCLE_")
            if lifecycle_text == "READY" and lifecycle.get("state"):
                lifecycle_text += " - " + str(lifecycle["state"]).replace("_", " ").title()
            elif lifecycle.get("reason"):
                lifecycle_text += f" - {_reason_text(lifecycle['reason'])}"
            lines.append(f"- Lifecycle: {lifecycle_text}")
            valuation = analysis.get("valuation") or {}
            valuation_text = _status(valuation.get("status"), "VALUATION_")
            if valuation.get("reason"):
                valuation_text += f" - {_reason_text(valuation['reason'])}"
            lines.append(f"- Valuation V2: {valuation_text}")
            rp = analysis.get("rp_v2") or {}
            lines.append(f"- RP V2: {_rp_presentation(rp)}")
            rv = analysis.get("rv") or {}
            rv_text = _status(rv.get("status"), "VALUATION_")
            if rv_text == "NOT_ELIGIBLE":
                rv_text = "Not eligible"
            elif rv.get("reason") and _status(rv.get("reason"), "VALUATION_") != _status(rv.get("status"), "VALUATION_"):
                rv_text += f" - {_reason_text(rv['reason'])}"
            lines.append(f"- RV: {rv_text}")
        lines.extend(["", "#### Final result", "", f"- {report.get('final_action') or 'Not available'}"])
    return "\n".join(lines) + "\n"
