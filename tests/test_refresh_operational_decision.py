from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.refresh_operational_decision import (
    refresh_operational_decision, advance_refresh_decision, operational_decision_rows,
)
from rawcandle.fundamentals.admin.full_workflow import run_refresh_full_workflow, render_workflow_report, workflow_ui_summary
from rawcandle.fundamentals.admin.operation_report import build_operation_summary
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_admin_refresh_full_workflow import _stage


def decision(safe=0, held=0, blockers=0, authorized=False, reason="NO_SAFE_CHANGES_TO_PUBLISH", **kw):
    return refresh_operational_decision(
        safe_effective_changes=safe, held_items=[{"ticker": "KO"} for _ in range(held)],
        global_blockers=[{"reason": "GLOBAL"} for _ in range(blockers)],
        future_test_authorized=authorized, test_reason_code=reason, **kw,
    )


@pytest.mark.parametrize("safe,held,blockers,authorized,expected", [
    (0,0,0,False,"NO_SAFE_CHANGES"), (0,1,0,False,"NO_SAFE_CHANGES"),
    (0,3,0,False,"NO_SAFE_CHANGES"), (2,1,0,True,"SAFE_CHANGES_AUTHORIZED"),
    (2,1,0,False,"TEST_NOT_AUTHORIZED"), (2,0,0,True,"SAFE_CHANGES_AUTHORIZED"),
    (2,0,1,False,"GLOBAL_BLOCKER"), (0,0,1,False,"GLOBAL_BLOCKER"),
    (2,1,1,False,"GLOBAL_BLOCKER"),
])
def test_decision_matrix(safe,held,blockers,authorized,expected):
    d=decision(safe,held,blockers,authorized,reason="PUBLICATION_DATE_PREREQUISITES" if safe else "NO_SAFE_CHANGES_TO_PUBLISH")
    assert d["decision_code"]==expected
    assert d["safe_effective_changes"]==safe
    assert d["held_item_count"]==held and d["global_blocker_count"]==blockers
    assert d["test_gate"]["authorized"] is authorized
    assert d["local_hold_blocked_safe_changes"] is (False if held else None)
    if not authorized:
        assert d["recommended_action_code"]!="RUN_TEST"
        assert "Proceed to Test" not in d["recommended_action_text"]
    if not safe and not blockers:
        assert d["production_gate"]["state"]=="NOT_APPLICABLE"
        assert "No Test or Production run is required" in d["recommended_action_text"]
    if blockers:
        assert d["production_gate"]["reason_code"]=="GLOBAL_BLOCKER_PRESENT"


@pytest.mark.parametrize("safe",[0,2])
@pytest.mark.parametrize("held",[0,1,3])
@pytest.mark.parametrize("blockers",[0,1])
def test_false_authorization_cannot_recommend_test(safe,held,blockers):
    assert decision(safe,held,blockers)["recommended_action_code"]!="RUN_TEST"


def test_production_stage_authority_and_technical_precedence():
    d=decision(2,1,0,True,"SAFE_CHANGES_TEST_AUTHORIZED")
    assert d["production_gate"]=={"state":"NOT_EVALUATED","reason_code":"TEST_MUST_COMPLETE_FIRST"}
    t=advance_refresh_decision(d,stage="Test on copies")
    assert t["production_gate"]["state"]=="NOT_EVALUATED"
    t=advance_refresh_decision(d,stage="Test on copies",production_state="AUTHORIZED",production_reason_code="MATCHING_SUCCESSFUL_TEST_VALIDATED")
    assert t["production_gate"]["state"]=="AUTHORIZED"
    f=advance_refresh_decision(t,stage="Test on copies",technical_failure="STALE_BINDING")
    assert f["decision_text"]=="STALE_BINDING"
    assert f["production_gate"]["state"]=="NOT_AUTHORIZED"
    assert f["recommended_action_code"]=="REVIEW_TECHNICAL_FAILURE"
    assert f["test_gate"]["authorized"] is False
    assert decision(0,1,1,False,technical_failure="SOURCE_FILE_CHANGED")["decision_code"]=="TECHNICAL_FAILURE"


def preview_extra(d):
    return {
        "operational_decision":d,"recommended_next_action":d["recommended_action_text"],
        "refresh_preview":{
            "future_test_authorized":d["test_gate"]["authorized"],
            "operational_decision":d,"ticker_changes":[{"ticker":"KO","classification":"REVIEW_REQUIRED"}],
            "review_partition":{"held":d["held_items"],"global_blockers":d["global_blockers"]},
        },
    }


