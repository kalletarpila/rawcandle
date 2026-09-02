from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_fundamentals_v4_delta_source import build_databases
from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import (
    COMPONENT_TABLE, LIFECYCLE_TABLE, META_TABLE, SCHEMA_STATEMENTS, TABLES, TOTAL_TABLE,
    VALUATION_TABLE, apply_package, build_persistence_package, ensure_schema, quick_check,
    recalculate_row_fingerprint, rebuild_package, schema_signature, validate_package,
)
from rawcandle.fundamentals.delta.phase5c import _readiness_reconciliation
from rawcandle.fundamentals.delta.readers import FundamentalDeltaRepository, LifecycleChangeRepository, ValuationChangeRepository
from rawcandle.fundamentals.delta.source import load_delta_source
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_FP
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_FP
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_FP


@pytest.fixture
def package(tmp_path):
    paths=build_databases(tmp_path/"source")
    source=load_delta_source(paths,score_model_fingerprint=SCORE_FP,lifecycle_model_fingerprint=LIFECYCLE_FP,valuation_model_fingerprint=VALUATION_FP)
    return build_persistence_package(source)


@pytest.fixture
def connection():
    conn=sqlite3.connect(":memory:"); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON"); ensure_schema(conn,applied_at_utc="2026-01-01T00:00:00Z"); conn.commit()
    yield conn; conn.close()


def changed_package(package, company_id=1):
    totals=[]
    changed=False
    for row in package.total_rows:
        if row["company_id"]==company_id and not changed:
            row={**row,"qoq_reason":f"{row['qoq_reason']}:TEST_CHANGE"}; row=recalculate_row_fingerprint(row); changed=True
        totals.append(row)
    return rebuild_package(totals,package.component_rows,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)


def without_company(package, company_id=1):
    return rebuild_package([r for r in package.total_rows if r["company_id"]!=company_id],[r for r in package.component_rows if r["company_id"]!=company_id],[r for r in package.lifecycle_rows if r["company_id"]!=company_id],[r for r in package.valuation_rows if r["company_id"]!=company_id],fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)


def with_second_company(package):
    id_map={row["fundamental_delta_result_id"]:row["fundamental_delta_result_id"]+10**15 for row in package.total_rows}
    def clone(row):
        values={**row,"company_id":2,"fundamental_delta_result_id":id_map[row["fundamental_delta_result_id"]]}
        return recalculate_row_fingerprint(values)
    return rebuild_package((*package.total_rows,*(clone(row) for row in package.total_rows)),(*package.component_rows,*(clone(row) for row in package.component_rows)),(*package.lifecycle_rows,*(clone(row) for row in package.lifecycle_rows)),(*package.valuation_rows,*(clone(row) for row in package.valuation_rows)),fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)


def test_fresh_and_upgraded_delta_schema_are_equivalent_and_idempotent():
    fresh=sqlite3.connect(":memory:"); upgraded=sqlite3.connect(":memory:")
    upgraded.execute("CREATE TABLE score_result(score_result_id INTEGER PRIMARY KEY)")
    before={row[0] for row in upgraded.execute("SELECT name FROM sqlite_schema")}
    for conn in (fresh,upgraded): ensure_schema(conn,applied_at_utc="n"); ensure_schema(conn,applied_at_utc="n")
    delta_names={META_TABLE,*TABLES,"idx_fundamental_delta_current","idx_fundamental_delta_cross_section","idx_fundamental_delta_component_reader","idx_lifecycle_change_current","idx_valuation_change_current"}
    fresh_objects={row[0]:row[1] for row in fresh.execute("SELECT name,sql FROM sqlite_schema WHERE name IN (%s)"%(','.join('?' for _ in delta_names)),tuple(delta_names))}
    upgraded_objects={row[0]:row[1] for row in upgraded.execute("SELECT name,sql FROM sqlite_schema WHERE name IN (%s)"%(','.join('?' for _ in delta_names)),tuple(delta_names))}
    assert fresh_objects==upgraded_objects
    assert before <= {row[0] for row in upgraded.execute("SELECT name FROM sqlite_schema")}
    assert not any("VACUUM" in statement.upper() or "ALTER TABLE" in statement.upper() or "DROP TABLE" in statement.upper() for statement in SCHEMA_STATEMENTS)
    assert upgraded.execute("PRAGMA foreign_key_check").fetchall()==[]


