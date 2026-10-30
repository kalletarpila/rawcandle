# Controlled current-state rebuild V1 — 2026-10-30

Task: `FUNDAMENTALS-CONTROLLED-CURRENT-STATE-REBUILD-V1`.
Policy: `FUNDAMENTALS_CONTROLLED_CURRENT_STATE_REBUILD_V1`.

## Contract and bounded architecture audit

Strict exact-source completeness repair is unchanged. In particular, adding
missing raw fields while changing `lastupdated` remains
`SOURCE_PAYLOAD_VALUE_REVISION`, rejected by the strict proposal and primitive.
The missing values cannot be attributed to the older accepted source version.

The new administration assessment tries strict repair first. Only the specific
strict rejection `PAYLOAD_WORKFLOW_NOT_COMPLETENESS_REPAIR`, followed by an exact
structured metadata-only advancement proof, can select the separate rebuild
operation. An exact repair remains the required first choice. Other rejected or
ambiguous cases remain UNRESOLVED; this operation grants no exclusion authority.
Ordinary Refresh, Add/Remove, scheduler selection, ownership approval and
publication-authority semantics do not invoke or depend on the new operation.

The bounded audit covered existing Sharadar acquisition/normalization, Add
insertion, Refresh replacement, canonical acceptance, parent-equity acceptance,
native full V2 analysis, generation publication, review scope, disposition and
backup cleanup. Whole-ticker Refresh replacement removes/reinserts complete
histories, and fresh canonical rebuild clears complete canonical histories. Those
scopes are inappropriate here. The new operation instead reuses the native
Refresh per-row normalizer/inserter and the native canonical reconciler with an
explicit selected-quarter scope. Defaults for existing callers are preserved.
It does not duplicate financial normalization or calculation.

## Eligibility and history boundary

Required evidence includes:

- Full, successful, unprojected Sharadar ARQ **and** MRQ history acquisition;
  authoritative endpoint, full source schema field manifest, acquisition time
  and fingerprints. Every captured record must include the complete field set.
  ABSENT and explicit NULL remain distinct. Capture evidence expires after one day.
- Exactly one current stored source key and one fresh counterpart; no duplicate
  history keys, ambiguous legacy source versions, competing current fiscal keys,
  changed source key/report period/fiscal identity, or newly advanced fiscal quarter.
- Deterministic native company, security and provider-security binding. Any
  explicit conflicting identity in fresh records rejects the operation.
- Equality of accepted canonical normalized financial values, old/fresh native
  projection and fiscal/source metadata. The sole changed normalized field must
  be a strictly advancing `lastupdated`. Existing nonprojection fields cannot be
  revised or removed. Missing values are never guessed; factor is never defaulted.
- Exact latest ACCEPTED, nonfrozen canonical quarter, and exact review-scope proof.
  Retained, accounting-boundary or otherwise reviewed current sources reject.
  A frozen review can coexist only when its accepted financial/source evidence,
  identity, affected keys and fingerprinted HELD conflicts are current and disjoint.
- Healthy native publication/recovery state, manifest/role hashes, watermark,
  queue content, market/taxonomy inputs, configuration and implementation binding.

Only the selected current observation is replaced **in the inactive candidate**.
All other provider records and historical canonical/provenance rows are compared
with the immutable baseline and must remain identical. The prior generation
retains the complete old current observation, raw payload and canonical evidence.
No historical observation is deleted from an existing generation.

The canonical reconciler selects its native publication winner, updates only the
selected existing quarter and calls the same parent-equity acceptor scoped to
that quarter. Existing parent values cannot change. Previously missing parent
equity can be filled from the new authoritative version only through that native
acceptor. TTM financial inputs remain identical; historical TTM records are
preserved. Full V2 analysis, RP and RV are rebuilt through the existing native
full-analysis path from protected copied inputs. Analysis calculation dates,
native prices and model metadata can consequently refresh; source financial
history, operational universe and ownership authority cannot change.

## Exact Preview, Test and native publication

Preview is read-only and binds exact acquisitions, baseline and review proof.
Test constructs disposable provider/canonical candidates, runs native full
analysis and independently measures source headers, raw completeness, native
financial values, canonical binding/equity, every unselected row, ownership
artifact and SQLite integrity. Its sealed receipt binds exact candidate bytes.

