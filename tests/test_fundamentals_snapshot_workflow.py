"""Phase 2 real SQLite/V2/native publication with fake Phase 1 HTTP only."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest

from rawcandle.fundamentals.admin import acquisition_snapshot as acquisition
from rawcandle.fundamentals.admin import refresh_update as phase2
from rawcandle.fundamentals.admin import publication_journal as journals
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.providers.sharadar import SharadarClient
from tests.provider_capture_fixtures import full_row
from tests import (
    test_fundamentals_admin_refresh_full_workflow_production_parity as native,
)

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


class Response(io.BytesIO):
    status = 200
    headers = {"Content-Type": "application/json"}

    def getcode(self):
        return 200


def add_degraded_baselines(fixture, count):
    """Independent accepted OLD state, including references that stay broken."""
    from tests.provider_capture_fixtures import trusted_history
    import shutil

    for n in range(count):
        company = n + 10
        ticker = f"HELD{n:03}"
        sid = company * 10
        pid = str(company * 100)
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            db.execute(
                "INSERT INTO company VALUES(?,?,?,?,?,?)",
                (company, ticker, ticker, "ACTIVE", native.NOW, native.NOW),
            )
            db.execute(
                "INSERT INTO security VALUES(?,?,?,?,1,NULL,NULL,?,?)",
                (sid, company, ticker, "NASDAQ", native.NOW, native.NOW),
            )
            db.execute(
                "INSERT INTO ticker_alias VALUES(?,?,?,'SHARADAR',NULL,NULL,'fixture')",
                (company, sid, ticker),
            )
            db.execute(
                "INSERT INTO provider_security_identity VALUES('SHARADAR',?,?,?,'fixture',?)",
                (pid, sid, ticker, native.NOW),
            )
            db.execute(
                "INSERT INTO provider_company_identity VALUES('SHARADAR','PERMATICKER',?,?,?,'fixture','fixture',?,?)",
                (pid, company, ticker, pid, native.NOW),
            )
        history = {
            d: [native._source_row(ticker, d, 2025, q) for q in range(1, 5)]
            for d in ("ARQ", "MRQ")
        }
        native.replace_provider_histories(
            fixture.paths.provider_db,
            {
                ticker: {
                    d: trusted_history(rows, ticker=ticker, dimension=d)
                    for d, rows in history.items()
                }
            },
            {
                ticker: {
                    "company_id": company,
                    "security_id": sid,
                    "provider_security_id": pid,
                }
            },
            applied_at=native.NOW,
        )
        with sqlite3.connect(fixture.paths.provider_db) as db:
            db.execute(
                "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,payload_json,fetched_at_utc) VALUES('fundamentals',?,?, '{}',?)",
                (ticker, pid, native.NOW),
            )
        fixture.client.histories[ticker] = deepcopy(history)
        for rows in fixture.client.histories[ticker].values():
            rows[-1]["revenue"] += 999
    native.fresh_rebuild_canonical(
        fixture.paths.provider_db, fixture.paths.canonical_db, applied_at=native.NOW
    )
    with sqlite3.connect(fixture.paths.canonical_db) as db:
        for company in range(10, 10 + count):
            db.execute(
                "UPDATE v4_common_earnings_provenance SET provider_observation_id=? WHERE quarter_id=(SELECT max(quarter_id) FROM v4_quarter WHERE company_id=?)",
                (f"missing-{company}", company),
            )
    result = native.run_full_v2_downstream(
        fixture.paths.as_dict(),
        output=fixture.root / "accepted-old-analysis",
        as_of_date=native.AS_OF,
    )
    shutil.copyfile(result["candidate_analysis_db"], fixture.paths.analysis_db)


def prepare_rolling_old(fixture):
    import shutil
    from tests.provider_capture_fixtures import trusted_history

    baseline = {
        d: [
            native._source_row("AAA", d, y, q)
            for y, q in native._quarter_range(2016, 3, 2026, 2)
        ]
        for d in ("ARQ", "MRQ")
    }
    native.replace_provider_histories(
        fixture.paths.provider_db,
        {
            "AAA": {
                d: trusted_history(rs, ticker="AAA", dimension=d)
                for d, rs in baseline.items()
            }
        },
        {"AAA": {"company_id": 1, "security_id": 10, "provider_security_id": "100"}},
        applied_at=native.NOW,
    )
    native.fresh_rebuild_canonical(
        fixture.paths.provider_db,
        fixture.paths.canonical_db,
        applied_at=native.NOW,
        affected_company_ids=[1],
    )
    initial = native.run_full_v2_downstream(
        fixture.paths.as_dict(),
        output=fixture.root / "old-rolling-analysis",
        as_of_date=native.AS_OF,
    )
    shutil.copyfile(initial["candidate_analysis_db"], fixture.paths.analysis_db)
    fixture.client.histories["AAA"] = {
        d: rs[1:] + [native._source_row("AAA", d, 2026, 3, lastupdated="2026-09-20")]
        for d, rs in baseline.items()
    }


def setup(
    tmp_path,
    monkeypatch,
    *,
    held=False,
    degraded_count=0,
    established=False,
    rolling=False,
):
    env = phase2.create_disposable_environment(tmp_path / "phase2")
    fixture = native._fixture(env.root, monkeypatch, include_yyai_hold=held)
    if degraded_count:
        add_degraded_baselines(fixture, degraded_count)
    if rolling:
        prepare_rolling_old(fixture)
    if established:
        from rawcandle.fundamentals.admin.refresh_production import (
            _publish_refresh_state,
        )

        _publish_refresh_state(
            fixture.paths.provider_db,
            source_watermark="2026-08-15",
            schema_fingerprint="fixture-schema",
            run_id="fixture-old-publication",
            completed_at=native.NOW,
        )
        import shutil

        old_analysis = native.run_full_v2_downstream(
            fixture.paths.as_dict(),
            output=env.root / "old-established-analysis",
            as_of_date=native.AS_OF,
        )
        shutil.copyfile(
            old_analysis["candidate_analysis_db"], fixture.paths.analysis_db
        )
    native._migrate_refresh_fixture_to_generation_layout(fixture, monkeypatch)
    histories = deepcopy(fixture.client.histories)
    calls = []

    def opener(request, timeout):
        p = {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}
        if "/schema/" in request.full_url:
            from rawcandle.fundamentals.admin.refresh_fundamentals import (
                REFRESH_REQUEST_FIELDS,
            )

            calls.append(("schema",))
            payload = list(REFRESH_REQUEST_FIELDS)
        else:
            calls.append((p["ticker"], p["dimension"]))
            payload = [
                full_row(row)
                for row in histories[p["ticker"]][p["dimension"]]
                if p["from"] <= row["date"] <= p["to"]
            ]
        return Response(json.dumps(payload).encode())

    def acquire(tickers=None):
        client = SharadarClient(
            api_key="fixture-phase2-key",
            opener=opener,
            wall_clock=lambda: NOW.timestamp(),
        )
        result = acquisition.start_fetch(
            tickers or sorted(histories),
            project_root=env.project,
            source_day=NOW.date().isoformat(),
            root=env.runs,
            client=client,
            now=lambda: NOW,
        )
        assert result["status"] == "FETCH_SEALED"
        return result["snapshot_reference"]["operation_id"]

    return env, fixture, histories, calls, acquire


def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden after FETCH")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("rawcandle.fundamentals.providers.sharadar.urlopen", forbidden)
    monkeypatch.setattr(SharadarClient, "_request", forbidden)
    from rawcandle.fundamentals.result_publication import SecClient

    monkeypatch.setattr(SecClient, "item_2_02_filings", forbidden)


def prepare(env, operation):
    validated = phase2.validate_snapshot(
        env, operation, as_of_date=native.AS_OF, now=lambda: NOW
    )
    assert validated["status"] == "VALIDATED", validated
    return phase2.build_candidate(
        env,
        validated["validation_id"],
        expected_validation_fingerprint=validated["fingerprint"],
        now=lambda: NOW,
    )


def publish(env, receipt, **kwargs):
    return phase2.publish_disposable(
        env,
        receipt["validation_id"],
        expected_validation_fingerprint=receipt["fingerprint"],
        confirmation=phase2.CONFIRM,
        now=lambda: NOW,
        **kwargs,
    )


def test_real_snapshot_candidate_native_publication_without_network(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    assert len(calls) == 5
    no_network(monkeypatch)
    before = {
        r: journals.sha256_file(p)
        for r, p in resolve_active_generation(env.project).role_paths().items()
    }
    receipt = prepare(env, operation)
    assert receipt["status"] == "CANDIDATE_READY"
    assert receipt["counts"]["safe"] == 1
    assert receipt["production_authorized"] is False
    assert resolve_active_generation(env.project).generation_id == "old"
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result
    assert result["postflight"]["cross_role_lineage"][
        "analysis_matches_validated_candidate"
    ]
    active = resolve_active_generation(env.project)
    assert active.generation_id == receipt["candidate_generation_id"]
    old = env.project / "data/fundamentals_generations/old"
    assert all(
        journals.sha256_file(old / p.name) == before[r]
        for r, p in active.role_paths().items()
    )
    journal = journals.load_journal(env.journal)
    assert (
        journal["state"],
        journal["postflight_state"],
        journal["rollback_recovery_state"],
    ) == ("COMPLETED", "PASSED", "NOT_REQUIRED")
    assert journal["preview_run_id"] is None and journal["test_run_id"] is None
    assert journal["snapshot_authorization"]["contract"] == phase2.CONTRACT
    assert len(calls) == 5


@pytest.mark.parametrize("defect", ["expired", "body_tamper"])
def test_snapshot_age_or_integrity_cannot_be_reacquired(tmp_path, monkeypatch, defect):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    count = len(calls)
    no_network(monkeypatch)
    if defect == "body_tamper":
        path = next((env.runs / operation / "fetch/responses").glob("*.body"))
        path.write_bytes(path.read_bytes() + b"x")
        with pytest.raises((acquisition.SnapshotError, ValueError)):
            phase2.validate_snapshot(
                env, operation, as_of_date=native.AS_OF, now=lambda: NOW
            )
    else:
        with pytest.raises(acquisition.SnapshotError, match="EXPIRED"):
            phase2.validate_snapshot(
                env,
                operation,
                as_of_date=native.AS_OF,
                now=lambda: NOW + timedelta(days=7, microseconds=1),
            )
    assert (
        len(calls) == count
        and resolve_active_generation(env.project).generation_id == "old"
    )


def test_local_history_removal_holds_ticker_and_publishes_safe_peer(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    for d in ("ARQ", "MRQ"):
        histories["AAA"][d].pop(1)
        histories["BBB"][d][-1]["revenue"] += 17
    operation = acquire()
    no_network(monkeypatch)
    before = native._published_financial_fingerprint(
        fixture.paths, ticker="AAA", company_id=1
    )
    receipt = prepare(env, operation)
    assert receipt["counts"]["safe"] == 1 and receipt["counts"]["local_holds"] == 1
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result
    assert (
        native._published_financial_fingerprint(env.paths(), ticker="AAA", company_id=1)
        == before
    )
    decision = json.loads(
        (env.runs / receipt["validation_id"] / "decisions.json").read_text()
    )
    assert decision["held"][0]["change"]["source_history_events"]
    assert decision["safe"][0]["ticker"] == "BBB"


def test_no_change_and_repeated_validation_have_no_candidate_build(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    from rawcandle.fundamentals.admin import refresh_fundamentals as rules

    for ticker in histories:
        histories[ticker] = {
            d: [
                dict(r["_acquisition_payload"])
                for r in rules.load_current_history(
                    fixture.paths.provider_db, ticker, d
                )["rows"]
            ]
            for d in ("ARQ", "MRQ")
        }
    operation = acquire()
    no_network(monkeypatch)
    first = phase2.validate_snapshot(
        env, operation, as_of_date=native.AS_OF, now=lambda: NOW
    )
    second = phase2.validate_snapshot(
        env, operation, as_of_date=native.AS_OF, now=lambda: NOW
    )
    assert first["status"] == second["status"] == "NO_CHANGE"
    assert first["decision_fingerprint"] == second["decision_fingerprint"]
    result = phase2.build_candidate(
        env,
        first["validation_id"],
        expected_validation_fingerprint=first["fingerprint"],
        now=lambda: NOW,
    )
    assert (
        result["status"] == "NO_CHANGE"
        and not (env.runs / first["validation_id"] / "candidate").exists()
    )
    assert not env.journal.exists()


@pytest.mark.parametrize(
    "boundary", ["AFTER_PREPARE", "AFTER_ACTIVATION", "AFTER_POSTFLIGHT"]
)
def test_native_failure_restores_exact_isolated_old_generation(
    tmp_path, monkeypatch, boundary
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    before = {
        r: journals.sha256_file(p)
        for r, p in resolve_active_generation(env.project).role_paths().items()
    }
    pointer = (env.project / "data/fundamentals_active_generation.json").read_bytes()
    receipt = prepare(env, operation)
    result = publish(env, receipt, inject_failure=boundary)
    assert result["status"] == "ROLLED_BACK", result
    assert resolve_active_generation(env.project).generation_id == "old"
    assert before == {
        r: journals.sha256_file(p)
        for r, p in resolve_active_generation(env.project).role_paths().items()
    }
    assert (
        env.project / "data/fundamentals_active_generation.json"
    ).read_bytes() == pointer
    assert journals.load_journal(env.journal)["state"] == "ROLLED_BACK"


@pytest.mark.parametrize(
    "boundary", ["AFTER_PREPARE", "AFTER_ACTIVATION", "AFTER_POSTFLIGHT"]
)
def test_crash_recovery_uses_native_old_without_source_snapshot(
    tmp_path, monkeypatch, boundary
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    before = {
        r: journals.sha256_file(p)
        for r, p in resolve_active_generation(env.project).role_paths().items()
    }
    receipt = prepare(env, operation)
    with pytest.raises(phase2.native.SimulatedPublicationCrash):
        publish(env, receipt, inject_crash=boundary)
    # Native OLD recovery must be independent of retained FETCH evidence.
    (env.runs / operation / "fetch/seal.json").unlink()
    with pytest.raises(journals.PublicationRecoveredRetryRequired):
        phase2.recover_disposable(env)
    assert journals.load_journal(env.journal)["state"] == "RECOVERED"
    assert resolve_active_generation(env.project).generation_id == "old"
    assert before == {
        r: journals.sha256_file(p)
        for r, p in resolve_active_generation(env.project).role_paths().items()
    }
    assert phase2.recover_disposable(env)["status"] == "RECOVERED"


@pytest.mark.parametrize(
    "defect", ["market", "queue", "candidate", "read_copy", "expiry"]
)
def test_stale_candidate_never_activates(tmp_path, monkeypatch, defect):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    if defect == "market":
        with sqlite3.connect(env.paths().market_db) as db:
            db.execute("CREATE TABLE changed_dependency(value)")
    elif defect == "queue":
        from rawcandle.fundamentals.admin.refresh_review_queue import (
            RefreshReviewQueue,
            classify_review_scope,
        )
        from tests.test_fundamentals_admin_refresh_review_queue import (
            _ticker_local_review,
        )

        RefreshReviewQueue(env.queue).upsert_local(
            classify_review_scope(_ticker_local_review("UNRELATED", 99)),
            run_id="new",
            published_binding="old",
        )
    elif defect == "candidate":
        path = Path(
            json.loads(
                (env.runs / receipt["validation_id"] / "build.json").read_text()
            )["prepared"]["roles"]["provider"]
        )
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE tamper(value)")
    if defect == "read_copy":
        build = json.loads(
            (env.runs / receipt["validation_id"] / "build.json").read_text()
        )
        with sqlite3.connect(build["read_only_sources"]["market"]) as db:
            db.execute("CREATE TABLE stale_copy(value)")
    if defect == "expiry":
        with pytest.raises(acquisition.SnapshotError, match="EXPIRED"):
            phase2.publish_disposable(
                env,
                receipt["validation_id"],
                expected_validation_fingerprint=receipt["fingerprint"],
                confirmation=phase2.CONFIRM,
                now=lambda: NOW + timedelta(days=8),
            )
    else:
        with pytest.raises(phase2.Phase2Error, match="DRIFT|TAMPERED"):
            publish(env, receipt)
    assert (
        not env.journal.exists()
        and resolve_active_generation(env.project).generation_id == "old"
    )


def test_explicit_disposable_intent_is_separate_from_validation_or_tests(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    with pytest.raises(PermissionError):
        phase2.publish_disposable(
            env,
            receipt["validation_id"],
            expected_validation_fingerprint=receipt["fingerprint"],
            confirmation="",
            now=lambda: NOW,
        )
    with pytest.raises(phase2.Phase2Error, match="EXACT_RECEIPT"):
        phase2.publish_disposable(
            env,
            receipt["validation_id"],
            expected_validation_fingerprint=None,
            confirmation=phase2.CONFIRM,
            now=lambda: NOW,
        )
    assert resolve_active_generation(env.project).generation_id == "old"


def test_global_foreign_identity_prevents_any_candidate(tmp_path, monkeypatch):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    for rows in histories["AAA"].values():
        rows[0]["permaticker"] = "FOREIGN"
    operation = acquire()
    no_network(monkeypatch)
    with pytest.raises(phase2.Phase2Error, match="FOREIGN_PROVIDER_IDENTITY"):
        phase2.validate_snapshot(
            env, operation, as_of_date=native.AS_OF, now=lambda: NOW
        )
    assert not env.journal.exists()


def test_native_ordinary_hold_does_not_enter_safe_candidate(tmp_path, monkeypatch):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch, held=True)
    operation = acquire()
    no_network(monkeypatch)
    before = native._published_financial_fingerprint(
        fixture.paths, ticker="YYAI", company_id=3
    )
    receipt = prepare(env, operation)
    assert receipt["counts"]["safe"] == 2 and receipt["counts"]["local_holds"] == 1
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result
    assert (
        native._published_financial_fingerprint(
            env.paths(), ticker="YYAI", company_id=3
        )
        == before
    )


def test_local_code_drift_invalidates_candidate_without_rebuilding(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    monkeypatch.setattr(phase2, "_code_binding", lambda: "different-validator")
    with pytest.raises(phase2.Phase2Error, match="LOCAL_AUTHORITY_DRIFT"):
        publish(env, receipt)
    assert resolve_active_generation(env.project).generation_id == "old"


def test_live_or_unowned_environment_paths_are_rejected(tmp_path):
    with pytest.raises(phase2.Phase2Error):
        phase2.create_disposable_environment(phase2.ROOT)
    env = phase2.create_disposable_environment(tmp_path / "owner")
    outside = tmp_path / "outside"
    outside.mkdir()
    env.project.symlink_to(outside, target_is_directory=True)
    with pytest.raises(phase2.Phase2Error, match="SYMLINK"):
        env.check()


def test_post_commit_bookkeeping_failure_never_rolls_back_healthy_finance(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    original = phase2._finalize_reviews

    def fail(*args, **kwargs):
        raise RuntimeError("fixture review sync failure")

    monkeypatch.setattr(phase2, "_finalize_reviews", fail)
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED_WITH_REVIEW_SYNC_PENDING"
    assert journals.load_journal(env.journal)["state"] == "COMPLETED"
    assert (
        resolve_active_generation(env.project).generation_id
        == receipt["candidate_generation_id"]
    )
    monkeypatch.setattr(phase2, "_finalize_reviews", original)
    assert phase2.finalize_disposable_reviews(env, receipt["validation_id"]) == []


@pytest.mark.parametrize("count,acquired_held", [(1, True), (100, False)])
def test_full_old_domain_degraded_holds_preserve_exact_finance(
    tmp_path, monkeypatch, count, acquired_held
):
    env, fixture, histories, calls, acquire = setup(
        tmp_path, monkeypatch, degraded_count=count
    )
    names = [f"HELD{n:03}" for n in range(count)]
    before = {
        name: native._published_financial_fingerprint(
            fixture.paths, ticker=name, company_id=n + 10
        )
        for n, name in enumerate(names)
    }
    operation = acquire() if acquired_held else acquire(["AAA", "BBB"])
    if not acquired_held:
        assert len(calls) == 5
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    assert receipt["counts"]["baseline_holds"] == count
    assert (
        receipt["counts"]["local_holds"] == count and receipt["counts"]["global"] == 0
    )
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result
    for n, name in enumerate(names):
        assert (
            native._published_financial_fingerprint(
                env.paths(), ticker=name, company_id=n + 10
            )
            == before[name]
        )
    assert result["held_preservation"]["unchanged"]
    with sqlite3.connect(f"file:{env.paths().canonical_db}?mode=ro", uri=True) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM v4_common_earnings_provenance WHERE provider_observation_id LIKE 'missing-%'"
            ).fetchone()[0]
            == count
        )


def test_new_quarter_uses_native_publication_retry_scope_with_offline_missing_input(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    for d in ("ARQ", "MRQ"):
        histories["AAA"][d].append(native._source_row("AAA", d, 2026, 1))
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    build = json.loads((env.runs / receipt["validation_id"] / "build.json").read_text())
    assert build["publication_dates"]["retry_days"] == 60
    assert build["publication_dates"]["retry_max_quarters"] == 100
    assert build["canonical_result"]["impact"]["added_quarters"] == 1
    assert build["analysis_result"]["invocation_counts"] == {
        "full_v2_rebuild": 1,
        "package": 1,
        "relative_position": 1,
        "relative_valuation": 1,
    }
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result


def test_shared_accepted_identity_fault_blocks_even_with_safe_peers(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(
        tmp_path, monkeypatch, degraded_count=1
    )
    # Amend this synthetic baseline BEFORE pinning FETCH, then rebind its native
    # fixture manifest. A foreign source company is a shared authority fault.
    active = resolve_active_generation(env.project)
    with sqlite3.connect(active.role_paths()["canonical"]) as db:
        foreign = db.execute(
            "SELECT provider_observation_id FROM v4_field_provenance p JOIN v4_quarter q USING(quarter_id) WHERE company_id=1 LIMIT 1"
        ).fetchone()[0]
        db.execute(
            "UPDATE v4_common_earnings_provenance SET provider_observation_id=? WHERE provider_observation_id=?",
            (foreign, "missing-10"),
        )
    manifest_path = active.manifest_path
    manifest = json.loads(manifest_path.read_text())
    path = active.role_paths()["canonical"]
    manifest["role_verification"]["canonical"]["sha256"] = journals.sha256_file(path)
    manifest["role_verification"]["canonical"]["size_bytes"] = path.stat().st_size
    manifest_path.write_text(json.dumps(manifest))
    operation = acquire(["AAA", "BBB"])
    no_network(monkeypatch)
    receipt = phase2.validate_snapshot(
        env, operation, as_of_date=native.AS_OF, now=lambda: NOW
    )
    assert receipt["status"] == "BLOCKED" and receipt["counts"]["global"] >= 1
    with pytest.raises(phase2.Phase2Error, match="BUILD_NOT_AUTHORIZED"):
        phase2.build_candidate(
            env,
            receipt["validation_id"],
            expected_validation_fingerprint=receipt["fingerprint"],
            now=lambda: NOW,
        )
    assert (
        resolve_active_generation(env.project).generation_id == "old"
        and not env.journal.exists()
    )


def test_review_approval_remains_explicit_bound_and_finalized_only_after_commit(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(
        tmp_path, monkeypatch, held=True, established=True
    )
    operation = acquire()
    no_network(monkeypatch)
    first = phase2.validate_snapshot(
        env, operation, as_of_date=native.AS_OF, now=lambda: NOW
    )
    from rawcandle.fundamentals.admin import refresh_review_queue as q

    queue = q.RefreshReviewQueue(env.queue)
    item = queue.get("YYAI")
    assert q.retained_history_approval_eligibility(item)["eligible"]
    approved = queue.apply_action(
        "YYAI", q.ACCEPT_RETAINED_HISTORY, evidence={"operator": "fixture"}
    )
    assert approved["status"] == "RETRY_REEVALUATION"
    receipt = prepare(env, operation)
    assert queue.get("YYAI")["status"] == "RETRY_REEVALUATION"
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result
    assert queue.get("YYAI")["status"] == "RESOLVED"
    assert phase2.finalize_disposable_reviews(env, receipt["validation_id"])


def test_verified_rolling_expiry_preserves_frozen_old_and_advances_current_quarter(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch, rolling=True)

    def frozen(path):
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute(
                "SELECT q.fiscal_year,q.fiscal_quarter,q.period_end,q.first_public_result_date,f.revenue,f.net_income FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) WHERE company_id=1 AND period_end<='2024-12-31' ORDER BY 1,2"
            ).fetchall()

    before = frozen(fixture.paths.canonical_db)
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    assert (
        receipt["counts"]["safe"] == 1
        and receipt["counts"]["local_holds"] == 0
        and receipt["counts"]["global"] == 0
    )
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result
    assert frozen(env.paths().canonical_db) == before
    with sqlite3.connect(f"file:{env.paths().canonical_db}?mode=ro", uri=True) as db:
        assert db.execute(
            "SELECT 1 FROM v4_quarter WHERE company_id=1 AND fiscal_year=2026 AND fiscal_quarter='Q3'"
        ).fetchone()
        assert db.execute(
            "SELECT 1 FROM v4_quarter WHERE company_id=1 AND fiscal_year=2016 AND fiscal_quarter='Q3'"
        ).fetchone()


def test_legacy_extended_queue_row_is_read_and_not_a_global_blocker_by_presence(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    from tests.test_fundamentals_history_queue_correction import old_queue_row

    old, _ = old_queue_row(env.root, extended=True, baseline=True)
    # Isolated operational queue, unrelated to this source scope. Its legacy
    # proof remains evidence rather than a new blocker or financial approval.
    old.path.rename(env.queue)
    operation = acquire()
    no_network(monkeypatch)
    before = journals.sha256_file(env.queue)
    receipt = prepare(env, operation)
    assert receipt["counts"]["global"] == 0
    assert journals.sha256_file(env.queue) == before
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED", result


def test_validation_and_receipt_tampering_prevents_candidate_build(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    receipt = phase2.validate_snapshot(
        env, operation, as_of_date=native.AS_OF, now=lambda: NOW
    )
    path = env.runs / receipt["validation_id"] / "decisions.json"
    data = json.loads(path.read_text())
    data["safe"][0]["identity"]["company_id"] = 999
    path.write_text(json.dumps(data))
    with pytest.raises(phase2.Phase2Error, match="DECISIONS_TAMPERED"):
        phase2.build_candidate(
            env,
            receipt["validation_id"],
            expected_validation_fingerprint=receipt["fingerprint"],
            now=lambda: NOW,
        )
    assert not env.journal.exists()


def test_only_one_native_full_build_and_healthy_journal_not_replayed(
    tmp_path, monkeypatch
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    observed = []
    original = phase2.native.run_refresh_production_full_v2_downstream

    def counted(**kwargs):
        observed.append(1)
        return original(**kwargs)

    monkeypatch.setattr(
        phase2.native, "run_refresh_production_full_v2_downstream", counted
    )
    receipt = prepare(env, operation)
    with pytest.raises(phase2.Phase2Error, match="BUILD_NOT_AUTHORIZED"):
        phase2.build_candidate(
            env,
            receipt["validation_id"],
            expected_validation_fingerprint=receipt["fingerprint"],
            now=lambda: NOW,
        )
    assert len(observed) == 1
    result = publish(env, receipt)
    assert result["status"] == "PUBLISHED"
    pointer = (env.project / "data/fundamentals_active_generation.json").read_bytes()
    assert phase2.recover_disposable(env)["status"] == "COMPLETED"
    assert (
        env.project / "data/fundamentals_active_generation.json"
    ).read_bytes() == pointer
    with pytest.raises(phase2.Phase2Error, match="LOCAL_AUTHORITY_DRIFT"):
        publish(env, receipt)
    report = (env.runs / receipt["validation_id"] / "operation_report.md").read_text()
    assert "PUBLISHED" in report and "root SHA" in report


@pytest.mark.parametrize("defect", ["pointer", "backup", "new_id"])
def test_native_recovery_cannot_follow_journal_outside_disposable_scope(
    tmp_path, monkeypatch, defect
):
    env, fixture, histories, calls, acquire = setup(tmp_path, monkeypatch)
    operation = acquire()
    no_network(monkeypatch)
    receipt = prepare(env, operation)
    with pytest.raises(phase2.native.SimulatedPublicationCrash):
        publish(env, receipt, inject_crash="AFTER_PREPARE")
    journal = json.loads(env.journal.read_text())
    if defect == "pointer":
        journal["active_generation_manifest_path"] = str(
            phase2.ROOT / "data/fundamentals_active_generation.json"
        )
    elif defect == "backup":
        journal["roles"]["provider"]["backup_path"] = str(
            phase2.ROOT / "data/fundamentals_provider.db"
        )
    else:
        journal["new_generation_id"] = "../../outside"
    env.journal.write_text(json.dumps(journal))
    before = env.journal.read_bytes()
    with pytest.raises((phase2.Phase2Error, ValueError, RuntimeError)):
        phase2.recover_disposable(env)
    assert env.journal.read_bytes() == before
    assert resolve_active_generation(env.project).generation_id == "old"


def test_disposable_controls_reject_hardlinks_and_traversal(tmp_path):
    import os

    env = phase2.create_disposable_environment(tmp_path / "owner")
    outside = tmp_path / "outside"
    outside.write_text("{}")
    os.link(outside, env.queue)
    with pytest.raises(phase2.Phase2Error, match="HARDLINK"):
        env.check()
    with pytest.raises(phase2.Phase2Error):
        phase2.create_disposable_environment(tmp_path / ".." / "escape")
