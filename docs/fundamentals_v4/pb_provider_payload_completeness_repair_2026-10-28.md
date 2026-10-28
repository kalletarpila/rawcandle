# Provider payload completeness repair: implementation and copy-only rehearsal

2026-10-28. Governing [factor-null audit](pb_ownership_provider_factor_null_audit_2026-10-28.md), commit `2df7c584e02bb975689d0172f7449fc2b3ff9576`. Existing acquisition preservation remains the implementation in `f23af13e7086296b1c917dcc5d2c25ca7accb3f6`.

**Implemented separate payload-completeness detection, exact repair bindings and an explicit inactive-copy repair helper. Fresh GE/RTX/T ARQ sources all contain 112 keys and sharefactor='1'. All three Q3 copy repairs and all 24 historical proof repairs passed.** Existing financial projection values/fingerprints remain unchanged; missing P/B inputs, including parent equity, were recovered from fresh same-key source evidence. No prior-quarter factor or equity was carried into Q3.

On the Q3 canonical copy, the unchanged ownership detector returns CONTINUATION_CANDIDATE for GE/RTX/T. Hypothetical P/B values are 17.55436232103115 / 3.7920742076120066 / 1.3211122199455392 respectively. These are not approved or published values. With the unchanged ownership artifact, actual Current P/B remains held for new-quarter review. Live queue decisions, all role DBs, active generation, watermark, journal and scheduler are unchanged. **367 distinct focused tests passed; full suite not run.**

The repair classification is a separately reviewable source-evidence candidate. It is intentionally **not** added to automatic financial replacement/Production dispatch. This phase implements detection and explicit copy rehearsal, not an operational repair publisher. The normal preservation writer is unchanged; later controlled-workflow integration is the one recommended next phase below.

## 1. Scope, contract review and baseline

The [quarterly ownership contract](fundamentals_v4_pb_quarterly_ownership_durability_v2.md), [operator continuation workflow](fundamentals_v4_pb_new_quarter_review_workflow.md) and [P/B reporting contract](fundamentals_v4_pb_reporting_v1.md) are unchanged. Provider P/B remains separate from Current P/B and neither enters Valuation Score. Current P/B uses latest usable price × latest accepted quarterly validated economic units / accepted same-quarter parent_equity_usd. Raw-factor binding, ordinary/ADS interpretation and explicit ownership confirmation remain independent of source-data repair.

No broad repository or all-history repair was performed. Real repair scope is three exact Q3 ARQ keys and the audit's 24 historical ARQ proof pairs, on separate disposable copies. Six normal provider requests reacquired complete ARQ/MRQ histories for GE, RTX and T. No operational Preview/Test/Production, scheduler, drain, ownership approval, registry repin or active-generation publication was run. Existing test cases exercise isolated fixture workflows; they are not operational runs.

