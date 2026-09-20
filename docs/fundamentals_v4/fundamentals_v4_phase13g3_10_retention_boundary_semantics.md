# Phase 13G.3.10 - Retention Boundary Semantics

## 1. Purpose

This phase audited the meaning of RawCandle's ten-year Sharadar policy, resolved the FLWS and LOVE boundary cases, and validated every row in the Phase 13G.3.9 aged-out population before the first live Refresh Test. It changed classifier semantics narrowly and ran one new read-only MANUAL Preview. It did not run Test, Production, full workflow, or scheduler Preview.

## 2. Phase 13G.3.9 Baseline

Baseline commit was `72b1968`. Preview `20260920T104446Z_refresh_fundamentals_0e0cb63ec2cc` discovered 545 rows and 269 tickers. It reported 96 aged-out rows, four true removals, and three ambiguous rows across FLWS and LOVE, producing `REVIEW_REQUIRED`. Production Refresh state remained `BOOTSTRAP_BASELINE`.

## 3. Existing 10-Year Policy Meaning

`sharadar_history_policy.py` defines `MINIMUM_HISTORY_YEARS = 10`, `APPEND_ONLY_NO_WINDOW_PRUNING`, `absence_from_later_snapshot_authorizes_deletion = False`, and `minimum_history_is_cleanup_cutoff = False`. `fundamentals_v4_phase12c2_permanent_ten_year_policy.md` states explicitly that ten years is a minimum upstream request, not an exact coverage promise, local maximum, or cleanup cutoff. Phase 12C.2 tests enforce `years >= 10` at the production download boundary and prove that later snapshot absence does not prune accepted rows.

Therefore Phase 13G.3.9 incorrectly reused the request-horizon integer as an exact report-period calendar-anniversary gate. It remains relevant as a quarterly coverage expectation and audit diagnostic, but it is not a source deletion timestamp.

## 4. FLWS Deep Dive

FLWS uses Sunday-based retail fiscal periods consistent with a 52/53-week calendar. Both dimensions move in lockstep:

| Dimension | Old/new count | Old min -> new min | Old max -> new max | Removed identity |
| --- | --- | --- | --- | --- |
| ARQ | 40/40 | 2016-07-03 -> 2016-10-02 | 2026-03-29 -> 2026-06-28 | `FLWS|ARQ|2016-09-16|2016-07-03` |
| MRQ | 40/40 | 2016-07-03 -> 2016-10-02 | 2026-03-29 -> 2026-06-28 | `FLWS|MRQ|2016-07-03|2016-07-03` |

Both removed rows are fiscal 2016 Q4, position 1, a paired contiguous oldest prefix with zero older rows and 39 newer old rows surviving. There is no interior gap or same-fiscal current replacement. Current history runs from fiscal 2017 Q1 through 2026 Q4. The removed-to-current-maximum span is 41 inclusive fiscal-quarter positions.

The report-period age is 3,647 days, or 9.985147 mean Gregorian years, five days before the literal ten-calendar-year anniversary. The Sunday quarter ends move by 13-week intervals and explain the calendar-day variance. Structurally this is identical to the accepted paired boundary cases; the exact-day shortfall is not deletion evidence.

## 5. LOVE Deep Dive

LOVE is not an aged-out case. Its removed row is `LOVE|MRQ|2017-01-29|2017-01-29`, fiscal 2017 Q4. MRQ changes from 38 to 39 rows, min `2017-01-29 -> 2017-02-04`, and max `2026-05-03 -> 2026-08-02`. The removed row is position 1, with zero older and 37 newer old rows surviving.

The current complete MRQ response contains replacement key `LOVE|MRQ|2017-02-04|2017-02-04` for the same fiscal 2017 Q4 identity. Its removed-to-current-maximum span is only 39 fiscal-quarter positions and its age is 3,472 days, or 9.506013 mean Gregorian years. This is a source-key correction/replacement, not rolling expiry.

LOVE ARQ is independently stable at its old minimum: count 35/36, min `2018-05-06` unchanged, max `2026-05-03 -> 2026-08-02`. ARQ/MRQ minima legitimately differ. There is no companion contradiction because the same-fiscal replacement is dimension-local and explicit.

## 6. Full 96-Row Audit

The machine-readable CSV contains 103 rows: the 96 Phase 13G.3.9 aged rows, the three FLWS/LOVE decision rows, and four true-removal controls. The aged population spans 49 tickers: 47 ARQ and 49 MRQ rows.

All 96 retain their `AGED_OUT_OF_SOURCE_WINDOW` classification. None has a same-fiscal replacement. Adding FLWS yields 98 aged rows; adding LOVE to the controls yields five true removals. No row remains ambiguous.

## 7. Position / Prefix Analysis

- Position 1: 93 of 96.
- Rows belonging to a contiguous prefix longer than one: 6, across FEIM ARQ, FIZZ ARQ, and USAU ARQ.
- Prefix-position-2 rows: 3.
- Interior rows: 0.
- Rows with an older current source row remaining: 0.
- Chronology inconsistencies: 0.
- Companion contradictions: 0.
- Same-fiscal current replacements: 0.

The audit found no material defect inside the existing 96-row retained population.

## 8. Age Distribution

Age days are `current maximum reportperiod - removed reportperiod`. Approximate years are days divided by 365.2425. Exact ten-year membership uses the calendar anniversary, not the approximate decimal.

All 96 rows satisfy the exact ten-calendar-year anniversary used by 13G.3.9, so the requested buckets are: `>=10.0 exact years = 96`; all lower buckets = 0. Day statistics are minimum 3,652, P10 3,652, median 3,654, P90 3,654, and maximum 3,745. Mean-Gregorian-year statistics are minimum 9.998836, P10 9.998836, median 10.004312, P90 10.004312, and maximum 10.253462.

