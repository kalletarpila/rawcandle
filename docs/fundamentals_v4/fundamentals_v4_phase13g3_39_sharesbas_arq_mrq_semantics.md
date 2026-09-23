# Phase 13G.3.39 ARQ vs MRQ `sharesbas` Semantics

## Decision

Keep canonical `shares_outstanding <- ARQ sharesbas` unchanged. Do not use MRQ `sharesbas` as a same-quarter correction or later current-share value.

The dominant local pattern is a one-quarter timing displacement: among 81,978 authority-matched ARQ/MRQ `sharesbas` disagreements, MRQ for quarter Q exactly equals ARQ for Q-1 in 79,252 cases (96.68%). It is closer to prior-quarter ARQ than same-quarter ARQ in 79,797 cases (97.34%). MRQ is therefore usually an earlier share state attached to the later fiscal identity, not a correction of same-quarter ARQ and not a later real-world state.

Phase 13G.3.39 does not authorize any ARQ/MRQ shares overlay. Its purpose is to distinguish historical corrections from later real share-count changes.

## Scope And Method

The study inspected only the current provider field contract, canonical share mapping, TTM endpoint behavior, Score dilution semantics, Valuation denominator semantics, local split data, and Phase 13G.3.38 findings.

The quantitative analysis opened `fundamentals_provider.db` and `osakedata.db` through SQLite read-only URI connections with `PRAGMA query_only=ON`. It joined observations to resolved `company_id` and selected ARQ and MRQ winners with the exact canonical reconciliation key and precedence:

`(company_id, fiscal_year, fiscal_quarter)` plus valid fiscal identity, current ticker/fiscal ordering, latest report period, latest `COALESCE(lastupdated, date)`, and observation identity.

The script lived only under `/tmp`; no analysis code or generated dataset was added to the repository. No workflow or network data acquisition was run. A narrow check of the official Nasdaq Data Link SF1 documentation did not yield machine-readable dimension-specific `sharesbas` semantics, so it was not used to force any case classification.

## Current Field Semantics

RawCandle's local contract states:

| Provider field | Local interpretation | Current downstream role |
| --- | --- | --- |
| `sharesbas` | actual period-end basic common shares outstanding | maps to canonical `shares_outstanding`; TTM endpoint stock value; Score dilution numerator/denominator; Valuation market-cap denominator |
| `shareswa` | period weighted-average basic shares used for Basic EPS | provider support and diagnostic context only |
| `shareswadil` | period weighted-average diluted shares used for Diluted EPS | provider support and diagnostic context only |

Canonical reconciliation takes `sharesbas` only from ARQ. TTM does not sum it: the endpoint quarter supplies the value. Score compares the current endpoint with four quarters earlier for YoY dilution; sequential change and split events are evidence only. Valuation multiplies the endpoint shares by the selected price to calculate market cap and enterprise value. The current split convention assumes stored price and shares are already retrospectively compatible and forbids a second automatic split adjustment.

The provider boundary stores all three native fields and both dimensions, but local metadata does not define different `sharesbas` timing rules for ARQ versus MRQ. The observed data must therefore be treated as empirical evidence, not silently converted into a provider definition.

## Timing Pattern

Across the 81,978 disagreements:

| Pattern | Cases | Share of disagreements |
| --- | ---: | ---: |
| MRQ Q exactly equals ARQ Q-1 | 79,252 | 96.675% |
| MRQ Q is closer to ARQ Q-1 than ARQ Q | 79,797 | 97.340% |
| MRQ Q exactly equals ARQ Q+1 | 83 | 0.101% |
| MRQ Q is closer to ARQ Q+1 than ARQ Q | 9,151 | 11.163% |
| MRQ `date` equals `reportperiod` | 81,978 | 100.000% |
| ARQ `date` is after `reportperiod` | 81,977 | 99.999% |
| ARQ and MRQ have the same `lastupdated` | 81,110 | 98.941% |

The “closer to next ARQ” statistic is not correction evidence: a value can be closer to both adjacent quarters than to a large same-quarter step. Exact next-quarter matches are rare, while exact prior-quarter matches dominate.

Examples show the rule directly:

