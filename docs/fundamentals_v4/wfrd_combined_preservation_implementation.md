# WFRD combined preservation implementation

Date: 2026-10-26. Task: WFRD-PRESERVATION-IMPLEMENTATION-2.

## Result and authority

Implemented two linked, exact-source reviewed meanings under `WFRD_ACCOUNTING_BOUNDARY_REVIEW_V1`:

- `PRESERVE_ACCEPTED_FISCAL_IDENTITY`: incoming `(WFRD, ARQ, 2020-03-16, 2019-12-31)` stays provider-native `2020-Q4`, with reviewed canonical interpretation `2019-Q4`.
- `RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE`: removed `(WFRD, MRQ, 2019-12-31, 2019-12-31)` becomes immutable historical-only successor-stock evidence. Current `(WFRD, MRQ, 2019-12-13, 2019-12-13)` remains distinct predecessor partial-flow evidence, calculation-ineligible.

Governing documents:

- [ARQ evidence review](wfrd_fiscal_identity_review_2026-10-25.md), commit `12e915cf4f908cef276c4d69ee49b1cbc9332607`.
- [Preservation stop report](wfrd_exact_source_fiscal_identity_preservation.md), commit `16696efccb2ab0e21177380d770af32b6c8fcd8b`.
- [MRQ disposition policy](wfrd_mrq_disposition_policy.md), commit `2f6ad3554dde831f315d0fe84ae048527451996b`.

The implementation is deliberately restricted to these three true source keys and the established WFRD accounting payload shape. There are no wildcard, ticker-wide, dimension-wide, fiscal-label remapping, or financial-fallback rules. No multi-segment canonical-quarter model or structural event was added.

**No WFRD runtime approval or live queue registration was made. No live schema migration, new real Preview, Test, or Production operation was run. The global blocker remains.**

## Original blocker and current evidence

Before source changes, the exact stored Preview `20261025T032113Z_refresh_fundamentals_bcfcec765c58` reproduced:

- stable ARQ source key; 2019 Q4 → 2020 Q4;
- unchanged 22-field financial payload;
- duplicate target with genuine December 2020 ARQ;
- separate MRQ `TRUE_SOURCE_REMOVAL` / `SAME_FISCAL_SOURCE_KEY_REPLACEMENT`;
- MRQ chronology false and expected window false;
- `GLOBAL_BLOCKING_REVIEW`, old Preview Test authorization false.

The recorded parent remains Scheduler FULL_WORKFLOW STOPPED at Preview, 84 safe changes, 0 local holds, 1 global blocker. Those historical counts were not reused as new authorization.

Read-only current WFRD ARQ/MRQ requests returned COMPLETE histories with the same fingerprints as the original Preview:

| Dimension | Rows | Raw normalized comparison fingerprint | Effective fingerprint |
| --- | --- | --- | --- |
| ARQ | 28 | `fba6bf8b3bf554f9a1d501362facb3db82ce78df4fc0d62d373489d0a173838c` | `94a9e4940bcaf351f0a28b6628da5a3edf6d7ee250ed1a77ee9ebc255780b695` |
| MRQ | 32 | `d8fd585f22669710e25f160ae326e322312d9bbe97a56b79a426ed1d015d9cef` | `f64e0a571711993723d7bbba91c4a80f7ff01c0ae0bed842d304d7cb03372edb` |

The predecessor row has OCF -68m, capex -73m, FCF -141m and weighted shares 1,004m, with null stocks. The removed successor row has year-end stocks and null flows. Their financial fingerprints differ. The proposal preserves that distinction and does not certify the historical MRQ debt as original as-reported ARQ debt.

After implementation, a pure read-only evaluation using current WFRD evidence and the live queue again returned `GLOBAL_BLOCKING_REVIEW`, with no applied decision. Live provider schema has no new preservation tables; live queue has no combined-review table/item.

## Reviewed model and binding

The new implementation is in `rawcandle/fundamentals/admin/accounting_boundary_review.py`.

