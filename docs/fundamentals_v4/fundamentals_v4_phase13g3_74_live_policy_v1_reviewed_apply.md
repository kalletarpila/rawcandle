# Phase 13G.3.74: Controlled Live Policy V1 Reviewed Apply

Date: 2026-10-06 (Europe/Helsinki).
Starting HEAD: `210d4f7ac363dcba8e33ea7fe0f25e6cbbe4998f`.
Result: **SUCCESS**, exact 23 AMBIGUOUS -> VERIFIED transitions.
No source changes, policy redesign, default-policy enablement or full suite.

## Contract Review and Preflight

The Phase 73 explicit schema-2 Policy V1 reviewed-plan path supports this
authorized historical cohort without changing the ordinary recent-open selector.
The existing writer owns the production/scheduler locks, candidate copies,
verified backups, journal, immutable-generation activation and rollback.
No implementation or locking conflict required changes or clarification.

Actual HEAD includes Phase 73. The pre-existing journal modification, untracked
active-generation data and unrelated P/E research files were preserved. There
were no unexpected source modifications. Host process checks before PREPARE and
immediately before APPLY found no conflicting publication/Fundamentals writer.
Both kernel locks were available. Free space was 674,991,472,640 bytes on the
shared production/rehearsal filesystem, exceeding the conservative 12-generation
margin checked by this operation.

Source generation: `publication_drain_20261006T110330Z_2d836e37`.
Provider, canonical and analysis quick_check were `ok`, with zero FK errors.
The source journal was COMPLETED, terminal/clean; no recovery was pending.
Every quarter, authority, company/CIK/security state and all 52 original evidence
records matched the Phase 73 copy-only baseline. All 26 authorities were still
AMBIGUOUS with NULL selected publication timestamps.

The exact 26 natural keys were read from the committed Phase 73 results CSV.
Policy evidence was the same explicit reviewed fixture used in Phase 73:
`tests/fixtures/publication_event_policy_v1.json`.
Its SHA-256 remained
`899ed0f8e5a61f7b8159632c0d5ab74640d6c8805cd69ad75fbaa9e771a54a3e`.
There was no cohort/evidence artifact drift.

## Live Plan and Gates

A **new live read-only PREPARE** was executed against the active production
generation. The Phase 73 copy plan was used only for baseline comparison, never
as the executable live plan. Explicit mode/version:
`PUBLICATION_EVENT_POLICY_V1`; schema 2;
evidence version `reviewed_event_observations_v1`.

Plan ID: `publication_policy_plan_4b3b123c7f894737872925ce753e1c8c`.
Created UTC: `2026-10-06T15:02:04Z`.
Plan fingerprint:
`04b3b058b4f676a7a93fc16588a75c742bc64a0e729748a2786c38b4132615fb`.
Prepared-key fingerprint:
`fddd07b14716d3a54c628afa20efe792c42107a97f635317fac379bcb6f058eb`.
Aggregate policy-decision fingerprint:
`2716cabb2c61e71a6037a68434d6f3194a5df5f6ff68fe8f4d021688e8ec0aae`.
Reviewed policy-evidence JSON fingerprint:
`406a26513fde62fccd7a3263be277b6d8c0f9d4d829f21dcb84b787b4f80ec2d`.
Active manifest fingerprint:
`a83e32c90cdb094e2e31fcf33abd2a79fbfcd59f8ae64dc6b469f2d9bec0b88c`.
Complete cohort authority/identity state fingerprint:
`488398880c685de2387eaf09dd20d3c0cf9eaf598ed446c25f968172b18ff36d`.

| Plan partition | Count |
| --- | ---: |
| Reviewed quarters / bound candidate events | 26 / 52 |
| Filtering-only deterministic UNIQUE | 19 |
| Typed-precedence deterministic UNIQUE | 4 |
| Prepared keys | 23 |
| REVIEW | 3 |
| Unsupported AMBIGUOUS / ERROR | 0 / 0 |

The immutable 0444 plan was loaded through the existing full validator.
Fingerprints, exact cohort/event sets, frozen filing contexts, eligibility,
relations, selected evidence and all acceptance discrepancy gates reproduced.
The decision and prepared-key fingerprints matched Phase 73. REVIEW cases had
no selected accession/timestamp; ABAT, OPTT and AMR alone remained REVIEW.
PREPARE network requests: 0.

