from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from rawcandle.fundamentals.relative_position.source import (
    ReadOnlySourcePaths,
    build_identity_index,
    load_current_relative_source,
    resolve_taxonomy_ticker,
)
from rawcandle.testing.database_isolation import (
    PROTECTED_DATABASE_ROLES,
    capture_file_state,
)


LOGICAL_TABLES = {
    "analysis_classification": (
        "analysis_findings",
        "ec_ecosystem",
        "ec_taxonomy_version",
        "ec_entity",
        "ec_entity_alias",
        "ec_membership",
    ),
    "market_data": ("ticker_meta",),
    "fundamentals_analysis": (
        "fundamentals_active_model_family",
        "operating_income_v2_package_manifest",
    ),
}

SCAN_EXCLUDES = {".git", ".venv", "venv", "temp", "backups", "__pycache__"}

EXPECTED_ACTIVE_PACKAGE = "0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30"
EXPECTED_ARCHIVED_PACKAGE = "a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d"


def _sha_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _schema_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE sql IS NOT NULL ORDER BY type,name"
        )
    ]


def _table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _logical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"blob_hex": value.hex()}
    if isinstance(value, float):
        return {"binary64_hex": value.hex()}
    return value


def table_fingerprint(connection: sqlite3.Connection, table: str) -> str:
    columns = [dict(row) for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")]
    names = [str(row["name"]) for row in columns]
    primary = [
        str(row["name"])
        for row in sorted(columns, key=lambda item: int(item["pk"]))
        if int(row["pk"]) > 0
    ]
    order = primary or names
    select = ",".join(_quote_identifier(name) for name in names)
    order_by = ",".join(_quote_identifier(name) for name in order)
    digest = hashlib.sha256()
    for row in connection.execute(
        f"SELECT {select} FROM {_quote_identifier(table)} ORDER BY {order_by}"
    ):
        values = [_logical_value(row[name]) for name in names]
        digest.update(
            json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def database_inventory(role: str, configured_path: Path) -> dict[str, Any]:
    resolved = configured_path.resolve(strict=True)
    configured_lstat = configured_path.lstat()
    main = capture_file_state(resolved)
    result: dict[str, Any] = {
        "role": role,
        "configured_path": str(configured_path),
        "resolved_path": str(resolved),
        "file_type": "regular" if stat.S_ISREG(configured_lstat.st_mode) else "other",
        "configured_is_symlink": configured_path.is_symlink(),
        "permissions": oct(stat.S_IMODE(configured_lstat.st_mode)),
        "main": main.__dict__,
        "wal": capture_file_state(Path(f"{resolved}-wal")).__dict__,
        "shm": capture_file_state(Path(f"{resolved}-shm")).__dict__,
    }
    with _readonly(resolved) as connection:
        schema = _schema_rows(connection)
        tables = _table_names(connection)
        result.update(
            {
                "schema_hash": _sha_json(schema),
                "page_size": int(connection.execute("PRAGMA page_size").fetchone()[0]),
                "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
                "freelist_count": int(connection.execute("PRAGMA freelist_count").fetchone()[0]),
                "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
                "quick_check": str(connection.execute("PRAGMA quick_check").fetchone()[0]),
                "foreign_key_check": [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")],
                "row_counts": {
                    table: int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
                        ).fetchone()[0]
                    )
                    for table in tables
                },
                "sequences": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT name,seq FROM sqlite_sequence ORDER BY name"
                    )
                ]
                if "sqlite_sequence" in {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table'"
                    )
                }
                else [],
                "logical_fingerprints": {
                    table: table_fingerprint(connection, table)
                    for table in LOGICAL_TABLES.get(role, ())
                    if table in tables
                },
            }
        )
    return result


