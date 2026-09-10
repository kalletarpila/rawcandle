from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2 import (
    activation,
    contract as operating_contract,
    diagnostic_flags_eight,
    phase10b,
    persistence as operating_persistence,
)
from rawcandle.fundamentals.operating_income_v2.readers import (
    ActiveModelRepository,
    ParallelModelRepository,
)
from rawcandle.fundamentals.schema.contract import SHARADAR_ARQ_FIELD_MAPPING
from rawcandle.fundamentals.schema.production_bootstrap import ProductionPaths
from rawcandle.fundamentals.schema.provenance import (
    COMMON_EARNINGS_PROVENANCE_TABLE,
    LEGACY_PROVENANCE_TABLE,
    OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
    ensure_provenance_schema,
    write_provenance,
)
from rawcandle.fundamentals.schema.prototype import parse_fiscalperiod
from rawcandle.fundamentals.ttm.engine import (
    MODEL_VERSION as TTM_MODEL_VERSION,
    apply_ttm,
    canonical_financial_fingerprint,
    compute_ttm_rows,
    ensure_ttm_schema,
    load_canonical_rows,
)
from rawcandle.research.fundamental_profile_baseline.contract import (
    CONTRACT_FINGERPRINT as PHASE12B_CONTRACT_FINGERPRINT,
)
from rawcandle.research.fundamental_profile_baseline.runner import run as run_phase12b
from rawcandle.research.fundamental_profile_baseline.source import ResearchPaths


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = {
    "provider": ROOT / "data/fundamentals_provider.db",
    "canonical": ROOT / "data/fundamentals_v4.db",
    "analysis": ROOT / "data/fundamentals_analysis.db",
    "market": ROOT / "data/osakedata.db",
    "taxonomy": ROOT / "data/analysis.db",
}
REPORT_ROOT = ROOT / "fundamental_reports"
SCHEDULER_CONFIG = ROOT / "scheduler_config.json"
REBUILD_VERSION = "TEN_YEAR_OPERATIONAL_V4_REBUILD_REHEARSAL_V1"
REBUILD_CONTRACT = {
    "version": REBUILD_VERSION,
    "provider_policy": "SHARADAR_FUNDAMENTALS_HISTORY_POLICY_V1",
    "provider_policy_fingerprint": "1e025bf2a19d494cc1dd6ce3a0b49d94a966db008476f780c7e4dd671cd543b9",
    "scope": "append-only operational provider company identities only",
    "canonical": "latest accepted ARQ revision per company and fiscal identity",
    "ttm": TTM_MODEL_VERSION,
    "package": phase10b.MODEL_MAP,
    "phase12b_contract": PHASE12B_CONTRACT_FINGERPRINT,
    "history_semantics": "currently revised non-PIT",
}


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode("utf-8")
    ).hexdigest()


REBUILD_FINGERPRINT = stable_hash(REBUILD_CONTRACT)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _sidecar(path: Path, suffix: str) -> dict[str, Any]:
    sidecar = Path(str(path) + suffix)
    return {
        "exists": sidecar.exists(),
        "size": sidecar.stat().st_size if sidecar.exists() else None,
        "mtime_ns": sidecar.stat().st_mtime_ns if sidecar.exists() else None,
        "sha256": sha256(sidecar) if sidecar.exists() else None,
    }


def database_inventory(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with readonly(path) as connection:
        tables = [str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        )]
        row_counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
            if not table.startswith("sqlite_")
        }
        schema = [tuple(row) for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        )]
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        freelist = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    return {
        "path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256(path), "schema_fingerprint": stable_hash(schema),
        "row_counts": row_counts, "page_count": page_count, "freelist_count": freelist,
        "quick_check": quick, "foreign_key_errors": foreign,
        "wal": _sidecar(path, "-wal"), "shm": _sidecar(path, "-shm"),
    }


def production_inventory() -> dict[str, Any]:
    databases = {name: database_inventory(path) for name, path in PRODUCTION.items()}
    reports = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(REPORT_ROOT.glob("**/*")) if path.is_file()
    }
    scheduler = {
        "exists": SCHEDULER_CONFIG.exists(),
        "sha256": sha256(SCHEDULER_CONFIG) if SCHEDULER_CONFIG.exists() else None,
        "size": SCHEDULER_CONFIG.stat().st_size if SCHEDULER_CONFIG.exists() else None,
        "mtime_ns": SCHEDULER_CONFIG.stat().st_mtime_ns if SCHEDULER_CONFIG.exists() else None,
    }
    with readonly(PRODUCTION["analysis"]) as connection:
        active = asdict(activation.assert_v2_active(connection))
        relative = [dict(row) for row in connection.execute(
            "SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint"
        )]
    return {
        "databases": databases,
        "reports": reports,
        "reports_fingerprint": stable_hash(reports),
        "scheduler": scheduler,
        "active_package": active,
        "active_relative_valuation": relative,
    }


