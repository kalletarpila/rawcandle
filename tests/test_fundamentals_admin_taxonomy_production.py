from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli import run_fundamentals_admin_taxonomy as taxonomy_cli
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.fundamentals.admin import taxonomy_production as prod
from rawcandle.fundamentals.admin.taxonomy import TaxonomyPaths


def _write_csv(path: Path, version: str, role: str = "CORE") -> Path:
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{version},AAA,Compute,Servers,{role},1,1.0,",
                f"{version},BBB,Power,UPS,CORE,1,1.0,",
                f"{version},AAOI,Networking,Optics / photonics / high-speed connectivity,CORE,1,1.0,authoritative",
                f"{version},EXTD,Power,UPS,EXTENDED,1,1.0,control extended row",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _create_db(tmp_path: Path, name: str = "analysis.db") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / name
    with sqlite3.connect(db_path) as conn:
        conn.executescript(Path("rawcandle/sqlite/migrations/019_create_ec_sidecar_schema.sql").read_text(encoding="utf-8"))
        conn.execute("CREATE TABLE IF NOT EXISTS fundamentals_result_dependency (consumer_family TEXT, consumer_object_type TEXT, consumer_object_id TEXT, dependency_id TEXT)")
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path,
        _write_csv(tmp_path / f"{name}.csv", "DC_TAXONOMY_FULL_V2_1"),
        "DC_TAXONOMY_FULL_V2_1",
        mark_active=True,
    )
    return db_path


def _paths(db_path: Path) -> TaxonomyPaths:
    return TaxonomyPaths(provider_db=db_path, canonical_db=db_path, analysis_db=db_path, market_db=db_path, taxonomy_db=db_path)


def test_protected_production_cli_requires_confirmation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def fail_apply(**kwargs):
        raise PermissionError("PHASE13G43_PRODUCTION_CONFIRMATION_REQUIRED")

    monkeypatch.setattr(taxonomy_cli, "run_protected_production_apply", fail_apply)
    code = taxonomy_cli.main(
        [
            "--taxonomy",
            "dc_ecosystem",
            "--production",
            "--apply",
            "--preview-payload",
            str(tmp_path / "payload.json"),
            "--preview-fingerprint",
            "abc",
            "--quiet-progress",
        ]
    )

    assert code == 2
    assert "PHASE13G43_PRODUCTION_CONFIRMATION_REQUIRED" in capsys.readouterr().out


def test_ec_taxonomy_production_mode_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    code = taxonomy_cli.main(["--taxonomy", "ec_taxonomy", "--production", "--quiet-progress"])

    assert code == 2
    assert "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY" in capsys.readouterr().out


def test_active_baseline_no_change_preview_has_zero_writes(tmp_path: Path) -> None:
    paths = _paths(_create_db(tmp_path))
    payload = prod.build_production_preview_payload(
        paths=paths,
        run_dir=tmp_path / "run",
        candidate_path=None,
        candidate_version=None,
        candidate_provenance=prod.ACTIVE_BASELINE_PROVENANCE,
    )
    preview = payload["taxonomy_preview"]

    assert preview["candidate"]["provenance"] == prod.ACTIVE_BASELINE_PROVENANCE
    assert preview["candidate"]["source_database_identity"]["aaoi_authoritative_role"] == "CORE"
    aaoi = [row for row in payload["candidate_rows"] if row["ticker"] == "AAOI"]
    assert aaoi == [
        {
            "is_primary": 1,
            "layer": "Networking",
            "notes": "authoritative",
            "report_group_status": "CORE",
            "role_weight": 1.0,
            "subindustry": "Optics / photonics / high-speed connectivity",
            "taxonomy_version": "DC_TAXONOMY_FULL_V2_1",
            "ticker": "AAOI",
        }
    ]
    assert preview["expected_result"] == "NO_CHANGE"
    assert preview["change_counts"]["semantic_changes"] == 0
    assert preview["change_counts"]["additions"] == 0
    assert preview["change_counts"]["removals"] == 0
    assert preview["change_counts"]["role_or_tier_changes"] == 0
    assert preview["change_counts"]["primary_changes"] == 0
    assert preview["change_counts"]["blockers"] == 0
    assert preview["expected_writable_database_set"] == []
    assert preview["role_matrix"]["role_matrix"]["production_writable_roles"] == []


def test_test_only_candidate_is_refused_for_production(tmp_path: Path) -> None:
    candidate = _write_csv(tmp_path / "phase13g42_test_only.csv", prod.TEST_ONLY_VERSION, role="EXTENDED")

    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G43_TEST_ONLY_CANDIDATE_REFUSED"):
        prod.guard_production_candidate(
            taxonomy_domain="dc_ecosystem",
            candidate_path=candidate,
            candidate_provenance="TEST_ONLY_NOT_FOR_PRODUCTION",
            candidate_version=prod.TEST_ONLY_VERSION,
        )


