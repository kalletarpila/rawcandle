# P/B.5 — Current P/B Eligibility Gate Correction

Date/as-of: **2026-10-07**. Corrected reporting implementation and fresh-copy validation complete. **Production rollout: NO**.

## Outcome

Corrected Current P/B valid: **1,691 / 2,468 (68.517018%)**, **+96** versus 1,595. The result is measured from the implementation, at the lower end of the P/B.4 **1,691–1,693** range. No count was forced: only after actual full-universe queries were the result and newly admitted identities checked against the audit.

The 25% endpoint-vs-EPS-average hard gate is removed. Missing weighted-average shares likewise no longer prevent valuation. Historical full-OHLC corroboration is no longer required. Missing old market history alone produces a diagnostic and can coexist with valid Current P/B. Substantial observed historical price-scale contradictions, canonical-share mismatches and native marketcap inconsistencies remain hard holds. The existing 409 ownership holds are unchanged.

KALA and FTFT remain explicit **reviewed unresolved-basis holds**. There is no deterministic universal discontinuity rule justified by their EPS-average differences alone. The user-authorized P/B.4 review classifications therefore bind only the exact accepted evidence, through a bounded mechanism described below. The five remaining SHARE_BASIS_UNVERIFIED cases are KALA, FTFT, BRTX, IESC and MNST. Provider P/B and four-quarter provider history are identical to the P/B.3 baseline for **every operational company**. Valuation Score and all unrelated snapshot fields remain identical in six real-company comparisons.

## Scope and Source

Reviewed narrowly: original P/B.3 contract and implementation at `6fbf22ef`; P/B.4 report, 101-row audit CSV and sensitivity CSV; `book_value.py`, accepted-parent-equity plumbing, compact warning renderer and focused P/B tests. Original audit artifacts and original P/B.3 coverage CSV remain unchanged historical evidence. No ownership-factor/identity expansion, new ADR ratio, issuer class capitalization or official-security override was introduced.

Source generation: **publication_drain_20261007T093516Z_fd654a20**. Same 2,468 operational company IDs and as-of 2026-10-07 as P/B.3/P/B.4. Fresh SQLite online backup of read-only active canonical was made at `/tmp/rawcandle_pb5/fundamentals_v4.db`; existing accepted-parent-equity migration ran only on this inactive copy. Migration bound **89,912** accepted quarters and **171,304** finite parent field values, identical to P/B.3. Provider/analysis/market databases were read-only. No production reconciliation, scheduler, refresh or generation publisher ran.

## Corrected Eligibility and Diagnostics

Formula remains **valid current close × canonical accepted shares_outstanding / latest accepted positive parent_equity_usd**. Filing-cover shares remain a reported current-ownership proxy; EPS averages and diluted potential shares are never the valuation denominator. Parent-attributable equity is not silently converted to common equity, and preferred-capital exclusion remains unproven. Current and provider/reference metrics remain reporting-only and not PIT-safe.

Unchanged mandatory rules:

- Latest accepted eligible fiscal quarter and exact accepted source/provenance binding; no richer alternate row, older fallback or dimension substitution.
- Finite positive USD parent equity, own source availability on/before as-of, equity age at most 180 calendar days.
- Latest complete positive valid current OHLC for ticker/market on/before as-of, current price age at most three calendar days.
- Finite positive accepted outstanding shares equal same-observation sharesbas.
- Supported ordinary category, factor exactly one, one active target security and no selected official ownership conflict. Existing primary-class/ADR/nonunit/zero/missing-factor holds remain.
- Finite positive native provider price/cap with same-row price × accepted sharesbas within **1%** of native marketcap. Current eligibility does not require Provider P/B equality.
- No demonstrated material unresolved price/share contradiction or explicitly bound unresolved-basis review; derived market cap/P/B finite and P/B positive.

Corrected rules in `rawcandle/fundamentals/book_value.py`:

| Evidence | Corrected effect |
| --- | --- |
| abs(sharesbas / shareswa − 1) >25% | `LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE` warning only |
| Missing/nonpositive/nonfinite shareswa | No eligibility dependency; sharesbas remains the denominator |
| No positive finite exact provider-date market close | `HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE` warning only |
| Usable historical close but full OHLC invalid/incomplete | `HISTORICAL_OHLC_INCOMPLETE` warning only; exact close still usable as corroboration |
| Exact-date close/native provider price mismatch >1% | `HISTORICAL_PRICE_MISMATCH` diagnostic plus hard SHARE_BASIS_UNVERIFIED |
| Matched explicit unresolved-basis review | `REVIEWED_UNRESOLVED_BASIS` diagnostic plus hard SHARE_BASIS_UNVERIFIED |
| Positive equity ≤USD1m | Existing `NEAR_ZERO_EQUITY` warning, valid if other gates pass |

