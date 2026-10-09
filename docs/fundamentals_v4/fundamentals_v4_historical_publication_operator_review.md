# Historical publication operator review — Stage 1

Prepared 2026-10-09. **Awaiting explicit operator confirmation. No approval artifact exists.**

All **85** P1.4 proposals remain stable and approvable across 32 companies; **0** stale/removed. The **514** holds remain excluded (102 period, 13 event, 394 financial, 5 entity/perimeter). No hold was researched, replayed as an approval candidate, or included in the selection.

Proposal fingerprint: `ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657`.

Proposal byte SHA-256: `6ca99cbc6aeb05ec15fd0927a0c008c9f6add54229ed705b0654c81f89891786`.

Approval candidate fingerprint: `5faea82e92b9887b00cea21e227a02860874964036a3caadaac31e1d50d691a6`.

Exact approve-all selection fingerprint: `8bdf27a1a754b36973e7728a1abb582fb5fd4ff1613e3040b597ca1c74d01b14`.

Current-state fingerprint: `601b232eb81ad4d7c3a3427ff0b42a10598b9e4246b5e6b374bf2f7b1f8956ab`.

[Compact review CSV](fundamentals_v4_historical_publication_operator_review.csv) · [Grouped case evidence](fundamentals_v4_historical_publication_operator_review_cases.md) · [Exact unapproved selection manifest](fundamentals_v4_historical_publication_operator_review_candidate.json).

## Meaning of review and approval

The requested action accepts only the exact source-bound event observations as reviewed evidence proposals. It does **not** install authoritative observations, prepare a publication plan, authorize publication, authorize Production apply, mutate authority, mark a case VERIFIED, or activate a generation.

The states remain distinct: PROPOSED → OPERATOR_APPROVED_REVIEW_EVIDENCE requires new explicit human confirmation. PUBLICATION_PLAN_PREPARED → PRODUCTION_PUBLICATION_AUTHORIZED → APPLIED/VERIFIED are separate future stages.

A YES at this gate refers to the displayed exact 85-case selection and fingerprints above. A NO records nothing. To choose a subset, identify natural keys as company ID / fiscal year / fiscal quarter and mark APPROVE, HOLD, or REJECT. Omitted cases remain unreviewed and unapproved. A changed selection must be displayed with its own fingerprint and explicitly confirmed before recording anything.

## Current baseline and exact stability

Baseline HEAD: `1b97795f44c518729248e961e8a2e796486d3536`. The pre-existing worktree changes were the publication journal plus untracked active-generation files and unrelated PE research outputs; all remain excluded from this commit.

Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.

