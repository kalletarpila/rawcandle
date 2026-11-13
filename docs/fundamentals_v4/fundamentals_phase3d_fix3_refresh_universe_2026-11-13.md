# Fundamentals Phase 3D FIX3 — installed Refresh scope and explicit STOP boundaries

Subsequent resolution: [FIX4 authority and historical retention](fundamentals_phase3d_fix4_identity_retention_2026-11-13.md).
The approved batch-add evidence proves KRSA's same-company successor relationship;
Refresh membership/representative reconciliation remains separately required.
FIX4 adds a narrow immutable-OLD retention proof for already reviewed new-company
admissions with intentionally absent provider mappings, including PSQL/QVCG.
It grants no incoming identity or membership. Multi-security Refresh selection
and unsupported inactive-company analysis retention remain STOP boundaries.
The FIX3 implementation/results below remain the historical observations.

**Verdict: bounded update-only scope correction implemented; production readiness
BLOCKED.** The installed universe has a CYCN/KRSA company/security contradiction,
and eleven admitted companies still require an explicit security selection.
Neither is repaired or interpreted as permission to exclude admitted identities.
PSQL/QVCG OLD carry-forward lacks the provider mapping required by the native
authority verifier; that boundary also remains unresolved.
Native reconstruction also cannot retain existing inactive-company analysis;
that input now stops before candidate construction. The task's complete
unconditional acceptance criteria are therefore **not claimed**.

Starting HEAD: `f83c2021fb74ef3d3b768db9ed0ca1e6f947e318`. Governing inputs:
[FIX2](fundamentals_phase3d_fix2_acquisition_quarantine_2026-11-13.md),
[Phase 3B](fundamentals_phase3b_snapshot_integration_2026-11-12.md),
[Phase 2](fundamentals_phase2_local_validation_publication_2026-11-12.md), the
operator's FIX3 policy and the exact RESUME2 operation artifacts listed below.
Investigation stayed within these operations, native universe/identity readers,
the snapshot coordinator/kernels, relevant builders and targeted fixtures.

## Actual installed authority

The source of membership is the canonical active-version pointer and its
`fundamentals_operational_universe_version`, `_member` and `_member_alias` rows,
under `PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1`. `_member` is keyed by
**version/company**, not ticker or security. The active version remains
`3b8121b74c852f08575fa1e2b70004e6`, activated `2026-09-20T14:58:55Z`.

| Installed population | Actual count |
| --- | ---: |
| Company membership rows | 2,468 |
| ACTIVE_SINGLE_SECURITY companies | 2,441 |
| ACTIVE_MULTI_SECURITY companies | 11 |
| HISTORICAL_RETAINED_NO_ACTIVE_SECURITY companies | 16 |
| Non-null, distinct directly selected member security IDs | 2,457 |
| Active securities recorded in version metadata | 2,463 |
| Versioned alias rows | 2,495 |
| Physical ticker-alias rows | 2,575 |

Thus the previously observed **2,457** is neither the full company population nor
the count of currently refreshable active securities: it includes sixteen
historical selections and omits the unresolved multi-security selections.

The version's economic fingerprint and population metadata reproduce exactly.
The native removal writer passed predecessor-version-bearing alias rows into
`universe_identity`; reproducing its source/physical fingerprints requires
predecessor `1ce607c4c34d326616575ad4cc2effb1`. Omitting that field creates a false
fingerprint mismatch. This historical encoding is preserved. FIX3 pins the exact
installed header, member/alias content and physical security/alias/provider
identity mappings; it does not create a registry or regenerate membership.

**Actual authority contradiction:** company **627**, key `SEC_CIK:0001755237`,
has an installed `ACTIVE_SINGLE_SECURITY` row selecting security **628 / CYCN**,
with `active_security_count=1`, `all_security_count=1`. Physical canonical state
also contains active security **2558 / KRSA** for that company, valid from
`2026-09-09`, created `2026-09-22T13:56:59Z`. Actual active/all counts are both
**2**. KRSA's alias source is the separate batch-add workflow. CYCN has the native
Sharadar provider identity `111101`; KRSA has no provider-security mapping in
that company. No handoff, substitution, automatic retirement or membership
repair can be inferred. The new authority reader raises
`REFRESH_UNIVERSE_SECURITY_CONTRADICTION` before a new UPDATE request/FETCH.
This is the operator's explicit installed-authority STOP condition.

