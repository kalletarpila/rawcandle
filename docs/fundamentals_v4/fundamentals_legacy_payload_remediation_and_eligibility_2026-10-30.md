# Legacy payload remediation and Fundamentals eligibility — 2026-10-30

## BMRA/NEOV targeted investigation — STOP, no runtime mutation

The subsequent `FUNDAMENTALS-BMRA-NEOV-TARGETED-REMEDIATION` task investigated
only these two unresolved current bindings. Conditional repair/exclusion was
authorized without another YES, but the exact native repair gates do not pass.
Both remain UNRESOLVED. No repair, exclusion, disposition-ledger update or new
publication was performed. The wider 181-ticker cohort was not reopened.

### Fresh baseline and exact current evidence

Active generation: `payload_repair_c76f86e26cbc7735_99b4b068a24f`. Manifest SHA-256:
`aa0cc808d1d0975a4918286b3a41314ad57aa9b24b3c6a8b0054b25ec7766627`. Watermark: `2026-10-28`.
All three role hashes, market/global analysis inputs, configuration, complete
review/audit state, current disposition rows and source-repair code were freshly
bound. Existing admin/production/scheduler locks were available. Journal remains
COMPLETED, postflight PASSED, recovery NOT_REQUIRED. Previous publication cleanup
remains COMPLETED; this investigation created no new rollback backups.

Four new authoritative complete histories were acquired: BMRA ARQ/MRQ 40/40 rows;
NEOV ARQ/MRQ 20/23 rows. Each current ARQ key has one accepted stored observation
and one exact fresh provider match. Company/security/provider identity, fiscal
identity, source key and accepted normalized financial projection agree.

| Ticker | Accepted fiscal quarter | Exact ARQ date / reportperiod | Stored lastupdated | Fresh lastupdated | Payload keys | Final disposition |
|---|---|---|---|---|---|---|
| BMRA | 2027-Q1 | 2026-10-15 / 2026-08-31 | 2026-10-16 | 2026-10-19 | 29 → 112 | UNRESOLVED |
| NEOV | 2026-Q4 | 2026-09-23 / 2026-06-30 | 2026-09-23 | 2026-10-29 | 29 → 112 | UNRESOLVED |

Exact bindings and raw fingerprints:

- BMRA: company/security `343/343`, provider security `123744`, canonical quarter `12153`.
  Accepted observation: `44a45a3a04732d633ef77492f6388ee01e54b9da5ab878cebe5bbbbad615e80d`.
  Stored payload: `77f86a86123f39be79288d40c18f761b585e406f1d9ad61fe58e13860b3a4d72`.
  Fresh full payload: `8972820c61de338cce0fdf6fb42f44c19ef7922a3d4d449f5b3f11fc498e4b25`.
- NEOV: company/security `1530/1539`, provider security `638745`, canonical quarter `54755`.
  Accepted observation: `d188c5c24ccf8d6e4ecc324f51f4578bee4c4ec7ca51e5dbb5b6d6a4aefbc42a`.
  Stored payload: `175447b7ff39c08a718e468fcb4bdcbff289942c7dca9884bb211e733b8e5a45`.
  Fresh full payload: `0c35628ba66fcf48fcda6f0b7c5491c7205bd1af2e45150f72f6c520b8da1067`.

### Exact cause and safety boundary

For both tickers the **only changed normalized projection field is `lastupdated`**.
The current source also supplies 83 previously absent raw fields. Existing shared
normalized financial values do not differ; this is not an identity revision,
source-key replacement or duplicate-current-key problem. Raw integer/string
representation differences are normalized by the existing contract.

However, completeness plus a different source metadata version is explicitly
`SOURCE_PAYLOAD_VALUE_REVISION`, not `SOURCE_PAYLOAD_COMPLETENESS_REPAIR`.
`fields_changed` is empty because it excludes projection fields; the changed
raw projection fingerprint plus added fields triggers the value-revision guard.
The native proposal rejects both with `PAYLOAD_WORKFLOW_NOT_COMPLETENESS_REPAIR`.
The inactive-copy primitive independently rejects both with
`PAYLOAD_REPAIR_NOT_COMPATIBLE` before mutation.

The primitive preserves native observation fields including `lastupdated` and
provider headers including the old observed-at date. Accepting a new stamped
payload while retaining those old version fields would violate that contract.
No timestamp was backdated, ignored or edited to manufacture compatibility.
No financial/source-repair policy was relaxed.

