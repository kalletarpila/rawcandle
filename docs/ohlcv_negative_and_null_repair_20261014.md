# Targeted Yahoo OHLCV verification and repair — 2026-10-14

Historical report of the October 14 operation. Counts and verification results describe that operation, which was not rerun when this document was committed. Linked provider evidence and repair receipts are retained locally and are excluded from this documentation commit.

## Outcome

**Verified partial repair:** updated only the existing USA rows **SPCX / 2026-07-28** and **SKHY / 2026-07-28**. No rows inserted or deleted. All **988 NFE** and **595 VATE** affected rows remain negative in current Yahoo `auto_adjust=True` responses and were left unchanged. No raw-price fallback, rescaling, interpolation, full-history refresh or downstream recalculation was used.

| Ticker / original affected period | Original anomalies | Valid current Yahoo target rows | Still invalid | Missing Yahoo target rows | Approved / updated | Anomalies after |
|---|---:|---:|---:|---:|---:|---:|
| NFE / 2019-01-31–2022-12-30 | 988 negative | 0 | 988 | 0 | 0 | 988 negative |
| VATE / 2018-01-02–2020-05-13 | 595 negative | 0 | 595 | 0 | 0 | 595 negative |
| SPCX / 2026-07-28 | 1 NULL-OHLC | 1 | 0 | 0 | 1 | 0 |
| SKHY / 2026-07-28 | 1 NULL-OHLC | 1 | 0 | 0 | 1 | 0 |
| **Total** | **1,585** | **2** | **1,583** | **0** | **2** | **1,583** |

Original anomalies were verified directly using read-only SQLite before provider retrieval. Production updates were authorized only after all gates were satisfied for the two NULL rows. Ordinary Yahoo preservation policy, normal collection, missing-day recovery, split handling, scheduling and schemas are unchanged.

## Phase A: acquisition and complete interval review

Reference reports: [zero-price audit](ohlcv_zero_price_audit_20261014.md), [DEC investigation](ohlcv_missing_day_dec_investigation_20261014.md). Existing normal acquisition and persistence were inspected in `main.py`, `services/stock_update_service.py`, `services/missing_day_recovery.py`, `analysis/splits_price_backfill.py`, and the local reviewed identity registry. Investigation SQL connections used `mode=ro` and `PRAGMA query_only=ON`.

The existing normal Ticker factory, `split_fetch_date_range`, `fetch_history_for_date_ranges`, `convert_histories_to_ohlcv_rows`, range pause and legacy ticker/batch sleeps were reused. A task-local wrapper added **only `auto_adjust=True` explicitly** to each normal `stock.history(start,end)` call. All other defaults, conversion, rate-limit/retry behavior and application code remained unchanged. yfinance version: **0.2.66**. Evidence creation timestamp: **2026-10-14T15:35:47.058522+00:00** (UTC).

Exactly **nine bounded history invocations**, with exclusive end dates:

| Ticker | Start inclusive | End exclusive | Converted provider rows |
|---|---|---|---:|
| NFE | 2019-01-24 | 2020-01-24 | 247 |
| NFE | 2020-01-24 | 2021-01-23 | 252 |
| NFE | 2021-01-23 | 2022-01-23 | 252 |
| NFE | 2022-01-23 | 2023-01-10 | 242 |
| VATE | 2017-12-26 | 2018-12-26 | 251 |
| VATE | 2018-12-26 | 2019-12-26 | 252 |
| VATE | 2019-12-26 | 2020-05-21 | 101 |
| SPCX | 2026-07-21 | 2026-08-05 | 11 |
| SKHY | 2026-07-21 | 2026-08-05 | 11 |

Requests cover affected intervals plus small boundary context only, not complete histories to the present. The seven longer calls follow existing 365-day partitioning for intervals over 730 days. Both short requests cover July 21–August 4. There were no duplicate converted dates, acquisition failures, retries initiated by this task, `auto_adjust=False` calls or other-provider calls. Nine history invocations are not an assertion of nine HTTP requests: yfinance manages metadata, caching and transport internally. The existing nonblocking stock-update operation lock was held during retrieval and acquired again for the controlled write; no running task was interrupted.

