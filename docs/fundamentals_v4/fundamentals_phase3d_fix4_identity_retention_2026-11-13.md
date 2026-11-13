# Fundamentals Phase 3D FIX4 — RawCandle authority and OLD retention

Subsequent [FIX5 actual-data audit](fundamentals_phase3d_fix5_representatives_actual_history_2026-11-13.md)
clarifies the historical STOP: empty accepted history permits the native rebuild.
Fresh inspection covers all 38 current analysis tables and all seventeen
inactive companies, including BNC outside installed membership. No actual
inactive historical endpoints are present. FIX5 extends checks beyond the
retained ticker plan and repeats the economic-key comparison at postflight;
nonempty unsupported history still stops. Financial representative decisions
remain explicit, and the PSQL/QVCG proof below is unchanged.

**Verdict: PSQL/QVCG historical retention resolved through a bounded source
correction; full production readiness remains BLOCKED.** KRSA's legal/company
relationship is already approved and proven in retained admission evidence.
Reconciling its Refresh authority still requires a separately authorized decision
and live universe correction. The eleven multi-security companies have unique
observed financial-source owners, but no existing native rule turns those
observations into selected Refresh securities. Inactive-company analysis import
has no established native reconstruction contract and retains its STOP.

Starting and accepted FIX3 HEAD: `d3576cf7f146d37a435a64873440feb0280be1fe`.
Governing inputs: [FIX3](fundamentals_phase3d_fix3_refresh_universe_2026-11-13.md),
[FIX2](fundamentals_phase3d_fix2_acquisition_quarantine_2026-11-13.md),
[Phase 3B](fundamentals_phase3b_snapshot_integration_2026-11-12.md),
[native Phase 13B](fundamentals_v4_phase13b_foundation.md), the existing reviewed
identity/admission code and exact retained operations below. Investigation used
these bounded components, their imports and directly related tests; no general
repository or runtime scan was used.

**StockCore integration: NO.** RawCandle IDs, ownership, identity registry,
membership authority, price/share/P/B economics and financial acceptance remain
in place. No cross-system synchronization or migration design is introduced.

## Current authority and ownership of facts

Fresh read-only inspection confirms active generation
`current_rebuild_2a684ef130c6a540de4adc560ab171ad` and universe version
`3b8121b74c852f08575fa1e2b70004e6`. The version still contains 2,468 company
members: 2,441 single-active, eleven multi-active and sixteen historical-only.
The 2,457 non-null selected security IDs include sixteen historical selections;
they are not the number of active Refresh securities. No historical count was
used as a required target.

| Fact | Native owner |
| --- | --- |
| Legal/company identity | `company.company_key`, `company_cik`, reviewed identity facts and the applied admission |
| Security identity and company relationship | `security`, dated `ticker_alias`, approved create/transition/successor mutation |
| Physical activity | `security.active`; an alias or successor does not automatically retire its predecessor |
| Installed Refresh population/selection | Active operational-universe version, company member rows and versioned aliases; multi-security selection is explicit |
| Provider identity | `provider_security_identity` and accepted Sharadar metadata; a CIK or historical admission does not invent a permaticker |
| Historical financial ownership | Accepted provider company/security headers, canonical company/quarter provenance and immutable OLD generation |
| Financial review approval | Native financial queue/action and exact source/OLD/approval binding; identity approval is a different authority |
| Analysis persistence | Native V2 package/activation manifests and full TTM/V2 reconstruction contract, including physical/economic fingerprints |

The checked-in registry remains `PHASE13G3_19_IDENTITY_REVIEW_APPROVAL_V2` /
schema 2.0. Its current-state matcher deliberately rejects replay of a creation
approval after the named security/company has been created. FIX4 preserves that
behavior; it reads already approved historical material for retention only.

## CYCN/KRSA: relationship proven, Refresh disposition requires reconciliation