Fresh provider `sharefactor` is explicitly 1 for both; fresh `equityusd` is
3,648,000 for BMRA and 39,567,340 for NEOV. These are **unused audit facts**, not
defaults or values authorized for the older accepted source version. All 83 new
fields were absent in the old projection, so their old-version values are not
known. Equality of the shared normalized financial fields cannot prove equality
of previously absent fields across source versions. Current canonical parent
equity remains missing, and the native current P/B reports `MISSING_EQUITY` with
no value for both. Existing holds remain; no ownership approval was created.

### Supported archive/retained evidence and NEOV frozen separation

The exact known authoritative archive at `phase12c_20260910` was checksum-verified
against its earlier audit. Its retained exact-key catalog contains no match for
BMRA's 2026-10-15 or NEOV's 2026-09-23 current source key. The exact preceding
immutable provider generation also
contains only the same 29-key observations. The originating provider-run records
bind projected acquisitions but provide no retained full-payload locator:
BMRA was fetched 2026-10-18 with stamp 2026-10-16; NEOV was fetched 2026-09-26
with stamp 2026-09-23. No directory-wide generation/artifact search was performed.
This is not proof that all possible upstream old versions are unavailable.

Fresh full current sources exist and are complete. Thus a proven inability to
use the strict old-version repair contract is **not** sufficient evidence for
INELIGIBLE_SOURCE_DATA. Neither ticker was excluded. Historical incompleteness
also cannot override the unresolved current binding to produce HISTORICAL_ONLY.

NEOV’s OPEN `FROZEN_HISTORICAL_PROVIDER_CONFLICT` has 13 exact frozen conflicts.
Their accepted financial/source states and evidence fingerprints match current
canonical/provider evidence; every conflicting key is at/before 2024-12-31.
They do not overlap current quarter 54755, source date 2026-09-23 or reportperiod
2026-06-30. Current/frozen scope separation is proven. That review is not the
reason the current repair fails; source-version incompatibility is. No frozen
authority was consumed and the review remains OPEN unchanged. BMRA has no current
provider-history review. Observation evidence is separate from each ticker’s one
active UNRESOLVED operating disposition.

### Actual-case copy validation, tests and final state

The actual unresolved-preservation case was rehearsed on disposable copies of
current provider/canonical/analysis roles and the queue. Both native proposal
and inactive-candidate repair paths reject the metadata-plus-completeness change.
All active-copy roles, the inactive provider candidate, review/ownership/disposition
queue and real runtime remain byte/logically unchanged; SQLite quick/FK checks pass.
No artificial live exclusion or repair case was manufactured. No new repair Test
receipt was created because no proposal qualifies. No publication/recovery/cleanup
lifecycle was invoked; the existing healthy generation/journal remain intact.

An initial raw primitive check addressed the clone’s active generation and was
correctly stopped by `PARENT_EQUITY_INACTIVE_COPY_REQUIRED` before writing.
The harness was corrected to a separate inactive candidate without weakening the
guard, discarding the clone or touching active files. The final preservation
rehearsal passed; both original and final logs are retained.

Focused tests: **172 passed**; WFRD/publication-authority/shared and ownership
cleanup regressions: **238 passed**; **410 distinct cases**, full suite NOT RUN.
Four new synthetic regressions reproduce the exact BMRA/NEOV version/date shapes
and native no-write rejection. Existing tests cover exact repair/receipt/staleness,
current/frozen coexistence and collision, historical-only/ineligible/unresolved
precedence, native universe/analysis/P/B selection and immutable journal/recovery/
cleanup. Production source code is unchanged in this targeted task.

Final read-only health query over latest active accepted bindings confirms exactly
BMRA and NEOV remain incomplete. The disposition aggregate remains 171 ELIGIBLE,
8 HISTORICAL_ONLY, 2 UNRESOLVED, 0 REPAIRABLE and 0 INELIGIBLE_SOURCE_DATA.
The active universe remains 2,468 members. These are aggregate health reads, not
a reclassification of other tickers. No ticker/provider/canonical/audit history,
frozen state, ownership decisions (including GE/RTX/T), WFRD, publication authority,
market/global analysis inputs, scheduler configuration or backup was changed.
All runtime role/manifest/input and complete queue digests match the fresh baseline.
No disposition row or source-repair row was added/changed for BMRA/NEOV.

Completeness V1 remains disabled; readiness remains **NOT_READY** for these exact
current bindings. The next required work is either authoritative full old-version
recovery matching the stored stamps, or a separately reviewed source-version
advancement path with exact metadata/header/native-row/provenance alignment,
unchanged normalized financial values and explicit current/frozen authority
separation. Simply bypassing the current comparison or running a broad Refresh
is not a demonstrated resolution and was not attempted.

