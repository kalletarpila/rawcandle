# Provider payload completeness — STOP at current-state audit

Task: `FUNDAMENTALS-PROVIDER-PAYLOAD-COMPLETENESS-HARDENING`.
Audit date: 2026-10-29. Source baseline: `65e158c9d29545479abaad02f4eac2484b2b4e43`.
Proposed policy: `PROVIDER_PAYLOAD_COMPLETENESS_V1` — **NOT IMPLEMENTED / NOT ENABLED**.

## Decision

**STOP: systemic legacy payload loss remains in the active provider population.** There are **13,113 exact reduced-projection observations across 181 tickers**, about 6.8% of 192,986 retained provider observations. Every one lacks sharefactor, equity, equityusd, price, marketcap and pb. This is larger than the three previously repaired current GE/RTX/T observations.

The task explicitly requires:

> STOP and report if … current population reveals large systemic incompleteness requiring bulk remediation

Its rollout gate also requires that no systemic historical payload-loss population needing separate cleanup be discovered. These gates did not pass. No production source/UI/test implementation, new metadata, profile enforcement, configuration change or live repair was made. Only this report is committed. Existing safety guards remain active and unchanged.

A separately scoped remediation/backlog phase is needed before this task's healthy-population rollout criterion can pass. This is **not authorization to mass-repair now**. The current audit identifies a backlog and does not establish that all those rows can or should immediately be repaired. In particular, retained/absent source keys need their own authoritative evidence; current missing facts must never be filled from historical assumptions or default factor 1.0.

**Immediate bulk historical repair required: NO. Separate backlog disposition required: YES.** No current automatic ownership candidate needs an emergency bulk repair. That does not satisfy the requested healthy-population gate or resolve the independently reproduced freeze loss-classification gap.

## Scope and current runtime

Read-only inspection covered acquisition and raw-row handling in `providers/sharadar.py`; bulk/generic staging in `schema/production_bootstrap.py` and `admin/batch_add_tickers.py`; Refresh normalization/acquisition/comparison/replacement; the controlled payload repair workflow; P/B source extraction and V1 automatic eligibility; and historical freeze V1. No broad historical artifact search or new upstream acquisition was performed.

Active generation: `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`.
Published source watermark: **2026-10-28**.
Journal: **COMPLETED / PASSED / NOT_REQUIRED**.

The impact audit held existing admin/production locks and a compatible shared scheduler read lock, opened data using SQLite `mode=ro`, and compared source/financial/queue/config/input snapshots before and after. It did not invoke native live Preview, queue synchronization, ownership reconciliation or publication.

## Population inventory

| Observation | Count |
| --- | ---: |
| Retained physical provider observations in active provider DB | 192,986 |
| Distinct exact source keys, all six retained dimensions | 192,316 |
| ARQ / MRQ observations | 92,617 / 93,323 |
| ART / MRT / ARY / MRY observations | 2,814 / 2,540 / 967 / 725 |
| SF1 full-shaped payloads containing the known SF1 field set | **179,873** |
| Payloads with 112 / 113 keys | 167,383 / 12,490 |
| Exact legacy 29-key financial projection payloads | **13,113** |
| Exact source keys represented only by those legacy payloads | **13,113** |
| Legacy ARQ / MRQ observations | 6,556 / 6,557 |
| Tickers with legacy payloads | **181** |
| Frozen accepted financial rows bound to legacy observations | **5,231** |
| Frozen accepted rows bound to full-shaped observations | 69,406 |
| Latest accepted quarterly source bindings with legacy payloads | **173** |
| Latest quarterly source bindings with full-shaped payloads | 2,367 |
| Legacy rows marked retained outside source window | **342** |
| Legacy rows without stored provider security ID | **0** |
| Legacy-producing retained provider-run records | **22** |

