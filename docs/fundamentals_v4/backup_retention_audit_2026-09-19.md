# RawCandle Backup Retention Audit - 2026-09-19

Scope: the complete `backups/` tree, active Fundamentals backup/restore code, and representative SQLite metadata. All sizes below are logical file sizes. GB is decimal; GiB is binary. Timestamps in the CSV inventories are UTC filesystem modification times, with the timestamp encoded in a path recorded separately where present.

No backup file was deleted, moved, renamed, compressed, or restored, and no backup database content was changed. One read-only SQLite probe opened the existing Phase 10C1 WAL/SHM set and caused the 32 KiB `-shm` sidecar's filesystem mtime to advance. Its original nanosecond mtime, captured in the pre-probe inventory, was restored. This metadata touch is disclosed because the stricter statement that no backup file was touched would be inaccurate.

## Current backup footprint

The tree contains **98 files and 97.764 GB (91.050 GiB)**. Every file is assigned exactly once between the proposed-deletion CSV (66 files) and keep CSV (32 files).

Largest families:

| Backup family | Files | Size (GB) | Interpretation |
| --- | ---: | ---: | --- |
| Phase 13F structural production activation | 32 | 24.962 | Eight four-file sets; seven database triples are exact duplicates of the retained final set. |
| Phase 13C multi-database transition | 7 | 15.738 | Broad provider/canonical/analysis/taxonomy/market transition milestone. |
| Phase 10C1 taxonomy analysis snapshot | 3 | 10.407 | One large historical `analysis.db` plus empty WAL and small SHM sidecars. |
| Fundamentals Administration production rollback | 11 | 9.925 | Five recent operations; this is the active, continuing backup family. |
| Phase 13E SNDK production onboarding | 12 | 9.283 | Three four-file attempts; role databases are exact duplicates. |
| Non-Fundamentals or mixed May families | 8 | 9.370 | Four owner-ambiguous enrichment/dashboard/scheduler groups. |

Size by database/object type:

| Type | Files | Size (GB) |
| --- | ---: | ---: |
| `fundamentals_analysis` | 33 | 37.867 |
| `analysis` / taxonomy | 5 | 30.448 |
| `fundamentals_provider` | 18 | 15.917 |
| `fundamentals_v4` canonical | 20 | 11.557 |
| `osakedata` | 1 | 1.971 |
| `ecosystem_dashboard` | 3 | 0.003 |
| JSON/configuration, sidecars, and other small objects | 18 | 0.0002 |

Age distribution as of 2026-09-19:

| Age | Files | Size (GB) |
| --- | ---: | ---: |
| < 7 days | 59 | 47.318 |
| 7-30 days | 31 | 41.076 |
| 31-90 days | 0 | 0 |
| 91-180 days | 8 | 9.370 |
| > 180 days | 0 | 0 |

Representative read-only SQLite inspection found:

- The earliest Phase 2D analysis copy passes `PRAGMA quick_check`, has 6 tables, and reports schema `v4_1a_prototype`.
- The 10.407 GB Phase 10C1 `analysis.db` has 51 tables, including `dc_ecosystem_membership`, `ec_taxonomy_version`, and taxonomy reporting tables. A full check was stopped as unjustified for this superseded large copy; the associated read-only open caused the disclosed `-shm` mtime touch, which was restored from the pre-probe inventory.
- Phase 13F manifests report `quick_check=ok`, schema fingerprints, row counts, and SHA-256 for all roles.
- The newest Administration provider, canonical, and analysis rollback files all pass `PRAGMA quick_check`. Provider/canonical report `v4_6a2_operating_working_capital`; analysis reports the same schema family and active `OPERATING_INCOME_MODEL_FAMILY_V2`.

## Backup-generating code

The active producer is `rawcandle/fundamentals/admin/production_transaction.py`. It uses SQLite online backup after production locks, source validation, matching copy-test validation, and storage preflight, but before source mutation or atomic analysis publication. `_restore_all` verifies the stored SHA-256, stages a copy on the target filesystem, atomically replaces the target, fsyncs it, and validates the restored database.