Durable exact evidence: `fundamental_reports/bmra_neov_targeted_evidence/bcde70cf97313dd746c7d0affbede17fc96aa0d666bae0426e3b3e780e03ffd7/manifest.json`.
Working evidence: `temp/fundamentals_bmra_neov_targeted_20261030/`.
No separate YES was requested; the task’s conditional mutation authority never
became applicable because native exact-repair compatibility failed.

---

## Fresh rebaseline and authorized live remediation

The subsequent `FUNDAMENTALS-LEGACY-PAYLOAD-REBASELINE-AND-LIVE-REMEDIATION`
task explicitly authorizes the freshly reconstructed safe batch after every gate
passes. The previous artifact/batch and prior scoped YES remain historical. This
new task supplies the conditional publication and exact owned-backup cleanup
authorization; no redundant second YES is required or requested.

Fresh baseline: generation `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`, watermark
`2026-10-28`; journal COMPLETED/PASSED/NOT_REQUIRED. Current
market SHA-256 is `6c51162f03755aaae5002ab77964af56f96822ad793d67458f60d3722cf225a6`.
Global `analysis.db` and its absent WAL are freshly bound separately. Existing
admin/production/scheduler locks were available. Source code identity, full
review/audit and disposition ledger snapshots are bound in the new evidence.

### ASX: independent current repair proven (Phase B, option A)

At the fresh pre-publication baseline, ASX's selected accepted source key was
`ASX / ARQ / 2026-07-30 / 2026-06-30`, observation
`0071e243a6de869236ce821ec755dfdb925283200693190d6fd8f2bb04d089f7`,
quarter ID 87986. All 29 conflicting accepted historical identities are at/before
2024-12-31, bind different exact source observations and match current canonical
financial state and provider content. The review's incoming/accepted candidates
and affected keys do not collide with the current repair. Every conflict remains
`FROZEN_PROVIDER_CONFLICT_HELD`. No reviewed repair binding is consumed.

The new read-only scope proof checks structured reason/type, exact identity,
cutoff, per-conflict fingerprints, accepted financial/source state and source-key
separation. It fails closed on unknown, mixed, stale or overlapping authority.
The native publisher repeats this check inside its existing locks and queue
transaction and binds the tested review fingerprint. This adds a safety gate;
payload comparison, parent-equity projection, freeze and source-repair financial
semantics are unchanged. BBAI/MIR are outside the selected cohort; the independent
source-repair contract does not consume or suppress their scheduler blockers.

### Fresh classification and receipts

All 181 exact original identities and 13,113 observations were recomputed using
362 newly acquired complete ARQ/MRQ histories and the same supported archive.
Initial fresh ticker partition: 171 REPAIRABLE, 7 ELIGIBLE, 1 HISTORICAL_ONLY (KO),
2 UNRESOLVED (BMRA, NEOV), 0 INELIGIBLE_SOURCE_DATA. Cohort difference from the old
171: none. The count was derived, not targeted. BMRA/NEOV still have exact current
metadata/value-revision ambiguity and are excluded from repair.

Fresh historical key-return evidence changed: 12,718 exact fresh keys and 395
not returned, compared with the historical 12,739/374. Completeness-only fresh
comparisons number 12,703; archive completeness-only evidence remains 11,310.
Their union remains 13,092; historical-only gaps remain 19 and current ambiguous
bindings remain 2. These overlapping observation categories are not ticker statuses.
No historical mass repair was added for a changed provider window.

Fresh disposition artifact: `03dd0631301496ffd19c920556783e1fb5f095307bcc456a04f96465d5c6a263`.
Fresh native repair batch: `c76f86e26cbc7735788333867447084a01a49644826ca0b3914b0920a46d9f40`.
Tested review-scope fingerprint: `617d5b04ff5e0f250c81504e2c49a6377390244cd9aca652abade924eec71467`.
Durable acquisition/disposition evidence: `/home/kalle/projects/rawcandle/fundamental_reports/legacy_payload_disposition_evidence/b2b73da49ab8ccec96b104c18ce78bcac0375dbff6ba14e61e23bf0bb87b5831/manifest.json`.
Fresh native proposal/Test receipts and disposable lifecycle evidence are under
`temp/fundamentals_legacy_rebaseline_20261030/`.

The native current-state DB-copy Test passed for all 171 selected repairs. The
complete native copy publication/postflight/recovery/acceptance/cleanup lifecycle
also passed with byte-identical candidate roles. Its repeated cleanup was
idempotent, all original review/ownership/disposition records were preserved and
the real runtime remained unchanged during rehearsal. The authorized live
publication then completed, followed by healthy native acceptance and cleanup.

