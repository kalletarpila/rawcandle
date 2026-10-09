# P1.1 — Historical publication completeness audit

As of **2026-10-09**, Europe/Helsinki. Audit-only; no retry, drain, reviewed-plan
creation, apply, refresh, or financial calculation was run.
Starting committed HEAD: `a9bb48da3e4db47a6737b9812ef9fc8ee22aa47c`.
Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.

## Authoritative population and scope

The full authority table contains **16,242 company/fiscal-quarter
cases: 12,890 VERIFIED and 3,352 open**. Natural identity is
`(company_id, fiscal_year, fiscal_quarter)`, not ticker. Every retained authority
row with `status <> 'VERIFIED'` was selected before applying any date partition.
The live CHECK model contains only VERIFIED, UNRESOLVED, NOT_FOUND and AMBIGUOUS;
no other open status is present. VERIFIED rows are comparison controls only.

There are also **73,684 canonical
quarters without an authority row**. These are not silently labeled NOT_FOUND or
included in the population of existing open authority cases. This audit is a
complete census of the retained authority table, not a claim that all financial
history has already received an authority assessment. The ordinary selector can
include missing authority in its recent scope; its current recent selection has
no such extra cases and agrees exactly with this partition.

| Stored status | Full open | Recent | Historical |
| --- | --- | --- | --- |
| UNRESOLVED | 842 | 21 | 821 |
| NOT_FOUND | 1882 | 129 | 1753 |
| AMBIGUOUS | 628 | 2 | 626 |
| TOTAL | 3352 | 152 | 3200 |

Recent means the existing selector's
`max(coalesce(first_public_result_date,''), coalesce(source_availability_date,''))`
is between **2026-08-10 and 2026-10-09 inclusive**. Historical means outside that
window; every historical date here is earlier than the cutoff, with no missing
or future context dates. `select_candidate_scope(..., [], as_of_date='2026-10-09',
retry_days=60, retry_max_quarters=None)` was called for independent enumeration
only. The ordinary 60-day horizon, cap **100**, uncapped NEW_THIS_REFRESH and
operator-only manual drain remain unchanged. Enumeration did not dispatch work.

Historical context dates: **2024-05-23–2026-08-07**.
Historical period ends: **2024-04-27–2026-07-05**.
Recent context dates: **2026-08-10–2026-09-29**.
Recent period ends: **2025-12-31–2026-08-15**.
Authority quarter IDs equal their current canonical quarter IDs and all open
canonical quarter identities are ACCEPTED.

## Current resolver evaluation and its limits

The current committed `SecClient.item_2_02_filings` and
`resolve_sec_filings_detailed` were used directly, without `enrich_database`,
`apply_resolution`, a worker, or an authority writer. Source hashes were checked
against HEAD. The input scope includes full retained open company history,
including pre-2025 fiscal years; the ordinary 180-day filing/quarter matching
window is unchanged. All current open quarters for each company are supplied
together, so a filing matching multiple quarter contexts is not made unique by
a single-quarter shortcut.

Official SEC submissions and relevant archived batches were read for exactly
**1070 historical-population companies**. Acquisition is bounded to
the union of their historical quarter-end-through-180-day windows, capped at
2026-10-09. Only current eligible Item 2.02 8-K parents and the existing bounded
same-accession exhibit path are automatically acquired. Metadata for other forms
is retained for source research, without authorizing them. Existing immutable
SEC document captures are reused where available. Acquisition completed for
**3,200/3,200 historical cases**;
company failures: **0**.
Network/cache accounting: `{"fresh_json_reads": 1071, "fresh_text_reads": 4653, "retained_immutable_html_hits": 161}`.

Every complete captured acquisition was independently replayed through the same
committed resolver twice. Every historical case also received a reproducible
Policy V1 diagnostic over its available evidence. Missing reviewed observations
produce REVIEW; an empty candidate inventory produces NOT_FOUND only within that
input, not proof that no publication exists globally. The separate
`policy_v1_diagnostic_status` preserves this distinction. Ordinary recognition is
not silently promoted into a reviewed semantic observation.

| Current resolver diagnostic | Cases |
| --- | --- |
| AMBIGUOUS | 630 |
| NOT_FOUND | 1113 |
| REVIEW | 2 |
| UNRESOLVED | 574 |
| VERIFIED | 881 |

