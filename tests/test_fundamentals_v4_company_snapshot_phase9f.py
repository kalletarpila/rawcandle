from pathlib import Path

import pytest

from rawcandle.fundamentals.operating_income_v2.persistence import PACKAGE_FINGERPRINT
from rawcandle.fundamentals.operating_income_v2.snapshot import MODEL_FINGERPRINT as SNAPSHOT_MODEL_FINGERPRINT
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.v2_assembler import REPORT_CONTRACT
from rawcandle.fundamentals.snapshot.v2_assembler import REPORT_PRESENTATION_FINGERPRINT
from rawcandle.fundamentals.snapshot.v2_assembler import _multiples_context


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
        "P/E",
        "Earnings Yield",
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
    assert "No active diagnostic flags" in report
    assert "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V2" in report


def test_v2_report_current_and_filing_valuations_are_distinct(nvda_report: tuple[str, dict]) -> None:
    report, snapshot = nvda_report
    filing = snapshot["history"][-1]["valuation"]
    indicative = snapshot["current_price_valuation"]
    assert filing["price_date"] == "2026-08-26"
    assert indicative["price_date"] == "2026-09-04"
    assert "Latest filing" in report
    assert "Current moment" in report
    assert "Indicative current-price Valuation Score" in report


def test_presentation_identity_is_separate_from_active_economic_bundle(
    nvda_report: tuple[str, dict],
) -> None:
    _, snapshot = nvda_report
    assert REPORT_PRESENTATION_FINGERPRINT == "bc4b4a3b355063697f1fe3182a105342d804a59bb41a86ec40ef6fe4364abee2"
    assert snapshot["model_fingerprints"]["snapshot"] == SNAPSHOT_MODEL_FINGERPRINT
    assert snapshot["source_state"]["active_package"][1] == PACKAGE_FINGERPRINT


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
