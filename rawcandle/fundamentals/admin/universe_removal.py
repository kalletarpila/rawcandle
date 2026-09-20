"""Controlled Fundamentals-universe removal with preview and copy-only rehearsal."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.batch_add_tickers import _assert_clean_worktree
from rawcandle.fundamentals.admin.contracts import AdminOperationType, fingerprint, utc_now
from rawcandle.fundamentals.admin.refresh_copy_runtime import fresh_rebuild_canonical
from rawcandle.fundamentals.admin.production_transaction import BACKUP_ROOT, production_lock
from rawcandle.fundamentals.admin.publication_journal import (
    ACTIVE_JOURNAL_PATH, PUBLICATION_ROLES, guard_production_writes,
    prepare_journal, restore_old_generation, update_journal,
)
from rawcandle.fundamentals.admin.refresh_production import (
    _candidate_manifest, _replace_role, _storage_preflight, _verified_backups,
)
from rawcandle.fundamentals.operating_income_v2.full_rebuild import rebuild_v2_analysis
from rawcandle.fundamentals.phase13b_foundation import online_backup, stable_hash, universe_identity


CONTRACT_VERSION = "PHASE13G3_13_CONTROLLED_UNIVERSE_REMOVAL_V1"
REASON = "BNC-specific contradictory Sharadar fiscal metadata"
MODEL_TABLES = {
    "score": "score_result",
    "lifecycle": "lifecycle_revised_result",
    "valuation": "valuation_revised_result",
    "delta": "fundamental_delta_result",
    "diagnostics": "diagnostic_flag_endpoint",
    "rp": "relative_position_result",
    "relative_coverage": "relative_position_coverage",
    "rv": "relative_valuation_company_result",
}


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def production_file_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for role, path in paths.as_dict().items():
        stat = path.stat()
        state[role] = {
            "path": str(path.resolve()), "sha256": _sha256(path),
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        }
    return state


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _identity(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.canonical_db) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT c.company_id,c.company_key,c.company_name,c.status,s.security_id,s.current_ticker,"
            "s.active,s.valid_from,s.valid_to FROM company c JOIN security s USING(company_id) "
            "WHERE UPPER(s.current_ticker)=UPPER(?) ORDER BY s.security_id", (ticker,),
        )]
        if len(rows) != 1:
            raise ValueError("UNIVERSE_REMOVAL_IDENTITY_NOT_EXACTLY_ONE_SECURITY")
        company_id, security_id = int(rows[0]["company_id"]), int(rows[0]["security_id"])
        company_securities = [dict(row) for row in connection.execute(
            "SELECT security_id,current_ticker,active FROM security WHERE company_id=? ORDER BY security_id",
            (company_id,),
        )]
        aliases = [dict(row) for row in connection.execute(
            "SELECT * FROM ticker_alias WHERE security_id=? ORDER BY alias_id", (security_id,),
        )]
        active_memberships = int(connection.execute(
            "SELECT COUNT(*) FROM fundamentals_operational_universe_member m "
            "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) "
            "WHERE m.company_id=?", (company_id,),
        ).fetchone()[0])
    exclusive = len(company_securities) == 1 and all(
        str(row["current_ticker"]).upper() == ticker.upper() for row in company_securities
    )
    if not exclusive or active_memberships != 1:
        raise ValueError("UNIVERSE_REMOVAL_IDENTITY_OWNERSHIP_AMBIGUOUS")
    return {
        **rows[0], "company_id": company_id, "security_id": security_id,
        "company_security_exclusive": True, "company_securities": company_securities,
        "ticker_aliases": aliases, "active_universe_memberships": active_memberships,
    }


def _provider_footprint(path: Path, ticker: str, company_id: int, security_id: int) -> dict[str, Any]:
    with _readonly(path) as connection:
        dimensions = {str(row["dimension"]): int(row["n"]) for row in connection.execute(
            "SELECT dimension,COUNT(*) n FROM sharadar_fundamental_observation "
            "WHERE UPPER(ticker)=UPPER(?) GROUP BY dimension", (ticker,),
        )}
        source_keys = int(connection.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?)", (ticker,),
        ).fetchone()[0])
        observations = int(connection.execute(
            "SELECT COUNT(*) FROM provider_observation WHERE company_id=? OR security_id=?",
            (company_id, security_id),
        ).fetchone()[0])
        retained = int(connection.execute(
            "SELECT COUNT(*) FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id) "
            "WHERE UPPER(s.ticker)=UPPER(?) AND COALESCE(po.provenance_json,'') LIKE '%RETAINED_OUTSIDE_SOURCE_WINDOW%'",
            (ticker,),
        ).fetchone()[0])
        metadata = int(connection.execute(
            "SELECT COUNT(*) FROM sharadar_ticker_metadata WHERE UPPER(ticker)=UPPER(?)", (ticker,),
        ).fetchone()[0])
        runs = [dict(row) for row in connection.execute(
            "SELECT run_id,COUNT(*) observation_count FROM provider_observation "
            "WHERE company_id=? OR security_id=? GROUP BY run_id ORDER BY run_id", (company_id, security_id),
        )]
    return {
        "observation_count": observations, "source_key_count": source_keys,
        "arq_count": dimensions.get("ARQ", 0), "mrq_count": dimensions.get("MRQ", 0),
        "other_dimensions": {key: value for key, value in dimensions.items() if key not in {"ARQ", "MRQ"}},
        "retained_outside_source_window": retained, "metadata_rows": metadata,
        "provider_run_references": runs,
    }


def _canonical_footprint(path: Path, company_id: int, security_id: int) -> dict[str, Any]:
    with _readonly(path) as connection:
        counts: dict[str, int] = {}
        for table in (
            "company", "security", "ticker_alias", "provider_company_identity", "provider_security_identity",
            "company_cik", "company_fiscal_calendar_profile", "company_fiscal_year_anchor",
            "v4_quarter", "v4_quarter_financials", "v4_ttm_values", "v4_ttm_contract",
            "v4_ttm_input_quarter", "v4_field_provenance", "v4_common_earnings_provenance",
            "v4_operating_working_capital_provenance", "fundamentals_quarter_economic_regime",
            "fundamentals_ttm_economic_regime",
        ):
            if not _table_exists(connection, table):
                continue
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
            if "company_id" in columns:
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE company_id=?", (company_id,)).fetchone()[0])
            elif "security_id" in columns:
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE security_id=?", (security_id,)).fetchone()[0])
            elif "quarter_id" in columns:
                counts[table] = int(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE quarter_id IN (SELECT quarter_id FROM v4_quarter WHERE company_id=?)",
                    (company_id,),
                ).fetchone()[0])
        quarter = dict(connection.execute(
            "SELECT COUNT(*) quarter_count,COUNT(first_public_result_date) first_public_count,"
            "MIN(fiscal_year||'-'||fiscal_quarter) earliest,MAX(fiscal_year||'-'||fiscal_quarter) latest,"
            "MIN(first_public_result_date) min_first_public,MAX(first_public_result_date) max_first_public "
            "FROM v4_quarter WHERE company_id=?", (company_id,),
        ).fetchone())
        active_member = int(connection.execute(
            "SELECT COUNT(*) FROM fundamentals_operational_universe_member m "
            "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) WHERE m.company_id=?",
            (company_id,),
        ).fetchone()[0])
    return {"tables": counts, **quarter, "active_universe_memberships": active_member}


def _analysis_footprint(path: Path, company_id: int, ticker: str) -> dict[str, Any]:
    with _readonly(path) as connection:
        output: dict[str, int] = {}
        for label, table in MODEL_TABLES.items():
            if not _table_exists(connection, table):
                output[label] = 0
                continue
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
            clauses, params = [], []
            if "company_id" in columns:
                clauses.append("company_id=?"); params.append(company_id)
            if "ticker" in columns:
                clauses.append("UPPER(ticker)=UPPER(?)"); params.append(ticker)
            output[label] = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {' OR '.join(clauses)}", params,
            ).fetchone()[0]) if clauses else 0
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    return {"tables": output, "total_direct_rows": sum(output.values()), "quick_check": quick, "foreign_key_errors": foreign}


def footprint(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    identity = _identity(paths, ticker)
    company_id, security_id = identity["company_id"], identity["security_id"]
    return {
        "ticker": ticker.upper(), "identity": identity,
        "provider": _provider_footprint(paths.provider_db, ticker, company_id, security_id),
        "canonical": _canonical_footprint(paths.canonical_db, company_id, security_id),
        "analysis": _analysis_footprint(paths.analysis_db, company_id, ticker),
    }


def _render_preview(result: Mapping[str, Any]) -> str:
    f = result["footprint"]
    return (
        "# Fundamentals Universe Removal Preview\n\n"
        f"- Ticker: `{f['ticker']}`\n- Action: Remove from Fundamentals universe\n"
        f"- Reason: `{result['reason']}`\n- Production changed: No\n\n"
        "## Current Footprint\n\n"
        f"- Provider observations: `{f['provider']['observation_count']}` "
        f"(ARQ `{f['provider']['arq_count']}`, MRQ `{f['provider']['mrq_count']}`)\n"
        f"- Canonical quarters: `{f['canonical']['quarter_count']}`\n"
        f"- Analysis direct rows: `{f['analysis']['total_direct_rows']}`\n\n"
        "## Identity\n\n"
        f"- Company/security: `{f['identity']['company_id']}` / `{f['identity']['security_id']}`\n"
        f"- Exclusive one-to-one ownership: `{f['identity']['company_security_exclusive']}`\n\n"
        "## Expected Candidate Effect\n\n"
        "BNC provider history and metadata are removed; canonical financial state is rebuilt without BNC; "
        "the historical identity is retired and omitted from the new active universe; analysis receives one full V2 + RP V2 + RV rebuild.\n\n"
        "## Safety\n\nProduction files are read-only in Preview.\n\n## Next Step\n\n`Test on copies`\n"
    )


def run_preview(
    ticker: str, *, source_paths: BatchAddTickerPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT,
) -> dict[str, Any]:
    normalized = ticker.strip().upper()
    if normalized != "BNC":
        raise PermissionError("PHASE13G3_13_ONLY_BNC_AUTHORIZED")
    paths = source_paths or BatchAddTickerPaths()
    before = production_file_state(paths)
    current = footprint(paths, normalized)
    preview_fingerprint = fingerprint({
        "contract_version": CONTRACT_VERSION, "ticker": normalized,
        "reason": REASON, "production_file_state": before, "footprint": current,
    })
    run_id = stable_run_id(AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS, preview_fingerprint, suffix="preview")
    writer = AdminRunWriter(run_id, AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS, root=run_root)
    result = {
        "contract_version": CONTRACT_VERSION, "operation_type": AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS.value,
        "mode": "PREVIEW", "outcome": "COMPLETED", "run_id": run_id, "ticker": normalized,
        "reason": REASON, "preview_fingerprint": preview_fingerprint, "footprint": current,
        "production_file_state": before, "production_changed": False,
        "artifact_dir": str(writer.run_dir),
    }
    writer.write_json("removal_preview.json", result)
    writer.write_json("result.json", result)
    writer.write_text("operation_report.md", _render_preview(result))
    writer.write_manifest()
    writer.write_exit_code(0)
    if production_file_state(paths) != before:
        raise RuntimeError("REMOVAL_PREVIEW_CHANGED_PRODUCTION")
    return result


def _non_target_provider_fingerprint(path: Path, ticker: str, company_id: int, security_id: int) -> str:
    with _readonly(path) as connection:
        observations = [tuple(row) for row in connection.execute(
            "SELECT * FROM provider_observation WHERE COALESCE(company_id,-1)<>? "
            "AND COALESCE(security_id,-1)<>? ORDER BY observation_id",
            (company_id, security_id),
        )]
        source = [tuple(row) for row in connection.execute(
            "SELECT * FROM sharadar_fundamental_observation WHERE UPPER(ticker)<>UPPER(?) ORDER BY observation_id",
            (ticker,),
        )]
        metadata = [tuple(row) for row in connection.execute(
            "SELECT * FROM sharadar_ticker_metadata WHERE UPPER(ticker)<>UPPER(?) ORDER BY table_name,ticker,lastupdated",
            (ticker,),
        )]
        controls = {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in ("provider_run", "schema_version", "sharadar_action_metadata")
        }
        if _table_exists(connection, "sharadar_refresh_state"):
            controls["sharadar_refresh_state"] = [
                tuple(row) for row in connection.execute("SELECT * FROM sharadar_refresh_state ORDER BY rowid")
            ]
    return stable_hash({
        "provider_observation": observations,
        "source": source,
        "metadata": metadata,
        "controls": controls,
    })


def _non_target_canonical_state(path: Path, company_id: int) -> dict[str, str]:
    with _readonly(path) as connection:
        first_public = [tuple(row) for row in connection.execute(
            "SELECT company_id,fiscal_year,fiscal_quarter,first_public_result_date FROM v4_quarter "
            "WHERE company_id<>? ORDER BY company_id,fiscal_year,fiscal_quarter", (company_id,),
        )]
        identities = [tuple(row) for row in connection.execute(
            "SELECT c.company_id,c.company_key,c.company_name,c.status,s.security_id,s.current_ticker,s.active,s.valid_from,s.valid_to "
            "FROM company c JOIN security s USING(company_id) WHERE c.company_id<>? ORDER BY c.company_id,s.security_id",
            (company_id,),
        )]
    return {"first_public_fingerprint": stable_hash(first_public), "identity_fingerprint": stable_hash(identities)}


def _delete_provider_ticker(path: Path, ticker: str, company_id: int, security_id: int) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        ids = [str(row[0]) for row in connection.execute(
            "SELECT observation_id FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?)", (ticker,),
        )]
        source_rows = connection.execute(
            "DELETE FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?)", (ticker,),
        ).rowcount
        provider_rows = connection.execute(
            "DELETE FROM provider_observation WHERE company_id=? OR security_id=?", (company_id, security_id),
        ).rowcount
        metadata_rows = connection.execute(
            "DELETE FROM sharadar_ticker_metadata WHERE UPPER(ticker)=UPPER(?)", (ticker,),
        ).rowcount
        connection.commit()
    return {"source_rows_removed": source_rows, "provider_rows_removed": provider_rows, "metadata_rows_removed": metadata_rows, "source_ids": len(ids)}


def _retire_from_active_universe(path: Path, identity: Mapping[str, Any], *, applied_at: str) -> dict[str, Any]:
    company_id, security_id = int(identity["company_id"]), int(identity["security_id"])
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        active = str(connection.execute(
            "SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1"
        ).fetchone()[0])
        members = [dict(row) for row in connection.execute(
            "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=? AND company_id<>? ORDER BY company_id",
            (active, company_id),
        )]
        aliases = [dict(row) for row in connection.execute(
            "SELECT a.* FROM fundamentals_operational_universe_member_alias a "
            "WHERE a.universe_version_id=? AND a.company_id<>? ORDER BY company_id,security_id,alias_ticker",
            (active, company_id),
        )]
        universe = universe_identity(members, aliases, as_of_date=applied_at[:10])
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE security SET active=0,valid_to=COALESCE(valid_to,?),updated_at_utc=? WHERE security_id=?",
            (applied_at[:10], applied_at, security_id),
        )
        connection.execute("UPDATE company SET status='RETIRED',updated_at_utc=? WHERE company_id=?", (applied_at, company_id))
        connection.execute("DELETE FROM fundamentals_operational_universe_active_version")
        connection.execute(
            "INSERT OR IGNORE INTO fundamentals_operational_universe_version VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (universe["universe_version_id"], "PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1", "CURRENT_OPERATIONAL_UNIVERSE",
             applied_at[:10], universe["source_fingerprint"], universe["economic_result_fingerprint"], universe["physical_content_fingerprint"],
             "COMPLETE", universe["member_count"], universe["company_count"], universe["active_security_count"],
             universe["zero_active_company_count"], universe["multi_active_company_count"], applied_at, applied_at),
        )
        for row in members:
            connection.execute(
                "INSERT OR REPLACE INTO fundamentals_operational_universe_member VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (universe["universe_version_id"], row["company_id"], row["security_id"], row["current_ticker"], row["market"],
                 row["membership_status"], row["identity_resolution_status"], row["active_security_count"], row["all_security_count"],
                 row["effective_start_date"], row["effective_end_date"], row["source"], row["reason"], row["created_at_utc"], row["updated_at_utc"]),
            )
        for row in aliases:
            connection.execute(
                "INSERT OR IGNORE INTO fundamentals_operational_universe_member_alias VALUES (?,?,?,?,?,?,?,?)",
                (universe["universe_version_id"], row["company_id"], row["security_id"], row["alias_ticker"],
                 row["provider"], row["valid_from"], row["valid_to"], row["source"]),
            )
        connection.execute(
            "INSERT INTO fundamentals_operational_universe_active_version VALUES (1,?,?)",
            (universe["universe_version_id"], applied_at),
        )
        connection.commit()
    return {"old_universe_version_id": active, "new_universe": universe, "identity_retained_as_historical": True}


def _health(path: Path) -> dict[str, Any]:
    with _readonly(path) as connection:
        return {
            "quick_check": str(connection.execute("PRAGMA quick_check").fetchone()[0]),
            "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
        }


def _company_model_fingerprints(path: Path, table: str, *, exclude_company_id: int) -> dict[int, str]:
    with _readonly(path) as connection:
        if not _table_exists(connection, table):
            return {}
        columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]
        if "company_id" not in columns:
            return {}
        stable_columns = [
            column for column in columns
            if not any(token in column for token in (
                "created_at", "updated_at", "applied_at", "generated_at", "calculated_at",
                "run_id", "fingerprint", "evidence_json", "provenance_json",
            ))
            and (not column.endswith("_id") or column in {"company_id", "security_id"})
        ]
        rows = [dict(row) for row in connection.execute(
            f"SELECT {','.join(stable_columns)} FROM {table} WHERE company_id<>? ORDER BY company_id,{','.join(stable_columns)}",
            (exclude_company_id,),
        )]
    if table == "score_result":
        for row in rows:
            details = json.loads(str(row.get("missing_input_reason") or "{}"))
            details.pop("structural_contract_fingerprint", None)
            row["missing_input_reason"] = details
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["company_id"]), []).append(row)
    return {company_id: stable_hash(values) for company_id, values in grouped.items()}


def _analysis_effects(before: Path, after: Path, company_id: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for label, table in (("score", "score_result"), ("lifecycle", "lifecycle_revised_result"), ("valuation", "valuation_revised_result"), ("rp", "relative_position_result"), ("rv", "relative_valuation_company_result")):
        left = _company_model_fingerprints(before, table, exclude_company_id=company_id)
        right = _company_model_fingerprints(after, table, exclude_company_id=company_id)
        changed = sorted(key for key in left.keys() | right.keys() if left.get(key) != right.get(key))
        output[label] = {"affected_company_count": len(changed), "affected_company_ids": changed}
    return output


def _render_test(result: Mapping[str, Any]) -> str:
    before, after = result["footprint_before"], result["footprint_after"]
    effects = result["analysis_effects"]
    return (
        "# Fundamentals Universe Removal Test on Copies\n\n"
        f"- Ticker: `{result['ticker']}`\n- Outcome: `{result['outcome']}`\n- Full B1 rebuild: `{result['analysis_rebuild']['status']}`\n\n"
        "## Provider\n\n"
        f"- BNC rows before/after: `{before['provider']['observation_count']} / {after['provider']['observation_count']}`\n"
        f"- Non-BNC fingerprint preserved: `{result['non_target_provider_preserved']}`\n\n"
        "## Canonical\n\n"
        f"- BNC quarters before/after: `{before['canonical']['quarter_count']} / {after['canonical']['quarter_count']}`\n"
        f"- BNC first-public rows removed: `{before['canonical']['first_public_count']}`\n"
        f"- Non-BNC first-public preserved: `{result['non_target_first_public_preserved']}`\n\n"
        "## Analysis\n\n"
        f"- BNC direct rows before/after: `{before['analysis']['total_direct_rows']} / {after['analysis']['total_direct_rows']}`\n"
        f"- Other Score/Lifecycle/Valuation affected: `{effects['score']['affected_company_count']} / "
        f"{effects['lifecycle']['affected_company_count']} / {effects['valuation']['affected_company_count']}`\n"
        f"- Other RP/RV affected: `{effects['rp']['affected_company_count']} / {effects['rv']['affected_company_count']}`\n\n"
        "## Safety\n\nProduction writes: `0`. Candidate databases were cleaned after evidence capture.\n"
    )


def run_test(
    *, preview_payload_path: Path, preview_fingerprint: str,
    source_paths: BatchAddTickerPaths | None = None, run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT, as_of_date: str | None = None,
) -> dict[str, Any]:
    paths = source_paths or BatchAddTickerPaths()
    preview = json.loads(preview_payload_path.read_text(encoding="utf-8"))
    if preview.get("preview_fingerprint") != preview_fingerprint or preview.get("ticker") != "BNC":
        raise ValueError("UNIVERSE_REMOVAL_PREVIEW_BINDING_INVALID")
    before_files = production_file_state(paths)
    if preview.get("production_file_state") != before_files:
        raise ValueError("UNIVERSE_REMOVAL_STALE_PREVIEW")
    run_id = stable_run_id(AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS, preview_fingerprint, suffix="test")
    writer = AdminRunWriter(run_id, AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS, root=run_root)
    lane = temp_root / run_id
    lane.mkdir(parents=True, exist_ok=False)
    identity = preview["footprint"]["identity"]
    company_id, security_id = int(identity["company_id"]), int(identity["security_id"])
    result: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "operation_type": AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS.value,
        "mode": "COPY_ONLY_APPLY", "outcome": "FAILED", "run_id": run_id, "ticker": "BNC",
        "preview_run_id": preview.get("run_id"), "preview_fingerprint": preview_fingerprint,
        "artifact_dir": str(writer.run_dir), "production_writes": 0,
    }
    try:
        provider = lane / "provider_candidate.db"
        canonical = lane / "canonical_candidate.db"
        analysis = lane / "analysis_candidate.db"
        result["copies"] = {
            "provider": online_backup(paths.provider_db, provider),
            "canonical": online_backup(paths.canonical_db, canonical),
        }
        before = footprint(paths, "BNC")
        provider_non_target = _non_target_provider_fingerprint(provider, "BNC", company_id, security_id)
        canonical_non_target = _non_target_canonical_state(canonical, company_id)
        result["provider_removal"] = _delete_provider_ticker(provider, "BNC", company_id, security_id)
        if provider_non_target != _non_target_provider_fingerprint(provider, "BNC", company_id, security_id):
            raise RuntimeError("UNIVERSE_REMOVAL_NON_TARGET_PROVIDER_CHANGED")
        applied_at = utc_now()
        result["canonical_rebuild"] = fresh_rebuild_canonical(
            provider, canonical, applied_at=applied_at, affected_company_ids=[company_id],
        )
        result["universe_removal"] = _retire_from_active_universe(canonical, identity, applied_at=applied_at)
        canonical_after_state = _non_target_canonical_state(canonical, company_id)
        if canonical_non_target != canonical_after_state:
            raise RuntimeError("UNIVERSE_REMOVAL_NON_TARGET_CANONICAL_CONTROL_CHANGED")
        output = writer.run_dir / "full_v2_rebuild"
        result["analysis_rebuild"] = rebuild_v2_analysis(
            analysis,
            {"provider": provider, "canonical": canonical, "market": paths.market_db, "taxonomy": paths.taxonomy_db},
            as_of_date=as_of_date or date.today().isoformat(), output=output,
        )
        after_paths = BatchAddTickerPaths(provider, canonical, analysis, paths.market_db, paths.taxonomy_db)
        after = {
            "ticker": "BNC", "identity": identity,
            "provider": _provider_footprint(provider, "BNC", company_id, security_id),
            "canonical": _canonical_footprint(canonical, company_id, security_id),
            "analysis": _analysis_footprint(analysis, company_id, "BNC"),
        }
        result.update(
            footprint_before=before, footprint_after=after,
            non_target_provider_preserved=True,
            non_target_first_public_preserved=canonical_non_target["first_public_fingerprint"] == canonical_after_state["first_public_fingerprint"],
            non_target_identity_preserved=canonical_non_target["identity_fingerprint"] == canonical_after_state["identity_fingerprint"],
            analysis_effects=_analysis_effects(paths.analysis_db, analysis, company_id),
            health={role: _health(path) for role, path in {"provider": provider, "canonical": canonical, "analysis": analysis}.items()},
        )
        if after["provider"]["observation_count"] or after["canonical"]["quarter_count"] or after["analysis"]["total_direct_rows"]:
            raise RuntimeError("UNIVERSE_REMOVAL_BNC_REMAINS_IN_CANDIDATE")
        if after["canonical"]["active_universe_memberships"]:
            raise RuntimeError("UNIVERSE_REMOVAL_BNC_REMAINS_ACTIVE")
        if any(item["quick_check"] != "ok" or item["foreign_key_errors"] for item in result["health"].values()):
            raise RuntimeError("UNIVERSE_REMOVAL_CANDIDATE_INTEGRITY_FAILED")
        if any(result["analysis_effects"][label]["affected_company_count"] for label in ("score", "lifecycle", "valuation")):
            raise RuntimeError("UNIVERSE_REMOVAL_UNRELATED_ABSOLUTE_MODEL_CHANGED")
        result["outcome"] = "COMPLETED"
        writer.write_json("removal_test_evidence.json", result)
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_test(result))
        writer.write_exit_code(0)
        return result
    finally:
        shutil.rmtree(lane, ignore_errors=True)
        result["candidate_cleanup"] = {"status": "COMPLETED", "lane_exists": lane.exists()}
        result["production_file_state_after"] = production_file_state(paths)
        result["production_unchanged"] = result["production_file_state_after"] == before_files
        if writer.run_dir.exists():
            writer.write_json("result.json", result)
            if result.get("outcome") == "COMPLETED":
                writer.write_text("operation_report.md", _render_test(result))
            writer.write_manifest()
        if not result["production_unchanged"]:
            raise RuntimeError("UNIVERSE_REMOVAL_TEST_CHANGED_PRODUCTION")


def assert_production_authorization(
    *, preview: Mapping[str, Any], test: Mapping[str, Any], preview_fingerprint: str,
    current_state: Mapping[str, Any], confirm_production: bool,
) -> None:
    if not confirm_production:
        raise PermissionError("UNIVERSE_REMOVAL_CONFIRM_PRODUCTION_REQUIRED")
    if preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("UNIVERSE_REMOVAL_PRODUCTION_PREVIEW_BINDING_INVALID")
    if preview.get("ticker") != "BNC" or test.get("ticker") != "BNC":
        raise ValueError("UNIVERSE_REMOVAL_PRODUCTION_TARGET_INVALID")
    if (
        test.get("mode") != "COPY_ONLY_APPLY"
        or test.get("outcome") != "COMPLETED"
        or test.get("production_unchanged") is not True
    ):
        raise ValueError("UNIVERSE_REMOVAL_MATCHING_SUCCESSFUL_TEST_REQUIRED")
    if test.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("UNIVERSE_REMOVAL_TEST_PREVIEW_BINDING_INVALID")
    if test.get("preview_run_id") != preview.get("run_id"):
        raise ValueError("UNIVERSE_REMOVAL_TEST_PREVIEW_RUN_INVALID")
    if test.get("production_file_state_after") != current_state:
        raise ValueError("UNIVERSE_REMOVAL_TEST_GENERATION_CHANGED")
    if preview.get("production_file_state") != current_state:
        raise ValueError("UNIVERSE_REMOVAL_PRODUCTION_GENERATION_CHANGED")


def run_production(
    *, preview_payload_path: Path, preview_fingerprint: str, test_run_id: str,
    confirm_production: bool, source_paths: BatchAddTickerPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT, temp_root: Path = ADMIN_TEMP_ROOT,
    backup_root: Path = BACKUP_ROOT, journal_path: Path = ACTIVE_JOURNAL_PATH,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Publish a bound removal generation; callers need separate explicit authorization."""
    paths = source_paths or BatchAddTickerPaths()
    preview = json.loads(preview_payload_path.read_text(encoding="utf-8"))
    test_path = run_root / test_run_id / "result.json"
    if Path(test_run_id).name != test_run_id or not test_path.is_file():
        raise ValueError("UNIVERSE_REMOVAL_TEST_RUN_ID_INVALID")
    test = json.loads(test_path.read_text(encoding="utf-8"))
    if not confirm_production:
        raise PermissionError("UNIVERSE_REMOVAL_CONFIRM_PRODUCTION_REQUIRED")
    git_state = _assert_clean_worktree()
    run_id = stable_run_id(AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS, preview_fingerprint, suffix="production")
    writer = AdminRunWriter(run_id, AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS, root=run_root)
    lane = temp_root / run_id / "candidates"
    backup_dir = backup_root / run_id
    identity = preview["footprint"]["identity"]
    company_id, security_id = int(identity["company_id"]), int(identity["security_id"])
    journal: dict[str, Any] | None = None
    write_boundary = False
    result: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "operation_type": AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS.value,
        "mode": "PRODUCTION_APPLY", "outcome": "FAILED", "run_id": run_id, "ticker": "BNC",
        "preview_run_id": preview.get("run_id"), "test_run_id": test_run_id,
        "preview_fingerprint": preview_fingerprint, "artifact_dir": str(writer.run_dir),
        "git_state": git_state, "warnings": [],
    }
    if git_state.get("dirty"):
        result["warnings"].append({
            "code": "DIRTY_GIT_WORKTREE",
            "message": "Git worktree contains uncommitted changes.",
        })
    try:
        with production_lock():
            result["recovery_preflight"] = guard_production_writes(journal_path)
            current_state = production_file_state(paths)
            assert_production_authorization(
                preview=preview, test=test, preview_fingerprint=preview_fingerprint,
                current_state=current_state, confirm_production=confirm_production,
            )
            result["production_file_state_before"] = current_state
            if production_file_state(paths) != current_state:
                raise ValueError("UNIVERSE_REMOVAL_PRODUCTION_GENERATION_CHANGED_AFTER_LOCK")
            _storage_preflight(paths, temp_root=temp_root, backup_root=backup_root)
            lane.mkdir(parents=True, exist_ok=False)
            provider, canonical, analysis = (
                lane / "provider.db", lane / "canonical.db", lane / "analysis.db"
            )
            online_backup(paths.provider_db, provider)
            online_backup(paths.canonical_db, canonical)
            provider_non_target = _non_target_provider_fingerprint(
                provider, "BNC", company_id, security_id,
            )
            canonical_non_target = _non_target_canonical_state(canonical, company_id)
            _delete_provider_ticker(provider, "BNC", company_id, security_id)
            if provider_non_target != _non_target_provider_fingerprint(
                provider, "BNC", company_id, security_id,
            ):
                raise RuntimeError("UNIVERSE_REMOVAL_NON_TARGET_PROVIDER_CHANGED")
            applied_at = utc_now()
            canonical_result = fresh_rebuild_canonical(
                provider, canonical, applied_at=applied_at, affected_company_ids=[company_id],
            )
            universe_result = _retire_from_active_universe(canonical, identity, applied_at=applied_at)
            if canonical_non_target != _non_target_canonical_state(canonical, company_id):
                raise RuntimeError("UNIVERSE_REMOVAL_NON_TARGET_CANONICAL_CONTROL_CHANGED")
            analysis_result = rebuild_v2_analysis(
                analysis,
                {"provider": provider, "canonical": canonical, "market": paths.market_db, "taxonomy": paths.taxonomy_db},
                as_of_date=as_of_date or date.today().isoformat(), output=writer.run_dir / "full_v2_rebuild",
            )
            after = {
                "provider": _provider_footprint(provider, "BNC", company_id, security_id),
                "canonical": _canonical_footprint(canonical, company_id, security_id),
                "analysis": _analysis_footprint(analysis, company_id, "BNC"),
            }
            if after["provider"]["observation_count"] or after["canonical"]["quarter_count"] or after["analysis"]["total_direct_rows"]:
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_CANDIDATE_INVALID")
            if after["canonical"]["active_universe_memberships"]:
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_BNC_REMAINS_ACTIVE")
            if any(_health(path)["quick_check"] != "ok" or _health(path)["foreign_key_errors"] for path in (provider, canonical, analysis)):
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_CANDIDATE_INTEGRITY_FAILED")
            analysis_effects = _analysis_effects(paths.analysis_db, analysis, company_id)
            if any(analysis_effects[label]["affected_company_count"] for label in ("score", "lifecycle", "valuation")):
                raise RuntimeError("UNIVERSE_REMOVAL_UNRELATED_ABSOLUTE_MODEL_CHANGED")
            if production_file_state(paths) != current_state:
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_CHANGED_DURING_CANDIDATE_BUILD")
            backups = _verified_backups(paths, backup_dir)
            roles = _candidate_manifest({"provider": provider, "canonical": canonical, "analysis": analysis}, backups)
            journal = prepare_journal(
                path=journal_path, operation_type=AdminOperationType.REMOVE_FUNDAMENTALS_TICKERS.value,
                run_id=run_id, preview_run_id=str(preview.get("run_id")), test_run_id=test_run_id,
                refresh_set_fingerprint=preview_fingerprint, old_source_watermark=None,
                new_source_watermark="UNCHANGED_BOOTSTRAP_BASELINE", source_schema_fingerprint="UNCHANGED",
                roles=roles,
            )
            for role in PUBLICATION_ROLES:
                write_boundary = True
                journal = _replace_role(role, journal, journal_path=journal_path)
            postflight = {
                "provider": _provider_footprint(paths.provider_db, "BNC", company_id, security_id),
                "canonical": _canonical_footprint(paths.canonical_db, company_id, security_id),
                "analysis": _analysis_footprint(paths.analysis_db, company_id, "BNC"),
                "health": {
                    role: _health(path)
                    for role, path in {
                        "provider": paths.provider_db,
                        "canonical": paths.canonical_db,
                        "analysis": paths.analysis_db,
                    }.items()
                },
            }
            if postflight["provider"]["observation_count"] or postflight["canonical"]["quarter_count"] or postflight["analysis"]["total_direct_rows"]:
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_POSTFLIGHT_FAILED")
            if postflight["canonical"]["active_universe_memberships"]:
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_POSTFLIGHT_ACTIVE_MEMBERSHIP")
            if any(
                item["quick_check"] != "ok" or item["foreign_key_errors"]
                for item in postflight["health"].values()
            ):
                raise RuntimeError("UNIVERSE_REMOVAL_PRODUCTION_POSTFLIGHT_INTEGRITY_FAILED")
            journal = update_journal(
                journal_path, journal, state="COMPLETED", current_publication_step="COMPLETED",
                postflight_state="PASSED", rollback_recovery_state="NOT_REQUIRED",
            )
            result.update(
                outcome="COMPLETED", canonical_rebuild=canonical_result,
                universe_removal=universe_result, analysis_rebuild=analysis_result,
                analysis_effects=analysis_effects, backups=backups, journal=journal,
                postflight=postflight,
            )
    except Exception:
        if journal is not None and write_boundary:
            recovered = restore_old_generation(journal, journal_path=journal_path)
            result["rollback"] = recovered
        raise
    finally:
        shutil.rmtree(lane.parent, ignore_errors=True)
        result["production_file_state_after"] = production_file_state(paths)
        writer.write_json("result.json", result)
        writer.write_manifest()
    return result
