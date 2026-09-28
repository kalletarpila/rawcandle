# Yahoo Sparse Fiscal Estimate Investigation (2026-09-28)

## 1. Scope And Decision

This investigation covers ATLX, BHP, BIVI, BTCT, CBL, JBGS, NFE, NUWE,
SIDU, SIGA, and VEEE at the Yahoo `quoteSummary/earningsTrend` boundary.
Evidence consists of 33 immutable production fetches, their 11 deduplicated
raw bodies, and two new read-only live rounds. No forecast or Fundamentals row
was written, rewritten, or reclassified.

Decision:

```text
KEEP_CURRENT_MALFORMED
```

The evidence does not contain a usable row with incomplete target metadata.
Every row missing `endDate` is the already accepted exact empty Yahoo template.
All usable rows have a string `period` and valid ISO `endDate`. The actual
shape is therefore `MIXED_TARGETED_DATA_AND_EMPTY_INCOMPLETE_ROWS`, not a
usable sparse fiscal observation. Implementing a generic sparse-target V2 from
this evidence would claim semantics the provider has not supplied.

## 2. Historical Production Evidence

All symbols have one fetch in each of these runs:

- R1: `e31ffae704a843ffab97dc9b25d8bf27`
- R2: `383460c92c33448094589b84c1555b60`
- R3: `dd088c08f70945ed8b83aa9cb025d947`

Every fetch is `MALFORMED_OR_SCHEMA_MISMATCH` with error code
`ForecastContractError` and message `trend row period and endDate are required
strings`. Each symbol retained the same raw hash in all three runs.

| Symbol | R1 fetch_id | R2 fetch_id | R3 fetch_id | raw evidence SHA-256 |
|---|---|---|---|---|
| ATLX | `5705ae697e244a2e98ceeedf143c7ffc` | `ac81617dff02418b9fb53470e80b4798` | `8bc0ac866c2f4fca9503d4201b8a33d2` | `529d255a5c65fa0f713d4fcc426b721ab3a06b52401643bcd14a7633842fcbd6` |
| BHP | `12ccc9220c7b4feda5537b713c41313c` | `d2982264505f49af959343dc35b30948` | `0a7fdad2c854431bb84bfb3c041667b7` | `9614987c9c144464f1938e35b668406db5ad5b0b2892027fc75990576b78fed5` |
| BIVI | `298cac7c43de46daa5fa042180484ad9` | `c151f98b6b494e82a4e75df745e324f9` | `e8e4dccfc6e04f818d9678174e19a929` | `f184c459b6f77a5bef65e18cafaa25f8dbd73d5af3df8202f149776c160ad397` |
| BTCT | `30de4a17283d4d199028a577906da04a` | `c850957edeeb40c6a9ad181dc29534e1` | `a7ec682e34c44abc9f333ffc4dc01637` | `9cff6130a1e586f154089ed143a618ce4b43efcb0d437021087d37153fb6d88f` |
| CBL | `ad7258e8580c4843a0212f4945bf8912` | `7863a09f2b6742bf848c5fa01d3dc38f` | `4a74f74be91f46b3ab49b6490121440d` | `2419fcdc36d52634c0a29e2852355b01e7bf4fa477d9673f79058067039c662d` |
| JBGS | `11e52f2013c048da8ec390cea79c0c24` | `6131224ee6874259a1c7762c9711a9ee` | `d50cda1cf4194fe59fb95f3cc604f5d0` | `e15d8a96b60d909950dfbe4c4d3cc821909fdb4ec0a06d0c0378e657aafc2eab` |
| NFE | `e71af0c4f7b647908465048cebd27906` | `fa8d144d6a134b80a0b9659e18ceb80a` | `62369f4d3de84d43a0d8a50c7acb3cbf` | `52eaf5b75a02cbad94730e02bf19df5c8549582b0f6b5f152b213db06781ebcb` |
| NUWE | `d7b49ba7eec845eabe0170057a2eb024` | `f89e50fc5e554bbe9ead681c365c190b` | `90ba8dc5d60b4a9e849a229544dbe31f` | `a83751a10fd1df81a27b294551b2609f1c737cd2a71473888df7ea8b0ba69382` |
| SIDU | `39cc692581344920834c4408db35d625` | `32daeb8545b845b5a57954605f25711f` | `269ba122fc7e477180f55712dee8db4a` | `f3d60441aa11f289b86a14209287fa5f0f3ea12eec620b78db098b83d6f46cf1` |
| SIGA | `c4619b3e784b442c9ad44b26316da8d8` | `f531bdb8fa58485d876c00ff3358c00e` | `5b5544f1c8b548389836e8a7940a4bd9` | `5746c195b2ff2f1c9728566c06ecffae4f096aab301d623d69785bc1a77037dc` |
| VEEE | `db908a128f1f4bf69b2ceb5ecfbac189` | `7a16189f8d744e878f1c9ab961f2435d` | `743fb57bcda54969a53fc68b44503cb4` | `e208aa0694e44057b8cb9247a644946d6fc2e602deebfd263ba12f9d73520ea5` |

