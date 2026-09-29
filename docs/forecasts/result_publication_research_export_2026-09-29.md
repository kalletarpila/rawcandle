# Result-publication research export

Date: 2026-09-29

Projection rule: `result_publication_daily_research_v1`

Decision: `RESULT_PUBLICATION_RESEARCH_EXPORT_READY`

## 1. Composition architecture

The production composition path is a narrow CLI over the existing read-only service:

```text
canonical authority + SEC evidence + security identity (read-only)
observed osakedata calendars (read-only)
optional Yahoo provider/artifact + optional reviewed V2 artifact
                              |
                              v
DailyResearchPublicationService batch API
                              |
                              v
CSV or JSONL + metadata JSON
```

`rawcandle.fundamentals.result_publication_research_export` owns artifact parsing, scope selection, output formatting, hashing, and metadata. `DailyResearchPublicationService` owns assembly. `project_daily_research` remains the sole owner of heuristic decisions.

No research result, Yahoo observation, or V2 selection is written to canonical tables. Normal export performs no SEC network requests because current SEC evidence is already persisted.

## 2. Yahoo production policy

Policy C is adopted:

- `none`: no Yahoo input; safest default;
- `live`: current/ad-hoc research through the narrow yfinance adapter;
- `frozen`: reproducible export from an audited JSON artifact.

EXACT rows and rows without SEC candidates skip Yahoo entirely. A live provider failure is recorded and degrades that quarter through existing SEC-only behavior; it does not stop the batch. Live mode can optionally write exactly the observations requested by the service, plus provider errors, to a frozen artifact.

Frozen mode is recommended for research outputs that must be reproduced later. Yahoo remains secondary research evidence and never creates a canonical or standalone SEC candidate.

## 3. Frozen Yahoo artifact

Version: `result_publication_yahoo_observations_v1`.

Recommended runtime convention:

```text
exports/result_publication/<export-name>.yahoo-observations.json
```

`temp/` is also appropriate for disposable runs. Generated Yahoo artifacts are not committed.

Top-level fields are `artifact_version`, `created_at_utc`, `projection_rule_version`, `source_scope`, `observations`, and `provider_errors`. Every observation contains stable quarter identity, ticker used, timezone-aware Yahoo timestamp, timezone, observation timestamp, provider `YAHOO_FINANCE`, and transport `yfinance`.

Parsing is strict: version/rule/provenance/timestamps/quarter identity are validated, and duplicate observations are rejected. The live writer deduplicates identical provider rows before creating an artifact.

## 4. Reviewed V2 artifact

Version: `result_publication_v2_candidates_v1`.

The current reviewed production input is:

`data/research/result_publication/v2_candidates_initial_result_sec_semantic_v2_research_2026-09-29.json`

It contains 83 accepted rows keyed by `(company_id, fiscal_year, fiscal_quarter)`, with selected candidate/accession, SEC reference, UTC timestamp, classifier version, review status, and review timestamp.

Before any export, every V2 row must exactly match a current quarter-scoped SEC evidence row with accepted/conflict disposition, identifier, timestamp, and reference. A stale or malformed artifact fails before output; the service projection independently ignores any candidate identifier that does not match current evidence. V2 is not recomputed or applied to canonical authority.

## 5. CLI usage

Module:

```text
python3 -m rawcandle.cli.result_publication_research_export
```

Single ticker:

```bash
python3 -m rawcandle.cli.result_publication_research_export \
  --output exports/result_publication/aapl.csv \
  --tickers AAPL
```

Full usable FY2025+ CSV with frozen Yahoo and reviewed V2:

```bash
python3 -m rawcandle.cli.result_publication_research_export \
  --output exports/result_publication/fy2025_plus.csv \
  --yahoo-mode frozen \
  --yahoo-observations exports/result_publication/reviewed.yahoo-observations.json \
  --v2-candidates data/research/result_publication/v2_candidates_initial_result_sec_semantic_v2_research_2026-09-29.json
```

Live ad-hoc export with a reproducibility artifact:

```bash
python3 -m rawcandle.cli.result_publication_research_export \
  --output exports/result_publication/live.jsonl \
  --format jsonl \
  --yahoo-mode live \
  --write-yahoo-observations exports/result_publication/live.yahoo-observations.json
```

`--tickers` accepts one or multiple comma/space-separated tickers. `--company-ids`, `--from-fiscal-year`, and `--to-fiscal-year` provide stable identity/year scope. UNUSABLE is excluded by default and included only with `--include-unusable`.

## 6. Output columns

CSV and JSONL expose:

- company ID, ticker, fiscal year/quarter;
- research status, confidence, method, publication date/session/effective day;
- canonical status/timestamp and `is_canonical`;
- selected candidate timestamp/reference;
- Yahoo timestamp/date/trading-day distance;
- projection rule version and shared warning.

The existing warning constant is reused. Every heuristic row has `is_canonical=false`; warning prose is not duplicated in the CLI.

## 7. Reproducibility