def test_full_apply_identical_noop_and_quick_check(connection,package):
    first=apply_package(connection,package,applied_at_utc="n")
    assert (first.total_inserted,first.component_inserted,first.lifecycle_inserted,first.valuation_inserted)==(5,35,5,5)
    second=apply_package(connection,package,applied_at_utc="n")
    assert second.outcome=="NO_CHANGE"
    assert sum((second.total_inserted,second.total_deleted,second.total_updated,second.component_inserted,second.component_deleted,second.component_updated,second.lifecycle_inserted,second.lifecycle_deleted,second.lifecycle_updated,second.valuation_inserted,second.valuation_deleted,second.valuation_updated))==0
    assert quick_check(connection,model_fingerprint=MODEL_FINGERPRINT)["ok"]
    assert connection.execute("PRAGMA foreign_key_check").fetchall()==[]


def test_changed_full_apply_reports_update_and_preserves_other_model(connection,package):
    apply_package(connection,package,applied_at_utc="n")
    row=dict(connection.execute(f"SELECT * FROM {TOTAL_TABLE} LIMIT 1").fetchone()); row["fundamental_delta_result_id"]+=1; row["company_id"]+=100; row["model_fingerprint"]="other"; row["result_fingerprint"]="other"
    columns=tuple(row); connection.execute(f"INSERT INTO {TOTAL_TABLE}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",tuple(row.values())); connection.commit()
    report=apply_package(connection,changed_package(package),applied_at_utc="n")
    assert report.total_updated==1 and report.total_unchanged==4
    assert report.retained_other_model_rows==1
    assert connection.execute(f"SELECT COUNT(*) FROM {TOTAL_TABLE} WHERE model_fingerprint='other'").fetchone()[0]==1


def test_company_rebuild_change_removal_restore_and_idempotency(connection,package):
    apply_package(connection,package,applied_at_utc="n")
    assert apply_package(connection,package,applied_at_utc="n",company_ids=(1,)).outcome=="NO_CHANGE"
    changed=changed_package(package)
    report=apply_package(connection,changed,applied_at_utc="n",company_ids=(1,))
    assert report.total_updated==1 and report.total_unchanged==4
    assert apply_package(connection,changed,applied_at_utc="n",company_ids=(1,)).outcome=="NO_CHANGE"
    removal=apply_package(connection,without_company(changed),applied_at_utc="n",company_ids=(1,))
    assert removal.total_deleted==5 and connection.execute(f"SELECT COUNT(*) FROM {TOTAL_TABLE}").fetchone()[0]==0
    restore=apply_package(connection,package,applied_at_utc="n",company_ids=(1,))
    assert restore.total_inserted==5


def test_multiple_company_rebuild_preserves_unselected_company(connection,package):
    multi=with_second_company(package); apply_package(connection,multi,applied_at_utc="n")
    company_two=[row[0] for row in connection.execute(f"SELECT result_fingerprint FROM {TOTAL_TABLE} WHERE company_id=2 ORDER BY fiscal_sequence")]
    changed=changed_package(multi,company_id=1)
    report=apply_package(connection,changed,applied_at_utc="n",company_ids=(1,))
    assert report.total_updated==1 and report.total_unchanged==4
    assert company_two==[row[0] for row in connection.execute(f"SELECT result_fingerprint FROM {TOTAL_TABLE} WHERE company_id=2 ORDER BY fiscal_sequence")]


def test_readiness_reconciliation_reports_historical_and_fresh_counts(package):
    report=_readiness_reconciliation(package,as_of_date="2026-01-01",freshness_days=10_000)
    assert report["historical_endpoints"]==5
    assert report["current_fresh_endpoints"]==1
    assert report["historical_total_ready"]=={"qoq":4,"two_quarter":3,"yoy":1}
    assert report["current_fresh_total_ready"]=={"qoq":1,"two_quarter":1,"yoy":1}
    assert report["maximum_total_reconciliation_error"] <= 1e-9


