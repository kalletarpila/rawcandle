from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from rawcandle.datacenter_taxonomy_replacement import ensure_taxonomy_replacement_schema
from rawcandle.ec_taxonomy_full_rebuild_orchestrator import (
    build_ec_taxonomy_rebuild_chunks,
    plan_ec_taxonomy_full_rebuild,
    run_ec_taxonomy_full_rebuild,
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

    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator._validate_whole_range", lambda **_: {"whole_range_validation_status": "OK", "coverage_status": "OK", "parity_status": "OK", "total_mismatch_count": 0, "blocking_errors": []})
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.advance_ec_pipeline_watermarks_after_historical_backfill", lambda **_: {"status": "OK", "watermark_advance_status": "OK", "watermark_rows_updated": 4})
    monkeypatch.setattr("rawcandle.ec_taxonomy_full_rebuild_orchestrator.apply_datacenter_taxonomy_rebuild_evidence", lambda **_: {"status_update": "READY_TO_ACTIVATE", "ready_to_activate": True})

    summary = run_ec_taxonomy_full_rebuild(
        **_plan_args(paths, date_from="2026-07-01", date_to="2026-09-10", confirm_date_from="2026-07-01", confirm_date_to="2026-09-10"),
        backfill_runner=fake_backfill_runner,
    )

    assert summary["overall_status"] == "REBUILD_COMPLETED"
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
