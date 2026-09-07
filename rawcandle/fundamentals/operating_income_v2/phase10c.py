from __future__ import annotations

import argparse
import fcntl
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.ui_service import (
    FundamentalsSnapshotUIService,
    resolve_report_download,
)

from . import activation, diagnostic_flags, diagnostic_flags_eight, phase10b, phase9e
from .phase9d import PRODUCTION, compare_production_integrity, production_integrity
from .pipeline import refresh_active_package
from .readers import ActiveModelRepository, ParallelModelRepository


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BACKUP_DIR = ROOT / "backups"
LOCK_PATH = phase9e.LOCK_PATH
ROLLBACK_PACKAGE = "a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d"
LOCKED_PACKAGE = "0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30"
LOCKED_DIAGNOSTIC = "0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904"
LOCKED_SNAPSHOT = "f04e5dedf0cadecbd6039eabdcfc16d77a17b8cce729a63a810df7914d352a11"
LOCKED_LAYOUT = "d2040687f976f6e3807f5de6b2022a384bedeee02eb8d5294e98101b3fe06979"
LOCKED_SOURCE = "ae75df9522de07ea2113f505d32f06dc4b112057c1cd74ac103af3b89b6414df"
LOCKED_DIAGNOSTIC_ECONOMIC = "a3dde822dbfff98081d50fd4dd7534ee346b31cc74d75d3a40a1d91c45aeff5d"
LOCKED_DIAGNOSTIC_PHYSICAL = "7f4ea56523a403a2789a4f74977301a299bc4941228b205fe84c820adc36f8bf"
LOCKED_PACKAGE_ECONOMIC = "da43d4f0c466c06dbf7a7777ae8e92d2f69b5fb7d27d5280345cb76c92be69fb"
LOCKED_PACKAGE_PHYSICAL = "d0b39ac2b568623e59b50288ebe304fa169f99830d615715b69a68b492f4b362"
EXPECTED_MODELS = {name: fingerprint for name, (_version, fingerprint) in phase10b.MODEL_MAP.items()}
DATABASE_TYPES = phase9e.DATABASE_TYPES
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_non_operating_gap_phase10c"


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _identity_gate() -> None:
    actual = {
        "package": phase10b.PACKAGE_FINGERPRINT,
        "diagnostic": diagnostic_flags_eight.MODEL_FINGERPRINT,
        "snapshot": phase10b.snapshot_eight.MODEL_FINGERPRINT,
        "layout": phase10b.persistence._hash({
            flag: diagnostic_flags_eight.EVIDENCE_FIELDS[flag]
            for flag in sorted(diagnostic_flags_eight.FLAG_NAMES)
        }),
    }
    expected = {
        "package": LOCKED_PACKAGE,
        "diagnostic": LOCKED_DIAGNOSTIC,
        "snapshot": LOCKED_SNAPSHOT,
        "layout": LOCKED_LAYOUT,
    }
    if actual != expected:
        raise RuntimeError(f"PHASE10C_SOURCE_IDENTITY_MISMATCH:{actual}")


def _has_symlink_component(path: Path) -> bool:
    current = path.absolute()
    while current != current.parent:
        if current.exists() and current.is_symlink():
            return True
        current = current.parent
    return current.is_symlink()


def _require_child_path(path: Path, parent: Path, error: str) -> None:
    if not path.is_absolute() or _has_symlink_component(path):
        raise PermissionError(error)
    resolved_parent = parent.resolve()
    resolved = path.resolve()
    if resolved == resolved_parent or resolved_parent not in resolved.parents:
        raise PermissionError(error)