def taxonomy_checks(repo_root: Path, *, as_of_date: str) -> dict[str, Any]:
    taxonomy = PROTECTED_DATABASE_ROLES["analysis_classification"]
    market = PROTECTED_DATABASE_ROLES["market_data"]
    canonical = PROTECTED_DATABASE_ROLES["fundamentals_canonical"]
    analysis = PROTECTED_DATABASE_ROLES["fundamentals_analysis"]
    with _readonly(taxonomy) as connection:
        duplicate_checks = {
            "ec_entity_identity": int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT ecosystem_id,entity_type,entity_code "
                    "FROM ec_entity GROUP BY 1,2,3 HAVING COUNT(*)>1)"
                ).fetchone()[0]
            ),
            "ec_membership_identity": int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT taxonomy_version_id,parent_entity_id,"
                    "child_entity_id,membership_type FROM ec_membership GROUP BY 1,2,3,4 "
                    "HAVING COUNT(*)>1)"
                ).fetchone()[0]
            ),
        }
        orphan_checks = {
            "ec_entity_ecosystem": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ec_entity child LEFT JOIN ec_ecosystem parent "
                    "ON parent.ecosystem_id=child.ecosystem_id "
                    "WHERE parent.ecosystem_id IS NULL"
                ).fetchone()[0]
            ),
            "ec_entity_alias_entity": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ec_entity_alias child LEFT JOIN ec_entity parent "
                    "ON parent.entity_id=child.entity_id WHERE parent.entity_id IS NULL"
                ).fetchone()[0]
            ),
            "ec_membership_ecosystem": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ec_membership child LEFT JOIN ec_ecosystem parent "
                    "ON parent.ecosystem_id=child.ecosystem_id "
                    "WHERE parent.ecosystem_id IS NULL"
                ).fetchone()[0]
            ),
            "ec_membership_taxonomy_version": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ec_membership child "
                    "LEFT JOIN ec_taxonomy_version parent "
                    "ON parent.taxonomy_version_id=child.taxonomy_version_id "
                    "WHERE parent.taxonomy_version_id IS NULL"
                ).fetchone()[0]
            ),
            "ec_membership_parent_entity": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ec_membership child LEFT JOIN ec_entity parent "
                    "ON parent.entity_id=child.parent_entity_id "
                    "WHERE parent.entity_id IS NULL"
                ).fetchone()[0]
            ),
            "ec_membership_child_entity": int(
                connection.execute(
                    "SELECT COUNT(*) FROM ec_membership child LEFT JOIN ec_entity parent "
                    "ON parent.entity_id=child.child_entity_id "
                    "WHERE parent.entity_id IS NULL"
                ).fetchone()[0]
            ),
        }
        incident_state = {
            "analysis_findings_count": int(
                connection.execute("SELECT COUNT(*) FROM analysis_findings").fetchone()[0]
            ),
            "analysis_findings_max_id": int(
                connection.execute("SELECT MAX(id) FROM analysis_findings").fetchone()[0]
            ),
            "analysis_findings_sequence": int(
                connection.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name='analysis_findings'"
                ).fetchone()[0]
            ),
            "phase10c_accidental_row_present": bool(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_findings WHERE id=4711711 "
                    "AND ticker='HRB' AND date='2018-12-24' AND pattern='downtrend' "
                    "AND created_at='2026-09-07 21:28:55'"
                ).fetchone()[0]
            ),
        }
        ecosystem_examples = [
            dict(row)
            for row in connection.execute(
                "SELECT e.ecosystem_code,t.ticker,m.membership_role,m.is_primary "
                "FROM ec_membership m JOIN ec_ecosystem e ON e.ecosystem_id=m.ecosystem_id "
                "JOIN ec_entity t ON t.entity_id=m.child_entity_id "
                "WHERE t.ticker IN ('NVDA','AMZN','VRT') AND m.status='ACTIVE' "
                "ORDER BY t.ticker,m.membership_id"
            )
        ]
    with _readonly(market) as connection:
        classifications = [
            dict(row)
            for row in connection.execute(
                "SELECT ticker,sector,industry FROM ticker_meta "
                "WHERE ticker IN ('NVDA','AMZN','VRT') ORDER BY ticker"
            )
        ]
    identity = build_identity_index(canonical)
    identity_examples = {
        ticker: resolve_taxonomy_ticker(ticker, identity)
        for ticker in ("NVDA", "AMZN", "VRT")
    }
    relative = load_current_relative_source(
        ReadOnlySourcePaths(
            analysis_db=analysis,
            canonical_db=canonical,
            market_db=market,
            taxonomy_db=taxonomy,
        ),
        as_of_date=as_of_date,
    )
    return {
        "duplicate_checks": duplicate_checks,
        "orphan_checks": orphan_checks,
        "incident_state": incident_state,
        "classifications": classifications,
        "ecosystem_examples": ecosystem_examples,
        "identity_examples": identity_examples,
        "relative_position_source": {
            "observation_count": len(relative.observations),
            "classification_fingerprint": relative.classification_fingerprint,
            "taxonomy_fingerprint": relative.taxonomy_fingerprint,
            "taxonomy_audit_count": len(relative.taxonomy_audit),
            "metadata": relative.metadata,
        },
        "repository_root": str(repo_root),
    }


