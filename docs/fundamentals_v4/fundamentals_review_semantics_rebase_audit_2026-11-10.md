# Fundamentals review semantics rebase audit — 2026-11-10

## Decision and scope

The current financial workflow stops at Preview because the review classifier's supported-local-shape allowlist sends 16 ticker-bounded exceptions to `GLOBAL_BLOCKING_REVIEW`. The publication architecture already supports safe peers plus unchanged held financial state. No current case proves a cross-ticker source, schema, identity, publication-mapping, or transaction defect. All 16 are **SAFE_TO_QUARANTINE_LOCALLY**, subject to a new, evidence-bound quarantine classification and the existing fresh Preview/Test/Production gates. This is a design conclusion, not authorization to reuse today's blocked Preview or to publish its proposed set.

The normal provider-history UI currently presents **342 tickers** as `Historical value preserved`, backed by **1,858 distinct accepted historical quarter/source conflicts**. Only **319** are pure frozen-history queue cases suitable for hiding from the normal operational list. The other **23** have source-removal or capture-integrity work and must remain visible. Five of those 23 currently expose exact source-removal confirmation authority. Filtering by the display label or `needs_action=False` alone is unsafe.

**Audit outcome: completed with a guarded design; no STOP invoked.** The proposed filter explicitly retains mixed/actionable cases and their controls. A blanket label-based filter is rejected, not approved with an exception. No production source policy or UI implementation was made. No runtime financial data, queue records, journal, manifest, scheduler settings, approvals, or historical evidence were mutated. Tests used disposable fixtures only. No live financial publication was run.

The inspection was limited to the current Fundamentals run chain, queue, active generation, publication journal, their directly responsible modules, UI/download entry points, and targeted tests. OHLCV/price-pipeline semantics and StockCore were not audited or changed. `PROVIDER_PAYLOAD_COMPLETENESS_V1` remains active and unchanged; this report does not reopen that workstream.

## A. Authoritative rebaseline

### Run identity and current result

| Fact | Current value |
| --- | --- |
| Scheduler receipt | `logs/stock_update_scheduler_summary_20261110T044418Z.json` |
| Full Workflow | `20261110T071841Z_refresh_fundamentals_d00eb7239fed_full_workflow_ba5bad1d` |
| Started / completed UTC | `2026-11-10T07:18:41Z` / `2026-11-10T07:59:27Z` |
| Helsinki time | November 10, 09:18:41–09:59:27 EET |
| Authoritative Preview child | `20261110T071841Z_refresh_fundamentals_dbbcb6f12f21` |
| Child computation completed UTC | `2026-11-10T07:54:32Z`; final artifact/report writes followed before parent completion |
| Full Workflow / child outcome | `STOPPED` / `REVIEW_REQUIRED`; child execution status `COMPLETED` |
| Trigger / mode | `SCHEDULER` / `FULL_WORKFLOW` |
| Safe effective changes | **1,073 tickers**: 1,042 `HISTORICAL_REVISION`, 31 `SOURCE_HISTORY_CHANGE` |
| Ticker-local held/quarantined items | **354** |
| Global blocker items | **16** |
| All review-required tickers | **370 = 354 + 16** |
| Other classifications | 61 `NO_EFFECTIVE_CHANGE`; 1,068 `NOT_IN_CANONICAL_UNIVERSE` |
| Discovery | `COMPLETE`; 5,167 source discovery rows; 2,570 changed source tickers; 2,572 evaluated tickers |
| Test authorization | `NO`, `GLOBAL_BLOCKER_PRESENT` |
| Production authorization | `NOT_AUTHORIZED`, `GLOBAL_BLOCKER_PRESENT` |
| Test / Production entered | **NO / NO**; parent has only a Preview stage |
| Production financial writes in this workflow | **0**, per structured terminal summary and child database-safety evidence |
| Ownership continuation | Enabled, `SKIPPED_UNSAFE_FINANCIAL_WORKFLOW`; evaluated/published **0/0** |
| Proposed source maximum | `2026-11-09`; not published |
| Refresh-set fingerprint | `d5c3ad56b5d6206a69c66c32f215978e500eb0b845558c727ea02a8cc483cf98` |

Authoritative files are the parent's `workflow_result.json` and `workflow_report.md`, and the child's `refresh_preview.json`, `refresh_ticker_changes.json`, `operation_report.md`, `status.json`, and `publish_date_bootstrap_exceptions.json` under `fundamental_reports/admin_runs/<run_id>/`. These are completed runs; no incomplete-run fallback was needed. Dated run directories were checked for later relevant entries.

The scheduler receipt uses `fundamentals_refresh_preview_run_id` for the **parent** in Full Workflow mode. Its `preview_status=FAILED`, `technical_failure` containing the global-stop message, and `published_baseline=BOOTSTRAP_BASELINE` must not override the child/parent structured evidence or actual published provider state. There is no recorded technical exception causing this stop; the current published baseline is `2026-10-28`. `final_completed_stage=null` in the stopped parent also does not mean the child Preview failed to complete.

`Local hold blocked safe peer changes: NO` describes the **354 already-local holds**, not all 370 reviews. `refresh_operational_decision()` sets this field to false whenever local held items exist, even when a separate global list prevents all progression. That field is not evidence that publication was authorized.

### Active publication and bindings

The active manifest is `data/fundamentals_active_generation.json`, created `2026-10-30T13:24:52.227558Z`. It resolves all three financial roles to:

`data/fundamentals_generations/current_rebuild_2a684ef130c6a540de4adc560ab171ad/`

| Role | File | Actual SHA-256, matching manifest verification |
| --- | --- | --- |
| Provider | `fundamentals_provider.db` | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| Canonical | `fundamentals_v4.db` | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| Analysis | `fundamentals_analysis.db` | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |

Manifest hash: `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097`. Journal hash: `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72`.

The journal's operation is `CONTROLLED_CURRENT_STATE_REBUILD`; production run ID is `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. State and current step are `COMPLETED`, generation activation is `ACTIVATED_AND_VERIFIED`, postflight is `PASSED`, recovery is `NOT_REQUIRED`, updated `2026-10-30T13:25:36Z`. Read-only `safety_status()` reports `production_writes_blocked=False`. No recovery was invoked.

The provider's `sharadar_refresh_state` still records successful routine refresh `20261029T054405Z_refresh_fundamentals_4c3b99953d00_production_a7f5b976`, completed `2026-10-29T05:47:02Z`, watermark `2026-10-28`. The later controlled rebuild did not claim a newer routine source watermark. Its provider semantic fingerprint is `8b15dea2e7338b376808d7d06ba4cf84c31436effc27acc26d3548b57ca90125`.

Current Preview schema: 112 fields, fingerprint `f13e84efeb5758665581db6303a31ac6b8953dbbe96017ff1ae5c1d2f103fe79`, equal to the published schema fingerprint. Discovery overlap starts `2026-10-25`. All **90,141** existing canonical quarters have established valid first-public dates; bootstrap eligible **0**, repair required **0**. Preview expects **1,042** new-quarter initializations in its proposed safe set. These date prerequisites are not the current stop.

### Source identity and worktree attribution

Audit checkout: `0955f03f3922d0c4cf0bd1ceab0d590e84fbfa43`. Latest relevant Fundamentals policy/source commit: `4d06c793cb6d1feb6120473955f7da2c9d4b500b`, `2026-10-30T23:09:29+02:00`, “Guard future Fundamentals ingestion with verified full provider capture”. The relevant source files are clean. Current policy identifiers include `PHASE13G3_44_REFRESH_REVIEW_QUARANTINE_V1`, `FUNDAMENTALS_HISTORICAL_FREEZE_V1`, `PROVIDER_PAYLOAD_COMPLETENESS_V1`, and `PB_ORDINARY_AUTO_CONTINUATION_V1`. The historical-source review horizon is three years, cutoff `2023-11-10`; the financial freeze is separately fixed at period end `2024-12-31`.