def validate_request(args: argparse.Namespace) -> None:
    _identity_gate()
    resolved_production = {path.resolve() for path in PRODUCTION.values()}
    for name, expected in PRODUCTION.items():
        supplied = getattr(args, f"{name}_db")
        if (
            not supplied.is_absolute()
            or _has_symlink_component(supplied)
            or supplied.resolve() != expected.resolve()
        ):
            raise PermissionError(f"PHASE10C_EXACT_PRODUCTION_{name.upper()}_PATH_REQUIRED")
        if not supplied.is_file() or supplied.resolve() not in resolved_production:
            raise FileNotFoundError(supplied)
        with sqlite3.connect(f"file:{supplied.resolve()}?mode=ro", uri=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
                (DATABASE_TYPES[name],),
            ).fetchone():
                raise ValueError(f"PHASE10C_WRONG_{name.upper()}_DATABASE_TYPE")
    if args.analysis_db.resolve() in {
        args.canonical_db.resolve(), args.provider_db.resolve(), args.market_db.resolve(),
        args.taxonomy_db.resolve(),
    }:
        raise PermissionError("PHASE10C_ANALYSIS_DESTINATION_COLLIDES_WITH_SOURCE")
    if not args.full_universe:
        raise ValueError("PHASE10C_FULL_UNIVERSE_REQUIRED")
    if args.package_fingerprint != LOCKED_PACKAGE:
        raise ValueError("PHASE10C_PACKAGE_FINGERPRINT_MISMATCH")
    supplied_models = {
        "score": args.score_fingerprint,
        "lifecycle": args.lifecycle_fingerprint,
        "valuation": args.valuation_fingerprint,
        "delta": args.delta_fingerprint,
        "relative_position": args.relative_fingerprint,
        "diagnostic_flags": args.diagnostic_fingerprint,
        "snapshot": args.snapshot_fingerprint,
    }
    if supplied_models != EXPECTED_MODELS:
        raise ValueError("PHASE10C_MODEL_PACKAGE_MISMATCH")
    if args.expected_active_package not in {ROLLBACK_PACKAGE, LOCKED_PACKAGE}:
        raise ValueError("PHASE10C_EXPECTED_ACTIVE_PACKAGE_REJECTED")
    output = getattr(args, "output", None)
    if output is not None:
        _require_child_path(output, ARTIFACT_ROOT, "PHASE10C_OUTPUT_PATH_REJECTED")
    backup_dir = getattr(args, "backup_dir", DEFAULT_BACKUP_DIR)
    if (
        not backup_dir.is_absolute()
        or _has_symlink_component(backup_dir)
        or backup_dir.resolve() != DEFAULT_BACKUP_DIR.resolve()
    ):
        raise PermissionError("PHASE10C_BACKUP_PATH_REJECTED")
    if args.apply and not args.confirm_production:
        raise PermissionError("PHASE10C_PRODUCTION_CONFIRMATION_REQUIRED")
    if args.apply and _git("status", "--porcelain"):
        raise RuntimeError("PHASE10C_CLEAN_GIT_WORKTREE_REQUIRED")


def _active_state(connection: sqlite3.Connection) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    active = activation.assert_v2_active(connection)
    manifests = [
        dict(row) for row in connection.execute(
            "SELECT persistence_fingerprint,family_fingerprint,family_version,persistence_version,"
            "model_manifest_json,economic_result_fingerprint,physical_content_fingerprint,status,applied_at_utc "
            "FROM operating_income_v2_package_manifest_history ORDER BY applied_at_utc,persistence_fingerprint"
        )
    ]
    return {"active": active.__dict__, "model_map": activation.active_model_manifest(connection), "manifest_history": manifests}


