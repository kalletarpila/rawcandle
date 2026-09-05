from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from rawcandle.fundamentals.diagnostic_flags.engine import (
    DiagnosticEndpoint, DiagnosticInput, FLAG_NAMES, MODEL_FINGERPRINT, FlagStatus,
)
from rawcandle.fundamentals.diagnostic_flags.persistence import (
    EVALUATION_TABLE, ENDPOINT_TABLE, LAYOUT_FINGERPRINT, PACKAGE_TABLE, SCHEMA_STATEMENTS,
    apply_package, build_persistence_package, ensure_schema, quick_check,
)
from rawcandle.fundamentals.diagnostic_flags.readers import DiagnosticFlagRepository
from rawcandle.fundamentals.diagnostic_flags.phase6c import PIPELINE_PLACEMENT, validate_request
from rawcandle.fundamentals.diagnostic_flags.source import DiagnosticSource, DiagnosticSourceRow
from rawcandle.cli.run_fundamentals_v4_diagnostic_flags_phase6c import build_parser


def endpoint(company: int, current: bool, *, marker: float = 0.0) -> DiagnosticEndpoint:
    return DiagnosticEndpoint(
        company_id=company, quarter_id=company*10+(2 if current else 1), fiscal_year=2025,
        fiscal_quarter="Q4" if current else "Q3", fiscal_sequence=8104 if current else 8103,
        period_end="2025-12-31" if current else "2025-09-30",
        source_available_date="2026-02-01" if current else "2025-11-01",
        ttm_available_date="2026-02-02" if current else "2025-11-02", valuation_available_date="2026-02-03",
        ttm_status="TTM_READY", revenue=100_000_000, ebit=10_000_000+marker,
        common_earnings=8_000_000, operating_cashflow=9_000_000, capex=-2_000_000,
        cash=5_000_000, total_debt=10_000_000, accounts_receivable=10_000_000,
        inventory=5_000_000, accounts_payable=4_000_000, deferred_revenue=1_000_000,
        total_assets=100_000_000, trajectory=8 if current else None, valuation_status="VALUATION_FULL",
        valuation_reason="READY", applicability_classification="SUPPORTED",
        applicability_reason="SUPPORTED_OPERATING_CLASS", ebit_yield=.1, fcf_yield=.1, earnings_yield=.1,
    )


def source(marker: float = 0.0, include_company_one: bool = True) -> DiagnosticSource:
    rows=[]
    for company in (1,2):
        if company == 1 and not include_company_one: continue
        prior=endpoint(company,False)
        for current in (prior,endpoint(company,True,marker=marker if company==1 else 0.0)):
            previous=None if current is prior else prior
            rows.append(DiagnosticSourceRow(DiagnosticInput(current,previous,previous is not None),f"T{company}","Technology","Software","MATURE","READY",1_000_000_000))
    rows.sort(key=lambda row:(row.diagnostic_input.current.company_id,row.diagnostic_input.current.fiscal_sequence))
    return DiagnosticSource(tuple(rows),f"source-{marker}-{include_company_one}",())


@pytest.fixture
def conn():
    value=sqlite3.connect(":memory:"); value.row_factory=sqlite3.Row; value.execute("PRAGMA foreign_keys=ON")
    ensure_schema(value); yield value; value.close()


def test_schema_is_idempotent_normalized_and_has_no_json_or_replace():
    db=sqlite3.connect(":memory:"); ensure_schema(db); first=tuple(db.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name")); ensure_schema(db); second=tuple(db.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"))
    assert first==second and LAYOUT_FINGERPRINT
    text="\n".join(SCHEMA_STATEMENTS).upper()
    assert "WITHOUT ROWID" in text and "JSON" not in text and "INSERT OR REPLACE" not in text and "VACUUM" not in text


def test_upgraded_schema_preserves_existing_objects_and_stable_codebooks():
    db=sqlite3.connect(":memory:"); db.execute("CREATE TABLE unrelated(value TEXT)"); db.execute("INSERT INTO unrelated VALUES('keep')"); db.commit()
    ensure_schema(db); ensure_schema(db)
    assert db.execute("SELECT value FROM unrelated").fetchone()[0]=="keep"
    package=build_persistence_package(source()); apply_package(db,package,applied_at_utc="n")
    assert tuple(row[0] for row in db.execute("SELECT flag_name FROM diagnostic_flag_type ORDER BY flag_id"))==FLAG_NAMES
    assert set(row[0] for row in db.execute("SELECT status_text FROM diagnostic_flag_status"))=={status.value for status in FlagStatus}
    assert LAYOUT_FINGERPRINT=="f48e6e7b40071fe536b7846cac17c59d2fed7c0b118c4771813348877d065aba"


