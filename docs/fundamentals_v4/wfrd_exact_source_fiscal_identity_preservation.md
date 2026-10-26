# WFRD exact-source fiscal-identity preservation

Date: 2026-10-26. Request: WFRD-FISCAL-IDENTITY-PRESERVATION-1.

## Status: implementation stopped at the MRQ reconciliation gate

**No preservation action, schema, UI control, runtime approval or canonical overlay has been implemented.** This is a documented stop under sections I–J of the request, not a completed implementation. WFRD remains globally blocked. No approval is requested.

The governing [evidence review](wfrd_fiscal_identity_review_2026-10-25.md), commit `12e915cf4f908cef276c4d69ee49b1cbc9332607`, correctly recommends `PRESERVE_EXISTING_CANONICAL_IDENTITY` for the exact ARQ observation. That recommendation remains valid. Further inspection confirms that its separate MRQ event is a change between economically different observations, not an equivalent-source replacement that can be resolved implicitly by preserving the ARQ label.

The request explicitly requires:

> If exact MRQ semantics cannot be safely proven: STOP implementation before clearing the global blocker.

The accounting interpretation of the new MRQ cash-flow fields is now substantially supported, but the correct disposition of the removed successor MRQ observation is not established by an existing reviewed policy or vendor explanation. No new disposal/retention policy was invented to enable the ARQ implementation. Remaining uncertainty concerns how RawCandle should reconcile the two records, not whether the SEC calls the annual filing FY2019.

No complete accounting-segment model was built. This investigation does not prove that a full new model is necessary: a narrower, explicitly reviewed provider-history disposition might suffice after that policy is established. The exact-source preservation implementation remains deferred until that prerequisite is resolved.

## Reproduction before any provider request

The exact stored Preview was read first, without a network request:

`fundamental_reports/admin_runs/20261025T032113Z_refresh_fundamentals_bcfcec765c58/refresh_preview.json`

Its WFRD object reproduces the following through the existing pure `classify_review_scope()` function:

| Attribute | Stored result |
| --- | --- |
| ARQ true source key | `(WFRD, ARQ, 2020-03-16, 2019-12-31)` |
| Accepted fiscal identity | 2019 Q4 |
| Incoming provider fiscal identity | 2020 Q4 |
| Stable source key | true |
| Financial payload changed | false, all 22 compared fields |
| Duplicate incoming target identity | true |
| Duplicate target's other source key | `(WFRD, ARQ, 2021-02-19, 2020-12-31)` |
| Classification | REVIEW_REQUIRED |
| Review reason | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| Scope | GLOBAL_BLOCKING_REVIEW |
| MRQ removed source key | `(WFRD, MRQ, 2019-12-31, 2019-12-31)` |
| MRQ same-fiscal candidate | `(WFRD, MRQ, 2019-12-13, 2019-12-13)` |
| Removal reason | SAME_FISCAL_SOURCE_KEY_REPLACEMENT |
| MRQ chronology coherent / expected window covered | false / false |
| Future Test authorized | false |

Parent run `20261025T032113Z_refresh_fundamentals_d00eb7239fed_full_workflow_19b7f4fa` remains the stored Scheduler/FULL_WORKFLOW result: STOPPED at Preview, 84 safe effective changes, 0 local holds, 1 global blocker, no Production entry and zero Production writes.

## Targeted current-source inspection

After reproducing the stored result, two successful read-only provider requests inspected complete WFRD MRQ and ARQ history. No workflow was invoked. An initial sandboxed MRQ request failed DNS resolution without obtaining records; a network-enabled retry succeeded. Requests used the existing `SharadarClient` and normal configured authentication; no secret was printed or stored in the report.

Although these requests were made on 2026-10-26, both dimensions' normalized complete-history fingerprints exactly equal the stored October 25 Preview. This establishes that the inspected normalized financial evidence agrees with that Preview; it does not imply historical identity of every field of the full raw API response, because the Refresh fingerprint covers only its defined source fields.

