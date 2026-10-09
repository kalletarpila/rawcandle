# P1.7 — Historical publication Production execution

Production publication completed through the existing reviewed-plan machinery for exactly 85 approved natural keys. All 85 transitioned to VERIFIED using their approved evidence, accession and timestamp. No context-only or nonmember authority/evidence row changed. Financial data and provider/analysis bytes are unchanged.

## Authorization and exact scope

The operator explicitly replied **YES** to the Stage 1 exact-plan/current-generation Production authorization question. Prior P1.5 evidence approval was not used as execution consent. Authorization was recorded at `2026-10-09T17:51:33Z` for interactive user identity only; no personal identity was inferred.

Authorization fingerprint: `1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d`. Immutable receipt: [historical_publication_execution_authorization_v1.1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d.json](review_execution_authorizations/historical_publication_execution_authorization_v1.1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d.json).

Plan fingerprint: `f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70`. Exact plan file SHA-256: `6c6d05c835ce6c286ff37583aab966f6f2d9f4c92d46aaa16ce970ae1ab150d2`. [Immutable plan](reviewed_publication_plans/historical_publication_policy_plan_v3.f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70.json).

Handoff fingerprint: `289eca58761068d8106ca628db65fe3454aa1dc16f178f7bfb975f67ce6a5d81`; P1.5 evidence approval fingerprint: `0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651`; P1.4 proposal fingerprint: `ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657`.

Exact writable count: **85**. Membership fingerprint: `deeb4247ea48ab89c76f22ea1de78d1437a9a4de726172fda5ecbfa30a502234`. Context-only count: **116**, excluded from writes. The 514 original holds, all other backlog keys and future plans are excluded.

The existing execution authorization mechanism is the explicit `confirm_production=True` gate combined with a validated `reviewed_apply_plan` and durable journal `scope_evidence`. The separate immutable receipt records the operator confirmation and exact generation/manifest/membership bindings as an audit artifact; it adds no alternative executor or runtime discovery. The original plan remains byte-identical with its original false authorization/executed fields; the separate receipt records this execution consent. The P1.5 evidence approval remains unchanged.

## Fresh baseline and preflight

