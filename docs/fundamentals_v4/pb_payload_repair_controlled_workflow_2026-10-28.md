# Provider payload repair: controlled workflow and frozen copy rehearsal

**Current Stage 1 update:** exact GE/RTX/T live OPEN registration is complete; no source repair or approval has been performed. See the successful restart appended below for the current bindings and pending YES/NO gate. Earlier blocked-attempt text is retained as history.

2026-10-28. Governing [completeness-repair report](pb_provider_payload_completeness_repair_2026-10-28.md), commit `f1b56911e1efebc859eb7dcff4904a06cd10a034`, and [factor-null audit](pb_ownership_provider_factor_null_audit_2026-10-28.md).

**The controlled source-repair workflow is implemented. GE/RTX/T each passed exact-source copy rehearsal and independent fresh revalidation. All 384 distinct focused tests passed. Existing financial values, ownership decisions and live runtime remain unchanged.**

**Operational Stage 1 remains incomplete: OPEN registration and its operator confirmation were stopped by the occupied scheduler lock. No live authorization question has been issued, and no authorization has been inferred.** PID `666030`, `/home/kalle/projects/stockcore/.venv/bin/python -B -m tools.daily_yahoo run`, holds `logs/stock_update_scheduler.lock`. The required nonblocking safety check raised `BlockingIOError` before queue-copy creation or registration. An initial staging helper then failed because that blocked snapshot had not been created; it performed no staging actions. Independent immutable-generation copy rehearsal and read-only verification subsequently completed without attempting registration. This report distinguishes those results from a completed OPEN/approval stage.

## 1. Architecture and existing-contract review

New [provider_payload_workflow.py](../../rawcandle/fundamentals/admin/provider_payload_workflow.py) wraps the existing `provider_payload.py` comparison and explicit inactive-copy replacement primitive. It does not change the existing acquisition writer, financial normalization, financial fingerprints, source-key replacement, ownership detector, ownership registry, P/B calculation, scoring or ordinary refresh dispatch. The completeness repair classification remains excluded from automatic replacement classes.

Source repair restores exact same-source evidence. Ownership review separately accepts a continuing economic-unit interpretation. P/B eligibility separately requires accepted ownership/equity/price evidence. Restoring factor/equity can expose a continuation candidate without approving it. No prior-quarter value is carried forward.

The normal `SharadarClient` and `fetch_complete_history` retain complete acquisition payloads. Existing full-payload canonical SHA-256 and ABSENT/NULL/VALUE fingerprints are reused without administrative hash exclusions. A compatible strict key extension is repairable; null→value and existing-value revisions remain real revisions and are not authorized by this workflow. Financial contradiction, removed keys, fiscal/source-identity mismatch, incomplete history, duplicate source or reviewed/retained source context fail closed.

All real candidate work in this phase is limited to three Q3 ARQ keys. No historical repair cohort was rerun or expanded.

## 2. Deterministic proposal schema

`PROVIDER_PAYLOAD_COMPLETENESS_REPAIR_V1` binds ticker, complete exact source key, SHARADAR/fundamentals provider/source, known company/security/provider stable identity and company key, original observation ID/content hash, old/new completeness and full-payload fingerprints, unchanged raw/effective financial fingerprints, restored/null/value field lists, financial-change assertion, original timezone-aware source fetch timestamp, baseline generation/role paths/hashes, active manifest hash, market hash, scheduler configuration hash and relevant implementation/ownership contract file hashes.

Proposal status is PROPOSED, stale=False and live_repair_authorized/ownership_authorized/pb_authorized=False. Proposal fingerprint covers the complete canonical object except its fingerprint; repair ID is `ppr_` plus that full fingerprint. Missing identity is rejected. `PROVIDER_PAYLOAD_COMPLETENESS_BATCH_V1` binds the sorted unique proposals/keys and common generation. The batch rejects duplicate keys/companies and different baselines.

`revalidate` rebuilds the exact proposal using current stored evidence, current baseline and independently fetched complete history. The original fetch time is preserved as immutable proposal identity; a new revalidation fetch time is recorded separately. A changed code file, market, generation, stored observation or fresh source invalidates the proposal instead of silently rebasing it.

## 3. Copy-only receipt schema and assertions

`PROVIDER_PAYLOAD_COMPLETENESS_REHEARSAL_V1` binds one proposal, source key, old/new observation identities, full comparison, exact batch/baseline, candidate paths/hashes for provider/canonical/analysis, measurement date, result/result fingerprint and passed=True. Each per-item receipt also binds the complete three-repair batch result. The resulting provider row uses a new ID derived from exact provider/source/key/full-payload hash; the old immutable generation remains untouched.

`rehearse` copies finalized role bytes, fsyncs them and verifies their baseline hashes. The existing copy repair primitive replaces only selected provider/native observations. The unchanged parent-equity acceptor runs on a scratch database containing only selected canonical quarters; only their source/equity projections and observation provenance references are copied back. Existing non-null equity cannot change. No all-history reconcile or scoring run occurs. The analysis role remains byte-identical.

