from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths, load_relative_valuation_source,
)

from . import activation, phase10b, relative_position, score, valuation


RECENT = ("SNDK", "AG", "ARM", "BHP", "BIDU", "CAMT", "ALOY", "ASML", "ASX", "BABA", "BTDR")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _v1_digests(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    result = {}
    for name, sql, model in (
        ("score_result", "SELECT * FROM score_result WHERE model_fingerprint!=? ORDER BY score_result_id", score.MODEL_FINGERPRINT),
        ("score_component", "SELECT c.* FROM score_component c JOIN score_result r USING(score_result_id) WHERE r.model_fingerprint!=? ORDER BY c.score_result_id,c.component_name", score.MODEL_FINGERPRINT),
        ("valuation_revised_result", "SELECT * FROM valuation_revised_result WHERE model_fingerprint!=? ORDER BY valuation_revised_result_id", valuation.MODEL_FINGERPRINT),
        ("relative_position_snapshot", "SELECT * FROM relative_position_snapshot WHERE model_fingerprint!=? ORDER BY snapshot_id", relative_position.MODEL_FINGERPRINT),
        ("relative_position_result", "SELECT r.* FROM relative_position_result r JOIN relative_position_snapshot s USING(snapshot_id) WHERE s.model_fingerprint!=? ORDER BY r.snapshot_id,r.company_id,r.measure,r.peer_scope,r.peer_group_id", relative_position.MODEL_FINGERPRINT),
        ("relative_position_coverage", "SELECT c.* FROM relative_position_coverage c JOIN relative_position_snapshot s USING(snapshot_id) WHERE s.model_fingerprint!=? ORDER BY c.snapshot_id,c.company_id,c.measure,c.peer_scope,c.peer_group_id", relative_position.MODEL_FINGERPRINT),
    ):
        digest = hashlib.sha256()
        count = 0
        for row in connection.execute(sql, (model,)):
            digest.update(json.dumps(tuple(row), default=str, separators=(",", ":")).encode())
            count += 1
        result[name] = {"count": count, "sha256": digest.hexdigest()}
    return result


def _state(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        "v1_digests": _v1_digests(connection),
        "v2_score_rows": connection.execute("SELECT COUNT(*) FROM score_result WHERE model_fingerprint=?", (score.MODEL_FINGERPRINT,)).fetchone()[0],
        "v2_valuation_rows": connection.execute("SELECT COUNT(*) FROM valuation_revised_result WHERE model_fingerprint=?", (valuation.MODEL_FINGERPRINT,)).fetchone()[0],
        "v2_rp_snapshot": connection.execute("SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?", (relative_position.MODEL_FINGERPRINT,)).fetchone()[0],
        "v2_rp_rows": connection.execute("SELECT COUNT(*) FROM relative_position_result WHERE snapshot_id=(SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?)", (relative_position.MODEL_FINGERPRINT,)).fetchone()[0],
    }


def _recent(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    result = []
    for ticker in RECENT:
        val = connection.execute("SELECT company_id,quarter_id,valuation_status,total_valuation_score FROM valuation_revised_result WHERE model_fingerprint=? AND ticker=? ORDER BY fiscal_sequence DESC LIMIT 1", (valuation.MODEL_FINGERPRINT, ticker)).fetchone()
        score_row = connection.execute("SELECT readiness_status,total_score FROM score_result WHERE model_fingerprint=? AND company_id=? AND quarter_id=?", (score.MODEL_FINGERPRINT, val[0], val[1])).fetchone() if val else None
        rp = connection.execute("SELECT peer_scope,COUNT(*) FROM relative_position_result WHERE snapshot_id=(SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?) AND ticker=? GROUP BY peer_scope ORDER BY peer_scope", (relative_position.MODEL_FINGERPRINT, ticker)).fetchall()
        result.append({"ticker": ticker, "score": tuple(score_row) if score_row else None, "valuation": tuple(val[2:]) if val else None, "rp": {scope: count for scope, count in rp}})
    return result


def run(root: Path, output: Path, as_of_date: str, *, resume_copy: bool = False) -> dict[str, Any]:
    date.fromisoformat(as_of_date)
    root = root.resolve()
    if output.is_symlink():
        raise PermissionError("PHASE13G25A_OUTPUT_SYMLINK_REJECTED")
    output = output.resolve()
    if not output.is_relative_to(root / "temp"):
        raise PermissionError("PHASE13G25A_OUTPUT_MUST_BE_UNDER_REPO_TEMP")
    if output.exists() and not resume_copy:
        raise FileExistsError(output)
    if resume_copy:
        if not (output / "fundamentals_analysis.copy.db").is_file():
            raise FileNotFoundError("PHASE13G25A_RESUME_COPY_MISSING")
    else:
        output.mkdir(parents=True)
    events = output / "events.jsonl"
    def emit(stage: str, status: str, **details: Any) -> None:
        record = {"at_utc": _now(), "stage": stage, "status": status, **details}
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps(record, sort_keys=True, default=str), flush=True)

    analysis = root / "data/fundamentals_analysis.db"
    copy = output / "fundamentals_analysis.copy.db"
    if copy.is_symlink() or copy.resolve() == analysis.resolve():
        raise PermissionError("PHASE13G25A_ANALYSIS_COPY_NOT_ISOLATED")
    paths = {
        "analysis": copy,
        "canonical": root / "data/fundamentals_v4.db",
        "market": root / "data/osakedata.db",
        "provider": root / "data/fundamentals_provider.db",
        "taxonomy": root / "data/analysis.db",
    }
    stop = threading.Event()
    stage = ["backup"]
    def heartbeat() -> None:
        while not stop.wait(30):
            emit(stage[0], "HEARTBEAT")
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    success = False
    try:
        if not resume_copy:
            emit("backup", "STARTED")
            with _ro(analysis) as source, sqlite3.connect(copy) as destination:
                source.backup(destination)
            emit("backup", "COMPLETED", bytes=copy.stat().st_size)
        else:
            emit("backup", "RESUMED", bytes=copy.stat().st_size)
        with _ro(analysis) as production, _ro(copy) as local:
            active = activation.assert_v2_active(production)
            persistence_fingerprint = active.persistence_fingerprint
            before = _state(production)
            if not resume_copy:
                assert before == _state(local)
            recent_before = _recent(production)
        rv_paths_before = ReadOnlySourcePaths(analysis, paths["canonical"], paths["market"], paths["taxonomy"])
        rv_paths = ReadOnlySourcePaths(copy, paths["canonical"], paths["market"], paths["taxonomy"])
        stage[0] = "rv_source_before"
        rv_before = load_relative_valuation_source(rv_paths_before, as_of_date=as_of_date)
        stage[0] = "calculate_first"
        emit(stage[0], "STARTED")
        first = phase10b.calculate(paths, as_of_date=as_of_date)
        emit(stage[0], "COMPLETED", fingerprints=first["fingerprints"])
        stage[0] = "apply_first"
        emit(stage[0], "STARTED")
        with sqlite3.connect(copy) as local:
            local.execute("PRAGMA foreign_keys=ON")
            applied = phase10b.apply_candidate_package(
                local, first, applied_at=_now(),
                persistence_fingerprint=persistence_fingerprint,
            )
            after = _state(local)
            recent_after = _recent(local)
            dependency = local.execute("SELECT * FROM relative_position_v2_taxonomy_dependency WHERE snapshot_id=?", (after["v2_rp_snapshot"],)).fetchone()
            integrity = local.execute("PRAGMA quick_check").fetchone()[0]
            foreign_keys = len(local.execute("PRAGMA foreign_key_check").fetchall())
        emit("v1_audit", "COMPLETED", before=before["v1_digests"], after=after["v1_digests"])
        assert after["v1_digests"] == before["v1_digests"]
        assert dependency is not None
        assert dependency[1:5] == (
            first["taxonomy_dependency"]["domain"], first["taxonomy_dependency"]["version"],
            first["taxonomy_dependency"]["semantic_fingerprint"], as_of_date,
        )
        assert integrity == "ok" and foreign_keys == 0
        emit(stage[0], "COMPLETED", outcome=applied.outcome, snapshot_id=after["v2_rp_snapshot"])
        stage[0] = "rv_source_after"
        rv_after = load_relative_valuation_source(rv_paths, as_of_date=as_of_date)
        stage[0] = "calculate_second"
        emit(stage[0], "STARTED")
        second = phase10b.calculate(paths, as_of_date=as_of_date)
        assert first["fingerprints"] == second["fingerprints"]
        emit(stage[0], "COMPLETED", fingerprints=second["fingerprints"])
        stage[0] = "apply_second"
        with sqlite3.connect(copy) as local:
            local.execute("PRAGMA foreign_keys=ON")
            repeated = phase10b.apply_candidate_package(
                local, second, applied_at=_now(),
                persistence_fingerprint=persistence_fingerprint,
            )
            final = _state(local)
        assert repeated.outcome == "NO_CHANGE"
        assert applied.outcome == "APPLIED"
        assert final == after
        result = {
            "as_of_date": as_of_date, "production_before": before, "copy_after": after,
            "copy_repeat": final, "first_outcome": applied.outcome,
            "second_outcome": repeated.outcome, "first_package": asdict(applied),
            "second_package": asdict(repeated), "fingerprints": first["fingerprints"],
            "taxonomy_dependency": first["taxonomy_dependency"],
            "recent_before": recent_before, "recent_after": recent_after,
            "rv_source_before": {"fingerprint": rv_before.source_fingerprint, "inputs": len(rv_before.inputs)},
            "rv_source_after": {"fingerprint": rv_after.source_fingerprint, "inputs": len(rv_after.inputs)},
            "copy_integrity": integrity, "copy_foreign_key_errors": foreign_keys,
        }
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output / "operation_report.md").write_text(
            f"# Phase 13G.2.5A copy rehearsal\n\nAs of: {as_of_date}\n\n"
            f"First package: {applied.outcome}; repeat: {repeated.outcome}.\n\n"
            f"V2 RP snapshot: {after['v2_rp_snapshot']}; rows: {after['v2_rp_rows']}.\n\n"
            f"V1 digest unchanged: {after['v1_digests'] == before['v1_digests']}.\n\n"
            f"RV source changed: {rv_before.source_fingerprint != rv_after.source_fingerprint}.\n\n"
            f"Taxonomy version: {first['taxonomy_dependency']['version']}.\n",
            encoding="utf-8",
        )
        emit("complete", "SUCCESS", result=str(output / "result.json"))
        success = True
        return result
    except Exception as exc:
        emit(stage[0], "FAILED", error=repr(exc))
        raise
    finally:
        stop.set()
        thread.join(timeout=1)
        if success and copy.exists():
            copy.unlink()
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(copy) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            emit("cleanup", "COMPLETED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--resume-copy", action="store_true")
    args = parser.parse_args()
    run(args.repo_root, args.output, args.as_of_date, resume_copy=args.resume_copy)


if __name__ == "__main__":
    main()
