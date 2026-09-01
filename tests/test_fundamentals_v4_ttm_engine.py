from __future__ import annotations

import inspect
import json
from pathlib import Path

from rawcandle.fundamentals.schema.migrations import bootstrap_all, canonical_ttm_contract_present, connect
from rawcandle.fundamentals.ttm import engine
from rawcandle.fundamentals.ttm.engine import (
    FLOW_FIELDS,
    INSTANT_FIELDS,
    apply_ttm,
    canonical_financial_fingerprint,
    compute_ttm_rows,
    ensure_ttm_schema,
    hash_json,
    markdown_known_gaps,
    parity_analysis,
    ttm_fingerprints,
)


def q(company_id: int, qid: int, fy: int, fq: str, **overrides):
    row = {
        "company_id": company_id,
        "company_key": f"C{company_id}",
        "company_name": f"Company {company_id}",
        "security_id": company_id,
        "ticker": overrides.pop("ticker", f"T{company_id}"),
        "quarter_id": qid,
        "fiscal_year": fy,
        "fiscal_quarter": fq,
        "period_end": f"{fy}-{qid % 12 + 1:02d}-28",
        "source_availability_date": f"{fy}-{qid % 12 + 1:02d}-29",
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
    row.update(overrides)
    return row


def four_rows(**overrides):
    rows = [q(1, 1, 2025, "Q1"), q(1, 2, 2025, "Q2"), q(1, 3, 2025, "Q3"), q(1, 4, 2025, "Q4")]
    for row in rows:
        row.update(overrides)
    return rows


def endpoint(rows):
    return compute_ttm_rows(rows, run_id="R", calculated_at="2026-01-01T00:00:00Z", canonical_fingerprint="fp")[-1]


def create_db(tmp_path: Path) -> Path:
    provider = tmp_path / "fundamentals_provider.db"
    canonical = tmp_path / "fundamentals_v4.db"
    analysis = tmp_path / "fundamentals_analysis.db"
    bootstrap_all(provider, canonical, analysis, "2026-01-01T00:00:00Z")
    return canonical


def insert_company_quarters(db: Path, rows):
    with connect(db) as conn:
        conn.execute("INSERT INTO company(company_id,company_key,company_name,created_at_utc,updated_at_utc) VALUES (1,'C1','Company 1','n','n')")
        conn.execute("INSERT INTO security(security_id,company_id,current_ticker,created_at_utc,updated_at_utc) VALUES (1,1,'T1','n','n')")
        for row in rows:
            conn.execute("""
                INSERT INTO v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,source_reportperiod,identity_provider,identity_status,source_availability_date,created_at_utc,updated_at_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (row["quarter_id"], 1, row["fiscal_year"], row["fiscal_quarter"], row["period_end"], f"{row['fiscal_year']}-{row['fiscal_quarter']}", row["period_end"], "SHARADAR", "ACCEPTED", row["source_availability_date"], "n", "n"))
            conn.execute("""
                INSERT INTO v4_quarter_financials(quarter_id,revenue,gross_profit,operating_income,ebit,ebitda,net_income,operating_cashflow,capex,free_cashflow,cash,total_debt,shares_outstanding,canonical_source_policy,created_at_utc,updated_at_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (row["quarter_id"], row["revenue"], row["gross_profit"], row["operating_income"], row["ebit"], row["ebitda"], row["net_income"], row["operating_cashflow"], row["capex"], row["free_cashflow"], row["cash"], row["total_debt"], row["shares_outstanding"], "SHARADAR_ARQ", "n", "n"))
        conn.commit()


def test_ttm_engine_has_no_swingmaster_runtime_import():
    source = inspect.getsource(engine)
    assert "import swingmaster" not in source
    assert "from swingmaster" not in source


def test_flow_fields_sum_and_endpoint_fields_do_not_sum():
    rows = [q(1, 1, 2025, "Q1", revenue=1, ebit=2, free_cashflow=3, cash=10, total_debt=20, shares_outstanding=30), q(1, 2, 2025, "Q2", revenue=4, ebit=5, free_cashflow=6, cash=40, total_debt=50, shares_outstanding=60), q(1, 3, 2025, "Q3", revenue=7, ebit=8, free_cashflow=9, cash=70, total_debt=80, shares_outstanding=90), q(1, 4, 2025, "Q4", revenue=10, ebit=11, free_cashflow=12, cash=100, total_debt=110, shares_outstanding=120)]
    row = endpoint(rows)
    assert row["ttm_revenue"] == 22
    assert row["ttm_ebit"] == 26
    assert row["ttm_free_cashflow"] == 30
    assert row["cash"] == 100
    assert row["total_debt"] == 110
    assert row["shares_outstanding"] == 120
    assert row["readiness_status"] == "TTM_READY"


def test_q4_q1_rollover_and_non_calendar_fiscal_year_sequence():
    rows = [q(1, 1, 2025, "Q2", ticker="WDAY"), q(1, 2, 2025, "Q3", ticker="WDAY"), q(1, 3, 2025, "Q4", ticker="WDAY"), q(1, 4, 2026, "Q1", ticker="WDAY")]
    row = endpoint(rows)
    assert row["endpoint_fiscal_year"] == 2026
    assert row["endpoint_fiscal_quarter"] == "Q1"
    assert json.loads(row["input_quarter_ids_json"]) == [1, 2, 3, 4]
    assert row["readiness_status"] == "TTM_READY"


def test_historical_old_gap_does_not_block_valid_latest_four_quarters():
    rows = [q(1, 1, 2022, "Q1"), q(1, 5, 2025, "Q1"), q(1, 6, 2025, "Q2"), q(1, 7, 2025, "Q3"), q(1, 8, 2025, "Q4")]
    latest = endpoint(rows)
    assert latest["readiness_status"] == "TTM_READY"


def test_missing_latest_window_quarter_and_true_q4_gap_block_only_affected_windows():
    rows = [q(1, 1, 2025, "Q1"), q(1, 3, 2025, "Q3"), q(1, 4, 2025, "Q4"), q(1, 5, 2026, "Q1")]
    latest = endpoint(rows)
    blockers = set(json.loads(latest["blocker_codes_json"]))
    assert "TTM_MISSING_QUARTER" in blockers
    assert latest["readiness_status"] == "TTM_DATA_INSUFFICIENT"


def test_missing_required_inputs_are_explicit_and_multiple_reasons_preserved():
    rows = four_rows()
    rows[0]["revenue"] = None
    rows[1]["ebit"] = None
    rows[2]["free_cashflow"] = None
    rows[-1]["cash"] = None
    rows[-1]["total_debt"] = None
    rows[-1]["shares_outstanding"] = None
    row = endpoint(rows)
    blockers = set(json.loads(row["blocker_codes_json"]))
    assert {"TTM_MISSING_REVENUE", "TTM_MISSING_EBIT", "TTM_MISSING_FCF", "TTM_MISSING_CASH", "TTM_MISSING_DEBT", "TTM_MISSING_SHARES"} <= blockers
    assert row["ttm_revenue"] is None
    assert row["ttm_ebit"] is None
    assert row["ttm_free_cashflow"] is None


def test_null_not_converted_to_zero_and_zero_remains_zero():
    zero = endpoint(four_rows(revenue=0, ebit=0, free_cashflow=0, cash=0, total_debt=0, shares_outstanding=0))
    assert zero["ttm_revenue"] == 0
    assert zero["ttm_ebit"] == 0
    assert zero["ttm_free_cashflow"] == 0
    assert zero["shares_outstanding"] == 0
    rows = four_rows()
    rows[0]["revenue"] = None
    null = endpoint(rows)
    assert null["ttm_revenue"] is None
    assert "TTM_MISSING_REVENUE" in json.loads(null["blocker_codes_json"])


def test_readiness_fingerprint_source_availability_and_no_fake_public_date():
    rows = four_rows()
    rows[0]["source_availability_date"] = "2025-02-01"
    rows[1]["source_availability_date"] = "2025-05-01"
    rows[2]["source_availability_date"] = "2025-08-01"
    rows[3]["source_availability_date"] = "2025-11-01"
    first = endpoint(rows)
    second = endpoint(rows)
    assert first["ttm_source_available_date"] == "2025-11-01"
    assert first["first_public_result_date"] is None
    assert first["output_fingerprint"] == second["output_fingerprint"]


def test_ttm_schema_provenance_links_replay_and_canonical_fingerprint(tmp_path: Path):
    db = create_db(tmp_path)
    rows = four_rows()
    insert_company_quarters(db, rows)
    before = canonical_financial_fingerprint(db)
    computed = compute_ttm_rows(rows, run_id="R", calculated_at="2026-01-01T00:00:00Z", canonical_fingerprint=before)
    with connect(db) as conn:
        assert canonical_ttm_contract_present(conn)
        apply_ttm(conn, computed)
        fp1 = ttm_fingerprints(conn)
        apply_ttm(conn, computed)
        fp2 = ttm_fingerprints(conn)
        duplicate = conn.execute("SELECT COUNT(*) FROM (SELECT company_id,endpoint_quarter_id,model_version,COUNT(*) n FROM v4_ttm_values GROUP BY company_id,endpoint_quarter_id,model_version HAVING n>1)").fetchone()[0]
    assert fp1["row_count"] == fp2["row_count"] == 4
    assert fp1["values_hash"] == fp2["values_hash"]
    assert duplicate == 0
    assert canonical_financial_fingerprint(db) == before


def test_hard_case_tickers_and_alias_continuity_are_company_based():
    rows = [q(1, 1, 2025, "Q1", ticker="AAPL"), q(1, 2, 2025, "Q2", ticker="AAPL"), q(1, 3, 2025, "Q3", ticker="AAPL"), q(1, 4, 2025, "Q4", ticker="AAPL"), q(2, 5, 2025, "Q1", ticker="ASTH"), q(2, 6, 2025, "Q2", ticker="ASTH"), q(2, 7, 2025, "Q3", ticker="ASTH"), q(2, 8, 2025, "Q4", ticker="ASTH"), q(3, 9, 2025, "Q1", ticker="CECO"), q(3, 10, 2025, "Q2", ticker="CECO"), q(3, 11, 2025, "Q3", ticker="CECO"), q(3, 12, 2025, "Q4", ticker="CECO")]
    result = compute_ttm_rows(rows, run_id="R", calculated_at="n", canonical_fingerprint="fp")
    latest = {(row["ticker"], row["endpoint_fiscal_quarter"]): row["readiness_status"] for row in result}
    assert latest[("AAPL", "Q4")] == "TTM_READY"
    assert latest[("ASTH", "Q4")] == "TTM_READY"
    assert latest[("CECO", "Q4")] == "TTM_READY"


def test_v3_v4_parity_classifier_has_no_engine_logic_difference(tmp_path: Path):
    paths = engine.TtmPaths(tmp_path, tmp_path, tmp_path / "p.db", tmp_path / "c.db", tmp_path / "a.db", tmp_path / "missing_v3.db", tmp_path)
    rows, summary = parity_analysis(paths, [endpoint(four_rows())])
    assert rows == []
    assert summary["ENGINE_LOGIC_DIFFERENCE"] == 0
    assert summary["V3_MISSING"] == 1


def test_known_gaps_markdown_document_contract():
    summary = {"baseline": {"companies": 2, "securities": 2}, "ttm_readiness": {"TTM_READY": 1, "TTM_NOT_READY": 1, "blocker_counts": {"TTM_MISSING_EBIT": 1}}}
    known = [
        {"status": "OPEN", "issue_code": "TRUE_INTERNAL_MISSING_QUARTER", "category": "Fiscal / quarter continuity", "ticker": "OLD", "fiscal_year": "", "company_id": "1"},
        {"status": "OPEN", "issue_code": "TRUE_Q4_PROVIDER_GAP", "category": "Q4", "ticker": "Q4X", "fiscal_year": "2025", "company_id": "2"},
        {"status": "OPEN", "issue_code": "CIK_NULL", "category": "Identity", "ticker": "CIK", "company_id": "3"},
        {"status": "OPEN", "issue_code": "PERMATICKER_NULL", "category": "Identity", "ticker": "PM", "company_id": "4"},
        {"status": "OPEN", "issue_code": "SHARES_DISCONTINUITY_INSUFFICIENT_EVIDENCE", "category": "Shares", "ticker": "SH", "company_id": "5"},
    ]
    doc = markdown_known_gaps(summary, known, Path("temp/artifacts"), commit="abc123")
    assert "Known Gaps" in doc
    assert "TTM ready" in doc
    assert "Q4X 2025-Q4" in doc
    assert "PM" in doc
    assert "abc123" in doc


def test_no_downstream_provider_or_v3_execution_markers():
    source = inspect.getsource(engine)
    assert "query1.finance.yahoo" not in source
    assert "query2.finance.yahoo" not in source
    assert "sec.gov" not in source
    assert "score_result" in source
    assert "lifecycle_result" in source
    assert "valuation_result" in source
    assert "INSERT INTO score" not in source
    assert "INSERT INTO lifecycle" not in source
    assert "INSERT INTO valuation" not in source