`measure` recomputes assertions from databases: exact replacement, full payload and expected completeness/content hash, unchanged native and canonical existing financial values, unique source key, unchanged unrelated provider/canonical tables and ownership artifacts, unchanged unrelated ownership detector cases, source/equity/provenance identity, SQLite quick_check, FK check, integrity check and no ownership/PB approval. Resealing a falsified assertion or repair identity does not bypass validation. Registration and publication remeasure the candidate files rather than trusting stored PASS flags.

## 4. Durable proposal/receipt binding

`PROVIDER_PAYLOAD_COMPLETENESS_RECEIPT_BINDING_V1` pins proposal fingerprint, receipt fingerprint, source key, baseline generation, complete old/new source comparison, candidate hashes, result fingerprint and batch fingerprint. Validation independently reconstructs the expected new observation ID and complete source-repair provenance including fetch timestamp.

The same proposal with a different receipt is rejected. The same key with another proposal is rejected while an earlier item is OPEN or APPROVED; an explicitly reasoned REJECTED/STALE item permits a new review. An exact duplicate registration is idempotent and does not append another registration audit event. Missing/legacy unbound items, malformed decisions and missing or altered original audit bindings are non-approvable.

## 5. Typed operational queue and append-only audit

`PROVIDER_PAYLOAD_COMPLETENESS_REPAIR_ITEM_V1` uses a separate `provider_payload_repair_review` table in the operational queue, outside financial databases. Columns are repair_id, source_key, status, proposal_json, receipt_json, binding_json and decision_json. States: OPEN, APPROVED, REJECTED, STALE. OPEN has no decision and no authorization. APPROVED means only the exact explicitly authorized source repair has passed publication postflight; it is not an ownership approval.

Registration is atomic for the frozen batch and appends exactly one `PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN` event per item to the existing generic `refresh_review_queue_audit`. Explicit terminal decisions and completed source repairs append their own events. Existing audit rows are never rewritten by the workflow. `_read` requires exactly one intact original registration binding and validates status/decision consistency.

The isolated queue fixtures demonstrate registration, idempotency, conflicts and unchanged ownership rows. **Real-data queue-copy registration was not performed because runtime safety preflight was blocked. The live operational queue is byte-identical and does not contain the new repair table.**

## 6. Read-only confirmation and future UI

`confirmation(project_root, queue_path, repair_id, fresh_history)` reads the typed item and audit, rebuilds the proposal against current source/baseline, checks candidate hashes and returns repair ID, ticker, exact key/status/decision, old observation/hash/completeness, fresh payload fingerprint, restored fields, fresh factor, financial-values-changed=False, proposal/receipt/binding/batch fingerprints, receipt PASS, baseline generation/candidate hashes and source-repair-only approval action. It writes no queue/database state and fails closed on stale/malformed/mismatched evidence.

All confirmation behavior is tested on isolated queue copies. The three real confirmations remain pending guarded OPEN registration; raw proposal/receipt bindings below are verified but are not represented as registered review confirmations.

Backlog: add a distinct source-repair review card using these fields, showing old completeness, exact source key, restored fields, fresh factor, financial-change flag and `EXPLICIT_YES_SOURCE_REPAIR_ONLY`. Keep the ownership review action separate. No UI redesign is implemented here.

## 7. Fresh GE/RTX/T evidence and frozen identities

Baseline generation: `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`. Published source watermark: **2026-10-27**. Batch fingerprint: `03a973f7d891b895d2bf2c3cec424a42f7dc9f378a52ff7c87d9e2114546c02c`.

| Ticker | Exact source key | Company / security / provider ID | Original ARQ fetch UTC | Complete ARQ / MRQ rows |
| --- | --- | --- | --- | --- |
| GE | GE\|ARQ\|2026-10-20\|2026-09-30 | 931 / 934 / 199688 | 2026-10-28T14:58:22.362663+00:00 | 42 / 40 |
| RTX | RTX\|ARQ\|2026-10-20\|2026-09-30 | 1928 / 1938 / 199251 | 2026-10-28T14:58:23.075086+00:00 | 40 / 40 |
| T | T\|ARQ\|2026-10-21\|2026-09-30 | 2123 / 2133 / 198738 | 2026-10-28T14:58:24.060941+00:00 | 42 / 40 |

Six normal ARQ/MRQ acquisitions passed COMPLETE validation. Only the three exact ARQ rows enter proposals/candidates. Independent new ARQ acquisitions at `2026-10-28T15:26:21.050086+00:00`–`2026-10-28T15:26:47.098147+00:00` matched all three frozen full payload, completeness, financial and stored/baseline bindings exactly. No source drift was silently accepted. Registration still requires a new fresh check after safety locks are free.

