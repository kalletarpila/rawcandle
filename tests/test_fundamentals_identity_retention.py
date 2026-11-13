"""FIX4: native reviewed admission is OLD retention, never incoming identity."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import batch_add_tickers as batch
from rawcandle.fundamentals.admin import identity_resolution as identities
from rawcandle.fundamentals.admin import refresh_update as core
from rawcandle.fundamentals.admin import refresh_universe as universe
from rawcandle.fundamentals.admin import review_locality as locality
from tests import test_fundamentals_refresh_universe as scope_fixtures
from tests import test_fundamentals_snapshot_integration as fixtures
from tests.provider_capture_fixtures import acquired
from tests.test_fundamentals_admin_identity_resolution import _review, _registry


def reviewed_environment(tmp_path, monkeypatch, *, ticker="LEGACY", defect=None):
    record = _review(
        ticker,
        "APPROVED",
        cik="0000000999",
        effective_date="2026-08-28",
        company_continuity="NEW_PUBLIC_ISSUER",
    )
    registry = _registry(tmp_path / "reviewed.json", record)
    monkeypatch.setattr(identities, "DEFAULT_REGISTRY_PATH", registry)
    context = dict(registry=registry, record=record)

    def prepare(fixture):
        resolution = identities.resolve_ticker_identity(
            fixture.paths, ticker, registry_path=registry
        )
        assert resolution.readiness_state == "APPROVED_VALID"
        metadata = dict(
            cik="0000000999", exchange="NASDAQ", firstpricedate="2026-08-28"
        )
        item = dict(
            ticker=ticker,
            identity_resolution=resolution.as_dict(),
            provider_metadata={"identity": metadata},
            source_category="network",
            source_fingerprint="deterministic-reviewed-fixture",
        )
        created = batch._apply_identities(
            fixture.paths, [item], applied_at="2026-09-22T13:56:59Z"
        )["rows"][0]
        context.update(
            identity=dict(
                company_id=created["company_id"],
                security_id=created["security_id"],
                provider_security_id=None,
            ),
            ticker=ticker,
        )
        histories = {
            d: [
                {
                    **fixtures.fixtures.native._source_row(ticker, d, 2025, q),
                    "permaticker": None,
                }
                for q in range(1, 5)
            ]
            for d in ("ARQ", "MRQ")
        }
        item["rows"] = acquired([r for rows in histories.values() for r in rows])
        staged = batch._stage_generic_provider_rows(
            fixture.paths, [item], applied_at="2026-09-22T13:56:59Z"
        )
        context["provider_run_id"] = staged["run_id"]
        fixtures.fixtures.native.fresh_rebuild_canonical(
            fixture.paths.provider_db,
            fixture.paths.canonical_db,
            applied_at=fixtures.fixtures.native.NOW,
        )
        old = fixtures.fixtures.native.run_full_v2_downstream(
            fixture.paths.as_dict(),
            output=fixture.root / "reviewed-old-analysis",
            as_of_date=fixtures.fixtures.native.AS_OF,
        )
        shutil.copyfile(old["candidate_analysis_db"], fixture.paths.analysis_db)
        fixture.client.histories[ticker] = deepcopy(histories)
        context["fixture_paths"] = fixture.paths

    def finish(fixture):
        scope_fixtures.subset_authority(fixture, {context["identity"]["company_id"]})
        if defect in {"owner", "run", "missing", "permaticker", "provider_header"}:
            with sqlite3.connect(fixture.paths.provider_db) as db:
                sid = context["identity"]["security_id"]
                if defect == "owner":
                    db.execute(
                        "UPDATE provider_observation SET security_id=10 WHERE security_id=?",
                        (sid,),
                    )
                elif defect == "run":
                    db.execute(
                        "UPDATE provider_run SET request_scope='unaccepted' WHERE run_id=?",
                        (context["provider_run_id"],),
                    )
                elif defect == "missing":
                    db.execute(
                        "DELETE FROM sharadar_fundamental_observation WHERE ticker=? AND dimension='MRQ'",
                        (ticker,),
                    )
                elif defect == "provider_header":
                    db.execute(
                        "UPDATE provider_observation SET provider_security_id='unproven' WHERE security_id=?",
                        (sid,),
                    )
                else:
                    rows = db.execute(
                        "SELECT s.observation_id,p.payload_json FROM sharadar_fundamental_observation s JOIN provider_observation p USING(observation_id) WHERE s.ticker=?",
                        (ticker,),
                    ).fetchall()
                    for oid, raw in rows:
                        payload = json.loads(raw)
                        payload["permaticker"] = "unproven"
                        db.execute(
                            "UPDATE provider_observation SET payload_json=? WHERE observation_id=?",
                            (json.dumps(payload), oid),
                        )
        if defect == "nonexclusive":
            with sqlite3.connect(fixture.paths.canonical_db) as db:
                db.execute(
                    "INSERT INTO security VALUES(900,?,'OTHER','NASDAQ',1,NULL,NULL,'fixture','fixture')",
                    (context["identity"]["company_id"],),
                )
        if defect == "inactive":
            with sqlite3.connect(fixture.paths.canonical_db) as db:
                db.execute(
                    "UPDATE security SET active=0 WHERE security_id=?",
                    (context["identity"]["security_id"],),
                )
        if defect == "canonical_owner":
            with sqlite3.connect(fixture.paths.provider_db) as db:
                foreign = db.execute(
                    "SELECT observation_id FROM provider_observation WHERE company_id=1 LIMIT 1"
                ).fetchone()[0]
            with sqlite3.connect(fixture.paths.canonical_db) as db:
                db.execute(
                    "UPDATE v4_field_provenance SET provider_observation_id=? WHERE quarter_id IN (SELECT quarter_id FROM v4_quarter WHERE company_id=?)",
                    (foreign, context["identity"]["company_id"]),
                )
        if defect in {"proposal", "rejected", "tampered"}:
            changed = deepcopy(record)
            if defect == "tampered":
                changed["approved_resolution"]["cik"] = "0000000888"
            else:
                changed["review_status"] = (
                    "PROPOSED" if defect == "proposal" else "REJECTED"
                )
            _registry(registry, changed)

    workflow, native, histories, calls = fixtures.setup(
        tmp_path,
        monkeypatch,
        prepare_identity=prepare,
        configure_universe=finish,
        established=True,
    )
    return workflow, context, histories, calls


def test_reviewed_old_null_provider_survives_native_publish_without_admission(
    tmp_path, monkeypatch
):
    workflow, context, _, calls = reviewed_environment(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    identity = context["identity"]
    ticker = context["ticker"]
    # The admission approval is historical, not a replayable current mutation.
    resolution = identities.resolve_ticker_identity(
        paths, ticker, registry_path=context["registry"]
    )
    assert (
        not resolution.automatic_mutation_permitted
        and resolution.readiness_state == "APPROVED_INVALID"
    )
    installed = universe.InstalledUniverse(paths)
    assert installed.resolve(ticker)["status"] == "EXCLUDED"
    retained, blocked = installed.old_retention()
    assert not blocked and [r["ticker"] for r in retained] == [ticker]
    evidence = retained[0]["retention_proof"]
    old = locality.authority(
        paths.provider_db,
        paths.canonical_db,
        ticker,
        identity,
        allow_missing_provider=True,
        retention_proof=evidence,
    )
    scores = scope_fixtures.historical_scores(paths, identity["company_id"])
    endpoints = universe.analysis_history(
        paths.analysis_db, paths.canonical_db, {identity["company_id"]}
    )
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"
    assert (ticker, "ARQ") not in calls and (ticker, "MRQ") not in calls
    build = core._read(workflow.env.runs / result["validation_id"] / "build.json")
    assert build["analysis_result"]["invocation_counts"]["full_v2_rebuild"] == 1
    assert build["old_retention_preservation"]["reviewed_retained_tickers"] == [ticker]
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    current = workflow.env.paths()
    assert (
        locality.authority(
            current.provider_db,
            current.canonical_db,
            ticker,
            identity,
            allow_missing_provider=True,
            retention_proof=evidence,
        )
        == old
    )
    assert scope_fixtures.historical_scores(current, identity["company_id"]) == scores
    assert (
        universe.analysis_history(
            current.analysis_db, current.canonical_db, {identity["company_id"]}
        )
        == endpoints
    )
    with sqlite3.connect(current.canonical_db) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM provider_security_identity WHERE security_id=?",
                (identity["security_id"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM fundamentals_operational_universe_member m JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) WHERE m.company_id=?",
                (identity["company_id"],),
            ).fetchone()[0]
            == 0
        )
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )


@pytest.mark.parametrize(
    "defect",
    [
        "owner",
        "run",
        "missing",
        "permaticker",
        "provider_header",
        "nonexclusive",
        "proposal",
        "rejected",
        "tampered",
        "canonical_owner",
    ],
)
def test_unproven_historical_owner_or_admission_stops(tmp_path, monkeypatch, defect):
    workflow, context, _, _ = reviewed_environment(tmp_path, monkeypatch, defect=defect)
    with pytest.raises(ValueError):
        universe.InstalledUniverse(workflow.env.paths()).old_retention()
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"


def test_retention_proof_cannot_be_used_for_incoming_or_changed_candidate(
    tmp_path, monkeypatch
):
    workflow, context, _, _ = reviewed_environment(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    retained, _ = universe.InstalledUniverse(paths).old_retention()
    proof = retained[0]["retention_proof"]
    with pytest.raises(ValueError, match="NOT_INCOMING_AUTHORITY"):
        locality.authority(
            paths.provider_db,
            paths.canonical_db,
            context["ticker"],
            context["identity"],
            validate=True,
            allow_missing_provider=True,
            retention_proof=proof,
        )
    result = workflow.start(stop_after="validate", ownership_intent=False)
    assert result["outcome"] == "VALIDATED", result
    changed = deepcopy(proof)
    changed["generation"]["generation_id"] = "other"
    item = {**retained[0], "retention_proof": changed}
    with pytest.raises(ValueError, match="GENERATION_BINDING_MISMATCH"):
        locality.verify_retained(
            paths,
            paths.provider_db,
            paths.canonical_db,
            [item],
            old_authority=core.acquisition.pin_old_authority(workflow.env.project),
        )
    with sqlite3.connect(paths.provider_db) as db:
        db.execute(
            "UPDATE provider_observation SET provenance_json='{} changed' WHERE security_id=?",
            (context["identity"]["security_id"],),
        )
    with pytest.raises(ValueError, match="PROOF_MISMATCH"):
        locality.authority(
            paths.provider_db,
            paths.canonical_db,
            context["ticker"],
            context["identity"],
            allow_missing_provider=True,
            retention_proof=proof,
        )


def test_unique_financial_source_is_not_implicit_multi_security_selection(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = scope_fixtures.environment(tmp_path, monkeypatch, "multi")
    paths = workflow.env.paths()
    with sqlite3.connect(paths.provider_db) as db:
        assert {
            r[0]
            for r in db.execute(
                "SELECT DISTINCT p.security_id FROM provider_observation p JOIN sharadar_fundamental_observation s USING(observation_id) WHERE p.company_id=1 AND s.dimension IN ('ARQ','MRQ')"
            )
        } == {10}
    installed = universe.InstalledUniverse(paths)
    assert installed.resolve("AAA")["status"] == "AMBIGUOUS"
    assert installed.resolve("AAAB")["status"] == "AMBIGUOUS"
    with sqlite3.connect(paths.canonical_db) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,count(*) n FROM v4_quarter GROUP BY 1,2,3 HAVING n>1)"
            ).fetchone()[0]
            == 0
        )


def test_reviewed_retention_does_not_bypass_inactive_analysis_stop(
    tmp_path, monkeypatch
):
    workflow, context, _, _ = reviewed_environment(
        tmp_path, monkeypatch, defect="inactive"
    )
    before = {
        r: core.sha256_file(p)
        for r, p in workflow.env.paths().as_dict().items()
        if r in ("provider", "canonical", "analysis")
    }
    result = workflow.start(stop_after="validate", ownership_intent=False)
    assert result["outcome"] == "VALIDATED", result
    result = workflow.advance(result["run_id"], stop_after="build")
    assert result["outcome"] == "FAILED", result
    assert "REFRESH_OLD_ANALYSIS_RETENTION_UNSUPPORTED" in result["message"]
    assert not (workflow.env.runs / result["validation_id"] / "candidate").exists()
    assert {
        r: core.sha256_file(p)
        for r, p in workflow.env.paths().as_dict().items()
        if r in before
    } == before


def test_reviewed_retention_preserves_native_rollback(tmp_path, monkeypatch):
    workflow, _, _, _ = reviewed_environment(tmp_path, monkeypatch)
    before = {
        r: core.sha256_file(p)
        for r, p in workflow.env.paths().as_dict().items()
        if r in ("provider", "canonical", "analysis")
    }
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    result = workflow.advance(
        result["run_id"], confirm_publish=True, inject_failure="AFTER_ACTIVATION"
    )
    assert result["outcome"] == "ROLLED_BACK", result
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"
    assert {
        r: core.sha256_file(p)
        for r, p in workflow.env.paths().as_dict().items()
        if r in before
    } == before