The raw ordinary preview has **881 unique results**. The actionable
`CURRENT_RESOLVER_CAN_SOLVE` partition has **599**: cases with a selected
exact-key candidate, without unresolved competing context, unresolved durable
same-rank conflicts, or a contrary reviewed lineage result. **282**
raw unique cases are held because the existing reviewed wrapper vetoes unresolved
competing context; **0** are held because durable competing events
lack reviewed exclusion/precedence proof. These audit holds do not alter ordinary
resolver semantics. Future application must validate current generation, exact
sources/times, eligibility and the applicable existing reviewed-plan contract.
No evidence, plan or authority timestamp was installed.

This is not an exhaustive issuer crawl or a new 6-K recognition implementation.
NOT_FOUND means no candidate under the inspected current acquisition path;
it does not establish absence of an issuer release, supported reviewed foreign
filing, or another authorized reviewed source. Consequently no case is assigned
TRUE_NO_PUBLICATION_FOUND merely from an empty 8-K result.

The exact comparison also identifies **264** historical cases with a current
and stored timestamp difference for the same accession, covering **538** accession
comparisons: **334** current values are four hours later and **204** are five hours
later. All 264 are in LEGACY_AMBIGUITY and remain held. The CSV retains both
instants and the accession mismatch flags. This is a bounded representation
discrepancy finding, not a claim of an EDGAR-wide defect, a new precedence rule,
or authorization for a blanket offset. No timestamp was repaired or selected
by earliest/latest. Ordinary diagnostics retain the committed parser's result;
a later reviewed phase must resolve the actual source-clock evidence.

## Mutually exclusive research classification

| Primary category | Historical cases |
| --- | --- |
| CURRENT_RESOLVER_CAN_SOLVE | 599 |
| RESOLVER_GAP | 10 |
| TRUE_NO_PUBLICATION_FOUND | 0 |
| LEGACY_AMBIGUITY | 630 |
| STALE_OPEN_STATE | 0 |
| INSUFFICIENT_EVIDENCE | 1961 |
| OTHER | 0 |

- CURRENT_RESOLVER_CAN_SOLVE: an exact candidate is available under current code;
  no resolver change is simulated. These are diagnostic stale-open opportunities.
- RESOLVER_GAP: retained document-backed prior evidence still identifies a
  recognition/authorized-form limitation; metadata alone never establishes a gap.
- LEGACY_AMBIGUITY: multiple plausible candidates or unresolved durable conflicts
  remain. This is a candidate-conflict category, not proof that every event has
  already passed modern semantic eligibility. No earliest/latest rule is used.
- INSUFFICIENT_EVIDENCE: covers absent authorized candidates, missing semantic or
  competing-context proof, and stale reviewed bindings. It is an explicit result,
  not a forced no-publication conclusion.
- STALE_OPEN_STATE is reserved for a proven already-terminal durable result that
  the authority row failed to reflect. **0** such cases were demonstrated: open
  authority timestamps/selected evidence are NULL and their durable evidence is
  conflict evidence, not an installed accepted terminal decision. The separate
  `stale_open_now_deterministic` flag identifies **599** currently solvable
  stored-open mismatches without double-counting primary categories.

Resolver-gap cases:

| Company / ticker | Fiscal quarter | Current reason |
| --- | --- | --- |
| 421 | CCLD 2026 Q2 | QUARTER_MATCH_FAILED |
| 425 | CCSI 2026 Q2 | QUARTER_MATCH_FAILED |
| 499 | CMP 2026 Q3 | QUARTER_MATCH_FAILED |
| 648 | DCO 2026 Q2 | QUARTER_MATCH_FAILED |
| 844 | FCX 2026 Q2 | QUARTER_MATCH_FAILED |
| 1967 | SD 2026 Q2 | QUARTER_MATCH_FAILED |
| 2108 | SVV 2026 Q2 | QUARTER_MATCH_FAILED |
| 2253 | UHS 2026 Q2 | QUARTER_MATCH_FAILED |
| 2275 | USAC 2026 Q2 | QUARTER_MATCH_FAILED |
| 2428 | XRAY 2026 Q2 | NO_ITEM_2_02_FOUND |