| Ticker | Proposal fingerprint | Receipt fingerprint | Binding fingerprint |
| --- | --- | --- | --- |
| GE | ec59380018faafdc85892995d381025a1c2ab90cec73f16cb3f95b8e57b00f2b | a47ee93a5eabb8fc9daf6e3f8e47e77e7c8e9703cc2b0e8df71f79152973bff9 | 676a9673f444fad1c8048b9e533c1f147ef7435cdb69d07ae4525ee5a44bb03a |
| RTX | fa48737bb61a6474741efd0898b566be33d244b0a3edb8043d99a20c840ea8b6 | 321385e8419079c0f1fcc9429157c4aa7f5beedc6d0615e411f47ff0ff7bec62 | 902073de4948367f158e79c3272a7359a4593fe797f2f0052c61845fcd3b4b85 |
| T | 76eda17a57f14875241e571fc7836f101b09f7fe29b46a5c77e3e0924ad8e017 | 4cf9b61c0341be6846aebfc6e45df03c659fd293e8ae89ef28efce39fbff6b50 | 6b17885ed521864a69fe705feef771219a7111a5f5ec68bc131fa43c11d1d7da |

Each repair ID is `ppr_` plus its full proposal fingerprint.

| Ticker | Old observation ID | Old content hash | New copy observation ID | Fresh payload/content hash |
| --- | --- | --- | --- | --- |
| GE | 5806bfc4a10a7d809ef83498c8360b26660ce28502d81408e7b189426a2cab24 | d47fcb1f67a85963201f7d0c0745672e6ba99bb75c9c7ad50f8581cfdcb86375 | 30891b203267dfa12056544407c8dcdff68edd3001822a4622d975c71d7e2248 | 14eba2facdb54dd1247923e9b684401709621787e8728ee8ab7665551a36e816 |
| RTX | bfd42bf2f633cfb8e511931673bc6769ea1bad22859c227d602d7328d42ea4f1 | 50238350ed044491f6198bbb922dc0a562f2badfc46bde9ad266a8ed6d6462ec | 9dda4193acb8676c52ee8b235e9822b609c4693234323ef25452681d366146f5 | 56b0a3e45b7b69e3308c4e3863aadb44c789746259283cfb0c08fab8361e2e84 |
| T | a04ecf0968eaee10a2018c39e9d80057e59520770412d784f518bdd0c3ad6e1c | 0fbe9ab6418a1f910f4bb40dc6231889a9c91e423354b94d43075c173e500be0 | 26198cc5927cf7a291d0fcb52eec541a1f16216c31b41670ffb4f9705c8dd2aa | 6f744958e889dc70bbeec7162a795a6cc451e77189fbd34ead8d1a8f07eee577 |

| Ticker | Old completeness fingerprint | New completeness fingerprint | Unchanged financial effective fingerprint |
| --- | --- | --- | --- |
| GE | e07a4222563fc8869ffbdcdb8e1546960aeabc214f80bea0c5e2c2b3a81c1f2c | 604a0cf24b3a4fb019601b97957729d425017b4b15dc1369367d8eaffce52c14 | 1ac5c84676f0162f14be2e7853236e3793afb817960a2ba06568299e84ee883a |
| RTX | e07a4222563fc8869ffbdcdb8e1546960aeabc214f80bea0c5e2c2b3a81c1f2c | 604a0cf24b3a4fb019601b97957729d425017b4b15dc1369367d8eaffce52c14 | 1ab4aa70967b849efb96367f2dcc32c7af332db0df65de071b149eb58aaa5313 |
| T | 887a4fa7a29ec784be9da84977b36775cb7ca3055c72e9cff4a0ee38166efb09 | 604a0cf24b3a4fb019601b97957729d425017b4b15dc1369367d8eaffce52c14 | d40f05fba5f26fe3fc5238d624da37887a3478575434ec2a43aeaa14bc58d5d8 |

All old rows have 29 keys; fresh rows have 112. All 83 additions are ABSENT→VALUE. Previously present source/financial values remain compatible, including the legacy normalized null representation of optional diluted shares; existing financial fingerprints are unchanged. No null→value revision is disguised as a repair.

## 8. Restored fields and three-copy rehearsal

The same 83 source keys are restored for each company. Canonical SHA-256 of the following sorted field-list array: `d03a4b213f417f1d28a3e3c81cf7f8c6a17b4f0258ebd1f9a83c0f83a5a88ed2`.

```text
accoci, assetsavg, assetsc, assetsnc, assetturnover, bvps, cashnequsd, consolinc
cor, currentratio, de, debtusd, depamor, deposits, divyield, dps
ebitdamargin, ebitdausd, ebitusd, ebt, eps, epsdil, epsusd, equity
equityavg, equityusd, ev, evebit, evebitda, fcfps, fxusd, grossmargin
intangibles, intexp, invcap, invcapavg, investments, investmentsc, investmentsnc, liabilities
liabilitiesc, liabilitiesnc, marketcap, ncf, ncfbus, ncfcommon, ncfdebt, ncfdiv
ncff, ncfi, ncfinv, ncfx, netinccmnusd, netincdis, netincnci, netmargin
opex, payoutratio, pb, pe, pe1, ppnenet, prefdivis, price
ps, ps1, retearn, revenueusd, rnd, roa, roe, roic
ros, sbcomp, sgna, sharefactor, sps, tangibles, taxassets, taxexp
taxliabilities, tbvps, workingcapital
```