The Preview does not persist a Git commit identity. Therefore the precise executable commit of that historical process cannot be independently asserted. Current clean source deterministically reproduced **all fields of all 16 saved global scopes**, providing stronger classification attribution than a date assumption. The checkout identity above is the source audited, not an invented runtime receipt.

The pre-existing modified publication journal and untracked active-generation tree are runtime evidence, not unexplained source edits. Unrelated untracked price-repair/research files remained untouched. None prevents attribution of the clean Fundamentals source, so the unrelated-worktree STOP does not apply. Only this report is intended for the commit.

### Queue, Deep Review, and history

Queue: `fundamental_reports/fundamentals_refresh_review_queue.db`.

| Current queue population | Count |
| --- | ---: |
| OPEN pure frozen-history review | 319 |
| OPEN capture-unverified review | 12 |
| OPEN true source removal | 21 |
| RETRY_REEVALUATION true source removal | 2 |
| All unresolved queue rows/tickers | 354 |
| Resolved history rows | 5 |
| Append-only refresh queue audit events | 1,210 |
| Historical-conflict-observed audit events | 436 |

The **16 globals are current Preview/run evidence, not 16 extra active queue rows**: `run_preview()` upserts only local holds. The 436 audit events are repeated historical evidence captures, not current ticker or observation counts.

Current presentation reports immediate action on 10 queue tickers: **AEHR, CYRX, FDX, FERG, LFST, LIVN, MCS, MGY, PRGO, RRC**, all `TRUE_SOURCE_REMOVAL`. The preserved-label override suppresses `needs_action` on mixed rows; this must not be interpreted as absence of authority or underlying work. Five additional preserved-label rows have current confirmation eligibility: **CRON, DAVE, GRNT, PACK, PTLO**. Another six preserved-label source-removal cases remain unresolved: **ASTH, CARS, CYTK, DXC, SITE, ZBRA**. Capture-integrity work remains for **CELH, CLPT, CSTM, DFIN, HR, INSW, IPI, MBIO, ORA, TEAM, TWLO, YUMC**. Thus 23 preserved-label cases require retained operational access; five have approval authority now, while today's `needs_action` field reports zero for all 342 preserved labels.

The two `RETRY_REEVALUATION` removals do not have an approval pending publication; no active queue item currently has `approval_pending_publication=True`. Review status is not rewritten by this audit.

Accounting-boundary queue: one **APPROVED WFRD** item, no active exceptional boundary action according to `boundary_route()`. P/B queue: **10 PUBLISHED, 3 SUPERSEDED, zero current unresolved cases**. Read-only ownership diagnostics against the active generation as of November 10 detected **0 candidates**, manual/deep **0/0**. Source dispositions: **173 ELIGIBLE, 8 HISTORICAL_ONLY**, none requiring current action. The last stopped financial workflow itself routes to Deep Review; its 16 globals remain operator investigations in its run evidence. “No current queued ownership Deep Review” does not mean “no financial workflow blocker”.

### Historical comparison

| Evidence | Safe | Local held | Global | Blocker tickers |
| --- | ---: | ---: | ---: | --- |
| User-supplied 2026-10-31 historical observation | 231 | 63 | 3 | BBAI, MIR, OSK |
| Latest completed 2026-11-10 run | 1,073 | 354 | 16 | AG, ARM, BBAI, CAMT, CHRD, CIFR, INDV, KLXE, MIR, NXH, OSK, PI, RCEL, SNDK, SUPN, VTOL |

All three historical blockers remain. New relative to that supplied list: **AG, ARM, CAMT, CHRD, CIFR, INDV, KLXE, NXH, PI, RCEL, SNDK, SUPN, VTOL**. “New” here means set difference from the supplied historical observation, not an asserted first occurrence date. The never-run October 31 audit is not evidence of implementation or validation. The November 8 contextual list is not used as an exhaustive current list.

## B–D. Current global path and individual cases

### Exact decision path

1. `refresh_fundamentals.py::resolve_identity()` resolves canonical company/security/provider identities and checks metadata IDs. `fetch_complete_history()` / `validate_complete_history()` obtain per-ticker ARQ/MRQ trust evidence. `source_schema()` validates the shared required fields.
2. `compare_ticker_histories()` detects fiscal revisions with `detect_fiscal_identity_revisions()`, source removals with `build_source_history_merge()`, and payload regressions with `provider_payload.py::compare_payload()`. Existing `historical_freeze.py::apply_to_comparison()` enriches reviews with exact accepted/incoming evidence; it does not erase a pre-existing review reason.
3. `refresh_review_queue.py::classify_review_scope()` recognizes five supported local shapes: coherent short source windows; MRQ-only fiscal revisions with matching published/current ARQ companions; proven true removals; pure frozen accepted history; and bounded acquisition-integrity holds. Its decisive expression is `local = source_window_local or fiscal_revision_local or true_removal_local or frozen_local or capture_local`; everything else defaults to `GLOBAL_BLOCKING_REVIEW`.
4. `partition_changes()` separates safe classifications, local held reviews, and global reviews. `refresh_fundamentals.py::run_preview()` derives replacement count from `REFRESH_REPLACEMENT_CLASSES`, counts held/globals separately, and requires `not global_blockers` for `future_test_authorized`. Any global makes the child outcome `REVIEW_REQUIRED`.
5. `refresh_operational_decision.py::refresh_operational_decision()` renders `GLOBAL_BLOCKER_PRESENT`; this is presentation of the gate, not its origin. `full_workflow.py::run_full_workflow()` stops on the child's non-COMPLETED outcome, before Test. Its later explicit `future_test_authorized` check is another gate.
6. `refresh_copy_runtime.py::_load_bound_preview()` independently recomputes the partition and rejects globals; `revalidate_bound_source()` recomputes it again. `refresh_production.py::load_production_authorization()` independently rejects globals and requires an exact successful bound Test. Changing only report wording or the parent stop would not authorize publication.

**Every current escalation is `EXPLICIT_CONSERVATIVE_POLICY_ONLY` as a reason for crossing the ticker boundary.** These are real unsafe incoming ticker histories, but the code contains no positive test establishing a shared defect for them. Failure of an approval-compatible local shape is being used as failure of quarantine locality. In particular, ability to approve an MRQ fiscal relabel is stricter than ability to retain the ticker's already-published history.

Do not collapse `reason_codes` in saved scopes into the full issue list. That field prefers event classification reasons; it can omit the primary fiscal/payload reason when age-out events exist. The following table gives the **full report issue codes**, with the primary review reason first.

### Current blocker table