“Full-shaped” means the retained object contains the existing known SF1 keys. It is **not proof of an exact original upstream capture**, because no independent acquired-key manifest/completeness envelope is retained. Unknown provider fields could not be reconstructed or certified retrospectively. No `PROVIDER_PAYLOAD_COMPLETENESS_V1` evidence has been backfilled into any observation.

The legacy source periods span **2015-05-28 through 2026-09-30**. Their fetched timestamps span **2026-09-20T16:53:30Z through 2026-10-29T05:46:16Z**. A later fetched timestamp can reflect carrying retained old observations forward; it does not prove a new upstream full acquisition or newly introduced loss on that date.

The largest retained producing run is `REFRESH_COPY_1b15962881816034da6b` (5,209 rows, `PHASE13G3_10_SHARADAR_REFRESH_RETENTION_COPY_TEST_V1`). The other affected retained runs also identify the ordinary ARQ/MRQ complete-history replacement path, including later contract versions. The shape matches exactly `REFRESH_REQUEST_FIELDS`, rather than an arbitrary provider nullable-data pattern.

### Missing keys versus explicit null

| Field | ABSENT | JSON null | Empty string | Present nonempty value |
| --- | ---: | ---: | ---: | ---: |
| sharefactor | **13,113** | 0 | 0 | 179,873 |
| equity | **13,113** | 0 | 1,987 | 177,886 |
| equityusd | **13,113** | 0 | 1,987 | 177,886 |
| price | **13,113** | 0 | 7,734 | 172,139 |
| marketcap | **13,113** | 0 | 7,745 | 172,128 |
| pb | **13,113** | 0 | 7,920 | 171,953 |
| sharesbas | 0 | 151 | 2,329 | 190,506 |

Among full-shaped payloads, **7,920** have at least one empty/null dependency among the seven ownership/P/B numerical inputs; **171,953** have all seven nonempty. These are raw source states, not a claim of financial usability, ordinary ownership eligibility or capture loss. Explicit-null business values must not be counted as absent-key loss.

Raw `permaticker` is absent from 180,496 observations and is not a universal SF1 raw-payload requirement. Stored `provider_security_id` is absent from 153,126 observations; company/security headers themselves are present. Existing identity resolution also uses separate provider metadata and canonical mappings. A future bounded profile must preserve and verify that exact identity evidence rather than declaring all ordinary bulk rows corrupt or fabricating a raw permaticker.

All **185,939 publication-date-valid ARQ/MRQ rows** checked have matching raw-versus-native normalized projections. The Refresh normalizer intentionally does not support the 7,046 retained non-ARQ/MRQ observations. One additional ARQ candidate fails `FILING_DATE_BEFORE_REPORT_PERIOD`; the existing publication-authority resolver disqualifies that candidate. These distinctions are not additional discovered ingestion-loss rows.

### Profile audit, not implemented profiles

These are observational key-coverage checks, not new production V1 profiles. Presence does not mean every field must be non-null.

| Audit dependency set | Required keys present | Missing keys |
| --- | ---: | ---: |
| Base normalized financial projection | 192,986 | 0 |
| Ownership/P/B: base keys plus factor/equity/price/marketcap/pb inputs | 179,873 | 13,113 |
| Freeze conflict evidence: base keys plus equity/equityusd/sharefactor | 179,873 | 13,113 |
| Fresh full-source repair evidence: base and P/B source keys | 179,873 | 13,113 |

Original acquired-key-set verification remains unavailable for existing rows, even when these keys are present. The repair row's old side may legitimately be incomplete: that is the exact target of a controlled evidence repair, not permission to substitute financial values.

## P/B current-state effect

Read-only `detect` and V1 `partition` returned **0 fresh continuation candidates**, **0 AUTO_CONTINUE**, **0 manual**, and **0 deep-review candidates**. There are **0 active ownership queue cases**. Queue terminal states remain **10 PUBLISHED + 3 SUPERSEDED**.

