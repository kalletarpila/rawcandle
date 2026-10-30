# Legacy payload remediation and Fundamentals eligibility — 2026-10-30

## Scope and authorization

The original STOP population is 181 tickers and 13,113 exact legacy 29-key
provider observations. This task authorizes exact-source repairs after a full
classification, disposable-copy rehearsal and the existing publication gates.
It does not authorize guessed financial repairs or historical rewrites.

Each ticker has one active operating disposition, in precedence order:
UNRESOLVED, INELIGIBLE_SOURCE_DATA, REPAIRABLE, HISTORICAL_ONLY, ELIGIBLE.
Contradictory or insufficient evidence resolves to UNRESOLVED. Observation
findings remain separately countable, overlapping evidence categories.
Historical incompleteness cannot override a current-source problem. Conversely,
many old incomplete observations do not alone make a healthy ticker ineligible.

## Eligibility architecture

Reuse the existing Fundamentals operational-universe version/membership and
`security.active` boundary. Refresh resolves identities from active membership;
active analysis selects active securities. Ownership detection now skips a
company without active securities. This changes universe selection, not P/B V1.
Remove creates an inactive candidate while preserving provider/canonical history.
Add sees an existing inactive identity and cannot silently reactivate it through
discovery. Reactivation requires the explicit native validated workflow.

The new queue disposition ledger explains evidence and status; it is not a second
eligibility authority and cannot repair, remove, reactivate or approve ownership.
INELIGIBLE registration requires prior native exclusion. Evidence is bound to an
exact baseline, current accepted source binding and immutable artifact hash.
Rendering detects changed bindings read-only and shows UNRESOLVED until reviewed.
HISTORICAL_ONLY and healthy eligible summaries are nonurgent; technical evidence
is available under Details.

## Pre-mutation audit and copy gates

- Initial ticker partition: 171 REPAIRABLE, 7 ELIGIBLE, 1 HISTORICAL_ONLY (KO),
  2 UNRESOLVED (BMRA, NEOV), 0 INELIGIBLE_SOURCE_DATA.
- Fresh authoritative ARQ and MRQ histories acquired for all 181 exact identities.
- Existing supported archive audited at one exact path, not through a broad scan.
- 171 unique current ARQ source bindings pass the existing completeness-only
  repair comparison, identity and unchanged-financial-value checks. Every selected
  accepted period ends on or after 2025-12-31; no frozen binding is selected.
- BMRA and NEOV have current source metadata/version drift. A fresh full payload
  is not sufficient to prove a completeness-only replacement. Leave both pending;
  no repair or exclusion is performed to force classification.
- No ticker has proven unrecoverable current source evidence; no exclusion is
  warranted. Explicit null business values are distinct from absent payload keys.
- Frozen accepted bindings (5,231) and retained observations (342) stay untouched.
  Historical-source report periods before the freeze cutoff (10,746) are a
  separate observation category, not the frozen accepted-binding count.

Native disposable-copy rehearsal passed for all 171 proposals, including exact
replacement/full payload hashes, unchanged existing financial values, unchanged
unselected provider/canonical content, unchanged ownership artifact and analysis
bytes, unique keys, SQLite integrity and no ownership/P/B approval. The existing
repair projects newly recovered parent equity only for selected current quarters;
it does not overwrite existing nonnull equity or frozen financial history.
Focused fixtures also cover native exclusion, safe peers, preserved history,
inactive Add/discovery, Refresh, analysis and scheduler/P/B selection.

Initial disposition artifact:
`42eccb8c47d03637f066e9c9977395de8efac1715155d994aba3641c79d819a5`.
Native repair batch:
`81d7fe15d2522703c42b6f8cb06f0bcda877d71b7ec0ff2d1f6dff810eb92a67`.
Durable source evidence manifest:
`fundamental_reports/legacy_payload_disposition_evidence/ba135471cdffd20645041d6f2bce9385e3c3095873918caa8dad0e9a9080713f/manifest.json`.


## Current-state revalidation after the scoped YES — STOP