| Ticker | Exact report issue codes | Why today's local allowlist fails | Audit classification |
| --- | --- | --- | --- |
| AG | SOURCE_PAYLOAD_KEY_REGRESSION; RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON | Payload-key regression has no supported local shape | SAFE_TO_QUARANTINE_LOCALLY |
| ARM | SOURCE_PAYLOAD_KEY_REGRESSION | Same; no history events to satisfy event-based proof | SAFE_TO_QUARANTINE_LOCALLY |
| BBAI | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION | MRQ revisions fail ARQ-companion agreement | SAFE_TO_QUARANTINE_LOCALLY |
| CAMT | SOURCE_PAYLOAD_KEY_REGRESSION; RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON | Payload-key regression has no supported local shape | SAFE_TO_QUARANTINE_LOCALLY |
| CHRD | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION | ARQ plus MRQ relabels; not MRQ-only | SAFE_TO_QUARANTINE_LOCALLY |
| CIFR | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION | ARQ plus MRQ relabels; changed financial payloads | SAFE_TO_QUARANTINE_LOCALLY |
| INDV | COMPLETE_HISTORY_NOT_TRUSTED | Empty responses are not the supported capture-failure shape | SAFE_TO_QUARANTINE_LOCALLY |
| KLXE | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION | ARQ plus MRQ relabels; not MRQ-only | SAFE_TO_QUARANTINE_LOCALLY |
| MIR | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; BOUNDARY_CHRONOLOGY_INCONSISTENT; INTERIOR_SOURCE_KEY_REMOVAL; SAME_FISCAL_SOURCE_KEY_REPLACEMENT | ARQ fiscal revisions plus mixed ambiguous/true removals | SAFE_TO_QUARANTINE_LOCALLY |
| NXH | SOURCE_PAYLOAD_KEY_REGRESSION; RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON | Payload-key regression has no supported local shape | SAFE_TO_QUARANTINE_LOCALLY |
| OSK | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; BOUNDARY_FISCAL_WINDOW_TOO_SHORT; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW | MRQ fiscal evidence agrees with ARQ, but mixed age-out/ambiguous events violate fiscal-only shape | SAFE_TO_QUARANTINE_LOCALLY |
| PI | AMBIGUOUS_SOURCE_REMOVAL; COMPANION_DIMENSION_CONTRADICTION; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW | Companion contradiction violates supported oldest-prefix shape | SAFE_TO_QUARANTINE_LOCALLY |
| RCEL | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION | ARQ plus MRQ relabels; not MRQ-only | SAFE_TO_QUARANTINE_LOCALLY |
| SNDK | SOURCE_PAYLOAD_KEY_REGRESSION | Payload-key regression has no supported local shape | SAFE_TO_QUARANTINE_LOCALLY |
| SUPN | COMPLETE_HISTORY_NOT_TRUSTED | Empty MRQ response is not the supported capture-failure shape | SAFE_TO_QUARANTINE_LOCALLY |
| VTOL | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW | ARQ relabels plus MRQ relabels plus age-out events | SAFE_TO_QUARANTINE_LOCALLY |

### Evidence and locality by case

All 16 have KNOWN company/security/provider identity. Read-only inspection of their **32 published dimension histories** found no invalid rows or unresolved legacy source-version ambiguity. `accepted_history()` validated their exact accepted frozen source bindings, including financial values and equity. Every safe ticker's company ID, security ID, and provider security ID is disjoint from all **370** current review tickers; this was checked over all 2,572 evaluated entries, not inferred from ticker spelling. Consequently none of the 1,073 safe candidates depends on choosing any of these 16 tickers' incoming fiscal labels, keys, or values. Holding an entire ticker avoids applying any contested rows from it.

**AG, ARM, CAMT, NXH, SNDK.** There are respectively **91 (52 ARQ/39 MRQ), 38 (21/17), 85 (50/35), 77 (39/38), 26 (13/13)** payload comparison rows. All 317 remove exactly the old payload's `permaticker` key; all record `financial_fields_changed=False`. These comparisons concern stable source keys and unchanged normalized fiscal identity/financial projection; other proposed added rows or historical conflicts remain held with the whole ticker. The payload comparison source keys, rather than the scope's unrelated age-out keys, are the affected regression identities. Incoming history is COMPLETE for both dimensions. The raw-source field removal is not approved by this audit.

This common missing field does **not** prove a shared identity defect: the current shared schema remains the same 112-field schema as the published state; `permaticker` is not a required fundamentals source-capture field. `resolve_identity()` binds provider identity through canonical `provider_security_identity` plus separate `sharadar_ticker_metadata`, not the incoming fundamentals row's optional `permaticker`. Current IDs are KNOWN and distinct from safe IDs. The exact 317 raw-key regressions remain evidence for five ticker holds; no normalization or payload-completeness exemption is proposed. AG/ARM/CAMT/SNDK also carry frozen-history conflicts; NXH does not.

**BBAI.** Four stable-key MRQ relabels: report/date `2020-12-24`, `2021-03-31`, `2021-06-30`, `2021-09-30`; old `2020-Q4`, `2021-Q1`, `2021-Q2`, `2021-Q3` become `2021-Q1` through `2021-Q4`. Financial payload changed **0/4**. Published/current ARQ companions disagree or are absent for those proposed labels. This blocks automatic acceptance, but all identities remain BBAI and ARQ/MRQ reads are complete. Three accepted frozen conflicts enrich the evidence. No source keys disappear in its recorded history events. Whole-ticker retention does not need a decision between the labels.

**CHRD.** Stable source keys ARQ `(2021-03-08, 2020-12-31)` and MRQ `(2020-12-31, 2020-12-31)` relabel `2020-Q4` to `2021-Q4`. Financial changed **0/2**; no removed-key events. One frozen conflict. ARQ revision is outside the approved MRQ-only shape. This is a bounded company fiscal interpretation, with no implication for other companies' accepted keying.

**CIFR.** Eight stable-key revisions: four ARQ filings `2022-03-04`, `2022-05-10`, `2022-08-09`, `2022-11-14` for report periods `2021-12-31`, `2022-03-31`, `2022-06-30`, `2022-09-30`, and their four MRQ keys dated on those report periods. Fiscal labels move from `2022-Q4/2023-Q1/Q2/Q3` to `2021-Q4/2022-Q1/Q2/Q3`. Financial changed **4/8**: three ARQ and one MRQ. Five frozen conflicts; no removed-key events. Neither relabel nor changed values may be accepted automatically; freezing CIFR avoids both without affecting peer inputs.

**INDV.** Both ARQ and MRQ source responses have **0 rows**, `INCOMPLETE`, `EMPTY_HISTORY_RESPONSE`; no exact incoming financial/fiscal changes can be claimed. Published ARQ/MRQ counts are **17/20** and their current history is valid. This is an exact request/ticker response failure, not failed shared discovery/schema or evidence of corrupt safe responses. Retain the whole published ticker and require provider reacquisition. Do not infer delisting, source deletion, zero financials, or financial equality from emptiness.

**KLXE.** Eight stable-key ARQ/MRQ relabels over the same four report periods as CIFR. ARQ filing dates `2022-03-14`, `2022-05-13`, `2022-08-12`, `2022-11-10`; MRQ dates equal report periods. Labels move from `2022-Q4/2023-Q1/Q2/Q3` to `2021-Q4/2022-Q1/Q2/Q3`. Financial changed **0/8**. Four frozen conflicts; no removed-key events. The ARQ relabels prevent the current narrow approval proof, not deterministic exclusion.

**MIR.** Two stable ARQ keys `(2020-08-14, 2020-06-30)` and `(2020-11-13, 2020-09-30)` change labels `2020-Q4→2020-Q2` and `2021-Q1→2020-Q3`, with financial changed **2/2**. Removed ARQ `(2020-06-24, 2020-03-31)` has a same-fiscal replacement; removed MRQ `(2019-03-31, 2019-03-31)` has inconsistent boundary chronology; removed MRQ `(2021-09-30, 2021-09-30)` is interior, with a current key at `2021-10-19`. Four frozen conflicts. These mixed fiscal/accounting-boundary questions need exceptional review, but every old/new identity remains MIR. They do not demonstrate a defect in shared fiscal parsing. No MIR resolution or special WFRD approval is required to keep MIR unchanged.

**NXH.** In addition to its 77 payload regressions above, its four age-out identities are ARQ `(2016-08-04, 2016-06-30)`, `(2016-11-03, 2016-09-30)` and MRQ dates/report periods `2016-06-30`, `2016-09-30`. They are retention events, not permission to delete old source evidence. No frozen financial conflict is recorded. Payload regression remains the primary blocker.

