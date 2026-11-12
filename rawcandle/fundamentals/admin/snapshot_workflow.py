"""One UPDATE coordinator using existing capture/build/publication authorities."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
from uuid import uuid4

from . import acquisition_snapshot as acquisition, refresh_update as core
from . import refresh_fundamentals as rules, refresh_review_queue as reviews
from . import publication_journal as journal, sec_snapshot
from .artifacts import AdminRunWriter, stable_run_id, sha256_file
from .contracts import AdminOperationType, fingerprint
from .snapshot_environment import CONTRACT, ROUTE, CONFIRM


def _now():
    return datetime.now(timezone.utc)


def sec_plan(env, snapshot, as_of):
    """Conservative NEW fiscal identities + unchanged native recent retry cap."""
    from .candidate_publication import select_candidate_scope

    paths = env.paths()
    retry = select_candidate_scope(paths.canonical_db, [], as_of_date=as_of)
    from . import accounting_boundary_review as boundary

    boundary_companies = set()
    for item in [
        *boundary.read_items(env.queue),
        *boundary.installed_decisions(paths.provider_db),
    ]:
        identity = (item.get("proposal") or {}).get("evidence", {}).get("identity", {})
        if identity.get("company_id") is not None:
            boundary_companies.add(identity["company_id"])
    periods = {}
    with core.carry.readonly(paths.canonical_db) as db:
        companies = {
            r["company_id"]: dict(r)
            for r in db.execute(
                "SELECT company_id,cik_normalized FROM company_cik WHERE status='ACTIVE'"
            )
        }
        old = {
            (r[0], f"{r[1]}-{r[2]}")
            for r in db.execute(
                "SELECT company_id,fiscal_year,fiscal_quarter FROM v4_quarter"
            )
        }
        for key in retry["quarter_keys"]:
            row = db.execute(
                "SELECT period_end FROM v4_quarter WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?",
                key,
            ).fetchone()
            periods.setdefault(key[0], set()).add(row[0])
    for slot in snapshot.iter_slots():
        if slot["dimension"] != "ARQ":
            continue
        identity = rules.resolve_identity(paths, slot["ticker"])
        if identity["status"] != "KNOWN":
            continue
        company = identity["company_id"]
        for record in snapshot.read_slot(slot["slot"])["records"]:
            raw = core.capture.raw_payload(record)
            if (
                (company, raw.get("fiscalperiod")) not in old
                or company in boundary_companies
            ) and raw.get("reportperiod"):
                periods.setdefault(company, set()).add(raw["reportperiod"])
    result = []
    for company, values in sorted(periods.items()):
        cik = companies.get(company, {}).get("cik_normalized")
        if not cik:
            continue  # Native scoped_quarters has the same CIK requirement.
        first, last = min(values), max(values)
        result.append(
            {
                "company_id": company,
                "cik": str(cik),
                "from_calendar_year": date.fromisoformat(first).year,
                "from_calendar_date": first,
                "to_calendar_date": (
                    date.fromisoformat(last) + timedelta(days=180)
                ).isoformat(),
            }
        )
    return result


class SnapshotWorkflow:
    def __init__(
        self,
        env,
        *,
        client=None,
        sec_fetch_bytes=None,
        now=_now,
        progress_callback=None,
        ownership_runner=None,
    ):
        self.env, self.client, self.sec_fetch_bytes = env, client, sec_fetch_bytes
        self.now, self.callback, self.ownership_runner = (
            now,
            progress_callback,
            ownership_runner,
        )
        self.env.clock = lambda: self.now()

    def _persist(self, result, stage=None):
        if stage:
            result["current_stage"] = stage
            if (
                not result.setdefault("phase_events", [])
                or result["phase_events"][-1] != stage
            ):
                result["phase_events"].append(stage)
        result["workflow_status"] = result["outcome"]
        result["preview_payload_path"] = str(
            self.env.directory() / "update_request.json"
        )
        request = core._read(self.env.directory() / "update_request.json")
        result["preview_fingerprint"] = request["fingerprint"]
        counts = result.get("source_summary", {})
        result["summary_rows"] = [
            f"Snapshot UPDATE: {result['outcome']} · {result['current_stage']}",
            f"Safe {counts.get('safe_changes',0)}; local holds {counts.get('held_for_review',0)}; global blockers {counts.get('global_blockers',0)}",
            f"Financial committed: {result['production_completed']}",
        ]
        writer = AdminRunWriter(
            result["run_id"],
            AdminOperationType.REFRESH_FUNDAMENTALS,
            root=self.env.runs,
        )
        for name in ("result.json", "workflow_result.json"):
            writer.write_json(name, result)
        progress = {
            "run_id": result["run_id"],
            "current_stage_id": result["current_stage"],
            "stage_state": result["outcome"],
            "message": result.get("message", result["current_stage"]),
            "stages": result["stages"],
        }
        writer.write_json("progress_status.json", progress)
        if self.callback:
            self.callback(progress)
        report = [
            "# Fundamentals snapshot UPDATE",
            "",
            f"Run: `{result['run_id']}`; outcome: **{result['outcome']}**; trigger: {result['trigger_source']}.",
            f"Stage: {result['current_stage']}; financial committed: {result['production_completed']}.",
            "Labels: Preview = local classification; Test on copies = the one inactive candidate; Production update = exact-candidate activation/postflight.",
            "",
            f"Source: `{result.get('snapshot_reference')}`.",
            f"Original OLD: `{request['old_authority']['generation_id']}`; as-of: {request['as_of_date']}; freshness limit: 168 hours, original capture timestamps.",
            f"Actual phase events: `{result.get('phase_events',[])}`.",
            f"SEC publication authority: `{json.dumps(result.get('sec_publication',{}),sort_keys=True)}`.",
            f"Decisions: `{json.dumps(result.get('source_summary',{}),sort_keys=True)}`.",
            f"Publication: `{json.dumps(result.get('publication_outcome',{}),sort_keys=True)}`.",
            f"Ownership (separate transaction): `{json.dumps(result.get('ownership_auto',{}),sort_keys=True)}`.",
            f"Message: {result.get('message','')}",
            "",
            "Detailed immutable source: fetch_operation_id and sec/manifest.json. Financial decisions, build and native postflight are linked by validation_id; no raw source bodies are embedded here.",
        ]
        for name in ("workflow_report.md", "operation_report.md"):
            writer.write_text(name, "\n".join(report) + "\n")
        writer.write_manifest()
        return result

    def start(
        self,
        *,
        trigger_source="MANUAL",
        as_of_date=None,
        publication_intent=False,
        ownership_intent=None,
        stop_after="publish",
    ):
        env = self.env
        if (
            trigger_source not in {"MANUAL", "SCHEDULER"}
            or env.config()["route"] != ROUTE
        ):
            raise PermissionError("SNAPSHOT_UPDATE_ROUTE_NOT_SELECTED")
        if type(publication_intent) is not bool:
            raise ValueError("UPDATE_INTENT_MUST_BE_BOOLEAN")
        if ownership_intent is not None and type(ownership_intent) is not bool:
            raise ValueError("OWNERSHIP_INTENT_MUST_BE_BOOLEAN")
        uid = uuid4().hex
        run_id = (
            stable_run_id(
                AdminOperationType.REFRESH_FUNDAMENTALS, uid, suffix="snapshot_update"
            )
            + "_"
            + uid[:8]
        )
        env.operation_id = run_id
        with env.writer_lock():
            journal.guard_production_writes(env.journal)
            request = core._seal(
                {
                    "contract": CONTRACT,
                    "intent": "UPDATE",
                    "mode": "FULL_WORKFLOW",
                    "update_run_id": run_id,
                    "environment_identity": env.identity,
                    "trigger_source": trigger_source,
                    "created_at_utc": self.now().isoformat(),
                    "as_of_date": as_of_date or self.now().date().isoformat(),
                    "source_day": self.now().date().isoformat(),
                    "configuration": env.config(),
                    "old_authority": acquisition.pin_old_authority(env.project),
                    "policy": {
                        "snapshot_max_age_seconds": acquisition.MAX_AGE_SECONDS,
                        "rolling_history": acquisition.POLICY,
                        "publication_retry_days": 60,
                        "publication_retry_cap": 100,
                        "sec_network_budget_seconds": sec_snapshot.NETWORK_BUDGET_SECONDS,
                    },
                    "fetch_operation_id": "fetch_" + uid,
                    "publication_intent": publication_intent,
                    "ownership_intent": (
                        env.config()["ownership"]
                        if ownership_intent is None
                        else ownership_intent
                    ),
                }
            )
            core._write(env.directory() / "update_request.json", request)
            AdminRunWriter(
                run_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=env.runs
            ).write_json(
                "request.json",
                {
                    "operation_type": "REFRESH_FUNDAMENTALS",
                    "mode": "FULL_WORKFLOW",
                    "trigger_source": trigger_source,
                    "update_request_fingerprint": request["fingerprint"],
                },
            )
        result = {
            "run_id": run_id,
            "artifact_dir": str(env.directory()),
            "operation_type": "REFRESH_FUNDAMENTALS",
            "mode": "FULL_WORKFLOW",
            "contract": CONTRACT,
            "trigger_source": trigger_source,
            "started_at_utc": self.now().isoformat(),
            "completed_at_utc": None,
            "outcome": "RUNNING",
            "current_stage": "FETCH",
            "stages": [],
            "warnings": [],
            "production_completed": False,
            "production_entered": False,
            "production_database_writes": 0,
            "fetch_operation_id": request["fetch_operation_id"],
        }
        self._persist(result)
        return self.advance(
            run_id, stop_after=stop_after, confirm_publish=publication_intent
        )

    def _fetch(self, request, result):
        env = self.env
        directory = env.directory()

        def fetch_progress(event):
            event = {**event, "run_id": result["run_id"]}
            AdminRunWriter(
                result["run_id"], AdminOperationType.REFRESH_FUNDAMENTALS, root=env.runs
            ).write_json("progress_status.json", event)
            if self.callback:
                self.callback(event)

        discovery_path = directory / "discovery.json"
        from rawcandle.fundamentals.providers.sharadar import SharadarClient

        if not discovery_path.exists():
            if acquisition.pin_old_authority(env.project) != request["old_authority"]:
                raise ValueError("UPDATE_OLD_DRIFT")
            api = self.client or SharadarClient()
            paths = env.paths()
            discovery = rules.discover_changed_tickers(
                api,
                query_start_date=rules.resolve_refresh_state(
                    paths.provider_db
                ).query_start_date,
                today=date.fromisoformat(request["source_day"]),
            )
            from . import accounting_boundary_review as boundary

            queue = reviews.RefreshReviewQueue(env.queue)
            pending = set(queue.pending_tickers())
            pending.update(
                i["proposal"]["evidence"]["identity"]["ticker"]
                for i in boundary.read_items(env.queue)
            )
            pending.update(
                i["proposal"]["evidence"]["identity"]["ticker"]
                for i in boundary.installed_decisions(paths.provider_db)
            )
            discovery["evaluation_tickers"] = sorted(
                set(discovery["changed_tickers"]) | pending
            )
            discovery["queued_tickers_reevaluated"] = sorted(pending)
            core._write(discovery_path, core._seal(discovery))
        discovery = core._read(discovery_path)
        core._verify(discovery)
        fetch_id = request["fetch_operation_id"]
        if not (env.runs / fetch_id).exists():
            fetched = acquisition.start_fetch(
                discovery["evaluation_tickers"],
                project_root=env.project,
                source_day=request["source_day"],
                root=env.runs,
                operation_id=fetch_id,
                client=self.client,
                now=self.now,
                update_binding=request,
                progress_callback=fetch_progress,
            )
        else:
            fetched = acquisition.resume_fetch(
                fetch_id,
                project_root=env.project,
                root=env.runs,
                client=self.client,
                now=self.now,
                progress_callback=fetch_progress,
            )
        result["fetch_status"] = {
            k: v for k, v in fetched.items() if k not in {"snapshot_reference"}
        }
        if fetched["status"] != "FETCH_SEALED":
            result.update(
                outcome=fetched["status"],
                message=fetched.get("reason", fetched["status"]),
            )
            return False
        snapshot = acquisition.open_snapshot(fetch_id, root=env.runs)
        snapshot.validate_preflight(
            old_authority=request["old_authority"], now=self.now()
        )
        env.require_update_snapshot(snapshot)
        result["snapshot_reference"] = snapshot.reference
        sec_snapshot.capture(
            directory / "sec",
            operation_id=env.operation_id,
            snapshot_reference=snapshot.reference,
            plan=sec_plan(env, snapshot, request["as_of_date"]),
            fetch_bytes=self.sec_fetch_bytes,
            now=self.now,
        )
        sealed = core._seal(
            {
                "update_run_id": env.operation_id,
                "snapshot_reference": snapshot.reference,
                "discovery_sha256": sha256_file(discovery_path),
                "sec_manifest_sha256": sha256_file(directory / "sec/manifest.json"),
            }
        )
        core._write(directory / "update_sources.json", sealed)
        return True

    def advance(
        self,
        run_id,
        *,
        stop_after="publish",
        confirm_publish=False,
        retry_local=False,
        inject_failure=None,
        inject_crash=None,
    ):
        if stop_after not in {"fetch", "validate", "build", "publish"}:
            raise ValueError("UPDATE_STAGE_INVALID")
        env = self.env
        env.operation_id = run_id
        directory = env.directory()
        result = core._read(directory / "result.json")
        if (
            result.get("production_completed")
            or result.get("outcome") == "NO_CHANGE"
            and not retry_local
            and (stop_after != "publish" or "ownership_auto" in result)
        ):
            return result  # Never replay a healthy committed financial operation.
        try:
            # Native recovery must precede opening source/authorization files.
            with env.writer_lock():
                journal.guard_production_writes(env.journal)
            request = env.request()
            acquisition._age([acquisition._time(request["created_at_utc"])], self.now())
            if retry_local and not (directory / "update_sources.json").is_file():
                raise ValueError("LOCAL_RETRY_REQUIRES_SEALED_FETCH")
            if not (directory / "update_sources.json").exists():
                self._persist(result, "FETCH")
                if not self._fetch(request, result):
                    return self._persist(result)
            if stop_after == "fetch":
                result["outcome"] = "FETCH_SEALED"
                return self._persist(result)
            env.update_inputs()
            snapshot = acquisition.open_snapshot(
                request["fetch_operation_id"], root=env.runs
            )
            snapshot.validate_preflight(
                old_authority=acquisition.pin_old_authority(env.project), now=self.now()
            )
            env.require_update_snapshot(snapshot)
            result["snapshot_source_age_hours"] = (
                self.now()
                - acquisition._time(snapshot.manifest["oldest_acquired_at_utc"])
            ).total_seconds() / 3600
            if retry_local:
                result.pop("validation_id", None)
                result.pop("test_run_id", None)
                result.update(
                    manual_production_available=False, manual_test_retry_available=False
                )
            if not result.get("validation_id"):
                self._persist(result, "VALIDATE")
                receipt = core.validate_snapshot(
                    env,
                    request["fetch_operation_id"],
                    as_of_date=request["as_of_date"],
                    now=self.now,
                )
                result["validation_id"] = receipt["validation_id"]
                result.setdefault("local_attempts", []).append(receipt["validation_id"])
            receipt = core._read(
                core._operation(env, result["validation_id"])
                / "validation_receipt.json"
            )
            core._verify(receipt)
            result["validation_fingerprint"] = receipt["fingerprint"]
            result["source_summary"] = {
                "safe_changes": receipt["counts"]["safe"],
                "effective_changed_known": receipt["counts"]["safe"],
                "held_for_review": receipt["counts"]["local_holds"],
                "global_blockers": receipt["counts"]["global"],
            }
            decisions = core._read(
                core._operation(env, result["validation_id"]) / "decisions.json"
            )
            result["review_partition"] = {
                "held": [
                    {k: h.get(k) for k in ("ticker", "scope", "review_type", "reason")}
                    for h in decisions["held"]
                ],
                "details": str(
                    core._operation(env, result["validation_id"]) / "decisions.json"
                ),
            }
            if receipt["status"] in {"BLOCKED", "NO_CHANGE"}:
                result.update(
                    outcome=receipt["status"], completed_at_utc=self.now().isoformat()
                )
                if receipt["status"] == "NO_CHANGE" and stop_after == "publish":
                    self._ownership(result, request, receipt, no_change=True)
                return self._persist(result)
            if stop_after == "validate":
                result["outcome"] = "VALIDATED"
                result["manual_test_retry_available"] = True
                result["stages"] = [
                    {"stage": "Preview", "status": "COMPLETED", "result": "VALIDATED"}
                ]
                return self._persist(result)
            if receipt["status"] == "VALIDATED":
                self._persist(result, "BUILD")
                receipt = core.build_candidate(
                    env,
                    receipt["validation_id"],
                    expected_validation_fingerprint=receipt["fingerprint"],
                    now=self.now,
                )
                result["validation_fingerprint"] = receipt["fingerprint"]
            result["stages"] = [
                {"stage": "Preview", "status": "COMPLETED", "result": "VALIDATED"},
                {
                    "stage": "Test on copies",
                    "status": "COMPLETED",
                    "result": "CANDIDATE_READY",
                },
            ]
            build = core._read(
                core._operation(env, receipt["validation_id"]) / "build.json"
            )
            result["sec_publication"] = {
                k: build["publication_dates"].get(k)
                for k in (
                    "status",
                    "status_counts",
                    "total_processed",
                    "retry_days",
                    "retry_max_quarters",
                    "unprocessed_selected",
                )
            }
            if stop_after == "build" or not confirm_publish:
                result.update(
                    outcome="CANDIDATE_READY",
                    message="Exact inactive candidate ready; separate publication confirmation required.",
                )
                result.update(
                    manual_production_available=True,
                    test_run_id=receipt["validation_id"],
                    manual_test_retry_available=False,
                )
                return self._persist(result, "BUILD")
            with env.writer_lock():
                env.grant_publication(receipt, confirmed=confirm_publish)
            self._persist(result, "PUBLISH")
            result["production_entered"] = True
            result["manual_production_available"] = False
            published = core._publish_candidate(
                env,
                receipt["validation_id"],
                expected_validation_fingerprint=receipt["fingerprint"],
                confirmation=CONFIRM,
                now=self.now,
                inject_failure=inject_failure,
                inject_crash=inject_crash,
                phase_callback=lambda stage: self._persist(result, stage),
            )
            result["publication_outcome"] = {
                k: v
                for k, v in published.items()
                if k not in {"postflight", "held_preservation"}
            }
            build = core._read(
                core._operation(env, receipt["validation_id"]) / "build.json"
            )
            result["publication_outcome"].update(
                old_watermark=receipt["old_refresh_state"]["published_watermark"],
                new_watermark=(
                    build["refresh_state"]["published_source_watermark"]
                    if published["status"].startswith("PUBLISHED")
                    else receipt["old_refresh_state"]["published_watermark"]
                ),
            )
            result["outcome"] = (
                "COMPLETED"
                if published["status"] == "PUBLISHED"
                else published["status"]
            )
            result["production_completed"] = published["status"] in {
                "PUBLISHED",
                "PUBLISHED_WITH_REVIEW_SYNC_PENDING",
            }
            result["production_database_writes"] = (
                3 if env.is_live and result["production_completed"] else 0
            )
            result["stages"].append(
                {
                    "stage": "Production update",
                    "status": (
                        "COMPLETED" if result["production_completed"] else "FAILED"
                    ),
                    "result": published["status"],
                    "run_id": receipt["validation_id"],
                }
            )
            if published["status"] == "PUBLISHED":
                self._ownership(result, request, receipt)
            result["completed_at_utc"] = self.now().isoformat()
            return self._persist(result, "VERIFY")
        except journal.PublicationRecoveredRetryRequired as error:
            result.update(
                outcome="RETRY_REQUIRED",
                message=str(error),
                publication_recovery=error.recovery,
                completed_at_utc=self.now().isoformat(),
            )
            return self._persist(result, "RECOVERY")
        except Exception as error:
            outcome = (
                "PUBLISHED_WITH_REVIEW_SYNC_PENDING"
                if result.get("production_completed")
                else (
                    "FETCH_PAUSED"
                    if result["current_stage"] == "FETCH"
                    and isinstance(error, rules.RefreshPreviewError)
                    and ":RATE_LIMITED:" in str(error)
                    else "FAILED"
                )
            )
            result.update(
                outcome=outcome,
                message=str(error),
                failed_stage=result["current_stage"],
                completed_at_utc=self.now().isoformat(),
            )
            result.update(
                manual_production_available=False, manual_test_retry_available=False
            )
            return self._persist(result)

    def finalize_reviews(self, run_id):
        """Explicit local bookkeeping retry after commit; no source/network use."""
        self.env.operation_id = run_id
        request = self.env.request()
        result = core._read(self.env.directory() / "result.json")
        if not result.get("production_completed"):
            raise ValueError("UPDATE_FINANCIAL_COMMIT_REQUIRED")
        core.finalize_disposable_reviews(self.env, result["validation_id"])
        receipt = core._read(
            core._operation(self.env, result["validation_id"])
            / "validation_receipt.json"
        )
        self._ownership(result, request, receipt)
        result.update(
            outcome="COMPLETED",
            message="Committed financial review finalization completed.",
        )
        return self._persist(result, "REVIEW_FINALIZATION")

    def _ownership(self, result, request, receipt, *, no_change=False):
        from .pb_ownership_future import FutureOwnershipWorkflow, summary

        if not request["ownership_intent"] or not self.env.config()["ownership"]:
            result["ownership_auto"] = summary(False, status="DISABLED")
            return
        try:
            outcome_path = self.env.directory() / "ownership_outcome.json"
            if outcome_path.exists():
                previous = core._read(outcome_path)
                core._verify(previous)
                if previous["status"] in {"COMPLETED", "NO_AUTO_CANDIDATES"}:
                    result["ownership_auto"] = {
                        k: v for k, v in previous.items() if k != "fingerprint"
                    }
                    result["ownership_production_completed"] = bool(
                        previous.get("published")
                    )
                    return
            with self.env.writer_lock():
                if no_change:
                    if (
                        receipt["status"] != "NO_CHANGE"
                        or receipt["counts"]["global"]
                        or receipt["counts"]["safe"]
                    ):
                        raise ValueError("OWNERSHIP_SAFE_NOOP_AUTHORITY_REQUIRED")
                    core._assert_inputs(self.env, receipt, self.env.paths(), self.now())
                else:
                    finalized = core._read(
                        core._operation(self.env, receipt["validation_id"])
                        / "review_finalization.json"
                    )
                    if finalized["status"] != "COMPLETED":
                        raise ValueError("OWNERSHIP_REVIEW_FINALIZATION_REQUIRED")
                safety = journal.safety_status(self.env.journal)
                if safety["production_writes_blocked"]:
                    raise ValueError("OWNERSHIP_FINANCIAL_RECOVERY_REQUIRED")
                financial_generation = core.resolve_active_generation(
                    self.env.project, require_generation=True
                ).generation_id
            runner = (
                self.ownership_runner
                or FutureOwnershipWorkflow(
                    project_root=self.env.project,
                    run_root=self.env.runs,
                    as_of=request["as_of_date"],
                    scheduler_log_dir=self.env.log_dir,
                ).run
            )
            ownership_root = self.env.directory() / "ownership_auto"
            attempt = (
                1 + len(list(ownership_root.glob("attempt_*")))
                if ownership_root.exists()
                else 1
            )
            state = dict(
                runner(
                    enabled=True,
                    directory=ownership_root / f"attempt_{attempt:04d}",
                    trigger_source=request["trigger_source"],
                )
            )
            state.update(
                financial_generation_id=financial_generation,
                financial_precondition=(
                    "SAFE_FINANCIAL_NO_OP"
                    if no_change
                    else "VERIFIED_REVIEW_FINALIZED_COMMIT"
                ),
            )
            result["ownership_auto"] = state
            result["ownership_production_completed"] = bool(state.get("published"))
            core._write(outcome_path, core._seal(state))
        except Exception as error:
            result["ownership_auto"] = summary(
                True, status="FAILED_OR_STALE", reason=str(error)
            )
            result["ownership_auto"]["failed_stale"] = 1
            result["warnings"].append(
                "Independent ownership continuation failed: " + str(error)
            )
