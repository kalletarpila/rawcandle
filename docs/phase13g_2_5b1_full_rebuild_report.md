# Phase 13G.2.5B1 - Full V2 analysis rebuild

## Outcome and architecture

Succeeded on production-shaped, phase-owned databases. A brand-new `fundamentals_analysis.db` can be bootstrapped from the existing schema and filled from provider, canonical V4, market (`ticker_meta`) and active `analysis.db` taxonomy sources. The prior analysis DB is neither copied nor read by the rebuild. The path is `operating_income_v2.full_rebuild.rebuild_v2_analysis(target, sources, as_of_date, output)`. It rejects an existing target, the production analysis target and use of the production analysis DB as a source. It does not replace production or change Administration routing.

The path bootstraps the base analysis schema and existing Lifecycle, Valuation, Delta, Diagnostics, RP, V2 package and RV schemas. It calculates Score, Lifecycle, Valuation, Delta, eight-flag Diagnostics and RP with `phase10b.calculate(..., verify_v1_overlap=False, as_of_date=...)`, publishes the V2 package, activates the current V2 family and then calculates/publishes RV from that fresh database. The current package manifest, active V2 family, RP snapshot/dependency and RV active pointer are current-state metadata; no component publication history or RP-only mode was added. The DB contains no V1 result rows or pointers. V1-capable shared schema remains for later retirement.

The V2 Snapshot reader previously constructed a full V1 snapshot first and therefore demanded a V1 Delta package. It now requests a canonical/identity-only scaffold, then resolves V2 components as before. The V1 Snapshot call path retains its original behavior. The RV source reader now excludes Valuation and RP SQLite surrogate row IDs, as it already excluded snapshot IDs and calculation timestamps; these storage identities are not economic inputs.

## Source and V1 boundaries

- Score: canonical V4 TTM and market split history; V2 score arithmetic.
- Lifecycle/Delta/Diagnostics: calculated V2 package inputs from canonical V4, V2 Score and Valuation. Existing wrappers still import legacy engines/types and shared table persistence, but read no persisted V1 result state.
- Valuation: canonical V4 fundamentals/shares, source-date market prices and current `osakedata.db.ticker_meta` Sector/Industry.
- RP: newly calculated V2 Score/Valuation, current `ticker_meta`, and active `analysis.db.dc_ecosystem` taxonomy.
- RV: freshly persisted and activated V2 Valuation/RP, plus canonical/provider/market/taxonomy sources.

Remaining implementation-code imports are V1 Lifecycle, Valuation, Delta and RP engines, and shared Delta/Diagnostics persistence. These are code-retirement work, not old-analysis calculation authority. The active Add Tickers path still calls RP V1 and is unchanged in this phase.

## Independent fresh rehearsals

Both `temp/phase13g25b1_final_a/` and `temp/phase13g25b1_final_b/` were built from separate empty DB files using `as_of_date=2026-09-18`. Each returned `READY` after V2/RV publication and validation. Results, durable events and per-run `operation_report.md` are retained in those directories; the large scratch DB files are removed after closure.

| Measure | Rebuild A | Rebuild B |
| --- | --- | --- |
| Score / Lifecycle / Valuation / Delta / Diagnostics endpoints | 87,860 each | 87,860 each |
| Delta components | 615,020 | 615,020 |
| Diagnostic evaluations | 702,880 | 702,880 |
| RP results / coverage | 13,799 / 19,696 | 13,799 / 19,696 |
| RV inputs / companies | 2,444 / 2,444 | 2,444 / 2,444 |
| V2 package economic fingerprint | `f377ebd50789b2f9ed6d7932528fb8c2faeb7f779a35ab03dea9cad27026980c` | identical |
| V2 package physical fingerprint | `40787b540b7763a3a5cceb2f5c797b998a0a918c9c900e260ff6ec60ddf28a66` | identical |
| RP snapshot | `40595b1b66c784a7ebda47f1aa5e61c437d26970d26b6d5b2a923cf4283bf9a7` | identical |
| RV source / result fingerprint | `68c7ccd463e096335cfa2849a423d750346f20e5fd805a5573ee6a73ebd99c9c` / `38bad6944e6272052b3f14ea4fde17579e189ada5a13c306f0199eb3eca1cc94` | identical |
| RV active snapshot | `42d59f1e8e31b29d7dfc711ce9f2aad1232659f48a68495403ee6d3d8d21e320` | identical |

In each rebuild, Score statuses are FULL 63,439, LIMITED 14,995, NOT_READY 9,426; Valuation statuses are FULL 67,514, NOT_APPLICABLE 5,495, NOT_READY 14,851; Lifecycle statuses are READY 70,719 and NOT_READY 17,141. RP has 13,199 ready and 600 small-peer-group results. RV has 2,250 FULL, 138 NOT_APPLICABLE and 56 NOT_READY companies, with 9,776 peer rows, 2,444 own-history rows and 7,332 component rows.

