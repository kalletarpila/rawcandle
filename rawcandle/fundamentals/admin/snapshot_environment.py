"""Native production paths/locks and an explicit owned-copy rehearsal adapter."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
from datetime import date, timedelta
import json

from . import refresh_update as core, acquisition_snapshot as acquisition
from . import publication_journal as journal, refresh_production as native
from . import refresh_copy_runtime as builders, source_bundle as sources
from . import sec_snapshot
from . import refresh_universe
from .artifacts import ROOT, ADMIN_RUN_ROOT, sha256_file
from .batch_add_tickers import BatchAddTickerPaths
from .contracts import fingerprint
from .production_transaction import production_lock, _no_sidecars
from .refresh_review_queue import queue_path_for_run_root
from rawcandle.datacenter_taxonomy_operation_log import current_taxonomy_operation_lock
from rawcandle.fundamentals.generations import (
    resolve_active_generation,
    resolved_production_paths,
)

CONTRACT = "FUNDAMENTALS_SNAPSHOT_UPDATE_V1"
ROUTE = "SNAPSHOT_V1"
CONFIRM = "CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS"


class SnapshotEnvironment:
    """No arbitrary live path overrides; copy mode retains Phase 2 ownership."""

    publication_confirmation = CONFIRM

    def __init__(
        self,
        *,
        copy_owner=None,
        configuration=None,
        scheduler_log_dir=None,
        scheduler_managed_locks=False
    ):
        if (
            copy_owner is not None
            and type(copy_owner) is not core.DisposableEnvironment
        ):
            raise PermissionError("SNAPSHOT_OWNED_COPY_ENVIRONMENT_REQUIRED")
        self.copy_owner = copy_owner
        self.root = copy_owner.root if copy_owner else ROOT.resolve()
        self.project = copy_owner.project if copy_owner else self.root
        self.runs = copy_owner.runs if copy_owner else ADMIN_RUN_ROOT
        self.queue = (
            copy_owner.queue if copy_owner else queue_path_for_run_root(self.runs)
        )
        self.journal = (
            self.project / "data/.fundamentals_admin_publication_journal.json"
            if copy_owner
            else journal.ACTIVE_JOURNAL_PATH
        )
        self.identity = copy_owner.identity if copy_owner else CONTRACT
        self.is_live = copy_owner is None
        self.configuration = configuration
        self.log_dir = (
            scheduler_log_dir if self.is_live else str(self.project / "scheduler_logs")
        )
        self.reentrant = scheduler_managed_locks
        self.operation_id = None
        self._stack = None
        self.check()

    def config(self):
        if self.is_live:
            from rawcandle.scheduler.config import read_scheduler_config

            cfg = read_scheduler_config(str(ROOT / "scheduler_config.json"))
            return {
                "route": cfg.fundamentals_refresh_route,
                "mode": cfg.fundamentals_refresh_mode,
                "ownership": cfg.pb_ownership_auto_continuation_enabled,
            }
        return dict(
            self.configuration
            or {"route": ROUTE, "mode": "FULL_WORKFLOW", "ownership": False}
        )

    def check(self):
        if self.copy_owner:
            self.copy_owner.check()
            core._trusted(self.journal, self.root)
            j = journal.load_journal(self.journal)
            if j:
                if (
                    j.get("publication_mode") != "GENERATION_POINTER"
                    or Path(j.get("active_generation_manifest_path", ""))
                    != self.project / "data/fundamentals_active_generation.json"
                ):
                    raise PermissionError("SNAPSHOT_JOURNAL_SCOPE_INVALID")
                for record in j["roles"].values():
                    for key in ("production_path", "backup_path", "candidate_path"):
                        core._trusted(record[key], self.root)
                from rawcandle.fundamentals.generations import _validate_generation_id

                _validate_generation_id(str(j.get("new_generation_id") or ""))
                _validate_generation_id(
                    str((j.get("old_generation") or {}).get("generation_id") or "")
                )
        else:
            if (
                self.root != ROOT.resolve()
                or self.project != self.root
                or self.runs != ADMIN_RUN_ROOT
                or self.journal != journal.ACTIVE_JOURNAL_PATH
                or self.queue != queue_path_for_run_root(ADMIN_RUN_ROOT)
            ):
                raise PermissionError("SNAPSHOT_PRODUCTION_PATH_OVERRIDE")
            for path in (self.root, self.runs, self.queue, self.journal):
                core._trusted(path, self.root)
            # Recovery uses the sole native live journal and native role paths.
            j = journal.load_journal(self.journal)
            if j and j.get("publication_mode") == "GENERATION_POINTER":
                if (
                    Path(j["active_generation_manifest_path"])
                    != self.root / "data/fundamentals_active_generation.json"
                ):
                    raise PermissionError("SNAPSHOT_JOURNAL_SCOPE_INVALID")
                for record in j["roles"].values():
                    for key in ("production_path", "backup_path", "candidate_path"):
                        core._trusted(record[key], self.root)
            binding = resolve_active_generation(self.project, require_generation=True)
            for p in binding.role_paths().values():
                core._trusted(p, self.root)
        return self

    def prepare_taxonomy_from(self, source):
        """Prepare a new owned-copy dependency without copying analysis.db."""
        self.check()
        if not self.copy_owner or type(source) is not SnapshotEnvironment:
            raise PermissionError("SNAPSHOT_OWNED_TAXONOMY_COPY_REQUIRED")
        source.check()
        destination = self.project / "data/analysis.db"
        core._trusted(destination, self.root)
        paths = source.paths()
        return sources.prepare_disposable_taxonomy_source(
            taxonomy_db=paths.taxonomy_db,
            canonical_db=paths.canonical_db,
            destination=destination,
            operation_id=f"{self.identity}:taxonomy-copy",
        )

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
        lock = self.project / "temp/.fundamentals_admin_production.lock"
        with production_lock(
            lock_path=lock,
            scheduler_log_dir=self.log_dir,
            allow_reentrant=self.reentrant,
        ):
            with ExitStack() as stack:
                self._stack = stack
                try:
                    paths = self.paths()
                    for role, p in paths.as_dict().items():
                        if role != "taxonomy":
                            _no_sidecars(p)
                    # Admin -> scheduler -> taxonomy -> SQLite. Reserve now;
                    # bind current semantic dependencies at prepare_sources.
                    stack.enter_context(sources.protected_direct_taxonomy_source(
                        paths.taxonomy_db,
                        paths.canonical_db,
                        operation_id=(self.operation_id or "snapshot-preflight") + ":taxonomy",
                        require_checkpointed=True,
                        bind_dependency=False,
                    ))
                    yield
                finally:
                    self._stack = None

    def dependency_binding(self, paths):
        return {
            r: sources._file_identity(paths.as_dict()[r])
            for r in ("market", "taxonomy")
        }

    def directory(self):
        if not self.operation_id or Path(self.operation_id).name != self.operation_id:
            raise ValueError("UPDATE_OPERATION_REQUIRED")
        return core._trusted(self.runs / self.operation_id, self.root)

    def request(self):
        request = core._read(
            core._trusted(self.directory() / "update_request.json", self.root)
        )
        core._verify(request)
        acquisition._validate_update_binding(request)
        if (
            request["update_run_id"] != self.operation_id
            or request["environment_identity"] != self.identity
        ):
            raise ValueError("UPDATE_OPERATION_OWNER_MISMATCH")
        if request["configuration"] != self.config() or self.config()["route"] != ROUTE:
            raise ValueError("UPDATE_CONFIGURATION_DRIFT")
        refresh_universe.require_binding(self.paths(), request)
        return request

    def require_update_snapshot(self, snapshot):
        request = self.request()
        if (
            snapshot._run.request.get("mode") != "UPDATE_FETCH"
            or snapshot._run.request.get("update_binding") != request
            or snapshot._run.operation_id != request["fetch_operation_id"]
            or snapshot.manifest["old_authority"] != request["old_authority"]
        ):
            raise PermissionError("ACQUISITION_ONLY_IS_NOT_UPDATE_AUTHORITY")
        refresh_universe.require_binding(self.paths(), request).require_tickers(
            {s['ticker'] for s in snapshot.iter_slots()})

    def validate_baseline(self, paths):
        # Legacy Preview's mandatory date prerequisite remains a financial gate.
        # OLD hashes subsequently bind the inspected baseline; no routine repair.
        audit = core.rules.audit_publish_date_bootstrap(paths)
        if not core.rules.publication_date_gate_authorized(audit):
            raise ValueError("UPDATE_PUBLICATION_DATE_PREREQUISITES")

    def update_inputs(self):
        request = self.request()
        acquisition._age([acquisition._time(request["created_at_utc"])], self.clock())
        sealed = core._read(
            core._trusted(self.directory() / "update_sources.json", self.root)
        )
        core._verify(sealed)
        if (
            sealed["update_run_id"] != self.operation_id
            or sha256_file(self.directory() / "discovery.json")
            != sealed["discovery_sha256"]
        ):
            raise ValueError("UPDATE_DISCOVERY_BINDING_MISMATCH")
        sec_snapshot.open_bundle(
            self.directory() / "sec",
            operation_id=self.operation_id,
            snapshot_reference=sealed["snapshot_reference"],
            expected=sealed["sec_manifest_sha256"],
        )
        return {
            "request": request["fingerprint"],
            "source_bundle": sealed["fingerprint"],
            "configuration": request["configuration"],
            "refresh_universe": request['refresh_universe'],
        }

    def sec_reader(self):
        sealed = core._read(self.directory() / "update_sources.json")
        return sec_snapshot.open_bundle(
            self.directory() / "sec",
            operation_id=self.operation_id,
            snapshot_reference=sealed["snapshot_reference"],
            expected=sealed["sec_manifest_sha256"],
        )[1]

    def verify_sec_scope(self, canonical, publication_dates):
        """Planning must cover the native actual scope; missing docs stay native unresolved."""
        manifest = core._read(self.directory() / "sec/manifest.json")
        with core.carry.readonly(canonical) as db:
            for key in publication_dates.get("quarter_keys", []):
                row = db.execute(
                    "SELECT q.period_end,c.cik_normalized FROM v4_quarter q JOIN company_cik c USING(company_id) WHERE q.company_id=? AND q.fiscal_year=? AND q.fiscal_quarter=? AND c.status='ACTIVE'",
                    key,
                ).fetchone()
                if row is None:
                    continue
                if not any(
                    str(p["cik"]) == str(row["cik_normalized"])
                    and p["from_calendar_date"] <= row["period_end"]
                    and (
                        date.fromisoformat(row["period_end"]) + timedelta(days=180)
                    ).isoformat()
                    <= p["to_calendar_date"]
                    for p in manifest["plan"]
                ):
                    raise ValueError("UPDATE_SEC_SCOPE_NOT_CAPTURED")

    def _taxonomy(self, canonical):
        if self._stack is None:
            raise PermissionError("UPDATE_TAXONOMY_WRITER_SCOPE_REQUIRED")
        # writer_lock already holds protected_direct_taxonomy_source through
        # postflight. Reuse its native owner instead of acquiring it a second time.
        return sources.bind_taxonomy_source(
            self.paths().taxonomy_db,
            canonical,
            mode=sources.TaxonomySourceMode.DIRECT_LOCKED_READ,
            operation_lock=current_taxonomy_operation_lock(),
        )

    def prepare_sources(self, paths, lane, canonical, as_of):
        native._storage_preflight(
            paths,
            temp_root=self.root / "temp",
            backup_root=self.root / "backups/fundamentals_admin_production",
        )
        binding = self._taxonomy(canonical)
        return builders.prepare_compact_read_only_sources(
            paths,
            lane_dir=lane,
            canonical_candidate=canonical,
            as_of_date=as_of,
            taxonomy_binding=binding,
        )

    def check_build_dependencies(self, build):
        canonical = Path(build["prepared"]["roles"]["canonical"])
        binding = self._taxonomy(canonical)
        old = build["dependency_copies"]["taxonomy"]["binding"]
        for key in (
            "source_path",
            "domain",
            "version",
            "semantic_fingerprint",
            "membership_rows",
        ):
            if getattr(binding, key) != old[key]:
                raise ValueError("UPDATE_TAXONOMY_DRIFT")
        sources.validate_stable_read_only_source_bundle(
            sources.StableReadOnlySourceBundle(
                market_db=Path(build["read_only_sources"]["market"]),
                manifest_path=Path(
                    build["dependency_copies"]["market"]["manifest_path"]
                ),
                manifest=build["dependency_copies"]["market"]["bundle_manifest"],
                extraction_seconds=build["dependency_copies"]["market"][
                    "bundle_build_seconds"
                ],
            )
        )

    def grant_publication(self, receipt, *, confirmed):
        if confirmed is not True:
            raise PermissionError("EXPLICIT_SNAPSHOT_PUBLICATION_INTENT_REQUIRED")
        self.request()
        self.update_inputs()
        grant = core._seal(
            {
                "update_run_id": self.operation_id,
                "validation_fingerprint": receipt["fingerprint"],
                "candidate_generation_id": receipt["candidate_generation_id"],
                "snapshot_reference": receipt["snapshot_reference"],
                "inputs": receipt["inputs"],
                "confirmation": CONFIRM,
            }
        )
        core._write(self.directory() / "publication_authorization.json", grant)
        return grant

    def publication_authority(self, receipt):
        request = self.request()
        grant = core._read(
            core._trusted(
                self.directory() / "publication_authorization.json", self.root
            )
        )
        core._verify(grant)
        if (
            grant["confirmation"] != CONFIRM
            or grant["update_run_id"] != self.operation_id
            or grant["validation_fingerprint"] != receipt["fingerprint"]
            or grant["candidate_generation_id"] != receipt["candidate_generation_id"]
            or grant["snapshot_reference"] != receipt["snapshot_reference"]
            or grant["inputs"] != receipt["inputs"]
        ):
            raise PermissionError("UPDATE_PUBLICATION_AUTHORITY_MISMATCH")
        native._storage_preflight(
            self.paths(),
            temp_root=self.root / "temp",
            backup_root=self.root / "backups/fundamentals_admin_production",
        )
        return {
            "contract": core.CONTRACT,
            "update_contract": CONTRACT,
            "update_run_id": self.operation_id,
            "snapshot_reference": receipt["snapshot_reference"],
            "validation_fingerprint": receipt["fingerprint"],
            "scope": "PRODUCTION_UPDATE" if self.is_live else "OWNED_COPY_UPDATE",
            "authorization_fingerprint": grant["fingerprint"],
            "explicit_confirmation": CONFIRM,
        }