`create_proposal()` reads published provider/canonical state and complete incoming histories. It creates an OPEN, non-authoritative proposal with operator placeholder null, stale false, and `production_authorized=false`. It verifies the published company/security/permaticker mapping, accepted ARQ shares provenance, both accepted Q4 identities/dates, exact source labels and the unchanged ARQ financial payload. Unsupported MRQ accounting payloads are rejected.

The artifact includes:

- exact three source keys, provider/dataset and separate action names;
- complete original accepted ARQ/MRQ provider and native records, IDs, raw JSON, original provenance/content hashes, normalized and financial fingerprints;
- actual incoming acquisition payloads and normalized/financial fingerprints, including dates, labels and updates;
- published company/security/company-key/provider mapping;
- both canonical Q4 IDs, fiscal keys, periods, source dates and established first-public dates;
- exact baseline generation, generation-manifest fingerprint, refresh-state rows, baseline fingerprint;
- MRQ complete-response row count, raw/effective fingerprints and absence context;
- fixed accounting roles and all calculation exclusions;
- SEC accession `0001603923-20-000017`, FY2019/FY semantics, fresh-start boundary and governing review/policy file hashes;
- per-action evidence fingerprints, combined evidence fingerprint, deterministic resolution ID, created timestamp and proposal fingerprint.

The original legacy row may have null per-observation provider-security ID. Its original value is preserved; the separate verified published permaticker mapping is bound explicitly.

`verify()`, `validate_pending()` and `verify_decision()` validate structure, semantic restrictions and fingerprints. Pending decisions are reconstructed against the current published baseline and source evidence before application. Proposal registration alone has no approval meaning. Approval requires a named operator, the unchanged actual candidate DBs verified against their receipt SHA-256 hashes, and an integrity-bound passing copy-rehearsal receipt covering both Q4s, established dates, unchanged existing financials, unrelated tickers, archive/context separation and P/B ARQ binding.

## Durable evidence schema and views

`ensure_store()` creates three additive tables only on inactive provider copies:

| Table | Primary key | Meaning |
| --- | --- | --- |
| `reviewed_historical_provider_observation` | original observation ID | Complete historical-only old MRQ source record and identity/baseline/absence/accounting evidence |
| `reviewed_accounting_boundary_resolution` | resolution ID | Linked operator decision, immutable proposal and rehearsal lineage |
| `reviewed_provider_observation_context` | exact serialized source key | Current predecessor partial-flow context bound to its normalized fingerprint and resolution |

Each stores `record_json` and `record_fingerprint`; UPDATE and DELETE triggers reject mutation. There are no cascading foreign keys to replaceable native observations. Repeated identical installation is idempotent; conflicting replacement records fail closed.

The archive contains original acquisition/native evidence, original timestamps/IDs/provenance, original content hash, normalized and financial fingerprints, accepted generation/identity, reason, complete-response absence proof, successor-stock role, resolution ID and creation timestamp. It is historical-only and calculation-ineligible.

Current MRQ context explicitly records:

- current provider evidence true;
- accounting basis PREDECESSOR and role PARTIAL_PERIOD_FLOW;
- full-quarter, canonical, TTM, share/P/B, stock-fallback and calculation eligibility all false;
- relationship DISTINCT_ACCOUNTING_OBSERVATION;
- October 1–December 13 interval tagged DERIVED_REVIEW_EVIDENCE, not a vendor-native start date.

Read APIs distinguish the layers:

- Existing `load_current_history()` reads native current stored history, including the existing independently defined source-window carry-forward behavior. It never joins the new archive.
- `current_provider_history()` explicitly excludes source-window carry-forward and adds exact current-row context.
- `historical_evidence()` returns separately queryable historical records.
- `combined_evidence()` is an explicit investigative view with membership/context labels; no calculation path uses it as a default input.

Native source counts, watermark derivation, completeness, canonical winner selection and financial readers do not include the archive. Replacing current ticker history preserves all three tables. No null filling, stock fallback or hybrid MRQ row is created.