Starting HEAD: `2df7c584e02bb975689d0172f7449fc2b3ff9576`. Baseline captured `2026-10-28T14:04:29.529142+00:00`; invariance verified `2026-10-28T14:28:33.561426+00:00`. Active generation remains `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, watermark **2026-10-27**. All nine original ownership cases remain OPEN with NULL approval/result.

## 2. Detection gap reproduced before source edits

The retained audit cohort supplied eight full historical payloads per company. For each pair, all normalized financial/source fields and both financial semantic fingerprints match the current 29-field stored projection exactly. Before editing source, the actual compare_ticker_histories path returned NO_EFFECTIVE_CHANGE for each company's compatible historical full-payload restoration. A synthetic same-shape absent sharefactor → 1.0 case also returned NO_EFFECTIVE_CHANGE. Thus the comparison missed a substantial source-evidence improvement.

Retained-only rows were excluded from the simulated fresh response, preserving the existing carry-forward behavior. Otherwise marking them as newly returned source rows would correctly create an unrelated source-history transition; that is not the completeness defect being reproduced.

| Before-change control | Pairs | Stored/full keys | Financial raw/effective fingerprints | Before classification |
| --- | --- | --- | --- | --- |
| GE | 8 | 29 / 112 | identical / identical | NO_EFFECTIVE_CHANGE |
| RTX | 8 | 29 / 112 | identical / identical | NO_EFFECTIVE_CHANGE |
| T | 8 | 29 / 112 | identical / identical | NO_EFFECTIVE_CHANGE |
| synthetic absent sharefactor → value | same shape | 29 / 30 | identical / identical | NO_EFFECTIVE_CHANGE |

The baseline code and exact comparison results were saved under `/tmp/pb_provider_payload_completeness_repair` before any implementation edit. All three fresh Q3 rows also have **zero differences** in REFRESH_REQUEST_FIELDS from the stored normalized Q3 rows. No unexpected financial revision or source-key drift required a case STOP.

## 3. Generic completeness and key-state contract

New [provider_payload.py](../../rawcandle/fundamentals/admin/provider_payload.py) defines SHARADAR_ACQUISITION_PAYLOAD_V1 over the retained acquisition mapping, not only the six P/B extras and not a fixed key-count threshold. Payload extraction requires actual retained `_acquisition_payload` evidence. It does not reconstruct a “raw” payload from normalized fields when that evidence is missing.

For every source key, field_state distinguishes ABSENT, NULL and VALUE. Completeness records the key-state mapping, key count and its own fingerprint. A separate canonical full-payload SHA-256 binds all values and every source field; it deliberately disables the administrative hash's exclusions for fields named run_id/timestamp_utc. Source strings, numbers and explicit nulls remain as received. VALUE means a preserved non-null source value, not an ownership approval or a promise that every optional numeric field passes downstream valuation gates.

A compatible strict key-set extension can be a repair: old keys must remain, previously present extras must agree, normalized source/financial fields must agree, and exact source identity must agree. No field is assumed mandatory merely because another row has it. A present null supplies completeness information without recovering a usable numeric value. No None→1 conversion exists.

| Transition | Comparison result | History classification / repair eligibility |
| --- | --- | --- |
| full old → same full new | NO_PAYLOAD_CHANGE | Existing NO_EFFECTIVE_CHANGE retained. |
| absent → compatible value | SOURCE_PAYLOAD_COMPLETENESS_REPAIR | Explicit copy-repair candidate. |
| absent → explicit null | SOURCE_PAYLOAD_COMPLETENESS_REPAIR | Information-only addition; separate null/value-restored lists. |
| explicit null → value | SOURCE_PAYLOAD_VALUE_REVISION | HISTORICAL_REVISION; not a completeness repair. |
| value → absent | SOURCE_PAYLOAD_KEY_REGRESSION | REVIEW_REQUIRED; not harmless missing data. |
| value → different value | SOURCE_PAYLOAD_VALUE_REVISION | HISTORICAL_REVISION; not a completeness repair. |
| financial/source identity contradiction | Existing financial revision or explicit payload contradiction/identity reason | No compatible repair; copy helper rejects. |
| ambiguous source or stored key | Incomplete/ambiguous evidence | Reject repair before any write. |

## 4. Implementation surface and unchanged financial semantics

Only two runtime source files are involved: the new completeness/copy helper and [refresh_fundamentals.py](../../rawcandle/fundamentals/admin/refresh_fundamentals.py). Three existing functions change:

- load_current_history retains exact observation ID/hash and provider/company/security binding, and fails closed when same-maximum source versions disagree in full payload even if financial projections agree. Optional identity columns remain compatible with older minimal schemas; missing identity cannot authorize a repair.
- compare_ticker_histories adds a separate source_payload_changes collection and fingerprint, recognizes SOURCE_PAYLOAD_COMPLETENESS_REPAIR, retains real extra-value changes as HISTORICAL_REVISION, and holds regressions/contradictions. Only actual response rows are eligible, not retained-only carry-forward rows.
- refresh_binding_change includes the separate payload-change fingerprint when present, so a changed factor/null/value cannot reuse a financial-only comparison binding.

The bodies of normalize_source_row, _raw_row, _effective_row, semantic_row_fingerprints, history_fingerprints, validate_complete_history and fetch_complete_history are AST-identical to baseline. Existing full-acquisition preservation and replace_provider_histories are byte-identical. No financial tuple or financial fingerprint was broadened. No schema, canonical identity, P/B formula, ownership policy, result-publication resolver, publication authority, scoring, generation/journal model, scheduler or UI source changed.

Reviewed fiscal relabels remain governed by the existing identity-review path, rather than being reinterpreted as payload completeness mismatches. The copy helper also rejects an existing reviewed fiscal interpretation, reviewed result context, retained-source provenance or other linked provider evidence. WFRD has no special new ticker branch; its existing reviewed-source semantics remain authoritative.

SOURCE_PAYLOAD_COMPLETENESS_REPAIR is distinct from ordinary financial replacement classes. A detector can expose the exact candidate and its binding, while the explicit repair helper requires selected observations and validated complete source histories on an inactive copy. No new default automatic source repair or Production dispatch is introduced in this phase.

## 5. Fresh complete current source acquisition

Used the existing SharadarClient and fetch_complete_history, without custom projections or alternate endpoints. ARQ and MRQ were fetched for each focus ticker using the normal fundamentals path and limit 10,000. All responses passed the existing COMPLETE history validator, with unique source keys and row counts far below the limit. No live provider write occurred. Parsed full acquisition payloads and fetch start times were retained outside Git; no API credentials were printed or committed.

| Ticker | Dimension | Complete rows | Fetch start UTC | Status |
| --- | --- | --- | --- | --- |
| GE | ARQ | 42 | 2026-10-28T14:04:51.001862+00:00 | COMPLETE |
| GE | MRQ | 40 | 2026-10-28T14:04:51.336698+00:00 | COMPLETE |
| RTX | ARQ | 40 | 2026-10-28T14:04:51.688300+00:00 | COMPLETE |
| RTX | MRQ | 40 | 2026-10-28T14:04:52.221316+00:00 | COMPLETE |
| T | ARQ | 42 | 2026-10-28T14:04:52.743241+00:00 | COMPLETE |
| T | MRQ | 40 | 2026-10-28T14:04:53.226089+00:00 | COMPLETE |

| Ticker | Exact Q3 source key | Fresh classification | Raw sharefactor | Keys | Equity / equityusd USD | Provider price / marketcap / pb |
| --- | --- | --- | --- | --- | --- | --- |
| GE | GE\|ARQ\|2026-10-20\|2026-09-30 | COMPLETE_VALID_FACTOR | '1' | 112 | 17522000000 / 17522000000 | 299.87 / 309871240550 / 17.685 |
| RTX | RTX\|ARQ\|2026-10-20\|2026-09-30 | COMPLETE_VALID_FACTOR | '1' | 112 | 69250000000 / 69250000000 | 193.34 / 260900835550 / 3.768 |
| T | T\|ARQ\|2026-10-21\|2026-09-30 | COMPLETE_VALID_FACTOR | '1' | 112 | 106775000000 / 106775000000 | 21.91 / 147596132917 / 1.382 |

All six required P/B extra keys are present with values for all three exact Q3 ARQ rows. These fresh responses are the first current-Q3 evidence for factor one; no prior-quarter values were used to derive it. No case is SOURCE_STILL_INCOMPLETE, SOURCE_VALUE_CHANGED or SOURCE_IDENTITY_DRIFT. A missing key or explicit null would have been preserved/reported without fabricating a number; actual explicit-null ownership policy would still be unchanged.

| Ticker | Complete Q3 source payload SHA-256 | Unchanged financial raw fingerprint | Unchanged financial effective fingerprint |
| --- | --- | --- | --- |
| GE | 14eba2facdb54dd1247923e9b684401709621787e8728ee8ab7665551a36e816 | d47fcb1f67a85963201f7d0c0745672e6ba99bb75c9c7ad50f8581cfdcb86375 | 1ac5c84676f0162f14be2e7853236e3793afb817960a2ba06568299e84ee883a |
| RTX | 56b0a3e45b7b69e3308c4e3863aadb44c789746259283cfb0c08fab8361e2e84 | 50238350ed044491f6198bbb922dc0a562f2badfc46bde9ad266a8ed6d6462ec | 1ab4aa70967b849efb96367f2dcc32c7af332db0df65de071b149eb58aaa5313 |
| T | 6f744958e889dc70bbeec7162a795a6cc451e77189fbd34ead8d1a8f07eee577 | 0fbe9ab6418a1f910f4bb40dc6231889a9c91e423354b94d43075c173e500be0 | d40f05fba5f26fe3fc5238d624da37887a3478575434ec2a43aeaa14bc58d5d8 |

The normal resolve_identity path independently returns KNOWN for all three, matching the repair receipt's stored company/security/permaticker binding. The source API does not add a new company identity from an omitted raw field: ticker/dimension/date/reportperiod and fiscal identity bind the response to the exact existing observation; any supplied conflicting company/security/permaticker/provider field is rejected.

| Ticker | Company / security | Provider stable ID | Current source identity result |
| --- | --- | --- | --- |
| GE | 931 / 934 | 199688 | KNOWN |
| RTX | 1928 / 1938 | 199251 | KNOWN |
| T | 2123 / 2133 | 198738 | KNOWN |

## 6. Exact copy-only repair and auditability

repair_payloads_on_copy uses the existing inactive-copy guard: active/legacy role paths, symlinks and finalized generations are rejected. It requires a nonempty explicit selection, original observation ID/hash, complete history, exactly one matching source row, exact compatible comparison fingerprint and timezone-aware fetch timestamp. Stored source identity must have company/security/provider binding and SUCCESS status. Stored duplicate source keys, retained/reviewed context and linked child evidence are rejected. The entire selection is validated before the first write in one SQLite transaction.

Each selected old observation is replaced only on the disposable copy through existing provider/native row semantics. The new row receives the full canonical source-payload hash and a new observation ID bound to provider/source/key/payload hash. Its native financial row is cloned unchanged except for observation ID. This avoids changing what an old observation/hash purports to represent. The original generation remains byte-identical and retains the old evidence. Existing unrelated observations and provider tables are untouched; no broad history replacement writer is used.

The new provenance source_payload_repair receipt records old observation/hash, old key-state/full-payload fingerprints, new full-payload/completeness fingerprints, exact source key, provider/company/security identity, reason, added/null/value fields, financial_fields_changed=False, exact source fetch start time and new observation/hash. These are source-repair receipts on copies, not approvals or ownership interpretations.

| Ticker | Old Q3 observation ID | Old content hash | New copy observation ID | New full-payload content hash |
| --- | --- | --- | --- | --- |
| GE | 5806bfc4a10a7d809ef83498c8360b26660ce28502d81408e7b189426a2cab24 | d47fcb1f67a85963201f7d0c0745672e6ba99bb75c9c7ad50f8581cfdcb86375 | 30891b203267dfa12056544407c8dcdff68edd3001822a4622d975c71d7e2248 | 14eba2facdb54dd1247923e9b684401709621787e8728ee8ab7665551a36e816 |
| RTX | bfd42bf2f633cfb8e511931673bc6769ea1bad22859c227d602d7328d42ea4f1 | 50238350ed044491f6198bbb922dc0a562f2badfc46bde9ad266a8ed6d6462ec | 9dda4193acb8676c52ee8b235e9822b609c4693234323ef25452681d366146f5 | 56b0a3e45b7b69e3308c4e3863aadb44c789746259283cfb0c08fab8361e2e84 |
| T | a04ecf0968eaee10a2018c39e9d80057e59520770412d784f518bdd0c3ad6e1c | 0fbe9ab6418a1f910f4bb40dc6231889a9c91e423354b94d43075c173e500be0 | 26198cc5927cf7a291d0fcb52eec541a1f16216c31b41670ffb4f9705c8dd2aa | 6f744958e889dc70bbeec7162a795a6cc451e77189fbd34ead8d1a8f07eee577 |

| Ticker | Old completeness SHA-256 | New completeness SHA-256 | Fields restored | Financial projection changed | Repair integrity |
| --- | --- | --- | --- | --- | --- |
| GE | e07a4222563fc8869ffbdcdb8e1546960aeabc214f80bea0c5e2c2b3a81c1f2c | 604a0cf24b3a4fb019601b97957729d425017b4b15dc1369367d8eaffce52c14 | 83 | NO | ok |
| RTX | e07a4222563fc8869ffbdcdb8e1546960aeabc214f80bea0c5e2c2b3a81c1f2c | 604a0cf24b3a4fb019601b97957729d425017b4b15dc1369367d8eaffce52c14 | 83 | NO | ok |
| T | 887a4fa7a29ec784be9da84977b36775cb7ca3055c72e9cff4a0ee38166efb09 | 604a0cf24b3a4fb019601b97957729d425017b4b15dc1369367d8eaffce52c14 | 83 | NO | ok |

The Q3 provider copy repairs exactly three observations. A separate disposable provider copy repairs exactly the audit's 24 historical proof observations, using fresh same-key history payloads for those quarters. Historical retained full payloads prove the defect but are not used as a substitute current source. Every one of the 27 real selected pairs has identical financial/source projection fingerprints before and after; all full source mappings are preserved. SQLite integrity and foreign-key checks pass. No source-key duplication is introduced.

Complete table digests, excluding only the selected old/new observation IDs from provider_observation and sharadar_fundamental_observation, match for each provider copy. All other tables match in full, including WFRD reviewed state and metadata. There is no unrelated provider row change. Fresh rows outside the 27 selected observations are not repaired.

## 7. Canonical-copy projection and ownership detector consequences

To measure ownership/P/B consequences, the Q3 provider copy was paired with a disposable copy of the current canonical DB. No all-history reconciliation or scoring rebuild was run. An ad hoc /tmp diagnostic ran the unchanged accept_parent_equity helper in a three-quarter scratch DB with the exact three repaired share-provenance bindings. It then copied only those three resulting parent-equity/source projections onto the canonical copy, rebinding their existing source provenance to the new provider IDs. This diagnostic is not a new production canonical writer or a publishable generation-preparation workflow.

All canonical tables outside the three affected parent-equity/field-provenance projections match in full. Within the affected tables, every row outside the three Q3 quarter_ids matches. For the three financial rows, all pre-existing core financial values and metadata match; only previously missing parent_equity/parent_equity_usd are populated from fresh same-key Q3 evidence. Provenance changes refer only to those repaired source observations. Fiscal identities, first-public dates, publication authorities, ownership artifact/pin and scores are unchanged. The other six ownership candidates are identical as complete dictionaries.

The pure detect and read-only ownership preview were run on that canonical copy. No proposed ownership record was written, no queue decision changed and no approval action was called. Hypothetical in-memory records are the existing preview mechanism, not real approvals.

| Ticker | Factor old → repaired | Category continuity | Share change % | After-copy classification | Accepted Q3 equity USD | Actual Current P/B | Hypothetical approved P/B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GE | 1.0 → 1.0 | unchanged Domestic Common Stock Primary Class | -0.4058157409547847 | CONTINUATION_CANDIDATE | 17522000000.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 17.55436232103115 |
| RTX | 1.0 → 1.0 | unchanged Domestic Common Stock Primary Class | 0.12482981516304115 | CONTINUATION_CANDIDATE | 69250000000.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 3.7920742076120066 |
| T | 1.0 → 1.0 | unchanged Domestic Common Stock Primary Class | -1.6915600335483116 | CONTINUATION_CANDIDATE | 106775000000.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 1.3211122199455392 |

All three become CONTINUATION_CANDIDATE on the repaired canonical copy, but Current P/B remains NULL / OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED under the unchanged artifact. Hypothetical current_pb returns OK in each case only in memory, when the existing preview supplies a prospective matching review. This outcome does not approve a continuation or guarantee approval safety on a later changed source vintage.

## 8. P/B source consequences

The repaired source projection restores same-Q3 parent equity, provider price, marketcap and original provider pb, along with factor evidence. Internal P/B still uses the latest usable local market close dated 2026-10-27, not the provider P/B or provider-date price as a replacement current quote. Ordinary economic units equal the accepted Q3 shares; there is no old-quarter equity/count fallback or ratio estimation.

| Ticker | Accepted Q3 shares / economic units | Current local close | New Q3 equity USD | Hypothetical market cap USD | Hypothetical internal P/B | Separate Provider P/B |
| --- | --- | --- | --- | --- | --- | --- |
| GE | 1033351921.0 | 297.6600036621094 | 17522000000.0 | 307587536589.1078 | 17.55436232103115 | 17.685 |
| RTX | 1349440548.0 | 194.60000610351562 | 69250000000.0 | 262601138877.13147 | 3.7920742076120066 | 3.768 |
| T | 6736473433.0 | 20.940000534057617 | 106775000000.0 | 141061757284.68494 | 1.3211122199455392 | 1.382 |

“Financial fields changed: NO” refers to existing financial-projection values and their semantic fingerprints. Previously absent equity/P/B evidence is restored, and parent-equity NULLs become fresh values on the canonical copy as intended. This is not a claim that every canonical financial column remains NULL or byte-identical after the projected repair. No financial value already present in the stored source is overwritten with a different value.

## 9. Regression controls and focused tests

**367 distinct directly relevant cases passed across seven files.** The new completeness file has 63 cases, covering every absent/null/value transition for all six P/B extras, generic full-payload hashing without administrative exclusions, full→same full, the three exact focus shapes, ordinary/ADS/zero-factor evidence, financial contradictions, source-key/company/security/permaticker drift, duplicate source/selection/stored keys, stale ID/hash/payload bindings, incomplete histories, linked child evidence, reviewed provider context, immutable new observation identity, exact persisted payloads, copy rollback and unchanged unrelated rows. No factor value is inferred by the helper.

The targeted groups were:

```text
tests/test_provider_payload_completeness.py
tests/test_fundamentals_admin_refresh_preview.py
tests/test_fundamentals_admin_refresh_copy_test.py
tests/test_wfrd_accounting_boundary_review.py
tests/test_wfrd_production_candidate_parity.py
tests/test_fundamentals_pb_reporting.py
tests/test_fundamentals_pb_quarterly_ownership.py
```

Passing validation consisted of 196 cases in refresh preview + the two WFRD files, 108 existing cases in refresh copy + P/B reporting + quarterly ownership, and 63 new completeness cases. The initial broad targeted run exposed compatibility with older minimal provider schemas and reviewed fiscal relabels; both were corrected and their targeted groups passed. A final three-case check repeated full-payload ambiguity, legacy identical-version collapse and reviewed WFRD rehearsal after the final loader hashing change. Those repetitions are not added to the 367 distinct count. No targeted failure required the full suite, and it was not run.

The real-data replays separately verified all 24 historical proof pairs and the three Q3 copy repairs. WFRD/source-preservation regressions passed, and protected WFRD tables matched in both real provider copies. No provider replacement/preservation body, ownership policy function, P/B formula or source-acquisition body changed.

## 10. Runtime and decision invariance

All live data access used read-only source connections; normal UI-operation/Production/scheduler kernel locks protected baseline/copy/final snapshots without rewriting lock-owner files. All nine runtime file hashes below match baseline. The exact sharadar_refresh_state row is unchanged: watermark 2026-10-27 and its prior successful run/completion fields. The active role paths/generation are unchanged. The complete nine ownership review rows remain identical with OPEN status and NULL approval/result. Source hashes for ownership policy, artifacts, P/B formula, UI, parent-equity acceptance and normal preservation writer are unchanged.

| Runtime artifact | Identical before/after SHA-256 |
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

No live provider repair, canonical/analysis edit, ownership approval, queue/journal mutation, scheduler change, watermark update, workflow, active-generation activation or publish occurred. Only code, focused tests and this report are intended for Git. Existing unrelated worktree files, including the already-modified journal, were preserved.

## 11. Candidate and evidence artifacts

Disposable DBs remain under /tmp and are not committed or installed:

| Copy artifact | SHA-256 |
| --- | --- |
| q3_provider_v2.db | bb719d7b689164bd70c7abd8057888d3f9a1a14d0e940c8f24b7f0a34e8e7343 |
| q3_canonical_v2.db | 2109d1df867ff1bc43d99e5f95006e6d20d13c0f87f3aa831909271bd18c11a7 |
| historical_proof_provider_v2.db | 753d6e0dbf391aaad876111cb142574a48c3b19bbbca10ab140efcf869cf04f1 |

Raw downloads, pre-change code, scripts, receipts and tests logs also remain outside Git. The principal evidence bindings are:

| Artifact under /tmp/pb_provider_payload_completeness_repair | SHA-256 |
| --- | --- |
| before.json | 7933dd7ea5a5203430c65f93e04bd27b7fdbf84c5ab3dbfe0d3d0e749d863873 |
| before_gap.json | 9d25e99a8edcd0f85e59db94e5813867664dd353d455cc7e207c568b8edec18d |
| fresh_histories.json | 231ad9ce17527f7454abc0423a36462734996a204d03f933cf438e32bcd22d0f |
| rehearsal_v2.json | dc0e15b2b7b4abcbc887174c0f8a5c65d79d7753fa7c9a52ffe1b10b55914a3e |
| identity_bindings.json | cd13a55d4a404a2c06f04dce968bd58552a60091ce973c7472eca68b904da677 |
| verification.json | 00ad1fefddac2ff6ead5db06851c6386c5acf0e2483a5a27a1cb925c55246c67 |

## 12. Exactly one next phase

**P/B-PAYLOAD-REPAIR-CONTROLLED-WORKFLOW-1 — integrate the explicit, scope-bound repair receipts into normal controlled candidate preparation and revalidation before any live repair authorization.** Carry the new full-payload IDs and exact canonical provenance through the existing generation workflow, reject stale source/hash/completeness bindings, keep the selection bounded and preserve unchanged scores/publication state. Revalidate fresh source and candidate hashes and obtain separate explicit Production authorization before publication. Ownership continuation remains a subsequent observation-bound review; this recommendation does not approve GE/RTX/T or authorize any live write. No auto-continuation or factor-null equivalence change is part of it.

Commit only the new completeness helper, bounded refresh comparison changes, focused tests and this report. No DB, raw provider response, temporary candidate, runtime artifact, queue, manifest, journal, log, cache or unrelated worktree change is committed. No push.
