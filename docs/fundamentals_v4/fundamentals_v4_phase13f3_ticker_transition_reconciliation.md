# Phase 13F.3 Ticker Transition Reconciliation

Status: `OUTCOME B - COPY-ONLY REBUILD NOT READY FOR PRODUCTION DEPLOYMENT`

Phase 13F.3 supersedes the stale Phase 13F.2 input-state conclusion for the
five formerly unresolved active tickers. `data/osakedata.db` and provider
metadata now expose the successor tickers VMRK, IA, VAI, NXH and NMAD with
current price and `ticker_meta` classification evidence. Production writes were
not authorized or performed.

## Evidence

Artifact directory:

`temp/fundamentals_v4_phase13f3_ticker_transition_reconciliation/20260913T_PHASE13F3_BLOCKED_FINAL/`

Primary files:

- `phase13f3_blocked_result.json`
- `phase13f3_blocked_report.md`

Evidence fingerprint:

`3df44431ece8e133a87c6a16dc9f8efd7a1f056aa6a983c64b458025bf97a554`

Production immutability:

`true`

## Transition Decisions

| Historical ticker | Current ticker | Provider permaticker | Current price range | Current rows | Structural status |
| --- | --- | --- | --- | ---: | --- |
| EQR | VMRK | 197624 | 2018-01-02..2026-09-11 | 2185 | `MAJOR_BUSINESS_COMBINATION` |
| ISSC | IA | 198182 | 2018-01-02..2026-09-11 | 2185 | `NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE` |
| AIHS | VAI | 120343 | 2018-03-19..2026-09-11 | 2133 | `BUSINESS_COMPARABILITY_REVIEW_REQUIRED` |
| BBBY | NXH | 195902 | 2018-01-02..2026-09-11 | 2185 | `TICKER_REUSE_SEPARATION` |
| LIXT | NMAD | 108994 | 2018-01-02..2026-09-11 | 2185 | `REVERSE_MERGER_MAJOR_BUSINESS_CHANGE` |

The BBBY/NXH transition is accepted only for the current Overstock/Beyond/NXH
lineage. It is not joined to the original bankrupt Bed Bath & Beyond security
by ticker text.

## Reconciliation Results

- Phase 13F.2 unresolved current active listing intervals: `5`
- Successor-aware unresolved current active listing intervals: `0`
- Exact classification matches: `2251`
- Accepted normalized-only classification matches: `196`
- Missing classifications: `0`
- Persisted valuation classification omissions in current production state: `7`
- Semantic mismatches in current production state before copy repair: `7`

The semantic mismatches and persisted omissions remain production-state facts
because Phase 13F.3 did not perform production writes. The copy-only correction
path updates security identities and valuation classification on isolated
copies before downstream rebuild.

## Blockers

The full copy-only downstream proof did not complete in the current run. The
rehearsal reached `package_refresh` on the isolated analysis copy and did not
return in the available execution window. Transient copy databases were removed.

Outcome A is therefore not claimed. Remaining blockers:

- `COPY_ONLY_PACKAGE_REFRESH_DID_NOT_COMPLETE_IN_CURRENT_RUN`
- `FULL_RP_RV_SNAPSHOT_REBUILD_NOT_PROVEN`
- `OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT`

## Next Scope

The next separately authorized production-deployment runbook is not prepared
because Outcome A was not achieved. Before production activation, rerun the
copy-only package refresh with instrumentation or a bounded resumable
orchestrator, then prove Relative Position, manual Relative Valuation refresh,
Snapshot smoke reports, deterministic replay, true `NO_CHANGE`, rollback and
production immutability end to end.
