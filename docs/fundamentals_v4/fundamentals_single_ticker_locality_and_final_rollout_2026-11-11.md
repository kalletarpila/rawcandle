# Single-ticker locality and final rollout investigation — 2026-11-11

## STOP: accepted financial source bindings cannot be fully verified

**No live Full Workflow, Test, Production, financial publication, UI deployment or new implementation commit was performed.** Recovery remains qualified. The governing locality principle was implemented in a diagnostic candidate, but that candidate is archived and removed from the executable checkout after a different safety precondition failed.

The diagnostic replay positively isolated **408 local reviews**, including SUPN, with **1,170 effective safe changes**. **17 reviews** failed accepted-baseline verification because each has six canonical field-provenance references to a provider observation absent from the active provider database. INM is one of those 17. Each remaining blocker has concrete unisolatable accepted-authority evidence; none is blocked merely because its shape is unknown or its response receipt is absent.

The task explicitly requires a valid accepted held baseline and STOP when that cannot be proven. The missing references were not ignored, rebound to different observations, repaired in runtime, or replaced with new incoming evidence. The current financial values checked for INM and NXXT match their current primary source; this is **not** a claim of corrupt financial amounts. It is a failure to verify the exact recorded source identities required by the preservation contract.

All temporary source changes were archived and removed. The committed recovery fix is retained exactly. No conditional live-run authorization was consumed.

## Fresh current-state baseline

The prompt's “uncommitted recovery fix” statement was stale: the user subsequently requested its commit, producing `9ed344e397fde8912eba5b0ebf38f285e7d4751d`. Current source HEAD is `4e332aa81fddfc9f833dff495e296df1b3359357`, with the intervening documentation/research commits retained. Relevant source/tests were clean before this investigation.

| Field | Fresh observation |
| --- | --- |
| Latest scheduler receipt | `logs/stock_update_scheduler_summary_20261111T044713Z.json` |
| Latest completed parent | `20261111T072655Z_refresh_fundamentals_d00eb7239fed_full_workflow_d07cf1a4` |
| Authoritative Preview | `20261111T072655Z_refresh_fundamentals_8d7ad5f72900` |
| Parent completed | `2026-11-11T08:11:34Z`, STOPPED at Preview |
| Test / Production child | None / none; both explicitly not invoked |
| Effective safe / local / global | 1,170 / 406 / 19, deployed baseline |
| Active generation | `current_rebuild_2a684ef130c6a540de4adc560ab171ad` |
| Provider watermark | `2026-10-28` |
| Journal operation | CONTROLLED_CURRENT_STATE_REBUILD |
| Journal state / current step | COMPLETED / COMPLETED |
| Postflight / recovery | PASSED / NOT_REQUIRED |
| Unresolved / resolved review rows | 406 / 6 |
| Review audit rows | 1,273 |
| P/B state | 10 PUBLISHED, 3 SUPERSEDED; no unresolved cases |
| Overnight P/B continuation | SKIPPED_UNSAFE_FINANCIAL_WORKFLOW, published 0 |
| WFRD accounting boundary | APPROVED; unchanged |
| Preserved-history N / M | 392 / 392, fresh read-only baseline projection |

No newer completed scheduler/financial workflow was found in the bounded run metadata inspection. The scheduler `.ec-retention.json` sidecar was excluded from receipt selection. Structured scheduler and parent evidence independently confirm no Test or Production entry. Legitimate overnight queue changes were preserved.

| Protected authority | Verified SHA-256 |
| --- | --- |
| Provider | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| Canonical | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| Analysis | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |
| Active manifest | `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097` |
| Runtime journal | `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72` |
| Review queue | `51e564ed7827464a6cb0c887822d03be684e0973805b4a28247a74d464d263d0` |
| Scheduler configuration | `f4ba4fc0fde48e3ac82f5314353556ae35a0327a2e568b41abf9c759c35bb8a3` |

All three role hashes matched the active manifest. The journal was terminal and healthy. Thus the initial immutable-generation safety gate passed; it does not by itself verify every cross-database field-provenance reference.

Deployed baseline globals and primary reasons: AG/ARM/CAMT/NXH/SNDK/VMRK — SOURCE_PAYLOAD_KEY_REGRESSION; AIOT/BBAI/CHRD/CIFR/KLXE/MIR/OSK/RCEL/VTOL — REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; PI/TDW — AMBIGUOUS_SOURCE_REMOVAL; INM/SUPN — COMPLETE_HISTORY_NOT_TRUSTED. Exact additional removal/companion reason codes are preserved in `current_globals.json` in the evidence directory below.

