# Fundamentals Phase 3D FIX5 — representatives and actual historical retention

**Verdict: actual-history gate PASS on current OLD; representative authority
still prevents a live Refresh.** The sixteen installed historical companies are
not the whole inactive population: canonical has seventeen inactive companies,
including BNC outside installed membership. None has accepted rows in any
company-owned analysis table. A historical importer is therefore unnecessary
for today's OLD. Unsupported nonempty history remains a STOP, and actual loss
is checked after BUILD and during publication VERIFY.

No financial representative is selected by inference. CYCN is the currently
installed-selected/mapped financial identity, but its sole-active membership
premise is stale after the approved KRSA admission. All eleven multi-security
companies still require an explicit financial-purpose decision. No native
standing rule authorizes promoting their observed source into that decision.

Starting/accepted FIX4 HEAD: `3e9bef1621da784eb7ad7ebb594815b73bf37aac`.
Governing inputs: [FIX4](fundamentals_phase3d_fix4_identity_retention_2026-11-13.md),
[FIX3](fundamentals_phase3d_fix3_refresh_universe_2026-11-13.md),
[FIX2](fundamentals_phase3d_fix2_acquisition_quarantine_2026-11-13.md), native
Phase 13B universe/identity contracts, relevant TTM/V2/RP/RV builders and exact
retained admission evidence. Investigation stayed within those components,
their direct dependencies/tests and the named runtime operations. StockCore
integration, new identity registries and identity synchronization: **NO**.

## Fresh installed and identity evidence

