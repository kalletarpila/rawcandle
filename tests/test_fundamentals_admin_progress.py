from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.contracts import AdminOperationType
from rawcandle.fundamentals.admin.history import AdminRunHistory
from rawcandle.fundamentals.admin.progress import (
    BATCH_ADD_TICKERS_STAGES,
    ProgressStage,
    ProgressTracker,
    progress_line,
)
from rawcandle.fundamentals.admin.rv_identity import active_relative_valuation_identity


class FakeClock:
    def __init__(self) -> None:
        self.step = 0

    def utc(self) -> str:
        value = f"2026-09-15T00:00:{self.step:02d}Z"
        self.step += 1
        return value

    def monotonic(self) -> float:
        value = float(self.step)
        self.step += 1
        return value


def _events(run_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (run_dir / "progress_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_progress_tracker_writes_deterministic_redacted_status_and_events(tmp_path: Path) -> None:
    clock = FakeClock()
    run_dir = tmp_path / "run1"
    callbacks: list[dict[str, object]] = []
    tracker = ProgressTracker(
        run_id="run1",
        operation_type=AdminOperationType.ADD_TICKERS,
        run_dir=run_dir,
        configured_secrets=("secret-token",),
        callback=callbacks.append,
        clock=clock.utc,
        monotonic=clock.monotonic,
    )

    declared = json.loads((run_dir / "progress_stages.json").read_text(encoding="utf-8"))
    assert [row["stage_id"] for row in declared["stages"]] == [stage.value for stage in BATCH_ADD_TICKERS_STAGES]

    first = tracker.running(ProgressStage.PREFLIGHT, "Resolving secret-token.", processed_items=1)
    tracker.heartbeat("Still resolving secret-token.")
    final = tracker.completed(
        ProgressStage.PREFLIGHT,
        "Request recorded.",
        processed_items=1,
        total_items=2,
        warnings=("secret-token warning",),
    )

    assert first["percent_complete"] is None
    assert final["percent_complete"] == 50.0
    text = (run_dir / "progress_events.jsonl").read_text(encoding="utf-8")
    assert "secret-token" not in text
    assert len(_events(run_dir)) == 3
    assert callbacks[-1]["stage_state"] == "COMPLETED"
    assert json.loads((run_dir / "progress_status.json").read_text(encoding="utf-8"))["sequence"] == 3
    assert progress_line(final).startswith("[1/19] PREFLIGHT - COMPLETED - ")


def test_progress_tracker_rejects_invalid_transitions(tmp_path: Path) -> None:
    tracker = ProgressTracker(run_id="run1", operation_type="ADD_TICKERS", run_dir=tmp_path / "run1")

    tracker.running(ProgressStage.SOURCE_RESOLUTION, "late")

    with pytest.raises(ValueError, match="PROGRESS_STAGE_ORDER_REGRESSION"):
        tracker.running(ProgressStage.PREVIEW_VALIDATION, "regression")

    with pytest.raises(ValueError, match="PROGRESS_ROLLED_BACK_REQUIRES_ROLLING_BACK"):
        tracker.rolled_back("rolled back without start")


def test_progress_status_replacement_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = ProgressTracker(run_id="run1", operation_type="ADD_TICKERS", run_dir=tmp_path / "run1")
    tracker.running(ProgressStage.PREFLIGHT, "started")
    status_path = tmp_path / "run1" / "progress_status.json"
    before = status_path.read_text(encoding="utf-8")

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("rawcandle.io_atomic.os.replace", fail_replace)
    with pytest.raises(OSError):
        tracker.completed(ProgressStage.PREFLIGHT, "done")

    assert status_path.read_text(encoding="utf-8") == before
    assert len(_events(tmp_path / "run1")) == 1


def test_progress_history_reader_reports_running_interrupted_and_rejects_escape(tmp_path: Path) -> None:
    tracker = ProgressTracker(run_id="run1", operation_type="ADD_TICKERS", run_dir=tmp_path / "run1")
    tracker.running(ProgressStage.PREFLIGHT, "started")
    tracker.completed(ProgressStage.PREFLIGHT, "done")

    history = AdminRunHistory(tmp_path)
    summary = history.progress("run1")
    assert summary.current_stage == "PREFLIGHT"
    assert summary.completed_stages == 1
    assert "progress_status.json" in summary.artifacts

    os.utime(tmp_path / "run1" / "progress_events.jsonl", (1, 1))
    assert AdminRunHistory(tmp_path, stale_seconds=0).progress("run1").status == "interrupted"

    with pytest.raises(ValueError):
        history.progress("../run1")
    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "link").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        history.progress("link")


def test_relative_valuation_identity_distinguishes_model_snapshot_and_result(tmp_path: Path) -> None:
    empty_db = tmp_path / "empty.db"
    sqlite3.connect(empty_db).close()
    empty = active_relative_valuation_identity(empty_db)
    assert empty["active_snapshot_id"] is None

    analysis = tmp_path / "analysis.db"
    with sqlite3.connect(analysis) as conn:
        conn.executescript(
            """
            CREATE TABLE relative_valuation_active_snapshot(
                model_fingerprint TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                activated_at_utc TEXT NOT NULL
            );
            CREATE TABLE relative_valuation_snapshot(
                snapshot_id TEXT PRIMARY KEY,
                as_of_date TEXT,
                created_at_utc TEXT,
                completed_at_utc TEXT,
                result_fingerprint TEXT,
                source_fingerprint TEXT,
                physical_content_fingerprint TEXT,
                status TEXT
            );
            INSERT INTO relative_valuation_active_snapshot VALUES('model-1','snapshot-1','2026-09-15T00:00:00Z');
            INSERT INTO relative_valuation_snapshot VALUES(
                'snapshot-1','2026-09-12','2026-09-13T00:00:00Z','2026-09-13T00:01:00Z',
                'result-1','source-1','physical-1','ACTIVE'
            );
            """
        )

    identity = active_relative_valuation_identity(analysis)

    assert identity["database_path"] == str(analysis.resolve())
    assert identity["active_model_fingerprint"] == "model-1"
    assert identity["active_snapshot_id"] == "snapshot-1"
    assert identity["active_result_fingerprint"] == "result-1"
