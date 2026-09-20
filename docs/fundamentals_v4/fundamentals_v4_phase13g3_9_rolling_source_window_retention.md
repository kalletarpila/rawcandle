# Phase 13G.3.9 - Rolling Source-Window Retention

## 1. Outcome

Refresh Fundamentals now distinguishes source-window expiry from genuine source-key removal. A single deterministic classifier and provider merge feeds Preview, Test candidate construction, and Production candidate construction. The phase stopped after one new live read-only Preview; no live Test or Production was run.

## 2. Prior Audit Basis

Phase 13G.3.8 found ten paired oldest-boundary removals and one interior NAMS removal in Preview `20260920T085848Z_refresh_fundamentals_0fb542ea4f44`. That Preview is obsolete for authorization because this phase changed source-history semantics.

## 3. History Policy

The implementation reuses `MINIMUM_HISTORY_YEARS = 10` from `sharadar_history_policy.py`. It introduces no second retention period. A trusted complete response may age out a contiguous oldest source-backed prefix; row counts alone never authorize retention.

## 4. Source-Key vs Fiscal-Quarter Identity

Retention is keyed by the established true source identity `(ticker, dimension, date, reportperiod)`. Fiscal `(company_id, fiscal_year, fiscal_quarter)` identity remains a separate canonical contract. Removing one source key does not imply deleting a fiscal quarter when another accepted ARQ winner survives.

## 5. Detection Classifications

- `AGED_OUT_OF_SOURCE_WINDOW`: safe oldest-prefix expiry, retained in provider history.
- `TRUE_SOURCE_REMOVAL`: an interior missing key, removed from the provider candidate.
- `AMBIGUOUS_SOURCE_REMOVAL`: insufficient or contradictory evidence; the ticker is `REVIEW_REQUIRED`.
- `RETAINED_OUTSIDE_SOURCE_WINDOW`: durable provider state for a previously accepted row that is no longer returned in the accessible source window.

## 6. Persisted Retention State

Existing `provider_observation.provenance_json` is sufficient; no schema migration was needed. It stores the retention status and compact boundary/source/fiscal evidence. Subsequent reads distinguish current source-backed rows from retained-only rows.

## 7. Boundary Classification

A new absence is retainable only after complete-history trust passes and the row is in the contiguous oldest prefix, the new source minimum starts strictly later, chronology is coherent, and the source maximum satisfies the existing ten-year rule. Multiple qualifying prefix rows are supported independently for ARQ and MRQ.

## 8. Ambiguous Fail-Closed Rules

Unexpected empty, malformed, duplicate, conflicting, truncated, or otherwise incomplete histories remain untrusted. A recent oldest boundary and contradictory companion-dimension evidence produce `AMBIGUOUS_SOURCE_REMOVAL`, block Test authorization, and do not default to either retention or deletion.

## 9. Provider Merge

The candidate generation is `current authoritative complete source rows + non-overlapping retained rows - true removals`. The same `build_source_history_merge` result is used by comparison, Test replacement, Production replacement, and provider candidate validation. Candidate validation checks exact keys, content fingerprints, retained provenance, and true-removal absence.

## 10. Provenance

Retention provenance records the source identity, fiscal identity, dimension boundaries, minimum-history rule, and prior accepted source. It does not claim that a retained row is currently returned by Sharadar and does not contain credentials or raw response dumps.

## 11. Current-Window Authority

Every source identity returned by the trusted current response wins over a retained copy. Current rows are written without retained status. The provider semantic fingerprint now includes provenance so publication postflight can prove retention state.

## 12. Reappearance Behavior

When an exact retained source key reappears, the current payload wins and retained status is cleared. Tests also cover a retained source key alongside a newer current ARQ key for the same fiscal quarter; both source identities remain available and the ordinary canonical winner selects the newer current row.

## 13. True Interior Removal

Interior missing keys remain deletable. NAMS is the production-shaped fixture and live example: ARQ key `(NAMS, ARQ, 2022-11-28, 2022-06-30)` is absent while older and newer rows remain. Another ARQ key still represents 2022 Q2, so the canonical quarter and established first-public date survive.

## 14. Canonical Rebuild

No canonical retention exception was added. Fresh canonical rebuild consumes the already merged provider candidate. Fixture acceptance proves retained quarters survive, true removed source keys do not, stable company/security identity remains unchanged, and downstream V2/RP/RV code accepts the rebuilt state.

## 15. first_public_result_date

Retention creates no publication event. Existing fiscal quarters preserve `first_public_result_date`; source-key removal also preserves it when the stable quarter survives through another winner. The live Preview reports 88,835 established dates, zero historical bootstrap-eligible rows, and zero repair-required rows.

