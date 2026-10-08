# P/B.10 — Quarterly ownership durability V2

Implemented on **2026-10-08**, using Production generation **pb_reporting_20261007T193505Z** as a read-only source. **Copy validation only; no Production rollout, DB modification, active-generation change, scheduler change or push.**

## Approved meaning and the earlier STOP

The user now explicitly accepts quarterly ownership units. Current P/B remains **PB_CURRENT_PARENT_EQUITY_V1**, with ownership validation version **PB_OWNERSHIP_BASIS_V2**:

```
Current P/B = latest usable market price
            × latest accepted quarterly validated economic units
            / latest accepted quarterly parent_equity_usd
```

This is a current-price valuation using quarterly shares, rather than a continuously observed market capitalization. Ordinary/direct-common units equal accepted `sharesbas`; ADS equivalents equal accepted ordinary `sharesbas` times the reviewed exact rational factor. The parent-equity denominator and its preferred-capital exclusion caveat remain unchanged.

[P/B.8A](fundamentals_v4_pb_ownership_durability_v1.md) correctly stopped under the earlier requirement to establish unchanged ownership through each report day. [P/B.9](fundamentals_v4_pb_current_marketcap_source_audit.md) established that DAILY marketcap largely carries filing-based counts and cannot prove complete intervening share changes. Neither finding has been reversed. The user's new quarterly approximation removes the daily-completeness requirement for this metric. It does not certify current outstanding shares or complete corporate-action monitoring.

No DAILY ingestion, numerator, `marketcap / price` share inference, daily action query or daily review workflow was added. Existing supplied action contradictions and explicit newer-count holds remain hard gates. The implementation never infers that missing events prove unchanged shares.

## V1 preservation and explicit candidate activation

`ownership_reviews_v1.json` is unchanged, SHA-256 **0baaf493afa2faa52c2179a2353fb9089d834ef2bcb91f6e088e58f1bae068bf**. The V1 evaluator body is syntactically identical to the committed implementation; only its dispatch/name was extracted. Default calculations and generations without explicit V2 configuration continue to use V1, including its October 7 expiry. V1 report objects and Markdown structure are unchanged.

V2 requires generation-local opt-in in additive canonical table `v4_pb_reporting_contract`. Its single row identifies ownership contract, effective date and exact review-artifact SHA-256. `activate_quarterly_ownership(candidate_path, effective_from='2026-10-08')` is restricted by the existing inactive-copy guard: active role DBs, legacy Production role paths, symlinks and finalized generations are rejected. Configuration reads do not write or create tables. Activation before October 8 is rejected; conflicting activation is rejected. Missing configuration means V1; malformed configuration or a mismatching V2 artifact fails explicitly.

The validation candidate opts in from **2026-10-08**. Report dates before activation select V1, independently of V2 artifact revisions. There is no live configuration row and no automatic source-code switch of Production to V2. A later separately authorized rollout must use the existing generation preparation/publication path. This phase creates no alternate publisher.

Historical reproducibility means identical calculation and evidence under identical inputs. All 2,468 October 7 P/B objects were compared against the committed V1 reporting implementation using the same frozen market inputs. They match exactly before and after candidate activation. The original October 7 rollout used an older market vintage: today's market inputs make CTVA unavailable, so current-input October 7 coverage is 1,721 rather than the rollout's 1,722. This is documented separately from contract behavior; the original rollout evidence and V1 semantics were not rewritten.

## Exact quarterly binding and supersession

V2 contains **63 migrated records: 31 supported, 32 explicit holds**. Supported releases remain **16 ordinary/common, six exact ADR/ADS factors and nine direct-common identity overrides**. V1 evidence URLs, source dates, raw accepted shares/factors, interpretation and hold dispositions are preserved. Each V2 record includes its canonical V1-record hash/reference, accepted fiscal year/quarter/report period, provider category, provider/availability dates, `valid_from_as_of`, validity mode and `OPERATOR_CONFIRMED` approval mode. Original evidence review timestamps are retained; the migration does not assert a fresh external-source review on October 8.

The same company/key/security/ticker, observation ID/content hash, fiscal quarter/report period, accepted sharesbas, raw factor, category and accepted source dates must match. A supported review also requires evidence provenance and a valid ordinary/ADS interpretation. Exact positive integer ADS numerator/denominator remain independent evidence; rounded provider factors are retained, including SCNI's raw zero. Supported ratios remain GPCR 1/3, MREO 1/5, ONC 1/13, ZLAB 1/10, ARM 1/1 and SCNI 1/40,000. Provider metadata is never rewritten to manufacture direct-common status.

