# Phase 13G.3.13 - BNC Universe Removal Rehearsal and Fiscal-Identity Guard

## 1. Purpose

This phase implements and rehearses a controlled removal of BNC from the Fundamentals universe and adds a generic fail-closed guard for same-source-key fiscal-identity revisions. It does not authorize or execute live BNC removal or Refresh Production.

## 2. BNC Audit Basis

Phase 13G.3.12 established that Sharadar changed the ARQ true key `(BNC, ARQ, 2026-06-23, 2026-04-30)` from FY2026 Q1 to Q4 while the current ARQ history also identifies 2026-01-31 as Q4. SEC and MRQ support April 30 as Q4 and January 31 as Q3. BNC was the only same-key fiscal-identity revision among 71 changed known tickers, so the defect is isolated and does not justify ticker-specific production logic.

## 3. Fundamentals Universe Contract

Active membership is owned by the canonical `fundamentals_operational_universe_*` contract. Provider history supplies accepted source observations, canonical tables own stable identities and financial state, and the analysis database is fully derived. Refresh now resolves known tickers through the active operational universe when that contract is present; a retired BNC remains visible in discovery as `NOT_IN_CANONICAL_UNIVERSE`.

## 4. Removal Scope

The write set for a future authorized publication is exactly:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`

`data/osakedata.db` and `data/analysis.db` remain read-only reference sources. Market history, `ticker_meta`, taxonomy, watchlists, and other applications are outside this operation.

## 5. Identity Ownership

BNC maps exclusively to company 346 and security 346. The company has one security, one ticker alias, and one active Fundamentals-universe membership. Removal retires the company/security and excludes it from a newly active universe version. Historical identity and old universe-version references are retained intentionally as audit/control history; no active financial state or orphan reference remains.

## 6. Provider Removal

Preview found 74 BNC observations/source keys: 36 ARQ, 38 MRQ, no other dimensions, no retained-outside-window rows, and three metadata rows. Observations referenced two historical provider runs (32 and 42 rows). The candidate deletes BNC-exclusive provider observations and metadata while preserving a deterministic non-BNC semantic fingerprint that includes observations, metadata, provider runs, schema/action controls, and Refresh state when present. It does not alter Refresh state or watermark.

## 7. Canonical Rebuild

The candidate uses the existing fresh canonical rebuild from the modified provider candidate and then activates a universe version without BNC. Before removal BNC had 34 quarters, 34 financial rows, 34 TTM rows, 368 field-provenance rows, 30 common-earnings provenance rows, and 170 operating-working-capital provenance rows. The candidate has zero BNC quarters and zero active BNC memberships. Non-BNC identity/control fingerprints are unchanged.

## 8. Analysis Rebuild

Exactly one full B1 V2 rebuild produced status `READY`. The pre-removal direct BNC footprint was Score 34, Lifecycle 34, Valuation 34, Delta 34, Diagnostics 34, RP 0, Relative Coverage 8, and RV 1, for 179 rows total. The candidate has zero direct BNC analysis rows.

## 9. first_public_result_date

BNC had 34 established first-public dates, from 2018-04-02 through 2026-06-23. They leave active canonical state with the removed BNC quarters and are not reassigned. The complete non-BNC `first_public_result_date` fingerprint is unchanged.

## 10. Relative-Model Effects

Outside BNC, changed company counts were Score 0, Lifecycle 0, Valuation 0, RP 0, and RV 2,443. The absolute/company-local models remained stable. The RV changes are the expected consequence of removing one member from a relative universe; surrogate IDs, timestamps, run metadata, and package lineage were excluded from semantic comparison, while economic/readiness fields remained compared.

## 11. Fiscal Identity Revision Guard

Refresh compares previously accepted and current complete source histories by true Sharadar key `(ticker, dimension, date, reportperiod)`. A changed normalized fiscal year/quarter on the same key emits `FISCAL_IDENTITY_REVISION`, records old/current identities, fingerprints, `lastupdated`, financial-change evidence, duplicate-target evidence, and canonical identities, and classifies the ticker as `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`. It never auto-accepts remapping.

## 12. Refresh Preview Integration

Preview exposes both fiscal-revision event and review-required counts and preserves financial-revision evidence when both occur. Review Required blocks Test, Production, and full-workflow continuation through existing Refresh gates. Source removal and rolling-window retention remain separate classifiers. Scheduler and manual triggers use the same classification code.

## 13. Add Tickers Interaction

Initial ingestion has no prior identity to compare, so Add Tickers performs a narrow current-history sequence check. It rejects an ARQ/MRQ fiscal-period contradiction for the same report period as `CONTRADICTORY_FISCAL_SEQUENCE`, but does not reject multiple legitimate source keys solely because they resolve to the same fiscal identity. This generic validation also prevents silent manual re-admission of an obviously contradictory history.

## 14. Removal Preview

The accepted read-only Preview is `20260920T140103Z_remove_fundamentals_tickers_3be926fa83fb_preview`, outcome `COMPLETED`, fingerprint `c4e59e864b51183ad4f6b561e920a51eec090fb126d2cec43b28ab8c183ccc62`. It captured provider/canonical/analysis/market/taxonomy SHA-256, size, and mtime_ns and performed no production writes.

## 15. Removal Test on Copies

The final accepted bound Test on the completed code is `20260920T143226Z_remove_fundamentals_tickers_3be926fa83fb_test`, outcome `COMPLETED`. Provider BNC rows changed 74 to 0, canonical quarters 34 to 0, and direct analysis rows 179 to 0. Non-BNC provider/control state, canonical identity, and first-public fingerprints were preserved. All three candidates returned `quick_check=ok`, zero foreign-key errors, and the full rebuild returned `READY`.

Earlier diagnostic copy runs were not accepted. They exposed comparison noise from surrogate identifiers and global structural package lineage; the comparator was narrowed to ignore only non-economic rebuild identity/lineage while retaining economic, readiness, status, and observed-point fields.

## 16. Publication Rehearsal

Fixture publication reused the shared durable three-role protocol: verified old-generation backups, prepared journal, provider replacement, canonical replacement, analysis replacement, per-role fsync/fingerprint verification, and terminal `COMPLETED`. No live path was used. The future operation also uses whole-generation journal recovery rather than filesystem inference.

## 17. Production Safety

Future Production requires explicit confirmation, an exact bound successful Preview/Test pair, unchanged production generation, no unresolved publication journal, the shared production lock, storage preflight, three verified backups, candidate validation, durable journal publication, and postflight. A dirty Git worktree is recorded as an audit warning only and is not a write-safety blocker, consistent with the established Fundamentals Admin policy. Removal does not create or advance a Refresh watermark.

## 18. Cleanup

The accepted Test removed its provider, canonical, and analysis candidates immediately after evidence capture. No phase candidate lane, live backup, or active publication journal remains. Lightweight JSON, Markdown reports, and the Phase 13G.3.12 audit CSV/Markdown remain as evidence.

## 19. Tests

Focused coverage includes fiscal-only and fiscal-plus-financial revisions, duplicate target identity, source-removal and retention separation, Review Required workflow blocking, scheduler/manual equivalence, Add Tickers sequence validation, exclusive/shared identity handling, stale Preview rejection before candidate creation, semantic model comparison, active-universe Refresh identity, and durable three-role fixture publication. The final command counts are recorded in the phase close-out and commit evidence.

## 20. Production Authorization Status

`NOT YET AUTHORIZED / NOT EXECUTED`

BNC live Production removal was not executed. Normal Refresh Production was not executed.

## 21. Next Step

Operator review may authorize a separate BNC removal Production invocation bound to a fresh Preview and successful Test if the production generation has changed since this evidence. After removal, run a fresh normal Refresh Preview against the unchanged `BOOTSTRAP_BASELINE`.

## 22. Git

The implementation, tests, and this evidence document are committed together on `chore/ignore-backups`. No push is performed by this phase.
