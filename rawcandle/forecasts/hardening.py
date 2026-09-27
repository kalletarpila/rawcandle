from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from rawcandle.forecasts.contracts import FORECAST_FAMILIES
from rawcandle.forecasts.operator import (
    DEFAULT_FORECAST_DB,
    DEFAULT_FUNDAMENTALS_DB,
    acquire_run,
    link_run,
    reconcile_run,
    report_run,
    verify_database,
)
from rawcandle.forecasts.schema import SCHEMA_VERSION, connect_forecasts_db


DEFAULT_BACKUP_DIR = Path(__file__).resolve().parents[2] / "backups" / "forecasts"
DRIFT_POLICY_VERSION = "yahoo_known_ignored_fields_v1"
KNOWN_IGNORED_PATHS = frozenset({
    "financialData.currentRatio", "financialData.debtToEquity",
    "financialData.earningsGrowth", "financialData.ebitda",
    "financialData.ebitdaMargins", "financialData.freeCashflow",
    "financialData.grossMargins", "financialData.grossProfits",
    "financialData.numberOfAnalystOpinions", "financialData.operatingCashflow",
    "financialData.operatingMargins", "financialData.profitMargins",
    "financialData.quickRatio", "financialData.recommendationKey",
    "financialData.recommendationMean", "financialData.returnOnAssets",
    "financialData.returnOnEquity", "financialData.revenueGrowth",
    "financialData.revenuePerShare", "financialData.totalCash",
    "financialData.totalCashPerShare", "financialData.totalDebt",
    "financialData.totalRevenue",
})
CORE_TABLES = (
    "forecast_run", "forecast_fetch", "forecast_snapshot", "forecast_estimate",
    "forecast_price_target", "forecast_earnings_history_reference",
    "forecast_identity_resolution", "forecast_fiscal_link", "forecast_raw_evidence",
)


def _utc(value: str | None = None) -> str:
    parsed = datetime.now(timezone.utc) if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_drift(paths: Iterable[str]) -> dict[str, Any]:
    values = [str(path) for path in paths]
    known = [path for path in values if path in KNOWN_IGNORED_PATHS]
    unknown = [path for path in values if path not in KNOWN_IGNORED_PATHS]
    return {
        "policy_version": DRIFT_POLICY_VERSION,
        "known_ignored_count": len(known),
        "unknown_drift_count": len(unknown),
        "distinct_unknown_paths": sorted(set(unknown)),
    }


