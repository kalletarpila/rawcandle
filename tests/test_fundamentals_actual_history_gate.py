"""Actual OLD analysis governs retention; empty history needs no importer."""

from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import refresh_universe as scope
from rawcandle.fundamentals.admin import refresh_update as core
from rawcandle.fundamentals.admin import review_locality as locality
from rawcandle.fundamentals.phase13b_foundation import online_backup
from tests import test_fundamentals_snapshot_integration as fixtures
from tests import test_fundamentals_refresh_universe as scope_fixtures


def inactive_environment(tmp_path, monkeypatch, *, accepted_history):
    def finish(fixture):
        if not accepted_history:
            # Build a coherent accepted OLD with inactive financial history and
            # no historical model endpoints, matching the actual production case.
            fixtures.fixtures.native.fresh_rebuild_canonical(
                fixture.paths.provider_db,
                fixture.paths.canonical_db,
                applied_at=fixtures.fixtures.native.NOW,
            )
            result = fixtures.fixtures.native.run_full_v2_downstream(
                fixture.paths.as_dict(),
                output=fixture.root / "inactive-old-analysis",
                as_of_date=fixtures.fixtures.native.AS_OF,
            )
            shutil.copyfile(result["candidate_analysis_db"], fixture.paths.analysis_db)

    return fixtures.setup(
        tmp_path,
        monkeypatch,
        prepare_identity=scope_fixtures.configure("historical"),
        configure_universe=finish,
    )


def financial_bytes(workflow):
    return {
        r: core.sha256_file(p)
        for r, p in workflow.env.paths().as_dict().items()
        if r in ("provider", "canonical", "analysis")
    }


def test_empty_inactive_history_allows_native_build_and_publication(
    tmp_path, monkeypatch
):
    workflow, _, _, calls = inactive_environment(
        tmp_path, monkeypatch, accepted_history=False
    )
    paths = workflow.env.paths()
    identity = scope_fixtures.old_identity(paths, "BBB")
    old = locality.authority(paths.provider_db, paths.canonical_db, "BBB", identity)
    before = scope.analysis_history(paths.analysis_db, paths.canonical_db, {2})
    assert all(not keys for keys in before.values())
    assert (
        scope.require_buildable_analysis_history(paths, [])["status"]
        == "NO_AT_RISK_ACCEPTED_HISTORY"
    )
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    assert ("BBB", "ARQ") not in calls and ("BBB", "MRQ") not in calls
    build = core._read(workflow.env.runs / result["validation_id"] / "build.json")
    assert build["old_analysis_preflight"]["checked_companies"] == [2]
    assert build["analysis_result"]["invocation_counts"]["full_v2_rebuild"] == 1
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    current = workflow.env.paths()
    assert (
        locality.authority(current.provider_db, current.canonical_db, "BBB", identity)
        == old
    )
    assert (
        scope.analysis_history(current.analysis_db, current.canonical_db, {2}) == before
    )
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )


def test_real_inactive_history_stops_even_without_retained_plan_entries(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = inactive_environment(
        tmp_path, monkeypatch, accepted_history=True
    )
    before = financial_bytes(workflow)
    with pytest.raises(
        scope.RefreshUniverseError, match="RETENTION_UNSUPPORTED:2:score_result"
    ):
        scope.require_buildable_analysis_history(workflow.env.paths(), [])
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "FAILED", result
    assert "REFRESH_OLD_ANALYSIS_RETENTION_UNSUPPORTED" in result["message"]
    assert not (workflow.env.runs / result["validation_id"] / "candidate").exists()
    assert financial_bytes(workflow) == before


def test_old_analysis_owner_missing_from_canonical_cannot_silently_disappear(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = fixtures.setup(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    # An inconsistent accepted-history owner must be surfaced, not filtered out
    # merely because canonical-quarter discovery does not enumerate it.
    with sqlite3.connect(paths.analysis_db) as db:
        db.execute("UPDATE score_result SET company_id=999 WHERE company_id=2")
    with pytest.raises(
        scope.RefreshUniverseError, match="RETENTION_UNSUPPORTED:999:score_result"
    ):
        scope.require_buildable_analysis_history(paths, [])


def test_economic_quarter_key_rejects_cross_company_physical_reference(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = fixtures.setup(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    candidate = tmp_path / "wrong-quarter.db"
    online_backup(paths.analysis_db, candidate)
    with sqlite3.connect(paths.canonical_db) as db:
        other = db.execute(
            "SELECT quarter_id FROM v4_quarter WHERE company_id=2 LIMIT 1"
        ).fetchone()[0]
    with sqlite3.connect(candidate) as db:
        result = db.execute(
            "SELECT score_result_id FROM score_result WHERE company_id=1 LIMIT 1"
        ).fetchone()[0]
        db.execute(
            "UPDATE score_result SET quarter_id=? WHERE score_result_id=?",
            (other, result),
        )
    with pytest.raises(scope.RefreshUniverseError, match="QUARTER_UNBOUND"):
        scope.analysis_history(candidate, paths.canonical_db, {1, 2})


def test_supported_retention_compares_economic_keys_at_build_and_postflight(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = scope_fixtures.environment(tmp_path, monkeypatch, "outside")
    paths = workflow.env.paths()
    expected = scope.analysis_history(paths.analysis_db, paths.canonical_db, {2})
    events = []
    original = scope.verify_analysis_retention

    def checked(old, canonical, analysis, retained):
        events.append(
            core.resolve_active_generation(workflow.env.project).generation_id
        )
        return original(old, canonical, analysis, retained)

    monkeypatch.setattr(scope, "verify_analysis_retention", checked)
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    assert events == ["old"]
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    assert len(events) == 2 and events[1] != "old"
    current = workflow.env.paths()
    assert (
        scope.analysis_history(current.analysis_db, current.canonical_db, {2})
        == expected
    )


def test_postflight_detects_actual_history_loss_and_rolls_back(tmp_path, monkeypatch):
    workflow, _, _, _ = scope_fixtures.environment(tmp_path, monkeypatch, "outside")
    before = financial_bytes(workflow)
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    original = scope.verify_analysis_retention

    def damaged(old, canonical, analysis, retained):
        assert (
            core.resolve_active_generation(workflow.env.project).generation_id != "old"
        )
        # Fault after native role/postflight verification, before final commit.
        # The historical comparison itself must detect actual endpoint loss.
        with sqlite3.connect(analysis) as db:
            db.execute("DELETE FROM score_result WHERE company_id=2")
        return original(old, canonical, analysis, retained)

    monkeypatch.setattr(scope, "verify_analysis_retention", damaged)
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "ROLLED_BACK", result
    assert (
        "REFRESH_OLD_ANALYSIS_HISTORY_LOST:score_result"
        in result["publication_outcome"]["error"]
    )
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"
    assert financial_bytes(workflow) == before
