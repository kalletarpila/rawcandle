# P/B ownership review: economic-units audit

2026-10-28. Audit only. Starting HEAD: `413d52268307b7accbf07e2e3ae59224c4f2269c`.

**The reported live 10× mismatch is not reproduced.** The three supplied equity figures are exactly one-tenth of the frozen live queue, accepted canonical values, raw provider equity and actual dialog text. Current displayed shares, price and equity reconstruct every available hypothetical P/B exactly using the existing binary64 formula. No hidden ×10/÷10 factor, formula defect or live UI scale conversion was found.

The supplied numbers do reproduce an approximately 10× arithmetic discrepancy. The user subsequently confirmed that those figures were read from screenshots, not copied as text from the dialog, and accepted the directly recovered equity values. The primary classification is **OTHER — screenshot-transcription discrepancy**. A missing zero in each transcribed equity value is the working explanation, supported by the exact tenfold denominator difference and the consistent UI/backend trace. The original screenshot pixels were not independently examined, so this is not a claim to have reconstructed the reading error itself. No application scale defect is established, and no backend value should be divided or multiplied by ten to fit the supplied figures.

**Economic-unit arithmetic: PASS. Ownership-continuation approval safety: UNKNOWN beyond this arithmetic audit.** The screenshot clarification removes the reported 10× discrepancy as evidence of an application defect. It does not constitute an ownership review or approval. In the frozen audit, all nine cases remain OPEN with no approval or result. No source/tests/runtime state changed. The only deliverable is this report.

## Governing scope and evidence

The [P/B reporting contract](fundamentals_v4_pb_reporting_v1.md), [quarterly ownership V2 contract](fundamentals_v4_pb_quarterly_ownership_durability_v2.md), [new-quarter review workflow](fundamentals_v4_pb_new_quarter_review_workflow.md) and [ownership publication workflow](fundamentals_v4_pb_ownership_publication_workflow.md) govern this audit. Provider factor meaning and price-history limitations are retained from the [parent-equity investigation](fundamentals_v4_pb_book_value_investigation.md) and [market-cap source audit](fundamentals_v4_pb_current_marketcap_source_audit.md); no external refresh was performed.

Current P/B remains reporting-only and separate from Valuation Score: latest usable price × latest accepted quarterly validated economic units / latest accepted quarterly parent_equity_usd. Provider P/B remains original same-observation evidence; four-quarter history is Provider P/B history, not historical current-price valuation. Ownership approval, inactive preparation and controlled publication remain separate operations.

The active generation is `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`. Its resolved provider/canonical/analysis DBs were read with SQLite mode=ro and query_only. Market inputs are `data/osakedata.db`; ownership cases are in `fundamental_reports/fundamentals_refresh_review_queue.db`, table `pb_ownership_review`. The generation-local ownership contract is `PB_OWNERSHIP_BASIS_V2`, effective 2026-10-08, pinning artifact SHA-256 `7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6`.

The audit froze all nine current ownership rows and independently regenerated their cases using the existing read-only detector. Each complete queued case equals the freshly detected case, its candidate fingerprint verifies, and the preview accepts the exact case/hash. No stale queued value is observed. Read-only ownership `preview()` means the existing pure review calculation; no Refresh Fundamentals Preview/Test/Production workflow or publication preview was run.

Baseline captured at `2026-10-28T12:55:55.495617+00:00`; final invariance check at `2026-10-28T13:01:38.885422+00:00`. Complete audit artifacts remain under `/tmp/pb_review_economic_units_audit` and are not committed.

**User clarification, 2026-10-28:** the supplied equity amounts were transcribed from screenshots. The user confirmed AMT 3,516,600,000, BA 6,547,000,000 and DHR 53,621,000,000 as the directly recovered current values, yielding approximately 24.24 / 20.36 / 3.04 P/B, and requested that exact UI/backend evidence take precedence over the unreliable transcription. This clarification updates interpretation of the existing frozen evidence; it does not represent a new runtime snapshot or approve any action.

## 1. Exact real AMT / BA / DHR cases

