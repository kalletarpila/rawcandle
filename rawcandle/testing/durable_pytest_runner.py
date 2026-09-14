from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _atomic_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _reader(pipe, log_handle, state: dict[str, object], lock: threading.Lock) -> None:
    try:
        for line in iter(pipe.readline, ""):
            with lock:
                log_handle.write(line)
                log_handle.flush()
                state["last_output_at_utc"] = _utc_now()
                state["last_output_line"] = line.rstrip("\n")[-500:]
    finally:
        pipe.close()


def run_pytest(
    pytest_args: Sequence[str],
    *,
    artifact_dir: Path,
    heartbeat_seconds: float,
    timeout_seconds: float | None,
) -> int:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / "pytest.log"
    heartbeat_path = artifact_dir / "heartbeat.jsonl"
    metadata_path = artifact_dir / "metadata.json"
    exit_code_path = artifact_dir / "exit_code"
    summary_path = artifact_dir / "summary.json"
    command = [sys.executable, "-m", "pytest", *pytest_args]
    start = time.monotonic()
    metadata = {
        "command": command,
        "cwd": str(Path.cwd()),
        "pid": os.getpid(),
        "started_at_utc": _utc_now(),
        "heartbeat_seconds": heartbeat_seconds,
        "timeout_seconds": timeout_seconds,
    }
    _write_json(metadata_path, metadata)
    state: dict[str, object] = {"last_output_at_utc": None, "last_output_line": None}
    lock = threading.Lock()
    timed_out = False
    with log_path.open("w", encoding="utf-8", buffering=1) as log_handle:
        proc = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        metadata["pytest_pid"] = proc.pid
        _write_json(metadata_path, metadata)
        reader = threading.Thread(target=_reader, args=(proc.stdout, log_handle, state, lock), daemon=True)
        reader.start()
        with heartbeat_path.open("w", encoding="utf-8", buffering=1) as heartbeat:
            while True:
                code = proc.poll()
                elapsed = time.monotonic() - start
                with lock:
                    event = {
                        "at_utc": _utc_now(),
                        "elapsed_seconds": round(elapsed, 3),
                        "runner_pid": os.getpid(),
                        "pytest_pid": proc.pid,
                        "pytest_returncode": code,
                        "last_output_at_utc": state.get("last_output_at_utc"),
                        "last_output_line": state.get("last_output_line"),
                    }
                heartbeat.write(json.dumps(event, sort_keys=True) + "\n")
                heartbeat.flush()
                print(
                    f"[durable-pytest] elapsed={int(elapsed)}s pid={proc.pid} "
                    f"returncode={code} last={event['last_output_line']!r}",
                    flush=True,
                )
                if code is not None:
                    break
                if timeout_seconds is not None and elapsed > timeout_seconds:
                    timed_out = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=15)
                    break
                time.sleep(heartbeat_seconds)
        reader.join(timeout=10)
        return_code = proc.returncode
    if timed_out and return_code == 0:
        return_code = 124
    if timed_out and return_code is None:
        return_code = 124
    _atomic_text(exit_code_path, f"{return_code}\n")
    summary = {
        "command": command,
        "cwd": str(Path.cwd()),
        "ended_at_utc": _utc_now(),
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "exit_code": return_code,
        "heartbeat_path": str(heartbeat_path),
        "log_path": str(log_path),
        "metadata_path": str(metadata_path),
        "timed_out": timed_out,
    }
    _write_json(summary_path, summary)
    return int(return_code)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pytest with durable log, heartbeat and atomic exit-code evidence.")
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    raise SystemExit(run_pytest(
        pytest_args,
        artifact_dir=args.artifact_dir,
        heartbeat_seconds=args.heartbeat_seconds,
        timeout_seconds=args.timeout_seconds,
    ))


if __name__ == "__main__":
    main()
