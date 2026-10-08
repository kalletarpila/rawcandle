"""Bounded real Preview + scheduler/service orchestration; no Production callback."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import refresh_scheduler
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    REFRESH_REQUEST_FIELDS, ensure_refresh_state_schema, run_preview,
)
from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue, queue_path_for_run_root
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_admin_refresh_preview import _create_preview_databases, row, result
from tests.test_fundamentals_admin_refresh_full_workflow import _stage


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root, safe_count, review):
    paths = _create_preview_databases(root)
    tickers = ["TEST", *[f"SAFE{i}" for i in range(1, safe_count)]] if safe_count else []
    if review in {"local", "human"}:
        tickers.append("HELD")
    with sqlite3.connect(paths.provider_db) as p, sqlite3.connect(paths.canonical_db) as c:
        p.execute("DELETE FROM provider_observation")
        p.execute("DELETE FROM sharadar_fundamental_observation")
        p.execute("DELETE FROM sharadar_ticker_metadata")
        c.execute("DELETE FROM security")
        c.execute("DELETE FROM provider_security_identity")
        c.execute("DELETE FROM v4_quarter")
        for i, ticker in enumerate(tickers, 1):
            c.execute("INSERT INTO security VALUES(?,?,?,1)", (i, i, ticker))
            c.execute("INSERT INTO provider_security_identity VALUES('SHARADAR',?,?,?)", (str(i), i, ticker))
            c.execute("INSERT INTO v4_quarter VALUES(?,?,2026,'Q2','2026-07-31','2026-08-26','2026-08-26')", (i, i))
            p.execute("INSERT INTO sharadar_ticker_metadata VALUES('fundamentals',?,?,'N',NULL,'2026-08-26')", (ticker, str(i)))
            for dimension in ("ARQ", "MRQ"):
                observations = [row(ticker=ticker, dimension=dimension)]
                if ticker == "HELD" and review == "local":
                    observations.append(row(ticker=ticker, dimension=dimension,
                                            filing_date="2026-05-26", reportperiod="2026-04-30", fiscalperiod="2026-Q1"))
                for j, item in enumerate(observations):
                    obs = f"{ticker}-{dimension}-{j}"
                    p.execute("INSERT INTO provider_observation VALUES(?,?,?,?)", (obs, obs, i, i))
                    fields = ["observation_id", *REFRESH_REQUEST_FIELDS]
                    p.execute(f"INSERT INTO sharadar_fundamental_observation({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
                              [obs, *[item.get(field) for field in REFRESH_REQUEST_FIELDS]])
        ensure_refresh_state_schema(p)
        p.execute("INSERT INTO sharadar_refresh_state VALUES(1,'SHARADAR','fundamentals','2026-08-26','provider','schema','published-run','2026-08-26T12:00:00Z')")

    class Client:
        def schema(self, _table):
            return result([], payload=[{"name": f} for f in REFRESH_REQUEST_FIELDS])

        def fundamentals(self, **kw):
            if not kw.get("ticker"):
                return result([{"ticker": t, "dimension": kw["dimension"], "lastupdated": "2026-09-15"} for t in tickers])
            ticker = kw["ticker"]
            item = row(ticker=ticker, dimension=kw["dimension"], lastupdated="2026-09-15",
                       revenue=100 if ticker == "HELD" else 120)
            if ticker == "HELD" and review == "human":
                item["fiscalperiod"] = "2026-Q4"  # Unapproved ARQ/MRQ identity revision: global.
            return result([item])

    return paths, Client()


@pytest.mark.parametrize("trigger,mode,safe,review,authorized,reason", [
    ("SCHEDULER", "FULL_WORKFLOW", 17, None, True, "SAFE_CHANGES_TEST_AUTHORIZED"),
    ("SCHEDULER", "PREVIEW_ONLY", 17, None, False, "SCHEDULER_PREVIEW_ONLY"),
    ("MANUAL", "PREVIEW_ONLY", 17, None, True, "SAFE_CHANGES_TEST_AUTHORIZED"),
    ("SCHEDULER", "FULL_WORKFLOW", 17, "local", True, "SAFE_CHANGES_TEST_AUTHORIZED"),
    ("SCHEDULER", "FULL_WORKFLOW", 17, "human", False, "GLOBAL_BLOCKER_PRESENT"),
    ("SCHEDULER", "FULL_WORKFLOW", 0, "local", False, "NO_SAFE_CHANGES_TO_PUBLISH"),
    ("SCHEDULER", "FULL_WORKFLOW", 17, "date_gate", False, "PUBLICATION_DATE_PREREQUISITES"),
])
def test_real_scheduler_preview_authorization_rehearsal(
    tmp_path, monkeypatch, trigger, mode, safe, review, authorized, reason,
):
    paths, client = _fixture(tmp_path / "dbs", safe, review)
    if review == "date_gate":
        monkeypatch.setattr("rawcandle.fundamentals.admin.refresh_fundamentals.publication_date_gate_authorized", lambda _state: False)
    before = {name: _hash(path) for name, path in paths.as_dict().items()}
    run_root = tmp_path / "runs"
    previews, calls = [], []

    def preview(**kw):
        payload = run_preview(source_paths=paths, client=client, as_of_date=date(2026, 10, 8), **kw)
        previews.append(payload)
        return payload

    def test_backend(**kw):
        calls.append("test")
        bound = json.loads(Path(kw["preview_payload_path"]).read_text())
        assert bound["future_test_authorized"] is True
        # Deliberately stop at the Test boundary; Production must not be invoked.
        child = _stage(run_root, "bounded-test", mode="COPY_ONLY_APPLY", outcome="FAILED")
        return json.loads((Path(child.artifact_dir) / "result.json").read_text()) | {"artifact_dir": child.artifact_dir}

    def forbidden(*_args, **_kw):
        pytest.fail("Production/approval must not run in isolated rehearsal")

    monkeypatch.setattr(refresh_scheduler, "safety_status", lambda: {"production_writes_blocked": False})
    service = FundamentalsAdminUIService(
        run_root=run_root, operation_lock_path=tmp_path / "admin.lock",
        refresh_preview=preview, refresh_apply=test_backend, refresh_production_apply=forbidden,
        recover_publication_on_startup=False,
    )
    monkeypatch.setattr(refresh_scheduler, "FundamentalsAdminUIService", lambda **_kw: service)
    monkeypatch.setattr(service, "resolve_refresh_review", forbidden)
    if trigger == "SCHEDULER":
        summary = refresh_scheduler.run_scheduler_refresh_discovery(run_root=run_root, scheduler_mode=mode)
        assert summary["configured_mode"] == mode
        assert summary["trigger_source"] == trigger
        assert summary["test_invoked"] is (authorized and mode == "FULL_WORKFLOW")
        assert summary["production_invoked"] is False
        report = Path(summary["report"]).read_text()
        assert "MANUAL_PREVIEW_REQUIRED" not in report
        if mode == "FULL_WORKFLOW":
            assert "- Trigger: Scheduler" in report
            assert "- Mode: FULL_WORKFLOW" in report
            parent = json.loads((Path(summary["report"]).parent / "workflow_result.json").read_text())
            assert parent["trigger_source"] == trigger and parent["mode"] == mode
            if not authorized:
                assert reason in report
                assert previews[0]["operational_decision"]["recommended_action_text"] in report
        else:
            assert "SCHEDULER_PREVIEW_ONLY" in report
            assert "No authorization prerequisite needs resolution" in report
            assert "Test/Production intentionally not requested" in summary["message"]
    else:
        service.preview("REFRESH_FUNDAMENTALS")

    payload = previews[0]
    decision = payload["operational_decision"]
    assert decision["test_gate"] == {"authorized": authorized, "reason_code": reason}
    assert payload["summary_counts"]["safe_changes"] == safe
    assert payload["trigger_source"] == trigger and payload["workflow_mode"] == mode
    request = json.loads((Path(payload["artifact_dir"]) / "request.json").read_text())
    assert request["options"]["workflow_mode"] == mode
    assert request["trigger_source"] == trigger
    assert calls == (["test"] if trigger == "SCHEDULER" and authorized and mode == "FULL_WORKFLOW" else [])
    assert payload["refresh_preview"]["published_watermark_advanced"] is False
    assert "MANUAL_PREVIEW_REQUIRED" not in json.dumps(payload)
    assert {name: _hash(path) for name, path in paths.as_dict().items()} == before
    with sqlite3.connect(paths.provider_db) as p:
        assert p.execute("SELECT published_source_watermark,successful_run_id FROM sharadar_refresh_state").fetchone() == ("2026-08-26", "published-run")
    if review == "local":
        assert decision["held_item_count"] == 1 and decision["global_blocker_count"] == 0
        queue = RefreshReviewQueue(queue_path_for_run_root(run_root))
        assert queue.get("HELD")["operator_action"] is None
    elif review == "human":
        assert decision["global_blocker_count"] == 1
        assert decision["recommended_action_code"] == "RESOLVE_GLOBAL_BLOCKER"
    else:
        assert payload["summary_counts"].get("fiscal_identity_revisions_requiring_review", 0) == 0
        assert decision["held_item_count"] == decision["global_blocker_count"] == 0
    assert not list(run_root.rglob("*candidate*.db"))
    assert not list(run_root.rglob("*journal*.json"))


def test_invalid_workflow_mode_fails_before_io(tmp_path):
    with pytest.raises(ValueError, match="REFRESH_WORKFLOW_MODE_INVALID"):
        run_preview(run_root=tmp_path, workflow_mode="AUTO_APPROVE")
    assert not list(tmp_path.iterdir())