The CSV supplies exact candidate accession, parent URL/time, source/rank/confidence,
matching method, stored competing evidence, mismatch reason, identity notes and
input/diagnostic fingerprints. Blank selected timestamp means no selected event;
it is never filled with a provider date or first-seen estimate.

## Age cohorts

Age is **2026-10-09 minus the selector context date**, not publication age,
first-seen age, time open, or cumulative retry age. These missing authority fields
are not fabricated. Fiscal period end and durable last-update time remain separate.

| Context-age days | Historical cases |
| --- | --- |
| 61-90 | 232 |
| 91-180 | 542 |
| 181-365 | 1141 |
| >365 | 1285 |

## Source / form patterns

Source families below are mutually exclusive descriptions of the candidate or
bounded metadata available to this audit. Metadata-only foreign forms do not
receive SEC_FORM_6K_RESULT authority automatically.

| Evidence/source family | Cases |
| --- | --- |
| 6-K | 1 |
| 6-K_METADATA_ONLY | 268 |
| 8-K | 2101 |
| 8-K/A_REVIEW_REQUIRED | 1 |
| NO_ELIGIBLE_8K_CANDIDATE | 829 |

| Family | Primary research category | Cases |
| --- | --- | --- |
| 6-K | INSUFFICIENT_EVIDENCE | 1 |
| 6-K_METADATA_ONLY | INSUFFICIENT_EVIDENCE | 268 |
| 8-K | CURRENT_RESOLVER_CAN_SOLVE | 599 |
| 8-K | INSUFFICIENT_EVIDENCE | 863 |
| 8-K | LEGACY_AMBIGUITY | 630 |
| 8-K | RESOLVER_GAP | 9 |
| 8-K/A_REVIEW_REQUIRED | RESOLVER_GAP | 1 |
| NO_ELIGIBLE_8K_CANDIDATE | INSUFFICIENT_EVIDENCE | 829 |

Relevant publication/financial forms in each exact 180-day window (non-exclusive; one case may have
several forms): `{"10-K": 1303, "10-K/A": 200, "10-Q": 2897, "10-Q/A": 67, "20-F": 97, "20-F/A": 7, "40-F": 23, "6-K": 273, "6-K/A": 25, "8-K": 2894, "8-K/A": 384, "NO_RELEVANT_FORMS_IN_BOUNDED_WINDOW": 16}`.

**378** historical cases use the current bounded linked-results-exhibit context
(non-exclusive with the parent 8-K family). Exact issuer-source candidate cases: **0**
in this historical population's retained/evaluated evidence; that is not evidence
that issuer releases do not exist.

8-K source is rank 3/HIGH; exhibits supply context only, with the parent acceptance
remaining the candidate boundary. Reviewed Form 6-K stays rank 2/MEDIUM and is
not an 8-K alias. No issuer source is synthesized from SEC metadata or provider
symbols. Generic 8-K/A, 6-K and annual/half-year packages remain subject to their
existing gates. Cases with no recognized 8-K generally require targeted official
issuer/foreign-filing evidence research, while multi-8-K conflicts require event
scope and typed precedence review rather than more chronology-based retries.

## Identity, perimeter and already-reviewed work

All joins use company/fiscal identity, current canonical period, and unique active
reporting CIK; ticker equality alone is not evidence of case equality. Identity
flags in the CSV are research warnings, not edits or proof of a wrong issuer.
Recorded structural events affect **13** historical cases: **8** for company 82,
AIHS→VAI (business-comparability review), and **5** for company 1304, LIXT→NMAD
(reverse merger / major business change). They need time-qualified issuer and
consolidated-perimeter review. Other recorded EQR→VMRK, ISSC→IA and BBBY→NXH
transitions have **0** historical-open cases in this population. The existing
company-level CIK match can recognize a filing; it cannot by itself establish
continuity of the economic reporting perimeter.

The Phase 77 official identity witnesses also cover companies with older
historical-open quarters. The CSV records the reviewed official security type,
provider-type conflict, and whether each older period falls within the reviewed
coverage boundary. It does not backdate the witness into unproven periods.
IQMX has **four historical-open quarters** with an explicitly UNCERTAIN temporal
chain; the later FY2026 Q2 issuer-handoff result is a different quarter and is not
applied to them. Common/ordinary-share issuers mislabeled ADR by provider metadata
(including MKDW, MLGO, HOLO, NEGG, TSEM, NBIS, BTDR, CAMT and NVMI) retain their
reviewed comparison flags. SCNI's reviewed ADS/provider-domestic mismatch is also
retained. These company-level identity observations do not donate quarter-specific
financial or publication evidence to older quarters.

