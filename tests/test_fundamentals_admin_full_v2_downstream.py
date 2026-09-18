import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import batch_add_tickers, full_v2_downstream, sector_industry, taxonomy_v2_sync
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths, CopyLane
from rawcandle.cli.run_fundamentals_admin_taxonomy import build_parser


def _paths(root: Path) -> BatchAddTickerPaths:
    return BatchAddTickerPaths(*(root / f"{role}.db" for role in ("provider", "canonical", "analysis", "market", "taxonomy")))


def test_shared_downstream_calls_b1_once_with_only_authoritative_sources(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    calls = []

    def rebuild(target, sources, *, as_of_date, output, inject_failure_at=None):
        calls.append((target, sources, as_of_date, output))
        return {
            "status": "READY", "package": {"outcome": "APPLIED"},
            "validation": {"rp_snapshot_id": "rp-v2"}, "rv": {"outcome": "APPLIED"},
            "fingerprints": {"package": "v2"},
            "taxonomy_dependency": {"domain": "dc_ecosystem", "version": "active", "semantic_fingerprint": "hash"},
        }

    monkeypatch.setattr(full_v2_downstream, "rebuild_v2_analysis", rebuild)
    result = full_v2_downstream.run_full_v2_downstream(paths.as_dict(), output=tmp_path / "output", as_of_date="2026-09-18")
    assert len(calls) == 1
    assert set(calls[0][1]) == {"provider", "canonical", "market", "taxonomy"}
    assert paths.analysis_db not in calls[0][1].values()
    assert result["active_taxonomy"] == {"domain": "dc_ecosystem", "version": "active", "semantic_fingerprint": "hash"}
    assert result["invocation_counts"]["full_v2_rebuild"] == 1


def test_shared_downstream_rejects_production_source(tmp_path):
    paths = _paths(tmp_path).as_dict()
    paths["taxonomy"] = full_v2_downstream.PRODUCTION["taxonomy"]
    with pytest.raises(PermissionError, match="ADMIN_FULL_V2_COPY_SOURCE_REQUIRED:taxonomy"):
        full_v2_downstream.run_full_v2_downstream(paths, output=tmp_path / "output", as_of_date="2026-09-18")


def test_shared_downstream_rejects_production_data_output(tmp_path):
    with pytest.raises(PermissionError, match="OUTPUT_MUST_BE_DISPOSABLE"):
        full_v2_downstream.run_full_v2_downstream(
            _paths(tmp_path).as_dict(),
            output=full_v2_downstream.PRODUCTION["analysis"].parent / "uncreated_b2_candidate",
            as_of_date="2026-09-18",
        )


def test_add_tickers_and_sector_use_the_same_full_v2_entrypoint(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    calls = []
    smoke_dates = []

    def rebuild(source_paths, *, output, as_of_date):
        calls.append((source_paths, as_of_date))
        return {
            "action": "FULL_V2_REBUILD", "candidate_analysis_db": str(tmp_path / "candidate.db"),
            "invocation_counts": {"full_v2_rebuild": 1, "package": 1, "relative_position": 1, "relative_valuation": 1},
        }

    monkeypatch.setattr(batch_add_tickers, "run_full_v2_downstream", rebuild)
    monkeypatch.setattr(sector_industry, "run_full_v2_downstream", rebuild)
    monkeypatch.setattr(batch_add_tickers, "reconcile_canonical", lambda *args, **kwargs: {"canonical_rows": 0})
    monkeypatch.setattr(batch_add_tickers, "rebuild_ttm", lambda *args, **kwargs: {"rows": 0})
    monkeypatch.setattr(batch_add_tickers.structural_break, "apply_contract", lambda *args, **kwargs: {})
    monkeypatch.setattr(batch_add_tickers, "_structural_evidence", lambda *args, **kwargs: {})
    monkeypatch.setattr(batch_add_tickers, "_structural_package_fingerprint", lambda *args, **kwargs: "structural")

    def smoke(*args, **kwargs):
        smoke_dates.append(kwargs["report_date"])
        return {}

    monkeypatch.setattr(batch_add_tickers, "_snapshot_smoke_generic", smoke)
    monkeypatch.setattr(sector_industry, "_snapshot_smoke", smoke)

    add = batch_add_tickers._run_authoritative_downstream(
        paths, tmp_path / "add", accepted_tickers=("ABC",),
        applied_at="2026-09-18T00:00:00Z", as_of_date="2026-09-17",
    )
    sector = sector_industry._run_downstream(
        paths, tmp_path / "sector", changed_tickers=("ABC",),
        applied_at="2026-09-18T00:00:00Z", as_of_date="2026-09-17", progress=None,
    )
    assert len(calls) == 2
    assert all(date == "2026-09-17" for _, date in calls)
    assert smoke_dates == ["2026-09-17", "2026-09-17"]
    assert add["action"] == sector["action"] == "FULL_V2_REBUILD"


def test_taxonomy_admin_rejects_csv_inputs_before_reading_sources(tmp_path):
    with pytest.raises(ValueError, match="CSV_NOT_ACCEPTED"):
        taxonomy_v2_sync.run_preview(candidate_path=tmp_path / "candidate.csv")
    with pytest.raises(ValueError, match="CSV_NOT_ACCEPTED"):
        taxonomy_v2_sync.run_preview(candidate_version="next")


def test_taxonomy_preview_binds_active_database_identity(tmp_path, monkeypatch):
    identity = {"domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic"}
    monkeypatch.setattr(taxonomy_v2_sync, "_state", lambda paths: {"sources": {}, "analysis": {}, "active_taxonomy": identity})
    result = taxonomy_v2_sync.run_preview(run_root=tmp_path)
    assert result["mode"] == "ACTIVE_TAXONOMY_PREVIEW"
    payload = json.loads(Path(result["preview_payload_path"]).read_text(encoding="utf-8"))
    assert payload["source_state"]["active_taxonomy"] == identity
    assert payload["action"] == "FULL_V2_REBUILD"


def test_taxonomy_copy_apply_uses_full_v2_without_writing_taxonomy(tmp_path, monkeypatch):
    identity = {"domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic"}
    paths = _paths(tmp_path)
    monkeypatch.setattr(taxonomy_v2_sync, "_state", lambda _, **kwargs: {"sources": {}, "analysis": {}, "active_taxonomy": identity})
    preview = taxonomy_v2_sync.run_preview(source_paths=paths, run_root=tmp_path / "runs")
    calls = []

    def copy_lane(source, *, lane_dir, writer):
        lane_dir.mkdir(parents=True)
        return CopyLane(lane_dir, source, {})

    def rebuild(source_paths, *, output, as_of_date, inject_failure_at=None):
        calls.append((source_paths, as_of_date))
        return {"action": "FULL_V2_REBUILD", "active_taxonomy": identity, "candidate_analysis_db": str(output / "analysis_candidate.db"), "invocation_counts": {"full_v2_rebuild": 1}}

    monkeypatch.setattr(taxonomy_v2_sync, "create_copy_lane", copy_lane)
    monkeypatch.setattr(taxonomy_v2_sync, "run_full_v2_downstream", rebuild)
    monkeypatch.setattr(taxonomy_v2_sync, "cleanup_copy_lane", lambda _: {})
    result = taxonomy_v2_sync.run_apply(
        taxonomy_domain="dc_ecosystem", preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"], source_paths=paths,
        run_root=tmp_path / "runs", temp_root=tmp_path / "temp", confirm_apply=True,
    )
    assert result["outcome"] == "COMPLETED"
    assert calls[0][0]["taxonomy"] == paths.taxonomy_db
    assert result["downstream"]["active_taxonomy"] == identity


def test_taxonomy_rebuild_failure_has_durable_failed_report(tmp_path, monkeypatch):
    identity = {"domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic"}
    paths = _paths(tmp_path)
    monkeypatch.setattr(taxonomy_v2_sync, "_state", lambda _, **kwargs: {"sources": {}, "analysis": {}, "active_taxonomy": identity})
    preview = taxonomy_v2_sync.run_preview(source_paths=paths, run_root=tmp_path / "runs")

    def copy_lane(source, *, lane_dir, writer):
        lane_dir.mkdir(parents=True)
        return CopyLane(lane_dir, source, {})

    monkeypatch.setattr(taxonomy_v2_sync, "create_copy_lane", copy_lane)
    monkeypatch.setattr(taxonomy_v2_sync, "cleanup_copy_lane", lambda _: {})
    monkeypatch.setattr(taxonomy_v2_sync, "run_full_v2_downstream", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rebuild failed")))
    with pytest.raises(RuntimeError, match="rebuild failed"):
        taxonomy_v2_sync.run_apply(
            taxonomy_domain="dc_ecosystem", preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"], source_paths=paths,
            run_root=tmp_path / "runs", temp_root=tmp_path / "temp", confirm_apply=True,
        )
    failed = list((tmp_path / "runs").glob("*_active_copy/result.json"))
    assert len(failed) == 1
    assert json.loads(failed[0].read_text(encoding="utf-8"))["outcome"] == "FAILED"


def test_taxonomy_stale_preview_is_logged_before_copy(tmp_path, monkeypatch):
    state = {"sources": {}, "analysis": {}, "active_taxonomy": {"domain": "dc_ecosystem", "version": "v1", "semantic_fingerprint": "one"}}
    monkeypatch.setattr(taxonomy_v2_sync, "_state", lambda _, **kwargs: state)
    preview = taxonomy_v2_sync.run_preview(run_root=tmp_path / "runs")
    state = {"sources": {}, "analysis": {}, "active_taxonomy": {"domain": "dc_ecosystem", "version": "v2", "semantic_fingerprint": "two"}}
    monkeypatch.setattr(taxonomy_v2_sync, "create_copy_lane", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("copy was created")))
    with pytest.raises(RuntimeError, match="STALE_PREVIEW"):
        taxonomy_v2_sync.run_apply(
            taxonomy_domain="dc_ecosystem", preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"], run_root=tmp_path / "runs",
            confirm_apply=True,
        )
    failed = list((tmp_path / "runs").glob("*_active_copy/result.json"))
    assert len(failed) == 1
    result = json.loads(failed[0].read_text(encoding="utf-8"))
    assert result["outcome"] == "FAILED"
    assert result["downstream"]["write_boundary_crossed"] is False


@pytest.mark.parametrize("changed_role", ("provider", "canonical", "market", "analysis"))
def test_taxonomy_preview_detects_same_row_count_source_content_change(tmp_path, monkeypatch, changed_role):
    paths = _paths(tmp_path)
    for path in paths.as_dict().values():
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE state(value TEXT NOT NULL)")
            conn.execute("INSERT INTO state VALUES('old')")
    identity = {"domain": "dc_ecosystem", "version": "DC_V2", "semantic_fingerprint": "semantic"}
    monkeypatch.setattr(taxonomy_v2_sync, "load_active_dc_memberships", lambda *args: ({}, identity))
    monkeypatch.setattr(taxonomy_v2_sync, "database_fingerprint", lambda path: {"rows": 1})
    preview = taxonomy_v2_sync.run_preview(source_paths=paths, run_root=tmp_path / "runs")
    payload = json.loads(Path(preview["preview_payload_path"]).read_text(encoding="utf-8"))
    assert set(payload["source_state"]["content_sha256"]) == {"provider", "canonical", "market", "analysis"}
    with sqlite3.connect(paths.as_dict()[changed_role]) as conn:
        conn.execute("UPDATE state SET value='new'")
    monkeypatch.setattr(taxonomy_v2_sync, "create_copy_lane", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("copy was created")))
    with pytest.raises(RuntimeError, match="STALE_PREVIEW"):
        taxonomy_v2_sync.run_apply(
            taxonomy_domain="dc_ecosystem", preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"], source_paths=paths,
            run_root=tmp_path / "runs", confirm_apply=True,
        )


def test_taxonomy_production_update_fails_before_write():
    with pytest.raises(PermissionError, match="CONFIRMATION_REQUIRED"):
        taxonomy_v2_sync.run_production_apply(
            preview_payload_path=Path("missing.json"), preview_fingerprint="missing", test_run_id="missing",
        )


def test_fundamentals_taxonomy_cli_has_no_csv_candidate_option():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--candidate", "candidate.csv"])