Exact retained production operation:
`20260922T135415Z_add_tickers_3ea1ee983f75_production_548b274e`, with preview
`20260922T134548Z_add_tickers_cc67eb6a9820` and copy apply
`20260922T134648Z_add_tickers_3ea1ee983f75_apply`.
Its native `result.json` and operation report record COMPLETED, successful full
V2/postflight and NOT_REQUIRED rollback. The applied identity rows reproduce
their stored native fingerprint and name the actual new IDs.

KRSA approval fingerprint:
`9440127ada42c4531eb4c2dd53c468efbe92810951bffcad64811488839ef7ee`, approved
`2026-09-21T15:50:20Z`. The accepted record establishes:

- Continuing legal issuer CIK `0001755237`, company **627**.
- A distinct **successor security**, following the merger/reverse split/new CUSIP;
  it is not an ordinary ticker rename or another unchanged share class.
- Reuse company 627, create security **2558 / KRSA**, effective `2026-09-09`.
- Preserve predecessor security **628 / CYCN** unchanged; do not rename it or copy
  CYCN aliases onto the KRSA security.
- Provider metadata was absent; no successor permaticker was approved.

The referenced SEC/Nasdaq facts are retained approved registry evidence; no
fresh external legal verification or network request was performed here.
The resulting current physical rows match the approved native successor plan.
Thus there is **no evidence that KRSA was accidentally attached to another legal
company**. Both active rows reflect the explicit preservation/create behavior.

The installed version predates this admission: it still selects CYCN/security
628 and records one active/total security, whereas the physical company now has
two. This is a stale installed representation of an approved later admission.
The native incoming provider map remains only CYCN → `111101`; it does not prove
that KRSA should use that identifier. FIX3's contradiction gate therefore remains
correctly closed until the authority is reconciled. No security was retired,
reassigned or preferred, and no live universe correction was made.

### Operator decision record: company 627

The legal-company continuity decision already exists and must not be requested
again as if unapproved. What remains is:

1. Authorize reconciliation of the installed universe with the accepted successor
   admission while preserving the reviewed predecessor/successor distinction.
2. Specify the intended current Refresh financial acquisition/publication
   representative and its exact company/security/provider binding. Retaining
   CYCN's mapping or using successor KRSA are different financial-source
   decisions; neither follows solely from the CIK or the two active flags.
3. If KRSA is selected, provide independently verified native provider identity
   or an explicitly accepted source-authority decision. The old CYCN permaticker
   cannot be copied. New metadata/network acquisition and live corrections need
   their own authorization.

Any decision to retire CYCN would change the previously approved preservation
plan and requires an explicit new decision. FIX4 grants none of these mutations.

## Eleven multi-security companies

The Phase 13B contract is explicitly company-level; its null `security_id` for
multi-active companies means later security selection, not absence of company
membership. Each company has two mapped securities, but current retained
ARQ/MRQ observations belong to one financial source:

| Company | Observed financial source | Security ID | Sharadar mapping | Companion |
| --- | --- | ---: | --- | --- |
| CENT/CENTA | CENT | 442 | 197778 | CENTA |
| FOX/FOXA | FOXA | 888 | 111125 | FOX |
| FWONA/FWONK | FWONA | 914 | 191707 | FWONK |
| GOOG/GOOGL | GOOGL | 973 | 195146 | GOOG |
| LBTYA/LBTYK | LBTYA | 1277 | 191556 | LBTYK |
| LILA/LILAK | LILA | 1302 | 121104 | LILAK |
| LLYVA/LLYVK | LLYVA | 1314 | 640301 | LLYVK |
| METC/METCB | METC | 1415 | 124161 | METCB |
| NWS/NWSA | NWSA | 1610 | 191637 | NWS |
| UA/UAA | UAA | 2254 | 194726 | UA |
| Z/ZG | ZG | 2458 | 179220 | Z |

These source mappings originate from `tickers:fundamentals`; the companions'
mappings originate from `tickers:stocks` and have no retained financial rows.
This proves historical source attribution, **not a native standing rule selecting
a Refresh security**. Canonical financial statements are company-owned and
reconciliation chooses one fiscal result per company/quarter. Importing both
share classes as duplicate company financial history is not permitted.