There is **no `effective_to` or share-source age expiry in V2**. Share-source and unit-effective dates must still be valid and not later than the accepted provider date/current quote; future review/activation and inactive security identities fail closed. Parent-equity availability must remain within **180 calendar days** and current price within **three calendar days**, exactly as before. All native price/cap arithmetic, historical basis conflicts, accepted-shares provenance and other hard gates remain unchanged.

The canonical reader selects the latest accepted fiscal-quarter slot before validating P/B. It never substitutes an older valid slot. For a previously reviewed scope, a different authoritative observation/hash/quarter/report period yields **OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED**. This includes same-quarter observation revisions. Identity, raw count/factor or provenance mismatches fail with OWNERSHIP_REVIEW_UNVERIFIED. No prior review's units are returned on mismatch. A newer authoritative Q therefore cannot borrow old shares, identity overrides or exact ADS ratios, even if its provider category would ordinarily pass the unreviewed common rule.

Matching explicit holds retain their original reasons, including local archived audit references. All 16 multi-class, seven newer-count and nine other registry holds remain unavailable; no per-class cap is expanded into whole-company equity. All unreviewed ownership cases and KALA/FTFT, BRTX/IESC/MNST remain held. Existing generic ordinary/common eligibility remains as before; the only restored releases are the reviewed 31.

## Normal refresh and new-Q review workflow

Normal Fundamentals reconciliation already calls `accept_parent_equity` after accepting canonical financials. That rebuild binds parent equity, sharesbas, provider factor and original Provider P/B to the same accepted ARQ shares observation. The existing four-slot reporting reader then rolls Provider P/B history automatically. No new refresh command or scheduling behavior is required. The additive reporting configuration survives the normal rebuild's explicit table deletion list.

When the accepted observation changes, the next report compares it with V2 immediately. Until a matching approved record exists, Current P/B is held with the new-quarter reason; new parent equity and Provider P/B/history can still be reported. Refresh does not write or approve ownership records.

The bounded first-version workflow is **operator confirmation**, not automatic continuation:

1. Read the newly accepted ARQ observation and its accepted provenance from an inactive candidate. Compare company key/security/ticker, provider category or the reviewed compatible direct-common interpretation, finite positive sharesbas, raw factor semantics, ordinary/ADS interpretation and exact ADS ratio with the previous supported review. Inspect accepted/provider evidence for new multi-class, treasury, NCI/perimeter or identity contradictions. A matching factor alone is not approval.
2. Confirm the new observation's count/source date and interpretation. Existing official ratio/identity evidence may support the new quarterly review if still applicable; changed ratios or identity need appropriate new evidence. No proof of daily action completeness is required, and quarterly uncertainty must remain explicit. Leave unresolved cases held.
3. Append a new, fully observation/hash/quarter-bound record to the versioned V2 artifact, with its actual review timestamp, source dates, provenance, exact ratio where applicable, `approval_mode='OPERATOR_CONFIRMED'` and `evidence_status='REVIEWED_SUPPORTED'`. Retain earlier observation records. Do not edit V1, transfer approval by ticker, approve a candidate suggestion, or use a Boolean “reconciled” flag as evidence.
4. Review/test the artifact change. On an inactive candidate only, explicitly call `repin_quarterly_reviews(candidate_path, expected_artifact_sha256=previous_digest)` to bind the new approved artifact. The expected old digest prevents an unnoticed conflicting update. This helper creates no evidence and is never called by normal refresh. A future code/artifact revision requires this explicit candidate binding; mismatching configured artifacts fail closed. Restart report workers after a reviewed artifact revision because the immutable packaged registry is process-cached.
5. Rehearse Current P/B with new shares and equity, provider/history invariants and score isolation, then use a separately authorized normal generation rollout. Calendar progression within the same accepted observation requires none of these review steps.

This phase appends **zero actual new-Q approvals** and implements no automatic approval/candidate suggestion. Synthetic approvals used for simulations exist only in test process memory; simulated DB transactions roll back.

## Reporting disclosure