### NFE: no recovery

All 988 specified rows were returned, with **all four OHLC fields negative in every row**. Every target's OHLC is numerically compatible with stored values at `math.isclose(rel_tol=1e-6, abs_tol=1e-6)` and every target volume matches exactly. This tolerance was used only to describe provider/stored differences, not to permit negative replacements or relax a gate.

Examples from current adjusted Yahoo responses:

- 2019-01-31: open `-1.376005254931671`, high `-1.431045437398142`, low `-1.339657906695412`, close `-1.3573123216629028`, volume `4047000`.
- 2022-12-30: open `-18.60498219996642`, high `-19.062041211320604`, low `-18.533286769323837`, close `-19.008268356323242`, volume `837800`.

There is no earlier stored observation before the interval's start, and Yahoo returned none in the requested preceding context. Its current first-trade date and local provider first-price date both identify 2019-01-31. Five valid right-side controls, January 3–9, 2023, match stored OHLC within numerical precision and volume exactly; the largest relative OHLC difference is approximately `7.42e-8` (fraction).

Yahoo action fields include a dividend value **150.0 on 2023-01-03**, the first positive boundary session, and ten earlier dividend entries of 5.0 in the retrieved interval. No split event occurs in that requested window. Local `splits_data` records a later **0.02 split on 2026-09-14**, marked corrected. These are observed provider/local action records, not independent verification of cash amounts in original historical units. A distribution/adjustment-factor issue is plausible; its cause cannot be proven from auto-adjusted responses alone. No action was recalculated or applied.

**Gate failure:** strict positivity fails for the entire interval; negative multiplication also gives reversed high/low relationships. No complete or partial repair qualifies. Right-boundary agreement does not turn the negative observations into valid replacements.

### VATE: no recovery

All 595 specified rows were returned with **all four OHLC fields negative in every row**. Target OHLC agrees numerically with stored observations at the same descriptive tolerance, and target volumes match exactly.

Examples:

- 2018-01-02: open `-17.284770366574122`, high `-17.544042361647175`, low `-17.255962855537604`, close `-17.428810119628906`, volume `7580`.
- 2020-05-13: open/high `-9.794702598250874`, low `-8.613576586803488`, close `-8.700000762939453`, volume `50740`.

The stored dataset begins on the affected start date, so no stored left-side control exists. Yahoo returned four additional preceding sessions, December 26–29, 2017; these were evidence only and were not inserted. Five valid right-side controls, May 14–20, 2020, match stored OHLC and volume exactly.

Yahoo records a dividend value **38.9 on 2020-05-14**, coinciding with the negative-to-positive boundary. Local splits record **0.1 on 2024-08-09**, marked corrected; no split occurs in the fetched interval. These facts support investigating action/adjustment provenance, but do not prove the dividend value caused the negative historical prices or establish an alternative correct basis.

**Gate failure:** all replacement candidates fail positivity and ordering. Historical alias continuity is also not fully dated locally: provider related tickers include `PTGI HCHC PMUG`; these strings were not used to reconstruct or certify predecessor history. No complete or partial repair qualifies.

## Identity and price-basis gates for the two approved rows

NFE and VATE have unique current canonical routes (security IDs 1543 and 2300), corroborated by local SHARADAR permatickers 111638 and 197117, but undated security starts. Yahoo reports their exact symbols, EQUITY type, New York timezone and matching current issuer names. This is corroborating current identity evidence, not exhaustive historical point-in-time certification. Their numerical failure independently prevents any repair.

SPCX and SKHY are absent from current canonical Fundamentals, which is not an acceptance prerequisite for this general maintenance task. Their exact July 2026 identities are corroborated by **all** the following:

- Exact Yahoo symbols `SPCX` / `SKHY`, EQUITY type, New York exchange timezone, USD and Nasdaq `NMS` exchange metadata; no reviewed registry conflict at the target date.
- Local provider stocks metadata identifies **SPACE EXPLORATION TECHNOLOGIES CORP** (permaticker 6399411, Domestic Common Stock) and **SK HYNIX INC** (6399698, ADR Common Stock), respectively, Nasdaq and not delisted. No aliases were used as price history.
- Yahoo first-trade dates, local provider first-price dates and first stored rows all agree: **2026-06-12 for SPCX**, **2026-07-10 for SKHY**. The target is after these dates, in the current July history, not an extension into a predecessor's period. No earlier stored route or mixed-market history was needed to assign these observations.
- Both dates immediately surrounding the target, **July 27 and July 29**, have valid stored bars and **exactly matching current Yahoo OHLC**. All ten control closes and nine of ten full control OHLC bars match exactly for each ticker. No stored split or fetched dividend/split event exists in the short windows.

Wider context has localized revisions: SPCX August 3 open changes from `106.42500305175781` to `106.4000015258789`; SKHY August 3 open changes from `139.7100067138672` to `139.9199981689453` and high from `144.16000366210938` to `144.1699981689453`. Close and other fields continue matching. These isolated field differences, with exact immediate neighbors, support the same adjusted-price basis rather than a systematic scale change; their precise revision cause is not proven. Those control rows were **not modified**.

Volumes match on the five preceding controls but differ on the five following controls. All exact revisions are retained in the manifest. Volume disagreement was not silently interpreted as exact OHLC adjustment disagreement: the user gates require finite nonnegative replacement volume, not identical neighboring volume. Current Yahoo target volumes were adopted explicitly as part of the approved OHLCV records. No convention or acceptance threshold in application code was changed.

Every approved row passed: exact existing ticker/USA/date and verified NULL anomaly; exact returned date/ticker/market; sufficiently corroborated target-period identity; finite strictly positive OHLC and valid high/low relationships; finite nonnegative volume; explicit `auto_adjust=True`; surrounding valid price-basis compatibility/action checks; unchanged original row rechecked within the write transaction. No gate was waived for NFE/VATE.

## Exact replacements and manifest

[Approved manifest](../outputs/ohlcv_targeted_verification_20261014/approved_repair_manifest.json) retains full original rows, exact new values, identity evidence, immediate neighbors, wider revisions and validation outcomes. SHA-256:

`ac025b5c0a62e776fe4564ff2632ec93a04d4a8dad0c2deb1194c73c89c09f7d`

Both original target rows had open/high/low/close **NULL**. Their original volumes were **80,968,276 for SPCX** and **44,965,601 for SKHY**.

| Ticker / 2026-07-28 | New open | New high | New low | New close | New volume |
|---|---:|---:|---:|---:|---:|
| SPCX | 109.31999969482422 | 118.12999725341797 | 107.01000213623047 | 116.41000366210938 | 81714300 |
| SKHY | 135.91000366210938 | 136.49000549316406 | 128.2899932861328 | 130.1699981689453 | 51088300 |

No full database backup/copy was created. The narrowly scoped manifest preserves the two old rows for audit and possible controlled recovery; it is not a database snapshot. It and the provider evidence are retained. No backup, Restic retention, WAL or SHM file was deleted or changed by cleanup.

## Controlled write and verification

A single small **two-row `BEGIN IMMEDIATE` transaction** performed only parameterized UPDATEs. The approved key set was fixed to those two ticker/date/USA triples. Before writing, the helper refused triggers, compared each complete original row to the manifest, and rechecked immediate stored neighbor OHLCV. SQL predicates additionally required original ID, ticker/date/market and original OHLCV, using NULL-safe `IS ?` comparisons. Rowcount had to equal one per UPDATE.

Only open/high/low/close/volume changed. IDs **15027002 (SPCX)** and **15026971 (SKHY)**, ticker/date/market, sector/industry and all database structures remain unchanged. No acquisition took place inside the write transaction. A SQLite authorizer denied INSERT, DELETE, schema changes and UPDATEs outside OHLCV columns of `osakedata`; the fixed SQL/key validation constrained permitted UPDATEs to the two approved rows. The pre/post `data_version` on that connection did not change from an external commit during the operation.

[Verified receipt](../outputs/ohlcv_targeted_verification_20261014/repair_receipt.json) records:

- **Updated 2, inserted 0, deleted 0**; SQLite `total_changes=2`.
- Global rowcount **8,869,834 before and after**.
- The other **4,291 rows belonging to the four target tickers**, including every unapproved NFE/VATE anomaly, have identical pre/post SHA-256: `d6b72b29da34cd8554c557a3600ae4f1de9354e2217e8cd177ba52891658f907`.
- Schema hash is unchanged. Exact full post-write rows equal original rows overlaid only with approved new OHLCV.
- **`PRAGMA quick_check`: `ok`**; `PRAGMA foreign_key_check`: no violations. This is an appropriate whole-database structural check plus targeted value/key verification; a separate full `integrity_check` was not run.

No full-database content hash was taken: evidence of no other changes combines the constant key-restricted SQL, absence of table triggers, authorizer, exactly two changes, unchanged schema/counts, target-ticker hashes and lack of concurrent external commits. No unrelated row can be touched by the executed UPDATE predicates.

[Post-write quality evidence](../outputs/ohlcv_targeted_verification_20261014/post_write_quality.json) independently rechecks the scoped counts through read-only SQL: NFE **988 → 988 negative**, VATE **595 → 595 negative**, SPCX **1 → 0 NULL-OHLC**, SKHY **1 → 0 NULL-OHLC**. The overall audit's zero-price observations were outside the update scope and remain untouched. No broad zero-price rescan or recalculation was needed.

## Tests, diagnostic commands and retained evidence

Task-local scripts were used only for this operation, without modifying application source:

```text
PYTHONPATH=/home/kalle/projects/rawcandle venv/bin/python /tmp/verify_targeted_yahoo_20261014.py
PYTHONPATH=/home/kalle/projects/rawcandle venv/bin/python /tmp/prepare_null_repair_20261014.py
PYTHONPATH=/home/kalle/projects/rawcandle venv/bin/python /tmp/apply_targeted_null_repair_20261014.py
PYTHONPATH=/home/kalle/projects/rawcandle venv/bin/python /tmp/apply_targeted_null_repair_20261014.py --apply
```

The first command performed the nine bounded Yahoo history invocations listed above, with existing pacing and no production writes. The second generated the reviewed approval manifest. The third used **only a small in-memory synthetic SQLite fixture**: successful two-row updates/unaffected columns, stale-manifest/repeat refusal, rollback of the first UPDATE when the second fails, and outside-scope refusal all passed. The final command performed the authorized two-row production transaction and verification. A second production apply was not run; the receipt prevents blind replay, and old-value predicates reject already-repaired rows. No full test suite was run.

Other commands were targeted `sed`/`rg` source reads, `git status --short`, read-only anomaly/context/split queries for the four tickers, local canonical/provider identity queries and pure arithmetic comparisons over retained responses. One preliminary metadata query referenced a nonexistent `cik` column and was corrected; this caused no acquisition or write. No inference relies on that failed query.

Persistent evidence directory: `outputs/ohlcv_targeted_verification_20261014/`:

- `phase_a_evidence.json`: exact old scoped rows, converted adjusted Yahoo rows, action fields, metadata and per-request timestamps/ranges; about 1.6 MB, not a full database copy.
- `phase_a_summary.json`: validity counts, control comparisons and action summaries.
- `approved_repair_manifest.json`: two approved keys and exact old/new values, with excluded classes.
- `repair_receipt.json`: committed/verified result and checksums.
- `post_write_quality.json`: independent scoped after-counts and exact target rows.

## Remaining risks and next action

Do not force NFE/VATE replacements while the required adjusted Yahoo observations remain negative. Their distribution-boundary coincidences warrant a separately scoped source-adjustment investigation; no claim of the true original-unit dividend amounts or repaired historical identity is established here. Do not change `auto_adjust`, apply empirical scale factors or invoke the existing full split refresh as a workaround.

The two NULL rows are repaired and verified; no further write is necessary. Downstream results, if previously computed with missing observations, were intentionally not recalculated. Any recomputation must be separately authorized and narrowly scoped. Normal preservation policy, missing-day recovery, split repair, Fundamentals, Forecasts, SwingMaster, SetupMaster, Analysis Engine and scheduler behavior remain unchanged. Unrelated working-tree changes were preserved; no production database/evidence was staged, and no push was performed.