## Provider evidence and canonical integration

Complete-history validation now retains the actual acquisition payload alongside normalized comparison fields. Replacement persists that acquisition payload instead of discarding support fields outside the 22-field comparison contract. Existing normalized financial/source fingerprints remain unchanged. This also preserves the incoming parent-equity/P/B support evidence.

`effective_fiscalperiod()` projects an effective label only for the exact reviewed ARQ key, after verifying the installed decision, bound row fingerprint and identity. Native `fiscalperiod`, raw payload and normalized fingerprints remain provider-reported `2020-Q4`.

Integration points:

- Preview performs combined-review revalidation after ordinary comparison. OPEN/rejected/stale combined items cannot become local holds or safe changes. Applied decisions and both original events remain explicit in JSON diagnostics and the Preview Markdown report.
- The comparator has a separate `accounting_boundary_application` semantic path. It does not manufacture or consume legacy fiscal-acceptance/removal approvals. Only the two exact events can be accounted for; additional unsupported events remain review-blocking.
- Refresh-set binding includes the complete combined application. Test's source revalidator independently reconstructs the decision and compares it to the newly authorized Preview.
- Provider candidate replacement validates incoming/absence bindings, installs the immutable historical/context/decision records on the inactive copy, then replaces native histories. Candidate validation checks exact native membership, row/observation IDs, context and archive integrity.
- `phase12d._provider_winners()` validates installed evidence and groups the exact source by reviewed 2019 Q4. Real December 2020 remains a separate 2020 Q4 winner. Publication-authority projection uses the same winner path.
- Preview publication-impact grouping recognizes the same exact reviewed identity. Fresh canonical rebuilding retains its established date-preservation map keyed by company/year/quarter.

Boundary errors are re-raised from canonical selection rather than treated as a disposable invalid fiscal label. Missing/drifting bound source observations cannot silently disappear from canonical history.

## Parent-equity and P/B

`schema/parent_equity.py` validates the accepted ARQ observation using the reviewed effective identity for the exact bound source. It still checks provider, ARQ dimension, report period and accepted shares; MRQ cannot become the source.

The canonical `v4_parent_equity_source` projection keeps its actual raw `fiscalperiod=2020-Q4` and adds `effective_fiscalperiod=2019-Q4` plus `fiscal_identity_resolution_id`. Thus the audit label is preserved separately from accepted interpretation. For unrelated observations the effective label equals the raw label and there is no resolution ID.

No P/B formula, share-unit convention, ownership approval or existing ownership-review eligibility was changed. Standard review needs for independently arriving new quarters remain governed by their existing contracts.

## Drift and published lifecycle

Pending application fails on changed keys, labels, financial or acquisition payloads, updates, availability/period end, accepted observation/provenance, canonical key/quarter/date, identity/permaticker, authority binding, baseline manifest/state, incomplete response, MRQ proof drift or old-key reappearance. Either stale side prevents the combined application.

After publication, the copied provider decision/archive supplies immutable lineage. Routine revalidation requires the same exact ARQ/current MRQ payloads and identity, the archived original evidence, the canonical fiscal keys/periods/established dates and a fresh complete absence attestation. Rebuilt internal quarter IDs may differ after a successful published rebuild; semantic identity and dates must still match. Incoming native observation IDs are checked against deterministic candidate source IDs.

Unrelated new periods may append without replaying the historical row as an active removal: archive rows are outside the ordinary absence comparator. New conflicting period or fiscal-quarter evidence, reappearance, source/context drift or authority drift restores a global review. An explicitly stale/rejected queue item cannot silently reactivate when the provider later returns similar data. There is no automatic renewal/rebinding after material drift; it requires a new authoritative review.

## Global review representation and approval boundary

The linked case uses a separate `accounting_boundary_review_item` table and append-only audit table in the existing operational queue DB. It does not use local-only `upsert_local()` or broaden existing action eligibility. Statuses include OPEN, APPROVED, STALE and REJECTED.