The active role contract in `rawcandle/fundamentals/admin/production_operations.py` is:

| Workflow | Backup write set | Backup location |
| --- | --- | --- |
| Add Tickers | provider, canonical, analysis | `backups/fundamentals_admin_production/<run_id>/` |
| Sector/Industry synchronization | analysis only | same |
| Taxonomy synchronization | analysis only | same |

No active retention, expiry, count limit, or automatic deletion was found. Consequently, every successful writing Administration run can add another full write-set backup indefinitely. The old Phase 13G Add Tickers backup helper and path constant remain in `batch_add_tickers.py`, along with restore-rehearsal code, but no active call to its `_backup_write_set` was found; current production routes through the shared transaction. Older Phase 11D/12C/13D modules also contain phase-specific creation or restore code, but their historical paths are not produced by the current unified Administration route.

`fundamentals_admin_production` is therefore the primary source of **future** growth, although repeated Phase 13F sets are the largest existing redundant family. Its five observed sets total 9.925 GB. The three current-architecture Add Tickers sets average about 2.484 GB each; an analysis-only backup is currently about 0.9 GB. At one Add Tickers run per week, Add Tickers alone would add roughly 129 GB/year; daily use would add roughly 907 GB/year. One weekly analysis-only synchronization would add another roughly 47 GB/year. The observed 9.925 GB burst over two calendar days is too short and irregular to annualize as a reliable point estimate.

## Backup classification

| Classification | Files | Size (GB) | Treatment |
| --- | ---: | ---: | --- |
| CURRENT_ROLLBACK | 3 | 2.492 | Keep newest complete Administration triple. |
| MILESTONE_BACKUP | 16 | 27.575 | Keep selected production/schema milestones. |
| REDUNDANT_ROLLBACK | 33 | 32.989 | Delete candidate after explicit approval. |
| LEGACY_ARCHITECTURE | 22 | 25.338 | Delete candidate after explicit approval. |
| DEVELOPMENT_OR_REHEARSAL | 0 | 0 | No file required this classification on available evidence. |
| EVIDENCE_OR_METADATA | 16 | 0.0002 | Five follow retained sets; eleven follow proposed-deletion sets. |
| AMBIGUOUS | 8 | 9.370 | Keep pending a separate owner review. |

Classification is not based on age alone. Phase 13E and 13F duplication is proven by their manifests: R2/R3/R4 have identical role-level SHA-256 values, and all eight Phase 13F database triples have identical role-level SHA-256 values. Same-sized Administration backups were **not** called exact duplicates because those directories have no local manifest and their sizes differ.

## Largest sources of unnecessary storage

| Candidate family | Files | Reclaimable (GB) | Evidence |
| --- | ---: | ---: | --- |
| Seven superseded Phase 13F sets | 28 | 21.842 | Exact role-level manifest hashes match retained Phase 13F4.13. |
| Phase 10C1 taxonomy analysis snapshot | 3 | 10.407 | Historical pre-current source snapshot; broader Phase 13C milestone retained. |
| Two superseded Phase 13E attempts | 8 | 6.189 | Exact role-level manifest hashes match retained R4. |
| Two older same-day Administration triples | 6 | 4.958 | Newer complete Add Tickers triple retained. |
| Phase 9E, 10C, 11D, and 12E transitions | 13 | 12.107 | Superseded phase-specific copies; later selected milestones retained. |

## Proposed retention policy

Use a small rule set tied to complete logical backup sets:

1. Keep every successful current-architecture production rollback set for 14 days.
2. From days 15-30, keep the newest verified set for each workflow: Add Tickers, Sector/Industry, and Taxonomy. Delete older superseded routine sets only after confirming a newer complete set and its run evidence.
3. After 30 days, keep at most one current-architecture analysis rollback per calendar month for 12 months. Keep a provider/canonical/analysis triple only when that operation actually wrote all three roles.
4. Keep explicitly named architecture or production milestones indefinitely until a manual architecture review retires them. Manifests and sidecars follow their parent set; never split a retained set casually.
5. Delete failed, rehearsal, or abandoned temporary backup sets after 7 days once their failure evidence is retained elsewhere. Delete legacy phase backups after a later compatible milestone has been confirmed.
6. Never auto-delete `AMBIGUOUS` material. Require an owner decision first.

Implementing these rules later can be a simple post-success pruning command over complete run directories. It does not require a backup catalog or new lineage system. The command should default to dry-run, refuse partial-set deletion, and print bytes and paths before requiring explicit approval.

## Proposed deletions

The proposed-deletion inventory contains **66 files totaling 58.327 GB (54.321 GiB)**. Its oldest filesystem timestamp is `2026-09-01T12:23:51.463858Z`; its newest is `2026-09-19T09:30:45.421415Z`. The newest candidates are superseded same-day Administration rollback files, illustrating why age alone is not the criterion.

Candidates comprise 33 redundant rollback database files (32.989 GB), 22 legacy architecture database files (25.338 GB), and 11 tiny manifests/sidecars that belong to those candidate sets. Every row is explicitly marked `DELETE_CANDIDATE`; the CSV is a plan, not an executable deletion script.

## Backups to retain

The keep inventory contains **32 files totaling 39.437 GB (36.729 GiB)**:

- The newest complete Administration Add Tickers provider/canonical/analysis rollback triple.
- Two recent active-architecture analysis milestones: taxonomy synchronization and final V2-only publication.
- One selected Phase 13G Add Tickers production milestone.
- The final Phase 13F durable structural activation and final Phase 13E SNDK onboarding sets, including their manifests.
- The broad Phase 13C multi-database transition milestone, preserving the last selected cross-domain historical baseline.
- Eight ambiguous non-Fundamentals or mixed files pending owner review.

This retains a current operational rollback, recent V2-only analysis states, representative exact copies for duplicated production families, and a broad historical transition point. The 39.437 GB estimate is intentionally conservative because all ambiguous material remains.

## Ambiguous items

Eight files in four May 2026 families, totaling 9.370 GB, need explicit review outside the Fundamentals cleanup:

- `backups/manual_enrichment_20260527T114407Z/`
- `backups/scheduler_switch_20260529T110757Z/`
- `backups/dashboard_prod_write_20260529T134917Z/`
- `backups/scheduler_config_reports_reference_20260529T150609Z/`

Their names point to enrichment, dashboard, or scheduler changes, not a retired Fundamentals phase. They may protect active non-Fundamentals data or configuration, so this audit recommends `KEEP_AMBIGUOUS` and makes no deletion claim about them.

## Risk assessment

The main deletion risk is loss of fine-grained rollback points between historical phases. That risk is reduced by retaining the current complete Administration set, selected recent V2 milestones, one exact representative of each duplicated Phase 13E/13F family, the Phase 13G production set, and the broad Phase 13C transition set. Exact manifest hashes make deletion of duplicate Phase 13E/13F copies low risk.

Legacy phase backups may remain useful for forensic comparison even when they are not practical current-runtime restores. Before a future cleanup, archive the two CSVs and this report in Git, re-check that the selected keep paths still exist, verify the newest current rollback again, and ensure no production operation is running. Delete complete listed sets only; do not infer additional candidates from wildcards. Ambiguous families must remain untouched.

## Recommendation

Approve a separate, explicitly scoped cleanup using only `backup_retention_proposed_deletions_2026-09-19.csv` as the reviewed allowlist. First perform a dry-run that revalidates path, size, and complete-set membership; then delete only the 66 approved candidates and report actual reclaimed bytes. Separately assign an owner to the four ambiguous May families. Add the simple 14-day/30-day/monthly retention pruning rule to the active Administration transaction in a later implementation task.