## Recovery fix retained and requalified

The existing native Refresh fix selects byte-exact backups for immutable generations and validates all three source/backup hashes and resolved paths against the OLD manifest before journal preparation. Legacy mutable flat-layout backups retain online-backup behavior. Recovery/manifest verification, full OLD restoration, activation-intent durability and retry semantics remain unchanged.

The required minimal reproduction ran first: `AFTER_NEW_GENERATION_READY` through the native immutable-generation workflow, verified OLD recovery, recovery-only first invocation and a successful subsequent fresh workflow. **1 passed in 18.11 seconds.**

The established bounded selection then ran: `test_fundamentals_generation_recovery_binding.py`, `test_fundamentals_generations.py` and the three relevant existing Refresh-production recovery/idempotence/completed-journal test families. **38 passed in 67.10 seconds.** This includes native production-parity safe publication, ordinary rollback, crashes around durable activation intent and manifest swap, postflight boundaries, all-role restoration, mismatch rejection and fresh retry. No live database was copied for that rehearsal. No full suite was run.

Recovery remains safe under this qualified contract. The later STOP concerns accepted ticker source bindings, not recurrence of `RECOVERY_OLD_GENERATION_SET_MISMATCH:provider`.

## Response-receipt authority and exact trace

Directly inspected the native Sharadar client, `source_capture.py`, complete-history validation, provider insertion/reload, review binding and the archived locality helper. These contracts must remain distinct:

- **Accept incoming rows:** require native authoritative full-source row capture, exact raw/projection integrity, identity validation and complete-history checks. Legacy accepted data cannot attest a new acquisition.
- **Hold an entire ticker:** prove unique identity, a valid accepted baseline, deterministic exclusion, no shared dependency, durable review evidence and preservation through candidate generation. This does not require accepting or interpreting incoming amounts.

### What the prior “required receipt” was

The archived patch added `HistoryTrust.response_evidence`, populated by its `fetch_complete_history()` wrapper after `result.ok`. Its fields were kind SUCCESSFUL_TICKER_HISTORY_RESPONSE, requested ticker, dimension, HTTP status, full-history-request flag and returned-record count. The archived `supported_evidence()` required these fields to localize incomplete histories.

That object is per ticker/dimension fetch, not per row. It is a consumer-generated response summary, not an independently sealed native HTTP acquisition receipt. Existing pre-patch Preview artifacts could not contain a field the pre-patch acquisition wrapper never created. It must not be invented during replay or treated as approval-grade row capture.

### Native creation, transport, persistence and reload

1. `SharadarClient._request()` obtains HTTP status/body, parses records and invokes `source_capture._http_records()` on successful unprojected supported endpoints.
2. `_http_records()` creates a CapturedRecord **for each returned row**. Its envelope binds native acquisition origin, request-parameter fingerprint, response-body SHA-256, UTC acquisition time, exact raw payload/key-state/projection fingerprints and source identity.
3. `capture.wire()` transports the exact raw acquisition payload plus envelope. Provider insertion stores the envelope in `provider_observation.provenance_json.source_capture`, with the raw payload stored separately.
4. `load_current_history()` restores `_capture_envelope`, `_capture_transport` and `_acquisition_payload`; it does not manufacture a new acquisition.
5. Stable review projections intentionally omit acquisition-time and response-wide volatile fields while keeping row evidence bindings. Full response receipts cannot simply be added to deterministic revalidation fingerprints without handling that distinction.
6. An empty response creates **zero row envelopes**. `SharadarResult` has HTTP status, endpoint, redacted URL, records and parsed payload, but no response-level receipt field. There is no receipt to transport, persist or reload for that empty response.
7. Complete-history validation emits INCOMPLETE / EMPTY_HISTORY_RESPONSE with zero rows and the normalized empty fingerprint. The old saved review evidence preserves that validation outcome, not the original HTTP status/request envelope.

An empty or limited/partial response can in principle have valid request/response provenance; absence of accepted rows is not absence of a real HTTP response. Existing per-row envelopes can prove native capture for returned rows, but cannot create an envelope for zero rows or prove completeness of a missing dimension. Missing receipt material alone does not establish shared failure. A whole-ticker hold can use less incoming interpretation than publication, while retaining its independent accepted-baseline requirements.

