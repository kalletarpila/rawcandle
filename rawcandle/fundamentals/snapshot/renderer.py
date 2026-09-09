from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2.diagnostic_flags import (
    FLAG_NAMES as DIAGNOSTIC_FLAG_NAMES,
    MODEL_CONTRACT as DIAGNOSTIC_MODEL_CONTRACT,
    REVENUE_SCALE_FLOOR,
)
from rawcandle.fundamentals.score.engine import COMPONENTS
from rawcandle.fundamentals.snapshot.assembler import (
    COMPONENT_LABELS,
    CURRENT_PRICE_LABEL,
    REPORT_CONTRACT,
)
from rawcandle.fundamentals.relative_valuation.contract import (
    CANDIDATE_REPORT_CONTRACT as RELATIVE_VALUATION_CANDIDATE_REPORT_CONTRACT,
    PRODUCTION_REPORT_CONTRACT as RELATIVE_VALUATION_PRODUCTION_REPORT_CONTRACT,
)


SUPPORTED_REPORT_CONTRACTS = {
    REPORT_CONTRACT,
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V2",
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V3",
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V4",
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V5",
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V6",
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V7",
    RELATIVE_VALUATION_CANDIDATE_REPORT_CONTRACT,
    RELATIVE_VALUATION_PRODUCTION_REPORT_CONTRACT,
}


DIAGNOSTIC_METRIC_DISPLAY_UNITS = {
    "ABRUPT_FUNDAMENTAL_SHIFT": "PERCENT",
    "EARNINGS_CASH_DIVERGENCE_CANDIDATE": "PERCENT",
    "CAPEX_INTENSITY_SHIFT_CANDIDATE": "PERCENTAGE_POINTS",
    "NET_DEBT_SHIFT_CANDIDATE": "PERCENT",
    "VALUATION_YIELD_OUTLIER": "PERCENT",
    "RECENT_MARGIN_DECELERATION_REVIEW": "PERCENTAGE_POINTS",
    "WORKING_CAPITAL_SHIFT_CANDIDATE": "PERCENT",
    "NON_OPERATING_EARNINGS_GAP_CANDIDATE": "PERCENT",
}


FINGERPRINT_PLACEHOLDER = "REPORT_CONTENT_SHA256_V1"
HISTORY_HEADERS = ("t−4 (YoY comparison)", "t−3", "t−2", "t−1", "Nykyinen")


@dataclass(frozen=True)
class RenderedSnapshot:
    markdown: str
    content_fingerprint: str


def _text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    if abs(number) < 0.5 * 10 ** (-decimals):
        number = 0.0
    return f"{number:.{decimals}f}"


def _score(value: Any) -> str:
    return _number(value, 2)


