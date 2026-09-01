from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from rawcandle.fundamentals.schema.migrations import bootstrap_all, connect, migrate_valuation_foundation
from rawcandle.fundamentals.ttm.engine import compute_ttm_rows
from rawcandle.fundamentals.valuation.engine import (
    BANK_INDUSTRIES,
    INSURANCE_INDUSTRIES,
    MODEL_CONTRACT,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    OTHER_UNSUPPORTED_FINANCIAL_INDUSTRIES,
    REIT_INDUSTRIES,
    PriceBar,
    ValuationObservation,
    calculate_valuation,
    classify_applicability,
    select_price,
)
from rawcandle.fundamentals.valuation.methodology import ANCHORS, piecewise_points


def observation(**overrides) -> ValuationObservation:
    values = {
        "company_id": 1,
        "security_id": 2,
        "ticker": "TEST",
        "fiscal_year": 2025,
        "fiscal_quarter": "Q4",
        "quarter_id": 4,
        "period_end": "2025-12-31",
        "fundamental_available_date": "2026-02-01",
        "ttm_readiness_status": "TTM_READY",
        "ttm_blocker_codes": (),
        "ttm_ebit": 6.0,
        "ttm_free_cashflow": 6.0,
        "ttm_net_income_common": 6.0,
        "net_income_common_4q_ready": True,
        "shares_outstanding": 10.0,
        "cash": 0.0,
        "total_debt": 0.0,
        "sector": "Technology",
        "industry": "Software - Application",
    }
    values.update(overrides)
    return ValuationObservation(**values)


def bar(day: str, close: float = 10.0, **overrides) -> PriceBar:
    values = {"price_date": day, "open": close, "high": close, "low": close, "close": close}
    values.update(overrides)
    return PriceBar(**values)


def quarter(qid: int, fiscal_quarter: str, **overrides) -> dict:
    values = {
        "company_id": 1,
        "company_key": "C1",
        "company_name": "Company",
        "security_id": 1,
        "ticker": "TEST",
        "quarter_id": qid,
        "fiscal_year": 2025,
        "fiscal_quarter": fiscal_quarter,
        "period_end": f"2025-{qid * 3:02d}-28",
        "source_availability_date": f"2025-{qid * 3:02d}-29",
        "first_public_result_date": None,
        "revenue": 10,
        "gross_profit": 9,
        "operating_income": 8,
        "ebit": 7,
        "ebitda": 6,
        "net_income": 5,
        "net_income_common": 4,
        "operating_cashflow": 4,
        "capex": -1,
        "free_cashflow": 3,
        "cash": 100,
        "total_debt": 50,
        "shares_outstanding": 20,
    }
    values.update(overrides)
    return values


