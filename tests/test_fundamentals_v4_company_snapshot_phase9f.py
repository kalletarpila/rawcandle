import csv
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals.operating_income_v2.persistence import PACKAGE_FINGERPRINT
from rawcandle.fundamentals.operating_income_v2.diagnostic_flags import (
    FLAG_NAMES,
    MODEL_CONTRACT as DIAGNOSTIC_MODEL_CONTRACT,
    REASON_CODES,
    REVENUE_SCALE_FLOOR,
)
from rawcandle.fundamentals.operating_income_v2.snapshot import MODEL_FINGERPRINT as SNAPSHOT_MODEL_FINGERPRINT
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.v2_assembler import REPORT_CONTRACT
from rawcandle.fundamentals.snapshot.v2_assembler import REPORT_PRESENTATION_FINGERPRINT
from rawcandle.fundamentals.snapshot.v2_assembler import _multiples_context
from rawcandle.fundamentals.snapshot.renderer import (
    ALL_DIAGNOSTICS_CLEAR_TEXT,
    DIAGNOSTIC_COVERAGE_TEXT,
    DIAGNOSTIC_DEFINITIONS,
    DIAGNOSTIC_LABELS,
    DIAGNOSTIC_REASON_EXPLANATIONS,
    INCOMPLETE_DIAGNOSTIC_COVERAGE_TEXT,
    UNKNOWN_DIAGNOSTIC_EXPLANATION,
    diagnostic_explanation,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def nvda_report(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, dict]:
    required = (
        "fundamentals_v4.db",
        "fundamentals_analysis.db",
        "osakedata.db",
        "analysis.db",
        "fundamentals_provider.db",
    )
    if not all((ROOT / "data" / name).exists() for name in required):
        pytest.skip("production-shaped read-only fixture databases are unavailable")
    paths = SnapshotPaths(*(ROOT / "data" / name for name in required))
    output = tmp_path_factory.mktemp("phase9f")
    first = generate_active_company_snapshot(
        paths, ticker="NVDA", report_date="2026-09-07", output_dir=output
    )
    second = generate_active_company_snapshot(
        paths, ticker="NVDA", report_date="2026-09-07", output_dir=output
    )
    assert first["status"] == "CREATED"
    assert second["status"] == "NO_CHANGE"
    assert first["report_content_fingerprint"] == second["report_content_fingerprint"]
    return Path(first["output_path"]).read_text(encoding="utf-8"), first["snapshot"]


@pytest.fixture(scope="module")
def phase9j_edge_reports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    required = (
        "fundamentals_v4.db",
        "fundamentals_analysis.db",
        "osakedata.db",
        "analysis.db",
        "fundamentals_provider.db",
    )
    if not all((ROOT / "data" / name).exists() for name in required):
        pytest.skip("production-shaped read-only fixture databases are unavailable")
    paths = SnapshotPaths(*(ROOT / "data" / name for name in required))
    output = tmp_path_factory.mktemp("phase9j-edges")
    reports = {}
    for ticker in ("CRMD", "APD", "AIV", "LEG", "AAT", "AGEN", "BNC", "AAOI", "ILLR"):
        result = generate_active_company_snapshot(
            paths, ticker=ticker, report_date="2026-09-07", output_dir=output
        )
        assert result["status"] == "CREATED"
        reports[ticker] = Path(result["output_path"]).read_text(encoding="utf-8")
    return reports


def test_v2_report_restores_compact_fiscal_histories(nvda_report: tuple[str, dict]) -> None:
    report, snapshot = nvda_report
    assert snapshot["report_contract"] == REPORT_CONTRACT
    assert len(snapshot["history"]) == 5
    assert len(snapshot["lifecycle"]["history"]) == 4
    assert "FY2027 Q2" in report
    assert "FY2027 Q1" in report
    assert "company_id" not in report
    assert "quarter_id" not in report
    assert "endpoint_id" not in report
    assert "fiscal_sequence" not in report


def test_v2_report_uses_operating_income_and_ten_three_point_metrics(nvda_report: tuple[str, dict]) -> None:
    report, snapshot = nvda_report
    for metric in (
        "Market Capitalization",
        "Enterprise Value",
        "P/E (Reported Common Earnings)",
        "Reported Common Earnings Yield",
        "P/FCF",
        "FCF Yield",
        "EV / Operating Income",
        "Operating Income / EV",
        "EV/Sales",
        "P/S",
    ):
        assert f"| {metric} |" in report
    assert "EBIT" not in report
    contexts = snapshot["valuation_multiples"]["contexts"]
    assert contexts[1]["fiscal_quarter"] == "Q2"
    assert contexts[2]["fiscal_quarter"] == "Q1"
    assert contexts[1]["fundamental_availability_date"] == "2026-08-26"
    assert contexts[2]["fundamental_availability_date"] == "2026-05-20"
    assert contexts[0]["ttm_period_end"] == contexts[1]["ttm_period_end"]
    assert contexts[2]["ttm_period_end"] != contexts[1]["ttm_period_end"]
    assert "### Valuation basis" in report
    assert "Reported Common Earnings TTM" in report
    assert "Reported common-shareholder earnings are a GAAP-based measure" in report
    assert "They are not normalized" in report
    assert "estimated adjusted earnings" not in report.lower()


def test_v2_report_formats_values_and_restores_context(nvda_report: tuple[str, dict]) -> None:
    report, _ = nvda_report
    assert "197.58B" in report
    assert "65.21%" in report
    assert "3.55%" in report
    assert "28.18x" in report
    assert "Currency: N/A (source currency not available in the validated contract)" in report
    assert "Datacenter" in report
    assert "Overall eligible universe" in report
    assert "n=2198" in report
    assert ALL_DIAGNOSTICS_CLEAR_TEXT in report
    assert "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V6" in report


def test_v2_report_current_and_filing_valuations_are_distinct(nvda_report: tuple[str, dict]) -> None:
    report, snapshot = nvda_report
    filing = snapshot["history"][-1]["valuation"]
    indicative = snapshot["current_price_valuation"]
    assert filing["price_date"] == "2026-08-26"
    assert indicative["price_date"] == "2026-09-04"
    assert "Latest endpoint (availability date)" in report
    assert "Current moment" in report
    assert "Indicative current-price Valuation Score" in report


def test_presentation_identity_is_separate_from_active_economic_bundle(
    nvda_report: tuple[str, dict],
) -> None:
    _, snapshot = nvda_report
    assert REPORT_PRESENTATION_FINGERPRINT == "8e88c312548974e14347b3db99853e63482a9dbf295af0e8f57671ca95930bfe"
    assert snapshot["model_fingerprints"]["snapshot"] == SNAPSHOT_MODEL_FINGERPRINT
    assert snapshot["source_state"]["active_package"][1] == PACKAGE_FINGERPRINT


def test_phase9j_2_definitions_are_complete_and_engine_reconciled(
    nvda_report: tuple[str, dict],
) -> None:
    report, _ = nvda_report
    assert tuple(row.flag_name for row in DIAGNOSTIC_DEFINITIONS) == FLAG_NAMES
    assert len({row.flag_name for row in DIAGNOSTIC_DEFINITIONS}) == 7
    assert set(DIAGNOSTIC_MODEL_CONTRACT["definitions"]) == set(FLAG_NAMES)
    assert REVENUE_SCALE_FLOOR == 10_000_000.0

    section = report.split("### Diagnostiikan määritelmät", maxsplit=1)[1].split(
        DIAGNOSTIC_COVERAGE_TEXT, maxsplit=1
    )[0]
    assert section.count("\n| ") == 9  # header, separator and seven definitions
    for row in DIAGNOSTIC_DEFINITIONS:
        assert section.count(f"| {DIAGNOSTIC_LABELS[row.flag_name]} |") == 1

    rendered = {row.flag_name: row for row in DIAGNOSTIC_DEFINITIONS}
    assert "tarkka fiscal Q−1" in rendered[FLAG_NAMES[0]].comparison
    assert "|Δ liikevaihto|/R" in rendered[FLAG_NAMES[0]].measurement
    assert "|Δ Operating Income|/R" in rendered[FLAG_NAMES[0]].measurement
    assert "≥ 20 %" in rendered[FLAG_NAMES[0]].trigger
    assert "10 M$" in rendered[FLAG_NAMES[0]].measurement

    assert "Reported Common Earnings" in rendered[FLAG_NAMES[1]].measurement
    assert "operating cash flow" in rendered[FLAG_NAMES[1]].measurement
    assert "≥ 20 %" in rendered[FLAG_NAMES[1]].trigger

    assert "|CAPEX|/max(liikevaihto, 10 M$)" in rendered[FLAG_NAMES[2]].measurement
    assert "≥ 10 pp" in rendered[FLAG_NAMES[2]].trigger

    assert "|Δ(kokonaisvelka − kassa)|/R" in rendered[FLAG_NAMES[3]].measurement
    assert "≥ 50 %" in rendered[FLAG_NAMES[3]].trigger

    assert "ei Q−1-vertailua" in rendered[FLAG_NAMES[4]].comparison
    assert "Operating Income/EV" in rendered[FLAG_NAMES[4]].measurement
    assert "FCF/Market Cap" in rendered[FLAG_NAMES[4]].measurement
    assert "mediaani ≥ 25 % TAI maksimi ≥ 50 %" in rendered[FLAG_NAMES[4]].trigger

    assert "Operating Margin" in rendered[FLAG_NAMES[5]].measurement
    assert "Trajectory ≥ 7 JA muutos ≤ −2 pp" in rendered[FLAG_NAMES[5]].trigger
    assert "Operating Income saa olla negatiivinen" in rendered[FLAG_NAMES[5]].trigger

    assert "canonical-kausi vs tarkka fiscal Q−1" in rendered[FLAG_NAMES[6]].comparison
    assert "|ΔONWC|/max(keskimääräinen taseen loppusumma, 10 M$)" in rendered[FLAG_NAMES[6]].measurement
    assert "myyntisaamiset + varasto − ostovelat − saadut ennakot" in rendered[FLAG_NAMES[6]].measurement
    assert "≥ 10 %" in rendered[FLAG_NAMES[6]].trigger
    assert "molemmat taseen loppusummat > 0" in rendered[FLAG_NAMES[6]].trigger

    for row in DIAGNOSTIC_DEFINITIONS:
        definition = DIAGNOSTIC_MODEL_CONTRACT["definitions"][row.flag_name]
        operators = definition.get("operators", (definition.get("operator"),))
        thresholds = definition.get("thresholds", (definition.get("threshold"),))
        assert all(operator in {">=", "<="} for operator in operators)
        assert all(threshold is not None for threshold in thresholds)


def test_phase9j_2_definition_audit_covers_exact_engine_contract() -> None:
    audit_path = (
        ROOT
        / "docs"
        / "fundamentals_v4"
        / "fundamentals_v4_company_snapshot_v2_phase9j_2_definition_audit.csv"
    )
    with audit_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(row["flag_identifier"] for row in rows) == FLAG_NAMES
    assert len(rows) == 7
    assert all(
        row["authoritative_rule"].endswith(definition.engine_rule)
        for row, definition in zip(rows, DIAGNOSTIC_DEFINITIONS)
    )
    assert all(row["threshold_and_operator"] for row in rows)
    assert all(row["rendered_finnish_definition"] for row in rows)


def test_phase9j_2_zero_flag_wording_preserves_readiness_scope(
    nvda_report: tuple[str, dict],
    phase9j_edge_reports: dict[str, str],
) -> None:
    nvda, snapshot = nvda_report
    assert {row["status"] for row in snapshot["diagnostic"]["evaluations"]} == {
        "EVALUATED_CLEAR"
    }
    assert ALL_DIAGNOSTICS_CLEAR_TEXT in nvda
    assert INCOMPLETE_DIAGNOSTIC_COVERAGE_TEXT not in nvda

    for ticker in ("BNC", "AAT"):
        assert INCOMPLETE_DIAGNOSTIC_COVERAGE_TEXT in phase9j_edge_reports[ticker]
        assert ALL_DIAGNOSTICS_CLEAR_TEXT not in phase9j_edge_reports[ticker]
    assert "FLAG_NOT_READY" in phase9j_edge_reports["BNC"]
    assert "EVALUATED_CLEAR" in phase9j_edge_reports["BNC"]
    assert "FLAG_NOT_APPLICABLE" in phase9j_edge_reports["AAT"]


def test_phase9j_2_active_flags_remain_candidates_with_limited_scope(
    phase9j_edge_reports: dict[str, str],
) -> None:
    for ticker in ("AGEN", "APD", "AAOI", "ILLR", "CRMD"):
        report = phase9j_edge_reports[ticker]
        assert "TARKASTETTAVA EHDOKAS" in report
        assert ALL_DIAGNOSTICS_CLEAR_TEXT not in report
        assert INCOMPLETE_DIAGNOSTIC_COVERAGE_TEXT not in report
        assert DIAGNOSTIC_COVERAGE_TEXT in report
        assert "eikä vahvista kirjanpitotapahtumia" in report


@pytest.mark.parametrize(
    ("operating_income", "expected"),
    ((10.0, "VALUE"), (0.0, "N_M"), (-10.0, "N_M"), (None, "N_A")),
)
def test_v2_multiple_operating_income_numerator_contract(
    operating_income: float | None, expected: str
) -> None:
    context = _multiples_context(
        evaluation_point="CURRENT_MOMENT",
        ttm={
            "shares_outstanding": 10.0,
            "total_debt": 0.0,
            "cash": 0.0,
            "ttm_revenue": 100.0,
            "ttm_operating_income": operating_income,
            "ttm_free_cashflow": 10.0,
            "ttm_net_income_common": 10.0,
            "net_income_common_4q_ready": 1,
        },
        persisted=None,
        fiscal_year=2026,
        fiscal_quarter="Q2",
        availability_date="2026-08-01",
        price_date="2026-09-01",
        price=10.0,
        price_eligible=True,
    )
    assert context["metrics"]["ev_operating_income"]["status"] == expected
    assert context["metrics"]["operating_income_yield"]["status"] == expected


@pytest.mark.parametrize(
    ("price", "eligible", "cash", "market_status", "enterprise_ratio_status"),
    (
        (None, True, 0.0, "N_A", "N_A"),
        (10.0, False, 0.0, "N_A", "N_A"),
        (0.0, True, 0.0, "N_M", "N_M"),
        (10.0, True, 100.0, "VALUE", "N_M"),
    ),
)
def test_v2_multiple_denominator_contract(
    price: float | None,
    eligible: bool,
    cash: float,
    market_status: str,
    enterprise_ratio_status: str,
) -> None:
    context = _multiples_context(
        evaluation_point="CURRENT_MOMENT",
        ttm={
            "shares_outstanding": 10.0,
            "total_debt": 0.0,
            "cash": cash,
            "ttm_revenue": 100.0,
            "ttm_operating_income": 10.0,
            "ttm_free_cashflow": 10.0,
            "ttm_net_income_common": 10.0,
            "net_income_common_4q_ready": 1,
        },
        persisted=None,
        fiscal_year=2026,
        fiscal_quarter="Q2",
        availability_date="2026-08-01",
        price_date="2026-09-01",
        price=price,
        price_eligible=eligible,
    )
    assert context["metrics"]["market_cap"]["status"] == market_status
    assert context["metrics"]["ev_operating_income"]["status"] == enterprise_ratio_status


@pytest.mark.parametrize(
    ("common_earnings", "ready", "expected_status"),
    (
        (25.0, 1, "VALUE"),
        (0.0, 1, "N_M"),
        (-25.0, 1, "N_M"),
        (None, 0, "N_A"),
    ),
)
def test_reported_common_earnings_multiple_contract(
    common_earnings: float | None,
    ready: int,
    expected_status: str,
) -> None:
    context = _multiples_context(
        evaluation_point="CURRENT_MOMENT",
        ttm={
            "shares_outstanding": 10.0,
            "total_debt": 0.0,
            "cash": 0.0,
            "ttm_revenue": 100.0,
            "ttm_operating_income": 10.0,
            "ttm_free_cashflow": 10.0,
            "ttm_net_income_common": common_earnings,
            "net_income_common_4q_ready": ready,
        },
        persisted=None,
        fiscal_year=2026,
        fiscal_quarter="Q2",
        period_end="2026-06-30",
        availability_date="2026-08-01",
        price_date="2026-09-01",
        price=10.0,
        price_eligible=True,
    )
    assert context["source_inputs"]["ttm_net_income_common"] == common_earnings
    assert context["ttm_period_end"] == "2026-06-30"
    assert context["metrics"]["earnings_yield"]["status"] == expected_status
    assert context["metrics"]["pe"]["status"] == expected_status
    if expected_status == "VALUE":
        assert context["metrics"]["earnings_yield"]["value"] == 0.25
        assert context["metrics"]["pe"]["value"] == 4.0
    assert all(check["ok"] for check in context["reconciliation"])


def test_nvda_three_context_common_earnings_reconciles_at_full_precision(
    nvda_report: tuple[str, dict],
) -> None:
    _, snapshot = nvda_report
    current, latest, previous = snapshot["valuation_multiples"]["contexts"]
    assert current["source_inputs"]["ttm_net_income_common"] == pytest.approx(
        192_879_000_000.0, rel=0, abs=0
    )
    assert current["source_inputs"]["ttm_net_income_common"] == latest["source_inputs"]["ttm_net_income_common"]
    assert current["price_date"] != latest["price_date"]
    assert current["metrics"]["market_cap"]["value"] != latest["metrics"]["market_cap"]["value"]
    assert previous["fiscal_quarter"] == "Q1"
    for context in (current, latest, previous):
        assert all(check["ok"] for check in context["reconciliation"])


def test_phase9i_edge_reports_preserve_na_nm_stale_and_not_applicable(
    phase9j_edge_reports: dict[str, str],
) -> None:
    assert "| Reported Common Earnings Yield | 28.49% | 29.50% | 29.10% |" in phase9j_edge_reports["CRMD"]
    assert "| Reported Common Earnings TTM | −47.30M | −47.30M | 2.11B |" in phase9j_edge_reports["APD"]
    assert "| P/E (Reported Common Earnings) | N/M | N/M | 31.71x |" in phase9j_edge_reports["APD"]
    assert "| Reported Common Earnings TTM | N/A | N/A | 554.01M |" in phase9j_edge_reports["AIV"]
    assert "CURRENT_PRICE_FALLBACK_TOO_OLD" in phase9j_edge_reports["LEG"]
    assert "| Market cap used | N/A | 1.31B | 1.41B |" in phase9j_edge_reports["LEG"]
    assert "VALUATION_NOT_APPLICABLE" in phase9j_edge_reports["AAT"]
    for report in phase9j_edge_reports.values():
        assert "company_id" not in report
        assert "quarter_id" not in report
        assert "167.522" not in report


def test_phase9j_uses_precise_availability_and_score_point_terminology(
    nvda_report: tuple[str, dict],
) -> None:
    report, _ = nvda_report
    assert "Source availability date" in report
    assert "Source availability / filing date" not in report
    assert "Latest filing" not in report
    assert "Previous filing" not in report
    assert "Filing-date Valuation" not in report
    assert "## Valuation-komponenttien pistemuutokset" in report
    assert "QoQ (pistettä)" in report
    assert "eivät ole raw-yieldien prosenttiyksikkömuutoksia" in report
    assert "Saatavuuspäivän hinnan muutos" in report
    assert "Price change %" in report


def test_phase9j_1_mixed_unit_table_labels_only_score_difference_as_points(
    nvda_report: tuple[str, dict],
    phase9j_edge_reports: dict[str, str],
) -> None:
    report, snapshot = nvda_report
    assert "| Mittari | Viimeisin saatavuuspäivä | Nykyhinta | Muutos |" in report
    assert "| Valuation Score | 27.02 | 24.15 | −2.87 p |" in report
    assert "Valuation Score (muutos pistettä)" not in report
    assert "| Price | 209.66 | 230.36 | +20.70 |" in report
    assert "| Price change % | — | — | 9.87% |" in report
    assert "| Operating Income / EV | 3.90% | 3.55% | −0.35 pp |" in report
    assert "| Valuation Score | — | — | — |" in phase9j_edge_reports["AAT"]
    assert "| Valuation Score | — | — | — p |" not in phase9j_edge_reports["AAT"]
    assert snapshot["history"][-1]["valuation"]["total_valuation_score"] == pytest.approx(27.02, abs=0.005)
    assert snapshot["current_price_valuation"]["total_valuation_score"] == pytest.approx(24.15, abs=0.005)


def test_phase9j_1_finnish_history_tables_use_saatavuuspaiva(
    nvda_report: tuple[str, dict],
) -> None:
    report, snapshot = nvda_report
    assert "| Saatavuuspäivä | 2025-08-27 | 2025-11-19 | 2026-02-25 | 2026-05-20 | 2026-08-26 |" in report
    assert "| Availability date |" not in report
    assert snapshot["history"][-1]["availability_date"] == "2026-08-26"


def test_phase9j_diagnostic_explanations_cover_engine_and_production_contract() -> None:
    assert set(DIAGNOSTIC_REASON_EXPLANATIONS) == set(REASON_CODES)
    analysis = ROOT / "data" / "fundamentals_analysis.db"
    if not analysis.exists():
        pytest.skip("production-shaped read-only fixture database is unavailable")
    connection = sqlite3.connect(f"file:{analysis.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        production_combinations = set(
            connection.execute(
                "SELECT DISTINCT f.flag_name,s.status_text,r.reason_text "
                "FROM diagnostic_flag_evaluation e "
                "JOIN diagnostic_flag_endpoint ep USING(endpoint_id) "
                "JOIN diagnostic_flag_package p USING(package_id) "
                "JOIN diagnostic_flag_type f USING(flag_id) "
                "JOIN diagnostic_flag_status s USING(status_id) "
                "JOIN diagnostic_flag_reason r USING(reason_id) "
                "WHERE p.model_fingerprint=?",
                ("7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031",),
            )
        )
    finally:
        connection.close()
    production_reasons = {row[2] for row in production_combinations}
    assert len(production_combinations) == 50
    assert production_reasons <= set(DIAGNOSTIC_REASON_EXPLANATIONS)
    for _, _, reason in production_combinations:
        explanation = diagnostic_explanation({"reason_code": reason})
        assert explanation != UNKNOWN_DIAGNOSTIC_EXPLANATION
        assert reason not in explanation


def test_phase9j_unknown_diagnostic_reason_is_neutral_and_does_not_leak_code() -> None:
    unknown = "FUTURE_INTERNAL_REASON_CODE"
    explanation = diagnostic_explanation({"reason_code": unknown})
    assert explanation == UNKNOWN_DIAGNOSTIC_EXPLANATION
    assert unknown not in explanation


def test_phase9j_package_identifiers_exist_only_in_technical_appendix(
    nvda_report: tuple[str, dict],
) -> None:
    report, snapshot = nvda_report
    analysis, technical = report.split("## Tekninen liite", maxsplit=1)
    family_fingerprint, package_fingerprint = snapshot["source_state"]["active_package"]
    assert package_fingerprint not in analysis
    assert family_fingerprint not in analysis
    assert "Aktiivinen V2-paketti" not in analysis
    assert technical.count(package_fingerprint) == 1
    assert technical.count(family_fingerprint) == 1
    assert "Active package fingerprint" in technical
    assert "Model-family fingerprint" in technical
    assert "Snapshot economic fingerprint" in technical


def test_phase9j_main_report_does_not_render_diagnostic_reason_codes(
    phase9j_edge_reports: dict[str, str],
) -> None:
    for report in phase9j_edge_reports.values():
        analysis = report.split("## Tekninen liite", maxsplit=1)[0]
        assert "| Lippu | Status | Tulkinta | Arvo | Raja |" in analysis
        assert "Reason code" not in analysis
        assert all(
            reason not in analysis
            for reason in REASON_CODES
            if reason != "VALUATION_NOT_APPLICABLE"
        )


def test_phase9j_explanations_keep_diagnostic_statuses_distinct(
    phase9j_edge_reports: dict[str, str],
) -> None:
    assert "Käyttöpääoman muutos jäi tarkastusrajan alle." in phase9j_edge_reports["CRMD"]
    assert "Käyttöpääoman muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas." in phase9j_edge_reports["AGEN"]
    assert "CAPEX-intensiteetin muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas." in phase9j_edge_reports["AAOI"]
    assert "Vähintään yksi lipun vaatima lähdearvo puuttuu." in phase9j_edge_reports["BNC"]
    assert "Fiscal-ketju ei ole katkeamaton." in phase9j_edge_reports["ILLR"]
    assert "Lippu ei sovellu tähän tuettujen mallien ulkopuoliseen kirjanpitoluokkaan." in phase9j_edge_reports["AAT"]
    assert "EVALUATED_CLEAR" in phase9j_edge_reports["CRMD"]
    assert "EVALUATED_FLAGGED" in phase9j_edge_reports["AGEN"]
    assert "FLAG_NOT_READY" in phase9j_edge_reports["BNC"]
    assert "FLAG_NOT_APPLICABLE" in phase9j_edge_reports["AAT"]