| Ticker | Repair | Fresh factor | Recovered parent equity USD | Read-only ownership classification | Hypothetical P/B | Actual Current P/B reason |
| --- | --- | --- | --- | --- | --- | --- |
| GE | PASS | 1.0 | 17522000000.0 | CONTINUATION_CANDIDATE | 17.55436232103115 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED |
| RTX | PASS | 1.0 | 69250000000.0 | CONTINUATION_CANDIDATE | 3.7920742076120066 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED |
| T | PASS | 1.0 | 106775000000.0 | CONTINUATION_CANDIDATE | 1.3211122199455392 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED |

Hypothetical P/B is measured using the unchanged current-price/accepted-quarter formula; it is not forced to provider pb. Source equity/equityusd, sharefactor, price, marketcap and pb are fresh same-key payload values. Existing financial values remain unchanged; newly available same-quarter parent-equity fields and their provenance are populated only on inactive canonical copies. No ownership decision or approved P/B is produced.

| Candidate role | SHA-256 |
| --- | --- |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 147e6ef965af071062fb89170d62b9bb471267c2cc5ac6cad4278afa2dbba054 |
| provider | 45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a |

All 12 receipt assertions are True for all three exact observations. Provider and canonical unrelated content comparisons pass; analysis is byte-identical. This phase repaired no additional real rows.

## 9. Runtime safety and registration result

The read-open, nonblocking preflight takes the existing Fundamentals UI-operation, Production and scheduler kernel locks without rewriting owner text, checks taxonomy activity and requires the publication journal to be terminal/recovery not required. Real-root registration always invokes this guard, including registration against disposable queue copies. It is reentrant only within the same guarded root/log-directory context.

The journal is COMPLETED, production_writes_blocked=False; taxonomy reports lock_active=False. The scheduler kernel lock is actively owned by the external daily Yahoo process identified above. No lock was removed, released, overwritten or bypassed. OPEN registration and the combined YES/NO confirmation stage are therefore deferred. No live queue registration occurred and no review item is claimed to be OPEN for this real batch. No normal Fundamentals Preview/Test/Production, scheduler start/drain, registry repin or automatic repair was run.

Read-only runtime evidence captured at `2026-10-28T15:24:38.059575+00:00` matched the previously frozen live state for all nine files:

| Runtime role | Unchanged SHA-256 |
| --- | --- |
| active_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e |
| generation_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| journal | 8c88e3894b9376be4b56cc51041274d7ca368967e87dbf532f5c491e54190eae |
| market | 0dd3a0fe6d4de465a075e7771128d11b370f3159b26a27c9d05d810fb360832f |
| provider | 6d0262597c4248d40ce8b7ac79b164b1f8fcdfc09fa72283e35486d94380ae81 |
| queue | 746836b89c2bc2bcf5880812bdcdd64024c2c4398e196e21746b74fbf0f68b99 |
| scheduler_config | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |

All nine existing ownership rows remain identical, OPEN and without approval/result. Existing ownership/UI/PB source hashes match the prior audit. Whole immutable provider/canonical/analysis hashes preserve WFRD reviewed fiscal/accounting-boundary state. The repair workflow has not changed the active generation, provider watermark, journal, market, scheduler configuration or queue. The end-of-work read-only comparison at `2026-10-28T15:31:00.286157+00:00` independently confirms all nine hashes, ownership rows and existing source hashes still match; the live queue still has no repair table and the watermark remains 2026-10-27.

## 10. Explicit authorization boundary

The user task's section J requires an explicit later combined YES/NO after the exact OPEN proposal/receipt confirmations. That gate has not been reached because section T's scheduler safety check blocked registration. **No YES is requested or accepted for publication in this report.** Earlier YES replies in the WFRD history do not authorize this separate repair batch.

After the lock clears, freshly revalidate the frozen identities, register the three exact OPEN items on a disposable queue copy, obtain the three read-only confirmations, and present one combined YES/NO question binding the exact proposal/receipt fingerprints, source keys, baseline generation, all 83 restored fields and financial-values-unchanged assertions above. Any drift stops the case rather than silently regenerating a proposal.

A later explicit YES authorizes only those exact source-payload repairs. It does not authorize ownership continuation, P/B approval, normal Fundamentals Preview/Test/Production, unrelated repairs, historical bulk repair or auto-continuation. The exact OPEN items must then be promoted to the actual operational queue under fresh safety/source/candidate checks; this implementation phase does not do that promotion.

## 11. Implemented Stage 2 publication lifecycle

`publish_batch` is implemented and exercised only on isolated projects in tests. It requires literal confirmed=True and the exact authorized batch fingerprint; actual-root use additionally requires production_intent=True, the actual operational queue, no symlink, no test client, no rehearsal flag and no fault injection. Isolated roots require rehearsal=True. There is no automatic scheduler or ordinary refresh dispatch to this function.

After later YES, acquire the existing UI, Production/scheduler and taxonomy publication locks and journal guard. Require all selected items still OPEN with NULL decisions. Re-fetch COMPLETE normal provider histories; verify old observations/source identities, proposal/receipt/batch, active baseline, candidate files and absence of a superseding refresh. Take an immediate queue transaction, reread exact items and baseline, and remeasure candidates.