def health_report(
    *, forecast_db: str | Path = DEFAULT_FORECAST_DB, lookback_days: int = 7,
    now_utc: str | None = None,
) -> dict[str, Any]:
    database = Path(forecast_db)
    verified = verify_database(database)
    now = datetime.fromisoformat(_utc(now_utc).replace("Z", "+00:00"))
    cutoff = (now - timedelta(days=max(1, int(lookback_days)))).isoformat(timespec="microseconds").replace("+00:00", "Z")
    with connect_forecasts_db(database) as connection:
        runs = [dict(row) for row in connection.execute(
            "SELECT * FROM forecast_run WHERE started_at_utc>=? ORDER BY started_at_utc", (cutoff,)
        )]
        fetches = [dict(row) for row in connection.execute(
            "SELECT * FROM forecast_fetch WHERE fetched_at_utc>=? ORDER BY fetched_at_utc", (cutoff,)
        )]
        identities = [dict(row) for row in connection.execute(
            "SELECT i.* FROM forecast_identity_resolution i JOIN forecast_fetch f USING(fetch_id) "
            "WHERE f.fetched_at_utc>=? ORDER BY i.resolved_at_utc DESC,i.rowid DESC", (cutoff,)
        )]
        links = [dict(row) for row in connection.execute(
            "SELECT l.* FROM forecast_fiscal_link l JOIN forecast_fetch f USING(fetch_id) "
            "WHERE f.fetched_at_utc>=? AND l.knowledge_mode='AS_KNOWN' "
            "ORDER BY l.linked_at_utc DESC,l.rowid DESC", (cutoff,)
        )]
        drift_paths: list[str] = []
        for row in connection.execute("SELECT schema_drift_json FROM forecast_snapshot"):
            drift_paths.extend(json.loads(row[0]))
        raw = connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(LENGTH(body_text)),0),"
            "SUM(CASE WHEN retain_until_utc<=? THEN 1 ELSE 0 END) FROM forecast_raw_evidence",
            (_utc(now_utc),),
        ).fetchone()
        snapshots = {
            str(row[0]): int(row[1]) for row in connection.execute(
                "SELECT forecast_family,COUNT(*) FROM forecast_snapshot GROUP BY forecast_family"
            )
        }
        history = connection.execute(
            "SELECT MIN(fetched_at_utc),MAX(fetched_at_utc) FROM forecast_fetch"
        ).fetchone()
        latest_success = connection.execute(
            "SELECT MAX(completed_at_utc) FROM forecast_run WHERE status='SUCCESS'"
        ).fetchone()[0]
    latest_identity: dict[str, dict[str, Any]] = {}
    for item in identities:
        latest_identity.setdefault(str(item["fetch_id"]), item)
    identity_counts = Counter()
    for item in latest_identity.values():
        identity_counts[str(item["resolution_method"] or item["identity_status"])] += 1
    latest_links: dict[tuple[str, int], dict[str, Any]] = {}
    for item in links:
        latest_links.setdefault((str(item["fetch_id"]), int(item["occurrence_index"])), item)
    status_counts = Counter(item["status"] for item in fetches)
    acquisition = {
        status: int(status_counts.get(status, 0))
        for status in (
            "SUCCESS_CHANGED", "SUCCESS_UNCHANGED", "VALID_NO_DATA",
            "PROVIDER_SYMBOL_UNAVAILABLE", "RATE_LIMITED", "TRANSIENT_FAILURE",
            "MALFORMED_OR_SCHEMA_MISMATCH",
        )
    }
    latest_run = runs[-1] if runs else None
    return {
        "database": verified | {"size_bytes": database.stat().st_size},
        "latest_run_status": latest_run["status"] if latest_run else None,
        "latest_successful_run_timestamp": latest_success,
        "recent_acquisition": {"runs": len(runs), "fetches": len(fetches), **acquisition},
        "identity": {
            key: int(identity_counts.get(key, 0))
            for key in (
                "PROVIDER_IDENTITY", "TICKER_ALIAS_AS_OF", "CURRENT_TICKER",
                "AMBIGUOUS", "UNRESOLVED",
            )
        },
        "fiscal_links": {
            key: sum(item["link_status"] == key for item in latest_links.values())
            for key in ("LINKED", "AMBIGUOUS", "UNRESOLVED")
        },
        "provider_quality": {
            "retries": sum(max(0, int(item["attempt_count"]) - 1) for item in fetches),
            "rate_limits": status_counts.get("RATE_LIMITED", 0),
            **classify_drift(drift_paths),
            "raw_evidence_rows": int(raw[0]), "raw_evidence_bytes": int(raw[1]),
            "expired_raw_evidence_rows": int(raw[2] or 0),
        },
        "history": {
            "snapshot_count_by_family": snapshots,
            "first_observation_timestamp": history[0],
            "latest_observation_timestamp": history[1],
        },
    }