def test_zero_safe_local_hold_report_and_ui_are_self_contained(tmp_path):
    d=decision(0,1)
    calls=[]
    r=run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _: _stage(tmp_path,"preview",mode="PREVIEW",outcome="REVIEW_REQUIRED",extra=preview_extra(d)),
        test_stage=lambda *_:calls.append("test"),production_stage=lambda *_:calls.append("production"),
    )
    assert not calls
    assert r["operational_decision"]==d==r["terminal_summary"]["operational_decision"]
    assert r["terminal_summary"]["problem_items"][0]["action"]=="Review this ticker separately. It remains quarantined."
    report=Path(r["artifact_dir"])/"workflow_report.md"
    text=report.read_text()
    assert text.index("## Executive Summary")<text.index("## Operational Decision")<text.index("## Failure / Review Summary")
    assert "Workflow stopped after Preview because" not in text
    assert "Use only this exact manual Preview" not in text
    assert "No safe effective changes" in text and "did not block any safe peer changes" in text
    persisted=json.loads((Path(r["artifact_dir"])/"workflow_result.json").read_text())
    shutil.rmtree(tmp_path/"preview")
    assert "No Test or Production run is required" in render_workflow_report(persisted)
    ui=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False)._finalize(persisted,default_message="done")
    assert ui.operational_decision==d
    assert all(row in ui.summary_rows for row in operational_decision_rows(d))
    assert tuple(build_operation_summary({"operational_decision":d})[1:])==operational_decision_rows(d)


@pytest.mark.parametrize("test_failed",[False,True])
def test_safe_peer_progression_and_latest_stage(tmp_path,test_failed):
    d=decision(2,1,0,True,"SAFE_CHANGES_TEST_AUTHORIZED")
    t=advance_refresh_decision(d,stage="Test on copies",production_state="AUTHORIZED",production_reason_code="MATCHING_SUCCESSFUL_TEST_VALIDATED")
    p=advance_refresh_decision(t,stage="Production update",production_state="AUTHORIZED",production_reason_code="MATCHING_SUCCESSFUL_TEST_VALIDATED",completed=True)
    calls=[]
    def production(*_):
        calls.append("production")
        return _stage(tmp_path,"production",mode="PRODUCTION_APPLY",extra={"operational_decision":p})
    r=run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _: _stage(tmp_path,"preview",mode="PREVIEW",extra=preview_extra(d)),
        test_stage=lambda *_: _stage(tmp_path,"test",mode="COPY_ONLY_APPLY",outcome="FAILED" if test_failed else "COMPLETED",extra={"operational_decision":t,"errors":[{"message":"STALE_BINDING"}]} if test_failed else {"operational_decision":t}),
        production_stage=production,
    )
    if test_failed:
        assert not calls
        assert r["operational_decision"]["decision_code"]=="TECHNICAL_FAILURE"
        assert r["operational_decision"]["production_gate"]["state"]=="NOT_AUTHORIZED"
    else:
        assert calls==["production"]
        assert r["operational_decision"]==p
        assert r["outcome"]=="COMPLETED"
        assert "Workflow stopped at" not in render_workflow_report(r)


def test_legacy_render_does_not_invent_authorization():
    legacy={"outcome":"STOPPED","stop_reason":"Legacy reason","terminal_summary":{"headline":"Legacy reason"}}
    assert "## Operational Decision" not in render_workflow_report(legacy)
    assert "Legacy reason" in workflow_ui_summary(legacy)
    assert not any("Test authorized" in row for row in workflow_ui_summary(legacy))


def test_safe_changes_without_backend_authorization_do_not_progress(tmp_path):
    d=decision(2,1,0,False,"PUBLICATION_DATE_PREREQUISITES")
    calls=[]
    r=run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _: _stage(tmp_path,"preview",mode="PREVIEW",extra=preview_extra(d)),
        test_stage=lambda *_: calls.append("test"), production_stage=lambda *_:calls.append("production"),
    )
    assert calls==[]
    assert r["terminal_summary"]["operational_decision"]==d
    assert "PUBLICATION_DATE_PREREQUISITES" in r["stop_reason"]
    assert d["recommended_action_code"]=="REVIEW_TEST_GATE"


def test_preview_technical_failure_keeps_diagnostics(tmp_path):
    d=decision(2,1,1,False,technical_failure="PRODUCTION_FILE_STATE_CHANGED_DURING_READ_ONLY_PREVIEW")
    r=run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _: _stage(tmp_path,"preview",mode="PREVIEW",outcome="FAILED",extra=preview_extra(d)|{"errors":[{"message":d["decision_text"]}]}),
        test_stage=lambda *_:pytest.fail("Unauthorized Test"),production_stage=lambda *_:pytest.fail("Unauthorized Production"),
    )
    assert r["operational_decision"]["decision_code"]=="TECHNICAL_FAILURE"
    assert "PRODUCTION_FILE_STATE_CHANGED" in r["terminal_summary"]["headline"]
    assert r["operational_decision"]["production_gate"]["state"]=="NOT_AUTHORIZED"
