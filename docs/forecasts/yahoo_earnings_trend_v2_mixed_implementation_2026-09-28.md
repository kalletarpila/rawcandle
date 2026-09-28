# Yahoo earningsTrend V2 mixed-row implementation (2026-09-28)

## 1. Purpose

Yahoo returns a proven `earningsTrend` shape in which complete, targeted estimate
rows coexist with exact empty placeholders. V1 correctly requires every row to
have a string `endDate`, so it rejected the complete payload when an empty row
had a null or missing target. V2 accepts only this observed mixed shape; it is
not a generic sparse-target contract.

Contract version:

`yahoo_earnings_trend_v2_mixed_empty_targets`

## 2. Eligibility and classification order

The deterministic acquisition order is:

1. A structurally valid payload whose rows are all exact approved empty
   templates is `VALID_NO_DATA`.
2. A normal payload without exact empty rows follows unchanged V1 parsing and
   becomes V1 `SUCCESS_WITH_DATA` when valid.
3. A payload containing both one or more `USABLE_TARGETED` rows and one or more
   exact `EMPTY_PLACEHOLDER` rows follows V2 and becomes
   `SUCCESS_WITH_DATA`.
4. Any target or structural violation remains
   `MALFORMED_OR_SCHEMA_MISMATCH`.

`USABLE_TARGETED` requires a string `period`, an ISO `endDate`, and at least one
accepted non-placeholder semantic value. `EMPTY_PLACEHOLDER` uses the existing
exact predicate without fuzzy matching. Every V2 row is explicitly classified.
A row matching neither class rejects the payload.

## 3. Canonical payload and hashes

V2 preserves module methodology, all provider rows in source order, zero-based
occurrence index, provider horizon, `endDate` field state, row classification,
and all accepted semantic states and values. Null and missing `endDate` remain
distinct as `EXPLICIT_NULL` and `FIELD_ABSENT`. Formatting-only fields remain
outside semantic identity.

The V1 canonicalizer was not changed. The frozen AAPL V1 fixture still hashes
to:

`9fa358243e2c0496622517895f9de8d4c0ae1214ce48f7d099dad981af3343ef`

The four V2 fixture hashes are deterministic:

| Fixture class | V2 semantic hash |
|---|---|
| ATLX, null `0q` | `6edde3f98be193b04396895b967960b902a82d64b42b7fd519a758fd5c525f0e` |
| BIVI, null `+1q` | `9625eb3de1f38acaec4aaad6b079ac6e24c2d2bf59a7b3398723d46ac024f94f` |
| BHP, null `0q/+1q` | `6109cd5f8a47ad713a9c4cd2e4203dedcc4003cef57c0a0c8401469f378a533e` |
| BTCT, null `0q/+1q/+1y` | `dd1a7c0d7d0ad5a9a1f9bcb873a3adb6c1012a71348ce494efc6fd3c9570d207` |

## 4. Persistence and linker handoff

The existing schema is sufficient. A V2 observation creates one immutable
snapshot with the V2 contract version. Only `USABLE_TARGETED` rows become
`forecast_estimate` records; each keeps its original occurrence index and its
validated target date. `EMPTY_PLACEHOLDER` rows create no normalized records.

The fiscal linker algorithm is unchanged. It reads distinct normalized
occurrences, so only usable rows create link attempts. No target, fiscal year,
or fiscal quarter is inferred for an empty row. The ATLX temporary end-to-end
case created one link attempt for occurrence 2 and resolved it as `UNRESOLVED`
under its deliberately minimal fiscal context; empty occurrences created no
attempts.

## 5. PIT and historical compatibility

The complete V2 canonical provider snapshot is known at `fetched_at`, while
targeted fiscal queries expose only its complete normalized rows. Existing
change-only snapshot behavior remains intact: equivalent V2 observations reuse
the snapshot and become `SUCCESS_UNCHANGED`.

No historical row is reparsed or rewritten. The production database still has
the 33 affected malformed fiscal-estimate fetches and 11 distinct raw evidence
hashes. A future observation may validly be V2 success even when an identical
historical raw body records the parser contract that existed earlier.

## 6. Fixtures and tests

The implementation reuses only these investigation fixtures:

- `mixed_empty_missing_enddate_0q_atlx.real_compact.json`
- `mixed_empty_missing_enddate_1q_bivi.real_compact.json`
- `mixed_empty_missing_enddate_0q_1q_bhp.real_compact.json`
- `mixed_empty_missing_enddate_0q_1q_1y_btct.real_compact.json`

The focused suite covers all four classifications and normalization shapes,
source order, null/missing target states, deterministic hashes, V1 compatibility,
whole-payload no-data, incomplete usable targets, unknown fields, changed versus
unchanged snapshots, PIT lookup, historical malformed isolation, and existing
linker handoff. The focused subset passed 53 tests, and the complete relevant
forecast/Yahoo suite passed 124 tests. Persistence tests use temporary databases.

## 7. Live verification

One serial read-only raw probe ran on 2026-09-28 with normal pacing. All requests
succeeded on their first attempt and all symbols selected V2:

| Symbol | Usable rows | Empty rows | Result |
|---|---:|---:|---|
| ATLX | 1 | 3 | `SUCCESS_WITH_DATA` |
| BHP | 2 | 2 | `SUCCESS_WITH_DATA` |
| BIVI | 2 | 2 | `SUCCESS_WITH_DATA` |
| BTCT | 1 | 3 | `SUCCESS_WITH_DATA` |
| CBL | 1 | 3 | `SUCCESS_WITH_DATA` |
| JBGS | 2 | 2 | `SUCCESS_WITH_DATA` |
| NFE | 2 | 2 | `SUCCESS_WITH_DATA` |
| NUWE | 1 | 3 | `SUCCESS_WITH_DATA` |
| SIDU | 1 | 3 | `SUCCESS_WITH_DATA` |
| SIGA | 2 | 2 | `SUCCESS_WITH_DATA` |
| VEEE | 1 | 3 | `SUCCESS_WITH_DATA` |

Total: 11 V2 payloads, 16 usable rows, 28 exact empty placeholders, no malformed
payloads, no retries, and no writes.

## 8. Production verification decision

No targeted production acquisition was performed. Temporary-database tests
proved parser, immutable snapshot, normalization, change detection, PIT, and
linker behavior end to end, while the read-only live probe proved that all 11
current provider payloads still match the reviewed contract. A production write
would not add a missing proof and would unnecessarily add observations during
implementation. Production remained at 6 runs, 22,587 fetches, and 7,353
snapshots, with `PRAGMA quick_check = ok`.

## 9. Remaining unsupported case

A semantically usable row with a missing, null, non-string, or invalid ISO
`endDate` remains malformed. V2 does not invent target metadata or create
unresolved sparse estimate records. Full-universe coverage is unchanged until a
normal future universe run observes the new contract.