### Four bounded current native requests

Only INM and SUPN were requested, ARQ and MRQ each, using the existing native limiter, authentication and capture path. Credentials were not printed or saved. No production persistence or queue update was performed.

| Ticker | Dimension | HTTP / status | Returned rows | Row capture envelopes | Explicit response receipt | Complete-history result |
| --- | --- | --- | ---: | ---: | --- | --- |
| INM | ARQ | 200 / SUCCESS | 0 | 0 | None | INCOMPLETE / EMPTY_HISTORY_RESPONSE |
| INM | MRQ | 200 / SUCCESS | 0 | 0 | None | INCOMPLETE / EMPTY_HISTORY_RESPONSE |
| SUPN | ARQ | 200 / SUCCESS | 16 | 16 | None | COMPLETE |
| SUPN | MRQ | 200 / SUCCESS | 0 | 0 | None | INCOMPLETE / EMPTY_HISTORY_RESPONSE |

The trace retains exact requested ticker/dimension/limit, endpoint, redacted URL, response status/count, returned row envelopes, trust evidence, current identity and accepted persisted provider provenance. The empty fingerprint is `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

For **both** tickers, receipt root-cause classification is **MULTIPLE_PROVEN_DEFECTS**: ACQUISITION_RECEIPT_NOT_CREATED at response level, plus LOCALITY_PROOF_OVERREQUIRES_RECEIPT in the old archived classifier. No transport loss, persistence loss, reload loss, or upstream non-authoritative response was proven. Existing accepted legacy provenance was not used to attest these new responses.

## Governing locality principle and diagnostic candidate

Unknown review shape is not positive shared-risk evidence. Multiple independent isolatable anomalies remain multiple local holds. A valid whole-ticker proof must establish unique company/security/provider identity, no collision with safe tickers, an exact valid accepted baseline, deterministic full exclusion, no shared source/schema/mapping dependency and healthy publication/recovery gates. It grants no approval authority.

For diagnostic replay, the archived core locality/publication hunks were reconciled against current source while retaining the committed recovery fix. UI hunks were not applied. The candidate replaced the shape/reason allowlist with generic exclusion proof:

- Bind complete incoming review evidence, including novel fields, without accepting its financial values.
- Re-resolve the exact identity against accepted authorities and check identity collisions across the evaluated operation.
- Check explicit shared-scope/failure evidence and foreign identity mappings, rather than using anomaly count or an unknown reason as globality.
- Validate and fingerprint exact accepted provider/canonical authority and provenance, mark whole-ticker exclusion, and bind the operation identity partition and healthy publication guard.
- Rebuild the same proof during native revalidation; retain the archived exact replacement-set and held-authority candidate checks.

Capture key-state maps were treated as field-presence metadata, not symbol identities: their VALUE/ABSENT/EXPLICIT_NULL enums are not ticker names. This was a diagnostic implementation correction, not a ticker or review-reason exception.

The candidate had no anomaly-count threshold. However, novel-shape unit tests and 10/100-ticker stress tests were **not qualified**, because accepted-baseline verification triggered the task's STOP. The candidate is not an accepted implementation and is not deployed.

## INM and SUPN isolation results

**SUPN: WHOLE_TICKER_ISOLATION PROVEN in read-only diagnostic replay; classification TICKER_LOCAL_REVIEW.** Identity is unique and matches its exact canonical/provider mapping. Accepted provider history contains 41 ARQ and 41 MRQ rows. Full accepted-baseline/provenance validation passed; incoming SUPN can be entirely excluded. Its empty MRQ response does not require a global stop merely because there is no response receipt. No approval eligibility was broadened.

**INM: WHOLE_TICKER_ISOLATION NOT_PROVEN under the full accepted-authority contract; classification GLOBAL_BLOCKING_REVIEW.** Identity itself is unique: company 1133, security 1137, provider security 632554. Accepted provider history contains 28 ARQ and 29 MRQ rows. The failed precondition is not the incoming empty response: canonical quarter 40292, 2026-Q4, has six field-provenance references to missing observation `2b1e4e2df12438ba34783f38ea06250e951795ee84c45d9c71bf904e55d187be`.

The six rows are one `v4_common_earnings_provenance` row and five `v4_operating_working_capital_provenance` rows. These tables bind actual financial fields to source observation IDs. Native `phase12d.reconcile_canonical()` includes their IDs in source-binding consistency and removes/rewrites provenance when the winner changes. Native historical-freeze validation likewise requires coherent source IDs. They are not merely display labels.

INM's 12 primary `v4_field_provenance` rows refer to current observation `29378f9fe87e6ce428e05a61137fb1c73c3b31b70ec364e80c8b13f90ad918ac`. The inspected current primary netinccmn/payables/receivables values equal the accepted canonical values. The old supplemental source ID is nevertheless absent; amount equality does not prove that different source IDs are interchangeable or authorize rewriting recorded provenance. No such rewrite was performed.

## All-current-review replay and positive reasons for remaining globals

The replay streamed the November 11 authoritative ticker changes, retained all review evidence and operation identities, and verified current accepted authorities read-only. All 425 current reviews were evaluated, not just the historical 19 globals.

| Result | Diagnostic replay |
| --- | ---: |
| Effective safe changes | 1,170 |
| Local holds | 408 |
| Accepted-baseline safety blockers | 17 |
| Other non-review entries | 1,222 outside universe + 61 no effective change |

All 19 former globals except INM localized, including SUPN. Sixteen previously local cases failed the stricter accepted-baseline source validation. This produces 406 − 16 + 18 = 408 locals, with 1 + 16 = 17 globals. The partition helper's 2,453 non-review entries are not 2,453 authorized financial replacements. No safe/review identity collision or overlap was observed.

Diagnostic partition fingerprint: `64909a99a0a9c1b8af189043e1a51aeecaf529aeec6dbc18bbaf0602e04bdc61`.

Every remaining global has the explicit reason `ACCEPTED_BASELINE_UNPROVEN:QUARANTINE_ACCEPTED_SOURCE_UNBOUND`. A separate direct SQL check confirmed that each referenced observation below is absent from `provider_observation`, rather than merely absent from a ticker-filtered projection. Each case has six unbound rows in the two supplemental financial-provenance tables.

| Ticker | Quarter ID | Fiscal quarter | Missing provider observation ID |
| --- | ---: | --- | --- |
| ASX | 87986 | 2026-Q2 | `0071e243a6de869236ce821ec755dfdb925283200693190d6fd8f2bb04d089f7` |
| CDT | 15181 | 2026-Q2 | `57fb066bd6ca353dba65c533bfdff84841d82f340938d35be539bab43e10ae57` |
| FLWS | 31097 | 2026-Q4 | `99f6cd7fb768578bfa87613eb5b46c6dcc285ccf5f85d637bbe6ba5fef82e05a` |
| GPMT | 34687 | 2026-Q2 | `acf422446a06804b5933cf1298ac720f25bad5a9e67a2cefad44707804dafc5e` |
| HAIN | 35785 | 2026-Q4 | `e396c06c93be67154abcf82a1f91e4db7a5c34a03d43ec76c0c6f724ce3b42ff` |
| IBEX | 38666 | 2026-Q4 | `3ed1f75a58d17ea19fac5bbb2d10466e310e82bd77904860a877813a7a505f4a` |
| INM | 40292 | 2026-Q4 | `2b1e4e2df12438ba34783f38ea06250e951795ee84c45d9c71bf904e55d187be` |
| IRM | 41285 | 2026-Q2 | `909189e945df492aac8f2bafe4c5930ce16228ccfabe8042503827f2a5e2cddf` |
| LITS | 46445 | 2026-Q4 | `85d2e8ea43afbd426a6ae51acbf61d49715607ba444b838ec762bb06d7bde821` |
| NAMS | 54111 | 2026-Q2 | `277c025345075936150ef91d4b95478ea736198d150a29ac52d2c27cc3802307` |
| NB | 54166 | 2026-Q4 | `81e0972fe529710c4a706d2c8a0d558155bf385ebcec05ce610b27631d6a3d62` |
| NXXT | 57422 | 2026-Q2 | `c94dcff5cb40ae00341ff7f73c5e3a896dbc0ba6fbaf1ad7bff6cabb3419ecfb` |
| REVB | 66844 | 2026-Q2 | `5f4e926e3fa2cd9b6a6fe7c47263b412c170eb6f63fbd6c10d785baf5287baa8` |
| RZLT | 69373 | 2026-Q4 | `047cfdee67772952a922ca746cf45525de9821ab7a01673dc4d0bb790137ba99` |
| SEGG | 70513 | 2026-Q1 | `7477c6b49e7fb5594c28c16923417f5d249e78f67d0586b405ac983954c01927` |
| SKIN | 71577 | 2026-Q2 | `04ffd32b22c2ecb277491674943e6741d9e78ae5b0b0ce4b306cf951426104ad` |
| WHLR | 84703 | 2026-Q2 | `cdbdfd61e1b72dc1cbe7a1da6548704503a9422e0335d521c853227600f6bae4` |

This is the allowed unisolatable-safety exception: the full exact accepted financial source baseline cannot be verified unchanged under the held-authority contract. It is not escalation based on anomaly count, missing receipt, novelty, fiscal interpretation, or an invented cross-ticker acquisition failure. The lifecycle cause of these stale references was not established or repaired in this task.

## Remaining phases and acceptance status

| Requirement | Status |
| --- | --- |
| Minimal recovery reproduction | PASS, 1 test |
| Established recovery / production-parity qualification | PASS, 38 tests |
| Generic unknown-shape / receipt regression suites | NOT RUN after baseline STOP |
| 10 / 100 independent-local stress tests | NOT RUN |
| Native response-level receipt implementation | NOT IMPLEMENTED before STOP |
| Full global/local + preserved-history UI reconciliation | NOT COMPLETED; only core diagnostic hunks were temporarily applied |
| Targeted full review/UI/publication/P/B/WFRD/payload regressions | NOT RUN in this task |
| Disposable A–I combined acceptance | NOT RUN; recovery-only rehearsal is not substituted for combined acceptance |
| Fresh live pre-run gate | NOT ENTERED; final collateral verification performed instead |
| Fresh live Preview / Test / Production | NOT RUN / NOT RUN / NOT RUN |
| Safe / held incoming publications | 0 / 0 |
| Actual replacement-set vs live safe-set qualification | NOT EXERCISED |
| Generation activations by this task | 0 |
| Post-live OLD/NEW recovery metadata sanity | NOT APPLICABLE; no new live publication/journal |
| P/B continuation | NOT RUN; current published state unchanged |
| Actual UI filtering / N/M / HTTP CSV acceptance | NOT RUN; no UI source deployed |

Source capture and receipt verification were not weakened. No normalized plain dictionaries were accepted as new authoritative financial evidence, no receipt was fabricated, and empty/partial responses were not interpreted as deletion or zero. Approval eligibility/authority, held provider/canonical authority, publication dates, WFRD, provider completeness and reevaluation behavior remain unchanged.

## Containment, collateral verification and evidence

Final read-only verification at **2026-11-11T10:31:59.669298Z** matched all seven protected file hashes and sizes to the fresh baseline. Source/tests were restored exactly to current HEAD; the immutable backup mode and pre-prepare binding guard remain present. Existing unrelated OHLCV, runtime and evidence files were not restored, staged or committed.

The deployed saved-Preview classification therefore remains **1,170 safe / 406 local / 19 global**. The **1,170 / 408 / 17** result belongs only to the unqualified read-only diagnostic candidate. N=392 and M=392 are baseline projections, not proof of deployed new filtering or CSV. No new persistence schema or runtime financial generation was created. No production recovery was invoked.

Evidence directory: `temp/fundamentals_single_ticker_rollout_20261111/`:

- `phase_a_runtime.json`, `phase_a_run.json`, `current_globals.json`, `current_identities.json`.
- `recovery_minimal.xml`, `recovery_qualification.xml`.
- `inm_supn_before_fix.json`: four native request/response traces and accepted stored provenance, without credentials.
- `accepted_baseline_findings.json`: exact INM/SUPN/NXXT quarter/provenance checks and current primary-source comparisons.
- `current_replay.json`: final diagnostic proof outcomes and exact safe/held/global sets.
- `baseline_unbound_details.json`: direct SQL evidence for every remaining global's missing source references.
- `unqualified_candidate.patch`, `unqualified_source/`, `source_inventory.json`: stopped diagnostic implementation against current HEAD.
- `final_verification.json`: exact runtime/source containment verification.

The original November 10 implementation archive is unchanged. At the initial STOP, no new commit was created because the required gates did not pass. The user subsequently explicitly requested a commit; this documentation-only commit includes this report and excludes the unqualified implementation, runtime state and temporary evidence. **No push was performed.** Resume requires resolving or independently validating the recorded held-baseline source bindings without silently changing accepted financial authority, followed by the uncompleted receipt/locality, regression, disposable and fresh live gates.