def cleanup_raw_evidence(
    *, forecast_db: str | Path = DEFAULT_FORECAST_DB, apply: bool = False,
    now_utc: str | None = None,
) -> dict[str, Any]:
    database = Path(forecast_db)
    cutoff = _utc(now_utc)
    with connect_forecasts_db(database) as connection:
        row = connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(LENGTH(body_text)),0),MIN(retain_until_utc),"
            "MAX(retain_until_utc) FROM forecast_raw_evidence WHERE retain_until_utc<=?",
            (cutoff,),
        ).fetchone()
        summary = {
            "mode": "APPLY" if apply else "DRY_RUN", "cutoff_utc": cutoff,
            "eligible_rows": int(row[0]), "eligible_bytes": int(row[1]),
            "earliest_expiry": row[2], "latest_expiry": row[3], "deleted_rows": 0,
        }
        if apply and row[0]:
            hashes = [item[0] for item in connection.execute(
                "SELECT raw_hash FROM forecast_raw_evidence WHERE retain_until_utc<=?", (cutoff,)
            )]
            marks = ",".join("?" for _ in hashes)
            connection.execute(f"UPDATE forecast_fetch SET raw_evidence_hash=NULL WHERE raw_evidence_hash IN ({marks})", hashes)
            connection.execute(f"UPDATE forecast_snapshot SET raw_evidence_hash=NULL WHERE raw_evidence_hash IN ({marks})", hashes)
            deleted = connection.execute(f"DELETE FROM forecast_raw_evidence WHERE raw_hash IN ({marks})", hashes).rowcount
            summary["deleted_rows"] = int(deleted)
    summary["quick_check"] = verify_database(database)["quick_check"]
    return summary


def _core_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in CORE_TABLES}


def _backup_name(timestamp_utc: str) -> str:
    stamp = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%S%fZ")
    return f"forecast_{stamp}.db"


