# Phase 13G.3.8 - Source Removal Rolling-Window Audit

## 1. Purpose

This phase audits the 11 `SOURCE_REMOVAL` tickers in the accepted Refresh
Preview. It is read-only analysis. It does not change Refresh behavior.

The result is recommendation **A: implement retention before the first live
Refresh Test**. Ten ticker-level cases are rolling-window expiry; one case is a
genuine interior source-key removal. Treating both kinds alike would discard
previously accepted history and conflict with the existing provider retention
contract.

## 2. Accepted Preview Basis

- Run: `20260920T085848Z_refresh_fundamentals_0fb542ea4f44`
- Refresh-set fingerprint:
  `2fea98011b0268c9b714aa7abd4fcc03c7808d475ff2fda0399402caee2c0491`
- Discovery rows / source tickers: `545 / 269`
- Effective changed known / unknown / review required: `71 / 191 / 0`
- State: `BOOTSTRAP_BASELINE`; no published watermark
- Preview observed source maximum: `2026-09-20`

The accepted JSON supplies exact removed keys, complete-history counts and
fingerprints. Production provider winner rows supply the prior payload and
ordering. No new API request or Preview was needed. For removal cases, key-set
chronology is exact even where IPDN and JAGX also contain common-key revisions.

## 3. Source Removal Population

| Ticker | Canonical latest | Sharadar latest | ARQ old/new | MRQ old/new | Added | Changed | Removed |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| ABM | 2026 Q3 | 2026 Q3 | 41/40 | 41/40 | 0 | 0 | 2 |
| BNED | 2027 Q1 | 2027 Q1 | 40/39 | 41/40 | 0 | 0 | 2 |
| CASY | 2027 Q1 | 2027 Q1 | 41/40 | 41/40 | 0 | 0 | 2 |
| DDS | 2027 Q2 | 2027 Q2 | 41/40 | 41/40 | 0 | 0 | 2 |
| DELL | 2027 Q2 | 2027 Q2 | 41/40 | 41/40 | 0 | 0 | 2 |
| DLTH | 2027 Q2 | 2027 Q2 | 41/40 | 41/40 | 0 | 0 | 2 |
| GIII | 2027 Q2 | 2027 Q2 | 41/40 | 41/40 | 0 | 0 | 2 |
| IPDN | 2026 Q2 | 2026 Q2 | 41/40 | 41/40 | 0 | 80 | 2 |
| IRM | 2026 Q2 | 2026 Q2 | 41/40 | 41/40 | 0 | 0 | 2 |
| JAGX | 2026 Q2 | 2026 Q2 | 42/41 | 41/40 | 0 | 57 | 2 |
| NAMS | 2026 Q2 | 2026 Q2 | 23/22 | 22/22 | 0 | 0 | 1 |

## 4. Exact Removed Rows

The complete 21-row inventory, true source identities, prior `lastupdated`,
semantic fingerprints and canonical date state are in
`phase13g3_8_source_removal_audit.csv`.

There are 11 removed ARQ rows and 10 removed MRQ rows. Every removed source row
maps to an existing stable canonical quarter. The 20 boundary rows have period
ends from `2016-06-30` through `2016-07-31`. The sole interior row is NAMS ARQ
`(NAMS, ARQ, 2022-11-28, 2022-06-30)`, fiscal `2022-Q2`.

## 5. ARQ/MRQ Pairing

- Paired ARQ+MRQ removals: `10`
- ARQ-only removals: `1` (NAMS)
- MRQ-only removals: `0`
- More complex removal groups: `0`

Thus `Removed = 2` means two source rows but one canonical fiscal quarter in
all ten paired cases.

## 6. Position in History

All ten paired ARQ rows and their paired MRQ rows are ordinal position 1: the
oldest row. No older row remains and 39-41 newer rows remain. Removing them
advances the minimum report period by one quarter while leaving the maximum
unchanged.

NAMS is different. Its removed ARQ row is position 10 of 23, with nine older
and thirteen newer rows. The old and new minima both remain `2020-10-07`.
Another ARQ key dated `2022-10-13` and an MRQ row still represent fiscal
`2022-Q2`; canonical `first_public_result_date` and `source_availability_date`
are both `2022-10-13`.

## 7. Rolling-Window Evidence