def test_saved_preview_validation_rejects_cross_domain_and_mutation(tmp_path: Path) -> None:
    payload = prod.build_production_preview_payload(
        paths=_paths(_create_db(tmp_path)),
        run_dir=tmp_path / "run",
        candidate_path=None,
        candidate_version=None,
        candidate_provenance=prod.ACTIVE_BASELINE_PROVENANCE,
    )
    payload["taxonomy_preview"]["expires_at_utc"] = "2099-01-01T00:00:00Z"
    good = payload["taxonomy_preview"]["preview_fingerprint"]

    prod._validate_saved_preview(payload, good)
    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G43_PREVIEW_FINGERPRINT_MISMATCH"):
        prod._validate_saved_preview(payload, "bad")
    payload["taxonomy_preview"]["taxonomy_domain"] = "ec_taxonomy"
    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G43_CROSS_DOMAIN_PREVIEW_REJECTED"):
        prod._validate_saved_preview(payload, good)


def test_active_version_filtering_excludes_stale_test_only_aaoi_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    paths = _paths(db_path)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path,
        _write_csv(tmp_path / "test_only.csv", prod.TEST_ONLY_VERSION, role="EXTENDED"),
        prod.TEST_ONLY_VERSION,
        mark_active=False,
    )

    payload = prod.build_production_preview_payload(
        paths=paths,
        run_dir=tmp_path / "run",
        candidate_path=None,
        candidate_version=None,
        candidate_provenance=prod.ACTIVE_BASELINE_PROVENANCE,
    )

    aaoi = [row for row in payload["candidate_rows"] if row["ticker"] == "AAOI"]
    assert {row["taxonomy_version"] for row in aaoi} == {"DC_TAXONOMY_FULL_V2_1"}
    assert {row["report_group_status"] for row in aaoi} == {"CORE"}
    reconciliation = prod.aaoi_source_reconciliation(paths, preview=payload)
    assert reconciliation["status"] == "OK"
    assert reconciliation["diagnosis"]["missing_active_version_filtering"] is False


def test_active_baseline_with_other_extended_rows_is_not_test_only(tmp_path: Path) -> None:
    payload = prod.build_production_preview_payload(
        paths=_paths(_create_db(tmp_path)),
        run_dir=tmp_path / "run",
        candidate_path=None,
        candidate_version=None,
        candidate_provenance=prod.ACTIVE_BASELINE_PROVENANCE,
    )

    assert any(row["report_group_status"] == "EXTENDED" for row in payload["candidate_rows"])
    prod._validate_saved_preview(payload, payload["taxonomy_preview"]["preview_fingerprint"])


def test_provenance_label_edit_cannot_promote_test_only_candidate(tmp_path: Path) -> None:
    candidate = _write_csv(tmp_path / "candidate.csv", "DC_TAXONOMY_FULL_V2_1", role="EXTENDED")
    version, rows, content_sha = prod.tax._rows_from_candidate(candidate, "DC_TAXONOMY_FULL_V2_1")
    payload = {
        "taxonomy_domain": "dc_ecosystem",
        "candidate_rows": prod.tax._semantic_payload(rows),
        "taxonomy_preview": {
            "taxonomy_domain": "dc_ecosystem",
            "preview_fingerprint": "preview",
            "expires_at_utc": "2099-01-01T00:00:00Z",
            "blockers": [],
            "expected_writable_database_set": [],
            "candidate": {
                "provenance": prod.ACTIVE_BASELINE_PROVENANCE,
                "generating_operation": "EXPORT_ACTIVE_PRODUCTION_BASELINE_NO_CHANGE",
                "path": str(candidate),
                "taxonomy_version": version,
                "content_sha256": content_sha,
                "source_database_identity": {
                    "active_version": "DC_TAXONOMY_FULL_V2_1",
                    "aaoi_authoritative_role": "CORE",
                },
                "candidate_fingerprint": prod._candidate_fingerprint(
                    provenance=prod.TEST_ONLY_PROVENANCE,
                    rows=rows,
                    content_sha256=content_sha,
                    source_database_identity={
                        "active_version": "DC_TAXONOMY_FULL_V2_1",
                        "aaoi_authoritative_role": "CORE",
                    },
                ),
            },
        },
    }

    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G431_CANDIDATE_PROVENANCE_FINGERPRINT_MISMATCH"):
        prod._validate_saved_preview(payload, "preview")


def test_dirty_worktree_guard_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    paths = _paths(_create_db(tmp_path))
    monkeypatch.setattr(prod, "validate_exact_production_paths", lambda _paths: {"ok": True})
    monkeypatch.setattr(prod, "reconcile_phase13g42_evidence", lambda _run: {"status": "VALIDATED"})
    monkeypatch.setattr(prod, "_is_clean_worktree", lambda: False)
    monkeypatch.setattr(prod, "_current_commit", lambda: "abc")
    monkeypatch.setattr(prod, "_commit_is_present", lambda _short: True)

    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G43_DIRTY_WORKTREE_REFUSED"):
        prod._preflight(paths, require_clean_worktree=True)


