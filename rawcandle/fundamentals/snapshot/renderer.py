from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.score.engine import COMPONENTS
from rawcandle.fundamentals.snapshot.assembler import (
    COMPONENT_LABELS,
    CURRENT_PRICE_LABEL,
    REPORT_CONTRACT,
)


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


def _pp(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if math.isfinite(number) and abs(number) < 0.00005:
        number = 0.0
    return "—" if not math.isfinite(number) else f"{number * 100:.2f} pp"


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


def _signed_score(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if not math.isfinite(number):
        return "—"
    if abs(number) < 0.005:
        return "0.00"
    return f"{number:+.2f}"


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
            f"{_percentile(row['percentile'])} (n={row['peer_count']}; {_text(row['peer_group_id'])}; {row['snapshot_date']})"
            for row in rows
        )
    coverage = [row for row in relative.get("coverage", []) if row["measure"] == measure and row["peer_scope"] == scope]
    if coverage:
        return "; ".join(f"— ({row['coverage_status']}; {row['reason_code']})" for row in coverage)
    return "— (NO_COVERAGE_RECORD)"


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
    return [
        COMPONENT_LABELS[name]
        for name in COMPONENTS
        if _at_ceiling(
            components.get(name, {}).get("component_score"),
            snapshot["component_contract"].get(name),
        )
    ]


def _valuation_ceiling_components(valuation: Mapping[str, Any]) -> list[str]:
    return [
        label
        for key, maximum, label in (
            ("ebit_points", 40.0, "EBIT / EV"),
            ("fcf_points", 40.0, "FCF / Market Cap"),
            ("earnings_points", 20.0, "Common earnings / Market Cap"),
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
    if branch == "NET_DEBT_TO_EBIT":
        if value is not None and float(value) < 0:
            return f"NET_CASH_TO_EBIT: {_multiple(abs(float(value)))}"
        return f"{branch}: {_multiple(value)}"
    if branch:
        return f"{branch}: {_money(value)}"
    return "NOT_READY"


def _diagnostic_evidence(evaluation: Mapping[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    flag = evaluation["flag_name"]
    fields = {
        "ABRUPT_FUNDAMENTAL_SHIFT": (("revenue_shift_ratio", "Liikevaihdon muutos"), ("ebit_shift_ratio", "EBIT-muutos")),
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE": (("signed_change_difference", "Tulos–OCF-erotus"), ("revenue_scale", "Liikevaihtoskaala")),
        "CAPEX_INTENSITY_SHIFT_CANDIDATE": (("current_capex_intensity", "Nykyinen capex-intensiteetti"), ("prior_capex_intensity", "Edellinen capex-intensiteetti")),
        "NET_DEBT_SHIFT_CANDIDATE": (("signed_net_debt_change", "Nettovelan muutos"), ("revenue_scale", "Liikevaihtoskaala")),
        "VALUATION_YIELD_OUTLIER": (("median_yield", "Mediaanituotto"), ("maximum_yield", "Maksimituotto")),
        "RECENT_MARGIN_DECELERATION_REVIEW": (("current_trajectory", "Trajectory"), ("signed_margin_change", "EBIT-marginaalimuutos QoQ")),
        "WORKING_CAPITAL_SHIFT_CANDIDATE": (("signed_delta_onwc", "ONWC-muutos"), ("asset_scale", "Taseskaala")),
    }
    output = []
    percentage_fields = {"revenue_shift_ratio", "ebit_shift_ratio", "current_capex_intensity", "prior_capex_intensity", "median_yield", "maximum_yield"}
    for key, label in fields.get(flag, ()):
        value = evidence.get(key)
        rendered = _pp(value) if key == "signed_margin_change" else _percentage(value) if key in percentage_fields else _money(value) if key in {"signed_change_difference", "revenue_scale", "signed_net_debt_change", "signed_delta_onwc", "asset_scale"} else _number(value)
        output.append(f"{label}: {rendered}")
    return "; ".join(output) or "—"


def _diagnostic_metric(evaluation: Mapping[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    if evaluation["flag_name"] == "VALUATION_YIELD_OUTLIER":
        return f"mediaani {_percentage(evidence.get('median_yield'), 4)}; maksimi {_percentage(evidence.get('maximum_yield'), 4)}"
    if evaluation["flag_name"] == "RECENT_MARGIN_DECELERATION_REVIEW":
        return _pp(evidence.get("signed_margin_change"))
    return _percentage(evidence.get("metric_value"), 4)


def _diagnostic_threshold(evaluation: Mapping[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    if "threshold" in evidence:
        return _percentage(evidence["threshold"])
    if evaluation["flag_name"] == "VALUATION_YIELD_OUTLIER":
        return f"mediaani {_percentage(evidence.get('median_threshold'))}; maksimi {_percentage(evidence.get('maximum_threshold'))}"
    if evaluation["flag_name"] == "RECENT_MARGIN_DECELERATION_REVIEW":
        return f"Trajectory ≥ {_number(evidence.get('trajectory_threshold'))}; marginaali ≤ {_pp(evidence.get('margin_change_threshold'))}"
    return "—"


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
    net_debt = current_absolute.get("net_debt")
    debt_label = "Net cash" if net_debt is not None and float(net_debt) < 0 else "Net debt"
    debt_value = abs(float(net_debt)) if net_debt is not None and float(net_debt) < 0 else net_debt
    candidate_note = (
        f"Odottava Lifecycle-siirtymä: {lifecycle['candidate_state']} (1/2). "
        f"Vahvistus vaatii vielä yhden peräkkäisen {lifecycle['candidate_state']} raw -havainnon."
        if lifecycle.get("candidate_state") else "Ei aktiivista odottavaa Lifecycle-siirtymää."
    )

    sections = [
        f"# {identity['ticker']} — Fundamental Snapshot",
        "",
        f"**{snapshot['history_notice']}**",
        "",
        "> Tulkinta: historia sisältää nykyisin revisioidut fundamentit, ei alkuperäistä PIT-rekonstruktiota. Nykyhintavaluation pitää viimeisimmän filing-endpointin fundamentit vakiona.",
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
            ("Vahvistetun tilan tenure", "—" if lifecycle.get("tenure_quarters") is None else f"{lifecycle['tenure_quarters']} kvartaalia"),
            ("Filing-date Absolute Valuation Score", _score(current_valuation.get("total_valuation_score"))),
            ("Valuation 4 havainnon keskiarvo", f"{_score(valuation_average)} ({snapshot['valuation_four_observation_count']}/4)"),
            ("Filing valuation vs 4Q average", _signed_score(filing_vs_average)),
            ("Indicative current-price Valuation Score", _score(current_price.get("total_valuation_score"))),
            ("Indicative current-price Valuation Score vs filing-date Valuation Score", _signed_score(current_change)),
            ("Fundamental-universumipersentiili", score_universe),
            ("Valuation-universumipersentiili", valuation_universe),
            ("Aktiivisia diagnostiikkalippuja", snapshot["diagnostic_counts"]["EVALUATED_FLAGGED"]),
            ("Data readiness", f"Score={_text(current_score.get('readiness_status'))}; Valuation={_text(current_valuation.get('valuation_status'))}; TTM={anchor['ttm_readiness']}"),
        ), ("left", "left")),
        "",
        "`vs 4Q average` on nykyhavainnon vertailu neljän havainnon keskiarvoon, ei trendimittari. Fundamental Trajectory on erillinen suuntakomponentti.",
        "",
        "## Fundamental Score -historia",
        "",
        _table(("Havainto", *HISTORY_HEADERS), (
            ("Fiscal quarter", *_history_values(snapshot, lambda slot: f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}")),
            ("Availability date", *_history_values(snapshot, lambda slot: _text(slot.get("availability_date")))),
            ("Fundamental Score", *_history_values(snapshot, lambda slot: _score((slot.get("score") or {}).get("total_score")))),
            ("Status", *_history_values(snapshot, lambda slot: _text((slot.get("score") or {}).get("readiness_status")))),
        )),
        "",
        "## Fundamental-komponenttien pistehistoria",
        "",
        _table(("Komponentti", "Maks.", *HISTORY_HEADERS), tuple(
            (COMPONENT_LABELS[name], _score(snapshot["component_contract"][name]), *_history_values(snapshot, lambda slot, component=name: _score(((slot.get("score") or {}).get("components") or {}).get(component, {}).get("component_score"))))
            for name in COMPONENTS
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
            ("EBIT margin TTM", *_history_values(snapshot, lambda slot: _percentage(slot["score_raw"]["ebit_margin_ttm"]))),
            ("EBIT margin direction (YoY)", *_history_values(snapshot, lambda slot: _pp(slot["score_raw"]["ebit_margin_direction"]))),
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
            (COMPONENT_LABELS.get(row["component_name"], row["component_name"]), _signed_score(row.get("qoq_delta")), _signed_score(row.get("two_quarter_delta")), _signed_score(row.get("yoy_delta")))
            for row in sorted(delta.get("components", []), key=lambda row: COMPONENTS.index(row["component_name"]))
        ) + (
            ("**Total Delta**", _signed_score(delta_total.get("qoq_delta")), _signed_score(delta_total.get("two_quarter_delta")), _signed_score(delta_total.get("yoy_delta"))),
            ("Readiness", _text(delta_total.get("qoq_status")), _text(delta_total.get("two_quarter_status")), _text(delta_total.get("yoy_status"))),
        )),
        "",
        "## Absoluuttiset fundamenttiarvot",
        "",
        _table(("Mittari", "t−4 (YoY comparison)", "Edellinen", "Nykyinen"), (
            *((label, _money(snapshot["absolute_values"]["yoy_base"].get(key)), _money(snapshot["absolute_values"]["previous"].get(key)), _money(snapshot["absolute_values"]["current"].get(key))) for key, label in (
                ("ttm_revenue", "Revenue TTM"), ("ttm_ebit", "EBIT TTM"),
                ("ttm_operating_cashflow", "Operating cash flow TTM"),
            )),
            ("Capex spend", *(
                _money(abs(float(values["ttm_capex"]))) if values.get("ttm_capex") is not None else "—"
                for values in (snapshot["absolute_values"]["yoy_base"], snapshot["absolute_values"]["previous"], snapshot["absolute_values"]["current"])
            )),
            *((label, _money(snapshot["absolute_values"]["yoy_base"].get(key)), _money(snapshot["absolute_values"]["previous"].get(key)), _money(snapshot["absolute_values"]["current"].get(key))) for key, label in (
                ("ttm_free_cashflow", "Free cash flow TTM"), ("ttm_net_income_common", "Common earnings TTM"),
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
        _table(("Kvartaali", "Saatavuuspäivä", "Raw state", "Vahvistettu final state", "Siirtymätila"), tuple(
            (f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}", _text((slot.get("row") or {}).get("source_available_date")), _text((slot.get("row") or {}).get("raw_state")), _text((slot.get("row") or {}).get("final_state")), _transition_text(slot["transition_status"]))
            for slot in lifecycle["history"]
        ), ("left", "left", "left", "left", "left")),
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
        "## Filing-date Valuation Score -historia",
        "",
        _table(("Havainto", *HISTORY_HEADERS), (
            ("Fiscal quarter", *_history_values(snapshot, lambda slot: f"FY{slot['fiscal_year']} {slot['fiscal_quarter']}")),
            ("Valuation price date", *_history_values(snapshot, lambda slot: _text((slot.get("valuation") or {}).get("price_date")))),
            ("Filing-date price", *_history_values(snapshot, lambda slot: _price((slot.get("valuation") or {}).get("selected_price")))),
            ("Valuation Score", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("total_valuation_score")))),
            ("Status", *_history_values(snapshot, lambda slot: _text((slot.get("valuation") or {}).get("valuation_status")))),
        )),
        "",
        f"Neljän havainnon keskiarvo käyttää vain t−3...t-havaintoja: {_score(valuation_average)} ({snapshot['valuation_four_observation_count']}/4). Se on vertailutaso, ei trendi.",
        "",
        "## Valuation-komponenttien pistehistoria",
        "",
        _table(("Komponentti", "Maks.", *HISTORY_HEADERS), (
            ("EBIT / EV", "40.00", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("ebit_points")))),
            ("FCF / Market Cap", "40.00", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("fcf_points")))),
            ("Common earnings / Market Cap", "20.00", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("earnings_points")))),
            ("**Valuation Score**", "**100.00**", *_history_values(snapshot, lambda slot: _score((slot.get("valuation") or {}).get("total_valuation_score")))),
        )),
        "",
        (
            f"Valuation-pistekatossa nykyisessä filing-endpointissa: {', '.join(valuation_ceilings)}. "
            + ("Kokonaispiste on 100, joten raw-yieldit voivat edelleen parantua ilman pisteiden nousua yli 100:n." if _at_ceiling(current_valuation.get("total_valuation_score"), 100.0) else "Raw-yield voi edelleen parantua ilman kyseisen komponentin pisteiden nousua.")
        ) if valuation_ceilings else "Yksikään Valuation-komponentti ei ole nykyisessä filing-endpointissa pistekatossa.",
        "",
        "## Valuation raw-yield -historia",
        "",
        _table(("Raw-mittari", *HISTORY_HEADERS), (
            ("EBIT / EV", *_history_values(snapshot, lambda slot: _percentage((slot.get("valuation") or {}).get("ebit_yield")))),
            ("FCF / Market Cap", *_history_values(snapshot, lambda slot: _percentage((slot.get("valuation") or {}).get("fcf_yield")))),
            ("Common earnings / Market Cap", *_history_values(snapshot, lambda slot: _percentage((slot.get("valuation") or {}).get("earnings_yield")))),
            ("Positive components", *_history_values(snapshot, lambda slot: "—" if not slot.get("valuation") else f"{sum((slot['valuation'].get(key) or 0) > 0 for key in ('ebit_yield', 'fcf_yield', 'earnings_yield'))}/3")),
        )),
        "",
        "## Filing-date Valuation comparisons",
        "",
        _table(("Komponentti", "QoQ", "2Q", "YoY"), tuple(
            (label, _signed_score(_filing_delta(history, key, 1)), _signed_score(_filing_delta(history, key, 2)), _signed_score(_filing_delta(history, key, 4)))
            for key, label in (("ebit_points", "EBIT / EV"), ("fcf_points", "FCF / Market Cap"), ("earnings_points", "Common earnings / Market Cap"), ("total_valuation_score", "Valuation Score"))
        )),
        "",
        _table(("Filing-price-muutos", "QoQ", "2Q", "YoY"), (
            ("Absoluuttinen", *(_signed_score(_filing_price_change(history, lag)[0]) for lag in (1, 2, 4))),
            ("Prosentuaalinen", *(_percentage(_filing_price_change(history, lag)[1]) for lag in (1, 2, 4))),
        )),
        "",
        "> Valuation Score history is not a pure price trend or pure fundamental trend. Each observation combines the fundamentals and the market price used on that filing’s valuation date.",
        "",
        "## Indicative current-price valuation",
        "",
        f"Tila: `{CURRENT_PRICE_LABEL}` / `{_text(current_price.get('valuation_status'))}` / `{_text(current_price.get('reason_code'))}`",
        "",
        _table(("Mittari", "Viimeisin filing-päivä", "Nykyhinta", "Muutos"), (
            ("Price date", _text(current_valuation.get("price_date")), _text(current_price.get("price_date")), "—"),
            ("Price", _price(current_valuation.get("selected_price")), _price(current_price.get("selected_price")), _signed_score(current_price_change)),
            ("Price change %", "—", "—", _percentage(current_price_change_pct)),
            ("Valuation Score", _score(current_valuation.get("total_valuation_score")), _score(current_price.get("total_valuation_score")), _signed_score(current_change)),
            ("EBIT / EV", _percentage(current_valuation.get("ebit_yield")), _percentage(current_price.get("ebit_yield")), _pp(None if current_valuation.get("ebit_yield") is None or current_price.get("ebit_yield") is None else current_price["ebit_yield"] - current_valuation["ebit_yield"])),
            ("FCF / Market Cap", _percentage(current_valuation.get("fcf_yield")), _percentage(current_price.get("fcf_yield")), _pp(None if current_valuation.get("fcf_yield") is None or current_price.get("fcf_yield") is None else current_price["fcf_yield"] - current_valuation["fcf_yield"])),
            ("Common earnings / Market Cap", _percentage(current_valuation.get("earnings_yield")), _percentage(current_price.get("earnings_yield")), _pp(None if current_valuation.get("earnings_yield") is None or current_price.get("earnings_yield") is None else current_price["earnings_yield"] - current_valuation["earnings_yield"])),
        )),
        "",
        "> Shares, debt and cash come from the latest fundamental filing and may differ from their true current-date values.",
        "",
        "Nykyhintalaskenta pitää anchor-fundamentit vakiona. Nykyhintapersentiiliä ei lasketa eikä esitetä.",
        "",
        "## Relative Position",
        "",
        "Alla oleva Ecosystem-sarake kertoo vain aktiivisen Relative Position -snapshotin kelpoisen ekosysteemivertailun tuloksen. Se ei ole taxonomy-layer-ranking eikä jäsenyystaulukon kopio.",
        "",
        _table(("Mittari", "Universe", "Sector", "Industry", "Ecosystem"), (
            ("Fundamental Score", *(_relative_cell(relative, "FUNDAMENTAL_SCORE", scope) for scope in ("UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM"))),
            ("Filing-date Valuation", *(_relative_cell(relative, "ABSOLUTE_VALUATION_SCORE", scope) for scope in ("UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM"))),
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
        _table(("Lippu", "Status", "Keskeinen evidenssi", "Laskettu arvo", "Raja"), tuple(
            (row["flag_name"], row["status"], _diagnostic_evidence(row), _diagnostic_metric(row), _diagnostic_threshold(row))
            for row in flagged
        ) or (("—", "Ei aktiivisia lippuja", "—", "—", "—"),), ("left", "left", "left", "right", "right")),
        "",
        "### Kaikki seitsemän statusta",
        "",
        _table(("Lippu", "Status", "Reason code", "Arvo", "Raja"), tuple(
            (row["flag_name"], row["status"], row["reason_code"], _diagnostic_metric(row), _diagnostic_threshold(row))
            for row in evaluations
        ), ("left", "left", "left", "right", "right")),
        "",
        "Liput ovat numeerisia review-candidate-havaintoja. Raportti ei päättele niiden syitä eikä vahvista kirjanpitotapahtumia.",
        "",
        "## Data readiness ja rajoitteet",
        "",
    ])
    missing_components = [name for name in COMPONENTS if ((current_score.get("components") or {}).get(name, {}).get("component_score") is None)]
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
            ("Anchor identity", f"company_id={anchor['company_id']}; quarter_id={anchor['quarter_id']}; FY{anchor['fiscal_year']} {anchor['fiscal_quarter']}"),
            *((f"Model fingerprint: {name}", value) for name, value in snapshot["model_fingerprints"].items()),
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
            ("Relative snapshot ID", _text((snapshot["source_state"].get("relative") or [None] * 5)[0])),
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
    return "\n".join(sections)


def render_snapshot(snapshot: Mapping[str, Any]) -> RenderedSnapshot:
    if snapshot.get("report_contract") != REPORT_CONTRACT:
        raise ValueError("SNAPSHOT_REPORT_CONTRACT_MISMATCH")
    template = _build_markdown(snapshot)
    if template.count(FINGERPRINT_PLACEHOLDER) != 1:
        raise RuntimeError("SNAPSHOT_FINGERPRINT_PLACEHOLDER_INVALID")
    content_fingerprint = hashlib.sha256(template.encode("utf-8")).hexdigest()
    markdown = template.replace(FINGERPRINT_PLACEHOLDER, content_fingerprint)
    if re.search(r"(?<![A-Za-z])(?:None|NaN|nan)(?![A-Za-z])", markdown):
        raise RuntimeError("SNAPSHOT_UNFORMATTED_INTERNAL_VALUE")
    return RenderedSnapshot(markdown=markdown, content_fingerprint=content_fingerprint)


def verify_rendered_report(rendered: RenderedSnapshot) -> bool:
    template = rendered.markdown.replace(rendered.content_fingerprint, FINGERPRINT_PLACEHOLDER, 1)
    return hashlib.sha256(template.encode("utf-8")).hexdigest() == rendered.content_fingerprint