Historical checks use the positive finite **exact-date close**, not a neighboring day, a guessed split-adjustment or a historical price as numerator. Current price validation continues using full OHLC. Warnings do not replace primary NULL reasons and can remain visible on blocked rows; warning counts are separated from hard eligibility counts.

## Bounded Reviewed-Evidence Holds

`rawcandle/fundamentals/book_value_reviews.py` contains two explicit P/B.4 unresolved review records. Lookup binds **company_id + accepted observation_id + content_hash**, with a **reviewed_as_of=2026-10-07** lower bound. Reporting includes company_id in its existing accepted-quarter query so those bindings can be checked. A match returns copied evidence/reference metadata in the Current P/B object; the existing compact Warnings row displays the review warning. Provider objects/history do not contain or depend on these holds.

| Reviewed case | Company | Observation ID | Content hash | Reason for explicit unresolved review |
| --- | ---: | --- | --- | --- |
| FTFT | 902 | `be26b0bf9b7eafb3efdfefe71f4266a3e3a3b71857df158f0aed05dac7afb64f` | `3607c414b271ba0c74ca95f9fc22b570cccd46aca8e7318aed6c15371722ec33` | Previously reviewed severe unit discontinuity with incomplete explanatory evidence and no same-date market corroboration |
| KALA | 1200 | `3de0925e0a28ebe14cf471ed3a8fc5c9b37a7d274d8410fd7d01e617ff8353fa` | `098713dc9ec03f48b34c07d0ede28cc975dab84b4226548db421eb57da4cab8b` | Previously reviewed severe unresolved ownership/unit discontinuity; internally matching cap and price do not independently resolve corporate-action basis |

These are **NEEDS_MORE_EVIDENCE review decisions**, not independently proved split errors. KALA's extreme average deviation has no additional demonstrated numerical contradiction; FTFT's absent history alone would normally be non-blocking. The explicit bounded review mechanism implements the user's instruction to retain unresolved cases when no generic automatic hold is evidenced. It does not convert their deviations into a percentage rule, invent corporate actions, or label their EPS average as the correct ownership base.

There is no ticker branch in calculation or review lookup. A named review reference is descriptive provenance only. Tests show a ticker string and arbitrarily large EPS-average deviation cannot create a hold. Reviews do not apply before their review date, to another company, another accepted observation or another content hash. The current accepted observation must still satisfy normal source binding. Clearing these exact records requires reviewed evidence resolving the ownership/split basis and a deliberate review update; a later different observation requires fresh review rather than inheriting a ticker-wide hold. Stored AR observations and calendar dates do not make the review mechanism PIT-certified.

## Coverage Reconciliation

| Primary result | P/B.3 | Corrected P/B.5 | Change |
| --- | ---: | ---: | ---: |
| OK | 1,595 | 1,691 | +96 |
| NEGATIVE_EQUITY | 215 | 215 | 0 |
| MISSING_EQUITY | 120 | 120 | 0 |
| MISSING_PRICE | 10 | 10 | 0 |
| STALE_PRICE | 12 | 12 | 0 |
| STALE_EQUITY | 6 | 6 | 0 |
| OWNERSHIP_BASIS_UNVERIFIED | 409 | 409 | 0 |
| SHARE_BASIS_UNVERIFIED | 101 | 5 | −96 |
| ZERO_EQUITY / MISSING_SHARES / EQUITY_AVAILABILITY_UNVERIFIED / PB_NONFINITE / other | 0 | 0 | 0 |
| Total | 2,468 | 2,468 | 0 |

The **96** newly valid IDs equal exactly the 96 P/B.4 LIKELY_OVERFILTERED IDs: 56 average-only exclusions, 39 historical-geometry-only exclusions and BROS with both. All formerly valid Current P/B values remain numerically identical. The five remaining share holds comprise **three demonstrated price-scale contradictions and two bounded reviewed unresolved cases**. None is rejected solely for EPS proximity or historical absence. Provider marketcap mismatch failures among the 1,696 original strict candidates remain **zero**. Primary reason precedence for other gates is unchanged.

## Warning Counts

Warnings are diagnostic observations, can overlap, and are attached independently of primary reason. “Valid Current P/B” below counts genuinely non-blocking warnings; “all operational rows” includes diagnostics on held/unavailable rows.