The native TTM join uses the minimum active security ID for consumer context.
For FOX, GOOG, NWS, UA and Z this differs from the observed financial source.
That implementation detail cannot supply a new financial representative policy
or justify changing price/share/valuation/P/B context. No alphabetical,
liquidity, price or ID ranking was introduced.

**Disposition: OPERATOR_DECISION_REQUIRED for Refresh selection.** An operator
may separately approve a purpose-specific rule using the proven financial
source or record individual selections with their installed version and native
provider binding. Until then, all twenty-two remain admitted-company securities
with unresolved selection; none is relabeled out-of-universe and no implicit
member/security expansion is performed.

## PSQL/QVCG: narrowly supported historical retention

The same accepted production operation created **PSQL/company 2546/security
2559**, CIK `0002119292`, and **QVCG/company 2547/security 2560**, CIK
`0001254699`. Their approval fingerprints are respectively
`ef64506712560ac892323bcfa590b7e454fa22feb2619363b6aee61f9eec6b6c` and
`2f6ac6bb546181dfe7e228bbae25cfacebc488d820eb46b5e66a8e95d65591c4`.
They explicitly approve **new company + new security**, absent provider metadata,
no provider permaticker and no reuse of BBCQ/QVCAQ ownership/aliases.

Their accepted source rows belong to native successful admission provider run
`PHASE13G2_176752d19eaf0668ef410dc0`, source contract
`PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V7_ACQUISITION_AUTHORITY`.
Current read-only proof results:

| OLD company | All accepted provider rows | ARQ/MRQ rows | Canonical economic quarters | Canonical provider map |
| --- | ---: | ---: | ---: | --- |
| PSQL | 16 | 6 | 2 | Absent, intentionally not fabricated |
| QVCG | 180 | 80 | 40 | Absent, intentionally not fabricated |

PSQL's three ARQ source observations are not three distinct accepted fiscal
quarters; the native canonical winner domain currently contains two. No count
was forced to match the admission report's source-row coverage.

### Source correction

`review_locality.historical_retention_proof` uses the existing immutable-generation
attestation and reviewed identity registry. Its dedicated
`REVIEWED_NEW_COMPANY_OLD_RETENTION_V1` context requires all of:

- Exact verified OLD role hashes/native generation and original manifest binding.
- Still-approved, fingerprint-valid new-company/new-security material with an
  approved CIK/effective date and intentionally absent provider identity.
- Exact current CIK/company key, exclusive physical security owner, subject ticker,
  exchange and effective date; no current provider mapping or metadata conflict.
- Accepted native admission run/scope/version, complete owned ARQ/MRQ presence
  and exact all-dimension provider content, including the original null IDs.
- No linked canonical provenance owned by a foreign company/security. Missing
  legacy lineage remains missing; it is not repaired or newly attested as incoming.

It does not replay the old pre-admission `expected_state`, authorize a new
mutation, infer a provider ID or admit the security. Its old-generation digest,
registry/approval fingerprint, identity and provider digest are sealed inside
the ordinary local financial decisions. BUILD and post-publication verification
bind this proof to the same receipt's OLD authority and compare the complete
native economic/provenance authority before/after carry-forward.

The ordinary provider-mapping requirement remains for incoming data and local
financial quarantine. `validate=True` rejects a retention context outright.
Changed/missing/foreign source ownership, invalid/rejected/proposed approvals,
nonexclusive ownership and changed generation fail closed. The fallback is
available only to positively excluded OLD retention; admitted unresolved incoming
identities still use their original gates.

The existing canonical carry-forward/rebuild and publication/rollback engines
are reused. No financial/schema/provider identity is rewritten. PSQL/QVCG proof
**PASS** is demonstrated on current read-only OLD and on fully authoritative
native disposable admission/build/publication fixtures; a production candidate
for them was not built in this task. The real global CYCN/multi-selection gates
are not bypassed to run that operation.

## Inactive-company analysis: unsupported import remains STOP

