# Phase 13G.2.5F: Final V2-Only Production Publication

## 1. Outcome

`SUCCESS / APPLIED`

On 2026-09-19, a brand-new final-schema V2 analysis database replaced
`data/fundamentals_analysis.db` atomically. The production write scope was that
database only. No provider, canonical, market, taxonomy, or `ticker_meta` data
was modified. Rollback was not required.

**Fundamentals V1 retirement is complete.**

## 2. Repository And Scheduler Preflight

- Branch: `chore/ignore-backups`.
- Required and pushed baseline: `a28e03ffc68ae4373e216d4132c926d209ecc77a`.
- Worktree before production: clean.
- Free space: 644,629,823,488 bytes; calculated requirement: 4,461,281,280 bytes.
- Scheduler before maintenance: service `inactive (dead)`, timer
  `active (waiting)` and enabled, next run 2026-09-20 05:30 EEST.
- Maintenance state: service and timer `inactive`; no child writer remained;
  Administration and scheduler kernel locks were available and then held for
  backup, rebuild, replacement, and postflight.

## 3. Preview And Test On Copies

- Preview fingerprint: `cdff3eaaa20229992c7d709b240e55d97b36eadbc34bfeb7d5ac1eba57c033e9`.
- Test run: `20260919T_phase13g25f_test_on_copies`.
- Explicit as-of date: `2026-09-18`, the last completed market day.
- Test outcome: `COMPLETED`; B1 gate: `READY`.
- Test candidate SHA-256: `b21c27ec9b26b1f768f17840647eda33817eb82ec1ae4c8729131d97a3499cb6`.
- Test candidate size: 892,231,680 bytes.
- Quick check: `ok`; foreign-key violations: zero.
- Active readers and NVDA, AMZN, SNDK, and IA V2 Snapshots succeeded.
- Retired V1 objects and non-V2 result/pointer state were absent.

The first wrapper-level revalidation stopped after B1 READY because a relative
candidate path was not absolute. The one-off `/tmp` runner was corrected and
resumed against the same untouched READY candidate. This was a tooling-path
error before production, not a rebuild or database failure.

## 4. Bound Source State

The Preview, Test, production candidate, and final source recheck used the same
state:

- provider SHA-256: `b79948a094cff6362488e1ce6f90406b125606d4c3f2d66ddd3c010ab3d58e01`;
- canonical SHA-256: `31613bde3be6cf22a218ea36f2c98424a6e4c3bf99b08b6858ceb31fc5c5b974`;
- market SHA-256: `2eccf0909c2859c545d8f85703bd688bafedfc3f1d06ff03b3898d342d2ff60f`;
- taxonomy database SHA-256: `c7625e289a649ee153d8734722af7c11e087efe97ad50d7647eb7d6b05d47e87`;
- pre-publication analysis SHA-256: `7ed45dd8e8ae902d66022d3dcdbfc1b9140c2a7710391f2f5046738c817782b7`.

The active taxonomy was `dc_ecosystem` / `DC_TAXONOMY_FULL_V2_1` with semantic
fingerprint `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`,
350 membership rows, 225 mapped companies, and 32 unresolved tickers.

## 5. Verified Rollback Backup

Immediate Phase F rollback point:

`backups/fundamentals_admin_production/20260919T_phase13g25f_final_v2_publication/analysis.db`

- Size: 892,256,256 bytes.
- SHA-256: `b3ec035c4fb4c0ca179ba518e7477d45c54a3e5dbb936a0478f836155b04ada7`.
- SQLite quick check: `ok`.
- Foreign-key check: `ok`.

The Phase C backup under
`20260918T182639Z_check_update_taxonomy_293c901ce1dd_production_12a72eb2`
was not modified or deleted.

## 6. Candidate And Atomic Replacement

The production candidate was rebuilt independently from the authoritative
read-only sources on the production filesystem. It matched the Test candidate's
seven economic component fingerprints. After the final source recheck, fsync,
`os.replace`, and directory fsync succeeded on the same filesystem.

- Production run: `20260919T_phase13g25f_final_v2_publication`.
- Published SHA-256: `eaab1d962e95434fdd8fdb406817a2ece8e3cb33959918c3968c965f34b1a594`.
- Published size: 892,231,680 bytes.
- Replacement status: `REPLACED`.

## 7. Production Postflight

The actual production path was reopened and passed:

- SQLite quick check and foreign-key check;
- active V2 family and current package validation;
- Score, Lifecycle, Valuation, Delta, Diagnostics, RP V2, and RV readers;
- current RP V2 pointer and exact taxonomy dependency;
- RV source recomputation and result verification;
- V2 Snapshot smoke;
- final-schema inventory and production SHA verification.

The package economic fingerprint is
`f377ebd50789b2f9ed6d7932528fb8c2faeb7f779a35ab03dea9cad27026980c`
and physical fingerprint is
`40787b540b7763a3a5cceb2f5c797b998a0a918c9c900e260ff6ec60ddf28a66`.

## 8. Current Production Metrics

- Score: 87,860 rows; FULL 63,439, LIMITED 14,995, NOT_READY 9,426.
- Lifecycle: 87,860 rows; READY 70,719, NOT_READY 17,141.
- Valuation: 87,860 rows; FULL 67,514, NOT_APPLICABLE 5,495,
  NOT_READY 14,851.