All seven V2 calculation-layer fingerprints, taxonomy dependency, row counts, package fingerprints, RP and RV snapshot IDs, and RV source/result fingerprints matched A against B. The only intentionally different values are target paths and run/event timestamps. `PRAGMA quick_check=ok`, foreign-key check empty; active V2, RV and V2 Snapshot readers succeeded. The fresh Snapshot sample was `A` (20 reconciliation checks).
The `A` Snapshot also had identical report source state, Score value/status, RP rows and reconciliation results across the two rebuilds.

The V2 package economic fingerprint, seven calculation-layer fingerprints, row counts and RP snapshot match the accepted 13G.2.5A corrected copy at the same date. Package physical fingerprint differs from the old production-copy run because the fresh DB has different storage row IDs. The old 13G.2.5A RV *source-loader* fingerprint was `b256f99f72042261ba75d9e4d11aede3b4448cf04ec166e48d5d11d133c8e94b`, with 2,444 inputs; the new source-loader fingerprint is `0c4be743958c5c52a4de5877a30fa3af2d7f7e87a2b505835e7e14955976cba1`, also with 2,444 inputs. That fingerprint deliberately changed because the loader no longer includes non-semantic SQLite Valuation/RP row IDs. The accepted phase did not publish a corrected RV snapshot, so there is no prior corrected RV result fingerprint to compare. The new RV result is deterministic across independent fresh builds.

## RP taxonomy and validation

The RP dependency is `dc_ecosystem`, version `DC_TAXONOMY_FULL_V2_1`, semantic fingerprint `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`. There are 350 active membership rows and 225 mapped companies. The 32 unresolved tickers are recorded in each result's `taxonomy_dependency.unmapped_tickers`; their unresolved memberships are excluded by the existing identity contract. They did not block the valid rebuild. CORE/EXTENDED remain eligible, WATCH_ONLY excluded, and multiple eligible memberships deduplicate to the Datacenter group. No identity or taxonomy data was changed.

`validate_rebuild` requires the active Phase 10B V2 package, matching physical package fingerprint, exact RP date and taxonomy dependency rechecked against the still-active source taxonomy, active RV on the same date, recomputed RV source and result fingerprints from the fresh DB, V2-only result models, no legacy result rows or RP pointer, working active V2 and V2 Snapshot readers, `quick_check=ok` and no foreign-key violations. A candidate is `READY` only after this gate. A controlled post-bootstrap Valuation failure produced `FAILED` artifacts and a disposable target. A separate copied candidate with a tampered active RV source fingerprint failed the gate with `V2_REBUILD_RV_SOURCE_OR_RESULT_MISMATCH`; the copy was deleted. No production DB or pointer was involved.

## Operations and next phase

The rebuild emits JSONL stages and 15-second heartbeat events, `result.json`, `operation_report.md` and a nonzero process exit on failure. The future production replacement phase must back up the active analysis DB, build a fresh candidate, run this gate, close handles, atomically replace and verify, and restore the backup if post-replacement verification fails. That replacement is **not implemented here**.

Rehearsal commands (run separately with `a` and `b`):

```bash
venv/bin/python -m rawcandle.fundamentals.operating_income_v2.full_rebuild --target temp/phase13g25b1_final_a.db --provider data/fundamentals_provider.db --canonical data/fundamentals_v4.db --market data/osakedata.db --taxonomy data/analysis.db --output temp/phase13g25b1_final_a --as-of-date 2026-09-18
venv/bin/python -m rawcandle.fundamentals.operating_income_v2.full_rebuild --target temp/phase13g25b1_final_b.db --provider data/fundamentals_provider.db --canonical data/fundamentals_v4.db --market data/osakedata.db --taxonomy data/analysis.db --output temp/phase13g25b1_final_b --as-of-date 2026-09-18
```

Final test invocation used `venv/bin/pytest -q` against `tests/test_fundamentals_v4_full_rebuild.py`, all `tests/test_fundamentals_v4_operating_income_v2*.py`, all `tests/test_fundamentals_v4_relative_position*.py`, all `tests/test_fundamentals_v4_relative_valuation*.py`, `tests/test_fundamentals_admin_batch_add_tickers.py`, `tests/test_fundamentals_admin_foundation.py`, `tests/test_fundamentals_admin_ui.py` and `tests/test_fundamentals_v4_company_snapshot_phase9f.py` (19 explicit files): **266 passed, 0 skipped, 0 failed**. Fundamentals V3 was not tested.

The next phase may route Add Tickers, Sector/Industry and Taxonomy Administration through this one full rebuild path and remove Add Tickers' RP V1 call. This phase made no production DB writes, pointer moves, Add Tickers routing changes, taxonomy writes, production RV run, V1 deletions or push.