def _validate_calculation(calculated: Mapping[str, Any]) -> dict[str, Any]:
    phase10b._validate(calculated)
    distribution = __import__(
        "rawcandle.fundamentals.operating_income_v2.phase10b_rehearsal",
        fromlist=["_distribution"],
    )._distribution(calculated)
    diagnostic_economic = phase10b.persistence._hash(calculated["diagnostics_full"])
    package_economic = phase10b.persistence.economic_fingerprint(calculated)
    gates = {
        "diagnostic_source": calculated["diagnostic_source_fingerprint"],
        "diagnostic_economic": diagnostic_economic,
        "package_economic": package_economic,
        "endpoints": len(calculated["rows"]),
        "evaluations": len(calculated["diagnostics_full"]),
        "distribution": distribution,
    }
    if (
        gates["diagnostic_source"] != LOCKED_SOURCE
        or diagnostic_economic != LOCKED_DIAGNOSTIC_ECONOMIC
        or package_economic != LOCKED_PACKAGE_ECONOMIC
        or gates["endpoints"] != 50_585
        or gates["evaluations"] != 404_680
    ):
        raise RuntimeError(f"PHASE10C_CALCULATION_GATE_FAILED:{gates}")
    current = distribution["current_fresh"]
    union = distribution["union"]
    historical = distribution["historical"]
    observed = (
        historical["evaluable"], historical["flagged"], current["evaluable"],
        current["flagged"], current["directions"].get("UPLIFT"),
        current["directions"].get("DRAG"), union["overlap"],
        union["newly_flagged"], union["combined"],
    )
    if observed != (36_893, 5_319, 2_110, 334, 230, 104, 226, 108, 531):
        raise RuntimeError(f"PHASE10C_DISTRIBUTION_GATE_FAILED:{observed}")
    references = __import__(
        "rawcandle.fundamentals.operating_income_v2.phase10b_rehearsal",
        fromlist=["_reference_cases"],
    )._reference_cases(calculated)
    expected_references = {
        "NVDA": (32_628_000_000.0, 0.10769418653393581, "UPLIFT"),
        "AMZN": (84_515_000_000.0, 0.10895601278877888, "UPLIFT"),
        "GOOG": (152_615_000_000.0, 0.3422881711362357, "UPLIFT"),
    }
    for ticker, (amount, ratio, direction) in expected_references.items():
        row = references[ticker]
        if (
            row["status"] != "EVALUATED_FLAGGED"
            or row["gap_direction"] != direction
            or row["gap_amount"] != amount
            or row["gap_abs_to_revenue"] != ratio
        ):
            raise RuntimeError(f"PHASE10C_REFERENCE_GATE_FAILED:{ticker}:{row}")
    gates["references"] = references
    return gates


def _backup(source: Path, backup_dir: Path, stamp: str) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"fundamentals_analysis.phase10c.{stamp}.db"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as reader:
        with sqlite3.connect(destination) as writer:
            reader.backup(writer)
    if destination.is_symlink() or not destination.is_file():
        raise RuntimeError("PHASE10C_BACKUP_NOT_REGULAR_FILE")
    with sqlite3.connect(f"file:{destination.resolve()}?mode=ro", uri=True) as connection:
        state = _active_state(connection)
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign = list(connection.execute("PRAGMA foreign_key_check"))
        old_endpoints = connection.execute(
            "SELECT COUNT(*) FROM diagnostic_flag_endpoint e JOIN diagnostic_flag_package p USING(package_id) "
            "WHERE p.model_fingerprint=?", (diagnostic_flags.MODEL_FINGERPRINT,),
        ).fetchone()[0]
        old_evaluations = connection.execute(
            "SELECT COUNT(*) FROM diagnostic_flag_evaluation v JOIN diagnostic_flag_endpoint e USING(endpoint_id) "
            "JOIN diagnostic_flag_package p USING(package_id) WHERE p.model_fingerprint=?",
            (diagnostic_flags.MODEL_FINGERPRINT,),
        ).fetchone()[0]
    if quick != "ok" or foreign or state["active"]["persistence_fingerprint"] not in {ROLLBACK_PACKAGE, LOCKED_PACKAGE}:
        raise RuntimeError("PHASE10C_BACKUP_INTEGRITY_FAILED")
    if old_endpoints != 50_585 or old_evaluations != 354_095:
        raise RuntimeError("PHASE10C_BACKUP_ROLLBACK_PACKAGE_INCOMPLETE")
    return {
        "path": str(destination.resolve()), "size": destination.stat().st_size,
        "sha256": phase9e._sha256(destination), "quick_check": quick,
        "foreign_key_check": foreign, "active_state": state,
        "old_diagnostic_endpoints": old_endpoints,
        "old_diagnostic_evaluations": old_evaluations,
        "independently_openable": True,
    }