The native TTM loader joins through an active security; fresh canonical rebuild
deletes/reconstructs TTM. `rebuild_v2_analysis` requires a new target and accepts
provider/canonical/market/taxonomy sources, with no OLD-analysis retention input.
V2 persistence replaces model result graphs and seals package economic/physical
fingerprints. Delta/diagnostic graphs reference score/endpoints/components;
copying only five endpoint tables would not preserve this contract.

No accepted native historical bundle import/rekey operation was found in these
relevant builders. Using today's chosen security to regenerate inactive history
could alter its economic meaning. Retaining OLD rows would need an accepted
complete graph/quarter-key/provenance/fingerprint contract, which FIX4 does not
invent. The existing `REFRESH_OLD_ANALYSIS_RETENTION_UNSUPPORTED` pre-BUILD STOP
and economic endpoint coverage check remain unchanged.

The sixteen actual installed historical companies still have zero rows in the
five checked historical model tables. That existing absence is not a repair
authorization. Fixtures with four accepted inactive-company endpoints retain
all OLD bytes and stop before a lossy candidate; even a valid new historical
identity proof does not waive this analysis boundary.

## Verification and protected production state

**Final targeted outcome: 168 distinct cases PASS across the relevant selections.**
No full repository suite was run. No new shared-core behavior failure justified
expanding beyond these contracts.

| Selection | Actual result | Evidence |
| --- | --- | --- |
| First native reviewed-retention end-to-end | 1 passed | `initial.xml` |
| Focused retention + FIX3 universe | 33 passed | `focused.xml` |
| Expanded relevant native regression selection | 166 passed, 2 stale-fixture failures | `acceptance.xml` |
| Those same two cases on accepted FIX3 kernels | Same 2 failures reproduced | `baseline_identity.xml` |
| Corrected identity/admission fixture group | 20 passed | `identity_compat.xml` |

Selections overlap; every one of the 168 distinct selected cases has a passing
final result. The expanded selection includes the fifteen new FIX4 cases, twenty
FIX3 scope cases, 34 production-adapter integration cases, 35 snapshot-backend
cases, 44 acquisition-quarantine cases and twenty identity/admission cases.

The two baseline failures predated FIX4: an unattested partial cache row expected
fiscal comparison before the mandatory source-capture gate, and a synthetic CSV
archive lacked the required full schema/checksum-bound acquisition manifest.
Only those fixtures/expectations were corrected. The archive now declares the
complete synthetic provider schema and original-byte manifest; the partial
cache still fails closed. Native capture/financial acceptance was not disabled
or changed. A bounded source overlay of the accepted FIX3 commit reproduced the
failures without modifying the shared worktree's implementation.

| Requested scenario | Demonstration/disposition |
| --- | --- |
| 1. CYCN/KRSA without selected authority | Existing actual single/two-active fixture remains blocked before request/FETCH |
| 2. Proven same-company relation | Native reviewed-successor admission preserves predecessor and creates separate security; applied production evidence matches |
| 3. Unique multi-security financial source | Unique source ownership is shown; it supplies no implicit Refresh selection |
| 4. No justified selection | Both admitted securities remain AMBIGUOUS/selection-required |
| 5. No duplicate financial history | Company/fiscal quarter uniqueness remains; current duplicate count is zero |
| 6. Reviewed historical null IDs | Real native admission → immutable OLD → retention → one BUILD → publication; IDs remain null and no map is created |
| 7. Missing/foreign authority | Proposed/rejected/tampered review, wrong source/header/run/owner, missing MRQ, nonexclusive owner and foreign canonical provenance fail closed |
| 8–9. Inactive accepted analysis | Existing four-endpoint loss boundary stays blocked before candidate, including with a valid reviewed retention identity |
| 10. No new Refresh membership | Historical source excluded from both acquisition dimensions; no member/provider map is inserted |
| 11. Same pinned authority | FIX3 request/receipt and actual VALIDATE/BUILD drift tests pass; retention also checks exact OLD generation |
| 12. Review/baseline unchanged | Existing exact financial approval and 100-baseline-hold integration pass |
| 13. Safe peers | Admitted peers capture/update/publish alongside excluded retained OLD |
| 14. Publication/recovery | Reviewed-retention ordinary rollback plus existing native crash/recovery/quarantine publication regressions pass |

