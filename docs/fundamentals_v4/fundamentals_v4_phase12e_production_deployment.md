# Phase 12E Ten-Year Operational History Production Deployment

## Outcome

`PHASE 12E COMPLETE - TEN-YEAR OPERATIONAL HISTORY ACTIVE AND STABLE`

The deployment ran on branch `chore/ignore-backups` at implementation HEAD
`9d3d49332ce4a811763cb4cbadfb631d708fa6f3`. It wrote only:

- `/home/kalle/projects/rawcandle/data/fundamentals_v4.db`
- `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`

The provider, market, taxonomy, Scheduler configuration, and existing
`fundamental_reports` content were unchanged. No provider request or push was made.

## Commands And Tests

Production command:

```text
python3 -m rawcandle.cli.run_phase12e_ten_year_production \
  --output temp/fundamentals_v4_phase12e/20260911T_PHASE12E_PRODUCTION_V2 \
  --apply --confirm-production
```

Verification completed before the accepted write:

- `pytest -q`: 2,835 passed, 8 warnings in 407.76 seconds.
- Focused deployment, rebuild, persistence, activation, and Relative Valuation tests:
  23 passed.
- Focused post-adapter-correction tests: 34 passed.
- `python3 -m compileall -q rawcandle`: passed.
- `git diff --check`: passed.

The first production attempt in
`temp/fundamentals_v4_phase12e/20260911T_PHASE12E_PRODUCTION_V1` stopped on a
presentation-evidence adapter `KeyError` before acceptance. The full-pair restore
handler restored both canonical and analysis databases byte-for-byte to their
pre-write backup SHA-256 values. Schema, row counts, active pointers,
`quick_check=ok`, and zero foreign-key violations were verified before the lock was
released. The adapter key was corrected in commit `9d3d493` without changing any
economic calculation.

## Reconciliation

| Measure | Result |
| --- | ---: |
| Canonical, TTM, and downstream endpoints | 87,319 |
| New historical endpoints | 36,734 |
| Revised overlap | 395 |
| Unchanged overlap | 50,190 |
| Existing overlap endpoints | 50,585 |
| Existing endpoint readiness changes | 6,383 |
| Removed endpoints | 0 |
| Score/Delta component rows | 611,233 each |
| Diagnostic evaluations | 698,552 |
| Duplicate Diagnostic evaluations | 0 |
| Orphan Diagnostic evaluations | 0 |
| BTAI / HLX quarters | 21 / 21 |

Identities:

- provider source: `e98f1334d3fd7d7ce22e48a3858f487b17e414e705ab64f1baef922572d4f6f4`
- canonical: `74cd17f19b253caa75e403dfe95a081f1af3b7d0c225715db88c9f169a3737bf`
- TTM: `7b74ab52354f51b31a425eae36dbe84d9a1be9ca68ae469a6c1cf832421b9862`
- active package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- package economic result: `3fdd93b6fedcdf7384728016c55fd955a2c44dfbc03c4618a758fd1601c84b27`
- package physical content: `63fb7191889c22835ebef895dd1afbca455998345b7d4495a1382a9b747324fa`

The previous package
`0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`
is retained as historical audit evidence. Its activation is rejected because its
stable-fingerprint result rows have been replaced; it is not an activation-only
rollback target.

## Relative Valuation

The as-of rule selected `2026-09-10`: 4,205 valid USA companies versus a 3,803
completeness floor. The observed `2026-09-11` market date was incomplete. The
unchanged Relative Valuation V1 model produced:

- source fingerprint: `5705b06e1e5e2a3ef9fe30c310eda6d3c1915489f9441f324afd49db4382d743`
- result fingerprint: `293a17ae153836d46aa4caa2656dc0faefd05f16a70d67ad323b41b2f000ccd2`
- physical fingerprint: `6a37fa35d51d74900f61ff162b1a71f7e0ea6375c51c90ca264c83cd5be5abac`
- active snapshot: `7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324`
- 2,448 company rows, 9,792 peer rows, 2,448 own-history rows, and 7,344 component rows
- 2,431 current-fresh and 2,239 current peer-eligible companies
- current-fresh own-history: 877 `READY` and 120 `LIMITED_HISTORY`

Each company has four peer rows and three component-history rows. The prior active
snapshot was `b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df`.

## Backups And Storage

Verified pre-write backups are retained in
`/home/kalle/projects/rawcandle/backups/fundamentals_v4_phase12e_20260911T135700Z`:

| Database | Bytes | SHA-256 |
| --- | ---: | --- |
| canonical | 372,228,096 | `7f01be0892d3f3c25aa677c42b45217b35bffbe5e229097f919cbe89f1a02fd0` |
| analysis | 1,152,614,400 | `0b3a7f266d852c4083f7aa9da8e06657bef4a83c504c98ea5bee71bfd591f107` |

Preflight free space was 336,604,340,224 bytes against a conservative requirement
of 7,296,112,640 bytes. Canonical grew by 264,044,544 bytes to 636,272,640 bytes;
analysis grew by 381,411,328 bytes to 1,534,025,728 bytes. The measured peak journal
was 61,151,024 bytes for canonical and 808,875,800 bytes for analysis. WAL peak was
zero. No target WAL, SHM, or rollback-journal sidecar remained at postflight.

The rollback rehearsal restored both backup copies successfully, all five injected stage
failures rolled back to identical state, and stale archived-package activation was
rejected. A real failure always restores both databases from the pair backup.

## Stable State

The second complete pass returned physical and logical `NO_CHANGE`: canonical had
87,319 unchanged rows, TTM made zero writes, the package made zero logical changes,
Relative Valuation inserted no snapshot or audit row, and all database file state and
activation timestamps were unchanged. The normal provider-disabled pipeline also
returned `NO_CHANGE` with zero logical changes.

Snapshot smoke reports for NVDA, AMZN, CRMD, APD, BTAI, and HLX were generated only
under the Phase 12E artifact directory. Every report had eight Diagnostic rows and a
second generation result of `NO_CHANGE`. UI batch generation, secure download, an
unknown ticker, and traversal rejection passed. Production reports remained
byte-identical.

Detailed evidence is in
`temp/fundamentals_v4_phase12e/20260911T_PHASE12E_PRODUCTION_V2`, including
`deployment_result.json`, `backup_manifest.json`, `rollback_rehearsal.json`,
`relative_valuation_refresh.json`, `second_no_change.json`, `journal_peak.json`, and
`production_postflight.json`. Total accepted deployment duration was 1,422.69 seconds.

## Limitations

- History is currently revised, not original point-in-time history.
- The operational universe remains survivorship-limited; the broad historical-only
  research universe was not deployed.
- Phase 12B.2 remains `OUTCOME C - NO REPEATABLE EVIDENCE UNDER THE CORRECTED CONTRACT`.
- No production prediction model exists.
- Relative Valuation refresh remains manual; no Scheduler integration was added.
- Valuation V3 remains deferred research.
- Package manifests are versioned, but all underlying result rows are not append-only.
  A future append-only persistence version is outside Phase 12E.