### Focused validation and cleanup integration

197 focused cases and 256 freeze/WFRD/publication-authority/completeness
regressions passed (453 distinct cases). The focused group includes the new
19-case rebaseline/scope/acceptance module, existing 29-case disposition module,
native source-repair workflow, shared cleanup, ownership cleanup, P/B policy and
scheduler integration. The strengthened supersession/cohort-count test also
passed on rerun. No full suite was run.

The existing source publisher did not expose a shared acceptance result. The new
payload acceptance adapter records the actual completed native journal and typed
APPROVED decisions, verifies current/old immutable lineage, role hashes/integrity,
review proof and the exact three journal-owned backups. It delegates all deletion
to the existing locked cleanup owner. Later journals/generations, changed receipts,
unsafe recovery, extra backups, symlinks/hardlinks, altered typed rows or changed
review authority fail closed. No historical-release shortcut was added.

Tests cover safe current/frozen coexistence, conflicting scopes/identities and
financial evidence, fresh baseline reconstruction, stale receipt rejection,
changed cohort-count binding, explicit stale-row supersession, exact acceptance,
cleanup idempotence and preservation of unrelated backups/generations/queue data.

### Live publication, acceptance and final health

Published generation: `payload_repair_c76f86e26cbc7735_99b4b068a24f`.
Journal COMPLETED; postflight PASSED; rollback/recovery NOT_REQUIRED.
Exact source replacements completed: **171**. All selected typed repair rows are APPROVED.
The old 171 rows are STALE with original proposal/receipt/binding evidence
unchanged. The only queue mutations are owned typed repair/audit and disposition
metadata; the complete provider-review and ownership tables are unchanged.
No financial value was guessed or defaulted, and existing normalized financial
values were preserved. Missing parent equity was projected only for selected
nonfrozen accepted quarters through the unchanged native acceptor. Source and
financial provenance now reference the exact restored full payloads.

Fresh Test receipt-set fingerprint: `c6a13aaa9eff5675e3d7e4714c6c07719df99e6bf1b267aa9d02edf71e24881f`.
Shared measured Test result fingerprint: `7df0efeb4b0758fe898e3762c59467bedce6e079b3f959c6cd3e2490798a59dc`.
Final disposition artifact: `9f8d49eadbb882d4cb0575861544fa9d706d7c5248034f0ef9eb35f71a3a4001`.
Native completed publication receipt and cleanup evidence:
`fundamental_reports/admin_runs/payload_repair_c76f86e26cbc7735_99b4b068a24f/result.json` and
`fundamental_reports/admin_runs/payload_repair_c76f86e26cbc7735_99b4b068a24f/backup_cleanup.json`.

Cleanup: COMPLETED; **3 exact journal-owned rollback backups**,
**2,630,086,656 bytes freed**. All other backup file identities, sizes and
mtimes match the pre-publication inventory. The old immutable generation, current
generation, source archives, Test candidates, receipts and unrelated evidence
remain. Published/old role integrity, absence of backup hardlinks and terminal
recovery independence were verified before deletion. The follow-up eligibility
inspection reports ALREADY_CLEANED. Cleanup did not rewrite the journal or live roles.

Pre/post checks against the fresh baseline passed for every frozen financial,
field-provenance and parent-equity table; all retained legacy observations remain.
The old generation role hashes still match. GE/RTX/T terminal decisions, the
ownership artifact and all ownership queue/history data are unchanged. WFRD
financial/history/review state and publication-authority semantics are unchanged.
The Fundamentals analysis role is byte-identical. Market data, global taxonomy/
analysis inputs and scheduler configuration match the fresh pre-publication
snapshot. Runtime collateral mutation: NO. Intended source/canonical projection,
generation/journal, owned review metadata and accepted-backup effects are recorded above.

ASX final disposition: **HISTORICAL_ONLY**. Its current source is now complete;
the exact 29-key frozen-history conflict review remains OPEN and unchanged.
This historical payload disposition does not approve frozen financial repair,
resolve the review or suppress the native hold. BBAI/MIR scheduler blockers remain
unchanged outside this repair lifecycle. BMRA/NEOV remain UNRESOLVED with their
original accepted observations and source-version ambiguity intact.

Post-remediation one-disposition-per-ticker partition (181 original tickers):