Publication requires explicit intent and the exact Preview fingerprint. Real
production cannot inject a fake provider client or failure hook. It reacquires
native UI, production/shared-scheduler and taxonomy locks, fetches full sources
again and requires exact source/schema equality. Only acquisition timestamps may
differ. Post-Test baseline drift rejects publication. The operational queue is
transactionally protected; this operation writes its own typed completed record.

Candidates use native verified rollback backups, generation preparation,
GENERATION_POINTER journal, atomic activation, postflight measurement and native
old-generation rollback. Final gates recheck all inputs, exact owned journal,
review scope and prepared bytes. A preactivation/postflight failure restores the
old generation; no financial or ownership approval is synthesized.

Provenance records policy, old generation/observation/hash, new observation/hash,
exact source key, old/new source-version stamps, acquisition fingerprint/time,
unchanged normalized-financial fingerprint, Preview and publication generation.
It explicitly identifies a new current state, not an old-version repair.

A dedicated acceptance adapter validates the actual completed typed receipt,
Test, journal, old/new generation lineage, full role integrity, exact review scope
and postflight result. The existing locked cleanup owner alone deletes the exact
three owned rollback backups. Changed evidence, foreign/extra backup files,
symlinks, hardlinks or wrong ownership reject cleanup. Prior immutable generations
and unrelated backups remain protected. Cleanup has an idempotent native receipt.

## Disposition and operator presentation

Successful native postflight finalizes only the selected ticker dispositions.
Current rebuild evidence is exact-bound to the new accepted observation and
payload. A healthy verified rebuild is ELIGIBLE even when separately counted
historical legacy evidence remains. Contradictory/incomplete current evidence
retains higher UNRESOLVED precedence; the rebuild marker cannot override it.
Normal current-view invalidation makes the disposition stale if its binding changes.
Historical observation counts remain evidence and are not summed as ticker statuses.

The existing disposition presentation shows:

- “Current provider state rebuilt from fresh authoritative source”
- “Historical accepted data was preserved”
- “Frozen historical review remains separate” when disjoint conflicts exist.

There is an explicit read-only administration assessment entry point, with strict
repair first. No ordinary one-click rebuild or render-time mutation was added.
Technical evidence stays in the existing Details evidence view.

## Validation and publication results

Results are recorded below after the current-state rehearsals and final gates.
`PROVIDER_PAYLOAD_COMPLETENESS_V1` remains disabled throughout this task.

### Focused verification

The final focused run passed **119 tests**, including 48 new policy, native
source/canonical, lifecycle, negative and presentation cases. These cover strict
repair first (without imposing rebuild-only MRQ prerequisites on strict repair),
metadata-only advancement, full capture, financial/fiscal/company/security/provider
identity drift, replaced/duplicate/ambiguous keys, stale acquisition/source/baseline,
unsafe journal, disjoint frozen review and collision, candidate/receipt tampering,
immutable publication, preactivation/postflight rollback, completed-queue recovery,
disposition/current-binding invalidation and exact cleanup ownership/idempotency.

Another **217 regressions** passed across exact repair review coexistence,
historical freeze, native Refresh/copy and production parity, WFRD parity,
publication authority, backup cleanup and Add/Remove. Another **199 tests** passed
across future ownership, scheduler Full Workflow, WFRD accounting-boundary review,
action-first presentation and the explicit capture-gap fixture. That last fixture
is also in the 119-test run: **536 distinct passing tests**, 537 passing executions
in these final verification runs. Two additional actual hobby-view render cases
verify both result presentations in the existing no-action history, preserved
secondary/frozen guidance, collapsed raw JSON and zero operator/state mutation.
No full suite was run.

The first concurrent lifecycle test run encountered the existing global taxonomy
lock owned by another regression process. The production preflight correctly
rejected the operation. Running the final focused set alone passed all 119;
no lock/recovery gate was removed or relaxed. Earlier development copies were
rejected when implementation file hashes changed before Test completion. They
are not publication receipts. Final Preview/Test evidence is generated only after
implementation and focused tests have stabilized.

### Fresh initial health

The live initial state was freshly confirmed as generation
`payload_repair_c76f86e26cbc7735_99b4b068a24f`, watermark `2026-10-28`, journal
COMPLETED / postflight PASSED / recovery NOT_REQUIRED. The 181-ticker ledger had
171 ELIGIBLE, 8 HISTORICAL_ONLY and 2 UNRESOLVED. Current-source full-schema audit
covered all 2,455 active accepted latest bindings in the unchanged 2,468-member
universe; exactly BMRA and NEOV were incomplete, with no unbound observation IDs
among those accepted bindings. The remaining universe members have no accepted
latest binding in that query and are not newly classified by this operation.