## 3. Live Re-probe

Two serial rounds used `YahooForecastTransport` with the normal raw transport
boundary, 0.75-second minimum request spacing, normal retry policy, and no
repository or database call:

| Round | UTC interval | Requests | HTTP | Attempts | Result |
|---|---|---:|---|---|---|
| 1 | 13:20:37-13:20:44 | 11 | all 200 | all 1 | all hashes equal production |
| 2 | 13:20:49-13:20:57 | 11 | all 200 | all 1 | all hashes equal production |

The payload for every symbol is byte-stable over three production observations
and two live observations. No row normalized, no `period` disappeared, and no
new usable incomplete-target row appeared.

## 4. Row-Level Inventory

Every payload has methodology `nongaap`, four rows in source order
`0q, +1q, 0y, +1y`, and all expected estimate/trend/revision sections. No row
has an absent, null, empty, or invalid `period`. `endDate` is either a valid ISO
date or explicit null; no absent, empty-string, wrong-type, or invalid-date
state occurs.

An `EMPTY` row below is the exact accepted placeholder: all earnings, trend,
revision, growth, and currency values are empty/null, while revenue
avg/low/high/analyst count use Yahoo's zero/null/`"0"` wrapper. Those zeros are
not usable estimates. `USABLE` means at least one non-placeholder semantic
value is present.

| Symbol | Row structure in provider order | Usable horizons |
|---|---|---|
| ATLX | `0q/null EMPTY; +1q/2026-06-30 EMPTY; 0y/2026-12-31 USABLE; +1y/2027-12-31 EMPTY` | `0y` |
| BHP | `0q/null EMPTY; +1q/null EMPTY; 0y/2027-06-30 USABLE; +1y/2028-06-30 USABLE` | `0y,+1y` |
| BIVI | `0q/2025-12-31 EMPTY; +1q/null EMPTY; 0y/2026-06-30 USABLE; +1y/2027-06-30 USABLE` | `0y,+1y` |
| BTCT | `0q/null EMPTY; +1q/null EMPTY; 0y/2026-12-31 USABLE; +1y/null EMPTY` | `0y` |
| CBL | `0q/null EMPTY; +1q/null EMPTY; 0y/2026-12-31 USABLE; +1y/null EMPTY` | `0y` |
| JBGS | `0q/null EMPTY; +1q/null EMPTY; 0y/2026-12-31 USABLE; +1y/2027-12-31 USABLE` | `0y,+1y` |
| NFE | `0q/null EMPTY; +1q/2026-12-31 EMPTY; 0y/2026-12-31 USABLE; +1y/2027-12-31 USABLE` | `0y,+1y` |
| NUWE | `0q/2026-06-30 EMPTY; +1q/null EMPTY; 0y/2026-12-31 USABLE; +1y/2027-12-31 EMPTY` | `0y` |
| SIDU | `0q/null EMPTY; +1q/null EMPTY; 0y/2026-12-31 EMPTY; +1y/2027-12-31 USABLE` | `+1y` |
| SIGA | `0q/null EMPTY; +1q/null EMPTY; 0y/2026-12-31 USABLE; +1y/2027-12-31 USABLE` | `0y,+1y` |
| VEEE | `0q/null EMPTY; +1q/null EMPTY; 0y/2026-12-31 USABLE; +1y/null EMPTY` | `0y` |