| Warning | Valid Current P/B | All operational rows |
| --- | ---: | ---: |
| LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE | 57 | 145 |
| HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE | 0 | 20 |
| HISTORICAL_OHLC_INCOMPLETE | 40 | 58 |
| HISTORICAL_PRICE_MISMATCH | 0 | 13 |
| REVIEWED_UNRESOLVED_BASIS | 0 | 2 |
| NEAR_ZERO_EQUITY | 1 | 1 |

No currently valid real-universe company happens to lack a historical close after the independent existing gates/review holds; that **zero is empirical, not an eligibility requirement**. Newly listed/discontinuous-history fixtures explicitly demonstrate valid current P/B with missing older prices. Forty valid companies warn about incomplete historical OHLC, including BROS. The 57 valid share-deviation warnings include BROS plus the 56 newly valid average-only cases; large deviations also occur on ownership/negative-equity/review-held rows, explaining 145 total diagnostics.

## Representative Copy Validation

Thirty real-company rows are retained in the corrected validation CSV. The sample covers 25–35%, 50–100% and >100% deviations, ordinary clean companies, historical-geometry exclusions, five retained basis holds, ADR/class/factor holds and negative equity. Values below are calculated from the new candidate; histories remain unchanged. Newly listed and limited/discontinuous-history shapes are tested as explicit fixtures rather than fabricated live companies.

| Ticker | Corrected Current P/B | Reason | Warnings / review |
| --- | ---: | --- | --- |
| AAPL | 45.285122 | OK | — |
| AMD | 15.770587 | OK | — |
| APVO | 0.535431 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| ASML | N/A | OWNERSHIP_BASIS_UNVERIFIED | — |
| BABA | N/A | OWNERSHIP_BASIS_UNVERIFIED | — |
| BIDU | N/A | OWNERSHIP_BASIS_UNVERIFIED | — |
| BROS | 8.553941 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE;HISTORICAL_OHLC_INCOMPLETE |
| BRTX | N/A | SHARE_BASIS_UNVERIFIED | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE;HISTORICAL_PRICE_MISMATCH |
| CAT | 20.465179 | OK | — |
| CNH | 2.751495 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| COP | 2.377894 | OK | HISTORICAL_OHLC_INCOMPLETE |
| CRM | 4.824816 | OK | HISTORICAL_OHLC_INCOMPLETE |
| CVNA | 17.452241 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| DSP | 6.990320 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| EE | 5.712936 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| FTFT | N/A | SHARE_BASIS_UNVERIFIED | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE;HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE;REVIEWED_UNRESOLVED_BASIS |
| IESC | N/A | SHARE_BASIS_UNVERIFIED | HISTORICAL_PRICE_MISMATCH |
| KALA | N/A | SHARE_BASIS_UNVERIFIED | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE;REVIEWED_UNRESOLVED_BASIS |
| MCD | N/A | NEGATIVE_EQUITY | — |
| MGRX | 0.774819 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| MNST | N/A | SHARE_BASIS_UNVERIFIED | HISTORICAL_PRICE_MISMATCH |
| MOVE | 0.510745 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| MSFT | 8.884396 | OK | — |
| NVDA | 25.179419 | OK | — |
| RRR | 31.952374 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| SCNI | N/A | OWNERSHIP_BASIS_UNVERIFIED | — |
| SLDB | 1.983556 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| SYM | 37.673764 | OK | LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE |
| TRU | 2.509090 | OK | HISTORICAL_OHLC_INCOMPLETE |
| XOM | 2.607477 | OK | — |

SLDB/MGRX/CNH now calculate despite deviations around 25–30%. APVO/CVNA/RRR calculate with 50–100% differences. DSP/EE/SYM/MOVE calculate with >100% differences when no independently observed price/cap contradiction or bound review exists. Metadata-clean ordinary ownership remains the restricted provider contract, not a universal certification that no unlisted economic class exists. TRU/CRM/COP and BROS calculate with matching exact historical closes despite invalid historical OHLC geometry.

BRTX remains held by provider 3.778 vs exact-date close 0.188899994 (~20×); IESC 372.27 vs 744.539978 (~2×); MNST 45.18 vs 90.3600006 (~2×). No split event/cause is invented. KALA/FTFT remain NULL with REVIEWED_UNRESOLVED_BASIS and their original provider references/history available. BABA/BIDU/ASML/SCNI retain ownership holds; MCD retains NEGATIVE_EQUITY. Provider/date comparisons are corroboration only and never equality tests between current and provider P/B.

## Focused Tests and Regression