The eleven multi-security companies are CENT/CENTA, FOX/FOXA, FWONA/FWONK,
GOOG/GOOGL, LBTYA/LBTYK, LILA/LILAK, LLYVA/LLYVK, METC/METCB, NWS/NWSA,
UA/UAA and Z/ZG. Their authority explicitly says
`MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION`, with null selected
security ID. Their twenty-two securities cannot all be called out-of-universe.
ADR/common distinctions likewise remain security/provider identity distinctions;
a shared company or raw alias does not authorize substitution.

## Exact original mismatch reconciliation

Original UPDATE:
`20261112T194901Z_refresh_fundamentals_a45d1fafcc56_snapshot_update_c604bb4c`.
FETCH: `fetch_c604bb4c912f491da652efd5d55592db`.
BLOCKED financial validation: `local_e16723705b79452b9516b1b47184e235`.
The retained native receipt and streamed top-level `global` array were checked;
the 3,203,120,851-byte decisions artifact was not rewritten or loaded as a
whole financial graph.

| Set | Total | Direct active-single | Multi selection unresolved | CYCN/KRSA contradiction | Historical retention | Outside installed companies | No physical identity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw discovery | 3,084 | 1,721 | 10 | 1 | 0 | 30 | 1,322 |
| Original pending union | 580 | 580 | 0 | 0 | 0 | 0 | 0 |
| FETCH plan | 3,235 | 1,872 | 10 | 1 | 0 | 30 | 1,322 |
| Native global blockers | 1,420 | 0 | 22 | 1 | 1 | 74 | 1,322 |
| Globals from FETCH | 1,363 | 0 | 10 | 1 | 0 | 30 | 1,322 |
| Globals outside FETCH / OLD domain | 57 | 0 | 12 | 0 | 1 | 44 | 0 |

The historical global is **LBRDK**, another inactive security of the installed
historical company selected through LBRDA. A direct member-security join misses
it even though the company's historical membership is explicit. It requires
OLD retention, not an active admission. The former aggregate “98 with physical
records” decomposes into **74 outside-company + 22 unresolved multi-security +
KRSA + historical LBRDK**. Those categories explain all 1,420 blockers without
converting them to holds or assuming every name should be dropped.

The original pending union reconstructs **exactly** from **579** pending
financial reviews plus **one** accounting-boundary name, **WFRD**. All are
direct active-single members. **429** overlap raw discovery; **150** review-only
members plus **WFRD** account for the **151** pending names without a newly
discovered source change. Out-of-universe original review/accounting additions:
**0 / 0**. Current pending financial rows: **638**, all direct active-single.
Queue presence still confers no admission or approval.

The full canonical OLD ticker domain is **2,553**: 2,439 active-single names,
22 unresolved multi-security names, 17 historical names, 74 outside-company
names and KRSA. The seventeen historical tickers belong to sixteen companies.
The 1,872 direct active-single planned names are a **diagnostic projection**,
not an authorized live plan: the installed contradiction first requires STOP.

## Bounded implementation and invariants

`refresh_universe.py` reads the existing authority, verifies its population and
physical ownership consistency, and provides an operation binding and explicit
ELIGIBLE / EXCLUDED / AMBIGUOUS resolutions. No membership writer or onboarding
change is introduced. A proven versioned historical alias resolves to the
current security/provider acquisition ticker; it does not create another source
slot. Physical-only aliases, collisions, handoffs, mismatched provider identity
and unselected admitted securities remain gated.

