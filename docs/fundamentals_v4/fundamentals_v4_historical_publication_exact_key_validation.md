# P1.3 — Exact-key reviewed validation of historical publication candidates

Validation baseline frozen at `2026-10-09T07:11:00Z`. Baseline HEAD: `510648e3e7681c2ffde3f7cfd9ff0f6038235908`. Starting inventory: P1.2 commit `510648e3e7681c2ffde3f7cfd9ff0f6038235908`, following P1.1 commit `c2499ec7fb7d683759a3c66a67c8c7f54d1e19be`.

**599 original natural keys reconcile; 599 remain open; zero pass all reviewed gates.** All selected ordinary resolver evidence reproduces exactly, but current Policy V1 returns `REVIEW_REQUIRED_EVENT_EVIDENCE` for every case. No source-bound reviewed event observations for these keys exist in the retained reviewed inputs. Each affected case stops at that gate and is classified `OTHER_HOLD`. The validated-candidate artifact contains its full schema and **zero data rows**. It is not a production apply plan.

## Current production baseline

Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. It matches P1.2. All three financial database hashes, pointer, Review Queue, scheduler configurations and publication journal also match the P1.2 protected baseline. No normal production advancement occurred between these audits.

| Authority state | Count |
|---|---:|
| VERIFIED | 12,890 |
| NOT_FOUND | 1,882 |
| UNRESOLVED | 842 |
| AMBIGUOUS | 628 |
| Total authority | 16,242 |
| Full open | 3,352 |
| Recent open, existing 60-day scope | 152 |
| Historical open | 3,200 |

The canonical database `quick_check` returns `ok`. Authority natural keys are unique. Every authority row binds an existing accepted canonical quarter with matching quarter ID; no authority orphan, surrogate disagreement or unaccepted quarter was found. Full authority logical fingerprint: `41e710eb4dca4418d48e403fde8c70777efa1c02be24cb48e7eb3a6a4ccce577`.

Provider watermark: `2026-10-08`. Latest successful normal Fundamentals production run, independently agreed by the provider refresh state and completed publication journal: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. Provider completion: `2026-10-09T04:27:27Z`; generation manifest creation: `2026-10-09T04:36:28.009206Z`. Journal terminal state and publication step: `COMPLETED`; activation: `ACTIVATED_AND_VERIFIED`; postflight: `PASSED`; last update: `2026-10-09T04:37:11Z`; recovery: `NOT_REQUIRED`.

Review Queue: six rows, all `RESOLVED`; 38 audit rows; zero ownership-review rows. Five resolved rows concern provider anomalies and one concerns fiscal identity revision. None has an exact candidate natural-key match in its retained company/fiscal identity binding. These queue resolutions are not source-bound publication event observations and were not borrowed to authorize candidates. No queue row was changed.

The starting worktree contained the already modified publication journal, untracked active-generation pointer and generation directory, and unrelated PE research script/image. They were preserved and excluded from this commit. No source helper or resolver change is needed for this validation-only phase.

## Exact natural-key and evidence validation

The starting inventory is `fundamentals_v4_historical_publication_candidates_after_timestamp_equivalence.csv`. Its 599 distinct `(company_id, fiscal_year, fiscal_quarter)` keys cover 144 companies. Tickers were used for display only. Current authority, canonical quarter, company, security, CIK and durable publication evidence rows were read through SQLite `mode=ro` with `query_only=on`, then frozen as a separate temporary validation snapshot.

For every key, the current canonical quarter is unique and `ACCEPTED`, with exactly matching company, year, quarter, period end, authority quarter ID and P1.2 quarter ID. Current active company/security/CIK links are compatible, and the source archive CIK agrees with the active company CIK. Current provider-security links and economic structural-event records were reread and agree with the retained identity baseline; no candidate has a recorded structural continuity conflict. No old reviewed quarter binding was rebound or silently reused.

This compatibility check is not a substitute for historical entity/perimeter review. 593 candidates have no recorded active-security `valid_from`; the other six do not thereby gain reviewed semantic authority. Source-bound reviewed observations proving entity, period and financial event scope are absent for all 599. That missing proof is preserved in the Policy V1 hold and explicitly recorded in the CSV identity/perimeter field. No candidate is marked perimeter-approved.

All 144 retained current-company SEC acquisition captures are complete, dated `2026-10-09`, and hash-bound before and after validation. Their parent filings, primary text, result sections, linked exhibits and official metadata were reread. The ordinary resolver was rerun over **all current open quarters for each company**, rather than only the candidate quarter or a ticker-selected subset. Its full candidates, diagnostics and unresolved findings reproduce the retained current acquisition output. No network acquisition was repeated and no raw capture was altered.

Each of the 599 keys still produces one ordinary SEC Item 2.02 parent candidate, with no unresolved competing context. Each source was checked for exact accession, ordinary 8-K form, primary document, parent archive reference, acceptance timestamp and document-confirmed Item 2.02 status against the retained filing and SEC metadata. The complete current evidence payload and current quarter ID were fingerprinted. The evidence hash was independently recomputed using the existing resolver payload contract, and compared with P1.2. Complete evidence fingerprints, source hashes, source references, source types, accessions and timestamps all match P1.2 exactly.