def _percentage(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    number = float(value)
    if math.isfinite(number) and abs(number) < 0.5 * 10 ** (-decimals) / 100:
        number = 0.0
    return "—" if not math.isfinite(number) else f"{number * 100:.{decimals}f} %"


def _percentile(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if math.isfinite(number) and abs(number) < 0.005:
        number = 0.0
    return "—" if not math.isfinite(number) else f"{number:.2f} %"


def _pp(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    number = float(value)
    if math.isfinite(number) and abs(number) < 0.00005:
        number = 0.0
    if not math.isfinite(number):
        return "—"
    if number == 0.0:
        return "0.00 pp"
    rendered = f"{number * 100:+.2f} pp" if signed else f"{number * 100:.2f} pp"
    return rendered.replace("-", "−") if signed else rendered


def _multiple(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if math.isfinite(number) and abs(number) < 0.005:
        number = 0.0
    return "—" if not math.isfinite(number) else f"{number:.2f}x"


def _money(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if not math.isfinite(number):
        return "—"
    absolute = abs(number)
    if absolute < 5_000:
        number = 0.0
    absolute = abs(number)
    if absolute >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f} B"
    return f"{number / 1_000_000:.2f} M"


def _price(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if math.isfinite(number) and abs(number) < 0.005:
        number = 0.0
    return "—" if not math.isfinite(number) else f"{number:.2f}"


def _valuation_metric(
    context: Mapping[str, Any], key: str, formatter: Any
) -> str:
    metric = context["metrics"][key]
    if metric["status"] == "N_A":
        return "N/A"
    if metric["status"] == "N_M":
        return "N/M"
    rendered = formatter(metric["value"])
    currency = context.get("price_currency")
    if key in {"market_cap", "enterprise_value"} and currency:
        return f"{rendered} {currency}"
    return rendered


def _valuation_context_quarter(context: Mapping[str, Any]) -> str:
    if context.get("fiscal_year") is None or not context.get("fiscal_quarter"):
        return "N/A"
    return f"FY{context['fiscal_year']} {context['fiscal_quarter']}"


def _basis_text(value: Any) -> str:
    return "N/A" if value is None or value == "" else _text(value)


def _basis_number(value: Any, formatter: Any) -> str:
    return "N/A" if value is None else formatter(value)


def _valuation_yield(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if not math.isfinite(number):
        return "—"
    percentage = number * 100
    decimals = 4 if 0 < abs(percentage) < 0.01 else 2
    if abs(percentage) < 0.5 * 10 ** (-decimals):
        percentage = 0.0
    return f"{percentage:.{decimals}f} %"


def _signed_score(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if not math.isfinite(number):
        return "—"
    if abs(number) < 0.005:
        return "0.00"
    return f"{number:+.2f}"


def _score_point_change(value: Any) -> str:
    rendered = _signed_score(value)
    return rendered if rendered == "—" else f"{rendered} p"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]], aligns: Sequence[str] | None = None) -> str:
    if aligns is None:
        aligns = ["left"] + ["right"] * (len(headers) - 1)
    separators = {"left": "---", "right": "---:", "center": ":---:"}
    lines = [
        "| " + " | ".join(_text(value) for value in headers) + " |",
        "| " + " | ".join(separators[value] for value in aligns) + " |",
    ]
    lines.extend("| " + " | ".join(_text(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _history_values(snapshot: Mapping[str, Any], getter: Any) -> list[str]:
    return [getter(slot) for slot in snapshot["history"]]


def _source_item(snapshot: Mapping[str, Any], source: str, index: int) -> Any:
    values = snapshot.get("source_state", {}).get(source) or []
    return values[index] if index < len(values) else None


def _relative_cell(relative: Mapping[str, Any], measure: str, scope: str) -> str:
    if not relative.get("available"):
        return f"— ({relative.get('reason', 'UNAVAILABLE')})"
    rows = [row for row in relative.get("rows", []) if row["measure"] == measure and row["peer_scope"] == scope]
    if rows:
        return "; ".join(
            f"{_percentile(row['percentile'])} (n={row['peer_count']}; {_text(row.get('peer_group_name') or row['peer_group_id'])}; {row['snapshot_date']})"
            for row in rows
        )
    coverage = [row for row in relative.get("coverage", []) if row["measure"] == measure and row["peer_scope"] == scope]
    if coverage:
        return "; ".join(f"— ({row['coverage_status']}; {row['reason_code']})" for row in coverage)
    return "— (NO_COVERAGE_RECORD)"


def _relative_valuation_sections(snapshot: Mapping[str, Any]) -> list[str]:
    value = snapshot.get("relative_valuation")
    if not value:
        unavailable = snapshot.get("relative_valuation_unavailable")
        if unavailable:
            eligible = unavailable.get("eligible_snapshot_date") or "—"
            return [
                "## Relative Valuation",
                "",
                "Relative Valuation ei ole saatavilla tämän raportin päivämäärälle.",
                "",
                f"Status: `{unavailable.get('reason_code')}`. Pyydetty as-of: "
                f"`{unavailable.get('requested_as_of_date')}`; kelvollinen snapshot: `{eligible}`.",
                "",
                "Yksittäinen raporttipyyntö ei käynnistä koko universumin uudelleenlaskentaa.",
                "",
            ]
        return []
    current = value.get("current_valuation") or {}
    filing = value.get("filing_valuation") or {}
    current_results = value.get("current_peer_results") or []
    current_coverage = value.get("current_peer_coverage") or []
    filing_results = value.get("filing_peer_results") or []

    def rows_for(rows: Sequence[Mapping[str, Any]], scope: str) -> list[Mapping[str, Any]]:
        return [row for row in rows if str(row.get("peer_scope")) == scope]

    def peer_cell(scope: str) -> tuple[str, str, str, str]:
        current_rows = rows_for(current_results, scope)
        filing_rows = rows_for(filing_results, scope)
        coverage_rows = rows_for(current_coverage, scope)
        current_row = current_rows[0] if current_rows else None
        filing_row = filing_rows[0] if filing_rows else None
        current_value = current_row.get("percentile") if current_row else None
        filing_value = filing_row.get("percentile") if filing_row else None
        difference = (
            float(current_value) - float(filing_value)
            if current_value is not None and filing_value is not None
            else None
        )
        if current_row:
            status = f"{current_row.get('status')} / n={current_row.get('peer_count')}"
        elif coverage_rows:
            status = "; ".join(
                f"{row.get('status')} / {row.get('reason_code')}"
                for row in coverage_rows
            )
        else:
            status = "NO_COVERAGE_RECORD"
        return _percentile(filing_value), _percentile(current_value), _signed_score(difference), status

    own = value["own_history"]
    component_labels = {
        "OPERATING_YIELD": "Operating Income / EV",
        "FCF_YIELD": "FCF / Market Cap",
        "REPORTED_EARNINGS_YIELD": "Reported Common Earnings / Market Cap",
    }
    component_rows = []
    for row in own["components"]:
        start, end = row.get("positive_history_start_date"), row.get("positive_history_end_date")
        span = f"{start} – {end}" if start and end else "—"
        component_rows.append(
            (
                component_labels[row["component"]],
                _percentage(row.get("current_yield")),
                _percentage(row.get("historical_median_positive_yield")),
                _percentile(row.get("historical_percentile")),
                row.get("positive_history_count"),
                span,
                f"{row.get('component_history_status')} / {row.get('reason_code')}",
            )
        )
    identity = snapshot.get("relative_valuation_identity") or {}
    snapshot_date = identity.get("as_of_date") or "—"
    persisted_price_date = current.get("price_date") or "—"
    report_price_date = (
        (snapshot.get("current_price_valuation") or {}).get("price_date") or "—"
    )
    readiness_requirement = {
        "READY": "READY: ≥12 per component",
        "LIMITED_HISTORY": (
            "LIMITED_HISTORY: ≥8 per component; at least one component has 8–11"
        ),
    }.get(
        str(own.get("status")),
        "Aggregate: ≥8 per component; READY: ≥12 per component",
    )
    production_context = (
        [
            f"Relative Valuation snapshot date: `{snapshot_date}`; "
            f"source fingerprint: `{identity.get('source_fingerprint')}`; "
            f"result fingerprint: `{identity.get('result_fingerprint')}`.",
            "",
        ]
        if snapshot.get("report_contract") == RELATIVE_VALUATION_PRODUCTION_REPORT_CONTRACT
        else []
    )
    return [
        "## Relative Valuation",
        "",
        f"Report date: `{snapshot['report_date']}`. Historia on nykyisin revisioitu, ei PIT-rekonstruktio.",
        "",
        *production_context,
        f"Relative Valuation laskettiin tallennetussa snapshotissa `{snapshot_date}` "
        f"yhtiön `{persisted_price_date}` päivän hinnalla. Raportin erillinen "
        f"Indicative current-price valuation käyttää `{report_price_date}` päivän hintaa. "
        "Peer-persentiilejä ei ole laskettu uudelleen tällä raporttihinnalla.",
        "",
        "Snapshot date on laskennan as-of-päivä ja yhtiön snapshot-hintapäivä on "
        "laskentaan valittu markkinahavainto. Peer-yhtiöillä on saman snapshotin "
        "säännöillä johdonmukaisesti valitut omat hintapäivänsä. Yhden yhtiön hinnan "
        "vaihtaminen ilman koko peer-snapshotin uudelleenrakennusta ei tuota "
        "kelvollista uutta peer-persentiiliä.",
        "",
        _table(
            ("Mittari", "Saatavuuspäivän konteksti", "Snapshot-hintainen", "Muutos"),
            (
                ("Snapshot-price Absolute Valuation Score", _score(filing.get("total_valuation_score")), _score(current.get("total_valuation_score")), _score_point_change(value.get("score_change_due_to_current_price"))),
                ("Price date", filing.get("price_date"), current.get("price_date"), "—"),
                ("Price age", filing.get("price_age_calendar_days"), current.get("price_age_calendar_days"), "—"),
            ),
        ),
        "",
        f"### Persisted peer comparison — snapshot {snapshot_date}",
        "",
        _table(
            ("Peer scope", "Filing percentile", "Snapshot percentile", "Snapshot − filing", "Snapshot status / peers"),
            tuple((scope.title(), *peer_cell(scope)) for scope in ("UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM")),
            ("left", "right", "right", "right", "left"),
        ),
        "",
        "### Own positive-yield history",
        "",
        _table(
            ("Own-History Valuation Percentile", "Status", "Five-year window", "Smallest component history count", "Readiness requirement", "Fiscal gaps"),
            ((
                _percentile(own.get("percentile")),
                f"{own.get('status')} / {own.get('reason_code')}",
                f"{own.get('window_start_date')} – {own.get('window_end_date')}",
                own.get("minimum_component_positive_history_count"),
                readiness_requirement,
                own.get("fiscal_gap_count"),
            ),),
            ("right", "left", "left", "right", "left", "right"),
        ),
        "",
        _table(
            ("Component", "Current yield", "Positive-history median", "Percentile", "Positive observations", "Positive-history span", "Status"),
            tuple(component_rows),
            ("left", "right", "right", "right", "right", "left", "left"),
        ),
        "",
        "Own-History Valuation Percentile = 40% × Operating Income / EV history "
        "percentile + 40% × FCF / Market Cap history percentile + 20% × Reported "
        "Common Earnings / Market Cap history percentile.",
        "",
        "Jokainen komponenttihistoria arvioidaan itsenäisesti mallin enintään viiden "
        "vuoden ja 20 endpointin ikkunassa. Kukin endpoint käyttää sen "
        "saatavuuspäivälle valittua kelvollista markkinahintaa. Vain havaittu, "
        "äärellinen ja aidosti positiivinen yield hyväksytään; puuttuva, nolla, "
        "negatiivinen, virheellinen tai muuten kelpaamaton havainto suljetaan pois, "
        "eikä sitä muuteta nollaksi.",
        "",
        "READY vaatii vähintään 12 hyväksyttyä positiivista havaintoa jokaiselle "
        "komponentille. LIMITED_HISTORY vaatii vähintään 8 jokaiselle ja 8–11 "
        "vähintään yhdelle. Aggregate-persentiiliä ei tuoteta, jos yhdelläkin "
        "komponentilla on alle 8 havaintoa tai nyky-yield puuttuu, ei ole äärellinen "
        "tai on enintään nolla.",
        "",
        "> A high peer percentile means the company is cheap relative to eligible peers in the persisted snapshot. A high own-history percentile means the company is cheap relative to its accepted positive history. It is not a percentage discount, probability of price appreciation, or forecast, and neither measure implies fundamental strength.",
        "",
    ]


def _filing_delta(history: Sequence[Mapping[str, Any]], key: str, lag: int) -> float | None:
    current = history[-1].get("valuation")
    prior = history[-1 - lag].get("valuation")
    if not current or not prior:
        return None
    if current["valuation_status"] != "VALUATION_FULL" or prior["valuation_status"] != "VALUATION_FULL":
        return None
    if current.get(key) is None or prior.get(key) is None:
        return None
    return float(current[key]) - float(prior[key])


def _filing_price_change(
    history: Sequence[Mapping[str, Any]], lag: int
) -> tuple[float | None, float | None]:
    current = history[-1].get("valuation")
    prior = history[-1 - lag].get("valuation")
    if not current or not prior:
        return None, None
    if current["valuation_status"] != "VALUATION_FULL" or prior["valuation_status"] != "VALUATION_FULL":
        return None, None
    current_price = current.get("selected_price")
    prior_price = prior.get("selected_price")
    if current_price is None or prior_price is None or float(prior_price) <= 0:
        return None, None
    absolute = float(current_price) - float(prior_price)
    return absolute, absolute / float(prior_price)


def _at_ceiling(value: Any, maximum: Any) -> bool:
    return value is not None and maximum is not None and math.isclose(
        float(value), float(maximum), abs_tol=1e-9
    )


def _score_ceiling_components(snapshot: Mapping[str, Any]) -> list[str]:
    score = snapshot["history"][-1].get("score") or {}
    components = score.get("components") or {}
    names = tuple(snapshot["component_contract"])
    labels = {
        **COMPONENT_LABELS,
        "OPERATING_PROFITABILITY": "Operating Profitability",
        "OPERATING_MARGIN_DIRECTION": "Operating Margin Direction",
        "BALANCE_SHEET_RESILIENCE": "Balance Sheet Resilience",
        "FCF_MARGIN": "FCF Margin",
    }
    return [
        labels[name]
        for name in names
        if _at_ceiling(
            components.get(name, {}).get("component_score"),
            snapshot["component_contract"].get(name),
        )
    ]


def _valuation_ceiling_components(valuation: Mapping[str, Any]) -> list[str]:
    operating_key = "operating_income_points" if "operating_income_points" in valuation else "ebit_points"
    operating_label = "Operating Income / EV" if operating_key.startswith("operating") else "EBIT / EV"
    return [
        label
        for key, maximum, label in (
            (operating_key, 40.0, operating_label),
            ("fcf_points", 40.0, "FCF / Market Cap"),
            (
                "earnings_points",
                20.0,
                "Reported Common Earnings / Market Cap"
                if operating_key.startswith("operating")
                else "Common earnings / Market Cap",
            ),
        )
        if _at_ceiling(valuation.get(key), maximum)
    ]


def _base_effect_observations(snapshot: Mapping[str, Any]) -> list[str]:
    observations = []
    for slot in snapshot["history"]:
        raw = slot["score_raw"]
        growth = raw.get("revenue_growth_yoy_ttm")
        base = raw.get("revenue_growth_comparison_base")
        current = (slot.get("ttm") or {}).get("ttm_revenue")
        if growth is None or base is None or current is None:
            continue
        threshold = max(10_000_000.0, abs(float(current)) * 0.10)
        if abs(float(growth)) >= 1.0 and abs(float(base)) < threshold:
            observations.append(
                f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}: kasvu {_percentage(growth)}, "
                f"vertailupohja {_money(base)} (raja {_money(threshold)})"
            )
    return observations


def _transition_text(status: str) -> str:
    if status.startswith("PENDING_"):
        body = status.removeprefix("PENDING_")
        state, suffix = body.split("_1_OF_2", 1)
        replacement = ""
        if suffix.startswith("; REPLACED_"):
            replacement = f"; korvasi ehdokkaan {suffix.removeprefix('; REPLACED_')}"
        return f"Odottaa: {state} (1/2){replacement}"
    if status.startswith("CONFIRMED_"):
        return f"Vahvistui: {status.removeprefix('CONFIRMED_').removesuffix('_2_OF_2')} (2/2)"
    return {
        "NO_PENDING_TRANSITION": "Ei odottavaa siirtymää",
        "NO_LIFECYCLE_OBSERVATION": "Ei lifecycle-havaintoa",
        "LIFECYCLE_NOT_READY": "Lifecycle ei valmis",
        "CANDIDATE_CLEARED_BY_UNCLASSIFIED": "Ehdokas nollautui: UNCLASSIFIED",
        "IMMEDIATE_DISTRESSED_ENTRY": "DISTRESSED astui voimaan välittömästi",
    }.get(status, status)


def _balance_raw(raw: Mapping[str, Any]) -> str:
    branch = raw.get("balance_sheet_branch")
    value = raw.get("balance_sheet_value")
    if branch in {"NET_DEBT_TO_EBIT", "NET_DEBT_TO_OPERATING_INCOME"}:
        if value is not None and float(value) < 0:
            label = "NET_CASH_TO_OPERATING_INCOME" if branch.endswith("OPERATING_INCOME") else "NET_CASH_TO_EBIT"
            return f"{label}: {_multiple(abs(float(value)))}"
        return f"{branch}: {_multiple(value)}"
    if branch:
        return f"{branch}: {_money(value)}"
    return "NOT_READY"


DIAGNOSTIC_LABELS = {
    "ABRUPT_FUNDAMENTAL_SHIFT": "Abrupt Fundamental Shift",
    "EARNINGS_CASH_DIVERGENCE_CANDIDATE": "Earnings-Cash Divergence",
    "CAPEX_INTENSITY_SHIFT_CANDIDATE": "Capex Intensity Shift",
    "NET_DEBT_SHIFT_CANDIDATE": "Net Debt Shift",
    "VALUATION_YIELD_OUTLIER": "Valuation Yield Outlier",
    "RECENT_MARGIN_DECELERATION_REVIEW": "Recent Margin Deceleration",
    "WORKING_CAPITAL_SHIFT_CANDIDATE": "Working Capital Shift",
    "NON_OPERATING_EARNINGS_GAP_CANDIDATE": "Non-Operating Earnings Gap",
}


@dataclass(frozen=True)
class DiagnosticDefinition:
    flag_name: str
    comparison: str
    measurement: str
    trigger: str
    engine_rule: str


def _definition_percent(value: float) -> str:
    return f"{value * 100:g} %".replace("-", "−")


def _definition_operator(value: str) -> str:
    return {">=": "≥", "<=": "≤"}.get(value, value)


def _build_diagnostic_definitions(
    model_contract: Mapping[str, Any] = DIAGNOSTIC_MODEL_CONTRACT,
    flag_names: Sequence[str] = DIAGNOSTIC_FLAG_NAMES,
) -> tuple[DiagnosticDefinition, ...]:
    definitions = model_contract["definitions"]
    abrupt = definitions["ABRUPT_FUNDAMENTAL_SHIFT"]
    earnings_cash = definitions["EARNINGS_CASH_DIVERGENCE_CANDIDATE"]
    capex = definitions["CAPEX_INTENSITY_SHIFT_CANDIDATE"]
    net_debt = definitions["NET_DEBT_SHIFT_CANDIDATE"]
    valuation = definitions["VALUATION_YIELD_OUTLIER"]
    margin = definitions["RECENT_MARGIN_DECELERATION_REVIEW"]
    working_capital = definitions["WORKING_CAPITAL_SHIFT_CANDIDATE"]
    floor_millions = REVENUE_SCALE_FLOOR / 1_000_000

    rows = [
        DiagnosticDefinition(
            "ABRUPT_FUNDAMENTAL_SHIFT",
            "Nykyinen TTM vs tarkka fiscal Q−1",
            "Suurempi arvoista |Δ liikevaihto|/R ja |Δ Operating Income|/R; "
            f"R = max(keskimääräinen |liikevaihto|, {floor_millions:g} M$)",
            f"{_definition_operator(abrupt['operator'])} {_definition_percent(abrupt['threshold'])}; "
            "jompikumpi muutos, liikevaihdot > 0 ja tuettu operatiivinen malli",
            "_abrupt",
        ),
        DiagnosticDefinition(
            "EARNINGS_CASH_DIVERGENCE_CANDIDATE",
            "Nykyinen TTM vs tarkka fiscal Q−1",
            "|Δ Reported Common Earnings − Δ operating cash flow|/R; "
            f"R = max(keskimääräinen |liikevaihto|, {floor_millions:g} M$)",
            f"{_definition_operator(earnings_cash['operator'])} {_definition_percent(earnings_cash['threshold'])}; "
            "liikevaihdot > 0 ja tuettu operatiivinen malli",
            "_earnings_cash",
        ),
        DiagnosticDefinition(
            "CAPEX_INTENSITY_SHIFT_CANDIDATE",
            "Nykyinen TTM vs tarkka fiscal Q−1",
            "Intensiteettien itseisarvoero; intensiteetti = "
            f"|CAPEX|/max(liikevaihto, {floor_millions:g} M$) kummallekin kaudelle",
            f"{_definition_operator(capex['operator'])} {_definition_percent(capex['threshold']).replace(' %', ' pp')}; "
            "liikevaihdot > 0 ja tuettu operatiivinen malli",
            "_capex",
        ),
        DiagnosticDefinition(
            "NET_DEBT_SHIFT_CANDIDATE",
            "Nykyinen TTM vs tarkka fiscal Q−1",
            "|Δ(kokonaisvelka − kassa)|/R; "
            f"R = max(keskimääräinen |liikevaihto|, {floor_millions:g} M$)",
            f"{_definition_operator(net_debt['operator'])} {_definition_percent(net_debt['threshold'])}; "
            "liikevaihdot > 0 ja tuettu operatiivinen malli",
            "_net_debt",
        ),
        DiagnosticDefinition(
            "VALUATION_YIELD_OUTLIER",
            "Nykyinen valuation-endpoint; ei Q−1-vertailua",
            "Saatavilla olevien raw-yieldien mediaani ja maksimi: Operating Income/EV, "
            "FCF/Market Cap ja Reported Common Earnings/Market Cap",
            f"mediaani {_definition_operator(valuation['operators'][0])} {_definition_percent(valuation['thresholds'][0])} TAI "
            f"maksimi {_definition_operator(valuation['operators'][1])} {_definition_percent(valuation['thresholds'][1])}; "
            "VALUATION_FULL ja soveltuva luokitus",
            "_valuation",
        ),
        DiagnosticDefinition(
            "RECENT_MARGIN_DECELERATION_REVIEW",
            "Nykyinen TTM vs tarkka fiscal Q−1",
            "Suunnallinen muutos Operating Marginissa "
            "(Operating Income/liikevaihto); nykyinen Trajectory",
            f"Trajectory {_definition_operator(margin['operators'][0])} {margin['thresholds'][0]:g} JA muutos "
            f"{_definition_operator(margin['operators'][1])} {_definition_percent(margin['thresholds'][1]).replace(' %', ' pp')}; "
            "liikevaihdot > 0, Operating Income saa olla negatiivinen, tuettu operatiivinen malli",
            "_margin",
        ),
        DiagnosticDefinition(
            "WORKING_CAPITAL_SHIFT_CANDIDATE",
            "Nykyinen canonical-kausi vs tarkka fiscal Q−1",
            "|ΔONWC|/max(keskimääräinen taseen loppusumma, "
            f"{floor_millions:g} M$); ONWC = myyntisaamiset + varasto − ostovelat − saadut ennakot",
            f"{_definition_operator(working_capital['operator'])} {_definition_percent(working_capital['threshold'])}; "
            "molemmat taseen loppusummat > 0 ja tuettu operatiivinen malli",
            "_working_capital",
        ),
    ]
    if "NON_OPERATING_EARNINGS_GAP_CANDIDATE" in flag_names:
        gap = definitions["NON_OPERATING_EARNINGS_GAP_CANDIDATE"]
        rows.append(DiagnosticDefinition(
            "NON_OPERATING_EARNINGS_GAP_CANDIDATE",
            "Nykyinen yhtenäinen TTM-endpoint; ei Q−1-vertailua",
            "|TTM EBIT − TTM Operating Income| / "
            f"max(TTM-liikevaihto, {floor_millions:g} M$); suunnallinen erotus säilytetään",
            f"{_definition_operator(gap['operator'])} {_definition_percent(gap['threshold'])}; "
            "TTM-liikevaihto > 0 ja tuettu operatiivinen malli",
            "_non_operating_gap",
        ))
    rows_tuple = tuple(rows)
    if tuple(row.flag_name for row in rows_tuple) != tuple(flag_names):
        raise RuntimeError("DIAGNOSTIC_DEFINITION_FLAG_CONTRACT_MISMATCH")
    return rows_tuple


DIAGNOSTIC_DEFINITIONS = _build_diagnostic_definitions()

ALL_DIAGNOSTICS_CLEAR_TEXT = (
    "Mikään seitsemästä arvioidusta tarkastusehdosta ei täyty. Tämä ei tarkoita, "
    "ettei yhtiössä olisi muita analysoitavia riskejä tai poikkeavia eriä."
)
INCOMPLETE_DIAGNOSTIC_COVERAGE_TEXT = (
    "Yksikään laskentavalmis tarkastusehto ei täyty. Kaikkia seitsemää ehtoa ei "
    "voitu välttämättä arvioida tai ne eivät kaikki sovellu tähän yhtiöön. Tämä ei "
    "tarkoita, ettei yhtiössä olisi muita analysoitavia riskejä tai poikkeavia eriä."
)
DIAGNOSTIC_COVERAGE_TEXT = (
    "Diagnostiikka kattaa vain alla määritellyt numeeriset tarkastusehdot eikä ole "
    "täydellinen kirjanpito- tai riskianalyysi."
)


def _zero_diagnostic_text(
    evaluations: Sequence[Mapping[str, Any]],
    flag_names: Sequence[str] = DIAGNOSTIC_FLAG_NAMES,
) -> str:
    all_clear = (
        len(evaluations) == len(flag_names)
        and all(row.get("status") == "EVALUATED_CLEAR" for row in evaluations)
    )
    if len(flag_names) == 8:
        return (
            "Mikään kahdeksasta arvioidusta tarkastusehdosta ei täyty. Tämä ei sulje pois "
            "muita riskejä tai ehtoja, joita ei voitu arvioida."
            if all_clear else
            "Yksikään laskentavalmis tarkastusehto ei täyty. Kaikkia kahdeksaa ehtoa ei "
            "voitu välttämättä arvioida tai ne eivät kaikki sovellu tähän yhtiöön. Tämä ei "
            "sulje pois muita riskejä tai ehtoja, joita ei voitu arvioida."
        )
    return ALL_DIAGNOSTICS_CLEAR_TEXT if all_clear else INCOMPLETE_DIAGNOSTIC_COVERAGE_TEXT

DIAGNOSTIC_REASON_EXPLANATIONS = {
    "ABRUPT_SHIFT_THRESHOLD_MET": "Fundamentaalisen muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas.",
    "ABRUPT_SHIFT_BELOW_THRESHOLD": "Fundamentaalinen muutos jäi tarkastusrajan alle.",
    "EARNINGS_CASH_DIVERGENCE_THRESHOLD_MET": "Tulos- ja kassavirtamuutosten eron tarkastusraja täyttyi; havainto on tarkastettava ehdokas.",
    "EARNINGS_CASH_DIVERGENCE_BELOW_THRESHOLD": "Tulos- ja kassavirtamuutosten ero jäi tarkastusrajan alle.",
    "CAPEX_INTENSITY_SHIFT_THRESHOLD_MET": "CAPEX-intensiteetin muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas.",
    "CAPEX_INTENSITY_SHIFT_BELOW_THRESHOLD": "CAPEX-intensiteetin muutos jäi tarkastusrajan alle.",
    "NET_DEBT_SHIFT_THRESHOLD_MET": "Nettovelan muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas.",
    "NET_DEBT_SHIFT_BELOW_THRESHOLD": "Nettovelan muutos jäi tarkastusrajan alle.",
    "VALUATION_YIELD_OUTLIER_THRESHOLD_MET": "Vähintään yksi valuation-yieldin poikkeamaraja täyttyi; havainto on tarkastettava ehdokas.",
    "VALUATION_YIELDS_BELOW_THRESHOLDS": "Valuation-yieldit jäivät poikkeamarajojen alle.",
    "VALUATION_YIELD_NON_FINITE": "Vähintään yksi tarvittava valuation-yield ei ole äärellinen.",
    "VALUATION_YIELDS_MISSING": "Vähintään yksi tarvittava valuation-yield puuttuu.",
    "VALUATION_SOURCE_NOT_READY": "Valuation-lähdetulos ei ole laskentavalmis.",
    "VALUATION_NOT_APPLICABLE": "Valuation-malli ei sovellu tähän kirjanpitoluokkaan.",
    "RECENT_MARGIN_DECELERATION_THRESHOLD_MET": "Trajectory- ja marginaaliehdot täyttyivät yhdessä; havainto on tarkastettava ehdokas.",
    "RECENT_MARGIN_DECELERATION_CONDITION_CLEAR": "Trajectory- ja marginaaliehdot eivät yhdessä täyttäneet tarkastusehtoa.",
    "WORKING_CAPITAL_SHIFT_THRESHOLD_MET": "Käyttöpääoman muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas.",
    "WORKING_CAPITAL_SHIFT_BELOW_THRESHOLD": "Käyttöpääoman muutos jäi tarkastusrajan alle.",
    "PRIOR_FISCAL_ENDPOINT_MISSING": "Tarkkaan edeltävä fiscal-endpoint puuttuu.",
    "NON_CONSECUTIVE_FISCAL_CHAIN": "Fiscal-ketju ei ole katkeamaton.",
    "REQUIRED_INPUT_MISSING": "Vähintään yksi lipun vaatima lähdearvo puuttuu.",
    "REQUIRED_INPUT_NON_FINITE": "Vähintään yksi lipun vaatima lähdearvo ei ole äärellinen.",
    "NONPOSITIVE_REVENUE": "Lippu ei sovellu, koska vaadittu liikevaihdon nimittäjä ei ole positiivinen.",
    "TOTAL_ASSETS_NOT_STRICTLY_POSITIVE": "Laskentaa ei voida tehdä, koska taseen loppusumma ei ole aidosti positiivinen.",
    "ACCOUNTING_CLASS_NOT_APPLICABLE": "Lippu ei sovellu tähän tuettujen mallien ulkopuoliseen kirjanpitoluokkaan.",
    "APPLICABILITY_NOT_READY": "Soveltuvuusluokitus ei ole käytettävissä.",
}

CANDIDATE_DIAGNOSTIC_REASON_EXPLANATIONS = {
    "NON_OPERATING_EARNINGS_GAP_THRESHOLD_MET": "EBITin ja Operating Incomen välinen suhteellinen ero täytti tarkastusrajan; erittely on tarkastettava ennen nettotulospohjaisen arvostuksen tulkintaa.",
    "NON_OPERATING_EARNINGS_GAP_BELOW_THRESHOLD": "EBITin ja Operating Incomen välinen suhteellinen ero jäi tarkastusrajan alle.",
    "TTM_EBIT_MISSING": "TTM EBIT puuttuu.",
    "TTM_EBIT_NON_FINITE": "TTM EBIT ei ole äärellinen.",
    "TTM_OPERATING_INCOME_MISSING": "TTM Operating Income puuttuu.",
    "TTM_OPERATING_INCOME_NON_FINITE": "TTM Operating Income ei ole äärellinen.",
    "TTM_REVENUE_MISSING": "TTM-liikevaihto puuttuu.",
    "TTM_REVENUE_NON_FINITE": "TTM-liikevaihto ei ole äärellinen.",
    "TTM_REVENUE_NONPOSITIVE": "Lippu ei ole laskentavalmis, koska TTM-liikevaihto ei ole aidosti positiivinen.",
    "TTM_ENDPOINT_INCOHERENT": "TTM-tulosluvut eivät kuulu samaan yhtenäiseen endpointiin.",
}

UNKNOWN_DIAGNOSTIC_EXPLANATION = "Tarkempaa käyttäjäselitettä ei ole saatavilla."


def diagnostic_explanation(evaluation: Mapping[str, Any]) -> str:
    reason = str(evaluation.get("reason_code"))
    return DIAGNOSTIC_REASON_EXPLANATIONS.get(
        reason, CANDIDATE_DIAGNOSTIC_REASON_EXPLANATIONS.get(
            reason, UNKNOWN_DIAGNOSTIC_EXPLANATION
        )
    )


def _diagnostic_evidence(evaluation: Mapping[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    flag = evaluation["flag_name"]
    abrupt_fields = (
        (("revenue_shift_ratio", "Revenue shift"), ("operating_income_shift_ratio", "Operating Income shift"))
        if "operating_income_shift_ratio" in evidence
        else (("revenue_shift_ratio", "Revenue shift"), ("ebit_shift_ratio", "EBIT-muutos"))
    )
    fields = {
        "ABRUPT_FUNDAMENTAL_SHIFT": abrupt_fields,
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE": (("signed_change_difference", "Tulos–OCF-erotus"), ("revenue_scale", "Liikevaihtoskaala")),
        "CAPEX_INTENSITY_SHIFT_CANDIDATE": (("current_capex_intensity", "Nykyinen capex-intensiteetti"), ("prior_capex_intensity", "Edellinen capex-intensiteetti")),
        "NET_DEBT_SHIFT_CANDIDATE": (("signed_net_debt_change", "Nettovelan muutos"), ("revenue_scale", "Liikevaihtoskaala")),
        "VALUATION_YIELD_OUTLIER": (("median_yield", "Mediaanituotto"), ("maximum_yield", "Maksimituotto")),
        "RECENT_MARGIN_DECELERATION_REVIEW": (("current_trajectory", "Trajectory"), ("signed_margin_change", "Operating Margin change QoQ")),
        "WORKING_CAPITAL_SHIFT_CANDIDATE": (("signed_delta_onwc", "ONWC-muutos"), ("asset_scale", "Taseskaala")),
        "NON_OPERATING_EARNINGS_GAP_CANDIDATE": (("gap_amount", "EBIT − Operating Income"), ("gap_direction", "Suunta"), ("gap_abs_to_revenue", "Absoluuttinen ero/liikevaihto")),
    }
    output = []
    percentage_fields = {"revenue_shift_ratio", "operating_income_shift_ratio", "ebit_shift_ratio", "current_capex_intensity", "prior_capex_intensity", "median_yield", "maximum_yield", "gap_abs_to_revenue"}
    for key, label in fields.get(flag, ()):
        value = evidence.get(key)
        rendered = _pp(value, signed="current_operating_margin" in evidence) if key == "signed_margin_change" else _percentage(value) if key in percentage_fields else _money(value) if key in {"signed_change_difference", "revenue_scale", "signed_net_debt_change", "signed_delta_onwc", "asset_scale", "gap_amount"} else _text(value) if key == "gap_direction" else _number(value)
        output.append(f"{label}: {rendered}")
    return "; ".join(output) or "—"


def _diagnostic_metric(evaluation: Mapping[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    if evaluation["flag_name"] == "VALUATION_YIELD_OUTLIER":
        return f"mediaani {_percentage(evidence.get('median_yield'), 4)}; maksimi {_percentage(evidence.get('maximum_yield'), 4)}"
    if evaluation["flag_name"] == "RECENT_MARGIN_DECELERATION_REVIEW":
        return _pp(evidence.get("signed_margin_change"), signed="current_operating_margin" in evidence)
    if evaluation["flag_name"] == "NON_OPERATING_EARNINGS_GAP_CANDIDATE":
        return _percentage(evidence.get("gap_abs_to_revenue"), 4)
    if DIAGNOSTIC_METRIC_DISPLAY_UNITS[evaluation["flag_name"]] == "PERCENTAGE_POINTS":
        return _pp(evidence.get("metric_value"))
    return _percentage(evidence.get("metric_value"), 4)


def _diagnostic_threshold(evaluation: Mapping[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    if "threshold" in evidence:
        if DIAGNOSTIC_METRIC_DISPLAY_UNITS[evaluation["flag_name"]] == "PERCENTAGE_POINTS":
            return _pp(evidence["threshold"])
        return _percentage(evidence["threshold"])
    if "activation_threshold" in evidence:
        return _percentage(evidence["activation_threshold"])
    if evaluation["flag_name"] == "VALUATION_YIELD_OUTLIER":
        return f"mediaani {_percentage(evidence.get('median_threshold'))}; maksimi {_percentage(evidence.get('maximum_threshold'))}"
    if evaluation["flag_name"] == "RECENT_MARGIN_DECELERATION_REVIEW":
        return f"Trajectory ≥ {_number(evidence.get('trajectory_threshold'))}; marginaali ≤ {_pp(evidence.get('margin_change_threshold'), signed='current_operating_margin' in evidence)}"
    return "—"


def _diagnostic_summary(evaluation: Mapping[str, Any]) -> str:
    label = DIAGNOSTIC_LABELS.get(evaluation["flag_name"], evaluation["flag_name"])
    metric = _diagnostic_metric(evaluation)
    threshold = _diagnostic_threshold(evaluation)
    if evaluation["flag_name"] == "NON_OPERATING_EARNINGS_GAP_CANDIDATE":
        evidence = evaluation.get("evidence", {})
        return (
            f"{label}: TARKASTETTAVA EHDOKAS — {_text(evidence.get('gap_direction'))}, "
            f"erotus {_money(evidence.get('gap_amount'))}, absoluuttinen suhde {metric} "
            f"rajaan {threshold}"
        )
    return f"{label}: TARKASTETTAVA EHDOKAS — {metric} suhteessa rajaan {threshold}"


def _missing_sections(snapshot: Mapping[str, Any]) -> list[str]:
    missing = []
    if any(slot.get("score") is None for slot in snapshot["history"]):
        missing.append("Fundamental Score -historiassa puuttuva strict fiscal -havainto")
    if any(slot.get("valuation") is None for slot in snapshot["history"]):
        missing.append("Valuation-historiassa puuttuva strict fiscal -havainto")
    if snapshot.get("delta") is None:
        missing.append("Fundamental Delta")
    if not snapshot["relative_position"].get("available"):
        missing.append("Relative Position")
    if snapshot.get("diagnostic") is None:
        missing.append("Diagnostic Flags")
    if snapshot["current_price_valuation"].get("valuation_status") != "VALUATION_FULL":
        missing.append("Indicative current-price valuation")
    return missing


def _build_markdown(snapshot: Mapping[str, Any]) -> str:
    is_v2 = str(snapshot.get("report_contract", "")).startswith("CURRENT_REVISED_COMPANY_SNAPSHOT_V2")
    component_names = tuple(snapshot["component_contract"])
    component_labels = {
        **COMPONENT_LABELS,
        "OPERATING_PROFITABILITY": "Operating Profitability",
        "OPERATING_MARGIN_DIRECTION": "Operating Margin Direction",
        "BALANCE_SHEET_RESILIENCE": "Balance Sheet Resilience",
        "FCF_MARGIN": "FCF Margin",
    }
    operating_points = "operating_income_points" if is_v2 else "ebit_points"
    operating_yield = "operating_income_yield" if is_v2 else "ebit_yield"
    operating_multiple = "ev_operating_income" if is_v2 else "ev_ebit"
    operating_value = "ttm_operating_income" if is_v2 else "ttm_ebit"
    operating_label = "Operating Income" if is_v2 else "EBIT"
    common_earnings_label = "Reported Common Earnings" if is_v2 else "Common earnings"
    diagnostic_flag_names = tuple(snapshot.get("diagnostic_flag_names") or DIAGNOSTIC_FLAG_NAMES)
    diagnostic_definitions = _build_diagnostic_definitions(
        snapshot.get("diagnostic_model_contract") or DIAGNOSTIC_MODEL_CONTRACT,
        diagnostic_flag_names,
    )
    pp = lambda value: _pp(value, signed=is_v2)
    identity = snapshot["identity"]
    anchor = snapshot["anchor"]
    history = snapshot["history"]
    current_score = history[-1].get("score") or {}
    current_valuation = history[-1].get("valuation") or {}
    current_price = snapshot["current_price_valuation"]
    delta = snapshot.get("delta") or {"total": {}, "components": []}
    delta_total = delta["total"]
    lifecycle = snapshot["lifecycle"]
    lifecycle_current = lifecycle["history"][-1].get("row") or {}
    relative = snapshot["relative_position"]
    memberships = identity.get("taxonomy_memberships", [])
    valuation_average = snapshot["valuation_four_observation_average"]
    filing_vs_average = None if valuation_average is None or current_valuation.get("total_valuation_score") is None else current_valuation["total_valuation_score"] - valuation_average
    current_change = None if current_price.get("total_valuation_score") is None or current_valuation.get("total_valuation_score") is None else current_price["total_valuation_score"] - current_valuation["total_valuation_score"]
    score_universe = _relative_cell(relative, "FUNDAMENTAL_SCORE", "UNIVERSE")
    valuation_universe = _relative_cell(relative, "ABSOLUTE_VALUATION_SCORE", "UNIVERSE")
    score_ceilings = _score_ceiling_components(snapshot)
    valuation_ceilings = _valuation_ceiling_components(current_valuation)
    base_effects = _base_effect_observations(snapshot)
    current_price_change = None
    current_price_change_pct = None
    if current_valuation.get("selected_price") is not None and current_price.get("selected_price") is not None:
        filing_price = float(current_valuation["selected_price"])
        current_price_change = float(current_price["selected_price"]) - filing_price
        current_price_change_pct = current_price_change / filing_price if filing_price > 0 else None
    current_absolute = snapshot["absolute_values"]["current"]
    valuation_contexts = snapshot["valuation_multiples"]["contexts"]
    current_multiple, latest_multiple, previous_multiple = valuation_contexts
    net_debt = current_absolute.get("net_debt")
    debt_label = "Net cash" if net_debt is not None and float(net_debt) < 0 else "Net debt"
    debt_value = abs(float(net_debt)) if net_debt is not None and float(net_debt) < 0 else net_debt
    candidate_note = (
        f"Odottava Lifecycle-siirtymä: {lifecycle['candidate_state']} (1/2). "
        f"Vahvistus vaatii vielä yhden peräkkäisen {lifecycle['candidate_state']} raw -havainnon."
        if lifecycle.get("candidate_state") else "Ei aktiivista odottavaa Lifecycle-siirtymää."
    )
    lifecycle_candidate = (
        f"{lifecycle['candidate_state']} ({lifecycle.get('candidate_count', 1)}/2)"
        if lifecycle.get("candidate_state") else "None" if is_v2 else "—"
    )

    sections = [
        f"# {identity['ticker']} — Fundamental Snapshot",
        "",
        f"**{snapshot['history_notice']}**",
        "",
        "> Tulkinta: historia sisältää nykyisin revisioidut fundamentit, ei alkuperäistä PIT-rekonstruktiota. Nykyhintavaluation pitää viimeisimmän saatavilla olevan endpointin fundamentit vakiona.",
        "",
        _table(("Kenttä", "Arvo"), (
            ("Ticker", identity["ticker"]), ("Yhtiö", identity["company_name"]),
            ("Raporttipäivä", snapshot["report_date"]), ("Historia", "Nykyisin revisioitu, ei alkuperäinen PIT-historia"),
            ("Sektori", _text(identity.get("sector"))), ("Toimiala", _text(identity.get("industry"))),
            ("Taxonomy-jäsenyydet", f"{len(memberships)} aktiivista jäsenyyttä" if memberships else "Ei aktiivista ekosysteemijäsenyyttä"),
            ("Anchor-kvartaali", f"FY{anchor['fiscal_year']} {anchor['fiscal_quarter']}"),
            ("Period end", anchor["period_end"]), ("Saatavuuspäivä", anchor["source_availability_date"]),
            ("Fundamenttidatan ikä", f"{anchor['fundamental_age_days']} pv"),
            ("Markkinahinnan päivä", _text(current_price.get("price_date"))),
            ("Markkinahinnan ikä", "—" if current_price.get("price_age_calendar_days") is None else f"{current_price['price_age_calendar_days']} pv"),
            *((
                ("Nykyhinta", _price(current_price.get("selected_price"))),
            ) if is_v2 else ()),
        ), ("left", "left")),
        "",
        "## Taxonomy-jäsenyydet",
        "",
        _table(("Ekosysteemi", "Segmentti", "Jäsenyystyyppi"), tuple(
            (row["ecosystem_name"], row["peer_group_name"], row["membership_role"])
            for row in memberships
        ), ("left", "left", "left")) if memberships else "Ei aktiivista taxonomy-jäsenyyttä.",
        "",
        "Taxonomy-jäsenyys ja kelpoisuus ekosysteemin Relative Position -vertailuun ovat eri asioita. Yksi jäsenyys ei automaattisesti tuota omaa prosenttipistettä.",
        "",
        "## Nykytilan yhteenveto",
        "",
        _table(("Mittari", "Arvo"), (
            ("Fundamental Score", _score(current_score.get("total_score"))),
            ("Score status", _text(current_score.get("readiness_status"))),
            ("Fundamental Delta QoQ", _signed_score(delta_total.get("qoq_delta"))),
            ("Fundamental Delta 2Q", _signed_score(delta_total.get("two_quarter_delta"))),
            ("Fundamental Delta YoY", _signed_score(delta_total.get("yoy_delta"))),
            ("Fundamental Trajectory", _score((current_score.get("components") or {}).get("FUNDAMENTAL_TRAJECTORY", {}).get("component_score"))),
            ("Lifecycle status", _text(lifecycle.get("current_status"))),
            ("Vahvistettu Lifecycle", _text(lifecycle.get("confirmed_state"))),
            ("Lifecycle candidate", lifecycle_candidate),
            ("Vahvistetun tilan tenure", "—" if lifecycle.get("tenure_quarters") is None else f"{lifecycle['tenure_quarters']} kvartaalia"),
            ("Viimeisimmän endpointin Valuation Score / hintapäivä", f"{_score(current_valuation.get('total_valuation_score'))} / {_text(current_valuation.get('price_date'))}"),
            ("Valuation 4 havainnon keskiarvo", f"{_score(valuation_average)} ({snapshot['valuation_four_observation_count']}/4)"),
            ("Saatavuuspäivän Valuation Score vs 4Q keskiarvo (pistettä)", _signed_score(filing_vs_average)),
            ("Indicative current-price Valuation Score", _score(current_price.get("total_valuation_score"))),
            ("Indicative current-price Valuation Score vs saatavuuspäivän Valuation Score (pistettä)", _signed_score(current_change)),
            ("Fundamental-universumipersentiili", score_universe),
            ("Valuation-universumipersentiili", valuation_universe),
            ("Aktiivisia diagnostiikkalippuja", snapshot["diagnostic_counts"]["EVALUATED_FLAGGED"]),
            ("Viimeisin Fundamental Score / saatavuuspäivä", f"{_score(current_score.get('total_score'))} / {_text(anchor.get('source_availability_date'))}"),
            ("Nykyhintavaluation / hintapäivä", f"{_score(current_price.get('total_valuation_score'))} / {_text(current_price.get('price_date'))}"),
            (f"{operating_label} TTM", _money(current_absolute.get(operating_value))),
            (f"{operating_label} Margin TTM", _percentage((history[-1].get('score_raw') or {}).get('operating_margin_ttm') if is_v2 else (history[-1].get('score_raw') or {}).get('ebit_margin_ttm'))),
            (f"{operating_label} / EV", _percentage(current_price.get(operating_yield))),
            (f"EV / {operating_label}", _multiple((current_multiple.get('metrics') or {}).get(operating_multiple, {}).get('value'))),
            ("Data readiness", f"Score={_text(current_score.get('readiness_status'))}; Valuation={_text(current_valuation.get('valuation_status'))}; TTM={anchor['ttm_readiness']}"),
        ), ("left", "left")),
        "",
        "`vs 4Q average` on nykyhavainnon vertailu neljän havainnon keskiarvoon, ei trendimittari. Fundamental Trajectory on erillinen suuntakomponentti.",
        "",
        "## Fundamental Score -historia",
        "",
        _table(("Havainto", *HISTORY_HEADERS), (
            ("Fiscal quarter", *_history_values(snapshot, lambda slot: f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}")),
            ("Saatavuuspäivä", *_history_values(snapshot, lambda slot: _text(slot.get("availability_date")))),
            ("Fundamental Score", *_history_values(snapshot, lambda slot: _score((slot.get("score") or {}).get("total_score")))),
            ("Status", *_history_values(snapshot, lambda slot: _text((slot.get("score") or {}).get("readiness_status")))),
        )),
        "",
        "## Fundamental-komponenttien pistehistoria",
        "",
        _table(("Komponentti", "Maks.", *HISTORY_HEADERS), tuple(
            (component_labels[name], _score(snapshot["component_contract"][name]), *_history_values(snapshot, lambda slot, component=name: _score(((slot.get("score") or {}).get("components") or {}).get(component, {}).get("component_score"))))
            for name in component_names
        ) + (("**Yhteensä**", "**100.00**", *_history_values(snapshot, lambda slot: _score((slot.get("score") or {}).get("total_score")))),)),
        "",
        "Näytetty kokonaispistemäärä lasketaan pyöristämättömistä komponenttiarvoista; taulukon kahden desimaalin summassa voi siksi olla pieni esitysero.",
        "",
        f"Pistekatossa nykyisessä endpointissa: {', '.join(score_ceilings)}. Raw-mittari voi edelleen parantua ilman komponenttipisteiden nousua." if score_ceilings else "Yksikään Fundamental-komponentti ei ole nykyisessä endpointissa pistekatossa.",
        "",
        "## Fundamental raw -mittarihistoria",
        "",
        _table(("Raw-mittari", *HISTORY_HEADERS), (
            ("Revenue growth YoY TTM", *_history_values(snapshot, lambda slot: _percentage(slot["score_raw"]["revenue_growth_yoy_ttm"]))),
            (f"{operating_label} Margin TTM", *_history_values(snapshot, lambda slot: _percentage(slot["score_raw"].get("operating_margin_ttm") if is_v2 else slot["score_raw"].get("ebit_margin_ttm")))),
            (f"{operating_label} Margin Direction (YoY)", *_history_values(snapshot, lambda slot: pp(slot["score_raw"].get("operating_margin_direction") if is_v2 else slot["score_raw"].get("ebit_margin_direction")))),
            ("FCF margin TTM", *_history_values(snapshot, lambda slot: _percentage(slot["score_raw"]["fcf_margin_ttm"]))),
            ("Balance Sheet branch", *_history_values(snapshot, lambda slot: _balance_raw(slot["score_raw"]))),
            ("Shares outstanding YoY", *_history_values(snapshot, lambda slot: _percentage(slot["score_raw"]["shares_outstanding_yoy_change"]))),
            ("Fundamental Trajectory", *_history_values(snapshot, lambda slot: _score(slot["score_raw"]["fundamental_trajectory"]))),
        )),
        "",
        "Base effect -huomio: " + "; ".join(base_effects) + ". Prosenttimuutos voi painottua pienen vertailupohjan vuoksi; havainto ei muuta pisteitä tai statuksia." if base_effects else "Ei läpinäkyvän base effect -rajan ylittäviä Revenue Growth -havaintoja tässä viiden endpointin näkymässä.",
        "",
        "## Fundamental Delta ja komponenttien kontribuutiot",
        "",
        _table(("Komponentti", "QoQ", "2Q", "YoY"), tuple(
            (component_labels.get(row["component_name"], row["component_name"]), _signed_score(row.get("qoq_delta")), _signed_score(row.get("two_quarter_delta")), _signed_score(row.get("yoy_delta")))
            for row in sorted(delta.get("components", []), key=lambda row: component_names.index(row["component_name"]))
        ) + (
            ("**Total Delta**", _signed_score(delta_total.get("qoq_delta")), _signed_score(delta_total.get("two_quarter_delta")), _signed_score(delta_total.get("yoy_delta"))),
            ("Readiness", _text(delta_total.get("qoq_status")), _text(delta_total.get("two_quarter_status")), _text(delta_total.get("yoy_status"))),
        )),
        "",
        "## Absoluuttiset fundamenttiarvot",
        "",
        _table(("Mittari", "t−4 (YoY comparison)", "Edellinen", "Nykyinen"), (
            *((label, _money(snapshot["absolute_values"]["yoy_base"].get(key)), _money(snapshot["absolute_values"]["previous"].get(key)), _money(snapshot["absolute_values"]["current"].get(key))) for key, label in (
                ("ttm_revenue", "Revenue TTM"), (operating_value, f"{operating_label} TTM"),
                ("ttm_operating_cashflow", "Operating cash flow TTM"),
            )),
            ("Capex spend", *(
                _money(abs(float(values["ttm_capex"]))) if values.get("ttm_capex") is not None else "—"
                for values in (snapshot["absolute_values"]["yoy_base"], snapshot["absolute_values"]["previous"], snapshot["absolute_values"]["current"])
            )),
            *((label, _money(snapshot["absolute_values"]["yoy_base"].get(key)), _money(snapshot["absolute_values"]["previous"].get(key)), _money(snapshot["absolute_values"]["current"].get(key))) for key, label in (
                ("ttm_free_cashflow", "Free cash flow TTM"),
                ("ttm_net_income_common", f"{common_earnings_label} TTM"),
            )),
        )),
        "",
        "Capex spend näytetään positiivisena menon suuruutena. Canonical CAPEX säilyy allekirjoitettuna arvona, jossa negatiivinen luku tarkoittaa kassavirran ulosmenoa; FCF-kaavaa ei muuteta.",
        "",
        _table(("Nykyisen endpointin tasekenttä", "Arvo"), (
            ("Cash", _money(current_absolute.get("cash"))),
            ("Total debt", _money(current_absolute.get("total_debt"))),
            (debt_label, _money(debt_value)),
            *((label, _money(current_absolute.get(key))) for key, label in (
                ("total_assets", "Total assets"), ("accounts_receivable", "Accounts receivable"),
                ("inventory", "Inventory"), ("accounts_payable", "Accounts payable"),
                ("deferred_revenue", "Deferred revenue"),
                ("operating_net_working_capital", "Operating net working capital"),
                ("shares_outstanding", "Shares outstanding"),
            )),
        ), ("left", "right")),
        "",
        "Operating net working capital = accounts receivable + inventory − accounts payable − deferred revenue. Puuttuvia komponentteja ei korvata nollalla.",
        "",
        "## Lifecycle-historia",
        "",
        _table(("Kvartaali", "Saatavuuspäivä", "Raw state", "Vahvistettu final state", "Status", "Candidate", f"{operating_label} Margin", f"{operating_label} Margin Direction", "Siirtymätila"), tuple(
            (
                f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}",
                _text((slot.get("row") or {}).get("source_available_date")),
                _text((slot.get("row") or {}).get("raw_state")),
                _text((slot.get("row") or {}).get("final_state")),
                _text((slot.get("row") or {}).get("lifecycle_status")),
                (
                    f"{slot['row']['candidate_state']} ({slot['row'].get('candidate_count', 1)}/2)"
                    if slot.get("row") and slot["row"].get("candidate_state") else "None" if is_v2 else "—"
                ),
                _percentage((slot.get("row") or {}).get("operating_margin_ttm") if is_v2 else (slot.get("row") or {}).get("ebit_margin_ttm")),
                pp((slot.get("row") or {}).get("operating_margin_direction") if is_v2 else (slot.get("row") or {}).get("ebit_margin_direction")),
                _transition_text(slot["transition_status"]),
            )
            for slot in lifecycle["history"]
        ), ("left", "left", "left", "left", "left", "left", "right", "right", "left")),
        "",
        _table(("Nykyinen Lifecycle-kenttä", "Arvo"), (
            ("Published status", _text(lifecycle.get("current_status"))),
            ("Confirmed final state", _text(lifecycle.get("confirmed_state"))),
            ("Tenure", "—" if lifecycle.get("tenure_quarters") is None else f"{lifecycle['tenure_quarters']} kvartaalia"),
            ("Voimassa fiscal-kaudesta", "—" if lifecycle.get("active_since_fiscal_year") is None else f"FY{lifecycle['active_since_fiscal_year']} {lifecycle['active_since_fiscal_quarter']}"),
            ("Voimassa saatavuuspäivästä", _text(lifecycle.get("active_since_available_date"))),
        ), ("left", "left")),
        "",
        candidate_note,
        "",
        "`UNCLASSIFIED` säilyy julkisesti `LIFECYCLE_NOT_READY`-tilana; sitä ei korvata viimeksi vahvistetulla tilalla.",
        "",
        "## Saatavuuspäivän Valuation Score -historia",
        "",
        _table(("Havainto", *HISTORY_HEADERS), (
            ("Fiscal quarter", *_history_values(snapshot, lambda slot: f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}")),
            ("Valuation price date", *_history_values(snapshot, lambda slot: _text((slot.get("valuation") or {}).get("price_date")))),
            ("Saatavuuspäivän hinta", *_history_values(snapshot, lambda slot: _price((slot.get("valuation") or {}).get("selected_price")))),
            ("Valuation Score", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("total_valuation_score")))),
            ("Status", *_history_values(snapshot, lambda slot: _text((slot.get("valuation") or {}).get("valuation_status")))),
        )),
        "",
        f"Neljän havainnon keskiarvo käyttää vain t−3...t-havaintoja: {_score(valuation_average)} ({snapshot['valuation_four_observation_count']}/4). Se on vertailutaso, ei trendi.",
        "",
        "## Valuation-komponenttien pistehistoria",
        "",
        _table(("Komponentti", "Maks.", *HISTORY_HEADERS), (
            (f"{operating_label} / EV", "40.00", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get(operating_points)))),
            ("FCF / Market Cap", "40.00", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("fcf_points")))),
            (f"{common_earnings_label} / Market Cap", "20.00", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("earnings_points")))),
            ("**Valuation Score**", "**100.00**", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("total_valuation_score")))),
        )),
        "",
        (
            f"Valuation-pistekatossa nykyisessä saatavuuspäivän endpointissa: {', '.join(valuation_ceilings)}. "
            + ("Kokonaispiste on 100, joten raw-yieldit voivat edelleen parantua ilman pisteiden nousua yli 100:n." if _at_ceiling(current_valuation.get("total_valuation_score"), 100.0) else "Raw-yield voi edelleen parantua ilman kyseisen komponentin pisteiden nousua.")
        ) if valuation_ceilings else "Yksikään Valuation-komponentti ei ole nykyisessä saatavuuspäivän endpointissa pistekatossa.",
        "",
        "## Valuation raw-yield -historia",
        "",
        _table(("Raw-mittari", *HISTORY_HEADERS), (
            (f"{operating_label} / EV", *_history_values(snapshot, lambda slot: _percentage((slot.get("valuation") or {}).get(operating_yield)))),
            ("FCF / Market Cap", *_history_values(snapshot, lambda slot: _percentage((slot.get("valuation") or {}).get("fcf_yield")))),
            (f"{common_earnings_label} / Market Cap", *_history_values(snapshot, lambda slot: _percentage((slot.get("valuation") or {}).get("earnings_yield")))),
            ("Positive components", *_history_values(snapshot, lambda slot: "—" if not slot.get("valuation") else f"{sum((slot['valuation'].get(key) or 0) > 0 for key in (operating_yield, 'fcf_yield', 'earnings_yield'))}/3")),
        )),
        "",
        "## Valuation-komponenttien pistemuutokset",
        "",
        _table(("Komponentti", "QoQ (pistettä)", "2Q (pistettä)", "YoY (pistettä)"), tuple(
            (label, _signed_score(_filing_delta(history, key, 1)), _signed_score(_filing_delta(history, key, 2)), _signed_score(_filing_delta(history, key, 4)))
            for key, label in ((operating_points, f"{operating_label} / EV"), ("fcf_points", "FCF / Market Cap"), ("earnings_points", f"{common_earnings_label} / Market Cap"), ("total_valuation_score", "Valuation Score"))
        )),
        "",
        "Taulukon arvot ovat Valuation-komponenttien ja kokonaispisteen muutoksia pisteinä. Ne eivät ole raw-yieldien prosenttiyksikkömuutoksia.",
        "",
        _table(("Saatavuuspäivän hinnan muutos", "QoQ", "2Q", "YoY"), (
            ("Absoluuttinen", *(_signed_score(_filing_price_change(history, lag)[0]) for lag in (1, 2, 4))),
            ("Prosentuaalinen", *(_percentage(_filing_price_change(history, lag)[1]) for lag in (1, 2, 4))),
        )),
        "",
        "> Valuation Score -historia ei ole puhdas hinta- tai fundamenttitrendi. Jokainen havainto yhdistää endpointin fundamentit ja sen lähteen saatavuuspäivälle valitun markkinahinnan.",
        "",
        "## Indicative current-price valuation",
        "",
        f"Tila: `{CURRENT_PRICE_LABEL}` / `{_text(current_price.get('valuation_status'))}` / `{_text(current_price.get('reason_code'))}`",
        "",
        _table(("Mittari", "Viimeisin saatavuuspäivä", "Nykyhinta", "Muutos"), (
            ("Price date", _text(current_valuation.get("price_date")), _text(current_price.get("price_date")), "—"),
            ("Price", _price(current_valuation.get("selected_price")), _price(current_price.get("selected_price")), _signed_score(current_price_change)),
            ("Price change %", "—", "—", _percentage(current_price_change_pct)),
            ("Valuation Score", _score(current_valuation.get("total_valuation_score")), _score(current_price.get("total_valuation_score")), _score_point_change(current_change)),
            (f"{operating_label} / EV", _percentage(current_valuation.get(operating_yield)), _percentage(current_price.get(operating_yield)), pp(None if current_valuation.get(operating_yield) is None or current_price.get(operating_yield) is None else current_price[operating_yield] - current_valuation[operating_yield])),
            ("FCF / Market Cap", _percentage(current_valuation.get("fcf_yield")), _percentage(current_price.get("fcf_yield")), pp(None if current_valuation.get("fcf_yield") is None or current_price.get("fcf_yield") is None else current_price["fcf_yield"] - current_valuation["fcf_yield"])),
            (f"{common_earnings_label} / Market Cap", _percentage(current_valuation.get("earnings_yield")), _percentage(current_price.get("earnings_yield")), pp(None if current_valuation.get("earnings_yield") is None or current_price.get("earnings_yield") is None else current_price["earnings_yield"] - current_valuation["earnings_yield"])),
        )),
        "",
        "> Osakemäärä, velka ja kassa tulevat viimeisimmästä saatavilla olevasta fundamentti-endpointista ja voivat poiketa nykyhetken arvoista.",
        "",
        "Nykyhintalaskenta pitää anchor-fundamentit vakiona. Tässä osiossa ei "
        "lasketa uutta persentiiliä raportin nykyhinnalla. Erillinen Relative "
        "Valuation -osio näyttää viimeisimmän tallennetun vertailun sen omalla "
        "snapshot- ja hintapäivällä; raportin generointi ei käynnistä tietokannan "
        "päivitystä.",
        "",
        "## Three-point valuation multiples",
        "",
        "### Valuation basis",
        "",
        _table(
            ("Basis", "Current moment", "Latest endpoint (availability date)", "Previous endpoint (exact Q−1 availability date)"),
            (
                ("Fiscal quarter", *(_valuation_context_quarter(context) for context in valuation_contexts)),
                ("TTM period end", *(_basis_text(context.get("ttm_period_end")) for context in valuation_contexts)),
                ("Source availability date", *(_basis_text(context.get("fundamental_availability_date")) for context in valuation_contexts)),
                ("Price date", *(_basis_text(context.get("price_date")) for context in valuation_contexts)),
                ("Price used", *(_basis_number(context.get("price"), _price) for context in valuation_contexts)),
                ("Shares used", *(_basis_number(context["source_inputs"].get("shares_outstanding"), _money) for context in valuation_contexts)),
                ("Market cap used", *(_valuation_metric(context, "market_cap", _money) for context in valuation_contexts)),
                ("Reported Common Earnings TTM", *(_basis_number(context["source_inputs"].get("ttm_net_income_common"), _money) for context in valuation_contexts)),
                ("Valuation status", *(_basis_text(context.get("valuation_status")) for context in valuation_contexts)),
            ),
            ("left", "right", "right", "right"),
        ),
        "",
        "Fiscal quarter ja TTM period end yksilöivät taloudellisen kauden. Source availability date kertoo, milloin RawCandle käsittelee tiedon saatavilla olevana; se ei automaattisesti ole oikeudellisesti varmennettu filing-ajankohta. Price date kertoo käytetyn markkinahinnan päivän ja raporttipäivä snapshotin muodostusajankohdan.",
        "",
        "Currency: N/A (source currency not available in the validated contract)" if is_v2 and not any(context.get("price_currency") for context in valuation_contexts) else "",
        "" if is_v2 and not any(context.get("price_currency") for context in valuation_contexts) else "",
        _table(
            ("Metric", "Current moment", "Latest endpoint (availability date)", "Previous endpoint (exact Q−1 availability date)"),
            tuple(
                (
                    label,
                    _valuation_metric(current_multiple, key, formatter),
                    _valuation_metric(latest_multiple, key, formatter),
                    _valuation_metric(previous_multiple, key, formatter),
                )
                for key, label, formatter in (
                    ("market_cap", "Market Capitalization", _money),
                    ("enterprise_value", "Enterprise Value", _money),
                    ("pe", "P/E (Reported Common Earnings)" if is_v2 else "P/E", _multiple),
                    ("earnings_yield", "Reported Common Earnings Yield" if is_v2 else "Earnings Yield", _valuation_yield),
                    ("p_fcf", "P/FCF", _multiple),
                    ("fcf_yield", "FCF Yield", _valuation_yield),
                    (operating_multiple, f"EV / {operating_label}" if is_v2 else "EV/EBIT", _multiple),
                    (operating_yield, f"{operating_label} / EV" if is_v2 else "EBIT Yield", _valuation_yield),
                    ("ev_sales", "EV/Sales", _multiple),
                    ("p_sales", "P/S", _multiple),
                )
            ),
            ("left", "right", "right", "right"),
        ),
        "",
        "> Reported common-shareholder earnings are a GAAP-based measure. They may include recognized investment gains and losses and other non-operating items included in reported earnings. They are not normalized." if is_v2 else "",
        "" if is_v2 else "",
        "> Current moment versus Latest endpoint mainly reflects the market-price change because both use the latest endpoint's fundamental base. Latest endpoint versus Previous endpoint (exact Q−1) combines changes in price, shares, balance sheet, and TTM fundamentals, so this is not a pure valuation trend decomposition. The metrics are descriptive and do not alter Valuation Score. Current-moment metrics are indicative because they combine a current market price with the latest available endpoint fundamentals.",
        "",
        *_relative_valuation_sections(snapshot),
        "## Relative Position",
        "",
        "Alla oleva Ecosystem-sarake kertoo vain aktiivisen Relative Position -snapshotin kelpoisen ekosysteemivertailun tuloksen. Se ei ole taxonomy-layer-ranking eikä jäsenyystaulukon kopio.",
        "",
        _table(("Mittari", "Universe", "Sector", "Industry", "Ecosystem"), (
            ("Fundamental Score", *(_relative_cell(relative, "FUNDAMENTAL_SCORE", scope) for scope in ("UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM"))),
            ("Saatavuuspäivän Valuation", *(_relative_cell(relative, "ABSOLUTE_VALUATION_SCORE", scope) for scope in ("UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM"))),
        ), ("left", "left", "left", "left", "left")),
        "",
        "Pientä peer-ryhmää ei korvata laajemmalla ryhmällä. Taxonomy-jäsenyys, percentile-kelpoisuus sekä toteutunut percentile ja peer count näytetään toisistaan erillään.",
        "",
        "## Diagnostic Flags",
        "",
        f"Flagged: **{snapshot['diagnostic_counts']['EVALUATED_FLAGGED']}**, clear: **{snapshot['diagnostic_counts']['EVALUATED_CLEAR']}**, not ready: **{snapshot['diagnostic_counts']['FLAG_NOT_READY']}**, not applicable: **{snapshot['diagnostic_counts']['FLAG_NOT_APPLICABLE']}**.",
        "",
    ]
    evaluations = (snapshot.get("diagnostic") or {}).get("evaluations", [])
    flagged = [row for row in evaluations if row["status"] == "EVALUATED_FLAGGED"]
    sections.extend([
        *( ["**" + _diagnostic_summary(row) + "**" for row in flagged] if flagged else [_zero_diagnostic_text(evaluations, diagnostic_flag_names)] ),
        "",
        _table(("Lippu", "Status", "Keskeinen evidenssi", "Laskettu arvo", "Raja"), tuple(
            (DIAGNOSTIC_LABELS.get(row["flag_name"], row["flag_name"]), row["status"], _diagnostic_evidence(row), _diagnostic_metric(row), _diagnostic_threshold(row))
            for row in flagged
        ) or (("—", "Ei aktiivisia lippuja", "—", "—", "—"),), ("left", "left", "left", "right", "right")),
        "",
        f"### Kaikki {'kahdeksan' if len(diagnostic_flag_names) == 8 else 'seitsemän'} statusta",
        "",
        _table(("Lippu", "Status", "Tulkinta", "Arvo", "Raja"), tuple(
            (DIAGNOSTIC_LABELS.get(row["flag_name"], row["flag_name"]), row["status"], diagnostic_explanation(row), _diagnostic_metric(row), _diagnostic_threshold(row))
            for row in evaluations
        ), ("left", "left", "left", "right", "right")),
        "",
        "### Diagnostiikan määritelmät",
        "",
        _table(("Lippu", "Vertailu", "Mittaus ja skaalaus", "Tarkastusehto"), tuple(
            (DIAGNOSTIC_LABELS[row.flag_name], row.comparison, row.measurement, row.trigger)
            for row in diagnostic_definitions
        ), ("left", "left", "left", "left")),
        "",
        DIAGNOSTIC_COVERAGE_TEXT,
        "",
        "Liput ovat numeerisia review-candidate-havaintoja. Raportti ei päättele niiden syitä eikä vahvista kirjanpitotapahtumia.",
        "",
        "## Data readiness ja rajoitteet",
        "",
    ])
    missing_components = [name for name in component_names if ((current_score.get("components") or {}).get(name, {}).get("component_score") is None)]
    blockers = []
    if history[-1].get("ttm"):
        try:
            import json
            blockers = json.loads(history[-1]["ttm"].get("blocker_codes_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            blockers = ["TTM_BLOCKER_DATA_INVALID"]
    missing_sections = _missing_sections(snapshot)
    sections.extend([
        _table(("Tarkistus", "Tila"), (
            ("Score", _text(current_score.get("readiness_status"))),
            ("Valuation", _text(current_valuation.get("valuation_status"))),
            ("Lifecycle", _text(lifecycle.get("current_status"))),
            ("Delta QoQ", _text(delta_total.get("qoq_status"))),
            ("Delta 2Q", _text(delta_total.get("two_quarter_status"))),
            ("Delta YoY", _text(delta_total.get("yoy_status"))),
            ("Relative Position", "AVAILABLE" if relative.get("available") else _text(relative.get("reason"))),
            ("Diagnostic statuses", f"flagged={snapshot['diagnostic_counts']['EVALUATED_FLAGGED']}; clear={snapshot['diagnostic_counts']['EVALUATED_CLEAR']}; not-ready={snapshot['diagnostic_counts']['FLAG_NOT_READY']}; not-applicable={snapshot['diagnostic_counts']['FLAG_NOT_APPLICABLE']}"),
            ("Fundamental availability / age", f"{anchor['source_availability_date']} / {anchor['fundamental_age_days']} pv"),
            ("Market price / age", f"{_text(current_price.get('price_date'))} / {_text(current_price.get('price_age_calendar_days'))} pv"),
            ("Puuttuvat Score-komponentit", ", ".join(missing_components) or "Ei puuttuvia"),
            ("Data-quality flags", ", ".join(blockers) or "Ei TTM-blockereita"),
            ("Puuttuvat raporttiosat", "; ".join(missing_sections) or "Ei puuttuvia osia"),
        ), ("left", "left")),
        "",
        "Tämä on nykyisin revisioitu raportti, ei historiallisen julkaisuhetken PIT-rekonstruktio. Aikaisempi report date voi sisältää myöhemmin tietokantaan tulleita restatement-korjauksia, mutta saatavuuspäivän ja markkinahinnan tulevaisuusrajat pidetään voimassa.",
        "",
        "Indicative current-price valuation käyttää viimeisimmän fundamentti-ilmoituksen osakkeita, velkaa ja kassaa. Se ei ole persisted Valuation-tulos eikä uusi Relative Position -havainto.",
        "",
        "## Tekninen liite",
        "",
        _table(("Kenttä", "Arvo"), (
            ("Report contract", snapshot["report_contract"]),
            ("Report date", snapshot["report_date"]),
            ("Anchor identity", f"FY{anchor['fiscal_year']} {anchor['fiscal_quarter']}; period_end={anchor['period_end']}; available={anchor['source_availability_date']}") if is_v2 else ("Anchor identity", f"company_id={anchor['company_id']}; quarter_id={anchor['quarter_id']}; FY{anchor['fiscal_year']} {anchor['fiscal_quarter']}"),
            *(([
                *(([("Candidate package fingerprint", _text((snapshot.get("source_state", {}).get("candidate_package") or [None, None])[1]))] if snapshot.get("source_state", {}).get("candidate_package") else [])),
                ("Active package fingerprint", _text((snapshot.get("source_state", {}).get("active_package") or [None, None])[1])),
                ("Model-family fingerprint", _text((snapshot.get("source_state", {}).get("active_package") or [None, None])[0])),
                ("Snapshot economic fingerprint", _text(snapshot.get("model_fingerprints", {}).get("snapshot"))),
            ] if is_v2 else [])),
            *(([("Report presentation fingerprint", snapshot.get("report_presentation_fingerprint"))] if is_v2 else [])),
            *((f"Model fingerprint: {name}", value) for name, value in snapshot["model_fingerprints"].items() if not is_v2 or name not in {"family", "snapshot"}),
            ("Delta fundamental source fingerprint", _text(_source_item(snapshot, "delta", 0))),
            ("Delta fundamental result fingerprint", _text(_source_item(snapshot, "delta", 1))),
            ("Delta lifecycle source fingerprint", _text(_source_item(snapshot, "delta", 2))),
            ("Delta lifecycle result fingerprint", _text(_source_item(snapshot, "delta", 3))),
            ("Delta valuation source fingerprint", _text(_source_item(snapshot, "delta", 4))),
            ("Delta valuation result fingerprint", _text(_source_item(snapshot, "delta", 5))),
            ("Delta economic package fingerprint", _text((snapshot["source_state"].get("delta") or [None] * 10)[6])),
            ("Delta physical content fingerprint", _text((snapshot["source_state"].get("delta") or [None] * 10)[7])),
            ("Diagnostic source fingerprint", _text((snapshot["source_state"].get("diagnostic") or [None] * 5)[0])),
            ("Diagnostic economic result fingerprint", _text((snapshot["source_state"].get("diagnostic") or [None] * 5)[1])),
            ("Diagnostic physical content fingerprint", _text((snapshot["source_state"].get("diagnostic") or [None] * 5)[2])),
            *(([] if is_v2 else [("Relative snapshot ID", _text((snapshot["source_state"].get("relative") or [None] * 5)[0]))])),
            ("Relative snapshot date", _text((snapshot["source_state"].get("relative") or [None] * 5)[1])),
            ("Relative calculation source fingerprint", _text((snapshot["source_state"].get("relative") or [None] * 5)[2])),
            ("Relative source content fingerprint", _text((snapshot["source_state"].get("relative") or [None] * 5)[3])),
            ("Relative result fingerprint", _text((snapshot["source_state"].get("relative") or [None] * 5)[4])),
            ("Current-price source date", _text(current_price.get("price_date"))),
            ("Source-state fingerprint", snapshot["source_state_fingerprint"]),
            ("Report-content fingerprint", FINGERPRINT_PLACEHOLDER),
            ("Generation command", f"python3 -m rawcandle.cli.run_fundamentals_v4_company_snapshot --ticker {identity['ticker']} --report-date {snapshot['report_date']} --output-dir fundamental_reports [read-only source paths]"),
        ), ("left", "left")),
        "",
        "Raportti on koonti- ja tarkastelutyökalu. Se ei ole tuottoennuste, tekninen entry-raportti eikä BUY/SELL-suositus.",
        "",
    ])
    rendered = "\n".join(sections)
    if is_v2:
        rendered = re.sub(r"(-?\d+(?:\.\d+)?) %", r"\1%", rendered)
        rendered = re.sub(r"(-?\d+(?:\.\d+)?) ([BM])\b", r"\1\2", rendered)
        rendered = re.sub(r"(?<![\w\d])-(?=\d)", "−", rendered)
    return rendered


def render_snapshot(snapshot: Mapping[str, Any]) -> RenderedSnapshot:
    if snapshot.get("report_contract") not in SUPPORTED_REPORT_CONTRACTS:
        raise ValueError("SNAPSHOT_REPORT_CONTRACT_MISMATCH")
    template = _build_markdown(snapshot)
    if template.count(FINGERPRINT_PLACEHOLDER) != 1:
        raise RuntimeError("SNAPSHOT_FINGERPRINT_PLACEHOLDER_INVALID")
    content_fingerprint = hashlib.sha256(template.encode("utf-8")).hexdigest()
    markdown = template.replace(FINGERPRINT_PLACEHOLDER, content_fingerprint)
    forbidden = r"(?<![A-Za-z])(?:NaN|nan)(?![A-Za-z])" if str(snapshot.get("report_contract", "")).startswith("CURRENT_REVISED_COMPANY_SNAPSHOT_V2") else r"(?<![A-Za-z])(?:None|NaN|nan)(?![A-Za-z])"
    if re.search(forbidden, markdown):
        raise RuntimeError("SNAPSHOT_UNFORMATTED_INTERNAL_VALUE")
    return RenderedSnapshot(markdown=markdown, content_fingerprint=content_fingerprint)


def verify_rendered_report(rendered: RenderedSnapshot) -> bool:
    template = rendered.markdown.replace(rendered.content_fingerprint, FINGERPRINT_PLACEHOLDER, 1)
    return hashlib.sha256(template.encode("utf-8")).hexdigest() == rendered.content_fingerprint