New snapshot UPDATE requests pin `refresh_universe`. Discovery projects native
changed names, pending financial reviews, accounting queue items and installed
accounting decisions through the same reader. Explicit source-origin exclusions
and identity ambiguities remain in immutable discovery evidence. Proven source
aliases normalize to the current acquisition ticker. `changed_tickers` and
`evaluation_tickers` contain the eligible projection; `raw_changed_tickers`
separately preserves the provider response population and raw count. Operator
summaries report eligible/excluded/ambiguous counts and point to origin/reason
evidence in `discovery.json`. An admitted ambiguity stops acquisition rather than becoming an exclusion or source
quarantine. Empty/no-source-change admitted review/accounting sets remain in the
selection union. Native overlap, source window, complete ARQ/MRQ capture,
rate-limit, source-age and positive quarantine contracts remain unchanged.

UPDATE_FETCH creation/resume verifies that every planned ticker is an eligible
current acquisition identity under that same request binding. VALIDATE checks
it again before incoming financial classification. BUILD/publication recheck
the existing OLD/code/source/queue/configuration/dependency bindings, now also
including the universe binding. Out-of-scope evidence cannot become a provider,
canonical or analysis addition. Genuine admitted OLD ambiguities remain global
blockers even if there is no raw source change.

The optional native publication-retry company filter applies **before** the
100-quarter cap, rejects out-of-scope NEW quarter identities, and excludes
historical/out-of-universe companies from new SEC planning and publication-date
enrichment. The native 60-day/100-quarter/300-second and unresolved-evidence
semantics remain. Existing non-Refresh callers retain their original defaults.
Financial approval matching/finalization, ownership continuation and native
journal/activation/rollback authorization are unchanged.

## OLD retention and the model incompatibility STOP

OLD-only state is identified for retention through its existing physical
company/security/provider ownership, without granting incoming approval.
The existing canonical carry-forward kernel captures and restores its full
accepted quarters, financials and provenance. Provider and canonical authority
are verified unchanged before candidate preparation and again after activation.
Existing held/restricted state remains held; no source repair or queue approval
is fabricated. Surrogate rebuilt row IDs are distinguished from economic keys.

**Additional native authority boundary:** among the 75 historical/outside-company
global identities, **PSQL** (company 2546/security 2559) and **QVCG** (company
2547/security 2560) have no canonical Sharadar provider-security mapping. Their
16 and 180 accepted provider observations respectively have the matching
company/security headers but null `provider_security_id`. The existing native
`review_locality.authority` permits a null legacy header only with an exact
canonical provider map; otherwise it raises
`QUARANTINE_CANONICAL_PROVIDER_MAPPING_AMBIGUOUS`. FIX3 does not replace that
verifier or synthesize a mapping. It raises
`REFRESH_OLD_RETENTION_IDENTITY_UNPROVEN:<ticker>` before financial classification
can authorize BUILD. The corresponding isolated fixture verifies exact OLD role
bytes, unchanged admission and no activation. Their OLD is preserved in place;
rebuilding it is not certified until an independently accepted native retention
authority can be supplied. No approval or repair is performed here.

The native builder preserves out-of-membership companies that still have an
active physical security. The disposable end-to-end case verifies complete OLD
provider/canonical authority, original publication dates/provenance, unchanged
security admission, historical score values and all five native historical-model
endpoint sets (score/lifecycle/valuation/delta/diagnostic). RP/RV use the normal
single full rebuild and native verification; no incoming excluded security is
added to their input authorities.

**Unsupported case demonstrated:** `ttm/engine.py:load_canonical_rows` joins a
company through `MIN(security_id)` with `active=1`. The fresh canonical builder
deletes/rebuilds all TTM rows, and the fresh V2 builder uses that reconstructed
history rather than the OLD analysis DB. Consequently an inactive-only OLD
company with four accepted analysis endpoints lost all four in the initial
disposable probe, despite retained provider/canonical state. Per task E/I this
contract is not redesigned. FIX3 now stops before creating a candidate lane with
`REFRESH_OLD_ANALYSIS_RETENTION_UNSUPPORTED:<company>:<table>:NATIVE_TTM_REQUIRES_ACTIVE_SECURITY`.
A separate historical-coverage check also rejects any lost OLD-only economic
endpoint after a supported analysis rebuild. No parallel archive is introduced.

