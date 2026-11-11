from pathlib import Path
from types import ModuleType
import gc, json, subprocess, sys, time, tracemalloc, statistics
from rawcandle.fundamentals.admin import full_workflow as current, artifacts
from rawcandle.fundamentals.admin import workflow_evidence as ev
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.admin.refresh_operational_decision import (
    refresh_operational_decision,
)
from rawcandle.fundamentals.admin.contracts import AdminOperationType
from tests.test_fundamentals_workflow_evidence import child, FP


def prepare(folder, blob_size):
    run = "preview"
    writer = artifacts.AdminRunWriter(
        run, AdminOperationType.REFRESH_FUNDAMENTALS, root=folder
    )
    decision = refresh_operational_decision(
        safe_effective_changes=1,
        held_items=[
            {
                "ticker": "HELD",
                "review_type": "PROVIDER_ANOMALY_SUSPECTED",
                "change": {"raw_history": "@@SYNTHETIC@@"},
            }
        ],
        global_blockers=[],
        future_test_authorized=True,
        test_reason_code="SAFE_CHANGES_TEST_AUTHORIZED",
    )
    payload = {
        "run_id": run,
        "operation_type": "REFRESH_FUNDAMENTALS",
        "mode": "PREVIEW",
        "outcome": "COMPLETED",
        "preview_fingerprint": FP,
        "completed_at_utc": "2026-11-11T12:00:00Z",
        "summary_counts": {
            "effective_changed_known": 1,
            "safe_changes": 1,
            "held_for_review": 1,
            "global_blockers": 0,
        },
        "refresh_preview": {"future_test_authorized": True},
        "operational_decision": decision,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    first, last = encoded.split("@@SYNTHETIC@@")
    path = writer.run_dir / "result.json"
    with path.open("w") as f:
        f.write(first)
        chunk = "X" * 65536
        for _ in range(blob_size // len(chunk)):
            f.write(chunk)
        f.write("X" * (blob_size % len(chunk)))
        f.write(last + "\n")
    writer.write_json(
        ev.SUMMARY,
        {
            "format": ev.VERSION,
            "run_id": run,
            "result_reference": ev.reference(
                folder, run, "RESULT", operation="REFRESH_FUNDAMENTALS"
            ),
            "summary": ev.child_summary(payload),
        },
    )
    writer.write_json(
        "refresh_preview.json",
        {"refresh_set_fingerprint": FP, "future_test_authorized": True},
    )
    writer.write_json("status.json", {"run_id": run, "stage": "COMPLETED"})
    writer.write_text("operation_report.md", "# Benchmark child native report\n")
    writer.write_manifest()
    from types import SimpleNamespace

    response = SimpleNamespace(
        run_id=run,
        artifact_dir=str(writer.run_dir),
        status="COMPLETED",
        outcome="COMPLETED",
        preview_fingerprint=FP,
        preview_payload_path=str(writer.run_dir / "refresh_preview.json"),
        message="COMPLETED",
    )
    return response, path


def measure(label, blob_size, updates, module):
    folder = root / label
    folder.mkdir(exist_ok=True)
    response, path = prepare(folder, blob_size)
    phase = {"progress": False, "parent": False, "ui": False}
    writes = []
    reads = []
    pieces = {
        "redaction": 0.0,
        "json_serialization": 0.0,
        "atomic_write_fsync_replace": 0.0,
    }
    original_write = artifacts.AdminRunWriter.write_json
    original_safe = artifacts.AdminRunWriter._safe
    original_atomic = artifacts.write_text_atomic
    original_dumps = json.dumps
    original_open = Path.open

    def safe(writer, value):
        start = time.perf_counter()
        out = original_safe(writer, value)
        if phase["progress"] and phase["parent"]:
            pieces["redaction"] += time.perf_counter() - start
        return out

    def dumps(*a, **kw):
        start = time.perf_counter()
        out = original_dumps(*a, **kw)
        if phase["progress"] and phase["parent"]:
            pieces["json_serialization"] += time.perf_counter() - start
        return out

    def atomic(*a, **kw):
        start = time.perf_counter()
        out = original_atomic(*a, **kw)
        if phase["progress"] and phase["parent"]:
            pieces["atomic_write_fsync_replace"] += time.perf_counter() - start
        return out

    def write(writer, name, value):
        previous = phase["parent"]
        phase["parent"] = "_full_workflow_" in writer.run_id
        start = time.perf_counter()
        try:
            out = original_write(writer, name, value)
            if phase["progress"] and phase["parent"]:
                writes.append(
                    {
                        "name": name,
                        "bytes": out.stat().st_size,
                        "seconds": time.perf_counter() - start,
                    }
                )
            return out
        finally:
            phase["parent"] = previous

    def opened(p, *a, **kw):
        if p == path and (phase["progress"] or phase["ui"]):
            reads.append({"phase": "ui" if phase["ui"] else "progress", "path": str(p)})
        return original_open(p, *a, **kw)

    artifacts.AdminRunWriter.write_json = write
    artifacts.AdminRunWriter._safe = safe
    artifacts.write_text_atomic = atomic
    json.dumps = dumps
    Path.open = opened
    timings = {}
    callback_times = []

    def preview(cb):
        timings["preview_return"] = time.perf_counter()
        return response

    def test(p, cb):
        timings["test_enter"] = time.perf_counter()
        for i in range(updates):
            phase["progress"] = True
            start = time.perf_counter()
            try:
                cb(
                    {
                        "run_id": "test",
                        "current_stage_id": "SYNTHETIC_PROGRESS",
                        "message": f"Progress {i}",
                    }
                )
            finally:
                phase["progress"] = False
            callback_times.append(time.perf_counter() - start)
        return child(folder, "test", "COPY_ONLY_APPLY")

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()
    try:
        result = module.run_refresh_full_workflow(
            run_root=folder,
            preview_stage=preview,
            test_stage=test,
            production_stage=lambda p, t, cb: child(
                folder,
                "production",
                "PRODUCTION_APPLY",
                provider_candidate={"ticker_count": 1},
                postflight={"status": "PASSED"},
            ),
        )
        elapsed = time.perf_counter() - start
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert result["outcome"] == "COMPLETED", result.get("stop_reason")
        if module is current:
            phase["ui"] = True
            reader = FundamentalsAdminUIService(
                run_root=folder, recover_publication_on_startup=False
            )
            assert reader.history_entries(limit=8)
            reader.progress(result["run_id"])
            reader.history_result_summary("preview")
            phase["ui"] = False
            assert reads == [], reads
            assert peak < 32 * 1024 * 1024, peak
        parent = Path(result["artifact_dir"])
        controls = {
            name: (parent / name).stat().st_size
            for name in ("workflow_result.json", "result.json", "progress_status.json")
        }
        output = {
            "label": label,
            "child_bytes": path.stat().st_size,
            "updates": updates,
            "parent_bytes": controls,
            "progress_total_write_bytes": sum(x["bytes"] for x in writes),
            "progress_bytes_per_event": sum(x["bytes"] for x in writes) / updates,
            "progress_event_seconds_median": statistics.median(callback_times),
            "progress_event_seconds_max": max(callback_times),
            "preview_to_test_transition_seconds": timings["test_enter"]
            - timings["preview_return"],
            "orchestration_seconds": elapsed,
            "tracemalloc_peak_bytes": peak,
            "child_reads_during_progress_or_ui": reads,
            "component_seconds_for_all_progress_updates": pieces,
            "max_control_bytes_during_updates": max(x["bytes"] for x in writes),
        }
        (folder / "measurements.json").write_text(original_dumps(output, indent=2))
        print(original_dumps(output), flush=True)
        return output
    finally:
        artifacts.AdminRunWriter.write_json = original_write
        artifacts.AdminRunWriter._safe = original_safe
        artifacts.write_text_atomic = original_atomic
        json.dumps = original_dumps
        Path.open = original_open


def main():
    global root
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "temp/fundamentals_parent_evidence_performance_20261111/benchmark"
        ),
    )
    parser.add_argument("--large-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--updates", type=int, default=100)
    args = parser.parse_args()
    if args.large_bytes <= 0 or args.updates <= 0:
        parser.error("positive sizes and update counts required")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    legacy = ModuleType("rawcandle.fundamentals.admin._legacy_parent_benchmark")
    legacy.__package__ = "rawcandle.fundamentals.admin"
    sys.modules[legacy.__name__] = legacy
    exec(
        subprocess.check_output(
            [
                "git",
                "show",
                "a9e314f2dad990101e7b830f9530db9eede9b5cb:rawcandle/fundamentals/admin/full_workflow.py",
            ],
            text=True,
        ),
        legacy.__dict__,
    )

    results = []
    results.append(measure("legacy_16mib", 16 * 1024 * 1024, 3, legacy))
    results.append(measure("compact_64kib", 64 * 1024, args.updates, current))
    results.append(measure("compact_2gib", args.large_bytes, args.updates, current))
    assert (
        results[1]["max_control_bytes_during_updates"] < 65536
        and results[2]["max_control_bytes_during_updates"] < 65536
    )
    assert (
        abs(
            results[1]["progress_bytes_per_event"]
            - results[2]["progress_bytes_per_event"]
        )
        < 1024
    )
    (root.parent / "benchmark_results.json").write_text(json.dumps(results, indent=2))
    print("STRUCTURAL_PERFORMANCE_ACCEPTANCE_PASS", flush=True)


if __name__ == "__main__":
    main()