def compare_production_inventory(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    normalized_before = json.loads(json.dumps(before))
    normalized_after = json.loads(json.dumps(after))
    ignored_sidecar_mtime_changes: list[dict[str, Any]] = []
    for database in sorted(set(before["databases"]) & set(after["databases"])):
        for sidecar in ("wal", "shm"):
            left = before["databases"][database][sidecar]
            right = after["databases"][database][sidecar]
            content_keys = ("exists", "size", "sha256")
            if all(left[key] == right[key] for key in content_keys):
                if left["mtime_ns"] != right["mtime_ns"]:
                    ignored_sidecar_mtime_changes.append({
                        "database": database,
                        "sidecar": sidecar,
                        "before_mtime_ns": left["mtime_ns"],
                        "after_mtime_ns": right["mtime_ns"],
                        "sha256": left["sha256"],
                    })
                normalized_after["databases"][database][sidecar]["mtime_ns"] = left["mtime_ns"]
    return {
        "identical": normalized_before == normalized_after,
        "exact_metadata_identical": before == after,
        "ignored_content_identical_sidecar_mtime_changes": ignored_sidecar_mtime_changes,
        "preflight_fingerprint": stable_hash(before),
        "postflight_fingerprint": stable_hash(after),
        "normalized_preflight_fingerprint": stable_hash(normalized_before),
        "normalized_postflight_fingerprint": stable_hash(normalized_after),
    }


def process_inventory() -> dict[str, Any]:
    lines = subprocess.run(
        ("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True
    ).stdout.splitlines()
    relevant = [
        line.strip() for line in lines
        if any(term in line.lower() for term in (
            "run_fundamentals_v4", "run_phase12", "sharadar", "stock_update_scheduler"
        ))
        and str(os.getpid()) not in line
    ]
    conflicts = [
        line for line in relevant
        if any(term in line for term in (
            "run_fundamentals_v4", "run_sharadar", "run_stock_update_scheduler"
        ))
    ]
    holders = {}
    if shutil.which("lsof"):
        for name, path in PRODUCTION.items():
            command = subprocess.run(
                ("lsof", str(path), str(path) + "-wal", str(path) + "-shm"),
                capture_output=True, text=True,
            )
            holders[name] = command.stdout.splitlines()
    return {
        "relevant_processes": relevant, "conflicting_writers": conflicts,
        "database_holders": holders, "lsof_available": bool(shutil.which("lsof")),
    }


def copy_database(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with readonly(source) as reader, sqlite3.connect(destination) as writer:
        reader.backup(writer)
    with readonly(destination) as connection:
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    if quick != "ok" or foreign:
        raise RuntimeError(f"PHASE12D_COPY_INTEGRITY_FAILED:{destination}")
    return {
        "source": str(source.resolve()), "destination": str(destination.resolve()),
        "source_sha256": sha256(source), "copy_sha256": sha256(destination),
        "size": destination.stat().st_size, "quick_check": quick,
        "foreign_key_errors": foreign,
    }


def _provider_winners(provider_db: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with readonly(provider_db) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT po.observation_id,po.company_id,po.security_id,s.* "
            "FROM sharadar_fundamental_observation s "
            "JOIN provider_observation po USING(observation_id) "
            "WHERE s.dimension='ARQ' "
            "ORDER BY s.ticker,s.fiscalperiod,s.reportperiod DESC,"
            "COALESCE(s.lastupdated,s.date,'') DESC,po.observation_id"
        )]
    winners: dict[tuple[int, int, str], dict[str, Any]] = {}
    invalid = 0
    unresolved = 0
    for row in rows:
        if row["company_id"] is None:
            unresolved += 1
            continue
        try:
            fiscal_year, fiscal_quarter = parse_fiscalperiod(row["fiscalperiod"])
        except ValueError:
            invalid += 1
            continue
        row["fiscal_year"] = fiscal_year
        row["fiscal_quarter"] = fiscal_quarter
        winners.setdefault((int(row["company_id"]), fiscal_year, fiscal_quarter), row)
    output = [winners[key] for key in sorted(winners)]
    payload = [
        {
            "observation_id": row["observation_id"], "company_id": row["company_id"],
            "security_id": row["security_id"], "fiscal_year": row["fiscal_year"],
            "fiscal_quarter": row["fiscal_quarter"], "reportperiod": row["reportperiod"],
            "fiscalperiod": row["fiscalperiod"], "date": row["date"],
            **{field: row[native] for field, native in SHARADAR_ARQ_FIELD_MAPPING.items()},
        }
        for row in output
    ]
    return output, {
        "provider_arq_rows": len(rows), "winner_rows": len(output),
        "superseded_or_duplicate_rows": len(rows) - len(output) - invalid - unresolved,
        "invalid_fiscal_rows": invalid, "unresolved_identity_rows": unresolved,
        "source_fingerprint": stable_hash(payload),
    }


def _canonical_rows(connection: sqlite3.Connection) -> dict[tuple[int, int, str], sqlite3.Row]:
    return {
        (int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])): row
        for row in connection.execute(
            "SELECT q.*,f.* FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id)"
        )
    }


def canonical_logical_fingerprint(canonical_db: Path) -> str:
    with readonly(canonical_db) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT q.company_id,q.fiscal_year,q.fiscal_quarter,q.period_end,"
            "q.source_fiscalperiod,q.source_reportperiod,q.source_availability_date,"
            + ",".join(f"f.{field}" for field in SHARADAR_ARQ_FIELD_MAPPING)
            + " FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) "
            "ORDER BY q.company_id,q.fiscal_year,q.fiscal_quarter"
        )]
        provenance = []
        for table in (
            LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE,
            OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
        ):
            provenance.extend(tuple(row) for row in connection.execute(
                f"SELECT q.company_id,q.fiscal_year,q.fiscal_quarter,p.canonical_field,"
                f"p.provider_observation_id,p.source_native_field,p.transformation,p.rule_version,p.confidence "
                f"FROM {table} p JOIN v4_quarter q USING(quarter_id) "
                "ORDER BY q.company_id,q.fiscal_year,q.fiscal_quarter,p.canonical_field"
            ))
    return stable_hash({"rows": rows, "provenance": sorted(provenance)})