Fixtures use real native admission, capture, canonical/V2 build, generation
activation/postflight and rollback. Their HTTP transport is deterministic fake
transport; a task-owned socket guard rejects actual connections. Production
SQLite write guards and fresh protected-file comparisons remain enabled.

The read-only PSQL/QVCG audit ran the actual new proof/authority functions with
SQLite URI `mode=ro&immutable=1`, after checking for no nonempty WAL/journal.
It retained native hash, quick-check and foreign-key validation and never
constructed a production UPDATE/environment/writer. Actual Sharadar/SEC/outgoing
requests: **0/0/0**. It also verified the retained admission IDs/approval material.

Fresh full protected-state comparison covers **26,870 files**, with **zero**
SHA-256/size/inode/mtime differences from
`2026-11-13T16:44:04.656831+00:00` to `2026-11-13T17:15:10.825615+00:00`:
all 26,861 original UPDATE/FETCH/BLOCKED-validation files and nine live protected
files (three active financial roles, manifest, journal, queue, scheduler config,
market and taxonomy). An additional **38** retained admission/registry files
also have zero byte/metadata differences. No identity approval record changed.

Active generation remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`,
watermark **2026-10-28**, journal **COMPLETED/PASSED/NOT_REQUIRED**. Scheduler HOLD
remains true with route SNAPSHOT_V1; scheduler configuration SHA remains
`113411a0e96eaad6c4fed186ca099b53bbfe9f827dbee11fa4f89cf43130e454`.
The three active financial role hashes are still the accepted FIX3 values.

No live UPDATE/resume/replacement, identity/universe/financial/queue mutation,
publication, watermark movement or scheduler change is performed. StockCore
integration, financial-policy relaxation, storage optimization and cleanup: NO.
Original BLOCKED UPDATE/FETCH/validation evidence and the 168-hour deadline
remain immutable. FIX3's new-UPDATE requirement remains; this task does not
rebind old captures or create a live replacement.

Evidence retained only under `temp/fundamentals_phase3d_fix4_20261113/` includes
`current_identity_audit.json`, `authority_audit.json`, `admission_files_before.json`,
protected-state inventories, JUnit results and outgoing-connection ledgers.
No runtime evidence, databases, captures or test outputs are committed.

## Remaining operator decisions and next action

1. Reconcile company 627's installed authority with the already approved
   CYCN-preserving KRSA successor admission; explicitly resolve the Refresh
   representative/provider binding. This needs separately authorized live
   authority work, not another inferred legal-company decision.
2. Resolve the eleven company-level Refresh selections, using explicit native
   authority rather than turning the observed source mapping into an unapproved
   ranking. Do not change price/share/P/B semantics implicitly.
3. Preserve STOP for any accepted inactive analysis endpoints until a separate
   historical model persistence contract is accepted. Current zero-history
   production cases and supported disposable cases do not waive it.
4. After those resolutions, recheck current OLD/universe/reviews/HOLD and
   separately authorize a fresh scoped UPDATE if appropriate. No live readiness
   or first production BUILD/publication is claimed here.

## Task-owned changes

- `rawcandle/fundamentals/admin/review_locality.py`: reviewed immutable-OLD proof,
  native historical authority comparison and explicit prohibition on incoming use.
- `rawcandle/fundamentals/admin/refresh_universe.py`: excluded OLD-only proof path;
  all admitted selection and universe consistency gates remain.
- `rawcandle/fundamentals/admin/refresh_update.py`: bind/verify retention during
  native BUILD and postflight, before native completion/review finalization.
- `tests/test_fundamentals_identity_retention.py`: native reviewed admission,
  retention/adversarial cases, one-build publication, inactive STOP and rollback.
- `tests/test_fundamentals_admin_identity_resolution.py`: adapt two pre-existing
  stale fixtures/expectations to the already enforced source-capture contract.
- This report, and FIX3/Phase 3B follow-up links. Only task-owned changes are
  committed; pre-existing journal/runtime/OHLCV/report work remains unstaged.
