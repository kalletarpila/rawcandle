# PROVIDER_PAYLOAD_COMPLETENESS_V1 — completed rollout, 2026-10-30

**ACTIVE. All acceptance gates passed.** `source_capture.ACTIVE=True` enables the
policy for future authoritative acquisition/replacement. Activation changed only
that source-policy line. No live acquisition, reconciliation, financial repair,
generation publication, queue update, scheduler configuration change, historical
migration or backup cleanup was performed by activation. No push.

## Current state and exact activation non-mutation

Native admin UI, production and scheduler preflight locks were available and held
across fresh pre-activation capture, source-flag activation and post-activation
comparison. The existing preflight was not bypassed or weakened. The earlier
scheduler-lock STOP was respected; no lock holder or StockCore activity was
inspected, stopped, modified or inferred from unrelated timestamps.

| Current-source measure | Result |
| --- | --- |
| Latest accepted source bindings | 2455 |
| Incomplete current-source tickers / latest incomplete bindings | 0 / 0 |
| Unresolved current-source remediation dispositions | 0 |
| Base / P/B content-profile failures | 0 / 0 |
| Grandfathered current captures lacking V1 envelopes | 2455 |
| Newly V1-attested accepted observations created by activation | 0 |
| Known unsafe authoritative future-ingestion paths after activation | 0 |
| BMRA / NEOV | Both complete, 112 keys, ELIGIBLE |
| NEOV frozen review | 13 OPEN conflicts; exact evidence unchanged |
| Ownership population | 10 PUBLISHED / 3 SUPERSEDED; no reopening |
| Native rollback-backup inventory | 50 files unchanged; none deleted |

The remediation ledger's **181-ticker cohort** contains 173 ELIGIBLE and 8
HISTORICAL_ONLY tickers. This is separate from the global 2455-binding
population. Historical observation evidence remains separately countable:
12940 legacy 29-key rows remain among 192986 provider
observations. Observation counts are not summed as ticker dispositions.

| Exact pre/post binding | Unchanged value |
| --- | --- |
| Active generation | `current_rebuild_2a684ef130c6a540de4adc560ab171ad` |
| Active manifest SHA-256 | `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097` |
| Analysis role SHA-256 | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |
| Canonical role SHA-256 | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| Provider role SHA-256 | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| Provider watermark | `2026-10-28` |
| Journal SHA-256 | `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72` |
| Market SHA-256 | `6c51162f03755aaae5002ab77964af56f96822ad793d67458f60d3722cf225a6` |
| Global analysis/taxonomy SHA-256 | `9a691a46d4bca6da7fb33703371e1bce7ad47c9b2e2920206ba480a745c1b044` |
| Scheduler configuration SHA-256 | `10e7c91e357ffaaacf56785a0bec064a95eaf21a84eb5592642be79fef1dab2b` |

The journal remains COMPLETED, postflight PASSED, recovery NOT_REQUIRED. Its
ACTIVATED_AND_VERIFIED generation state belongs to the earlier financial
publication, not this source-only rollout. Complete queue/audit content,
disposition records, BMRA/NEOV bindings, ownership terminal records, GE/RTX/T,
NEOV frozen evidence, market/global inputs and the native backup inventory also
compare exactly. Role-byte hashes bind WFRD and publication-authority state.
Backups compare by complete native-root path/size/mtime/inode inventory; no backup
operation was invoked. All application-source identities except the policy file
remain identical. Its before/after hashes are
`2266a232ddb54743ddfd34cd15fa82b8f9acda3b050ce351e2e20bd7626ae45c` and
`0b0d042325944a80ad058c15b977a9fa46d2c20e3b4ccbfafe04b4f90c301f4b`.

Evidence is retained locally under `temp/fundamentals_payload_completeness_closeout_20261030`: `pre_activation.json`,
`post_activation.json`, `activation.json`, the final XML/logs, `copy_matrix.json`
and the exact selected-file list. These temporary artifacts and copied databases
are deliberately excluded from the source commit.

## Defect and compatibility boundary

The old defect serialized a normalized 29-field dictionary as though it were a
complete provider payload. Financial projection could remain plausible while
factor, equity and other source fields disappeared. Exact remediation and the
BMRA/NEOV current-state rebuild cleaned current accepted bindings before this
future-ingestion hardening. This rollout performs no historical mass repair,
backfill, deletion or re-attestation.