The local security table does not record official ADR/direct-common type or a
full historical reporting-perimeter chain. Unrecorded valid_from dates are
explicitly flagged; no first-listing date is inferred. Except where reviewed
6-K inputs provide a chain, ADR/perimeter sufficiency remains unproven. Retained
company/ticker aliases and provider-security IDs are inspected without treating
aliases as new companies or implying a known identity defect.

Of the **51** historical cases that overlap the earlier 278-case audit, **46**
have changed quarter IDs while retaining the same natural key and period. SEC
recognition can be regenerated for the current quarter; old reviewed plans or
quarter-bound inputs are not silently rebound.

**CLLS (company 2506, FY2026 Q2)** is the historical case in the reviewed foreign
cohort. Phase 81 proved an economic chain using existing typed relations. Replaying
that frozen input against today's quarter ID triggers the current binding gate,
so the live row is intentionally held here rather than claimed ready for apply.
This is an evidence-binding refresh requirement, not a resolver-code gap or a
new generic earliest rule. The old frozen result remains a research control: current code reproduces UNIQUE
at `2026-08-06T20:30:05Z` against the original binding, while current-quarter
inputs reproduce REVIEW_FROZEN_EVIDENCE_BINDING. All **284** available prior audit
document hashes and the Phase 81 reviewed-case hash were revalidated.
**AMR (company 145, FY2026 Q2)** remains under the existing Policy V1 REVIEW;
Phase 75 found incomplete preliminary consolidated-revenue proof. No generic
candidate-count rule overrides that reviewed result. Other 6-K/issuer handoff
cases are compared by exact quarter: they are recent or already terminal and do
not become historical drain candidates through ticker equality.

## Prior recent-open baseline comparison

A read-only comparison with the later reviewed-apply generation
`publication_drain_20261007T093516Z_fd654a20` finds all **3,200** current historical
keys already present with exactly the same stored statuses. Prior VERIFIED →
current historical-open regressions: **0**. Thus these are not lost terminal
authorities from that generation.

The Phase 64 exact baseline had 278 open cases (53 UNRESOLVED, 199 NOT_FOUND,
26 AMBIGUOUS). Today **75 are VERIFIED** and
**203 remain open**. Of the remaining cases,
**51 are historical** and the other
**152 are recent**.
**3,149 historical cases were outside that
specific accepted recent-open audit scope**. This does not mean they were never
within any rolling 60-day window during their lifetime; no such lifetime scope
history is recorded. Earlier gap/ambiguity/evidence counts are not reused as
current totals.

## Hypothetical impact and next phases

Applying only the diagnostic CURRENT_RESOLVER_CAN_SOLVE partition in a future
safely reviewed phase would add **599 VERIFIED**, yielding
**13,489 VERIFIED** and **2,753 open**
across the same 16,242 retained authority cases. This is arithmetic
simulation, not an apply-plan validation or a claim that evidence stays fresh.
No hypothetical code changes for resolver gaps are included.

| Remaining open status | Hypothetical cases |
| --- | --- |
| AMBIGUOUS | 628 |
| NOT_FOUND | 1514 |
| UNRESOLVED | 611 |

| Next phase | Cases |
| --- | --- |
| L1_REVIEWED_DETERMINISTIC_DRAIN | 599 |
| L2_RESOLVER_RECOGNITION | 10 |
| L3_EVIDENCE_RESEARCH | 1961 |
| L4_TRUE_NO_PUBLICATION | 0 |
| L5_LEGACY_AMBIGUITY | 630 |

Recommended first phase: **exact-key reviewed validation of L1**, with source,
current-generation and event-scope binding before any separately authorized apply.
Keep unresolved competitors, durable conflicts, CLLS's stale input binding and
all L2–L5 cases out of that initial partition. L2 needs bounded recognition/policy
research; L3 needs targeted issuer/SEC documents or missing reviewed context;
L5 needs explicit event eligibility/typed precedence, not routine retries.
L4 has zero proven cases; unknown absence is not irreducibility.