Consequently, **0 current candidate cases are blocked solely by completeness**. This does not mean the legacy population is eligible: 13,113 observations fail the source-key dependency check, including 173 latest accepted source bindings. Most provider observations do not independently constitute an ownership continuation candidate with a previously reviewed basis.

GE, RTX and T remain **PUBLISHED**. Their already repaired/published current decisions were not reopened. Older legacy observations remain for these tickers: **GE 84, RTX 83, T 84**. A repair of one current exact observation did not repair an entire ticker history.

Existing V1 already blocks missing factor/source evidence with `SOURCE_PAYLOAD_INCOMPLETE` and checks complete known SF1 keys plus identity, category, provenance, factor and valuation evidence. It never fills absent/null factor with 1.0. That existing protection is preserved; no automatic continuation or publication was run to test it against live data.

## Acquisition/ingestion audit and remaining lossy entry points

1. **Provider client:** `SharadarClient` retains record dictionaries and supports an optional `fields` parameter. Discovery intentionally requests a small discovery projection. That discovery response must never be promoted into authoritative full financial acquisition evidence.
2. **Normal Refresh acquisition:** `fetch_complete_history` now requests complete ARQ/MRQ responses without a `fields` projection. `validate_complete_history` keeps `_acquisition_payload` alongside normalized financial fields. However, its `COMPLETE` status proves history-row validation/coverage, not full original capture completeness. It accepts a 29-key record that satisfies the normalized contract. Its fallback acquisition-dictionary construction also filters leading-underscore keys, which is not a safe general guarantee for preserving arbitrary future upstream fields.
3. **Refresh replacement fallback:** `replace_provider_histories` serializes `_acquisition_payload` when provided but falls back to the normalized `item`. A caller supplying normalized-only rows can still recreate the old payload representation. There is no captured upstream-key manifest against which to reject that loss immediately.
4. **Bulk/archive ingestion:** CSV dictionaries preserve complete available headers/values, and `insert_production_sharadar_observation` serializes the complete supplied dictionary separately from the relational normalized projection. But it cannot prove its input dictionary was itself a full source record rather than a prior projection.
5. **Local-provider reuse:** `_local_provider_rows` returns rows from the normalized `sharadar_fundamental_observation` table. Generic staging passes supplied row dictionaries to the production inserter. A normalized local-cache row must not be treated as independently acquired full raw evidence. Generic staging can also enrich ticker/permaticker using resolver metadata; that enrichment needs provenance separate from original raw fields.
6. **Repair acquisition:** the controlled repair preserves exact supplied `_acquisition_payload`, but `HistoryTrust.COMPLETE` alone does not certify faithful original full capture. A future repair profile must attest source capture separately, while retaining exact old/new binding and financial protections.

The old defect class is therefore still possible at entry points accepting projected dictionaries. Current full network acquisition fixes the common route, but no uniform full-capture contract rejects every lossy caller path.

### Hash conventions and absent/null gap

Provider rows use multiple established content-hash conventions. **178,372** stored content hashes match the complete payload hash used by the existing payload helper; **14,614** use another existing convention, including normalized/source-record hashing. These differences are not evidence of tampering by themselves. A new complementary completeness hash must identify its own serialization and bind both raw and normalized identities instead of reinterpreting all old content hashes.

The existing `SHARADAR_ACQUISITION_PAYLOAD_V1` helper preserves raw key absence versus JSON null and exposes a raw payload fingerprint. Its completeness hash describes states of present keys, rather than a complete versioned profile/acquisition envelope. Its `field_state({'sharefactor': ''}, 'sharefactor')` returns **VALUE**, while native numerical acceptance treats empty string as null. This requested semantic alignment is not yet implemented.

## Historical freeze interaction

Frozen canonical values remain protected by existing holds and candidate checks. However, source-capture loss is not currently distinguished reliably from source truth in the freeze reason classification.