Full-shaped pre-V1 rows remain explicitly grandfathered accepted evidence. They
are not falsely labelled V1-attested and cannot independently attest a new full
acquisition. Reading/rendering does not migrate them. Existing terminal ownership
and frozen-history decisions remain intact.

## Capture contract and persistence

`rawcandle/fundamentals/source_capture.py` separates complete raw provider data,
native normalized projection and a compact capture envelope. Successful
unprojected official Sharadar HTTP acquisition constructs `CapturedRecord` objects
with a separate envelope attribute. Discovery projections remain permitted but
carry no full-source authority. Plain dictionary/relational/canonical projections
cannot attest acquisition; `HistoryTrust.COMPLETE` alone is insufficient.

The envelope binds policy, origin/path/status/time, source identity, request and
HTTP-response identities, raw payload/key-set/key-state fingerprints, normalized
projection fingerprint and required profile states. Managed CSV/ZIP acquisition
requires the checksum-bound unprojected acquisition manifest and preserves original
origin/time. Field count or filename alone is not attestation. This is a native
integrity/provenance contract, not an external digital-signature service.

Wire transport contains one complete raw object plus metadata and the small native
projection. The existing provider DB stores raw fields in `payload_json` and the
compact envelope in `provenance_json.source_capture`. There is no parallel raw
store or SQL schema migration. Unknown upstream fields, including underscore keys
and nested values, survive persistence and reload. Revalidation checks raw,
projection, identity and envelope consistency before new authority is persisted.
Review/Add bindings exclude only volatile recapture time/response-wide identities
from decision comparison; each fresh capture is independently validated, exact row
fingerprints remain bound, and the timestamped original envelope is retained in
provider provenance. Review binding evidence cannot become acquisition authority.

## Field states and profiles

Canonical states are ABSENT, EXPLICIT_NULL and VALUE. Known numeric provider null/
empty tokens, including whitespace strings, agree with native financial acceptance.
Zero and string `"0"`, factor 1 and string `"1"` remain values. Absent/null factor
never becomes 1.0. Unknown/text strings are not globally reinterpreted. The native
integer helper now preserves numeric zero. Old exact NULL-label receipts remain
backward-readable without rewriting them or relaxing their payload fingerprints.

| Profile | Presence / usable requirements | Explicit null |
| --- | --- | --- |
| BASE_FINANCIAL_SOURCE | Native 29 projection keys, usable source identity, valid normalization | Nullable financial metrics allowed |
| PB_OWNERSHIP_SOURCE | Base plus factor/equity/equityusd/price/marketcap/pb; seven ownership metrics usable | Required ownership metrics cannot be unusable |
| HISTORICAL_FREEZE_SOURCE | Base plus equity/equityusd/sharefactor | Provider null remains real source evidence |
| PAYLOAD_REPAIR_SOURCE | All known 112 SF1 keys, usable identity, valid normalization | Nullable metrics allowed |

Profiles do not require all 112 values to be non-null. Existing P/B thresholds,
financial calculations and source/economic policy still apply after capture checks.

## Guarded entry points and downstream behavior

Guards cover native HTTP complete-history Refresh, direct Refresh insertion and
history replacement; Add/network acquisition and generic authoritative staging;
local-provider reuse; managed bulk/bootstrap/backfill; the existing SNDK archive
path; exact payload repair; and controlled current-state rebuild. The historical
prototype acceptance-cache loader is not future full-source authority. No new
ticker-specific policy branch was introduced.

Replacement verifies the entire incoming selection before deletion or boundary
installation. No normalized fallback is serialized as raw source. Exact retained
history keeps original observation/header/capture identity; cache reuse preserves
original capture and cannot silently use a truncated valid subset or claim a fresh
acquisition. Unattested cache requires archive/network reacquisition.

Failures distinguish SOURCE_PAYLOAD_CAPTURE_UNVERIFIED from a verified acquisition
that is SOURCE_PAYLOAD_INCOMPLETE for its required profile. Proven ticker-local
capture failure holds that ticker while safe peers continue; unknown identity and
existing global blockers remain blocking. No new backend review state is added.

P/B adds the source precondition without changing ordinary continuation thresholds
or reopening terminal cases. Freeze protects canonical values on local capture
loss with capture-quality evidence and empty financial changes; verified provider
null/value revisions still follow native financial holds. Existing frozen reviews
are not rewritten. Strict repair retains exact key/version/identity/financial
eligibility, with stronger full-capture provenance. Current-state rebuild remains
a separate newer-source-version operation; its financial/fiscal/review/generation
contracts are unchanged.

