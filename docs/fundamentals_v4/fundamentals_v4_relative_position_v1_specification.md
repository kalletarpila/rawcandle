# Fundamentals V4 Relative Position V1 Specification

## Model identity

- Model version: `CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V1`
- Semantic mode: `CURRENT_REVISED_SNAPSHOT`
- Model fingerprint: `983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2`

Relative Position V1 is a separate comparison layer. It does not modify, reweight, or feed back into Fundamental Score V1, Fundamental Trajectory, Lifecycle V1, or Absolute Valuation Score V1.

It is not a prediction, historical PIT rank, survivorship-free historical rank, or combined investment score.

## Measures and scopes

V1 ranks only total scores:

- `FUNDAMENTAL_SCORE`
- `ABSOLUTE_VALUATION_SCORE`

The only peer scopes are:

- `UNIVERSE`
- `SECTOR`
- `INDUSTRY`
- `ECOSYSTEM`

There is no `TAXONOMY_LAYER` scope. V1 does not rank components or raw valuation yields and does not combine the two measures.

## Eligibility

The snapshot requires an explicit as-of date. Each measure independently selects the latest source observation available on or before that date and applies a maximum age of 180 calendar days.

Fundamental ranking includes only fresh `SCORE_FULL` observations from the canonical Fundamental Score model fingerprint. `SCORE_LIMITED`, `SCORE_NOT_READY`, stale, missing, and invalid observations do not enter any Fundamental denominator.

Valuation ranking includes only fresh `VALUATION_FULL` rows from the persisted filing-date Absolute Valuation model fingerprint. `VALUATION_NOT_APPLICABLE`, `VALUATION_NOT_READY`, stale, missing, and invalid observations do not enter any Valuation denominator. Current-day repricing is not part of this model.

There is no imputation, dynamic reweighting, shared Fundamental/Valuation denominator, or cross-measure fallback.

## Identity and classifications

`company_id` is the ranking identity. The source chain is:

```text
source result -> quarter/company_id -> observation security_id
-> security.current_ticker -> current ticker_meta sector/industry
-> active taxonomy ticker membership -> peer groups
```

Ticker is a current lookup key and audit field, not company identity. The adapter prefers the observation's valid company-owned `security_id`; only a unique active company security is an allowed fallback. Duplicate company/measure inputs and duplicate Fundamental source rows are rejected.

Sector and industry come from current `data/osakedata.db.ticker_meta`. Values are trimmed; SQL null, blank, and case-insensitive `NULL`, `NONE`, `N/A`, `NA`, `UNKNOWN`, and `UNCLASSIFIED` are missing. Other labels are preserved exactly. These classifications are current-snapshot data, not PIT-versioned history.

## Ecosystem membership

Taxonomy comes from active versions in `data/analysis.db`. A membership qualifies only when its role is `CORE` or `EXTENDED`. `WATCH_ONLY` is excluded.

A company is included once per measure and ecosystem even if it has duplicate memberships, several qualifying roles, or several taxonomy-layer records. A company in different ecosystems receives one result per distinct ecosystem. No best ecosystem is selected, and taxonomy layers never form ranking groups.

## Percentile mathematics

Scores rank ascending, so a higher absolute score produces a higher relative percentile. Exact ties use average rank:

```text
rank_low = 1 + count(score < x)
rank_high = count(score <= x)
average_rank = (rank_low + rank_high) / 2
percentile = 100 * (average_rank - 1) / (peer_count - 1)
```

The persisted-calculation representation is a Python/SQLite-compatible finite binary64 value serialized by canonical JSON using its shortest round-trip representation. Values are not rounded before ranking or in engine output. Exact numeric equality defines a tie; input order, ticker, company id, and database order never break one.

`None`, NaN, infinity, booleans, non-numeric values, and values outside 0...100 are invalid and do not enter peer groups. Canonical JSON uses `allow_nan=False`.

## Peer minimums

| Scope | Minimum eligible peers |
|---|---:|
| `UNIVERSE` | 2 |
| `SECTOR` | 20 |
| `INDUSTRY` | 10 |
| `ECOSYSTEM` | 20 |

Below minimum, `percentile` is null, status is `PEER_GROUP_TOO_SMALL`, peer-group identity and peer count remain available, and there is no fallback.

## Output and statuses

Each ranking row contains model/snapshot/source identities, company/security/ticker evidence, measure, scope, group id, source observation identity/date, score, percentile, rank interval, average rank, peer count, tie count, status, and reason.

Actual group members receive ranking rows, including too-small groups. Missing or ineligible expectations are represented in separate coverage/audit records instead of fake peer-group rows.

Statuses are:

- `RELATIVE_POSITION_READY`
- `SOURCE_MEASURE_NOT_ELIGIBLE`
- `PEER_CLASSIFICATION_MISSING`
- `NOT_ECOSYSTEM_MEMBER`
- `PEER_GROUP_TOO_SMALL`
- `INVALID_SOURCE_VALUE`
- `IDENTITY_MAPPING_UNRESOLVED`

## Fingerprints

The model fingerprint covers the measures, four scopes, exact formula, numeric behavior, minimums, ecosystem roles/deduplication, statuses, and no-fallback/no-imputation rules.

The source fingerprint covers the snapshot date, freshness policy, selected observations and statuses, source observation/model/result identities, scores, company/security/ticker resolution, current classifications, all attached ecosystem memberships, the current classification content fingerprint, and active taxonomy content/mapping fingerprint.

The result fingerprint covers the complete deterministically ordered ranking and coverage snapshot together with the model and source fingerprints. No calculation timestamp participates in any of these fingerprints.

## Current-only boundary

Existing Fundamental, Lifecycle, and Valuation histories are revised economic histories. Sector and industry are accepted as current-only; taxonomy membership can be revised; and no complete historical PIT classification and peer-membership chain exists. Relative Position V1 therefore exposes only a current revised snapshot.

Phase 4C may add separate persistence, atomic snapshot activation, unchanged-source idempotency, readers, and daily full-snapshot refresh after Fundamental and Valuation updates. Such refresh recalculates only relative positions. It must not rebuild canonical history, TTM, Score, Lifecycle, or Valuation.
