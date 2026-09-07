from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.operating_income_v2 import (
    contract,
    score,
    valuation,
)
from rawcandle.fundamentals.operating_income_v2.activation import (
    active_model_manifest,
    assert_v2_active,
)
from rawcandle.fundamentals.operating_income_v2.persistence import (
    HISTORY_MODE,
)
from rawcandle.fundamentals.operating_income_v2.readers import ParallelModelRepository
from rawcandle.fundamentals.snapshot import assembler as v1


REPORT_CONTRACT = "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V6"
REPORT_CONTRACT_SPEC = {
    "version": REPORT_CONTRACT,
    "model_family": contract.FAMILY_FINGERPRINT,
    "history_windows": {"score": 5, "valuation": 5, "lifecycle": 4},
    "valuation_points": ("CURRENT_MOMENT", "LATEST_FILING", "PREVIOUS_FILING_Q_MINUS_1"),
    "valuation_metrics": (
        "market_cap", "enterprise_value", "pe", "earnings_yield", "p_fcf",
        "fcf_yield", "ev_operating_income", "operating_income_yield", "ev_sales", "p_sales",
    ),
    "valuation_basis": (
        "fiscal_quarter", "ttm_period_end", "fundamental_availability_date",
        "price_date", "price", "shares_outstanding", "market_cap",
        "ttm_net_income_common",
    ),
    "common_earnings_display": "REPORTED_GAAP_COMMON_SHAREHOLDER_EARNINGS_NOT_NORMALIZED",
    "availability_date_terminology": "SOURCE_AVAILABILITY_DATE_WITH_FINNISH_HISTORY_LABEL",
    "valuation_change_units": "COMPONENT_SCORE_POINTS_AND_MIXED_TABLE_SCORE_CHANGE_CELL_POINTS",
    "diagnostic_reason_rendering": "EXHAUSTIVE_READABLE_FINNISH_WITH_NEUTRAL_UNKNOWN_FALLBACK",
    "active_package_rendering": "TECHNICAL_APPENDIX_ONLY",
    "diagnostic_rendering": "READABLE_SUMMARY_PLUS_COMPLETE_AUDIT_TABLE",
    "diagnostic_definition_rendering": "SEVEN_ENGINE_RECONCILED_COMPACT_DEFINITIONS",
    "zero_flag_scope": "ALL_CLEAR_DISTINCT_FROM_NOT_READY_AND_NOT_APPLICABLE",
    "lifecycle_rendering": "FOUR_ENDPOINTS_WITH_STATUS_CANDIDATE_AND_OPERATING_MARGIN_EVIDENCE",
    "context": "CURRENT_PRICE_AND_ACTIVE_V2_PACKAGE_IDENTITY",
    "formatting": "COMPACT_MONEY_PERCENT_PP_MULTIPLE_AND_EXPLICIT_CURRENCY_NA",
    "internal_database_ids": "NOT_RENDERED",
}
REPORT_PRESENTATION_FINGERPRINT = hashlib.sha256(
    json.dumps(REPORT_CONTRACT_SPEC, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()

CANDIDATE_REPORT_CONTRACT = "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V7"
CANDIDATE_REPORT_CONTRACT_SPEC = {
    **REPORT_CONTRACT_SPEC,
    "version": CANDIDATE_REPORT_CONTRACT,
    "diagnostic_definition_rendering": "EIGHT_ENGINE_RECONCILED_COMPACT_DEFINITIONS",
    "diagnostic_zero_flag_scope": "EIGHT_FLAGS_WITH_EXPLICIT_INCOMPLETE_COVERAGE",
    "diagnostic_gap_rendering": "SIGNED_AMOUNT_DIRECTION_ABSOLUTE_REVENUE_RATIO_AND_THRESHOLD",
}
CANDIDATE_REPORT_PRESENTATION_FINGERPRINT = hashlib.sha256(
    json.dumps(CANDIDATE_REPORT_CONTRACT_SPEC, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _component_map(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    output = dict(row)
    components = {}
    for item in row.get("components", []):
        component = dict(item)
        raw = component.pop("evidence_json", None)
        component["evidence"] = json.loads(raw) if raw else {}
        components[str(component["component_name"])] = component
    output["components"] = components
    return output


def _finite_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _score_raw(
    scored: Mapping[str, Any] | None,
    ttm: Mapping[str, Any] | None,
    yoy_base: Mapping[str, Any] | None,
) -> dict[str, Any]:
    components = scored.get("components", {}) if scored else {}

    def metric(name: str) -> Any:
        return components.get(name, {}).get("evidence", {}).get("metric_value")

    branch = None
    branch_value = None
    if ttm:
        cash, debt, operating, fcf = (
            ttm.get(key) for key in ("cash", "total_debt", "ttm_operating_income", "ttm_free_cashflow")
        )
        if all(value is not None for value in (cash, debt, operating, fcf)):
            net_debt = float(debt) - float(cash)
            if float(operating) > 0:
                branch, branch_value = "NET_DEBT_TO_OPERATING_INCOME", net_debt / float(operating)
            elif net_debt <= 0 and float(fcf) >= 0:
                branch, branch_value = "NET_CASH_NONPOSITIVE_OPERATING_INCOME_POSITIVE_FCF", net_debt
            elif net_debt <= 0:
                branch, branch_value = "NET_CASH_NONPOSITIVE_OPERATING_INCOME_NEGATIVE_FCF", net_debt
            else:
                branch, branch_value = "POSITIVE_NET_DEBT_NONPOSITIVE_OPERATING_INCOME", net_debt
    return {
        "revenue_growth_yoy_ttm": metric("REVENUE_GROWTH"),
        "operating_margin_ttm": metric("OPERATING_PROFITABILITY"),
        "operating_margin_direction": metric("OPERATING_MARGIN_DIRECTION"),
        "fcf_margin_ttm": metric("FCF_MARGIN"),
        "balance_sheet_branch": branch,
        "balance_sheet_value": branch_value,
        "shares_outstanding_yoy_change": metric("DILUTION"),
        "fundamental_trajectory": metric("FUNDAMENTAL_TRAJECTORY"),
        "revenue_growth_comparison_base": yoy_base.get("ttm_revenue") if yoy_base else None,
    }


def _current_price_valuation(
    market: sqlite3.Connection,
    *,
    ticker: str,
    report_date: str,
    anchor: Mapping[str, Any],
    classification: Mapping[str, Any],
) -> dict[str, Any]:
    bars = [
        valuation.PriceBar(str(row["pvm"]), row["open"], row["high"], row["low"], row["close"])
        for row in market.execute(
            "SELECT pvm,open,high,low,close FROM osakedata WHERE UPPER(osake)=? AND pvm<=? ORDER BY pvm DESC LIMIT 32",
            (ticker, report_date),
        )
    ]
    selected = valuation.select_price(bars, report_date)
    base = {"label": v1.CURRENT_PRICE_LABEL, "price_date": selected.price_date, "price_age_calendar_days": selected.price_age_calendar_days}
    if selected.selected_price is None or selected.price_date is None:
        return {**base, "valuation_status": "VALUATION_NOT_READY", "reason_code": selected.reason_code or "PRICE_MISSING"}
    if selected.price_age_calendar_days is None or selected.price_age_calendar_days > v1.PRICE_MAX_AGE_DAYS:
        return {**base, "valuation_status": "VALUATION_NOT_READY", "reason_code": "CURRENT_PRICE_FALLBACK_TOO_OLD", "selected_price": selected.selected_price}
    selected_bar = next(bar for bar in bars if bar.price_date == selected.price_date)
    observation = valuation.ValuationObservation(
        company_id=int(anchor["company_id"]), security_id=anchor.get("security_id"), ticker=ticker,
        fiscal_year=int(anchor["endpoint_fiscal_year"]), fiscal_quarter=str(anchor["endpoint_fiscal_quarter"]),
        quarter_id=int(anchor["endpoint_quarter_id"]), period_end=str(anchor["period_end"]),
        fundamental_available_date=selected.price_date,
        ttm_readiness_status=str(anchor["readiness_status"]),
        ttm_blocker_codes=tuple(json.loads(anchor.get("blocker_codes_json") or "[]")),
        ttm_operating_income=anchor.get("ttm_operating_income"),
        ttm_free_cashflow=anchor.get("ttm_free_cashflow"),
        ttm_net_income_common=anchor.get("ttm_net_income_common"),
        net_income_common_4q_ready=bool(anchor.get("net_income_common_4q_ready")),
        shares_outstanding=anchor.get("shares_outstanding"), cash=anchor.get("cash"),
        total_debt=anchor.get("total_debt"), sector=classification.get("sector"),
        industry=classification.get("industry"),
    )
    result = valuation.calculate_valuation(observation, (selected_bar,)).to_dict()
    result.update(base, fundamental_anchor_available_date=anchor.get("ttm_source_available_date"), diagnostic_selected_price=selected.selected_price, diagnostic_price_eligible=True)
    return result


def _multiples_context(
    *, evaluation_point: str, ttm: Mapping[str, Any] | None,
    persisted: Mapping[str, Any] | None, fiscal_year: int | None,
    fiscal_quarter: str | None, availability_date: str | None,
    price_date: str | None, price: Any, price_eligible: bool,
    period_end: str | None = None,
) -> dict[str, Any]:
    source = persisted or {}
    fundamentals = ttm or {}

    def finite(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def source_value(name: str) -> float | None:
        value = source.get(name)
        return finite(fundamentals.get(name) if value is None else value)

    def metric(value: float | None, status: str) -> dict[str, Any]:
        return {"status": status, "value": value if status == "VALUE" else None}

    price_value = finite(price)
    shares = source_value("shares_outstanding")
    debt = source_value("total_debt")
    cash = source_value("cash")
    revenue = source_value("ttm_revenue")
    operating_income = source_value("ttm_operating_income")
    fcf = source_value("ttm_free_cashflow")
    common_earnings = source_value("ttm_net_income_common")
    if fundamentals and not bool(fundamentals.get("net_income_common_4q_ready")):
        common_earnings = None

    if not price_eligible or price_value is None:
        market_cap_status, market_cap = "N_A", None
    elif price_value <= 0 or shares is not None and shares <= 0:
        market_cap_status, market_cap = "N_M", None
    elif shares is None:
        market_cap_status, market_cap = "N_A", None
    else:
        calculated_market_cap = price_value * shares
        if not math.isfinite(calculated_market_cap):
            market_cap_status, market_cap = "N_A", None
        elif calculated_market_cap <= 0:
            market_cap_status, market_cap = "N_M", None
        else:
            market_cap_status, market_cap = "VALUE", calculated_market_cap

    if market_cap_status == "N_A" or debt is None or cash is None:
        enterprise_value_status, enterprise_value = "N_A", None
    elif market_cap_status == "N_M":
        enterprise_value_status, enterprise_value = "N_M", None
    else:
        calculated_enterprise_value = market_cap + debt - cash
        if not math.isfinite(calculated_enterprise_value):
            enterprise_value_status, enterprise_value = "N_A", None
        else:
            enterprise_value_status, enterprise_value = "VALUE", calculated_enterprise_value

    def market_ratio(numerator: float | None, *, reciprocal: bool) -> dict[str, Any]:
        if market_cap_status == "N_A" or numerator is None:
            return metric(None, "N_A")
        if market_cap_status != "VALUE" or numerator <= 0:
            return metric(None, "N_M")
        return metric(market_cap / numerator if reciprocal else numerator / market_cap, "VALUE")

    def enterprise_ratio(numerator: float | None, *, reciprocal: bool) -> dict[str, Any]:
        if enterprise_value_status == "N_A" or numerator is None:
            return metric(None, "N_A")
        if enterprise_value_status != "VALUE" or enterprise_value <= 0 or numerator <= 0:
            return metric(None, "N_M")
        return metric(enterprise_value / numerator if reciprocal else numerator / enterprise_value, "VALUE")

    context = {
        "evaluation_point": evaluation_point,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "ttm_period_end": period_end,
        "fundamental_availability_date": availability_date,
        "price_date": price_date,
        "price": price_value,
        "price_eligible": price_eligible,
        "price_currency": None,
        "valuation_status": source.get("valuation_status"),
        "source_inputs": {
            "shares_outstanding": shares,
            "total_debt": debt,
            "cash": cash,
            "ttm_revenue": revenue,
            "ttm_operating_income": operating_income,
            "ttm_free_cashflow": fcf,
            "ttm_net_income_common": common_earnings,
        },
        "authoritative_ttm_net_income_common": finite(
            fundamentals.get("ttm_net_income_common")
        ),
        "authoritative_market_cap": finite(source.get("market_cap")),
        "authoritative_enterprise_value": finite(source.get("enterprise_value")),
        "metrics": {
            "market_cap": metric(market_cap, market_cap_status),
            "enterprise_value": metric(enterprise_value, enterprise_value_status),
            "pe": market_ratio(common_earnings, reciprocal=True),
            "earnings_yield": market_ratio(common_earnings, reciprocal=False),
            "p_fcf": market_ratio(fcf, reciprocal=True),
            "fcf_yield": market_ratio(fcf, reciprocal=False),
            "ev_operating_income": enterprise_ratio(operating_income, reciprocal=True),
            "operating_income_yield": enterprise_ratio(operating_income, reciprocal=False),
            "ev_sales": enterprise_ratio(revenue, reciprocal=True),
            "p_sales": market_ratio(revenue, reciprocal=True),
        },
    }
    context["reconciliation"] = _valuation_context_reconciliation(context)
    return context


def _three_point_multiples(history: list[dict[str, Any]], current: Mapping[str, Any]) -> dict[str, Any]:
    latest, previous = history[-1], history[-2]

    def filing(point: str, slot: Mapping[str, Any]) -> dict[str, Any]:
        persisted = slot.get("valuation") or {}
        age = persisted.get("price_age_calendar_days")
        eligible = persisted.get("selected_price") is not None and age is not None and 0 <= int(age) <= v1.FILING_PRICE_MAX_AGE_DAYS
        return _multiples_context(
            evaluation_point=point, ttm=slot.get("ttm"), persisted=persisted,
            fiscal_year=slot["fiscal_year"] if slot.get("ttm") else None,
            fiscal_quarter=slot["fiscal_quarter"] if slot.get("ttm") else None,
            period_end=(slot.get("ttm") or {}).get("period_end"),
            availability_date=slot.get("availability_date") if slot.get("ttm") else None,
            price_date=persisted.get("price_date"), price=persisted.get("selected_price"),
            price_eligible=eligible,
        )

    selected_price = current.get("diagnostic_selected_price", current.get("selected_price"))
    current_context = _multiples_context(
        evaluation_point="CURRENT_MOMENT", ttm=latest.get("ttm"), persisted=None,
        fiscal_year=latest["fiscal_year"] if latest.get("ttm") else None,
        fiscal_quarter=latest["fiscal_quarter"] if latest.get("ttm") else None,
        period_end=(latest.get("ttm") or {}).get("period_end"),
        availability_date=latest.get("availability_date"), price_date=current.get("price_date"),
        price=selected_price, price_eligible=bool(current.get("diagnostic_price_eligible")),
    )
    current_context["valuation_status"] = current.get("valuation_status")
    current_context["authoritative_market_cap"] = _finite_value(current.get("market_cap"))
    current_context["authoritative_enterprise_value"] = _finite_value(current.get("enterprise_value"))
    current_context["reconciliation"] = _valuation_context_reconciliation(current_context)
    contexts = (
        current_context,
        filing("LATEST_FILING", latest),
        filing("PREVIOUS_FILING_Q_MINUS_1", previous),
    )
    return {"contexts": contexts}


def _valuation_context_reconciliation(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs = context["source_inputs"]
    metrics = context["metrics"]
    price = _finite_value(context.get("price"))
    shares = _finite_value(inputs.get("shares_outstanding"))
    common = _finite_value(inputs.get("ttm_net_income_common"))
    authoritative_common = _finite_value(
        context.get("authoritative_ttm_net_income_common")
    )

    def same(left: float | None, right: float | None) -> bool:
        if left is None or right is None:
            return left is right
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)

    checks: list[dict[str, Any]] = []

    def add(name: str, actual: Any, expected: Any, ok: bool) -> None:
        checks.append({"name": name, "actual": actual, "expected": expected, "ok": ok})

    add("reported_common_earnings_ttm", common, authoritative_common, same(common, authoritative_common))

    market_metric = metrics["market_cap"]
    expected_market_cap = (
        price * shares
        if bool(context.get("price_eligible"))
        and price is not None and shares is not None and price > 0 and shares > 0
        else None
    )
    add(
        "market_cap_price_times_shares",
        market_metric.get("value"),
        expected_market_cap,
        same(_finite_value(market_metric.get("value")), expected_market_cap),
    )
    authoritative_market_cap = _finite_value(context.get("authoritative_market_cap"))
    add(
        "market_cap_authoritative",
        market_metric.get("value"),
        authoritative_market_cap,
        authoritative_market_cap is None
        or same(_finite_value(market_metric.get("value")), authoritative_market_cap),
    )

    for metric_name, reciprocal in (("earnings_yield", False), ("pe", True)):
        metric = metrics[metric_name]
        expected = None
        expected_status = "N_A" if common is None or expected_market_cap is None else "N_M"
        if common is not None and common > 0 and expected_market_cap is not None:
            expected_status = "VALUE"
            expected = expected_market_cap / common if reciprocal else common / expected_market_cap
        add(
            f"reported_common_earnings_{metric_name}",
            {"status": metric.get("status"), "value": metric.get("value")},
            {"status": expected_status, "value": expected},
            metric.get("status") == expected_status
            and same(_finite_value(metric.get("value")), expected),
        )
    return checks


def _delta(analysis: sqlite3.Connection, company_id: int, fiscal_year: int, fiscal_quarter: str, model_fingerprint: str) -> dict[str, Any] | None:
    package = analysis.execute("SELECT package_id FROM fundamental_delta_package WHERE model_fingerprint=? AND history_mode=?", (model_fingerprint, HISTORY_MODE)).fetchone()
    if not package:
        return None
    row = analysis.execute(
        "SELECT r.*,sq.status_text qoq_status,s2.status_text two_quarter_status,sy.status_text yoy_status "
        "FROM fundamental_delta_result r "
        "JOIN fundamental_delta_status sq ON sq.status_id=r.qoq_status_id "
        "JOIN fundamental_delta_status s2 ON s2.status_id=r.two_quarter_status_id "
        "JOIN fundamental_delta_status sy ON sy.status_id=r.yoy_status_id "
        "WHERE r.package_id=? AND r.company_id=? AND r.fiscal_year=? AND r.fiscal_quarter=?",
        (package[0], company_id, fiscal_year, int(fiscal_quarter[1])),
    ).fetchone()
    if not row:
        return None
    total = dict(row)
    components = [dict(item) for item in analysis.execute(
        "SELECT c.*,t.component_name,t.maximum_points FROM fundamental_delta_component c "
        "JOIN fundamental_delta_component_type t USING(component_id) WHERE c.endpoint_id=? ORDER BY t.component_name",
        (row["endpoint_id"],),
    )]
    return {"total": total, "components": components}


def _diagnostic(repository: ParallelModelRepository, company_id: int, fiscal_year: int, fiscal_quarter: str, model_fingerprint: str) -> dict[str, Any] | None:
    row = repository.diagnostic_quarter(company_id, fiscal_year, int(fiscal_quarter[1]), model_fingerprint=model_fingerprint)
    if not row:
        return None
    output = dict(row)
    output["evaluations"] = [
        {**item, "status": item["status_text"], "reason_code": item["reason_text"]}
        for item in row["evaluations"]
    ]
    return output


def _relative(analysis: sqlite3.Connection, company_id: int, report_date: str, model_fingerprint: str) -> dict[str, Any]:
    metadata = analysis.execute(
        "SELECT s.* FROM relative_position_active_snapshot a JOIN relative_position_snapshot s USING(snapshot_id) WHERE a.model_fingerprint=?",
        (model_fingerprint,),
    ).fetchone()
    if not metadata or str(metadata["snapshot_date"]) > report_date:
        return {"available": False, "reason": "RELATIVE_SNAPSHOT_MISSING_OR_FUTURE", "metadata": dict(metadata) if metadata else None, "rows": [], "coverage": []}
    rows = [dict(row) for row in analysis.execute(
        "SELECT * FROM relative_position_result WHERE snapshot_id=? AND company_id=? ORDER BY measure,peer_scope,peer_group_id",
        (metadata["snapshot_id"], company_id),
    )]
    coverage = [dict(row) for row in analysis.execute(
        "SELECT * FROM relative_position_coverage WHERE snapshot_id=? AND company_id=? ORDER BY measure,peer_scope,peer_group_id",
        (metadata["snapshot_id"], company_id),
    )]
    for row in rows:
        row["snapshot_date"] = metadata["snapshot_date"]
        row["peer_group_name"] = (
            "Overall eligible universe"
            if row["peer_scope"] == "UNIVERSE"
            else str(row["peer_group_id"]).replace("_", " ").title()
        )
    return {"available": True, "reason": None, "metadata": dict(metadata), "rows": rows, "coverage": coverage}


def _source_state(
    analysis: sqlite3.Connection,
    base: Mapping[str, Any],
    model_map: Mapping[str, tuple[str, str]],
    package_fingerprint: str,
    *,
    candidate: bool = False,
) -> dict[str, Any]:
    state = dict(base)
    state["score"] = list(analysis.execute("SELECT COUNT(*),MAX(generated_at_utc),MAX(run_id) FROM score_result WHERE model_fingerprint=?", (model_map["score"][1],)).fetchone())
    state["lifecycle"] = list(analysis.execute("SELECT COUNT(*),MAX(generated_at_utc) FROM lifecycle_revised_result WHERE model_fingerprint=?", (model_map["lifecycle"][1],)).fetchone())
    state["valuation"] = list(analysis.execute("SELECT COUNT(*),MAX(calculated_at_utc) FROM valuation_revised_result WHERE model_fingerprint=?", (model_map["valuation"][1],)).fetchone())
    state["delta"] = list(analysis.execute("SELECT fundamental_source_fingerprint,fundamental_result_fingerprint,lifecycle_source_fingerprint,lifecycle_result_fingerprint,valuation_source_fingerprint,valuation_result_fingerprint,economic_package_fingerprint,physical_content_fingerprint,total_row_count,component_row_count FROM fundamental_delta_package WHERE model_fingerprint=?", (model_map["delta"][1],)).fetchone())
    state["relative"] = list(analysis.execute("SELECT s.snapshot_id,s.snapshot_date,s.calculation_source_fingerprint,s.source_content_fingerprint,s.result_fingerprint FROM relative_position_active_snapshot a JOIN relative_position_snapshot s USING(snapshot_id) WHERE a.model_fingerprint=?", (model_map["relative_position"][1],)).fetchone())
    state["diagnostic"] = list(analysis.execute("SELECT source_fingerprint,economic_result_fingerprint,physical_content_fingerprint,endpoint_count,evaluation_count FROM diagnostic_flag_package WHERE model_fingerprint=?", (model_map["diagnostic_flags"][1],)).fetchone())
    if candidate:
        state["candidate_package"] = [contract.FAMILY_FINGERPRINT, package_fingerprint]
        active = analysis.execute(
            "SELECT family_fingerprint,persistence_fingerprint "
            "FROM fundamentals_active_model_family WHERE singleton=1"
        ).fetchone()
        state["active_package"] = list(active) if active else None
    else:
        state["active_package"] = [contract.FAMILY_FINGERPRINT, package_fingerprint]
    return state


def _assemble_company_snapshot_v2(
    paths: v1.SnapshotPaths,
    *,
    ticker: str,
    report_date: str,
    candidate_model_map: Mapping[str, tuple[str, str]] | None = None,
    candidate_package_fingerprint: str | None = None,
    diagnostic_model_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = v1.assemble_company_snapshot(paths, ticker=ticker, report_date=report_date)
    with _readonly(paths.analysis_db) as analysis, _readonly(paths.market_db) as market:
        is_candidate = candidate_model_map is not None
        if is_candidate:
            if candidate_package_fingerprint is None or diagnostic_model_contract is None:
                raise ValueError("CANDIDATE_SNAPSHOT_IDENTITY_INCOMPLETE")
            model_map = dict(candidate_model_map)
            package_fingerprint = candidate_package_fingerprint
            ParallelModelRepository(analysis).assert_v2_bundle(
                model_map, persistence_fingerprint=package_fingerprint
            )
        else:
            assert_v2_active(analysis)
            model_map = active_model_manifest(analysis)
            package_fingerprint = str(
                analysis.execute(
                    "SELECT persistence_fingerprint FROM fundamentals_active_model_family WHERE singleton=1"
                ).fetchone()[0]
            )
        repository = ParallelModelRepository(analysis)
        company_id = int(base["identity"]["company_id"])
        score_rows = {int(row["quarter_id"]): _component_map(row) for row in repository.score_history(company_id, model_fingerprint=model_map["score"][1])}
        value_rows = {int(row["quarter_id"]): dict(row) for row in repository.valuation_history(company_id, model_fingerprint=model_map["valuation"][1])}
        canonical_by_sequence = {slot["fiscal_sequence"]: slot.get("ttm") for slot in base["history"] if slot.get("ttm")}
        for slot in base["history"]:
            qid = slot.get("quarter_id")
            slot["score"] = score_rows.get(qid)
            slot["valuation"] = value_rows.get(qid)
            if slot["valuation"] and slot["valuation"].get("fundamental_available_date", report_date) > report_date:
                slot["valuation"] = None
            slot["score_raw"] = _score_raw(slot["score"], slot.get("ttm"), canonical_by_sequence.get(slot["fiscal_sequence"] - 4))

        anchor = base["anchor"]
        canonical_anchor = base["history"][-1]["ttm"]
        lifecycle_rows = [row for row in repository.lifecycle_history(company_id, model_fingerprint=model_map["lifecycle"][1]) if not row.get("source_available_date") or row["source_available_date"] <= report_date]
        base["lifecycle"] = v1.lifecycle_presentation(lifecycle_rows, anchor_year=anchor["fiscal_year"], anchor_quarter=anchor["fiscal_quarter"])
        base["delta"] = _delta(analysis, company_id, anchor["fiscal_year"], anchor["fiscal_quarter"], model_map["delta"][1])
        base["current_price_valuation"] = _current_price_valuation(market, ticker=base["identity"]["ticker"], report_date=report_date, anchor=canonical_anchor, classification=base["identity"])
        base["valuation_multiples"] = _three_point_multiples(base["history"], base["current_price_valuation"])
        base["relative_position"] = _relative(analysis, company_id, report_date, model_map["relative_position"][1])
        base["diagnostic"] = _diagnostic(repository, company_id, anchor["fiscal_year"], anchor["fiscal_quarter"], model_map["diagnostic_flags"][1])
        base["diagnostic_counts"] = {status: 0 for status in ("EVALUATED_FLAGGED", "EVALUATED_CLEAR", "FLAG_NOT_READY", "FLAG_NOT_APPLICABLE")}
        for item in (base["diagnostic"] or {}).get("evaluations", []):
            base["diagnostic_counts"][item["status"]] = base["diagnostic_counts"].get(item["status"], 0) + 1
        for name, slot in (("yoy_base", base["history"][0]), ("previous", base["history"][3]), ("current", base["history"][4])):
            source = slot.get("ttm") or {}
            base["absolute_values"][name] = {key: source.get(key) for key in ("ttm_revenue", "ttm_operating_income", "ttm_operating_cashflow", "ttm_capex", "ttm_free_cashflow", "ttm_net_income_common")}
        base["absolute_values"]["current"].update({key: canonical_anchor.get(key) for key in ("cash", "total_debt", "total_assets", "accounts_receivable", "inventory", "accounts_payable", "deferred_revenue", "shares_outstanding")})
        base["absolute_values"]["current"]["net_debt"] = None if canonical_anchor.get("cash") is None or canonical_anchor.get("total_debt") is None else canonical_anchor["total_debt"] - canonical_anchor["cash"]
        wc = [canonical_anchor.get(key) for key in ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue")]
        base["absolute_values"]["current"]["operating_net_working_capital"] = None if any(value is None for value in wc) else wc[0] + wc[1] - wc[2] - wc[3]
        filing_values = [slot["valuation"]["total_valuation_score"] if slot.get("valuation") and slot["valuation"]["valuation_status"] == "VALUATION_FULL" else None for slot in base["history"][1:]]
        base["valuation_four_observation_average"] = v1.four_observation_average(filing_values)
        base["valuation_four_observation_count"] = sum(value is not None for value in filing_values)
        base["component_contract"] = {name: score.MODEL_CONTRACT["components"][name]["maximum"] for name in contract.COMPONENTS}
        base["model_fingerprints"] = {name: identity[1] for name, identity in model_map.items()}
        base["model_fingerprints"]["family"] = contract.FAMILY_FINGERPRINT
        base["report_contract"] = CANDIDATE_REPORT_CONTRACT if is_candidate else REPORT_CONTRACT
        base["report_presentation_fingerprint"] = (
            CANDIDATE_REPORT_PRESENTATION_FINGERPRINT
            if is_candidate else REPORT_PRESENTATION_FINGERPRINT
        )
        if is_candidate:
            base["diagnostic_model_contract"] = dict(diagnostic_model_contract)
            base["diagnostic_flag_names"] = list(diagnostic_model_contract["flags"])
        base["source_state"] = _source_state(
            analysis, base["source_state"], model_map, package_fingerprint,
            candidate=is_candidate,
        )
        base["source_state_fingerprint"] = hashlib.sha256(json.dumps(base["source_state"], sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        base["reconciliation"] = []
        for slot in base["history"]:
            scored = slot.get("score")
            if scored and scored["readiness_status"] == "SCORE_FULL":
                total = sum(item["component_score"] for item in scored["components"].values())
                base["reconciliation"].append({"name": f"v2_score:{slot['fiscal_year']}:{slot['fiscal_quarter']}", "ok": math.isclose(total, scored["total_score"], abs_tol=1e-9)})
        for context in base["valuation_multiples"]["contexts"]:
            for check in context["reconciliation"]:
                base["reconciliation"].append({
                    "name": f"v2_valuation:{context['evaluation_point']}:{check['name']}",
                    "ok": check["ok"],
                })
        if any(not row["ok"] for row in base["reconciliation"]):
            raise RuntimeError("SNAPSHOT_V2_RECONCILIATION_FAILED")
    return base


def assemble_company_snapshot_v2(paths: v1.SnapshotPaths, *, ticker: str, report_date: str) -> dict[str, Any]:
    return _assemble_company_snapshot_v2(paths, ticker=ticker, report_date=report_date)


def assemble_company_snapshot_v2_candidate(
    paths: v1.SnapshotPaths,
    *,
    ticker: str,
    report_date: str,
    model_map: Mapping[str, tuple[str, str]],
    package_fingerprint: str,
    diagnostic_model_contract: Mapping[str, Any],
) -> dict[str, Any]:
    return _assemble_company_snapshot_v2(
        paths,
        ticker=ticker,
        report_date=report_date,
        candidate_model_map=model_map,
        candidate_package_fingerprint=package_fingerprint,
        diagnostic_model_contract=diagnostic_model_contract,
    )