@pytest.mark.parametrize("stage",["after_delete","after_total","after_component","after_lifecycle","after_valuation","metadata"])
def test_failure_injection_rolls_back_every_material_stage(connection,package,stage):
    apply_package(connection,package,applied_at_utc="n")
    before=quick_check(connection,model_fingerprint=MODEL_FINGERPRINT)["content_fingerprint"]
    with pytest.raises(RuntimeError,match="INJECTED_DELTA"):
        apply_package(connection,changed_package(package),applied_at_utc="n",inject_failure_at=stage)
    assert quick_check(connection,model_fingerprint=MODEL_FINGERPRINT)["content_fingerprint"]==before


def test_partial_duplicate_wrong_and_reconciliation_packages_rejected(package):
    with pytest.raises(ValueError,match="FUNDAMENTAL_RESULT_FINGERPRINT"):
        validate_package(replace(package,fundamental_result_fingerprint="wrong"))
    with pytest.raises(ValueError):
        rebuild_package(package.total_rows,package.component_rows[:-1],package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)
    duplicate=(*package.total_rows,package.total_rows[0])
    with pytest.raises(ValueError):
        rebuild_package(duplicate,package.component_rows,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)
    ready=next(row for row in package.component_rows if row["qoq_delta"] is not None)
    broken=[recalculate_row_fingerprint({**row,"qoq_delta":row["qoq_delta"]+1}) if row is ready else row for row in package.component_rows]
    with pytest.raises(ValueError,match="RECONCILIATION"):
        rebuild_package(package.total_rows,broken,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)


def test_source_lag_and_unavailable_value_contracts_rejected(package):
    with pytest.raises(ValueError,match="FUNDAMENTAL_SOURCE_FINGERPRINT"):
        rebuild_package(package.total_rows,package.component_rows,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint="wrong",lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)

    ready_total=next(row for row in package.total_rows if row["qoq_status"]=="DELTA_READY")
    invalid_lag=recalculate_row_fingerprint({**ready_total,"qoq_prior_fiscal_sequence":ready_total["fiscal_sequence"]-2})
    totals=[invalid_lag if row is ready_total else row for row in package.total_rows]
    with pytest.raises(ValueError,match="READY_TOTAL_LAG_OR_VALUE_INVALID"):
        rebuild_package(totals,package.component_rows,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)

    unavailable=next(row for row in package.component_rows if row["qoq_status"]!="DELTA_READY")
    invalid_zero=recalculate_row_fingerprint({**unavailable,"qoq_delta":0.0})
    components=[invalid_zero if row is unavailable else row for row in package.component_rows]
    with pytest.raises(ValueError,match="UNAVAILABLE_COMPONENT_DELTA_MUST_BE_NULL"):
        rebuild_package(package.total_rows,components,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=package.fundamental_source_fingerprint,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)


def test_readers_current_history_endpoint_cross_section_components_and_contexts(connection,package):
    apply_package(connection,package,applied_at_utc="n")
    fundamental=FundamentalDeltaRepository(connection); lifecycle=LifecycleChangeRepository(connection); valuation=ValuationChangeRepository(connection)
    current=fundamental.current_company(1,model_fingerprint=MODEL_FINGERPRINT)
    assert current["fiscal_quarter"]=="Q1" and len(fundamental.history(1,model_fingerprint=MODEL_FINGERPRINT))==5
    assert len(fundamental.current_universe(model_fingerprint=MODEL_FINGERPRINT))==1
    assert len(fundamental.cross_section(current["fiscal_year"],current["fiscal_quarter"],model_fingerprint=MODEL_FINGERPRINT))==1
    combined=fundamental.with_components(1,current["fiscal_year"],current["fiscal_quarter"],model_fingerprint=MODEL_FINGERPRINT)
    assert len(combined["components"])==7
    assert lifecycle.current_company(1,model_fingerprint=MODEL_FINGERPRINT)["current_final_state"]=="MATURE"
    assert isinstance(valuation.current_company(1,model_fingerprint=MODEL_FINGERPRINT)["qoq_payload"],dict)
    assert fundamental.history(1,model_fingerprint=MODEL_FINGERPRINT)[0]["qoq_delta"] is None
    assert current["qoq_delta"] == 0.0
    with pytest.raises(ValueError,match="FINGERPRINT_REJECTED"): fundamental.current_company(1,model_fingerprint="wrong")