The 20 boundary source rows are approximately 10.14-10.22 years old at the
Preview timestamp. Their new minima are the immediately following fiscal
quarter. Current ARQ/MRQ histories generally contain about 40 quarters, while
the exact counts vary from 39 to 41 as expected from source-key and fiscal
calendar differences.

The clustering is exact: ten unrelated tickers lose their oldest ARQ and MRQ
pair at the same June/July 2016 boundary. This strongly supports an empirical
rolling approximately ten-year source window. The Preview did not advance the
latest fiscal quarter for these tickers, so a same-run new-quarter arrival is
not required for the boundary to move.

NAMS is only 4.23 years old, is not at the boundary, and preserves older source
rows. It is therefore evidence that genuine source-key removal also exists.

## 8. Control Tickers

ASX is a control from the accepted Preview: its complete source response has
43 ARQ and 38 MRQ rows, no removals, and an oldest ARQ report period of
`2016-12-31`. Stored provider controls show the same near-ten-year boundary:

| Ticker | ARQ rows/range | MRQ rows/range |
| --- | --- | --- |
| AAPL | 41, 2016-06-25 to 2026-06-27 | 40, 2016-09-24 to 2026-06-27 |
| NVDA | 41, 2016-07-31 to 2026-07-26 | 41, 2016-07-31 to 2026-07-26 |
| MSFT | 41, 2016-06-30 to 2026-06-30 | 41, 2016-06-30 to 2026-06-30 |
| IBM | 41, 2016-06-30 to 2026-06-30 | 41, 2016-06-30 to 2026-06-30 |
| KO | 41, 2016-07-01 to 2026-07-03 | 41, 2016-07-01 to 2026-07-03 |

Only ASX was freshly fetched in the accepted Preview; the other controls are
stored effective provider histories. They support the boundary pattern but are
not presented as current API responses. Row count alone is not a classifier.

## 9. License/Repository Evidence

Repository evidence is stronger than a mere inferred preference:

- `sharadar_history_policy.py` sets `MINIMUM_HISTORY_YEARS = 10` and
  `RETENTION_MODE = APPEND_ONLY_NO_WINDOW_PRUNING`.
- Its contract says `absence_from_later_snapshot_authorizes_deletion = False`
  and `minimum_history_is_cleanup_cutoff = False`.
- Phase 12C.2 says older observations may remain and a row absent from a later
  snapshot remains stored.
- Phase 12C retained 84 prior base-period keys absent from its new snapshot.

No repository or API metadata proves the vendor's contractual cutoff mechanics.
The rolling-window conclusion is therefore empirical, while RawCandle's local
append-only retention requirement is explicit. No public web research was
needed.

## 10. Proposed Classification Contract

`AGED_OUT_OF_SOURCE_WINDOW` requires all of the following: the missing ARQ row
is the oldest prior ARQ row; no older current-window ARQ observation remains;
the new minimum advances at the observed rolling boundary; and paired MRQ
behavior is consistent when MRQ exists. Row count or age alone is insufficient.

`TRUE_SOURCE_REMOVAL` applies when a missing key is interior to the accessible
history, older observations remain, and complete source evidence is trusted.
An alternate source key for the same fiscal quarter does not negate the key
removal; it determines whether canonical quarter deletion follows.

`AMBIGUOUS_SOURCE_REMOVAL` applies whenever boundary position, complete-history
authority, fiscal identity, pairing, or source continuity is insufficient.
It must remain fail-closed as `REVIEW_REQUIRED`.

## 11. Recommended Retention Term

Use `RETAINED_OUTSIDE_SOURCE_WINDOW`. It says both why the source no longer
returns the row and why RawCandle still stores it. The retained value means the
last authoritative version observed before expiry, not current Sharadar data
or a guaranteed forever-final value.

## 12. Provider Implications

Current `replace_provider_histories()` deletes every ARQ/MRQ observation for a
changed ticker before inserting only the newly fetched histories. Retention
therefore needs explicit merge logic before that destructive replacement:

`retained boundary history + current authoritative window history`.

Current-window keys and values remain authoritative. Interior removals remain
deletable. The existing `provider_observation.provenance_json` can record a
`RETAINED_OUTSIDE_SOURCE_WINDOW` status, so a new schema column is not required.
Persisted provenance is preferable to run evidence alone because later runs
must distinguish already-retained rows from current source rows without
reclassifying them as fresh removals each time.