| Dimension | Rows | Raw comparison fingerprint | Effective fingerprint |
| --- | --- | --- | --- |
| ARQ | 28 | `fba6bf8b3bf554f9a1d501362facb3db82ce78df4fc0d62d373489d0a173838c` | `94a9e4940bcaf351f0a28b6628da5a3edf6d7ee250ed1a77ee9ebc255780b695` |
| MRQ | 32 | `d8fd585f22669710e25f160ae326e322312d9bbe97a56b79a426ed1d015d9cef` | `f64e0a571711993723d7bbba91c4a80f7ff01c0ae0bed842d304d7cb03372edb` |

Both responses validate as `COMPLETE`, with no validation errors. Downloads were held only under `/tmp`; they are not committed. No provider database was updated.

## MRQ evidence: distinct predecessor flows and successor stocks

The removed published MRQ observation was read directly from the active provider generation with SQLite `mode=ro` and `query_only=ON`. The incoming December 13 record was inspected in the complete provider response.

| Attribute | Removed accepted observation | Current same-fiscal candidate |
| --- | --- | --- |
| ticker / dimension | WFRD / MRQ | WFRD / MRQ |
| date | 2019-12-31 | 2019-12-13 |
| reportperiod | 2019-12-31 | 2019-12-13 |
| calendardate | 2019-12-31 | 2019-12-31 |
| fiscalperiod | 2019-Q4 | 2019-Q4 |
| lastupdated | 2026-07-22 | 2026-10-22 |
| revenue / net income | null / null | null / null |
| operating cash flow | null | -68,000,000 |
| capex | null | -73,000,000 |
| free cash flow | null | -141,000,000 |
| cash | 800,000,000 | null |
| assets | 7,293,000,000 | null |
| receivables | 1,241,000,000 | null |
| inventory | 972,000,000 | null |
| payables | 585,000,000 | null |
| total debt | 2,456,000,000 | null |
| debt current / noncurrent | 92,000,000 / 2,364,000,000 | null / null |
| sharesbas | 69,999,966 | null |
| shareswa | 69,999,966 | 1,004,000,000 |

Removed accepted observation ID: `15d7195100fac119b2d47a45294860afaa594a73c8032cac2be0dca38eddd3bf`. Its stored raw payload has blank flow fields; this is not a missing-value conversion invented by this review.