def _smoke_reports(calculated: Mapping[str, Any], output: Path) -> dict[str, Any]:
    report_paths = SnapshotPaths(
        PRODUCTION["canonical"], PRODUCTION["analysis"], PRODUCTION["market"],
        PRODUCTION["taxonomy"], PRODUCTION["provider"],
    )
    new_rows = [
        row for row in calculated["diagnostics"]
        if row["flag_name"] == diagnostic_flags_eight.FLAG_NAME
    ]
    tickers = ["NVDA", "AMZN", "GOOG"]
    tickers.append(next(row["ticker"] for row in new_rows if row["status"] == "EVALUATED_FLAGGED" and row["evidence"]["gap_direction"] == "DRAG"))
    tickers.append(next(row["ticker"] for row in new_rows if row["status"] == "EVALUATED_CLEAR"))
    tickers.append(next(row["ticker"] for row in new_rows if row["status"] == "FLAG_NOT_READY"))
    tickers.append(next(row["ticker"] for row in new_rows if row["status"] == "FLAG_NOT_APPLICABLE"))
    report_dir = output / "company_snapshots_v2"
    results = []
    for ticker in dict.fromkeys(tickers):
        generated = generate_active_company_snapshot(
            report_paths, ticker=ticker, report_date="2026-09-06", output_dir=report_dir
        )
        markdown = Path(generated["output_path"]).read_text(encoding="utf-8")
        required = (
            "### Kaikki kahdeksan statusta", "Non-Operating Earnings Gap",
            "Reported Common Earnings", "≥ 10%",
        )
        if len(generated["snapshot"]["diagnostic"]["evaluations"]) != 8 or not all(value in markdown for value in required):
            raise RuntimeError(f"PHASE10C_SNAPSHOT_SMOKE_FAILED:{ticker}")
        gap_lines = [line.lower() for line in markdown.splitlines() if "non-operating earnings gap" in line.lower()]
        if any(term in line for line in gap_lines for term in ("investment gain", "data error")):
            raise RuntimeError(f"PHASE10C_GAP_CAUSE_INFERENCE_RENDERED:{ticker}")
        if any(value in markdown for value in ("company_id", "quarter_id", "endpoint_id", "package_id")):
            raise RuntimeError(f"PHASE10C_INTERNAL_ID_RENDERED:{ticker}")
        results.append({
            "ticker": ticker, "status": generated["status"],
            "content_fingerprint": generated["report_content_fingerprint"],
            "path": generated["output_path"],
        })

    ui_dir = output / "ui_smoke"
    service = FundamentalsSnapshotUIService(paths=report_paths, output_dir=ui_dir)
    batch = service.generate_batch(
        ticker_input="NVDA, AMZN, ZZZZZPHASE10C", report_date_input="2026-09-06"
    )
    successful = [item for item in batch.results if item.status in {"GENERATED", "NO_CHANGE"}]
    download = resolve_report_download(successful[0].filename, ui_dir)
    traversal_rejected = symlink_rejected = False
    try:
        resolve_report_download("../fundamentals_analysis.db", ui_dir)
    except (ValueError, FileNotFoundError):
        traversal_rejected = True
    alias = ui_dir / "outside.md"
    alias.symlink_to(PRODUCTION["analysis"])
    try:
        resolve_report_download(alias.name, ui_dir)
    except (ValueError, FileNotFoundError):
        symlink_rejected = True
    alias.unlink()
    if len(successful) != 2 or not traversal_rejected or not symlink_rejected or not download.is_file():
        raise RuntimeError("PHASE10C_UI_SMOKE_FAILED")
    return {
        "reports": results, "batch_status": batch.status,
        "created_or_unchanged": len(successful),
        "not_generated": batch.summary.not_generated,
        "recent_reports": len(service.recent_reports()),
        "secure_download": True, "traversal_rejected": traversal_rejected,
        "symlink_rejected": symlink_rejected,
    }


