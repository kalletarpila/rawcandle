# SIMPLIFY-01 — Fundamentals Refresh simplification audit

**Recommendation: simplify the existing generation workflow; do not build FIX8C's
additional acceptance issuer.** Retain one explicit exact-candidate publication
confirmation, one generation authority and the existing durable journal. Use the
retained immutable OLD generation for pointer rollback. Implement nothing in this
audit. This recommendation changes future workflow infrastructure, not financial
acceptance or the twelve approved identity decisions.

## Verified current state and scope

Starting HEAD `0a43dcd0f030356760d011bf636990c2c2a8ac70`, branch
`chore/ignore-backups`; no conflicting source modifications. Existing unrelated
runtime/untracked work is excluded. Read-only inspection observed generation
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`, universe
`3b8121b74c852f08575fa1e2b70004e6`, journal
`COMPLETED / PASSED / NOT_REQUIRED`, and Fundamentals disabled with
`SNAPSHOT_V1 / FULL_WORKFLOW`. The scheduler configuration records 04:30 Helsinki;
the operator specifies 04:45. Neither is changed. No work is scheduled by this
audit, and no writer/taxonomy/scheduler leases or network calls were needed.

Governing reports: [FIX8](fundamentals_fix8_native_universe_reconciliation_2026-11-14.md),
[FIX8A](fundamentals_phase3d_fix8a_taxonomy_sidecar_compatibility_2026-11-14.md),
[FIX8B](fundamentals_phase3d_fix8b_commit_bound_acceptance_2026-11-14.md).
Additional reads were limited to their concrete generation, source-validation,
SEC and recovery dependencies. No financial source bodies or 3.2 GB decision
artifact were loaded. Current-state inspection is not a fresh financial validation.

## Existing architecture, in plain language — VERIFIED

`snapshot_workflow.py:start/advance` coordinates acquisition, local validation,
one inactive BUILD, publication and postflight. `refresh_update.py` stores a
validation receipt and `decisions.json`, updates that receipt with the prepared
candidate, and uses `_publish_candidate` for activation. `SnapshotEnvironment`
adds request/source checks and a separate publication authorization file.

The financial databases already form one generation. In `generations.py`,
`prepare_generation_from_candidates` **moves**, rather than copies, the three
candidate files into a generation directory, validates them and writes its
manifest. `activate_generation` checks expected OLD and role integrity, then
`_atomic_manifest` fsyncs and atomically replaces the active pointer. Publication's
external native lock is essential: the pointer helper alone is not a concurrent
compare-and-swap transaction.

`publication_journal.py` records intent before the pointer switch and recovers
interruption. Its generation-pointer recovery reactivates OLD. However, it first
requires separately copied backup files and compares OLD against their hashes.
`refresh_production._verified_backups(..., immutable_generation=True)` actually
copies all three OLD files. The present recovery branch does **not** repair a
corrupt OLD file from those copies; it reopens the original OLD generation.

FIX8 adds a universe-specific coordinator using that same atomic engine, but also
requires a separate `DISPOSABLE_ACCEPTANCE` receipt. FIX8B established that its
required native issuer does not exist. Building an issuer would satisfy this
extra prerequisite without simplifying publication itself.

## Minimum necessary architecture — RECOMMENDATION

**FETCH → VALIDATE → BUILD B → VERIFY B → atomic A→B → retain A until accepted → cleanup.**
Keep A unchanged and protect the source-use intervals with existing locks. Verify
B after its last financial/publication-date mutation. The activation confirmation
must identify B and expected A. Persist the existing journal intent before the
switch; perform postflight and record completion afterwards. Pre-switch failure
leaves A active. Interrupted or failed activation resolves the journal and verifies
A before restoring its pointer. Recovery must accept only this operation's A/B
pointer states; an unexpected newer C must STOP, not be overwritten by rollback.
Postflight success is not permission to delete A:
operator acceptance and absence of pending recovery/reference obligations are
separate cleanup prerequisites, recorded in existing operation metadata.

Retain at activation: expected A ID/manifest and valid OLD roles; exact B ID and
role manifest/hashes; source snapshot and immutable universe/version/selection
binding; financial/model policy and consumed review authority; current scoped
market/taxonomy dependency binding; explicit operator confirmation; writer lease
and journal state. Relevant builder/model changes invalidate stale candidates.
A documentation-only HEAD change should not create another approval ceremony.
Use existing candidate/control metadata, not a new receipt or registry.

| Mechanism | Real protection and overlap | Recommendation / what removal must preserve |
| --- | --- | --- |
| One generation manifest + atomic pointer | Prevents mixed provider/canonical/analysis publication; identifies exact bytes | RETAIN; verify complete B and expected A under the writer lease |
| Native writer/scheduler/taxonomy protection | Excludes conflicting publication and drifting live dependencies | RETAIN scoped protection; never hold it across acquisition/cooldowns |
| One durable publication journal | Distinguishes crash-before/after-switch and unfinished postflight | RETAIN and simplify pointer-mode records; the pointer alone cannot prove completion |
| Extra immutable-OLD backup copies | Independent duplicate bytes and hash evidence; pointer recovery still uses original A | RETIRE for newly qualified pointer-mode operations; verify and pin A directly instead |
| Legacy ROLE_REPLACEMENT backups | Restore files actually overwritten in place | RETAIN for those callers and unresolved historical journals; deleting them loses their recovery mechanism |
| Validation/build receipt + publication grant + journal authorization | Bind financial decisions/candidate and operator intent, but repeat control authority | COMBINE into existing candidate/control state plus one explicit B/A confirmation and journal reference; retain financial decisions and real review approvals |
| FIX8 `_qualification` / proposed FIX8C issuer | Attests code/tests separately; does not itself establish candidate economics | RETIRE this extra per-operation test authorization requirement; keep regression tests and native candidate/identity/economic verification |
| Snapshot/SEC manifests and review evidence | Reproducible data, attribution, dates and corruption detection | RETAIN; verification results are not permission to accept missing or corrupted source data |

Backup removal is **not** a global deletion of `_verified_backups`: its callers
include `refresh_update`, `universe_reconciliation`, legacy `refresh_production`,
`universe_removal`, `remove_tickers`, provider payload/backlog workflows,
`current_state_rebuild` and ownership publication. Change only the qualified
GENERATION_POINTER path and its recovery consumer. Preserve old journal decoding
and all referenced backup files until their real obligations end. If A is not a
verified retained immutable generation, do not use the no-extra-copy path. This
removes redundant local rollback copies, not an independent disaster backup policy.

## Universe handling and FIX8C — RECOMMENDATION

Choose option B: existing candidate verification + explicit operator authority +
native activation/postflight. Do not implement another commit/OLD/candidate-bound
acceptance issuer solely to satisfy FIX8's current `_qualification` predicate.
Removing that predicate is a future qualified source change, never a bypass in
this audit or permission to activate today.

Keep FIX7's twelve company/security/Sharadar choices and companion restrictions
unchanged. The versioned selection tables live in the canonical role, so they can
be installed by one **identity-only financial generation B**, with provider and
analysis contents unchanged and canonical non-universe economics preserved.
Reuse the current FIX8 selection/equivalence checks and the one native activation
engine; do not introduce an independent universe pointer or publication journal.

A one-time identity-only operation remains the simplest bootstrap: current Refresh
discovery needs the corrected selectors **before FETCH**. Installing them only at
the end of the first financial BUILD cannot fix that acquisition scope. Combining
both into one live run would require prospective-universe acquisition authority
that does not currently exist. Avoid that extra design. After this bootstrap,
normal Refresh uses the single installed financial-generation universe. No new
security admission, companion financial duplication, StockCore synchronization or
review-approval transfer is permitted.

## Performance evidence and bounded work — VERIFIED / RECOMMENDED

The original UPDATE's `phase3d_resume2_operator_report.md` records VALIDATE
3,926.219 s (65m26s) and observed RSS high-water 22.979 GiB, including decision
serialization/readback. Its retained `decisions.json` is currently
**3,203,120,851 bytes**. This was a historical incorrectly scoped run, before later
scope fixes; these are not measured current-HEAD timings or a speedup prediction.

Concrete current duplicate paths:

- `open_snapshot` and immediately following `validate_preflight` both call
  `_verify_snapshot`. That walks checkpoints, parses bodies/captures and checks
  coverage through `_validate_checkpoint`. Workflow and `refresh_update` repeat
  this pair; BUILD/publication `_assert_inputs` opens/preflights again.
- VALIDATE loads both dimensions and current histories, then
  `compare_source_history` reloads them, revalidates complete history and computes
  another merge. `_compare` separately builds a merge. Some comparison axes differ
  (source-window versus financial/as-of policy): share loaded records and common
  primitives, not blindly substitute one decision for another.
- `read_slot` walks plan/index references for each requested slot; build one small
  slot/index map per phase rather than repeatedly searching unchanged metadata.
- `decisions` serializes the same classifications under `changes` and again under
  `safe`, `held.change` or `global.change`; `_load` hashes then fully decodes that
  file at later handoffs. This is proven repetition; its exact fraction of the
  historical RSS/time was not separately measured.

Already simplified: `_compact_plan` stores row references instead of merged rows;
per-ticker source-history checking does not rehash all OLD databases; the earlier
parent-evidence performance fix already uses compact child references. Keep these
improvements. Do not recreate them or blame the parent for the remaining child
artifact. Do not skip baseline protection for OLD names outside incoming FETCH.

| Work | Proposed owner and frequency |
| --- | --- |
| Transport, identity, coverage and body/capture correspondence | Once when accepting each capture; once per consumed slot in a later independent verification phase, with its loaded rows reused |
| Full snapshot graph validation | One verified open per unchanged phase, combining open + preflight; age/OLD/version checks remain cheap separate checks |
| Financial/history classification | Once per ticker in VALIDATE; share loaded OLD/NEW across financial/source-window checks; retain every policy decision |
| Decision evidence | One sequential detail record per ticker in existing run storage; compact `decisions.json` partitions contain references, identities, approvals and plan keys, not repeated payload trees |
| Complete generation integrity/economics | Once on final B before activation; merge redundant same-scope candidate checks. Recheck bytes on delayed/resumed activation and recovery; postflight verifies pointer/role identity and required preservation |

Never turn a cached hash into semantic validation. Reuse only the actual verified
rows in a protected phase; do not persist an unchecked “verified forever” bit.
After restart, delay, drift or detected corruption, reverify consumed bytes and
invalidate affected decisions/candidates. Final B corruption must stop activation.
Keep hashes bound to actual immutable artifacts, not merely their names/stat data.

## SEC — VERIFIED / RECOMMENDED

The retained SEC manifest verifies **1,654 scopes, 941 actual HTTP requests and
1,220 budget-exhausted outcomes**. Its 2,161 request-map entries include errors;
they are not 2,161 HTTP calls. `sec_snapshot.capture` retains the initial start time
across pending resumes, subtracts wall-clock elapsed time from 300 seconds, caches
errors, and seals a manifest even after the remaining scopes exhaust the budget.
A sealed manifest is subsequently returned unchanged. Thus the current lifetime
wall-clock ceiling is bounded but does not provide useful large-run resumption.

Keep 300 seconds as a **per-invocation acquisition slice**, with an explicit bounded
request/attempt allowance in the existing pending state. Reuse the same UPDATE,
plan, captured bytes and completed URLs/scopes. Budget exhaustion means PAUSED with
remaining work, not a terminal missing-document finding. Retry only eligible
transient/budget outcomes under the existing limiter/backoff and recorded attempt
counts; retain explicit permanent/unresolved outcomes. Seal when scope accounting
is terminal, with true missing evidence explicit. Required publication evidence
still blocks the applicable financial acceptance; never invent dates. Keep source
freshness/168-hour expiry independent of slice budgets; an expired snapshot needs
fresh acquisition, not refreshed timestamps. Use current `pending.json`, immutable
bytes and `SecClient`; no HTTP archive/framework or automatic live retry here.

## One implementation plan — maximum three phases

| Phase / exact affected components | Reduction and measurable acceptance | Invariants, tests, write boundary and risk |
| --- | --- | --- |
| **1. One publication/recovery path:** `universe_reconciliation.py`, `refresh_update.py`, `snapshot_environment.py`, `publication_journal.py`, `_verified_backups` pointer callers and `generations.py` | Remove FIX8's extra acceptance requirement without implementing an issuer; combine workflow publication authorization into existing candidate state; zero extra OLD role copies for qualified pointer operations; one journal and exact B/A confirmation. Reuse FIX8 for one-time universe bootstrap | Preserve twelve choices, identity/economic/history checks, stale-candidate refusal, A retention, native locks/fsync and explicit intent. Disposable tests: all twelve, held/OLD preservation, wrong B/A or unexpected active C, crashes before/after switch, missing/corrupt A/B, old-journal recovery and cleanup refusal before acceptance. Writes: inactive B first; only confirmed activation changes journal/pointer. Risk: breaking shared recovery readers or removing genuine consent; stop if safe backward compatibility fails |
| **2. One bounded validation pass:** `acquisition_snapshot.py`, `refresh_update.py`, `snapshot_workflow.py` and their existing report readers | One graph verification per unchanged phase; reuse two dimension loads rather than reload for source comparison; one detail record per ticker, compact partitions; BUILD/report readers never decode the entire large detail tree. Measure pass counts, output bytes, RSS and time on a retained scoped fixture; do not promise a timing multiplier | Same safe/local/global and review outcomes, accepted dates/history and corruption detection. Test equivalent decisions, quarantine safe peers, OLD-only names, source tampering after verification, restart/drift and review-evidence bindings. Writes: acquisition/validation evidence and permitted review observations, then inactive B; production switch still phase 1. Risk: lost diagnostics or differing policy axes; stop on any acceptance difference |
| **3. Resumable SEC slices:** `sec_snapshot.py`, its `snapshot_workflow.py` call site and existing `SecClient` only as needed | Same pending capture resumes across bounded slices; completed successful URLs fetched once; budget-pending scopes are not sealed as 1,220 terminal failures. Measure known-request counts and remaining scopes over two slices | Preserve pacing/retries, identity/document/date semantics and freshness. Fake-clock/offline tests: pause/resume, transient retry, permanent missing document, rate limit, expired snapshot and foreign scope. Writes: source evidence/checkpoints only until normal B validation; no separate publication boundary. Risk: unbounded retries or stale source evidence; enforce persistent attempts and existing expiry |

Leave financial calculators, financial acceptance thresholds, actual financial
review approvals, identity evidence/selection tuples, provenance/publication-date
rules, retention and inactive-history gates, ticker-local quarantine, immutable
source bodies, normal scheduler configuration and StockCore untouched. Keep compact
market/protected taxonomy readers; change only proven redundant handoffs. No model
rewrite or wholesale UI/legacy-workflow retirement is proposed.

**STOP:** no retained valid A; incomplete/misattributed B; lost OLD history/dates;
wrong representative or new admission; stale approval/input/candidate; inability
to exclude a conflicting writer; unresolved legacy recovery reference; corrupted
source evidence; missing mandatory SEC evidence; removal of explicit publication
consent; or a change requiring a broad financial-model rewrite. These are actual
financial/recovery boundaries, not reasons to build another acceptance subsystem.

Audit outcome: recommendations only. Source changes, production DB/review/manifest
writes, live UPDATE/FETCH, Sharadar/SEC calls, scheduler changes and tests: **none**.
Only this intentional Markdown report is committed. No runtime cleanup or push.