## Reproduction, validation and no-write evidence

Population SQL (read-only connection, `PRAGMA query_only=ON`):

```sql
SELECT a.*, q.period_end,
       max(coalesce(q.first_public_result_date,''),
           coalesce(q.source_availability_date,'')) AS context_date
FROM v4_result_publication_authority a
JOIN v4_quarter q USING(company_id,fiscal_year,fiscal_quarter)
WHERE a.status <> 'VERIFIED'
ORDER BY a.company_id,a.fiscal_year,a.fiscal_quarter;
```

Validation passed: independently reproduced full census, exact selector partition,
status and age reconciliation, 3,200 unique CSV natural keys, one primary category
per row, repeated pure current-resolver outputs, exact selected candidate binding,
and hypothetical status reconciliation. The committed resolver/policy/schema and
retry-selector source hashes remain unchanged. No source helper is retained, so
no broad workflow tests or pytest suite were run; deterministic audit assertions
only. Full suite: **NO**.

Historical key/status SHA-256: `fe24d9a3ff37da1f00093e0d9bbbb0df8dc359b30649a2083f29889e54943e60`.
Complete authority logical SHA-256: `41e710eb4dca4418d48e403fde8c70777efa1c02be24cb48e7eb3a6a4ccce577`.
CSV SHA-256: `7c5786ca641899e5bbadb9b0198c318d76eda64610a5cab8baf3a7898df2ea5a`.

Before/after byte fingerprints (all equal):

| Protected artifact | SHA-256 |
| --- | --- |
| provider | fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981 |
| canonical | 996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845 |
| analysis | 9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c |
| pointer | 30c08f22b5b9b2a3cbb07f5183d2946e3ed8b980634d0e54255936b9310b5de3 |
| queue | 84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b |
| scheduler | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |
| forecast_scheduler | 67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79 |
| journal | 6f7e625fe10c0ab98c31902bb34d4e7a0c24ea2c94b840497b0459a07817aa67 |
| queue-wal | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| queue-shm | fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb |

Provider watermark is unchanged: published source watermark
`2026-10-08`, successful run
`20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. Active pointer, journal,
Review Queue DB, both scheduler configs and SQLite sidecars were checked as well
as all three active financial databases. No authority mutation, Review Queue
mutation, financial write, watermark advance, schema/resolver change, retry cap
or horizon change, scheduler action, or active-generation switch occurred.

Temporary acquisition and replay inputs live under
`/tmp/historical_publication_p11/`; prior reviewed source captures stay in their
existing temporary locations. They are not committed. Diagnostic fingerprints
bind the actual captures, not an assertion that future SEC responses are identical.
Reproduction in this session uses `replay_audit.py` followed by
`final_validation.py` in that directory; two complete replays produced identical
row/summary artifacts. If temporary captures are lost or stale, sources must be
recaptured and reviewed before future application. No reviewed binding is invented.

Lineage: [13G.3.64 persistent-open audit](fundamentals_v4_phase13g3_64_persistent_open_publication_audit.md), [13G.3.65 recognition](fundamentals_v4_phase13g3_65_sec_recognition_improvements.md), [13G.3.72 Policy V1](fundamentals_v4_phase13g3_72_publication_event_policy_v1.md), [13G.3.74 reviewed domestic apply](fundamentals_v4_phase13g3_74_live_policy_v1_reviewed_apply.md), [13G.3.75 domestic holdouts](fundamentals_v4_phase13g3_75_abat_optt_amr_evidence_completion.md), [13G.3.80 reviewed Form 6-K apply](fundamentals_v4_phase13g3_80_live_form6k_reviewed_apply.md), [13G.3.81 Form 6-K holdout review](fundamentals_v4_phase13g3_81_form6k_holdout_resolution.md).

Artifacts: [fundamentals_v4_historical_publication_completeness_audit.csv](fundamentals_v4_historical_publication_completeness_audit.csv) and [fundamentals_v4_historical_publication_completeness_summary.csv](fundamentals_v4_historical_publication_completeness_summary.csv).
Only this report and compact audit/summary CSVs are committed. Raw filings,
databases, runtime logs, caches, temporary helpers and pre-existing unrelated
worktree changes are excluded. Push: **NO**.
