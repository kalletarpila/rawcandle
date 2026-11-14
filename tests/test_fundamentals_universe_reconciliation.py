"""Identity-only native generations: exact economics, journal and safe STOPs."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import sqlite3

import pytest

from rawcandle.fundamentals.admin import universe_reconciliation as reconciliation
from rawcandle.fundamentals.admin import refresh_update as core
from rawcandle.fundamentals.admin import publication_journal as journal
from rawcandle.fundamentals.admin.artifacts import AdminRunWriter
from rawcandle.fundamentals.admin.contracts import AdminOperationType, fingerprint
from rawcandle.fundamentals.admin.refresh_universe import InstalledUniverse
from rawcandle.fundamentals.generations import resolve_active_generation
from tests import test_fundamentals_financial_selection as fixtures


def setup(tmp_path, monkeypatch):
    workflow, native, histories, calls, decisions = fixtures.fixture_environment(
        tmp_path, monkeypatch
    )
    env = workflow.env
    reference = fixtures.APPROVED["approval_reference"]
    approval = reconciliation.approval_fingerprint(decisions, reference)
    paths = env.paths()
    args = dict(
        approval_reference=reference,
        expected_approval=approval,
        expected_code=reconciliation.code_binding(),
        expected_old=core.carry.verified_generation(paths),
        expected_universe=fingerprint(
            reconciliation.selection.read_state(paths.canonical_db)
        ),
        confirm_candidate=deepcopy,
        confirmation=reconciliation.CONFIRM,
    )
    return workflow, decisions, args


def financial_hashes(env):
    return {
        r: journal.sha256_file(env.paths().as_dict()[r])
        for r in journal.PUBLICATION_ROLES
    }


def test_identity_only_native_publication_then_refresh_validation(
    tmp_path, monkeypatch
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    env = workflow.env
    old = env.paths()
    before = financial_hashes(env)
    result = reconciliation.run_reconciliation(
        env, decisions, **args, stop_after="publish"
    )
    assert result["outcome"] == "COMPLETED", result
    assert result["postflight"] == "PASSED"
    assert result["financial_update_publication"] is False
    assert result["financial_watermark_advanced"] is False
    assert (
        resolve_active_generation(env.project).generation_id
        != args["expected_old"]["generation_id"]
    )
    active = env.paths()
    assert journal.sha256_file(active.provider_db) == before["provider"]
    assert journal.sha256_file(active.analysis_db) == before["analysis"]
    assert reconciliation._economic_tables(
        old.canonical_db
    ) == reconciliation._economic_tables(active.canonical_db)
    assert InstalledUniverse(active).resolve("AAA")["status"] == "ELIGIBLE"
    assert (
        InstalledUniverse(active).resolve("AAAB")["reason"]
        == "FINANCIAL_COMPANION_RETENTION_ONLY"
    )
    native_journal = journal.load_journal(env.journal)
    assert (
        native_journal["state"] == "COMPLETED"
        and native_journal["postflight_state"] == "PASSED"
    )
    # The newly installed authority is immediately usable by the real pipeline.
    result = workflow.start(
        stop_after="validate", ownership_intent=False, publication_intent=False
    )
    assert result["outcome"] == "VALIDATED", result
    request = env.request()
    assert (
        request["refresh_universe"]["financial_selection_fingerprint"]
        == InstalledUniverse(env.paths()).binding["financial_selection_fingerprint"]
    )
    assert (
        request["publication_intent"] is False and request["ownership_intent"] is False
    )


def test_prepared_candidate_never_activates_without_publish_intent(
    tmp_path, monkeypatch
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    before = financial_hashes(workflow.env)
    result = reconciliation.run_reconciliation(workflow.env, decisions, **args)
    assert result["outcome"] == "CANDIDATE_READY", result
    assert financial_hashes(workflow.env) == before
    assert resolve_active_generation(workflow.env.project).generation_id == "old"
    assert journal.load_journal(workflow.env.journal) is None


@pytest.mark.parametrize(
    "boundary", ["AFTER_PREPARE", "AFTER_ACTIVATION", "AFTER_POSTFLIGHT"]
)
def test_ordinary_failure_uses_native_restore_under_writer_lock(
    tmp_path, monkeypatch, boundary
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    env = workflow.env
    before = financial_hashes(env)
    original = journal.restore_old_generation
    events = []

    def restore(*a, **kw):
        assert env._stack is not None
        events.append("writer lifetime retained")
        return original(*a, **kw)

    monkeypatch.setattr(journal, "restore_old_generation", restore)
    result = reconciliation.run_reconciliation(
        env, decisions, **args, stop_after="publish", inject_failure=boundary
    )
    assert result["outcome"] == "ROLLED_BACK", result
    assert events and financial_hashes(env) == before
    assert resolve_active_generation(env.project).generation_id == "old"
    assert journal.load_journal(env.journal)["state"] == "RECOVERED"


@pytest.mark.parametrize("boundary", ["AFTER_PREPARE", "AFTER_ACTIVATION"])
def test_interruption_uses_native_prepared_or_active_generation_recovery(
    tmp_path, monkeypatch, boundary
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    env = workflow.env
    before = financial_hashes(env)
    with pytest.raises(reconciliation.native.SimulatedPublicationCrash):
        reconciliation.run_reconciliation(
            env, decisions, **args, stop_after="publish", inject_crash=boundary
        )
    assert journal.safety_status(env.journal)["production_writes_blocked"]
    with env.writer_lock():
        result = journal.recover_if_required(env.journal)
    assert result["status"] == "RECOVERED"
    assert financial_hashes(env) == before
    assert resolve_active_generation(env.project).generation_id == "old"


@pytest.mark.parametrize("key", ["expected_old", "expected_universe"])
def test_stale_starting_authority_stops_before_candidate(tmp_path, monkeypatch, key):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    before = financial_hashes(workflow.env)
    args[key] = "stale"
    result = reconciliation.run_reconciliation(
        workflow.env, decisions, **args, stop_after="publish"
    )
    assert (
        result["outcome"] == "BLOCKED" and "STALE_STARTING_AUTHORITY" in result["error"]
    )
    assert financial_hashes(workflow.env) == before
    assert "candidate_roles" not in result


@pytest.mark.parametrize(
    "defect", ["approval", "code", "confirmation", "intent"]
)
def test_explicit_native_authority_is_mandatory(tmp_path, monkeypatch, defect):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    if defect == "approval":
        args["expected_approval"] = "unapproved"
    if defect == "code":
        args["expected_code"] = {}
    if defect == "confirmation":
        args["confirmation"] = "financial UPDATE approval is insufficient"
    if defect == "intent":
        args["production_intent"] = True
    with pytest.raises((ValueError, PermissionError)):
        reconciliation.run_reconciliation(
            workflow.env, decisions, **args, stop_after="publish"
        )
    assert resolve_active_generation(workflow.env.project).generation_id == "old"


def test_identity_only_preserves_accepted_analysis_without_reasserting_freshness(
    tmp_path, monkeypatch
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    env = workflow.env
    before = financial_hashes(env)
    # Independent market maintenance is allowed; no historical checksum is fixed.
    # Financial rebuild validation must reject incompatible OLD RV; identity
    # publication preserves that original result rather than claiming freshness.
    with sqlite3.connect(env.paths().market_db) as db:
        cols = [
            r[1]
            for r in db.execute("PRAGMA table_info(osakedata)")
            if r[1].lower() in {"open", "high", "low", "close"}
        ]
        assert cols
        db.execute(
            "UPDATE osakedata SET "
            + ",".join('"' + c + '"="' + c + '"*1.2' for c in cols)
        )
    params = reconciliation._analysis_parameters(env.paths().analysis_db)
    with pytest.raises(RuntimeError, match="RV_SOURCE_OR_RESULT_MISMATCH"):
        reconciliation.native._validate_analysis_generation(
            env.paths().analysis_db,
            analysis_result=params,
            as_of_date=params["as_of_date"],
            sources=env.paths().as_dict(),
        )
    result = reconciliation.run_reconciliation(
        env, decisions, **args, stop_after="publish"
    )
    assert result["outcome"] == "COMPLETED", result
    assert result["baseline_analysis"] == result["candidate_analysis"]
    assert result["baseline_analysis"]["financial_freshness_reasserted"] is False
    after = financial_hashes(env)
    assert (
        after["provider"] == before["provider"]
        and after["analysis"] == before["analysis"]
    )
    with pytest.raises(RuntimeError, match="RV_SOURCE_OR_RESULT_MISMATCH"):
        reconciliation.native._validate_analysis_generation(
            env.paths().analysis_db,
            analysis_result=params,
            as_of_date=params["as_of_date"],
            sources=env.paths().as_dict(),
        )


def test_recheck_rejects_policy_drift_without_activation(tmp_path, monkeypatch):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    before = financial_hashes(workflow.env)
    original = reconciliation._authority
    calls = []

    def changing(*a, **kw):
        result = original(*a, **kw)
        calls.append(1)
        if len(calls) > 1:
            result["configuration"] = "changed independently"
        return result

    monkeypatch.setattr(reconciliation, "_authority", changing)
    result = reconciliation.run_reconciliation(
        workflow.env, decisions, **args, stop_after="publish"
    )
    assert (
        result["outcome"] == "BLOCKED" and "STALE_AUTHORITY" in result["error"]
    ), result
    assert financial_hashes(workflow.env) == before


def test_normal_nightly_scheduler_margin_is_respected():
    live = SimpleNamespace(is_live=True)
    with pytest.raises(RuntimeError, match="NIGHTLY_WINDOW"):
        reconciliation._nightly_coordination(
            live, datetime(2026, 11, 14, 2, 15, tzinfo=timezone.utc)
        )
    assert (
        reconciliation._nightly_coordination(
            live, datetime(2026, 11, 13, 22, tzinfo=timezone.utc)
        )["seconds_remaining"]
        > 3600
    )


@pytest.mark.parametrize("tamper", ["environment_type", "live_flag", "copy_root"])
def test_native_environment_cannot_be_relabelled_as_unchecked_copy(
    tmp_path, monkeypatch, tamper
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    env = workflow.env
    if tamper == "environment_type":
        env = SimpleNamespace(check=lambda: None, is_live=False, copy_owner=None)
    elif tamper == "live_flag":
        env.is_live = True
    else:
        env.root = reconciliation.selection.ROOT
    with pytest.raises(
        PermissionError, match="NATIVE_ENVIRONMENT_REQUIRED|COPY_OWNER_SCOPE"
    ):
        reconciliation.run_reconciliation(env, decisions, **args, stop_after="publish")


def test_operation_induced_native_input_change_is_a_pre_activation_stop(
    tmp_path, monkeypatch
):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    env = workflow.env
    before = financial_hashes(env)
    original = reconciliation._accepted_analysis
    old_canonical = env.paths().canonical_db

    def changed(paths, *a, **kw):
        report = original(paths, *a, **kw)
        if paths.canonical_db != old_canonical:
            report["current_rv_input_fingerprint"] = (
                "injected different native economic input"
            )
        return report

    monkeypatch.setattr(reconciliation, "_accepted_analysis", changed)
    result = reconciliation.run_reconciliation(
        env, decisions, **args, stop_after="publish"
    )
    assert (
        result["outcome"] == "BLOCKED"
        and "NATIVE_ECONOMIC_INPUT_CHANGED" in result["error"]
    ), result
    assert financial_hashes(env) == before and journal.load_journal(env.journal) is None


def test_invalid_native_package_stops_before_copy_or_activation(tmp_path, monkeypatch):
    workflow, decisions, args = setup(tmp_path, monkeypatch)
    before = financial_hashes(workflow.env)

    def reject(*a, **kw):
        raise RuntimeError("INJECTED_NATIVE_PACKAGE_INVALID")

    monkeypatch.setattr(reconciliation.phase10b, "validate_candidate_package", reject)
    result = reconciliation.run_reconciliation(
        workflow.env, decisions, **args, stop_after="publish"
    )
    assert (
        result["outcome"] == "BLOCKED" and "NATIVE_PACKAGE_INVALID" in result["error"]
    ), result
    assert financial_hashes(workflow.env) == before and "candidate_roles" not in result