def create_backup(
    *, source: str | Path = DEFAULT_FORECAST_DB, destination: str | Path = DEFAULT_BACKUP_DIR,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    source_check = verify_database(source_path)
    created = _utc(created_at_utc)
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    backup_path = destination_path / _backup_name(created)
    if backup_path.exists():
        raise FileExistsError(backup_path)
    temp_path = backup_path.with_suffix(".db.tmp")
    with connect_forecasts_db(source_path) as source_connection:
        source_counts = _core_counts(source_connection)
        with sqlite3.connect(temp_path) as backup_connection:
            source_connection.backup(backup_connection)
            backup_connection.commit()
    with connect_forecasts_db(temp_path) as backup_connection:
        quick_check = str(backup_connection.execute("PRAGMA quick_check").fetchone()[0])
        version_row = backup_connection.execute("SELECT version FROM forecast_schema_version").fetchone()
        backup_counts = _core_counts(backup_connection)
    if quick_check != "ok" or not version_row or version_row[0] != SCHEMA_VERSION or backup_counts != source_counts:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError("forecast backup verification failed")
    os.replace(temp_path, backup_path)
    fingerprint = _sha256(backup_path)
    manifest = {
        "contract_version": "forecast_backup_v1", "created_at_utc": created,
        "source_path": str(source_path.resolve()), "source_schema_version": source_check["schema_version"],
        "source_size_bytes": source_path.stat().st_size, "source_fingerprint_sha256": _sha256(source_path),
        "backup_path": str(backup_path.resolve()), "backup_size_bytes": backup_path.stat().st_size,
        "backup_fingerprint_sha256": fingerprint, "quick_check": quick_check,
        "core_counts": backup_counts,
    }
    manifest_path = backup_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    backup_path.chmod(0o444)
    manifest_path.chmod(0o444)
    return manifest | {"manifest_path": str(manifest_path.resolve())}


def _valid_backup(path: Path) -> bool:
    manifest_path = path.with_suffix(".manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            version = connection.execute(
                "SELECT version FROM forecast_schema_version WHERE db_name='forecasts'"
            ).fetchone()
            counts = _core_counts(connection)
        return (
            manifest.get("backup_fingerprint_sha256") == _sha256(path)
            and quick_check == "ok"
            and version is not None
            and str(version[0]) == SCHEMA_VERSION
            and counts == manifest.get("core_counts")
        )
    except Exception:
        return False


def backup_retention(
    *, backup_dir: str | Path = DEFAULT_BACKUP_DIR, apply: bool = False,
    now_utc: str | None = None,
) -> dict[str, Any]:
    directory = Path(backup_dir)
    now = datetime.fromisoformat(_utc(now_utc).replace("Z", "+00:00"))
    valid = sorted((path for path in directory.glob("forecast_*.db") if _valid_backup(path)), reverse=True)
    keep: set[Path] = set(valid[:1])
    weekly: set[tuple[int, int]] = set()
    monthly: set[tuple[int, int]] = set()
    for path in valid:
        stamp = datetime.strptime(path.stem.removeprefix("forecast_"), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
        age = now - stamp
        if age <= timedelta(days=14):
            keep.add(path)
        elif age <= timedelta(weeks=8):
            key = stamp.isocalendar()[:2]
            if key not in weekly:
                weekly.add(key); keep.add(path)
        elif age <= timedelta(days=366):
            key = (stamp.year, stamp.month)
            if key not in monthly:
                monthly.add(key); keep.add(path)
    selected = [path for path in valid if path not in keep]
    result = {
        "mode": "APPLY" if apply else "DRY_RUN", "valid_backups": len(valid),
        "protected_backups": len(keep), "selected_files": len(selected) * 2,
        "selected_bytes": sum(path.stat().st_size + path.with_suffix(".manifest.json").stat().st_size for path in selected),
        "newest_valid_backup": str(valid[0]) if valid else None,
    }
    if apply:
        for path in selected:
            path.chmod(0o644); path.unlink()
            manifest = path.with_suffix(".manifest.json"); manifest.chmod(0o644); manifest.unlink()
        result["deleted_backups"] = len(selected)
        remaining = sorted((path for path in directory.glob("forecast_*.db") if _valid_backup(path)), reverse=True)
        result["remaining_newest_valid_backup"] = str(remaining[0]) if remaining else None
        if valid and not remaining:
            raise RuntimeError("backup retention removed every valid backup")
    return result


def restore_backup(
    *, backup: str | Path, target: str | Path, apply_production: bool = False,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
) -> dict[str, Any]:
    backup_path = Path(backup)
    target_path = Path(target)
    if backup_path.resolve() == target_path.resolve():
        raise ValueError("backup and restore target must differ")
    if target_path.resolve() == DEFAULT_FORECAST_DB.resolve() and not apply_production:
        raise PermissionError("production restore requires --apply-production")
    if not _valid_backup(backup_path):
        raise ValueError("backup or manifest validation failed")
    manifest = json.loads(backup_path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    safety = None
    if target_path.exists():
        try:
            verify_database(target_path)
            safety = create_backup(source=target_path, destination=backup_dir)
        except Exception as exc:
            if target_path.resolve() != DEFAULT_FORECAST_DB.resolve():
                raise ValueError("existing restore target is not a valid forecast database") from exc
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="forecast-restore-", suffix=".db", dir=target_path.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        with sqlite3.connect(f"file:{backup_path.resolve()}?mode=ro", uri=True) as source_connection:
            with sqlite3.connect(temp_path) as target_connection:
                source_connection.backup(target_connection)
        verify_database(temp_path)
        with sqlite3.connect(temp_path) as restored_connection:
            if _core_counts(restored_connection) != manifest["core_counts"]:
                raise RuntimeError("restored core counts differ from manifest")
        os.replace(temp_path, target_path)
        directory_fd = os.open(target_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp_path.unlink(missing_ok=True)
    return {"target": str(target_path), "quick_check": verify_database(target_path)["quick_check"], "safety_backup": safety and safety["backup_path"]}


def universe_preview(
    *, fundamentals_db: str | Path = DEFAULT_FUNDAMENTALS_DB,
    minimum_interval_seconds: float = 0.5,
) -> dict[str, Any]:
    path = Path(fundamentals_db)
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        active = connection.execute(
            "SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1"
        ).fetchone()
        if active is None:
            raise RuntimeError("no active Fundamentals operational universe")
        rows = connection.execute(
            "SELECT m.*,s.active security_active,s.current_ticker security_ticker "
            "FROM fundamentals_operational_universe_member m "
            "LEFT JOIN security s ON s.security_id=m.security_id "
            "WHERE m.universe_version_id=? ORDER BY m.company_id", (active[0],)
        ).fetchall()
    symbols: list[str] = []
    exclusions: Counter[str] = Counter()
    companies: set[int] = set()
    securities: set[int] = set()
    for row in rows:
        companies.add(int(row["company_id"]))
        if row["membership_status"] != "ACTIVE_SINGLE_SECURITY":
            exclusions[str(row["membership_status"])] += 1
        elif row["security_id"] is None or int(row["security_active"] or 0) != 1:
            exclusions["INACTIVE_OR_MISSING_SECURITY"] += 1
        elif not str(row["current_ticker"] or row["security_ticker"] or "").strip():
            exclusions["MISSING_YAHOO_SYMBOL_ROUTE"] += 1
        else:
            securities.add(int(row["security_id"]))
            symbols.append(str(row["current_ticker"] or row["security_ticker"]).strip().upper())
    symbols = list(dict.fromkeys(symbols))
    requests = len(symbols) * len(FORECAST_FAMILIES)
    return {
        "authority": "fundamentals_v4.fundamentals_operational_universe_active_version/member",
        "universe_version_id": str(active[0]), "total_candidates": len(rows),
        "company_count": len(companies), "security_count": len(securities),
        "symbols_count": len(symbols), "symbols": symbols,
        "excluded_count": sum(exclusions.values()), "excluded_reasons": dict(sorted(exclusions.items())),
        "estimated_requests_per_day": requests,
        "ideal_minimum_runtime_seconds": requests * float(minimum_interval_seconds),
    }


def daily_workflow(
    *, symbols: Iterable[str] | None = None, max_symbols: int | None = None,
    forecast_db: str | Path = DEFAULT_FORECAST_DB,
    fundamentals_db: str | Path = DEFAULT_FUNDAMENTALS_DB,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR, transport: Any = None,
) -> dict[str, Any]:
    if symbols is None and (max_symbols is None or max_symbols < 1):
        raise ValueError("daily workflow requires a positive universe bound")
    if symbols is not None and max_symbols is not None:
        raise ValueError("symbols and max_symbols are mutually exclusive")
    verify_database(forecast_db)
    backup = create_backup(source=forecast_db, destination=backup_dir)
    universe = None
    if symbols is None:
        universe = universe_preview(fundamentals_db=fundamentals_db)
        selected = tuple(universe["symbols"][:max_symbols])
    else:
        selected = tuple(dict.fromkeys(
            str(item).strip().upper() for item in symbols if str(item).strip()
        ))
    if not selected:
        raise ValueError("daily workflow resolved no symbols")
    outcome = acquire_run(
        forecast_db=forecast_db, fundamentals_db=fundamentals_db,
        symbols=selected, transport=transport,
    )
    errors: dict[str, str] = {}
    try:
        link = link_run(outcome.run_id, forecast_db=forecast_db, fundamentals_db=fundamentals_db)
    except Exception as exc:
        link = {}
        errors["link"] = f"{type(exc).__name__}: {exc}"
    try:
        reconciliation = reconcile_run(
            outcome.run_id, forecast_db=forecast_db, fundamentals_db=fundamentals_db
        )
    except Exception as exc:
        reconciliation = {}
        errors["reconciliation"] = f"{type(exc).__name__}: {exc}"
    try:
        report = report_run(outcome.run_id, forecast_db=forecast_db)
    except Exception as exc:
        report = None
        errors["report"] = f"{type(exc).__name__}: {exc}"
    run_status = report["run_status"] if report else "UNKNOWN"
    return {
        "backup": backup, "run_id": outcome.run_id, "acquisition": dict(outcome.counters),
        "link": link, "reconciliation": reconciliation,
        "report": report, "errors": errors,
        "terminal_status": "SUCCESS" if run_status == "SUCCESS" and not errors else "PARTIAL",
        "universe": None if universe is None else {
            "authority": universe["authority"],
            "available_symbols": universe["symbols_count"],
            "selected_symbols": len(selected),
            "max_symbols": max_symbols,
        },
        "failure_policy": "INDIVIDUAL_FAILURE_PARTIAL_DB_OR_BACKUP_FAIL_CLOSED_LINK_FAILURE_ACQUISITION_PRESERVED",
    }