def reconcile_canonical(
    provider_db: Path,
    canonical_db: Path,
    *,
    applied_at: str,
    inject_failure: bool = False,
) -> dict[str, Any]:
    winners, source = _provider_winners(provider_db)
    counts = Counter()
    changed_sample: list[dict[str, Any]] = []
    connection = sqlite3.connect(canonical_db)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        ensure_provenance_schema(connection)
        existing = _canonical_rows(connection)
        connection.execute("BEGIN IMMEDIATE")
        for winner in winners:
            key = (int(winner["company_id"]), int(winner["fiscal_year"]), str(winner["fiscal_quarter"]))
            current = existing.get(key)
            values = {field: winner[native] for field, native in SHARADAR_ARQ_FIELD_MAPPING.items()}
            metadata = (
                winner["reportperiod"], winner["fiscalperiod"], winner["reportperiod"], winner["date"]
            )
            if current is None:
                cursor = connection.execute(
                    "INSERT INTO v4_quarter(company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,"
                    "source_reportperiod,identity_provider,identity_status,source_availability_date,"
                    "first_public_result_date,created_at_utc,updated_at_utc) "
                    "VALUES(?,?,?,?,?,?,'SHARADAR_ARQ','ACCEPTED',?,NULL,?,?)",
                    (key[0], key[1], key[2], *metadata[:3], metadata[3], applied_at, applied_at),
                )
                quarter_id = int(cursor.lastrowid)
                fields = list(values)
                connection.execute(
                    f"INSERT INTO v4_quarter_financials(quarter_id,{','.join(fields)},canonical_source_policy,created_at_utc,updated_at_utc) "
                    f"VALUES(?,{','.join('?' for _ in fields)},'SHARADAR_ARQ_PRIMARY',?,?)",
                    (quarter_id, *[values[field] for field in fields], applied_at, applied_at),
                )
                classification = "NEW_HISTORY"
            else:
                quarter_id = int(current["quarter_id"])
                provider_ids = {
                    str(row[0])
                    for table in (
                        LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE,
                        OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
                    )
                    for row in connection.execute(
                        f"SELECT DISTINCT provider_observation_id FROM {table} WHERE quarter_id=?",
                        (quarter_id,),
                    )
                }
                changed = (
                    current["period_end"] != metadata[0]
                    or current["source_fiscalperiod"] != metadata[1]
                    or current["source_reportperiod"] != metadata[2]
                    or current["source_availability_date"] != metadata[3]
                    or any(current[field] != value for field, value in values.items())
                    or bool(provider_ids and provider_ids != {str(winner["observation_id"])})
                )
                if not changed:
                    counts["UNCHANGED_OVERLAP"] += 1
                    continue
                connection.execute(
                    "UPDATE v4_quarter SET period_end=?,source_fiscalperiod=?,source_reportperiod=?,"
                    "source_availability_date=?,identity_provider='SHARADAR_ARQ',identity_status='ACCEPTED',updated_at_utc=? "
                    "WHERE quarter_id=?",
                    (*metadata, applied_at, quarter_id),
                )
                assignments = ",".join(f"{field}=?" for field in values)
                connection.execute(
                    f"UPDATE v4_quarter_financials SET {assignments},canonical_source_policy='SHARADAR_ARQ_PRIMARY',updated_at_utc=? WHERE quarter_id=?",
                    (*values.values(), applied_at, quarter_id),
                )
                classification = "REVISED_OVERLAP"
            for table in (
                LEGACY_PROVENANCE_TABLE, COMMON_EARNINGS_PROVENANCE_TABLE,
                OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
            ):
                connection.execute(f"DELETE FROM {table} WHERE quarter_id=?", (quarter_id,))
            for field, native in SHARADAR_ARQ_FIELD_MAPPING.items():
                if winner[native] is None:
                    continue
                write_provenance(connection, {
                    "quarter_id": quarter_id, "canonical_field": field, "provider": "SHARADAR",
                    "provider_observation_id": winner["observation_id"], "source_native_field": native,
                    "transformation": "DIRECT", "accepted_at_utc": applied_at,
                    "rule_version": "SHARADAR_ARQ_PRIMARY_V1", "confidence": "HIGH",
                })
            counts[classification] += 1
            if len(changed_sample) < 100:
                changed_sample.append({
                    "company_id": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2],
                    "classification": classification, "provider_observation_id": winner["observation_id"],
                })
        if inject_failure:
            raise RuntimeError("INJECTED_PHASE12D_CANONICAL_FAILURE")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    with readonly(canonical_db) as check:
        canonical_count = int(check.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0])
        orphan_financials = int(check.execute(
            "SELECT COUNT(*) FROM v4_quarter_financials f LEFT JOIN v4_quarter q USING(quarter_id) WHERE q.quarter_id IS NULL"
        ).fetchone()[0])
        duplicates = int(check.execute(
            "SELECT COUNT(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,COUNT(*) n FROM v4_quarter GROUP BY 1,2,3 HAVING n<>1)"
        ).fetchone()[0])
    unexplained = canonical_count - source["winner_rows"]
    return {
        **source, **dict(counts), "canonical_rows": canonical_count,
        "unexplained_or_stale_rows": unexplained, "duplicate_identities": duplicates,
        "orphan_financials": orphan_financials, "changed_sample": changed_sample,
        "canonical_fingerprint": canonical_logical_fingerprint(canonical_db),
    }