The sixteen actual installed historical companies currently have **zero** rows
in each of those five OLD analysis-model tables. This is an observed accepted
OLD state, not permission to reconstruct erased history or a claim that every
future inactive-company history can be preserved. The incompatible fixture
stops with all three OLD role bytes and activation unchanged.

## Original sealed UPDATE disposition

**New UPDATE required; original retry/reprojection is not authorized by the
established contract.** Its immutable request lacks the new installed-universe
policy/binding, and its exact request, discovery, FETCH and SEC bundle are
cross-bound. Existing local retry does not provide an independently authorized
eligible-universe projection. Adding a permissive legacy fallback would be a
special bypass; rewriting the request or dropping source slots would invalidate
the original authority. New code explicitly rejects that missing binding.

No native cross-UPDATE capture-import/rebinding contract exists here. The old
captures remain audit/diagnostic evidence; they are not silently promoted into
a fresh acquisition. The old BLOCKED receipt, source fingerprints, financial
decisions and original deadline **2026-11-19T19:49:02.002339+00:00** remain exact.
No old UPDATE retry, replacement UPDATE or network acquisition was performed.

## Disposable evidence and production protection

**228 distinct targeted cases passed.** No full repository suite was run.
The native TTM/history incompatibility is unchanged shared-core behavior;
discovering it does not justify unrelated suite expansion or a model redesign.

| Selection | Passed | Evidence |
| --- | ---: | --- |
| New scope cases + snapshot integration/backend + acquisition/quarantine/rejections | 219 | `acceptance.xml` |
| Existing native candidate-publication regressions | 7 | `publication.xml` |
| Final 20 scope cases + supported publication, quarantine, reporting and rollback | 25 | `final2.xml` |
| Strengthened actual VALIDATE/BUILD drift entry tests | 2 | `native_drift.xml` |

Selections overlap; 253 successful executions represent 228 distinct cases,
not 253 independent scenarios. The final source and test hashes are retained in
`tested_source_hashes.json`. Early probes exposed the documented inactive-history
and missing-map STOP boundaries; those cases now assert STOP with OLD unchanged.

| Required scenarios | Demonstrated outcome |
| --- | --- |
| 1. Admitted new ARQ/MRQ change | Native eligible AAA capture/comparison/build/publication |
| 2. Pending review without discovery | Real pending queue selects AAA despite no raw AAA discovery |
| 3. Admitted accounting obligation | Origin projection retains admitted accounting member without raw change |
| 4. Raw new name outside membership | NEW reported/excluded before capture; no canonical admission |
| 5. Outside review only | REVIEWNEW remains stored; no source acquisition or approval |
| 6. Outside accounting only | Both accounting origin projections exclude it with reason |
| 7. OLD outside active Refresh | Complete supported OLD retained; unsupported native proofs STOP |
| 8. Proven historical alias | Versioned OLD alias normalizes to current AAA/security 10 |
| 9. Collision/handoff | Ambiguous alias and company/security contradiction fail closed |
| 10. Multiple securities/company | No implicit security selection or company expansion |
| 11. Local acquisition quarantine | Existing real FIX2 whole-ticker exclusion/publication regressions pass |
| 12. Local baseline hold | Existing 100-held-member native integration passes |
| 13. Safe-peer continuation | Native financial hold and source quarantine peers continue |
| 14. Complete OLD history | Full economic/provenance comparison, rolling-history and five model endpoint sets |
| 15. No new admission | Security rows unchanged; NEW absent after verified publication |
| 16. Same pinned authority | Request/receipt equality; drift rejected by actual VALIDATE/BUILD entry points |
| 17. Coherent candidate | One inactive native full V2 build, followed by explicit disposable activation |
| 18. Admitted ambiguity | OLD-only multi-security identities remain financial globals without discovery |
| 19. Outside evidence cannot publish | UPDATE_FETCH rejects outside plans; exact source/candidate/receipt gates remain |
| 20. Publication/recovery | Native postflight, ordinary rollback and source-independent crash recovery regressions |

Deterministic fixtures use native capture, SQLite builds, generation publication,
postflight and recovery; outgoing sockets and production SQLite writes are
guarded. Fixture HTTP counters are simulated transport, not live HTTP calls.

