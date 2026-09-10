# Phase 12D: Ten-Year Operational V4 Rebuild Rehearsal

## Decision

Phase 12D rehearses the ten-year operational rebuild on isolated production-shaped
copies. The resulting history is **currently revised, non-PIT history** reconstructed
from the provider snapshot available in 2026. It must not be represented as an
investable point-in-time backtest.

The final decision is **Outcome B: rebuild correct but material data or versioning
decision required**. The canonical and coherent Operating-Income V2 package rebuild
is valid, but the separately persisted Relative Valuation snapshot becomes
economically stale when Absolute Valuation history expands from 50,585 to 87,319
rows. Phase 12D neither refreshed nor activated it.

## Locked Contract

- Rebuild contract: `TEN_YEAR_OPERATIONAL_V4_REBUILD_REHEARSAL_V1`
- Rebuild fingerprint: `06521fcd073813e4bfa3605a15bcd9e2e4002a05dbb1e55ebe3444defe4eb741`
- Provider retention policy: `SHARADAR_FUNDAMENTALS_HISTORY_POLICY_V1`
- Provider policy fingerprint: `1e025bf2a19d494cc1dd6ce3a0b49d94a966db008476f780c7e4dd671cd543b9`
- Phase 12B contract fingerprint: `26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139`

No formula, threshold, weight, readiness rule, diagnostic definition, return label,
research period, purge, embargo, or hypothesis changed. ARQ remains the canonical
quarterly source. MRQ remains revision/comparison evidence and is not mixed into the
TTM chain.

## Dependency Order

1. Select the latest accepted ARQ observation for each operational company and
   fiscal identity.
2. Reconcile canonical quarters and all field-level provenance.
3. Rebuild TTM values, input-quarter evidence, readiness, and availability dates.
4. Rebuild Fundamental Score V2.
5. Rebuild Lifecycle V2.
6. Rebuild Absolute Valuation V2.
7. Rebuild Fundamental Delta V2 for QoQ, 2Q, and YoY.
8. Rebuild the active eight-flag Diagnostic Flags V2 package.
9. Rebuild Relative Position V2 as required by the coherent package contract.
10. Persist a new candidate package manifest without creating an active pointer.

Operating Income is used directly on the V2 operating path. There is no EBIT or
EBITDA fallback. TTM EBIT remains only for the independently specified
Non-Operating Earnings Gap flag.

## Rehearsal Evidence

The authoritative evidence is under
`temp/fundamentals_v4_phase12d/20260910T_PHASE12D_REHEARSAL_V7/`.

The deterministic V6 substantive run established these counts; V7 reruns the same
contract with the final production-sidecar immutability rule:

| Measure | Before | Candidate |
| --- | ---: | ---: |
| Canonical quarters | 50,585 | 87,319 |
| TTM endpoints | 50,585 | 87,319 |
| Score results | 50,585 | 87,319 |
| Lifecycle results | 50,585 | 87,319 |
| Absolute Valuation results | 50,585 | 87,319 |
| Delta endpoints | 50,585 | 87,319 |
| Diagnostic endpoints | 50,585 | 87,319 |
| Diagnostic evaluations | 404,680 | 698,552 |

Canonical classification:

- new history: 36,734
- revised overlap: 395
- unchanged overlap: 50,190
- superseded/duplicate provider observations: 2,113
- unresolved operational identities: 0
- duplicate fiscal identities: 0
- orphan financial rows: 0
- unexplained or stale rows: 0
- canonical period-end range: `2015-05-28` through `2026-08-02`

The two append-only provider tickers absent from the 2,449-ticker current source
intersection are `BTAI` and `HLX`. The authoritative operational rule retains them;
Phase 12D did not apply a current-membership filter. Each remains in canonical and
all coherent downstream layers with 21 quarters from `2021-06-30` through
`2026-06-30`. Thus the provider population remains 2,451 tickers and the separate
6,568-ticker historical-only research universe was not introduced.

All 87,319 non-null canonical observations have field-appropriate provenance.
Ready TTM chains have zero cross-company inputs, zero nonconsecutive chains, and
zero maximum-input-availability mismatches. A total of 665 nonconsecutive partial
chains remain explicitly blocked as `TTM_DATA_INSUFFICIENT`; they are evidence of
missing quarters, not ready TTM calculations. Historical warmup changes readiness
on 6,383 of the original 50,585 overlap endpoints.

Candidate row counts include 611,233 Score components, 611,233 Delta components,
698,552 Diagnostic evaluations, 19,596 Relative Position coverage rows, and 13,737
Relative Position result rows. SQLite `quick_check` is `ok`, foreign-key errors are
zero, and every expected component/evaluation count reconciles.

## Identities

Economic model fingerprints remain unchanged:

| Layer | Model fingerprint |
| --- | --- |
| Score V2 | `271585e4136f6733c047e89dac7646f2ff91f8c84b10f88c56356ad495970360` |
| Lifecycle V2 | `0502822c20501c1487d09a20a378e86c0908a0953dfcb13b384428822fc4e175` |
| Absolute Valuation V2 | `9675c2d947a86d2115f366424eab7454ec013cc100c7548af004c19c691c9aeb` |
| Delta V2 | `c65062c1ac66f1e98ab239404dba96c43060708a35a84bcfd2ed01c30d5e2f11` |
| Relative Position V2 | `993a3cfbbfd7d724852cf78466a91edf0a1adca8cd08c35e8bcc2891a5cbe30f` |
| Diagnostic Flags V2 | `0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904` |
| Snapshot presentation | `f04e5dedf0cadecbd6039eabdcfc16d77a17b8cce729a63a810df7914d352a11` |

The enlarged source population requires a new package persistence identity. The
rehearsed candidate package fingerprint is
`f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`.
Its economic result fingerprint is
`3fdd93b6fedcdf7384728016c55fd955a2c44dfbc03c4618a758fd1601c84b27`
and physical-content fingerprint is
`63fb7191889c22835ebef895dd1afbca455998345b7d4495a1382a9b747324fa`.
The canonical and TTM fingerprints are respectively
`74cd17f19b253caa75e403dfe95a081f1af3b7d0c225715db88c9f169a3737bf`
and `7b74ab52354f51b31a425eae36dbe84d9a1be9ca68ae469a6c1cf832421b9862`.

The first apply wrote 2,390,946 logical rows. The identical second apply returned
`NO_CHANGE`, wrote zero logical rows, and preserved candidate database bytes, mtime,
page count, freelist, pointer, audit population, and sidecar state. Two independent
clean-copy rebuilds matched for canonical, TTM, layer results, package identity,
economic result, and physical content.

Rollback was verified after injected failures at canonical, TTM, Score persistence,
manifest, and activation-boundary stages. The archived active production package
remained independently readable. Candidate active-pointer row count remained zero.

The V7 stage runtimes were 603.94 seconds for the failure-injected first apply,
211.96 seconds for the full no-change replay, and 279.26 seconds for the independent
clean-copy apply. Canonical storage grew from 372,228,096 to 636,272,640 bytes and
analysis storage from 1,152,614,400 to 1,528,291,328 bytes: 639,721,472 bytes of
persistent candidate growth in total. The preflight copy-space gate required
9,789,456,384 bytes and 365,753,217,024 bytes were free.

SQLite used transient DELETE-mode rollback journals and left no WAL or journal
sidecar on either completed candidate. V7 did not sample transient journal size
during the transactions, so a defensible peak-byte figure is unavailable. This is
reported rather than estimated. Phase 12E must monitor the transient WAL/journal
peak during its pre-deployment rehearsal and preserve the 9.79 GB minimum gate plus
operator margin. Based on the measured first-apply time, reserve at least a
20-minute locked production maintenance window before independent no-op and smoke
verification time; remeasure on the production host at preflight.

Production preflight and postflight differ only in the mtime of a content-identical
SQLite SHM sidecar created/touched by read-only inspection. Its size and SHA-256 are
unchanged. Main database bytes, schemas, rows, mtimes and hashes; WAL content;
active pointers; Scheduler configuration; Relative Valuation snapshot; and report
files remain unchanged. A sidecar size/hash change is not permitted by the gate.

## Phase 12B Replay

The locked Phase 12B contract was replayed without changing periods or gates. The
contract fingerprint remained unchanged. The rebuilt source fingerprint is
`402abff41586358b412f111fda297369b5a1011c5c28e4ffdb7fe308176d661a`
and the deterministic sample fingerprint is
`1ddb68c9cfaebd6b9e047c3596ad68c06cdf292eafb2327a038f8ad83d305308`.

Across all 87,319 endpoints, LABEL_READY counts are 84,314 at 21 sessions, 82,773
at 42 sessions, and 82,620 at 63 sessions. There are 464 unresolved price identities;
these are research-label exclusions and not unresolved canonical identities.

The 2021-2023 development attrition is:

| Gate | Rows | Companies | Signal months |
| --- | ---: | ---: | ---: |
| All endpoints | 28,226 | 2,430 | 37 |
| 63-session label ready | 27,390 | 2,406 | 37 |
| SCORE_FULL | 22,146 | 2,109 | 36 |
| VALUATION_FULL | 15,629 | 1,968 | 29 |
| Delta 2Q ready | 14,878 | 1,886 | 29 |
| Lifecycle ready | 14,878 | 1,886 | 29 |
| Eight-flag diagnostic coverage | 14,878 | 1,886 | 29 |
| Identity and price gates | 14,878 | 1,886 | 29 |
| Purge and embargo | 13,051 | 1,870 | 26 |

The sample gate now passes, so only the preregistered H1-H8 analyses and fixed B0-B4
baselines ran. The locked result is `OUTCOME_B`: no hypothesis has repeated evidence,
and no later ML or production prediction model is authorized. Results remain
revised-history exploratory evidence.

## Remaining Decision

Phase 12E must decide and explicitly authorize the ordering of package activation
and a separate Relative Valuation refresh. The old Relative Valuation snapshot must
not be silently combined with the enlarged package. The broad 6,568-ticker
historical-only universe, prospective PIT collection, report redesign, and model
changes remain outside scope. Capturing a transient rollback-journal peak is also a
mandatory Phase 12E pre-write gate because Phase 12D has no defensible peak figure.