All three transitions are FY2026 Q2 → FY2026 Q3; all are OPEN, CONTINUATION_CANDIDATE, with current reason OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED. The reason is observation/quarter supersession without a matching explicit review, not a scale-error hold. The queue's classification and its current_pb_status are distinct from the fresh calculation's status/reason.

| Case | Company / security | Old → new report period | Old → new provider date | Previous → new shares | First / last seen UTC |
| --- | --- | --- | --- | --- | --- |
| AMT | 150 / 150 | 2026-06-30 → 2026-09-30 | 2026-07-28 → 2026-10-27 | 465960048.0 → 463763555.0 | 2026-10-28T05:35:32Z / 2026-10-28T05:35:32Z |
| BA | 269 / 269 | 2026-06-30 → 2026-09-30 | 2026-07-28 → 2026-10-27 | 790370020.0 → 792449940.0 | 2026-10-28T05:35:32Z / 2026-10-28T05:35:32Z |
| DHR | 670 / 671 | 2026-06-26 → 2026-09-25 | 2026-07-21 → 2026-10-21 | 702986054.0 → 703530815.0 | 2026-10-27T11:02:09Z / 2026-10-27T11:02:09Z |

**AMT identity:** observation `d76ed514b053931df52a6f88c7f30cbb2194d0d739342cd444944a2746089413`; content hash `6dec2f5339ba3ef18abf1fc8e1c3a04b26c83a01020853c6c9998fa60e95ed0c`; review case `9e013833acbece570cd72b1239965a6b31f008ce5ebce2d754cd25da9fa8d1b3`; full candidate fingerprint `327d7d459b849426c7f9a2e35a5adf29e0b518dc333a55aa5116c23a2c4ebb64`. Prior review fingerprint `f615ab7703fd8c7d449b5d5c82ec011718aff3ca7ced065fe5e3be2faaf6572b`.

**BA identity:** observation `432ef662bf06829a4100e4dc9602803130530635af1bb95a57a81fc0fe9733ad`; content hash `0428d5210e9c1f7fa948b8cdde1a54783b106de786785003aa9cb305c8e0480b`; review case `8bc27f080d9d65718994ff08fd4d50590b4d43aa7b3c9bdc35aeb04758abb937`; full candidate fingerprint `8bb1a8f53dd81d842fd2da668f8f3621a3566575ae24dd2f849520e5a91fdb05`. Prior review fingerprint `46986c776d0fda4f5849aa8d68825f94af125742c0f77a64371ac0a36633afb6`.

**DHR identity:** observation `92be12ae42c6b7a9247123045a0b60c2fdb7c789ac8834b6fa77e70de35e93d2`; content hash `b50bd10488850f0fa36eba6b7ca0e7419d21f9031d0a9e5899c18b89835ed697`; review case `02d04d87dd80c0a3dab8dd153bc1f32afe8191e9eda8c1b016bab3a713f948d3`; full candidate fingerprint `3267f42df5018a6931de67de73888b756ce82fcc116abf39af60f5830f9f4093`. Prior review fingerprint `0d9d70dc6da5b604dae89afacd591653fe16533e1ddfe952de95748dc912b758`.

All three have prior/new category `Domestic Common Stock Primary Class`, prior/new raw provider factor 1.0, economic rule ORDINARY_COMMON and reviewed type COMMON_OR_ORDINARY. Accepted exact ordinary conversion is 1; ADR numerator/denominator fields are NULL and unused. Source availability equals the new provider date shown above. All approval_json/result_json fields are NULL.

## 2. Supplied reproduction versus current live display

These are separate evidence sets. The first table recomputes only the supplied approximate values using Decimal arithmetic before inferring any source units. The ratio to the supplied P/B is approximate because that P/B and two prices were rounded in the request.

| Case | Supplied shares | Supplied price | Supplied equity | Market cap from supplied values | P/B from supplied values | Supplied P/B | Ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AMT | 463763555 | 183.83 | 351660000 | 85253654315.65 | 242.4320488985099243587556162202127054541 | 24.2432 | 10.00000201699899041210548179366637677592 |
| BA | 792449940 | 168.18 | 654700000 | 133274230909.20 | 203.5653442938750572781426607606537345349 | 20.3565 | 10.00001691321568330892553537006134328273 |
| DHR | 703530815 | 232.0 | 5362100000 | 163219149080.0 | 30.43940789616008653326122228231476473770 | 3.04394 | 10.00000259405904404596057158889950680293 |