**OSK.** Eight stable MRQ relabels at quarter ends `2020-12-31` through `2022-09-30`; old `2020-Q4` through `2022-Q3` move forward one fiscal quarter. Financial changed **3/8**. Every proposed MRQ label has matching accepted/current ARQ companion proof. However, two 2016-Q3 age-out events plus a 2016-Q4 short MRQ-window removal make the event stream mixed, so the fiscal-only predicate fails. Removed/retained identities: ARQ `(2016-07-28, 2016-06-30)`, MRQ `(2016-06-30, 2016-06-30)`, and ambiguous MRQ `(2016-09-30, 2016-09-30)`. No frozen conflict is attached. Excluding all OSK evidence is deterministic; accepting or merging its incoming history remains unauthorized.

**PI.** Five removal/retention events: three ARQ and two MRQ, report periods in 2016 Q1–Q3. Two are ambiguous Q3 companion contradictions, including old ARQ `(2016-11-07, 2016-09-30)` replaced by ARQ filings `2016-11-15` and `2016-11-28`, while the corresponding MRQ `(2016-09-30, 2016-09-30)` disappears. One frozen conflict. This is disagreement between PI dimensions, not different tickers. The early review return does not quantify all proposed financial differences; do not report them as zero. No stable-key fiscal-revision events are recorded. Whole-ticker freeze avoids choosing a replacement.

**RCEL.** Eight stable-key ARQ/MRQ revisions for report periods `2021-12-31` through `2022-09-30`; ARQ filing dates `2022-02-28`, `2022-05-12`, `2022-08-11`, `2022-11-10`. Labels shift `2021-Q4/2022-Q1/Q2/Q3` to `2022-Q2/Q3/Q4/2023-Q1`. Financial changed **2/8**, one ARQ and one MRQ at the earliest period. Six frozen conflicts; no removed-key events. A bounded relabel/value conflict, not shared uncertainty.

**SUPN.** ARQ source is COMPLETE with **16 rows**, MRQ is empty/INCOMPLETE with `EMPTY_HISTORY_RESPONSE`. Current published ARQ/MRQ histories are valid with **41/41 rows**. Financial/fiscal deltas cannot be concluded from this early trust failure. Exclude the whole ticker and reacquire; do not convert partial responses into removals. Independent safe responses and the shared schema passed their own gates.

**VTOL.** Eight stable-key relabels: ARQ report periods `2022-12-31`, `2023-03-31`, `2023-06-30`, `2023-09-30`, with filings `2023-03-09`, `2023-05-04`, `2023-08-03`, `2023-11-02`, shift `2022-Q4/2023-Q1/Q2/Q3` to `2023-Q3/Q4/2024-Q1/Q2`. MRQ report/dates `2021-03-31` through `2021-12-31` shift `2021-Q1/Q2/Q3/Q4` to `2021-Q4/2022-Q1/Q2/Q3`. Financial changed **2/8**. Four additional age-out events involve ARQ/MRQ report periods `2016-06-30` and `2016-09-30`; four frozen conflicts. MRQ companion proofs agree, but ARQ/mixed events remain outside the allowlist. The entire interpretation is bounded to VTOL; preserving its current generation inputs needs no fiscal repair.

Financial-change counts above cover the exact fiscal/payload comparison evidence stated, not a complete recomputation of every financial delta in early-return review cases. A proposed incoming difference is not a production write. All current published financial state remains in the October 30 generation.

### True global contract

| Escalation reason | Required cross-ticker proof | Current occurrence |
| --- | --- | --- |
| SHARED_SOURCE_INTEGRITY | Shared acquisition/discovery integrity cannot be trusted, not merely one ticker's empty response | None proved |
| SHARED_SCHEMA_OR_NORMALIZATION | Required field schema or common normalization is uncertain/inconsistent | None proved; current schema equals published schema |
| SHARED_IDENTITY_SEMANTICS | Ambiguous/colliding company/security/provider mapping can affect safe peers | None proved; reviewed and safe identity sets are disjoint |
| SHARED_PUBLICATION_MAPPING | Shared source-to-canonical or generation-role mapping is not trustworthy | None proved |
| TRANSACTION_OR_RECOVERY_SAFETY | Missing/invalid journal, generation, rollback, backups, or unresolved recovery | None current; journal terminal and verified |
| SAFE_PARTITION_NOT_PROVABLE | Cannot name/exclude all affected company/security/provider identities or preserve their accepted inputs | None current |
| EXPLICIT_CONSERVATIVE_POLICY_ONLY | Unsupported ticker-review shape defaults to global, without boundary-crossing evidence | All 16 current cases |
| OTHER_PROVEN_REASON | Equivalent cross-ticker dependency demonstrated in evidence | None current |

Unknown or incomplete locality must still fail closed globally. Do not downgrade a class merely because its label says “fiscal” or “accounting”. Shared schema drift, cross-ticker identity collisions, invalid authoritative mappings, non-deterministic partitioning, material shared input drift, candidate preservation failures, and unavailable recovery must continue to stop the workflow.

## E–F. Safe-peer publication proof and policy correction

### Existing path

`Preview partition → exact bound Test → fresh source/partition revalidation → inactive provider copy containing only safe replacements → full canonical rebuild from that mixed old/new provider → full V2/RP/RV candidate → final shared-source recheck → verified OLD generation/backups → durable PREPARED journal → prepare complete immutable generation → atomic manifest activation → cross-role postflight → COMPLETED journal → bounded queue finalization → independent P/B continuation`.

`refresh_copy_runtime.py::revalidate_bound_source()` reevaluates held tickers as well as discovery and approvals, recomputes the partition/binding, and rejects drift. `refresh_production.py::run_production_apply()` selects replacement-class tickers only after that gate, limits `histories`, `identities`, and `merge_plans` to them, and copies the provider before mutation. `replace_provider_histories()` iterates only those histories and hashes unrelated provider state before/after. `fresh_rebuild_canonical()` starts from the copied OLD canonical authority, reconstructs from candidate provider observations, preserves dates, validates unaffected financial state and fixed historical freeze, and fails before publication if accepted state cannot be preserved.

### Thirteen invariants