Clone the already validated inactive role candidates into a unique run-owned directory, verify hashes/fsync, and take verified rollback backups of all OLD roles. Reuse the existing candidate manifest, durable publication journal, immutable-generation preparer and atomic generation-pointer activation. The journal pins OLD generation/manifest, full repair batch, bindings, candidate role hashes and source-only decisions. The source watermark stays unchanged; this is not a provider-history refresh.

At the last publication gate, recheck source baseline, items, prepared candidate hashes and journal identity. Activate only the prepared immutable generation. Postflight verifies all active role hashes/SQLite health and remeasures exact scope, unrelated data and ownership outcomes against the retained OLD baseline. Only then write durable COMPLETED/PASSED, mark the repair-only items APPROVED and append their source-repair audit events. No active provider row is manually updated in place.

## 12. Rollback, recovery and queue retry

Before durable postflight completion, any boundary failure calls the existing full `restore_old_generation` recovery path. Both injected pre-activation and postflight failures restore the complete OLD generation/role hashes, leave source-repair items OPEN without decisions and finish the journal RECOVERED. Run-owned candidates allow the existing cleanup ownership checks to succeed. No partial database patch is used.

After durable COMPLETED/PASSED, a queue-finalization failure does not roll back an already completed generation. `synchronize_completed` verifies the exact active generation, role hashes, selected item bindings and durable source-only decisions, then finalizes only this typed queue state. Retry is idempotent; it does not publish again or duplicate approval events. Incompatible terminal queue state fails closed. Existing journal recovery remains authoritative after a crash.

## 13. Ownership and P/B re-evaluation boundary

The unchanged detector and hypothetical preview run read-only during candidate measurement and again during future publication postflight. GE/RTX/T are CONTINUATION_CANDIDATE on copies. The generation ownership artifact is unchanged and actual Current P/B stays OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED. All source decisions explicitly set ownership_authorized=False and pb_authorized=False. Ownership review and controlled P/B publication remain separate later actions requiring their existing contracts.

## 14. Focused regressions and validation

New [test_provider_payload_workflow.py](../../tests/test_provider_payload_workflow.py) contains 38 isolated tests covering deterministic proposals/receipts, read-only confirmation, exact identity/source/financial drift, candidate/generation mismatch, duplicate registration, conflicting receipt/proposal, explicitly stale replacement, malformed/unbound items, immutable original audit binding, selected financial/native/header corruption, unchanged existing non-null equity, no ownership/PB side effects, explicit publication intent, source-only immutable generation publication, full OLD rollback and completed queue-only retry. Three added safety tests prove scheduler, journal and taxonomy blockers stop preflight without rewriting lock-owner evidence.

The eight directly relevant groups below passed **381 tests in 273.88s**; the three subsequently added preflight tests passed in **8.68s**. Total: **384 distinct focused tests PASS**, including all 38 new workflow tests. No runtime source changed after that regression run; only those three additional tests and documentation were added.

```text
tests/test_provider_payload_workflow.py
tests/test_provider_payload_completeness.py
tests/test_fundamentals_admin_refresh_copy_test.py
tests/test_fundamentals_generations.py
tests/test_wfrd_accounting_boundary_review.py
tests/test_wfrd_production_candidate_parity.py
tests/test_fundamentals_pb_reporting.py
tests/test_fundamentals_pb_quarterly_ownership.py
```

Existing completeness fixtures cover compatible projection→full, absent→value/null, null→value, value→absent/different value, financial contradiction, incomplete and duplicate histories, reviewed/retained observation protection, generic source-key replacement and full acquisition preservation. Existing WFRD accounting-boundary and production-candidate parity regressions pass unchanged. The three actual GE/RTX/T copy cases independently prove real identity/economic outcomes without hard-coded ticker branches in the workflow.

Full suite: **NOT RUN**, as requested. No external financial/legal research or valuation advice was needed; this is local source-contract implementation and normal provider evidence verification.

Evidence remains outside Git under `/tmp/pb_payload_repair_controlled_workflow`: fresh_histories.json, proposals.json, receipts.json, fresh_revalidation.json, readonly_runtime.json, candidate/{provider,canonical,analysis}.db and focused test logs. These contain disposable evidence, not live approvals. A missing or changed candidate/evidence file fails freshness gates; it must not be silently replaced under a frozen receipt.

Only the new bounded workflow source, focused test file and this report are committed. No database, raw download, queue, manifest, journal, backup, runtime report, log/cache or unrelated worktree change is included. Nothing is pushed.

## 15. Exactly one recommended next phase

**P/B-PAYLOAD-REPAIR-OPEN-REGISTRATION-1:** after the shared scheduler operation finishes, fresh-revalidate the exact frozen three-item proposal/receipt batch, stop on any drift, register OPEN items on a disposable queue copy, obtain the exact read-only confirmations, and present the single combined source-repair YES/NO question. Stop and wait for that later answer. Do not perform live repair or ownership/PB approval in that phase.

## Stage 1 OPEN registration

### 2026-10-28T15:38:55Z attempt: STOP at operational preflight

Requested task: **P/B-PAYLOAD-REPAIR-OPEN-REGISTRATION-1**, starting HEAD `61b5fb9d05cb2f83250690593183ea6d3e69e5ab`. The worktree still contains the previously reported unrelated journal/runtime/research changes; none is included in this documentation commit. The exact prior proposal and receipt files still exist under `/tmp/pb_payload_repair_controlled_workflow`; their existence is not a claim of current freshness.

