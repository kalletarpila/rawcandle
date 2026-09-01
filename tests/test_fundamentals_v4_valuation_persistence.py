from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_valuation_rehearsal import build_parser, run as run_cli
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_database,
    connect,
    migrate_canonical_valuation_copy,
)
from rawcandle.fundamentals.ttm.engine import ensure_ttm_schema
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT, PriceBar, ValuationObservation
from rawcandle.fundamentals.valuation.persistence import (
    HISTORY_MODE,
    LOGICAL_FIELDS,
    ValuationRepository,
    ValuationSource,
    build_persisted_results,
    ensure_schema,
    logical_fingerprint,
    persisted_rows,
    quick_check,
    replace_results,
)
from rawcandle.fundamentals.valuation.phase3c import (
    deterministic_zero_sample,
    distribution_summary,
    sign_pattern,
    validate_destinations,
    zero_score_audit,
)


def observation(**changes: object) -> ValuationObservation:
    values = {
        "company_id": 1, "security_id": 1, "ticker": "TEST", "fiscal_year": 2025,
        "fiscal_quarter": "Q4", "quarter_id": 4, "period_end": "2025-12-31",
        "fundamental_available_date": "2026-02-01", "ttm_readiness_status": "TTM_READY",
        "ttm_blocker_codes": (), "ttm_ebit": 6.0, "ttm_free_cashflow": 6.0,
        "ttm_net_income_common": 6.0, "net_income_common_4q_ready": True,
        "shares_outstanding": 10.0, "cash": 10.0, "total_debt": 10.0,
        "sector": "Technology", "industry": "Software - Application",
    }
    values.update(changes)
    return ValuationObservation(**values)


def source(*observations: ValuationObservation) -> ValuationSource:
    rows = tuple({
        "observation": item,
        "price_bars": (PriceBar("2026-02-01", 10.0, 10.0, 10.0, 10.0),),
        "security_active": 1,
        "source_fingerprint": f"source-{item.quarter_id}",
    } for item in observations)
    return ValuationSource(rows, "global-source")


def rows(*observations: ValuationObservation) -> list[dict]:
    return build_persisted_results(source(*observations), calculated_at="2026-09-01T00:00:00Z")


def analysis_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def test_fresh_schema_and_full_rebuild_are_traceable() -> None:
    conn = analysis_connection()
    result_rows = rows(observation())
    report = replace_results(conn, result_rows)
    stored = persisted_rows(conn, model_fingerprint=MODEL_FINGERPRINT)
    assert report.rows_inserted == 1
    assert stored[0]["source_fingerprint"] == "source-4"
    assert stored[0]["history_mode"] == HISTORY_MODE
    assert quick_check(conn, expected_rows=result_rows)["ok"] is True


def test_identical_rerun_has_zero_writes() -> None:
    conn = analysis_connection()
    result_rows = rows(observation())
    first = replace_results(conn, result_rows)
    second = replace_results(conn, result_rows)
    assert first.rows_inserted == 1
    assert (second.rows_inserted, second.rows_deleted, second.rows_unchanged) == (0, 0, 1)
    assert first.result_fingerprint == second.result_fingerprint


def test_replace_rolls_back_on_injected_insert_failure() -> None:
    conn = analysis_connection()
    original = rows(observation())
    replace_results(conn, original)
    conn.execute("CREATE TRIGGER fail_new BEFORE INSERT ON valuation_revised_result WHEN NEW.ticker='FAIL' BEGIN SELECT RAISE(ABORT,'injected'); END")
    failing = rows(observation(ticker="FAIL", ttm_ebit=7.0))
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        replace_results(conn, failing)
    assert logical_fingerprint(persisted_rows(conn, model_fingerprint=MODEL_FINGERPRINT)) == logical_fingerprint(original)


def test_other_model_fingerprint_is_preserved() -> None:
    conn = analysis_connection()
    original = rows(observation())[0]
    columns = (*LOGICAL_FIELDS, "calculated_at_utc")
    other = dict(original)
    other["model_fingerprint"] = "other-model"
    other["result_fingerprint"] = "other-result"
    conn.execute(
        f"INSERT INTO valuation_revised_result ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        [other.get(column) for column in columns],
    )
    replace_results(conn, [original])
    assert conn.execute("SELECT COUNT(*) FROM valuation_revised_result WHERE model_fingerprint='other-model'").fetchone()[0] == 1


def test_unique_constraint_prevents_logical_duplicate() -> None:
    conn = analysis_connection()
    result_rows = rows(observation())
    replace_results(conn, result_rows)
    columns = (*LOGICAL_FIELDS, "calculated_at_utc")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"INSERT INTO valuation_revised_result ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [result_rows[0].get(column) for column in columns],
        )


