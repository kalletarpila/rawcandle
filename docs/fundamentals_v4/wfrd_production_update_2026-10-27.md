# WFRD Production authorization — stopped before consent

Task: WFRD-PRODUCTION-AUTHORIZATION-1. Date: 2026-10-27. Starting HEAD: `fb90d46854fd94c77a338a41f616bd696fd885fd`.

**STOPPED_SOURCE_DEFECT. Production preflight cannot pass. No Production authorization question was presented, no Production operation was invoked, and no publication boundary was entered.**

The request explicitly requires stopping on a source defect and making it a separate implementation phase. The defect below was found during the required narrow review of the actual Production candidate path, before fresh network/source/bundle work or any runtime mutation. No source was modified and no pytest/full suite ran.

Governing evidence: [Test on copies](wfrd_test_on_copies_2026-10-27.md) and [approved WFRD review history](wfrd_combined_preservation_approval.md).

## Exact authority inspected

| Field | Stored/verified evidence |
| --- | --- |
| Preview | `20261027T101828Z_refresh_fundamentals_052a88da4fba` |
| Preview fingerprint | `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9` |
| Test | `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test` |
| Test outcome | COMPLETED |
| Stored authorized effective changes | 94 |
| Stored Production gate | AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED |
| WFRD resolution | `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d` |
| WFRD proposal | `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34` |
| Registered V2 receipt | `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3` |
| Approved decision | `be718f56947cc3774bcd4fa9567620d4bf94511a704b503d59ffc9e086b71865` |
| Current queue item | APPROVED / operator kalle / no stale or rejection reason |

The existing read-only `load_production_authorization()` accepts this exact saved Preview/Test pair and its durable Test evidence. Decision integrity verification passes. The stored AUTHORIZED gate is preserved; it is not relabeled or treated as operator permission. It also does not prove that the separate Production builder installs WFRD semantics correctly.

## Blocking Test-versus-Production candidate construction gap

The successfully tested copy path passes the applied decisions explicitly:

```python
# refresh_copy_runtime.py:1184, normal Test candidate construction
replace_provider_histories(
    provider_candidate, selected_histories, identities,
    applied_at=applied_at, merge_plans=selected_merge_plans,
    boundary_applications={
        item["ticker"]: item["accounting_boundary_resolution"]
        for item in changed
        if (item.get("accounting_boundary_resolution") or {}).get("applied")
    },
)
```

The actual Production path omits that argument:

```python
# refresh_production.py:952, normal Production candidate construction
replace_provider_histories(
    provider_candidate, histories, identities,
    applied_at=utc_now(), merge_plans=merge_plans,
)
```

In `refresh_copy_runtime.py:400`, `boundary_applications` defaults to None. The loop over that argument is the mechanism that verifies candidate inputs and calls `boundary.install_on_copy(provider_db, application["decision"])` before native histories are replaced. That installation creates the immutable historical MRQ evidence, current MRQ context, and reviewed ARQ interpretation/decision store on the inactive provider copy.

The current published provider has **zero installed reviewed decisions and zero historical MRQ archive rows**, as expected before publication. Production backs up that published provider to construct its fresh candidate; it does not inherit the deleted Test candidate. No alternate accounting-boundary installation call exists in `refresh_production.py`. Consequently the Production call shown above cannot install the required approved WFRD resolution/archive/context through this path, even though source revalidation can recognize the approved decision in memory.

This is a real missing candidate-installation step, distinct from an approval or presentation problem. Without the installed decision, the incoming native ARQ 2020-Q4 label has no reviewed effective 2019-Q4 projection in that candidate, and the removed MRQ has no required historical-only archive/context installation. The required Production semantics cannot be certified. No claim is made that incorrect data was actually published or that later candidate checks would necessarily permit publication: the Production path was not run.

The omission must be fixed and validated in a separate bounded implementation phase. The natural parity fix is to pass the validated applied accounting-boundary applications into the Production provider builder, as Test does, and verify the expected decision/archive/context explicitly in candidate and postflight checks. Regression evidence should cover raw/effective ARQ identity, both genuine Q4s/dates, historical/current MRQ separation, calculation exclusions, and ARQ P/B/share provenance through the real Production candidate path on disposable copies. No manual installation into active provider/canonical storage is an acceptable substitute.

## Read-only closeout and untouched state

Fresh local hashing matches the completed Test's closeout for provider, canonical, analysis, active/generation manifests, journal, and queue. Scheduler config was hashed separately for closeout. The active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; watermark remains `2026-10-21`. Journal state/step remain COMPLETED, activation ACTIVATED_AND_VERIFIED, postflight PASSED, recovery NOT_REQUIRED.

The live WFRD decision remains APPROVED and unchanged. DHR's exact P/B review remains OPEN and unchanged; the entire live queue hash remains `d92e21f51d002fe6d9093f1db0da0b02d062fe466217b7285d19ddbbb680c17d`. No review mutation, source fetch, candidate build, Preview, Test, Production, journal preparation, generation activation, backup creation/deletion, recovery action, or publication-authority workflow was performed in this attempt.

| Stage 1 gate | Result |
| --- | --- |
| Exact saved Preview/Test authorization reader | PASS |
| Stored WFRD decision integrity/status | PASS; external current-source freshness not revalidated after stop |
| Fresh full source revalidation | NOT RUN after source-defect stop |
| Fresh market semantic/bundle comparison | NOT RUN after source-defect stop |
| Fresh taxonomy binding comparison | NOT RUN after source-defect stop |
| Full operational lock/storage/publication preflight | Not completed after source-defect stop |
| Production preflight | FAIL_SOURCE_DEFECT |
| Production consent question / explicit Production YES | Not presented / not received |
| Production run / publication boundary | None / not entered |
| Active generation / watermark / financial state changed | NO / NO / NO |

The stopped attempt does not assert fresh WFRD source validity from a stored non-stale flag. The recorded market/taxonomy/source PASS results remain historical Test evidence and are not reused as new Production preflight results. DHR's OPEN case is not the cause of this stop; no new global blocker interpretation was invented for it.

## Next phase and commit scope

Implement and validate the bounded Production candidate parity fix separately, then restart this Production task from Stage 1. Freshly revalidate the exact saved Preview/Test pair and current source/market/taxonomy/baseline under the existing contract; stop if stale. Only after every Stage 1 gate passes should the one exact Production YES/NO question be presented. This report supplies no Production consent and authorizes no replacement Preview/Test.

Only this stopped-authorization report is committed. No DB, manifest, journal, queue, download, runtime evidence, backup, cache, or unrelated work is included. Nothing is pushed. The proposed successful-publication commit title is not used because no publication occurred.