The scheduler is **not free**. A fresh read of kernel lock ownership identifies PID `666030` holding `/home/kalle/projects/rawcandle/logs/stock_update_scheduler.lock`; a separate process check identifies `/home/kalle/projects/stockcore/.venv/bin/python -B -m tools.daily_yahoo run`. The normal `provider_payload_workflow.preflight` independently failed on nonblocking `fcntl.flock(..., LOCK_EX | LOCK_NB)` with `BlockingIOError: [Errno 11] Resource temporarily unavailable`. Its earlier UI/Production lock acquisitions were scoped read-open locks and were released on failure; no owner metadata was rewritten. No lock was removed, bypassed or waited on.

Task sections A and M explicitly require STOP when a legitimate scheduler operation is active. Accordingly, stages B–L were not entered. The existing last-verified baseline remains a historical reference only: generation `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, provider watermark `2026-10-27`; no fresh baseline hash/invariance certification is claimed for this stopped attempt while another operation is running.

| Stage 1 evidence/action | This attempt |
| --- | --- |
| Operational preflight | STOP: active scheduler lock |
| Fresh GE/RTX/T acquisitions and factors | Not checked; prior factors were 1.0 |
| Current proposal/receipt/source/candidate validation | Not performed; stale/current status unknown |
| Queue-copy registration and confirmations | Not run |
| Live OPEN items registered | 0 |
| REGISTERED_OPEN audit events appended | 0 |
| Live read-only item confirmations | Not run |
| Restored source fields | 0 applied; prior proposals each specify 83 |
| Financial values changed by this attempt | NO |
| Ownership/P/B approvals and approval events | 0 |
| Provider/canonical/analysis mutation or repair | NO |
| Generation activation, watermark advance, journal/config mutation | NO |
| Queue mutation, including unrelated rows | NO |
| Repository/full-suite tests | Not run; source unchanged |
| Explicit combined YES/NO gate | Not reached; no consent requested or inferred |

No fresh registered repair IDs, binding confirmations or source freshness results are asserted. The exact prior proposal-derived repair IDs remain documented in section 7, but none was registered by this attempt. No backup cleanup, bulk repair, normal Preview/Test/Production or ownership continuation occurred. This attempt writes only this documentation section; any externally concurrent runtime activity is outside this attempt and is not certified unchanged by it.

Stage 1 is **incomplete**, and no source defect was discovered. The single recommended next phase remains **P/B-PAYLOAD-REPAIR-OPEN-REGISTRATION-1**, retried after the existing scheduler operation has finished: restart at fresh operational preflight, then proceed through fresh evidence validation, queue-copy validation, exact live OPEN registration, read-only confirmation and invariance checks. Present the exact combined YES/NO question only if all preceding gates pass, and stop for the later answer. This stopped attempt grants no authorization to publish a repair.

### 2026-10-28T16:48:09.201680+00:00 restart: Stage 1 PASS, exact live OPEN registration

User task: **P/B-PAYLOAD-REPAIR-OPEN-REGISTRATION-1**, explicitly restarted from the beginning after the scheduler process ended. Starting HEAD: `2f6287d20cb6dbc5dfdf1198a384729a0a764c98`. The pre-existing journal/runtime/research worktree changes remain outside this documentation commit. The original implementation and blocked-attempt sections above describe historical snapshots; **this successful restart supersedes their incomplete OPEN-registration status**. Stage 2 source repair remains unauthorized and unperformed.

#### Fresh operational preflight and baseline

At `2026-10-28T16:45:35.949831+00:00`, all existing scheduler, Fundamentals UI-operation and Production kernel locks were acquired nonblocking through `provider_payload_workflow.preflight`. They remained held through fresh fetches, queue-copy validation, immediate live-registration gates, live OPEN registration and post-registration verification. No lock owner text was rewritten. No live scheduler process or conflicting refresh was found. The terminal journal is COMPLETED / postflight PASSED / rollback-recovery NOT_REQUIRED; taxonomy is safe, recovery is not pending, and no visible or hidden `.preparing` generation exists. The same guards were rechecked before live registration and after confirmation.

The generation remains `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, watermark **2026-10-27**. Fresh baseline role/manifest/market/configuration/code hashes exactly match the frozen proposals. Exact old provider observations and all existing ownership review rows were captured; the live repair table did not exist before this attempt. Original proposals and receipts were reloaded unchanged, not regenerated or rebound.

One preliminary temporary helper assumed a journal key named run_id; the actual journal uses production_run_id. That read-only formatting failure occurred before baseline capture, provider acquisition or queue writes. The temporary helper was corrected and every gate restarted. No repository source defect or source change was involved.

#### Independent fresh source evidence and original candidate revalidation

Normal Sharadar complete ARQ histories were independently acquired twice: `2026-10-28T16:45:36.009465+00:00`–`2026-10-28T16:45:37.301217+00:00`, then immediately before live registration at `2026-10-28T16:47:14.036874+00:00`–`2026-10-28T16:47:15.298276+00:00`. Both sets passed the existing COMPLETE validator. Each exact source row, identity, full acquisition payload, financial fingerprints, completeness fingerprint, restored-field set and factor matched the frozen proposal exactly. No drift was accepted. Original proposal fetch timestamps remain immutable; these new revalidation fetch times are recorded separately.

