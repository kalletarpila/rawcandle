# P1.6B — Durable approved historical publication plan

One immutable version 3 plan is prepared and validated for 85 approved, currently open cases. Publication and Production apply remain **NOT AUTHORIZED**. No Production writer was called; the existing candidate writer was exercised only against a SQLite backup under `/tmp`.

## Current baseline

Inspected HEAD: `1c654ed8068dc37e1b3ca5b55ad05aa416de1121`. Initial worktree contained the pre-existing modified publication journal and untracked active-generation pointer/directory and PE research script/PNG; these are excluded from this commit.

Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. Manifest fingerprint: `0cc331f59dfefbf58adb09d8467048e392e95dda24cbe3cb1ac3d54fe8debc3f`. It did not advance during this phase.

Provider watermark: `2026-10-08`; latest successful normal Production run: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`, completed `2026-10-09T04:27:27Z`. Journal: `COMPLETED`, activation `ACTIVATED_AND_VERIFIED`, postflight `PASSED`, recovery `NOT_REQUIRED`, updated `2026-10-09T04:37:11Z`.

Authority census: 16,242 total; VERIFIED 12,890; NOT_FOUND 1,882; UNRESOLVED 842; AMBIGUOUS 628. Whole-authority fingerprint: `41e710eb4dca4418d48e403fde8c70777efa1c02be24cb48e7eb3a6a4ccce577`. Review Queue: 6 refresh rows, all RESOLVED; 38 audit rows; 0 ownership rows.

## Exact approved population

| Classification | Count |
|---|---:|
| READY_FOR_PLAN | 85 |
| ALREADY_VERIFIED | 0 |
| STALE_APPROVAL_SOURCE_CHANGED | 0 |
| STALE_APPROVAL_QUARTER_CHANGED | 0 |
| STALE_APPROVAL_COMPETING_CONTEXT | 0 |
| STALE_APPROVAL_IDENTITY_OR_PERIMETER | 0 |
| STALE_APPROVAL_POLICY_INPUT_CHANGED | 0 |
| OTHER_HOLD | 0 |

Reconciled: 85/85. Writable membership: 85. The original 514 P1.4 holds are excluded. No stale or terminal case exists in this baseline. All 85 canonical quarters remain unique and ACCEPTED; active CIK, security, provider identity and structural/perimeter bindings match. Missing Production evidence remains absent in all 85 cases and is allowed only through the explicit approved-frozen contract.

Fresh snapshots were reconstructed from current read-only canonical queries and complete retained captures, rather than copied from P1.6A outputs. Every snapshot reproduces the exact P1.5 approved case fingerprint. Full-company resolver replay with the approved observations yields UNIQUE for all 85; the empty-observation control yields REVIEW for all 85. All 595 literal excerpt locators, source hashes, evidence hashes, accessions, document references, timestamps and observation fingerprints reproduce. No relation or competing-context change was observed.

Full resolver population: 201 distinct quarters in 32 companies, including **116 context-only quarters**. Only the membership CSV's exact 85 natural keys are writable. Current context and identity/perimeter comparisons run before any copy-only writer call. Terminal/stale selection is never rebound to the old approval; existing open-scope and full approved-context guards fail closed if context changes.

- [Revalidation ledger](fundamentals_v4_historical_publication_plan_p16b_revalidation.csv): one row per approved key, current status/quarter/period, accession/timestamp/source reference, source/capture/context/evidence/observation/state fingerprints and explicit identity/perimeter fingerprints.
- [Writable membership](fundamentals_v4_historical_publication_plan_p16b_membership.csv): exact 85-key allowlist.

Membership fingerprint: `deeb4247ea48ab89c76f22ea1de78d1437a9a4de726172fda5ecbfa30a502234` (also the source allowlist fingerprint).

## Durable immutable evidence and plan

| Artifact | Canonical fingerprint | Exact file SHA-256 |
|---|---|---|
| P1.4 proposal | `ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657` | `6ca99cbc6aeb05ec15fd0927a0c008c9f6add54229ed705b0654c81f89891786` |
| P1.5 approval | `0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651` | `77571dfad2b9d5b6b3a0601df6718b68cf93b2d5f150c898f0141db4039a8387` |
| Fresh handoff v1 | `289eca58761068d8106ca628db65fe3454aa1dc16f178f7bfb975f67ce6a5d81` | `2468472a8497fe7dfab12362938eb3f9f6c2a0a2dd85830e52db1a44d64bf9cd` |
| Publication plan v3 | `f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70` | `6c6d05c835ce6c286ff37583aab966f6f2d9f4c92d46aaa16ce970ae1ab150d2` |

Handoff: [historical_publication_approved_handoff_v1.289eca58761068d8106ca628db65fe3454aa1dc16f178f7bfb975f67ce6a5d81.json](reviewed_evidence_handoffs/historical_publication_approved_handoff_v1.289eca58761068d8106ca628db65fe3454aa1dc16f178f7bfb975f67ce6a5d81.json).

Plan: [historical_publication_policy_plan_v3.f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70.json](reviewed_publication_plans/historical_publication_policy_plan_v3.f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70.json).

The existing preparer accepts an explicit caller-selected output path; it has no fixed durable plan directory. These versioned hash-named files live under `docs/fundamentals_v4/reviewed_evidence_handoffs/` and `reviewed_publication_plans/`, outside active data/backups and scheduler inputs. Both use the existing exclusive temporary-write/fsync/read-only/hard-link publisher (0444), with no overwrite or runtime discovery. The one durable plan embeds the exact handoff. The duplicate plan remains temporary and uncommitted.

The handoff includes required complete capture payloads, the original review candidate and immutable receipt, exact approved observations/snapshots, embedded identity proof and the six required additional extracted document texts. No raw HTML downloads or separate temporary company captures are committed.

The necessary reviewed semantic input formerly at `/tmp/rawcandle_13g381/reviewed_cases.json` is preserved byte-for-byte as [reviewed_cases.18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a.json](reviewed_evidence_handoffs/reviewed_cases.18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a.json) (SHA-256 `18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a`, exclusive creation, 0444). This supporting semantic reference is required by `check_live_inputs`, and is not an additional handoff or plan. Other semantic inputs already reside in the repository. `semantic_input_paths` explicitly maps original provenance labels to repository-relative durable paths. Future validation/application must run from the repository root, which resolves every pinned alias without reading `/tmp`; original `/tmp` labels remain provenance only. No automatic discovery or fallback is involved.

| Reviewed semantic reference | SHA-256 | Durable alias |
|---|---|---|
| `/home/kalle/projects/rawcandle/rawcandle/fundamentals/result_publication.py` | `3007a390ee065728e3c421c6a0cfa134acb6600d7fccebbbc191a40977a6dfd5` | `rawcandle/fundamentals/result_publication.py` |
| `/home/kalle/projects/rawcandle/rawcandle/fundamentals/publication_event_policy.py` | `7686211d903365791137b2bcaf21d80f9af9e1e5d5c3e6e99107536cf6b23018` | `rawcandle/fundamentals/publication_event_policy.py` |
| `/home/kalle/projects/rawcandle/rawcandle/fundamentals/publication_timestamp_equivalence.py` | `52be9997fef3bd36bbcc0c79eae986de67cbca5934098891c31525af22946402` | `rawcandle/fundamentals/publication_timestamp_equivalence.py` |
| `/home/kalle/projects/rawcandle/tests/fixtures/publication_event_policy_v1.json` | `899ed0f8e5a61f7b8159632c0d5ab74640d6c8805cd69ad75fbaa9e771a54a3e` | `tests/fixtures/publication_event_policy_v1.json` |
| `/home/kalle/projects/rawcandle/tests/fixtures/form6k_authority_v1.json` | `689f3e25f3309a5414af84ff6c58f9563f0eb401be6421400373168e1a418387` | `tests/fixtures/form6k_authority_v1.json` |
| `/tmp/rawcandle_13g381/reviewed_cases.json` | `18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a` | `docs/fundamentals_v4/reviewed_evidence_handoffs/reviewed_cases.18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a.json` |

The approved snapshot retains its original planner implementation hash as immutable historical metadata. As in P1.6A, the authorized adapter change is excluded from live Policy V1 semantic references; the policy, ordinary resolver, timestamp helper and reviewed fixtures remain byte-identical. The embedded identity proof remains bound to its original exact byte hash and to current rows; population context is verified directly from current canonical data.

## Supported deterministic preparation

Explicit audit metadata: plan ID `historical_publication_p16b_289eca58761068d8106ca628`; creation timestamp `2026-10-09T15:50:50Z`; as-of date `2026-10-09`; retry days `60`.

`prepare_policy_plan` and `prepare_reviewed_plan` now accept paired `plan_id` and `created_at_utc` arguments only for explicit approved mode. IDs must be nonblank strings; timestamps must be valid timezone-aware strings and are normalized to UTC. Omitted metadata keeps fresh random IDs and the normal audit clock. Legacy v2 behavior is preserved. No production monkeypatch, global predictable-ID behavior or execution path was added.

Two preparations used the same durable handoff path, durable membership path, frozen metadata and generation baseline. Their complete bytes and canonical plan fingerprints are identical, proving identical membership, observations, evidence and full source/resolver context. One durable file is retained.

## Validation and copy-only rehearsal

| Check | Result |
|---|---|
| Durable v3 validate_policy_plan, receipt/handoff/source integrity | PASS |
| Exact approved writable membership / context-only exclusion | PASS |
| Byte-identical deterministic preparation | PASS |
| Fresh post-plan generation/current-state revalidation | PASS |
| Existing candidate execution against temporary SQLite backup only | PASS |
| Fresh Production revalidation after rehearsal | PASS |
| Protected-file invariance (27 files) | PASS |

The rehearsal uses the existing `run_policy_candidate` against `/tmp/publication_plan_p16b/rehearsal_candidate.db`, copied via SQLite backup from the read-only current canonical DB. All 85 planned keys become VERIFIED with exactly the approved selected evidence ID, accession and publication timestamp. The complete logical digests of every other table and all nonmember authority/evidence rows remain unchanged, proving the 116 context-only keys, unapproved keys and financial tables remain untouched. The authority references selected_evidence_id, whose evidence row supplies the accession; the proof checks this actual schema linkage.

| Copy-only unchanged logical table | Rows excluding writable authority/evidence | SHA-256 |
|---|---:|---|
| `company` | 2547 | `70dffe941c4cbf43142d3d96557d060f98f9b61b26a0ea10f94ca762833d5a58` |
| `company_cik` | 2542 | `4232e4eac7ecb0222837344372cec5b58a43edced6838af36e802670aaa84597` |
| `company_fiscal_calendar_profile` | 2458 | `0cbc1e7d7564738bda99275c83733f813ddded7a49f2bed1f8025b7b35b7e818` |
| `company_fiscal_year_anchor` | 35245 | `667cdb1aedc3a9210ac0c20d13f689ef9d4e6779fee9ae9da29bae1be19eb1fc` |
| `fundamentals_economic_structural_event` | 5 | `9c487a8fb67c778642b3df1a1e1d0ac7c0b1eec7e138d2552335a8a69ca4556e` |
| `fundamentals_operational_universe_active_version` | 1 | `acb39f603b511f6f449638997d054650196d72b6beebb98f5b16c57b76d04a6a` |
| `fundamentals_operational_universe_member` | 12313 | `24cc0478d25bbda44d492fb827a2bf7c69efea7a16c0e6ba3a02519cb839af0b` |
| `fundamentals_operational_universe_member_alias` | 12428 | `fc9b0ecf769a6870b9c1d2397eb3d6b5bde091a71c39c33b5d3ebfcb86af3fef` |
| `fundamentals_operational_universe_schema_meta` | 1 | `87d3ddc7eddd7c9133be3cca583c750be3ead98a86c1678beb2595d18b9ea6fe` |
| `fundamentals_operational_universe_version` | 5 | `b6209adf44fcf050aff17c61b02faee31a3edeb2885a021178dd62e44efc44b0` |
| `fundamentals_quarter_economic_regime` | 197 | `05df233dfbc8fd54395da93ff9ac0801c2419455ccc4a8a4df2ae75a95f68603` |
| `fundamentals_ttm_economic_regime` | 197 | `cd0d8c449714bef75ec999598460b36a6c9243cddf9cca3ecb6137500e074d3e` |
| `phase13g2_applied_plan` | 8 | `6595903f0724da264a5a4dcfdf02faba45142a52b44d0af19c5abfb5fcec848c` |
| `provider_company_identity` | 2527 | `526a4ccc5049c4dfe07c6b80b5b5e1a61abe960d04913508711fa85fe5c08d11` |
| `provider_security_identity` | 2557 | `2876029b11526ffe1a5f76dc3de8cf05989c54914f5fdd0d9548dcff17790e9b` |
| `schema_version` | 1 | `06f678da71a4c948f8efe6838452fb1f2e65cf1976bc9252d4ec667fbdd6c115` |
| `security` | 2560 | `b4071f70c05990a6ab6736f2585b752bdefdf8ac601bcbe296442ff855349fc2` |
| `ticker_alias` | 2575 | `a72cd1928536b8f447a0dc870ea9d04e8e8cc55931efd133726401d31e34c276` |
| `v4_common_earnings_provenance` | 88662 | `641a53a29fc0d8112c7a3c85cc7ca15e1f913edb1ada50d5fe76b628c1ccd534` |
| `v4_field_provenance` | 1065776 | `bf3f04c72f8c81d5cf0980fa3a070997e2557527d89291fd4d7407aea07ea36f` |
| `v4_operating_working_capital_provenance` | 449615 | `da1aa7c0fd605c9d4b2f3458b3acbab1903f5af0e7dc2bc606f70f7a22754c28` |
| `v4_parent_equity_provenance` | 170290 | `fffcd50f1b01f0c7c19214a1eac4ee85bd59e1bb123c1299581009a5547eaae4` |
| `v4_parent_equity_source` | 89924 | `e535b89ae3d8067e227e4f47a0dc79335491d182de9ee74c68e7f5c2859606bb` |
| `v4_pb_reporting_contract` | 1 | `7b3b55f91afab0ff562455a3e3529cbd080400f69d3cfe93269d9fe724625861` |
| `v4_quarter` | 89926 | `4e8d28b7e4bcc3e72891eaa18fb5350f6806d6ff275ff5aed7fc1f44010b0353` |
| `v4_quarter_financials` | 89926 | `cede87ae5704d206b0486f640e85c6507526703bd28e0ac0974158377f1650d7` |
| `v4_result_publication_authority` | 16157 | `09bd3ca368659d3eea3a7a10c1e3f668b4335acdb8bfa153f39fd46b589649c0` |
| `v4_result_publication_evidence` | 14185 | `2b9e0ae479f50b5b16bddd42f2a87fe20734af6d81b0ed4fcac67e5e3c7bcd7c` |
| `v4_ttm_contract` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `v4_ttm_input_quarter` | 341299 | `30cd3fa11a1cbe0dbc0ca8011e2ae82115d56cdb6132729404552ae8addf7841` |
| `v4_ttm_values` | 89456 | `cf09018fa1139401209dcd93a7803f79cdd652d34ba61fa58864c564e172d1dc` |

## Production invariance and authorization

Publication authority/statuses/timestamps changed: **NO**. Authoritative reviewed observations installed: **NO**. Approval artifact changed/consumed: **NO**. Provider, canonical and analysis DBs changed: **NO**. Active generation, Review Queue (including existing WAL/SHM), publication journal, schedulers, watermark and retry behavior changed: **NO**. Policy V1 semantics and ordinary resolver semantics changed: **NO**. Publication authorized: **NO**. Production apply executed: **NO**.

Plan flags remain `publication_authorized=false`, `production_apply_authorized=false`, `executed=false`. The immutable P1.5 approval remains evidence approval only, with all original non-executing flags. No previous YES authorizes P1.7.

| Protected artifact | SHA-256 before and after |
|---|---|
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771/fundamentals_provider.db` | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771/fundamentals_v4.db` | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771/fundamentals_analysis.db` | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| `/home/kalle/projects/rawcandle/data/fundamentals_active_generation.json` | `30c08f22b5b9b2a3cbb07f5183d2946e3ed8b980634d0e54255936b9310b5de3` |
| `/home/kalle/projects/rawcandle/fundamental_reports/fundamentals_refresh_review_queue.db` | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| `/home/kalle/projects/rawcandle/scheduler_config.json` | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| `/home/kalle/projects/rawcandle/forecast_scheduler_config.json` | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |
| `/home/kalle/projects/rawcandle/data/.fundamentals_admin_publication_journal.json` | `6f7e625fe10c0ab98c31902bb34d4e7a0c24ea2c94b840497b0459a07817aa67` |
| `/home/kalle/projects/rawcandle/fundamental_reports/fundamentals_refresh_review_queue.db-wal` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `/home/kalle/projects/rawcandle/fundamental_reports/fundamentals_refresh_review_queue.db-shm` | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_completeness_summary.csv` | `572e72a7970c34f2031660afe71fd62be1232135fc4ab1cde0a34e7a45347dcc` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_completeness_audit.md` | `9af8abcf4485757d14d4653a8e72cbc44bfaf0abf9fb85bbbcef080f1ace2ec2` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_completeness_audit.csv` | `7c5786ca641899e5bbadb9b0198c318d76eda64610a5cab8baf3a7898df2ea5a` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_publication_timestamp_equivalence.md` | `eeba5924756359008f193718909ea857ad3a51a35b196565053b21bfb375b548` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_publication_timestamp_equivalence_cases.csv` | `52ada711cf10614e9233535a993373929250618ef540817bcf42c9369de6b43c` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_candidates_after_timestamp_equivalence.csv` | `1d6ce5e9792b4ebcd664545d8ce3f981ca010f5fb2e1caec013bd33025f44d57` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_exact_key_validation.csv` | `035718c2697b3a5ea99d2bc4af6ecadb3358331e43e1bd49450ac35632fb16b3` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_exact_key_validation.md` | `3bd9bcfa130aeae5722d25e38eea0485ca1b2878d8956a0ae41e6dbedfc0f1e4` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_validated_apply_candidates.csv` | `5fff765be6078e47bdbb05e405aead52cea081705cfe5b547b999ebd1b8c97c0` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_review_observation_proposals.md` | `881b5524fbc23e8526dea6dbd8c7ffb1cca287a5b20821b88b1360416277659a` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_review_observation_classification.csv` | `96b24b620694bea88203485fd6c7d29c5bddf62fa566d77bafb4117e7b4636ad` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_proposed_reviewed_observations.csv` | `ab6cd037a0c9480f157700a96af26e98d3dcd7c4e262f0c62bba1e7a3ad4d6a2` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/review_proposals/historical_publication_review_proposal_v1.ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657.json` | `6ca99cbc6aeb05ec15fd0927a0c008c9f6add54229ed705b0654c81f89891786` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/review_approvals/historical_publication_review_approval_v1.0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651.json` | `77571dfad2b9d5b6b3a0601df6718b68cf93b2d5f150c898f0141db4039a8387` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_operator_review.md` | `be3f929a5a89b098b1a2e73ddd95c077d6c0651f3efc270980aa2d7a2ffd3fbf` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_plan_handoff.md` | `9a5dd411ee4335264883152d54e42811f77b1f12ea7e13346afe0f36688b1c07` |
| `/home/kalle/projects/rawcandle/docs/fundamentals_v4/fundamentals_v4_historical_publication_plan_revalidation.csv` | `597692ff6066bbec9e29c97f9cfb04225f5f410fd5eebc8956a7c8f8a104c53e` |

## Focused verification

66 tests passed in the focused approved-evidence group and the one directly relevant legacy Policy V1 reviewed-plan regression group (`tests/test_approved_publication_evidence.py`, `tests/test_policy_reviewed_publication_plan.py`). Two additional focused cases passed for durable handoff serialization/pinned relocation/immutable publication and already-VERIFIED population exclusion. Total: **68 passed**. Full suite: **NOT RUN**.

The focused cases cover mandatory receipt/pin, handoff tampering, absent/exact/conflicting/extra stored evidence, quarter/authority/identity/perimeter/fiscal/source/policy/context drift rejection, full context-only exclusion, immutable output/duplicate paths, explicit metadata and ordinary metadata defaults, no writer during preparation, untouched approval/false flags, and legacy v2 behavior. Stale evidence cannot enter writable membership because exact snapshot and source guards reject it.

## P1.7 boundary

Do you authorize P1.7 to execute only publication plan `f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70` for exactly 85 cases, bound to active generation `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`, subject to fresh generation, authority, evidence, identity/perimeter, full resolver-context and Policy V1 checks? This is separate execution authorization; the earlier YES approved evidence only.

This is the recommended question for the separate P1.7 phase. This phase stops after preparation, validation and copy-only proof. Nothing was pushed.