def test_temporary_schema_adds_common_earnings_without_repurposing_net_income(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    bootstrap_all(provider, canonical, analysis, "now")
    with connect(provider) as conn:
        assert "netinccmn" in {row["name"] for row in conn.execute("PRAGMA table_info(sharadar_fundamental_observation)")}
    with connect(canonical) as conn:
        canonical_columns = {row["name"] for row in conn.execute("PRAGMA table_info(v4_quarter_financials)")}
        ttm_columns = {row["name"] for row in conn.execute("PRAGMA table_info(v4_ttm_values)")}
        assert {"net_income", "net_income_common"} <= canonical_columns
        assert {"ttm_net_income", "ttm_net_income_common", "net_income_common_4q_ready"} <= ttm_columns


def test_explicit_temporary_migration_backfills_common_earnings_and_is_idempotent(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    bootstrap_all(provider, canonical, analysis, "old")
    with connect(provider) as conn:
        conn.execute("ALTER TABLE sharadar_fundamental_observation DROP COLUMN netinccmn")
        conn.execute(
            "INSERT INTO provider_run(run_id,provider,started_at_utc,status,request_scope) VALUES ('R','SHARADAR','n','SUCCESS','test')"
        )
        conn.execute(
            """
            INSERT INTO provider_observation(
                observation_id,run_id,provider,provider_record_key,native_table,dimension,reportperiod,
                fetched_at_utc,content_hash,provider_status,payload_json
            ) VALUES ('O','R','SHARADAR','K','fundamentals','ARQ','2025-12-31','n','h','SUCCESS','{"netinccmn":"7"}')
            """
        )
        conn.execute(
            "INSERT INTO sharadar_fundamental_observation(observation_id,ticker,dimension,reportperiod,netinc) VALUES ('O','TEST','ARQ','2025-12-31',9)"
        )
    with connect(canonical) as conn:
        conn.execute("ALTER TABLE v4_quarter_financials DROP COLUMN net_income_common")
        conn.execute("ALTER TABLE v4_ttm_values DROP COLUMN ttm_net_income_common")
        conn.execute("ALTER TABLE v4_ttm_values DROP COLUMN net_income_common_4q_ready")
        conn.execute("INSERT INTO company(company_id,company_key,created_at_utc,updated_at_utc) VALUES (1,'C','n','n')")
        conn.execute(
            """
            INSERT INTO v4_quarter(
                quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,source_reportperiod,
                identity_provider,identity_status,created_at_utc,updated_at_utc
            ) VALUES (1,1,2025,'Q4','2025-12-31','2025-Q4','2025-12-31','SHARADAR','ACCEPTED','n','n')
            """
        )
        conn.execute(
            "INSERT INTO v4_quarter_financials(quarter_id,net_income,canonical_source_policy,created_at_utc,updated_at_utc) VALUES (1,9,'SHARADAR','n','n')"
        )
        conn.execute(
            """
            INSERT INTO v4_field_provenance(
                quarter_id,canonical_field,provider,provider_observation_id,source_native_field,
                transformation,accepted_at_utc,rule_version,confidence
            ) VALUES (1,'net_income','SHARADAR','O','netinc','DIRECT','n','V1','HIGH')
            """
        )
    first = migrate_valuation_foundation(provider, canonical, "new")
    second = migrate_valuation_foundation(provider, canonical, "new")
    assert first["provider_columns_added"] == 1
    assert first["canonical_columns_added"] == 1
    assert first["ttm_columns_added"] == 2
    assert first["provider_rows_backfilled"] == 1
    assert first["canonical_rows_backfilled"] == 1
    assert first["provenance_rows_added"] == 1
    assert second["provider_rows_backfilled"] == 0
    assert second["canonical_rows_backfilled"] == 0
    assert second["provenance_rows_added"] == 0
    with connect(canonical) as conn:
        row = conn.execute("SELECT net_income,net_income_common FROM v4_quarter_financials").fetchone()
        assert (row["net_income"], row["net_income_common"]) == (9, 7)


def test_phase3b_migration_refuses_production_paths() -> None:
    with pytest.raises(PermissionError, match="PHASE3B_PRODUCTION_SCHEMA_MIGRATION_NOT_AUTHORIZED"):
        migrate_valuation_foundation(
            Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
            Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
            "now",
        )


def test_common_earnings_ttm_is_four_quarter_sum_and_existing_net_income_is_preserved() -> None:
    rows = [quarter(index, f"Q{index}", net_income=index, net_income_common=index + 10) for index in range(1, 5)]
    result = compute_ttm_rows(rows, run_id="R", calculated_at="now")[-1]
    assert result["ttm_net_income"] == 10
    assert result["ttm_net_income_common"] == 50
    assert result["net_income_4q_ready"] == 1
    assert result["net_income_common_4q_ready"] == 1


def test_missing_common_earnings_does_not_change_existing_core_ttm_readiness() -> None:
    rows = [quarter(index, f"Q{index}") for index in range(1, 5)]
    rows[1]["net_income_common"] = None
    result = compute_ttm_rows(rows, run_id="R", calculated_at="now")[-1]
    assert result["readiness_status"] == "TTM_READY"
    assert result["core_ttm_ready"] == 1
    assert result["ttm_net_income"] == 20
    assert result["ttm_net_income_common"] is None
    assert result["net_income_common_4q_ready"] == 0


def test_invalid_fiscal_chain_does_not_form_common_ttm() -> None:
    rows = [quarter(1, "Q1"), quarter(2, "Q2"), quarter(4, "Q4")]
    result = compute_ttm_rows(rows, run_id="R", calculated_at="now")[-1]
    assert result["ttm_net_income_common"] is None
    assert result["net_income_common_4q_ready"] == 0


def test_revised_common_earnings_changes_only_additive_ttm_output() -> None:
    rows = [quarter(index, f"Q{index}") for index in range(1, 5)]
    first = compute_ttm_rows(rows, run_id="R1", calculated_at="one")[-1]
    revised = [dict(row) for row in rows]
    revised[0]["net_income_common"] = 40
    second = compute_ttm_rows(revised, run_id="R2", calculated_at="two")[-1]
    assert first["ttm_net_income"] == second["ttm_net_income"]
    assert first["ttm_net_income_common"] == 16
    assert second["ttm_net_income_common"] == 52
    assert first["output_fingerprint"] != second["output_fingerprint"]


@pytest.mark.parametrize("age", [0, 1, 2, 3])
def test_price_selection_accepts_same_day_and_three_day_backward_fallback(age: int) -> None:
    days = {0: "2026-02-01", 1: "2026-01-31", 2: "2026-01-30", 3: "2026-01-29"}
    selected = select_price([bar(days[age])], "2026-02-01")
    assert selected.reason_code is None
    assert selected.price_age_calendar_days == age
    assert selected.price_date == days[age]


def test_price_selection_rejects_four_day_fallback() -> None:
    selected = select_price([bar("2026-01-28")], "2026-02-01")
    assert selected.reason_code == "PRICE_FALLBACK_TOO_OLD"
    assert selected.price_age_calendar_days == 4


def test_price_selection_skips_incomplete_bar_and_never_looks_forward() -> None:
    selected = select_price(
        [bar("2026-02-01", high=None), bar("2026-01-31", 9.0), bar("2026-02-02", 11.0)],
        "2026-02-01",
    )
    assert selected.price_date == "2026-01-31"
    assert selected.selected_price == 9.0


def test_price_selection_weekend_style_gap_and_missing_history() -> None:
    assert select_price([bar("2026-01-30")], "2026-02-01").price_age_calendar_days == 2
    assert select_price([bar("2026-02-02")], "2026-02-01").reason_code == "PRICE_MISSING"


def test_price_selection_requires_valid_source_availability_date() -> None:
    assert select_price([bar("2026-02-01")], None).reason_code == "SOURCE_AVAILABILITY_DATE_MISSING"
    assert select_price([bar("2026-02-01")], "not-a-date").reason_code == "SOURCE_AVAILABILITY_DATE_INVALID"


@pytest.mark.parametrize("industry", sorted(REIT_INDUSTRIES))
def test_each_reviewed_reit_industry_is_not_applicable(industry: str) -> None:
    assert classify_applicability("Real Estate", industry).reason_code == "UNSUPPORTED_REIT_MODEL"


def test_non_reit_real_estate_company_is_supported() -> None:
    result = classify_applicability("Real Estate", "Real Estate Services")
    assert result.supported is True


@pytest.mark.parametrize("industry", sorted(BANK_INDUSTRIES))
def test_banks_are_not_applicable(industry: str) -> None:
    assert classify_applicability("Financial Services", industry).reason_code == "UNSUPPORTED_BANK_MODEL"


@pytest.mark.parametrize("industry", sorted(INSURANCE_INDUSTRIES))
def test_insurers_are_not_applicable(industry: str) -> None:
    assert classify_applicability("Financial Services", industry).reason_code == "UNSUPPORTED_INSURANCE_MODEL"


@pytest.mark.parametrize("industry", sorted(OTHER_UNSUPPORTED_FINANCIAL_INDUSTRIES))
def test_other_reviewed_financial_models_are_not_applicable(industry: str) -> None:
    assert classify_applicability("Financial Services", industry).reason_code == "UNSUPPORTED_FINANCIAL_MODEL"


def test_financial_data_exchange_and_ordinary_company_are_supported() -> None:
    assert classify_applicability("Financial Services", "Financial Data & Stock Exchanges").supported is True
    assert classify_applicability("Technology", "Semiconductors").supported is True


def test_missing_and_unrecognized_classification_are_not_silently_supported_or_excluded() -> None:
    assert classify_applicability(None, None).reason_code == "CLASSIFICATION_MISSING"
    result = classify_applicability("Financial Services", "Unknown Finance")
    assert result.supported is None
    assert result.reason_code == "CLASSIFICATION_UNRECOGNIZED"


@pytest.mark.parametrize(
    ("metric", "input_field", "points_field"),
    [
        ("ebit_yield", "ttm_ebit", "ebit_points"),
        ("fcf_yield", "ttm_free_cashflow", "fcf_points"),
        ("earnings_yield", "ttm_net_income_common", "earnings_points"),
    ],
)
def test_every_anchor_is_exact(metric: str, input_field: str, points_field: str) -> None:
    for yield_value, expected_points in ANCHORS[metric]:
        result = calculate_valuation(replace(observation(), **{input_field: yield_value * 100.0}), [bar("2026-02-01")])
        assert getattr(result, points_field) == pytest.approx(expected_points)


@pytest.mark.parametrize("metric", sorted(ANCHORS))
def test_interpolation_between_every_adjacent_anchor(metric: str) -> None:
    anchors = ANCHORS[metric]
    for left, right in zip(anchors, anchors[1:]):
        midpoint = (left[0] + right[0]) / 2
        expected = (left[1] + right[1]) / 2
        assert piecewise_points(midpoint, anchors) == pytest.approx(expected)


def test_piecewise_floor_and_ceiling() -> None:
    assert piecewise_points(-100, ANCHORS["ebit_yield"]) == 0
    assert piecewise_points(100, ANCHORS["ebit_yield"]) == 40


@pytest.mark.parametrize("field", ["ttm_ebit", "ttm_free_cashflow", "ttm_net_income_common"])
@pytest.mark.parametrize("value", [-1.0, 0.0])
def test_nonpositive_numerator_is_observed_zero_points(field: str, value: float) -> None:
    result = calculate_valuation(replace(observation(), **{field: value}), [bar("2026-02-01")])
    assert result.valuation_status == "VALUATION_FULL"
    points_field = {"ttm_ebit": "ebit_points", "ttm_free_cashflow": "fcf_points", "ttm_net_income_common": "earnings_points"}[field]
    assert getattr(result, points_field) == 0.0


@pytest.mark.parametrize(
    ("cash", "debt", "expected_net_debt"),
    [(0.0, 10.0, 10.0), (10.0, 10.0, 0.0), (20.0, 10.0, -10.0)],
)
def test_positive_zero_and_negative_net_debt(cash: float, debt: float, expected_net_debt: float) -> None:
    result = calculate_valuation(observation(cash=cash, total_debt=debt), [bar("2026-02-01")])
    assert result.valuation_status == "VALUATION_FULL"
    assert result.net_debt == expected_net_debt


def test_nonpositive_ev_is_not_ready_and_never_gets_full_points() -> None:
    result = calculate_valuation(observation(cash=100.0, total_debt=0.0), [bar("2026-02-01")])
    assert result.enterprise_value == 0.0
    assert result.valuation_status == "VALUATION_NOT_READY"
    assert result.reason_code == "ENTERPRISE_VALUE_NONPOSITIVE"
    assert result.total_valuation_score is None


def test_nonfinite_market_cap_is_not_ready() -> None:
    result = calculate_valuation(observation(shares_outstanding=1e308), [bar("2026-02-01")])
    assert result.valuation_status == "VALUATION_NOT_READY"
    assert result.reason_code == "MARKET_CAP_INVALID"


def test_common_earnings_readiness_flag_is_required() -> None:
    result = calculate_valuation(observation(net_income_common_4q_ready=False), [bar("2026-02-01")])
    assert result.valuation_status == "VALUATION_NOT_READY"
    assert result.reason_code == "COMMON_EARNINGS_HISTORY_INCOMPLETE"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"shares_outstanding": 0.0}, "SHARES_MISSING_OR_NONPOSITIVE"),
        ({"cash": None}, "CASH_MISSING"),
        ({"total_debt": None}, "DEBT_MISSING"),
        ({"ttm_ebit": None}, "TTM_EBIT_MISSING"),
        ({"ttm_free_cashflow": None}, "TTM_FCF_MISSING"),
        ({"ttm_net_income_common": None}, "COMMON_EARNINGS_HISTORY_INCOMPLETE"),
    ],
)
def test_missing_required_inputs_are_not_imputed(changes: dict, reason: str) -> None:
    result = calculate_valuation(replace(observation(), **changes), [bar("2026-02-01")])
    assert result.valuation_status == "VALUATION_NOT_READY"
    assert result.reason_code == reason
    assert result.total_valuation_score is None