| Ticker | Exact source key | COMPLETE ARQ rows, both fetches | Fresh factor | Restored fields proposed | Financial values changed | Stale |
| --- | --- | --- | --- | --- | --- | --- |
| GE | GE\|ARQ\|2026-10-20\|2026-09-30 | 42 | 1.0 | 83 | NO | NO |
| RTX | RTX\|ARQ\|2026-10-20\|2026-09-30 | 40 | 1.0 | 83 | NO | NO |
| T | T\|ARQ\|2026-10-21\|2026-09-30 | 42 | 1.0 | 83 | NO | NO |

The same 83 sorted fields listed in section 8 remain bound, including sharefactor, equity, equityusd, price, marketcap and pb. Field-list fingerprint remains `d03a4b213f417f1d28a3e3c81cf7f8c6a17b4f0258ebd1f9a83c0f83a5a88ed2`. These are proposed restorations; **no live field was restored in Stage 1**.

Current `verify_receipts` remeasured the original disposable provider/canonical/analysis files. Exact candidate hashes, source payloads, new observation IDs/hashes, financial/no-unrelated-change assertions, SQLite integrity and no-approval assertions passed. The unchanged detector still gives CONTINUATION_CANDIDATE for GE/RTX/T; hypothetical P/B remains 17.55436232103115 / 3.7920742076120066 / 1.3211122199455392. Actual Current P/B remains OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED. No new provider candidate or production generation was prepared.

| Candidate role | Unchanged receipt-bound SHA-256 |
| --- | --- |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 147e6ef965af071062fb89170d62b9bb471267c2cc5ac6cad4278afa2dbba054 |
| provider | 45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a |

#### Queue-copy validation, immediate live gate and exact registration

A disposable exact copy of the original operational queue was registered through `register`, then read through `_read` and `confirmation`. Each returned one OPEN item, NULL decision, receipt PASS, stale=False, exact proposal/receipt/binding/source identity and all live-repair/ownership/PB authorization flags False. Exactly three REGISTERED_OPEN events were appended; existing table contents, audit rows, ownership rows and schemas remained intact. Queue quick/FK checks passed.

Before live registration, retained kernel exclusion and fresh journal/taxonomy/preparing checks were confirmed, baseline and all exact provider rows remained unchanged, the live queue byte hash and logical contents still equalled the initial baseline, and no repair item existed. The second independent fresh-source acquisition and full receipt remeasurement passed. **Section H explicitly authorizes this exact live OPEN registration after A–G PASS.** The normal controlled-workflow service then atomically registered the three items. No manual queue SQL, approval action or provider writer was used.

All three live confirmations are byte-for-byte equal as JSON values to the queue-copy confirmations. The following full identities are bound to the one frozen batch `03a973f7d891b895d2bf2c3cec424a42f7dc9f378a52ff7c87d9e2114546c02c`. Each proposal fingerprint is the repair ID below with the `ppr_` prefix removed.

| Ticker | Exact registered repair ID / proposal binding | Receipt fingerprint | Binding fingerprint |
| --- | --- | --- | --- |
| GE | ppr_ec59380018faafdc85892995d381025a1c2ab90cec73f16cb3f95b8e57b00f2b | a47ee93a5eabb8fc9daf6e3f8e47e77e7c8e9703cc2b0e8df71f79152973bff9 | 676a9673f444fad1c8048b9e533c1f147ef7435cdb69d07ae4525ee5a44bb03a |
| RTX | ppr_fa48737bb61a6474741efd0898b566be33d244b0a3edb8043d99a20c840ea8b6 | 321385e8419079c0f1fcc9429157c4aa7f5beedc6d0615e411f47ff0ff7bec62 | 902073de4948367f158e79c3272a7359a4593fe797f2f0052c61845fcd3b4b85 |
| T | ppr_76eda17a57f14875241e571fc7836f101b09f7fe29b46a5c77e3e0924ad8e017 | 4cf9b61c0341be6846aebfc6e45df03c659fd293e8ae89ef28efce39fbff6b50 | 6b17885ed521864a69fe705feef771219a7111a5f5ec68bc131fa43c11d1d7da |

| Ticker | Old observation ID | Old content hash | Fresh source payload fingerprint |
| --- | --- | --- | --- |
| GE | 5806bfc4a10a7d809ef83498c8360b26660ce28502d81408e7b189426a2cab24 | d47fcb1f67a85963201f7d0c0745672e6ba99bb75c9c7ad50f8581cfdcb86375 | 14eba2facdb54dd1247923e9b684401709621787e8728ee8ab7665551a36e816 |
| RTX | bfd42bf2f633cfb8e511931673bc6769ea1bad22859c227d602d7328d42ea4f1 | 50238350ed044491f6198bbb922dc0a562f2badfc46bde9ad266a8ed6d6462ec | 56b0a3e45b7b69e3308c4e3863aadb44c789746259283cfb0c08fab8361e2e84 |
| T | a04ecf0968eaee10a2018c39e9d80057e59520770412d784f518bdd0c3ad6e1c | 0fbe9ab6418a1f910f4bb40dc6231889a9c91e423354b94d43075c173e500be0 | 6f744958e889dc70bbeec7162a795a6cc451e77189fbd34ead8d1a8f07eee577 |