The supplied P/B values are approximately ten times smaller than reconstruction. Relative errors from an exact ratio of 10 are about 0.0000202% (AMT), 0.0001691% (BA) and 0.0000259% (DHR), consistent with the supplied rounding. Replacing only each supplied equity with its live equity, while keeping the same supplied shares and price, changes P/B by **exactly 10** in Decimal arithmetic. Each supplied_equity/live_equity ratio is exactly **0.1**. Absolute P/B differences from the supplied rounded P/B are approximately 218.1888488985, 183.2088442939 and 27.3954678962 respectively; these are far beyond floating-point error.

The second table uses actual live dialog values, including the full stored close rather than the two-decimal approximation:

| Case | Actual displayed shares | Actual displayed price | Actual displayed equity USD | Actual market cap USD | Hypothetical P/B = reconstructed P/B | Reconstruction / hypothetical |
| --- | --- | --- | --- | --- | --- | --- |
| AMT | 463763555.0 | 183.8300018310547 | 3516600000.0 | 85253655164.82643 | 24.243205131327542 | 1.0 |
| BA | 792449940.0 | 168.17999267578125 | 6547000000.0 | 133274225105.12329 | 20.35653354286288 | 1.0 |
| DHR | 703530815.0 | 232.0 | 53621000000.0 | 163219149080.0 | 3.0439407896160087 | 1.0 |

Actual display/calculation ratios for shares, price and equity are all exactly **1.0**. Actual binary64 P/B residual is **0.0** for all three. Independent Decimal recomputation of the emitted text differs from the P/B text by only 8.17e-16 (AMT), 2.39e-15 (BA) and 4.67e-17 (DHR). Audit tolerance is `abs(a-b) <= max(1e-12, 1e-12*abs(b))`; all pass. It is not a 10× effect.

The current raw text includes `New parent equity: 3516600000.0`, `6547000000.0` and `53621000000.0` respectively. Each has one more zero than the supplied reconstruction figure. The current field is an ungrouped decimal float string, not an integer count of millions or billions. There is no formatting scale in this dialog. No evidence establishes a historical source change since an unidentified screenshot: only one retained ARQ observation exists for each of these company/report-period pairs, with the larger equity stated here. All nine queued cases match the current detector; the recorded ownership audit history contains no approved decision.

## 3. UI field provenance and actual runtime capture