The user approved only the exact batch and disposition artifact identified above,
then explicitly required revalidation after the overnight scheduler execution and
STOP if any member/binding/gate was stale or newly conflicting. That approval is
recorded; it does not authorize a replacement batch or waive native baseline gates.

**Live publication did not start. No source repairs or exclusions were applied.**
The wrapper stopped on its initial baseline check, before invoking the native
publisher. Independent read-only revalidation also produced the existing native
`PAYLOAD_WORKFLOW_STALE_BASELINE` rejection. No new proposal, batch, disposition
artifact, rehearsal receipt or OPEN repair registration was generated. The original
171 OPEN items and their exact stored receipt evidence remain intact.

Fresh audit acquired complete authoritative ARQ and MRQ histories for all 181
tickers (362 acquisitions). Results for the approved 171 members:

| Check against the approved evidence | Result |
|---|---|
| Exact accepted observation IDs, source keys and period bindings | 171/171 unchanged |
| Full fresh source payload fingerprints | 171/171 unchanged |
| Native payload comparison evidence | 171/171 unchanged |
| Selected parent-equity targets | 171/171 unchanged |
| Company/security identities and existing canonical targets | Byte-identical provider/canonical databases |
| Selected source-payload deltas | 0 |
| Stored batch/artifact fingerprints | Integrity verified; unchanged |
| Valid against the current native baseline | **FAIL — stale market hash** |
| New selected-member review | **ASX — frozen historical provider conflict** |

The only change inside the native repair baseline is `data/osakedata.db`:

- Approved SHA-256: `1e00094ca1813455e630b4deb183d9dfdf56efcc9a28de5c82f29a5821058722`.
- Current SHA-256: `6c51162f03755aaae5002ab77964af56f96822ad793d67458f60d3722cf225a6`.

The existing contract requires complete baseline equality; there is no market-only
exception. Every approved proposal binds the old baseline. Reproducing the stored
hashes verifies evidence integrity, not current publication validity. They cannot
be carried to the new baseline under the existing exact-binding contract. No
baseline, fingerprint, market data or source evidence was overwritten to make a
gate pass.

The broader input snapshot also records an external change to the global
`data/analysis.db` (distinct from the unchanged Fundamentals analysis generation
role). Its SHA-256 changed from
`764e90e83f60c04d54a706fb032ea99d1f4f31a1542c00996787a3d7218174b0` to
`9a691a46d4bca6da7fb33703371e1bce7ad47c9b2e2920206ba480a745c1b044`;
its formerly empty WAL is now absent. These are observed external input changes,
not changes caused or reversed by this validation. The input snapshot is preserved;
no sector/industry data was edited. This global analysis input is not part of the
native repair baseline, so the native stale-baseline reason remains the market
hash difference above.

The operational provider-review queue and its audit table also changed legitimately
overnight. ASX, which is in the approved batch, acquired an OPEN
`FROZEN_HISTORICAL_PROVIDER_CONFLICT` review at `2026-10-30T05:33:56Z`.
Its queue item is
`32dd979f040d8c3f342c21451caa2b883d89045947ec42a37cbf26cb49e28a7d`;
source evidence fingerprint is
`4ed6356db81764949040cf3ed0d851cce42cd143a017925acca51703998d1b91`.
The 29 affected source keys concern frozen history, not the selected current ARQ
source. Exact current payload recovery alone does not authorize ignoring this new
ticker-level review. The review was preserved; it was not resolved or bypassed.

BMRA and NEOV retain unchanged current source payloads and the same
`SOURCE_PAYLOAD_VALUE_REVISION` ambiguity; their recorded disposition remains
UNRESOLVED. NEOV additionally appears in the overnight frozen-history review
population. Neither ticker was repaired or excluded.

### Latest scheduler execution