`FundamentalsAdminUIService` supports explicit proposal registration, read-only listing and named-operator approval with a bound rehearsal receipt. The UI's Refresh review area displays both exact actions, raw/accepted labels, source keys, roles, historical/current membership, calculation exclusions, authority, consequences, fingerprints and stale status. There is no generic approval bypass.

No real proposal was registered in that queue during this implementation. The real artifact remains an external OPEN proposal. Existing `ACCEPT_FISCAL_IDENTITY_REVISION`, `ACCEPT_RETAINED_HISTORY`, `CONFIRM_TRUE_SOURCE_REMOVAL`, wait/retry, local holds and unsupported-global rules retain their established semantics.

A fixture Preview regression proves:

1. Registering an OPEN proposal leaves WFRD global and Test unauthorized.
2. Explicit synthetic approval cannot retroactively authorize the old Preview.
3. A new fixture Preview can validate both linked meanings and independently authorize Test when otherwise eligible.
4. Source revalidation reconstructs the same bound combined application.

This is fixture-only testing. No real Preview or workflow Test/Production operation was executed.

## Real proposal and complete copy-only rehearsal

Non-authoritative proposal:

- Path: `/tmp/wfrd_implementation2/proposal_0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34.json`.
- Proposal fingerprint: `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`.
- Resolution ID: `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d`.
- Baseline generation: `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`.
- Status OPEN, operator null, Production authorization false; revalidated non-stale against the unchanged real baseline and fetched exact evidence.

Final rehearsal receipt:

- `/tmp/wfrd_implementation2/receipt_1275e85ca75f46eadd44a24bd28b7ed32ab0b87344aafd837b837965a776b380.json`.
- Receipt fingerprint: `1275e85ca75f46eadd44a24bd28b7ed32ab0b87344aafd837b837965a776b380`.
- Candidate DB SHA-256: provider `82cca9344d2c7cadc78223c27243ecb2b601181b6c60ccff367dfc687bdfb65e`; canonical `000253e7ab287fae943aa1fa160a8776f0e2004f9d6e8c66bbd20044802be438`.
- Candidates: `/tmp/wfrd_implementation2/receipt_bound_candidate_rehearsal/{provider.db,canonical.db}`.

`rehearse()` backed up the complete real provider and canonical DBs to inactive copies, validated the proposal, used a synthetic copy-only operator decision, installed the historical/context records, replaced only WFRD provider histories, and ran actual fresh canonical/TTM rebuilding and parent-equity acceptance. The synthetic decision is explicitly marked `copy_only=true` and exists only inside disposable candidates. Queue registration rejects such a decision, and a runtime Preview cannot treat it as published approval. It is not a live queue approval or an authoritative proposal status change.

Results:

| Assertion | Result |
| --- | --- |
| Provider ARQ raw label | 2020-Q4, unchanged in native and acquisition payload |
| Effective canonical identity | 2019 Q4 |
| Current MRQ | 32 rows; Dec. 13 present, old Dec. 31 absent |
| Historical store | 1 exact old MRQ observation, immutable/historical-only/calculation-ineligible |
| Current MRQ context | Predecessor partial-flow, all calculation eligibility flags false |
| Existing canonical quarters | 89,970 unchanged |
| Changed/removed existing canonical quarters | 0 / 0 |
| Unrelated company changes | 0 |
| Source-availability changes / historical date bootstrap | 0 / 0 |
| Existing first-public dates preserved | 89,970 |
| Canonical 2019 Q4 | 2019-12-31, first-public 2020-03-16 |
| Genuine canonical 2020 Q4 | 2020-12-31, first-public 2021-02-19 |
| Fiscal collision / date transplant / MRQ hybrid | None |
| P/B source | ARQ; raw 2020-Q4, effective 2019-Q4, exact resolution linkage |
| Provider quick check / FK errors | ok / 0 |