Observation evidence was separately counted: 12,942 legacy 29-key observations,
5,231 frozen accepted legacy observations; 867 provider observations carry retained
history status globally. The ledger cohort's retained observation count is 342.
These are overlapping evidence categories, not mutually exclusive ticker statuses.

Fresh full acquisitions bound BMRA ARQ/MRQ 40/40 and NEOV 20/23 records against the
112-field authoritative fundamentals schema. BMRA current 2027-Q1, source
2026-10-15 / reportperiod 2026-08-31, has metadata advancement 2026-10-16 →
2026-10-19. NEOV current 2026-Q4, source 2026-09-23 / reportperiod 2026-06-30,
has 2026-09-23 → 2026-10-29. All shared normalized financial values are equal;
83 raw fields are newly supplied for each new version. Fresh source factor is
explicitly 1 for both. Native fresh parent-equity USD inputs are 3,648,000 and
39,567,340 respectively. These are new-version source facts, never defaults or
backdated facts attributed to the old accepted observations.

### Final exact current-state Test

Preview: `2a684ef130c6a540de4adc560ab171ada468dc65d69a7cf86cc7dd507db2b16c`.

Test: `6f39e4cfedea9ccf9ef3044146e202946c9da4aaa9cb62de3507013ebafdaf97`. Native full V2, RP, RV and snapshot-reader validation passed. The final source/runtime/code baseline remained unchanged throughout Test.

| Ticker | New active observation | New metadata stamp | Native parent equity USD |
|---|---|---|---|
| BMRA | `7d9b7470b8fdc47c017feba15bbf2096cc9b2fa913142d226238db8a02bf406b` | 2026-10-19 | 3,648,000 |
| NEOV | `f964301d3c512efbcc878654a6d26730df9773901b8fe43a0d88d704ebc5fbfb` | 2026-10-29 | 39,567,340 |

Exact tested candidate role SHA-256:

- analysis: `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f`
- canonical: `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d`
- provider: `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f`

The independent row-level measurement confirms all unselected provider and
canonical rows, historical TTM data, and the generation ownership artifact are
unchanged. Each old 29-key current observation remains intact in the old immutable
generation. The 13 NEOV frozen conflicts are proven disjoint and remain OPEN.

### Disposable-copy native publication and cleanup

The final full-population clone passed exact Test, fresh-source revalidation,
immutable publication and postflight as generation
`current_rebuild_cc6d56097afb05678846b38dcfa9dcaf`. Both copied current
sources are full-shaped and both copied dispositions become ELIGIBLE. Old source
observations and every unrelated provider/canonical row remain preserved. NEOV's
13 frozen conflicts remain OPEN and unchanged; no frozen repair authority or
ownership approval was consumed. Native full analysis was rebuilt and validated.

The dedicated completed-publication adapter and native cleanup owner deleted
exactly three owned rollback backups, freeing **2,630,086,656 bytes**. A second
cleanup returned ALREADY_CLEANED, with no further deletion. The entire live source
baseline remained unchanged throughout the clone lifecycle. Generic failure
fixtures independently passed native preactivation/postflight rollback and
completed-queue recovery without republication.

### Explicit authorization and successful live publication

The user supplied an explicit visible-chat YES for the exact Preview/Test pair
above, including native parent-equity acceptance, immutable activation and cleanup
of only this operation's three rollback backups. The earlier attachment-only
approval-review rejection was superseded by that exact chat authorization.
No approval gate was bypassed.

The unchanged baseline and source-review scopes were freshly revalidated before
launch. Under native UI, production/shared-scheduler and taxonomy locks the
publisher reacquired authoritative full ARQ/MRQ histories and schema, required
exact source/schema equality with the approved acquisitions, and revalidated the
exact Test and baseline. No selected source, financial, identity, fiscal,
review-scope or eligibility delta was accepted. Acquisition timestamps alone may
differ; installed provenance retains the actual Test acquisition timestamp.

Native verified backups, immutable generation preparation, final baseline/review
and candidate-byte gates, atomic activation and postflight all passed.