The compact 23/3 plan gate was reported before rehearsal. Immediately before
production APPLY, live generation/manifest, complete 26-case state/evidence,
plan/input fingerprints, source DBs, journal, queue and scheduler configuration
were re-read and unchanged. No key was dropped, plan regenerated or scope widened.
The writer repeated its own state validation under both production locks.

## Exact-Plan Rehearsal

Rehearsal root: `/tmp/rawcandle_policy_v1_13g374_20261006`.
Copy writer run: `publication_drain_20261006T150451Z_2fcefaf9`.
The **same immutable live-prepared plan** was consumed without network refetch.
Rehearsal PASSED: 23 prepared/selected/enriched/applied, 23 new VERIFIED;
network requests 0, unrelated changes 0. ABAT/OPTT/AMR were untouched and all
52 full original evidence records retained, including filtered/completion rows.
Canonical non-publication tables and outside-plan publication tables were
semantically identical before/after. Provider/analysis hashes were identical.
Identity/fiscal mappings, unrelated AMBIGUOUS, VERIFIED, UNRESOLVED and NOT_FOUND
rows were unchanged. Journal COMPLETED, postflight PASSED, rollback NOT_REQUIRED;
immutable copy activation succeeded and the candidate lane was removed.

## Production Apply and Postflight

Production run/activated generation:
`publication_drain_20261006T150551Z_9cfd3ca0`.
Writer runtime: 22.960 seconds; this excludes PREPARE, rehearsal and independent
operator postflight. Terminal result SUCCESS; network requests 0.
Prepared/selected/enriched/applied sets were exactly the same 23 natural keys.
New VERIFIED count: 23; original 26 cohort after apply: VERIFIED 23, AMBIGUOUS 3.

ABAT, OPTT and AMR retained their complete original AMBIGUOUS authority rows,
NULL timestamps and unchanged evidence. All 52 original evidence rows were
compared in full and retained unchanged. Filtering never erased evidence.
The immutable plan and original source generation files also remained unchanged.

Journal: COMPLETED; current step COMPLETED; postflight PASSED;
activation ACTIVATED_AND_VERIFIED; rollback NOT_REQUIRED.
All active DBs passed fresh read-only quick_check/FK verification. Their SHA-256:

| Role | SHA-256 | quick_check | FK errors |
| --- | --- | --- | ---: |
| Provider | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` | ok | 0 |
| Canonical | `ed5f37239dcde7b012e9ba4aaaa9e00c0ad5ba91e98d23a5c1fd32525170a65d` | ok | 0 |
| Analysis | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` | ok | 0 |

Provider and analysis were byte-equivalent to the source. Canonical financial,
identity and fiscal tables were semantically identical. All authority/evidence
outside the 23 plan keys were semantically identical, including existing VERIFIED
and unrelated AMBIGUOUS/open rows. Review Queue and scheduler configuration file
hashes were unchanged. No Refresh, scheduler command or network acquisition ran.
The production candidate lane was removed after successful activation.

Verified rollback backups are retained, not deleted, under
`backups/fundamentals_admin_production/publication_drain_20261006T150551Z_9cfd3ca0/`.
Each of the three backup hashes was rechecked against the original source hash.
No rollback/recovery or manual repair was needed. Any later rollback must use the
existing reviewed generation/journal recovery contract, not manual SQL/pointer edits.

## Semantic Resolution Reasons

The 19 filtering-only cases resolved by reviewed event scope, not chronology:

| Exclusion group | Count | Cases |
| --- | ---: | --- |
| Selected-metric/incomplete preliminary initial disclosure | 11 | SMCI, GOSS, REKR, ANRO, KSCP, CDXS, ASTS, CRC, PLUG, PDYN, RGLD |
| Supplemental/repeat disclosures | 4 | APA, SM, DMLP, CF |
| Wrong-period/non-result event | 2 | BKD, KLXE |
| Entity/perimeter/pro-forma context | 2 | ARKO, MOVE |

DMLP's distribution/receipts-only supplemental disclosure is represented by the
policy class PARTIAL_RESULTS and insufficient broad earnings minimum. CF's repeat
exclusion specifically reproduces RESULT_TO_SAME_RESULT_REPEAT proof. Neither
grouping introduces a new policy rule. ANRO's qualifying pre-revenue complete
expense/net-loss package does not fabricate revenue.

The four precedence cases reproduce
PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT, with both events eligible and
retained. Production selected the stored qualifying preliminary SEC acceptance:

| Case | Selected preliminary UTC | Retained completion UTC |
| --- | --- | --- |
| GME | 2026-08-31T10:23:08Z | 2026-09-08T13:02:39Z |
| TE | 2026-07-28T10:37:38Z | 2026-08-12T10:50:51Z |
| RDVT | 2026-08-05T20:05:42Z | 2026-08-11T21:26:49Z |
| RXT | 2026-07-09T12:13:03Z | 2026-08-10T20:08:51Z |

No generic earliest/latest shortcut was used. Later completion evidence retained
its own availability timestamp; no later financial values were backdated.

All 10 reviewed acceptance-source discrepancy events (both accessions for GME,
MOVE, ANRO, KLXE and PDYN) remained bound to their original stored timestamps,
fresh submissions observations, reviewed index evidence and timezone interpretation.
Each reproduced ACCEPTANCE_SOURCE_DISCREPANCY_REVIEWED. The original DB evidence
was unchanged, the frozen discrepancy payload was unchanged, and each selected
authority used its reviewed stored SEC timestamp, never the fresh feed value.
Source hierarchy and SEC acceptance acquisition/normalization semantics did not change.

## Measured Authority Impact

Read-only normal selector measurement as of `2026-10-06`, retry_days 60, no drain:

| Recent-open status | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Total | 188 | 171 | -17 |
| UNRESOLVED | 20 | 20 | 0 |
| NOT_FOUND | 148 | 148 | 0 |
| AMBIGUOUS | 20 | 3 | -17 |

Of the 23 applied cases, **17 were inside** and **6 outside** the current 60-day
scope. The historical six were APA, CF, DMLP, PDYN, RGLD and SM, explicitly
authorized by the reviewed event-cohort plan. They were not forced into recent-open
metrics. No normal historical retry behavior, retry cap or 60-day horizon changed.
ABAT/OPTT/AMR remain the three reviewed ambiguity holdouts. No post-apply retries
or ordinary backlog drain were executed.

## Runtime Evidence and Reproduction

Runtime directory, not committed:
`fundamental_reports/publication_drains/policy_v1_13g374_20261006/`.
It retains preflight, PREPARE output, immutable `reviewed_plan.json`, complete plan
validation, rehearsal output/verification, final gate, production output and
independent postflight with the full cohort recount and before/after recent scope.
The writer's canonical production report is
`fundamental_reports/publication_drains/publication_drain_20261006T150551Z_9cfd3ca0/result.json`.
Copy rehearsal evidence remains at
`/tmp/rawcandle_policy_v1_13g374_20261006/fundamental_reports/publication_plan_rehearsal.json`.
Operator verification helper: `/tmp/phase374_operator.py`; no repo source edit.

Commands executed, with CLI-generated output retained in the runtime directory:

```sh
venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --prepare-reviewed-plan \
  --publication-event-policy PUBLICATION_EVENT_POLICY_V1 \
  --policy-evidence tests/fixtures/publication_event_policy_v1.json \
  --exact-allowlist docs/fundamentals_v4/fundamentals_v4_phase13g3_73_policy_v1_reviewed_plan_results.csv \
  --output-plan fundamental_reports/publication_drains/policy_v1_13g374_20261006/reviewed_plan.json

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/policy_v1_13g374_20261006/reviewed_plan.json \
  --publication-event-policy PUBLICATION_EVENT_POLICY_V1 \
  --rehearsal --rehearsal-root /tmp/rawcandle_policy_v1_13g374_20261006

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/policy_v1_13g374_20261006/reviewed_plan.json \
  --publication-event-policy PUBLICATION_EVENT_POLICY_V1 \
  --apply --confirm-production
```

These are the completed audited commands, not instructions to rerun the consumed
plan against the new generation. Validation consisted only of live PREPARE,
complete immutable-plan validation, same-plan rehearsal, final gate, production
postflight/cohort measurements and `git diff --check`. No pytest suite or Phase 73
227-test rerun was performed.

Production publication state changed: YES, exact 23 plan keys only.
Active generation changed: YES, existing safe immutable publication.
Default Production policy, financial content, Review Queue, source hierarchy,
SEC acceptance semantics, retry logic and 60-day horizon changed: NO.
Live Refresh executed, scheduler state changed, full suite run: NO.
Only this report and its 26-row CSV are committed; no runtime artifacts or source
changes are included. Nothing pushed.