| # | Invariant | Result and exact supporting mechanism |
| ---: | --- | --- |
| 1 | Held excluded before authoritative provider mutation | **PASS architecturally.** Replacement classes only; safe-only history maps; mutation on inactive provider copy. Local-hold fixture verifies provider replacement count 2 and held provider fingerprint unchanged. |
| 2 | Held canonical financial rows unchanged | **PASS semantically, not physical bytes.** Full rebuild changes physical IDs/timestamps/provenance packaging; accepted fiscal identities, financial values, period/source dates remain protected. `fresh_rebuild_canonical()` rejects unexplained unaffected changes; `historical_freeze.validate_candidate()` protects accepted historical financial/source state. Held fixture fingerprints remain equal. Strengthen next-phase assertions to cover all economic fields, including parent equity and source binding. |
| 3 | Deterministic safe candidate | **PASS.** `partition_changes()`, `refresh_binding()`, partition and artifact fingerprints; Test and Production independently recompute them. Current safe/review identity sets disjoint for company/security/provider IDs. |
| 4 | Coherent V2/RP/RV | **PASS.** `full_v2_downstream.py::run_full_v2_downstream()` reads candidate provider/canonical plus bounded market and locked taxonomy. One full rebuild/package/RP/RV invocation each. Held derived scores may change with shared peer inputs; held financial authority stays old. |
| 5 | Internally consistent generation | **PASS.** `generations.py::prepare_generation_from_candidates()` and journal activation bind all three verified roles to one manifest; `_postflight()` checks physical hashes, canonical identity, dates, and analysis/taxonomy lineage. Current active three hashes equal manifest hashes. |
| 6 | Journal records actual safe publication set | **PASS by durable binding/reference, not an inline ticker list.** `prepare_journal()` records Preview/Test IDs and refresh-set fingerprint; bound Preview contains deterministic partition, provider candidate's `provider_run.metadata_json` records actual replacement tickers, and role hashes bind the published files. Refresh currently does not supply optional `scope_evidence`. Adding explicit safe/held sets there is a small auditability improvement, not a new transaction mechanism. |
| 7 | Ordinary rollback restores complete OLD generation | **PASS.** `refresh_production` exception path invokes journal recovery/rollback; generation-pointer recovery reactivates and verifies all OLD roles. Disposable post-boundary failure test passed. |
| 8 | Crash recovery valid | **PASS.** Durable activation intent precedes pointer swap; `publication_journal.recover_if_required()` / restore logic verifies OLD role hashes, handles activation-boundary ambiguity and requires a fresh retry. Generation and workflow crash tests passed. No live recovery was executed. |
| 9 | Held queue evidence intact | **PASS.** Preview upserts local evidence plus append-only historical-conflict audit; Production finalizes only applied exact approvals after successful commit. Unapproved held cases remain unresolved; held ticker reevaluation survives the watermark advance. |
| 10 | Watermark does not claim held resolution | **PASS under existing meaning.** `published_source_watermark` tracks processed discovery maximum, not universal ticker acceptance. Queue `pending_tickers()` unions unresolved tickers into future evaluation independently of overlap. Existing test forces held source timestamps below overlap and proves reevaluation persists. New local classes must enter this same durable queue before any advance. |
| 11 | Existing first-public dates preserved | **PASS.** `build_publication_date_preservation_map()` keyed by `(company_id,fiscal_year,fiscal_quarter)`; changed established date raises `REFRESH_FIRST_PUBLIC_RESULT_DATE_MOVED`; postflight checks preservation count. Current 90,141 dates already established. |
| 12 | New safe-quarter dates correct | **PASS.** Initial date comes from accepted source availability when no established date exists; missing dates fail candidate construction. Date test covers a second generation with existing preservation and new-quarter initialization. Result-publication enrichment is separately bounded in the inactive candidate. |
| 13 | P/B excludes unsafe incoming evidence | **PASS for the intended financial contract.** Continuation is skipped on current global stop; after success it resolves active published roles, never the held fetched histories. `pb_ownership_auto.evaluate()` checks exact provider/canonical/provenance evidence and unresolved source reviews before auto-continuation. Held old accepted financial data may remain usable as published authority; unapproved incoming held financial data may not. |

This proves the architecture supports safe partition publication. It does **not** claim that today's 1,073 proposed replacements were actually rebuilt/published or that current network evidence will remain stable at a future execution. Fresh native Test, all candidate gates, final source checks, and postflight remain mandatory. Candidate source/normalization or held-state preservation failure must stop that attempt rather than silently accepting drift.

### A or B

**B: current classification conservatively escalates bounded ticker reviews even though safe partition publication is supported.** There is no current proven technical need for these 16 ticker cases to block unrelated safe changes. No current ticker is classified TRUE_GLOBAL or UNRESOLVED_SHARED_SEMANTIC_RISK by this audit.

Minimal correction: separate **quarantine-locality proof** from **approval-eligibility proof** in `classify_review_scope()`. Add narrowly supported quarantine shapes for known, isolated fiscal/accounting disagreements (including ARQ and mixed events), known-ticker empty/partial history failures, bounded companion/removal contradictions, and exact optional-key payload regressions. Keep full evidence and hold the whole ticker. Do not broaden `fiscal_revision_approval_eligibility()`, `true_removal_approval_eligibility()`, historical repair authority, or WFRD accounting-boundary authority.

New proofs must bind exact company/security/provider identity; all event/source/completeness tickers; the accepted published baseline; fiscal/removal/payload evidence and fingerprints; and disjointness from the replacement set. For empty histories bind the exact failed ticker/dimension response, not fictional affected rows. Reject unexplained/multiple identity mappings and shared defects globally. Add payload comparison evidence to the local queue evidence binding rather than persisting only unrelated age-out events. Newly local holds must be durable and reevaluated after watermark advancement. Do not merely change a global label, ignore a blocker, or bypass `future_test_authorized`.

With this correction, a fresh equivalent Preview would propose **370 local holds, 0 globals, 1,073 safe changes** before fresh source/date/candidate validation. Those are counterfactual counts from the audited snapshot, not runtime state changes or guaranteed next-run counts.

## G–K. Preserved-history storage, filtering, summary, and CSV

### Current persistence and presentation

`historical_freeze.accepted_history()` reads the authoritative accepted canonical/provenance/provider binding. `historical_financial_freeze_decision()` emits exact `FROZEN_PROVIDER_CONFLICT_HELD` evidence for period ends on/before `2024-12-31`. `apply_to_comparison()` attaches it to the ticker comparison and, for otherwise safe changes, creates a frozen-history review.

`RefreshReviewQueue.upsert_local()` persists that evidence inside `refresh_review_queue.review_context_json.historical_freeze.conflicts`, one current queue row per ticker. On changed frozen evidence it appends `HISTORICAL_PROVIDER_CONFLICT_OBSERVED` to `refresh_review_queue_audit`; old evidence is retained there. Latest Preview artifacts also preserve complete evidence, including the 12 global cases with freeze evidence that are not current queue rows. Provider observations and immutable OLD generations preserve accepted financial source authority separately.

`ui_service.py::list_refresh_review_queue()` reads/decode-checks existing rows and calls `present_review_item()` to compute existing approval eligibility. `review_presentation.py::provider_review()` changes the label/classification to `Historical value preserved` / `FROZEN_HISTORICAL_PROVIDER_CONFLICT` if **any** HELD conflict exists, the row is not resolved, and no approval is pending. It sets `needs_action=False` but retains the existing allowed actions. It does not mark the queue row resolved. `review_groups()` treats these nonterminal rows as current. `dev_tools/fundamentals_admin_page.py::render_review_queue()` consequently renders each one in the ordinary provider-history/source-removal list; `operational_presentation.review_route()` explicitly routes frozen classification to REVIEW.

These are **persistent ticker queue rows plus nested conflict evidence plus derived presentation labels**, not 1,858 independent queue items or disposable UI rows. Retained-outside-source-window age-out evidence is distinct: a retention event alone does not make a ticker preserved-history, actionable, or resolved.

| Population | Unique tickers | Current conflict entries |
| --- | ---: | ---: |
| Pure frozen queue reviews | 319 | 1,797 |
| Mixed preserved-label queue reviews | 23 | 61 |
| All current preserved-label queue reviews | **342** | **1,858** |
| Additional latest-Preview globals with frozen evidence | 12 | 50 |
| All latest-Preview frozen evidence, regardless of queue presentation | **354** | **1,908** |

The 1,858 queue conflict identities are distinct by `(company_id,fiscal_year,fiscal_quarter)` in the current snapshot. That is an accepted historical quarter/source-observation binding count, not the count of all incoming candidate versions. Pure frozen rows contain 2,313 affected history-event source keys, which include retention and must not be substituted for 1,797 accepted frozen-conflict identities. Resolved frozen history is excluded from the current presentation population; append-only observations are not summed into current totals.

### Safe normal-list predicate

Prefer a pure presentation helper operating on existing validated rows and their existing eligibility fields. Hide a row from the **normal list only** when all are true:

1. Its persisted primary `review_type` is exactly `FROZEN_HISTORICAL_PROVIDER_CONFLICT`, it is unresolved, and exact current HELD frozen evidence exists.
2. It has no independent unresolved removal, fiscal/accounting, capture-integrity, explicit actionable hold, global, or Deep Review issue. Allow only frozen-conflict and benign retained/age-out context; unknown codes remain visible.
3. None of the existing approval eligibility booleans is true; no approval awaits publication; no separate backend-required next action exists.

Never use only `display_status`, overridden view classification, or overridden `needs_action`. With current evidence the predicate hides **319**, retains all **23 mixed preserved-label rows**, and leaves all other active review rows visible. Mixed rows should present their persisted primary issue/action before the historical-preservation note so the existing frozen-label override no longer masks actual work. This is display precedence only; approval eligibility and actions remain exactly backend-owned.

Add an “Historical preservation evidence” expander in the existing Deep Review/evidence area or use the existing evidence-panel mechanisms to enumerate the hidden cases on explicit request. It must retain Details and the existing Wait/Retry navigation/actions without adding approval. Do not rely only on resolved-history controls or their recent-history filter: these OPEN rows are not terminal history. Keep current Details dialogs, raw technical evidence, audit trail, and original run reports accessible. This satisfies evidence access without rendering 319 rows during normal loading.

**Safe answer:** presentation-only filtering of the proven non-actionable subset is possible. Hiding all 342 display-label rows would remove current operator access and is prohibited. No review deletion, migration, status resolution, authority change, financial rewrite, or historical cleanup is required.

### Deterministic summary definitions

Use the existing **provider queue presentation population** as the explicitly scoped list. Suggested summary:

> Historical values preserved: **342 tickers · 342 seen in latest run**

Add a short neutral explanation: “Historical evidence is retained. Cases with other current reviews remain in the operational list.” Do not add these counts to attention/deep totals.

**N** = cardinality of normalized ticker keys `ticker.strip().upper()` in validated current unresolved queue rows with at least one current `FROZEN_PROVIDER_CONFLICT_HELD` conflict, excluding resolved/terminal rows and approvals already pending publication. This is the same population currently eligible for the preserved presentation label; it includes mixed actionable cases, which remain visible operationally. Source is the current queue snapshot, not accumulated audit events. Count each ticker once. N is currently **342**.

**M** = cardinality of `N_ticker_set ∩ latest_preview_preserved_ticker_set`, where the second set comes from HELD frozen-conflict evidence in `ticker_changes` of the **latest completed authoritative financial Preview**. M is currently **342**. There are 354 such tickers in that Preview across all scopes; 12 are global run-only evidence outside this chosen queue-presentation population and are not added to M or N. Deep Review/run evidence still exposes them. If a future implementation elects to expand N to all current run-only globals, change and label that contract explicitly; do not silently mix the populations.

Select the authoritative Preview by completed financial execution metadata, not lexicographic directory mtime, a parent masquerading as a Preview, a running child, ownership runs, or a historical copy test. Resolve a Full Workflow parent to its Preview child. Never rerun Preview to compute these numbers. Current `last_seen_run_id` for all 342 equals the authoritative child, corroborating the explicit set intersection. A queue upsert of the ticker alone is not a general proof that a frozen conflict was encountered in that run. Missing/corrupt latest evidence means “latest run count unavailable”, not zero and not a silent older-run substitution.

Read current queue population/eligibility in one read transaction; capture latest completed Preview identity once; summary and CSV use the same pure aggregation. If evidence changes during export, retry the read or fail visibly. Keep the read-only contract; do not instantiate startup recovery or sync workflows.

### Download design

One on-demand **UTF-8 CSV**, one row per N ticker, sorted ascending by normalized ticker. Suggested filename: `fundamentals_preserved_history_2026-11-10.csv`. A dedicated fixed GET endpoint, for example `/fundamentals/admin/preserved-history.csv`, should call the read-only aggregation directly and return an attachment with `text/csv; charset=utf-8`. Add a button beside the compact summary. Register it through the existing scheduler UI application factory in `dev_tools/stock_update_scheduler_ui.py`, using the same access context as Fundamentals Admin.

The existing report download resolver only allows Markdown operation/workflow reports. Do not insert CSV into that allowlist or pretend a generated current list is an old run artifact. A dedicated response avoids persistent temporary files and any client-supplied filesystem path. Use the standard CSV writer for quoting/newlines and neutralize spreadsheet formulas in textual fields.

| Column | Deterministic derivation |
| --- | --- |
| ticker | Normalized queue key; one row per ticker |
| presentation_status | `Historical value preserved` |
| primary_reason | Mixed actionable persisted primary review reason first; otherwise `Frozen historical provider conflict`; fixed human wording |
| issue_codes | Sorted distinct union of persisted review type, reason codes, and current HELD conflict reason codes, semicolon separated |
| affected_historical_observation_count | Distinct accepted `(company_id,fiscal_year,fiscal_quarter,accepted_source_observation_id)` bindings among HELD conflicts; exclude incoming candidates and age-out-only events; blank/unavailable on incomplete evidence rather than an invented zero |
| latest_seen_run_id | Latest authoritative financial Preview encounter of this preserved evidence, from current context plus exact frozen-event audit/run evidence; not unrelated last ticker activity |
| latest_seen_date | UTC date of that encounter, ISO `YYYY-MM-DD`; current rows `2026-11-10` |
| operator_action_required | `true` for independent unresolved operational work or existing approval eligibility; `false` for pure protected-history cases. Current design: 23 true, 319 false. This is conservative UI triage, not new approval authority. |
| current_next_action | Existing permitted review action/guidance for mixed rows; `No immediate action required` for pure cases; no raw JSON |

Where several audit encounters support a ticker, choose maximum `(Preview completion timestamp, run_id)` among encounters that actually contain preserved evidence; aggregate conflicts by the accepted-binding key and issue codes by sorted set. Current row `last_seen_*` may be used when it is verified to be a preserved encounter, as in this snapshot. If it is not, resolve existing audit/run evidence; leave unknown fields blank when proof is unavailable. Current authoritative rows are one per ticker, so no second list database or historical version graph is needed. Extra evidence references may be added, but ordinary columns should remain human-readable.

### Persistence decision

**No new persistence is required.** Current queue evidence, existing audit events, and completed Preview artifacts deterministically yield current membership, encounter provenance, counts, CSV, and evidence links. A request-scoped read projection is sufficient. A small completed-Preview summary artifact may later improve read cost without becoming a shadow authority; do not add it merely to avoid implementing deterministic reads. Current run artifacts are large, so stream the necessary projections or reuse existing bounded history metadata rather than loading several gigabytes per page render.

## L. Next implementation phase

Implement one combined **review locality and preserved-history operational presentation** phase. Backend classification and UI are compatible with one source rollback boundary; no schema/data migration is needed. Financial publication and the existing independent ownership publication remain separate transactions. Do not combine those transaction boundaries.