FLWS sits just outside that population at 3,647 days because its fiscal quarter boundaries are weekday-based. LOVE is materially separate at 3,472 days and has direct same-fiscal replacement evidence.

## 9. ARQ vs MRQ Behavior

The validated population contains 47 ARQ and 49 MRQ rows. Dimension counts and minima differ legitimately. Detection remains source-row and dimension aware; it does not force count or date symmetry. Companion dimensions are used only to detect contradictory classifications for the same fiscal identity.

## 10. Fiscal-Calendar Effects

Exact report-period days are unsuitable as the hard boundary across calendar and 52/53-week issuers. FLWS advances from Sunday `2016-07-03` to Sunday `2016-10-02` and ends at Sunday `2026-06-28`, while its fiscal identities cover 2016 Q4 through 2026 Q4. The classifier now compares validated fiscal-quarter identities. No arbitrary day tolerance was introduced.

## 11. Local Retention Policy vs Detection Evidence

Local policy is append-only preservation of already accepted history when a later snapshot no longer exposes it. Detection still requires evidence for why a key disappeared. RawCandle does not retain every missing key: interior keys and explicit same-fiscal replacements are true removals, while insufficient boundary coverage or contradictory evidence remains ambiguous.

## 12. Final Classifier Contract

Hard requirements for aged-out retention are: trusted complete history; prior source-backed row; contiguous oldest prior prefix; current minimum strictly beyond the missing key; no older current row; coherent chronology; no same-dimension current key for the same fiscal identity; no companion contradiction; and at least 41 inclusive fiscal-quarter positions from the missing fiscal quarter to the current maximum. The 41 positions are derived as `10 years * 4 quarters + inclusive boundary`, not as a calendar-day tolerance.

An interior key or a current same-fiscal replacement is `TRUE_SOURCE_REMOVAL`. A boundary with short fiscal coverage, incoherent chronology, incomplete source evidence, or companion contradiction is `AMBIGUOUS_SOURCE_REMOVAL` and blocks authorization. Report-period age remains a supporting diagnostic only.

## 13. FLWS Decision

FLWS is safely `AGED_OUT_OF_SOURCE_WINDOW` for both ARQ and MRQ: paired oldest prefix, normal one-quarter boundary advance, 41-position fiscal span, no older row, no gap, no same-fiscal replacement, and a five-day difference explained by its Sunday-based 52/53-week fiscal calendar.

## 14. LOVE Decision

LOVE is `TRUE_SOURCE_REMOVAL`: current MRQ explicitly replaces the old fiscal 2017 Q4 key with a new key for the same fiscal identity. The old key must not be frozen as retained history. This is generic logic; no ticker-specific production exception was added.

## 15. Code Change, If Any

The classifier no longer calls the ten-year constant as an exact calendar anniversary gate. It derives `MINIMUM_QUARTER_BOUNDARY_SPAN = MINIMUM_HISTORY_YEARS * 4 + 1`, checks same-fiscal replacement before retention, and emits deterministic reason codes. Preview, Test, and Production continue to use the same merge implementation and provenance model. Contract versions were advanced to Phase 13G.3.10 / retention V2.

## 16. Regression Results

Focused Preview/retention/copy tests: 52 passed, 0 skipped, 0 failed. Broader Refresh, scheduler, UI, first-public, publication/recovery, full V2 downstream, and RV suite: 322 passed, 0 skipped, 0 failed. The suite includes FLWS-like fiscal-calendar variance, LOVE-like same-fiscal replacement, BNED/ABM/IRM retention patterns, IPDN/JAGX revisions with boundary expiry, NAMS interior removal, multi-prefix, ambiguity, incomplete source, idempotence, reappearance, canonical rebuild, and first-public preservation.

## 17. New Live Preview, If Run

Run `20260920T112149Z_refresh_fundamentals_81d416e6f45b`, fingerprint `7e3e0a06ce995203549ac93379a4273ce942f9576911d67d013f99a9353754c0`, completed successfully.

- Discovery rows/tickers: 545/269.
- Known/unknown tickers: 78/191.
- Effective changed known: 71.
- Newly aged-out: 98, comprising 48 ARQ and 50 MRQ.
- True source removals: 5.
- Ambiguous rows/tickers: 0/0.
- Review Required: false; future Test authorized: true.
- Established/bootstrap/repair: 88,835/0/0.
- Expected new-quarter first-public initializations: 56.

Compared with 13G.3.9, FLWS contributes two additional aged rows, LOVE contributes one additional true removal, effective changed known rises from 69 to 71, and Review Required clears from two tickers to zero.

## 18. Production Safety

The live action was Preview only. Provider, canonical, and analysis SHA-256, size, and `mtime_ns` were identical before and after:

| Role | SHA-256 | Size | mtime_ns |
| --- | --- | ---: | ---: |
| provider | `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468` | 958828544 | 1789831083995864659 |
| canonical | `bee62a677777be63ce67737d9e77d375f22dd044b6a7c9c834ccbe7b9f1684cf` | 655724544 | 1789893262044507282 |
| analysis | `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2` | 902062080 | 1789831394579542627 |

No candidate database, backup, publication journal, watermark advance, or scheduler activation occurred.

## 19. Recommendation Before Test

### A - Ready for live Test on copies

The classifier is semantically sound, all 96 prior aged rows pass structural revalidation, FLWS and LOVE have deterministic generic outcomes, the new Preview has no unresolved review blocker, and first-public baseline/repair counts remain clean. Test still requires a separate explicit authorization.

## 20. Git

The phase commits only source, tests, this report, and the lightweight CSV. Live reports and databases remain outside Git. Nothing is pushed.
