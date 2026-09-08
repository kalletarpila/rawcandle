from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.renderer import render_snapshot

from .candidate_snapshot import (
    assemble_relative_valuation_candidate_snapshot,
    attach_persisted_relative_valuation_candidate,
)
from .engine import (
    MODEL_FINGERPRINT, RelativeValuationInput, calculate_current_price_valuation,
    calculate_own_history, calculate_relative_valuation, canonical_json,
)
from .persistence import (
    LAYOUT_FINGERPRINT, PERSISTENCE_VERSION, RelativeValuationRepository,
    apply_snapshot, migrate_analysis_copy, quick_check, schema_signature,
)
from .source import ReadOnlySourcePaths, load_relative_valuation_source


REPORT_TICKERS = (
    "NVDA", "AMZN", "GOOG", "CRMD", "APD", "PLTR", "CLS", "VRT", "HUBG",
    "AAOI", "BBWI", "O", "AVB", "ALAB", "AA",
)
FAILURE_STAGES = (
    "metadata", "company", "peer", "own_history", "component",
    "before_reconciliation", "after_reconciliation", "after_activation", "cleanup",
)


def changed_inputs(inputs: Sequence[RelativeValuationInput], iteration: int) -> tuple[RelativeValuationInput, ...]:
    target = next(row for row in inputs if row.ticker == "A")
    observation = replace(
        target.valuation_observation,
        ttm_operating_income=float(target.valuation_observation.ttm_operating_income) * (1.0 + iteration),
    )
    changed = replace(target, valuation_observation=observation)
    return tuple(changed if row.company_id == target.company_id else row for row in inputs)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def _storage(connection: sqlite3.Connection, path: Path, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "file_size": path.stat().st_size,
        "page_size": int(connection.execute("PRAGMA page_size").fetchone()[0]),
        "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
        "freelist_count": int(connection.execute("PRAGMA freelist_count").fetchone()[0]),
        "wal_size": Path(str(path) + "-wal").stat().st_size if Path(str(path) + "-wal").exists() else 0,
    }


def _object_storage(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in connection.execute(
            "SELECT name,SUM(pgsize) bytes,COUNT(*) pages FROM dbstat "
            "WHERE name LIKE 'relative_valuation_%' OR name LIKE 'idx_relative_valuation_%' "
            "GROUP BY name ORDER BY name"
        )]
    except sqlite3.OperationalError:
        return []


def _calculate(source: Any, inputs: Sequence[RelativeValuationInput], as_of_date: str):
    return calculate_relative_valuation(
        inputs,
        as_of_date=as_of_date,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )


def _measured_apply(connection: sqlite3.Connection, database: Path, operation: Any):
    stopped = threading.Event()
    peak = {"journal": 0, "wal": 0}

    def sample() -> None:
        while not stopped.is_set():
            for suffix, key in (("-journal", "journal"), ("-wal", "wal")):
                path = Path(str(database) + suffix)
                if path.exists():
                    peak[key] = max(peak[key], path.stat().st_size)
            time.sleep(0.001)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        result = operation()
    finally:
        stopped.set()
        sampler.join()
    return result, time.perf_counter() - started, peak


def _resign(snapshot: Any, *, as_of_date: str, source_fingerprint: str):
    changed = replace(snapshot, as_of_date=as_of_date, source_fingerprint=source_fingerprint)
    payload = {
        "model_version": changed.model_version,
        "model_fingerprint": changed.model_fingerprint,
        "semantic_mode": changed.semantic_mode,
        "as_of_date": changed.as_of_date,
        "source_fingerprint": changed.source_fingerprint,
        "companies": [asdict(row) for row in changed.companies],
    }
    result = hashlib.sha256(canonical_json(payload).encode("ascii")).hexdigest()
    return replace(changed, result_fingerprint=result)


