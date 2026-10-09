# P1.8 — P1.7 run acceptance blocked; backups retained

Selected run: `publication_drain_20261009T175136Z_e99387cf`. Acceptance result: **FAIL / NOT_ELIGIBLE**. **No backup was deleted and no acceptance state was recorded.** The existing contract does not support this publication-drain report shape; P1.8 requires stopping rather than manually deleting backups or changing source.

## Existing mechanism and failed gate

Inspected `FundamentalsAdminUIService.accept_run_and_cleanup_backups` and its existing `run_acceptance_cleanup.inspect_cleanup_eligibility` / `accept_run_and_cleanup_backups` implementation. No cleanup/delete function was called. The read-only eligibility checks returned:

- Default Admin UI run root (`fundamental_reports/admin_runs`): `NOT_ELIGIBLE`, reason `CLEANUP_RUN_DIRECTORY_INVALID`; this selected operation is stored under `fundamental_reports/publication_drains`.
- Explicit selected publication-drain report root, with current active role paths: `NOT_ELIGIBLE`, reason **`Run is not a Production update`**. The required `mode=PRODUCTION_APPLY` field is absent.

The publication-drain result uses `apply=true`, `status=SUCCESS`, `journal_state=COMPLETED`; the acceptance implementation requires `mode=PRODUCTION_APPLY`, `outcome=COMPLETED` and publication/postflight evidence in its expected result schema. It also obtains immutable-generation source ownership from an embedded `journal`, which this report does not contain. These are contract integration gaps, not a failed P1.7 publication. No report was rewritten or wrapped to bypass the gate. The inspector’s zero backup count on rejection is not an inventory count; the actual inventory below remains three files.

## Current and selected-run state

Inspected HEAD: `13de79ae0d51d9e5e4991e33ec4ba26ae55cd6b0`; checked at `2026-10-09T19:22:07.561032+00:00`. Current active generation before and after: `publication_drain_20261009T175136Z_e99387cf`. Manifest fingerprint: `ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a`. Production had not advanced past P1.7; no historical-active-generation exception was needed or invented.

Selected run terminal evidence: `COMPLETED`; postflight: `PASSED`; activation: `ACTIVATED_AND_VERIFIED`; rollback/recovery: `NOT_REQUIRED`. The current terminal journal belongs to this selected run and agrees with the successful operation result and published generation. All three active DB and backup SQLite quick checks passed with zero foreign-key errors. Selected published role hashes match the operation postflight. Backup ownership is explicitly bound by each recorded role/source/path/hash/size to the OLD generation; exact inventory contains only the three expected files, with no symlinks or unexpected entries.

OLD generation retained: `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. Published P1.7 generation retained: `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf`. Neither generation nor the active pointer was modified.

Provider watermark: `2026-10-08`; latest successful normal refresh: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`, completed `2026-10-09T04:27:27Z`. Watermark unchanged.

## Exact retained backup allowlist

| Role | Exact path | Bytes | Verified SHA-256 |
|---|---|---:|---|
| analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/analysis.db` | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/canonical.db` | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| provider | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/provider.db` | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |

Before: **3 files / 2,627,518,464 bytes**. Deleted: **0 files / 0 bytes**. Remaining: **3 files / 2,627,518,464 bytes**. The selected directory remains intact. Backup hashes match recorded P1.7 evidence.

## Protected-state verification

Before/after hashes and sizes match for active provider/canonical/analysis roles, active manifest, terminal journal, Review Queue (including existing WAL/SHM), scheduler configurations, operation result, proposal, approval, durable handoff and semantic reference, immutable plan, execution authorization receipt and P1.7 report/result CSV. Canonical byte identity proves publication authority and financial state unchanged. Recursive filesystem metadata inventories restricted to the backup and immutable-generation roots match before/after; no other backup directory, generation or unrelated runtime artifact was deleted.

| Active/protected core artifact | SHA-256 before and after |
|---|---|
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf/fundamentals_provider.db` | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf/fundamentals_v4.db` | `a67c996aadfaa7e600b88d6d9e31804bb30a784b182ff37ae23c8756ff949c34` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf/fundamentals_analysis.db` | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| `/home/kalle/projects/rawcandle/data/fundamentals_active_generation.json` | `73cdace134b7d33069cf5b7f1e7dfe283ae5348a2b52742297102838eb1253aa` |
| `/home/kalle/projects/rawcandle/data/.fundamentals_admin_publication_journal.json` | `a45cf8349978c76cd1f5e1cb82b24e13e008f463a48d865d5ee2484beba4a3f8` |
| `/home/kalle/projects/rawcandle/fundamental_reports/fundamentals_refresh_review_queue.db` | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| `/home/kalle/projects/rawcandle/scheduler_config.json` | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| `/home/kalle/projects/rawcandle/forecast_scheduler_config.json` | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |
| `/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/result.json` | `afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1` |

[Existing operation report](/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/result.json) remains available and byte-identical. P1.7 audit artifacts and its publication operation record are preserved. No Admin Run History record for this selected ID exists under the default Admin root; this task did not create, hide or remove one. Runtime acceptance evidence `backup_cleanup.json` was not created because eligibility failed.

Full test suite: **NOT RUN**. Pytest: **NOT RUN**. Source changes: **NONE**. Only read-only runtime validation and the requested acceptance document were produced.

## Required follow-up

A separate implementation phase is needed to integrate publication-drain run discovery and its successful generation/journal evidence with the existing Admin acceptance contract, including tested exact backup ownership, clean-journal and integrity gates. This runtime task does not implement that adapter, normalize historical run evidence, weaken gates or manually remove files. Retry the existing acceptance action only after that integration is implemented and reviewed.

Acceptance remains blocked; all three rollback backups are intact. Nothing was pushed.