The latest terminal scheduled Full Workflow is
`20261030T052848Z_refresh_fundamentals_d00eb7239fed_full_workflow_1b15f1a8`,
running `2026-10-30T05:28:48Z` to `05:34:55Z` (07:28–07:34 Europe/Helsinki).
It ended **STOPPED at Preview**, rather than completing a financial publication.
`production_completed=false`; `ownership_production_completed=false`; ownership
auto-continuation was skipped for the unsafe financial workflow.

Its two global blockers are outside the approved 171-member batch:

- BBAI: `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`.
- MIR: `BOUNDARY_CHRONOLOGY_INCONSISTENT`, `INTERIOR_SOURCE_KEY_REMOVAL`,
  `SAME_FISCAL_SOURCE_KEY_REPLACEMENT`.

This investigation read the existing bounded history service and the exact latest
parent/Preview result references. It did not scan all historical artifacts or
change provider-history/freeze semantics to clear the workflow.

### Preserved state and resulting scope

Active generation remains `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`,
with unchanged manifest and provider/canonical/analysis role hashes. Source
watermark remains `2026-10-28`. Journal is COMPLETED, postflight PASSED,
recovery NOT_REQUIRED. Provider and canonical byte identity proves preservation
of all frozen history, retained evidence, identities, accepted financial targets
and canonical ownership artifacts. The ownership-review table, terminal decisions
(including GE/RTX/T), typed repair rows, disposition ledger and configuration are
unchanged. Only the existing provider-review queue and audit digests differ from
the pre-scheduler review-queue snapshot. Those changes, the market update and the
global analysis input update are external state and were preserved.

Beginning/end snapshots during this fresh validation match. No runtime DB, queue,
generation, journal, configuration, review status or financial value was mutated
by this validation. Only read-only audit evidence files were written. No cleanup,
rollback, backup deletion, batch shrinking/expansion or substitute publication ran.

Readiness remains **NOT_READY**. There are still 13,113 active legacy observations
and 173 latest incomplete accepted bindings. The old 171-member copy rehearsal
remains historical PASS evidence, **not a valid current-baseline publication
receipt**. It was not rerun into a replacement batch under this scoped YES.
The original 553 distinct focused tests remain recorded below; this continuation
changed documentation only and performed live read-only assertions rather than
rerunning unrelated tests. No full suite was run.

Next work must review ASX's new conflict and establish separately authorized
current evidence/receipts before any new publication proposal. BMRA/NEOV and the
latest scheduler blockers remain explicit pending work, not automatic exclusions.

Revalidation evidence: `temp/fundamentals_legacy_remediation_20261030/revalidation_20261030_0740/`.
`approved_batch_stop.json` records exact deltas, all 362 source proofs, selected
hold keys, native rejection and unchanged runtime checks. Durable manifest and
fresh source acquisitions are retained outside Git at
`fundamental_reports/legacy_payload_disposition_revalidation/2131287864a74359a0b324af3aae879fdf5114471869af8f274f8906129d4e57/manifest.json`.
Supplementary external-input delta and a final unchanged-runtime check:
`fundamental_reports/legacy_payload_disposition_revalidation/c22b435f85cb3cda8c5dc03647d87c4f4cf681b87949f314fd4758fe8167f1f2.json`.

## Approved audit snapshot: ticker partition and observation evidence

This table preserves the approved pre-scheduler audit; it is not a regenerated
post-scheduler disposition artifact or permission to publish over the ASX hold.
It groups observations by their owner ticker's single recorded disposition.
The evidence columns are not additional ticker statuses. Frozen and retained
evidence can overlap. Every ticker appears exactly once.

| Active ticker disposition | Tickers | Remaining legacy observations | Latest incomplete bindings | Frozen accepted evidence | Retained evidence |
|---|---:|---:|---:|---:|---:|
| UNRESOLVED | 2 | 126 | 2 | 48 | 3 |
| INELIGIBLE_SOURCE_DATA | 0 | 0 | 0 | 0 | 0 |
| REPAIRABLE | 171 | 12,717 | 171 | 5,069 | 311 |
| HISTORICAL_ONLY | 1 | 4 | 0 | 2 | 4 |
| ELIGIBLE | 7 | 266 | 0 | 112 | 24 |