| Ticker disposition | Tickers | Remaining legacy observations | Latest incomplete bindings | Frozen legacy evidence | Retained legacy evidence |
|---|---:|---:|---:|---:|---:|
| UNRESOLVED | 2 | 126 | 2 | 48 | 3 |
| INELIGIBLE_SOURCE_DATA | 0 | 0 | 0 | 0 | 0 |
| REPAIRABLE | 0 | 0 | 0 | 0 | 0 |
| HISTORICAL_ONLY | 8 | 574 | 0 | 240 | 16 |
| ELIGIBLE | 171 | 12,242 | 0 | 4,943 | 323 |

Observation-level evidence remains separate and overlapping:

| Evidence category | Count |
|---|---:|
| Original legacy observations classified and preserved in evidence/old generation | 13,113 |
| Completed exact current source replacements | 171 |
| Remaining active legacy observations | 12,942 |
| Remaining latest incomplete accepted bindings | 2 |
| Frozen accepted legacy source evidence | 5,231 |
| Retained legacy source evidence | 342 |
| Fresh or archive completeness-only diagnostic evidence (original cohort) | 13,092 |
| Noncurrent historical exact evidence unavailable | 19 |
| Current ambiguous exact recovery | 2 |

Do not sum overlapping evidence categories as ticker statuses. The legacy rows
remaining are mostly historical; they were not mass-repaired. Current repairable
tickers remaining: 0. Ineligible tickers/exclusions: 0. No historical provider/
canonical data or old immutable generation was deleted.

HISTORICAL_ONLY tickers: ASX, AYTU, AZZ, IPDN, JAGX, KO, MLKN, WHLR.
Remaining current incomplete/UNRESOLVED tickers: BMRA, NEOV (2).
Completeness V1 readiness: **NOT_READY**. Those two exact current bindings remain
ambiguous; targeted source-version investigation or separately validated refresh
is required. Completeness V1 was not enabled. Frozen reviews and scheduler blockers
also remain visible for their own native workflows; none was resolved to make
this independent source publication pass.

Fresh final source-disposition UI replay passed: 181 rows, no stale source binding,
2 unresolved attention rows, nonurgent healthy/historical evidence, no render
actions, unchanged queue and financial runtime hashes. No full suite and no push.

Durable completion bundle (baseline, exact receipt identities, copy lifecycle,
authorization, native publication, cleanup, final disposition and test/UI proofs):
`fundamental_reports/legacy_payload_rebaseline_completed/8593bcfde5bbc1f0551864a8ac68d997e0a21b3f1e90df47c56bd6a7ff77d794/manifest.json`.
Exact conditional prompt authorization:
`fundamental_reports/legacy_payload_rebaseline_authorization/be5b81ce5158309a4dd7569dccb19b1040ab45010f4023b802d3a0ea504250fc.json`.

### Final role identity

| Role | SHA-256 |
|---|---|
| analysis | `b1fef5fd8eb651e0337c9f6128b1e068df2999873da158c653b45fff42223327` |
| canonical | `f7e63dd4ecd40d260764fb6a5611a6ec1f01bbadb30b183a69dde145e6a1da74` |
| provider | `f2e939f64de5c901e5fcc05761af091aa43f13271d790ce671d961750123c596` |

Final manifest SHA-256: `aa0cc808d1d0975a4918286b3a41314ad57aa9b24b3c6a8b0054b25ec7766627`.
Watermark remains `2026-10-28`.

### Complete fresh post-remediation ticker classification

These are the final active payload dispositions. Frozen/retained counts refer
to preserved original legacy evidence; current provider-review states are separate
structured reviews and are not competing observation-level ticker statuses.