The complete current source independently adds WFRD **2026 Q3**, filed 2026-10-21. The rehearsal therefore adds one legitimate current-source quarter and initializes its own date under the ordinary contract. That addition is not caused by preservation. No existing WFRD quarter changes, no preservation-induced quarter/date initialization, and no unrelated ticker changes occurred. Counts were observed, not forced to the old Preview's 84 peer changes.

All new decisions, native rows and accounting context were revalidated on the final candidates after the rehearsal. No analysis database was written. Archive exclusion from financial inputs is enforced by native/current versus historical table separation and the existing ARQ-only canonical/TTM/P/B input paths, exercised by the focused tests.

## Tests and verification

Focused selection only:

```text
 tests/test_wfrd_accounting_boundary_review.py
 tests/test_fundamentals_admin_refresh_preview.py
 tests/test_fundamentals_admin_refresh_review_queue.py
 tests/test_fundamentals_admin_source_window_retention.py
 tests/test_fundamentals_admin_refresh_copy_test.py
 tests/test_publication_date_authority.py
 tests/test_fundamentals_pb_reporting.py
 tests/test_fundamentals_pb_quarterly_ownership.py
 tests/test_fundamentals_pb_new_quarter_review.py
 tests/test_fundamentals_admin_refresh_full_workflow.py
 tests/test_fundamentals_admin_ui.py
```

Commands used `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider -o addopts=''` with those explicit files/subsets and the production-database isolation guard.

- The selected regression run initially passed 363 cases and exposed 8 existing P/B fixture clock failures: its ASOF is 2026-10-09 while approval used the host date. The factory now pins only that fixture's review clock to its declared ASOF; production approval-date checks are unchanged.
- P/B new-quarter review group after that fix: **36 passed**.
- Affected fiscal/source/review/candidate/new-WFRD/Full-workflow regression rerun after additive comparator integration: **190 passed**.
- Final WFRD test group after final semantic guards and the additional conflicting-period case: **47 passed**.
- Other selected publication/P/B/UI regressions passed in the focused selection. There are no outstanding focused failures; the named selection now covers 374 cases across these runs, not a claim that a full repository suite was run.

The new tests cover exact proposal/action/schema binding, non-authoritative proposals, pending/global gates and new Preview requirement, archive immutability/survival/query separation, counts/watermark/completeness exclusion, MRQ eligibility/no hybrid/fallback, raw ARQ preservation, exact-source/ticker/dimension isolation, financial/source/identity/authority/baseline drift, stale/rejected lifecycle, reappearance/conflicts, actual candidate rebuilding, both Q4s/dates, parent-equity/P/B source binding, unrelated ticker invariance, published routine-quarter behavior, and read-only real-source proposal/copy boundaries.

Compile and whitespace checks passed. **Full suite: NOT RUN.**

## Production invariance

The following active authorities were hashed before work and checked unchanged after implementation, tests and rehearsal:

| Authority | SHA-256 |
| --- | --- |
| Active provider DB | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Active canonical DB | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Active analysis DB | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Live Review Queue | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` |

All real evidence reads used SQLite `mode=ro`/`query_only`; schema/replacement/canonical writes occurred on fixtures or inactive `/tmp` copies. No active generation, watermark, publication date, Policy V1 or resolver semantics changed. No live queue registration/decision or structural event was created. The provider downloads, proposal, receipts and candidate DBs remain under `/tmp` and are not committed. Existing unrelated worktree changes are excluded. Nothing is pushed.

## Exact next operator step

Review the OPEN proposal fingerprint and linked copy-only receipt above. In a separate explicitly authorized step, register that immutable proposal and approve **both linked actions** through the combined-review backend with the named operator and matching passing receipt. If baseline/source/authority evidence has changed, regenerate/rehearse instead of approving stale evidence.

Only after explicit approval may a **new real Preview** be requested. It must independently fetch/revalidate current evidence, recompute all changes/blockers and Test authorization, and stop if any review remains. The old Preview is not reusable. Neither this implementation nor the copy receipt grants Production authorization. No operator approval is requested in this implementation turn.