A pure read-only reproduction used an actual accepted frozen financial/source snapshot and a **synthetic local projection-loss copy** of its incoming payload. Removing sharefactor/equity/equityusd/price/marketcap/pb produced `FROZEN_PROVIDER_CONFLICT_HELD` with `ECONOMIC_SOURCE_FACTOR_CHANGED` and `FINANCIAL_PAYLOAD_CHANGED`, rather than `SOURCE_PAYLOAD_INCOMPLETE`. No upstream change was asserted and no provider/canonical row was written.

Thus preserving canonical values works, but the requested loss-aware interpretation does not. **5,231** current accepted frozen rows have incomplete source capture for these dependencies. The audit does not assert that 5,231 live conflicts currently exist: future full evidence acquisition could change their interpretation, and their missing original facts cannot safely be guessed. Missing capture must not be “fixed” by suppressing real provider revisions or weakening the existing freeze.

## Existing source repair boundary

The controlled payload repair already binds exact source key, old observation ID/hash, resolved company/security/provider identity, complete supplied new payload hash, restored/removed fields, before/after helper completeness fingerprints, source fetch timestamp, unchanged normalized financial fingerprints, baseline generation/role hashes, copy receipt and explicit authorization. Receipts cannot authorize an arbitrary financial override. Ownership approval/publication remains a separate native step.

This contract does not automatically cover the whole backlog. The **342 retained-source observations** have nonempty retention provenance and are explicitly rejected by the ordinary payload repair guard. Their exact historical source keys may no longer be returned. The remaining **12,771** unretained rows are not automatically eligible either: fresh exact source identity, authoritative payload, no financial drift and all native receipt gates must be revalidated individually.

Adding future completeness metadata to provenance also needs careful compatibility work: existing repair checks reject nonempty provenance for reviewed/retained observations. A new capture envelope cannot silently bypass that check or turn it into a generic override. No repair, registration, approval, backfill or publication was attempted here.

## Validation, rollout and follow-up boundary

**162 existing-contract focused tests PASS**:

- `tests/test_provider_payload_completeness.py`
- `tests/test_provider_payload_workflow.py`
- `tests/test_pb_ownership_auto_continuation.py`
- `tests/test_fundamentals_historical_freeze.py`

These verify the existing exact-source repair, missing-factor guard, immutable copy workflow and freeze behavior. They do **not** constitute acceptance of the proposed new completeness policy. The requested 15-scenario new-policy copy rehearsal is **NOT RUN / acceptance gate not passed**, because implementation stopped at the systemic-loss gate. No full test suite was run.

Required follow-up is a separately scoped source-evidence backlog disposition: preserve exact observation IDs/source keys; distinguish current versus retained/historical observations; identify authoritative recoverable upstream/archive evidence; retain GE/RTX/T terminal decisions; and define approved cohorts with fresh exact receipts. Future-only hardening may be separated from that backlog only under an explicitly revised rollout scope acknowledging the discovered population. No factor defaults, mass repair, global JSON rewrite, new canonical store or historical version graph is appropriate.

**Rollout: STOPPED.** `PROVIDER_PAYLOAD_COMPLETENESS_V1` remains a proposed name, not a deployed contract. No production/UI/test source was changed. Historical freeze V1, P/B V1, WFRD, publication authority, scheduler configuration/locking and immutable-generation journal/recovery remain unchanged. No backups or evidence were deleted. No push was performed.

Detailed local audit evidence is excluded under `temp/fundamentals_payload_completeness_20261029/`: initial population/key-state inventory, impact/profile audit, all affected frozen identities, producing run summary, native-loss classification reproduction and focused test log. Runtime DBs, queues, journal, generations, scheduler config and unrelated OHLCV/research worktree artifacts are excluded from the commit.

Final post-test non-mutation verification: **PASS**, 2026-10-29T21:22:26Z. Active generation, watermark, all financial role hashes, queue content, journal, market/research inputs, scheduler configuration and production source exactly match the initial task snapshot. New policy enabled: **NO**.
