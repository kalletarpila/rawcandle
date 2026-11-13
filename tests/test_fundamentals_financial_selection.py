"""Operator selections, native immutable versions, isolated build/publication."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import financial_selection as selection
from rawcandle.fundamentals.admin import refresh_universe as scope
from rawcandle.fundamentals.admin import refresh_update as core
from rawcandle.fundamentals.admin import refresh_production as publication
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin import baseline_carry_forward as carry
from rawcandle.fundamentals.admin.contracts import fingerprint
from rawcandle.fundamentals.generations import (
    active_manifest_path,
    prepare_generation_from_candidates,
    resolve_active_generation,
)
from rawcandle.fundamentals.phase13b_foundation import online_backup
from tests import test_fundamentals_snapshot_integration as fixtures
from tests import test_fundamentals_refresh_universe as scope_fixtures
from tests.provider_capture_fixtures import trusted_history

APPROVED = json.loads(
    (Path(__file__).parent / "fixtures/fundamentals_fix7_selections.json").read_text()
)


def plan(paths, decisions):
    return selection.prepare_reconciliation(
        paths,
        decisions,
        expected_start=fingerprint(selection.read_state(paths.canonical_db)),
        expected_old=carry.verified_generation(paths),
        approval_reference=APPROVED["approval_reference"],
        applied_at="2026-11-13T20:00:00Z",
    )


def fixture_environment(
    tmp_path, monkeypatch, *, unapproved=False, wrong_provenance=False
):
    def prepare(fixture):
        scope_fixtures.configure("multi")(fixture)
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            db.execute(
                "INSERT INTO ticker_alias VALUES(990,11,'AAAB','SHARADAR',NULL,NULL,'existing companion')"
            )
            if unapproved:
                db.execute(
                    "INSERT INTO security VALUES(21,2,'BBBC','NASDAQ',1,NULL,NULL,'fixture','fixture')"
                )
        # Accepted OLD companion observations have no provider ID. Keep them;
        # their later source dates must not replace the chosen company source.
        histories = {
            d: [
                {
                    **fixtures.fixtures.native._source_row(
                        "AAAB", d, 2025, q, revenue_delta=999
                    ),
                    "date": "2026-08-16",
                    "lastupdated": "2026-08-16",
                }
                for q in range(1, 5)
            ]
            for d in ("ARQ", "MRQ")
        }
        trusted = {
            d: trusted_history(v, ticker="AAAB", dimension=d)
            for d, v in histories.items()
        }
        fixtures.fixtures.native.replace_provider_histories(
            fixture.paths.provider_db,
            {"AAAB": trusted},
            {"AAAB": dict(company_id=1, security_id=11, provider_security_id=None)},
            applied_at=fixtures.fixtures.native.NOW,
        )
        fixture.client.histories["AAAB"] = histories
        if wrong_provenance:
            with sqlite3.connect(fixture.paths.provider_db) as p:
                oid = p.execute(
                    "SELECT observation_id FROM provider_observation WHERE security_id=11 LIMIT 1"
                ).fetchone()[0]
            with sqlite3.connect(fixture.paths.canonical_db) as c:
                c.execute(
                    "UPDATE v4_field_provenance SET provider_observation_id=? WHERE quarter_id IN (SELECT quarter_id FROM v4_quarter WHERE company_id=1)",
                    (oid,),
                )

    workflow, native, histories, calls = fixtures.setup(
        tmp_path, monkeypatch, prepare_identity=prepare
    )
    decisions = [
        dict(
            company_id=1,
            security_id=10,
            ticker="AAA",
            provider_security_id="100",
            companion_security_ids=[11],
        )
    ]
    return workflow, native, histories, calls, decisions


def candidate_copy(workflow, decisions, lane):
    old = workflow.env.paths()
    receipt = plan(old, decisions)
    roles = {r: lane / (r + ".db") for r in ("provider", "canonical", "analysis")}
    for r, p in roles.items():
        online_backup(old.as_dict()[r], p)
    paths = BatchAddTickerPaths(
        roles["provider"],
        roles["canonical"],
        roles["analysis"],
        old.market_db,
        old.taxonomy_db,
    )
    installed = selection.install_disposable_candidate(paths, receipt)
    return paths, receipt, installed


def publish_selection_fixture(workflow, decisions, lane, *, crash=False):
    """Use the native generation journal, full V2 validation and OLD recovery."""
    old = workflow.env.paths()
    current = resolve_active_generation(workflow.env.project)
    paths, receipt, installed = candidate_copy(workflow, decisions, lane)
    analysis = fixtures.fixtures.native.run_full_v2_downstream(
        paths.as_dict(),
        output=lane / "analysis-build",
        as_of_date=fixtures.fixtures.native.AS_OF,
    )
    shutil.copyfile(analysis["candidate_analysis_db"], paths.analysis_db)
    publication._validate_analysis_generation(
        paths.analysis_db,
        analysis_result=analysis,
        as_of_date=fixtures.fixtures.native.AS_OF,
        sources=paths.as_dict(),
    )
    assert selection.verify_companion_retention(
        paths, paths.provider_db, paths.canonical_db
    )
    backups = publication._verified_backups(
        old, lane / "backups", immutable_generation=True
    )
    publication._validate_generation_backup_binding(current, backups)
    roles = publication._candidate_manifest(
        {r: paths.as_dict()[r] for r in ("provider", "canonical", "analysis")}, backups
    )
    prepared = prepare_generation_from_candidates(
        {r: paths.as_dict()[r] for r in roles},
        generation_id="selected",
        project_root=workflow.env.project,
        source=selection.CONTRACT,
    )
    j = core.journals.prepare_journal(
        path=workflow.env.journal,
        operation_type="FINANCIAL_UNIVERSE_RECONCILIATION",
        run_id=lane.name,
        preview_run_id=None,
        test_run_id=None,
        refresh_set_fingerprint=receipt["fingerprint"],
        old_source_watermark=None,
        new_source_watermark="",
        source_schema_fingerprint=selection.CONTRACT,
        roles=roles,
        publication_mode="GENERATION_POINTER",
        old_generation=current.evidence() | {"manifest": dict(current.manifest)},
        new_generation_id="selected",
        active_generation_manifest_path=active_manifest_path(workflow.env.project),
    )
    j = core.journals.update_journal(
        workflow.env.journal,
        j,
        new_generation_manifest=prepared["manifest"],
        new_generation_dir=prepared["generation_dir"],
    )
    j = core.journals.activate_prepared_generation(
        j, new_manifest=prepared["manifest"], journal_path=workflow.env.journal
    )
    if crash:
        recovered = core.journals.recover_if_required(workflow.env.journal)
        assert recovered["status"] == "RECOVERED"
        assert (
            resolve_active_generation(workflow.env.project).generation_id
            == current.generation_id
        )
        for r in roles:
            assert core.sha256_file(
                workflow.env.paths().as_dict()[r]
            ) == core.sha256_file(old.as_dict()[r])
        return receipt, installed
    active = workflow.env.paths()
    assert scope.InstalledUniverse(active).binding == installed["universe"]
    publication._validate_analysis_generation(
        active.analysis_db,
        analysis_result=analysis,
        as_of_date=fixtures.fixtures.native.AS_OF,
        sources=active.as_dict(),
    )
    assert fixtures.fixtures.native._semantic_fingerprint(
        active.provider_db
    ) == fixtures.fixtures.native._semantic_fingerprint(old.provider_db)
    core.journals.update_journal(
        workflow.env.journal, j, state="COMPLETED", postflight_state="PASSED"
    )
    return receipt, installed


def test_selected_rep_native_fetch_validate_build_publication(tmp_path, monkeypatch):
    workflow, native, histories, calls, decisions = fixture_environment(
        tmp_path, monkeypatch
    )
    old = workflow.env.paths()
    with sqlite3.connect(old.canonical_db) as db:
        old_members = db.execute(
            "SELECT * FROM fundamentals_operational_universe_member"
        ).fetchall()
    receipt, installed = publish_selection_fixture(
        workflow, decisions, workflow.env.root / "selection"
    )
    selected = workflow.env.paths()
    universe = scope.InstalledUniverse(selected)
    assert universe.resolve("AAA")["status"] == "ELIGIBLE"
    assert universe.resolve("AAAB")["reason"] == "FINANCIAL_COMPANION_RETENTION_ONLY"
    assert universe.resolve("NEW")["reason"] == "OUTSIDE_INSTALLED_UNIVERSE"
    with sqlite3.connect(selected.canonical_db) as db:
        assert (
            db.execute(
                "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=?",
                (receipt["starting_universe"]["universe_version_id"],),
            ).fetchall()
            == old_members
        )
        assert (
            db.execute(
                "SELECT count(*) FROM provider_security_identity WHERE security_id=11"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM ticker_alias WHERE security_id=11 AND ticker='AAAB'"
            ).fetchone()[0]
            == 1
        )
    before = selection.verify_companion_retention(
        selected, selected.provider_db, selected.canonical_db
    )
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    assert ("AAAB", "ARQ") not in calls and ("AAAB", "MRQ") not in calls
    assert calls.count(("AAA", "ARQ")) == calls.count(("AAA", "MRQ")) == 1
    build = core._read(workflow.env.runs / result["validation_id"] / "build.json")
    assert build["analysis_result"]["invocation_counts"]["full_v2_rebuild"] == 1
    assert build["financial_companion_retention"] == before
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    active = workflow.env.paths()
    assert (
        selection.verify_companion_retention(
            selected, active.provider_db, active.canonical_db
        )
        == before
    )
    with sqlite3.connect(active.canonical_db) as c, sqlite3.connect(
        active.provider_db
    ) as p:
        for (oid,) in c.execute(
            "SELECT DISTINCT provider_observation_id FROM v4_field_provenance fp JOIN v4_quarter q USING(quarter_id) WHERE q.company_id=1"
        ):
            assert (
                p.execute(
                    "SELECT security_id FROM provider_observation WHERE observation_id=?",
                    (oid,),
                ).fetchone()[0]
                == 10
            )
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )


def test_native_selection_generation_crash_restores_original_authority(
    tmp_path, monkeypatch
):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    before = selection.read_state(workflow.env.paths().canonical_db)
    publish_selection_fixture(
        workflow, decisions, workflow.env.root / "selection", crash=True
    )
    assert selection.read_state(workflow.env.paths().canonical_db) == before


@pytest.mark.parametrize(
    "defect", ["provider", "security", "companion", "provenance", "start", "old"]
)
def test_wrong_selection_or_authority_fails_closed(tmp_path, monkeypatch, defect):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    args = dict(
        expected_start=fingerprint(selection.read_state(paths.canonical_db)),
        expected_old=carry.verified_generation(paths),
        approval_reference="explicit fixture decision",
        applied_at="2026-11-13T20:00:00Z",
    )
    if defect == "provider":
        decisions[0]["provider_security_id"] = "wrong"
    if defect == "security":
        decisions[0]["security_id"] = 11
    if defect == "companion":
        decisions[0]["companion_security_ids"] = []
    if defect == "provenance":
        # Alter the claimed tuple, not an immutable accepted generation.
        decisions[0]["ticker"] = "AAAB"
    if defect == "start":
        args["expected_start"] = "wrong"
    if defect == "old":
        args["expected_old"] = {}
    with pytest.raises(ValueError):
        selection.prepare_reconciliation(paths, decisions, **args)


@pytest.mark.parametrize("defect", ["installed", "mapping", "code", "receipt"])
def test_candidate_install_rejects_drift_and_preserves_old_version(
    tmp_path, monkeypatch, defect
):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    old = workflow.env.paths()
    receipt = plan(old, decisions)
    canonical = tmp_path / "copy.db"
    online_backup(old.canonical_db, canonical)
    paths = BatchAddTickerPaths(
        old.provider_db, canonical, old.analysis_db, old.market_db, old.taxonomy_db
    )
    if defect in ("installed", "mapping"):
        with sqlite3.connect(canonical) as db:
            db.execute(
                "UPDATE fundamentals_operational_universe_member SET reason='drift'"
                if defect == "installed"
                else "UPDATE provider_security_identity SET provider_security_id='wrong' WHERE security_id=10"
            )
    if defect == "code":
        receipt["code_binding"] = {}
        receipt["fingerprint"] = fingerprint(
            {k: v for k, v in receipt.items() if k != "fingerprint"}
        )
    if defect == "receipt":
        receipt["decisions"] = []
    before = core.sha256_file(canonical)
    with pytest.raises(ValueError):
        selection.install_disposable_candidate(paths, receipt)
    assert core.sha256_file(canonical) == before


def test_unapproved_multi_remains_blocked_and_companion_obligations_bound(
    tmp_path, monkeypatch
):
    workflow, _, _, _, decisions = fixture_environment(
        tmp_path, monkeypatch, unapproved=True
    )
    paths, _, _ = candidate_copy(workflow, decisions, workflow.env.root / "selection")
    universe = scope.InstalledUniverse(paths)
    assert universe.resolve("BBB")["status"] == "AMBIGUOUS"
    assert universe.resolve("BBBC")["status"] == "AMBIGUOUS"
    result = universe.plan(
        financial_reviews=["AAAB"],
        accounting_queue=["AAAB"],
        accounting_installed=["AAAB"],
    )
    assert result["evaluation_tickers"] == ["AAA"]
    assert all(
        x["ticker"] == "AAAB" and x["reevaluate_representative"] == "AAA"
        for x in result["scope_exclusions"]
    )
    assert not universe.plan(discovered=["AAAB"])["evaluation_tickers"]
    with pytest.raises(scope.RefreshUniverseError):
        universe.require_tickers(["AAAB"])


def test_companion_provider_loss_or_fabricated_mapping_fails(tmp_path, monkeypatch):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    paths, _, _ = candidate_copy(workflow, decisions, workflow.env.root / "selection")
    provider = tmp_path / "damaged.db"
    online_backup(paths.provider_db, provider)
    with sqlite3.connect(provider) as db:
        db.execute(
            "DELETE FROM sharadar_fundamental_observation WHERE observation_id IN (SELECT observation_id FROM provider_observation WHERE security_id=11)"
        )
    with pytest.raises(ValueError, match="COMPANION_OLD_PROVIDER_CHANGED"):
        selection.verify_companion_retention(paths, provider, paths.canonical_db)


def test_candidate_never_writes_an_accepted_generation(tmp_path, monkeypatch):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    receipt = plan(paths, decisions)
    before = core.sha256_file(paths.canonical_db)
    with pytest.raises(ValueError, match="DISPOSABLE_INACTIVE_COPY_REQUIRED"):
        selection.install_disposable_candidate(paths, receipt)
    assert core.sha256_file(paths.canonical_db) == before


def test_all_twelve_real_approved_tuples_bind_without_changing_companions(
    tmp_path, monkeypatch
):
    # Actual approved identity tuples; authored economic data only. The separate
    # read-only current-production rehearsal checks these against real provenance.
    companions = {
        442: ("CENTA", "114230"),
        627: ("KRSA", None),
        886: ("FOX", "111122"),
        912: ("FWONK", "119287"),
        969: ("GOOG", "119496"),
        1272: ("LBTYK", "119285"),
        1296: ("LILAK", "114228"),
        1307: ("LLYVK", "640300"),
        1407: ("METCB", "640161"),
        1600: ("NWS", "119317"),
        2243: ("UA", "119495"),
        2441: ("Z", "119315"),
    }

    def prepare(fixture):
        histories, identities = {}, {}
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            alias_id = 1000
            for choice in APPROVED["decisions"]:
                cid, sid, ticker = (
                    choice["company_id"],
                    choice["security_id"],
                    choice["ticker"],
                )
                companion = choice["companion_security_ids"][0]
                cticker, cpid = companions[cid]
                db.execute(
                    "INSERT INTO company VALUES(?,?,?,'ACTIVE','fixture','fixture')",
                    (cid, "AUTHORED_ECONOMICS:" + str(cid), ticker),
                )
                for sec, name, pid in (
                    (sid, ticker, choice["provider_security_id"]),
                    (companion, cticker, cpid),
                ):
                    db.execute(
                        "INSERT INTO security VALUES(?,?,?,'NASDAQ',1,NULL,NULL,'fixture','fixture')",
                        (sec, cid, name),
                    )
                    db.execute(
                        "INSERT INTO ticker_alias VALUES(?,?,?,'SHARADAR',NULL,NULL,'explicit real-ID fixture')",
                        (alias_id, sec, name),
                    )
                    alias_id += 1
                    if pid is not None:
                        db.execute(
                            "INSERT INTO provider_security_identity VALUES('SHARADAR',?,?,?,'explicit approved-ID fixture','fixture')",
                            (pid, sec, name),
                        )
                histories[ticker] = {
                    d: trusted_history(
                        [
                            fixtures.fixtures.native._source_row(ticker, d, 2025, q)
                            for q in range(1, 5)
                        ],
                        ticker=ticker,
                        dimension=d,
                    )
                    for d in ("ARQ", "MRQ")
                }
                identities[ticker] = dict(
                    company_id=cid,
                    security_id=sid,
                    provider_security_id=choice["provider_security_id"],
                )
        fixtures.fixtures.native.replace_provider_histories(
            fixture.paths.provider_db,
            histories,
            identities,
            applied_at=fixtures.fixtures.native.NOW,
        )
        fixtures.fixtures.native.fresh_rebuild_canonical(
            fixture.paths.provider_db,
            fixture.paths.canonical_db,
            applied_at=fixtures.fixtures.native.NOW,
        )
        analysis = fixtures.fixtures.native.run_full_v2_downstream(
            fixture.paths.as_dict(),
            output=fixture.root / "twelve-old-analysis",
            as_of_date=fixtures.fixtures.native.AS_OF,
        )
        shutil.copyfile(analysis["candidate_analysis_db"], fixture.paths.analysis_db)

    workflow, _, _, _ = fixtures.setup(tmp_path, monkeypatch, prepare_identity=prepare)
    old = workflow.env.paths()
    before = selection.read_state(old.canonical_db)
    paths, receipt, installed = candidate_copy(
        workflow, APPROVED["decisions"], workflow.env.root / "selection"
    )
    universe = scope.InstalledUniverse(paths)
    assert len(universe.financial_selections) == 12
    assert (
        universe.binding["financial_selection_fingerprint"]
        == installed["universe"]["financial_selection_fingerprint"]
    )
    after = selection.read_state(paths.canonical_db)
    for key in ("securities", "mappings", "physical_aliases"):
        assert before[key] == after[key]
    for choice in APPROVED["decisions"]:
        resolved = universe.resolve(choice["ticker"])
        assert resolved["status"] == "ELIGIBLE"
        assert {
            k: resolved["identity"][k]
            for k in ("company_id", "security_id", "provider_security_id")
        } == {
            k: choice[k] for k in ("company_id", "security_id", "provider_security_id")
        }
        companion = companions[choice["company_id"]][0]
        assert (
            universe.resolve(companion)["reason"]
            == "FINANCIAL_COMPANION_RETENTION_ONLY"
        )
    with sqlite3.connect(paths.canonical_db) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM provider_security_identity WHERE security_id=2558"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT security_id FROM fundamentals_operational_universe_member WHERE universe_version_id=? AND company_id=627",
                (receipt["identity"]["universe_version_id"],),
            ).fetchone()[0]
            == 628
        )
    assert fixtures.fixtures.native._semantic_fingerprint(
        paths.provider_db
    ) == fixtures.fixtures.native._semantic_fingerprint(old.provider_db)
    assert fixtures.fixtures.native._semantic_fingerprint(
        paths.analysis_db
    ) == fixtures.fixtures.native._semantic_fingerprint(old.analysis_db)


def test_companion_obligation_reevaluates_rep_without_consuming_review(
    tmp_path, monkeypatch
):
    workflow, _, _, calls, decisions = fixture_environment(tmp_path, monkeypatch)
    publish_selection_fixture(workflow, decisions, workflow.env.root / "selection")
    queue = core.reviews.RefreshReviewQueue(workflow.env.queue)
    queue.upsert_local(
        dict(
            ticker="AAAB",
            review_type="SOURCE_HISTORY_REVIEW_REQUIRED",
            reason_codes=["companion-specific pending evidence"],
            source_evidence_fingerprint="companion-only",
            affected_source_keys=[],
            fiscal_identities=[],
        ),
        run_id="fixture",
        published_binding=None,
    )
    before = queue.get("AAAB")
    opener = workflow.client._opener

    def transport(request, timeout):
        response = opener(request, timeout)
        if "/schema/" not in request.full_url and "ticker=" not in request.full_url:
            rows = [r for r in json.loads(response.read()) if r["ticker"] != "AAA"]
            return fixtures.fixtures.Response(json.dumps(rows).encode())
        return response

    monkeypatch.setattr(workflow.client, "_opener", transport)
    result = workflow.start(stop_after="fetch", ownership_intent=False)
    assert result["outcome"] == "FETCH_SEALED", result
    discovery = core._read(workflow.env.directory() / "discovery.json")
    assert (
        "AAA" in discovery["evaluation_tickers"]
        and "AAA" not in discovery["changed_tickers"]
    )
    assert queue.get("AAAB") == before
    assert ("AAAB", "ARQ") not in calls and ("AAA", "ARQ") in calls
    assert (
        discovery["universe_binding"]["financial_selection_fingerprint"]
        == scope.InstalledUniverse(workflow.env.paths()).binding[
            "financial_selection_fingerprint"
        ]
    )


def test_companion_loss_during_postflight_rolls_back_exact_selected_old(
    tmp_path, monkeypatch
):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    publish_selection_fixture(workflow, decisions, workflow.env.root / "selection")
    before = {
        r: core.sha256_file(workflow.env.paths().as_dict()[r])
        for r in ("provider", "canonical", "analysis")
    }
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    original = selection.verify_companion_retention

    def damaged(old, provider, canonical):
        assert (
            resolve_active_generation(workflow.env.project).generation_id != "selected"
        )
        with sqlite3.connect(provider) as db:
            db.execute(
                "DELETE FROM sharadar_fundamental_observation WHERE observation_id IN (SELECT observation_id FROM provider_observation WHERE security_id=11)"
            )
        return original(old, provider, canonical)

    monkeypatch.setattr(selection, "verify_companion_retention", damaged)
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "ROLLED_BACK", result
    assert (
        "FINANCIAL_COMPANION_OLD_PROVIDER_CHANGED"
        in result["publication_outcome"]["error"]
    )
    assert resolve_active_generation(workflow.env.project).generation_id == "selected"
    assert {
        r: core.sha256_file(workflow.env.paths().as_dict()[r]) for r in before
    } == before


def test_stale_financial_selection_cannot_activate_snapshot_candidate(
    tmp_path, monkeypatch
):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    publish_selection_fixture(workflow, decisions, workflow.env.root / "selection")
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    # Fault injection affects this disposable accepted generation only.
    with sqlite3.connect(workflow.env.paths().canonical_db) as db:
        db.execute(
            "UPDATE fundamentals_operational_universe_member SET reason='unauthorized drift' WHERE source=?",
            (selection.CONTRACT,),
        )
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "FAILED", result
    assert resolve_active_generation(workflow.env.project).generation_id == "selected"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "traversal"])
def test_installer_refuses_disposable_path_aliases(tmp_path, monkeypatch, kind):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    old = workflow.env.paths()
    receipt = plan(old, decisions)
    target = workflow.env.root / "alias.db"
    if kind == "symlink":
        target.symlink_to(old.canonical_db)
    elif kind == "hardlink":
        target.hardlink_to(old.canonical_db)
    else:
        online_backup(old.canonical_db, target)
        (workflow.env.root / "other").mkdir()
        target = workflow.env.root / "other" / ".." / "alias.db"
    paths = BatchAddTickerPaths(
        old.provider_db, target, old.analysis_db, old.market_db, old.taxonomy_db
    )
    before = core.sha256_file(old.canonical_db)
    with pytest.raises(ValueError, match="DISPOSABLE_INACTIVE_COPY_REQUIRED"):
        selection.install_disposable_candidate(paths, receipt)
    assert core.sha256_file(old.canonical_db) == before


def test_candidate_transaction_rolls_back_if_final_selection_validation_fails(
    tmp_path, monkeypatch
):
    workflow, _, _, _, decisions = fixture_environment(tmp_path, monkeypatch)
    old = workflow.env.paths()
    receipt = plan(old, decisions)
    canonical = workflow.env.root / "copy.db"
    online_backup(old.canonical_db, canonical)
    paths = BatchAddTickerPaths(
        old.provider_db, canonical, old.analysis_db, old.market_db, old.taxonomy_db
    )
    # Fault injection reaches final native validation inside BEGIN IMMEDIATE.
    receipt["aliases"] = [a for a in receipt["aliases"] if a["security_id"] != 11]
    receipt["fingerprint"] = fingerprint(
        {k: v for k, v in receipt.items() if k != "fingerprint"}
    )
    before = core.sha256_file(canonical)
    with pytest.raises(ValueError, match="FINANCIAL_SELECTION_AUTHORITY_INVALID"):
        selection.install_disposable_candidate(paths, receipt)
    assert core.sha256_file(canonical) == before
    assert selection.read_state(canonical) == selection.read_state(old.canonical_db)


def test_operator_selection_cannot_override_cross_class_canonical_provenance(
    tmp_path, monkeypatch
):
    workflow, _, _, _, decisions = fixture_environment(
        tmp_path, monkeypatch, wrong_provenance=True
    )
    with pytest.raises(ValueError, match="CANONICAL_OWNER_MISMATCH"):
        plan(workflow.env.paths(), decisions)