def _ttm_payload(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    excluded = {
        "ttm_id", "run_id", "calculated_at_utc", "created_at_utc", "updated_at_utc",
        "input_rows", "company_key", "ticker",
    }
    payload = [
        {
            **{key: value for key, value in row.items() if key not in excluded},
            "input_quarter_ids": [item["quarter_id"] for item in row.get("input_rows", ())],
        }
        for row in rows
    ]
    for row in payload:
        for field in ("cash", "total_debt", "shares_outstanding"):
            if row[field] is not None:
                row[field] = float(row[field])
    return payload


def persisted_ttm_fingerprint(canonical_db: Path) -> str:
    with readonly(canonical_db) as connection:
        rows = []
        for row in connection.execute(
            "SELECT * FROM v4_ttm_values ORDER BY company_id,endpoint_fiscal_year,endpoint_fiscal_quarter"
        ):
            item = dict(row)
            ttm_id = item.pop("ttm_id")
            for field in ("run_id", "calculated_at_utc", "created_at_utc", "updated_at_utc"):
                item.pop(field, None)
            item["input_quarter_ids"] = [
                int(link[0]) for link in connection.execute(
                    "SELECT input_quarter_id FROM v4_ttm_input_quarter WHERE ttm_id=? ORDER BY input_position",
                    (ttm_id,),
                )
            ]
            rows.append(item)
    return stable_hash(rows)


def rebuild_ttm(
    canonical_db: Path,
    *,
    applied_at: str,
    inject_failure: bool = False,
) -> dict[str, Any]:
    canonical_fp = canonical_financial_fingerprint(canonical_db)
    rows = compute_ttm_rows(
        load_canonical_rows(canonical_db), run_id="PHASE12D",
        calculated_at=applied_at, canonical_fingerprint=canonical_fp,
    )
    target = stable_hash(_ttm_payload(rows))
    current = persisted_ttm_fingerprint(canonical_db)
    if target == current and not inject_failure:
        return {"outcome": "NO_CHANGE", "rows": len(rows), "fingerprint": target, "logical_writes": 0}
    connection = sqlite3.connect(canonical_db)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        ensure_ttm_schema(connection)
        report = apply_ttm(connection, rows)
        if inject_failure:
            raise RuntimeError("INJECTED_PHASE12D_TTM_FAILURE")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    actual = persisted_ttm_fingerprint(canonical_db)
    if actual != target:
        raise RuntimeError("PHASE12D_TTM_RECONCILIATION_FAILED")
    return {"outcome": "APPLIED", "rows": len(rows), "fingerprint": target, "logical_writes": report["rows_written"]}


def _file_state(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with readonly(path) as connection:
        return {
            "sha256": sha256(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
            "freelist_count": int(connection.execute("PRAGMA freelist_count").fetchone()[0]),
            "wal": _sidecar(path, "-wal"), "shm": _sidecar(path, "-shm"),
        }


def _archived_package_readability(analysis_db: Path) -> dict[str, Any]:
    with readonly(analysis_db) as connection:
        active_identity = activation.assert_v2_active(connection)
        active = ActiveModelRepository(connection)
        company = int(connection.execute(
            "SELECT company_id FROM score_result WHERE model_fingerprint=? ORDER BY company_id LIMIT 1",
            (phase10b.MODEL_MAP["score"][1],),
        ).fetchone()[0])
        diagnostic = active.diagnostic_current(company)
        return {
            "active_package": active_identity.persistence_fingerprint,
            "model_fingerprints": dict(active.model_fingerprints),
            "sample_company_id": company,
            "sample_diagnostic_evaluations": len(diagnostic["evaluations"]),
            "readable": len(diagnostic["evaluations"]) == 8,
        }


def _candidate_package_fingerprint(source_fp: str, canonical_fp: str, ttm_fp: str) -> str:
    return stable_hash({
        "rebuild_fingerprint": REBUILD_FINGERPRINT,
        "parent_persistence_fingerprint": phase10b.PACKAGE_FINGERPRINT,
        "provider_source_fingerprint": source_fp,
        "canonical_fingerprint": canonical_fp,
        "ttm_fingerprint": ttm_fp,
        "model_map": phase10b.MODEL_MAP,
    })


def _validate_candidate(
    analysis_db: Path, calculated: Mapping[str, Any], package_fingerprint: str
) -> dict[str, Any]:
    expected = len(calculated["rows"])
    with readonly(analysis_db) as connection:
        ParallelModelRepository(connection).assert_v2_bundle(
            phase10b.MODEL_MAP, persistence_fingerprint=package_fingerprint
        )
        counts = operating_persistence.row_counts(
            connection, diagnostic_model=diagnostic_flags_eight
        )
        requirements = {
            "score": expected, "score_component": expected * 7,
            "lifecycle": expected, "valuation": expected,
            "delta": expected, "delta_component": expected * 7,
            "diagnostic_endpoint": expected, "diagnostic_evaluation": expected * 8,
        }
        mismatches = {
            key: {"actual": counts[key], "expected": value}
            for key, value in requirements.items() if counts[key] != value
        }
        active_rows = int(connection.execute(
            "SELECT COUNT(*) FROM fundamentals_active_model_family"
        ).fetchone()[0])
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    if mismatches or active_rows or quick != "ok" or foreign:
        raise RuntimeError(f"PHASE12D_CANDIDATE_INVALID:{mismatches}:{active_rows}:{quick}:{foreign}")
    return {
        "ok": True, "counts": counts, "expected": requirements,
        "active_pointer_rows": active_rows, "quick_check": quick,
        "foreign_key_errors": foreign,
    }


def _clear_candidate_activation(analysis_db: Path) -> None:
    with sqlite3.connect(analysis_db) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM fundamentals_active_model_family")
        connection.commit()


def build_candidate(
    paths: Mapping[str, Path],
    *,
    applied_at: str,
    run_failures: bool,
) -> dict[str, Any]:
    timings: dict[str, float] = {}
    failures: list[dict[str, Any]] = []
    started = time.perf_counter()
    if run_failures:
        before = canonical_logical_fingerprint(paths["canonical"])
        try:
            reconcile_canonical(paths["provider"], paths["canonical"], applied_at=applied_at, inject_failure=True)
        except RuntimeError as exc:
            after = canonical_logical_fingerprint(paths["canonical"])
            failures.append({"stage": "canonical", "error": str(exc), "rollback_equal": before == after})
    canonical = reconcile_canonical(paths["provider"], paths["canonical"], applied_at=applied_at)
    timings["canonical_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    if run_failures:
        before = persisted_ttm_fingerprint(paths["canonical"])
        try:
            rebuild_ttm(paths["canonical"], applied_at=applied_at, inject_failure=True)
        except RuntimeError as exc:
            after = persisted_ttm_fingerprint(paths["canonical"])
            failures.append({"stage": "ttm", "error": str(exc), "rollback_equal": before == after})
    ttm = rebuild_ttm(paths["canonical"], applied_at=applied_at)
    timings["ttm_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    calculated = phase10b.calculate(paths, verify_v1_overlap=False)
    timings["calculation_seconds"] = time.perf_counter() - started
    package_fingerprint = _candidate_package_fingerprint(
        canonical["source_fingerprint"], canonical["canonical_fingerprint"], ttm["fingerprint"]
    )
    _clear_candidate_activation(paths["analysis"])
    if run_failures:
        for stage in ("score", "manifest", "activation"):
            with readonly(paths["analysis"]) as connection:
                before = operating_persistence.physical_fingerprint(
                    connection, diagnostic_model=diagnostic_flags_eight
                )
            try:
                with sqlite3.connect(paths["analysis"]) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA foreign_keys=ON")
                    phase10b.apply_candidate_package(
                        connection, calculated, applied_at=applied_at,
                        inject_failure_at=stage,
                        persistence_fingerprint=package_fingerprint,
                    )
            except RuntimeError as exc:
                with readonly(paths["analysis"]) as connection:
                    after = operating_persistence.physical_fingerprint(
                        connection, diagnostic_model=diagnostic_flags_eight
                    )
                failures.append({"stage": stage, "error": str(exc), "rollback_equal": before == after})
    with sqlite3.connect(paths["analysis"]) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        first = phase10b.apply_candidate_package(
            connection, calculated, applied_at=applied_at,
            persistence_fingerprint=package_fingerprint,
        )
    validation = _validate_candidate(paths["analysis"], calculated, package_fingerprint)
    timings["downstream_seconds"] = time.perf_counter() - started
    if run_failures and (len(failures) != 5 or not all(row["rollback_equal"] for row in failures)):
        raise RuntimeError(f"PHASE12D_ROLLBACK_GATE_FAILED:{failures}")
    return {
        "canonical": canonical, "ttm": ttm,
        "package": {**asdict(first), "persistence_fingerprint": package_fingerprint},
        "validation": validation, "fingerprints": calculated["fingerprints"],
        "failures": failures, "timings": timings,
    }


def verify_no_change(paths: Mapping[str, Path], result: Mapping[str, Any], *, applied_at: str) -> dict[str, Any]:
    before = {name: _file_state(paths[name]) for name in ("canonical", "analysis")}
    canonical = reconcile_canonical(paths["provider"], paths["canonical"], applied_at=applied_at)
    ttm = rebuild_ttm(paths["canonical"], applied_at=applied_at)
    calculated = phase10b.calculate(paths, verify_v1_overlap=False)
    with sqlite3.connect(paths["analysis"]) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        package = phase10b.apply_candidate_package(
            connection, calculated, applied_at=applied_at,
            persistence_fingerprint=result["package"]["persistence_fingerprint"],
        )
    after = {name: _file_state(paths[name]) for name in ("canonical", "analysis")}
    passed = (
        canonical.get("NEW_HISTORY", 0) == 0
        and canonical.get("REVISED_OVERLAP", 0) == 0
        and ttm["outcome"] == "NO_CHANGE"
        and package.outcome == "NO_CHANGE" and package.logical_changes == 0
        and before == after
    )
    if not passed:
        raise RuntimeError("PHASE12D_NO_CHANGE_GATE_FAILED")
    return {
        "outcome": "NO_CHANGE", "logical_writes": 0,
        "canonical": canonical, "ttm": ttm, "package": asdict(package),
        "byte_and_metadata_state_equal": True,
    }


def _overlap_readiness(before_db: Path, after_db: Path) -> dict[str, Any]:
    def values(path: Path) -> dict[tuple[int, int], str]:
        with readonly(path) as connection:
            return {
                (int(row[0]), int(row[1])): str(row[2])
                for row in connection.execute(
                    "SELECT company_id,endpoint_quarter_id,readiness_status FROM v4_ttm_values"
                )
            }
    before, after = values(before_db), values(after_db)
    overlap = set(before) & set(after)
    return {
        "overlap_rows": len(overlap),
        "readiness_changed": sum(before[key] != after[key] for key in overlap),
        "new_rows": len(set(after) - set(before)),
        "removed_rows": len(set(before) - set(after)),
    }


def _relative_valuation_staleness(before_analysis: Path, candidate_analysis: Path) -> dict[str, Any]:
    def valuation_count(path: Path) -> int:
        with readonly(path) as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM valuation_revised_result WHERE model_fingerprint=?",
                (phase10b.MODEL_MAP["valuation"][1],),
            ).fetchone()[0])
    before, after = valuation_count(before_analysis), valuation_count(candidate_analysis)
    return {
        "status": "ECONOMICALLY_STALE_AFTER_HISTORY_EXPANSION" if before != after else "CURRENT_INPUT_POPULATION_UNCHANGED",
        "valuation_history_rows_before": before,
        "valuation_history_rows_after": after,
        "relative_valuation_refreshed": False,
        "production_pointer_changed": False,
        "phase12e_action": "separately authorize and refresh Relative Valuation after package activation",
    }


def _provenance_reconciliation(canonical_db: Path) -> dict[str, Any]:
    groups = (
        (
            LEGACY_PROVENANCE_TABLE,
            (
                "revenue", "gross_profit", "operating_income", "ebit", "ebitda",
                "net_income", "operating_cashflow", "capex", "free_cashflow",
                "cash", "total_debt", "shares_outstanding",
            ),
        ),
        (COMMON_EARNINGS_PROVENANCE_TABLE, ("net_income_common",)),
        (
            OPERATING_WORKING_CAPITAL_PROVENANCE_TABLE,
            ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue", "total_assets"),
        ),
    )
    with readonly(canonical_db) as connection:
        by_field: dict[str, dict[str, int]] = {}
        missing = 0
        unexpected = 0
        for table, fields in groups:
            counts = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    f'SELECT canonical_field,COUNT(*) FROM "{table}" GROUP BY canonical_field'
                )
            }
            for field in fields:
                expected = int(connection.execute(
                    f"SELECT COUNT(*) FROM v4_quarter_financials WHERE {field} IS NOT NULL"
                ).fetchone()[0])
                absent = int(connection.execute(
                    f"SELECT COUNT(*) FROM v4_quarter_financials f "
                    f"WHERE f.{field} IS NOT NULL AND NOT EXISTS ("
                    f'SELECT 1 FROM "{table}" p WHERE p.quarter_id=f.quarter_id '
                    "AND p.canonical_field=?)",
                    (field,),
                ).fetchone()[0])
                by_field[field] = {
                    "non_null_canonical_values": expected,
                    "provenance_rows": counts.get(field, 0),
                    "missing_provenance": absent,
                }
                missing += absent
                unexpected += abs(counts.get(field, 0) - expected)
        duplicate_fiscal_identities = int(connection.execute(
            "SELECT COUNT(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,COUNT(*) n "
            "FROM v4_quarter GROUP BY company_id,fiscal_year,fiscal_quarter HAVING n<>1)"
        ).fetchone()[0])
    return {
        "fields": by_field,
        "missing_provenance_total": missing,
        "unexpected_provenance_row_delta_total": unexpected,
        "duplicate_authoritative_fiscal_identities": duplicate_fiscal_identities,
        "passed": missing == unexpected == duplicate_fiscal_identities == 0,
    }


def _ttm_chain_reconciliation(canonical_db: Path) -> dict[str, Any]:
    with readonly(canonical_db) as connection:
        cross_company = int(connection.execute(
            "SELECT COUNT(*) FROM v4_ttm_input_quarter i "
            "JOIN v4_ttm_values t USING(ttm_id) JOIN v4_quarter q ON q.quarter_id=i.input_quarter_id "
            "WHERE q.company_id<>t.company_id"
        ).fetchone()[0])
        availability_mismatch = int(connection.execute(
            "SELECT COUNT(*) FROM (SELECT t.ttm_id,t.ttm_source_available_date,"
            "MAX(i.source_availability_date) maximum_date,t.readiness_status FROM v4_ttm_values t "
            "LEFT JOIN v4_ttm_input_quarter i USING(ttm_id) GROUP BY t.ttm_id) "
            "WHERE readiness_status<>'TTM_DATA_INSUFFICIENT' "
            "AND ttm_source_available_date IS NOT maximum_date"
        ).fetchone()[0])
        chains: dict[int, list[tuple[int, int, str]]] = {}
        readiness: dict[int, str] = {
            int(row[0]): str(row[1])
            for row in connection.execute("SELECT ttm_id,readiness_status FROM v4_ttm_values")
        }
        for row in connection.execute(
            "SELECT ttm_id,input_position,input_fiscal_year,input_fiscal_quarter "
            "FROM v4_ttm_input_quarter ORDER BY ttm_id,input_position"
        ):
            chains.setdefault(int(row[0]), []).append((int(row[1]), int(row[2]), str(row[3])))
        ttm_rows = int(connection.execute("SELECT COUNT(*) FROM v4_ttm_values").fetchone()[0])
    invalid_ready_order = 0
    blocked_incomplete_chains = 0
    for ttm_id, chain in chains.items():
        ordinals = [year * 4 + int(quarter[1]) for _, year, quarter in chain]
        positions = [position for position, _, _ in chain]
        invalid = positions != list(range(1, len(chain) + 1)) or any(
            current != previous + 1 for previous, current in zip(ordinals, ordinals[1:])
        )
        if invalid and readiness[ttm_id] == "TTM_DATA_INSUFFICIENT":
            blocked_incomplete_chains += 1
        elif invalid:
            invalid_ready_order += 1
    return {
        "ttm_rows": ttm_rows,
        "input_rows": sum(map(len, chains.values())),
        "cross_company_inputs": cross_company,
        "availability_max_mismatches": availability_mismatch,
        "invalid_ready_nonconsecutive_or_unordered_chains": invalid_ready_order,
        "blocked_incomplete_nonconsecutive_chains": blocked_incomplete_chains,
        "passed": cross_company == availability_mismatch == invalid_ready_order == 0,
    }


def write_reconciliation_artifacts(
    output: Path,
    candidate_paths: Mapping[str, Path],
    first: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> None:
    provenance = _provenance_reconciliation(candidate_paths["canonical"])
    ttm_chain = _ttm_chain_reconciliation(candidate_paths["canonical"])
    if not provenance["passed"] or not ttm_chain["passed"]:
        raise RuntimeError("PHASE12D_DEEP_RECONCILIATION_FAILED")
    write_json(output / "provenance_reconciliation.json", provenance)
    write_json(output / "ttm_chain_reconciliation.json", ttm_chain)
    write_json(output / "overlap_classification.json", {
        key: first["canonical"].get(key, 0)
        for key in ("NEW_HISTORY", "REVISED_OVERLAP", "UNCHANGED_OVERLAP")
    } | {"readiness_changes": dict(readiness)})
    write_json(output / "per_layer_reconciliation.json", {
        "row_counts": first["validation"]["counts"],
        "expected_row_counts": first["validation"]["expected"],
        "result_fingerprints": first["fingerprints"],
        "package": first["package"],
        "economic_formulas_changed": False,
        "engine_and_persistence_reconciled": True,
    })
    write_json(output / "unexplained_difference_report.json", {
        "unexplained_or_stale_rows": first["canonical"]["unexplained_or_stale_rows"],
        "status": "PASS" if first["canonical"]["unexplained_or_stale_rows"] == 0 else "FAIL",
    })


def _validate_artifacts(output: Path) -> None:
    for path in output.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in output.rglob("*.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            if next(reader, None) is None:
                raise RuntimeError(f"PHASE12D_EMPTY_CSV:{path}")


def run(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if not output.is_absolute() or ROOT / "temp/fundamentals_v4_phase12d" not in output.parents:
        raise ValueError("PHASE12D_OUTPUT_PATH_REJECTED")
    if output.exists():
        raise FileExistsError(output)
    if (ROOT / ".git/rebase-merge").exists() or (ROOT / ".git/rebase-apply").exists() or (ROOT / ".git/MERGE_HEAD").exists():
        raise RuntimeError("PHASE12D_INTERRUPTED_GIT_OPERATION")
    free = shutil.disk_usage(ROOT).free
    required = sum(PRODUCTION[name].stat().st_size for name in ("provider", "canonical", "analysis")) * 4
    if free < required:
        raise RuntimeError(f"PHASE12D_DISK_GATE_FAILED:{free}:{required}")
    output.mkdir(parents=True)
    processes = process_inventory()
    write_json(output / "process_and_writer_inventory.json", processes)
    if processes["conflicting_writers"]:
        raise RuntimeError(f"PHASE12D_CONFLICTING_WRITER:{processes['conflicting_writers']}")
    preflight = production_inventory()
    write_json(output / "production_preflight.json", preflight)
    write_json(output / "rebuild_contract.json", {
        "contract": REBUILD_CONTRACT, "fingerprint": REBUILD_FINGERPRINT,
        "git_head": subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=ROOT, capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "worktree_at_execution": subprocess.run(
            ("git", "status", "--porcelain"), cwd=ROOT, capture_output=True,
            text=True, check=True,
        ).stdout.splitlines(),
    })

    copies: dict[str, dict[str, Path]] = {}
    copy_manifests = []
    for label in ("candidate_a", "candidate_b"):
        paths = {
            "provider": output / label / "fundamentals_provider.db",
            "canonical": output / label / "fundamentals_v4.db",
            "analysis": output / label / "fundamentals_analysis.db",
            "market": PRODUCTION["market"], "taxonomy": PRODUCTION["taxonomy"],
        }
        copies[label] = paths
        for name in ("provider", "canonical", "analysis"):
            copy_manifests.append({"copy_set": label, "database": name, **copy_database(PRODUCTION[name], paths[name])})
    archive = output / "archived_active_package.db"
    copy_manifests.append({"copy_set": "archive", "database": "analysis", **copy_database(PRODUCTION["analysis"], archive)})
    write_json(output / "source_copy_manifests.json", copy_manifests)
    archived = _archived_package_readability(archive)
    write_json(output / "archived_package_readability.json", archived)
    if not archived["readable"]:
        raise RuntimeError("PHASE12D_ARCHIVED_PACKAGE_NOT_READABLE")

    applied_at = "2026-09-10T00:00:00Z"
    before_canonical = output / "candidate_a/fundamentals_v4.before.db"
    copy_database(PRODUCTION["canonical"], before_canonical)
    first_started = time.perf_counter()
    first = build_candidate(copies["candidate_a"], applied_at=applied_at, run_failures=True)
    first_runtime = time.perf_counter() - first_started
    no_change_started = time.perf_counter()
    no_change = verify_no_change(copies["candidate_a"], first, applied_at=applied_at)
    no_change_runtime = time.perf_counter() - no_change_started
    second_started = time.perf_counter()
    second = build_candidate(copies["candidate_b"], applied_at=applied_at, run_failures=False)
    second_runtime = time.perf_counter() - second_started

    compare_fields = {
        "canonical": first["canonical"]["canonical_fingerprint"] == second["canonical"]["canonical_fingerprint"],
        "ttm": first["ttm"]["fingerprint"] == second["ttm"]["fingerprint"],
        "package_economic": first["package"]["economic_result_fingerprint"] == second["package"]["economic_result_fingerprint"],
        "package_physical": first["package"]["physical_content_fingerprint"] == second["package"]["physical_content_fingerprint"],
        "package_identity": first["package"]["persistence_fingerprint"] == second["package"]["persistence_fingerprint"],
        "layer_results": first["fingerprints"] == second["fingerprints"],
    }
    if not all(compare_fields.values()):
        raise RuntimeError(f"PHASE12D_INDEPENDENT_REPLAY_FAILED:{compare_fields}")
    write_json(output / "independent_replay_comparison.json", compare_fields)
    write_json(output / "first_apply.json", first)
    write_json(output / "second_no_change.json", no_change)
    write_json(output / "independent_apply.json", second)
    write_json(output / "rollback_failure_injection.json", first["failures"])

    readiness = _overlap_readiness(before_canonical, copies["candidate_a"]["canonical"])
    write_json(output / "ttm_readiness_reconciliation.json", readiness)
    write_reconciliation_artifacts(output, copies["candidate_a"], first, readiness)
    relative = _relative_valuation_staleness(archive, copies["candidate_a"]["analysis"])
    write_json(output / "relative_valuation_staleness.json", relative)

    phase12b_results = []
    for label in ("candidate_a", "candidate_b"):
        paths = copies[label]
        result = run_phase12b(
            ResearchPaths(paths["canonical"], paths["analysis"], paths["provider"], paths["market"], paths["taxonomy"]),
            output / label / "phase12b_replay",
            contract_fingerprint=PHASE12B_CONTRACT_FINGERPRINT,
            allow_expanded_revised_history=True,
        )
        phase12b_results.append({"copy_set": label, **asdict(result)})
    phase12b_deterministic = (
        phase12b_results[0]["source_fingerprint"] == phase12b_results[1]["source_fingerprint"]
        and phase12b_results[0]["sample_fingerprint"] == phase12b_results[1]["sample_fingerprint"]
    )
    if not phase12b_deterministic:
        raise RuntimeError("PHASE12D_PHASE12B_REPLAY_NOT_DETERMINISTIC")
    write_json(output / "phase12b_replay_summary.json", {
        "contract_fingerprint": PHASE12B_CONTRACT_FINGERPRINT,
        "results": phase12b_results, "source_and_sample_deterministic": True,
    })

    storage = {
        "free_bytes_preflight": free, "required_gate_bytes": required,
        "runtime_seconds": {
            "first_apply": first_runtime, "second_no_change": no_change_runtime,
            "independent_apply": second_runtime,
        },
        "candidate_a": {
            name: database_inventory(copies["candidate_a"][name])
            for name in ("canonical", "analysis")
        },
        "production_sizes": {name: PRODUCTION[name].stat().st_size for name in ("canonical", "analysis")},
    }
    write_json(output / "storage_and_runtime.json", storage)
    postflight = production_inventory()
    immutability = compare_production_inventory(preflight, postflight)
    immutable = bool(immutability["identical"])
    write_json(output / "production_postflight.json", postflight)
    write_json(output / "production_immutability.json", immutability)
    if not immutable:
        raise RuntimeError("PHASE12D_PRODUCTION_STATE_CHANGED")

    unexplained = first["canonical"]["unexplained_or_stale_rows"]
    outcome = (
        "OUTCOME A - TEN-YEAR OPERATIONAL REBUILD REHEARSED; PHASE 12E PRODUCTION DEPLOYMENT READY"
        if unexplained == 0 and relative["status"] != "ECONOMICALLY_STALE_AFTER_HISTORY_EXPANSION"
        else "OUTCOME B - REBUILD CORRECT BUT MATERIAL DATA OR VERSIONING DECISION REQUIRED"
    )
    decision = {
        "outcome": outcome,
        "reason": (
            "Relative Valuation requires a separately authorized post-activation refresh"
            if relative["status"] == "ECONOMICALLY_STALE_AFTER_HISTORY_EXPANSION"
            else "all acceptance gates passed"
        ),
        "phase12e_ready": outcome.startswith("OUTCOME A"),
        "production_immutable": True,
        "revised_non_pit": True,
        "candidate_package_fingerprint": first["package"]["persistence_fingerprint"],
        "phase12b_outcome": phase12b_results[0]["outcome"],
    }
    write_json(output / "decision.json", decision)
    write_json(output / "canonical_rebuild_summary.json", first["canonical"])
    write_json(output / "downstream_reconciliation.json", first["validation"])
    write_json(output / "fingerprints.json", {
        "rebuild_contract": REBUILD_FINGERPRINT,
        "operating_family_economic": operating_contract.FAMILY_FINGERPRINT,
        "models": phase10b.MODEL_MAP,
        "provider_source": first["canonical"]["source_fingerprint"],
        "canonical": first["canonical"]["canonical_fingerprint"],
        "ttm": first["ttm"]["fingerprint"],
        "layers": first["fingerprints"],
        "package_persistence": first["package"]["persistence_fingerprint"],
        "package_economic": first["package"]["economic_result_fingerprint"],
        "package_physical": first["package"]["physical_content_fingerprint"],
    })
    write_csv(output / "overlap_revision_sample.csv", first["canonical"]["changed_sample"])
    (output / "commands_run.txt").write_text(
        "python3 -m rawcandle.cli.run_phase12d_operational_rebuild --output <temp/fundamentals_v4_phase12d/run_id>\n"
        "pytest -q <complete Fundamentals V4 and relevant isolation/UI suites>\n"
        "python3 -m compileall -q rawcandle tests\n"
        "git diff --check\n"
        "No provider API, Scheduler, production writer, report generator, Relative Valuation refresh, or activation command was run.\n",
        encoding="utf-8",
    )
    report = [
        "# Phase 12D Ten-Year Operational Rebuild Rehearsal", "",
        f"Decision: **{outcome}**", "",
        "The operational universe was rebuilt only on isolated SQLite copies. The history is currently revised and non-PIT.", "",
        f"Canonical rows: {first['canonical']['canonical_rows']:,}; new history: {first['canonical'].get('NEW_HISTORY', 0):,}; revised overlap: {first['canonical'].get('REVISED_OVERLAP', 0):,}; unchanged overlap: {first['canonical'].get('UNCHANGED_OVERLAP', 0):,}.",
        f"TTM and each full-history downstream layer contain {first['ttm']['rows']:,} endpoints. Diagnostics contain {first['validation']['counts']['diagnostic_evaluation']:,} evaluations.",
        f"Second apply: `{no_change['outcome']}` with zero logical writes and unchanged bytes/mtime/pages/freelist/sidecars.",
        f"Phase 12B locked outcome: `{phase12b_results[0]['outcome']}`. Contract fingerprint remained `{PHASE12B_CONTRACT_FINGERPRINT}`.",
        f"Relative Valuation: `{relative['status']}`; it was not refreshed.",
        "Production databases, pointers, Scheduler configuration, and reports were unchanged.", "",
        "See the machine-readable artifacts in this directory and the Phase 12E runbook in repository documentation.", "",
    ]
    (output / "PHASE12D_REHEARSAL_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    _validate_artifacts(output)
    return decision
