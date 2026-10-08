# P/B.8A — Ownership durability safety audit: STOP

Date: **2026-10-08**, Europe/Helsinki. **Durable ownership is NOT implemented.** The task's section Y STOP condition applies: automatic future reuse would trust the absence of corporate actions without an available safety contract. No review interval was extended, no V2 artifact was created, and no source or test file changed. This is a blocked implementation audit, not a completed durability release.

Active generation remains **pb_reporting_20261007T193505Z**. P/B.8 deployed `PB_OWNERSHIP_BASIS_V1` with 63 records valid on October 7 only. Its source code, registry and accounting/reporting semantics remain unchanged.

## Evidence establishing the STOP condition

- `docs/fundamentals_v4/fundamentals_v4_pb_ownership_contract_v1.md`, Validity and Carry-Forward, explicitly says there is no complete current action/issuance feed in the reporting architecture. The P/B.6 audit likewise labels its stored action query incomplete and does not certify an exhaustive post-filing issuance/buyback search.
- `rawcandle/fundamentals/ownership_basis.py` accepts known events from static registry `known_share_changes` and optional row `ownership_share_changes`. All 63 current registry lists are empty. `rawcandle/fundamentals/book_value.py:book_value_report` never supplies the dynamic event list or `newer_share_count_required`. Tests inject these inputs directly; they do not establish a live event-acquisition/reconciliation path.
- Live provider `sharadar_action_metadata` contains **156 rows**, maximum action date **2026-08-31**, maximum fetched timestamp **2026-08-31T06:24:31Z**. It has splits, relations, dividends, listing/name/SIC events and acquisitions. It has no coverage watermark or assertion covering all relevant issuance, retirement, treasury, class, merger or official ADS-ratio changes through October 8. A maximum event date is not a completeness watermark.
- `schema/bootstrap_review.py:insert_actions_metadata` filters imports to flagged tickers/contra-tickers. This is scoped metadata, not guaranteed continuous assurance for the reviewed cohort.
- `admin/refresh_copy_runtime.py:_provider_unrelated_fingerprint` counts action/ticker metadata as unrelated state; the normal Fundamentals history replacement/rebuild does not refresh an ownership action-coverage witness. Category and declared factor can detect some contradictions, but unchanged rounded metadata or SCNI's unchanged raw zero cannot establish absence of a new official ratio.

Turning `effective_to` into NULL would remove the evidence boundary while leaving these missing inputs absent. A 180-day source-age limit bounds count age but cannot establish that a material action has not already occurred within those 180 days. Retaining observation hashes would not solve daily expiry; removing them would additionally permit unverified new-quarter identity/count reuse.

## Stable evidence and observation evidence

The requested distinction is sound, but not yet executable safely:

| Evidence | Required future contract |
|---|---|
| Stable identity | Versioned company/security/issuer/quoted-unit/type/perimeter/class witness, effective start and optional end, contradiction and closure provenance |
| Stable official ADS factor | Exact rational factor and its effective interval, depositary/security identity, official ratio/program/split contradiction checks; raw provider zero remains diagnostic |
| Current accepted shares | New ARQ observation/hash, positive finite sharesbas, accepted shares provenance, count source date, provider category/factor and source availability; never copy an old count's approval |
| Carry-forward coverage | Explicit issuer/security/event scope and verified-through watermark, unavailable/conflicting coverage holds, known-event reconciliation to a newly dated accepted count |
| Calculation date | Version activation/as-of selection independent of count date; price date and count-date freshness rules stay unchanged |

The existing parent projection contains accepted observation/hash, sharesbas, category, factor and availability, but **does not carry an independently sourced share-count date for future observations, complete class/perimeter witnesses or official ratio-change coverage**. Provider filing availability is not automatically the date to which a cover share count refers. No missing fields were invented.

## Registry migration classification

The compact validation CSV records every existing review separately, including original observation/hash and evidence references.

- **31** supported records are candidates for reusing stable identity evidence: **16 ordinary/common, nine direct-common identity overrides, six ADS**.
- **Six** contain exact official factor evidence that is a candidate for reuse with a verified effective interval and continuing contradiction coverage.
- **31** supported share-count witnesses remain observation-specific; a new count/date must be established for each new accepted observation.
- **Zero** records were approved for automatic next-quarter continuation or migrated to open-ended validity.
- Later-event continuation safety is **unknown for all 31**, not certified absent and not asserted blocked by a newly discovered event. Existing evidence ends October 7.
- **32** explicit holds and the unaudited cohort receive no approval. KALA/FTFT's separate share-basis reviews remain unchanged. Under unchanged V1, October 8's date-expiry reason masks the original registry hold reason for these 32; their ineligibility is preserved.

This classification recognizes reusable evidence candidates; it does not certify the new-period truth of their structure or ratio. Proceeding requires the missing machine-readable evidence/coverage contract, rather than manual daily date extensions.

## Refresh integration

Normal `refresh_copy_runtime.fresh_rebuild_canonical` calls `phase12d.reconcile_canonical`. The reconciliation transaction calls `accept_parent_equity`, rebuilding parent fields and dedicated source/provenance from the accepted shares ARQ observation. Thus parent equity, Provider P/B and accepted-quarter history already refresh through the normal workflow. Report assembly reevaluates current ownership every run.