Observation categories below intentionally overlap. Do not add these counts
together or interpret them as mutually exclusive ticker populations.

| Observation-level evidence category | Count |
|---|---:|
| Original exact legacy observations | 13,113 |
| Original latest accepted legacy bindings | 173 |
| Frozen accepted financial bindings | 5,231 |
| Retained outside source window | 342 |
| Source reportperiod <= 2024-12-31 (not a canonical freeze test) | 10,746 |
| Fresh exact source key returned | 12,739 |
| Fresh completeness-only comparison | 12,724 |
| Archive exact source key matched | 12,815 |
| Archive completeness-only comparison | 11,310 |
| Fresh or archive completeness-only evidence (union, not a repair authorization) | 13,092 |
| Neither source proves completeness-only recovery | 21 |
| Noncurrent historical exact evidence unavailable | 19 |
| Current ambiguous exact recovery | 2 |
| Live exact source repairs completed | 0 |

Fresh comparison details: 12,724 completeness-only, 374 exact keys not returned,
14 payload-value revisions and 1 financial/source-metadata revision. Differences
are diagnostic evidence, never permission to substitute revised source values.
Archive matches: 12,815; 11,310 completeness-only, 1,136 financial/source-metadata
revisions, 361 payload-value revisions and 8 identity mismatches. The archive is
diagnostic only; no archive override was added to the native repair workflow.

Only 19 noncurrent observations lack exact completeness-only fresh/archive
evidence: ASX 1, AYTU 1, AZZ 11, IPDN 1, JAGX 1, KO 1, MLKN 1, NEOV 1, WHLR 1.
NEOV's current ambiguity takes precedence over its historical evidence.
HISTORICAL_ONLY requires both this historical gap and proof that current
operation is healthy. Recoverable historical rows alone do not force that status.
MRQ findings remain evidence; the existing exact repair projector accepts the
accepted ARQ financial/shares binding. No MRQ repair or projector expansion was
introduced, and no frozen/retained-history mass repair was attempted.

## Preservation, locks and operational boundaries

- Existing admin, production and shared scheduler locks guard registration and
  native publication. Taxonomy lock and terminal-safe journal gates are reused.
- Exact baseline includes generation, role hashes, manifest, watermark, market,
  scheduler configuration and native repair code. Disposition authorization binds
  the exact artifact; repair authorization binds the exact receipt batch.
- Existing core financial values are unchanged. Native recovery may fill missing
  parent equity on the selected nonfrozen current quarters from the exact source.
- No old provider/canonical/audit evidence is deleted. Selected active source
  observations are replaced only in a new immutable generation; original rows
  remain in the old generation and exact before/after evidence.
- No frozen accepted values, retained source observations, terminal ownership
  decisions (including GE/RTX/T), ownership artifact, analysis role, market or
  sector/industry metadata are changed by this task. No ownership decisions are
  republished. Existing P/B, freeze, WFRD, source-repair and publication-authority
  semantics remain unchanged. No backup/evidence deletion or push.
- Financial eligibility remains the native active universe. The new ledger is
  evidence/status metadata. No unknown case is silently marked ineligible.
- Recorded disposition evidence can become stale after a legitimate refresh.
  UI compares exact current fiscal/source/hash binding and displays UNRESOLVED
  read-only; rendering never repairs, excludes or updates review state.

## Focused validation

- 292 passed: disposition, native source-repair workflow, P/B auto-continuation,
  action-first UI, admin UI, Remove and Remove production parity, Batch Add,
  scheduler Full Workflow. Initial run: 309.40 s.
- 256 passed: historical freeze, WFRD accounting-boundary review and production
  candidate parity, result publication authority, provider payload completeness.
  Run: 160.90 s.
- Final disposition module: 29 passed (9.87 s), including precedence, overlapping
  evidence, no guessed classification, exact registration authorization, lock
  use, stale baseline/binding rejection, idempotent audit and read-only rendering.
  These include the earlier 24 disposition tests; do not count reruns as distinct
  coverage. Total distinct focused cases: 553. Full suite: NOT RUN.