[The dialog constructor](../../dev_tools/fundamentals_admin_page.py#L954) calls the [service review preview](../../rawcandle/fundamentals/admin/ui_service.py#L857), which uses the current resolved production paths and calls [pb_ownership_review.preview](../../rawcandle/fundamentals/admin/pb_ownership_review.py#L223). No approval function was invoked.

The diagnostic executed the unchanged dialog function extracted from its AST with real Flet controls, a headless page and the actual read-only preview result. Approve/Hold callbacks were replaced by fail-fast sentinels and never dispatched. It captured `ft.Text.value`, parsed the displayed operands and P/B back out, and recomputed the result. It did not launch a live UI or inspect pixel rendering. In-memory instrumentation around the unchanged current_pb callable captured complete row, quote, review-record arguments and results, including held/prior/hypothetical calls. Source files were not edited.

| Displayed field | Immediate UI expression | Stored / calculation provenance | Conversion |
| --- | --- | --- | --- |
| New shares | item['new']['sharesbas'] | Queue candidate_json → detect/latest_basis → v4_parent_equity_source.sharesbas; same accepted provider observation as shares provenance | Raw numeric string → finite float; no scale |
| Price | hypothetical.get('price') | preview → book_value_report → latest usable osakedata.close; date in current.price_date | finite(close); no unit multiplier |
| New parent equity | item['new']['parent_equity_usd'] | Queue candidate_json → latest_basis → v4_quarter_financials.parent_equity_usd → provider_observation.payload_json.equityusd | DIRECT finite numeric conversion; no scale |
| Hypothetical approved P/B | hypothetical.get('value') | current_pb with new accepted row plus proposed in-memory review and same current quote | price × reviewed economic units / parent_equity_usd |

The queue contributes shares/equity while the fresh effect contributes price/P/B. The observation/candidate hash revalidation currently makes those bases agree in every sampled case; nevertheless the renderer does not explicitly assert arithmetic equality of its displayed operands. Nothing in the current dialog divides an operand by ten or applies `_money` formatting.

## 4. Shares and provider-factor economic units

For all three raw provider sharesbas values are numeric strings and become the exactly representable integer-valued floats shown below; canonical shares_outstanding is an integer with the same value. Shares provenance names the same observation and uses the direct sharesbas mapping. The provider native typed row corroborates that count. No million/thousand scaling or normalization factor is present.

| Case | Raw provider sharesbas | Canonical shares_outstanding | Accepted/displayed sharesbas | Actual calculation economic units | Raw old → new sharefactor | Applied ordinary factor |
| --- | --- | --- | --- | --- | --- | --- |
| AMT | '463763555' | 463763555 | 463763555.0 | 463763555.0 | 1.0 → 1.0 | 1.0 |
| BA | '792449940' | 792449940 | 792449940.0 | 792449940.0 | 1.0 → 1.0 | 1.0 |
| DHR | '703530815' | 703530815 | 703530815.0 | 703530815.0 | 1.0 → 1.0 | 1.0 |

Provider ShareFactor is a dimensionless ownership/security-unit ratio used in provider capitalization evidence; it is not a decimal magnitude flag for equity. A raw 1.0 denotes identity in these ordinary cases. The reviewed ordinary path explicitly selects factor 1.0; an ADS path instead uses the independently reviewed positive integer numerator/denominator. Provider factors are preserved as evidence and compared exactly during review binding; an ADR factor is not inferred from price, marketcap or P/B. Equity never receives this factor.

`None` is not silently replaced by 1 in continuation classification. GE/RTX/T change 1.0 → None and are REVIEW_REQUIRED_FACTOR_CHANGE; no hypothetical continuation is calculated. In reviewed binding, None differs from a bound 1.0 and fails validation. An unreviewed generic common path also requires finite factor exactly one. A hypothetical review record construction can copy raw fields, but eligibility/classification and binding checks govern whether it may be used. No factor-null continuation policy was changed or evaluated for release here.

## 5. Price trace, adjustment and currency limits

All three current quotes are `osakedata.db:osakedata.close`, `market='usa'`, date **2026-10-27**, selected as the latest complete positive geometrically valid OHLC on/before 2026-10-28. This is one calendar day old and within the unchanged three-day gate. Calculation and UI use exactly the same close; the P/B path performs no split/dividend adjustment, FX conversion or price scaling.

| Case | Market row id | Close used and displayed | Provider observation price/date | Provider-date stored close | Current-price / provider-price |
| --- | --- | --- | --- | --- | --- |
| AMT | 15558435 | 183.8300018310547 | 183.83 / 2026-10-27 | 183.8300018310547 | 1.0000000099605868 |
| BA | 15558622 | 168.17999267578125 | 168.18 / 2026-10-27 | 168.17999267578125 | 0.9999999564501204 |
| DHR | 15559310 | 232.0 | 233.86 / 2026-10-21 | 233.86000061035156 | 0.9920465235611049 |

AMT/BA quote differences from 183.83/168.18 are stored floating representation differences, not 10× adjustments. DHR's current 232.0 quote differs legitimately from its dated provider reference 233.86; Provider P/B is not a current-price measure.

The local stock-update adapter constructs `yf.Ticker`; its `stock.history(start,end)` path copies the returned `Close` directly into market storage. The installed local yfinance history implementation defaults auto_adjust=True, back_adjust=False, with no override in that service call. Thus this source path requests adjusted OHLC; it does not request an unadjusted close. The DB bar schema stores no per-row vendor/adjustment/currency flag, so the exact historical ingestion options of each retained row cannot be independently certified from the row alone. This audit does not relabel those bars as proven unadjusted or globally certify split compatibility. There are no stored split events for these three between their prior provider basis date and current quote; absence from that bounded local table is not a complete corporate-action proof.

USD/share (ordinary U.S.-quoted securities) and USD equity are the current contract assumptions; fxusd is the raw string '1' for each. Raw equity equals raw equityusd. The raw payloads do not provide a currency label; no label was invented from that absence. No market-source or corporate-action logic was changed. These provenance limits do not create a difference between displayed and calculation price: they are the identical stored close.

## 6. Parent-equity trace

Raw provider equity/equityusd are full-unit numeric strings. The accepted conversion in [parent_equity.py](../../rawcandle/fundamentals/schema/parent_equity.py#L17) is `finite(raw['equityusd'])`, with a DIRECT provenance row. No factor-of-ten operation, market factor, FX recalculation, millions conversion or display conversion occurs.

| Case | Raw equity | Raw equityusd | Normalized accepted USD | Calculation USD | Actual dialog USD | Supplied reproduction USD |
| --- | --- | --- | --- | --- | --- | --- |
| AMT | '3516600000' | '3516600000' | 3516600000.0 | 3516600000.0 | 3516600000.0 | 351660000 |
| BA | '6547000000' | '6547000000' | 6547000000.0 | 6547000000.0 | 6547000000.0 | 654700000 |
| DHR | '53621000000' | '53621000000' | 53621000000.0 | 53621000000.0 | 53621000000.0 | 5362100000 |

The canonical source observation/hash and equity provenance point back to the exact raw observations identified above. All three equity provenance transformations are DIRECT; canonical stored and calculated/displayed values are identical. The analysis DB has no P/B or parent_equity storage columns; it is not an alternate source of a scaled denominator. P/B is calculated in the reporting query layer. The ordinary company-report renderer separately formats money in explicit M/B units (AMT 3.52 B, BA 6.55 B, DHR 53.62 B); the approval dialog does not use that formatter.

## 7. Compact calculation trace and first divergence

Steps 1–13 below are the requested complete economic-unit chain. “Raw” provider quantities retain the original strings; quotes are stored REAL values. Calculation shares are validated ordinary economic units.

| Step | AMT | BA | DHR |
| --- | --- | --- | --- |
| 1. Raw shares | '463763555' | '792449940' | '703530815' |
| 2. Normalized shares | 463763555 | 792449940 | 703530815 |
| 3. Displayed shares | 463763555.0 | 792449940.0 | 703530815.0 |
| 4. Raw stored quote | 183.8300018310547 | 168.17999267578125 | 232.0 |
| 5. Calculation price | 183.8300018310547 | 168.17999267578125 | 232.0 |
| 6. Displayed price | 183.8300018310547 | 168.17999267578125 | 232.0 |
| 7. Raw parent equity USD | '3516600000' | '6547000000' | '53621000000' |
| 8. Normalized parent equity USD | 3516600000.0 | 6547000000.0 | 53621000000.0 |
| 9. Calculation parent equity USD | 3516600000.0 | 6547000000.0 | 53621000000.0 |
| 10. Displayed parent equity USD | 3516600000.0 | 6547000000.0 | 53621000000.0 |
| 11. Calculated market cap USD | 85253655164.82643 | 133274225105.12329 | 163219149080.0 |
| 12. Calculated P/B | 24.243205131327542 | 20.35653354286288 | 3.0439407896160087 |
| 13. Displayed hypothetical P/B | 24.243205131327542 | 20.35653354286288 | 3.0439407896160087 |

There is **no first divergence inside the current application chain**. The first observable divergence is between the task's supplied equity figures and both steps 7–10 of the current chain. Each supplied denominator is one-tenth of the actual denominator; shares and prices agree within the request's stated approximation. There is no evidence that calculation equity is ten times actual displayed equity.

Primary root-cause class: **OTHER — screenshot-transcription discrepancy**, incorporating the user's subsequent confirmation that the supplied figures were read from images. UI_DISPLAY_SCALE_BUG, P/B_CALCULATION_SCALE_BUG, SHARES_NORMALIZATION_BUG, EQUITY_NORMALIZATION_BUG, FACTOR_APPLICATION_BUG and MIXED_UNIT_CONTRACT_BUG are not supported by this frozen current evidence. Secondary finding: ungrouped raw floats impair readability, and arithmetic reconstruction is not an explicit UI approval invariant. Neither establishes an actual current scale bug. The original screenshot pixels and historical display binding remain unexamined; the supplied transcription is not treated as an exact application output.

## 8. Current published, hypothetical and historical impact

For AMT/BA/DHR current reported P/B is **NULL / NOT_AVAILABLE / OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED**. There is no current published numerical value that is ten times wrong. The report renderer emits N/A. No approved new-quarter review was found and no old-quarter shares are used as a fallback.

| Case | Live current P/B | Held equity USD | Hypothetical P/B | Provider P/B | Provider native cap / equity | Prior reviewed Current P/B reference |
| --- | --- | --- | --- | --- | --- | --- |
| AMT | NULL | 3516600000.0 | 24.243205131327542 | 24.243 | 24.24320488995052 | MISSING_EQUITY |
| BA | NULL | 6547000000.0 | 20.35653354286288 | 20.357 | 20.35653442935696 | MISSING_EQUITY |
| DHR | NULL | 53621000000.0 | 3.0439407896160087 | 3.068 | 3.0683447976725535 | MISSING_EQUITY |

Prior-reference MISSING_EQUITY is an actual preview diagnostic at reference as-of 2026-10-08, separate from the current Q3 hypothetical. The previous review does not supply an accepted old equity fallback. No prior-reference repair is attempted.

Provider P/B histories are the four latest accepted quarter slots and preserve their own source prices/dates and rounded original P/B:

| Case | Fiscal slot | Provider date | Stored/displayed Provider P/B | Same-row marketcap / equityusd | Reason |
| --- | --- | --- | --- | --- | --- |
| AMT | 2026-Q3 | 2026-10-27 | 24.243 | 24.24320488995052 | OK |
| AMT | 2026-Q2 | 2026-07-28 | 21.483 | 21.483492817162674 | OK |
| AMT | 2026-Q1 | 2026-04-28 | 23.595 | 23.594879779140406 | OK |
| AMT | 2025-Q4 | 2026-02-24 | 24.27 | 24.269588478028748 | OK |
| BA | 2026-Q3 | 2026-10-27 | 20.357 | 20.35653442935696 | OK |
| BA | 2026-Q2 | 2026-07-28 | 28.707 | 28.707275677213115 | OK |
| BA | 2026-Q1 | 2026-04-22 | 30.452 | 30.45240740170369 | OK |
| BA | 2025-Q4 | 2026-01-30 | 33.654 | 33.65444137825449 | OK |
| DHR | 2026-Q3 | 2026-10-21 | 3.068 | 3.0683447976725535 | OK |
| DHR | 2026-Q2 | 2026-07-21 | 2.393 | 2.393289087826401 | OK |
| DHR | 2026-Q1 | 2026-04-21 | 2.6 | 2.60042111800034 | OK |
| DHR | 2025-Q4 | 2026-02-24 | 2.816 | 2.815823692884608 | OK |

All 12 provider-history rows reconstruct within the unchanged absolute tolerance 0.0005001 for three-decimal provider rounding. Current P/B and its historical as-of reconstruction are not persisted as a separate P/B history table. This audit does not claim to replay every historical market vintage or inspect previously exported files; it establishes no 10× issue in the current reporting path, sampled historical Provider P/B, or hypothetical candidate calculations. Severity is not escalated to a published numerical valuation defect on unsupported evidence.

## 9. Bounded broader sample

The sample is the complete current ownership-review table: nine OPEN cases, not a repository/universe-wide scan. PNR is a normal continuation with a +0.0104812170% share change; GE/RTX/T cover the factor-change holds. AMT/BA/DHR and GM/PSA complete the sample.

| Case | Classification | Shares change % | Factor old → new | Live current reason | Hypothetical P/B | Displayed-input reconstruction ratio |
| --- | --- | --- | --- | --- | --- | --- |
| AMT | CONTINUATION_CANDIDATE | -0.47139084336260684 | 1.0 → 1.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 24.243205131327542 | 1.0 |
| BA | CONTINUATION_CANDIDATE | 0.26315775489560433 | 1.0 → 1.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 20.35653354286288 | 1.0 |
| DHR | CONTINUATION_CANDIDATE | 0.07749243344163936 | 1.0 → 1.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 3.0439407896160087 | 1.0 |
| GE | REVIEW_REQUIRED_FACTOR_CHANGE | -0.4058157409547847 | 1.0 → NULL | MISSING_EQUITY | not calculated | N/A |
| GM | CONTINUATION_CANDIDATE | -3.8637025996174024 | 1.0 → 1.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 1.0817353644669707 | 1.0 |
| PNR | CONTINUATION_CANDIDATE | 0.010481217028912582 | 1.0 → 1.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 2.5765299466159455 | 1.0 |
| PSA | CONTINUATION_CANDIDATE | 6.390070912536072 | 1.0 → 1.0 | OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED | 4.025757519078477 | 1.0 |
| RTX | REVIEW_REQUIRED_FACTOR_CHANGE | 0.12482981516304115 | 1.0 → NULL | MISSING_EQUITY | not calculated | N/A |
| T | REVIEW_REQUIRED_FACTOR_CHANGE | -1.6915600335483116 | 1.0 → NULL | MISSING_EQUITY | not calculated | N/A |

**Affected: 0/9 sampled reviews; 0/6 numerical hypotheticals.** The other three are nonnumerical holds, not successful arithmetic comparisons. GE/RTX/T also lack current parent equity, so fresh held reason is MISSING_EQUITY before ownership validation; the queue's current_pb_status remains its generic new-quarter review status. Their review classification is still FACTOR_CHANGE. The normal UI disables Approve for those classifications. Their None factors are not an explanation for the three ordinary continuations' reported 10× mismatch.

## 10. Approval safety and inactive candidate implications

**UNKNOWN** remains the classification for ownership-continuation approval beyond the arithmetic checks performed here. The earlier uncertainty attributed to the reported 10× incident is superseded by the user's screenshot-transcription clarification: this audit identifies no economic-unit arithmetic blocker. Current AMT/BA/DHR calculations are correct, and the current dialog emits consistent operands. No operator ownership evidence review or continuation approval was authorized or performed; arithmetic consistency alone is not a new ownership authorization. The class SAFE_TO_APPROVE_DESPITE_UI_DISPLAY_BUG would wrongly assert an established UI bug, so it is not used.

The existing read-only ownership preview is the available dry-run. It calls proposed_record only in memory with operator HYPOTHETICAL, adds that record to the supplied review-record tuple and runs the existing current_pb against the new row. No review JSON file, candidate DB or decision was created. Its exact prospective financial values are:

| Case | Candidate shares / economic units | Candidate parent_equity_usd | Candidate P/B if matching review and existing gates pass |
| --- | --- | --- | --- |
| AMT | 463763555.0 | 3516600000.0 | 24.243205131327542 |
| BA | 792449940.0 | 6547000000.0 | 20.35653354286288 |
| DHR | 703530815.0 | 53621000000.0 | 3.0439407896160087 |

Read-only inspection of [approve](../../rawcandle/fundamentals/admin/pb_ownership_review.py#L250) shows that it revalidates the exact case/hash, requires OPEN/CONTINUATION_CANDIDATE and explicit operator/note/confirmation, then backs up canonical into a new inactive lane and appends the review artifact/pin. It does not rescale financial shares/equity. It compares the candidate report reason/value to the hypothetical and asserts Provider P/B/history equality. Thus, under unchanged inputs, the dry-run values above are precisely those the inactive candidate would report. This audit inspected that writer logic but did not execute it, including on copies. Controlled publication remains a separate boundary.

## 11. UI reconstruction contract gap

**An explicit displayed-input reconstruction invariant is not currently enforced.** The list button requires OPEN/CONTINUATION_CANDIDATE; the dialog then enables confirmation on nonempty operator/note and the checkbox. Neither that enable function nor the dialog renderer recomputes P/B from the emitted operand strings. Backend candidate equality checks compare calculation outputs, not UI operand reconstruction. The immutable observation/hash checks are useful and remain valid, but they are a different check.

A future fail-closed invariant should ensure that one bound calculation payload supplies displayed economic units, full-unit USD equity, price/date and hypothetical value; the displayed inputs reproduce displayed P/B within an explicit tolerance before Approve is enabled. Ordinary and ADS economic units must be distinguished explicitly. Grouped units/clear USD labels should preserve enough displayed precision for the chosen tolerance; display-rounding must not create a spurious rejection. Missing/invalid operands or a failed reconstruction must hold approval. This audit does not implement any of those changes.

## 12. Validation and runtime invariance

No pytest or writer tests were run; no full suite was run. Validation used read-only SQL, the existing pure ownership detector/preview, runtime input capture, unchanged headless dialog construction, Decimal/binary64 reconstruction and the existing pure company-report renderer. All six numerical dialogs reconstruct exactly in binary64 and within 1e-12 absolute/relative tolerance in Decimal. The 12 historical provider rows pass their separate provider-rounding tolerance. All nine candidate fingerprints/current bindings and unchanged decision rows verify.

Read-only kernel locks used the normal UI-operation, Production and scheduler lock files without rewriting lock-owner metadata. Whole-file before/after hashes below are identical. Whole provider/canonical/analysis bytes plus unchanged active/generation manifests protect their persisted watermark and accepted-generation state; no separate watermark update or refresh was invoked. The operational queue's complete nine ownership rows and all ten existing PB ownership audit events are also exactly unchanged. No approvals, holds, synchronization, publication decisions, evidence exports, inactive candidate creation, Preview/Test/Production, active-generation activation, journal recovery, manual drain, scheduler change or network request occurred.

| Artifact | Identical before/after SHA-256 |
| --- | --- |
| active_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e |
| generation_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| journal | 8c88e3894b9376be4b56cc51041274d7ca368967e87dbf532f5c491e54190eae |
| market | 0dd3a0fe6d4de465a075e7771128d11b370f3159b26a27c9d05d810fb360832f |
| provider | 6d0262597c4248d40ce8b7ac79b164b1f8fcdfc09fa72283e35486d94380ae81 |
| queue | 746836b89c2bc2bcf5880812bdcdd64024c2c4398e196e21746b74fbf0f68b99 |
| scheduler_config | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |

All inspected UI/calculation/ownership/source-acceptance modules and bundled ownership registries remain byte-identical to baseline. Existing unrelated worktree files, including the already-modified publication journal, remain untouched; its full baseline hash above is preserved. No formula, source hierarchy, ownership policy, provider/canonical/analysis data, scoring input or market-source logic changed.

Temporary evidence (not committed):

| Artifact in /tmp/pb_review_economic_units_audit | SHA-256 |
| --- | --- |
| before.json | a10a03023eaac6256b9de7475943d686c3034cfd9476bad698de06d3e9645e1e |
| audit.json | eb566456f13720c575a7959aebdb7b0a9f052a8c8327eab3a086408c6d080d5b |
| extra.json | 9d079937f295defce7364e2e65d9690f2d245b0ad08aba35dd8a61fe8cab291e |
| dialog_reconstruction.json | 8566fa6fc2d603644f4761b0cf18c3a602f34d63c6ac15781923620786f439f5 |
| price_split_check.json | 4aae6ede3f2b64f437a231608282b86a8728e4cb4bce22f8f1ce3fc080d4a1aa |
| verification.json | 4ac4d2d77c1234629b37ab360b47660588a23e8dd53d2e323d79c3e9f316e43e |

## 13. Git scope

Commit this audit Markdown only. No source, tests, raw provider payload, DB, market bar, queue, manifest, journal, screenshot, runtime artifact, log or diagnostic helper is included. No push.

## 14. Exactly one bounded next implementation phase

**P/B-REVIEW-DISPLAY-RECONSTRUCTION-INVARIANT-1 — make the ownership dialog's economic inputs readable and enforce their reconstruction before approval.** Use one observation/hash-bound preview payload for display, show grouped full-unit shares/economic units and explicit USD equity/price/date, and fail closed when displayed operands do not reproduce hypothetical P/B within a declared precision-aware tolerance. Add focused ordinary/ADS/invalid/mismatch/stale-display tests with AMT/BA/DHR as current consistent controls. Preserve formula, accepted data, factor semantics, ownership policy, writer/publication boundaries and all explicit confirmation requirements. Do not add auto-continuation or factor-null policy. No backend ×10 correction is supported by this audit, and no ownership approval is part of that recommendation.
