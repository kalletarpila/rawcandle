# Fundamentals V4 Phase 12C.2 Permanent Ten-Year Policy

## Outcome

`OUTCOME A - PERMANENT TEN-YEAR POLICY VERIFIED`.

Phase 12C.2 replaces the ordinary production bootstrap's five-year default
with one versioned minimum-ten-year Sharadar fundamentals contract. It changes
ingestion configuration and observability only. It does not change the current
company universe, ARQ/MRQ selection, canonical data, TTM values, economic
models, active pointers, production reports, or Scheduler behavior.

Phase 12D remains unauthorized. The Phase 12C.1 historical-universe blocker
remains: the current operational universe is not a survivorship-safe historical
ML universe.

## Authoritative contract

The contract lives in
`rawcandle/fundamentals/schema/sharadar_history_policy.py`:

- policy version: `SHARADAR_FUNDAMENTALS_HISTORY_POLICY_V1`;
- policy fingerprint:
  `1e025bf2a19d494cc1dd6ce3a0b49d94a966db008476f780c7e4dd671cd543b9`;
- minimum upstream request: 10 years;
- dimensions: ARQ and MRQ;
- target scope: exact current bootstrap CSV ticker universe;
- retention: `APPEND_ONLY_NO_WINDOW_PRUNING`.

Ten years is a request minimum, not an exact coverage promise, local maximum,
or cleanup cutoff. Older observations may remain. A row absent from a later
snapshot remains stored. Actual staged and retained date ranges are reported
separately from the requested horizon. The retained data is revised history,
not point-in-time history.

## Production paths

The former `download_sharadar_5y_bulk()` production path and `years=5`
default were replaced by `download_sharadar_fundamentals_bulk()`. An omitted
horizon resolves to 10. An explicit value below 10 raises `ValueError` before
artifact creation, preflight, credential resolution, or network access. Values
of 10 or more remain valid.

The normal bootstrap CLI accepts optional `--history-years` and delegates its
validation to the contract boundary. The Phase 12C staging command calls the
same production wrapper and records the same policy metadata. The generic
low-level `download_sharadar_bulk(years=...)` remains available for isolated
tests and non-production use, but no production entrypoint calls it directly.

Provider run metadata records the policy identity, requested and minimum
horizons, request scope, dimensions, target scope, and retention mode. Download
metadata records actual staged dimension ranges. Ingest metadata records actual
retained provider ranges. Credentials are excluded from URLs and serialized
metadata.

## Append-only verification

Temporary-database tests establish that:

- new periods and revision-distinct rows are inserted;
- exact replay is a logical no-op and creates no duplicates;
- an older-than-ten-year row remains after a later snapshot omits it;
- null numeric values remain null;
- unrelated Yahoo provider data remains unchanged;
- retained oldest dates are queried from stored provider rows rather than
  inferred from the requested horizon.

No delete, replacement, pruning, or rolling-window cleanup was added.

## Remaining five-year references

The remaining references are intentionally non-production:

- `sharadar_acceptance.py` preserves the historical paid-entitlement label for
  a single-company acceptance workflow and does not build a bulk years request;
- Phase 12C disk sizing recognizes the legacy five-year staging filename for
  backward-compatible size estimation only;
- Phase 12C.1 code, fixtures, and documentation describe or simulate the old
  defect;
- focused tests call the generic low-level downloader with five years to prove
  its separation from production and reject reintroduction into production;
- older phase documents remain immutable historical evidence.

The detailed classification is in
`applicable_five_year_reference_audit.csv` under the temporary evidence path.

## Source archive

The Phase 12C ZIP remains at
`temp/fundamentals_v4_phase12c/20260910T_STAGE_10Y_C/sharadar_fundamentals_10y.zip`.
Its size is 235,876,508 bytes and its verified SHA-256 is
`dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`.
The location is under `temp` and is not expected to survive normal temporary
artifact cleanup. Before Phase 12C.3, move it to a managed local data archive
under separate authorization. Do not commit the ZIP.

## Production immutability

Phase 12C.1's aggregate fingerprint was
`43274d224adb48af0f1101c868dedb592b58dca918b499640dd353ce7933a32d`.
Before the Phase 12C.2 verification, three independently created report files
had increased the report inventory from 15 to 18. Their timestamps predate this
phase's execution. The first Phase 12C.2 read-only inventory therefore records
the new preflight aggregate fingerprint
`44f85d4fc2c449f68eca504ff3be221e0d67c7cbd303147eef2f49807c74ac63`.
The final postflight matches that Phase 12C.2 preflight exactly.

Provider fundamentals remain 179,853 observations: 89,432 ARQ and 90,421 MRQ.
Database schemas, logical row counts, file and WAL hashes, active
Operating-Income V2 package, active Relative Valuation snapshot, and existing
production report hashes are unchanged. Read-only SQLite queries include
visible WAL state and do not use `immutable=1`.

Detailed evidence is under `temp/fundamentals_v4_phase12c2/`.

Verification results:

- focused Phase 12C.2, bootstrap, Phase 12C, and Phase 12C.1: 52 passed;
- complete Fundamentals V4 plus Phase 12C regressions: 825 passed;
- production database isolation: 12 passed;
- `compileall` and `git diff --check`: passed.

The complete repository suite was not run because no shared infrastructure
outside Fundamentals/provider ingestion changed. No test loaded credentials or
performed a real network request.

## Phase 12C.3

The next separately authorized phase should define a broad historical research
universe with dated identity resolution, inactive/delisted security handling,
security-type eligibility, terminal-return semantics, and explicit PIT versus
revised-history boundaries. It must not broaden operational Snapshot production
scope merely to satisfy ML research needs.
