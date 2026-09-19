# Phase 13G.2.6 Add Tickers Production Preflight and Administration UX

## Outcome

Phase 13G.2.6 completed successfully on 2026-09-19. Add Tickers now uses a dedicated
exact-production validation route inside the guarded B3 transaction. The Phase 13D
copy-only guard remains unchanged and still rejects live production databases.

The Administration UI now derives its final message from the backend outcome, retains
scrollable progress events, and displays a user-facing Stage column and meaningful Count.
Reports identify Operation, Stage, Result, and Duration, while detailed fingerprints remain
in the Technical Appendix.

## Root Cause and Fix

`production_operations._add_validate()` rebuilt the saved plan through
`build_preview_from_copy()`. That copy-only helper correctly calls the Phase 13D production
path refusal guard, but the B3 production transaction had already verified explicit intent
and exact paths. Consequently, the production provider path was rejected before Preview/Test
binding and before any write.

`ProductionOperation` now supports a separate production validator selected only when
`run_transaction()` has established an actual, explicitly authorized production transaction.
The Add Tickers production validator revalidates all five exact production paths and rebuilds
the generic read-only plan directly. Rehearsal and copy validation continue through the
copy-only helper.

## Acceptance

- Focused UI and transaction suite: 56 passed.
- New contract and report checks: 7 passed, followed by the direct exact-production check.
- Broad Admin, B1/full-V2, RP, RV, taxonomy, and Scheduler UI suite: 305 passed in 266.56 s.
- Local UI route: HTTP 200 at `http://127.0.0.1:8573/fundamentals/admin`.
- Browser screenshot automation was unavailable because this environment has neither
  Chromium nor Playwright; Flet control tests verified progress scrolling and layout state.
- Isolated Preview -> Test on copies -> guarded production rehearsal completed, including
  backups, source mutation, full V2 candidate, atomic replacement, and postflight.
- Controlled preflight failure reporting was verified: no success wording, no writes,
  no backup required, and no rollback required.

## Production Retry

Fresh Preview:

- Run: `20260919T075233Z_add_tickers_2926098254ee`
- Result: 9 eligible
- Fingerprint: `24e97a9b2a571a2369d7dfa3410db8ff51cc86a63f64376386181bbd46ee2def`

Fresh Test on copies:

- Run: `20260919T075404Z_add_tickers_4f6c0b45159a_apply`
- Result: 9 applied
- Full V2, package, RP V2, and RV invocation counts: one each
- No production databases changed; heavy copy databases were removed automatically

Production update:

- Run: `20260919T080318Z_add_tickers_4f6c0b45159a_production_e87a68ab`
- Result: `COMPLETED`
- Source state verified: yes
- Atomic replacement: `REPLACED`, same filesystem
- B1 gate: `READY`
- Postflight: passed; SQLite quick check `ok`, no foreign-key violations
- Rollback: not required
- Production analysis SHA-256:
  `fedbb50ac4463fb00f12868fb835d7d1b4825cd0402be310a84d2f43bd981ff8`

The initial corrected-command attempt omitted the CLI-required `--apply` switch and was
rejected by argument validation before a run directory or backend production transaction
was created. The subsequent command was the only production transaction invocation.

## Ticker Outcomes

| Ticker | Company | Security | Provider rows | V2 score/valuation/diagnostic | RP V2 rows |
| --- | ---: | ---: | ---: | --- | ---: |
| TSEM | 2470 | 2482 | 261 | 41 / 41 / 41 | 8 |
| TSM | 2471 | 2483 | 216 | 41 / 41 / 41 | 8 |
| UMC | 2472 | 2484 | 206 | 40 / 40 / 40 | 8 |
| UPST | 2473 | 2485 | 127 | 24 / 24 / 24 | 3 |
| UUUU | 2474 | 2486 | 187 | 41 / 41 / 41 | 6 |
| VNET | 2475 | 2487 | 213 | 41 / 41 / 41 | 8 |
| WPM | 2476 | 2488 | 232 | 41 / 41 / 41 | 8 |
| WULF | 2477 | 2489 | 185 | 41 / 41 / 41 | 4 |
| WYFI | 2478 | 2490 | 40 | 7 / 7 / 7 | 4 |

All securities are active. The active RP snapshot is
`CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V2` and `COMPLETE`. The RV snapshot is
`COMPLETE` with 2,444 companies and passed the full-rebuild validation gate. Per-ticker RV
rows are not required for every company by the RV input eligibility contract.

The active taxonomy remained `DC_TAXONOMY_FULL_V2_1` with semantic fingerprint
`801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.
Mapped taxonomy companies increased from 225 to 233 and unresolved ticker identities fell
from 32 to 24. Eight added tickers were resolved; UPST is not a member of the active taxonomy.

## Safety and Cleanup

The production write set was provider, canonical, and analysis only. Market classification
and active taxonomy remained read-only. Locks, verified backups, source binding, B1 READY,
same-filesystem replacement, postflight, and rollback remained enabled.

The verified 2.4 GiB rollback backup is retained at
`backups/fundamentals_admin_production/20260919T080318Z_add_tickers_4f6c0b45159a_production_e87a68ab`.
No phase-owned rehearsal database or candidate remains. Scheduler service and timer were
inactive before the retry and remain inactive; the production lock is free.
