"""Production adapter on owned SQLite copies; no actual network or live writes."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit
from urllib.error import URLError

import pytest

from rawcandle.fundamentals.admin import refresh_update as core, sec_snapshot
from rawcandle.fundamentals.admin.snapshot_environment import SnapshotEnvironment, ROUTE
from rawcandle.fundamentals.admin.snapshot_workflow import SnapshotWorkflow
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.providers.sharadar import SharadarClient
from rawcandle.fundamentals.result_publication import SecClient, enrich_database
from tests import test_fundamentals_snapshot_workflow as fixtures
from tests import test_result_publication_authority as sec_fixtures
from tests.provider_capture_fixtures import full_row
from tests.test_pb_ownership_future import project, ordinary, factory


def setup(
    tmp_path,
    monkeypatch,
    *,
    held=False,
    degraded_count=0,
    rolling=False,
    ownership=False,
    established=False
):
    owner, native, histories, _, _ = fixtures.setup(
        tmp_path,
        monkeypatch,
        held=held,
        degraded_count=degraded_count,
        rolling=rolling,
        established=established,
    )
    calls = []

    def opener(request, timeout):
        query = {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}
        if "/schema/" in request.full_url:
            from rawcandle.fundamentals.admin.refresh_fundamentals import (
                REFRESH_REQUEST_FIELDS,
            )

            calls.append(("schema",))
            payload = list(REFRESH_REQUEST_FIELDS)
        elif "ticker" not in query:
            calls.append(("discovery", query["dimension"]))
            payload = [
                {
                    "ticker": t,
                    "dimension": query["dimension"],
                    "lastupdated": "2026-11-10",
                }
                for t in histories
            ]
        else:
            calls.append((query["ticker"], query["dimension"]))
            payload = [
                full_row(r)
                for r in histories[query["ticker"]][query["dimension"]]
                if query["from"] <= r["date"] <= query["to"]
            ]
        return fixtures.Response(json.dumps(payload).encode())

    client = SharadarClient(
        api_key="phase3b-fixture",
        opener=opener,
        wall_clock=lambda: fixtures.NOW.timestamp(),
    )
    env = SnapshotEnvironment(
        copy_owner=owner,
        configuration={"route": ROUTE, "mode": "FULL_WORKFLOW", "ownership": ownership},
    )

    def no_sec(url):
        raise URLError("fixture missing SEC document")

    workflow = SnapshotWorkflow(
        env, client=client, sec_fetch_bytes=no_sec, now=lambda: fixtures.NOW
    )
    return workflow, native, histories, calls


@pytest.mark.parametrize("defect", [None, "primary", "exhibit"])
def test_sec_durable_replay_uses_real_parser_and_resolver(
    tmp_path, monkeypatch, defect
):
    canonical = sec_fixtures._database(tmp_path)
    client = sec_fixtures._client()
    requested = []

    def raw(url):
        requested.append(url)
        if "submissions" in url:
            return json.dumps(client._fetch_json(url)).encode()
        if defect == "primary" and url.endswith("aapl.htm"):
            raise URLError("missing primary fixture")
        if url.endswith("ex99.htm"):
            raise URLError("missing exhibit fixture")
        text = client._fetch_text(url)
        if defect == "exhibit" and url.endswith("aapl.htm"):
            text = '<p>Item 2.02 Results of Operations and Financial Condition.</p><a href="ex99.htm">Exhibit 99.1</a>'
        return text.encode()

    plan = [
        {
            "company_id": v[0],
            "cik": v[1],
            "from_calendar_year": 2026,
            "from_calendar_date": "2026-01-01",
            "to_calendar_date": "2026-12-31",
        }
        for v in sec_fixtures.SAMPLES.values()
    ]
    ref = {"operation_id": "fetch_fixture", "sha256": "fixture"}
    manifest = sec_snapshot.capture(
        tmp_path / "sec",
        operation_id="update-fixture",
        snapshot_reference=ref,
        plan=plan,
        fetch_bytes=raw,
    )
    assert manifest["network_budget_seconds"] == 300
    original = SecClient(
        fetch_json=lambda url: json.loads(raw(url)),
        fetch_text=lambda url: raw(url).decode(),
    )
    baseline = enrich_database(
        canonical, client=original, apply=False, from_fiscal_year=2026
    )
    before = len(requested)
    offline = sec_snapshot.open_bundle(
        tmp_path / "sec", operation_id="update-fixture", snapshot_reference=ref
    )[1]
    replay = enrich_database(
        canonical, client=offline, apply=False, from_fiscal_year=2026
    )
    assert replay["results"] == baseline["results"]
    assert replay["status_counts"] == baseline["status_counts"]
    assert len(requested) == before
    if defect == "exhibit":
        assert any(url.endswith("ex99.htm") for url in requested)
    if defect == "primary":
        assert replay["errors"]
    else:
        assert replay["status_counts"]["VERIFIED"] >= 3


def test_native_integrated_build_publication_and_service_history(tmp_path, monkeypatch):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    service = FundamentalsAdminUIService(
        run_root=workflow.env.runs,
        refresh_route=ROUTE,
        snapshot_workflow=workflow,
        recover_publication_on_startup=False,
    )
    result = service.full_workflow(operation_type="REFRESH_FUNDAMENTALS", raw_inputs="")
    assert result.outcome == "CANDIDATE_READY", result
    assert resolve_active_generation(workflow.env.project).generation_id == "old"
    assert len(calls) == 7

    def forbidden(*args, **kwargs):
        raise AssertionError("network after FETCH")

    monkeypatch.setattr(SharadarClient, "_request", forbidden)
    monkeypatch.setattr(SecClient, "_request", forbidden)
    result = service.full_workflow(
        operation_type="REFRESH_FUNDAMENTALS",
        raw_inputs="",
        snapshot_update_run_id=result.run_id,
        snapshot_publish_confirmed=True,
    )
    assert result.outcome == "COMPLETED", result
    assert len(calls) == 7
    payload = core._read(workflow.env.runs / result.run_id / "result.json")
    assert payload["production_completed"]
    assert payload["production_database_writes"] == 0
    assert payload["stages"][-1]["stage"] == "Production update"
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )
    assert any(e.run_id == result.run_id for e in service.history_entries())
    assert len(calls) == 7


def test_default_route_is_legacy_without_configuration_mutation(tmp_path):
    from rawcandle.scheduler.config import read_scheduler_config

    cfg = read_scheduler_config("scheduler_config.json")
    assert cfg.fundamentals_refresh_route == "LEGACY"
    assert cfg.fundamentals_refresh_preview_enabled is False
    service = FundamentalsAdminUIService(
        run_root=tmp_path / "admin_runs", recover_publication_on_startup=False
    )
    assert service.selected_refresh_route() == "LEGACY"


def test_acquisition_only_cannot_be_used_as_update_authority(tmp_path, monkeypatch):
    owner, native, histories, calls, acquire = fixtures.setup(tmp_path, monkeypatch)
    operation = acquire()
    workflow = SnapshotWorkflow(
        SnapshotEnvironment(copy_owner=owner), now=lambda: fixtures.NOW
    )
    # A valid unrelated acquisition remains financial-authorization-free.
    workflow.env.operation_id = "unrelated-update"
    with pytest.raises((ValueError, FileNotFoundError, PermissionError)):
        workflow.env.require_update_snapshot(
            core.acquisition.open_snapshot(operation, root=owner.runs)
        )
    assert resolve_active_generation(owner.project).generation_id == "old"


@pytest.mark.parametrize(
    "defect", ["old", "queue", "market", "configuration", "sec", "expired"]
)
def test_integrated_stale_authority_never_activates(tmp_path, monkeypatch, defect):
    workflow, native, histories, calls = setup(
        tmp_path, monkeypatch, held=defect == "queue"
    )
    result = workflow.start(stop_after="build")
    assert result["outcome"] == "CANDIDATE_READY", result
    env = workflow.env
    before = len(calls)
    if defect == "old":
        with sqlite3.connect(env.paths().provider_db) as db:
            db.execute("UPDATE provider_observation SET content_hash='changed'")
    elif defect == "queue":
        with sqlite3.connect(env.queue) as db:
            db.execute("CREATE TABLE IF NOT EXISTS refresh_review_queue_unrelated(x)")
        # Financial material drift, not unrelated ownership/table presence.
        from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue

        q = RefreshReviewQueue(env.queue)
        with sqlite3.connect(env.queue) as db:
            db.execute("UPDATE refresh_review_queue SET last_seen_run_id='changed'")
        assert q.list_items(include_resolved=True)
    elif defect == "market":
        with sqlite3.connect(env.paths().market_db) as db:
            db.execute("UPDATE osakedata SET close=close+1")
    elif defect == "configuration":
        env.configuration["ownership"] = True
    elif defect == "sec":
        path = env.directory() / "sec/manifest.json"
        path.write_text(path.read_text().replace("300", "301"))
    else:
        workflow.now = lambda: fixtures.NOW + timedelta(hours=169)
    failed = workflow.advance(result["run_id"], confirm_publish=True)
    assert failed["outcome"] == "FAILED", failed
    assert resolve_active_generation(env.project).generation_id == "old"
    assert len(calls) == before


@pytest.mark.parametrize(
    "boundary", ["AFTER_PREPARE", "AFTER_ACTIVATION", "AFTER_POSTFLIGHT"]
)
def test_integrated_native_rollback_and_source_independent_recovery(
    tmp_path, monkeypatch, boundary
):
    import shutil

    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    result = workflow.start(stop_after="build")
    assert result["outcome"] == "CANDIDATE_READY", result
    env = workflow.env
    before = {
        r: core.sha256_file(p)
        for r, p in resolve_active_generation(env.project).role_paths().items()
    }
    with pytest.raises(core.native.SimulatedPublicationCrash):
        workflow.advance(result["run_id"], confirm_publish=True, inject_crash=boundary)
    shutil.rmtree(env.runs / result["fetch_operation_id"])
    recovered = workflow.advance(result["run_id"], confirm_publish=True)
    assert recovered["outcome"] == "RETRY_REQUIRED", recovered
    assert resolve_active_generation(env.project).generation_id == "old"
    assert all(
        core.sha256_file(p) == before[r]
        for r, p in resolve_active_generation(env.project).role_paths().items()
    )


def test_integrated_ordinary_failure_reports_rollback(tmp_path, monkeypatch):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    result = workflow.start(stop_after="build")
    failed = workflow.advance(
        result["run_id"], confirm_publish=True, inject_failure="AFTER_ACTIVATION"
    )
    assert failed["outcome"] == "ROLLED_BACK", failed
    assert resolve_active_generation(workflow.env.project).generation_id == "old"


@pytest.mark.parametrize("scope", ["ordinary", "baseline", "rolling"])
def test_integrated_safe_peers_and_preserved_history(tmp_path, monkeypatch, scope):
    workflow, native, histories, calls = setup(
        tmp_path,
        monkeypatch,
        held=scope == "ordinary",
        degraded_count=100 if scope == "baseline" else 0,
        rolling=scope == "rolling",
    )
    result = workflow.start(publication_intent=True)
    assert result["outcome"] == "COMPLETED", result
    if scope != "rolling":
        assert result["source_summary"]["held_for_review"] >= (
            100 if scope == "baseline" else 1
        )
    assert result["source_summary"]["safe_changes"] >= 1
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )


def test_ownership_failure_leaves_verified_financial_commit(tmp_path, monkeypatch):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch, ownership=True)
    observed = []

    def fail(**kwargs):
        active = resolve_active_generation(workflow.env.project)
        j = core.journals.load_journal(workflow.env.journal)
        assert j["state"] == "COMPLETED" and j["postflight_state"] == "PASSED"
        assert active.generation_id == j["new_generation_id"]
        observed.append(active.generation_id)
        raise ValueError("controlled ownership failure")

    workflow.ownership_runner = fail
    result = workflow.start(publication_intent=True)
    assert result["outcome"] == "COMPLETED" and result["production_completed"], result
    assert result["ownership_auto"]["status"] == "FAILED_OR_STALE"
    assert resolve_active_generation(workflow.env.project).generation_id == observed[0]
    assert workflow.advance(result["run_id"], confirm_publish=True) == result


def test_scheduler_and_manual_share_selected_route_and_no_fallback(
    tmp_path, monkeypatch
):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    service = FundamentalsAdminUIService(
        run_root=workflow.env.runs,
        refresh_route=ROUTE,
        snapshot_workflow=workflow,
        recover_publication_on_startup=False,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy execution fallback forbidden")

    service._refresh_preview = service._refresh_apply = (
        service._refresh_production_apply
    ) = forbidden
    from rawcandle.fundamentals.admin import refresh_scheduler as scheduler

    monkeypatch.setattr(
        scheduler, "FundamentalsAdminUIService", lambda **kwargs: service
    )
    response = scheduler.run_scheduler_refresh_discovery(
        run_root=workflow.env.runs, scheduler_mode="FULL_WORKFLOW", refresh_route=ROUTE
    )
    assert response["outcome"] == "CANDIDATE_READY", response
    assert response["trigger_source"] == "SCHEDULER"
    assert not response["production_invoked"]
    result = core._read(workflow.env.runs / response["run_id"] / "result.json")
    with pytest.raises(ValueError, match="EXISTING_UPDATE"):
        service.preview("REFRESH_FUNDAMENTALS")
    tested = service.copy_apply(
        "REFRESH_FUNDAMENTALS",
        preview_payload_path=result["preview_payload_path"],
        preview_fingerprint=result["preview_fingerprint"],
    )
    assert tested.outcome == "CANDIDATE_READY"
    # Inject a technical failure: no old backend may be invoked.
    monkeypatch.setattr(
        workflow,
        "advance",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("snapshot failure")),
    )
    with pytest.raises(ValueError, match="snapshot failure"):
        service.full_workflow(
            operation_type="REFRESH_FUNDAMENTALS",
            raw_inputs="",
            snapshot_update_run_id=result["run_id"],
        )


def test_scheduler_kernel_lease_allows_local_financial_stage_without_fetch_lock(
    tmp_path, monkeypatch
):
    from rawcandle.scheduler.runner import acquire_scheduler_lock_context
    from rawcandle.fundamentals.admin.production_transaction import (
        _ACTIVE_PRODUCTION_LOCK,
    )

    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    workflow.env.reentrant = True
    original = workflow.client._request

    def observed(*args, **kwargs):
        assert (
            _ACTIVE_PRODUCTION_LOCK.get() is None
        ), "financial writer held across FETCH"
        return original(*args, **kwargs)

    monkeypatch.setattr(workflow.client, "_request", observed)
    with acquire_scheduler_lock_context(workflow.env.log_dir):
        result = workflow.start(publication_intent=True)
    assert result["outcome"] == "COMPLETED", result


def test_native_ownership_continuation_is_separate_and_idempotent(project):
    # Exercise the actual existing owner through the integration continuation.
    # Its fixture already contains observation-bound quarterly ownership evidence.
    from types import SimpleNamespace

    w = project

    class Env:
        root = w.root
        project = w.root
        runs = w.runs
        journal = w.root / "data/.fundamentals_admin_publication_journal.json"
        log_dir = w.log_dir
        operation_id = "integrated-noop"

        def config(self):
            return {"ownership": True}

        def directory(self):
            return self.runs / self.operation_id

        def writer_lock(self):
            return w._lock()

        def paths(self):
            from rawcandle.fundamentals.admin.batch_add_tickers import (
                BatchAddTickerPaths,
            )

            return BatchAddTickerPaths(
                *(
                    resolve_active_generation(self.project).role_paths()[r]
                    for r in ("provider", "canonical", "analysis")
                ),
                self.project / "data/osakedata.db",
                self.project / "data/analysis.db"
            )

    env = Env()
    env.directory().mkdir(parents=True)
    workflow = SnapshotWorkflow(env, now=lambda: fixtures.NOW)
    result = {"outcome": "COMPLETED", "production_completed": True, "warnings": []}
    receipt = {"validation_id": "local_" + "a" * 32}
    directory = env.runs / receipt["validation_id"]
    directory.mkdir()
    core._write(directory / "review_finalization.json", {"status": "COMPLETED"})
    workflow._ownership(
        result,
        {"ownership_intent": True, "as_of_date": w.as_of, "trigger_source": "MANUAL"},
        receipt,
    )
    assert result["ownership_auto"]["status"] == "COMPLETED", result
    assert result["ownership_auto"]["published"] == 1
    first = resolve_active_generation(w.root).generation_id
    result2 = {"warnings": []}
    workflow._ownership(
        result2,
        {"ownership_intent": True, "as_of_date": w.as_of, "trigger_source": "MANUAL"},
        receipt,
    )
    assert result2["ownership_auto"] == result["ownership_auto"], result2
    assert resolve_active_generation(w.root).generation_id == first


def test_phase_controls_require_the_exact_snapshot_candidate(tmp_path, monkeypatch):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    service = FundamentalsAdminUIService(
        run_root=workflow.env.runs,
        refresh_route=ROUTE,
        snapshot_workflow=workflow,
        recover_publication_on_startup=False,
    )
    ready = service.full_workflow(operation_type="REFRESH_FUNDAMENTALS", raw_inputs="")
    assert ready.direct_production_retry_available and ready.test_run_id.startswith(
        "local_"
    )
    with pytest.raises(ValueError, match="EXACT_CANDIDATE"):
        service.production_apply(
            "REFRESH_FUNDAMENTALS",
            preview_payload_path=ready.preview_payload_path,
            preview_fingerprint=ready.preview_fingerprint,
            test_run_id="unrelated-test",
            confirmation="CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS",
        )
    published = service.production_apply(
        "REFRESH_FUNDAMENTALS",
        preview_payload_path=ready.preview_payload_path,
        preview_fingerprint=ready.preview_fingerprint,
        test_run_id=ready.test_run_id,
        confirmation="CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS",
    )
    assert published.outcome == "COMPLETED", published


def test_exact_native_review_approval_is_applied_after_explicit_local_retry(
    tmp_path, monkeypatch
):
    from rawcandle.fundamentals.admin import refresh_review_queue as q

    workflow, native, histories, calls = setup(
        tmp_path, monkeypatch, held=True, established=True
    )
    first = workflow.start(stop_after="validate")
    assert first["source_summary"]["held_for_review"] == 1
    queue = q.RefreshReviewQueue(workflow.env.queue)
    queue.apply_action(
        "YYAI", q.ACCEPT_RETAINED_HISTORY, evidence={"operator": "fixture"}
    )
    second = workflow.advance(first["run_id"], stop_after="build", retry_local=True)
    assert second["outcome"] == "CANDIDATE_READY", second
    assert second["source_summary"]["held_for_review"] == 0
    assert queue.get("YYAI")["status"] == "RETRY_REEVALUATION"
    count = len(calls)
    final = workflow.advance(first["run_id"], confirm_publish=True)
    assert final["outcome"] == "COMPLETED", final
    assert queue.get("YYAI")["status"] == "RESOLVED"
    assert len(calls) == count


def test_snapshot_scheduler_hold_keeps_other_native_dispatch(tmp_path, monkeypatch):
    from dataclasses import replace
    from tests import test_fundamentals_scheduler_hold as hold

    read = hold.read_scheduler_config
    monkeypatch.setattr(
        hold,
        "read_scheduler_config",
        lambda path: replace(read(path), fundamentals_refresh_route=ROUTE),
    )
    hold.test_full_workflow_hold_skips_finance_and_preserves_other_dispatch_after_reload(
        tmp_path, monkeypatch
    )


def test_scheduler_explicit_publication_intent_is_separate_from_route_selection(
    tmp_path, monkeypatch
):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    service = FundamentalsAdminUIService(
        run_root=workflow.env.runs,
        refresh_route=ROUTE,
        snapshot_workflow=workflow,
        recover_publication_on_startup=False,
    )
    from rawcandle.fundamentals.admin import refresh_scheduler as scheduler

    monkeypatch.setattr(
        scheduler, "FundamentalsAdminUIService", lambda **kwargs: service
    )
    result = scheduler.run_scheduler_refresh_discovery(
        run_root=workflow.env.runs,
        scheduler_mode="FULL_WORKFLOW",
        refresh_route=ROUTE,
        snapshot_publish_confirmed=True,
    )
    assert result["outcome"] == "COMPLETED" and result["production_completed"], result


def test_fetch_pause_reuses_checkpoint_without_reacquiring_completed_arq(
    tmp_path, monkeypatch
):
    from urllib.parse import parse_qs, urlsplit

    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    original = workflow.client._opener
    first = [True]

    def paused(request, timeout):
        query = {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}
        if (
            query.get("ticker") == "AAA"
            and query.get("dimension") == "MRQ"
            and first[0]
        ):
            first[0] = False
            response = fixtures.Response(b"rate limit")
            response.status = 429
            response.headers = {"Retry-After": "0"}
            return response
        return original(request, timeout)

    monkeypatch.setattr(workflow.client, "_opener", paused)
    result = workflow.start(stop_after="fetch")
    assert result["outcome"] == "FETCH_PAUSED", result
    assert calls.count(("AAA", "ARQ")) == 1
    result = workflow.advance(result["run_id"], stop_after="fetch")
    assert result["outcome"] == "FETCH_SEALED", result
    assert calls.count(("AAA", "ARQ")) == 1


def test_new_route_retains_native_old_publication_date_prerequisite(
    tmp_path, monkeypatch
):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    active = resolve_active_generation(workflow.env.project)
    canonical = active.role_paths()["canonical"]
    with sqlite3.connect(canonical) as db:
        db.execute(
            "UPDATE v4_quarter SET first_public_result_date=NULL WHERE company_id=1"
        )
    manifest = json.loads(active.manifest_path.read_text())
    manifest["role_verification"]["canonical"].update(
        sha256=core.sha256_file(canonical), size_bytes=canonical.stat().st_size
    )
    active.manifest_path.write_text(json.dumps(manifest))
    result = workflow.start()
    assert (
        result["outcome"] == "FAILED"
        and result["message"] == "UPDATE_PUBLICATION_DATE_PREREQUISITES"
    ), result
    assert not workflow.env.journal.exists()


def test_existing_ui_resume_control_uses_same_update_identity():
    from tests.test_fundamentals_admin_ui import _Page
    from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
    from rawcandle.fundamentals.admin.ui_service import (
        AdminUIRunResult,
        AdminOperationCapability,
    )

    class Service:
        def __init__(self):
            self.calls = []

        def capabilities(self):
            return (AdminOperationCapability("REFRESH_FUNDAMENTALS", True, True, True),)

        def history_entries(self, **kwargs):
            return []

        def full_workflow(self, **kwargs):
            self.calls.append(kwargs)
            return AdminUIRunResult(
                status="FETCH_PAUSED",
                outcome="FETCH_PAUSED",
                mode="FULL_WORKFLOW",
                run_id="same-update",
                snapshot_update_run_id="same-update",
                message="FETCH paused on cooldown",
            )

    service = Service()
    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    controls.operation_dropdown.value = "REFRESH_FUNDAMENTALS"
    controls.operation_dropdown.on_change(None)
    controls.full_workflow_button.on_click(None)
    assert controls.full_workflow_button.text == "Resume snapshot UPDATE"
    controls.full_workflow_button.on_click(None)
    assert "snapshot_update_run_id" not in service.calls[0]
    assert service.calls[1]["snapshot_update_run_id"] == "same-update"


def test_integrated_shared_baseline_fault_is_global_and_never_builds(
    tmp_path, monkeypatch
):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch, degraded_count=1)
    active = resolve_active_generation(workflow.env.project)
    canonical = active.role_paths()["canonical"]
    with sqlite3.connect(canonical) as db:
        foreign = db.execute(
            "SELECT p.provider_observation_id FROM v4_field_provenance p JOIN v4_quarter q USING(quarter_id) WHERE q.company_id=1 LIMIT 1"
        ).fetchone()[0]
        db.execute(
            "UPDATE v4_common_earnings_provenance SET provider_observation_id=? WHERE provider_observation_id='missing-10'",
            (foreign,),
        )
    manifest = json.loads(active.manifest_path.read_text())
    manifest["role_verification"]["canonical"].update(
        sha256=core.sha256_file(canonical), size_bytes=canonical.stat().st_size
    )
    active.manifest_path.write_text(json.dumps(manifest))
    result = workflow.start(publication_intent=True)
    assert (
        result["outcome"] == "BLOCKED"
        and result["source_summary"]["global_blockers"] >= 1
    ), result
    assert not workflow.env.journal.exists()
    assert not list(workflow.env.runs.glob("local_*/build.json"))
    assert resolve_active_generation(workflow.env.project).generation_id == "old"


def test_copy_environment_cannot_be_supplied_as_unchecked_path_object():
    from types import SimpleNamespace

    with pytest.raises(PermissionError, match="OWNED_COPY_ENVIRONMENT"):
        SnapshotEnvironment(
            copy_owner=SimpleNamespace(root=core.ROOT, project=core.ROOT)
        )


def test_local_service_actions_cannot_resume_unsealed_fetch(tmp_path, monkeypatch):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch)
    result = workflow.start(stop_after="fetch")
    (workflow.env.directory() / "update_sources.json").unlink()
    service = FundamentalsAdminUIService(
        run_root=workflow.env.runs,
        refresh_route=ROUTE,
        snapshot_workflow=workflow,
        recover_publication_on_startup=False,
    )
    count = len(calls)
    with pytest.raises(ValueError, match="SEALED_FETCH"):
        service.preview("REFRESH_FUNDAMENTALS", raw_inputs=result["run_id"])
    with pytest.raises(ValueError, match="SEALED_FETCH"):
        service.copy_apply(
            "REFRESH_FUNDAMENTALS",
            preview_payload_path=result["preview_payload_path"],
            preview_fingerprint=result["preview_fingerprint"],
        )
    assert len(calls) == count and not workflow.env.journal.exists()
    failed = workflow.advance(result["run_id"], retry_local=True)
    assert (
        failed["outcome"] == "FAILED"
        and failed["message"] == "LOCAL_RETRY_REQUIRES_SEALED_FETCH"
    )
    assert len(calls) == count and not failed["manual_production_available"]


def test_existing_ui_preview_uses_the_selected_update_without_new_fetch():
    from tests.test_fundamentals_admin_ui import _Page
    from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
    from rawcandle.fundamentals.admin.ui_service import (
        AdminUIRunResult,
        AdminOperationCapability,
    )

    class Service:
        def __init__(self):
            self.previews = []

        def capabilities(self):
            return (AdminOperationCapability("REFRESH_FUNDAMENTALS", True, True, True),)

        def history_entries(self, **kwargs):
            return []

        def full_workflow(self, **kwargs):
            return AdminUIRunResult(
                status="CANDIDATE_READY",
                outcome="CANDIDATE_READY",
                mode="FULL_WORKFLOW",
                run_id="same-update",
                preview_payload_path="/tmp/same-update/update_request.json",
                preview_fingerprint="f" * 64,
                test_run_id="local_candidate",
                direct_production_retry_available=True,
                message="Candidate ready",
            )

        def preview(self, operation_type, **kwargs):
            self.previews.append(kwargs)
            return AdminUIRunResult(
                status="VALIDATED",
                outcome="VALIDATED",
                mode="FULL_WORKFLOW",
                run_id="same-update",
                message="Local validation",
            )

    service = Service()
    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    controls.operation_dropdown.value = "REFRESH_FUNDAMENTALS"
    controls.operation_dropdown.on_change(None)
    controls.full_workflow_button.on_click(None)
    controls.preview_button.on_click(None)
    assert service.previews[0]["raw_inputs"] == "same-update"
