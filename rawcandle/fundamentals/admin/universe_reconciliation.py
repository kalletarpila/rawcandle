"""Identity-only universe reconciliation through the native generation journal.

Financial statements and analysis are never rebuilt or approved here. Native
analysis/source validation must pass on OLD and the unchanged economic copy.
"""

from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
from zoneinfo import ZoneInfo

from . import financial_selection as selection
from . import refresh_update as core, refresh_production as native
from . import publication_journal as journal
from . import refresh_fundamentals as rules
from . import identity_resolution
from .artifacts import AdminRunWriter, stable_run_id
from .batch_add_tickers import BatchAddTickerPaths
from .contracts import AdminOperationType, fingerprint, utc_now
from .refresh_universe import InstalledUniverse
from .source_bundle import semantic_source_binding
from .snapshot_environment import SnapshotEnvironment
from rawcandle.fundamentals.generations import (
    active_manifest_path,
    prepare_generation_from_candidates,
    resolve_active_generation,
)

CONTRACT = "NATIVE_FINANCIAL_UNIVERSE_RECONCILIATION_V1"
CONFIRM = "CONFIRM_IDENTITY_ONLY_FINANCIAL_UNIVERSE_RECONCILIATION"
APPROVED_FIX7 = "edbde9bd7016eceac4b9a71dead231eb0b84670c66f31181f15291e708ce07d3"
UNIVERSE_TABLES = frozenset(
    {
        "fundamentals_operational_universe_version",
        "fundamentals_operational_universe_active_version",
        "fundamentals_operational_universe_member",
        "fundamentals_operational_universe_member_alias",
    }
)
QUALIFIED_FEATURES = (
    "identity_only",
    "native_activation",
    "native_postflight",
    "ordinary_rollback",
    "preparation_recovery",
    "activation_recovery",
    "stale_authority_rejection",
)


def code_binding():
    files = [
        Path(__file__),
        Path(journal.__file__),
        selection.ROOT / "rawcandle/fundamentals/generations.py",
    ]
    return {
        **selection.code_binding(),
        **{str(p.relative_to(selection.ROOT)): journal.sha256_file(p) for p in files},
    }


def approval_fingerprint(decisions, reference):
    return fingerprint(
        dict(
            reference=reference,
            decisions=sorted(decisions, key=lambda d: d["company_id"]),
        )
    )


def _qualification(env, run_id, expected_code, expected_approval):
    path = core._trusted(env.runs / run_id / "result.json", env.root)
    result = core._read(path)
    core._verify(result)
    if (
        result.get("contract") != CONTRACT
        or result.get("mode") != "DISPOSABLE_ACCEPTANCE"
        or result.get("outcome") != "PASSED"
        or result.get("code_binding") != expected_code
        or result.get("approval_fingerprint") != expected_approval
        or not all(
            result.get("features", {}).get(k) is True for k in QUALIFIED_FEATURES
        )
        or not result.get("tests_evidence")
    ):
        raise ValueError("UNIVERSE_RECONCILIATION_MATCHING_ACCEPTANCE_REQUIRED")
    if env.is_live:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=env.root, text=True
        ).strip()
        if result.get("source_commit") != head:
            raise ValueError("UNIVERSE_RECONCILIATION_TESTED_COMMIT_REQUIRED")
        if result.get("native_source_binding") != core._code_binding():
            raise ValueError("UNIVERSE_RECONCILIATION_NATIVE_CODE_DRIFT")
        for name, expected in expected_code.items():
            committed = subprocess.check_output(
                ["git", "show", head + ":" + name], cwd=env.root
            )
            if hashlib.sha256(committed).hexdigest() != expected:
                raise ValueError("UNIVERSE_RECONCILIATION_UNCOMMITTED_CODE")
    return dict(
        run_id=run_id,
        fingerprint=result["fingerprint"],
        source_commit=result.get("source_commit"),
    )


def _nightly_coordination(env, at):
    if not env.is_live:
        return dict(mode="DISPOSABLE")
    local = at.astimezone(ZoneInfo("Europe/Helsinki"))
    start = datetime.combine(local.date(), time(4, 45), tzinfo=local.tzinfo)
    if start < local:
        start += timedelta(days=1)
    remaining = (start - local).total_seconds()
    # A local, conservative coordination margin, never a scheduler alteration.
    if remaining <= 3600:
        raise RuntimeError("UNIVERSE_RECONCILIATION_NIGHTLY_WINDOW")
    return dict(
        next_nightly_start=start.isoformat(),
        seconds_remaining=remaining,
        scheduler_lease="NATIVE_NONBLOCKING_KERNEL_LOCK",
        fundamentals_hold=True,
    )