- Native 171-member disposable provider/canonical/analysis rehearsal PASS.
  Unrecoverable/ineligible behavior was tested with disposable fixtures; no live
  ticker was forced into that category to manufacture an exclusion example.
- Current-state UI replay uses the actual read-only service and Flet presenter
  with read-only adapter. All 181 current dispositions render summary first;
  no stale binding, no render action and unchanged queue/financial runtime hashes.
  This is a control-tree replay, not a browser screenshot.

## Evidence locations

`temp/fundamentals_legacy_remediation_20261030/` contains exact source acquisitions,
archive comparisons, baseline, proposals, sealed native receipts, copy databases,
test logs and current-state replay. Durable acquisition/audit evidence is copied
to the manifest referenced above. Native typed queue rows retain exact proposals
and receipt bindings. `fundamental_reports/source_dispositions/<artifact>.json`
retains immutable full-cohort evidence; the current queue ledger has one row per
ticker with compact audit history. Runtime evidence is intentionally outside Git.

Archive: `data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip`
(1,036,805 rows at this exact supported archive). SHA-256:
`dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`.

Original active generation:
`pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`.
Watermark: `2026-10-28` (source repair does not advance it).

## Complete ticker classification — approved audit snapshot

Counts refer to remaining active legacy observations and preserved original
frozen/retained evidence. Repair counts are completed live source replacements,
not merely proposals. Full exact source identities/hashes are in sealed artifacts.