- Delta: 87,860 endpoints and 615,020 components.
- Diagnostics: 87,860 endpoints and 702,880 evaluations.
- RP V2: 13,799 results; Sector 4,460, Industry 4,460, Ecosystem 419,
  Universe 4,460; READY 13,199 and peer-group-too-small 600.
- RV: 2,444 companies; FULL 2,249, NOT_APPLICABLE 138, NOT_READY 57.
- RV input fingerprint:
  `7631d5d3a1eae2137d444d89bc325a5d12c482b285f43d3d0ae572a9001bfad9`.
- RV source fingerprint:
  `ff36b9874c33ed5a9e40b32cfffe905aed798d48723bb055a00d8ae5f6a48188`.
- RV result fingerprint:
  `c4caee88e63ec378ecba3341f621ced844baa5daa6daa3440014ff57c085c8a9`.

## 9. Semantic Comparison

Pre-publication and fresh candidate Score, Lifecycle, Valuation, Delta,
Diagnostics, RP counts/statuses, package economic fingerprint, package physical
fingerprint, and RP scope counts matched. Current source-driven RV legitimately
changed from stale source/result fingerprints `68c7ccd4...c9c` /
`38bad694...c94` to the validated values above. One RV company moved from FULL
to NOT_READY. This is the expected current-market-source rebuild result.

NVDA, AMZN, SNDK, and IA Snapshot business semantics matched. Only
`source_state_audit_v2` changed because the physical analysis database identity
and current RV publication changed.

## 10. Final V2-Only Schema

Confirmed absent in production:

- `lifecycle_result`;
- `valuation_result`;
- `idx_lifecycle_result_company_quarter`;
- `idx_valuation_result_company_quarter`;
- `operating_income_v2_package_manifest_history`;
- RP V1 active pointer/result/snapshot state;
- Score V1 and Valuation V1 result state.

Confirmed present and valid include `analysis_model_run`, current V2 package and
family state, revised Score/Lifecycle/Valuation/Delta/Diagnostics storage, RP V2
snapshot/pointer/taxonomy dependency, and active RV state. Fresh bootstrap now
produces the exact production schema. Current RV's model-version suffix `V1` is
the live Relative Valuation contract and is unrelated to retired Fundamentals
V1 or RP V1.

## 11. Runtime And Administration Closure

No active Fundamentals V1 calculation engine, writer, reader, CLI, Admin route,
scheduler route, default, or fallback remains. Administration remains V2-only:

- Add Tickers performs its source work and then a full V2 + RP V2 + RV rebuild.
- Sector/Industry reads authoritative `ticker_meta` read-only and performs the
  same full rebuild; it does not edit classifications.
- Taxonomy reads the already active `analysis.db.dc_ecosystem` and performs the
  same full rebuild.
- The active Taxonomy Administration route rejects taxonomy CSV input.
- Repair or unclear state uses the same canonical fresh rebuild path.

## 12. Tests

Post-publication targeted suite:

```text
python3 -m pytest -q \
  tests/test_fundamentals_v4_full_rebuild.py \
  tests/test_fundamentals_v4_production_bootstrap.py \
  tests/test_fundamentals_v4_operating_income_v2.py \
  tests/test_fundamentals_v4_operating_income_v2_persistence.py \
  tests/test_fundamentals_v4_operating_income_v2_current_sources.py \
  tests/test_fundamentals_v4_company_snapshot_phase9f.py \
  tests/test_fundamentals_v4_relative_valuation_engine.py \
  tests/test_fundamentals_v4_relative_valuation_source.py \
  tests/test_fundamentals_v4_relative_valuation_persistence.py \
  tests/test_fundamentals_v4_relative_valuation_production.py \
  tests/test_fundamentals_admin_full_v2_downstream.py \
  tests/test_fundamentals_admin_production_transaction.py \
  tests/test_fundamentals_admin_batch_add_tickers.py \
  tests/test_fundamentals_admin_sector_industry.py \
  tests/test_fundamentals_admin_taxonomy.py \
  tests/test_fundamentals_admin_taxonomy_production.py \
  tests/test_fundamentals_admin_ui.py
```

Final result: 283 passed, 0 skipped/deselected, 0 failed in 195.06 seconds.
The first run exposed one brittle synthetic date assertion after current RV made
its as-of and current-price dates equal. The fixture was corrected; the focused
test passed and the complete suite then passed. Production SHA remained
unchanged through testing. `git diff --check` passed.

## 13. Cleanup And Retention

The 892,231,680-byte Test-on-copies database was deleted after its complete
result, schema inventory, fingerprints, events, and Snapshot evidence were
persisted. Production staging was consumed by atomic replacement and no large
Phase F candidate remained. Preview, result JSON, event log, rebuild report,
fingerprints, and documentation remain as lightweight evidence.

Retain the Phase F backup as the immediate rollback point. Retain the Phase C
backup through at least the next successful scheduled cycle or the normal
confidence period. Remove older redundant backups later through normal backup
policy, not as part of V1 retirement.

The scheduler was restored to its observed starting state: service
`inactive (dead)`, timer `active (waiting)` and enabled, with the next run shown
for 2026-09-20 at 05:30 EEST. No immediate scheduler run was triggered.

## 14. Remaining Issue And Closure

The 32 unresolved taxonomy identities remain a separate non-V1 issue. Phase F
did not change taxonomy, `ticker_meta`, provider/canonical schemas, RV design,
or scheduler design.

No additional V1 phase is recommended unless new evidence appears. Future work
must be scoped separately from V1 retirement.