## 16. Repeated-Run Stability

An absent row already marked `RETAINED_OUTSIDE_SOURCE_WINDOW` is carried without a new aged-out event or effective change. Retention evidence is stable and excludes trigger/run metadata. A reappearing source key replaces retained state and follows ordinary revision semantics.

## 17. Preview Reporting

Preview reports newly aged-out rows, retained ARQ/MRQ counts, already-retained carry-forward, true removals, ambiguities, and reappearances separately. Ticker detail includes a concise source-history action and canonical impact. `SOURCE_HISTORY_CHANGE` authorizes candidate work for a first retention-state transition without pretending that financial content changed.

## 18. Scheduler Compatibility

Shared operation-summary and UI payloads expose the new counters. Scheduler trigger metadata does not affect classification or semantic fingerprints. Scheduler Refresh remains Preview-only and disabled; both `stock-update-scheduler.service` and `stock-update-scheduler.timer` were inactive for the live run.

## 19. Production Safety

The only live operation was a MANUAL read-only Preview. Provider, canonical, and analysis SHA-256, size, and `mtime_ns` were identical before and after:

| Role | SHA-256 | Size | mtime_ns |
| --- | --- | ---: | ---: |
| provider | `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468` | 958828544 | 1789831083995864659 |
| canonical | `bee62a677777be63ce67737d9e77d375f22dd044b6a7c9c834ccbe7b9f1684cf` | 655724544 | 1789893262044507282 |
| analysis | `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2` | 902062080 | 1789831394579542627 |

## 20. Cleanup

The live run contains JSON/Markdown/progress evidence only. It created no database candidate, backup, publication journal, or phase-owned large temporary file. Existing older Add Tickers `accepted_preview.json` files under the shared temp root were not created or modified by this phase.

## 21. Tests

Focused retention/Preview/copy tests: 50 passed, 0 skipped, 0 failed. The broader relevant acceptance suite covered Refresh Preview/Test/Production fixtures, full workflow, scheduler integration, UI/reporting, first-public bootstrap, publication transactions, full V2 downstream, and RV engine: 320 passed, 0 skipped, 0 failed. `python3 -m py_compile` and `git diff --check` passed.

Production-shaped fixtures prove retained provider rows and provenance survive candidate replacement, canonical quarters survive fresh rebuild, true removals stay absent, current source wins on reappearance, first-public dates remain stable, and the next identical generation reaches no-change semantics.

## 22. New Live Preview

- Run: `20260920T104446Z_refresh_fundamentals_0e0cb63ec2cc`
- Fingerprint: `2165b71fdc824a92b3914c21a8e52bfeafdfb11b55a425b7586317ef87e0f7b7`
- Outcome: `REVIEW_REQUIRED`; Test authorization: false
- Discovery rows / source tickers / known canonical / unknown: `545 / 269 / 78 / 191`
- Effective changed known: `69`
- `NEW_QUARTER / HISTORICAL_REVISION / NEW_QUARTER_AND_REVISION`: `35 / 6 / 19`
- `SOURCE_HISTORY_CHANGE / SOURCE_REMOVAL / NO_EFFECTIVE_CHANGE`: `8 / 1 / 7`
- Newly aged-out rows: `96` (`47` ARQ, `49` MRQ)
- Already-retained carry-forward / reappearances: `0 / 0`
- True source removals: `4` (three BNC MRQ keys and one NAMS ARQ key)
- Ambiguous removals: `3` rows across `FLWS` and `LOVE`

BNED safely retains its paired oldest ARQ/MRQ 2016 boundary and is `SOURCE_HISTORY_CHANGE`. NAMS remains one true interior ARQ removal while its alternate 2022 Q2 ARQ winner preserves the canonical quarter and `first_public_result_date = 2022-10-13`.

## 23. Remaining Issues

FLWS has paired oldest ARQ/MRQ rows at report period `2016-07-03`, but its current source maximum is `2026-06-28`, five days short of the exact ten-year threshold. LOVE has one oldest MRQ row at `2017-01-29` with current maximum `2026-08-02`. Both are coherent boundary moves but do not satisfy the locked age rule, so the classifier correctly returns `AMBIGUOUS_SOURCE_REMOVAL` and blocks Test. No validation was relaxed to force acceptance.

## 24. Next Step

Review the FLWS and LOVE boundary evidence and decide their explicit handling in a separate prompt. Then run a new Preview. Do not authorize Test from this `REVIEW_REQUIRED` Preview.

## 25. Git

Baseline was `7053c29`. Code, focused tests, regression updates, and this document are committed locally under the Phase 13G.3.9 change; nothing is pushed. Runtime reports and live database files remain outside Git.