def _unchanged_config(env):
    if not env.is_live:
        return fingerprint(env.config())
    path = env.root / "scheduler_config.json"
    raw = json.loads(path.read_text())
    if (
        raw.get("fundamentals_refresh_preview_enabled") is not False
        or raw.get("fundamentals_refresh_route") != "SNAPSHOT_V1"
    ):
        raise ValueError("UNIVERSE_RECONCILIATION_FUNDAMENTALS_HOLD_REQUIRED")
    return journal.sha256_file(path)


def _analysis_parameters(path):
    with closing(core.carry.readonly(path)) as db:
        # Rebinding older explicit universe dependencies would need a different
        # qualified contract. Do not silently relabel existing accepted results.
        for table in (
            "fundamentals_result_dependency",
            "relative_valuation_snapshot_dependency",
        ):
            if db.execute(
                "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)
            ).fetchone():
                if db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    raise ValueError(
                        "UNIVERSE_RECONCILIATION_ANALYSIS_UNIVERSE_DEPENDENCY"
                    )
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT d.* FROM relative_position_active_snapshot a "
                "JOIN relative_position_v2_taxonomy_dependency d USING(snapshot_id)"
            )
        ]
        if len(rows) != 1:
            raise ValueError("UNIVERSE_RECONCILIATION_NATIVE_ANALYSIS_REQUIRED")
        row = rows[0]
    return dict(
        as_of_date=row["calculation_as_of_date"],
        active_taxonomy=dict(
            domain=row["taxonomy_domain"],
            version=row["taxonomy_version"],
            semantic_fingerprint=row["taxonomy_semantic_fingerprint"],
        ),
    )


def _economic_tables(path):
    """Stream exact accepted canonical contents outside the four universe tables."""
    result = {}
    with closing(core.carry.readonly(path)) as db:
        schema = [
            tuple(r)
            for r in db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
            )
        ]
        for row in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        ):
            table = row[0]
            if table in UNIVERSE_TABLES:
                continue
            h, count = hashlib.sha256(), 0
            # The candidate is a byte copy and only the version tables mutate;
            # native row IDs/order of every protected table are preserved too.
            for record in db.execute(
                'SELECT * FROM "' + table.replace('"', '""') + '"'
            ):
                h.update(
                    json.dumps(tuple(record), sort_keys=True, default=str).encode()
                )
                h.update(b"\n")
                count += 1
            result[table] = dict(rows=count, sha256=h.hexdigest())
    return dict(
        schema=fingerprint(schema), tables=result, fingerprint=fingerprint(result)
    )


def _authority(env, paths):
    return dict(
        old=core.carry.verified_generation(paths),
        universe=fingerprint(selection.read_state(paths.canonical_db)),
        configuration=_unchanged_config(env),
        queue=core._queue_binding(env),
        identity_review_registry=journal.sha256_file(
            identity_resolution.DEFAULT_REGISTRY_PATH
        ),
        code=code_binding(),
    )


def _check_selections(paths, decisions):
    universe = InstalledUniverse(paths)
    for choice in decisions:
        resolved = universe.resolve(choice["ticker"])
        if resolved["status"] != "ELIGIBLE" or any(
            resolved["identity"].get(k) != choice[k]
            for k in ("company_id", "security_id", "provider_security_id")
        ):
            raise ValueError("UNIVERSE_RECONCILIATION_REPRESENTATIVE_MISMATCH")
        for sid in choice["companion_security_ids"]:
            ticker = universe.securities[sid]["current_ticker"]
            if (
                universe.resolve(ticker).get("reason")
                != "FINANCIAL_COMPANION_RETENTION_ONLY"
            ):
                raise ValueError("UNIVERSE_RECONCILIATION_COMPANION_INCOMING")
    return universe.binding