def _reader_reconciliation(
    connection: sqlite3.Connection,
    calculated: Mapping[str, Any],
    *,
    require_active: bool,
) -> dict[str, Any]:
    module = __import__(
        "rawcandle.fundamentals.operating_income_v2.phase10b_rehearsal",
        fromlist=["_reader_reconciliation"],
    )
    result = module._reader_reconciliation(connection, calculated)
    if result["differences"]:
        raise RuntimeError("PHASE10C_READER_RECONCILIATION_FAILED")
    result["default_active_diagnostic"] = None
    if require_active:
        active = ActiveModelRepository(connection)
        nvda = connection.execute(
            "SELECT company_id FROM lifecycle_revised_result WHERE ticker='NVDA' "
            "AND model_fingerprint=? LIMIT 1", (phase10b.MODEL_MAP["lifecycle"][1],),
        ).fetchone()[0]
        current = active.diagnostic_current(int(nvda))
        if active.model_fingerprints["diagnostic"] != LOCKED_DIAGNOSTIC or len(current["evaluations"]) != 8:
            raise RuntimeError("PHASE10C_DEFAULT_READER_FAILED")
        result["default_active_diagnostic"] = active.model_fingerprints["diagnostic"]
    return result


def _rollback_rehearsal(source: Path, output: Path) -> dict[str, Any]:
    destination = output / "activation_rollback_rehearsal.db"
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as reader:
        with sqlite3.connect(destination) as writer:
            reader.backup(writer)
    with sqlite3.connect(destination) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        old = activation.activate_package(connection, ROLLBACK_PACKAGE, activated_at="PHASE10C_ROLLBACK_TEST")
        connection.commit()
        old_rows = ParallelModelRepository(connection).diagnostic_all(
            model_fingerprint=diagnostic_flags.MODEL_FINGERPRINT
        )
        old_active = ActiveModelRepository(connection)
        old_manifest = dict(old_active.model_fingerprints)
        rehearsal_paths = SnapshotPaths(
            PRODUCTION["canonical"], destination, PRODUCTION["market"],
            PRODUCTION["taxonomy"], PRODUCTION["provider"],
        )
        old_snapshot = generate_active_company_snapshot(
            rehearsal_paths, ticker="NVDA", report_date="2026-09-06",
            output_dir=output / "rollback_old_snapshot",
        )
        connection.execute("BEGIN IMMEDIATE")
        new = activation.activate_package(connection, LOCKED_PACKAGE, activated_at="PHASE10C_REACTIVATION_TEST")
        connection.commit()
        new_rows = ParallelModelRepository(connection).diagnostic_all(
            model_fingerprint=diagnostic_flags_eight.MODEL_FINGERPRINT
        )
        new_active = ActiveModelRepository(connection)
        new_manifest = dict(new_active.model_fingerprints)
        new_snapshot = generate_active_company_snapshot(
            rehearsal_paths, ticker="NVDA", report_date="2026-09-06",
            output_dir=output / "rollback_new_snapshot",
        )
    if len(old_rows) != 50_585 or any(len(row["evaluations"]) != 7 for row in old_rows):
        raise RuntimeError("PHASE10C_ROLLBACK_OLD_PACKAGE_FAILED")
    if len(new_rows) != 50_585 or any(len(row["evaluations"]) != 8 for row in new_rows):
        raise RuntimeError("PHASE10C_ROLLBACK_REACTIVATION_FAILED")
    if old_manifest["diagnostic"] != diagnostic_flags.MODEL_FINGERPRINT:
        raise RuntimeError("PHASE10C_ROLLBACK_ACTIVE_READER_FAILED")
    if new_manifest["diagnostic"] != diagnostic_flags_eight.MODEL_FINGERPRINT:
        raise RuntimeError("PHASE10C_REACTIVATION_ACTIVE_READER_FAILED")
    if len(old_snapshot["snapshot"]["diagnostic"]["evaluations"]) != 7:
        raise RuntimeError("PHASE10C_ROLLBACK_SNAPSHOT_FAILED")
    if len(new_snapshot["snapshot"]["diagnostic"]["evaluations"]) != 8:
        raise RuntimeError("PHASE10C_REACTIVATION_SNAPSHOT_FAILED")
    return {
        "copy": str(destination), "old_activation": old.__dict__,
        "old_active_model_manifest": old_manifest,
        "old_snapshot": old_snapshot["report_content_fingerprint"],
        "old_endpoints": len(old_rows), "old_evaluations": sum(len(row["evaluations"]) for row in old_rows),
        "new_activation": new.__dict__, "new_endpoints": len(new_rows),
        "new_active_model_manifest": new_manifest,
        "new_snapshot": new_snapshot["report_content_fingerprint"],
        "new_evaluations": sum(len(row["evaluations"]) for row in new_rows),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    validate_request(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or ARTIFACT_ROOT / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = production_integrity()
    reports_before = phase9e._report_inventory()
    with sqlite3.connect(f"file:{PRODUCTION['analysis'].resolve()}?mode=ro", uri=True) as connection:
        state_before = _active_state(connection)
    if state_before["active"]["persistence_fingerprint"] != args.expected_active_package:
        raise RuntimeError("PHASE10C_UNEXPECTED_ACTIVE_PACKAGE")
    process = phase9e._process_inventory()
    disk = phase9e._disk_gate(args.backup_dir.resolve(), output)
    calculated = phase10b.calculate(PRODUCTION)
    calculation = _validate_calculation(calculated)
    preflight = {
        "git_head": _git("rev-parse", "HEAD"), "git_status": _git("status", "--porcelain"),
        "paths": {name: str(path.resolve()) for name, path in PRODUCTION.items()},
        "expected_active_package": args.expected_active_package,
        "candidate_package": LOCKED_PACKAGE, "models": EXPECTED_MODELS,
        "process": process, "disk": disk, "active_state": state_before,
        "database_inventory": before,
    }
    _json(output / "preflight.json", preflight)
    _json(output / "dry_run.json", {"writes": False, **calculation})
    if not args.apply:
        return {"mode": "DRY_RUN", "output": str(output), **calculation}

    phase9e._assert_write_lock_available(PRODUCTION["analysis"])
    lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_handle.close()
        raise RuntimeError("PHASE10C_MAINTENANCE_LOCK_HELD") from error

    activated = False
    previous_row: tuple[Any, ...] | None = None
    backup = None
    try:
        is_first_deployment = args.expected_active_package == ROLLBACK_PACKAGE
        if is_first_deployment:
            backup = _backup(PRODUCTION["analysis"], args.backup_dir.resolve(), stamp)
            _json(output / "backup_manifest.json", backup)
        analysis_before_apply = production_integrity()["analysis"]
        with sqlite3.connect(PRODUCTION["analysis"]) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            previous = connection.execute(
                "SELECT * FROM fundamentals_active_model_family WHERE singleton=1"
            ).fetchone()
            previous_row = tuple(previous) if previous else None
            v1_before = phase9e._v1_state(connection)
            first = phase10b.apply_candidate_package(connection, calculated, applied_at=stamp)
            validation = phase10b.validate_candidate_package(connection)
            if (
                first.diagnostic_source_fingerprint != LOCKED_SOURCE
                or first.diagnostic_economic_fingerprint != LOCKED_DIAGNOSTIC_ECONOMIC
                or first.diagnostic_physical_fingerprint != LOCKED_DIAGNOSTIC_PHYSICAL
                or first.economic_result_fingerprint != LOCKED_PACKAGE_ECONOMIC
                or first.physical_content_fingerprint != LOCKED_PACKAGE_PHYSICAL
            ):
                raise RuntimeError("PHASE10C_PERSISTED_IDENTITY_MISMATCH")
            explicit_reader = _reader_reconciliation(
                connection, calculated, require_active=False
            )
            if phase9e._v1_state(connection) != v1_before:
                raise RuntimeError("PHASE10C_V1_STATE_CHANGED")
            if is_first_deployment:
                connection.execute("BEGIN IMMEDIATE")
                active = activation.activate_package(connection, LOCKED_PACKAGE, activated_at=stamp)
                connection.commit()
                activated = True
            else:
                active = activation.assert_v2_active(connection)
            reader = _reader_reconciliation(connection, calculated, require_active=True)

        ui = _smoke_reports(calculated, output)
        pipeline = refresh_active_package(PRODUCTION)
        if pipeline["outcome"] != "NO_CHANGE" or pipeline["logical_changes"]:
            raise RuntimeError("PHASE10C_PIPELINE_NOT_NO_CHANGE")
        rollback = _rollback_rehearsal(PRODUCTION["analysis"], output) if is_first_deployment else None
        after = production_integrity()
        reports_after = phase9e._report_inventory()
        source_comparison = compare_production_integrity(
            {name: value for name, value in before.items() if name != "analysis"},
            {name: value for name, value in after.items() if name != "analysis"},
        )
        if source_comparison["differences"] or reports_before != reports_after:
            raise RuntimeError("PHASE10C_UNAUTHORIZED_PRODUCTION_CHANGE")
        if not is_first_deployment and after["analysis"] != analysis_before_apply:
            raise RuntimeError("PHASE10C_SECOND_COMMAND_NOT_BYTE_NOOP")
        result = {
            "mode": "APPLIED_AND_ACTIVATED" if is_first_deployment else "NO_CHANGE",
            "output": str(output), "backup": backup, "apply": first.__dict__,
            "validation": validation, "active": active.__dict__, "reader": reader,
            "pre_activation_explicit_reader": explicit_reader, "ui": ui,
            "pipeline": pipeline, "rollback_rehearsal": rollback,
            "distribution": calculation["distribution"],
            "database_before": before, "database_after": after,
            "source_comparison": source_comparison,
            "existing_reports_unchanged": reports_before == reports_after,
        }
        _json(output / "deployment_result.json", result)
        _json(output / "commands_run.json", {"argv": __import__("sys").argv})
        return result
    except Exception:
        if activated and previous_row is not None:
            with sqlite3.connect(PRODUCTION["analysis"]) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT OR REPLACE INTO fundamentals_active_model_family VALUES(?,?,?,?,?,?)",
                    previous_row,
                )
                activation.assert_v2_active(connection)
                connection.commit()
        raise
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy the eight-flag Diagnostic V2 package")
    for name, path in PRODUCTION.items():
        parser.add_argument(f"--{name}-db", type=Path, default=path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--package-fingerprint", required=True)
    parser.add_argument("--expected-active-package", required=True)
    parser.add_argument("--score-fingerprint", required=True)
    parser.add_argument("--lifecycle-fingerprint", required=True)
    parser.add_argument("--valuation-fingerprint", required=True)
    parser.add_argument("--delta-fingerprint", required=True)
    parser.add_argument("--relative-fingerprint", required=True)
    parser.add_argument("--diagnostic-fingerprint", required=True)
    parser.add_argument("--snapshot-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(run(args), indent=2, sort_keys=True, allow_nan=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