def test_invalid_chain_and_not_ready_ttm_have_deterministic_reasons() -> None:
    invalid = observation(ttm_blocker_codes=("TTM_NON_CONTIGUOUS_WINDOW",))
    assert calculate_valuation(invalid, [bar("2026-02-01")]).reason_code == "INVALID_FISCAL_CHAIN"
    unready = observation(ttm_readiness_status="TTM_DATA_INSUFFICIENT")
    assert calculate_valuation(unready, [bar("2026-02-01")]).reason_code == "TTM_NOT_READY"


def test_not_applicable_is_not_economic_zero() -> None:
    reit = observation(sector="Real Estate", industry="REIT - Retail")
    result = calculate_valuation(reit, [bar("2026-02-01")])
    assert result.valuation_status == "VALUATION_NOT_APPLICABLE"
    assert result.total_valuation_score is None


def test_exact_40_40_20_aggregation_without_reweighting() -> None:
    result = calculate_valuation(
        observation(ttm_ebit=15.0, ttm_free_cashflow=20.0, ttm_net_income_common=15.0),
        [bar("2026-02-01")],
    )
    assert (result.ebit_points, result.fcf_points, result.earnings_points) == (40.0, 40.0, 20.0)
    assert result.total_valuation_score == 100.0


def test_model_contract_and_logical_result_are_deterministic() -> None:
    first = calculate_valuation(observation(), [bar("2026-02-01")])
    second = calculate_valuation(observation(), [bar("2026-02-01")])
    assert MODEL_VERSION == "ABSOLUTE_VALUATION_SCORE_V1"
    assert len(MODEL_FINGERPRINT) == 64
    assert MODEL_CONTRACT["weight_transfer"] is False
    assert first.result_fingerprint == second.result_fingerprint
    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json())["total_valuation_score"] == first.total_valuation_score