| Ticker | Final disposition | Remaining legacy | Frozen | Retained | Repaired |
|---|---|---:|---:|---:|---:|
| ABAT | ELIGIBLE | 82 | 34 | 1 | 1 |
| ABM | ELIGIBLE | 81 | 34 | 2 | 1 |
| ACI | ELIGIBLE | 74 | 28 | 0 | 1 |
| ACN | ELIGIBLE | 81 | 34 | 1 | 1 |
| ADBE | ELIGIBLE | 81 | 34 | 1 | 1 |
| ADC | ELIGIBLE | 4 | 2 | 4 | 0 |
| AEO | ELIGIBLE | 81 | 34 | 2 | 1 |
| AI | ELIGIBLE | 51 | 17 | 0 | 1 |
| AIR | ELIGIBLE | 82 | 35 | 3 | 1 |
| ALMU | ELIGIBLE | 44 | 14 | 0 | 1 |
| ALZN | ELIGIBLE | 50 | 17 | 0 | 1 |
| AMST | ELIGIBLE | 56 | 19 | 0 | 1 |
| ANAB | ELIGIBLE | 81 | 35 | 2 | 1 |
| ANGO | ELIGIBLE | 82 | 35 | 3 | 1 |
| APLD | ELIGIBLE | 48 | 15 | 0 | 1 |
| APOG | ELIGIBLE | 82 | 35 | 3 | 1 |
| ASO | ELIGIBLE | 55 | 19 | 0 | 1 |
| ASX | HISTORICAL_ONLY | 80 | 29 | 0 | 1 |
| AVAV | ELIGIBLE | 82 | 34 | 2 | 1 |
| AVGO | ELIGIBLE | 81 | 34 | 2 | 1 |
| AYTU | HISTORICAL_ONLY | 82 | 35 | 1 | 1 |
| AZZ | HISTORICAL_ONLY | 82 | 34 | 3 | 1 |
| BB | ELIGIBLE | 83 | 34 | 2 | 1 |
| BBW | ELIGIBLE | 81 | 34 | 2 | 1 |
| BKE | ELIGIBLE | 81 | 34 | 2 | 1 |
| BMRA | UNRESOLVED | 83 | 35 | 3 | 0 |
| BNED | ELIGIBLE | 80 | 34 | 2 | 1 |
| BRZE | ELIGIBLE | 46 | 15 | 0 | 1 |
| BTDR | ELIGIBLE | 53 | 16 | 0 | 1 |
| BYRN | ELIGIBLE | 84 | 35 | 2 | 1 |
| CAG | ELIGIBLE | 82 | 35 | 3 | 1 |
| CAL | ELIGIBLE | 81 | 34 | 2 | 1 |
| CALM | ELIGIBLE | 82 | 35 | 3 | 1 |
| CAPS | ELIGIBLE | 20 | 3 | 0 | 1 |
| CASY | ELIGIBLE | 81 | 34 | 2 | 1 |
| CBRL | ELIGIBLE | 81 | 34 | 2 | 1 |
| CCL | ELIGIBLE | 82 | 35 | 3 | 1 |
| CDT | ELIGIBLE | 42 | 13 | 0 | 1 |
| CELU | ELIGIBLE | 61 | 24 | 0 | 1 |
| CHWY | ELIGIBLE | 65 | 24 | 0 | 1 |
| CLF | ELIGIBLE | 83 | 35 | 3 | 1 |
| CMC | ELIGIBLE | 81 | 34 | 1 | 1 |
| CMTL | ELIGIBLE | 81 | 34 | 2 | 1 |
| CNM | ELIGIBLE | 50 | 16 | 0 | 1 |
| CNXC | ELIGIBLE | 56 | 19 | 0 | 1 |
| COO | ELIGIBLE | 81 | 34 | 2 | 1 |
| COST | ELIGIBLE | 81 | 34 | 2 | 1 |
| CPB | ELIGIBLE | 81 | 34 | 2 | 1 |
| CPRT | ELIGIBLE | 81 | 34 | 2 | 1 |
| CRMT | ELIGIBLE | 81 | 34 | 2 | 1 |
| CTAS | ELIGIBLE | 82 | 35 | 3 | 1 |
| CTNT | ELIGIBLE | 34 | 9 | 0 | 1 |
| CURV | ELIGIBLE | 49 | 16 | 0 | 1 |
| DAL | ELIGIBLE | 83 | 35 | 4 | 1 |
| DBI | ELIGIBLE | 81 | 34 | 2 | 1 |
| DCI | ELIGIBLE | 81 | 34 | 2 | 1 |
| DDS | ELIGIBLE | 81 | 34 | 2 | 1 |
| DELL | ELIGIBLE | 81 | 34 | 2 | 1 |
| DLTH | ELIGIBLE | 81 | 34 | 2 | 1 |
| DPZ | ELIGIBLE | 82 | 35 | 2 | 1 |
| DRI | ELIGIBLE | 82 | 35 | 3 | 1 |
| DXLG | ELIGIBLE | 81 | 34 | 2 | 1 |
| EBF | ELIGIBLE | 82 | 35 | 3 | 1 |
| EFX | ELIGIBLE | 83 | 35 | 3 | 1 |
| FAST | ELIGIBLE | 84 | 35 | 4 | 1 |
| FDS | ELIGIBLE | 82 | 35 | 2 | 1 |
| FEIM | ELIGIBLE | 82 | 35 | 3 | 1 |
| FIZZ | ELIGIBLE | 82 | 35 | 3 | 1 |
| FLWS | ELIGIBLE | 81 | 35 | 2 | 1 |
| FNGR | ELIGIBLE | 80 | 30 | 1 | 1 |
| FOXX | ELIGIBLE | 37 | 12 | 0 | 1 |
| FRGT | ELIGIBLE | 49 | 17 | 1 | 1 |
| FUL | ELIGIBLE | 81 | 34 | 2 | 1 |
| GCO | ELIGIBLE | 81 | 34 | 2 | 1 |
| GE | ELIGIBLE | 84 | 35 | 3 | 0 |
| GIII | ELIGIBLE | 81 | 34 | 2 | 1 |
| GIS | ELIGIBLE | 82 | 35 | 3 | 1 |
| GITS | ELIGIBLE | 33 | 9 | 0 | 1 |
| GM | ELIGIBLE | 4 | 2 | 4 | 0 |
| GME | ELIGIBLE | 82 | 34 | 2 | 1 |
| GOSS | ELIGIBLE | 67 | 26 | 0 | 1 |
| GPC | ELIGIBLE | 83 | 35 | 3 | 1 |
| GPMT | ELIGIBLE | 78 | 32 | 2 | 1 |
| GPRO | ELIGIBLE | 82 | 35 | 3 | 1 |
| GUTS | ELIGIBLE | 28 | 7 | 0 | 1 |
| GWRE | ELIGIBLE | 82 | 34 | 2 | 1 |
| HAIN | ELIGIBLE | 78 | 32 | 1 | 1 |
| HELE | ELIGIBLE | 83 | 35 | 4 | 1 |
| HOVR | ELIGIBLE | 33 | 8 | 0 | 1 |
| IBEX | ELIGIBLE | 59 | 21 | 0 | 1 |
| IDT | ELIGIBLE | 81 | 34 | 1 | 1 |
| INM | ELIGIBLE | 56 | 19 | 0 | 1 |
| IPDN | HISTORICAL_ONLY | 81 | 35 | 2 | 1 |
| IRDM | ELIGIBLE | 84 | 35 | 3 | 1 |
| IRM | ELIGIBLE | 81 | 35 | 2 | 1 |
| JAGX | HISTORICAL_ONLY | 82 | 35 | 2 | 1 |
| JILL | ELIGIBLE | 81 | 33 | 1 | 1 |
| KBH | ELIGIBLE | 82 | 35 | 3 | 1 |
| KFY | ELIGIBLE | 81 | 34 | 2 | 1 |
| KITT | ELIGIBLE | 52 | 16 | 0 | 1 |
| KMX | ELIGIBLE | 82 | 35 | 3 | 1 |
| KO | HISTORICAL_ONLY | 4 | 2 | 4 | 0 |
| KR | ELIGIBLE | 81 | 34 | 2 | 1 |
| LAKE | ELIGIBLE | 83 | 34 | 2 | 1 |
| LEN | ELIGIBLE | 82 | 35 | 3 | 1 |
| LEVI | ELIGIBLE | 84 | 35 | 3 | 1 |
| LITS | ELIGIBLE | 81 | 35 | 3 | 1 |
| LNAI | ELIGIBLE | 70 | 27 | 0 | 1 |
| LOVE | ELIGIBLE | 74 | 27 | 0 | 1 |
| LPTH | ELIGIBLE | 81 | 35 | 2 | 1 |
| LW | ELIGIBLE | 84 | 36 | 5 | 1 |
| M | ELIGIBLE | 81 | 34 | 2 | 1 |
| MCFT | ELIGIBLE | 81 | 35 | 2 | 1 |
| MIND | ELIGIBLE | 81 | 34 | 2 | 1 |
| MKC | ELIGIBLE | 82 | 35 | 3 | 1 |
| MLKN | HISTORICAL_ONLY | 82 | 35 | 2 | 1 |
| MMM | ELIGIBLE | 83 | 35 | 3 | 1 |
| MSCI | ELIGIBLE | 83 | 35 | 3 | 1 |
| MTN | ELIGIBLE | 81 | 34 | 2 | 1 |
| MU | ELIGIBLE | 82 | 35 | 2 | 1 |
| NAMS | ELIGIBLE | 43 | 14 | 0 | 1 |
| NB | ELIGIBLE | 82 | 34 | 2 | 1 |
| NEOG | ELIGIBLE | 82 | 35 | 3 | 1 |
| NEOV | UNRESOLVED | 43 | 13 | 0 | 0 |
| NEUP | ELIGIBLE | 35 | 9 | 0 | 1 |
| NFE | ELIGIBLE | 68 | 27 | 0 | 1 |
| NFLX | ELIGIBLE | 84 | 35 | 4 | 1 |
| NKE | ELIGIBLE | 82 | 35 | 2 | 1 |
| NOC | ELIGIBLE | 4 | 2 | 4 | 0 |
| NRIX | ELIGIBLE | 56 | 20 | 0 | 1 |
| NTNX | ELIGIBLE | 81 | 34 | 1 | 1 |
| NXXT | ELIGIBLE | 55 | 17 | 0 | 1 |
| OCC | ELIGIBLE | 81 | 34 | 2 | 1 |
| ORCL | ELIGIBLE | 81 | 34 | 2 | 1 |
| PANW | ELIGIBLE | 81 | 34 | 2 | 1 |
| PAYX | ELIGIBLE | 82 | 35 | 3 | 1 |
| PEGA | ELIGIBLE | 83 | 35 | 3 | 1 |
| PENG | ELIGIBLE | 80 | 32 | 1 | 1 |
| PEP | ELIGIBLE | 82 | 35 | 3 | 1 |
| PLAB | ELIGIBLE | 81 | 34 | 2 | 1 |
| PLAY | ELIGIBLE | 81 | 34 | 2 | 1 |
| PLCE | ELIGIBLE | 81 | 34 | 2 | 1 |
| PRGS | ELIGIBLE | 82 | 35 | 3 | 1 |
| REBN | ELIGIBLE | 42 | 13 | 0 | 1 |
| RENT | ELIGIBLE | 45 | 14 | 0 | 1 |
| REVB | ELIGIBLE | 59 | 19 | 0 | 1 |
| RGP | ELIGIBLE | 82 | 35 | 3 | 1 |
| RH | ELIGIBLE | 82 | 34 | 2 | 1 |
| RPM | ELIGIBLE | 82 | 35 | 3 | 1 |
| RTX | ELIGIBLE | 83 | 35 | 3 | 0 |
| RZLT | ELIGIBLE | 70 | 27 | 0 | 1 |
| SCHL | ELIGIBLE | 82 | 35 | 3 | 1 |
| SEGG | ELIGIBLE | 79 | 27 | 0 | 1 |
| SFIX | ELIGIBLE | 78 | 30 | 1 | 1 |
| SGLY | ELIGIBLE | 82 | 33 | 3 | 1 |
| SHPH | ELIGIBLE | 41 | 12 | 0 | 1 |
| SIG | ELIGIBLE | 81 | 34 | 2 | 1 |
| SKIN | ELIGIBLE | 51 | 19 | 0 | 1 |
| SMXT | ELIGIBLE | 41 | 13 | 0 | 1 |
| SNX | ELIGIBLE | 82 | 35 | 3 | 1 |
| STZ | ELIGIBLE | 82 | 35 | 3 | 1 |
| T | ELIGIBLE | 84 | 35 | 3 | 0 |
| TGL | ELIGIBLE | 43 | 13 | 0 | 1 |
| THO | ELIGIBLE | 81 | 34 | 1 | 1 |
| TLRY | ELIGIBLE | 74 | 28 | 0 | 1 |
| TRUG | ELIGIBLE | 46 | 12 | 0 | 1 |
| UAL | ELIGIBLE | 83 | 35 | 4 | 1 |
| UNFI | ELIGIBLE | 81 | 34 | 1 | 1 |
| UPXI | ELIGIBLE | 50 | 17 | 0 | 1 |
| URBN | ELIGIBLE | 81 | 34 | 2 | 1 |
| URI | ELIGIBLE | 83 | 35 | 4 | 1 |
| USAU | ELIGIBLE | 82 | 35 | 3 | 1 |
| VNCE | ELIGIBLE | 81 | 34 | 2 | 1 |
| VRA | ELIGIBLE | 81 | 34 | 2 | 1 |
| VRSN | ELIGIBLE | 3 | 1 | 3 | 0 |
| WHLR | HISTORICAL_ONLY | 81 | 35 | 2 | 1 |
| WOR | ELIGIBLE | 82 | 35 | 3 | 1 |
| WS | ELIGIBLE | 31 | 7 | 0 | 1 |
| XTIA | ELIGIBLE | 82 | 35 | 3 | 1 |
| YYAI | ELIGIBLE | 88 | 32 | 23 | 1 |
| ZUMZ | ELIGIBLE | 81 | 34 | 2 | 1 |

---


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

The complete historical pre-scheduler ticker list remains in its immutable
artifact and source commit `1aa23813`; the current full list is above.