def run_reconciliation(
    env,
    decisions,
    *,
    approval_reference,
    expected_approval,
    expected_code,
    expected_old,
    expected_universe,
    qualification_run_id,
    confirmation,
    production_intent=False,
    stop_after="candidate",
    now=None,
    inject_failure=None,
    inject_crash=None,
):
    """Qualify/conditionally install one exact identity-only native generation.

    Existing COPY Test evidence and explicit production intent are both required.
    It never creates a live UPDATE, fetches evidence or publishes financial changes.
    """
    if type(env) is not SnapshotEnvironment or env.is_live != (env.copy_owner is None):
        raise PermissionError("UNIVERSE_RECONCILIATION_NATIVE_ENVIRONMENT_REQUIRED")
    if env.copy_owner is not None and (
        type(env.copy_owner) is not core.DisposableEnvironment
        or env.root != env.copy_owner.root
        or env.project != env.copy_owner.project
        or env.runs != env.copy_owner.runs
        or env.queue != env.copy_owner.queue
    ):
        raise PermissionError("UNIVERSE_RECONCILIATION_COPY_OWNER_SCOPE")
    env.check()
    if confirmation != CONFIRM or stop_after not in {"candidate", "publish"}:
        raise PermissionError("UNIVERSE_RECONCILIATION_CONFIRMATION_REQUIRED")
    if env.is_live != production_intent:
        raise PermissionError("UNIVERSE_RECONCILIATION_EXPLICIT_PRODUCTION_INTENT")
    if approval_fingerprint(decisions, approval_reference) != expected_approval or (
        env.is_live and expected_approval != APPROVED_FIX7
    ):
        raise ValueError("UNIVERSE_RECONCILIATION_UNAPPROVED_SELECTIONS")
    if expected_code != code_binding():
        raise ValueError("UNIVERSE_RECONCILIATION_TESTED_CODE_DRIFT")
    qualification = _qualification(
        env, qualification_run_id, expected_code, expected_approval
    )
    clock = now or (lambda: datetime.now(timezone.utc))
    run_id = (
        stable_run_id(
            AdminOperationType.REFRESH_FUNDAMENTALS,
            expected_approval,
            suffix="universe_reconciliation",
        )
        + "_"
        + secrets.token_hex(4)
    )
    writer = AdminRunWriter(
        run_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=env.runs
    )
    lane = core._trusted(
        env.root / "temp/fundamentals_universe_reconciliation" / run_id / "candidates",
        env.root,
    )
    backups_dir = core._trusted(
        env.root / "backups/fundamentals_admin_production" / run_id, env.root
    )
    result = dict(
        contract=CONTRACT,
        operation_type="FINANCIAL_UNIVERSE_RECONCILIATION",
        mode="PRODUCTION_IDENTITY_ONLY" if env.is_live else "DISPOSABLE_IDENTITY_ONLY",
        run_id=run_id,
        outcome="BLOCKED",
        started_at_utc=utc_now(),
        qualification=qualification,
        approval_fingerprint=expected_approval,
        financial_update_publication=False,
        financial_watermark_advanced=False,
    )
    env.operation_id = run_id
    intent, committed = None, False
    stage = "NATIVE_PREFLIGHT"

    def boundary(name):
        if inject_crash == name:
            raise native.SimulatedPublicationCrash(name)
        if inject_failure == name:
            raise RuntimeError("UNIVERSE_RECONCILIATION_INJECTED:" + name)

    try:
        with env.writer_lock():
            try:
                journal.guard_production_writes(env.journal)
                result["coordination"] = _nightly_coordination(env, clock())
                paths = env.paths()
                current = resolve_active_generation(
                    env.project, require_generation=True
                )
                result["old_generation"] = current.evidence()
                authority = _authority(env, paths)
                result["starting_authority"] = authority
                result["financial_watermark"] = rules.resolve_refresh_state(
                    paths.provider_db
                ).published_watermark
                if (
                    authority["old"] != expected_old
                    or authority["universe"] != expected_universe
                ):
                    raise ValueError("UNIVERSE_RECONCILIATION_STALE_STARTING_AUTHORITY")
                result["storage"] = native._storage_preflight(
                    paths, temp_root=env.root / "temp", backup_root=backups_dir.parent
                )
                fs = shutil.disk_usage(env.root)
                inodes = os.statvfs(env.root)
                if inodes.f_favail < 32:
                    raise RuntimeError("UNIVERSE_RECONCILIATION_INSUFFICIENT_INODES")
                result["resource_preflight"] = dict(
                    free_bytes=fs.free, free_inodes=inodes.f_favail
                )
                plan = selection.prepare_reconciliation(
                    paths,
                    decisions,
                    expected_start=authority["universe"],
                    expected_old=authority["old"],
                    approval_reference=approval_reference,
                    applied_at=utc_now(),
                )
                result["old_universe"] = plan["starting_universe"]
                result["candidate_universe"] = plan["identity"]
                writer.write_json("selection_plan.json", plan)
                parameters = _analysis_parameters(paths.analysis_db)
                lane.mkdir(parents=True, exist_ok=False)
                stage = "BASELINE_ANALYSIS_NATIVE_VALIDATION"
                sources, evidence = env.prepare_sources(
                    paths, lane, paths.canonical_db, parameters["as_of_date"]
                )
                result["source_dependencies"] = semantic_source_binding(evidence)
                writer.write_json("source_dependencies.json", evidence)
                validation_sources = {**paths.as_dict(), **sources}
                result["baseline_analysis"] = native._validate_analysis_generation(
                    paths.analysis_db,
                    analysis_result=parameters,
                    as_of_date=parameters["as_of_date"],
                    sources=validation_sources,
                )
                stage = "IDENTITY_ONLY_CANDIDATE"
                protected = _economic_tables(paths.canonical_db)
                candidate_roles = {}
                for role in journal.PUBLICATION_ROLES:
                    destination = lane / (role + ".db")
                    shutil.copyfile(paths.as_dict()[role], destination)
                    journal.fsync_file(destination)
                    if (
                        journal.sha256_file(destination)
                        != current.manifest["role_verification"][role]["sha256"]
                    ):
                        raise RuntimeError(
                            "UNIVERSE_RECONCILIATION_COPY_CHANGED:" + role
                        )
                    candidate_roles[role] = destination
                candidate = BatchAddTickerPaths(
                    candidate_roles["provider"],
                    candidate_roles["canonical"],
                    candidate_roles["analysis"],
                    paths.market_db,
                    paths.taxonomy_db,
                )
                installed = selection.install_disposable_candidate(candidate, plan)
                if _economic_tables(candidate.canonical_db) != protected:
                    raise RuntimeError("UNIVERSE_RECONCILIATION_ECONOMIC_MUTATION")
                old_state, new_state = selection.read_state(
                    paths.canonical_db
                ), selection.read_state(candidate.canonical_db)
                for key in ("securities", "physical_aliases", "mappings"):
                    if old_state[key] != new_state[key]:
                        raise RuntimeError("UNIVERSE_RECONCILIATION_IDENTITY_MUTATION")
                targets = {d["company_id"] for d in decisions}
                for old, new in zip(old_state["members"], new_state["members"]):
                    if old["company_id"] not in targets and {
                        k: v for k, v in old.items() if k != "universe_version_id"
                    } != {k: v for k, v in new.items() if k != "universe_version_id"}:
                        raise RuntimeError(
                            "UNIVERSE_RECONCILIATION_UNRELATED_MEMBER_MUTATION"
                        )
                result["selected_universe"] = _check_selections(candidate, decisions)
                result["companion_preservation"] = selection.verify_companion_retention(
                    candidate, candidate.provider_db, candidate.canonical_db
                )
                result["candidate_analysis"] = native._validate_analysis_generation(
                    candidate.analysis_db,
                    analysis_result=parameters,
                    as_of_date=parameters["as_of_date"],
                    sources={**candidate.as_dict(), **sources},
                )
                for role in ("provider", "analysis"):
                    if (
                        journal.sha256_file(candidate.as_dict()[role])
                        != current.manifest["role_verification"][role]["sha256"]
                    ):
                        raise RuntimeError(
                            "UNIVERSE_RECONCILIATION_FINANCIAL_ROLE_MUTATED"
                        )
                result.update(
                    outcome="CANDIDATE_READY",
                    plan_fingerprint=plan["fingerprint"],
                    candidate_roles={r: str(p) for r, p in candidate_roles.items()},
                    protected_canonical=protected,
                    installed=installed,
                )
                boundary("AFTER_CANDIDATE")
                if stop_after == "publish":
                    stage = "FINAL_AUTHORITY_RECHECK"
                    if _authority(env, paths) != authority:
                        raise RuntimeError("UNIVERSE_RECONCILIATION_STALE_AUTHORITY")
                    result["coordination"] = _nightly_coordination(env, clock())
                    backups = native._verified_backups(
                        paths, backups_dir, immutable_generation=True
                    )
                    native._validate_generation_backup_binding(current, backups)
                    roles = native._candidate_manifest(candidate_roles, backups)
                    stage = "NATIVE_GENERATION_PREPARATION"
                    prepared = prepare_generation_from_candidates(
                        candidate_roles,
                        generation_id=run_id,
                        project_root=env.project,
                        source=CONTRACT,
                    )
                    intent = journal.prepare_journal(
                        path=env.journal,
                        operation_type=CONTRACT,
                        run_id=run_id,
                        preview_run_id=None,
                        test_run_id=qualification_run_id,
                        refresh_set_fingerprint=plan["fingerprint"],
                        old_source_watermark=rules.resolve_refresh_state(
                            paths.provider_db
                        ).published_watermark,
                        new_source_watermark=rules.resolve_refresh_state(
                            paths.provider_db
                        ).published_watermark
                        or "",
                        source_schema_fingerprint=CONTRACT,
                        roles=roles,
                        publication_mode="GENERATION_POINTER",
                        old_generation=current.evidence()
                        | {"manifest": dict(current.manifest)},
                        new_generation_id=run_id,
                        active_generation_manifest_path=active_manifest_path(
                            env.project
                        ),
                        scope_evidence=dict(
                            contract=CONTRACT,
                            approval_fingerprint=expected_approval,
                            economic_change=False,
                            qualification=qualification,
                        ),
                    )
                    intent = journal.update_journal(
                        env.journal,
                        intent,
                        new_generation_manifest=prepared["manifest"],
                        new_generation_dir=prepared["generation_dir"],
                        generation_activation_state="READY",
                    )
                    boundary("AFTER_PREPARE")
                    stage = "NATIVE_ACTIVATION"
                    intent = journal.activate_prepared_generation(
                        intent,
                        new_manifest=prepared["manifest"],
                        journal_path=env.journal,
                    )
                    boundary("AFTER_ACTIVATION")
                    stage = "NATIVE_POSTFLIGHT"
                    active = env.paths()
                    if (
                        _check_selections(active, decisions)
                        != result["selected_universe"]
                    ):
                        raise RuntimeError(
                            "UNIVERSE_RECONCILIATION_POSTFLIGHT_UNIVERSE"
                        )
                    for role in journal.PUBLICATION_ROLES:
                        if (
                            journal.sqlite_verification(active.as_dict()[role])[
                                "sha256"
                            ]
                            != roles[role]["candidate_fingerprint"]
                        ):
                            raise RuntimeError(
                                "UNIVERSE_RECONCILIATION_POSTFLIGHT_ROLE:" + role
                            )
                    native._validate_analysis_generation(
                        active.analysis_db,
                        analysis_result=parameters,
                        as_of_date=parameters["as_of_date"],
                        sources={**active.as_dict(), **sources},
                    )
                    if (
                        _unchanged_config(env) != authority["configuration"]
                        or core._queue_binding(env) != authority["queue"]
                    ):
                        raise RuntimeError(
                            "UNIVERSE_RECONCILIATION_POSTFLIGHT_POLICY_DRIFT"
                        )
                    boundary("AFTER_POSTFLIGHT")
                    intent = journal.update_journal(
                        env.journal,
                        intent,
                        state="COMPLETED",
                        postflight_state="PASSED",
                    )
                    committed = True
                    result.update(
                        outcome="COMPLETED",
                        postflight="PASSED",
                        new_generation=resolve_active_generation(
                            env.project
                        ).evidence(),
                        identity_generation_activated=True,
                        recovery="NOT_REQUIRED",
                    )
            except Exception as exc:
                result.update(
                    outcome="BLOCKED" if intent is None else "FAILED",
                    error=str(exc),
                    failed_stage=stage,
                )
                if intent is not None and not committed:
                    result["recovery"] = journal.restore_old_generation(
                        intent, journal_path=env.journal
                    )
                    result["outcome"] = "ROLLED_BACK"
            except native.SimulatedPublicationCrash as exc:
                result.update(outcome="INTERRUPTED", error=str(exc), failed_stage=stage)
                raise
    except Exception as exc:
        result.update(outcome="BLOCKED", error=str(exc), failed_stage=stage)
    finally:
        result["finished_at_utc"] = utc_now()
        writer.write_json("result.json", result)
        writer.write_text(
            "UNIVERSE_RECONCILIATION_REPORT.md",
            "# Native universe reconciliation\n\n"
            + "\n".join(
                f"- {key}: `{result.get(key)}`"
                for key in (
                    "run_id",
                    "outcome",
                    "failed_stage",
                    "error",
                    "postflight",
                    "financial_update_publication",
                    "financial_watermark_advanced",
                )
            )
            + "\n",
        )
    return result