def production_invariants(repo_root: Path) -> dict[str, Any]:
    analysis = PROTECTED_DATABASE_ROLES["fundamentals_analysis"]
    diagnostic_model = "0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904"
    with _readonly(analysis) as connection:
        active = dict(
            connection.execute(
                "SELECT family_version,family_fingerprint,persistence_fingerprint,"
                "model_manifest_json,activated_at_utc FROM fundamentals_active_model_family "
                "WHERE singleton=1"
            ).fetchone()
        )
        package = dict(
            connection.execute(
                "SELECT package_id,model_version,model_fingerprint,endpoint_count,"
                "evaluation_count,economic_result_fingerprint,physical_content_fingerprint "
                "FROM diagnostic_flag_package WHERE model_fingerprint=?",
                (diagnostic_model,),
            ).fetchone()
        )
        package_id = int(package["package_id"])
        actual_endpoints = int(
            connection.execute(
                "SELECT COUNT(*) FROM diagnostic_flag_endpoint WHERE package_id=?",
                (package_id,),
            ).fetchone()[0]
        )
        actual_evaluations = int(
            connection.execute(
                "SELECT COUNT(*) FROM diagnostic_flag_evaluation v "
                "JOIN diagnostic_flag_endpoint e ON e.endpoint_id=v.endpoint_id "
                "WHERE e.package_id=?",
                (package_id,),
            ).fetchone()[0]
        )
        wrong_evaluation_cardinality = int(
            connection.execute(
                "SELECT COUNT(*) FROM (SELECT e.endpoint_id,COUNT(v.flag_id) count "
                "FROM diagnostic_flag_endpoint e LEFT JOIN diagnostic_flag_evaluation v "
                "ON v.endpoint_id=e.endpoint_id WHERE e.package_id=? "
                "GROUP BY e.endpoint_id HAVING count<>8)",
                (package_id,),
            ).fetchone()[0]
        )
        archived = dict(
            connection.execute(
                "SELECT persistence_fingerprint,status,applied_at_utc "
                "FROM operating_income_v2_package_manifest_history "
                "WHERE persistence_fingerprint=?",
                (EXPECTED_ARCHIVED_PACKAGE,),
            ).fetchone()
        )
    report_root = repo_root / "fundamental_reports"
    report_records = []
    if report_root.is_dir():
        for path in sorted(item for item in report_root.rglob("*") if item.is_file()):
            report_records.append(
                {
                    "path": str(path.relative_to(report_root)),
                    "size": path.stat().st_size,
                    "sha256": capture_file_state(path).sha256,
                }
            )
    return {
        "active_package": active,
        "candidate_diagnostic": {
            **package,
            "actual_endpoints": actual_endpoints,
            "actual_evaluations": actual_evaluations,
            "wrong_evaluation_cardinality": wrong_evaluation_cardinality,
        },
        "archived_package": archived,
        "fundamental_reports": {
            "file_count": len(report_records),
            "aggregate_fingerprint": _sha_json(report_records),
        },
    }