| Ticker | Active disposition | Legacy | Frozen | Retained | Repaired |
|---|---|---:|---:|---:|---:|
| ABAT | REPAIRABLE | 83 | 34 | 1 | 0 |
| ABM | REPAIRABLE | 82 | 34 | 2 | 0 |
| ACI | REPAIRABLE | 75 | 28 | 0 | 0 |
| ACN | REPAIRABLE | 82 | 34 | 1 | 0 |
| ADBE | REPAIRABLE | 82 | 34 | 1 | 0 |
| ADC | ELIGIBLE | 4 | 2 | 4 | 0 |
| AEO | REPAIRABLE | 82 | 34 | 2 | 0 |
| AI | REPAIRABLE | 52 | 17 | 0 | 0 |
| AIR | REPAIRABLE | 83 | 35 | 3 | 0 |
| ALMU | REPAIRABLE | 45 | 14 | 0 | 0 |
| ALZN | REPAIRABLE | 51 | 17 | 0 | 0 |
| AMST | REPAIRABLE | 57 | 19 | 0 | 0 |
| ANAB | REPAIRABLE | 82 | 35 | 2 | 0 |
| ANGO | REPAIRABLE | 83 | 35 | 3 | 0 |
| APLD | REPAIRABLE | 49 | 15 | 0 | 0 |
| APOG | REPAIRABLE | 83 | 35 | 3 | 0 |
| ASO | REPAIRABLE | 56 | 19 | 0 | 0 |
| ASX | REPAIRABLE | 81 | 29 | 0 | 0 |
| AVAV | REPAIRABLE | 83 | 34 | 2 | 0 |
| AVGO | REPAIRABLE | 82 | 34 | 2 | 0 |
| AYTU | REPAIRABLE | 83 | 35 | 1 | 0 |
| AZZ | REPAIRABLE | 83 | 34 | 3 | 0 |
| BB | REPAIRABLE | 84 | 34 | 2 | 0 |
| BBW | REPAIRABLE | 82 | 34 | 2 | 0 |
| BKE | REPAIRABLE | 82 | 34 | 2 | 0 |
| BMRA | UNRESOLVED | 83 | 35 | 3 | 0 |
| BNED | REPAIRABLE | 81 | 34 | 2 | 0 |
| BRZE | REPAIRABLE | 47 | 15 | 0 | 0 |
| BTDR | REPAIRABLE | 54 | 16 | 0 | 0 |
| BYRN | REPAIRABLE | 85 | 35 | 2 | 0 |
| CAG | REPAIRABLE | 83 | 35 | 3 | 0 |
| CAL | REPAIRABLE | 82 | 34 | 2 | 0 |
| CALM | REPAIRABLE | 83 | 35 | 3 | 0 |
| CAPS | REPAIRABLE | 21 | 3 | 0 | 0 |
| CASY | REPAIRABLE | 82 | 34 | 2 | 0 |
| CBRL | REPAIRABLE | 82 | 34 | 2 | 0 |
| CCL | REPAIRABLE | 83 | 35 | 3 | 0 |
| CDT | REPAIRABLE | 43 | 13 | 0 | 0 |
| CELU | REPAIRABLE | 62 | 24 | 0 | 0 |
| CHWY | REPAIRABLE | 66 | 24 | 0 | 0 |
| CLF | REPAIRABLE | 84 | 35 | 3 | 0 |
| CMC | REPAIRABLE | 82 | 34 | 1 | 0 |
| CMTL | REPAIRABLE | 82 | 34 | 2 | 0 |
| CNM | REPAIRABLE | 51 | 16 | 0 | 0 |
| CNXC | REPAIRABLE | 57 | 19 | 0 | 0 |
| COO | REPAIRABLE | 82 | 34 | 2 | 0 |
| COST | REPAIRABLE | 82 | 34 | 2 | 0 |
| CPB | REPAIRABLE | 82 | 34 | 2 | 0 |
| CPRT | REPAIRABLE | 82 | 34 | 2 | 0 |
| CRMT | REPAIRABLE | 82 | 34 | 2 | 0 |
| CTAS | REPAIRABLE | 83 | 35 | 3 | 0 |
| CTNT | REPAIRABLE | 35 | 9 | 0 | 0 |
| CURV | REPAIRABLE | 50 | 16 | 0 | 0 |
| DAL | REPAIRABLE | 84 | 35 | 4 | 0 |
| DBI | REPAIRABLE | 82 | 34 | 2 | 0 |
| DCI | REPAIRABLE | 82 | 34 | 2 | 0 |
| DDS | REPAIRABLE | 82 | 34 | 2 | 0 |
| DELL | REPAIRABLE | 82 | 34 | 2 | 0 |
| DLTH | REPAIRABLE | 82 | 34 | 2 | 0 |
| DPZ | REPAIRABLE | 83 | 35 | 2 | 0 |
| DRI | REPAIRABLE | 83 | 35 | 3 | 0 |
| DXLG | REPAIRABLE | 82 | 34 | 2 | 0 |
| EBF | REPAIRABLE | 83 | 35 | 3 | 0 |
| EFX | REPAIRABLE | 84 | 35 | 3 | 0 |
| FAST | REPAIRABLE | 85 | 35 | 4 | 0 |
| FDS | REPAIRABLE | 83 | 35 | 2 | 0 |
| FEIM | REPAIRABLE | 83 | 35 | 3 | 0 |
| FIZZ | REPAIRABLE | 83 | 35 | 3 | 0 |
| FLWS | REPAIRABLE | 82 | 35 | 2 | 0 |
| FNGR | REPAIRABLE | 81 | 30 | 1 | 0 |
| FOXX | REPAIRABLE | 38 | 12 | 0 | 0 |
| FRGT | REPAIRABLE | 50 | 17 | 1 | 0 |
| FUL | REPAIRABLE | 82 | 34 | 2 | 0 |
| GCO | REPAIRABLE | 82 | 34 | 2 | 0 |
| GE | ELIGIBLE | 84 | 35 | 3 | 0 |
| GIII | REPAIRABLE | 82 | 34 | 2 | 0 |
| GIS | REPAIRABLE | 83 | 35 | 3 | 0 |
| GITS | REPAIRABLE | 34 | 9 | 0 | 0 |
| GM | ELIGIBLE | 4 | 2 | 4 | 0 |
| GME | REPAIRABLE | 83 | 34 | 2 | 0 |
| GOSS | REPAIRABLE | 68 | 26 | 0 | 0 |
| GPC | REPAIRABLE | 84 | 35 | 3 | 0 |
| GPMT | REPAIRABLE | 79 | 32 | 2 | 0 |
| GPRO | REPAIRABLE | 83 | 35 | 3 | 0 |
| GUTS | REPAIRABLE | 29 | 7 | 0 | 0 |
| GWRE | REPAIRABLE | 83 | 34 | 2 | 0 |
| HAIN | REPAIRABLE | 79 | 32 | 1 | 0 |
| HELE | REPAIRABLE | 84 | 35 | 4 | 0 |
| HOVR | REPAIRABLE | 34 | 8 | 0 | 0 |
| IBEX | REPAIRABLE | 60 | 21 | 0 | 0 |
| IDT | REPAIRABLE | 82 | 34 | 1 | 0 |
| INM | REPAIRABLE | 57 | 19 | 0 | 0 |
| IPDN | REPAIRABLE | 82 | 35 | 2 | 0 |
| IRDM | REPAIRABLE | 85 | 35 | 3 | 0 |
| IRM | REPAIRABLE | 82 | 35 | 2 | 0 |
| JAGX | REPAIRABLE | 83 | 35 | 2 | 0 |
| JILL | REPAIRABLE | 82 | 33 | 1 | 0 |
| KBH | REPAIRABLE | 83 | 35 | 3 | 0 |
| KFY | REPAIRABLE | 82 | 34 | 2 | 0 |
| KITT | REPAIRABLE | 53 | 16 | 0 | 0 |
| KMX | REPAIRABLE | 83 | 35 | 3 | 0 |
| KO | HISTORICAL_ONLY | 4 | 2 | 4 | 0 |
| KR | REPAIRABLE | 82 | 34 | 2 | 0 |
| LAKE | REPAIRABLE | 84 | 34 | 2 | 0 |
| LEN | REPAIRABLE | 83 | 35 | 3 | 0 |
| LEVI | REPAIRABLE | 85 | 35 | 3 | 0 |
| LITS | REPAIRABLE | 82 | 35 | 3 | 0 |
| LNAI | REPAIRABLE | 71 | 27 | 0 | 0 |
| LOVE | REPAIRABLE | 75 | 27 | 0 | 0 |
| LPTH | REPAIRABLE | 82 | 35 | 2 | 0 |
| LW | REPAIRABLE | 85 | 36 | 5 | 0 |
| M | REPAIRABLE | 82 | 34 | 2 | 0 |
| MCFT | REPAIRABLE | 82 | 35 | 2 | 0 |
| MIND | REPAIRABLE | 82 | 34 | 2 | 0 |
| MKC | REPAIRABLE | 83 | 35 | 3 | 0 |
| MLKN | REPAIRABLE | 83 | 35 | 2 | 0 |
| MMM | REPAIRABLE | 84 | 35 | 3 | 0 |
| MSCI | REPAIRABLE | 84 | 35 | 3 | 0 |
| MTN | REPAIRABLE | 82 | 34 | 2 | 0 |
| MU | REPAIRABLE | 83 | 35 | 2 | 0 |
| NAMS | REPAIRABLE | 44 | 14 | 0 | 0 |
| NB | REPAIRABLE | 83 | 34 | 2 | 0 |
| NEOG | REPAIRABLE | 83 | 35 | 3 | 0 |
| NEOV | UNRESOLVED | 43 | 13 | 0 | 0 |
| NEUP | REPAIRABLE | 36 | 9 | 0 | 0 |
| NFE | REPAIRABLE | 69 | 27 | 0 | 0 |
| NFLX | REPAIRABLE | 85 | 35 | 4 | 0 |
| NKE | REPAIRABLE | 83 | 35 | 2 | 0 |
| NOC | ELIGIBLE | 4 | 2 | 4 | 0 |
| NRIX | REPAIRABLE | 57 | 20 | 0 | 0 |
| NTNX | REPAIRABLE | 82 | 34 | 1 | 0 |
| NXXT | REPAIRABLE | 56 | 17 | 0 | 0 |
| OCC | REPAIRABLE | 82 | 34 | 2 | 0 |
| ORCL | REPAIRABLE | 82 | 34 | 2 | 0 |
| PANW | REPAIRABLE | 82 | 34 | 2 | 0 |
| PAYX | REPAIRABLE | 83 | 35 | 3 | 0 |
| PEGA | REPAIRABLE | 84 | 35 | 3 | 0 |
| PENG | REPAIRABLE | 81 | 32 | 1 | 0 |
| PEP | REPAIRABLE | 83 | 35 | 3 | 0 |
| PLAB | REPAIRABLE | 82 | 34 | 2 | 0 |
| PLAY | REPAIRABLE | 82 | 34 | 2 | 0 |
| PLCE | REPAIRABLE | 82 | 34 | 2 | 0 |
| PRGS | REPAIRABLE | 83 | 35 | 3 | 0 |
| REBN | REPAIRABLE | 43 | 13 | 0 | 0 |
| RENT | REPAIRABLE | 46 | 14 | 0 | 0 |
| REVB | REPAIRABLE | 60 | 19 | 0 | 0 |
| RGP | REPAIRABLE | 83 | 35 | 3 | 0 |
| RH | REPAIRABLE | 83 | 34 | 2 | 0 |
| RPM | REPAIRABLE | 83 | 35 | 3 | 0 |
| RTX | ELIGIBLE | 83 | 35 | 3 | 0 |
| RZLT | REPAIRABLE | 71 | 27 | 0 | 0 |
| SCHL | REPAIRABLE | 83 | 35 | 3 | 0 |
| SEGG | REPAIRABLE | 80 | 27 | 0 | 0 |
| SFIX | REPAIRABLE | 79 | 30 | 1 | 0 |
| SGLY | REPAIRABLE | 83 | 33 | 3 | 0 |
| SHPH | REPAIRABLE | 42 | 12 | 0 | 0 |
| SIG | REPAIRABLE | 82 | 34 | 2 | 0 |
| SKIN | REPAIRABLE | 52 | 19 | 0 | 0 |
| SMXT | REPAIRABLE | 42 | 13 | 0 | 0 |
| SNX | REPAIRABLE | 83 | 35 | 3 | 0 |
| STZ | REPAIRABLE | 83 | 35 | 3 | 0 |
| T | ELIGIBLE | 84 | 35 | 3 | 0 |
| TGL | REPAIRABLE | 44 | 13 | 0 | 0 |
| THO | REPAIRABLE | 82 | 34 | 1 | 0 |
| TLRY | REPAIRABLE | 75 | 28 | 0 | 0 |
| TRUG | REPAIRABLE | 47 | 12 | 0 | 0 |
| UAL | REPAIRABLE | 84 | 35 | 4 | 0 |
| UNFI | REPAIRABLE | 82 | 34 | 1 | 0 |
| UPXI | REPAIRABLE | 51 | 17 | 0 | 0 |
| URBN | REPAIRABLE | 82 | 34 | 2 | 0 |
| URI | REPAIRABLE | 84 | 35 | 4 | 0 |
| USAU | REPAIRABLE | 83 | 35 | 3 | 0 |
| VNCE | REPAIRABLE | 82 | 34 | 2 | 0 |
| VRA | REPAIRABLE | 82 | 34 | 2 | 0 |
| VRSN | ELIGIBLE | 3 | 1 | 3 | 0 |
| WHLR | REPAIRABLE | 82 | 35 | 2 | 0 |
| WOR | REPAIRABLE | 83 | 35 | 3 | 0 |
| WS | REPAIRABLE | 32 | 7 | 0 | 0 |
| XTIA | REPAIRABLE | 83 | 35 | 3 | 0 |
| YYAI | REPAIRABLE | 89 | 32 | 23 | 0 |
| ZUMZ | REPAIRABLE | 82 | 34 | 2 | 0 |