def test_full_apply_noop_and_exact_seven_contract(conn):
    package=build_persistence_package(source())
    first=apply_package(conn,package,applied_at_utc="n")
    assert (first.endpoint_inserted,first.evaluation_inserted)==(4,28)
    second=apply_package(conn,package,applied_at_utc="n")
    assert second.outcome=="NO_CHANGE" and second.endpoint_unchanged==4 and second.evaluation_unchanged==28
    assert quick_check(conn,authoritative_package=package)["ok"]
    assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]


def test_readers_cover_current_batch_history_cross_section_filter_and_metadata(conn):
    package=build_persistence_package(source()); apply_package(conn,package,applied_at_utc="n")
    repo=DiagnosticFlagRepository(conn)
    current=repo.current_company(1,model_fingerprint=MODEL_FINGERPRINT)
    assert current["fiscal_quarter"]=="Q4" and len(current["evaluations"])==7
    assert [row["flag_name"] for row in current["evaluations"]]==list(FLAG_NAMES)
    assert len(repo.current_batch((2,1),model_fingerprint=MODEL_FINGERPRINT))==2
    assert len(repo.history(1,model_fingerprint=MODEL_FINGERPRINT))==2
    assert len(repo.cross_section(2025,"Q4",model_fingerprint=MODEL_FINGERPRINT))==2
    assert len(repo.current_filtered(FLAG_NAMES[0],model_fingerprint=MODEL_FINGERPRINT))==2
    assert repo.endpoint(1,2025,"Q4",model_fingerprint=MODEL_FINGERPRINT)==current
    assert repo.package_metadata(model_fingerprint=MODEL_FINGERPRINT)["layout_fingerprint"]==LAYOUT_FINGERPRINT
    flagged=repo.current_flagged_universe(model_fingerprint=MODEL_FINGERPRINT)
    assert all(tuple(sorted(row["flags"],key=FLAG_NAMES.index))==row["flags"] for row in flagged)
    with pytest.raises(ValueError,match="FINGERPRINT_REJECTED"): repo.current_company(1,model_fingerprint="wrong")


def test_null_and_zero_round_trip_without_missing_as_clear(conn):
    package=build_persistence_package(source()); apply_package(conn,package,applied_at_utc="n")
    row=DiagnosticFlagRepository(conn).current_company(1,model_fingerprint=MODEL_FINGERPRINT)
    capex=next(item for item in row["evaluations"] if item["flag_name"]==FLAG_NAMES[2])
    assert capex["evidence"]["current_capex"]==-2_000_000
    valuation=next(item for item in row["evaluations"] if item["flag_name"]==FLAG_NAMES[4])
    assert valuation["comparison_quarter_id"] is None
    conn.execute(f"DELETE FROM {EVALUATION_TABLE} WHERE endpoint_id=(SELECT endpoint_id FROM {ENDPOINT_TABLE} WHERE company_id=1 ORDER BY fiscal_sequence DESC LIMIT 1) AND flag_id=1")
    with pytest.raises(RuntimeError,match="INCOMPLETE_NOT_CLEAR"): DiagnosticFlagRepository(conn).current_company(1,model_fingerprint=MODEL_FINGERPRINT)


def test_company_change_removal_restore_preserves_other_company(conn):
    base=build_persistence_package(source()); changed=build_persistence_package(source(marker=30_000_000)); removed=build_persistence_package(source(marker=30_000_000,include_company_one=False))
    apply_package(conn,base,applied_at_utc="n")
    company_two=tuple(conn.execute(f"SELECT result_fingerprint FROM {ENDPOINT_TABLE} WHERE company_id=2 ORDER BY fiscal_sequence"))
    report=apply_package(conn,changed,applied_at_utc="n",company_ids=(1,))
    assert report.evaluation_updated>=1 and apply_package(conn,changed,applied_at_utc="n",company_ids=(1,)).outcome=="NO_CHANGE"
    assert apply_package(conn,removed,applied_at_utc="n",company_ids=(1,)).endpoint_deleted==2
    assert apply_package(conn,base,applied_at_utc="n",company_ids=(1,)).endpoint_inserted==2
    assert tuple(conn.execute(f"SELECT result_fingerprint FROM {ENDPOINT_TABLE} WHERE company_id=2 ORDER BY fiscal_sequence"))==company_two


def test_full_rebuild_preserves_an_unrelated_model_package(conn):
    values=(999,"OTHER_PERSISTENCE","other-layout","OTHER_MODEL","other-model-fingerprint","OTHER_MODE","OTHER_HISTORY","other-evidence","source","economic","physical",1,0,"now")
    conn.execute(f"INSERT INTO {PACKAGE_TABLE} VALUES({','.join('?' for _ in values)})",values)
    conn.execute(f"""INSERT INTO {ENDPOINT_TABLE}(
      endpoint_id,package_id,company_id,quarter_id,fiscal_year,fiscal_quarter,fiscal_sequence,
      period_end,source_available_date,ttm_available_date,source_status_id,result_fingerprint)
      VALUES(999,999,999,999,2025,4,8104,'2025-12-31',NULL,NULL,NULL,'other-row')""")
    conn.commit()
    report=apply_package(conn,build_persistence_package(source()),applied_at_utc="n")
    assert report.retained_other_model_endpoints==1
    assert conn.execute(f"SELECT result_fingerprint FROM {ENDPOINT_TABLE} WHERE endpoint_id=999").fetchone()[0]=="other-row"