- AAPL 2026-Q3: MRQ 14,687,356,000 equals ARQ 2026-Q2; ARQ 2026-Q3 is 14,594,180,000.
- AMD 2026-Q2: MRQ 1,630,600,639 equals ARQ 2026-Q1; ARQ 2026-Q2 is 1,632,475,042.
- NVDA 2027-Q2: MRQ 24.2 billion equals ARQ 2027-Q1; ARQ 2027-Q2 is 24.1 billion.
- LOVE 2027-Q2: MRQ 14,638,418 equals ARQ 2027-Q1; ARQ 2027-Q2 is 14,423,433.
- VRT 2026-Q2: MRQ 384,108,816 equals ARQ 2026-Q1; ARQ 2026-Q2 is 384,988,173.

This is a dimension/timing convention in the local provider data. It is not evidence that ARQ was wrong.

## Weighted-Share Diagnostics

MRQ `sharesbas` is within 0.1% of same-quarter ARQ `shareswa` in 25,328 cases (30.90%) and `shareswadil` in 10,287 cases (12.55%). Exact equality is much rarer: 613 cases (0.75%) for `shareswa` and 460 (0.56%) for `shareswadil`.

The weighted-share fields therefore provide context but do not explain the dominant pattern. The 96.68% exact prior-ARQ match is far stronger. Substituting either weighted field would also change the economic meaning from period-end ownership to an EPS denominator.

## Split And Corporate-Action Evidence

Local `splits_data` events occurred in the prior-report-period to ARQ-availability interval for 1,366 disagreements (1.67%). Only 81 cases (0.10%) had an ARQ share-count step approximately matching a local split ratio or its inverse under an 8% tolerance.

Splits explain a small, important exception class, but they do not explain the broad ARQ/MRQ disagreement. Most cases have no split evidence, and the same one-quarter-lag pattern occurs continuously in ordinary large-cap histories. Because stored shares are already commonly on a comparable split-adjusted basis, the event remains evidence; it does not authorize another mechanical adjustment.

## Classification Framework

- `HISTORICAL_CORRECTION_CANDIDATE`: requires positive evidence that MRQ corrects the same historical quarter-end state. Similarity alone is insufficient.
- `LATER_REAL_SHARE_CHANGE`: requires evidence that MRQ represents a state after the valid ARQ quarter. An earlier/lagged state cannot qualify.
- `DEFINITION_OR_TIMING_DIFFERENCE`: used when MRQ equals or is within 0.1% of prior ARQ, or clearly follows a support-field convention without correction evidence.
- `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION`: used when a local event exists and its ratio explains the ARQ sequence step.
- `UNRESOLVED`: used when surrounding sequence or action evidence is insufficient or contradictory.

The classifier deliberately has no automatic positive rule for historical correction or later real change. Those classes require evidence absent from the local winner rows.

## Forty-Case Sample

The deterministic sample includes named large-cap/datacenter/recent-IPO/small-company probes, latest large-percentage differences, split-ratio matches, persistent small differences, large ARQ steps without a local split, and unresolved exceptions. Percentage is `(MRQ / ARQ - 1)` for the target fiscal quarter.