All proposal/receipt/binding schemas remain the V1 schemas in sections 2–4. The confirmations also include exact old/new completeness, baseline generation, candidate hashes, factor, full restored-field list, financial_values_changed=False, decision=None, approval_action=EXPLICIT_YES_SOURCE_REPAIR_ONLY and all authorization flags False. Full confirmation payloads are retained outside Git in stage1_result.json.

| Audit ID | Ticker | Event | Occurred UTC | Repair ID |
| --- | --- | --- | --- | --- |
| 49 | GE | PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN | 2026-10-28T16:48:01Z | ppr_ec59380018faafdc85892995d381025a1c2ab90cec73f16cb3f95b8e57b00f2b |
| 50 | RTX | PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN | 2026-10-28T16:48:01Z | ppr_fa48737bb61a6474741efd0898b566be33d244b0a3edb8043d99a20c840ea8b6 |
| 51 | T | PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN | 2026-10-28T16:48:01Z | ppr_76eda17a57f14875241e571fc7836f101b09f7fe29b46a5c77e3e0924ad8e017 |

Live totals: **3 OPEN items, 3 registration events, 0 approval events**. Existing audit entries remain identical; no duplicate items/events exist. All nine original ownership cases, including GE/RTX/T, retain their exact prior state, NULL approval/result and unchanged candidate JSON/hashes. The only queue changes are the typed repair table/required primary-key index, its three OPEN rows, three appended audit rows and the required audit SQLite sequence advancement by three. No unrelated schema, sequence or queue row changed.

#### Runtime invariance and documentation-only validation

| Protected binding | Unchanged SHA-256 |
| --- | --- |
| active manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| active analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| active canonical | 11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e |
| active provider | 6d0262597c4248d40ce8b7ac79b164b1f8fcdfc09fa72283e35486d94380ae81 |
| market | 0dd3a0fe6d4de465a075e7771128d11b370f3159b26a27c9d05d810fb360832f |
| journal | 8c88e3894b9376be4b56cc51041274d7ca368967e87dbf532f5c491e54190eae |
| scheduler configuration | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |

Queue SHA-256 changed only as authorized: `746836b89c2bc2bcf5880812bdcdd64024c2c4398e196e21746b74fbf0f68b99` → `0c61f100e9b36b2cd5ce392b83f37a88fb1d050bc321ded8c7063b3a46c88951`. Whole-row provider observation equality and full baseline equality were rechecked after registration. Active generation, watermark, provider/canonical/analysis/market, manifest, journal and scheduler configuration remain unchanged. Existing WFRD state is preserved by unchanged provider/canonical role hashes and unchanged relevant code/contract hashes. No source repair, ownership/PB approval, Preview/Test/Production run, auto-continuation, bulk/historical repair, registry repin or backup cleanup occurred.

Repository/full-suite tests run: **NO**; runtime source is unchanged, as required. Validation consists of fresh normal-provider reacquisition, current exact proposal/receipt validators, queue-copy/live readbacks, six read-only confirmations, SQLite checks and row/hash invariance. No approval or source-repair completion is inferred from successful registration.

Evidence lane: `/tmp/pb_payload_repair_open_registration_20261028/attempt_164533` (before.json, original proposal/receipt copies, two fresh-source snapshots, disposable queue, queue_copy.json and stage1_result.json); log: `/tmp/pb_payload_repair_open_registration_20261028.log`. Only this documentation file is committed; no DB, provider download, queue, journal, manifest, log or unrelated worktree change is included. Nothing is pushed.

#### Exact combined authorization boundary — STOP and wait

Stage 1 is complete. The current action is to wait for the explicit answer required by section L of the user task; the earlier OPEN-registration next-phase recommendation has now been fulfilled. The pending question binds all three exact registered repair IDs, their proposal/receipt/binding fingerprints, source keys, the baseline generation and all 83 restored fields with financial-values-unchanged assertions above.

> Do you authorize the exact source-payload completeness repairs for GE, RTX and T bound to the three OPEN repair items and exact proposal/receipt/binding fingerprints above, for GE|ARQ|2026-10-20|2026-09-30, RTX|ARQ|2026-10-20|2026-09-30 and T|ARQ|2026-10-21|2026-09-30, using the existing controlled provider-repair lifecycle? YES/NO

A later YES authorizes **only this exact source-payload repair set**, through its existing verified candidate/immutable-generation/journal/rollback lifecycle. It does not authorize ownership continuation, P/B approval, auto-continuation, Preview/Test/Production beyond the lifecycle necessary for this source repair, unrelated repairs, historical bulk repair, review-queue cleanup or policy/resolver changes. Any source, baseline, proposal or receipt drift before the repair boundary invalidates consent and requires STOP. No Stage 2 action has been executed or authorized in this turn.