V2 compact reporting exposes Current P/B, current price date, equity quarter, share-basis quarter/date and ownership status. Reviewed records expose their specific share source date/basis. Generic ordinary/common cases use the provider filing date as an explicitly labeled **PROVIDER_FILING_DATE_PROXY**, rather than inventing a cover-count date. `OPERATOR_CONFIRMED_QUARTER`, `EXISTING_UNREVIEWED_COMMON_RULE` and `HELD` distinguish reviewed eligibility, existing generic eligibility and unavailable reports. Detailed numerator semantics are labeled **CURRENT_PRICE_QUARTERLY_SHARE_BASIS_PROXY**.

The rendered report includes exactly:

> Current P/B uses the latest market price with the latest accepted quarterly share basis and parent equity. Share changes after that quarterly basis may not yet be reflected.

These fields/disclosure are conditional on V2. Provider reference dates, original ARQ slot selection, four-quarter history, revised/non-PIT labeling and reporting-only status are unchanged.

## Validation results

Fresh backups of all three active-generation role DBs and market DB were made using read-only source connections. V2 activation and simulated changes were confined to the inactive canonical/market copies. The copied market input was frozen throughout the three-date comparison. The operational universe contains **2,468 members**.

| Report date | Selected ownership contract | V1 valid | Candidate valid | Change versus V1 |
|---|---|---:|---:|---:|
| 2026-10-07 | V1 (before activation) | 1,721 | 1,721 | +0 |
| 2026-10-08 | V2 | 1,690 | 1,721 | +31 |
| 2026-10-09 | V2 | 1,689 | 1,720 | +31 |

**October 8/9 restore exactly the same 31 company/observation approvals. Additional ownership releases: zero.** All 32 explicit holds retain their original underlying reasons under V2. Date-only OWNERSHIP_REVIEW_STALE: zero after V2 activation. The 63 V1 stale reasons on later days become 31 valid results and the 32 original hard hold reasons. All unreviewed scopes retain their existing eligibility/holds.

The original rollout had 1,722 valid companies. **CTVA** now has a demonstrated historical provider-date price mismatch, returning SHARE_BASIS_UNVERIFIED under both implementations; it accounts for the sole eligibility difference against the original rollout. On October 9, **QRVO** has latest valid price **2026-10-05**, now four calendar days old, and changes from OK to STALE_PRICE under both implementations. Every other day-to-day eligibility change is zero. No count was forced.

| Candidate hard reason | October 7 | October 8 | October 9 |
|---|---:|---:|---:|
| MISSING_EQUITY | 120 | 120 | 120 |
| MISSING_PRICE | 10 | 10 | 10 |
| MULTI_CLASS_UNVERIFIED | 16 | 16 | 16 |
| NEGATIVE_EQUITY | 215 | 215 | 215 |
| NEWER_SHARE_COUNT_REQUIRED | 7 | 7 | 7 |
| OK | 1721 | 1721 | 1720 |
| OWNERSHIP_BASIS_UNVERIFIED | 355 | 355 | 355 |
| SHARE_BASIS_UNVERIFIED | 6 | 6 | 6 |
| STALE_EQUITY | 6 | 6 | 6 |
| STALE_PRICE | 12 | 12 | 13 |

Provider P/B remains available for **2,133** companies. Valid four-slot history distribution: 4: 2,081, 3: 50, 2: 36, 1: 25, 0: 276. All 2,468 provider/history objects match V1 for every report date and the original P/B.8 frozen provider/history objects. There is no ARQ/PIT/date/slot/provenance change.

**R1:** All 2,468 October 7 complete P/B objects match the committed V1 implementation exactly under identical current-vintage inputs. Additionally, all **31** supported reviews were calculated under V2 on its October 8 activation date with the October 7 quote, accepted equity and shares frozen: every value and economic-unit count equals V1 exactly. This verifies V2 value logic without retroactively activating V2 on October 7.

**R2/R3:** The full universe was assembled twice for each date under the final implementation. Both runs matched exactly. All 31 supported approvals survive October 8/9; the 32 explicit registry holds retain their original reasons. Later-date unit tests extend the same observation through October 30 and remove the separate 180-day share-source age expiry while retaining equity/price freshness.

**R4/R5:** Nine synthetic accepted new-quarter scenarios on the fresh full-universe copy covered **AMT, APTV, CAMT, GPCR, MREO, ONC, ZLAB, ARM and SCNI**. Old approval first yielded OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED with no numerator/value. Provider P/B and history rolled to the new accepted slot. A matching simulated operator-confirmed observation-bound review then restored Current P/B using **110% of old shares** and **120% of old parent equity**, preserving the frozen current quote. Exact ADS ratios were reviewed on the new record; SCNI raw factor remained zero. Old shares were never substituted. Simulations rolled back and added no real registry record. The focused integration test also drove this sequence through **normal `phase12d.reconcile_canonical`**, then verified repeated reconciliation/reporting is deterministic.