Provider watermark: `2026-10-08`. Latest successful normal Fundamentals Production run: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`; provider completion `2026-10-09T04:27:27Z`.

Journal: COMPLETED / COMPLETED; activation ACTIVATED_AND_VERIFIED; postflight PASSED; recovery NOT_REQUIRED; updated `2026-10-09T04:37:11Z`.

Authority census: VERIFIED 12,890; NOT_FOUND 1,882; UNRESOLVED 842; AMBIGUOUS 628. Whole-authority logical fingerprint: `41e710eb4dca4418d48e403fde8c70777efa1c02be24cb48e7eb3a6a4ccce577`. All 85 remain open with zero durable candidate evidence. No publication candidate was inserted.

Review Queue: six RESOLVED refresh rows, 38 audit rows, zero ownership reviews; unchanged, with no matching publication-review approval. Existing queue actions concern retained history, fiscal revision, source removal, or ownership. Reusing them would assign incorrect semantics or introduce queue mutations, so this workflow uses a bounded docs-only receipt helper instead of a UI extension.

For each of the 85 keys, current accepted canonical quarter, complete quarter row, authority row, company/CIK/security chain, structural identity context and durable evidence inventory were compared with the P1.4 frozen state. All match. Full current open-quarter scopes for the 32 companies were replayed against their retained complete official filing captures to detect competing contexts; selected evidence payloads, accession, timestamp, form, primary document, reference and resolver contexts match exactly. No P1.2 timestamp tolerance was needed.

The proposal fingerprint and recorded byte hash reproduce. The retained P1.4 review-input file and frozen-baseline semantic fingerprint also reproduce. Policy/resolver source and known reviewed-observation/relation inputs match the proposal-bound hashes. No new reviewed exclusion or precedence relation exists in those inputs; no implicit global reviewed-input discovery was introduced.

All **595** exact excerpt locators reproduce from retained raw HTML through `result_publication.filing_text`, including raw-source SHA-256, extracted-text SHA-256, Unicode offsets, literal text and excerpt SHA-256. The seven evidence dimensions are grouped inside each case below. Copy-only current-scope Policy V1 replay returns **85 UNIQUE** with the proposed observations and **85 REVIEW** without observations. These previews confer no human approval.

This revalidation uses the already-retained official captures dated 2026-10-09 and the unchanged current Production state. Network acquisitions: zero. It does not assert that an independent new SEC crawl occurred. Any changed/missing source, review input, current-state binding or competing context at Stage 2 must block recording and require a fresh candidate summary. Changed cases are classified STALE_PROPOSAL_REVIEW_REQUIRED; none occurred here.

Cautions retained from P1.4: all 85 active security records lack valid_from; issuer/perimeter proofs use the exact registrant and linked result release. Six cases use additional already-retained official same-accession exhibit HTML beyond the frozen resolver exhibit list. Those source documents have explicit hashes and excerpt locators; resolver context and policy remain unchanged. All 85 financial proofs use linked result exhibits; parent-only proofs: zero.

## Bounded approval mechanism

Source: `rawcandle/fundamentals/admin/publication_observation_approval.py`.

`prepare_candidate` compares caller-reproduced baseline/current snapshots, excludes stale cases, and fingerprints the exact stable bindings and current global state. It is not a source adjudicator: callers must first reproduce sources and Policy V1. `select_cases` supports exact APPROVE/HOLD/REJECT membership and explicit approve-all selection, rejecting unknown, duplicate, overlapping or stale keys. Merely creating a candidate or selection records no approval.

Only after a new explicit YES, `make_approval` requires an independently revalidated identical current candidate, the exact confirmed selection fingerprint, explicit confirmation, operator identity, note and UTC timestamp. Changed state or selection blocks the operation. Human identity will be recorded as supplied, or as an interactive user confirmation without inventing a personal identity.

`write_approval` writes exclusively to `docs/fundamentals_v4/review_approvals/historical_publication_review_approval_v1.<artifact_fingerprint>.json` with exclusive creation; an existing artifact cannot be overwritten. Redirected destination symlinks are rejected. Nothing has been written there in Stage 1.

The immutable envelope binds rule/version, proposal fingerprint/path, proposal-baseline authority fingerprint, current generation, current-state/candidate/selection fingerprints, exact approved natural keys and observation/evidence/context/source fingerprints, operator, note and approval timestamp. HOLD/REJECT/unreviewed membership remains explicit. Original proposal-binding flags inside approved_cases remain unchanged as provenance; the receipt's OPERATOR_APPROVED_REVIEW_EVIDENCE state records the human decision.

Its fixed flags are `runtime_use_permitted=false`, `publication_authorized=false`, `production_apply_authorized=false`, and `authority_mutation_authorized=false`. It has no Production plan schema or root reviewed-input cases, and existing Production plan validation rejects both proposal and receipt. Scheduler, refresh, resolver, backlog worker and reviewed-plan consumers have no reference to this helper or docs destination. No runtime discovery or handoff was added.

For Stage 2, independently repeat the baseline hashes, snapshot/source proofs, current-company competition replay and candidate calculation before calling the helper. Compare with the committed candidate and selection manifest; do not use the saved candidate as the purported fresh current candidate. If anything changes during the pause, stop and present a new review summary. Local audit scripts/snapshots are retained under `/tmp/publication_operator_p15/`, with P1.4 proof inputs under `/tmp/publication_observation_p14/` and retained captures under `/tmp/historical_publication_p11/sec/`. Missing local inputs must fail closed, never bypass revalidation.

## Validation and Production invariance

Focused approval tests: **25 passed** (`tests/test_publication_observation_approval.py`). Directly relevant reviewed-publication regression group: **25 passed** (`tests/test_policy_reviewed_publication_plan.py`). Initial focused test failures were test assertions (HOLD field spelling and an overly broad consumer substring); corrected focused group passes. Full suite: **not run**.

Tests cover grouped review rendering, exact/partial/all selection, omissions, holds/rejections, stale evidence/quarter/competition/source/policy rejection, changed proposal/current-generation/selection rejection, explicit confirmation, immutable versioned output, redirected paths, non-executing flags, rejection by Production plan validation, and absence of scheduler/worker integration. Synthetic test receipts are confined to pytest temporary repositories; no real receipt was created.

Deterministic assertions: byte-identical review CSV/case report/candidate manifest on repeated preparation; 85 stable / 0 stale / 514 excluded reconciliation; 595 exact source proofs; Policy V1 control/review replay; unchanged protected Production files, prior reports, source contracts and pre-existing SQLite sidecars. No new sidecars were introduced.

Authoritative observations, authority, all financial DBs, active generation, Review Queue, publication journal, schedulers, provider watermark, resolver and Policy V1: **unchanged**. No worker, drain, apply, Production-plan preparation or generation activation was invoked. No approval artifact was created. No push.

Protected file SHA-256 values (identical before/after):

| Role | SHA-256 |
| --- | --- |
| provider | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| canonical | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| analysis | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| pointer | `30c08f22b5b9b2a3cbb07f5183d2946e3ed8b980634d0e54255936b9310b5de3` |
| queue | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| queue-wal | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| queue-shm | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` |
| journal | `6f7e625fe10c0ab98c31902bb34d4e7a0c24ea2c94b840497b0459a07817aa67` |
| scheduler | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| forecast_scheduler | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |

## Operator index

Each link opens the grouped source evidence for that exact natural key. All rows are STABLE_APPROVABLE, still PROPOSED. The CSV additionally provides complete exact evidence/context/observation fingerprints.

| Ticker / company | Natural key | Period end | Accession | Source time UTC |
| --- | --- | --- | --- | --- |
| [ACA / ACA](fundamentals_v4_historical_publication_operator_review_cases.md#case-22-2025-Q1) | 22/2025/Q1 | 2025-03-31 | 0001739445-25-000065 | 2025-05-06T20:20:08Z |
| [ACA / ACA](fundamentals_v4_historical_publication_operator_review_cases.md#case-22-2025-Q2) | 22/2025/Q2 | 2025-06-30 | 0001739445-25-000113 | 2025-08-07T20:37:22Z |
| [ACA / ACA](fundamentals_v4_historical_publication_operator_review_cases.md#case-22-2026-Q1) | 22/2026/Q1 | 2026-03-31 | 0001739445-26-000064 | 2026-04-30T20:22:00Z |
| [ACA / ACA](fundamentals_v4_historical_publication_operator_review_cases.md#case-22-2026-Q2) | 22/2026/Q2 | 2026-06-30 | 0001739445-26-000124 | 2026-08-05T20:19:02Z |
| [ACIW / ACIW](fundamentals_v4_historical_publication_operator_review_cases.md#case-31-2026-Q2) | 31/2026/Q2 | 2026-06-30 | 0000935036-26-000026 | 2026-08-06T12:04:28Z |
| [APOG / APOG](fundamentals_v4_historical_publication_operator_review_cases.md#case-176-2026-Q4) | 176/2026/Q4 | 2026-02-28 | 0000006845-26-000020 | 2026-04-24T17:05:11Z |
| [BL / BL](fundamentals_v4_historical_publication_operator_review_cases.md#case-330-2025-Q1) | 330/2025/Q1 | 2025-03-31 | 0001171843-25-002819 | 2025-05-06T20:06:01Z |
| [BL / BL](fundamentals_v4_historical_publication_operator_review_cases.md#case-330-2025-Q2) | 330/2025/Q2 | 2025-06-30 | 0001171843-25-005050 | 2025-08-05T20:06:42Z |
| [BL / BL](fundamentals_v4_historical_publication_operator_review_cases.md#case-330-2025-Q3) | 330/2025/Q3 | 2025-09-30 | 0001171843-25-007093 | 2025-11-06T21:07:26Z |
| [BL / BL](fundamentals_v4_historical_publication_operator_review_cases.md#case-330-2025-Q4) | 330/2025/Q4 | 2025-12-31 | 0001171843-26-000734 | 2026-02-10T21:05:28Z |
| [BL / BL](fundamentals_v4_historical_publication_operator_review_cases.md#case-330-2026-Q1) | 330/2026/Q1 | 2026-03-31 | 0001171843-26-003023 | 2026-05-05T20:05:34Z |
| [BL / BL](fundamentals_v4_historical_publication_operator_review_cases.md#case-330-2026-Q2) | 330/2026/Q2 | 2026-06-30 | 0001171843-26-005201 | 2026-08-04T20:05:29Z |
| [BRC / BRC](fundamentals_v4_historical_publication_operator_review_cases.md#case-358-2025-Q1) | 358/2025/Q1 | 2024-10-31 | 0000746598-24-000137 | 2024-11-18T17:05:24Z |
| [BRC / BRC](fundamentals_v4_historical_publication_operator_review_cases.md#case-358-2025-Q2) | 358/2025/Q2 | 2025-01-31 | 0000746598-25-000007 | 2025-02-21T17:06:17Z |
| [BRC / BRC](fundamentals_v4_historical_publication_operator_review_cases.md#case-358-2026-Q1) | 358/2026/Q1 | 2025-10-31 | 0000746598-25-000059 | 2025-11-17T17:15:33Z |
| [BRC / BRC](fundamentals_v4_historical_publication_operator_review_cases.md#case-358-2026-Q2) | 358/2026/Q2 | 2026-01-31 | 0000746598-26-000005 | 2026-02-19T17:05:23Z |
| [CCLD / CCLD](fundamentals_v4_historical_publication_operator_review_cases.md#case-421-2025-Q2) | 421/2025/Q2 | 2025-06-30 | 0001493152-25-011596 | 2025-08-05T15:05:48Z |
| [CGNX / CGNX](fundamentals_v4_historical_publication_operator_review_cases.md#case-451-2026-Q2) | 451/2026/Q2 | 2026-07-05 | 0000851205-26-000061 | 2026-08-05T20:32:16Z |
| [COHR / COHR](fundamentals_v4_historical_publication_operator_review_cases.md#case-524-2025-Q1) | 524/2025/Q1 | 2024-09-30 | 0001193125-24-252062 | 2024-11-07T02:20:03Z |
| [COHR / COHR](fundamentals_v4_historical_publication_operator_review_cases.md#case-524-2025-Q2) | 524/2025/Q2 | 2024-12-31 | 0001193125-25-020821 | 2025-02-06T02:05:24Z |
| [COHR / COHR](fundamentals_v4_historical_publication_operator_review_cases.md#case-524-2025-Q3) | 524/2025/Q3 | 2025-03-31 | 0001193125-25-114882 | 2025-05-08T00:05:27Z |
| [CTXR / CTXR](fundamentals_v4_historical_publication_operator_review_cases.md#case-602-2026-Q1) | 602/2026/Q1 | 2025-12-31 | 0001213900-26-015895 | 2026-02-13T13:30:27Z |
| [DAN / DAN](fundamentals_v4_historical_publication_operator_review_cases.md#case-636-2026-Q2) | 636/2026/Q2 | 2026-06-30 | 0001193125-26-336664 | 2026-08-06T11:00:22Z |
| [DOCS / DOCS](fundamentals_v4_historical_publication_operator_review_cases.md#case-697-2027-Q1) | 697/2027/Q1 | 2026-06-30 | 0001516513-26-000038 | 2026-08-07T00:04:42Z |
| [EPC / EPC](fundamentals_v4_historical_publication_operator_review_cases.md#case-780-2025-Q2) | 780/2025/Q2 | 2025-03-31 | 0001628280-25-022844 | 2025-05-07T10:06:10Z |
| [EPC / EPC](fundamentals_v4_historical_publication_operator_review_cases.md#case-780-2025-Q3) | 780/2025/Q3 | 2025-06-30 | 0001628280-25-037579 | 2025-08-05T10:11:29Z |
| [EPC / EPC](fundamentals_v4_historical_publication_operator_review_cases.md#case-780-2026-Q3) | 780/2026/Q3 | 2026-06-30 | 0001628280-26-052881 | 2026-08-05T10:10:48Z |
| [FAST / FAST](fundamentals_v4_historical_publication_operator_review_cases.md#case-835-2026-Q2) | 835/2026/Q2 | 2026-06-30 | 0000815556-26-000037 | 2026-07-14T12:01:18Z |
| [HTO / HTO](fundamentals_v4_historical_publication_operator_review_cases.md#case-1067-2025-Q1) | 1067/2025/Q1 | 2025-03-31 | 0000766829-25-000035 | 2025-04-28T21:15:50Z |
| [IEX / IEX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1103-2025-Q3) | 1103/2025/Q3 | 2025-09-30 | 0001628280-25-046909 | 2025-10-29T11:08:27Z |
| [MELI / MELI](fundamentals_v4_historical_publication_operator_review_cases.md#case-1404-2025-Q1) | 1404/2025/Q1 | 2025-03-31 | 0001099590-25-000025 | 2025-05-07T20:01:57Z |
| [MELI / MELI](fundamentals_v4_historical_publication_operator_review_cases.md#case-1404-2025-Q2) | 1404/2025/Q2 | 2025-06-30 | 0001099590-25-000041 | 2025-08-04T20:01:19Z |
| [MELI / MELI](fundamentals_v4_historical_publication_operator_review_cases.md#case-1404-2026-Q1) | 1404/2026/Q1 | 2026-03-31 | 0001099590-26-000014 | 2026-05-07T20:00:57Z |
| [MELI / MELI](fundamentals_v4_historical_publication_operator_review_cases.md#case-1404-2026-Q2) | 1404/2026/Q2 | 2026-06-30 | 0001099590-26-000021 | 2026-08-05T20:00:58Z |
| [MNKD / MNKD](fundamentals_v4_historical_publication_operator_review_cases.md#case-1443-2025-Q1) | 1443/2025/Q1 | 2025-03-31 | 0000950170-25-066426 | 2025-05-08T12:08:08Z |
| [MPAA / MPAA](fundamentals_v4_historical_publication_operator_review_cases.md#case-1457-2025-Q1) | 1457/2025/Q1 | 2024-06-30 | 0001140361-24-036287 | 2024-08-08T11:59:11Z |
| [MPAA / MPAA](fundamentals_v4_historical_publication_operator_review_cases.md#case-1457-2025-Q2) | 1457/2025/Q2 | 2024-09-30 | 0001140361-24-046024 | 2024-11-12T12:58:16Z |
| [MPAA / MPAA](fundamentals_v4_historical_publication_operator_review_cases.md#case-1457-2025-Q3) | 1457/2025/Q3 | 2024-12-31 | 0001140361-25-003643 | 2025-02-10T12:58:17Z |
| [MTRX / MTRX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1487-2025-Q1) | 1487/2025/Q1 | 2024-09-30 | 0000866273-24-000112 | 2024-11-06T21:17:26Z |
| [MTRX / MTRX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1487-2025-Q2) | 1487/2025/Q2 | 2024-12-31 | 0000866273-25-000013 | 2025-02-05T21:40:10Z |
| [MTRX / MTRX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1487-2025-Q3) | 1487/2025/Q3 | 2025-03-31 | 0000866273-25-000027 | 2025-05-07T20:13:36Z |
| [MTRX / MTRX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1487-2025-Q4) | 1487/2025/Q4 | 2025-06-30 | 0000866273-25-000066 | 2025-09-09T20:19:50Z |
| [MTRX / MTRX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1487-2026-Q1) | 1487/2026/Q1 | 2025-09-30 | 0000866273-25-000098 | 2025-11-05T21:53:49Z |
| [MTRX / MTRX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1487-2026-Q2) | 1487/2026/Q2 | 2025-12-31 | 0000866273-26-000012 | 2026-02-04T21:50:17Z |
| [NX / NX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1602-2025-Q2) | 1602/2025/Q2 | 2025-04-30 | 0001171843-25-003726 | 2025-06-06T00:17:35Z |
| [NX / NX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1602-2025-Q4) | 1602/2025/Q4 | 2025-10-31 | 0001171843-25-007891 | 2025-12-12T02:17:27Z |
| [NX / NX](fundamentals_v4_historical_publication_operator_review_cases.md#case-1602-2026-Q1) | 1602/2026/Q1 | 2026-01-31 | 0001171843-26-001364 | 2026-03-06T02:17:28Z |
| [PPC / PPC](fundamentals_v4_historical_publication_operator_review_cases.md#case-1772-2025-Q1) | 1772/2025/Q1 | 2025-03-30 | 0000802481-25-000059 | 2025-04-30T22:52:27Z |
| [PPC / PPC](fundamentals_v4_historical_publication_operator_review_cases.md#case-1772-2025-Q2) | 1772/2025/Q2 | 2025-06-29 | 0000802481-25-000108 | 2025-07-30T22:27:49Z |
| [QCOM / QCOM](fundamentals_v4_historical_publication_operator_review_cases.md#case-1826-2025-Q1) | 1826/2025/Q1 | 2024-12-29 | 0000804328-25-000010 | 2025-02-05T21:04:42Z |
| [QCOM / QCOM](fundamentals_v4_historical_publication_operator_review_cases.md#case-1826-2025-Q2) | 1826/2025/Q2 | 2025-03-30 | 0000804328-25-000029 | 2025-04-30T20:04:10Z |
| [QCOM / QCOM](fundamentals_v4_historical_publication_operator_review_cases.md#case-1826-2026-Q1) | 1826/2026/Q1 | 2025-12-28 | 0000804328-26-000016 | 2026-02-04T21:00:59Z |
| [QCOM / QCOM](fundamentals_v4_historical_publication_operator_review_cases.md#case-1826-2026-Q2) | 1826/2026/Q2 | 2026-03-29 | 0000804328-26-000060 | 2026-04-29T20:02:20Z |
| [QCOM / QCOM](fundamentals_v4_historical_publication_operator_review_cases.md#case-1826-2026-Q3) | 1826/2026/Q3 | 2026-06-28 | 0000804328-26-000085 | 2026-07-29T20:01:35Z |
| [RDW / RDW](fundamentals_v4_historical_publication_operator_review_cases.md#case-1861-2026-Q2) | 1861/2026/Q2 | 2026-06-30 | 0001819810-26-000121 | 2026-08-06T00:28:41Z |
| [RRR / RRR](fundamentals_v4_historical_publication_operator_review_cases.md#case-1923-2025-Q1) | 1923/2025/Q1 | 2025-03-31 | 0001193125-25-109965 | 2025-05-01T20:10:06Z |
| [RRR / RRR](fundamentals_v4_historical_publication_operator_review_cases.md#case-1923-2025-Q2) | 1923/2025/Q2 | 2025-06-30 | 0001193125-25-167977 | 2025-07-29T20:01:29Z |
| [RRR / RRR](fundamentals_v4_historical_publication_operator_review_cases.md#case-1923-2025-Q3) | 1923/2025/Q3 | 2025-09-30 | 0001193125-25-253457 | 2025-10-28T20:01:12Z |
| [RRR / RRR](fundamentals_v4_historical_publication_operator_review_cases.md#case-1923-2025-Q4) | 1923/2025/Q4 | 2025-12-31 | 0001193125-26-044612 | 2026-02-10T21:01:18Z |
| [SOLV / SOLV](fundamentals_v4_historical_publication_operator_review_cases.md#case-2050-2025-Q1) | 2050/2025/Q1 | 2025-03-31 | 0001964738-25-000049 | 2025-05-08T20:13:51Z |
| [SOLV / SOLV](fundamentals_v4_historical_publication_operator_review_cases.md#case-2050-2025-Q2) | 2050/2025/Q2 | 2025-06-30 | 0001964738-25-000062 | 2025-08-07T20:12:27Z |
| [SOLV / SOLV](fundamentals_v4_historical_publication_operator_review_cases.md#case-2050-2025-Q3) | 2050/2025/Q3 | 2025-09-30 | 0001964738-25-000089 | 2025-11-06T21:11:32Z |
| [SOLV / SOLV](fundamentals_v4_historical_publication_operator_review_cases.md#case-2050-2025-Q4) | 2050/2025/Q4 | 2025-12-31 | 0001964738-26-000005 | 2026-02-26T21:08:05Z |
| [SOLV / SOLV](fundamentals_v4_historical_publication_operator_review_cases.md#case-2050-2026-Q1) | 2050/2026/Q1 | 2026-03-31 | 0001964738-26-000022 | 2026-05-05T20:08:36Z |
| [SOLV / SOLV](fundamentals_v4_historical_publication_operator_review_cases.md#case-2050-2026-Q2) | 2050/2026/Q2 | 2026-06-30 | 0001964738-26-000045 | 2026-08-05T20:17:48Z |
| [SWBI / SWBI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2110-2025-Q2) | 2110/2025/Q2 | 2024-10-31 | 0001193125-24-271518 | 2024-12-05T21:08:32Z |
| [SWBI / SWBI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2110-2025-Q3) | 2110/2025/Q3 | 2025-01-31 | 0001193125-25-048413 | 2025-03-06T21:05:38Z |
| [SWBI / SWBI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2110-2025-Q4) | 2110/2025/Q4 | 2025-04-30 | 0001193125-25-142704 | 2025-06-18T20:05:38Z |
| [SWBI / SWBI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2110-2026-Q1) | 2110/2026/Q1 | 2025-07-31 | 0001193125-25-196031 | 2025-09-04T20:06:24Z |
| [SWBI / SWBI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2110-2026-Q3) | 2110/2026/Q3 | 2026-01-31 | 0001193125-26-093923 | 2026-03-05T21:05:58Z |
| [TBCH / TBCH](fundamentals_v4_historical_publication_operator_review_cases.md#case-2131-2025-Q4) | 2131/2025/Q4 | 2025-12-31 | 0001193125-26-104292 | 2026-03-12T20:35:25Z |
| [TBCH / TBCH](fundamentals_v4_historical_publication_operator_review_cases.md#case-2131-2026-Q2) | 2131/2026/Q2 | 2026-06-30 | 0001193125-26-338051 | 2026-08-06T20:15:24Z |
| [TNC / TNC](fundamentals_v4_historical_publication_operator_review_cases.md#case-2180-2025-Q1) | 2180/2025/Q1 | 2025-03-31 | 0000097134-25-000011 | 2025-04-30T20:46:34Z |
| [TNC / TNC](fundamentals_v4_historical_publication_operator_review_cases.md#case-2180-2025-Q2) | 2180/2025/Q2 | 2025-06-30 | 0000097134-25-000024 | 2025-08-06T20:39:24Z |
| [TNC / TNC](fundamentals_v4_historical_publication_operator_review_cases.md#case-2180-2025-Q3) | 2180/2025/Q3 | 2025-09-30 | 0000097134-25-000034 | 2025-11-03T21:19:11Z |
| [TNC / TNC](fundamentals_v4_historical_publication_operator_review_cases.md#case-2180-2026-Q1) | 2180/2026/Q1 | 2026-03-31 | 0000097134-26-000012 | 2026-05-04T20:57:59Z |
| [TNC / TNC](fundamentals_v4_historical_publication_operator_review_cases.md#case-2180-2026-Q2) | 2180/2026/Q2 | 2026-06-30 | 0000097134-26-000022 | 2026-08-05T22:41:48Z |
| [UTI / UTI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2283-2025-Q1) | 2283/2025/Q1 | 2024-12-31 | 0001261654-25-000003 | 2025-02-05T21:10:20Z |
| [VPG / VPG](fundamentals_v4_historical_publication_operator_review_cases.md#case-2321-2025-Q4) | 2321/2025/Q4 | 2025-12-31 | 0001437749-26-003697 | 2026-02-11T11:20:35Z |
| [WST / WST](fundamentals_v4_historical_publication_operator_review_cases.md#case-2400-2026-Q1) | 2400/2026/Q1 | 2026-03-31 | 0000105770-26-000047 | 2026-04-23T11:11:01Z |
| [WST / WST](fundamentals_v4_historical_publication_operator_review_cases.md#case-2400-2026-Q2) | 2400/2026/Q2 | 2026-06-30 | 0000105770-26-000097 | 2026-07-23T11:14:59Z |
| [YETI / YETI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2435-2025-Q1) | 2435/2025/Q1 | 2025-03-29 | 0001670592-25-000022 | 2025-05-08T10:10:15Z |
| [YETI / YETI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2435-2025-Q2) | 2435/2025/Q2 | 2025-06-28 | 0001670592-25-000038 | 2025-08-07T10:04:51Z |
| [YETI / YETI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2435-2025-Q3) | 2435/2025/Q3 | 2025-09-27 | 0001670592-25-000046 | 2025-11-06T11:03:29Z |
| [YETI / YETI](fundamentals_v4_historical_publication_operator_review_cases.md#case-2435-2025-Q4) | 2435/2025/Q4 | 2026-01-03 | 0001670592-26-000004 | 2026-02-19T11:08:48Z |

## Next phase

First await explicit operator confirmation of this exact selection. After YES, independently revalidate and record only one immutable non-executing receipt in a separate commit. A subsequent separately scoped phase must re-establish current state and design exact-evidence handoff into the existing reviewed publication-plan mechanism. No publication is authorized by this review.