def test_production_path_alias_symlink_and_uri_are_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    expected = _paths(db_path)
    monkeypatch.setattr(prod.tax, "TaxonomyPaths", lambda: expected)
    symlink = tmp_path / "alias.db"
    symlink.symlink_to(db_path)

    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G43_PRODUCTION_(SYMLINK|ALIAS)_PATH_REFUSED"):
        prod.validate_exact_production_paths(_paths(symlink))
    with pytest.raises(prod.ProductionTaxonomyError, match="PHASE13G43_SQLITE_URI_PATH_REFUSED"):
        prod.validate_exact_production_paths(_paths(Path(f"file:{db_path}")))


def test_role_aware_writable_set_selects_only_taxonomy_and_analysis(tmp_path: Path) -> None:
    paths = _paths(_create_db(tmp_path))
    no_change = prod._role_matrix(paths, planned_nonzero_change=False)
    nonzero = prod._role_matrix(paths, planned_nonzero_change=True, write_boundary_crossed=True)

    assert no_change["role_matrix"]["production_writable_roles"] == []
    assert sorted(nonzero["role_matrix"]["production_writable_roles"]) == ["analysis", "taxonomy"]
    assert sorted(nonzero["role_matrix"]["production_readonly_roles"]) == ["canonical", "market", "provider"]
    writable_entries = [row for row in nonzero["roles"] if row["access_mode"] == "writable"]
    assert all(row["backup_required"] for row in writable_entries)
    assert all("post_write_quick_check" in row["postflight_checks"] for row in writable_entries)


def test_future_nonzero_simulation_backs_up_writable_only_and_runs_downstream(tmp_path: Path) -> None:
    dbs = {role: _create_db(tmp_path / role, f"{role}.db") for role in ("provider", "canonical", "analysis", "market", "taxonomy")}
    paths = TaxonomyPaths(**{f"{role}_db": path for role, path in dbs.items()})
    pauses: list[str] = []

    result = prod.simulate_future_nonzero_production_path(
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "tmp",
        scheduler_pause=lambda: pauses.append("pause") or {"initial_active": True, "paused": True},
        scheduler_restore=lambda state: {"restored": state["initial_active"]},
        downstream=lambda _paths: {"invocations": {"package": 1, "relative_position": 1, "relative_valuation": 1, "dependency_attachment": 1, "snapshot": 1}},
    )

    assert result["outcome"] == "COMPLETED"
    assert sorted(result["backup_manifest"]["roles"]) == ["analysis", "taxonomy"]
    assert result["read_only_roles_backed_up"] == []
    assert result["downstream"]["invocations"]["package"] == 1
    assert result["second_pass"]["outcome"] == "NO_CHANGE"
    assert pauses == ["pause"]


@pytest.mark.parametrize("failure_after", ["taxonomy", "dependency", "package_rp_rv"])
def test_future_nonzero_simulation_restores_after_post_write_failures(tmp_path: Path, failure_after: str) -> None:
    dbs = {role: _create_db(tmp_path / role, f"{role}.db") for role in ("provider", "canonical", "analysis", "market", "taxonomy")}
    paths = TaxonomyPaths(**{f"{role}_db": path for role, path in dbs.items()})

    result = prod.simulate_future_nonzero_production_path(
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "tmp",
        failure_after=failure_after,
        scheduler_pause=lambda: {"initial_active": True, "paused": True},
        scheduler_restore=lambda state: {"restored": state["initial_active"]},
    )

    assert result["outcome"] == "ROLLED_BACK"
    assert result["rollback"]["restored_complete_writable_set"] is True
    assert result["scheduler_after"]["restored"] is True


def test_report_and_progress_artifacts_are_redacted_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _create_db(tmp_path)
    paths = _paths(db_path)
    monkeypatch.setattr(prod, "_preflight", lambda _paths, require_clean_worktree: {"worktree_clean": True})
    result = prod.run_production_preview(
        source_paths=paths,
        run_root=tmp_path / "runs",
        candidate_provenance=prod.ACTIVE_BASELINE_PROVENANCE,
    )
    run_dir = Path(result["artifact_dir"])

    assert result["outcome"] == "NO_CHANGE"
    assert (run_dir / "progress_status.json").exists()
    assert (run_dir / "progress_events.jsonl").exists()
    assert (run_dir / "exit_code").read_text(encoding="utf-8").strip() == "0"
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Phase 13G.4.3 Protected Taxonomy Production" in report
    assert "SECRET" not in report.upper()
    assert json.loads((run_dir / "preview.json").read_text(encoding="utf-8"))["expected_result"] == "NO_CHANGE"