**42 focused P/B tests passed** in `tests/test_fundamentals_pb_reporting.py`. Corrections to test setup during development did not demonstrate shared-core failures and did not warrant a full suite.

Tests cover:

- >25% and >100% endpoint-average differences remain numeric, correct warning, outstanding-share denominator; absent/zero/nonfinite average does not block.
- Missing historical close remains numeric and warning renders in existing compact report.
- Newly listed fixture has only a valid current bar; discontinuous historical ticker fixture has old bars under another symbol. Both remain valid; removing current bar gives normal missing/stale price reasons. Inactive ownership is not relaxed.
- Matching historical close with invalid historical full-OHLC remains valid with incomplete-OHLC warning.
- Demonstrated historical scale contradiction and native-marketcap reconstruction failure remain hard holds.
- Bound reviews for both records, company/observation/hash/date scoping, source revision boundaries, no ticker/percentage rule, provider reference independent of review.
- Existing ADR/class/nonunit/zero/missing-factor/official-conflict holds; negative/missing/stale/future equity; missing/stale/future current price; canonical share equality.
- Exact parent mapping/provenance, unrelated financial values, source mismatch rollback, immutable copy guard, current rebuild determinism, provider absolute rounding, original accepted ARQ selection, four-quarter gaps/N/A and no richer MRQ fallback.
- Provider/history equality under missing/incomplete old market evidence; warning rendering and parent/preferred/PIT caveats.

One relevant Fundamentals/reporting regression group: **88 passed** across `test_fundamentals_v4_additive_provenance.py`, `test_fundamentals_snapshot_ui.py` and `test_fundamentals_v4_company_snapshot_phase9f.py`. Full suite **not run**; no targeted failure showed shared-core impact.

## Copy, Score and Production Safety Verification

Fresh-copy migration's original canonical tables and all original financial columns retained identical deterministic logical SHA-256 fingerprints before/after. Foreign-key check passed. Coverage was recalculated over every operational company; P/B.3 source loaded separately from commit 6fbf22ef provided the exact comparator on the same candidate/market/as-of. All 2,468 provider references and maximum-four-quarter history objects compare exactly, all equity/current-price associations are unchanged, and all 1,595 previously valid current values are identical.

Six complete real snapshots were compared using original vs corrected P/B function on identical paths for **AAPL, NVDA, MCD, SLDB, TRU, KALA**. **Every top-level snapshot field other than book_value is exactly equal**, including score/model fingerprints, financial history, valuation inputs/multiples, score/valuation outputs and averages. Provider/history inside book_value also compare exactly. Corrected full Markdown reports render successfully on /tmp. Snapshot full-content hashes may naturally change when the P/B section changes; score fingerprints do not.

Active generation manifest bytes and production canonical/provider/analysis plus market DB size/mtime stayed unchanged. Candidate migration occurred only on the newly created inactive /tmp copy. No production write, identity-policy expansion, analysis rebuild, scheduler change, live workflow or rollout. CSV rows/IDs, finite/null values, reason totals, warning totals and newly valid sets validated; `git diff --check` and staged bounded-file review performed before commit.

## Deliverables and Readiness

- Updated current contract: `docs/fundamentals_v4/fundamentals_v4_pb_reporting_v1.md`.
- Detailed correction report: `docs/fundamentals_v4/fundamentals_v4_pb_reporting_v1_gate_correction.md`.
- Full operational coverage: `docs/fundamentals_v4/fundamentals_v4_pb_reporting_v1_corrected_coverage.csv` (2,468 rows).
- Representative real validation: `docs/fundamentals_v4/fundamentals_v4_pb_reporting_v1_corrected_validation.csv` (30 rows).
- Bounded source changes: current P/B gate/diagnostics plus exact-evidence review registry; focused tests only. Parent-equity acceptance and Provider P/B/4Q logic unchanged.

Corrected candidate is validated for later review through the existing immutable-generation workflow. **No Production rollout in this phase.** Clearing KALA/FTFT or resolving official ordinary/provider ADR conflicts remains separate reviewed evidence work; no expanded ownership coverage is claimed. The observed 1,691 is inside the expected range, so no coverage STOP condition applies.

Source code changed: **YES**, bounded gate correction. Production rollout: **NO**. Production DBs changed: **NO**. Active generation changed: **NO**. Valuation Score changed: **NO**. Unrelated financial/model outputs changed: **NO**. Provider P/B semantics changed: **NO**. 4Q Provider history changed: **NO**. Ownership gate changed: **NO**. Scheduler changed: **NO**. Full suite: **NO**. Push: **NO**.