## 5. Distinct Provider Shapes

All belong to one semantic class,
`MIXED_TARGETED_DATA_AND_EMPTY_INCOMPLETE_ROWS`, with four target-state
subshapes:

| Missing `endDate` horizons | Symbols | Stability |
|---|---|---|
| `0q` | ATLX, NFE | identical across five observations |
| `+1q` | BIVI, NUWE | identical across five observations |
| `0q,+1q` | BHP, JBGS, SIDU, SIGA | identical across five observations |
| `0q,+1q,+1y` | BTCT, CBL, VEEE | identical across five observations |

There is no `PERIOD_MISSING_*`, no stale or invalid target string, no
structurally invalid section, and no row combining a usable semantic value
with missing target metadata.

## 6. Usable-Value And Coverage Inventory

The 44 provider rows contain 16 usable, fully targeted annual rows and 28 exact
empty placeholders. Twenty-one of the empty rows have null `endDate`; seven
empty rows have a valid target. The usable inventory is:

| Symbol | Rows | EPS | Revenue | Analyst counts | EPS trend | Revisions | Growth | Currencies |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ATLX | 1 | 4 | 4 | 2 | 5 | 4 | 3 | 4 |
| BHP | 2 | 8 | 8 | 4 | 10 | 8 | 6 | 8 |
| BIVI | 2 | 8 | 8 | 4 | 10 | 8 | 6 | 8 |
| BTCT | 1 | 4 | 3 | 2 | 5 | 4 | 1 | 4 |
| CBL | 1 | 3 | 3 | 2 | 5 | 4 | 0 | 4 |
| JBGS | 2 | 0 | 8 | 2 | 0 | 0 | 2 | 2 |
| NFE | 2 | 8 | 6 | 4 | 10 | 8 | 4 | 6 |
| NUWE | 1 | 0 | 4 | 1 | 0 | 0 | 1 | 1 |
| SIDU | 1 | 0 | 3 | 1 | 0 | 0 | 0 | 1 |
| SIGA | 2 | 8 | 8 | 4 | 10 | 8 | 6 | 8 |
| VEEE | 1 | 3 | 3 | 2 | 5 | 4 | 0 | 4 |
| **Total** | **16** | **46** | **58** | **28** | **60** | **48** | **29** | **50** |

Currency observations are 46 USD and four CNY fields; the CNY fields are the
BTCT `0y` row. Counts include numeric zero only when it occurs in a non-empty
usable row. Empty-template revenue zero wrappers are excluded.

Current persisted provider-usable coverage for these responses is 0 symbols
and 0 rows because the whole fetch is malformed. A future mixed-row contract
could add 11 symbols and 16 provider-usable rows. All 11 acquisition-time
identities resolve. A read-only evaluation of the existing V1 fiscal-linker
against only the 16 complete rows returned `LINKED` for all 16. This is a
hypothetical coverage estimate, not persisted link coverage: actual
fiscal-target-resolved coverage remains 0 until a versioned observation is
successfully acquired and linked. The 21 incomplete empty rows contribute no
provider-usable or target-resolved coverage.

## 7. Acquisition Versus Linking

The current acquisition classification is correct under V1: the payload is
neither exact whole-payload no-data nor valid V1 canonical data, so it remains
`MALFORMED_OR_SCHEMA_MISMATCH`. It must not become `VALID_NO_DATA`, because 16
rows contain real estimates.

The proposed `SUCCESS_WITH_DATA + sparse UNRESOLVED` interpretation is not
supported by the evidence. There is no usable sparse row to preserve or link.
For a future mixed-row contract, acquisition could be `SUCCESS_WITH_DATA`, the
16 complete rows could enter ordinary linking, and the incomplete empty rows
would produce neither estimates nor fiscal-link attempts. A truly usable row
with missing `period` or `endDate` must remain malformed until separately
observed and designed; no target may be inferred.

## 8. Schema And Contract Options

### A. Make `forecast_estimate` target columns nullable

Rejected for this evidence. `provider_horizon` and `provider_end_date` are
currently non-null, but no usable observed row needs null storage. Relaxing
them would weaken the normal-row invariant without preserving any additional
semantic value.