- New active generation: `current_rebuild_2a684ef130c6a540de4adc560ab171ad`.
- Journal: COMPLETED.
- Postflight: PASSED, measured against the exact approved Test.
- Recovery: NOT_REQUIRED; production writes are not blocked.
- Watermark: `2026-10-28`, unchanged.
- Native cleanup: COMPLETED; exactly 3 owned rollback backups deleted,
  **2,630,086,656 bytes** freed. No unrelated backup was deleted.
- Old generation: `payload_repair_c76f86e26cbc7735_99b4b068a24f`, all three role hashes preserved.

Durable native receipts are under
`fundamental_reports/admin_runs/current_rebuild_2a684ef130c6a540de4adc560ab171ad/`:
`result.json`, `completed_journal.json` and `backup_cleanup.json`. They bind the
actual native publication, full Test/Preview, old/new lineage, review proof and
cleanup ownership. Temporary driver/copy evidence is excluded from the source commit.

| Ticker | Live disposition | Current payload keys | Current binding complete | Native current P/B reason |
|---|---|---:|---|---|
| BMRA | ELIGIBLE | 112 | YES | `OK` |
| NEOV | ELIGIBLE | 112 | YES | `OWNERSHIP_BASIS_UNVERIFIED` |

Both current dispositions are exact-bound and nonstale. Their new observation IDs,
source-version stamps and parent-equity values match the tested table above.
Ownership decisions and the generation ownership artifact are unchanged; current
P/B remains governed by the native ownership/valuation rules. Source completeness
does not synthesize an ownership approval.

NEOV's **13 frozen conflicts remain OPEN**, with its complete review fingerprint
identical to the prepublication snapshot. No frozen repair authority was consumed.
Every unselected provider/canonical row, historical TTM row, WFRD source and
canonical interpretation, active-universe record and all ownership/GE/RTX/T terminal
decisions remain unchanged. Every preexisting queue table except the selected
disposition ledger/audit is identical to the saved logical snapshot. The other
179 disposition rows and all prior disposition audit rows are identical; exactly
two new disposition audit rows and the typed completed rebuild record were added.

Market/global-analysis inputs and scheduler configuration hashes are unchanged.
The new Fundamentals analysis role is the exact tested native full V2/RP/RV rebuild,
including native calculation-date/current-price refresh. Historical provider,
canonical and audit evidence remains in the immutable old generation. No old
financial evidence was deleted, no financial value guessed, no factor defaulted,
and no publication-authority semantics changed. Runtime collateral mutation: NO.
`PROVIDER_PAYLOAD_COMPLETENESS_V1` remains disabled.

### Post-rebuild completeness health and concrete handoff

The fresh read-only audit covers all **2,455 active accepted latest bindings**
in the unchanged **2,468-member universe**.

- Active incomplete current-source tickers: **0**.
- Latest incomplete accepted bindings: **0**.
- Unresolved current-source dispositions in the legacy cohort: **0**.
- Ticker ledger: **173 ELIGIBLE, 8 HISTORICAL_ONLY**, 0 REPAIRABLE,
  0 INELIGIBLE_SOURCE_DATA and 0 UNRESOLVED.

Observation evidence remains separately countable:

| Evidence category | Count |
|---|---:|
| Legacy 29-key observations in active provider history | 12,940 |
| Frozen accepted legacy observations | 5,231 |
| Retained provider observations, all tickers | 867 |
| Retained observations in the 181-ticker ledger cohort | 342 |
| Newly rebuilt accepted current observations | 2 |

These categories overlap and must not be summed as ticker dispositions. The two
old current projections remain preserved in the prior generation; their
replacement removes two incomplete current bindings from the new active view.
No historical legacy population was purged to obtain zero current incompleteness.

**Remaining active-source data blocker: none.** The concrete remaining ingestion
contract gap is uniform faithful-capture enforcement: `validate_complete_history`
still accepts a normalized 29-key dictionary as COMPLETE, Refresh's native
inserter retains its normalized-only fallback for existing callers, and bulk/local
reuse does not attest original full capture. The focused fixture proves the gap
and proves the new rebuild rejects it against the authoritative schema manifest.
Completeness hardening must cover those entry points and distinguish local field
loss from genuine provider revision before freeze/ownership comparisons while
preserving all legacy historical evidence. This task does not enable that rollout
or return an abstract readiness label.

Only task-owned source, tests and documentation are committed. Runtime databases,
queues, journal, generations, configuration, copies, backups, temporary evidence
and unrelated worktree files are excluded. No push is performed.