@pytest.mark.parametrize("latest_status", ["VALUATION_NOT_READY", "VALUATION_NOT_APPLICABLE"])
def test_latest_reader_never_falls_back_to_older_full(latest_status: str) -> None:
    old = observation(fiscal_year=2025, fiscal_quarter="Q3", quarter_id=3)
    if latest_status == "VALUATION_NOT_READY":
        latest = observation(fiscal_year=2025, fiscal_quarter="Q4", quarter_id=4, ttm_readiness_status="TTM_DATA_INSUFFICIENT")
    else:
        latest = observation(fiscal_year=2025, fiscal_quarter="Q4", quarter_id=4, sector="Real Estate", industry="REIT - Retail")
    conn = analysis_connection()
    replace_results(conn, rows(old, latest))
    result = ValuationRepository(conn).latest_company(1, model_fingerprint=MODEL_FINGERPRINT)
    assert result["valuation_status"] == latest_status
    assert len(ValuationRepository(conn).history(1, model_fingerprint=MODEL_FINGERPRINT)) == 2
    assert ValuationRepository(conn).fiscal_quarter(1, 2025, "Q3", model_fingerprint=MODEL_FINGERPRINT)["valuation_status"] == "VALUATION_FULL"


def test_explicit_fingerprint_has_no_silent_fallback() -> None:
    conn = analysis_connection()
    replace_results(conn, rows(observation()))
    repo = ValuationRepository(conn)
    assert repo.latest_company(1, model_fingerprint="unknown") is None
    assert repo.current_universe(model_fingerprint="unknown", as_of_date="2026-09-01") == []


def test_current_universe_uses_latest_as_of_and_180_day_freshness() -> None:
    fresh = observation(company_id=1, quarter_id=4, fundamental_available_date="2026-08-01")
    stale = observation(company_id=2, security_id=2, ticker="OLD", quarter_id=8, fundamental_available_date="2026-01-01")
    conn = analysis_connection()
    replace_results(conn, rows(fresh, stale))
    current = ValuationRepository(conn).current_universe(model_fingerprint=MODEL_FINGERPRINT, as_of_date="2026-09-01")
    assert [row["company_id"] for row in current] == [1]


def test_zero_score_hard_invariant_and_sign_reconciliation() -> None:
    zero = rows(observation(ttm_ebit=-1.0, ttm_free_cashflow=0.0, ttm_net_income_common=-2.0))[0]
    positive = rows(observation(company_id=2, security_id=2, ticker="POS", quarter_id=8))[0]
    audit = zero_score_audit([zero, positive])
    assert audit["passed"] is True
    assert audit["zero_observations"] == 1
    assert audit["sign_patterns"]["nonpositive/nonpositive/nonpositive"]["count"] == 1
    assert sign_pattern(zero) == "nonpositive/nonpositive/nonpositive"


def test_missing_and_nonfinite_values_cannot_become_economic_zero() -> None:
    missing = rows(observation(ttm_net_income_common=None))[0]
    assert missing["valuation_status"] == "VALUATION_NOT_READY"
    assert missing["total_valuation_score"] is None
    nonfinite = rows(observation(ttm_ebit=float("nan")))[0]
    assert nonfinite["valuation_status"] == "VALUATION_NOT_READY"
    assert nonfinite["total_valuation_score"] is None


def test_deterministic_sample_and_nonoverlapping_bands() -> None:
    zero_rows = [rows(observation(company_id=index, security_id=index, ticker=f"Z{index}", quarter_id=index * 4, shares_outstanding=10.0 * index, ttm_ebit=-index, ttm_free_cashflow=-index, ttm_net_income_common=-index))[0] for index in range(1, 8)]
    assert deterministic_zero_sample(zero_rows) == deterministic_zero_sample(list(reversed(zero_rows)))
    summary = distribution_summary(zero_rows)
    assert sum(summary["score_bands"].values()) == 7
    assert summary["band_semantics"] == "[0,20),[20,40),[40,60),[60,80),[80,100]"


def test_destination_safety_blocks_production_source_and_symlink(tmp_path: Path) -> None:
    repo = Path("/home/kalle/projects/rawcandle")
    sources = {name: repo / "data" / name for name in ("fundamentals_v4.db", "fundamentals_analysis.db", "fundamentals_provider.db", "osakedata.db")}
    with pytest.raises(PermissionError, match="PRODUCTION_DESTINATION_BLOCKED"):
        validate_destinations(repo, canonical_source=sources["fundamentals_v4.db"], analysis_source=sources["fundamentals_analysis.db"], provider_source=sources["fundamentals_provider.db"], market_source=sources["osakedata.db"], canonical_destination=sources["fundamentals_v4.db"], analysis_destination=tmp_path / "a.db", apply=True)
    alias = tmp_path / "alias.db"
    alias.symlink_to(sources["fundamentals_v4.db"])
    with pytest.raises(PermissionError):
        validate_destinations(repo, canonical_source=sources["fundamentals_v4.db"], analysis_source=sources["fundamentals_analysis.db"], provider_source=sources["fundamentals_provider.db"], market_source=sources["osakedata.db"], canonical_destination=alias, analysis_destination=tmp_path / "a.db", apply=True)