## WFRD and acceptance API corrections

The WFRD positive clients lost capture when copying raw dictionaries. They now
route full synthetic responses through the native HTTP boundary with `full=False`;
assertions prove exact raw contents and the registered item remains OPEN before
approval. Discovery projections remain small.

The missing-key parity case removes the reviewed key only after capture. The
conflict case adds an independently captured full synthetic conflict, preserving
original rows and the conflict's exact key/financial values. Both explicitly prove
valid capture/COMPLETE history and retain the original boundary exception classes,
now matching the specific missing-key/new-accounting-conflict reasons. The native
accounting-boundary implementation, decision/fiscal semantics and authorization
were not changed or bypassed.

The acceptance test incorrectly queried a computed eligibility field on a raw
queue row. Raw assertions now use the raw API; eligibility uses the existing pure
`present_review_item` result, as used by the presentation API. The test verifies the
computed field is absent from raw persistence, the OPEN hold/classification is
correct, approval remains blocked, and presentation leaves queue bytes unchanged.
No persistence column, schema or backend approval rule was added.

## Final verification

**904 distinct targeted tests PASS**: 881 across 31 explicitly named relevant
files plus 23 operational rebuild/archive tests in two additional files.
No full suite ran. Repeated exact-case/intermediate runs are not added to this total.
The six acceptance cases all pass: lossy Refresh, safe peer, managed projected
backfill rejection, forged-COMPLETE strict-repair rejection, and both source-integrity
UI classes. Primary UI retains ticker/status/classification/reason/next action;
profile, missing/null/unusable fields, provenance and fingerprints remain Details;
raw JSON stays nested. Rendering does not mutate state or grant approval.

| Copy scenario | Final passing evidence |
| --- | --- |
| 1. Complete Refresh | Native full workflow and immutable generation/postflight/rollback/recovery tests |
| 2. Lossy Refresh rejected | Full workflow hold, unchanged generation/journal and exact source/canonical preservation |
| 3. Verified full-source Add | Generic Add/Batch Add staging, apply and workflow tests |
| 4. Projected-source Add rejected | Native authoritative writer rollback and no provider/canonical change |
| 5. Exact payload repair | Native isolated receipt-bound immutable publication and source provenance |
| 6. Controlled current rebuild | Additional real full-analysis copy receipt; native publication/rollback/cleanup lifecycle regressions |
| 7. Complete P/B source | Copied future publication, cleanup and second-reconciliation idempotency |
| 8. Incomplete/unverified P/B | Source/factor/identity negatives remain undecided |
| 9. Verified frozen conflict | Exact holds, reviewed copy publication and cleanup |
| 10. Local capture loss | No fabricated financial revision; genuine provider null remains distinguishable |
| 11. Safe peer continues | Native peer generation/postflight/cleanup while held source remains exact |

The operational negative-date fixtures now seed their intentionally invalid
pre-V1 history through the existing legacy prototype fixture path, with no V1
attestation, rather than the newly guarded future-authoritative inserter. This
preserves reader rejection/precedence coverage without weakening the new guard.

The additional current-rebuild analysis test uses native initialized review/P/B
contracts in its disposable fixture and does not substitute the analysis engine.
Existing lifecycle unit fixtures retain their established expensive-calculation
substitution; the companion test supplies actual analysis coverage. All applicable
source, canonical, analysis, generation, journal, recovery, cleanup and no-collateral
assertions pass. Synthetic provider fixtures use real native acquisition boundaries;
production never fills absent source values to manufacture capture proof.

Final lossy certification covers projected 29-key input at Refresh insertion/
replacement, Add/generic staging, local cache, bootstrap/backfill, strict repair and
controlled rebuild, plus discovery compatibility. Rejection precedes authoritative
persistence; no downgrade, canonical mutation, false attestation or invalid-cache
promotion occurs. Full-payload persistence/reload preserves unknown fields, states,
fingerprints and provenance for P/B/freeze/repair/rebuild consumers.

## Publication and commit scope

Activation is the source flag only, after fresh healthy preflight and all gates.
It invokes no live provider or financial workflow and publishes no generation.
Only task-owned source, tests and this report belong in the local commit. Runtime
DBs, queues/audits, journal, manifests/generations, scheduler configuration, temporary
evidence/copies, backups and unrelated OHLCV/research artifacts remain excluded and
preserved. No push.