Current durable publication evidence inventories for these 599 still-open keys are empty. The selected ordinary evidence exists in the retained SEC captures and reproduces through the resolver; it has not been inserted into production. No unresolved durable same-rank conflict was found. Evidence was not invented to fill those empty production inventories.

| Comparison to P1.2 | Cases |
|---|---:|
| Already VERIFIED through normal production | 0 |
| Still open | 599 |
| Current NOT_FOUND | 368 |
| Current UNRESOLVED | 231 |
| Accession changed | 0 |
| Complete evidence fingerprint changed | 0 |
| Canonical quarter ID changed | 0 |
| Natural key changed | 0 |
| New competing context | 0 |
| Timestamp-equivalence rule used | 0 |

All current clock values are identical to their P1.2 selected values. The P1.2 comparison helper reports `IDENTICAL_TIMESTAMP_UNCHANGED`; no candidate needs a 4/5-hour equivalence concession. No different accession, parent/amendment pair or cross-source event was merged. Both resolver semantics and raw clocks remain unchanged.

Rebinding rule: a future surrogate quarter-ID change must be evaluated against the accepted natural key and economic period, with explicitly reviewed current evidence binding. It cannot be accepted merely because an old fingerprint excludes quarter ID, or rejected solely because a surrogate changed. No such change occurs in this baseline. Evidence, source or fingerprint changes would likewise stop the affected case for explicit review. No plan preparation or production rebinding was performed here.

## Reviewed policy authority and exact classifications

The existing `resolve_sec_filings_with_event_policy` wrapper and `evaluate_candidates` were executed on the current frozen quarter/evidence scope. Neither current canonical publication tables nor the retained reviewed domestic Policy V1 and reviewed Form 6-K cohorts supplies a source-bound event observation for any of these exact keys. Those reviewed cohorts have **zero natural-key intersection** with the 599. Raw resolver context, a prior CSV label, queue resolution, another company's observation or another quarter's review cannot substitute for the missing observation.

Every current Policy V1 candidate evaluation returns `REVIEW_REQUIRED_EVENT_EVIDENCE`; the final reviewed result is `REVIEW`, with no selected accession or timestamp. This is the same gate already visible in P1.2, not new production drift. Full observations would need review references, bound evidence/context fingerprints, source document hashes and excerpts, and reviewed event/entity/period/financial-scope dimensions under the existing policy. None was synthesized from raw uniqueness.

`OTHER_HOLD` is necessary because the provided category list has no category for **unchanged deterministic evidence with missing reviewed event proof**. `EVIDENCE_CHANGED_REVIEW_REQUIRED` would falsely claim evidence changed; `NO_LONGER_RESOLVES_DETERMINISTICALLY` would falsely claim ordinary recognition regressed. There is no separately evidenced new identity transition or competing context to assign those categories. All 599 carry the exact hold reason `POLICY_V1_REVIEW:REVIEW_REQUIRED_EVENT_EVIDENCE;NO_SOURCE_BOUND_REVIEWED_EVENT_OBSERVATION` and identity status `CURRENT_CHAIN_COMPATIBLE_SEMANTIC_PERIMETER_REVIEW_MISSING`.

| Final validation category | Count |
|---|---:|
| VALIDATED_FOR_FUTURE_REVIEWED_APPLY | 0 |
| ALREADY_VERIFIED | 0 |
| EVIDENCE_CHANGED_REVIEW_REQUIRED | 0 |
| QUARTER_BINDING_CHANGED_REVIEW_REQUIRED | 0 |
| NEW_COMPETING_CONTEXT | 0 |
| IDENTITY_OR_PERIMETER_REVIEW_REQUIRED | 0 |
| NO_LONGER_RESOLVES_DETERMINISTICALLY | 0 |
| OTHER_HOLD | 599 |
| Total reconciled | 599 |

Current state classification is `STILL_OPEN_VALIDATION_REQUIRED` for all 599. None is `ALREADY_VERIFIED_BY_NORMAL_PRODUCTION`, `NO_LONGER_CURRENT_CANDIDATE` or `REVIEW_REQUIRED_DUE_TO_CHANGED_CONTEXT`. There are no already-VERIFIED cases to exclude or reopen.

Net change: zero candidates resolved through normal production, zero new evidence/context/quarter changes, and **599 prior recognition candidates held at reviewed validation**. The future reviewed-apply set has zero members. This does not revoke their unchanged ordinary recognition result or claim that no publication exists. It records the required boundary between recognition and reviewed authority.

No reviewed exclusion, precedence decision, frozen-evidence failure or independent context hold was suppressed. Policy V1 `REVIEW` stops each case as requested. No new observation extractor, event class, chronology tiebreaker, precedence rule, recognition rule or apply gate was introduced. A later authorized source-bound semantic review would be needed before any case can become a reviewed apply candidate.