## 13. Canonical Implications

The canonical fresh rebuild clears derived quarter state and reconstructs it
from provider ARQ winners while preserving identity tables. If provider retains
aged-out ARQ rows, the existing rebuild naturally reconstructs those quarters.
No separate stale canonical-row exception should be added. True removals still
flow through provider winners and can remove a canonical quarter only when no
other accepted ARQ row represents that stable fiscal identity.

## 14. first_public_result_date Implications

For retained quarters, preserve the established date and last accepted source
data; retention is neither a revision nor a new publication. The current
pre-clear preservation map already carries dates by stable
`(company_id, fiscal_year, fiscal_quarter)` identity. For a true quarter
removal, its prior date belongs only in deletion evidence, not in a stale row.

## 15. TTM / Historical Research Implications

Current replacement semantics would gradually remove oldest canonical quarters,
their old TTM endpoints and reproducible historical V2 research inputs.
Retention allows RawCandle to accumulate beyond the accessible source window.
No V2/RP/RV code was found to require that every historical provider row remain
currently retrievable; those engines consume rebuilt canonical/TTM state.

## 16. Limitations

The accepted Preview did not retain full current financial payload snapshots,
but it retained trusted complete-history fingerprints, counts and exact changed
keys. That is sufficient for key removal, chronology and pairing because the
prior provider winners remain available. This audit does not independently
prove Sharadar license language, and corrections after a row leaves the source
window cannot be observed under the current entitlement.

## 17. Production Safety

Preflight and postflight file identities are identical:

| Role | SHA-256 | Bytes | mtime_ns |
| --- | --- | ---: | ---: |
| provider | `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468` | 958828544 | 1789831083995864659 |
| canonical | `bee62a677777be63ce67737d9e77d375f22dd044b6a7c9c834ccbe7b9f1684cf` | 655724544 | 1789893262044507282 |
| analysis | `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2` | 902062080 | 1789831394579542627 |

No API request, candidate database, Test copy, backup, publication journal or
watermark write was created by this phase.

## 18. Recommendation

**A - Implement retention before first live Test.** Classify and retain the ten
boundary ARQ/MRQ pairs, while permitting the NAMS interior source key to be
removed. Keep ambiguous cases fail-closed. Running the current Test first would
exercise behavior already shown to violate the established history policy.

## 19. Next Phase

Implement and test boundary classification, retained/current history merge,
durable provider provenance, repeated-run stability, true interior deletion and
ambiguous fail-closed behavior. Then create a new Preview because the accepted
Preview's classification semantics will have changed. Do not reuse its Test
authorization.

## 20. Git

Baseline: `78c8ce2 fix: correct refresh publication date reporting`.
This phase adds only this report and its lightweight CSV evidence. Refresh Test
on copies was NOT executed.

## Aggregate Findings

- SOURCE_REMOVAL tickers: `11`
- Removed source rows: `21` (`11` ARQ, `10` MRQ)
- Paired ARQ+MRQ groups: `10`
- Oldest-edge rows: `20`; interior rows: `1`
- Tickers classified aged-out / true-removal / ambiguous: `10 / 1 / 0`
- Source rows classified aged-out / true-removal / ambiguous: `20 / 1 / 0`

## Representative Deep Dives

- **BNED:** old boundary `2016-07-30` -> removed ARQ `2016-09-08`
  plus MRQ `2016-07-30` -> new boundary `2016-10-29`. Both removals were the
  oldest rows. Interpretation: aged out.
- **ABM:** `2016-07-31` -> paired oldest removal -> `2016-10-31`; aged out.
- **IRM:** `2016-06-30` -> paired oldest removal -> `2016-09-30`; aged out.
- **IPDN:** `2016-06-30` -> paired oldest removal -> `2016-09-30`; aged out,
  independently of its 80 same-key financial revisions.
- **JAGX:** `2016-06-30` -> paired oldest removal -> `2016-09-30`; aged out,
  independently of its 57 same-key financial revisions.
- **NAMS:** old boundary remains `2020-10-07`; interior `2022-Q2` ARQ key dated
  `2022-11-28` disappears while nine older rows and alternate `2022-Q2` ARQ/MRQ
  evidence remain. Interpretation: true source-key removal, no canonical-quarter
  deletion.
