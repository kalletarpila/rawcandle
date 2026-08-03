from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.datacenter_taxonomy_replacement import ensure_taxonomy_replacement_schema
from rawcandle.ec_taxonomy_full_rebuild_orchestrator import (
    KNOWN_DEPLOYMENT_AUDIT_COLUMNS,
    build_ec_taxonomy_rebuild_chunks,
    plan_ec_taxonomy_full_rebuild,
    run_ec_taxonomy_full_rebuild,
    validate_existing_backup,
)


def _write_taxonomy(path: Path, version: str = "DC_TAXONOMY_FULL_V2") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerow([version, "AAA", "Compute", "GPU", "CORE", 1, 1.0, ""])
    return path


def _write_watchlist(path: Path) -> Path:
    path.write_text("AAA\n", encoding="utf-8")
    return path


def _db(tmp_path: Path, *, active_v2: bool = False, source_hash: str | None = None) -> Path:
    db_path = tmp_path / "analysis.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY, ecosystem_code TEXT, ecosystem_name TEXT, status TEXT)")
        conn.execute(
            """
            CREATE TABLE ec_taxonomy_version (
                taxonomy_version_id INTEGER PRIMARY KEY,
                ecosystem_id INTEGER,
                taxonomy_version_code TEXT,
                source_hash TEXT,
                source_reference TEXT,
                status TEXT,
                is_active INTEGER,
                active_from TEXT,
                active_to TEXT
            )
            """
        )
        conn.execute("CREATE TABLE ec_pipeline_watermark (ecosystem_id INTEGER, pipeline_name TEXT, source_table TEXT, latest_signal_date TEXT, status TEXT, taxonomy_version_id INTEGER)")
        conn.execute("CREATE TABLE dc_pipeline_watermark (component_name TEXT, taxonomy_version TEXT, market TEXT, start_date TEXT, end_date TEXT, status TEXT)")
        conn.execute("CREATE TABLE ec_entity (entity_id INTEGER PRIMARY KEY, ecosystem_id INTEGER NOT NULL, entity_type TEXT NOT NULL, entity_code TEXT NOT NULL, ticker TEXT NULL, status TEXT)")
        conn.execute("CREATE TABLE ec_membership (membership_id INTEGER PRIMARY KEY, ecosystem_id INTEGER NOT NULL, taxonomy_version_id INTEGER NOT NULL, parent_entity_id INTEGER NOT NULL, child_entity_id INTEGER NOT NULL, membership_type TEXT)")
        conn.execute("CREATE TABLE ec_watchlist (watchlist_id INTEGER PRIMARY KEY, ecosystem_id INTEGER NOT NULL, watchlist_code TEXT NOT NULL)")
        conn.execute("CREATE TABLE ec_watchlist_member (watchlist_member_id INTEGER PRIMARY KEY, watchlist_id INTEGER NOT NULL, entity_id INTEGER NOT NULL)")
        for table in (
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
        ):
            conn.execute(f"CREATE TABLE {table} (ecosystem_id INTEGER, taxonomy_version_id INTEGER, signal_date TEXT)")
        for table, date_column in (
            ("dc_ticker_swing_signal_daily", "signal_date"),
            ("dc_group_swing_signal_daily", "signal_date"),
            ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
            ("dc_group_index_daily", "index_date"),
        ):
            conn.execute(f"CREATE TABLE {table} ({date_column} TEXT, taxonomy_version TEXT, ticker TEXT, group_name TEXT)")
        ensure_taxonomy_replacement_schema(conn)
        conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER', 'Datacenter', 'ACTIVE')")
        conn.execute("INSERT INTO ec_ecosystem VALUES (2, 'ENERGY', 'Energy', 'ACTIVE')")
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (1, 1, 'DC_TAXONOMY_FULL_V1', 'v1hash', 'v1.csv', 'ACTIVE', ?, '2025-01-01', NULL)", (0 if active_v2 else 1,))
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (2, 1, 'DC_TAXONOMY_FULL_V2', ?, 'v2.csv', ?, ?, NULL, NULL)", (source_hash or "v2hash", "ACTIVE" if active_v2 else "INACTIVE", 1 if active_v2 else 0))
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                taxonomy_change_id, ecosystem_code, previous_taxonomy_version,
                proposed_taxonomy_version, source_reference, source_sha256,
                change_summary, added_ticker_count, removed_ticker_count,
                membership_change_count, group_change_count, status,
                rebuild_required, rebuild_start_date, activation_status
            ) VALUES (7, 'DATACENTER', 'DC_TAXONOMY_FULL_V1',
                      'DC_TAXONOMY_FULL_V2', 'v2.csv', ?, '{}',
                      0, 0, 0, 0, 'REBUILD_IN_PROGRESS', 1,
                      '2025-08-01', 'NOT_ACTIVE')
            """,
            (source_hash or "v2hash",),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _paths(tmp_path: Path) -> dict[str, str]:
    repo_root = tmp_path
    temp_root = repo_root / "temp"
    backup_dir = temp_root / "backups"
    evidence_root = temp_root / "evidence"
    backup_dir.mkdir(parents=True)
    evidence_root.mkdir(parents=True)
    taxonomy = _write_taxonomy(tmp_path / "taxonomy.csv")
    watchlist = _write_watchlist(tmp_path / "watchlist.txt")
    import hashlib

    source_hash = hashlib.sha256(taxonomy.read_bytes()).hexdigest()
    db_path = _db(tmp_path, source_hash=source_hash)
    return {
        "repo_root": str(repo_root),
        "backup_dir": str(backup_dir),
        "evidence_root": str(evidence_root),
        "taxonomy": str(taxonomy),
        "watchlist": str(watchlist),
        "db": str(db_path),
    }


def _existing_backup(paths: dict[str, str], name: str = "existing.sqlite") -> Path:
    backup_path = Path(paths["backup_dir"]) / name
    shutil.copy2(paths["db"], backup_path)
    return backup_path


def _drop_backup_columns(backup_path: Path, table_name: str, columns: set[str]) -> None:
    conn = sqlite3.connect(backup_path)
    try:
        existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}
        for column_name in sorted(columns & existing):
            conn.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
        conn.commit()
    finally:
        conn.close()


def _validate_backup(paths: dict[str, str], backup_path: Path) -> dict[str, object]:
    return validate_existing_backup(
        existing_backup_path=str(backup_path),
        confirm_existing_backup_path=str(backup_path.resolve()),
        db_path=paths["db"],
        repo_root=paths["repo_root"],
        orchestrator_started_at_utc=datetime.now(timezone.utc),
    )


def _successful_backfill_calls() -> tuple[list[dict[str, object]], object]:
    calls: list[dict[str, object]] = []

    def fake_backfill_runner(**kwargs):
        calls.append(kwargs)
        return {
            "status": "BACKFILL_COMPLETED",
            "selected_dates": [{"date": kwargs["date_from"], "action": "TAXONOMY_REBUILD_REPLACE"}],
            "completed_dates": [kwargs["date_from"]],
            "skipped_dates": [],
            "per_date_results": [{"coverage_status": "OK", "parity_status": "OK", "total_mismatch_count": 0}],
            "total_mismatch_count": 0,
            "error": None,
        }

    return calls, fake_backfill_runner


def _patch_success_finalizers(monkeypatch) -> None:
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator._validate_whole_range", lambda **_: {"whole_range_validation_status": "OK", "coverage_status": "OK", "parity_status": "OK", "total_mismatch_count": 0, "blocking_errors": []})
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill", lambda **_: {"status": "OK", "watermark_advance_status": "OK", "watermark_rows_updated": 4})
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.apply_datacenter_taxonomy_rebuild_evidence", lambda **_: {"status_update": "READY_TO_ACTIVATE", "ready_to_activate": True})


def _plan_args(paths: dict[str, str], **overrides):
    args = {
        "db_path": paths["db"],
        "ecosystem_code": "DATACENTER",
        "taxonomy_version_code": "DC_TAXONOMY_FULL_V2",
        "taxonomy_csv_path": paths["taxonomy"],
        "watchlist_path": paths["watchlist"],
        "deployment_id": 7,
        "date_from": "2025-08-01",
        "date_to": "2026-07-31",
        "backup_dir": paths["backup_dir"],
        "evidence_output_root": paths["evidence_root"],
        "confirm_db": paths["db"],
        "confirm_ecosystem": "DATACENTER",
        "confirm_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "confirm_deployment_id": 7,
        "confirm_date_from": "2025-08-01",
        "confirm_date_to": "2026-07-31",
        "expected_active_taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "repo_root": paths["repo_root"],
    }
    args.update(overrides)
    return args


def test_chunk_plan_is_deterministic_bounded_gapless_and_non_overlapping() -> None:
    first = build_ec_taxonomy_rebuild_chunks(date_from="2025-08-01", date_to="2026-07-31")
    second = build_ec_taxonomy_rebuild_chunks(date_from="2025-08-01", date_to="2026-07-31")

    assert first == second
    assert all(chunk.chunk_span_days <= 60 for chunk in first)
    assert first[0].chunk_start == "2025-08-01"
    assert first[-1].chunk_end == "2026-07-31"
    for left, right in zip(first, first[1:]):
        assert right.chunk_index == left.chunk_index + 1
        assert right.chunk_start > left.chunk_end


def test_failed_backfill_with_empty_per_date_results_never_aggregates_audits_as_ok(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)

    def failed_backfill_runner(**_):
        return {
            "status": "BACKFILL_FAILED",
            "selected_dates": [{"date": "2025-08-01", "action": "TAXONOMY_REBUILD_REPLACE"}],
            "completed_dates": [],
            "skipped_dates": [],
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": "Coverage audit returned non-success status: FAILED",
        }

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2025-08-01",
            date_to="2025-08-01",
            confirm_date_from="2025-08-01",
            confirm_date_to="2025-08-01",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
        ),
        backfill_runner=failed_backfill_runner,
    )

    failed_chunk = summary["chunk_results"][-1]
    assert summary["overall_status"] == "FAILED"
    assert failed_chunk["status"] == "BACKFILL_FAILED"
    assert failed_chunk["coverage_status"] == "FAILED"
    assert failed_chunk["parity_status"] == "NOT_RUN_COVERAGE_FAILED"
    assert failed_chunk["coverage_execution_status"] == "FAILED_BEFORE_ACCEPTED_DATE_RESULT"
    assert failed_chunk["parity_execution_status"] == "NOT_RUN_COVERAGE_FAILED"
    assert failed_chunk["coverage_status_source"] == "chunk_failure_no_per_date_results"
    assert failed_chunk["parity_status_source"] == "chunk_failure_no_per_date_results"


def test_short_range_produces_one_chunk_and_reversed_range_is_blocked() -> None:
    chunks = build_ec_taxonomy_rebuild_chunks(date_from="2026-07-01", date_to="2026-07-05")
    assert len(chunks) == 1
    assert chunks[0].chunk_span_days == 5

    try:
        build_ec_taxonomy_rebuild_chunks(date_from="2026-07-05", date_to="2026-07-01")
    except ValueError as exc:
        assert "date_from must be less than or equal to date_to" in str(exc)
    else:
        raise AssertionError("reversed range should fail")


def test_plan_blocks_missing_deployment_wrong_hash_and_active_taxonomy(tmp_path) -> None:
    paths = _paths(tmp_path)
    missing = plan_ec_taxonomy_full_rebuild(**_plan_args(paths, deployment_id=8, confirm_deployment_id=8))
    assert missing["status"] == "BLOCKED_TAXONOMY_FULL_REBUILD_PLAN"
    assert "deployment row not found" in missing["blocking_errors"]

    bad_hash_paths = _paths(tmp_path / "bad_hash")
    conn = sqlite3.connect(bad_hash_paths["db"])
    try:
        conn.execute("UPDATE ec_taxonomy_version SET source_hash = 'wrong' WHERE taxonomy_version_code = 'DC_TAXONOMY_FULL_V2'")
        conn.commit()
    finally:
        conn.close()
    bad_hash = plan_ec_taxonomy_full_rebuild(**_plan_args(bad_hash_paths))
    assert "loaded taxonomy hash does not match taxonomy CSV" in bad_hash["blocking_errors"]

    active_paths = _paths(tmp_path / "active")
    conn = sqlite3.connect(active_paths["db"])
    try:
        conn.execute("UPDATE ec_taxonomy_version SET is_active = 1, status = 'ACTIVE' WHERE taxonomy_version_code = 'DC_TAXONOMY_FULL_V2'")
        conn.commit()
    finally:
        conn.close()
    active = plan_ec_taxonomy_full_rebuild(**_plan_args(active_paths))
    assert "proposed taxonomy is already active" in active["blocking_errors"]


def test_run_creates_one_backup_executes_chunks_sequentially_and_defers_chunk_watermarks(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    calls, fake_backfill_runner = _successful_backfill_calls()
    _patch_success_finalizers(monkeypatch)

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(paths, date_from="2026-07-01", date_to="2026-09-10", confirm_date_from="2026-07-01", confirm_date_to="2026-09-10"),
        backfill_runner=fake_backfill_runner,
    )

    assert summary["overall_status"] == "REBUILD_COMPLETED"
    assert summary["backup_mode"] == "ORCHESTRATOR_CREATED"
    assert summary["backup_created_by_orchestrator"] is True
    assert summary["backup_reused"] is False
    assert len(list(Path(paths["backup_dir"]).glob("*.sqlite"))) == 1
    assert [call["date_from"] for call in calls] == ["2026-07-01", "2026-08-30"]
    assert all(call["create_backup"] is False for call in calls)
    assert all(call["advance_watermark"] is False for call in calls)


def test_chunk_failure_stops_later_chunks_without_retry_or_watermark_finalization(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def fake_backfill_runner(**kwargs):
        calls.append(kwargs["date_from"])
        if len(calls) == 2:
            return {"status": "BACKFILL_FAILED", "error": "forced", "total_mismatch_count": 0, "per_date_results": []}
        return {
            "status": "BACKFILL_COMPLETED",
            "selected_dates": [],
            "completed_dates": [],
            "skipped_dates": [],
            "per_date_results": [{"coverage_status": "OK", "parity_status": "OK", "total_mismatch_count": 0}],
            "total_mismatch_count": 0,
            "error": None,
        }

    watermark_calls: list[dict[str, object]] = []
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill", lambda **kwargs: watermark_calls.append(kwargs))

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(paths, date_from="2026-07-01", date_to="2026-11-01", confirm_date_from="2026-07-01", confirm_date_to="2026-11-01"),
        backfill_runner=fake_backfill_runner,
    )

    assert summary["overall_status"] == "FAILED"
    assert summary["failed_chunk_index"] == 2
    assert summary["retry_required"] is True
    assert summary["watermark_finalization_performed"] is False
    assert calls == ["2026-07-01", "2026-08-30"]
    assert watermark_calls == []


def test_failed_chunk_progress_preserves_ticker_loader_diagnostics(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    ticker_summary = {
        "status": "FAILED",
        "loader_status": "FAILED",
        "loader_error_code": "TARGET_MAPPING_UNRESOLVED",
        "loader_error": "Ticker rows could not be resolved to one V2 primary EC membership",
        "source_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "source_row_count": 257,
        "source_distinct_ticker_count": 257,
        "unexpected_taxonomy_version_count": 0,
        "unresolved_membership_count": 1,
        "unresolved_tickers": ["AMD"],
        "duplicate_source_ticker_count": 0,
        "duplicate_target_key_count": 0,
    }

    def fake_backfill_runner(**kwargs):
        return {
            "status": "BACKFILL_FAILED",
            "date_from": kwargs["date_from"],
            "date_to": kwargs["date_to"],
            "selected_dates": [{"date": kwargs["date_from"], "action": "TAXONOMY_REBUILD_REPLACE"}],
            "completed_dates": [],
            "skipped_dates": [],
            "failed_date": kwargs["date_from"],
            "failed_step": "load_ec_ticker_signal_daily_from_dc",
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": "Ticker fact loader returned FAILED: Ticker rows could not be resolved to one V2 primary EC membership",
            "ticker_loader_summary": ticker_summary,
            **{key: value for key, value in ticker_summary.items() if key != "status"},
        }

    watermark_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill",
        lambda **kwargs: watermark_calls.append(kwargs),
    )

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-09-10",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-09-10",
        ),
        backfill_runner=fake_backfill_runner,
    )

    progress = json.loads((Path(paths["evidence_root"]) / "ec_taxonomy_full_rebuild_progress.json").read_text())
    failed_summary = progress["failed_chunk"]["summary"]

    assert summary["overall_status"] == "FAILED"
    assert summary["failed_chunk_index"] == 1
    assert summary["watermark_finalization_performed"] is False
    assert watermark_calls == []
    assert failed_summary["loader_error_code"] == "TARGET_MAPPING_UNRESOLVED"
    assert failed_summary["loader_error"] == "Ticker rows could not be resolved to one V2 primary EC membership"
    assert failed_summary["source_row_count"] == 257
    assert failed_summary["unresolved_tickers"] == ["AMD"]
    assert failed_summary["ticker_loader_summary"] == ticker_summary


def test_failed_chunk_progress_preserves_group_loader_diagnostics(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    group_summary = {
        "status": "FAILED",
        "loader_status": "FAILED",
        "loader_error_code": "TARGET_KEY_INVALID",
        "loader_error": "Group rows produced duplicate or null EC target keys",
        "requested_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "source_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "source_row_count": 54,
        "source_distinct_group_count": 54,
        "duplicate_source_group_count": 0,
        "unexpected_taxonomy_version_count": 0,
        "mapped_row_count": 108,
        "distinct_target_key_count": 54,
        "duplicate_target_key_count": 54,
        "null_target_key_count": 0,
        "unresolved_group_count": 0,
        "unresolved_groups": [],
        "multiple_source_to_same_target_count": 54,
    }

    def fake_backfill_runner(**kwargs):
        return {
            "status": "BACKFILL_FAILED",
            "date_from": kwargs["date_from"],
            "date_to": kwargs["date_to"],
            "selected_dates": [{"date": kwargs["date_from"], "action": "TAXONOMY_REBUILD_REPLACE"}],
            "completed_dates": [],
            "skipped_dates": [],
            "failed_date": kwargs["date_from"],
            "failed_step": "load_ec_group_signal_daily_from_dc",
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": "Group signal fact loader returned FAILED: Group rows produced duplicate or null EC target keys",
            "group_loader_summary": group_summary,
            **{key: value for key, value in group_summary.items() if key != "status"},
        }

    watermark_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill",
        lambda **kwargs: watermark_calls.append(kwargs),
    )

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-09-10",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-09-10",
        ),
        backfill_runner=fake_backfill_runner,
    )

    progress = json.loads((Path(paths["evidence_root"]) / "ec_taxonomy_full_rebuild_progress.json").read_text())
    failed_summary = progress["failed_chunk"]["summary"]

    assert summary["overall_status"] == "FAILED"
    assert summary["failed_chunk_index"] == 1
    assert summary["watermark_finalization_performed"] is False
    assert watermark_calls == []
    assert failed_summary["loader_error_code"] == "TARGET_KEY_INVALID"
    assert failed_summary["loader_error"] == "Group rows produced duplicate or null EC target keys"
    assert failed_summary["source_row_count"] == 54
    assert failed_summary["duplicate_target_key_count"] == 54
    assert failed_summary["group_loader_summary"] == group_summary


def test_failed_chunk_progress_preserves_synthetic_loader_diagnostics(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    synthetic_summary = {
        "status": "FAILED",
        "loader_status": "FAILED",
        "loader_error_code": "TARGET_KEY_INVALID",
        "loader_error": "Synthetic OHLC rows produced duplicate or null EC target keys",
        "requested_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "source_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "source_row_count": 53,
        "source_distinct_group_count": 53,
        "duplicate_source_group_count": 0,
        "unexpected_taxonomy_version_count": 0,
        "unexpected_calc_version_count": 0,
        "mapped_row_count": 106,
        "distinct_target_key_count": 53,
        "duplicate_target_key_count": 53,
        "null_target_key_count": 0,
        "unresolved_group_count": 0,
        "unresolved_groups": [],
        "multiple_source_to_same_target_count": 53,
    }

    def fake_backfill_runner(**kwargs):
        return {
            "status": "BACKFILL_FAILED",
            "date_from": kwargs["date_from"],
            "date_to": kwargs["date_to"],
            "selected_dates": [{"date": kwargs["date_from"], "action": "TAXONOMY_REBUILD_REPLACE"}],
            "completed_dates": [],
            "skipped_dates": [],
            "failed_date": kwargs["date_from"],
            "failed_step": "load_ec_group_synthetic_ohlc_daily_from_dc",
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": "Synthetic OHLC fact loader returned FAILED: Synthetic OHLC rows produced duplicate or null EC target keys",
            "synthetic_loader_summary": synthetic_summary,
            **{key: value for key, value in synthetic_summary.items() if key != "status"},
        }

    watermark_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill",
        lambda **kwargs: watermark_calls.append(kwargs),
    )

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-09-10",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-09-10",
        ),
        backfill_runner=fake_backfill_runner,
    )

    progress = json.loads((Path(paths["evidence_root"]) / "ec_taxonomy_full_rebuild_progress.json").read_text())
    failed_summary = progress["failed_chunk"]["summary"]

    assert summary["overall_status"] == "FAILED"
    assert summary["failed_chunk_index"] == 1
    assert summary["watermark_finalization_performed"] is False
    assert watermark_calls == []
    assert failed_summary["loader_error_code"] == "TARGET_KEY_INVALID"
    assert failed_summary["loader_error"] == "Synthetic OHLC rows produced duplicate or null EC target keys"
    assert failed_summary["source_row_count"] == 53
    assert failed_summary["duplicate_target_key_count"] == 53
    assert failed_summary["synthetic_loader_summary"] == synthetic_summary


def test_resume_rejects_changed_range_hash_and_plan(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    progress_path = Path(paths["evidence_root"]) / "ec_taxonomy_full_rebuild_progress.json"
    progress_path.write_text(
        """
        {
          "deployment_id": 7,
          "taxonomy_version": "DC_TAXONOMY_FULL_V2",
          "taxonomy_source_sha256": "wrong",
          "requested_start": "2025-08-01",
          "requested_end": "2026-07-31",
          "chunk_plan_hash": "wrong",
          "backup_summary": {},
          "completed_chunks": []
        }
        """,
        encoding="utf-8",
    )

    summary = run_ec_taxonomy_full_rebuild(**_plan_args(paths), resume=True, backfill_runner=lambda **_: {})

    assert summary["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert any("taxonomy_source_sha256" in error for error in summary["blocking_errors"])
    assert any("chunk_plan_hash" in error for error in summary["blocking_errors"])


def test_whole_range_failure_blocks_finalization(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)

    def fake_backfill_runner(**kwargs):
        return {
            "status": "BACKFILL_COMPLETED",
            "selected_dates": [],
            "completed_dates": [],
            "skipped_dates": [],
            "per_date_results": [{"coverage_status": "OK", "parity_status": "OK", "total_mismatch_count": 0}],
            "total_mismatch_count": 0,
            "error": None,
        }

    watermark_calls: list[dict[str, object]] = []
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator._validate_whole_range", lambda **_: {"whole_range_validation_status": "FAILED", "coverage_status": "FAILED", "parity_status": "OK", "total_mismatch_count": 0, "blocking_errors": ["coverage failed"]})
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill", lambda **kwargs: watermark_calls.append(kwargs))

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(paths, date_from="2026-07-01", date_to="2026-07-05", confirm_date_from="2026-07-01", confirm_date_to="2026-07-05"),
        backfill_runner=fake_backfill_runner,
    )

    assert summary["overall_status"] == "FAILED"
    assert summary["watermark_finalization_performed"] is False
    assert watermark_calls == []


def test_valid_existing_backup_is_reused_and_passed_to_every_chunk(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    calls, fake_backfill_runner = _successful_backfill_calls()
    _patch_success_finalizers(monkeypatch)

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-09-10",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-09-10",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path.resolve()),
        ),
        backfill_runner=fake_backfill_runner,
    )

    assert summary["overall_status"] == "REBUILD_COMPLETED"
    assert summary["backup_mode"] == "EXISTING_BACKUP"
    assert summary["backup_created_by_orchestrator"] is False
    assert summary["backup_reused"] is True
    assert summary["backup_validation_status"] == "OK"
    assert summary["backup_sha256"] == hashlib.sha256(backup_path.read_bytes()).hexdigest()
    assert len(list(Path(paths["backup_dir"]).glob("*.sqlite"))) == 1
    assert all(call["existing_backup_path"] == str(backup_path.resolve()) for call in calls)
    progress = (Path(paths["evidence_root"]) / "ec_taxonomy_full_rebuild_progress.json").read_text(encoding="utf-8")
    assert str(backup_path.resolve()) in progress
    assert summary["backup_sha256"] in progress
    assert summary["backup_schema_compatibility_status"] == "EXACT_MATCH"
    assert summary["backup_schema_exact_match"] is True
    assert summary["backup_schema_compatible_with_live"] is True


def test_existing_backup_accepts_known_live_only_deployment_audit_columns(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    _drop_backup_columns(backup_path, "ec_taxonomy_change_deployment", KNOWN_DEPLOYMENT_AUDIT_COLUMNS)
    calls, fake_backfill_runner = _successful_backfill_calls()
    _patch_success_finalizers(monkeypatch)

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
        ),
        backfill_runner=fake_backfill_runner,
    )

    assert summary["overall_status"] == "REBUILD_COMPLETED"
    assert calls
    assert summary["backup_validation_status"] == "OK"
    assert summary["backup_schema_compatibility_status"] == "COMPATIBLE_ADDITIVE_DRIFT"
    assert summary["backup_schema_exact_match"] is False
    assert summary["backup_schema_compatible_with_live"] is True
    assert summary["backup_schema_critical_mismatch_count"] == 0
    assert summary["backup_schema_allowed_difference_count"] == 7
    assert summary["backup_restore_requires_forward_schema_reapply"] is True
    assert [item["column"] for item in summary["backup_schema_allowed_differences"]] == sorted(KNOWN_DEPLOYMENT_AUDIT_COLUMNS)
    assert {item["compatibility"] for item in summary["backup_schema_allowed_differences"]} == {
        "ALLOWED_ADDITIVE_OPERATIONAL_SCHEMA_DRIFT"
    }
    progress = (Path(paths["evidence_root"]) / "ec_taxonomy_full_rebuild_progress.json").read_text(encoding="utf-8")
    assert "COMPATIBLE_ADDITIVE_DRIFT" in progress
    assert summary["backup_sha256"] in progress


def test_existing_backup_accepts_generic_nullable_deployment_audit_column(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("ALTER TABLE ec_taxonomy_change_deployment ADD COLUMN operator_note TEXT")
        conn.commit()
    finally:
        conn.close()

    summary = _validate_backup(paths, backup_path)

    assert summary["backup_validation_status"] == "OK"
    assert summary["backup_schema_compatibility_status"] == "COMPATIBLE_ADDITIVE_DRIFT"
    assert summary["backup_schema_allowed_difference_count"] == 1
    assert summary["backup_schema_allowed_differences"][0]["column"] == "operator_note"
    assert summary["backup_schema_allowed_differences"][0]["known_incident_column"] is False


def test_existing_backup_blocks_arbitrary_additive_canonical_column(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("ALTER TABLE ec_ticker_signal_daily ADD COLUMN debug_note TEXT")
        conn.commit()
    finally:
        conn.close()

    summary = _validate_backup(paths, backup_path)

    assert summary["backup_validation_status"] == "FAILED"
    assert summary["backup_schema_compatibility_status"] == "INCOMPATIBLE_SCHEMA_DRIFT"
    assert summary["backup_schema_compatible_with_live"] is False
    assert summary["backup_schema_critical_mismatch_count"] == 1
    assert summary["backup_schema_blocking_differences"] == [
        {"table": "ec_ticker_signal_daily", "difference": "CANONICAL_SCHEMA_MISMATCH"}
    ]


def test_existing_backup_blocks_destructive_deployment_audit_change(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("ALTER TABLE ec_taxonomy_change_deployment RENAME COLUMN status TO deployment_status")
        conn.commit()
    finally:
        conn.close()

    summary = _validate_backup(paths, backup_path)

    assert summary["backup_validation_status"] == "FAILED"
    differences = summary["backup_schema_blocking_differences"]
    assert {"table": "ec_taxonomy_change_deployment", "difference": "BACKUP_ONLY_COLUMNS", "columns": ["status"]} in differences
    assert {
        "table": "ec_taxonomy_change_deployment",
        "difference": "LIVE_ONLY_ADDITIVE_COLUMNS",
        "columns": ["deployment_status"],
    } not in differences


def test_existing_backup_blocks_changed_canonical_column_definition(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("ALTER TABLE ec_pipeline_watermark RENAME TO ec_pipeline_watermark_old")
        conn.execute(
            "CREATE TABLE ec_pipeline_watermark (ecosystem_id TEXT, pipeline_name TEXT, source_table TEXT, latest_signal_date TEXT, status TEXT, taxonomy_version_id INTEGER)"
        )
        conn.execute(
            "INSERT INTO ec_pipeline_watermark SELECT ecosystem_id, pipeline_name, source_table, latest_signal_date, status, taxonomy_version_id FROM ec_pipeline_watermark_old"
        )
        conn.execute("DROP TABLE ec_pipeline_watermark_old")
        conn.commit()
    finally:
        conn.close()

    summary = _validate_backup(paths, backup_path)

    assert summary["backup_validation_status"] == "FAILED"
    assert summary["backup_schema_blocking_differences"] == [
        {"table": "ec_pipeline_watermark", "difference": "CANONICAL_SCHEMA_MISMATCH"}
    ]


def test_existing_backup_blocks_changed_canonical_primary_key(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("ALTER TABLE ec_entity RENAME TO ec_entity_old")
        conn.execute(
            "CREATE TABLE ec_entity (entity_id INTEGER, ecosystem_id INTEGER NOT NULL, entity_type TEXT NOT NULL, entity_code TEXT NOT NULL, ticker TEXT NULL, status TEXT)"
        )
        conn.execute("DROP TABLE ec_entity_old")
        conn.commit()
    finally:
        conn.close()

    summary = _validate_backup(paths, backup_path)

    assert summary["backup_validation_status"] == "FAILED"
    assert summary["backup_schema_blocking_differences"] == [
        {"table": "ec_entity", "difference": "CANONICAL_SCHEMA_MISMATCH"}
    ]


def test_existing_backup_schema_failure_executes_zero_chunks_and_no_watermarks(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("DROP TABLE dc_pipeline_watermark")
        conn.commit()
    finally:
        conn.close()
    calls: list[dict[str, object]] = []
    watermark_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill",
        lambda **kwargs: watermark_calls.append(kwargs),
    )

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
        ),
        backfill_runner=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert "live DB missing critical tables: dc_pipeline_watermark" in summary["backup_error"]
    assert calls == []
    assert watermark_calls == []


def test_incident_backup_shape_is_accepted_in_isolated_fixture(tmp_path) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    _drop_backup_columns(backup_path, "ec_taxonomy_change_deployment", KNOWN_DEPLOYMENT_AUDIT_COLUMNS)

    summary = _validate_backup(paths, backup_path)

    assert summary["backup_validation_status"] == "OK"
    assert summary["backup_schema_compatibility_status"] == "COMPATIBLE_ADDITIVE_DRIFT"
    assert summary["backup_schema_allowed_difference_count"] == 7
    assert summary["backup_restore_requires_forward_schema_reapply"] is True


def test_existing_backup_validation_failures_block_before_chunks(tmp_path, monkeypatch) -> None:
    cases: list[tuple[str, Path, str | None]] = []

    outside_paths = _paths(tmp_path / "outside")
    outside_backup = tmp_path / "outside.sqlite"
    shutil.copy2(outside_paths["db"], outside_backup)
    cases.append(("outside temp", outside_backup, "path must be under repository temp/"))

    live_paths = _paths(tmp_path / "live")
    live_db = Path(live_paths["repo_root"]) / "temp" / "analysis.db"
    shutil.copy2(live_paths["db"], live_db)
    live_paths["db"] = str(live_db)
    cases.append(("live db", live_db, "must not be the live production DB"))

    missing_paths = _paths(tmp_path / "missing")
    cases.append(("missing", Path(missing_paths["backup_dir"]) / "missing.sqlite", "does not exist"))

    empty_paths = _paths(tmp_path / "empty")
    empty_backup = Path(empty_paths["backup_dir"]) / "empty.sqlite"
    empty_backup.write_bytes(b"")
    cases.append(("empty", empty_backup, "existing backup is empty"))

    invalid_paths = _paths(tmp_path / "invalid")
    invalid_backup = Path(invalid_paths["backup_dir"]) / "invalid.sqlite"
    invalid_backup.write_text("not sqlite", encoding="utf-8")
    cases.append(("invalid", invalid_backup, "file is not a database"))

    missing_schema_paths = _paths(tmp_path / "schema")
    missing_schema_backup = Path(missing_schema_paths["backup_dir"]) / "missing_schema.sqlite"
    conn = sqlite3.connect(missing_schema_backup)
    try:
        conn.execute("CREATE TABLE not_enough (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    cases.append(("missing schema", missing_schema_backup, "missing critical tables"))

    mismatch_paths = _paths(tmp_path / "confirm")
    mismatch_backup = _existing_backup(mismatch_paths)
    calls: list[dict[str, object]] = []
    for label, backup_path, expected in cases:
        paths = {
            "outside temp": outside_paths,
            "live db": live_paths,
            "missing": missing_paths,
            "empty": empty_paths,
            "invalid": invalid_paths,
            "missing schema": missing_schema_paths,
        }[label]
        summary = run_ec_taxonomy_full_rebuild(
            **_plan_args(
                paths,
                date_from="2026-07-01",
                date_to="2026-07-05",
                confirm_date_from="2026-07-01",
                confirm_date_to="2026-07-05",
                existing_backup_path=str(backup_path),
                confirm_existing_backup_path=str(backup_path),
            ),
            backfill_runner=lambda **kwargs: calls.append(kwargs),
        )
        assert summary["overall_status"] == "BLOCKED_BEFORE_WRITES", label
        assert summary["backup_validation_status"] == "FAILED", label
        assert expected in summary["backup_error"], label

    mismatch = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            mismatch_paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(mismatch_backup),
            confirm_existing_backup_path=str(Path(mismatch_paths["backup_dir"]) / "other.sqlite"),
        ),
        backfill_runner=lambda **kwargs: calls.append(kwargs),
    )
    assert mismatch["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert mismatch["backup_validation_status"] == "FAILED"
    assert "confirm-existing-backup-path" in mismatch["backup_error"]
    assert calls == []


def test_failed_integrity_check_blocks_before_chunks(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    calls: list[dict[str, object]] = []
    real_connect = sqlite3.connect

    class FakeBackupConnection:
        def execute(self, sql):
            assert sql == "PRAGMA integrity_check"
            return self

        def fetchone(self):
            return ("database disk image is malformed",)

        def close(self):
            return None

    def fake_connect(target, *args, **kwargs):
        if str(backup_path.resolve()) in str(target):
            return FakeBackupConnection()
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.sqlite3.connect", fake_connect)

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
        ),
        backfill_runner=lambda **kwargs: calls.append(kwargs),
    )

    assert summary["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert "integrity_check failed" in summary["backup_error"]
    assert calls == []


def test_resume_accepts_same_backup_and_rejects_changed_path_or_sha(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    calls, fake_backfill_runner = _successful_backfill_calls()
    _patch_success_finalizers(monkeypatch)
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator._verify_completed_chunk", lambda **_: {"status": "OK", "verified_dates": ["2026-07-01"]})

    first = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
        ),
        backfill_runner=fake_backfill_runner,
    )
    assert first["overall_status"] == "REBUILD_COMPLETED"
    calls.clear()

    same = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
            resume=True,
        ),
        backfill_runner=fake_backfill_runner,
    )
    assert same["overall_status"] == "REBUILD_COMPLETED"
    assert calls == []

    other_backup = _existing_backup(paths, "other.sqlite")
    changed_path = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(other_backup),
            confirm_existing_backup_path=str(other_backup),
            resume=True,
        ),
        backfill_runner=fake_backfill_runner,
    )
    assert changed_path["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert "backup path does not match" in "; ".join(changed_path["blocking_errors"])

    backup_path.write_bytes(backup_path.read_bytes() + b"changed")
    changed_sha = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
            resume=True,
        ),
        backfill_runner=fake_backfill_runner,
    )
    assert changed_sha["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert "backup SHA-256" in "; ".join(changed_sha["blocking_errors"])


def test_resume_rejects_newly_blocking_schema_difference(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    backup_path = _existing_backup(paths)
    calls, fake_backfill_runner = _successful_backfill_calls()
    _patch_success_finalizers(monkeypatch)
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator._verify_completed_chunk", lambda **_: {"status": "OK"})

    first = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
        ),
        backfill_runner=fake_backfill_runner,
    )
    assert first["overall_status"] == "REBUILD_COMPLETED"
    calls.clear()
    conn = sqlite3.connect(paths["db"])
    try:
        conn.execute("ALTER TABLE dc_ticker_swing_signal_daily ADD COLUMN incompatible_debug TEXT")
        conn.commit()
    finally:
        conn.close()

    resumed = run_ec_taxonomy_full_rebuild(
        **_plan_args(
            paths,
            date_from="2026-07-01",
            date_to="2026-07-05",
            confirm_date_from="2026-07-01",
            confirm_date_to="2026-07-05",
            existing_backup_path=str(backup_path),
            confirm_existing_backup_path=str(backup_path),
            resume=True,
        ),
        backfill_runner=fake_backfill_runner,
    )

    assert resumed["overall_status"] == "BLOCKED_BEFORE_WRITES"
    assert resumed["backup_schema_compatibility_status"] == "INCOMPATIBLE_SCHEMA_DRIFT"
    assert calls == []