Every export writes `<output>.metadata.json` by default, or the requested `--metadata-output`. It records:

- generation timestamp and projection rule;
- canonical and OHLC paths and SHA-256 hashes;
- Yahoo mode/artifact path/hash/row count or live observations/errors;
- V2 path/hash/row count;
- ticker/company/fiscal/status filters;
- evaluated/exported rows and status counts;
- output format/path/SHA-256.

Frozen input, unchanged source databases, fixed filters, and the same projection version produce deterministic CSV/JSONL content. Large raw source payloads are not embedded in output rows.

## 8. Validation decomposition

All four modes evaluated the same 16,210 FY2025+ production quarters through the CLI batch path:

| Inputs | EXACT | HIGH | MEDIUM | UNUSABLE |
|---|---:|---:|---:|---:|
| Frozen Yahoo + reviewed V2 | 12,782 | 570 | 0 | 2,858 |
| No Yahoo, no V2 | 12,782 | 11 | 8 | 3,409 |
| Frozen Yahoo only | 12,782 | 565 | 0 | 2,863 |
| Reviewed V2 only | 12,782 | 87 | 6 | 3,335 |

The no-secondary-source MEDIUM rows are narrow SEC local clusters. Frozen Yahoo consumes or rejects those cases before the SEC-only fallback. V2 contributes 76 HIGH rows beyond the 11 same-effective-day rows. Together Yahoo and V2 reproduce the accepted 13,352 usable rows.

Representative output semantics were confirmed:

- AAPL 2026-Q3: EXACT, AFTER_MARKET 2026-07-30 -> 2026-07-31;
- NVDA 2027-Q2: EXACT, AFTER_MARKET 2026-08-26 -> 2026-08-27;
- CF 2025-Q1: HIGH / same effective day -> 2025-05-08, no fabricated exact timestamp;
- ABG 2025-Q1: Yahoo HIGH, PRE_MARKET 2025-04-29 -> 2025-04-29;
- ORN 2025-Q3: Yahoo HIGH, PRE_MARKET 2025-10-29 -> 2025-10-29;
- DTE 2025-Q1: V2 HIGH, PRE_MARKET 2025-05-01 -> 2025-05-01;
- GSIT 2026-Q2: V2 HIGH with Yahoo unavailable, AFTER_MARKET 2025-10-30 -> 2025-10-31;
- sampled UNRESOLVED and NOT_FOUND: UNUSABLE / no SEC candidate.

## 9. Performance

The full frozen-Yahoo plus reviewed-V2 CLI export, including 16,210 CSV rows, both database hashes, artifact validation/hashes, metadata, and file writing, completed in 11.13 seconds on the current host. This remains in the same performance class as the underlying 10.37-second service validation.

The CLI calls the service batch API once. Connections, ticker calendars, and provider mappings are reused. Live full-universe mode is intentionally serial and can be much slower because its runtime depends on Yahoo; no concurrency was added.

## 10. Safety

Before and after implementation and all exports:

- `data/fundamentals_v4.db` SHA-256 remained `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`;
- authority remained 12,782 VERIFIED, 864 UNRESOLVED, 651 AMBIGUOUS, 1,913 NOT_FOUND;
- evidence remained 12,782 ACCEPTED and 1,318 CONFLICT;
- canonical `quick_check=ok` and foreign-key errors remained zero;
- `data/forecasts.db` SHA-256 remained `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`;
- no forecast scheduler, systemd unit, migration, or canonical resolver was changed.

SQLite source connections use URI `mode=ro` and `query_only=ON`. Only requested export, metadata, and optional Yahoo artifact paths are writable.

## 11. Limitations

- Yahoo live availability and history can change; use frozen mode for reproducibility.
- The reviewed V2 artifact is a point-in-time input and must be rebuilt/re-reviewed when canonical SEC evidence changes.
- Full live Yahoo export has not been used as a timing benchmark and is expected to be provider-bound.
- The export is current-state research output, not a historical chain of prior projections.
- JSONL and CSV are research artifacts, not canonical evidence or precision event-study data.

## 12. Recommended operational use

Use no-Yahoo mode for a minimal canonical/SEC-only export, frozen Yahoo plus the reviewed V2 artifact for repeatable broad coverage, and live mode only for ad-hoc refreshes that also write a frozen observation artifact. Keep the metadata sidecar with every retained export.

Default output should remain usable-only. Include UNUSABLE rows for QA/audit exports, not downstream signal generation.

## 13. Next step

Gate: `RESULT_PUBLICATION_RESEARCH_EXPORT_READY`.

The exact next step is to run one named frozen production export under `exports/result_publication/`, retain its CSV/JSONL, Yahoo observation artifact, and metadata sidecar together, and wire that explicit export path into the first downstream daily-OHLC research job. The downstream job must filter to EXACT/HIGH/MEDIUM, preserve `is_canonical` and warning fields, and never feed heuristic values back into canonical Fundamentals or forecast workflows.
