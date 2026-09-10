from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.schema.production_bootstrap import (
    ALLOWED_DIMENSIONS,
    ProductionPaths,
    insert_production_sharadar_observation,
    target_tickers,
)
from rawcandle.fundamentals.schema.prototype import stable_hash, stable_id


HISTORY_YEARS = 10
RUN_TYPE = "SHARADAR_10Y_RAW_BACKFILL"
REQUIRED_COLUMNS = frozenset({
    "ticker", "dimension", "calendardate", "reportperiod", "fiscalperiod",
    "date", "lastupdated", "revenue", "opinc", "ebit", "fcf", "cashneq",
    "debt", "sharesbas",
})
NATIVE_FIELDS = {
    "revenue": "revenue", "ebit": "ebit", "free_cashflow": "fcf",
    "cash": "cashneq", "total_debt": "debt", "shares_outstanding": "sharesbas",
}


@dataclass(frozen=True)
class Phase12CPaths:
    root: Path
    output: Path
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    market_db: Path
    taxonomy_db: Path
    reports_dir: Path
    bootstrap_csv: Path
    backup_dir: Path

    @property
    def staged_zip(self) -> Path:
        return self.output / "sharadar_fundamentals_10y.zip"

    @property
    def staged_csv(self) -> Path:
        return self.output / "sharadar_fundamentals_10y.csv"

    def production_paths(self) -> ProductionPaths:
        return ProductionPaths(
            self.root, self.output, self.provider_db, self.canonical_db,
            self.analysis_db, self.bootstrap_csv, self.staged_zip, self.staged_csv,
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    return stable_hash([tuple(row) for row in rows])


def database_inventory(path: Path, *, include_hash: bool = True) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        foreign = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
        result = {
            "path": str(path.resolve()), "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns, "schema_hash": schema_hash(conn),
            "page_count": conn.execute("PRAGMA page_count").fetchone()[0],
            "freelist_count": conn.execute("PRAGMA freelist_count").fetchone()[0],
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
            "quick_check": quick, "foreign_key_violations": foreign,
            "wal_exists": Path(str(path) + "-wal").exists(),
            "shm_exists": Path(str(path) + "-shm").exists(),
        }
    if include_hash:
        result["sha256"] = sha256(path)
    return result


def provider_counts(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        by_dimension = [dict(row) for row in conn.execute(
            "SELECT dimension,COUNT(*) rows,COUNT(DISTINCT provider_ticker) tickers,"
            "MIN(calendardate) oldest,MAX(calendardate) newest FROM provider_observation "
            "WHERE provider='SHARADAR' AND native_table='fundamentals' GROUP BY dimension ORDER BY dimension"
        )]
        totals = dict(conn.execute(
            "SELECT COUNT(*) observations,COUNT(DISTINCT company_id) companies,"
            "COUNT(DISTINCT provider_ticker) tickers FROM provider_observation "
            "WHERE provider='SHARADAR' AND native_table='fundamentals'"
        ).fetchone())
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM (SELECT observation_id,COUNT(*) n FROM provider_observation "
            "GROUP BY observation_id HAVING n>1)"
        ).fetchone()[0]
        orphaned = conn.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation s LEFT JOIN provider_observation p "
            "USING(observation_id) WHERE p.observation_id IS NULL"
        ).fetchone()[0]
    return {"totals": totals, "by_dimension": by_dimension,
            "duplicate_observation_ids": duplicates, "orphaned_normalized_rows": orphaned}


def _finite_integer(value: Any) -> bool:
    if value is None or str(value).strip() == "":
        return True
    try:
        return math.isfinite(float(str(value).replace(",", "")))
    except ValueError:
        return False


def validate_staged_source(path: Path, *, target: set[str], old_oldest_arq: str | None) -> dict[str, Any]:
    dimensions = Counter()
    years = Counter()
    quarters = Counter()
    tickers_by_year: dict[str, set[str]] = {}
    coverage = Counter()
    allowed_rows = 0
    allowed_dimensions = Counter()
    malformed = Counter()
    blank = Counter()
    logical_hashes: dict[tuple[str, ...], set[str]] = defaultdict(set)
    exact_duplicate_rows = 0
    oldest: dict[str, str] = {}
    newest: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            raise RuntimeError("PHASE12C_STAGED_SCHEMA_MISMATCH:" + ",".join(missing_columns))
        for row in reader:
            ticker = str(row.get("ticker") or "").strip().upper()
            dimension = str(row.get("dimension") or "").strip().upper()
            period = str(row.get("calendardate") or row.get("reportperiod") or "")
            dimensions[dimension] += 1
            if period:
                oldest[dimension] = min(oldest.get(dimension, period), period)
                newest[dimension] = max(newest.get(dimension, period), period)
                year = period[:4]
                years[(dimension, year)] += 1
                quarters[(dimension, year, str(row.get("fiscalperiod") or "")[-2:])] += 1
                tickers_by_year.setdefault(f"{dimension}:{year}", set()).add(ticker)
            if dimension not in ALLOWED_DIMENSIONS or ticker not in target:
                continue
            allowed_rows += 1
            allowed_dimensions[dimension] += 1
            key = (ticker, dimension, str(row.get("reportperiod") or ""),
                   str(row.get("fiscalperiod") or ""), str(row.get("lastupdated") or row.get("date") or ""))
            row_hash = stable_hash(dict(row))
            if row_hash in logical_hashes[key]:
                exact_duplicate_rows += 1
            logical_hashes[key].add(row_hash)
            for canonical, native in NATIVE_FIELDS.items():
                value = row.get(native)
                if value is None or str(value).strip() == "":
                    blank[canonical] += 1
                else:
                    coverage[canonical] += 1
                    if not _finite_integer(value):
                        malformed[canonical] += 1
    if allowed_rows == 0:
        raise RuntimeError("PHASE12C_EMPTY_TARGET_SOURCE")
    if not {"ARQ", "MRQ"}.issubset(dimensions):
        raise RuntimeError("PHASE12C_REQUIRED_DIMENSIONS_MISSING")
    if not {"ARQ", "MRQ"}.issubset(allowed_dimensions):
        raise RuntimeError("PHASE12C_TARGET_DIMENSIONS_MISSING")
    oldest_arq = oldest.get("ARQ")
    if not oldest_arq or (old_oldest_arq and oldest_arq >= old_oldest_arq):
        raise RuntimeError("PHASE12C_HISTORY_NOT_EXTENDED")
    if malformed:
        raise RuntimeError("PHASE12C_MALFORMED_NUMERIC_VALUES:" + json.dumps(malformed, sort_keys=True))
    revision_key_collision_extra = sum(
        len(hashes) - 1 for hashes in logical_hashes.values() if len(hashes) > 1
    )
    if exact_duplicate_rows:
        raise RuntimeError(f"PHASE12C_EXACT_DUPLICATE_STAGED_ROWS:{exact_duplicate_rows}")
    return {
        "source_path": str(path), "source_sha256": sha256(path),
        "dimensions": dict(sorted(dimensions.items())),
        "allowed_dimensions": dict(sorted(allowed_dimensions.items())),
        "allowed_target_rows": allowed_rows,
        "oldest": dict(sorted(oldest.items())), "newest": dict(sorted(newest.items())),
        "rows_by_year": [{"dimension": d, "year": y, "rows": n} for (d, y), n in sorted(years.items())],
        "rows_by_fiscal_quarter": [{"dimension": d, "year": y, "quarter": q, "rows": n} for (d, y, q), n in sorted(quarters.items())],
        "ticker_coverage_by_year": [{"dimension_year": key, "tickers": len(value)} for key, value in sorted(tickers_by_year.items())],
        "field_populated": dict(sorted(coverage.items())), "field_blank": dict(sorted(blank.items())),
        "malformed_numeric": dict(sorted(malformed.items())),
        "exact_duplicate_rows": exact_duplicate_rows,
        "revision_key_collision_extra_rows": revision_key_collision_extra,
    }


def _identity_map(path: Path) -> dict[str, tuple[int, int]]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        return {str(row[0]).upper(): (int(row[1]), int(row[2])) for row in conn.execute(
            "SELECT current_ticker,security_id,company_id FROM security"
        )}


def staged_provider_reconciliation(path: Path, provider_db: Path, *, target: set[str]) -> dict[str, Any]:
    with sqlite3.connect(f"file:{provider_db.resolve()}?mode=ro", uri=True) as conn:
        existing_ids = {str(row[0]) for row in conn.execute(
            "SELECT observation_id FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals'"
        )}
        existing_base = {
            (str(row[0]).upper(), str(row[1]), str(row[2] or ""), str(row[3] or ""))
            for row in conn.execute(
                "SELECT provider_ticker,dimension,reportperiod,fiscalperiod FROM provider_observation "
                "WHERE provider='SHARADAR' AND native_table='fundamentals'"
            ) if str(row[0]).upper() in target and str(row[1]) in ALLOWED_DIMENSIONS
        }
    counts = Counter()
    staged_base = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            ticker = str(row.get("ticker") or "").strip().upper()
            dimension = str(row.get("dimension") or "").strip().upper()
            if ticker not in target or dimension not in ALLOWED_DIMENSIONS:
                continue
            base = (ticker, dimension, str(row.get("reportperiod") or ""), str(row.get("fiscalperiod") or ""))
            staged_base.add(base)
            permaticker = str(row.get("permaticker") or "").strip()
            record_key = "|".join((permaticker, ticker, dimension, base[2], base[3],
                                   str(row.get("lastupdated") or row.get("date") or "")))
            observation_id = stable_id("SHARADAR", "fundamentals", record_key, stable_hash(dict(row)))
            if observation_id in existing_ids:
                counts["unchanged"] += 1
            elif base in existing_base:
                counts["revised"] += 1
            else:
                counts["new"] += 1
    counts["previously_stored_base_keys_absent_from_snapshot"] = len(existing_base - staged_base)
    return dict(sorted(counts.items()))


def import_staged(paths: Phase12CPaths, validation: Mapping[str, Any], *, fail_after: int | None = None) -> dict[str, Any]:
    identities = _identity_map(paths.canonical_db)
    target = target_tickers(paths.bootstrap_csv)
    run_id = "PHASE12C_" + str(validation["source_sha256"])[:24]
    inserted = Counter()
    matched = Counter()
    skipped = Counter()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    conn = sqlite3.connect(paths.provider_db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,"
            "request_scope,entitlement_scope,source_version,metadata_json) VALUES(?, 'SHARADAR',?,?,"
            "'SUCCESS',?,?,?,?)",
            (run_id, now, now, RUN_TYPE, "Sharadar Fundamentals 10 Years", "PHASE12C",
             json.dumps({"history_scope": "years=10", "source_sha256": validation["source_sha256"]}, sort_keys=True)),
        )
        with paths.staged_csv.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                ticker = str(row.get("ticker") or "").strip().upper()
                dimension = str(row.get("dimension") or "").strip().upper()
                if dimension not in ALLOWED_DIMENSIONS or ticker not in target:
                    continue
                identity = identities.get(ticker)
                if identity is None:
                    skipped["identity_not_found"] += 1
                    continue
                matched[dimension] += 1
                if insert_production_sharadar_observation(
                    conn, row, run_id, now, company_id=identity[1], security_id=identity[0]
                ):
                    inserted[dimension] += 1
                if fail_after is not None and sum(matched.values()) >= fail_after:
                    raise RuntimeError("PHASE12C_INJECTED_IMPORT_FAILURE")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("PHASE12C_POST_IMPORT_FOREIGN_KEY_FAILURE")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"run_id": run_id, "matched_by_dimension": dict(sorted(matched.items())),
            "inserted_by_dimension": dict(sorted(inserted.items())),
            "logical_changes": sum(inserted.values()), "skipped": dict(sorted(skipped.items()))}