def run_phase11c(
    paths: ReadOnlySourcePaths,
    *,
    as_of_date: str,
    output_dir: Path,
    upgraded_database: Path,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source = load_relative_valuation_source(paths, as_of_date=as_of_date)
    snapshot = _calculate(source, source.inputs, as_of_date)
    calculation_seconds = time.perf_counter() - started

    fresh_db = output_dir / "fresh_analysis_shape.db"
    with _connect(fresh_db) as fresh:
        fresh.executescript(ANALYSIS_SCHEMA_SQL)
        fresh_signature = schema_signature(fresh)
    migration = migrate_analysis_copy(upgraded_database, applied_at_utc="2026-09-08T16:10:00Z")

    with _connect(upgraded_database) as upgraded:
        if schema_signature(upgraded) != fresh_signature:
            raise RuntimeError("RELATIVE_VALUATION_FRESH_UPGRADED_SCHEMA_MISMATCH")
        storage = [_storage(upgraded, upgraded_database, "before_apply")]
        first, first_seconds, first_peak = _measured_apply(
            upgraded, upgraded_database,
            lambda: apply_snapshot(
                upgraded, snapshot, source.inputs,
                applied_at_utc="2026-09-08T16:11:00Z",
            ),
        )
        storage.append(_storage(upgraded, upgraded_database, "after_first_apply"))
        second, second_seconds, second_peak = _measured_apply(
            upgraded, upgraded_database,
            lambda: apply_snapshot(
                upgraded, snapshot, source.inputs,
                applied_at_utc="2026-09-08T16:12:00Z",
            ),
        )
        storage.append(_storage(upgraded, upgraded_database, "after_second_apply"))
        if second.outcome != "NO_CHANGE" or second.logical_bulk_writes != 0:
            raise RuntimeError("RELATIVE_VALUATION_SECOND_APPLY_NOT_LOGICAL_NOOP")
        if storage[-1]["file_size"] != storage[-2]["file_size"]:
            raise RuntimeError("RELATIVE_VALUATION_SECOND_APPLY_DATABASE_GROWTH")

        repository = RelativeValuationRepository(upgraded)
        ids = [int(row.company_id) for row in snapshot.companies[:20] if row.company_id is not None]
        latency = []
        operations = (
            ("one_company", lambda: repository.company(ids[0], model_fingerprint=MODEL_FINGERPRINT)),
            ("twenty_companies", lambda: repository.companies(ids, model_fingerprint=MODEL_FINGERPRINT)),
            ("current_universe", lambda: repository.current_universe(model_fingerprint=MODEL_FINGERPRINT)),
            ("universe_peer_group", lambda: repository.peer_group(model_fingerprint=MODEL_FINGERPRINT, scope="UNIVERSE", group_id="ALL")),
        )
        for label, operation in operations:
            started = time.perf_counter()
            result = operation()
            latency.append({
                "operation": label,
                "seconds": time.perf_counter() - started,
                "rows": len(result) if isinstance(result, list) else int(result is not None),
            })
        deep = quick_check(upgraded)
        object_storage = _object_storage(upgraded)

        report_dir = output_dir / "candidate_reports"
        report_dir.mkdir(exist_ok=True)
        snapshot_paths = SnapshotPaths(
            paths.canonical_db.resolve(), paths.analysis_db.resolve(),
            paths.market_db.resolve(), paths.taxonomy_db.resolve(),
            (paths.canonical_db.parent / "fundamentals_provider.db").resolve(),
        )
        report_checks = {}
        for ticker in REPORT_TICKERS:
            pure = assemble_relative_valuation_candidate_snapshot(
                snapshot_paths, ticker=ticker, report_date=as_of_date,
                relative_valuation=snapshot,
            )
            base = {key: value for key, value in pure.items() if key not in {
                "relative_valuation", "relative_valuation_identity",
            }}
            persisted = attach_persisted_relative_valuation_candidate(base, repository)
            pure_markdown = render_snapshot(pure).markdown
            persisted_markdown = render_snapshot(persisted).markdown
            visible_pure = "\n".join(
                line for line in pure_markdown.splitlines()
                if not line.startswith("| Report-content fingerprint |")
            )
            visible_persisted = "\n".join(
                line for line in persisted_markdown.splitlines()
                if not line.startswith("| Report-content fingerprint |")
            )
            if visible_pure != visible_persisted:
                raise RuntimeError(f"RELATIVE_VALUATION_PERSISTED_REPORT_MISMATCH:{ticker}")
            report_checks[ticker] = {
                "visible_markdown_equal": True,
                "report_fingerprint_expected_to_differ": pure_markdown != persisted_markdown,
                "current_fresh": persisted["relative_valuation"]["current_fresh"],
            }
            (report_dir / f"{ticker}_{as_of_date}.md").write_text(persisted_markdown, encoding="utf-8")

    retention_db = output_dir / "retention_analysis_shape.db"
    with _connect(retention_db) as retention:
        retention.executescript(ANALYSIS_SCHEMA_SQL)
        retention_storage = []
        retention_reports = []
        for iteration in range(6):
            inputs = changed_inputs(source.inputs, iteration)
            changed = _calculate(source, inputs, as_of_date)
            report = apply_snapshot(
                retention, changed, inputs,
                applied_at_utc=f"2026-09-08T16:{20 + iteration:02d}:00Z",
            )
            retention_reports.append(report.__dict__)
            retention_storage.append(_storage(retention, retention_db, f"snapshot_{iteration + 1}"))
            if quick_check(retention)["snapshot_count"] > 2:
                raise RuntimeError("RELATIVE_VALUATION_RETENTION_UNBOUNDED")
        retention_check = quick_check(retention)

    failure_db = output_dir / "failure_analysis_shape.db"
    with _connect(failure_db) as failure:
        failure.executescript(ANALYSIS_SCHEMA_SQL)
        apply_snapshot(failure, snapshot, source.inputs, applied_at_utc="2026-09-08T16:30:00Z")
        inputs = changed_inputs(source.inputs, 2)
        changed = _calculate(source, inputs, as_of_date)
        failure_results = []
        for stage in FAILURE_STAGES:
            before = RelativeValuationRepository(failure).active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT)
            try:
                apply_snapshot(
                    failure, changed, inputs,
                    applied_at_utc="2026-09-08T16:31:00Z",
                    inject_failure_at=stage,
                )
                raised = False
            except RuntimeError:
                raised = True
            after = RelativeValuationRepository(failure).active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT)
            failure_results.append({"stage": stage, "raised": raised, "active_preserved": before == after})
            if not raised or before != after:
                raise RuntimeError(f"RELATIVE_VALUATION_FAILURE_ROLLBACK_FAILED:{stage}")

    date_db = output_dir / "date_cases_analysis_shape.db"
    with _connect(date_db) as date_connection:
        date_connection.executescript(ANALYSIS_SCHEMA_SQL)
        apply_snapshot(date_connection, snapshot, source.inputs, applied_at_utc="2026-09-08T16:40:00Z")
        date_only = _resign(
            snapshot, as_of_date="2026-09-09",
            source_fingerprint=hashlib.sha256(b"phase11c-date-only").hexdigest(),
        )
        date_only_report = apply_snapshot(
            date_connection, date_only, source.inputs,
            applied_at_utc="2026-09-09T16:40:00Z",
        )
        stale = _calculate(source, source.inputs, "2027-09-08")
        stale_report = apply_snapshot(
            date_connection, stale, source.inputs,
            applied_at_utc="2027-09-08T16:40:00Z",
        )
        date_cases = {
            "same_as_of_same_result": second.outcome,
            "new_as_of_same_bulk": date_only_report.__dict__,
            "new_as_of_changed_readiness": stale_report.__dict__,
            "check": quick_check(date_connection),
        }

    cohorts = {
        "company_count": len(snapshot.companies),
        "current_fresh": sum(row.current_fresh for row in snapshot.companies),
        "current_peer_eligible": sum(
            any(item["peer_scope"] == "UNIVERSE" for item in row.current_peer_results)
            for row in snapshot.companies
        ),
        "own_history_ready_current_fresh": sum(
            row.current_fresh and row.own_history.status == "READY" for row in snapshot.companies
        ),
        "own_history_limited_current_fresh": sum(
            row.current_fresh and row.own_history.status == "LIMITED_HISTORY" for row in snapshot.companies
        ),
        "same_anchor_filing_current_pairs": sum(
            row.current_fresh
            and row.current_valuation.get("valuation_status") == "VALUATION_FULL"
            and row.filing_valuation is not None
            and row.filing_valuation.get("valuation_status") == "VALUATION_FULL"
            and int(row.filing_valuation["quarter_id"]) == int(row.current_valuation["quarter_id"])
            for row in snapshot.companies
        ),
    }
    hubg = next(row for row in snapshot.companies if row.ticker == "HUBG")
    broader_ready = []
    for row in source.inputs:
        if row.current_fresh:
            continue
        current = calculate_current_price_valuation(
            row.valuation_observation, row.price_bars, as_of_date=as_of_date,
        )
        own = calculate_own_history(
            current, row.history, as_of_date=as_of_date, current_fresh=True,
        )
        if own.status == "READY":
            broader_ready.append(row.ticker)
    cohorts["own_history_ready_broader_calculable"] = (
        cohorts["own_history_ready_current_fresh"] + len(broader_ready)
    )
    summary = {
        "outcome": "REHEARSED_NOT_DEPLOYED",
        "as_of_date": as_of_date,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "model_fingerprint": MODEL_FINGERPRINT,
        "source_fingerprint": snapshot.source_fingerprint,
        "result_fingerprint": snapshot.result_fingerprint,
        "calculation_seconds": calculation_seconds,
        "migration": migration,
        "first_apply": first.__dict__,
        "first_apply_seconds": first_seconds,
        "first_apply_peak_sidecar_bytes": first_peak,
        "second_apply": second.__dict__,
        "second_apply_seconds": second_seconds,
        "second_apply_peak_sidecar_bytes": second_peak,
        "cohorts": cohorts,
        "hubg": {
            "current_fresh": hubg.current_fresh,
            "endpoint": f"{hubg.current_valuation.get('fiscal_year')} {hubg.current_valuation.get('fiscal_quarter')}",
            "endpoint_available_date": hubg.endpoint_available_date,
            "fundamental_age_days": (
                date.fromisoformat(as_of_date) - date.fromisoformat(hubg.endpoint_available_date)
            ).days,
            "broader_only_ready_tickers": broader_ready,
        },
        "deep_check": deep,
        "storage": storage,
        "object_storage": object_storage,
        "reader_latency": latency,
        "retention_reports": retention_reports,
        "retention_storage": retention_storage,
        "retention_check": retention_check,
        "failure_injection": failure_results,
        "date_cases": date_cases,
        "report_checks": report_checks,
    }
    _write_json(output_dir / "phase11c_rehearsal_summary.json", summary)
    _write_json(output_dir / "failure_injection_results.json", failure_results)
    _write_json(output_dir / "storage_measurements.json", {
        "stages": storage, "objects": object_storage, "retention": retention_storage,
    })
    _write_json(output_dir / "reader_latency.json", latency)
    return summary