| Module/file | Required change |
| --- | --- |
| `rawcandle/fundamentals/admin/refresh_review_queue.py` | Add explicit evidence-bound quarantine-local shapes; retain unknown/shared global fallback; bind payload/empty-response/mixed fiscal evidence into durable queue context; keep approval predicates unchanged. |
| `rawcandle/fundamentals/admin/refresh_fundamentals.py` | Bind operation-wide identity disjointness and shared validity before authorizing safe set; persist newly local holds through existing queue; count safe/local/global independently; include primary issue alongside event codes. |
| `rawcandle/fundamentals/admin/refresh_copy_runtime.py` | Recompute identical quarantine policy at Test and fresh revalidation; maintain safe-only histories; strengthen semantic held-state evidence including equity/source binding. |
| `rawcandle/fundamentals/admin/refresh_production.py` | Reuse existing authorization and transaction; pass optional journal `scope_evidence` containing actual replacement/held ticker sets plus partition fingerprint; assert candidate provider replacement set equals the authorized safe set. |
| `rawcandle/fundamentals/admin/full_workflow.py`, `refresh_operational_decision.py`, `refresh_scheduler.py`, `run_presentation.py` | Report actual stage/outcome, separate local holds from true globals, and avoid interpreting `local_hold_blocked_safe_changes=False` as authorization. Do not bypass native gates. |
| `rawcandle/fundamentals/admin/review_presentation.py`, `operational_presentation.py` | Pure hidden-row predicate and mixed-issue precedence; preserve all eligibility and authority. |
| New `rawcandle/fundamentals/admin/preserved_history_presentation.py` | One pure deduplicating projection shared by summary, CSV, and evidence population; no database writes or authority. |
| `rawcandle/fundamentals/admin/ui_service.py` | Read-only service projection with one queue snapshot and authoritative completed Preview selection; expose summary/list/export without recovery/sync side effects. |
| `dev_tools/fundamentals_admin_page.py` | Hide only pure non-actionable rows normally; render compact N/M plus download; retain mixed cases and explicit evidence navigation. |
| `dev_tools/stock_update_scheduler_ui.py` | Dedicated fixed CSV response route; preserve existing report resolver restrictions. |

`historical_freeze.py`, `accounting_boundary_review.py`, `provider_payload.py`, `source_capture.py`, generation activation, recovery, publication-date policy, and P/B financial ownership rules should retain their authority semantics. Modify them only for narrowly necessary evidence plumbing with regression proof; do not weaken them to make new locality tests pass.

Required sequence: implement the bounded classification/evidence projection and presentation together; run targeted regression tests; run the combined workflow on a **disposable coherent generation/queue copy** with captured provider fixtures and isolated manifest/journal/market/taxonomy bindings; review exact safe/held sets, held economic fingerprints, dates, watermark, journal, and postflight; exercise ordinary failure and crash recovery; verify CSV/rendering immutability. Only a later explicitly authorized live operation may execute a fresh Full Workflow with native current source checks. Do not reuse this audit's blocked Preview/Test authorization or publish a generation as part of the source patch.

Migration: **none**. No historical/queue/generation rewrite, review-decision backfill, new list table, or runtime cleanup. New observed evidence flows through normal Preview upserts and existing append-only audit. Deployment rolls back source/UI together; native financial failure restores OLD generation, retaining held review evidence.

## M. Exact acceptance coverage

Extend existing bounded files rather than run the full suite. Existing fixture foundation is `tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py`; generation/recovery foundation is `tests/test_fundamentals_generations.py`. New test names below are implementation targets, not claims they already exist.

| # | Targeted acceptance test | Required assertions |
| ---: | --- | --- |
| 1 | `test_arq_or_conflicting_mrq_fiscal_hold_publishes_safe_peers` in full-workflow parity | BBAI-shaped MRQ disagreement and CHRD-shaped ARQ relabel each stay held; two safe peers reach bound Test and disposable Production; approval remains unavailable for unsupported repair. |
| 2 | `test_multiple_mixed_local_reviews_publish_safe_partition` in parity | Combine CIFR/MIR/OSK/PI/VTOL shapes, optional-key regression, and empty dimension response; all affected ticker/company IDs excluded; safe peer set publishes exactly once. |
| 3 | `test_shared_defects_still_stop_before_test` in review queue/parity | Parameterize required schema failure, shared capture invalidity, identity collision, cross-ticker event, ambiguous mapping, unprovable accepted baseline, and partition mismatch; zero Test/Production entry. |
| 4 | `test_every_held_financial_binding_is_preserved` in parity | Hash complete held provider payload/header/provenance plus canonical economic state keyed by stable identity, including parent equity, source binding, periods, established dates; compare before/after. Physical canonical IDs/timestamps may rebuild. |
| 5 | `test_actual_provider_run_equals_safe_publication_set` in parity | Candidate provider metadata and actual changed canonical values equal safe set; no held incoming row or approved-evidence substitution. |
| 6 | Existing generation activation plus new combined-held fixture | All three roles activate under one manifest, V2/RP/RV lineage and postflight PASS; OLD hashes unchanged; journal scope and role hashes match actual publication. |
| 7 | Existing post-boundary rollback test with new held classes | Inject after activation and at postflight; restore complete OLD generation and dates/watermark, preserve unresolved queue evidence. |
| 8 | Existing crash-recovery tests with combined fixture | Crash before activation, during activation intent, after swap, and before COMPLETED; verify OLD recovery and fresh retry requirement. |
| 9 | `test_new_local_classes_reevaluate_below_watermark_overlap` | Advance safe discovery watermark; force held source timestamps below overlap; each held class remains durably queued and reevaluated, never falsely resolved. |
| 10 | Existing second-generation publication-date test with holds | Established first-public dates immutable; new safe quarter date initialized correctly; no held new-quarter/date acceptance. |
| 11 | `test_ownership_after_safe_partition_uses_published_safe_financials` in P/B future tests | Auto continuation only after safe result/current active generation; explicit held financial/review cases do not consume incoming evidence; unchanged published held values may not be replaced; independent ownership failure cannot roll back completed financial publication. |
| 12 | `test_pure_preserved_history_is_hidden_normally` in UI/presentation | Pure OPEN freeze case absent from normal list; no row-by-row hidden evidence construction on normal render. |
| 13 | `test_hidden_preserved_history_remains_in_evidence` | Same exact evidence/Details/Wait/Retry reachable through explicit evidence view; no terminal-history age filter hides unresolved evidence. |
| 14 | `test_mixed_preserved_cases_keep_existing_authority` | CRON/DAVE/GRNT/PACK/PTLO-shaped confirmation cases and capture/other removal/global/Deep cases stay visible with primary next action; unknown codes stay visible. |
| 15 | `test_preserved_summary_total_deduplicates_current_tickers` in new projection tests | Duplicate audit/conflict rows do not inflate N; exclude resolved and pending approved-publication cases; known fixture N exact. |
| 16 | `test_preserved_latest_count_uses_completed_preview_intersection` | M is set intersection; ignore running runs, ownership children, parent-as-preview, unrelated ticker encounters; missing evidence reports unavailable; current-snapshot fixture N/M 342/342 while total latest freeze tickers 354. |
| 17 | `test_preserved_csv_matches_summary_population` | Exactly N unique sorted rows, exact required columns/aggregation, no raw JSON; current fixture 342 rows, 23 operational-action flags, 319 pure cases; quote multiline/semicolon text and spreadsheet formulas safely. |
| 18 | `test_preserved_csv_is_read_only` in endpoint/service tests | Forbid writable SQLite connects and recovery/sync/upsert; before/after queue/audit/financial/journal/manifest hashes equal; traversal inputs cannot name paths. |
| 19 | `test_preserved_render_and_summary_are_read_only` | Same mutation guards for refresh/render/expand evidence and summary; repeat calls deterministic; no source fetching or approval creation. |
| 20 | `test_existing_review_eligibility_is_unchanged` | Existing positive/negative exact approval fixtures unchanged; pending/consumed/drift cases keep existing behavior; new quarantine-local status alone grants no financial/fiscal/removal/boundary repair authority. |

Also retain existing tampered-partition, stale-source, shared-input drift, historical-freeze, true-removal authority, fiscal-approval evidence drift, P/B source review, and report-routing regression tests. Test scope should be bounded to these modules and cases, with every financial mutation redirected to disposable paths.

## Audit validation and STOP conditions

Read-only diagnostics performed:

- Matched November 10 scheduler receipt, parent, child artifacts, and structured report counts; streamed the large ticker-change artifact instead of querying live providers.
- Replayed `classify_review_scope()` on all **16** current blockers and compared every computed scope field with saved authoritative scope evidence: **PASS**.
- Checked safe/review partition company, security, and provider-security disjointness across the complete evaluated snapshot: **PASS** for **1,073 / 370** identities in each domain.
- Checked all 16 current published ARQ/MRQ histories for invalid/ambiguous source versions and validated accepted frozen bindings: **PASS**.
- Decoded current queue evidence fingerprints and evaluated existing presentation/approval eligibility read-only; derived exact 342/319/23 populations and 1,858 conflicts.
- Read active generation hashes, provider refresh state, terminal journal/safety, boundary/ownership/disposition state, and read-only P/B diagnostics.

Existing tests run, with production database guard enabled, bytecode/cache writes disabled for the invocation, and disposable test root `/tmp/rawcandle-fundamentals-rebase-tests`:

```text
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/tmp/rawcandle-fundamentals-rebase-tests \
  tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py::test_refresh_full_workflow_quarantines_local_mrq_fiscal_revision \
  tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py::test_refresh_full_workflow_quarantines_yyai_and_publishes_two_safe_tickers \
  tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py::test_refresh_full_workflow_global_review_still_stops_fail_closed \
  tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py::test_refresh_real_production_activates_one_complete_generation \
  tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py::test_refresh_full_workflow_publication_failure_rolls_back_only_three_db_generation \
  tests/test_fundamentals_admin_refresh_full_workflow_production_parity.py::test_refresh_full_workflow_crash_recovery_restores_old_and_requires_retry \
  tests/test_fundamentals_generations.py \
  tests/test_fundamentals_historical_freeze.py \
  tests/test_fundamentals_admin_refresh_copy_test.py::test_second_generation_preserves_established_date_and_initializes_new_quarter
```

Result: **42 passed in 68.80 seconds**. No full suite or live publication was run. These tests prove existing supported-local architecture, not the unimplemented expanded-local classification or new UI/CSV; acceptance for those changes remains required in the next phase.

Reapply STOP if current authority cannot be established; saved/current classification diverges without explanation; safe-peer invariants become unprovable; a real shared semantic/source defect appears; current membership cannot be derived deterministically; proposed filtering loses current authority/action; live runtime mutation becomes necessary; or worktree changes prevent source attribution. Reject blanket preserved-label filtering because it would lose access to five existing confirmation actions and obscure other mixed work. The guarded pure-row filter avoids that condition. Any newly discovered candidate preservation defect must remain fail-closed and be repaired/proven before a downgrade or publication.

**No-runtime-mutation statement:** this audit performed no live provider/canonical/analysis or review-queue writes, no review decisions, no generation activation, no journal/recovery changes, no scheduler edits, no cleanup, and no price-pipeline modifications. Only the audit document and disposable diagnostic/test artifacts were created. Before/after SHA-256, size, and modification-time comparisons passed for the active manifest, publication journal, queue database, and all three active financial database files. The queue database hash remained `9d461822eb51b5e01fdf6310c58b1a67265a9fefb210b3c50232911f1a041428`; all active-role/manifest/journal hashes remained those recorded above. SQLite's shared-memory reader bookkeeping is not a queue-record or financial-data mutation. The commit is restricted to this report; the existing runtime journal diff and unrelated files are excluded.

## Appendix: exact current ticker-local partition

These are the 354 local-held tickers in the authoritative Preview, grouped by persisted review type. The 16 global cases are listed separately above.

**FROZEN_HISTORICAL_PROVIDER_CONFLICT — 319 tickers**

AA, ABR, ADV, AEVA, AFCG, AHCO, AIN, AIP, AISP, AKR, ALEC, ALGS, ALHC, ALIT, ALLO, AMD, AMR, AORT, APA, APG, APLE, APPN, AQB, ARAY, ARHS, ARLP, ARVN, ASLE, ASTI, ASX, ATLX, ATMU, AUR, AVPT, BBSI, BCTX, BDSX, BFLY, BHR, BIAF, BILL, BIVI, BJDX, BL, BLNK, BLZE, BMBL, BRCC, BSM, BSY, BWMN, BWXT, CABO, CCCC, CCSI, CDE, CDRE, CDT, CENX, CGC, CGTX, CHMI, CL, CLOV, CLVT, CMPS, CMTG, CNX, COCH, CODI, CORZ, CP, CPAY, CRC, CRGY, CRH, CRK, CROX, CRTO, CSL, CVI, CWK, CXDO, DEC, DH, DHC, DKNG, DOLE, DT, DTM, DV, DWTX, ELF, EMPD, ENB, EOSE, ERNA, ESAB, EVEX, EVH, FLUT, FLWS, FND, FTDR, FWRG, GEV, GHM, GMED, GNK, GPK, GPMT, GRMN, GRND, GTM, GTX, GXO, HCAT, HGV, HLLY, HLMN, HNI, HRMY, HWM, IBEX, ICE, ICFI, ICHR, ILPT, INDI, INGR, INM, INMB, INSE, INSG, INSP, IONQ, IPAR, IRM, IRON, ITW, JBGS, JBTM, JOBY, JSPR, KD, KIM, KNF, KOSS, KRP, KRYS, KTB, KVUE, KVYO, KYMR, LAD, LASR, LCII, LENZ, LIND, LITS, LLY, LMB, LPX, LTBR, LUCK, LUNG, LVWR, LXFR, MAC, MAS, MDGL, MG, MLTX, MLYS, MP, MSEX, MSGE, MTH, MTRX, NAMS, NB, NEOV, NGL, NMRK, NNDM, NSSC, NVCR, NVCT, NVT, NWN, NXDR, NXXT, O, OABI, OCGN, OEC, OGE, OGN, OGS, OKLO, OM, OMEX, ONCO, OPAD, OPEN, OSW, OTIS, OUST, PACS, PAYO, PCT, PGEN, PGY, PHAT, PHIN, PHIO, PLBY, PLSE, PMT, PRM, PROF, PRVA, PSQH, PTCT, PVLA, PYXS, QNRX, QSI, RBBN, RDDT, RDVT, RDW, REVB, REYN, RIVN, RLJ, RSI, RUN, RZLT, SABS, SBGI, SCI, SDRL, SEGG, SERV, SG, SHLS, SHOP, SINT, SKIN, SLDB, SMHI, SMMT, SMR, SN, SOLV, SON, SPOK, SPSC, SRPT, SRTA, SSNC, SSRM, STOK, STRL, STTK, SVV, SWK, SXT, SYRE, TALO, TARA, TARS, TASK, TBLA, TECH, TECX, TELO, TKO, TLN, TMUS, TNDM, TNET, TOST, TPL, TRDA, TRON, TROX, TTGT, TVTX, TYGO, UFPT, ULS, UMH, UP, USAC, USFD, UVV, VAC, VEEE, VICI, VMD, VNT, VRRM, VST, WEST, WHD, WHLR, WLDN, WPC, WRBY, WY, XERS, XFOR, XNCR, XPEL, XXII, YUM, ZLAB.

**SOURCE_PAYLOAD_CAPTURE_UNVERIFIED — 12 tickers**

CELH, CLPT, CSTM, DFIN, HR, INSW, IPI, MBIO, ORA, TEAM, TWLO, YUMC.

**TRUE_SOURCE_REMOVAL — 23 tickers**

AEHR, ASTH, CARS, CRON, CYRX, CYTK, DAVE, DBD, DXC, FDX, FERG, GRNT, LFST, LIVN, MCS, MGY, PACK, PRGO, PSN, PTLO, RRC, SITE, ZBRA.