The accepted December 31 MRQ row contains successor year-end stocks. Several match the [SEC year-end balance sheet](https://www.sec.gov/Archives/edgar/data/1603923/000160392320000017/R4.htm): assets $7,293 million, receivables $1,241 million, inventory $972 million and payables $585 million. Cash plus restricted cash totals $800 million. Its MRQ debt figures differ from the as-reported ARQ/filing amounts, so this report does not certify every MRQ stock as identical to the original audited filing. It contains no combined quarter earnings or cash flows.

The [2019 accounting policies](https://www.sec.gov/Archives/edgar/data/1603923/000160392320000017/R8.htm) establish the December 13 fresh-start date and separate predecessor and successor bases. Duration results through December 13 are predecessor results; the December 31 balance sheet is successor data.

The current MRQ cash-flow fields reconcile arithmetically to a predecessor residual interval ending at emergence:

| USD millions | Predecessor through Dec. 13 | First nine months through Sept. 30 | Difference | Current MRQ |
| --- | --- | --- | --- | --- |
| Operating cash flow | -747 | -679 | -68 | -68 |
| Capex | -250 | -177 | -73 | -73 |
| Free cash flow, OCF plus signed capex | — | — | -141 | -141 |

Sources: [2019 10-K cash-flow statement](https://www.sec.gov/Archives/edgar/data/1603923/000160392320000017/R7.htm) and [2019 Q3 10-Q cash-flow statement](https://www.sec.gov/Archives/edgar/data/1603923/000160392319000095/wftq3201910-q093019.htm). The full-year predecessor and first-nine-month amounts support an October 1–December 13 residual; the successor cash-flow amounts reported separately are different. This is a supported inference about the vendor's normalization, not a vendor-provided derivation or an explicit start-date field in the row.

### Reconciliation classification

**`UNRESOLVED_ACCOUNTING_BOUNDARY_MRQ_REMOVAL`** — descriptive classification in this report only, not a new runtime status or reason code.

The December 13 row should remain distinct evidence from the December 31 row. They have different true source keys, dates, accounting bases and populated financial fields. Their common `2019-Q4` label does not prove equivalence. Do not merge their non-null fields into a hybrid quarter, treat one as a fiscal relabel of the other, or assert that provider absence authorizes dropping accepted successor evidence.

What is proven:

- The old key is absent from the complete current response.
- The new key exists and contains predecessor residual cash-flow amounts consistent with the filings.
- The removed row contains successor stocks, not equivalent predecessor residual flows.
- The ARQ canonical authority remains independent of the provider-only MRQ history.

What remains unresolved:

- Whether the provider intentionally removed the successor MRQ observation as a documented normalization correction, and what its intended MRQ boundary treatment is.
- Whether RawCandle should accept removal from its active provider snapshot, preserve the old observation in a separately reviewed archive, or retain both as explicitly distinct accounting observations.
- How a reviewed disposition would preserve audit evidence and prevent an MRQ consumer from treating the new partial-period flows as a comparable full quarter or borrowing stocks from the removed successor record.

Vendor absence proves removal; it does not by itself prove the accounting-policy choice RawCandle should adopt. Equivalence is specifically disproven by the payload shapes. A new explicit disposal/retention interpretation cannot be hidden inside `PRESERVE_ACCEPTED_FISCAL_IDENTITY` for the ARQ key.

The current provider schema can physically store distinct source keys, but it has no explicit per-row accounting basis or duration start. Physical storage capacity does not resolve this policy question. The existing true-removal action is intentionally restricted to its established locally proven review shape; this mixed global fiscal review is ineligible. Its eligibility was not broadened.

## Preservation contract design — proposed, not implemented

The bounded action name would be **`PRESERVE_ACCEPTED_FISCAL_IDENTITY`**. It would authorize a canonical-interpretation overlay for one exact observation; the acquired provider label must remain `2020-Q4`. It must not be implemented by rewriting incoming `fiscalperiod`, raw payload, normalized source fingerprints or provider acquisition history.

The proposed immutable decision binding needs all of:

- Contract version, action, decision ID, decision timestamp, operator/reviewer identity, decision status and evidence fingerprint.
- Provider/dataset, ticker, dimension and exact `(ticker, dimension, date, reportperiod)` key.
- Accepted fiscal year/quarter and contradictory incoming provider year/quarter.
- Accepted observation ID and accepted normalized source fingerprint; exact incoming normalized fingerprint; unchanged financial-payload fingerprint; provider update date.
- Filing/source availability and period end.
- Published company/security IDs, company key, provider security identity, current canonical quarter ID and accepted fiscal key.
- Published generation/state binding and authoritative filing reference plus authenticated evidence summary.
- Independent MRQ disposition with exact removed/current keys, both available row payloads/fingerprints, complete-response absence proof, accounting interpretation, and an explicit reviewed policy decision. An `UNRESOLVED` disposition must make overall application ineligible.

Proposed lifecycle: OPEN proposal → explicitly approved preservation → revalidated in a new Preview. Stale evidence must reopen review without consumption. Rejected/keep-blocked must not apply an overlay. Existing status vocabulary should be reused where semantics agree; no statuses were added in this phase.

Rejection must cover drift in every material binding: key, dimension, fiscal labels, financial payload, availability/period end, observation ID, company/security/provider identity, canonical fiscal key/quarter ID, authoritative reference, published baseline or source fingerprints. `lastupdated` is included by the current normalized raw-source fingerprint, so changing it must not silently qualify for an exception. Do not invent a looser fingerprint for convenience.

Published overlays also need a deliberate lifecycle after candidate publication: a pending approval bound to an old generation is not automatically valid forever in later generations. The future implementation must preserve audited decision lineage while revalidating current source evidence and canonical identity after observation/quarter IDs are regenerated. An unbound ticker-level fallback is unacceptable.

### Comparison, candidate and publication-date integration requirements

Preview must continue showing the actual provider label and explicit applied-decision evidence. The effective canonical key may differ only for the exact bound observation. Other ARQ keys, MRQ rows, tickers and labels must be unaffected. Unresolved independent events must survive comparison and keep the global gate closed.

The overlay must be applied during canonical winner grouping in `phase12d._provider_winners()` and every relevant canonical-authority projection, not only in the comparison report. `replace_provider_histories()` and candidate validation must continue verifying actual incoming vendor fields. Review metadata belongs in a separate interpretation/provenance contract.

`fresh_rebuild_canonical()` preserves established first-public dates by `(company_id, fiscal_year, fiscal_quarter)`. The future overlay must leave these two exact identities and dates intact:

| Canonical key | Period end | Established first-public date |
| --- | --- | --- |
| (2368, 2019, Q4) | 2019-12-31 | 2020-03-16 |
| (2368, 2020, Q4) | 2020-12-31 | 2021-02-19 |

No date transplant, historical repair, or source-availability exception is part of this design. These integration points and requirements are documented, not implemented or certified by the existing regression tests.

### Review Queue / UI requirements

No executable preservation item was created. The live queue still has no WFRD row; global reviews are represented in Preview evidence rather than `upsert_local()`.

The future artifact/backend must support exact preservation evidence and show source key, dimension, provider and accepted labels, unchanged-payload result, filing reference, canonical consequences and stale status. A generic “approve anyway” button is not acceptable. The live queue's retained-history, fiscal-acceptance, true-removal, wait/retry and local-hold behaviors remain unchanged.

## Structural-event and TTM machinery

The existing `structural_break.py` distinguishes legal/security continuity from economic comparability and classifies TTM inputs by economic regime. Its current event contract has no source-bound fiscal-preservation action or intra-quarter predecessor/successor flow representation. The active published generation has no WFRD structural event, as established in the governing review.

No established rule inspected mandates automatically adding one solely because Chapter 11 occurred. No event was recorded. The old/new MRQ records do not feed canonical ARQ financial selection today; that is a useful existing boundary, but it does not authorize an unreviewed removal or establish safe semantics for all future MRQ readers. Any use of predecessor flows in canonical history or TTM would require explicit comparability/period policy before ingestion. This remains a separate architecture decision.

## Read-only consequence rehearsal

No candidate DB or Fundamentals Test stage was run. An in-memory grouping projection of the complete fetched ARQ history used the existing fiscal winner precedence and `select_valid_publication_winner()`, with a separate effective grouping key for the exact ARQ source observation. It did not alter any provider row or call the candidate builder.

Result:

- Raw source label for the exact observation remained `2020-Q4`.
- Effective grouping key was `2019-Q4` only for that observation.
- Published ARQ has 27 fiscal groups; the current complete ARQ response yields 28 with the proposed overlay.
- No existing fiscal group is lost. Both 2019 Q4 and genuine 2020 Q4 remain distinct.
- The sole added group is the independently observed 2026 Q3, filed 2026-10-21; it is not a side effect of preservation.
- No financial payload changed for any surviving published ARQ fiscal group.
- The published first-public dates above were read and remain unchanged in Production. This is not proof of a new overlay-enabled candidate rebuild, which does not exist.
- No other ticker was loaded into or changed by the projection.

As a separate gate probe, removing just the ARQ revision from the stored mixed event object while leaving the MRQ event unresolved still yields `GLOBAL_BLOCKING_REVIEW` and one global blocker through `classify_review_scope()` / `partition_changes()`. No runtime object or queue row was mutated.

**ARQ-only design projection: PASS. Complete ARQ+MRQ preservation/candidate rehearsal: NOT PERFORMED, stopped at MRQ policy gate.** No claim is made that the full WFRD blocker would become zero, that the new action handles drift, or that an unimplemented candidate path is validated.

## Tests

The directly relevant existing regression groups were run with the production-database isolation guard enabled:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider -o addopts='' \
  tests/test_fundamentals_admin_refresh_preview.py \
  tests/test_fundamentals_admin_refresh_review_queue.py \
  tests/test_fundamentals_admin_source_window_retention.py \
  tests/test_fundamentals_admin_refresh_copy_test.py \
  tests/test_publication_date_authority.py
```

**127 passed in 17.40s.** This includes existing fiscal/review drift checks, true-removal/retained-history behavior, unsupported-global blocking, candidate rebuilding and publication-date preservation regressions. Test stages here mean unit/regression tests against fixtures/copies, not the Fundamentals workflow's Test operation.

No source changes or diagnostic helper were added, so no new preservation schema/drift/UI tests were written. The requested implementation-specific tests remain unfulfilled because implementation was stopped. Passing the old regressions is not evidence of a new preservation action. The full suite was not run or widened.

## Real WFRD validation status

| Check | Result |
| --- | --- |
| Stored blocker reproduced before provider fetch | YES |
| Current source comparison fingerprints agree with exact Preview | YES, ARQ and MRQ |
| Preservation item created | NO |
| Preservation action/schema implemented | NO |
| Stale preservation item | Not applicable; none exists |
| MRQ interpretation | successor stocks versus distinct predecessor residual flows |
| MRQ reconciliation | unresolved reviewed removal/retention disposition |
| Global blockers after dry partial-ARQ-resolution probe | 1 |
| ARQ-only grouping projection | PASS |
| Complete overlay-enabled candidate rebuild | NOT PERFORMED |
| Publication dates changed | NO |
| Live queue mutation / approval | NO / NO |

## Production invariance

The active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`. Its databases, active manifest and Review Queue were hashed before investigation and checked again after the focused regression run and documentation work. Production access used `mode=ro` and `PRAGMA query_only=ON`; no queue constructor/action method, production writer, candidate builder, watermark writer or workflow entry point was invoked by the real-evidence diagnostics.

| Authority | SHA-256 |
| --- | --- |
| Provider DB | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Canonical DB | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Analysis DB | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Refresh Review Queue | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` |
| Active generation manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |

No provider, canonical or analysis mutation; no first-public or watermark mutation; no identity/Policy V1/resolver changes; no global-to-local reclassification; no Test/Production workflow execution; no new Preview or old-Preview authorization reuse. Only this report is committed. Unrelated worktree state is untouched. No runtime records, provider downloads, DBs or caches are committed. Nothing is pushed.

## Exact next phase and approval boundary

First establish an explicit MRQ disposition for the two bound observations, supported by vendor methodology or an independently reviewed RawCandle policy: distinguish predecessor partial flows from successor stocks, determine active-snapshot versus historical-evidence retention, and show how MRQ consumers avoid cross-basis merging. Assess whether this needs only a provider-history audit extension; do not assume a full new multi-segment canonical-quarter model is necessary.

Then implement the exact-source canonical overlay and its queue/artifact lifecycle, candidate integration and implementation-specific drift/publication regressions. Rehearse the complete combined event on copies. Only once all of that succeeds may an exact non-stale WFRD proposal be shown for explicit preservation approval. Approval must bind its evidence and authorize neither Production nor a silent MRQ disposition. A new Preview is required after that approval; Test/Production remain separate later boundaries.

**Current next approval step: none.** An unresolved prerequisite prevents presenting this as an approval-ready preservation decision. The correct current action is to keep the global blocker and return to the bounded MRQ policy/architecture phase.