## Deterministic replay and artifacts

The complete validation was run **twice** against the same frozen baseline, retained inputs, source hashes and fixed validation timestamp. Both runs produce identical natural-key populations, classifications, ordinary accession selections, evidence fingerprints, reviewed decisions, CSV bytes and artifact hashes. No natural key disappears. All 599 receive exactly one final category. The zero-row validated set excludes every Policy V1 REVIEW case.

Validation CSV SHA-256: `035718c2697b3a5ea99d2bc4af6ecadb3358331e43e1bd49450ac35632fb16b3`.

Validated-candidate CSV SHA-256 (header-only artifact): `5fff765be6078e47bdbb05e405aead52cea081705cfe5b547b999ebd1b8c97c0`.

Validated candidate population fingerprint (canonical Policy V1 fingerprint of the empty row list): `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

Complete validation population fingerprint: `56f597fc076640c28d2bf70f05288aa615c76207088d6ae88d196de13574717a`.

The validation CSV is ordered by numeric company ID, numeric fiscal year and fiscal quarter. Its ordinary `selected_accession` and `selected_timestamp` fields describe the recognized evidence for the held case; `reviewed_selected_accession` is empty throughout. Those ordinary fields are not a reviewed selection or authority update. The CSV records current authority state, exact source identity, hashes, full evidence and policy decision fingerprints, parent-context fingerprint, gate outcomes, all change flags, active generation, validation timestamp/version and future hold action. The separate validated-candidate CSV has the same complete schema and zero rows, preventing a held candidate from entering a future plan by accident.

No reusable source helper was added or changed. As requested, verification used deterministic validation assertions only, not a test-suite run. Assertions cover natural-key reconciliation, accepted current quarter binding, exact source/hash/fingerprint checks, full company resolver replay, reviewed wrapper and direct policy agreement, unresolved/durable conflict preservation, current identity compatibility, timestamp-equivalence preservation, output ordering, exclusion of all held rows, two complete byte-identical validation runs and production invariance. Targeted/regression pytest groups: **not run; no source changes**. Full suite: **not run**.

## Production invariance

Protected production artifacts, source files, retained captures and original P1.1/P1.2 artifacts were hashed before and after validation. All protected hashes and sizes are unchanged; no new SQLite sidecars appeared. Full authority logical fingerprint, provider watermark and publication journal contents also match the frozen baseline after both runs.

| Protected artifact | Baseline SHA-256 |
|---|---|
| provider | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| canonical | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| analysis | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| pointer | `30c08f22b5b9b2a3cbb07f5183d2946e3ed8b980634d0e54255936b9310b5de3` |
| queue | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| scheduler | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| forecast_scheduler | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |
| journal | `6f7e625fe10c0ab98c31902bb34d4e7a0c24ea2c94b840497b0459a07817aa67` |
| queue-wal | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| queue-shm | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` |
| fundamentals_v4_historical_publication_completeness_summary.csv | `572e72a7970c34f2031660afe71fd62be1232135fc4ab1cde0a34e7a45347dcc` |
| fundamentals_v4_historical_publication_completeness_audit.md | `9af8abcf4485757d14d4653a8e72cbc44bfaf0abf9fb85bbbcef080f1ace2ec2` |
| fundamentals_v4_historical_publication_completeness_audit.csv | `7c5786ca641899e5bbadb9b0198c318d76eda64610a5cab8baf3a7898df2ea5a` |
| fundamentals_v4_publication_timestamp_equivalence.md | `eeba5924756359008f193718909ea857ad3a51a35b196565053b21bfb375b548` |
| fundamentals_v4_publication_timestamp_equivalence_cases.csv | `52ada711cf10614e9233535a993373929250618ef540817bcf42c9369de6b43c` |
| fundamentals_v4_historical_publication_candidates_after_timestamp_equivalence.csv | `1d6ce5e9792b4ebcd664545d8ce3f981ca010f5fb2e1caec013bd33025f44d57` |

Publication authority, authority statuses, authority timestamps, provider/canonical/analysis databases, active generation, Review Queue, publication journal, scheduler configurations, provider watermark, retry horizon/cap, resolver and SEC raw evidence changed: **NO**. No authority writer, plan builder, manual drain, normal worker, generation activation or network acquisition was invoked. No Production apply plan exists from this phase. No push.

## Deliverables

- Detailed report: `docs/fundamentals_v4/fundamentals_v4_historical_publication_exact_key_validation.md`
- One-for-one 599-key validation: `docs/fundamentals_v4/fundamentals_v4_historical_publication_exact_key_validation.csv`
- Zero-row validated set: `docs/fundamentals_v4/fundamentals_v4_historical_publication_validated_apply_candidates.csv`

Only these three report/artifact files are included in the commit. Temporary frozen inputs, validation scripts, DBs, raw SEC captures, runtime artifacts and unrelated worktree changes are excluded.