def create_verified_backup(source: Path, backup_dir: Path, stamp: str) -> dict[str, Any]:
    source_evidence = database_inventory(source)
    source_counts = provider_counts(source)
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"fundamentals_provider.phase12c.{stamp}.db"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    evidence = database_inventory(destination)
    if evidence["quick_check"] != "ok" or evidence["foreign_key_violations"]:
        raise RuntimeError("PHASE12C_BACKUP_VERIFICATION_FAILED")
    if evidence["schema_hash"] != source_evidence["schema_hash"] or provider_counts(destination) != source_counts:
        raise RuntimeError("PHASE12C_BACKUP_RECONCILIATION_FAILED")
    evidence["source_path"] = str(source.resolve())
    evidence["source_sha256"] = source_evidence["sha256"]
    evidence["relevant_row_counts_reconciled"] = True
    evidence["independently_openable"] = True
    return evidence


def isolation_inventory(paths: Phase12CPaths) -> dict[str, Any]:
    files = {
        "canonical": paths.canonical_db, "analysis": paths.analysis_db,
        "market": paths.market_db, "taxonomy": paths.taxonomy_db,
    }
    reports = {}
    if paths.reports_dir.exists():
        reports = {str(path.relative_to(paths.reports_dir)): sha256(path) for path in sorted(paths.reports_dir.rglob("*")) if path.is_file()}
    databases = {name: database_inventory(path) for name, path in files.items()}
    return {"databases": databases, "reports": reports, "fingerprint": stable_hash({
        "databases": {name: evidence["sha256"] for name, evidence in databases.items()},
        "reports": reports,
    })}


def disk_gate(paths: Phase12CPaths) -> dict[str, Any]:
    provider_size = paths.provider_db.stat().st_size
    old_stage = max((p.stat().st_size for p in paths.root.glob("temp/fundamentals_v4_1b_production_bootstrap/*/sharadar_fundamentals_5y.csv")), default=500_000_000)
    required = int((provider_size * 3 + old_stage * 4) * 1.25)
    free = shutil.disk_usage(paths.root).free
    if free < required:
        raise RuntimeError("PHASE12C_INSUFFICIENT_FREE_SPACE")
    return {"free_bytes": free, "required_bytes": required, "provider_size": provider_size,
            "assumed_10y_staged_bytes": old_stage * 2, "contingency": 0.25, "ok": True}