@pytest.mark.parametrize("stage",["codebooks","company_delete","package","endpoint_partial","endpoints","evaluation_partial","evaluations","final_verification"])
def test_every_apply_failure_rolls_back_and_reopens(tmp_path,stage):
    path=tmp_path/"analysis.db"; conn=sqlite3.connect(path); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON"); ensure_schema(conn)
    base=build_persistence_package(source()); changed=build_persistence_package(source(marker=30_000_000)); apply_package(conn,base,applied_at_utc="n"); before=quick_check(conn)["content_fingerprint"]
    with pytest.raises(RuntimeError,match="INJECTED_DIAGNOSTIC"): apply_package(conn,changed,applied_at_utc="n",company_ids=(1,),inject_failure_at=stage)
    conn.close(); reopened=sqlite3.connect(path); reopened.row_factory=sqlite3.Row; reopened.execute("PRAGMA foreign_keys=ON")
    assert quick_check(reopened)["content_fingerprint"]==before and reopened.execute("PRAGMA foreign_key_check").fetchall()==[]; reopened.close()


def test_schema_failure_rolls_back_completely():
    db=sqlite3.connect(":memory:")
    with pytest.raises(RuntimeError,match="SCHEMA_CREATION"): ensure_schema(db,inject_failure_at="schema_creation")
    assert db.execute(f"SELECT 1 FROM sqlite_schema WHERE name='{PACKAGE_TABLE}'").fetchone() is None


def test_phase6c_safety_rejects_production_aliases_and_wrong_destination(tmp_path):
    canonical=tmp_path/"canonical.db"; analysis=tmp_path/"analysis.db"; canonical.touch(); analysis.touch()
    common=dict(canonical_db=canonical,analysis_db=analysis,model_fingerprint=MODEL_FINGERPRINT,company_ids=(),full_universe=True)
    validate_request(**common,destination=analysis)
    with pytest.raises(PermissionError,match="CANONICAL_SOURCE"): validate_request(**common,destination=canonical)
    with pytest.raises(PermissionError,match="PRODUCTION_DESTINATION"): validate_request(**common,destination=Path('/home/kalle/projects/rawcandle/data/fundamentals_analysis.db'))
    link=tmp_path/"alias.db"; link.symlink_to(analysis)
    with pytest.raises(PermissionError,match="SYMLINK"): validate_request(canonical_db=canonical,analysis_db=link,destination=analysis,model_fingerprint=MODEL_FINGERPRINT,company_ids=(),full_universe=True)
    wrong=tmp_path/"provider-copy.db"
    with sqlite3.connect(wrong) as db: db.execute("CREATE TABLE provider_observation(id INTEGER)")
    with pytest.raises(PermissionError,match="INCORRECT_DESTINATION"): validate_request(**common,destination=wrong)
    with pytest.raises(ValueError,match="ABSOLUTE_DATABASE_PATHS"): validate_request(canonical_db=Path("canonical.db"),analysis_db=analysis,destination=analysis,model_fingerprint=MODEL_FINGERPRINT,company_ids=(),full_universe=True)


def test_phase6c_cli_is_dry_run_by_default_and_has_no_production_confirmation():
    parser=build_parser()
    args=parser.parse_args(["--canonical-db","/tmp/canonical.db","--analysis-db","/tmp/analysis.db","--destination","/tmp/destination.db","--model-fingerprint",MODEL_FINGERPRINT,"--full-universe"])
    assert args.apply is False
    assert "confirm-production" not in parser.format_help()


def test_phase6c_pipeline_plan_remains_historical_after_phase6d_activation():
    import inspect
    from rawcandle.fundamentals.score import engine as score_engine
    source=inspect.getsource(score_engine)
    assert PIPELINE_PLACEMENT["after"]=="VALUATION_REFRESH_COMMITTED"
    assert PIPELINE_PLACEMENT["delta_is_prerequisite"] is False
    assert PIPELINE_PLACEMENT["relative_position_is_prerequisite"] is False
    assert PIPELINE_PLACEMENT["phase6c_activation"] is False
    assert "refresh_diagnostic_after_valuation" in source
    assert source.index("refresh_diagnostic_after_valuation") < source.index(
        "refresh_delta_then_relative_position"
    )