Active generation remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`.
Installed version is `3b8121b74c852f08575fa1e2b70004e6`, as of `2026-09-20`:
2,468 company members, 2,441 active-single, eleven active-multi and sixteen
historical-only. Its 2,457 directly selected security IDs include sixteen
historical selections. Canonical contains **2,547 companies**, seventeen with
no active security. Counts, IDs and relationships were queried from current
read-only native files; they were not assumed from the previous summaries.

Company identity belongs to canonical company/CIK and accepted review material;
security identity/activity belongs to the security and alias records. Installed
membership is versioned separately. Provider identity is the exact native
Sharadar map. Financial source ownership is provider/canonical provenance;
market/price/shares/ownership/P/B context remains security-specific. Historical
retention is not incoming identity, admission or financial review approval.

## CYCN/KRSA: existing facts versus required authority

The accepted operation
`20260922T135415Z_add_tickers_3ea1ee983f75_production_548b274e`, its named preview
and copy apply, and approval fingerprint
`9440127ada42c4531eb4c2dd53c468efbe92810951bffcad64811488839ef7ee`
prove the approved same-company successor plan:

| Fact | Current evidence |
| --- | --- |
| Legal company | 627, CIK `0001755237` |
| Preserved predecessor | CYCN/security 628, active, Sharadar map `111101` |
| Created successor | KRSA/security 2558, active, effective `2026-09-09` |
| Successor provider identity | No canonical Sharadar mapping; none approved by the succession record |
| Installed representation | ACTIVE_SINGLE_SECURITY / 628 / CYCN, active/all counts 1/1 |
| Actual physical relationship | Two active securities, matching the approved preserve/create plan |
| Retained ARQ/MRQ observations | CYCN: 112; KRSA: 70 |
| Accepted canonical source | All 32 company quarters link through field provenance to CYCN/security 628 |

**CYCN is the only currently installed-selected and provider-mapped financial
identity.** That is a directly proven existing binding, not a choice made here.
The installed `security_id` was populated by the native exactly-one-active
backfill rule; it is not an explicit standing financial representative policy
after a second security is admitted. KRSA succession does not transfer `111101`
or invalidate CYCN's accepted history. Provider history under KRSA is not a
verified current mapping or a Refresh membership grant.

The installed version predates the approved admission and is stale. Its native
single-active invariant is no longer true. The consistency STOP remains;
neither automatic retirement/reassignment nor a source exception is justified.
**Disposition: existing CYCN binding proven; post-succession Refresh authority
and installed reconciliation require an operator decision/action.**

## Eleven-company decision matrix

All rows currently have ACTIVE_MULTI_SECURITY, two active securities, null
selected `security_id`, and
`MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION`. Financial-source
maps below originate from `tickers:fundamentals`; companion maps originate
from `tickers:stocks`. Canonical quarter provenance independently confirms
the single observed financial source in each row.

“Observed proposal” is an evidence-backed source to review, **not an authorized
selection**. Action R means: approve/reject that exact company/security/provider
tuple for **financial Refresh only**, retaining both existing securities and
their market/ownership contexts; install nothing until the native purpose and
versioned selection contract is explicitly approved. Another class needs its
own verified financial-source evidence, not a borrowed mapping.

| Company ID | Securities / IDs | Sharadar maps (same order) | Observed financial source / accepted quarters | Authorized representative | Status / exact action |
| ---: | --- | --- | --- | --- | --- |
| 442 | CENT 442 / CENTA 443 | 197778 / 114230 | CENT 442 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 442/197778 |
| 886 | FOX 887 / FOXA 888 | 111122 / 111125 | FOXA 888 / 33 | Not selected | OPERATOR_DECISION_REQUIRED; R: 888/111125 |
| 912 | FWONA 914 / FWONK 915 | 191707 / 119287 | FWONA 914 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 914/191707 |
| 969 | GOOG 972 / GOOGL 973 | 119496 / 195146 | GOOGL 973 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 973/195146 |
| 1272 | LBTYA 1277 / LBTYK 1278 | 191556 / 119285 | LBTYA 1277 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 1277/191556 |
| 1296 | LILA 1302 / LILAK 1303 | 121104 / 114228 | LILA 1302 / 36 | Not selected | OPERATOR_DECISION_REQUIRED; R: 1302/121104 |
| 1307 | LLYVA 1314 / LLYVK 1315 | 640301 / 640300 | LLYVA 1314 / 7 | Not selected | OPERATOR_DECISION_REQUIRED; R: 1314/640301 |
| 1407 | METC 1415 / METCB 1416 | 124161 / 640161 | METC 1415 / 40 | Not selected | OPERATOR_DECISION_REQUIRED; R: 1415/124161 |
| 1600 | NWS 1609 / NWSA 1610 | 119317 / 191637 | NWSA 1610 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 1610/191637 |
| 2243 | UA 2253 / UAA 2254 | 119495 / 194726 | UAA 2254 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 2254/194726 |
| 2441 | Z 2452 / ZG 2458 | 119315 / 179220 | ZG 2458 / 41 | Not selected | OPERATOR_DECISION_REQUIRED; R: 2458/179220 |

The unique company financial source does not authorize selecting a security for
every purpose. The native TTM minimum-active-ID join differs from that source
for FOX, GOOG, NWS, UA and Z. It is not a representative rule. No ticker, volume,
market-cap, price, liquidity or ID ranking is introduced. Both securities remain
admitted-company identities with unresolved selection, not outside exclusions.
Financial histories remain unique by company/fiscal quarter.

## Consolidated proposed native operator action — not executed

Current authority for every decision is version
`3b8121b74c852f08575fa1e2b70004e6` and the exact OLD generation above.

1. Review one consolidated decision: company 627's successor context plus the
   eleven R tuples. For company 627, explicitly preserve or supersede the existing
   CYCN/628/111101 financial binding; choosing KRSA/2558 requires independently
   verified provider/source authority. Do not transfer CYCN's provider ID.
2. Approve the **purpose** of the selections. Existing backfill automatically
   emits null selection for multi-active companies; the current Refresh reader
   also stops on that status. Backfill alone cannot install the proposed financial
   selections. A separately approved bounded native compatibility/update operation
   must express the explicit choices using the existing versioned authority.
   No existing direct write command is claimed to implement that missing purpose.
3. Prepare through the native identity review and owned copy/candidate process,
   not direct live SQL. Current → proposed is null → explicitly approved R tuple
   for the eleven rows; company 627's stale single-active representation → a
   reconciled version retaining the reviewed two-security relationship and the
   separately approved financial binding. Allocate no company/security IDs and
   do not retire companions merely to fit a single-active rule.
4. Required copy validation: expected OLD/version/hash binding; identity review
   material; exact provider IDs; no duplicate company financial statements;
   complete OLD/provenance/publication dates; unchanged market/share/P/B contexts;
   financial review/accounting and analysis retention gates; one coherent native
   generation with normal package/taxonomy dependency checks and postflight.
5. Live installation needs separate authorization and the native generation
   publication/journal/backup/expected-OLD boundary. Preserve the current version
   and OLD role backups for native full-generation rollback/recovery. Restore the
   complete OLD generation on failure; do not improvise an active-pointer or
   single membership-row patch.

Expected effect after a supported, separately authorized reconciliation: only
the approved mapped securities become financial acquisition candidates. OLD
predecessor/companion history is retained under its own authority. Selection
does not approve financial revisions, clear holds or authorize publication.
Until then, the native consistency/ambiguity STOP remains at the affected boundary.

## Actual OLD analysis risk — complete current inventory

Read-only schema/data inspection covered **all 38 current analysis tables**,
not only the sixteen installed historical members or five endpoint counts.
Canonical inactive companies are:
ALUR, AREB, AVB, BNC, BSLK, CERO, LBRDA, LEG, LYRA, MAPS, MSPR, NOTE, PTIX,
RMAX, SSKN, TALK and VSTD. BNC/company 346 is outside installed membership.

| Accepted analysis domain | Current result |
| --- | --- |
| Score/lifecycle/valuation/delta/diagnostic historical roots | 89,671 economic keys in **each** table |
| Exact native active-security financial input domain | 89,671 keys; every historical root matches this domain |
| Historical keys outside the current native input domain | 0 in every root table |
| Invalid score quarter/company references | 0 |
| Inactive-company rows in any company_id analysis table | 0 across all seventeen inactive companies |
| Analysis owners absent from canonical / without canonical quarter domain | 0 in every company_id table |
| Orphan score components / delta components / diagnostic evaluations | 0 / 0 / 0 |
| Analysis foreign-key violations | 0 |

The three component families are FK-bound to their historical roots. Their
current counts are 627,697 score components, 627,697 delta components and
717,368 diagnostic evaluations. Packages/model-run/activation/lookup metadata
are not independent company fiscal endpoints.

RP/RV company, coverage, peer and history tables were also inspected: no inactive,
unknown or canonical-quarter-less company rows exist. RV `own_history` and
`component_history` are per-company aggregates bound to a valuation snapshot;
they are not another independent store of quarterly score endpoints. Their
native current-snapshot calculation/retention semantics and all package/FK/role
validation remain unchanged. No RP/RV model redesign or new archive is introduced.

**Actual at-risk accepted inactive/OLD analysis history: none found.** This is
supported by the full current inventory, native input-key equality and component
graph checks, not inferred from one empty subset. No production candidate was
built, so future actual candidate preservation is still verified independently.

## Minimal actual-data gate implementation

The accepted FIX3/FIX4 preflight was already conditional on existing historical
rows, not an unconditional requirement for a new importer. FIX5 retains that
rule and closes its plan-domain limitation:

- Derive all inactive canonical owners plus historical model owners missing from
  canonical; include them even if absent from installed membership, FETCH or the
  retained ticker list. Check the known native historical model families.
- If none owns accepted historical endpoints, return
  `NO_AT_RISK_ACCEPTED_HISTORY` and allow the ordinary BUILD gates to continue.
- If native reconstruction would lose accepted history and no supported import
  exists, STOP before constructing a candidate. No invented historical join or
  recomputation using today's different security is permitted.
- Compare accepted economic keys for retained and inactive/missing owners after
  BUILD and again after native publication postflight, before completion. Check
  score quarter ownership as well as fiscal labels; surrogate IDs may change.

The candidate report now records the actual preflight result. Native role hashes,
model/package checks and ordinary rollback remain mandatory. This adds no new
financial acceptance, source acquisition, identity decision or historical model.
The five-family historical STOP is maintained for real nonempty fixtures.

## FIX4 PSQL/QVCG preservation

The FIX4 proof and restrictions are unchanged. Current read-only native proof
again passes: PSQL/company 2546/security 2559 retains 16 provider rows, six ARQ/MRQ
rows and two accepted quarters; QVCG/company 2547/security 2560 retains 180 provider
rows, eighty ARQ/MRQ rows and forty quarters. Provider mappings remain absent;
none is manufactured. Historical retention grants no incoming eligibility.
The original approved registry, admission records, provider data and generation
bindings are protected. Relevant FIX4 positive/adversarial/rollback tests remain
in the focused verification selection; the cases were not reopened or redesigned.

## Verification and protected state

Final acceptance: **154 passed, zero failures/errors/skips**, in 498.681 seconds.
Only the following directly relevant test modules were run; the full suite was
not run.

| Test module | Passing cases | Relevant coverage |
| --- | ---: | --- |
| `test_fundamentals_actual_history_gate.py` | 6 | Empty/nonempty inactive history, missing owner, wrong quarter owner, supported economic retention, real loss and rollback |
| `test_fundamentals_identity_retention.py` | 15 | FIX4 reviewed null-provider OLD, adversarial evidence, no fabricated/incoming identity, unique source still requiring multi-security selection |
| `test_fundamentals_refresh_universe.py` | 20 | Admitted scope, aliases, multi-security and installed contradictions, no implicit onboarding, OLD retention and universe fingerprints |
| `test_fundamentals_snapshot_integration.py` | 34 | Native integrated UPDATE fixture, review/accounting/publication authority, stale inputs, HOLD, native rollback/recovery |
| `test_fundamentals_snapshot_workflow.py` | 35 | Exact source/OLD/code/candidate binding, explicit review and publication, one native BUILD, postflight/recovery |
| `test_fundamentals_acquisition_quarantine.py` | 44 | Local quarantine, safe peers, unchanged financial approvals and held OLD, shared failures and immutable resume binding |

The first focused run had 40 passes and one failed assertion: the rollback test
looked for the historical error in the workflow's high-level message, which
retains its prior candidate-ready wording. Native rollback had succeeded. The
test now checks the authoritative `publication_outcome.error`; no production
behavior or gate was relaxed. The complete targeted selection above then passed.

Fixtures use real native capture, financial/V2 builders, inactive generations,
explicit disposable publication/VERIFY and native rollback. Fake transport is
guarded against real outgoing connections. The actual-data audit uses checked
immutable read-only SQLite access and performs no financial operation.

The empty inactive-history fixture reaches one BUILD and verified publication
while preserving all accepted OLD financial/provenance authority. Nonempty
inactive history stops before a candidate, even without a retained-plan entry.
Actual endpoint loss during postflight triggers native full OLD rollback.
Wrong quarter ownership fails the economic-key check. No gate is disabled to
make ambiguous identity or missing financial evidence pass.

The required identity cases are covered by the unchanged unique-source/multi-
security, installed-single/two-physical-actives, mapping, reviewed-admission and
scope tests, together with the fresh read-only CYCN/KRSA succession evidence
above. The isolated fixtures do not invent a production financial selection.
Required historical cases are exercised by the six new tests and FIX4 retention
regressions. Existing integrated tests cover the remaining review/accounting,
candidate/OLD binding, safe-peer, publication and recovery requirements.

Final SHA-256/size/inode/mtime comparison matched **all 26,870 protected files**:
the 26,861 original UPDATE/FETCH/validation evidence files plus nine production
files covering active financial roles, manifest, journal, review queue, scheduler,
market and taxonomy dependencies. All **38 separately inventoried admission and
identity-registry files** also matched exactly. Both targeted test network ledgers
and the read-only authority audit recorded **zero outgoing connection attempts**.
The three tested source/test byte hashes were recorded and checked unchanged
before staging. Temporary audit/JUnit/hash records are excluded from the commit.

Active generation is unchanged as named above. Native journal remains
`COMPLETED` / postflight `PASSED`. Provider watermark remains `2026-10-28`.
Scheduler remains `FULL_WORKFLOW`, route `SNAPSHOT_V1`,
`fundamentals_refresh_preview_enabled=false`: **HOLD preserved**. Scheduler config,
review queue and financial-role bytes are unchanged; this is no production write
or new financial authorization.

No StockCore integration, live UPDATE/resume/new UPDATE, production identity or
universe mutation, financial/queue write, publication, watermark movement or
scheduler change is performed. No storage optimization, cleanup or unnecessary
production database copies are made. Original BLOCKED UPDATE/FETCH/SEC/validation
evidence and deadlines remain exact. Old captures cannot authorize a new UPDATE.

Evidence is retained only under `temp/fundamentals_phase3d_fix5_20261113/`:
`analysis_inventory.json`, `representative_matrix.json`,
`canonical_financial_source_owners.json`, `authority_audit.json`, protected-state
inventories, targeted JUnit results and network ledgers. None is committed.

## Readiness and task-owned files

Historical reconstruction is technically possible for today's empty inactive
history and for supported active OLD retention; fully authoritative disposable
scope demonstrates the actual native candidate/publication path. It is not
currently possible to start a conforming full live UPDATE against the installed
production identity authority: company 627 is inconsistent and the eleven
financial selections remain unresolved. These are the next operator decisions,
not an empty-history engineering requirement.

After separately approved authority work, recheck current OLD/universe/reviews
and HOLD, then separately authorize a **new UPDATE** if appropriate. This task
does not activate a production candidate or enable the scheduler.

Changed source: `admin/refresh_universe.py` (actual historical scope, conditional
preflight and exact quarter ownership) and `admin/refresh_update.py` (record
preflight, repeat historical comparison in postflight). Added tests:
`tests/test_fundamentals_actual_history_gate.py`. Documentation: this report and
FIX4/Phase 3B follow-up links. No representative selection, identity writer,
TTM/V2/RP/RV calculation, financial approval or PSQL/QVCG proof was modified.