**Score and financial isolation:** Seventeen representative complete snapshots were compared on each of three dates, **51 comparisons**: AAPL, NVDA, MSFT, CAT, XOM, MCD, BA, PSA, GPCR, ONC, SCNI, ARM, CAMT, BABA, BIDU, KALA and FTFT. Every non-`book_value` JSON field matched exactly, including Valuation Score, Fundamental Score, relative position, fingerprints, score history, financial statements, existing valuation multiples and all other financial outputs. Repeated candidate snapshots were identical; V2 Markdown rendered the required share fields/status/disclosure.

**Database safety:** All **30 pre-existing canonical tables** retain identical row counts and ordered-row SHA-256 digests, including parent equity, accepted provenance and financial inputs. The only addition is the singleton V2 reporting configuration table. Provider, analysis and market copies are byte-identical to source after excluding SQLite backup header counters at offsets **24–27**, **40–43** and **92–95** (file change counter, schema cookie, version-valid-for). A full binary comparison found differences only in those fields: provider two bytes, analysis three bytes, market seven bytes. The initial raw copy SHA assertion detected these benign backup metadata changes and was replaced by this precise check; no data/page difference was ignored. All four candidate quick_checks were OK and canonical FK errors zero.

| Read-only Production role | Source SHA-256 before = after |
|---|---|
| provider | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` |
| canonical | `f1bfcfcb9c03c23dcce0c1186243c14a2f7a375fb48271cc9d14bd857cfa37d8` |
| analysis | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` |

Active manifest SHA-256 before = after: **730b93fec46c3d4ed37b8340d7ec5ce6b2106dd42c64141c18d37ca045664eb8**. Source role and market sizes, mtimes and complete byte hashes remained identical. V2 registry SHA-256: **7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6**.

**Tests: 142 focused passed; 49 reporting regression passed; total 191 passed.**

```text
pytest -q tests/test_fundamentals_pb_quarterly_ownership.py tests/test_fundamentals_pb_ownership.py tests/test_fundamentals_pb_reporting.py tests/test_phase12d_operational_rebuild.py
142 passed in 13.54s

pytest -q tests/test_fundamentals_snapshot_ui.py
49 passed in 15.19s
```

The 43 V2-focused cases cover same-Q next/multiple days, independent price changes, ordinary/identity/ADR/zero-factor cases, supersession and same-Q revisions, new shares/equity after explicit review, no old-count fallback, multi-class/all explicit holds, strict binding/provenance/dates, unchanged provider/history, reporting fields/disclosure, V1 artifact preservation, activation safety and expected-digest repinning. Full-universe validation supplies the exact +31 check; complete snapshot comparisons and whole-analysis copy invariance supply Valuation/Fundamental Score isolation. **The full test suite was not run.**

The compact CSV contains **292 checks**: 189 reviewed scope/date rows, three full-universe aggregates, 51 complete snapshot comparisons, nine new-Q scenarios, nine safety checks and 31 frozen-October-7 input comparisons. All PASS.

## Bounded changes and acceptance

Source changes are confined to ownership dispatch/V2 validation, generation-local reporting activation, Current P/B metadata/dispatch and compact P/B rendering. No valuation core, score calculation, schema financial acceptance, provider acquisition, scheduler or publishing path was changed.

The committed validation CSV contains all 63 reviewed scopes for each of three dates, full-universe aggregate checks, representative complete snapshot digests, new-quarter simulations and safety checks. Full-universe detailed outputs, DB copies, source-state hashes and rendered sample reports remain under `/tmp/rawcandle_pb10`, outside Git. No DB, generation data, raw provider response, log/cache or unrelated working-tree change is included in the commit.

Production rollout **NO**; Production DBs changed **NO**; active generation changed **NO**; current formula materially changed **NO**; ownership validity changed **YES, inactive candidate only**; ownership release set expanded **NO**; DAILY dependency **NO**; Provider P/B/4Q changed **NO**; scores/unrelated financial outputs changed **NO**; scheduler changed **NO**; full suite **NO**; push **NO**.