def test_apply_requires_explicit_destinations(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    source_path.touch()
    with pytest.raises(ValueError, match="EXPLICIT_CANONICAL_AND_ANALYSIS"):
        validate_destinations(tmp_path, canonical_source=source_path, analysis_source=source_path, provider_source=source_path, market_source=source_path, canonical_destination=None, analysis_destination=None, apply=True)


def test_cli_defaults_to_dry_run(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("canonical.db", "provider.db", "analysis.db", "market.db")]
    for path in paths:
        path.touch()
    args = build_parser().parse_args([
        "--canonical-source", str(paths[0]), "--provider-source", str(paths[1]),
        "--analysis-source", str(paths[2]), "--market-source", str(paths[3]),
    ])
    report = run_cli(args)
    assert report["mode"] == "DRY_RUN"
    assert args.apply is False


def test_canonical_copy_migration_and_ttm_rebuild_are_idempotent(tmp_path: Path) -> None:
    provider, canonical = tmp_path / "provider.db", tmp_path / "canonical.db"
    bootstrap_database(provider, "fundamentals_provider", PROVIDER_SCHEMA_SQL, "old")
    bootstrap_database(canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "old")
    with connect(canonical) as conn:
        ensure_ttm_schema(conn)
        conn.execute("INSERT INTO company(company_id,company_key,company_name,created_at_utc,updated_at_utc) VALUES (1,'X','X','n','n')")
        conn.execute("INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) VALUES (1,1,'X',1,'n','n')")
        for qid in range(1, 5):
            conn.execute("INSERT INTO v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,source_reportperiod,identity_provider,identity_status,source_availability_date,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (qid, 1, 2025, f'Q{qid}', f'2025-{qid*3:02d}-28', f'Q{qid}', f'2025-{qid*3:02d}-28', 'SHARADAR', 'ACCEPTED', f'2025-{qid*3:02d}-29', 'n', 'n'))
            conn.execute("INSERT INTO v4_quarter_financials(quarter_id,net_income,canonical_source_policy,created_at_utc,updated_at_utc) VALUES (?,?,'SHARADAR','n','n')", (qid, qid * 10))
            conn.execute("INSERT INTO v4_field_provenance(quarter_id,canonical_field,provider,provider_observation_id,source_native_field,transformation,accepted_at_utc,rule_version,confidence) VALUES (?,'net_income','SHARADAR',?,'netinc','DIRECT','n','V1','HIGH')", (qid, f'O{qid}'))
        conn.execute("INSERT INTO v4_ttm_values(ttm_id,company_id,security_id,endpoint_quarter_id,endpoint_fiscal_year,endpoint_fiscal_quarter,period_end,model_version,calculation_version,readiness_status,blocker_codes_json,blocker_details_json,revenue_4q_ready,gross_profit_4q_ready,operating_income_4q_ready,ebit_4q_ready,ebitda_4q_ready,net_income_4q_ready,net_income_common_4q_ready,operating_cashflow_4q_ready,capex_4q_ready,free_cashflow_4q_ready,core_ttm_ready,input_quarter_ids_json,input_values_hash,canonical_financial_fingerprint,output_fingerprint,run_id,calculated_at_utc,created_at_utc,updated_at_utc) VALUES (1,1,1,4,2025,'Q4','2025-12-28','V4_TTM_EBIT_FIRST_V1','V1','TTM_READY','[]','[]',1,1,1,1,1,1,0,1,1,1,1,'[1,2,3,4]','i','c','o','r','n','n','n')")
        for position, qid in enumerate(range(1, 5), 1):
            conn.execute("INSERT INTO v4_ttm_input_quarter(ttm_id,input_position,input_quarter_id,input_fiscal_year,input_fiscal_quarter,period_end,source_availability_date,input_values_hash) VALUES (?,?,?,?,?,?,?,?)", (1, position, qid, 2025, f'Q{qid}', f'2025-{qid*3:02d}-28', f'2025-{qid*3:02d}-29', f'h{qid}'))
    with connect(provider) as conn:
        conn.execute("INSERT INTO provider_run(run_id,provider,started_at_utc,status,request_scope) VALUES ('R','SHARADAR','n','COMPLETE','TEST')")
        for qid in range(1, 5):
            payload = json.dumps({"netinccmn": qid})
            conn.execute("INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,provider_ticker,native_table,dimension,calendardate,reportperiod,fiscalperiod,source_availability_date,fetched_at_utc,content_hash,provider_status,payload_json) VALUES (?,'R','SHARADAR',?,'X','SF1','ARQ',?,?,?,?,'n',?,'ACCEPTED',?)", (f'O{qid}', f'K{qid}', f'2025-{qid*3:02d}-28', f'2025-{qid*3:02d}-28', f'Q{qid}', f'2025-{qid*3:02d}-29', f'h{qid}', payload))
    first = migrate_canonical_valuation_copy(canonical, provider, "new")
    second = migrate_canonical_valuation_copy(canonical, provider, "new")
    assert first["canonical_rows_backfilled"] == 4
    assert first["ttm_rows_changed"] == 1
    assert second["canonical_rows_backfilled"] == 0
    assert second["ttm_rows_changed"] == 0
    with connect(canonical) as conn:
        row = conn.execute("SELECT ttm_net_income,ttm_net_income_common,net_income_common_4q_ready FROM v4_ttm_values").fetchone()
        assert row["ttm_net_income"] is None
        assert (row["ttm_net_income_common"], row["net_income_common_4q_ready"]) == (10, 1)
