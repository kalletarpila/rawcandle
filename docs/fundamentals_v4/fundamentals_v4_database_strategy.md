# Fundamentals V4 Database Strategy

V4 uses three separate databases. No V4 production database is created in V4-0C.

## `data/fundamentals_provider.db`

Owner: fundamentals ingestion/provider layer.

Purpose: provider-side truth and acquisition metadata.

Likely contents:

- provider runs
- provider observations
- Sharadar native rows
- Yahoo event/current observations
- SEC filing/fact observations
- source timestamps and identifiers
- fetch status, retry metadata, and content hashes

Provider disagreements are not canonicalized here.

## `data/fundamentals_v4.db`

Owner: canonical/TTM layer.

Purpose: accepted canonical financial data.

Likely contents:

- company/security mapping
- canonical fiscal quarters
- canonical quarterly financials
- fiscal identity and availability metadata
- field provenance pointers
- quality/readiness metadata
- TTM

TTM belongs here initially because it is a deterministic financial-data derivation from accepted quarterly values, not a model output.

## `data/fundamentals_analysis.db`

Owner: Score/Lifecycle/Valuation layer.

Purpose: derived analytical outputs.

Likely contents:

- Score and score components
- Lifecycle state
- Valuation outputs
- readiness/quality flags used by analysis
- model versions and fingerprints
- later fundamental signals

Analysis must be rebuildable from `fundamentals_v4.db`.

## `analysis.db`

Do not reuse RawCandle's existing `analysis.db` for Fundamentals V4 analytical output. Repo inspection shows it is an existing broad analysis database, and V4 benefits from a dedicated, rebuildable `fundamentals_analysis.db` boundary.
