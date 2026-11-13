# Fundamentals Phase 3D FIX7 — approved financial representatives

Subsequent [FIX8](fundamentals_fix8_native_universe_reconciliation_2026-11-14.md)
implements the native reconciliation adapter and its acceptance/production gates.
It can preserve provider/analysis bytes and all non-universe canonical contents
through identity-only generation publication. Current OLD must independently
pass native analysis/source validation; the adapter does not rebuild financial
results or override a baseline incompatibility to make installation succeed.

**Verdict: the approved selection contract and disposable candidate are
implemented. Production installation remains BLOCKED at the activation-adapter
boundary.** All twelve tuples match freshly inspected accepted identity and
financial provenance. A native disposable generation journal publishes and
verifies a selected universe; the subsequent snapshot fixture reaches one
inactive financial BUILD and explicitly confirmed publication. Production's
installed universe, financial roles, reviews, watermark and HOLD are untouched.

Starting/accepted FIX6 HEAD: `43cfaeb0cf15296bf0e4f75f97afcaaf885d4298`.
Governing inputs: [FIX6](fundamentals_phase3d_fix6_financial_membership_resolution_2026-11-13.md),
[FIX5](fundamentals_phase3d_fix5_representatives_actual_history_2026-11-13.md),
[FIX4](fundamentals_phase3d_fix4_identity_retention_2026-11-13.md),
[FIX3](fundamentals_phase3d_fix3_refresh_universe_2026-11-13.md), native Phase 13B
versioning, current canonical/provider authority and the explicit FIX7 operator
decisions. No StockCore code, database or integration is used by this phase.

## Approved authority, freshly verified