The remaining lifecycle gap is not a missing manual P/B command: V1 deliberately binds observation ID/hash, old sharesbas and factor. A new accepted observation fails that binding. Before V2 can safely inherit identity, reconciliation/reporting must have the new count's actual source date and a compatible current issuer/security/unit/perimeter witness plus action/ratio coverage. A reconciled Boolean alone must remain insufficient. Security/issuer/class/ratio changes need explicit hard holds; no ticker exception or cap/PB-derived factor can substitute.

## Copy validation and measured coverage

Fresh SQLite backups of the live provider, canonical, analysis and market databases were made under **`/tmp/rawcandle_pb8a`**, reading Production in mode=ro. No canonical migration was needed or performed. Calculations on all **2,468** operational members used unchanged V1 code and one copied market state for October 7, 8 and 9.

| As-of | Valid Current P/B | Review stale | Share basis hold | Stale price |
|---|---:|---:|---:|---:|
| 2026-10-07 | 1721 | 0 | 6 | 12 |
| 2026-10-08 | 1690 | 63 | 6 | 12 |
| 2026-10-09 | 1689 | 63 | 6 | 13 |

Exactly **31 previously valid reviewed cases become OWNERSHIP_REVIEW_STALE on October 8**. No other hard reason changes between the October 7 and October 8 copy runs. Relative to rollout's 1,722, next-day count is **−32**: **−31 review expiry** and **−1 existing market-input change (CTVA)**. October 9 adds one stale-price hold under the existing three-day rule. The requested durability target is **not met**.

Production market data has changed since rollout: October 7 quote bars arrived, and CTVA now has a historical-price corroboration mismatch. An initial exact comparison with frozen `/tmp/pb8_reports.json` correctly failed on changed quote inputs. A diagnostic copy-only cutoff removed October 7 bars but still exposed CTVA's mismatch, so it was discarded and the market copy recreated from Production before the final measurements. No historical quotes were fabricated or repaired to force 1,722. These results use the newly copied market state, not a claimed byte-identical P/B.8 market snapshot.

All **2,468 original Provider P/B objects and all 4Q history objects** exactly match frozen P/B.8 output and remain identical across the three dates. No new quarter was fabricated as an accepted production observation.

| Requested simulation | Result |
|---|---|
| Q1 next day, retained reviewed eligibility | FAIL under unchanged V1: 31 released cases expire |
| Q2 new ordinary quarter/count | NOT IMPLEMENTED: STOP; V1's exact binding still rejects new observation/hash/count |
| Q3 new ADS quarter, same official ratio | NOT IMPLEMENTED: STOP; continuing official factor/count coverage is missing |
| Q4 identity/class conflict | Existing adversarial binding/multi-class hold tests pass; no V2 lifecycle simulation claimed |
| Q5 intervening issuance | Existing supplied-event tests block, including a reconciled Boolean; automatic reconciled new-quarter restoration not implemented |

## Reproducibility and safety

V1 historical semantics and the immutable registry are untouched. Old reports remain stored with their original contract and output. **Exact numerical replay of all P/B.8 Current P/B objects against today's market DB is not demonstrated**: only 30 entire objects still match because current quote inputs changed for most companies. This is input mutability, not a reinterpretation by V2. Byte-identical market inputs would also be needed for exact replay; a future V2 must activate from its own date/version and preserve V1 selection for October 7. No V2 selector was added.

Source Production DB SHA-256, size and mtime, plus active manifest bytes, were checked before/after copy validation and stayed identical. Provider/canonical/analysis hashes match the P/B.8 activated set. Analysis being unchanged covers score/model fingerprints; no source or score code changed. Provider/4Q, parent accounting, price rules, publication authority, scheduler and Review Queue were not modified. Revised market inputs described above predate the audit's copy and were not caused by this work.

Focused baseline ownership/P/B/refresh tests: **99 passed** (`test_fundamentals_pb_ownership.py`, `test_fundamentals_pb_reporting.py`, `test_phase12d_operational_rebuild.py`). One reporting regression group: **49 passed** (`test_fundamentals_snapshot_ui.py`). These verify the existing safety contract; they are **not** passing tests for an implemented durable lifecycle. Full suite **not run**. No source changes or new behavior tests were committed because implementation stopped at the safety prerequisite.

## Required prerequisite to resume

Define and provide a scoped automated evidence contract that establishes issuer/security/unit/class/perimeter consistency, official ADS factor validity and relevant share-action coverage through the calculation/price period. It must expose acquisition freshness/completeness, coverage gaps, contradiction closure, actual share-count source dates and event-to-new-count reconciliation. Do not use absence of rows or unchanged provider factor as an assurance. With this input, a dated V2 artifact and observation revalidation can be implemented and tested on copies; until then neither open-ended approvals nor the requested next-quarter automation are authorized by the task's safety conditions.

**Production rollout: NO. Production DBs changed: NO. Active generation changed: NO. Current formula changed: NO. Ownership lifecycle changed: NO. Registry changed: NO. Provider/4Q/score semantics changed: NO. Full suite: NO. Push: NO.** Only this audit report and compact 63-record validation CSV are committed. The implementation acceptance criteria remain unmet.