Starting HEAD: `a4145e73f54f0169e925000af91bdebd49ea9a24`. Initial unrelated dirty journal, generation pointer/directory and PE research files are excluded from the documentation commit. Pre-execution generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`; manifest fingerprint: `0cc331f59dfefbf58adb09d8467048e392e95dda24cbe3cb1ac3d54fe8debc3f`.

Stage 1 validation completed at `2026-10-09T16:46:20.878681+00:00`. After YES, all protected file byte hashes/sizes, HEAD, generation/manifest, clean terminal journal, immutable plan/handoff/receipt/proposal, exact open membership, quarter/evidence/identity/perimeter/full resolver context and live semantic inputs were checked again. The current-state check was repeated after collecting read-only logical baselines and immediately before recording authorization and entering the existing executor. All passed; no binding changed during the consent pause.

Provider watermark remained `2026-10-08`; the last normal successful Fundamentals refresh remains `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`, completed `2026-10-09T04:27:27Z`. Review Queue remains 6 RESOLVED refresh rows, 38 audit rows and 0 ownership rows; existing queue WAL/SHM bytes are unchanged. Stage 1 protected hashes prove that snapshot; the postflight protected-file checks prove preservation.

No source changed since P1.6B. No large test group or full suite was repeated. Exact plan validation and fresh current-state revalidation were run before authorization, after YES and again by the existing executor under its writer lock.

## Existing publication transaction

Operation: `publication_drain_20261009T175136Z_e99387cf`. [Existing operation report](/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/result.json).

The existing `run_backlog_drain(project_root=repo, apply=True, confirm_production=True, reviewed_apply_plan=exact_plan_path)` acquired the admin Production lock and scheduler lock, checked journal/recovery fences, loaded the same immutable plan again and revalidated exact scope under lock. It copied the complete old generation into its established candidate lane, and invoked the existing reviewed Policy V1 candidate path. Candidate execution revalidated the entire cohort before its first writer and used the existing `apply_resolution`. Every candidate result was checked for the exact key, selected evidence, source and timestamp. The plan is all-or-nothing: any candidate/validation failure prevents activation; ordinary post-journal failures use existing restore-old recovery. No ad hoc SQL update or parallel execution path was used.

The existing path verified all source roles, required free disk space and lack of source SQLite sidecars, preserved provider/analysis bytes, produced the three required verified backups, and durably journaled PREPARED before generation construction/activation. It constructed the complete new immutable generation, activated its pointer atomically, verified all active role hashes/SQLite checks and marked the journal terminal COMPLETED. No refresh, scoring, RP/RV, P/B, taxonomy or forecast operation was run.

Post-execution active generation: `publication_drain_20261009T175136Z_e99387cf`. Manifest fingerprint: `ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a`. Journal: **COMPLETED**; activation: **ACTIVATED_AND_VERIFIED**; postflight: **PASSED**; rollback/recovery: **NOT_REQUIRED**.

## Exact results and backlog impact

| Measure | Result |
|---|---:|
| Planned / VERIFIED | 85 / 85 |
| Failed / held | 0 |
| Context-only quarters changed | 0 |
| Nonmember authority rows changed | 0 |
| Nonmember evidence rows changed | 0 |
| Exact approved accession/timestamp/source/evidence parity | PASS |

[Exact before/after result CSV](fundamentals_v4_historical_publication_p17_results.csv) records every natural key, quarter ID, prior/new authority status, selected evidence, approved accession/time/source, evidence fingerprint, authority fingerprints and verification time.

| Authority status | Before | After | Delta |
|---|---:|---:|---:|
| VERIFIED | 12890 | 12975 | +85 |
| UNRESOLVED | 842 | 769 | -73 |
| NOT_FOUND | 1882 | 1870 | -12 |
| AMBIGUOUS | 628 | 628 | +0 |
| Total open | 3352 | 3267 | -85 |

Historical open after execution: **3115**; recent open: **152**. Historical uses the established 60-day partition: context date `max(first_public_result_date, source_availability_date)` outside `2026-08-10` through `2026-10-09` inclusive. No remaining backlog case was processed.

## Postflight invariants

All planned quarters/company/security/CIK rows remain unchanged. All 116 context-only state/evidence inventories match pre-authorization values. Complete canonical logical digests match for every nonpublication table and for all nonmember authority/evidence rows. Provider/analysis roles are byte-identical to their old immutable sources, which proves their financial contents and outputs unchanged. The old complete generation is unchanged. Proposal, approval, handoff, plan and live semantic sources retain their exact protected byte hashes. Scheduler configuration, Review Queue and watermark are unchanged.

| Active role | SHA-256 |
|---|---|
| analysis | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| canonical | `a67c996aadfaa7e600b88d6d9e31804bb30a784b182ff37ae23c8756ff949c34` |
| provider | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |

The following before/after logical digests are identical; only the 85 writable publication keys are excluded from the two publication tables.

| Logical table | Rows | SHA-256 before and after |
|---|---:|---|
| `company` | 2547 | `696692857c70a99b60abdb66fcc5dafc4caf401013a48b3671c75ef8fc0d392f` |
| `company_cik` | 2542 | `09425b2fb47e1f68dcd2fd807be0f9ddf43a8c950ca41dd50e3fd438444e6f09` |
| `company_fiscal_calendar_profile` | 2458 | `9ed5e69331d3f290ed69d9bbd4ec9766b90fd7d5736c9663d79c44c614729184` |
| `company_fiscal_year_anchor` | 35245 | `58001cd6900f114d6cdf5c379e1fa3fd1f11a2ab3f33668c5c507106f022c4da` |
| `fundamentals_economic_structural_event` | 5 | `3005b54a71dc43f022a0932a34dbc615641d70338ed41087b1d0c425e0c05a31` |
| `fundamentals_operational_universe_active_version` | 1 | `9ce28b228430489d5553d5efc739fb8d44809c055b0c2e2b5712c8c76566c3b8` |
| `fundamentals_operational_universe_member` | 12313 | `13708e571f83d3ce1a1bae55ee033ece493f7b60e85ca57019f989789ec16d68` |
| `fundamentals_operational_universe_member_alias` | 12428 | `718bb2d6cd35825e30caca15649a06e790cf987b168d98f56ea230db93e76180` |
| `fundamentals_operational_universe_schema_meta` | 1 | `a89bb6bdb0ea789e83400bf384b429a234a0591538268825208c611c0e642b89` |
| `fundamentals_operational_universe_version` | 5 | `e6cc8dccfef4e1b817013e3d1f00169d088e961183bb1017431d07e8965799e0` |
| `fundamentals_quarter_economic_regime` | 197 | `909ab36f625f5d5732c5908fde48545b82f6c5a76441c0afe81fc0728575b73b` |
| `fundamentals_ttm_economic_regime` | 197 | `5f3d5a24ef5b778af2002a541d1367cd937816cc68c44771dbb0ac35a8aaed06` |
| `phase13g2_applied_plan` | 8 | `e15760b465b0f5c681164812ea2ec0e14d1b38a03a98fbc4c2636a3aa265be83` |
| `provider_company_identity` | 2527 | `d267b68b970c418b270deebbe3ec8a96d0f977d336883936b31463e83d4d5211` |
| `provider_security_identity` | 2557 | `4d854760e94bcfb385c6c37d2ad6d1930692b85b05696e2b91e63a0c5d660022` |
| `schema_version` | 1 | `f891d6796f9cf95d3d03634b6284be7b61c6b2ad3f88add4ec81888f47271116` |
| `security` | 2560 | `321a9827c392913141aff110d1d147b55319cde228301f00f2fc8d615978f06e` |
| `ticker_alias` | 2575 | `eebdace181ce44e4be678f89f0c3f278c5234b306d13775dc7d12484c41b5376` |
| `v4_common_earnings_provenance` | 88662 | `979ee3b43b609330e172a6449caeb2b404c85fdabb526af2db742181e6a2d766` |
| `v4_field_provenance` | 1065776 | `44e8cdb8055fe4dac128fb3faa6a1cd76d135eacb46142bb929a18368d83267a` |
| `v4_operating_working_capital_provenance` | 449615 | `e778f555e631585eb54c77ff07620da25e094eefd97f785aca079d8d0ef07698` |
| `v4_parent_equity_provenance` | 170290 | `8268c093fa53135a2371cad96ee1fd0144c054c746376144da8653c7986a1303` |
| `v4_parent_equity_source` | 89924 | `bbf4356daf51552b91f9fa1d36c7190201b0658d8bd7484c3bcef6eb41a5ce12` |
| `v4_pb_reporting_contract` | 1 | `89fac030ea9647074ee9fdcb6b47dec3eaba0f147cfb5cdc51b6b4ad3e4a493b` |
| `v4_quarter` | 89926 | `51f9ce460cce50b0c3b5927cdb3f340df9d5ae04461a9a5fca73292d07037e5d` |
| `v4_quarter_financials` | 89926 | `495bf38353adc99fdb113267fe6329bdf9a32249a229ede146fdae5545380c12` |
| `v4_ttm_contract` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `v4_ttm_input_quarter` | 341299 | `f98a170c1d5e0786293a0f11e8e45830fd83472eaa116dbd4751873a667475c8` |
| `v4_ttm_values` | 89456 | `786e158fa512da96fe4b039ee320e5d395a37e0265f96bea85f974a8cc354c2f` |
| `v4_result_publication_authority` | 16157 | `030079dc6ddd3350bba245383679360a4bb814a6798d770b372492a7873f79fc` |
| `v4_result_publication_evidence` | 14185 | `bcf720ddc6a9db0aefde88fdac30b5b29fa5f39212b398e2d49d774300d5c27b` |

## Backup retention and cleanup

Retained rollback backups: **3**, total **2,627,518,464 bytes** (2.447 GiB), created only by the existing publication path. They are retained for operator acceptance/recovery; no rollback backup was deleted. The old immutable generation also remains available. The phase-owned candidate lane was removed by the executor after success; no redundant full DB copy was created by this phase.

| Role | Required rollback backup | Bytes | SHA-256 |
|---|---|---:|---|
| analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/analysis.db` | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/canonical.db` | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| provider | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/provider.db` | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |

## Validation and reporting

Exact immutable plan validation: PASS. Fresh post-YES current-state revalidation: PASS. Locked pre-write revalidation: PASS. Existing candidate all-or-nothing result checks: PASS. Generation activation/SQLite/hash postflight: PASS. Independent exact membership, accession/time/source, financial and nonmember logical-digest postflight: PASS. No source changes or broad tests were needed. Full suite: NOT RUN. Existing operation reporting is preserved without adding a UI workflow.

Publication authority/evidence changed only for the exact authorized 85 keys. Approval/proposal/plan changed: NO. Financial logical state changed: NO. Scheduler changed: NO. Policy V1 changed: NO. Ordinary resolver changed: NO. Rollback required: NO. Recovery required: NO. Nothing was pushed.

Recommended next backlog phase: perform a read-only post-publication census and prioritize the remaining 514 held historical cases for source-specific review. Any new proposal/approval/plan and execution authorization must remain separate from this completed exact-plan authorization.