Active OLD remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`.
Installed universe remains `3b8121b74c852f08575fa1e2b70004e6` as of `2026-09-20`.
Its observed population is 2,468 companies: 2,441 single-active, eleven
multi-active, sixteen historical, with 2,495 versioned aliases. CYCN's stored 1/1
physical counts still conflict with the actual two active securities. The old
reader correctly continues to STOP on production; installing new code grants no
selection to an unmodified legacy row.

Each approved representative was checked against exact current security ownership,
Sharadar mapping, installed company membership/selected alias, retained ARQ/MRQ
headers and canonical field provenance. The candidate preparer rejects missing or
contradictory mappings, companion sets and canonical source ownership. The
operation-scoped OLD proof binds all three accepted role hashes and manifest.
Identity selection is not financial review approval or baseline repair.

| Company | Representative / security | Sharadar ID | Companion / security | OLD ARQ/MRQ rows | Accepted company quarters |
| ---: | --- | --- | --- | ---: | ---: |
| 442 | CENT / 442 | 197778 | CENTA / 443 | 81 | 41 |
| 627 | CYCN / 628 | 111101 | KRSA / 2558 | 112 | 32 |
| 886 | FOXA / 888 | 111125 | FOX / 887 | 70 | 33 |
| 912 | FWONA / 914 | 191707 | FWONK / 915 | 82 | 41 |
| 969 | GOOGL / 973 | 195146 | GOOG / 972 | 82 | 41 |
| 1272 | LBTYA / 1277 | 191556 | LBTYK / 1278 | 82 | 41 |
| 1296 | LILA / 1302 | 121104 | LILAK / 1303 | 75 | 36 |
| 1307 | LLYVA / 1314 | 640301 | LLYVK / 1315 | 18 | 7 |
| 1407 | METC / 1415 | 124161 | METCB / 1416 | 81 | 40 |
| 1600 | NWSA / 1610 | 191637 | NWS / 1609 | 82 | 41 |
| 2243 | UAA / 2254 | 194726 | UA / 2253 | 82 | 41 |
| 2441 | ZG / 2458 | 179220 | Z / 2452 | 82 | 41 |

The maintained test JSON records only these explicitly approved identity tuples;
it is not consulted as a runtime registry. Runtime eligibility comes from the
installed versioned member. There is no alphabetic, liquidity, capitalization,
price or ID heuristic. An unapproved future multi-security company remains
unresolved even when one security has financial observations.

KRSA separately retains **160** OLD provider observations, including **70** ARQ/MRQ,
with null provider IDs and no canonical financial-source ownership. It receives
no Sharadar map or incoming eligibility. The accepted same-company succession
and both physical active flags/IDs remain unchanged. CYCN's financial role does
not reinterpret StockCore's price-facing lifecycle or retire either security.

## Minimal purpose-specific extension

`FUNDAMENTALS_FINANCIAL_REPRESENTATIVE_V1` extends the existing member rows;
there are **no new identity tables, schema migrations or registries**. The native
Phase 13B header/version algorithm remains V1. For an approved company:

- `member.security_id` and `current_ticker` name its one financial representative;
  `membership_status` still describes the real physical population. A multi-active
  company remains multi-active, including CYCN/KRSA with corrected 2/2 counts.
- `source` names the extension; `identity_resolution_status` is
  `OPERATOR_APPROVED_FINANCIAL_REPRESENTATIVE`. Typed JSON in `reason` records
  financial-only purpose, exact tuple, admitted companion IDs, physical fingerprint,
  approval reference/set fingerprint, starting universe, OLD and code binding.
- The existing native economic/version fingerprint includes that member content.
  The runtime request additionally pins `financial_selection_fingerprint` along
  with the complete universe content fingerprint. Ordinary legacy multi rows do
  not gain eligibility from a populated provider history.

The generic read-only preparer accepts explicit decisions and expected starting
authority, verifies them, and produces a fingerprinted immutable plan. The
installer is deliberately restricted to physically owned inactive `/tmp` or
repository `temp/` copies: it refuses production/accepted-generation paths,
symlinks, hardlinks, traversal, stale code, stale universe and damaged receipts.
It creates a **new** version, copies unaffected members, preserves the old version,
retains aliases and adds the existing KRSA alias to the new version only. Final
native reader validation happens inside `BEGIN IMMEDIATE`; failure rolls back the
candidate transaction. No existing version is edited in place.

## Real-data disposable candidate

The native SQLite backup of current canonical was reconciled in task-owned
storage using the exact twelve decisions; provider/analysis remained read-only
production inputs. No production financial rebuild or publication was executed.

| Binding | Candidate value |
| --- | --- |
| Starting universe | `3b8121b74c852f08575fa1e2b70004e6` |
| Candidate universe | `3edb315c20c6b82146790a59693a3b5a` |
| Candidate economic fingerprint | `ab5b552bc7065d2db6974d67131427a024f41fa240f24e33629c148045ef2721` |
| Candidate source fingerprint | `a6b64cac528411acdaff40987debb732c430076154b50c995a46bc107d4388ee` |
| Candidate physical fingerprint | `5d9fdc97a8f4ba173afea0f7fd77a946604d5b4dbb5efd2fc40ec1e2f240e0c4` |
| Selection fingerprint | `69a427960bb63c7584ed92586a4a3577a780b820d732390e4bcd56d4260fbf6c` |
| Approval-set fingerprint | `edbde9bd7016eceac4b9a71dead231eb0b84670c66f31181f15291e708ce07d3` |
| Complete plan fingerprint | `7ec592fca4e14705e2c704165c47acc00a234d626ec99018b3c0d0afe4b3574c` |

The candidate keeps all **2,468 companies**, including the sixteen historical
members. Physical classifications become 2,440 single/12 multi/16 historical;
recorded active securities become 2,464, correcting the one stale assertion.
All 2,468 companies now have a non-null selected or historical security ID;
this includes historical rows and is not a count of incoming acquisition targets.
The financial eligible-company projection is 2,452. Versioned aliases become
2,496 through the existing KRSA alias; no physical security or alias was created.

All twelve representatives resolve ELIGIBLE with the approved tuples. All twelve
companions resolve `FINANCIAL_COMPANION_RETENTION_ONLY` for incoming purposes,
with physical identity and membership retained. Canonical security, provider map
and physical alias rows compare exactly before/after. All **28 non-universe
canonical tables** compare exactly, including financial facts, provenance, first
public dates and TTM. Unaffected new-version member fields and every old alias
remain unchanged, and the starting version/header/member rows remain intact.

The reviewable plan and final canonical copy are retained under
`temp/fundamentals_phase3d_fix7_20261113/real_candidate_final_plan.json` and
`candidate/fundamentals_v4_candidate_final.db`. They are not committed, sealed as
a production generation or activated. The copy alone is not a coherent replacement
for production's complete generation/dependency set.

## Snapshot integration and financial retention

Discovery, UPDATE_FETCH, snapshot scope checks, VALIDATE, inactive BUILD and
publication rechecks consume the same installed selection/universe binding.
Only representatives fetch incoming ARQ/MRQ. A companion discovery does not
schedule duplicate company statements. Companion financial-review/accounting
origins may reevaluate the selected company source; the original obligation and
approval remain tied to the original identity and are never transferred or
finalized by a representative decision. Nonmembers remain outside incoming scope;
true ownership, map, alias and fingerprint contradictions still STOP.

Preserving KRSA rows in provider while letting them compete for a company winner
would be unsafe. The existing canonical reconciler now has an optional exact
company-to-security input domain. Snapshot BUILD derives it from installed
selections and filters companion ARQ rows **in memory before winner selection**.
Provider rows are not removed or rewritten. Default callers without a selection
domain retain their prior behavior and publication-date winner rules.

Companions are not put into the company-wide canonical hold list: doing that
would discard an authorized representative update. Instead BUILD and native
postflight compare their exact all-dimensional provider data and physical
security/alias/mapping records. The company's financial facts continue through
the normal representative review, source merge and historical-freeze gates.
Historical endpoint comparison now also covers selected companies. It runs after
BUILD and during postflight, with real loss causing native rollback.

FIX4's PSQL/QVCG reviewed retention code/proof is unchanged and freshly passes
against current OLD: six/eighty financial rows, two/forty canonical quarters,
without fabricated provider maps or incoming admission. FIX5's actual-history
gate remains conditional: today's seventeen inactive owners have no accepted
at-risk endpoints; real unsupported history still stops. Fresh inventory again
finds 89,671 economic keys in each of the five historical roots, zero outside
native current inputs, zero orphan components and zero analysis FK violations.
V2/RP/RV and price/share/ownership/P/B/TTM calculations are unchanged.

## Disposable acceptance and exact limits

The selection-generation rehearsal uses the existing generation preparer,
generation-pointer journal, native full V2 validation and native recovery. Its
analysis dependency set is rebuilt for the selected universe before sealing;
it does not activate a canonical-only copy against stale analysis dependencies.
Then a separate snapshot UPDATE fixture reaches FETCH → VALIDATE → exactly one
inactive V2/RP/RV BUILD → explicit PUBLISH/VERIFY. No provider is contacted.
The reconciliation rehearsal's dependency build is separate from that one
financial UPDATE BUILD; they are not claimed to be one combined invocation.

The native journal also recovers the original disposable universe/roles after
activation interruption. Companion provider loss injected after normal postflight
verification triggers financial rollback to the exact selected OLD generation.
Stale selection authority cannot activate a financial candidate. Unapproved multi
members, wrong mappings, cross-class canonical provenance, out-of-universe inputs
and actual historical loss remain blocked. Review/accounting obligations stay
bound, and no new company/security is admitted.

**184 distinct targeted cases PASS**, zero final failures/errors/skips. The
focused selection passed 63 cases; the final regression selection passed 143.
Their 22 overlapping cases are counted once, not as extra independent coverage.
The final selection includes the complete final 24-case new module.

| Directly relevant selection | Distinct passing cases |
| --- | ---: |
| New financial selection/version/candidate/publication cases | 24 |
| FIX3 installed scope and identity | 20 |
| FIX4 reviewed OLD retention | 15 |
| FIX5 actual analysis-history gate | 6 |
| Native snapshot integration | 34 |
| Native snapshot financial backend | 35 |
| Acquisition quarantine and safe-peer controls | 44 |
| Direct canonical winner/publication-date/TTM regressions | 6 |

The six direct canonical regressions verify unchanged default winner behavior,
invalid-date rejection, revision precedence, first-public preservation and native
transaction rollback. No targeted failure demonstrated unrelated shared-core
impact; **the full suite was not run**. No StockCore tests were run.

Development probes exercised intact native ownership guards: the first journal
fixture used a lane outside its disposable owner; a later recovery fixture used
a run ID inconsistent with the candidate lane. The harness was corrected to use
the native owner/run layout. A raw-byte copy assertion was also corrected to
compare full SQL content because SQLite backup can alter physical headers. No
production safety or financial acceptance check was loosened for these fixtures.
The real-data audit's first companion comparison used the pre-selection scope;
it was corrected to validate the installed candidate scope, alongside the separate
exact OLD-to-copy comparison of all non-universe canonical tables.

Final full SHA-256/size/inode/mtime comparison matched **26,870 protected files**
with zero differences, from `2026-11-13T21:14:25.406878+00:00` to
`2026-11-13T21:42:24.102664+00:00`: all 26,861 original UPDATE/FETCH/validation
files, three active financial roles, active manifest, journal, review queue,
scheduler and market/taxonomy dependencies. All **38** separately inventoried
admission/registry files also matched exactly. Original decisions, receipts, SEC
bundles and deadline were not rewritten or reprojected.

Both final test socket ledgers, the read-only authority audit and the real-data
candidate audit recorded **zero outgoing attempts**. The five source files and
two maintained test artifacts were byte-hashed; the final real candidate's code
binding matches those source bytes. Active generation remains as named above,
watermark `2026-10-28`; scheduler remains `FULL_WORKFLOW` / `SNAPSHOT_V1` /
`fundamentals_refresh_preview_enabled=false`: **HOLD preserved**. Production
financial, universe/identity and review writes: **NO**. Live/new UPDATE/FETCH,
production publication, StockCore integration/writes and acceptance relaxation:
**NO**. Disposable writes occurred only in isolated task-owned copies.

## Native production reconciliation plan and blocked boundary

**No production activation adapter is implemented or qualified by this task.**
`install_disposable_candidate` intentionally refuses production and immutable
generation targets. Native atomic publication/recovery exists and is exercised
on disposable complete generations, but there is no current production operator
entry point that safely installs this purpose-specific plan under all native
authority/dependency rechecks. Do not invoke a direct SQL patch or reuse a
financial UPDATE to smuggle in the universe change.

A later bounded adapter must reuse the existing generation/journal engine:

1. Under the established writer lock, revalidate exact expected OLD role/manifest
   hashes, installed universe and physical mappings/aliases, queue/config/HOLD,
   code/contract and the operator-approved twelve-choice fingerprint. Any drift
   requires a reviewed replacement plan, not rebinding this artifact silently.
2. Build an inactive canonical copy with this new version: populate the eleven
   previously null financial selectors, keep CYCN/628/111101, correct company627
   to multi-active 2/2, include KRSA's existing alias as a nonincoming companion,
   and preserve every other member, identity and OLD fact. No provider source
   acquisition, ID allocation, companion retirement or financial approval occurs.
3. Prepare/validate the compatible analysis/dependency set and all three roles;
   prove OLD financial/provider/analysis preservation with normal native checks.
   Preserve current watermark, first-public dates, holds and original evidence.
   Existing writers must preserve or explicitly invalidate these selectors;
   ordinary unannotated backfill cannot issue a replacement approval.
4. Only after the candidate is reviewable and a **separate production universe
   publication authorization** is granted, create the native expected-OLD journal,
   verified recovery material and complete generation, then atomically activate
   through the existing engine and run native postflight before completion.
   No new financial UPDATE or scheduler enablement is implied.
5. On failure/crash, restore the complete prior generation/manifest through native
   journal recovery and verify its universe and all role hashes. Retain previous
   versions, backups and original UPDATE evidence; never restore one member row
   or advance the watermark independently.

Thus the bounded selection/candidate work is complete; **production reconciliation
readiness remains BLOCKED** pending that adapter's qualification and authorization.
The original blocked UPDATE/FETCH/SEC bundle remains immutable. A future live
Refresh still requires a separately authorized **new UPDATE** after installation.

## Task-owned files and retained storage

Source: `admin/financial_selection.py`, `admin/refresh_universe.py`,
`admin/refresh_update.py`, `admin/refresh_copy_runtime.py`, and `phase12d.py`.
Tests: `tests/test_fundamentals_financial_selection.py` and the authored approved
tuple JSON in `tests/fixtures/`. Documentation: this report plus Phase 13B,
Phase 3B and FIX6 follow-ups. No unrelated worktree changes are staged.

The final canonical candidate is **749,953,024 bytes**; the earlier provisional
copy is **749,957,120 bytes**, retained separately as development evidence. At the
protected-state audit, the task evidence/candidate directory occupied
**1,518,167,212 bytes**; the two canonical copies are its largest consumers.
Retained isolated pytest roots add **1,346,939,529 bytes** (the final acceptance
root is 951,374,326 bytes). Measured combined generated storage is
**2,865,106,741 bytes** before final bookkeeping. Provisional copies and expired
test fixtures are potential later cleanup candidates after review; none is
removed or optimized by this task.
Before the final copy,
535,069,773,824 bytes were free versus a conservative 2,248,114,176-byte remaining
copy/journal peak estimate. No production provider/analysis full copies, storage
optimization, VACUUM, production cleanup or original-evidence deletion were performed.
All generated candidates, plans, JUnit, hashes and socket ledgers remain ignored.