def _call_name(node: ast.Call) -> str:
    try:
        return ast.unparse(node.func)
    except Exception:
        return "UNKNOWN"


def _iter_python_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*.py"):
        if any(part in SCAN_EXCLUDES for part in path.relative_to(repo_root).parts):
            continue
        yield path


def connection_audit(repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _iter_python_files(repo_root):
        relative = path.relative_to(repo_root)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            kind = None
            if name.endswith("sqlite3.connect") or name in {"sqlite3.connect", "connect"}:
                kind = "SQLITE_CONNECT"
            elif name.endswith("DatabaseManager"):
                kind = "DATABASE_MANAGER"
            elif name.endswith(("subprocess.run", "subprocess.Popen", "subprocess.check_call", "subprocess.check_output")):
                kind = "SUBPROCESS"
            elif name.endswith("create_engine"):
                kind = "SQLALCHEMY"
            if kind is None:
                continue
            expression = ast.get_source_segment(source, node) or ast.dump(node, include_attributes=False)
            function = None
            parent = node
            while parent in parents:
                parent = parents[parent]
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function = parent
                    break
            function_name = function.name if function is not None else "<module>"
            function_args = {arg.arg for arg in function.args.args} if function is not None else set()
            lowered = expression.lower()
            if "mode=ro" in lowered or "_readonly" in name or "connect_readonly" in name:
                classification = "SAFE_READ_ONLY"
                reason = "SQLite read-only URI/helper is explicit"
            elif relative == Path("tests/test_production_database_isolation.py"):
                classification = "PRODUCTION_GUARDED"
                reason = "guard regression; real files are never mutated"
            elif "tests" in relative.parts and "tmp_path" in function_args:
                classification = "SAFE_TEMP_COPY"
                reason = "test function is rooted in pytest tmp_path"
            elif "tests" in relative.parts and kind == "SUBPROCESS":
                classification = "SAFE_TEMP_COPY"
                reason = "subprocess test is covered by inherited test guard and session inventory"
            elif "tests" in relative.parts:
                classification = "PRODUCTION_GUARDED"
                reason = "pytest process guard rejects protected writable targets; session inventory contains aliases"
            elif kind == "SQLALCHEMY":
                classification = "NOT_SQLITE"
                reason = "no supported SQLAlchemy SQLite production adapter discovered"
            elif kind == "SUBPROCESS":
                classification = "NOT_SQLITE"
                reason = "runtime subprocess entrypoint; pytest invocations inherit the SQLite guard"
            else:
                classification = "PRODUCTION_GUARDED"
                reason = "runtime-capable path; pytest process guard protects production targets"
            findings.append(
                {
                    "classification": classification,
                    "file": str(relative),
                    "line": int(node.lineno),
                    "function": function_name,
                    "mechanism": kind,
                    "expression": " ".join(expression.split()),
                    "possible_mutation": kind in {"SQLITE_CONNECT", "DATABASE_MANAGER"}
                    and classification != "SAFE_READ_ONLY",
                    "subprocess": kind == "SUBPROCESS",
                    "reason": reason,
                }
            )
    return sorted(findings, key=lambda row: (row["file"], row["line"], row["mechanism"]))


def write_connection_audit(path: Path, findings: list[dict[str, Any]]) -> None:
    fieldnames = (
        "classification",
        "file",
        "line",
        "function",
        "mechanism",
        "expression",
        "possible_mutation",
        "subprocess",
        "reason",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(findings)


def online_backup(source: Path, backup_dir: Path, timestamp: str) -> dict[str, Any]:
    source_size = source.stat().st_size
    free = shutil.disk_usage(backup_dir).free
    required = source_size * 2 + 5 * 1024**3
    if free < required:
        raise OSError(f"INSUFFICIENT_BACKUP_SPACE:free={free}:required={required}")
    destination = backup_dir / f"analysis.phase10c1.{timestamp}.db"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    source_connection = _readonly(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection, pages=4096, sleep=0.01)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    if not destination.is_file() or destination.is_symlink():
        raise OSError("BACKUP_NOT_REGULAR_FILE")
    inventory = database_inventory("analysis_classification", destination)
    if inventory["quick_check"] != "ok" or inventory["foreign_key_check"]:
        raise OSError("BACKUP_INTEGRITY_FAILED")
    return {
        "source": str(source),
        "destination": str(destination),
        "free_bytes_before": free,
        "required_bytes": required,
        "inventory": inventory,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit RawCandle production SQLite test isolation")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-date", default="2026-09-08")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--create-taxonomy-backup", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    inventory = {
        role: database_inventory(role, path)
        for role, path in PROTECTED_DATABASE_ROLES.items()
    }
    checks = taxonomy_checks(Path.cwd().resolve(), as_of_date=args.as_of_date)
    invariants = production_invariants(Path.cwd().resolve())
    findings = connection_audit(Path.cwd().resolve())
    payload = {
        "status": "LOGICALLY_VERIFIED_CURRENT_BASELINE",
        "captured_at_utc": timestamp,
        "inventory": inventory,
        "taxonomy_checks": checks,
        "production_invariants": invariants,
        "connection_audit_counts": {
            classification: sum(1 for row in findings if row["classification"] == classification)
            for classification in (
                "SAFE_READ_ONLY",
                "SAFE_TEMP_COPY",
                "PRODUCTION_GUARDED",
                "UNSAFE_REAL_PATH",
                "AMBIGUOUS",
                "NOT_SQLITE",
            )
        },
    }
    integrity_failures = [
        role
        for role, item in inventory.items()
        if item["quick_check"] != "ok" or item["foreign_key_check"]
    ]
    if integrity_failures:
        raise RuntimeError(f"DATABASE_INTEGRITY_FAILED:{','.join(integrity_failures)}")
    if checks["incident_state"]["phase10c_accidental_row_present"]:
        raise RuntimeError("PHASE10C_ACCIDENTAL_ROW_STILL_PRESENT")
    if any(checks["duplicate_checks"].values()):
        raise RuntimeError("TAXONOMY_DUPLICATE_IDENTITY")
    if any(checks["orphan_checks"].values()):
        raise RuntimeError("TAXONOMY_ORPHAN_RELATIONSHIP")
    if invariants["active_package"]["persistence_fingerprint"] != EXPECTED_ACTIVE_PACKAGE:
        raise RuntimeError("ACTIVE_PACKAGE_IDENTITY_CHANGED")
    if invariants["archived_package"]["persistence_fingerprint"] != EXPECTED_ARCHIVED_PACKAGE:
        raise RuntimeError("ARCHIVED_PACKAGE_IDENTITY_CHANGED")
    diagnostic = invariants["candidate_diagnostic"]
    if (
        diagnostic["actual_endpoints"] != 50_585
        or diagnostic["actual_evaluations"] != 404_680
        or diagnostic["wrong_evaluation_cardinality"] != 0
    ):
        raise RuntimeError("DIAGNOSTIC_PACKAGE_CARDINALITY_CHANGED")
    if any(checks["orphan_checks"].values()):
        raise RuntimeError("TAXONOMY_ORPHAN_RELATIONSHIP")
    (output / "production_database_inventory.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_connection_audit(output / "repository_write_path_audit.csv", findings)
    if args.create_taxonomy_backup:
        if args.backup_dir is None:
            raise ValueError("BACKUP_DIR_REQUIRED")
        backup = online_backup(
            PROTECTED_DATABASE_ROLES["analysis_classification"],
            args.backup_dir.resolve(strict=True),
            timestamp,
        )
        (output / "taxonomy_online_backup.json").write_text(
            json.dumps(backup, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps({"output": str(output), "status": payload["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
