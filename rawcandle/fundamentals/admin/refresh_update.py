"""Snapshot-only Phase 2, deliberately restricted to owned disposable projects.

No scheduler/UI production entry imports this module. Review approval, source
validity and successful builds never grant publication permission. Native model,
generation, journal and recovery kernels remain the transaction authorities.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from rawcandle.io_atomic import write_text_atomic
from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.generations import (
    _validate_generation_id,
    active_manifest_path,
    prepare_generation_from_candidates,
    resolve_active_generation,
    resolved_production_paths,
)
from rawcandle.fundamentals.phase13b_foundation import online_backup
from . import acquisition_snapshot as acquisition
from . import baseline_carry_forward as carry
from . import refresh_universe
from . import review_locality as locality
from . import refresh_fundamentals as rules
from . import refresh_review_queue as reviews
from . import refresh_copy_runtime as builders
from . import refresh_production as native
from . import publication_journal as journals
from .artifacts import ROOT, AdminRunWriter, sha256_file
from .batch_add_tickers import BatchAddTickerPaths
from .contracts import AdminOperationType, fingerprint
from .production_transaction import production_lock

CONTRACT = "FUNDAMENTALS_SIMPLIFICATION_V1"
DISPOSABLE = "FUNDAMENTALS_PHASE2_DISPOSABLE_V1"
CONFIRM = "PUBLISH_DISPOSABLE_FUNDAMENTALS_ONLY"


class Phase2Error(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, default=str)


def _write(path, value):
    write_text_atomic(path, _json(value) + "\n")
    journals.fsync_directory(path.parent)


def _read(path):
    return json.loads(path.read_text())


def _seal(value):
    return {**value, "fingerprint": fingerprint(value)}


def _verify(value, expected=None):
    if value.get("fingerprint") != fingerprint(
        {k: v for k, v in value.items() if k != "fingerprint"}
    ):
        raise Phase2Error("PHASE2_RECEIPT_TAMPERED")
    if expected is not None and value["fingerprint"] != expected:
        raise Phase2Error("PHASE2_RECEIPT_IDENTITY_MISMATCH")


def _trusted(path, root):
    path = Path(path).absolute()
    if ".." in path.parts or not path.is_relative_to(root):
        raise Phase2Error("PHASE2_PATH_OUTSIDE_DISPOSABLE")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise Phase2Error("PHASE2_SYMLINK_FORBIDDEN")
    if path.is_file() and path.stat().st_nlink != 1:
        raise Phase2Error("PHASE2_HARDLINK_FORBIDDEN")
    return path


@dataclass(frozen=True)
class DisposableEnvironment:
    root: Path
    identity: str

    @property
    def project(self):
        return self.root / "generation-project"

    @property
    def runs(self):
        return self.root / "admin_runs"

    @property
    def queue(self):
        return self.root / "fundamentals_refresh_review_queue.db"

    @property
    def journal(self):
        return self.root / "publication-journal.json"

    def check(self):
        root = self.root.absolute()
        if root == ROOT.resolve() or not (
            root.is_relative_to(Path("/tmp")) or root.is_relative_to(ROOT / "temp")
        ):
            raise Phase2Error("PHASE2_DISPOSABLE_ROOT_REQUIRED")
        _trusted(root, root)
        marker = _read(_trusted(root / "phase2_disposable.json", root))
        if marker != {
            "format": DISPOSABLE,
            "root": str(root),
            "identity": self.identity,
        }:
            raise Phase2Error("PHASE2_OWNER_MISMATCH")
        for path in (
            self.project,
            self.runs,
            self.queue,
            self.journal,
            root / "publication.lock",
            root / "logs",
            root / "logs/stock_update_scheduler.lock",
        ):
            _trusted(path, root)
        # Native recovery follows journal paths. Check its complete write/delete
        # scope BEFORE allowing the native guard to run in this environment.
        if self.journal.exists():
            journal = journals.load_journal(self.journal)
            if (
                journal.get("publication_mode") != "GENERATION_POINTER"
                or Path(journal.get("active_generation_manifest_path", ""))
                != active_manifest_path(self.project)
                or set(journal.get("roles", {})) != set(journals.PUBLICATION_ROLES)
            ):
                raise Phase2Error("PHASE2_JOURNAL_SCOPE_INVALID")
            for value in (
                journal.get("new_generation_id"),
                (journal.get("old_generation") or {}).get("generation_id"),
            ):
                _validate_generation_id(str(value or ""))
            for record in journal["roles"].values():
                for key in ("production_path", "backup_path", "candidate_path"):
                    _trusted(Path(record[key]), root)
            for key in ("new_generation_dir",):
                if journal.get(key):
                    _trusted(Path(journal[key]), root)
        if self.project.exists():
            binding = resolve_active_generation(self.project, require_generation=True)
            for path in (
                *binding.role_paths().values(),
                binding.manifest_path,
                self.project / "data/osakedata.db",
                self.project / "data/analysis.db",
            ):
                _trusted(path, root)
        return self

    def paths(self):
        self.check()
        paths = resolved_production_paths(self.project)
        return BatchAddTickerPaths(
            *(
                paths[r]
                for r in ("provider", "canonical", "analysis", "market", "taxonomy")
            )
        )

    @contextmanager
    def writer_lock(self):
        self.check()
        with production_lock(
            lock_path=self.root / "publication.lock",
            scheduler_log_dir=str(self.root / "logs"),
        ):
            yield


def create_disposable_environment(root):
    root = Path(root).absolute()
    if root == ROOT.resolve() or not (
        root.is_relative_to(Path("/tmp")) or root.is_relative_to(ROOT / "temp")
    ):
        raise Phase2Error("PHASE2_DISPOSABLE_ROOT_REQUIRED")
    _trusted(root, root)
    root.mkdir(parents=True, exist_ok=False)
    identity = uuid4().hex
    _write(
        root / "phase2_disposable.json",
        {"format": DISPOSABLE, "root": str(root), "identity": identity},
    )
    return DisposableEnvironment(root, identity).check()


def _code_binding():
    # HEAD + relevant tracked changes catch model/validator edits without a new
    # registry/framework. Hash new entry kernels too before they are committed.
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
    diff = subprocess.check_output(
        ["git", "diff", "HEAD", "--", "rawcandle/fundamentals"], cwd=ROOT
    )
    names = (
        "refresh_update.py",
        "review_locality.py",
        "baseline_carry_forward.py",
        "snapshot_environment.py",
        "snapshot_workflow.py",
        "acquisition_quarantine.py",
        "sec_snapshot.py",
        "refresh_universe.py",
        "financial_selection.py",
    )
    return fingerprint(
        {
            "head": head.decode().strip(),
            "diff": hashlib.sha256(diff).hexdigest(),
            "entry": {n: sha256_file(Path(__file__).parent / n) for n in names},
        }
    )


def _queue_binding(env):
    if not env.queue.exists():
        return None
    # Native read-only decoder validates old and current evidence. Include all
    # financial review rows; unrelated ownership tables are not authorization.
    with carry.readonly(env.queue) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='refresh_review_queue'"
        ).fetchone():
            return None
        rows = [
            dict(r)
            for r in db.execute("SELECT * FROM refresh_review_queue ORDER BY ticker")
        ]
    for row in rows:
        reviews._decode_row(row)
    return fingerprint(rows) if rows else None


def _inputs(env, paths):
    value = {
        "old": acquisition.pin_old_authority(env.project),
        "queue": _queue_binding(env),
        "dependencies": (
            env.dependency_binding(paths)
            if hasattr(env, "dependency_binding")
            else {r: sha256_file(paths.as_dict()[r]) for r in ("market", "taxonomy")}
        ),
        "code": _code_binding(),
    }
    if hasattr(env, "update_inputs"):
        value["update"] = env.update_inputs()
    return value


def _operation(env, validation_id):
    if (
        not isinstance(validation_id, str)
        or not validation_id.startswith("local_")
        or len(validation_id) != 38
    ):
        raise Phase2Error("PHASE2_VALIDATION_ID_INVALID")
    try:
        int(validation_id[6:], 16)
    except ValueError as error:
        raise Phase2Error("PHASE2_VALIDATION_ID_INVALID") from error
    return _trusted(env.runs / validation_id, env.root)


def _load(env, validation_id, expected=None):
    env.check()
    if not isinstance(expected, str) or len(expected) != 64:
        raise Phase2Error("PHASE2_EXACT_RECEIPT_CONFIRMATION_REQUIRED")
    directory = _operation(env, validation_id)
    receipt = _read(_trusted(directory / "validation_receipt.json", env.root))
    _verify(receipt, expected)
    if (
        receipt["environment_identity"] != env.identity
        or receipt["validation_id"] != validation_id
    ):
        raise Phase2Error("PHASE2_VALIDATION_OWNER_MISMATCH")
    child = _trusted(directory / "decisions.json", env.root)
    if sha256_file(child) != receipt["decisions_sha256"]:
        raise Phase2Error("PHASE2_DECISIONS_TAMPERED")
    return directory, receipt, _read(child)


def _assert_inputs(env, receipt, paths, now):
    if _inputs(env, paths) != receipt["inputs"]:
        raise Phase2Error("PHASE2_LOCAL_AUTHORITY_DRIFT")
    snapshot = acquisition.open_snapshot(
        receipt["snapshot_operation_id"],
        root=env.runs,
        expected_reference=receipt["snapshot_reference"],
    )
    snapshot.validate_preflight(
        old_authority=receipt["inputs"]["old"],
        now=now,
        expected_reference=receipt["snapshot_reference"],
    )
    if hasattr(env, "require_update_snapshot"):
        env.require_update_snapshot(snapshot)
    return snapshot


def _report(directory, receipt, decisions, *, build=None, publication=None):
    snapshot = receipt["snapshot_reference"]
    lines = [
        "# Fundamentals Phase 2 — disposable local workflow",
        "",
        f"Validation: `{receipt['validation_id']}`; status: **{(publication or {}).get('status', receipt['status'])}**.",
        f"Snapshot: `{receipt['snapshot_operation_id']}`; root SHA: `{snapshot['sha256']}`.",
        f"Age at validation: {receipt['snapshot_source_age_seconds'] / 3600:.6f} hours; maximum 168 hours, original timestamps.",
        f"OLD generation: `{receipt['inputs']['old']['generation_id']}`; OLD watermark: `{receipt['old_refresh_state']['published_watermark']}`.",
        f"Production mutation: **{bool((publication or {}).get('production_mutation', False))}**. Publication requires separate explicit confirmation.",
        "",
        f"Safe/local-held/global: {receipt['counts']['safe']}/{receipt['counts']['local_holds']}/{receipt['counts']['global']}.",
        "Queue rows are evidence; this table reflects actual validated dispositions.",
        f"Acquisition quarantines: {receipt['counts'].get('acquisition_quarantines',0)}; "
        "whole-ticker OLD retained, incoming excluded, no financial approval or queue resolution granted.",
        "",
        "| Ticker | Disposition | Native reason/classification |",
        "| --- | --- | --- |",
    ]
    for disposition, items in (
        ("SAFE", decisions["safe"]),
        ("LOCAL_HOLD", decisions["held"]),
        ("GLOBAL_BLOCKER", decisions["global"]),
    ):
        for item in items:
            change = item.get("change", item)
            lines.append(
                f"| {item['ticker']} | {disposition} | {change.get('review_reason') or change['classification']} |"
            )
            source_hold = change.get("acquisition_quarantine")
            if source_hold:
                lines.append(f"Source quarantine `{item['ticker']}`: reasons `{source_hold['reasons']}`; "
                    f"affected slots `{source_hold['affected_slots']}`; immutable receipts `{source_hold['receipts']}`; "
                    "both incoming dimensions excluded; OLD preserved; no deletion/approval authority.")
    lines += [
        "",
        "OLD rolling/source-history events and exact native approval bindings remain in hash-bound `decisions.json`.",
        "Missing source keys never grant automatic deletion. Held OLD provider/canonical authority must match before and after publication.",
        "Local holds remain outstanding review; no approval is manufactured.",
    ]
    if build:
        impact = build["canonical_result"]["impact"]
        lines += [
            "",
            f"Candidate generation: `{receipt.get('candidate_generation_id',build['prepared']['manifest']['generation_id'])}`.",
            f"Native canonical impact: {impact['added_quarters']} added, {impact['changed_quarters']} changed, {impact['removed_quarters']} removed quarters.",
            f"Full V2/RP/RV invocation counts: `{_json(build['analysis_result']['invocation_counts'])}`.",
            f"Native publication-date enrichment: {build['publication_dates']['status']}; retry scope/cap unchanged; missing SEC inputs stay unresolved.",
            f"Held OLD authority verified unchanged: {build['held_preservation']['unchanged']}.",
            "Candidate/build metadata and source-dependency copies are bound in `build.json`.",
        ]
    if publication:
        lines += [
            "",
            f"Publication outcome: **{publication['status']}**; journal: `{publication.get('journal_state','see native journal')}`.",
            f"Postflight present: {bool(publication.get('postflight'))}; error: {publication.get('error','none')}.",
            "Recovery and terminal OLD verification use the native journal, independently of source availability.",
        ]
    _write(
        directory / "summary.json",
        {
            "validation_id": receipt["validation_id"],
            "status": (publication or {}).get("status", receipt["status"]),
            "counts": receipt["counts"],
            "snapshot_reference": snapshot,
            "candidate_generation_id": receipt.get("candidate_generation_id"),
            "production_mutation": bool(
                (publication or {}).get("production_mutation", False)
            ),
            "details": "operation_report.md",
        },
    )
    write_text_atomic(directory / "operation_report.md", "\n".join(lines) + "\n")


def _scope(change):
    scope = reviews.classify_review_scope(change)
    if change.get("quarantine_failure"):
        scope["scope"] = reviews.GLOBAL_BLOCKING_REVIEW
    elif locality.valid_proof(change):
        scope.update(
            scope=reviews.TICKER_LOCAL_REVIEW,
            quarantine_locality=change["quarantine_locality"],
        )
        if change.get("baseline_integrity_hold"):
            scope.update(
                review_type=carry.HOLD,
                baseline_integrity_hold=change["baseline_integrity_hold"],
            )
    return scope


def _compare(
    paths, ticker, current, histories, identity, queue_item, as_of, queue_path
):
    policy = {
        "as_of_date": date.fromisoformat(as_of),
        "historical_source_window_review_years": 0,
    }
    item = rules.compare_ticker_histories(ticker, current, histories, **policy)
    item["identity"] = identity
    item = locality.apply_to_comparison(
        item,
        canonical_db=paths.canonical_db,
        provider_db=paths.provider_db,
        current=current,
        histories=histories,
        policy_args=policy,
    )
    approved = {}
    if item["classification"] == "REVIEW_REQUIRED":
        state = rules.resolve_refresh_state(paths.provider_db)
        for name, matcher in (
            ("retained_history_approval", reviews.match_retained_history_approval),
            ("fiscal_revision_approval", reviews.match_fiscal_revision_approval),
            ("true_removal_approval", reviews.match_true_removal_approval),
        ):
            matched = matcher(
                queue_item,
                reviews.classify_review_scope(item),
                published_binding=state.successful_run_id,
            )
            if matched.get("applied"):
                approved[name] = matched
    if approved:
        item = rules.compare_ticker_histories(
            ticker, current, histories, **approved, **policy
        )
        item["identity"] = identity
        item = locality.apply_to_comparison(
            item,
            canonical_db=paths.canonical_db,
            provider_db=paths.provider_db,
            current=current,
            histories=histories,
            policy_args=policy,
        )
    # Existing WFRD/accounting-boundary authority is evaluated locally, unchanged.
    from . import accounting_boundary_review as boundary

    application = boundary.evaluate_for_refresh(
        paths.provider_db, paths.canonical_db, histories, identity, queue_path
    )
    if (
        application.get("applied")
        or application.get("stale")
        or application.get("pending")
    ):
        item = boundary.comparison(ticker, current, histories, application, **policy)
        item["identity"] = identity
        item = locality.apply_to_comparison(
            item,
            canonical_db=paths.canonical_db,
            provider_db=paths.provider_db,
            current=current,
            histories=histories,
            policy_args=policy,
        )
    plan = rules.build_source_history_merge(
        ticker,
        current,
        histories,
        retained_history_approval=approved.get("retained_history_approval"),
        **policy,
    )
    return item, plan


def _compact_plan(plan):
    result = {k: v for k, v in plan.items() if k != "dimensions"}
    result["dimensions"] = {}
    for d, detail in plan["dimensions"].items():
        result["dimensions"][d] = {
            k: v for k, v in detail.items() if k != "merged_rows"
        }
        result["dimensions"][d]["row_references"] = [
            {
                "key": list(rules.source_key(row)),
                "retained": row.get("_history_retention_status")
                == rules.RETAINED_OUTSIDE_SOURCE_WINDOW,
                **(
                    {
                        k: row[k]
                        for k in (
                            "_history_retention_status",
                            "_history_retention_evidence",
                        )
                        if k in row
                    }
                ),
            }
            for row in detail["merged_rows"]
        ]
    return result


def _hydrate_plan(plan, current, source):
    result = {k: v for k, v in plan.items() if k != "dimensions"}
    result["dimensions"] = {}
    for d, detail in plan["dimensions"].items():
        old = {rules.source_key(r): r for r in current[d]["rows"]}
        new = {rules.source_key(r): r for r in source[d].rows}
        rows = []
        for ref in detail["row_references"]:
            row = dict((old if ref["retained"] else new)[tuple(ref["key"])])
            row.update({k: v for k, v in ref.items() if k.startswith("_")})
            rows.append(row)
        result["dimensions"][d] = {
            k: v for k, v in detail.items() if k != "row_references"
        } | {"merged_rows": tuple(rows)}
    return result


def validate_snapshot(env, snapshot_operation_id, *, as_of_date, now=_now):
    env.check()
    with env.writer_lock():
        # Recovery requires its own explicit entry; validation never recovers an
        # incomplete publication or silently consumes an old authorization.
        safety = journals.safety_status(env.journal)
        if safety.get("production_writes_blocked"):
            raise Phase2Error("PHASE2_RECOVERY_REQUIRED")
        paths = env.paths()
        universe = None
        if hasattr(env, 'request'):
            universe = refresh_universe.require_binding(paths, env.request())
        if hasattr(env, "validate_baseline"):
            env.validate_baseline(paths)
        snapshot = acquisition.open_snapshot(snapshot_operation_id, root=env.runs)
        snapshot.validate_preflight(
            old_authority=acquisition.pin_old_authority(env.project), now=now()
        )
        if hasattr(env, "require_update_snapshot"):
            env.require_update_snapshot(snapshot)
        date.fromisoformat(as_of_date)
        validation_id = "local_" + uuid4().hex
        writer = AdminRunWriter(
            validation_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=env.runs
        )
        queue = reviews.RefreshReviewQueue(env.queue)
        slots = {}
        for slot in snapshot.iter_slots():
            slots.setdefault(slot["ticker"], {})[slot["dimension"]] = slot
        acquisition_quarantines = snapshot.quarantines()
        # Full OLD domain protection, including missing provenance without an
        # existing dangling-reference row and names absent from FETCH/queue.
        degraded = set(carry.degraded_tickers(paths))
        retained_old, admitted_ambiguities = universe.old_retention() if universe else ([], [])
        if universe:
            degraded = {t for t in degraded if universe.resolve(t)['status'] != 'EXCLUDED'}
        global_baseline = []
        with carry.readonly(paths.canonical_db) as db:
            if db.execute(
                "SELECT 1 FROM v4_quarter q LEFT JOIN security s USING(company_id) WHERE s.security_id IS NULL LIMIT 1"
            ).fetchone():
                raise Phase2Error("PHASE2_BASELINE_IDENTITY_UNISOLATABLE")
            domain = [
                r[0]
                for r in db.execute(
                    "SELECT DISTINCT s.current_ticker FROM security s JOIN v4_quarter q USING(company_id) ORDER BY 1"
                )
            ]
        for ticker in domain:
            if universe and universe.resolve(ticker)['status'] == 'EXCLUDED':
                continue  # Retention is separate from incoming review/admission.
            identity = rules.resolve_identity(paths, ticker)
            if identity["status"] != "KNOWN" or ticker in admitted_ambiguities:
                global_baseline.append(ticker)
                continue
            try:
                locality.authority(
                    paths.provider_db,
                    paths.canonical_db,
                    ticker,
                    identity,
                    validate=True,
                )
            except ValueError:
                degraded.add(ticker)
        changes = []
        plans = {}
        max_updated = []
        for ticker in sorted(set(slots) | degraded | set(global_baseline)):
            identity = rules.resolve_identity(paths, ticker)
            if identity["status"] != "KNOWN" or ticker in global_baseline:
                changes.append(
                    {
                        "ticker": ticker,
                        "classification": "REVIEW_REQUIRED",
                        "review_reason": "WHOLE_TICKER_IDENTITY_UNPROVEN",
                        "identity": identity,
                        "shared_integrity_failure": True,
                    }
                )
                continue
            if ticker in acquisition_quarantines:
                disposition = acquisition_quarantines[ticker]
                if disposition["identity"] != identity:
                    raise Phase2Error("ACQUISITION_QUARANTINE_IDENTITY_DRIFT")
                changes.append({"ticker": ticker, "identity": identity,
                    "classification": "REVIEW_REQUIRED", "review_reason": "LOCAL_ACQUISITION_QUARANTINE",
                    "acquisition_scope": "NO_INCOMING_DATA_ACCEPTED",
                    "acquisition_quarantine": disposition, "snapshot_reference": snapshot.reference})
                continue
            if ticker not in slots:
                changes.append(
                    {
                        "ticker": ticker,
                        "classification": "REVIEW_REQUIRED",
                        "review_reason": carry.REASON,
                        "identity": identity,
                        "acquisition_scope": "NO_INCOMING_DATA_ACCEPTED",
                    }
                )
                continue
            if set(slots[ticker]) != {"ARQ", "MRQ"}:
                raise Phase2Error("PHASE2_DIMENSION_SCOPE_INVALID")
            source = {}
            diagnostic = False
            for d, slot in slots[ticker].items():
                loaded = snapshot.read_slot(slot["slot"])
                for row in loaded["records"]:
                    raw = capture.raw_payload(row)
                    for key in ("permaticker", "provider_security_id"):
                        if raw.get(key) is not None and str(raw[key]) != str(
                            identity["provider_security_id"]
                        ):
                            raise Phase2Error("PHASE2_FOREIGN_PROVIDER_IDENTITY")
                source[d] = rules.validate_complete_history(
                    loaded["records"], ticker=ticker, dimension=d
                )
                diagnostic |= loaded["receipt"]["state"] != "COMPLETE_VERIFIED"
                if source[d].status == "COMPLETE":
                    max_updated.extend(r["lastupdated"] for r in source[d].rows)
            current = {
                d: rules.load_current_history(paths.provider_db, ticker, d)
                for d in ("ARQ", "MRQ")
            }
            item, plan = _compare(
                paths,
                ticker,
                current,
                source,
                identity,
                queue.get(ticker),
                snapshot._run.request["source_day"],
                env.queue,
            )
            history = snapshot.compare_source_history(ticker, project_root=env.project)
            if (
                history["ticker_local_hold_required"]
                and not any(
                    (item.get(k) or {}).get("applied")
                    for k in (
                        "retained_history_approval",
                        "fiscal_revision_approval",
                        "true_removal_approval",
                        "accounting_boundary_resolution",
                    )
                )
            ) or diagnostic:
                item.update(
                    classification="REVIEW_REQUIRED",
                    review_reason=item.get("review_reason")
                    or "SOURCE_HISTORY_REVIEW_REQUIRED",
                )
            if ticker in degraded:
                item.update(
                    classification="REVIEW_REQUIRED", review_reason=carry.REASON
                )
            item["snapshot_reference"] = snapshot.reference
            changes.append(item)
            plans[ticker] = _compact_plan(plan)
        locality.bind_locality(
            changes, paths, publication_safety=safety, pending_baseline_holds=degraded
        )
        safe = []
        held = []
        global_items = []
        for change in changes:
            if change["classification"] != "REVIEW_REQUIRED":
                if change["classification"] in builders.REPLACEMENT_CLASSES:
                    safe.append(change)
                continue
            scope = _scope(change)
            scope["change"] = change
            if scope["scope"] == reviews.TICKER_LOCAL_REVIEW:
                held.append(scope)
                if not change.get("acquisition_quarantine"):
                    queue.upsert_local(
                        {k: v for k, v in scope.items() if k != "change"},
                        run_id=validation_id,
                        published_binding=rules.resolve_refresh_state(paths.provider_db).successful_run_id,
                    )
            else:
                global_items.append(scope)
        if set(x["ticker"] for x in safe) & set(x["ticker"] for x in held):
            raise Phase2Error("PHASE2_SAFE_HELD_COLLISION")
        status = "BLOCKED" if global_items else "VALIDATED" if safe else "NO_CHANGE"
        decisions = {
            "changes": changes,
            "safe": safe,
            "held": held,
            "global": global_items,
            "plans": plans,
            "old_retention": retained_old,
        }
        writer.write_json("decisions.json", decisions)
        inputs = _inputs(env, paths)
        receipt = _seal(
            {
                "contract": CONTRACT,
                "environment_identity": env.identity,
                "validation_id": validation_id,
                "snapshot_operation_id": snapshot_operation_id,
                "snapshot_reference": snapshot.reference,
                "snapshot_source_age_seconds": (
                    now()
                    - acquisition._time(snapshot.manifest["oldest_acquired_at_utc"])
                ).total_seconds(),
                "as_of_date": as_of_date,
                "old_refresh_state": rules.resolve_refresh_state(
                    paths.provider_db
                ).as_dict(),
                "inputs": inputs,
                "status": status,
                "production_authorized": False,
                "decision_fingerprint": fingerprint(
                    {"safe": safe, "held": held, "global": global_items}
                ),
                "decisions_sha256": sha256_file(writer.run_dir / "decisions.json"),
                "counts": {
                    "safe": len(safe),
                    "local_holds": len(held),
                    "baseline_holds": sum(
                        bool(h.get("baseline_integrity_hold")) for h in held
                    ),
                    "global": len(global_items),
                    "acquisition_quarantines": len(acquisition_quarantines),
                },
                "new_source_watermark": max(max_updated) if max_updated else None,
            }
        )
        writer.write_json("validation_receipt.json", receipt)
        _report(writer.run_dir, receipt, decisions)
        return receipt


class _OfflineSec:
    """No supplied supplemental SEC inputs: preserve native unresolved outcomes.

    Raising on a cache miss avoids claiming NOT_FOUND from an empty fabricated
    response. The unchanged resolver records the missing-input error/partial.
    """

    stats = {"requests": 0, "offline": True}

    def item_2_02_filings(self, *args, **kwargs):
        raise RuntimeError("PHASE2_SEC_INPUT_NOT_CAPTURED")


def build_candidate(env, validation_id, *, expected_validation_fingerprint, now=_now):
    with env.writer_lock():
        directory, receipt, decisions = _load(
            env, validation_id, expected_validation_fingerprint
        )
        if receipt["status"] == "NO_CHANGE":
            return receipt
        if (
            receipt["status"] != "VALIDATED"
            or decisions["global"]
            or not decisions["safe"]
        ):
            raise Phase2Error("PHASE2_BUILD_NOT_AUTHORIZED")
        paths = env.paths()
        snapshot = _assert_inputs(env, receipt, paths, now())
        analysis_preflight = refresh_universe.require_buildable_analysis_history(
            paths, decisions.get('old_retention', []))
        if hasattr(env, 'request'):
            refresh_universe.require_binding(paths, env.request())
        if journals.safety_status(env.journal).get("production_writes_blocked"):
            raise Phase2Error("PHASE2_RECOVERY_REQUIRED")
        lane = directory / "candidate"
        lane.mkdir(exist_ok=False)
        sources = {}
        plans = {}
        identities = {}
        for change in decisions["safe"]:
            ticker = change["ticker"]
            identities[ticker] = change["identity"]
            slots = [s for s in snapshot.iter_slots() if s["ticker"] == ticker]
            sources[ticker] = {
                s["dimension"]: rules.validate_complete_history(
                    snapshot.read_slot(s["slot"])["records"],
                    ticker=ticker,
                    dimension=s["dimension"],
                )
                for s in slots
            }
            current = {
                d: rules.load_current_history(paths.provider_db, ticker, d)
                for d in ("ARQ", "MRQ")
            }
            plans[ticker] = _hydrate_plan(
                decisions["plans"][ticker], current, sources[ticker]
            )
        provider = lane / "provider_candidate.db"
        canonical = lane / "canonical_candidate.db"
        online_backup(paths.provider_db, provider)
        provider_result = native.build_provider_candidate(
            provider,
            sources,
            identities,
            changes=decisions["safe"],
            applied_at=now().isoformat(),
            merge_plans=plans,
        )
        locality.verify_replacements(provider_result, identities)
        refresh_state = native._publish_refresh_state(
            provider,
            source_watermark=receipt["new_source_watermark"],
            schema_fingerprint=acquisition._read(
                snapshot._run.path("fetch/schema_receipt.json")
            )["schema_fingerprint"],
            run_id=validation_id,
            completed_at=now().isoformat(),
        )
        online_backup(paths.canonical_db, canonical)
        canonical_result = builders.fresh_rebuild_canonical(
            provider,
            canonical,
            applied_at=now().isoformat(),
            affected_company_ids=[int(x["company_id"]) for x in identities.values()],
            ownership_review_queue_path=env.queue,
            historical_freeze_changes=decisions["safe"],
            held_changes=decisions["held"] + decisions.get('old_retention', []),
        )
        held = locality.verify_held(paths, provider, canonical, decisions["held"])
        old_retention = locality.verify_retained(
            paths, provider, canonical, decisions.get('old_retention', []),
            old_authority=receipt['inputs']['old'])
        companion_retention = refresh_universe.financial_selection.verify_companion_retention(
            paths, provider, canonical)
        # Isolated fixture sources use the existing FULL_SQLITE_BACKUP authority
        # mode. No production-scale dependency copies or global taxonomy locks.
        if not hasattr(env, "prepare_sources") and any(
            paths.as_dict()[r].stat().st_size > 64 * 1024**2
            for r in ("market", "taxonomy")
        ):
            raise Phase2Error("PHASE2_DISPOSABLE_DEPENDENCY_TOO_LARGE")
        if hasattr(env, "prepare_sources"):
            read_sources, dependency_copies = env.prepare_sources(
                paths, lane, canonical, receipt["as_of_date"]
            )
        else:
            read_sources, dependency_copies = builders.prepare_full_v2_read_only_copies(
                paths, lane_dir=lane
            )
        analysis = native.run_refresh_production_full_v2_downstream(
            provider_candidate=provider,
            canonical_candidate=canonical,
            read_only_sources=read_sources,
            lane_dir=lane,
            as_of_date=receipt["as_of_date"],
        )
        if (
            analysis["status"] != "READY"
            or analysis["invocation_counts"]["full_v2_rebuild"] != 1
        ):
            raise Phase2Error("PHASE2_FULL_V2_NOT_READY")
        old_analysis_retention = refresh_universe.verify_analysis_retention(
            paths, canonical, Path(analysis['candidate_analysis_db']), decisions.get('old_retention', []))
        from .candidate_publication import run_candidate_publication

        publication_dates = run_candidate_publication(
            canonical,
            canonical_result["new_quarter_identities"],
            as_of_date=receipt["as_of_date"],
            client=env.sec_reader() if hasattr(env, "sec_reader") else _OfflineSec(),
            eligible_company_ids=(
                refresh_universe.require_binding(paths, env.request()).eligible_companies
                if hasattr(env, 'request') else None),
        )
        if hasattr(env, "verify_sec_scope"):
            env.verify_sec_scope(canonical, publication_dates)
        roles = {
            "provider": provider,
            "canonical": canonical,
            "analysis": Path(analysis["candidate_analysis_db"]),
        }
        candidate_sources = {
            "provider": provider,
            "canonical": canonical,
            **read_sources,
        }
        native._validate_analysis_generation(
            roles["analysis"],
            analysis_result=analysis,
            as_of_date=receipt["as_of_date"],
            sources=candidate_sources,
        )
        # Builder may touch independent ownership tables, never financial review
        # approval material. Any unexpected change remains a failed build.
        if _queue_binding(env) != receipt["inputs"]["queue"]:
            raise Phase2Error("PHASE2_APPROVAL_DRIFT_DURING_BUILD")
        generation_id = (
            f"snapshot_{env.operation_id}_{validation_id[6:14]}"
            if hasattr(env, "operation_id")
            else "snapshot_" + uuid4().hex
        )
        prepared = prepare_generation_from_candidates(
            roles,
            generation_id=generation_id,
            project_root=env.project,
            source=CONTRACT,
        )
        state = {
            # Native recovery owns the pre-move candidate lane. Generation
            # preparation moves those bytes; keep native cleanup ownership.
            "original_candidate_paths": {r: str(p.resolve()) for r, p in roles.items()},
            "canonical_result": canonical_result,
            "analysis_result": analysis,
            "provider_result": provider_result,
            "refresh_state": refresh_state,
            "read_only_sources": {k: str(v) for k, v in read_sources.items()},
            "read_only_source_fingerprints": {
                k: sha256_file(v)
                for k, v in read_sources.items()
                if k != "taxonomy" or not hasattr(env, "check_build_dependencies")
            },
            "dependency_copies": dependency_copies,
            "held_preservation": held,
            "old_retention_preservation": old_retention,
            "old_analysis_retention": old_analysis_retention,
            "old_analysis_preflight": analysis_preflight,
            "financial_companion_retention": companion_retention,
            "publication_dates": publication_dates,
            "prepared": prepared,
        }
        _write(directory / "build.json", state)
        updated = {k: v for k, v in receipt.items() if k != "fingerprint"}
        updated.update(
            status="CANDIDATE_READY",
            build_sha256=sha256_file(directory / "build.json"),
            candidate_generation_id=generation_id,
            candidate_manifest=prepared["manifest"],
        )
        updated = _seal(updated)
        _write(directory / "validation_receipt.json", updated)
        _report(directory, updated, decisions, build=state)
        return updated


def _load_build(env, directory, receipt):
    if sha256_file(directory / "build.json") != receipt["build_sha256"]:
        raise Phase2Error("PHASE2_BUILD_TAMPERED")
    build = _read(directory / "build.json")
    prepared = build["prepared"]
    if (
        prepared["manifest"] != receipt["candidate_manifest"]
        or prepared["manifest"]["generation_id"] != receipt["candidate_generation_id"]
    ):
        raise Phase2Error("PHASE2_CANDIDATE_IDENTITY_MISMATCH")
    root = _trusted(Path(prepared["generation_dir"]), env.root)
    roles = {
        r: _trusted(root / name, env.root)
        for r, name in prepared["manifest"]["roles"].items()
    }
    for r, path in roles.items():
        expected = prepared["manifest"]["role_verification"][r]
        if (
            sha256_file(path) != expected["sha256"]
            or path.stat().st_size != expected["size_bytes"]
        ):
            raise Phase2Error("PHASE2_CANDIDATE_TAMPERED")
    for role, path in build["read_only_sources"].items():
        source = _trusted(path, env.root)
        expected = build["read_only_source_fingerprints"].get(role)
        if expected is not None and sha256_file(source) != expected:
            raise Phase2Error("PHASE2_READ_ONLY_SOURCE_TAMPERED")
        if expected is None and not hasattr(env, "check_build_dependencies"):
            raise Phase2Error("PHASE2_READ_ONLY_SOURCE_UNBOUND")
    if hasattr(env, "check_build_dependencies"):
        env.check_build_dependencies(build)
    return build, roles


def _publish_candidate(
    env,
    validation_id,
    *,
    expected_validation_fingerprint,
    confirmation,
    now=_now,
    inject_failure=None,
    inject_crash=None,
    phase_callback=None,
):
    if confirmation != getattr(env, "publication_confirmation", CONFIRM):
        raise PermissionError("PHASE2_DISPOSABLE_PUBLICATION_CONFIRMATION_REQUIRED")
    with env.writer_lock():
        # Recovery first, independent of lost/corrupt source snapshots.
        journals.guard_production_writes(env.journal)
        directory, receipt, decisions = _load(
            env, validation_id, expected_validation_fingerprint
        )
        if (
            receipt["status"] != "CANDIDATE_READY"
            or decisions["global"]
            or not decisions["safe"]
        ):
            raise Phase2Error("PHASE2_PUBLICATION_NOT_AUTHORIZED")
        paths = env.paths()
        snapshot = _assert_inputs(env, receipt, paths, now())
        build, roles = _load_build(env, directory, receipt)
        authority = (
            env.publication_authority(receipt)
            if hasattr(env, "publication_authority")
            else {
                "contract": CONTRACT,
                "snapshot_reference": snapshot.reference,
                "validation_fingerprint": receipt["fingerprint"],
                "scope": "DISPOSABLE_ONLY",
                "explicit_confirmation": confirmation,
            }
        )
        current = resolve_active_generation(env.project, require_generation=True)
        journal = None
        committed = False

        def boundary(name):
            if inject_crash == name:
                raise native.SimulatedPublicationCrash(name)
            if inject_failure == name:
                raise RuntimeError("PHASE2_INJECTED_" + name)

        try:
            backups = native._verified_backups(
                paths, directory / "backups", immutable_generation=True
            )
            native._validate_generation_backup_binding(current, backups)
            records = native._candidate_manifest(roles, backups)
            for role, record in records.items():
                original = _trusted(
                    Path(build["original_candidate_paths"][role]), env.root
                )
                if validation_id not in original.parts:
                    raise Phase2Error("PHASE2_CANDIDATE_LANE_OWNER_MISMATCH")
                record["candidate_path"] = str(original)
            journal = journals.prepare_journal(
                path=env.journal,
                operation_type="REFRESH_FUNDAMENTALS",
                run_id=validation_id,
                preview_run_id=None,
                test_run_id=None,
                refresh_set_fingerprint=receipt["decision_fingerprint"],
                old_source_watermark=rules.resolve_refresh_state(
                    paths.provider_db
                ).published_watermark,
                new_source_watermark=build["refresh_state"][
                    "published_source_watermark"
                ],
                source_schema_fingerprint=build["refresh_state"][
                    "source_schema_fingerprint"
                ],
                roles=records,
                publication_mode="GENERATION_POINTER",
                old_generation=current.evidence()
                | {"manifest": dict(current.manifest)},
                new_generation_id=receipt["candidate_generation_id"],
                active_generation_manifest_path=active_manifest_path(env.project),
                snapshot_authorization=authority,
            )
            journal = journals.update_journal(
                env.journal,
                journal,
                new_generation_manifest=receipt["candidate_manifest"],
                new_generation_dir=build["prepared"]["generation_dir"],
                generation_activation_state="READY",
            )
            boundary("AFTER_PREPARE")
            if phase_callback:
                phase_callback("PUBLISH")
            journal = journals.activate_prepared_generation(
                journal,
                new_manifest=receipt["candidate_manifest"],
                journal_path=env.journal,
            )
            boundary("AFTER_ACTIVATION")
            if phase_callback:
                phase_callback("VERIFY")
            active = env.paths()
            sources = {}
            plans = {}
            for change in decisions["safe"]:
                ticker = change["ticker"]
                slots = [s for s in snapshot.iter_slots() if s["ticker"] == ticker]
                sources[ticker] = {
                    s["dimension"]: rules.validate_complete_history(
                        snapshot.read_slot(s["slot"])["records"],
                        ticker=ticker,
                        dimension=s["dimension"],
                    )
                    for s in slots
                }
                old = {
                    d: rules.load_current_history(paths.provider_db, ticker, d)
                    for d in ("ARQ", "MRQ")
                }
                plans[ticker] = _hydrate_plan(
                    decisions["plans"][ticker], old, sources[ticker]
                )
            postflight = native._postflight(
                paths=active,
                histories=sources,
                merge_plans=plans,
                canonical_result=build["canonical_result"],
                analysis_result=build["analysis_result"],
                expected_roles=journal["roles"],
                refresh_state=build["refresh_state"],
                as_of_date=receipt["as_of_date"],
                read_only_sources={
                    k: Path(v) for k, v in build["read_only_sources"].items()
                },
                boundary_applications=native.applied_applications(decisions["safe"]),
            )
            held = locality.verify_held(
                paths, active.provider_db, active.canonical_db, decisions["held"]
            )
            locality.verify_retained(paths, active.provider_db, active.canonical_db,
                                    decisions.get('old_retention', []), old_authority=receipt['inputs']['old'])
            refresh_universe.financial_selection.verify_companion_retention(
                paths, active.provider_db, active.canonical_db)
            refresh_universe.verify_analysis_retention(
                paths, active.canonical_db, active.analysis_db, decisions.get('old_retention', []))
            boundary("AFTER_POSTFLIGHT")
            journal = journals.update_journal(
                env.journal,
                journal,
                state="COMPLETED",
                postflight_state="PASSED",
                rollback_recovery_state="NOT_REQUIRED",
                current_publication_step="COMPLETED",
            )
            committed = True
            result = {
                "status": "PUBLISHED",
                "validation_id": validation_id,
                "snapshot_reference": snapshot.reference,
                "generation_id": receipt["candidate_generation_id"],
                "postflight": postflight,
                "held_preservation": held,
                "production_mutation": bool(getattr(env, "is_live", False)),
                "disposable_mutation": True,
                "journal_state": journal["state"],
            }
            _write(directory / "commit_receipt.json", _seal(result))
            _finalize_reviews(env, directory, receipt, decisions, build)
            _report(directory, receipt, decisions, build=build, publication=result)
            return result
        except Exception as error:
            if committed:
                result = {
                    "status": "PUBLISHED_WITH_REVIEW_SYNC_PENDING",
                    "error": str(error),
                    "production_mutation": bool(getattr(env, "is_live", False)),
                    "journal_state": "COMPLETED",
                }
                _report(directory, receipt, decisions, build=build, publication=result)
                return result
            if journal is not None:
                restored = journals.restore_old_generation(
                    journal, journal_path=env.journal
                )
                journals.update_journal(
                    env.journal,
                    restored["journal"],
                    state="ROLLED_BACK",
                    rollback_recovery_state="RESTORED_AND_VERIFIED",
                    publication_error=str(error),
                )
                result = {
                    "status": "ROLLED_BACK",
                    "error": str(error),
                    "production_mutation": bool(getattr(env, "is_live", False)),
                    "disposable_mutation": True,
                }
            else:
                result = {
                    "status": "FAILED_BEFORE_PUBLISH",
                    "error": str(error),
                    "production_mutation": False,
                }
            _write(directory / "publication_failure.json", result)
            _report(directory, receipt, decisions, build=build, publication=result)
            return result


def _finalize_reviews(env, directory, receipt, decisions, build):
    pending = directory / "review_finalization.json"
    _write(pending, {"status": "PENDING", "validation_id": receipt["validation_id"]})
    queue = reviews.RefreshReviewQueue(env.queue)
    finalized = []
    for change in decisions["safe"]:
        for key in (
            "retained_history_approval",
            "fiscal_revision_approval",
            "true_removal_approval",
        ):
            approval = change.get(key) or {}
            if not approval.get("applied"):
                continue
            item = queue.finalize_published_approval(
                change["ticker"],
                production_run_id=receipt["validation_id"],
                approval_evidence_fingerprint=approval["approval_evidence_fingerprint"],
                published_state_binding_before=str(
                    receipt["old_refresh_state"]["successful_run_id"]
                ),
                published_state_binding_after=str(
                    build["refresh_state"]["successful_run_id"]
                ),
                published_at_utc=str(build["refresh_state"]["completed_at_utc"]),
            )
            finalized.append({"ticker": item["ticker"], "status": item["status"]})
    _write(
        pending,
        {
            "status": "COMPLETED",
            "validation_id": receipt["validation_id"],
            "finalized": finalized,
        },
    )
    return finalized


def finalize_disposable_reviews(env, validation_id):
    """Idempotent post-commit bookkeeping; no source/network/financial writes."""
    with env.writer_lock():
        directory = _operation(env, validation_id)
        receipt = _read(_trusted(directory / "validation_receipt.json", env.root))
        _verify(receipt)
        commit = _read(_trusted(directory / "commit_receipt.json", env.root))
        _verify(commit)
        journal = journals.load_journal(env.journal)
        active = resolve_active_generation(env.project, require_generation=True)
        if (
            not journal
            or journal["state"] != "COMPLETED"
            or journal["postflight_state"] != "PASSED"
            or journal["production_run_id"] != validation_id
            or commit["generation_id"] != active.generation_id
            or commit["snapshot_reference"] != receipt["snapshot_reference"]
        ):
            raise Phase2Error("PHASE2_FINANCIAL_COMMIT_REQUIRED")
        child = _trusted(directory / "decisions.json", env.root)
        if sha256_file(child) != receipt["decisions_sha256"]:
            raise Phase2Error("PHASE2_DECISIONS_TAMPERED")
        build_path = _trusted(directory / "build.json", env.root)
        if sha256_file(build_path) != receipt["build_sha256"]:
            raise Phase2Error("PHASE2_BUILD_TAMPERED")
        return _finalize_reviews(
            env, directory, receipt, _read(child), _read(build_path)
        )


def recover_disposable(env):
    with env.writer_lock():
        return journals.guard_production_writes(env.journal)


def publish_disposable(env, validation_id, **kwargs):
    if not isinstance(env, DisposableEnvironment):
        raise Phase2Error("PHASE2_DISPOSABLE_ENVIRONMENT_REQUIRED")
    return _publish_candidate(env, validation_id, **kwargs)