| Ticker | Fiscal quarter | Selection | Difference | Classification | Local evidence |
| --- | --- | --- | ---: | --- | --- |
| AAPL | 2026-Q3 | Named | 0.638% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| MSFT | 2026-Q4 | Named | 0.039% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near `shareswa` |
| NVDA | 2027-Q2 | Named | 0.415% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near `shareswa` |
| AMZN | 2026-Q2 | Named | -0.271% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| GOOGL | 2026-Q2 | Named | -0.932% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| AMD | 2026-Q2 | Named | -0.115% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near `shareswa` |
| AVGO | 2026-Q3 | Named | -0.336% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| VRT | 2026-Q2 | Named | -0.228% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| ANET | 2026-Q2 | Named | -0.160% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near `shareswa` |
| CRWV | 2026-Q2 | Recent IPO | -1.082% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| FLWS | 2026-Q4 | Small/structural | -0.135% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near weighted fields |
| LOVE | 2027-Q2 | Small/structural | 1.491% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near weighted fields |
| PSQL | 2025-Q4 | Recent/structural | -84.298% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| BTDR | 2026-Q2 | Large difference | 162.830% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| AREB | 2025-Q4 | Large difference | -98.685% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; multiple later split events do not explain target step |
| NUWE | 2026-Q2 | Large difference | -97.900% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; split window present |
| CHRN | 2026-Q4 | Large difference | -97.553% | `UNRESOLVED` | no prior/next sequence evidence |
| WHLR | 2026-Q2 | Large difference | -97.301% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; multiple split events |
| MLGO | 2025-Q2 | Large difference | -96.479% | `UNRESOLVED` | no prior sequence; split evidence insufficient |
| FTFT | 2026-Q2 | Large difference | -95.448% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; split window present |
| RNAZ | 2026-Q2 | Large difference | -94.387% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| MTVA | 2019-Q4 | Split-ratio match | -96.211% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local 0.04 ratio explains ARQ step |
| DELL | 2019-Q4 | Corporate-action ratio match | 93.190% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local 1.806 ratio explains step |
| GRI | 2023-Q4 | Split-ratio match | -85.493% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local 1:7 reverse split |
| WHLR | 2025-Q3 | Split-ratio match | -79.132% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local 1:5 reverse split |
| ELAB | 2026-Q1 | Split-ratio match | -74.490% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; two reverse splits in window |
| ILLR | 2024-Q3 | Corporate-action ratio match | -74.474% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local action ratios explain step |
| CNX | 2017-Q4 | Corporate-action ratio match | 23.403% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local 1.2 ratio explains step |
| CTO | 2020-Q4 | Corporate-action ratio match | -20.715% | `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | MRQ = prior ARQ; local 1.228 ratio explains step |
| VZ | 2026-Q2 | Small persistent | 0.500% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| PM | 2026-Q2 | Small persistent | -0.004% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near `shareswa` |
| PKG | 2026-Q2 | Small persistent | 0.0004% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near `shareswa` |
| BMI | 2026-Q2 | Small persistent | 0.686% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| ROL | 2026-Q2 | Small persistent | 0.066% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near weighted fields |
| KMI | 2026-Q2 | Small persistent | -0.089% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ; near weighted fields |
| PTIX | 2016-Q4 | Large ARQ step, no split | -19.037% | `UNRESOLVED` | MRQ is closer to next ARQ; insufficient cause evidence |
| GNLN | 2025-Q1 | Large ARQ step, no split | -99.183% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| KALA | 2025-Q4 | Large ARQ step, no split | -99.117% | `DEFINITION_OR_TIMING_DIFFERENCE` | MRQ = prior ARQ |
| PTIX | 2016-Q3 | Exception | 40,227.056% | `UNRESOLVED` | MRQ closer to next ARQ; no reliable local cause |
| HURA | 2024-Q1 | Exception | 1,052.300% | `UNRESOLVED` | MRQ closer to next ARQ; no reliable local cause |

KRSA and QVCG were requested named probes but had no authority-matched `sharesbas` disagreement eligible for this sample. They were not replaced with forced classifications.

## Quantitative Classification

| Classification | Cases | Sample share | Median absolute difference | 90th percentile | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| `HISTORICAL_CORRECTION_CANDIDATE` | 0 | 0.0% | n/a | n/a | n/a |
| `LATER_REAL_SHARE_CHANGE` | 0 | 0.0% | n/a | n/a | n/a |
| `DEFINITION_OR_TIMING_DIFFERENCE` | 27 | 67.5% | 0.638% | 99.117% | 162.830% |
| `SPLIT_OR_CORPORATE_ACTION_NORMALIZATION` | 8 | 20.0% | 76.811% | 96.211% | 96.211% |
| `UNRESOLVED` | 5 | 12.5% | 97.553% | 40,227.056% | 40,227.056% |

The sample is deliberately stratified and is not an estimator of population class prevalence. Across all disagreements, the median absolute ARQ-to-MRQ difference is 0.416%, the 90th percentile 5.763%, the 99th percentile 61.717%, and the maximum 40,227.056%.

Within the sample, 35/40 cases exactly match prior-quarter ARQ, 4/40 are closer to next-quarter ARQ than same-quarter ARQ, 13/40 have a split event in the timing window, and 11/40 are within 0.1% of `shareswa`. These diagnostics can overlap.

## Correction Versus Later Change

### Historical correction

No sampled case has positive local evidence that MRQ corrected an incorrect same-quarter ARQ value. Exact equality with the prior ARQ quarter is evidence against that interpretation. A correction would require filing-level quarter-end evidence, a provider correction record, or a dimension contract tying MRQ explicitly to the same quarter-end state.

### Later real share change

No sampled case establishes MRQ as a later real share state. MRQ `date` equals the period end, ARQ is normally dated at the later filing/source-availability date, and the MRQ value overwhelmingly equals the earlier ARQ quarter. Buybacks, issuance, conversions, compensation, and M&A may explain the change from prior ARQ to current ARQ, but that makes MRQ stale for Q; it does not make MRQ a later authority.

### Timing/definition difference

This is the ordinary pattern. MRQ Q carries a prior-quarter `sharesbas` state while `shareswa` and `shareswadil` generally retain same-quarter weighted-period semantics. The row is therefore internally unsuitable for a field-level same-quarter overlay.

### Split/corporate action

The eight sampled action cases show why sequence and event evidence are necessary. Their large differences can be explained by an ARQ step aligned with a local action ratio, while MRQ still commonly carries prior ARQ. These cases need split-compatible source interpretation, not MRQ replacement or a second share adjustment.

## Automation Feasibility

A safe positive historical-correction detector cannot be built from current local data.

Mechanically detectable exclusions are possible:

- reject MRQ as a correction when it equals prior-quarter ARQ;
- reject rows without a contiguous surrounding sequence;
- separate split/action windows from ordinary changes;
- treat period-end MRQ `date` as non-authoritative for publication timing;
- fail closed on contradictory provider versions or identity changes.

These rules identify timing differences and review cases; they do not prove that any remaining MRQ value is the correct same-quarter historical value. “MRQ differs and later ARQ converges” is also insufficient because buybacks, issuance, and normalization can produce the same numerical pattern.

Therefore automatic correction detection is **NO** under the present evidence. Only filing-level or explicit provider correction evidence could authorize a manually reviewed historical repair.

## Downstream Consequences

| Classification | Correct modeling behavior |
| --- | --- |
| Historical correction, externally proven | A separately versioned repair may revise canonical historical shares, dilution history, market cap, enterprise value, Valuation, Score, RP/RV, snapshots, and backtests. Preserve original and repair provenance. |
| Later real share change | Keep the earlier ARQ quarter unchanged. Introduce the new share state only at the first later period for which it is valid and available. |
| Definition/timing difference | Do not overlay. Keep ARQ authority and retain MRQ only as diagnostic provider evidence. |
| Split/corporate-action normalization | Keep one split-compatible stored basis, record event evidence, and do not apply an unproved second adjustment. |
| Unresolved | Fail closed; no canonical or downstream change. |

Phase 13G.3.38's what-if calculation already demonstrated the blast radius: a naive historical MRQ share overlay changed latest Score for 1,762 companies and latest Valuation for 1,574. Those are sensitivity results, not corrected truths. AAPL, NVDA, AMD, AVGO, VRT, and ANET changed despite no latest economic-field change; LOVE's Score moved by about 2.20 points. This reinforces the need for positive authority evidence before any share repair.

## Recommendation

1. Keep `sharesbas` ARQ-only in canonical, TTM, Score, and Valuation.
2. Do not develop a general MRQ correction overlay from this dataset.
3. Optionally add future read-only diagnostics for `MRQ_SHARESBAS_EQUALS_PRIOR_ARQ`, split/action context, and unresolved exceptions; this phase does not implement them.
4. Allow a historical share repair only through a separate manually reviewed workflow backed by filing-level or explicit provider correction evidence and full downstream regeneration.
5. If a true current-share estimate is later needed, design a separate current-share-state source and availability contract. Do not derive it by relabeling lagged MRQ values.

## Unresolved Questions

- Why does the provider populate MRQ Q `sharesbas` from ARQ Q-1 so consistently while keeping same-quarter weighted-share fields?
- Are the 2,726 non-exact-prior disagreement cases provider exceptions, identity/action effects, missing-quarter effects, or true corrections?
- Can provider support supply dimension-specific field timing documentation or correction lineage unavailable in the local schema?
- Which high-impact unresolved cases merit filing-level manual review, if any, given that no production overlay is currently justified?