**Protected-state comparison: 26,867 files, zero differences** in SHA-256, size,
inode and modification time, from `2026-11-13T13:24:00.561183+00:00` through
`2026-11-13T13:53:59.757890+00:00`. This covers all **26,861** current files under
the exact original UPDATE (958), FETCH (25,899) and BLOCKED validation (4), plus
the active manifest, journal, live review queue and three active financial roles.
All source/SEC bundles, mutable original operator views, receipt and decisions
are unchanged. The decisions SHA remains
`3dc25f338f852e552fc051e2cbbf745411c99399b4336705c13f70a78e3b9701`;
the native validation-receipt file SHA remains
`49afc13dd37de7f0d86c22e256a96f2c28d33ba07fc55e6551da716f7fa3a6fa`.

| Protected financial role | Bytes | Unchanged SHA-256 |
| --- | ---: | --- |
| Provider | 968,331,264 | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| Canonical | 749,371,392 | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| Analysis | 912,351,232 | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |

Queue bytes remain 882,114,560; SHA
`dcb51f9afbf5329ff6a3a33318ea15fd3082d2193aeedf4aaffacaa982b4c7af`.
The scheduler configuration's hash and mtime also remain unchanged, with
Fundamentals enabled **false**, route **SNAPSHOT_V1**, mode FULL_WORKFLOW.
The repository test guard independently hashes its protected live database set,
including market/taxonomy, around each pytest session; all sessions completed
without protected-state differences. No live financial or review connection was
opened writable by this task.

Active generation remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`;
published source watermark **2026-10-28**; journal
**COMPLETED/PASSED/NOT_REQUIRED**. Actual Sharadar HTTP **0**, SEC HTTP **0**,
outgoing-socket attempts **0**, live UPDATE/new UPDATE **NO**, production
financial/review writes **NO**, activation/watermark/configuration changes **NO**,
scheduler HOLD **YES**. Explicit publication occurs only in task-owned copies.

Task-owned evidence is retained under
`temp/fundamentals_phase3d_fix3_20261113/` and excluded from Git. It includes
`reconciliation.json`, `installed_contradiction.json`,
`installed_historical_analysis.json`, `protected_before.json`, targeted JUnit
results and outgoing-socket ledgers. No runtime cleanup or storage optimization
is performed. The original pre-existing worktree changes remain unstaged.

## Remaining operational blockers and next action

1. Resolve company 627's installed-versus-physical CYCN/KRSA ownership and the
   eleven multi-security selections through the established authority process,
   under separate authorization. Do not mutate them to make this task pass.
2. Treat the inactive-company OLD analysis case as a STOP until an independently
   accepted historical-model contract can preserve it. Supported input fixtures
   passing does not waive that boundary.
3. Resolve the native OLD carry-forward proof boundary for PSQL/QVCG separately;
   a missing provider map is not filled by this Refresh scope correction.
4. Recheck actual installed authority, OLD, review obligations and scheduler HOLD
   after any separately authorized correction. Only then authorize a **new**
   update-only UPDATE with its own scope/source/SEC/approval bindings. This task
   does not execute that operation, publish finance or enable the scheduler.

## Changed implementation files

`admin/refresh_universe.py` (reader, binding, resolution, OLD retention guards),
`snapshot_workflow.py` (request/discovery/SEC scope), `acquisition_snapshot.py`
(plan/resume gate), `snapshot_environment.py` (same authority at financial gates),
`refresh_update.py` (OLD retention, BUILD/publication checks) and
`candidate_publication.py` (optional native retry eligibility). Tests add
`tests/test_fundamentals_refresh_universe.py`;
`tests/test_fundamentals_snapshot_workflow.py` and
`tests/test_fundamentals_snapshot_integration.py` now install native membership
explicitly for integration copies. Documentation changes are this report and
`fundamentals_phase2_local_validation_publication_2026-11-12.md`,
`fundamentals_phase3b_snapshot_integration_2026-11-12.md`, and
`fundamentals_phase3d_fix2_acquisition_quarantine_2026-11-13.md`.
Total: **6 source files, 3 test files, 4 intended documentation files**.