### B. Add an unresolved sparse-row table

Rejected for this evidence. Such a table would contain only empty placeholders
for the observed payloads. It may become appropriate after a real usable
incomplete-target row is captured.

### C. Version a mixed-row canonical contract

Recommended for a separate reviewed implementation task, not implemented here.
A repository-consistent name would be
`yahoo_earnings_trend_v2_mixed_empty_targets`. It should preserve all four rows
and their order in canonical JSON, encode explicit target field states, mark
each row `EMPTY_PLACEHOLDER` or `USABLE_TARGETED`, and normalize only complete
usable rows into the existing non-null `forecast_estimate` schema. This model
needs no schema migration for the evidence observed here.

Normal fully targeted payloads must continue to use
`yahoo_earnings_trend_v1`. Existing V1 snapshots and hashes must not change.
The new contract version necessarily produces a different semantic hash for
new mixed observations; that is explicit and preferable to silently changing
V1 hash semantics. Historical malformed fetches remain untouched and have no
snapshot to reinterpret.

## 9. Fiscal Linker And PIT Semantics

Under the proposed future mixed contract, only complete usable rows are handed
to the existing linker. No missing target is invented, no nearest-date rule is
added, and empty rows do not get artificial `UNRESOLVED` links. The current
linker's read-only result for the 16 complete rows is 16 `LINKED`, but actual
status must be produced only from a future persisted fetch.

Earlier malformed observations remain malformed as-known. A later V2 mixed
observation can be acquired and linked without rewriting them. Current
reconciliation may only operate on that later persisted observation under the
existing append-only rules.

Future PIT callers would query the V2 snapshot by provider/identity/fetch time
to see the complete provider observation as known at T. Fiscal FY/Q queries
would see only normalized rows with complete provider targets and persisted
link evidence. If a genuinely usable incomplete-target row is observed later,
it needs a separate unresolved sparse query surface keyed by provider,
fetch/snapshot, occurrence index, and explicit target states; normal FY/Q
queries must exclude it until append-only link evidence exists.

## 10. Fixtures And Tests

Four compact real fixtures cover every observed missing-`endDate` subshape:

- `mixed_empty_missing_enddate_0q_atlx.real_compact.json`
- `mixed_empty_missing_enddate_1q_bivi.real_compact.json`
- `mixed_empty_missing_enddate_0q_1q_bhp.real_compact.json`
- `mixed_empty_missing_enddate_0q_1q_1y_btct.real_compact.json`

Metadata records source symbol, first observation, production/live observation
counts, full provider raw SHA-256, missing horizons, and absent missing-period
evidence. Fixtures preserve row order, null/date distinctions, methodology,
all representative usable values, and contain no cookie, crumb, session,
header, or unrelated provider data.

Focused tests prove that incomplete rows are exact empty placeholders, usable
rows are target-complete, mixed payloads are neither V1 success nor no-data,
strict V1 canonicalization still rejects them, unknown fields remain visible
and malformed, normal V1 success is unchanged, and exact whole-payload empty
templates remain `VALID_NO_DATA`.

## 11. Production And Scheduler Safety

No acquisition, parser, persistence, schema, fiscal-link, PIT, scheduler,
pacing, retry, concurrency, timeout, or Fundamentals runtime code changed.
The two probes never called `ForecastRepository`. Production history retains
all 33 original malformed fetches and raw references. Scheduler operation
should continue unchanged; the stable 11 malformed outcomes remain an expected
known limitation until a separately reviewed mixed-row V2 is implemented.

## 12. Unresolved Issues And Exact Next Step

There is still no evidence defining semantics for a row that combines usable
values with absent/null/invalid `period` or `endDate`. Do not implement
`yahoo_earnings_trend_v2_sparse` or an unresolved-target table without such
evidence.

The exact next step is a separate implementation review for
`yahoo_earnings_trend_v2_mixed_empty_targets`: fixture-drive a canonicalizer
that preserves all row states, normalizes only the 16-equivalent complete
usable rows, keeps normal V1 hashes unchanged, and verifies persistence and
linking exclusively on temporary databases before any targeted production
observation. Historical malformed rows must not be backfilled or rewritten.
